# NorwegianSpeechBase – prosjektkontrakt

**Sist oppdatert:** 2026-10-16. Erstatter kontrakten fra 2025-12-29, som beskrev `train_whisper.py` (deaktivert) og `whisper-medium` (faktisk brukt: `whisper-small`).

## 1. Hva som er sant nå

- Målestokken (`nsb_eval`) er eneste kilde til kvalitetstall. Tall fra treningsløkken er bare veiledende.
- De faste testsettene i `eval/testsets/` er låst med sjekksum og brukes aldri til trening.
- Utgangspunkt for videre arbeid er NB-Whisper (Apache 2.0), ikke egen trening fra Whisper.
- Trening skjer med `src/python/train_whisper_iterable.py`.

## 2. Treningskontrakt (gjelder `train_whisper_iterable.py`)

Invarianter som ikke skal brytes:

1. Språk og oppgave settes: `set_prefix_tokens(language, task="transcribe")` og `generate(language=..., task="transcribe")`.
2. Etiketter fylles ut med -100, aldri ved å maskere `pad_token_id` (Whisper har `pad == eos`; sluttokenet må beholdes).
3. Start-tokenet fjernes fra etikettene før forskyvning.
4. Strømmen stokkes (`--shuffle_size`, fast frø per epoke).
5. Fasiter renses med `clean_training_text`: stille opptak med tekst og usikre segmenter forkastes, uttalt tegnsetting (`\Komma`) håndteres.
6. Train/val/test deles per taler med `split_by_group.py`, og de faste testsettene ekskluderes.
7. Beste modell lagres i `best/` etter WER på valideringssettet; bare de siste `--keep_last` stegmappene beholdes.
8. Lazy lasting, `num_workers=0` på Windows, korrupte filer hoppes over.

## 3. Kjente feil (KFM) som har skjedd

| Feil | Symptom | Årsak | Status |
| --- | --- | --- | --- |
| Manglende språk/oppgave | WER steg fra 0,24 til 8,9 mens tapet falt | Etiketter uten `<\|no\|><\|transcribe\|>`, `generate()` uten språk | Rettet 2026-10-16 |
| Sluttoken maskert | Gjentakelsesløkker, WER over 1 | `labels == pad_token_id` maskerte også `eos` | Rettet 2026-10-16 |
| Ingen stokking | Bare første 22 % av NST sett på 40k steg | Filen lest i rekkefølge | Rettet 2026-10-16 |
| `(...Vær stille under dette opptaket...)` som fasit | Modellen lærer å finne på tekst i stillhet | 1 011 NST-klipp | Filtreres |
| `\Komma` i fasit | Modellen skriver «\Komma» | NST-diktat med uttalt tegnsetting (~21 000 klipp) | Håndteres |
| Split per setning | Valideringstall måler pugging | Samme taler og manus i train og val | `split_by_group.py` |
| `--out_dir True` | Modell lagret i mappen «True» | PowerShell-variabel sendt inn som tekst | Stoppes av `validate_out_dir` |
| `datasets.map` over alt | ArrowMemoryError | Arrow-buffer | Forbudt |
| `num_workers > 0` på Windows | spawn/pickle-feil | multiprocessing | Forbudt |

## 4. Miljø

- Windows 11, PowerShell 7, RTX 4080 (16 GB).
- Målestokk: Python 3.11, `faster-whisper==1.2.1`, `av<16` (nyere PyAV er inkompatibel), CUDA-biblioteker fra pip (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12==9.*`). Se `scripts/run_benchmark.ps1`.
