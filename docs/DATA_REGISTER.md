# Dataregister

Ingen data brukes til trening, test eller produkt uten en linje her med dokumentert lisens. Lisensene er sjekket mot Språkbankens ressurskatalog og data.norge.no 2026-10-16.

| Datasett | Innhold | Omfang | Lisens | Kommersiell bruk | Bruk i NSB | Lokal sti |
| --- | --- | --- | --- | --- | --- | --- |
| [NPSC](https://www.huggingface.co/datasets/NbAiLab/NPSC/blob/main/README.md) (Norwegian Parliamentary Speech Corpus) | Stortingsdebatter 2017–2018, ordrett transkribert, taler og dialekt | ca. 140 timer | CC0 1.0 | Ja | Testsett `npsc_test_20170207`, `npsc_eval_20170209`; trening (train-splitt) | `dataset/norwegian/NPSC_1`, `NPSC_2` |
| [NB Samtale](https://www.nb.no/sprakbanken/?p=31660) (Norwegian Conversation Speech Corpus) | Podkast og arrangementer, samtaletale, fem dialektområder, bokmål og nynorsk | 24 timer, 69 talere, 12 080 segmenter | CC0 1.0 | Ja | Testsett `nb_samtale_test`; trening (train-splitt) | `dataset/nb_samtale` |
| [NST norsk ASR-database (16 kHz)](https://data.norge.no/en/datasets/813152f3-a3b7-353f-ba92-e3107208a56f/nst-norwegian-asr-database-16-khz-reorganized) | Opplest manus 1999, mange talere leser samme setninger, inkl. uttalt tegnsetting | ca. 386 000 klipp | CC0 1.0 | Ja | Trening med forsiktighet: gjentatte manus og stille opptak filtreres. Ikke testsett (inngår i NB-Whispers trening) | `F:\GPT\datasetVoice\norwegian\lydfiler_16_begge_*` |
| [NVCC](https://data.norge.no/en/datasets/627e433b-8848-3b6c-bffe-dcd79b86e5ca/norwegian-voice-control-corpus) (Norsk talestyringskorpus) | Stemmekommandoer til assistent, 183 intensjoner | 9 834 innspilte kommandoer, 11 talere | CC0 1.0 | Ja | Kandidat for kommando-testsett (EVIDA stemmestyring) | `dataset/norwegian/NVCC` |
| [Stortinget Speech Corpus (SSC)](https://aclanthology.org/2023.resourceful-1.7.pdf) | Stortingslyd med offisielt referat (svak tilsyn) | 5 000+ timer | CC0 | Ja | Kandidat for trening (referat er ikke ordrett) | `dataset/Stortinget Speech Corpus versjon 1.0` |
| [LIA norsk](https://www.nb.no/sprakbanken/?p=30580) | Eldre dialektopptak, 1 374 talere fra 222 steder | ca. 25 GB lyd | CLARIN ACA-NC-LOC-PRIV-ND (akademisk, ikke-kommersiell, ingen avledede verk) | **Nei** | **Brukes ikke.** Kan ikke inngå i produkt, trening eller publisert målestokk | `dataset/LIA` |
| Juridisk diktat (`eval/recording/legal_dictation_v1`) | Egne opptak av juridiske diktater og kommandoer | 50 setninger per taler | Eget materiale, samtykke fra hver taler | Ja | Testsett for EVIDA | Lokalt, ikke i git |

## Kjente forhold

- NB-Whisper er trent på NST, Stortinget-tale, NRK-teksting og lydbøker ([modellkort](https://huggingface.co/NbAiLab/nb-whisper-large)). Resultater på NPSC kan derfor være noe optimistiske for NB-Whisper hvis samme møter inngikk i treningen.
- NPSCs offisielle testsplitt har fire møter; lokalt finnes lyd bare for 7. februar 2017 (501 setninger, ni talere).
- NB Samtale-testen har 447 av 1 195 segmenter med overlappende tale. Resultatene brytes ned på dialekt og rettskrivning.
- NB Samtales offisielle splitter (train/dev/test) er delt per segment: alle 66 talere i testsplitten finnes også i train. For trening deles korpuset i stedet i talergrupper uten felles talere (`scripts/build_finetune_dialect.py`, testsett `nb_samtale_spk_test` og `nb_samtale_spk_dev`).
