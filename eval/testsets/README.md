# Faste testsett

Bygget med `python scripts/build_testsets.py --root . --out eval/testsets` fra Språkbankens originalfiler (CC0). Lydstiene er relative til prosjektroten; lyden ligger under `dataset/` og er ikke i git.

| Fil | Setninger | Kilde | sha256 |
| --- | ---: | --- | --- |
| `npsc_test_20170207.jsonl` | 501 | NPSC 2.0 testsplitt, møtet 7. februar 2017, 9 talere (øst 203, vest 162, sør 136; 39 på nynorsk) | `491eab00fdd8f234d4f5b7210ff69fd97980dd7f606b53e7d9cd402c88c4e444` |
| `npsc_eval_20170209.jsonl` | 582 | NPSC 2.0 eval-splitt, møtet 9. februar 2017 (brukt i målinger januar 2026) | `62e68e6abd97d692625c74983c2573390736c93832e3d33f4d5470bdaa5411a0` |
| `nb_samtale_test.jsonl` | 1 195 | NB Samtale testsplitt, 66 talere, 2,35 timer (øst 557, nord 261, sørvest 163, vest 136, trøndelag 78; bokmål 881, nynorsk 314) | `ac4da957b6815498b3a2d7c2f5d0828d8811716a273633e0703d6158da530ac7` |
| `silence_v1/` | 12 | Syntetisk stillhet og støy, lages med `python -m nsb_eval.silence --out-dir eval/testsets/silence_v1` | deterministisk |

Endres et testsett, skal sjekksummen oppdateres i både denne filen og `tests/eval/test_testsets.py`, og det skal få et nytt navn (for eksempel `_v2`). Gamle resultater er bare sammenlignbare med samme sjekksum.
