import json

from nsb_eval.dialect_report import collect_groups, gap, main, to_markdown


def _summary(path, model, testset, groups, overall_wer):
    path.mkdir(parents=True, exist_ok=True)
    (path / "summary.json").write_text(
        json.dumps(
            {
                "testset": testset,
                "model": {"model": model},
                "speech": {"wer": overall_wer, "deletion_rate": 0.1},
                "by_dialect": groups,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _g(items, wer):
    return {"items": items, "wer": wer, "deletion_rate": wer / 2,
            "critical": {"negation": {"reference": 10, "missed": 3}}}


def test_collect_and_markdown(tmp_path):
    _summary(tmp_path / "a", "modell-a", "nb_samtale_test", {"øst": _g(500, 0.24), "vest": _g(130, 0.40)}, 0.29)
    _summary(tmp_path / "b", "modell-b", "nb_samtale_test", {"øst": _g(500, 0.27), "vest": _g(130, 0.41)}, 0.31)
    _summary(tmp_path / "c", "modell-c", "annet_sett", {"øst": _g(5, 0.1)}, 0.1)
    rows = collect_groups(tmp_path, "nb_samtale_test")
    assert [r["model"] for r in rows] == ["modell-a", "modell-b"]
    assert gap(rows[0]) == ("øst", "vest", 0.40 - 0.24)

    md = to_markdown(rows, "nb_samtale_test", min_items=200)
    assert "# Resultater per dialekt: nb_samtale_test" in md
    assert "| modell-a | 29,0 % | 40,0 % | 24,0 % |" in md
    assert "vest (130)*" in md and "øst (500) |" in md
    assert "| modell-a | øst | vest | 16,0 prosentpoeng |" in md
    assert "3/10" in md


def test_main_writes_files(tmp_path):
    _summary(tmp_path / "res" / "a", "modell-a", "nb_samtale_test", {"øst": _g(500, 0.24), "nord": _g(250, 0.3)}, 0.26)
    out = tmp_path / "DIALECT.md"
    assert main(["--results", str(tmp_path / "res"), "--testset", "nb_samtale_test", "--out", str(out)]) == 0
    assert "nord (250)" in out.read_text(encoding="utf-8")
    assert json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))["nb_samtale_test"][0]["model"] == "modell-a"


def test_empty(tmp_path):
    assert "Ingen resultater" in to_markdown([], "x")
