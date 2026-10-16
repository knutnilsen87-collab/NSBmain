# Analyse av første måling (2026-10-16)

Første versjon av NSB-målestokken: fem modeller, fire faste testsett, 20 kjøringer på RTX 4080 (faster-whisper 1.2.1, float16), ingen feilede setninger. Tallene er scoret med `nsb_eval.normalize` v4, som har to profiler: lesbar (fyllord og avbrutte ord fjernet) og ordrett (beholdt). Tabellene står i [BENCHMARK.md](BENCHMARK.md); modellrevisjoner og sjekksummer i [models.json](models.json).

Hva denne målingen dekker og ikke dekker av fase 1, står i [PHASE1_STATUS.md](../../docs/PHASE1_STATUS.md). Den viktigste begrensningen: juridisk diktat og simulerte avhør er ikke spilt inn ennå, så ingen av konklusjonene under er målt på det EVIDA og domstolene faktisk skal bruke.

## Konklusjon

**NB-Whisper large distil-turbo (beta) er kandidat for fase 2 (diktering i EVIDA).** Den har lavest WER på formell tale og er bedre enn NB-Whisper large på alle tre talesettene (på NPSC test så vidt). Valget er foreløpig til den er målt på juridisk diktat mot kravene i [ACCEPTANCE_CRITERIA.md](../../docs/ACCEPTANCE_CRITERIA.md). Den skriver tekst i en tredjedel av stillhetsklippene og må ha stemmeaktivitetsdeteksjon foran seg.

**Ingen modell er valgt for ordrett transkribering (fase 3).** NB-Whisper utelater systematisk ord, alle modellene mister mange nektelser i samtaletale, og alle feiler kraftig på nynorsk.

## Hovedtall

| Modell | NPSC test | NPSC eval | NB Samtale | NB Samtale, ordrett | Stillhet: klipp med tekst | Sanntidsfaktor (NPSC test) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| nb-whisper-large-distil-turbo-beta | **12,5 %** | **15,3 %** | 29,9 % | 33,2 % | 4 av 12 | 0,030 |
| nb-whisper-large | 13,4 % | 17,0 % | 31,6 % | 34,8 % | **1 av 12** | 0,096 |
| whisper-large-v3 | 14,4 % | 18,8 % | **28,8 %** | **32,0 %** | 12 av 12 | 0,101 |
| nb-whisper-medium | 18,2 % | 28,4 % | 34,7 % | 37,7 % | 9 av 12 | 0,108 |
| nb-whisper-small | 18,8 % | 21,0 % | 34,1 % | 37,0 % | 12 av 12 | 0,114 |

WER i prosent, lesbar profil hvis ikke annet står. Sanntidsfaktor 0,03 betyr at én time lyd tar under to minutter på RTX 4080. Det sier ikke noe om ventetiden ved direktediktering, som ikke er målt.

`npsc_eval_20170209` er rapportert her fordi det var med i første måling. Fra [godkjenningskravene](../../docs/ACCEPTANCE_CRITERIA.md) versjon 1 er det et valideringssett, ikke et testsett.

## Er forskjellene reelle?

Parvis bootstrap (2 000 trekk, samme setninger for begge modeller), forskjell i WER mot distil-turbo i prosentpoeng med 95 %-intervall. Reprodusér med `python -m nsb_eval.compare --results eval/results --testset <sett> --baseline nb-whisper-large-distil-turbo-beta`.

| Modell minus distil-turbo | NPSC test | NPSC eval | NB Samtale |
| --- | --- | --- | --- |
| nb-whisper-large | +0,8 [+0,0; +1,7] | +1,6 [+0,8; +2,5] | +1,6 [+0,6; +2,8] |
| whisper-large-v3 | +1,9 [+1,1; +2,8] | +3,5 [+2,7; +4,4] | **−1,1 [−2,1; −0,1]** |
| nb-whisper-small | +6,3 [+4,8; +8,0] | +5,7 [+4,6; +6,7] | +4,2 [+3,2; +5,0] |
| nb-whisper-medium | +5,7 [+4,4; +7,1] | +13,0 [+7,6; +20,6] | +4,8 [+3,8; +5,6] |

## Meningsbærende feil

WER teller alle ord likt. Her telles ord som endrer meningen når de faller ut: nektelser, tall og navn. Målt på lesbar profil; tapte av antall i fasiten.

| Modell | Tapte nektelser, NB Samtale | Tilføyde nektelser, NB Samtale | Tapte nektelser, NPSC test | Feil tall, NPSC test | Feil navn, NPSC test |
| --- | ---: | ---: | ---: | ---: | ---: |
| nb-whisper-large-distil-turbo-beta | 86 av 365 (24 %) | 21 | 5 av 112 (4 %) | 5 av 53 | 42 av 203 (21 %) |
| nb-whisper-large | 100 av 365 (27 %) | 19 | 6 av 112 (5 %) | 3 av 53 | 28 av 203 (14 %) |
| whisper-large-v3 | 75 av 365 (21 %) | 40 | 8 av 112 (7 %) | 2 av 53 | 102 av 203 (50 %) |
| nb-whisper-medium | 112 av 365 (31 %) | 24 | 7 av 112 (6 %) | 6 av 53 | 48 av 203 (24 %) |
| nb-whisper-small | 95 av 365 (26 %) | 40 | 8 av 112 (7 %) | 6 av 53 | 42 av 203 (21 %) |

Slik er det målt: en nektelse (ikke, ingen, aldri, nei ...) er tapt når den er utelatt eller erstattet med noe som ikke er en nektelse; frasen «ikke sant» telles ikke. Tallet 1 telles ikke som tall, fordi «en» og «ett» oftest er artikkel. Navn er ord med stor forbokstav i fasiten utenom setningsstart, et grovt mål.

Det viktigste her: **i samtaletale mister alle modellene hver fjerde til tredje nektelse.** Omtrent halvparten av tilfellene (47–50 %) er i setninger med overlappende tale. Resten er setninger der modellen har strammet inn teksten og tatt nektelsen med seg ut, eller gjentatte nektelser der bare én er skrevet («ikkje, ikkje plent»). På formell tale er tapet 4–7 %. Whisper large-v3 skriver norske navn feil i halvparten av tilfellene på NPSC, mot 14–24 % for NB-Whisper.

Tallfeil på NPSC eval er ikke tatt med: møtet bruker forkortede årstall («tjueseks til tjuefemten» for 2006–2015), som normaliseringen ikke kan tolke entydig.

## Funn

1. **NB-Whisper utelater ord.** På NB Samtale står utelatelser for 17–21 % av ordene hos NB-Whisper, mot 12 % hos Whisper large-v3; i ordrett profil 21–25 % mot 16 %. Det gjelder også setninger uten overlappende tale. Modellene ser ut til å skrive en strammet tekst, i tråd med at de er trent på blant annet NRK-teksting.
2. **Nynorsk er det svakeste punktet.** På NB Samtale har nynorsk 42–48 % WER mot 24–31 % for bokmål, for alle modellene. Modellene ble kjørt med språk `no` og skriver bokmål; normaliseringen gjør ikke om mellom målformene. Ny måling med nynorsk dekodet som `nn` er klar (`scripts/RUN_PHASE1_CLOSEOUT.cmd`), men ikke kjørt.
3. **Vestlandet og sørvest er vanskeligst.** Distil-turbo: øst 24,8 %, nord 30,7 %, trøndelag 31,7 %, sørvest 39,1 %, vest 41,2 %. Mønsteret er likt for alle modellene. Overlapp med nynorsk forklarer trolig en del av dette.
4. **Hallusinasjon i stillhet varierer mye.** Whisper large-v3 og NB-Whisper small skriver tekst i alle 12 stillhetsklipp, distil-turbo i 4, NB-Whisper large i 1. Målingen kjører uten stemmeaktivitetsdeteksjon for å avdekke dette. Hallusinasjon inne i tale (tekst som ikke har støtte i lyden selv om noen snakker) er ikke målt ennå; det krever egne merkede opptak.
5. **NB-Whisper medium låser seg.** Den gjentar fraser i løkker (8,3 % innsatte ord og 64 tilføyde nektelser på NPSC eval) og er dårligere enn small på to av tre sett. Den bør ikke brukes.

## Feil i målestokken funnet underveis

- v3: «hundre og enogsytti» ble «101 og 70» i stedet for 171. NPSC-fasitene bruker gammel tellemåte, så modeller som skrev sifre fikk feil de ikke gjorde. Gjentakelsesdetektoren fanger nå fraser på opptil 12 ord.
- v4: forkortelser som modellene skriver («mrd.», «pst.», «kr», «jf.», «Innst.»), ble talt som feil mot fasitens hele ord. De utvides nå på begge sider. Ordrett profil og meningsbærende feil er lagt til.
- Alle 20 kjøringene er scoret på nytt fra rå tekst for hver versjon. Endringene flyttet WER med opptil 0,2 prosentpoeng.

## Forbehold

- NB-Whisper er trent på Stortinget-tale. Hvis møtene i NPSC-testene inngikk i treningen, er NB-Whisper-tallene på NPSC for optimistiske.
- Kjøringen brukte kode fra commit `5fb95d5`; scoringen er gjort med senere kode. Selve dekodingen er ikke endret.
- Stillhetssettet har bare 12 klipp. Andelene er grove.
- Minnebruk og CPU-ytelse er ikke målt i denne kjøringen; måleverktøyet er lagt til etterpå.
- Distil-turbo er merket «beta» av Nasjonalbiblioteket.
