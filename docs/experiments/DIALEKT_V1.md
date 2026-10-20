# Forsøk dialekt_v1: distil-turbo på dialekt og nynorsk

Skrevet 2026-10-20, **før** treningen er kjørt. Kriteriene under endres ikke etter at resultatene er kjent (se [godkjenningskravene](../ACCEPTANCE_CRITERIA.md)).

## Hypotese

NB-Whisper large distil-turbo er svakest på vestlandsk og sørvestlandsk tale og på nynorsk, og den utelater ord i samtale. Videre trening på samtaletale med dialekt (NB Samtale) og formell tale med nynorsk (NPSC), med riktig språktoken for nynorsk, reduserer feilene på samtale og nynorsk uten å gjøre den dårligere på formell bokmålstale.

## Data

Bygges med `scripts/build_finetune_dialect.py` (deterministisk, frø 42). Lokal kjøring 2026-10-20:

| Del | Segmenter | Innhold |
| --- | ---: | --- |
| Trening | 17 542 (4 651 nynorsk) | NB Samtale, to talergrupper (7 542 segmenter, 42 talere), og NPSC train fra 16 lokale møter (10 000: alle nynorsk-setninger og et tilfeldig utvalg bokmål) |
| Validering under trening | 500 | 400 fra `nb_samtale_spk_dev` (380 bokmål / 120 nynorsk i alt med NPSC) og 100 fra `npsc_eval_20170209` |
| Validering etter trening | 1 091 + 582 | `nb_samtale_spk_dev` (3 opptak, 8 talere) og `npsc_eval_20170209` |
| Låst test | 2 444 + 501 | `nb_samtale_spk_test` (7 opptak, 18 talere, 5,2 timer) og `npsc_test_20170207` |

**NB Samtale er delt på nytt.** De offisielle splittene deler alle 66 talere mellom train, dev og test (de er delt per segment innenfor hvert opptak). Opptakene er derfor gruppert slik at ingen taler finnes i mer enn én gruppe, og gruppene er fordelt på trening, validering og låst test. Segmentene i den offisielle testsplitten trenes aldri på. Det offisielle `nb_samtale_test` gjelder fortsatt for modeller som ikke er trent på NB Samtale, men brukes ikke for modeller fra dette forsøket.

**Forbehold om dataene:**
- Den låste testen har ingen tale fra Nord-Norge og lite fra Vestlandet (147 segmenter) og Sørvestlandet (109). Den måler dialekt dårligere enn ønsket.
- NPSC-talere fra de låste møtene er tatt ut av treningen. Det gjelder 39 talere fra NPSC og NB Samtale til sammen.
- NB-Whisper kan allerede være trent på deler av NPSC (se dataregisteret).

## Trening

`scripts\RUN_FINETUNE_DIALECT.cmd`: 1 500 steg, batch 4 × 8 (32 segmenter per steg, omtrent 2,7 gjennomganger av dataene), læringsrate 1e-5 med 150 stegs oppvarming, bf16. De 24 nederste koderlagene er frosset, så bare de 8 øverste koderlagene og dekoderen trenes. Gradient checkpointing og SpecAugment er på. Beste checkpoint velges på validering (ordvektet WER, bokmål og nynorsk dekodet med hvert sitt språktoken), og utgangsmodellen valideres ved steg 0.

## Kriterier for å gå videre (bestemt før kjøring)

Målt med målestokken (`nsb_eval.runner`, faster-whisper, strålesøk 5), parvis bootstrap (`nsb_eval.compare`, 2 000 trekk, 95 %).

**På validering**, for å velge kandidaten:
1. `nb_samtale_spk_dev`: lavere WER enn utgangsmodellen (beste av `no` og målform fra manifestet), og forskjellen er signifikant.
2. Nynorsk i `nb_samtale_spk_dev`: lavere WER enn utgangsmodellen.
3. `npsc_eval_20170209`: høyst 0,5 prosentpoeng dårligere enn utgangsmodellen.

Oppfylles alle tre, kjøres den låste testen **én gang**:

4. `nb_samtale_spk_test`: signifikant lavere WER enn utgangsmodellen.
5. `npsc_test_20170207`: ikke signifikant dårligere enn utgangsmodellen (kravet som gjelder alltid).
6. Tekst i stillhet med VAD: fortsatt 0 av 12.

Oppfylles også disse, blir modellen ny kandidat for diktering. Den må likevel måles på juridisk diktat mot godkjenningskravene før den tas i bruk. Feiler den låste testen, kan den ikke justeres mot testresultatene og prøves igjen; en ny kandidat må velges på validering.

## Resultat

Ikke kjørt.
