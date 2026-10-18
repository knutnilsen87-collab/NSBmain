# Fase 2: status krav for krav

Oppdatert 2026-10-18. Fase 2 (diktering i EVIDA) er **startet** mens fase 1 venter på opptak. Fase 1 er ikke lukket, og modellvalget (NB-Whisper distil-turbo) er foreløpig til den er målt på juridisk diktat.

Statusverdier som i [fase 1](PHASE1_STATUS.md): **verifisert**, **venter på kjøring**, **blokkert**, **ikke startet**.

| Krav i planen | Status | Bevis eller hva som mangler |
| --- | --- | --- |
| Felles talemotor (`nsb-engine`): én tjeneste, ett API, én versjonert modell | Verifisert (første versjon) | `nsb_engine/`, [ENGINE.md](ENGINE.md). HTTP og WebSocket testet med NB-Whisper small og NPSC-lyd |
| Strømmende gjenkjenning med kort forsinkelse | Bygget, venter på kjøring | LocalAgreement-2 med VAD-endepunkt. CI: strømmet tekst like god som hel dekoding (12,5 % mot 12,5 %). Ventetid på GPU måles med `scripts\RUN_STREAMING_CHECK.cmd` |
| Ventetid fra ord til tekst, og hvor ofte teksten endres | Venter på kjøring | `nsb_eval.streaming_eval` måler begge. Krav settes i [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) etter første måling |
| Kontekst fra saken (navn, steder, saksnummer) | Bygget, effekt blokkert | `hotwords` i API-et. Effekten krever juridisk diktat med og uten kontekst |
| Normalisering av juridiske uttrykk | Verifisert | `nsb_engine.legal_format`: paragraf, datoer, beløp, klokkeslett, saksnummer, dikteringskommandoer. 29 tester. Endret ikke WER på distil-turbos utdata for tre testsett |
| Ordliste over lovnavn og fagord | Ikke startet | |
| Usikre ord synlige | Bygget, venter på kjøring | Ord under 0,5 merkes og understrekes på testsiden. Om grensen peker ut feilene, måles i strømmemålingen |
| Klikk for å høre lyden og rette; rettelser lagres som testdata | Ikke startet | Krever lagring med samtykke, som igjen krever sikkerhetstiltakene under |
| Stemmestyring med bekreftelse | Ikke startet | |
| Mål mot juridisk testsett for hver ny versjon | Blokkert | Venter på opptak fra fase 1 |
| Sikkerhet før første ekte opptak: tilgangsstyring, kryptert lagring, sletting, innsynslogg, lyd forlater ikke maskinen | Delvis | Tjenesten lytter bare på 127.0.0.1 og lagrer ingenting. Resten er ikke bygget, så tjenesten skal ikke brukes med ekte saksopplysninger |
| EVIDA med diktering hos 3–5 advokater | Ikke startet | Integrasjon mot EVIDA via WebSocket-API-et |

## Neste steg

1. Kjør `scripts\RUN_STREAMING_CHECK.cmd` (30–45 minutter) og sett krav til ventetid og endringer.
2. Prøv diktering selv med `scripts\RUN_ENGINE.cmd`.
3. Koble EVIDA til `ws://127.0.0.1:8765/v1/stream`.
4. Bygg sikkerhetstiltakene før noen dikterer med ekte saksopplysninger.
