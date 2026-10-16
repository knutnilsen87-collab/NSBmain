# -*- coding: utf-8 -*-
from __future__ import annotations
import re
import unicodedata
from typing import List, Dict

SYMBOLS: List[str] = [
    "_", " ",
    "a","b","c","d","e","f","g","h","i","j","k","l","m","n","o","p","q","r","s","t","u","v","w","x","y","z",
    "æ","ø","å",
    "A","B","C","D","E","F","G","H","I","J","K","L","M","N","O","P","Q","R","S","T","U","V","W","X","Y","Z",
    "Æ","Ø","Å",
    "0","1","2","3","4","5","6","7","8","9",
    ".",",",";"," :",":","!","?","-","–","—","'","\"","(",")","[","]","{","}","/","\\","@","#","%","&","+","=",
]
_symbol_to_id: Dict[str, int] = {s: i for i, s in enumerate(SYMBOLS)}
_id_to_symbol: Dict[int, str] = {i: s for i, s in enumerate(SYMBOLS)}

_replacements = {
    "\u2018": "'", "\u2019": "'", "\u201A": "'", "\u201B": "'",
    "\u201C": "\"", "\u201D": "\"", "\u201E": "\"", "\u201F": "\"",
    "\u00A0": " ", "\u2009": " ", "\u200A": " ", "\u200B": "",
    "\u202F": " ", "\u205F": " ", "\u3000": " ",
}
_allow_re = re.compile(r"[A-Za-zÆØÅæøå0-9 \.,;:!\?\-–—'\"\(\)\[\]\{\}/\\@#%&\+=]+")

def normalize_text(text: str) -> str:
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    for k, v in _replacements.items():
        text = text.replace(k, v)
    text = re.sub(r"\s+", " ", text).strip()
    m = _allow_re.findall(text)
    return "".join(m) if m else ""

def text_to_sequence(text: str):
    text = normalize_text(text)
    return [_symbol_to_id[ch] for ch in text if ch in _symbol_to_id]

def sequence_to_text(seq):
    return "".join(_id_to_symbol.get(int(i), "") for i in seq)
