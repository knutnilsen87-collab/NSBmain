"""nsb_eval: faste, etterprøvbare målinger av norsk talegjenkjenning.

Moduler:

- ``normalize``: felles tekstnormalisering for norsk
- ``metrics``: WER, CER og hallusinasjonsflagg
- ``manifest``: lasting av testsett
- ``backends``: faster-whisper (Whisper og NB-Whisper) og en mock for tester
- ``runner``: kjører én modell mot ett testsett
- ``silence``: lager stillhet- og støysettet
- ``report``: samler resultater til én tabell
"""

__version__ = "1.0.0"
