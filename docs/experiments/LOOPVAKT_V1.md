# Forsøk loopvakt_v1: vakt mot gjentakelsesløkker i dialekt_v1

Skrevet 2026-10-24, **før** dekodingsprofilene er målt med modellen.

## Bakgrunn

dialekt_v1 besto den låste testen, men fikk flere gjentakelsesløkker (44 av 2 444 setninger i `nb_samtale_spk_test`, mot 2) og flere innsatte ord (4,3 % mot 1,6 %). Se [DIALEKT_V1](DIALEKT_V1.md).

## Tiltak

1. **Kortere løkker i etterkant** (`nsb_eval.decoding.collapse_loops`): en frase som gjentas fire ganger eller mer etter hverandre, kortes til to. Naturlige gjentakelser som «er du er du» og «takk takk takk» beholdes.
2. **Ny dekoding ved repetitiv tekst** (profil `loopvakt`): et segment med kompresjonsforhold over 2,4 dekodes på nytt ved temperatur 0,2 og 0,4.
3. **Sperre mot gjentatte firordssekvenser** (profil `loopvakt_ngram`): som `loopvakt`, og ingen sekvens på fire ord kan gjentas i samme segment.

## Allerede målt (på eksisterende utdata, validering)

Tiltak 1 på utdataene fra valideringen av dialekt_v1 (standard dekoding):

| Valideringssett | WER uten → med | Innsatte ord uten → med | Løkker uten → med |
| --- | --- | --- | --- |
| `nb_samtale_spk_dev` | 19,55 % → 19,06 % | 4,86 % → 4,26 % | 27 → 0 |
| `npsc_eval_20170209` | 10,89 % → 10,89 % | uendret | 0 → 0 |

Forkortingen fjerner løkkene og senker WER. Den brukes derfor i alle profilene, og i talemotoren som standard (kan slås av med `--no-loop-collapse`). At flagget for løkker går til 0, følger av definisjonen (samme grense), og er ikke i seg selv et bevis; WER og innsatte ord er målene.

Om de innsatte nektelsene: av 28 innsatte nektelser i `nb_samtale_spk_dev` er flere ord fra en annen taler som snakker samtidig (fasiten har bare taleren i segmentet, utgangsmodellen skriver dem også). Andre er reelle feil.

## Kriterier (bestemt før kjøring)

Kandidater: `standard`, `loopvakt` og `loopvakt_ngram`, alle med forkorting. Målt på `nb_samtale_spk_dev` (målform fra manifestet) og `npsc_eval_20170209`. Den låste testen brukes ikke.

1. WER på hvert av de to settene høyst 0,3 prosentpoeng dårligere enn `standard` med forkorting.
2. Blant profilene som oppfyller 1: lavest andel innsatte ord på `nb_samtale_spk_dev`.
3. Er forskjellen i innsatte ord under 0,2 prosentpoeng, velges den enkleste (`standard` før `loopvakt` før `loopvakt_ngram`).
4. Stillhet med VAD: 0 av 12 for den valgte.

Den valgte profilen brukes for dialekt_v1 i Verity. EVIDA er ikke berørt før juridisk diktat er målt.

## Resultat

Ikke kjørt.
