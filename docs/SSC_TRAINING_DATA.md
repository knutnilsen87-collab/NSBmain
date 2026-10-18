# Treningsdata fra Stortinget Speech Corpus

Oppdatert 2026-10-18.

**Beslutning (prosjekteier, 2026-10-18): fasiten i treningsdata skal være på bokmål**, også for talere som snakker dialekt eller skriver nynorsk.

## Kilden

[Stortinget Speech Corpus (SSC)](https://www.nb.no/sprakbanken/?p=21882) fra Språkbanken: stortingslyd fra hele landet, delt i segmenter på inntil 30 sekunder, med tekst fra det offisielle referatet. Omtrent 5 190 timer, 724 783 segmenter og 729 talere. CC0, står i [dataregisteret](DATA_REGISTER.md).

Referatet er ikke ordrett. Det er redigert til skriftspråk og skrevet på talerens målform, bokmål eller nynorsk. Ifølge artikkelen om korpuset er rundt 1 245 timer nær ordrette. En senere [utvidelse](https://aclanthology.org/2025.nodalida-1.49.pdf) legger til talerdata (fødested, fylke og antatt dialekt). Den kan kobles på med `--speaker-meta`.

Feltnavnene i SSC-fila er ikke kontrollert i dette repoet, fordi korpuset ikke er tilgjengelig fra utviklingsmiljøet. Verktøyet finner feltene selv. Kjør derfor alltid inspeksjonen først og kontroller valget.

## Slik velges fasiten

`src/python/ssc_select.py` transkriberer hvert segment med NB-Whisper large (bokmål) og velger fasit slik:

| Tilfelle | Fasit | Krav |
| --- | --- | --- |
| Referatet er på bokmål og modellen bekrefter det | **Referatet** | WER mellom referat og modell ≤ 10 % |
| Referatet er redigert (bokmål) | **Modellsvaret** | WER mot referatet ≤ 40 %, høyst 15 % utelatte ord mot referatet, og whisper-large-v3 enig (≤ 10 % WER mellom modellene) |
| Referatet er på nynorsk | **Modellsvaret** (bokmål) | Som over, men WER mot referatet ≤ 60 %, siden målformen alene gir avvik |
| Alt annet | Forkastes | Grunnen skrives i `rejected.jsonl` |

Felles for alle: lengde 1–30 s, minst 3 ord i referatet, modellen må være sikker (log-sannsynlighet ≥ −0,6, «ingen tale» ≤ 0,5, komprimeringsforhold ≤ 2,4, ingen gjentakelsesløkke), og ord per sekund må ligge mellom 1 og 6 når modellsvaret brukes.

Hvorfor slik:

- **Referatet er best når det stemmer.** Det er skrevet av mennesker med riktige navn, tall og lovhenvisninger, som er det EVIDA trenger. At modellen nesten gjengir det, viser at det faktisk ble sagt.
- **Referatet er en kontroll mot hullene til NB-Whisper.** Modellen utelater 21–25 % av ordene på samtaletale. Et modellsvar som mangler mye av referatet, forkastes (`omits_words`), selv om kontrollmodellen er enig.
- **Kontrollmodellen kjøres bare når den trengs.** Når referatet bekrefter modellsvaret, er to uavhengige kilder allerede enige. Det sparer GPU-tid.
- **Nynorsk gir bokmålsfasit.** Nynorsk-referatet kan ikke brukes som tekst, men det kontrollerer fortsatt innholdet med en løsere grense.

Målform finnes fra et felt i fila hvis det finnes, ellers fra ord som bare finnes i én målform (`ikkje`/`ikke`, `eg`/`jeg`, `frå`/`fra` ...). Korte setninger uten slike ord regnes som bokmål. Hvis referatet likevel er nynorsk, blir avviket mot modellsvaret stort, og segmentet går til modellsvar med kontroll eller forkastes. Feil målformgjetning gir altså ikke nynorsk fasit.

## Sperrer

- Møtene som de faste NPSC-testsettene kommer fra (7. og 9. februar 2017), hoppes alltid over. Treff på datoen i datofeltet, i lydstien eller i id-en.
- Resultatet skal gjennom `split_by_group.py --exclude-manifest` for alle faste testsett før trening, slik at tekst som også finnes i testsettene, fjernes.
- Taletid per taler kan begrenses (`--max-hours-per-speaker`, standard 3 timer i skriptet). Uten tak dominerer et fåtall erfarne representanter, og modellen lærer dem i stedet for dialektene.

## GPU-tid

NB-Whisper large har sanntidsfaktor rundt 0,1 på RTX 4080. Hele korpuset tar da omtrent 520 timer for hovedmodellen alene, så det er ikke aktuelt å kjøre alt. Med 3 timer per taler blir utvalget høyst rundt 2 200 timer (729 talere), i praksis mindre fordi mange talere har lite taletid. Inspeksjonen viser tallene for den lokale kopien. Start med `--max-hours`, for eksempel 200 timer (omtrent 20 GPU-timer pluss kontrollmodellen).

## Slik kjøres det

På RTX 4080-maskinen, etter at `scripts\RUN_BENCHMARK.cmd` har laget miljøet og lastet ned modellene:

1. **`scripts\RUN_SSC_INSPECT.cmd`** (sekunder). Kontroller i `build\ssc\INSPECT.json` at `field_map.audio` og `field_map.text` peker på riktige felt, at `audio_missing_in_first_200` er 0, og se timer og målform.
2. **`scripts\RUN_SSC_TRIAL.cmd`** (200 segmenter, noen minutter). Se `build\ssc\trial\summary.json`: andel beholdt, fordeling mellom referat og modellsvar, og grunner til forkasting. Les 20 tilfeldige linjer i `labels.jsonl` og lytt til noen av lydfilene.
3. **Hele utvalget:** `pwsh -File scripts\run_ssc.ps1 -Mode Full -MaxHours 200`. Kan avbrytes og startes igjen.
4. Lekkasjesjekk og deling:

   ```powershell
   python src/python/split_by_group.py --in build/ssc/v1/labels.jsonl --out-dir build/ssc/v1/split `
     --group-field speaker_id --val-pct 0 --test-pct 0 `
     --exclude-manifest eval/testsets/npsc_test_20170207.jsonl `
     --exclude-manifest eval/testsets/npsc_eval_20170209.jsonl `
     --exclude-manifest eval/testsets/nb_samtale_test.jsonl `
     --exclude-path-contains 20170207 --exclude-path-contains 20170209
   ```

5. Tren med `train_whisper_iterable.py` og velg checkpoint på validering, brutt ned på dialekt.

Feltene kan overstyres hvis inspeksjonen velger feil, for eksempel `--audio-field segment_path --text-field proceedings`.

## Hva som følger av bokmålsbeslutningen

- **Målingen må følge samme valg.** I `nb_samtale_test` er 314 av 1 195 fasiter på nynorsk. En modell som er trent til å skrive bokmål, vil få høy WER på dem uten å ta feil av innholdet. Rapporter derfor WER for bokmålsdelen for seg (`--group-by standard`), og vurder å lage bokmålsfasit for nynorsk-segmentene som et eget testsett (`_v2`) før fase 2 godkjennes.
- **Nynorsk-segmenter fra SSC blir modellsvar, ikke referat.** De går derfor gjennom strengere kontroll, og en lavere andel blir beholdt. Dette er villet: feil i bokmålsfasiten koster mer enn færre segmenter.
- **Godkjenningskravet for nynorsk** i [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) må vurderes på nytt i lys av dette.
