# NSB-målestokk: resultater

## nb_samtale_test

| Modell | Enhet | WER | Ordrett WER | CER | Innsetting | Utelatelse | Hallusinasjon | Tapte negasjoner | Feil tall | Feil navn | Sanntidsfaktor | Minne (MB) | Klipp (feilet) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| whisper-large-v3 | cuda/float16 | 28.8 % | 32.0 % | 17.3 % | 2.5 % | 12.4 % | 0.3 % | 75/365 | 18/150 | 209/581 | 0.1128 | – | 1195 (0) |
| nb-whisper-large-distil-turbo-beta | cuda/float16 | 29.9 % | 33.2 % | 19.6 % | 1.1 % | 17.3 % | 0.2 % | 86/365 | 24/150 | 235/581 | 0.0218 | – | 1195 (0) |
| nb-whisper-large | cuda/float16 | 31.6 % | 34.8 % | 22.5 % | 1.0 % | 20.7 % | 0.1 % | 100/365 | 19/150 | 197/581 | 0.0771 | – | 1195 (0) |
| nb-whisper-small | cuda/float16 | 34.1 % | 37.0 % | 23.6 % | 1.5 % | 19.5 % | 0.1 % | 95/365 | 40/150 | 228/581 | 0.0638 | – | 1195 (0) |
| nb-whisper-medium | cuda/float16 | 34.7 % | 37.7 % | 24.6 % | 1.2 % | 21.3 % | 0.2 % | 112/365 | 39/150 | 192/581 | 0.0558 | – | 1195 (0) |

Tapte negasjoner, feil tall og feil navn: tapte av antall i fasiten. Navn er ord med stor forbokstav i fasiten (grovt mål).


## npsc_eval_20170209

| Modell | Enhet | WER | Ordrett WER | CER | Innsetting | Utelatelse | Hallusinasjon | Tapte negasjoner | Feil tall | Feil navn | Sanntidsfaktor | Minne (MB) | Klipp (feilet) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nb-whisper-large-distil-turbo-beta | cuda/float16 | 15.3 % | 16.7 % | 6.6 % | 0.6 % | 5.0 % | 0.0 % | 10/129 | 34/147 | 39/269 | 0.0524 | – | 582 (0) |
| nb-whisper-large | cuda/float16 | 17.0 % | 18.4 % | 9.0 % | 0.4 % | 8.1 % | 0.0 % | 10/129 | 40/147 | 39/269 | 0.0954 | – | 582 (0) |
| whisper-large-v3 | cuda/float16 | 18.8 % | 20.2 % | 7.1 % | 1.1 % | 4.5 % | 0.0 % | 9/129 | 31/147 | 84/269 | 0.1149 | – | 582 (0) |
| nb-whisper-small | cuda/float16 | 21.0 % | 22.3 % | 12.5 % | 1.4 % | 9.1 % | 0.0 % | 9/129 | 32/147 | 45/269 | 0.0639 | – | 582 (0) |
| nb-whisper-medium | cuda/float16 | 28.4 % | 29.5 % | 19.4 % | 8.3 % | 8.4 % | 0.7 % | 13/129 | 34/147 | 36/269 | 0.0706 | – | 582 (0) |

Tapte negasjoner, feil tall og feil navn: tapte av antall i fasiten. Navn er ord med stor forbokstav i fasiten (grovt mål).


## npsc_test_20170207

| Modell | Enhet | WER | Ordrett WER | CER | Innsetting | Utelatelse | Hallusinasjon | Tapte negasjoner | Feil tall | Feil navn | Sanntidsfaktor | Minne (MB) | Klipp (feilet) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nb-whisper-large-distil-turbo-beta | cuda/float16 | 12.5 % | 13.8 % | 6.4 % | 0.5 % | 5.8 % | 0.0 % | 5/112 | 5/53 | 42/203 | 0.03 | – | 501 (0) |
| nb-whisper-large | cuda/float16 | 13.4 % | 14.7 % | 7.8 % | 0.5 % | 7.8 % | 0.0 % | 6/112 | 3/53 | 28/203 | 0.0955 | – | 501 (0) |
| whisper-large-v3 | cuda/float16 | 14.4 % | 15.7 % | 6.3 % | 0.9 % | 5.2 % | 0.0 % | 8/112 | 2/53 | 102/203 | 0.1008 | – | 501 (0) |
| nb-whisper-medium | cuda/float16 | 18.2 % | 19.4 % | 11.6 % | 1.2 % | 9.6 % | 0.2 % | 7/112 | 6/53 | 48/203 | 0.1076 | – | 501 (0) |
| nb-whisper-small | cuda/float16 | 18.8 % | 19.9 % | 12.0 % | 2.0 % | 8.9 % | 0.4 % | 8/112 | 6/53 | 42/203 | 0.114 | – | 501 (0) |

Tapte negasjoner, feil tall og feil navn: tapte av antall i fasiten. Navn er ord med stor forbokstav i fasiten (grovt mål).


## silence_v1

| Modell | Klipp | Hallusinasjon i stillhet | Innsatte ord | Sanntidsfaktor |
| --- | ---: | ---: | ---: | ---: |
| nb-whisper-large | 12 | 8.3 % | 6 | 0.0563 |
| nb-whisper-large-distil-turbo-beta | 12 | 33.3 % | 4 | 0.0116 |
| nb-whisper-medium | 12 | 75.0 % | 53 | 0.0743 |
| nb-whisper-small | 12 | 100.0 % | 62 | 0.0119 |
| whisper-large-v3 | 12 | 100.0 % | 48 | 0.0173 |
