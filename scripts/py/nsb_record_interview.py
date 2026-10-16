"""Spill inn testsettet for simulerte avhør (to talere, én mikrofon).

To personer leser et fiktivt avhør fra ``scripts.json`` som én sammenhengende
samtale: Enter starter opptaket, manuset vises replikk for replikk (Enter for
neste), og siste Enter stopper. Opptaket lagres lokalt og skal ikke i git.

    python scripts/py/nsb_record_interview.py --session s1 --speakers knut,kari --device 1

Etterpå MÅ fasiten kontrolleres: hør gjennom opptaket og rett ``text`` i
``manifest.jsonl`` der dere sa noe annet enn manuset (``--edit`` åpner det).
Først når ``verified`` er satt til true, brukes avhøret i målingen
(``nsb_eval.runner`` hopper ikke over noe selv, så ta bare med verifiserte rader).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SET_DIR = ROOT / "eval" / "recording" / "simulated_interview_v1"


def load_scripts(path: Path = SET_DIR / "scripts.json") -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["interviews"]


def reference_text(interview: dict) -> str:
    """Fasit for WER: alle replikker i rekkefølge, slik de skal sies."""
    return " ".join(t["say"] for t in interview["turns"])


def manifest_row(interview: dict, wav_rel: str, session: str, speakers: list[str]) -> dict:
    return {
        "id": f"{session}-{interview['id']}",
        "audio": wav_rel,
        "text": reference_text(interview),
        "turns": interview["turns"],
        "roles": interview["roles"],
        "speakers": dict(zip(interview["roles"], speakers, strict=True)),
        "verified": False,
        "note": "Hør gjennom og rett text til det som faktisk ble sagt, sett så verified til true.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session", required=True, help="Kort id for innspillingen, f.eks. s1")
    ap.add_argument("--speakers", required=True, help="Kommaliste i rollerekkefølge, f.eks. knut,kari")
    ap.add_argument("--device", type=int, default=None)
    ap.add_argument("--samplerate", type=int, default=44100)
    ap.add_argument("--channels", type=int, default=2)
    ap.add_argument("--only", default=None, help="Bare ett avhør, f.eks. av-02")
    args = ap.parse_args(argv)

    sys.path.insert(0, str(ROOT / "scripts" / "py"))
    import soundfile as sf
    from nsb_record_prompts import record_until_enter

    speakers = [s.strip() for s in args.speakers.split(",") if s.strip()]
    out_dir = SET_DIR / args.session
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "manifest.jsonl"
    done = set()
    if manifest.exists():
        done = {json.loads(line)["id"] for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()}

    with open(manifest, "a", encoding="utf-8") as f:
        for iv in load_scripts():
            if args.only and iv["id"] != args.only:
                continue
            row_id = f"{args.session}-{iv['id']}"
            if row_id in done:
                continue
            if len(speakers) != len(iv["roles"]):
                raise SystemExit(f"--speakers må ha {len(iv['roles'])} navn ({', '.join(iv['roles'])})")
            roles = dict(zip(iv["roles"], speakers, strict=True))
            print(f"\n=== {iv['id']}: {iv['title']}  ({', '.join(f'{r}: {s}' for r, s in roles.items())})")
            input("Les gjennom manuset først. Enter for å starte opptaket ...")
            print("Tar opp. Les replikkene under; siste Enter stopper opptaket.\n")
            lines = [f"{t['speaker'].upper()}: {t['say']}" for t in iv["turns"]]
            # Opptaket går i bakgrunnen; record_until_enter stopper på første Enter,
            # så vi viser hele manuset og lar én Enter stoppe.
            print("\n".join(lines))
            print("\n(Enter når siste replikk er lest)")
            audio = record_until_enter(args.samplerate, args.channels, args.device)
            wav = out_dir / f"{iv['id']}.wav"
            sf.write(str(wav), audio, args.samplerate)
            f.write(json.dumps(manifest_row(iv, wav.relative_to(ROOT).as_posix(), args.session, speakers), ensure_ascii=False) + "\n")
            f.flush()
            print(f"Lagret {wav.name} ({len(audio) / args.samplerate:.0f} s)")
    print(f"\nFerdig. Kontroller fasiten i {manifest} før målingen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
