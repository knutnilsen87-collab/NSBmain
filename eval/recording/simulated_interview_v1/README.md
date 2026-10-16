# Simulerte avhør (testsett, versjon 1)

Tre fiktive avhør med to talere, laget for å måle transkribering av samtaler der hvert ord kan ha rettslig betydning. Alle navn, adresser, beløp og hendelser er oppdiktet. Manusene ligger i [`scripts.json`](scripts.json).

## Hva settet måler

- Ordfeil (lesbar og ordrett profil) på samtale mellom to personer i ett rom, med én mikrofon.
- Meningsbærende detaljer: hvert manus har nektelser («jeg betalte ikke kontant»), tall og beløp, klokkeslett, datoer, telefonnummer, lovhenvisninger og personnavn.
- Senere (fase 3): skille mellom talere, ved hjelp av rollene i `turns`.

Settet er lite (tre opptak, rundt 1 000 ord per innspilling). Det egner seg til å finne feiltyper og grove forskjeller, ikke til fine sammenligninger. Flere innspillinger med ulike talere gjør det sterkere.

## Slik spilles det inn

1. To personer, ett rom uten ekko, mikrofonen omtrent én meter fra begge. Samme oppsett som skal brukes i praksis.
2. Les manuset gjennom én gang før opptak. Snakk naturlig, i eget tempo og med egen dialekt.
3. Kjør `python scripts/py/nsb_record_interview.py --session s1 --speakers <avhører>,<vitne> --device <nr>`.
4. Avvik fra manuset er greit og realistisk, men da må fasiten rettes.

## Kontroll av fasit (obligatorisk)

Opptakene får `verified: false`. Før de brukes i målingen:

1. Hør gjennom hvert opptak med manuset ved siden av.
2. Rett `text` i `manifest.jsonl` til det som faktisk ble sagt, ord for ord (også gjentakelser og avbrutte ord, markert med `£`, og nøling som `eh`).
3. Sett `verified: true` og skriv hvem som kontrollerte i `note`.

Uverifiserte opptak tas ikke med i målingen. Tidskoder fra modellen kan ikke erstatte denne kontrollen: de plasserer teksten mot lyden, men bekrefter ikke at teksten er riktig.

## Personvern

Opptakene er stemmer av virkelige personer og er personopplysninger, selv om innholdet er fiktivt. De lagres lokalt, aldri i git, og bare med skriftlig samtykke fra dem som leser. Se [dataregisteret](../../../docs/DATA_REGISTER.md).
