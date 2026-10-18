# Godkjenningskrav

Kravene settes før en modell eller innstilling prøves, og de endres ikke etter at resultatene er kjent. Endres et krav, får det nytt versjonsnummer, og endringen begrunnes her.

Versjon 1, 2026-10-16. **Status: forslag.** Tallene under er satt ut fra første måling og må godkjennes av prosjekteier før de brukes.

## Tre typer data

| Type | Brukes til | Hva den ikke brukes til | Sett |
| --- | --- | --- | --- |
| Trening | Å lære modellen | Valg av checkpoint, rapportering | NPSC train, NB Samtale train, NST (filtrert), egne opptak med samtykke |
| Validering | Valg av checkpoint, læringsrate, dekodingsinnstillinger, terskler for hallusinasjonskontroll | Godkjenning, publiserte tall | `npsc_eval_20170209`, NB Samtale dev (bygges), en egen del av juridisk diktat |
| Låst test | Én sluttmåling per kandidat, godkjenning, publiserte tall | Alt annet | `npsc_test_20170207`, `nb_samtale_test`, `silence_v1`, juridisk diktat (test), simulerte avhør |

Regler:

1. Ingen trenings- eller valideringsdata kan overlappe med låst test på taler, møte eller fasittekst. `split_by_group.py --exclude-manifest` håndhever dette.
2. Låst test kjøres bare på en kandidat som er valgt ut fra valideringsdata. Hver kjøring logges i `eval/results/` med git-SHA, modellrevisjon og sjekksum.
3. En kandidat som feiler på låst test, kan ikke justeres mot de samme testresultatene og prøves igjen. Ny kandidat må velges på validering.
4. `npsc_eval_20170209` ble brukt som rapportert testsett i første måling. Fra versjon 1 av disse kravene er det et valideringssett.
5. LIA brukes ikke til trening, validering, test eller publiserte tall. Lisensen (CLARIN ACA-NC-LOC-PRIV-ND) tillater ikke kommersiell bruk eller avledede verk; se [dataregisteret](DATA_REGISTER.md).

## Krav for pilot med diktering (fase 2)

Målt på låst test. Alle krav må være oppfylt.

| Krav | Grense (forslag) | Første måling, distil-turbo | Hvorfor |
| --- | --- | --- | --- |
| WER, juridisk diktat (lesbar) | ≤ 8 % | Ikke målt | Diktat leses og rettes av advokaten; høyere tall gir mer retting enn skriving |
| Tapte negasjoner, juridisk diktat | 0 | Ikke målt | En tapt «ikke» snur meningen |
| Feil tall og lovhenvisninger, juridisk diktat | ≤ 2 % | Ikke målt | Paragrafnummer og beløp må stemme |
| Tekst i stillhet, med stemmeaktivitetsdeteksjon | 0 av 12 | 0 av 12 med deteksjon (4 av 12 uten) | Ingenting skal skrives når ingen snakker |
| WER, NPSC test | ≤ 15 % | 12,5 % | Formell norsk tale, kontroll mot tilbakegang |
| WER, nynorsk (NB Samtale, dekodet som `nn`) | Settes når nynorsk-diktat er målt | 47,1 % | Distil-turbo blir dårligere med `nn`; nynorskbrukere kan trenge NB-Whisper large (36,8 %) |
| Sanntidsfaktor, kundens maskinvare | ≤ 0,3 | 0,027 på RTX 4080; 0,64 på CPU (int8) | Teksten må komme mens advokaten snakker. Kravet nås ikke på CPU i dag |
| Minne | Innenfor kundens maskin | 2,7 GB GPU-minne, 1,3–1,6 GB RAM | Kjører lokalt hos advokaten |

Høy behandlingshastighet viser at modellen klarer å holde følge, men dokumenterer ikke god direktediktering. Ventetid fra ord til tekst og hvor ofte teksten endrer seg underveis, måles når strømming er bygget (fase 2).

## Krav for ordrett transkribering (fase 3)

Settes før fase 3 starter, på grunnlag av målingene av simulerte avhør. Skal minst omfatte ordrett WER, utelatelser i ordrett profil, tapte og tilføyde negasjoner, feil tall og navn, hallusinasjon i stillhet og i tale, og skille mellom talere.

Tidskoder fra tvungen justering plasserer tekst mot lyd, men beviser ikke at ordene ble sagt. Hallusinasjonskontroll vurderes for seg, og usikre partier vises som usikre.

## Krav som gjelder alltid

- Ingen kandidat tas i bruk uten en full kjøring på låst test.
- En ny versjon skal ikke være signifikant dårligere enn forrige på noe låst testsett (parvis bootstrap, `nsb_eval.compare`).
- Endres normaliseringen, scores alle tidligere resultater på nytt før sammenligning.
