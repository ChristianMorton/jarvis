"""Spoken-number parsing.

Vosk emits number words ("five", "twenty three"), not digits, so every command
that takes a count has to go through here.
"""

from __future__ import annotations

from typing import Optional, Sequence

UNITS = {
    "zero": 0, "oh": 0, "o": 0, "nought": 0,
    "one": 1, "won": 1, "a": 1, "an": 1,
    "two": 2, "to": 2, "too": 2,
    "three": 3, "four": 4, "for": 4, "fore": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "ate": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}

TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

SCALES = {"hundred": 100, "thousand": 1000}

ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11,
    "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
    "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
    "twentieth": 20,
}

#: Every word this module can consume. Fed into the Vosk grammar so the decoder
#: is allowed to emit them even when no command literal mentions a number.
NUMBER_WORDS = sorted(set(UNITS) | set(TENS) | set(SCALES) | set(ORDINALS) | {"and"})


def _token_value(token: str) -> Optional[int]:
    if token.isdigit():
        return int(token)
    for table in (UNITS, TENS, ORDINALS):
        if token in table:
            return table[token]
    return None


def _can_extend(current: int, value: int) -> bool:
    """True if ``value`` slots into the empty low places of ``current``.

    Lets "twenty"+"three" make 23 and "a hundred"+"five" make 105, while
    rejecting "three"+"five", which is two numbers rather than one.
    """
    if current == 0:
        return False
    if value < 10:
        return current % 10 == 0
    if value < 100:
        return current % 100 == 0
    return False


def parse_number(tokens: Sequence[str]) -> Optional[int]:
    """Parse a full token sequence as one number, or return None.

    Handles "seven", "twenty three", "a hundred and five", "42".
    """
    if not tokens:
        return None

    total = 0
    current = 0
    seen_value = False

    for token in tokens:
        if token == "and":
            # Only legal mid-number ("a hundred and five"), never leading.
            if not seen_value:
                return None
            continue
        if token in SCALES:
            if not seen_value:
                current = 1  # bare "hundred" means 100
            scale = SCALES[token]
            if scale == 100:
                current *= scale
            else:
                total += (current or 1) * scale
                current = 0
            seen_value = True
            continue
        value = _token_value(token)
        if value is None:
            return None
        if token in TENS:
            # "twenty" alone, or trailing a hundreds block: "a hundred twenty".
            if current and current % 100 != 0:
                return None
            current += value
        elif _can_extend(current, value):
            current += value  # "twenty"+"three", "a hundred"+"five"
        elif current:
            return None  # "three five" is not a number
        else:
            current = value
        seen_value = True

    if not seen_value:
        return None
    return total + current


def take_number(tokens: Sequence[str], start: int = 0, max_len: int = 4):
    """Greedily consume a number from ``tokens`` at ``start``.

    Returns ``(value, tokens_consumed)`` for the longest prefix that parses,
    or ``(None, 0)``.
    """
    best: tuple[Optional[int], int] = (None, 0)
    for length in range(1, min(max_len, len(tokens) - start) + 1):
        value = parse_number(tokens[start:start + length])
        if value is not None:
            best = (value, length)
    return best
