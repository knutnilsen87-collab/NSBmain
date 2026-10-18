# Dialekter og pseudo-merking

Oppdatert 2026-10-18. Dokumentet beskriver hva målestokken sier om dialekter, og hvordan NSB lager treningsdata for dialekttale ved pseudo-merking. Pseudo-merking betyr at en sterk modell lager fasiten for ekte lyd som mangler transkripsjon, og at bare de klippene modellen sannsynligvis har rett på, beholdes.

## Hva målingen sier om dialekter

Tabellene står i [eval/results/DIALECT.md](../eval/results/DIALECT.md). De lages på nytt med:

```powershell
python -m nsb_eval.dialect_report --results eval/results --testset nb_samtale_test `
  --testset nb_samtale_test_maalform --out eval/results/DIALECT.md
```

WER på NB Samtale, lesbar profil, nynorsk dekodet som nynorsk (`nb_samtale_test_maalform`):

| Modell | Øst (547) | Nord (247) | Trøndelag (77) | Sørvest (159) | Vest (131) |
| --- | ---: | ---: | ---: | ---: | ---: |
| whisper-large-v3 | 23,8 % | 27,7 % | 31,9 % | 35,0 % | 35,0 % |
| nb-whisper-large | 27,6 % | 30,3 % | 34,0 % | 32,5 % | 35,2 % |
| nb-whisper-large-distil-turbo-beta | 24,9 % | 30,9 % | 31,3 % | 40,4 % | 46,1 % |

Det viktigste:

1. **Dialekt og målform er blandet sammen i testsettet.** «Vest» er 89 % nynorsk og «sørvest» 71 % nynorsk; øst og nord er nesten bare bokmål. Når alt dekodes som bokmål (`nb_samtale_test`), ser vest ut til å ligge 14–16 prosentpoeng bak øst. Når nynorsk dekodes som nynorsk, krymper gapet for NB-Whisper large fra 14,0 til 7,6 prosentpoeng. En stor del av det som så ut som et dialektproblem, er et målformproblem.
2. **Det er et reelt gap etter at målformen er tatt hensyn til:** 7,6 prosentpoeng (NB-Whisper large) og 11,2 prosentpoeng (whisper-large-v3) mellom øst og det dårligste området. Trøndelag har bare 77 setninger og er usikkert.
3. **Utelatelsene er like i alle dialekter** (NB-Whisper large 21–25 %, whisper-large-v3 9–13 %). De er en egenskap ved modellen, ikke ved dialekten. Dette avgjør hvordan pseudo-merkingen må filtreres (se under).
4. **Distil-turbo tåler ikke nynorsk-dekoding på vest og sørvest** (46,1 % og 40,4 %). Kandidaten for diktering i fase 2 er dårligst nettopp der dialektgapet er størst.

**Beslutning 2026-10-18: fasiten i treningsdata er på bokmål**, også for dialekttalere og nynorskbrukere. Pseudo-merk derfor med `--language no` (standard) og ikke `--language-from-meta`. NB Samtale transkriberer hver taler på enten bokmål eller nynorsk (feltet `standard`), så målingen må rapportere bokmålsdelen for seg; se [SSC_TRAINING_DATA.md](SSC_TRAINING_DATA.md).

## Verktøyet

`src/python/pseudo_label.py` tar ekte lyd med kjent lisens og gir klipp med fasit i samme format som treningsmanifestene (`audio`, `text` og metadata). Kjøringen kan stoppes og startes igjen.

```powershell
python src/python/pseudo_label.py --in data/unlabeled/kilde_vest.jsonl `
  --out-dir build/pseudo/kilde_vest --source "Kildenavn fra dataregisteret" --license "CC BY 4.0" `
  --model models/benchmark/nb-whisper-large/ct2 --label nb-whisper-large `
  --second-model models/benchmark/whisper-large-v3/ct2 --second-label whisper-large-v3 `
  --exclude-manifest eval/testsets/nb_samtale_test.jsonl `
  --exclude-manifest eval/testsets/npsc_test_20170207.jsonl `
  --exclude-manifest eval/testsets/npsc_eval_20170209.jsonl `
  --device cuda --compute-type float16
```

Inndata er én linje per lydfil, for eksempel `{"audio": "D:/lyd/ep12.mp3", "dialect": "vest", "standard": "nn", "speaker_id": "kildeX-vert1"}`. Lange opptak deles i klipp på inntil 30 sekunder langs modellens segmentgrenser.

### Filtre

| Filter | Standard | Hvorfor |
| --- | --- | --- |
| Lengde | 1–30 s | Whisper trenes på klipp på inntil 30 s |
| Gjennomsnittlig log-sannsynlighet | ≥ −0,5 | Modellen er usikker under dette |
| Sannsynlighet for «ingen tale» | ≤ 0,5 i alle segmenter | Tekst uten tale er hallusinasjon |
| Komprimeringsforhold | ≤ 2,4 | Høyt forhold betyr gjentakelser |
| Gjentakelsesløkke, minst antall ord | ingen løkke, ≥ 3 ord | Samme mål som målestokken |
| Ord per sekund | 1,0–6,0 | **Nedre grense fanger utelatelser.** NB-Whisper utelater 21–25 % av ordene; et klipp med for få ord for lengden har trolig hull i fasiten |
| Enighet med kontrollmodell | WER mellom modellene ≤ 15 % | To modeller med ulike svakheter tar sjelden feil på samme måte |

Anbefalt par er NB-Whisper large som hovedmodell (skriver norske navn riktig og følger norsk rettskrivning) og whisper-large-v3 som kontroll (færrest utelatelser, 9–13 %). Kravet om enighet fanger da både utelatelsene til NB-Whisper og navnefeilene til large-v3. VAD er på under pseudo-merking, i motsetning til målestokken, fordi stillhet her skal gi ingen tekst og ikke måles.

Alle forkastede klipp skrives til `rejected.jsonl` med grunn og mål. Prøv tersklene på et lite utvalg først (`--limit 20`), lytt til et tilfeldig utvalg av beholdte og forkastede klipp, og juster før hele kjøringen.

### Sperrer

- **Lisens:** `--source` og `--license` er påkrevd og skrives i hver linje. Lisenser med NC (ikke-kommersiell) eller ND (ingen avledede verk) stoppes før noe kjøres; pseudo-merket tekst er et avledet verk. LIA kan derfor ikke brukes. Kilden skal stå i [dataregisteret](DATA_REGISTER.md) før kjøring.
- **Testsett:** lydfiler fra de faste testsettene (`--exclude-manifest`) og stier med møtedatoene (`--exclude-path-contains`) hoppes over. Talere kan utelukkes med `--exclude-speaker-field`, men bare når id-ene kommer fra samme kilde som testsettet.

## Fra pseudo-merking til trening

1. Registrer kilden i dataregisteret med lisens.
2. Lag inndatafilen med dialekt, målform og taler-id per fil.
3. Prøv tersklene med `--limit`, lytt og juster.
4. Kjør alt. Se `summary.json` for timer per dialekt og per grunn til forkasting.
5. Kjør resultatet gjennom `split_by_group.py` med `--exclude-manifest` for alle faste testsett, slik at taler- og tekstlekkasje fjernes.
6. Bland med ekte data. Pseudo-merket lyd bør være en mindre del av treningstimene, for eksempel 20–30 %; riktig andel finnes på validering, ikke på låst test.
7. Velg checkpoint på validering (`npsc_eval_20170209`, NB Samtale dev) brutt ned på dialekt. Mål på låst test én gang, etter [godkjenningskravene](ACCEPTANCE_CRITERIA.md).

## Kilder

Den største begrensningen er lisensiert dialektlyd uten fasit, ikke verktøyet. Kandidater:

- **Stortinget Speech Corpus** (CC0, over 5 000 timer, står i dataregisteret): eget verktøy, `src/python/ssc_select.py`, som bruker referatet som fasit der modellen bekrefter det og som kontroll ellers. Se [SSC_TRAINING_DATA.md](SSC_TRAINING_DATA.md).
- **NB Samtale train** og **NPSC train** har allerede fasit og skal brukes direkte, ikke pseudo-merkes.
- **Egne opptak med samtykke**, for eksempel innsamling fra vest og Trøndelag, der testsettet er tynnest.
- Podkaster, lokalradio og NRK krever avtale eller åpen lisens per kilde; de er ikke åpne i dag.

## Ikke laget ennå

- Blanding av ekte og pseudo-merket data med tak per dialekt og per kilde.
- Augmentering (hastighet, støy, romklang, telefonlyd).
- Talesyntese (TTS) for ord og navn som mangler i treningsdataene. Dette gir ikke dialektuttale og har lavest prioritet.
- Et NB Samtale dev-sett for validering per dialekt (nevnt i godkjenningskravene).
