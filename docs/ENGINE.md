# nsb-engine: talemotoren

`nsb-engine` er den felles talemotoren som EVIDA og senere domstolsløsningen skal bruke: én lokal tjeneste med strømming, ett API og én versjonert modell. Versjon 0.2.0 (oktober 2026).

## Hva den gjør

- **Tekst mens man snakker.** Lyden samles i en buffer som dekodes på nytt hvert sekund. Et ord blir ferdig når to dekodinger etter hverandre er enige om det (LocalAgreement-2, samme metode som whisper_streaming). Foreløpige ord vises grå og kan endre seg; ferdige ord endres aldri.
- **Stemmeaktivitetsdeteksjon (VAD).** Silero-VAD. Ingen dekoding når det er stille, så modellen kan ikke dikte opp tekst i pauser. En pause på 0,8 sekunder avslutter ytringen, slik at teksten blir ferdig uten å vente på neste ord.
- **Usikre ord.** Hvert ord har modellens sannsynlighet. Ord under 0,5 merkes som usikre. Om grensen faktisk peker ut feilene, måles med `nsb_eval.streaming_eval`.
- **Kontekst fra saken.** Navn og fagord sendes inn som `hotwords`. Ferdig tekst fra før bufferen brukes som innledning til neste dekoding. Effekten på juridisk diktat er ikke målt; det krever opptakene fra fase 1.
- **Juridisk skrivemåte** (`nsb_engine.legal_format`): «paragraf to hundre og syttien» → «§ 271», «tolvte mars totusenogtjuefem» → «12. mars 2025», «en komma fem millioner kroner» → «1,5 millioner kroner», «klokka fjorten tretti» → «kl. 14.30», saksnummer, og dikteringskommandoene punktum, komma, kolon, spørsmålstegn, ny linje og nytt avsnitt. Små tall uten juridisk sammenheng står med ord («to vitner»). «Første punktum» er en henvisning, ikke en kommando.

## Personvern

Versjon 0.2 har sikkerhetstiltakene planen krever før første ekte opptak. Hva de beskytter mot, og hva de ikke beskytter mot, står under.

| Tiltak | Slik virker det |
| --- | --- |
| Lyden forlater ikke maskinen | Tjenesten lytter bare på 127.0.0.1 og nekter å starte på andre adresser uten `--allow-remote`. Den gjør ingen kall ut (`HF_HUB_OFFLINE=1`; modellen leses fra disk) |
| Tilgangsstyring | Alle kall unntatt `/v1/health` og testsiden krever tilgangsnøkkelen (`Authorization: Bearer …`, eller `?token=` for WebSocket). Nøkkelen lages ved første start og ligger i `%LOCALAPPDATA%\nsb-engine\access_token`. Tjenesten avviser fremmede `Host`-navn (mot DNS-rebinding) og WebSocket fra nettsider som ikke er godkjent (`--allow-origin` for EVIDA) |
| Lagring bare med samtykke | Ingenting lagres med mindre klienten sender `"store": true` og `"consent": true` |
| Kryptert lagring | Hver økt krypteres med sin egen nøkkel (AES-256-GCM). Øktnøklene krypteres med en hovednøkkel som Windows beskytter med DPAPI, bundet til Windows-brukeren. Endret innhold oppdages ved dekryptering |
| Fast sletting | Økter slettes automatisk etter 30 dager (`--retention-days`); klienten kan korte ned, ikke forlenge. Sletting skjer ved oppstart og hver time, og fjerner øktnøkkelen først, så rester på disken ikke kan dekrypteres |
| Innsynslogg | `%LOCALAPPDATA%\nsb-engine\audit.jsonl`: lagret, lest, lyttet, rettet, slettet, avvist tilgang, start og stopp, med tid og hvem (nøkkelens kjennetegn og `X-NSB-User` fra klienten). Aldri lyd eller tekst. Hver linje er kjedet til den forrige med en HMAC avledet av hovednøkkelen; `python -m nsb_engine.admin verify` sier om loggen er endret |

**Beskytter ikke mot:** noen som er logget inn som samme Windows-bruker (de kan lese nøkkelen og dekryptere), skadevare på maskinen, eller en klient som har nøkkelen og misbruker den. Hvem som er bruker, bestemmer klienten (`X-NSB-User`); tjenesten har bare én nøkkel per maskin. Full disk-kryptering (BitLocker) anbefales i tillegg. Sertifisering og ekstern revisjon er fase 5.

## Starte

På RTX 4080-maskinen, etter at målestokken har lastet ned modellene:

```powershell
Set-Location "F:\prosjekter_MAIN\NorwegianSpeechBase"
& ".\scripts\RUN_ENGINE.cmd"
```

Testsiden åpnes på http://127.0.0.1:8765/ (Edge eller Chrome; Firefox støtter ikke 16 kHz-mikrofon i nettleseren).

## API (versjon 1)

| Kall | Hva |
| --- | --- |
| `GET /v1/health` | Modell, enhet og versjon |
| `POST /v1/transcribe?hotwords=…&format=legal&vad=true` | Kroppen er en lyd- eller videofil. Svar: `text`, `formatted`, `words`. Med `vad=true` (for lange opptak, brukes av Verity) dekodes bare tale, i biter på under 30 sekunder, og svaret har også `speech_chunks` |
| `WS /v1/stream?token=…` | Binære meldinger med 16 kHz mono 16-bit PCM. Valgfri første melding `{"type":"start","hotwords":"…","format":"legal","store":true,"consent":true,"case_ref":"…","retention_days":7}`. Avslutt med `{"type":"end"}` |
| `POST /v1/pair` | `{"code":"…"}` fra en godkjent nettside gir tilgangsnøkkelen (engangskode i vinduet til motoren) |
| `GET /v1/whoami` | Sjekker at nøkkelen fortsatt gjelder |
| `GET /v1/sessions` | Lagrede økter, uten innhold |
| `GET /v1/sessions/{id}` / `…/audio` | Tekst (og eventuell retting) / lyd som WAV. Føres i innsynsloggen |
| `PUT /v1/sessions/{id}/transcript` | Rettet tekst `{"text":"…"}` |
| `DELETE /v1/sessions/{id}` | Sletter økten og nøkkelen |
| `GET /v1/audit?session=…` / `GET /v1/audit/verify` | Innsynsloggen / kontroll av den |

Alle kall unntatt `/v1/health` krever `Authorization: Bearer <nøkkel>`. Valgfritt `X-NSB-User` (for eksempel EVIDA-brukeren) skrives i innsynsloggen.

Hver oppdatering har også `preview`: ferdig og foreløpig tekst formatert sammen (motorens beste gjetning akkurat nå). Med lagring inneholder sluttmeldingen også `session_id` og `expires`. Strømmen svarer med `{"type":"update", "committed":[…], "tentative":[…], "text":"…", "tentative_text":"…", "endpoint":false}` og til slutt `{"type":"final", "text":"…", "words":[…]}`. Et ord er `{"text","start","end","probability","joined","uncertain"}`. `joined` betyr at ordet henger sammen med det forrige uten mellomrom (for eksempel «.2» i «13.2»).

Eksempel i Python:

```python
import asyncio, json, os, pathlib, websockets

NØKKEL = (pathlib.Path(os.environ["LOCALAPPDATA"]) / "nsb-engine" / "access_token").read_text().strip()

async def dikter(pcm_biter):
    async with websockets.connect(f"ws://127.0.0.1:8765/v1/stream?token={NØKKEL}") as ws:
        await ws.send(json.dumps({"type": "start", "hotwords": "Bjørdal, MED-OTIR"}))
        for bit in pcm_biter:            # bytes, 16 kHz mono int16
            await ws.send(bit)
        await ws.send(json.dumps({"type": "end"}))
        while (m := json.loads(await ws.recv()))["type"] != "final":
            print(m["text"], "|", m["tentative_text"])
        return m["text"]
```

## Måling

```powershell
& ".\scripts\RUN_STREAMING_CHECK.cmd"
```

Måler på NPSC test og NB Samtale, med setninger satt sammen til strømmer på 60 sekunder:

- ventetid fra et ord slutter i lyden til det vises, og til det er ferdig
- endringer: viste ord som forsvinner eller byttes ut, per 100 ferdige ord
- WER for strømmet tekst mot WER for samme lyd dekodet i ett stykke
- om ordene modellen er usikker på, faktisk er feil oftere (presisjon og dekning for grensene 0,3, 0,5 og 0,7)
- om CPU holder følge (distil-turbo og NB-Whisper small, int8)

Klokken er simulert, men behandlingstiden er ekte. Resultater: `eval/results/streaming/`.

## Kontrollert så langt

- 52 tester for strømming, formatering, tjeneste og strømmemåling (pluss to røyktester som krever modell).
- CI kjører motoren med en ekte modell (Whisper tiny) på syntetisk tale og krever at strømmet tekst ikke er mer enn 5 prosentpoeng dårligere enn samme lyd dekodet i ett stykke. Siste kjøring: 12,5 % mot 12,5 %.
- NB-Whisper small på CPU med NPSC-lyd: tjenesten svarer over HTTP og WebSocket, og strømmet tekst hadde 15,0 % WER mot 16,7 % i ett stykke. CPU-en (2 kjerner) var for treg til å si noe om ventetid.
- Juridisk formatering endret ikke WER på distil-turbos utdata for NPSC test, NPSC eval og NB Samtale (NB-Whisper skriver allerede tall og paragrafer med sifre i de fleste tilfeller).

## Kjente begrensninger

- Krever skjermkort. På CPU henger motoren etter (distil-turbo 5,5 ganger sanntiden), fordi bufferen dekodes på nytt hvert sekund. Se [strømmeanalysen](../eval/results/streaming/ANALYSIS.md).
- Understrekingen av usikre ord fanger bare én av ti feil eller færre. Ord uten understreking kan også være feil.
- Mye foreløpig tekst byttes ut før den blir ferdig (38 ord per 100 på formell tale, 65 på samtale).
- Én tilgangsnøkkel per maskin; brukeridentitet kommer fra klienten. Kryptering er bundet til Windows-brukeren, ikke til den enkelte advokat.
- Stemmestyring (kommandoer som «finn alle dokumenter der …») er ikke bygget.
- «kl.» scores som feil av målestokkens normalisering, som ikke utvider «kl.» til «klokka». Påvirker bare målingen, ikke teksten.
