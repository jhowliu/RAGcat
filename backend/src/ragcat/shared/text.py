"""Language-aware text measures shared by Ingestion (chunk sizes) and Curation (warnings, token counts).

Latin text is measured in words. CJK text has no spaces, so it is measured in characters,
with 1.5 characters counting as one word-equivalent unit; sentence ends include 。！？.
"""

from __future__ import annotations

import re

CJK_RANGES = "぀-ヿ㐀-䶿一-鿿豈-﫿가-힯"
CJK_PER_UNIT = 1.5

_CJK = re.compile(f"[{CJK_RANGES}]")
_CJK_OR_PUNCT = re.compile(f"[{CJK_RANGES}　-〿＀-￯]")
_WORD = re.compile(f"[^\\W{CJK_RANGES}]+")  # word characters, excluding CJK
_SENTENCE_END = re.compile(
    r"[。！？]+[」』”’）)]*"  # CJK sentences end at the punctuation itself
    r"|[.!?]+[\"'”’)]*(?=\s+[\"'“‘(A-Z0-9" + CJK_RANGES + "])"  # Latin: then a space and a new sentence
)


def words(text: str) -> list[str]:
    """Latin-script words (and numbers); CJK characters are counted separately."""
    return _WORD.findall(text)


def cjk_chars(text: str) -> int:
    return len(_CJK.findall(text))


def text_length(text: str) -> int:
    """Word-equivalent length: comparable between English and CJK text."""
    return round(len(words(text)) + cjk_chars(text) / CJK_PER_UNIT)


def token_estimate(text: str) -> int:
    """Rough embedding/LLM token count: ~1.3 per English word, ~1 per CJK character."""
    return round(len(words(text)) * 1.3 + cjk_chars(text))


def joins_tightly(left: str, right: str) -> bool:
    """CJK text is written without spaces between characters, lines or sentences."""
    return bool(left and right and _CJK_OR_PUNCT.match(left[-1]) and _CJK_OR_PUNCT.match(right[0]))


def join_text(left: str, right: str) -> str:
    if not left or not right:
        return left or right
    return left + right if joins_tightly(left, right) else f"{left} {right}"


def sentences(text: str) -> list[str]:
    out, start = [], 0
    for match in _SENTENCE_END.finditer(text):
        piece = text[start : match.end()].strip()
        if piece:
            out.append(piece)
        start = match.end()
    rest = text[start:].strip()
    if rest:
        out.append(rest)
    return out
