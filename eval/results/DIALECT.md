# Resultater per dialekt: nb_samtale_test

## WER

| Modell | Alle | nord (247) | sørvest (159) | trøndelag (77)* | vest (131) | øst (547) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| whisper-large-v3 | 28,8 % | 28,4 % | 37,4 % | 33,0 % | 39,4 % | 24,0 % |
| nb-whisper-large-distil-turbo-beta | 29,9 % | 30,7 % | 39,1 % | 31,7 % | 41,2 % | 24,8 % |
| nb-whisper-large | 31,6 % | 31,8 % | 38,5 % | 33,9 % | 41,4 % | 27,4 % |
| nb-whisper-small | 34,1 % | 33,3 % | 42,1 % | 34,1 % | 44,1 % | 30,3 % |
| nb-whisper-medium | 34,7 % | 33,6 % | 42,2 % | 36,0 % | 46,0 % | 30,7 % |

## Utelatelser

| Modell | Alle | nord (247) | sørvest (159) | trøndelag (77)* | vest (131) | øst (547) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| whisper-large-v3 | 12,4 % | 13,7 % | 11,8 % | 14,1 % | 11,2 % | 12,1 % |
| nb-whisper-large-distil-turbo-beta | 17,3 % | 18,9 % | 17,3 % | 17,9 % | 17,1 % | 16,6 % |
| nb-whisper-large | 20,7 % | 21,1 % | 20,0 % | 22,0 % | 20,6 % | 20,5 % |
| nb-whisper-small | 19,5 % | 19,3 % | 18,1 % | 18,5 % | 19,6 % | 20,0 % |
| nb-whisper-medium | 21,3 % | 20,2 % | 20,6 % | 22,3 % | 23,6 % | 21,3 % |

## Ordrett WER

| Modell | Alle | nord (247) | sørvest (159) | trøndelag (77)* | vest (131) | øst (547) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| whisper-large-v3 | 32,0 % | 32,1 % | 39,5 % | 35,8 % | 41,7 % | 27,6 % |
| nb-whisper-large-distil-turbo-beta | 33,2 % | 34,2 % | 41,3 % | 34,8 % | 43,3 % | 28,4 % |
| nb-whisper-large | 34,8 % | 35,3 % | 40,8 % | 36,8 % | 43,6 % | 31,0 % |
| nb-whisper-small | 37,0 % | 36,6 % | 43,8 % | 37,1 % | 46,1 % | 33,7 % |
| nb-whisper-medium | 37,7 % | 37,0 % | 44,2 % | 38,8 % | 47,9 % | 34,1 % |

## Tapte nektelser

| Modell | nord (247) | sørvest (159) | trøndelag (77)* | vest (131) | øst (547) |
| --- | ---: | ---: | ---: | ---: | ---: |
| whisper-large-v3 | 9/58 | 8/45 | 3/25 | 12/39 | 43/198 |
| nb-whisper-large-distil-turbo-beta | 12/58 | 8/45 | 8/25 | 10/39 | 48/198 |
| nb-whisper-large | 15/58 | 12/45 | 6/25 | 10/39 | 57/198 |
| nb-whisper-small | 12/58 | 9/45 | 3/25 | 12/39 | 59/198 |
| nb-whisper-medium | 16/58 | 11/45 | 5/25 | 11/39 | 69/198 |

## Gap mellom beste og dårligste gruppe (WER)

| Modell | Beste | Dårligste | Forskjell |
| --- | --- | --- | ---: |
| whisper-large-v3 | øst | vest | 15,4 prosentpoeng |
| nb-whisper-large-distil-turbo-beta | øst | vest | 16,4 prosentpoeng |
| nb-whisper-large | øst | vest | 14,0 prosentpoeng |
| nb-whisper-small | øst | vest | 13,7 prosentpoeng |
| nb-whisper-medium | øst | vest | 15,3 prosentpoeng |

Tall i parentes: antall setninger i gruppen. «*»: under 100 setninger, usikkert tall.
WER og utelatelser i lesbar profil; ordrett WER beholder fyllord og avbrutte ord.

# Resultater per dialekt: nb_samtale_test_maalform

## WER

| Modell | Alle | nord (247) | sørvest (159) | trøndelag (77)* | vest (131) | øst (547) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| whisper-large-v3 | 27,8 % | 27,7 % | 35,0 % | 31,9 % | 35,0 % | 23,8 % |
| nb-whisper-large | 30,0 % | 30,3 % | 32,5 % | 34,0 % | 35,2 % | 27,6 % |
| nb-whisper-large-distil-turbo-beta | 30,7 % | 30,9 % | 40,4 % | 31,3 % | 46,1 % | 24,9 % |

## Utelatelser

| Modell | Alle | nord (247) | sørvest (159) | trøndelag (77)* | vest (131) | øst (547) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| whisper-large-v3 | 11,9 % | 12,9 % | 10,8 % | 13,3 % | 9,4 % | 12,1 % |
| nb-whisper-large | 22,3 % | 21,3 % | 23,3 % | 24,9 % | 25,2 % | 21,4 % |
| nb-whisper-large-distil-turbo-beta | 18,3 % | 19,3 % | 18,7 % | 17,7 % | 23,6 % | 16,8 % |

## Ordrett WER

| Modell | Alle | nord (247) | sørvest (159) | trøndelag (77)* | vest (131) | øst (547) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| whisper-large-v3 | 31,0 % | 31,4 % | 37,3 % | 34,8 % | 37,5 % | 27,5 % |
| nb-whisper-large | 33,3 % | 34,0 % | 34,9 % | 37,0 % | 37,6 % | 31,1 % |
| nb-whisper-large-distil-turbo-beta | 33,9 % | 34,4 % | 42,6 % | 34,4 % | 48,1 % | 28,5 % |

## Tapte nektelser

| Modell | nord (247) | sørvest (159) | trøndelag (77)* | vest (131) | øst (547) |
| --- | ---: | ---: | ---: | ---: | ---: |
| whisper-large-v3 | 8/58 | 6/45 | 3/25 | 14/39 | 43/198 |
| nb-whisper-large | 14/58 | 12/45 | 6/25 | 9/39 | 58/198 |
| nb-whisper-large-distil-turbo-beta | 12/58 | 11/45 | 8/25 | 11/39 | 48/198 |

## Gap mellom beste og dårligste gruppe (WER)

| Modell | Beste | Dårligste | Forskjell |
| --- | --- | --- | ---: |
| whisper-large-v3 | øst | sørvest | 11,2 prosentpoeng |
| nb-whisper-large | øst | vest | 7,6 prosentpoeng |
| nb-whisper-large-distil-turbo-beta | øst | vest | 21,3 prosentpoeng |

Tall i parentes: antall setninger i gruppen. «*»: under 100 setninger, usikkert tall.
WER og utelatelser i lesbar profil; ordrett WER beholder fyllord og avbrutte ord.
