# nsb-engine: talemotoren

`nsb-engine` er den felles talemotoren som EVIDA og senere domstolsløsningen skal bruke: én lokal tjeneste med strømming, ett API og én versjonert modell. Versjon 0.1.0 (oktober 2026).

## Hva den gjør

- **Tekst mens man snakker.** Lyden samles i en buffer som dekodes på nytt hvert sekund. Et ord blir ferdig når to dekodinger etter hverandre er enige om det (LocalAgreement-2, samme metode som whisper_streaming). Foreløpige ord vises grå og kan endre seg; ferdige ord endres aldri.
- **Stemmeaktivitetsdeteksjon (VAD).** Silero-VAD. Ingen dekoding når det er stille, så modellen kan ikke dikte opp tekst i pauser. En pause på 0,8 sekunder avslutter ytringen, slik at teksten blir ferdig uten å vente på neste ord.
- **Usikre ord.** Hvert ord har modellens sannsynlighet. Ord under 0,5 merkes som usikre. Om grensen faktisk peker ut feilene, måles med `nsb_eval.streaming_eval`.
- **Kontekst fra saken.** Navn og fagord sendes inn som `hotwords`. Ferdig tekst fra før bufferen brukes som innledning til neste dekoding. Effekten på juridisk diktat er ikke målt; det krever opptakene fra fase 1.
- **Juridisk skrivemåte** (`nsb_engine.legal_format`): «paragraf to hundre og syttien» → «§ 271», «tolvte mars totusenogtjuefem» → «12. mars 2025», «en komma fem millioner kroner» → «1,5 millioner kroner», «klokka fjorten tretti» → «kl. 14.30», saksnummer, og dikteringskommandoene punktum, komma, kolon, spørsmålstegn, ny linje og nytt avsnitt. Små tall uten juridisk sammenheng står med ord («to vitner»). «Første punktum» er en henvisning, ikke en kommando.

## Personvern

Tjenesten lytter bare på 127.0.0.1. Lyd og tekst lagres ikke, og loggen inneholder bare varighet, behandlingstid og antall ord. Tilgangsstyring, kryptert lagring, sletting og innsynslogg (planens krav før første ekte opptak) er **ikke** bygget ennå.

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
| `POST /v1/transcribe?hotwords=…&format=legal` | Kroppen er en lydfil. Svar: `text`, `formatted`, `words` |
| `WS /v1/stream` | Binære meldinger med 16 kHz mono 16-bit PCM. Valgfri første melding `{"type":"start","hotwords":"…","format":"legal"}`. Avslutt med `{"type":"end"}` |

Strømmen svarer med `{"type":"update", "committed":[…], "tentative":[…], "text":"…", "tentative_text":"…", "endpoint":false}` og til slutt `{"type":"final", "text":"…", "words":[…]}`. Et ord er `{"text","start","end","probability","joined","uncertain"}`. `joined` betyr at ordet henger sammen med det forrige uten mellomrom (for eksempel «.2» i «13.2»).

Eksempel i Python:

```python
import asyncio, json, websockets

async def dikter(pcm_biter):
    async with websockets.connect("ws://127.0.0.1:8765/v1/stream") as ws:
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

- Ventetid og stabilitet på GPU er ikke målt ennå (kjør `RUN_STREAMING_CHECK.cmd`).
- Ingen lagring, tilgangsstyring eller innsynslogg; tjenesten er ikke klar for ekte saksopplysninger.
- Stemmestyring (kommandoer som «finn alle dokumenter der …») er ikke bygget.
- «kl.» scores som feil av målestokkens normalisering, som ikke utvider «kl.» til «klokka». Påvirker bare målingen, ikke teksten.
