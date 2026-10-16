# NSB-målestokk: resultater

## nb_samtale_test

| Modell | WER | CER | Innsetting | Utelatelse | Hallusinasjon | Sanntidsfaktor | Klipp (feilet) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| whisper-large-v3 | 28.8 % | 17.3 % | 2.5 % | 12.4 % | 0.3 % | 0.1128 | 1195 (0) |
| nb-whisper-large-distil-turbo-beta | 29.9 % | 19.6 % | 1.1 % | 17.3 % | 0.2 % | 0.0218 | 1195 (0) |
| nb-whisper-large | 31.6 % | 22.5 % | 1.0 % | 20.7 % | 0.1 % | 0.0771 | 1195 (0) |
| nb-whisper-small | 34.1 % | 23.6 % | 1.5 % | 19.5 % | 0.1 % | 0.0638 | 1195 (0) |
| nb-whisper-medium | 34.7 % | 24.6 % | 1.2 % | 21.3 % | 0.2 % | 0.0558 | 1195 (0) |

## npsc_eval_20170209

| Modell | WER | CER | Innsetting | Utelatelse | Hallusinasjon | Sanntidsfaktor | Klipp (feilet) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nb-whisper-large-distil-turbo-beta | 15.5 % | 6.8 % | 0.6 % | 5.0 % | 0.0 % | 0.0524 | 582 (0) |
| nb-whisper-large | 17.1 % | 9.2 % | 0.4 % | 8.1 % | 0.0 % | 0.0954 | 582 (0) |
| whisper-large-v3 | 18.9 % | 7.1 % | 1.1 % | 4.5 % | 0.0 % | 0.1149 | 582 (0) |
| nb-whisper-small | 21.1 % | 12.6 % | 1.4 % | 9.1 % | 0.0 % | 0.0639 | 582 (0) |
| nb-whisper-medium | 28.5 % | 19.5 % | 8.3 % | 8.4 % | 0.7 % | 0.0706 | 582 (0) |

## npsc_test_20170207

| Modell | WER | CER | Innsetting | Utelatelse | Hallusinasjon | Sanntidsfaktor | Klipp (feilet) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nb-whisper-large-distil-turbo-beta | 12.6 % | 6.5 % | 0.5 % | 5.8 % | 0.0 % | 0.03 | 501 (0) |
| nb-whisper-large | 13.4 % | 7.9 % | 0.5 % | 7.8 % | 0.0 % | 0.0955 | 501 (0) |
| whisper-large-v3 | 14.4 % | 6.3 % | 0.9 % | 5.2 % | 0.0 % | 0.1008 | 501 (0) |
| nb-whisper-medium | 18.3 % | 11.6 % | 1.2 % | 9.6 % | 0.2 % | 0.1076 | 501 (0) |
| nb-whisper-small | 18.8 % | 12.0 % | 2.0 % | 8.9 % | 0.4 % | 0.114 | 501 (0) |

## silence_v1

| Modell | Klipp | Hallusinasjon i stillhet | Innsatte ord | Sanntidsfaktor |
| --- | ---: | ---: | ---: | ---: |
| nb-whisper-large | 12 | 8.3 % | 6 | 0.0563 |
| nb-whisper-large-distil-turbo-beta | 12 | 33.3 % | 4 | 0.0116 |
| nb-whisper-medium | 12 | 75.0 % | 53 | 0.0743 |
| nb-whisper-small | 12 | 100.0 % | 62 | 0.0119 |
| whisper-large-v3 | 12 | 100.0 % | 48 | 0.0173 |
