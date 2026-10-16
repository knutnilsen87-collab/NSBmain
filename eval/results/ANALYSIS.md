# Analyse av første måling (2026-10-16)

Første versjon av NSB-målestokken: fem modeller, fire faste testsett, 20 kjøringer på RTX 4080 (faster-whisper 1.2.1, float16), ingen feilede setninger. Tallene er scoret med `nsb_eval.normalize` v3. Tabellene står i [BENCHMARK.md](BENCHMARK.md); modellrevisjoner og sjekksummer i [models.json](models.json).

## Konklusjon

**NB-Whisper large distil-turbo (beta) er standardmodellen for fase 2 (diktering i EVIDA).** Den har lavest WER på formell tale, er bedre enn NB-Whisper large på alle tre talesettene (på NPSC test så vidt) og er 2–3,5 ganger raskere. Den må kombineres med stillhetskontroll, fordi den skriver tekst i en tredjedel av stillhetsklippene.

**For ordrett transkribering (fase 3) er ingen av modellene gode nok ennå.** NB-Whisper utelater systematisk ord, og alle modellene feiler kraftig på nynorsk.

## Hovedtall

| Modell | NPSC test | NPSC eval | NB Samtale | Stillhet: klipp med tekst | Sanntidsfaktor (NPSC test) |
| --- | ---: | ---: | ---: | ---: | ---: |
| nb-whisper-large-distil-turbo-beta | **12,6 %** | **15,5 %** | 29,9 % | 4 av 12 | 0,030 |
| nb-whisper-large | 13,4 % | 17,1 % | 31,6 % | **1 av 12** | 0,096 |
| whisper-large-v3 | 14,4 % | 18,9 % | **28,8 %** | 12 av 12 | 0,101 |
| nb-whisper-medium | 18,3 % | 28,5 % | 34,7 % | 9 av 12 | 0,108 |
| nb-whisper-small | 18,8 % | 21,1 % | 34,1 % | 12 av 12 | 0,114 |

WER i prosent. Sanntidsfaktor 0,03 betyr at én time lyd tar under to minutter.

## Er forskjellene reelle?

Parvis bootstrap (2 000 trekk, samme setninger for begge modeller), forskjell i WER mot distil-turbo i prosentpoeng. Reprodusér med `python -m nsb_eval.compare --results eval/results --testset <sett> --baseline nb-whisper-large-distil-turbo-beta`.

| Modell minus distil-turbo | NPSC test | NPSC eval | NB Samtale |
| --- | --- | --- | --- |
| nb-whisper-large | +0,8 [+0,0; +1,7] | +1,6 [+0,7; +2,5] | +1,6 [+0,6; +2,8] |
| whisper-large-v3 | +1,9 [+1,0; +2,7] | +3,3 [+2,5; +4,2] | **−1,1 [−2,1; −0,1]** |
| nb-whisper-small | +6,2 [+4,7; +7,9] | +5,6 [+4,6; +6,6] | +4,2 [+3,2; +5,0] |
| nb-whisper-medium | +5,7 [+4,4; +7,1] | +13,0 [+7,6; +20,6] | +4,8 [+3,8; +5,6] |

Distil-turbo slår NB-Whisper large på alle sett (på NPSC test så vidt). Whisper large-v3 er signifikant bedre enn distil-turbo bare på samtaletale, med liten margin.

## Fem funn

1. **NB-Whisper utelater ord.** På NB Samtale står utelatelser for 17–21 % av ordene hos NB-Whisper, mot 12 % hos Whisper large-v3. Det gjelder også setninger uten overlappende tale (NB-Whisper large 19,3 % mot large-v3 11,4 %). Modellene ser ut til å skrive en strammet tekst, i tråd med at de er trent på blant annet NRK-teksting. For domstoler, som trenger ordrett gjengivelse, er dette det viktigste avviket.
2. **Nynorsk er det svakeste punktet.** På NB Samtale har nynorsk-setningene 42–48 % WER mot 24–31 % for bokmål, for alle modellene. Modellene ble kjørt med språk `no` og skriver bokmål; normaliseringen gjør ikke om mellom målformene. Neste måling bør dekode nynorsk med `nn` (`--language-from-meta standard`) for å skille modellfeil fra målformsvalg.
3. **Vestlandet og sørvest er vanskeligst.** Distil-turbo: øst 24,8 %, nord 30,7 %, trøndelag 31,7 %, sørvest 39,1 %, vest 41,2 %. Mønsteret er likt for alle modellene. Overlapp med nynorsk forklarer trolig en del av dette.
4. **Hallusinasjon i stillhet varierer mye.** Whisper large-v3 og NB-Whisper small skriver tekst i alle 12 stillhetsklipp, distil-turbo i 4, NB-Whisper large i 1. Målingen kjører uten VAD for å avdekke dette. I produktet må talegjenkjenningen derfor alltid ha stemmeaktivitetsdeteksjon og hallusinasjonskontroll foran seg.
5. **NB-Whisper medium låser seg.** Medium gjentar fraser i løkker (8,3 % innsatte ord på NPSC eval) og er dårligere enn small på to av tre sett. Den bør ikke brukes.

## Feil i målestokken funnet underveis

Gjennomgangen av radene avdekket at normaliseringen gjorde «hundre og enogsytti» om til «101 og 70» i stedet for 171. NPSC-fasitene bruker gammel tellemåte, så modeller som skrev sifre fikk feil de ikke gjorde. Rettet i v3, sammen med en gjentakelsesdetektor som nå fanger fraser på opptil 12 ord. Alle 20 kjøringene er scoret på nytt fra rå tekst; for kjøringene som allerede var scoret med v2, flyttet endringen WER med opptil 0,1 prosentpoeng.

## Forbehold

- NB-Whisper er trent på Stortinget-tale. Hvis møtene i NPSC-testene inngikk i treningen, er NB-Whisper-tallene på NPSC for optimistiske. Whisper large-v3 har ikke den fordelen.
- Kjøringen brukte kode fra commit `5fb95d5`; scoringen er gjort med commit som inneholder v3. Selve dekodingen er ikke endret mellom de to.
- Stillhetssettet har bare 12 klipp. Tallene viser tydelige forskjeller mellom modellene, men andelene er grove.
- Distil-turbo er merket «beta» av Nasjonalbiblioteket.

## Neste steg

1. Spill inn juridisk diktat (`eval/recording/legal_dictation_v1`) og mål distil-turbo på det. Det avgjør fase 2.
2. Ny måling med nynorsk dekodet som `nn`.
3. Undersøk om Nasjonalbiblioteket har en ordrett variant av NB-Whisper, og mål den mot utelatelsene over. Hvis ikke, er ordrett finjustering det viktigste arbeidet i fase 4.
4. Legg VAD og hallusinasjonskontroll inn i pilot-API-et før det brukes på ekte opptak.
