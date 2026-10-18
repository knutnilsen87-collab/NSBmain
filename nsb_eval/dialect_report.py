"""Bryter ned resultatene på dialekt (eller et annet metadatafelt).

Kjøreren lagrer allerede tall per dialekt i ``summary.json`` (``by_dialect``)
når den kjøres med ``--group-by dialect``. Denne modulen samler dem til én
tabell per testsett, slik at man ser hvilke dialekter modellene sliter med og
hvor stort gapet er mot den beste dialekten.

    python -m nsb_eval.dialect_report --results eval/results --testset nb_samtale_test \
        --testset nb_samtale_test_maalform --out eval/results/DIALECT.md

Tallene er WER summert over alle setninger i gruppen. Små grupper gir usikre
tall; grupper under ``--min-items`` merkes med «*».

Dialekt og målform henger sammen i NB Samtale: «vest» er 89 % og «sørvest»
71 % nynorsk. Sammenlign derfor med kjøringen der nynorsk dekodes som nynorsk
(``nb_samtale_test_maalform``) før gapet tolkes som et dialektproblem.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

__all__ = ["collect_groups", "main", "to_markdown"]

FIELD_TITLES = {"dialect": "dialekt", "standard": "målform", "gender": "kjønn"}

# Faste mål som vises per gruppe: (nøkkel i summary, overskrift).
METRICS = (
    ("wer", "WER"),
    ("deletion_rate", "Utelatelser"),
    ("verbatim_wer", "Ordrett WER"),
)


def collect_groups(results_dir: str | Path, testset: str, field: str = "dialect") -> list[dict]:
    """Én rad per modell med gruppene fra ``by_<field>`` for ett testsett."""
    rows = []
    for path in sorted(Path(results_dir).glob("**/summary.json")):
        s = json.loads(path.read_text(encoding="utf-8"))
        if s.get("testset") != testset:
            continue
        groups = s.get(f"by_{field}")
        if not groups:
            continue
        rows.append(
            {
                "model": (s.get("model") or {}).get("model"),
                "path": str(path),
                "overall": s.get("speech", {}),
                "groups": groups,
            }
        )
    return rows


def _pct(v) -> str:
    return "–" if v is None else f"{100 * v:.1f} %".replace(".", ",")


def _negation(g: dict) -> str:
    c = (g.get("critical") or {}).get("negation")
    if not c or not c.get("reference"):
        return "–"
    return f"{c['missed']}/{c['reference']}"


def gap(row: dict, metric: str = "wer") -> tuple[str, str, float] | None:
    """(beste gruppe, dårligste gruppe, forskjell) for én modell, uten «ukjent»."""
    vals = {k: g.get(metric) for k, g in row["groups"].items() if k != "ukjent" and g.get(metric) is not None}
    if len(vals) < 2:
        return None
    best = min(vals, key=vals.get)
    worst = max(vals, key=vals.get)
    return best, worst, vals[worst] - vals[best]


def to_markdown(rows: list[dict], testset: str, field: str = "dialect", min_items: int = 100) -> str:
    lines = [f"# Resultater per {FIELD_TITLES.get(field, field)}: {testset}", ""]
    if not rows:
        return "\n".join(lines + [f"Ingen resultater med `by_{field}` for dette testsettet.", ""])
    rows = sorted(rows, key=lambda r: (r["overall"].get("wer") is None, r["overall"].get("wer") or 0, r["model"] or ""))
    groups = sorted({g for r in rows for g in r["groups"]})
    sizes = {g: max(r["groups"].get(g, {}).get("items", 0) for r in rows) for g in groups}
    head = [f"{g} ({sizes[g]}){'*' if sizes[g] < min_items else ''}" for g in groups]
    for key, title in METRICS:
        lines += [f"## {title}", "", "| Modell | Alle | " + " | ".join(head) + " |",
                  "| --- | ---: | " + " | ".join("---:" for _ in groups) + " |"]
        for r in rows:
            cells = [_pct(r["groups"].get(g, {}).get(key)) for g in groups]
            lines.append(f"| {r['model']} | {_pct(r['overall'].get(key))} | " + " | ".join(cells) + " |")
        lines.append("")
    lines += ["## Tapte nektelser", "", "| Modell | " + " | ".join(head) + " |",
              "| --- | " + " | ".join("---:" for _ in groups) + " |"]
    for r in rows:
        lines.append(f"| {r['model']} | " + " | ".join(_negation(r["groups"].get(g, {})) for g in groups) + " |")
    lines += ["", "## Gap mellom beste og dårligste gruppe (WER)", "", "| Modell | Beste | Dårligste | Forskjell |",
              "| --- | --- | --- | ---: |"]
    for r in rows:
        g = gap(r)
        if g:
            diff = f"{100 * g[2]:.1f}".replace(".", ",")
            lines.append(f"| {r['model']} | {g[0]} | {g[1]} | {diff} prosentpoeng |")
    lines += [
        "",
        f"Tall i parentes: antall setninger i gruppen. «*»: under {min_items} setninger, usikkert tall.",
        "WER og utelatelser i lesbar profil; ordrett WER beholder fyllord og avbrutte ord.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", required=True, help="Mappe med summary.json-filer")
    ap.add_argument("--testset", required=True, action="append",
                    help="Testsettnavn slik det står i summary.json. Kan gis flere ganger")
    ap.add_argument("--field", default="dialect", help="Metadatafelt kjøringen ble brutt ned på")
    ap.add_argument("--min-items", type=int, default=100)
    ap.add_argument("--out", default=None, help="Markdown-fil; JSON skrives ved siden av. Uten: skriv til skjerm")
    args = ap.parse_args(argv)
    found = {t: collect_groups(args.results, t, args.field) for t in args.testset}
    md = "\n".join(to_markdown(rows, t, args.field, args.min_items) for t, rows in found.items())
    if args.out:
        out = Path(args.out)
        out.write_text(md, encoding="utf-8")
        out.with_suffix(".json").write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{sum(len(r) for r in found.values())} kjøringer -> {out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
