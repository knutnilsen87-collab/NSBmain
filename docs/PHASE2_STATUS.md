# Fase 2: status krav for krav

Oppdatert 2026-10-19. Fase 2 (diktering i EVIDA) er **startet** mens fase 1 venter på opptak. Fase 1 er ikke lukket, og modellvalget (NB-Whisper distil-turbo) er foreløpig til den er målt på juridisk diktat.

Statusverdier som i [fase 1](PHASE1_STATUS.md): **verifisert**, **venter på kjøring**, **blokkert**, **ikke startet**.

| Krav i planen | Status | Bevis eller hva som mangler |
| --- | --- | --- |
| Felles talemotor (`nsb-engine`): én tjeneste, ett API, én versjonert modell | Verifisert (første versjon) | `nsb_engine/`, [ENGINE.md](ENGINE.md). HTTP og WebSocket testet med NB-Whisper small og NPSC-lyd |
| Strømmende gjenkjenning med kort forsinkelse | Verifisert på GPU | Distil-turbo på RTX 4080: ord vises etter 0,7–0,8 s (median) og er ferdige etter knapt 2 s; strømmet tekst 1,4 pp dårligere enn setning for setning på NPSC, 2,3 pp bedre på samtale. Henger etter på CPU. Se [strømmeanalysen](../eval/results/streaming/ANALYSIS.md) |
| Ventetid fra ord til tekst, og hvor ofte teksten endres | Verifisert | Krav godkjent 2026-10-19 i [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md); distil-turbo på RTX 4080 oppfyller alle. Effekten av VAD og kortere steg på NPSC mangler (to kjøringer stoppet på en feil i faster-whisper, nå rettet) |
| Kontekst fra saken (navn, steder, saksnummer) | Bygget, effekt blokkert | `hotwords` i API-et. Effekten krever juridisk diktat med og uten kontekst |
| Normalisering av juridiske uttrykk | Verifisert | `nsb_engine.legal_format`: paragraf, datoer, beløp, klokkeslett, saksnummer, dikteringskommandoer. 29 tester. Endret ikke WER på distil-turbos utdata for tre testsett |
| Ordliste over lovnavn og fagord | Ikke startet | |
| Usikre ord synlige | Bygget, svakt signal | Understreking under 0,5: et understreket ord er feil 3–4 ganger så ofte som andre, men bare 6–11 % av feilene blir understreket. Vakling mellom dekodinger fanger en tredjedel, men markerer hvert fjerde til sjette ord. Et bedre signal må utvikles og måles på juridisk diktat |
| Klikk for å høre lyden og rette; rettelser lagres som testdata | Ikke startet | Krever lagring med samtykke, som igjen krever sikkerhetstiltakene under |
| Stemmestyring med bekreftelse | Ikke startet | |
| Mål mot juridisk testsett for hver ny versjon | Blokkert | Venter på opptak fra fase 1 |
| Sikkerhet før første ekte opptak: tilgangsstyring, kryptert lagring, sletting, innsynslogg, lyd forlater ikke maskinen | Delvis | Tjenesten lytter bare på 127.0.0.1 og lagrer ingenting. Resten er ikke bygget, så tjenesten skal ikke brukes med ekte saksopplysninger |
| EVIDA med diktering hos 3–5 advokater | Ikke startet | Integrasjon mot EVIDA via WebSocket-API-et |

## Neste steg

1. ~~Kjør `scripts\RUN_STREAMING_CHECK.cmd`~~ Gjort 19. oktober. Kjør det én gang til for de to manglende NPSC-kjøringene (omtrent 5 minutter). Kravene til strømming er godkjent.
2. Prøv diktering selv med `scripts\RUN_ENGINE.cmd`.
3. Koble EVIDA til `ws://127.0.0.1:8765/v1/stream`.
4. Bygg sikkerhetstiltakene før noen dikterer med ekte saksopplysninger.
