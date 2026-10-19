# Fase 1: status krav for krav

Oppdatert 2026-10-19. Fase 1 er **ikke lukket**. Alle målinger som kan gjøres med åpne data, er gjort og etterprøvbare. Det som gjenstår, krever opptak (juridisk diktat og simulerte avhør) og godkjenning av kravene for diktering.

Statusverdier: **verifisert** (gjort og kontrollert, med bevis), **venter på kjøring** (klart, men må kjøres på RTX 4080-maskinen), **blokkert** (krever opptak eller en beslutning), **utsatt** (flyttet til senere fase, med begrunnelse), **endret** (kravet er tatt ut eller erstattet).

| Krav i planen | Status | Bevis eller hva som mangler |
| --- | --- | --- |
| Faste testsett: NPSC | Verifisert | `npsc_test_20170207` (501), `npsc_eval_20170209` (582), låst med sha256 i `tests/eval/test_testsets.py` |
| Faste testsett: NB Samtale | Verifisert | `nb_samtale_test` (1 195), låst med sha256 |
| Faste testsett: LIA, utvalg per landsdel | Endret | Tatt ut. Lisensen (CLARIN ACA-NC-LOC-PRIV-ND) tillater ikke kommersiell bruk eller avledede verk. Dialekt måles på NB Samtale (fem områder) |
| Juridisk diktat, 1–2 timer med ordrett fasit | Blokkert | 50 setninger og innspillingsverktøy klart (`eval/recording/legal_dictation_v1`). Mangler opptak fra minst tre talere |
| Simulerte rettsmøter og avhør | Blokkert | Tre fiktive avhør med to roller, innspillingsverktøy og fasitkontroll klart (`eval/recording/simulated_interview_v1`). Mangler opptak med to personer |
| Evalueringskjører: WER og CER | Verifisert | `nsb_eval.metrics`, testet mot kjente tilfeller |
| Fast norsk normalisering | Verifisert | v4: tall, gammel tellemåte, forkortelser. To feil funnet og rettet etter første måling; alt scoret på nytt |
| Egen profil for ordrett tekst | Verifisert | `normalize(..., "ordrett")` beholder fyllord og avbrutte ord. Rapportert som «Ordrett WER» |
| Meningsbærende feil (nektelser, tall, navn) | Verifisert, med forbehold | `nsb_eval.critical`. Navn er et grovt mål (stor forbokstav). Tall på NPSC eval er ikke pålitelige på grunn av forkortede årstall |
| Hallusinasjon: tekst uten støtte i lyden | Delvis | Stillhet (12 klipp), gjentakelsesløkker og overlange svar måles. Hallusinasjon inne i tale måles ikke; krever merkede opptak og er flyttet til fase 3 |
| Tekst i stillhet med stemmeaktivitetsdeteksjon (VAD) | Verifisert | Målt 18. oktober: 0 av 12 stillhetsklipp for alle fem modeller. I tale ingen målbar forskjell for distil-turbo (NPSC og NB Samtale); NB-Whisper large +0,6 pp på samtale. Se [ANALYSIS.md](../eval/results/ANALYSIS.md) |
| Utelatelser | Verifisert | Lesbar og ordrett profil |
| Sanntidsfaktor på GPU | Verifisert | Alle 20 kjøringer |
| Minnebruk | Verifisert | Målt 16. oktober på 100 setninger, GPU og CPU: distil-turbo 2,7 GB GPU-minne og 1,3–1,6 GB RAM, NB-Whisper large 4,1 GB og 6 GB. Se [ANALYSIS.md](../eval/results/ANALYSIS.md) |
| Fem modeller på RTX 4080 | Verifisert | 20 kjøringer, 0 feilede setninger, modellrevisjon og sha256 registrert |
| Samme modeller på CPU | Verifisert | Fire modeller, int8, 100 setninger. Samme nøyaktighet som GPU; sanntidsfaktor 0,20 (small) til 0,94 (large). Medium ikke kjørt på CPU (frarådet) |
| Nynorsk dekodet som nynorsk | Verifisert | Tre modeller. NB-Whisper large 44,8 → 36,8 % WER på nynorsk, large-v3 42,5 → 38,2 %, distil-turbo 44,0 → 47,1 % (dårligere) |
| Rettelser i treningskoden | Verifisert | Røyktester med liten modell og ekte Whisper-tokenizer: 33 bestått 2026-10-16. Egen CI-jobb (`train-smoke`) kjører dem ved hver endring og feiler hvis de hoppes over |
| Åpen publisering av resultater | Verifisert | Kode, testsett og resultater i det offentlige repoet. Resultatsiden er delt med lenke (alle med lenken kan åpne den), oppdatert med v4-tallene |
| Modell for fase 2 (diktering) | Foreløpig | Kandidat: NB-Whisper distil-turbo. Endelig valg etter måling på juridisk diktat mot [godkjenningskravene](ACCEPTANCE_CRITERIA.md) |
| Modell for fase 3 (ordrett) | Blokkert | Ingen modell oppfyller behovet. Krever avhørsopptak og undersøkelse av ordrette NB-Whisper-varianter |
| Godkjenningskrav fastsatt før nye forsøk | Delvis | Kravene til strømming er godkjent 2026-10-19. Kravene for juridisk diktat, stillhet, NPSC, sanntidsfaktor og minne er forslag i [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) og venter på godkjenning fra prosjekteier |
| Skille mellom trening, validering og låst test | Verifisert | Regel i [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md); `split_by_group.py` utelukker testsettene |

## Hva som lukker fase 1

1. ~~Kjør `scripts\RUN_PHASE1_CLOSEOUT.cmd`~~ Gjort 16. oktober: CPU, minne og nynorsk er målt.
2. ~~Kjør `scripts\RUN_VAD_CHECK.cmd`~~ Gjort 18. oktober: ingen tekst i stillhet med deteksjon, og ingen målbar ordtap for distil-turbo.
3. Spill inn juridisk diktat med minst tre talere: `scripts\RECORD_DICTATION.cmd`, én gang per taler (omtrent 15 minutter hver).
4. Spill inn simulerte avhør med to personer: `scripts\RECORD_INTERVIEW.cmd`. Kontroller fasitene og sett `verified: true`.
5. Godkjenn eller endre tallene i godkjenningskravene for diktering (kravene til strømming er godkjent).
6. Kjør `scripts\MEASURE_RECORDINGS.cmd`. Først da kan modellvalget for fase 2 bekreftes.
