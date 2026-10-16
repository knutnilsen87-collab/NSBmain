# -*- coding: utf-8 -*-
from __future__ import annotations

class CharTokenizer:
    """
    En enkel char-level tokenizer.
    - Bygger vokabular dynamisk (eller fra et startsett)
    - Har <pad> og <unk>
    """
    def __init__(self, init_chars: str | None = None):
        self.stoi = {"<pad>": 0, "<unk>": 1}
        self.itos = {0: "<pad>", 1: "<unk>"}

        # Et fornuftig startsett (ASCII + norske bokstaver + vanlige tegn)
        base = " abcdefghijklmnopqrstuvwxyzæøåABCDEFGHIJKLMNOPQRSTUVWXYZÆØÅ0123456789"
        punct = ".,!?;:'\"-()[]{}«»/\\@#%&+=*<>|_~`"
        extra = "µ°"  # behold om du trenger disse

        chars = base + punct + extra
        if init_chars:
            chars += init_chars

        for ch in chars:
            self._add(ch)

    def _add(self, ch: str):
        if ch not in self.stoi:
            i = len(self.stoi)
            self.stoi[ch] = i
            self.itos[i] = ch

    def encode(self, text: str):
        ids = []
        for ch in text:
            if ch not in self.stoi:
                self._add(ch)
            ids.append(self.stoi.get(ch, 1))
        return ids

    @property
    def vocab_size(self) -> int:
        return len(self.stoi)
