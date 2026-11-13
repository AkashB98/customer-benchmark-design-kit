"""Text normalization for STT scoring.

The contract declares ONE normalization profile. Scoring must apply
that exact profile to both the truth (reference) text and every
vendor hypothesis before any error rate is computed. If the truth
file was produced under a different profile — digits where the
contract says number words, say — a naive raw comparison inflates
WER by several points for reasons that have nothing to do with
recognition quality. That planted defect is what validation catches.
"""
from __future__ import annotations

import re
import string

# Digit token -> word form. Only single tokens 0-99 plus hundreds used
# in the synthetic templates are needed; anything else is left as-is.
_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven",
         "eight", "nine", "ten", "eleven", "twelve", "thirteen",
         "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
         "nineteen"]
_TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty",
         60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety"}


def _digit_token_to_words(tok: str) -> str:
    if not tok.isdigit():
        return tok
    n = int(tok)
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, rem = divmod(n, 10)
        base = _TENS[tens * 10]
        return base if rem == 0 else f"{base} {_ONES[rem]}"
    if n == 100:
        return "one hundred"
    return tok


def normalize_text(text: str, profile: dict) -> str:
    """Apply a declared normalization profile to one transcript.

    Profile keys: lowercase (bool), strip_punctuation (bool),
    number_format ("words" | "digits").
    """
    out = text
    if profile.get("lowercase"):
        out = out.lower()
    if profile.get("strip_punctuation"):
        out = out.translate(str.maketrans("", "", string.punctuation))
    tokens = out.split()
    if profile.get("number_format") == "words":
        expanded = []
        for tok in tokens:
            expanded.extend(_digit_token_to_words(tok).split())
        tokens = expanded
    # "digits" profile: synthetic templates already use words, so a
    # digits-profile truth file is produced by the generator's
    # reverse mapping, not here. Scoring under "digits" leaves word
    # numbers untouched — which is exactly why mixing profiles breaks.
    return " ".join(tokens)


def words(text: str) -> list:
    return text.split() if text.strip() else []
