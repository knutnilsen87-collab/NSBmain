# Metode for NSB-målestokken

Målet er at hvem som helst kan kjøre samme måling og få samme tall. Alt som påvirker tallene er låst og står her.

## Testsett

| Testsett | Setninger | Hva det måler | Sjekksum (sha256) |
| --- | ---: | --- | --- |
| `npsc_test_20170207` | 501 | Formell tale, Stortinget, NPSCs offisielle testsplitt | `491eab00…c4e444` |
| `npsc_eval_20170209` | 582 | Samme type. Valideringssett fra godkjenningskravene versjon 1; brukes til valg av innstillinger, ikke til godkjenning | `62e68e6a…5411a0` |
| `nb_samtale_test` | 1 195 | Samtale, fem dialektområder, bokmål og nynorsk, mye overlapp | `ac4da957…0ac7` |
| `silence_v1` | 12 | Stillhet og støy uten tale; alt modellen skriver er oppdiktet | lages deterministisk av `nsb_eval.silence` |

Testsettene bygges fra Språkbankens originalfiler med `scripts/build_testsets.py` og låses med sjekksum i `tests/eval/test_testsets.py`. De brukes aldri til trening (`split_by_group.py --exclude-manifest`).

## Dekoding

Samme innstillinger for alle modeller: faster-whisper 1.2.1, språk `no` (nynorsk-setningene kan dekodes med `nn` via `--language-from-meta standard`; versjon 1 av målestokken bruker `no` for alt),  oppgave `transcribe`, strålesøk 5, temperatur 0, `condition_on_previous_text=False`, ingen VAD-filter. VAD er slått av fordi den skjuler hallusinasjon i stillhet. GPU: float16; CPU: int8.

## Normalisering

Lik for fasit og svar (`nsb_eval/normalize.py`, versjon 4, profil «lesbar»): små bokstaver, annotasjoner fjernet (`<ee>`, `%eee`, `%unint`), NB Samtales `sagt\skriftlig` erstattet med skriftlig form, avbrutte ord (`£`) fjernet, fyllord fjernet, tegnsetting og aksenter (unntatt æøå) fjernet.

Profil «ordrett» er lik, men beholder det som ble sagt uten å bære innhold: fyllord (også annotert som `<ee>`, `%eee`, `%emm`) blir «eh», og avbrutte ord beholdes uten `£`. Latter (`%heh`) og smatting (`%ttt`) regnes ikke som ord. Ordrett profil måler om alt som ble sagt står i teksten, slik ordrett gjengivelse krever.

Forkortelser utvides på begge sider: «mrd.» = milliarder, «pst.» = prosent, «kr» = kroner, «jf.» = jamfør, «Innst.» = innstilling, «Prop.» = proposisjon, med flere (`_ABBREVIATIONS` i koden).

Tall gjøres om til sifre på begge sider, slik at skrivemåte ikke teller som feil:

| Fasit | Modellsvar | Begge blir |
| --- | --- | --- |
| `totusenogseksten`, `to tusen og seksten` | `2016` | `2016` |
| `nittenåttiåtte` | `1988` | `1988` |
| `femogtjue`, `tjuefem` | `25` | `25` |
| `hundre og enogsytti`, `to tusen og femogtjue` | `171`, `2025` | `171`, `2025` |
| `tjueen null null` | `21.00` | `21 0 0` |
| `paragraf to hundre og syttien` | `§ 271` | `paragraf 271` |
| `tre komma fem prosent` | `3,5 %` | `3 komma 5 prosent` |

Ordenstall (`13. februar`) blir ord (`trettende februar`). Ord som bare ligner tall (`tito`, `tusenvis`) røres ikke.

Ikke normalisert, og dermed talt som feil: bokmål mot nynorsk, radikale mot konservative bokmålsformer, sammensatte ord skrevet i to ord.

Endres normaliseringen, scores lagrede resultater på nytt uten å kjøre modellene (både `summary.json` og radene i `items.jsonl` skrives på nytt): `python -m nsb_eval.rescore --results eval/results --models-json models/benchmark/models.json`.

## Mål

- **WER**: (erstatninger + utelatelser + innsettinger) / antall ord i fasiten, summert over hele settet.
- **CER**: samme på tegnnivå.
- **Hallusinasjon**: andel setninger der modellen gjentar en frase (1–12 ord) minst fire ganger på rad, eller skriver mer enn dobbelt så mange ord som fasiten pluss fem.
- **Ordrett WER**: WER med profil «ordrett».
- **Meningsbærende feil** (`nsb_eval.critical`): tapte og tilføyde nektelser (ikke, ingen, aldri, nei ...; ikke frasen «ikke sant»), feil tall (unntatt 1, som oftest er artikkel) og feil navn (ord med stor forbokstav i fasiten utenom setningsstart; grovt mål). Telles mot fasiten etter justering.
- **Minne**: høyeste RAM for prosessen og høyeste brukte GPU-minne på kortet under kjøringen (`nsb_eval.resources`; GPU-tallet inkluderer andre programmer på samme kort).

Hallusinasjon inne i tale (tekst uten støtte i lyden mens noen snakker) måles ikke av disse målene. Tidskoder fra modellen bekrefter heller ikke at ordene ble sagt.
- **Hallusinasjon i stillhet**: andel stillhetsklipp der modellen skriver noe som helst.
- **Sanntidsfaktor**: behandlingstid / lydlengde.
- Setninger der fasiten bare består av fyllord eller «uforståelig» holdes utenfor WER og rapporteres som antall.

## Kjøring

```powershell
pwsh -File scripts\run_benchmark.ps1
```

Skriptet sjekker først at alle lydfiler finnes (`nsb_eval.preflight`) og at GPU-en virker; feiler GPU-en av CUDA-årsaker, brukes CPU int8. Det avslutter med feilkode hvis en jobb feiler. En resultatmappe kan bare fortsettes med samme modell og testsett (`run_meta.json`).

Resultat per modell og testsett i `eval/results/<testsett>/<modell>/summary.json` (med Hugging Face-revisjon, sha256 av `model.bin`, git-SHA og manifestets sjekksum) og samlet i `eval/results/BENCHMARK.md`.
