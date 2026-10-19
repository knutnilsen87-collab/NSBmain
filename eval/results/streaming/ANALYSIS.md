# Strømming: første måling (2026-10-18 og 19)

`nsb-engine` 0.1 på RTX 4080 (float16) og CPU (int8, samme maskin). Setninger fra testsettene er satt sammen til strømmer på omtrent ett minutt med 0,5 s pause mellom setningene, og matet til motoren i biter på 0,5 s. Motoren dekoder på nytt for hvert sekund ny lyd. Klokken er simulert, men behandlingstiden er ekte. Metode: `nsb_eval/streaming_eval.py`.

Tre kjøringer mangler: distil-turbo på NPSC med stemmeaktivitetsdeteksjon (VAD), med og uten kortere steg (0,5 s). De stoppet på en feil i ordjusteringen i faster-whisper; se «Feil funnet» under.

## Hovedtall

| Kjøring | Modell | Enhet | WER strømmet | WER setning for setning | Vist etter (median / 90 %) | Ferdig etter (median / 90 %) | Ombyttede ord per 100 | Sanntidsfaktor | Største etterslep |
| --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: |
| NPSC test, 200 setninger, uten VAD | distil-turbo | GPU | 9,8 % | 8,4 % | 0,74 / 1,45 s | 1,78 / 2,76 s | 38 | 0,21 | 0,6 s |
| NB Samtale, 300 setninger, VAD | distil-turbo | GPU | 26,4 % | 28,7 % | 0,81 / 1,84 s | 1,97 / 3,70 s | 65 | 0,21 | 0,6 s |
| NPSC test, 200 setninger, VAD | NB-Whisper large | GPU | 8,4 % | 9,4 % | 1,05 / 2,19 s | 2,12 / 3,42 s | 38 | 0,45 | 7,2 s |
| NPSC test, 50 setninger, VAD | distil-turbo | CPU | 10,5 % | – | 127 s | 134 s | 33 | 5,5 | 304 s |
| NPSC test, 50 setninger, VAD | NB-Whisper small | CPU | 12,1 % | – | 11 s | 16 s | 68 | 1,5 | 42 s |

«Setning for setning» er hovedmålingen (hver setning dekodet for seg) på nøyaktig de samme setningene. Målingen av hele strømmen dekodet i ett stykke (`wer_batch` i filene) er ikke tatt med i tabellen: uten `condition_on_previous_text` mister faster-whisper hele setninger i lange lydbiter (distil-turbo 33 % WER på NPSC), så den er ingen rettferdig sammenligning.

## Hva tallene betyr

1. **Distil-turbo på GPU holder følge med god margin.** Ordene vises i snitt 0,7–0,8 sekunder etter at de er sagt, og 90 % vises innen 1,5–1,8 sekunder. Et ord er ferdig (endres ikke mer) etter knapt 2 sekunder. Behandlingen bruker en femdel av sanntiden, og motoren lå aldri mer enn 0,6 sekunder etter.
2. **Strømming koster lite nøyaktighet.** På formell tale er strømmet tekst 1,4 prosentpoeng dårligere enn setning for setning (9,8 mot 8,4 %). På samtale er den 2,3 prosentpoeng bedre (26,4 mot 28,7 %), trolig fordi motoren ser mer sammenheng enn én kort setning. Forskjellene er ikke testet for signifikans.
3. **NB-Whisper large er for tung for strømming på denne måten.** Behandlingen tar nesten halve sanntiden, og etterslepet nådde 7 sekunder i en av strømmene. Distil-turbo er tre ganger så rask med lik eller bedre nøyaktighet.
4. **CPU er ikke mulig med dagens metode.** Distil-turbo på CPU bruker 5,5 ganger sanntiden fordi bufferen dekodes på nytt hvert sekund; teksten kom flere minutter for sent. Selv NB-Whisper small henger etter. Diktering med `nsb-engine` krever i dag skjermkort, eller en annen strømmemetode for CPU (lengre steg, mindre buffer, eller en modell laget for strømming).
5. **Mye av teksten endrer seg før den er ferdig.** 38 ombyttede ord per 100 på formell tale og 65 på samtale. Ferdige ord endres aldri, men den grå, foreløpige teksten blafrer. Kortere steg (0,5 s) gir raskere tekst men trolig mer blafring; den målingen mangler.

## Usikre ord

Grunnfeilraten er 6,4 % av ordene på NPSC og 14,6 % på NB Samtale (distil-turbo, strømmet).

| Signal | NPSC: andel markert | presisjon | dekning | Samtale: andel markert | presisjon | dekning |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Sannsynlighet under 0,5 | 1,3 % | 28 % | 6 % | 4,1 % | 39 % | 11 % |
| Modellen vaklet (annet ord gjettet på samme sted) | 16,9 % | 11 % | 30 % | 27,1 % | 17 % | 32 % |
| En av de to | 17,9 % | 12 % | 33 % | 28,9 % | 18 % | 36 % |
| Vaklet minst to ganger | 8,0 % | 12 % | 15 % | 12,5 % | 16 % | 13 % |

Presisjon er andelen markerte ord som faktisk er feil. Dekning er andelen av feilene som blir markert.

- **Sannsynlighet under 0,5 er det beste enkeltsignalet**, men det markerer få ord. Et understreket ord er feil omtrent tre til fire ganger så ofte som et tilfeldig ord, men bare én av ti feil eller færre blir understreket.
- **Vakling fanger flere feil (omtrent en tredjedel), men markerer for mange ord.** Hvert sjette til fjerde ord blir markert, og de fleste av dem er riktige. Det gir mer støy enn hjelp.
- **Konklusjon:** testsiden beholder understreking under 0,5. Advokaten kan ikke stole på at ord uten understreking er riktige; det må stå i brukerveiledningen. Et bedre signal er et eget arbeid (for eksempel sammenligning av to modeller, eller en liten modell trent på feilmønstrene), og må måles på juridisk diktat.

## Feil funnet

- **Distil-turbo krasjet med ordtider.** Modellen har 2 dekoderlag, men innstillingene peker på lag 7–25 fra NB-Whisper large. CTranslate2 krasjet uten feilmelding. `download_models.py` retter nå hodene, og motoren gir en tydelig feil før den krasjer.
- **Ordjusteringen i faster-whisper 1.2.1 feiler på enkelte lydbiter** (`IndexError` i `find_alignment`). Det stoppet to av kjøringene. Motoren dekoder nå biten på nytt uten ordtider når dette skjer, fordeler tidene jevnt i segmentet og markerer ordene som usikre. Antallet slike tilfeller skrives i resultatet (`alignment_fallbacks`).

## Forbehold

- Strømmene er satt sammen av opptak fra Stortinget og NB Samtale, ikke ekte diktat. Ekte diktat har lengre pauser, kommandoer og fagord.
- Ventetiden er simulert: nettverk og nettleser er ikke med. Lydbitene fra mikrofonen er 0,5 s, så det første ordet kan i praksis komme opptil et kvart sekund senere.
- Én kjøring per innstilling. NB-Whisper large er ikke bit-reproduserbar på GPU.
