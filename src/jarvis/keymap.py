"""Turn spoken key names into chord strings the driver understands.

    "control c"          -> "ctrl+c"
    "control shift p"    -> "ctrl+shift+p"
    "alt f four"         -> "alt+f4"
    "control alpha"      -> "ctrl+a"

The NATO alphabet is supported because single letters are the hardest thing
for any recogniser to get right: "b", "d", "e", "p", "t" and "v" all collapse
into each other, while "bravo" and "delta" never do.
"""

from __future__ import annotations

from .matcher import normalize
from .numbers import parse_number

MODIFIER_WORDS = {
    "control": "ctrl", "ctrl": "ctrl", "command": "ctrl", "cmd": "ctrl",
    "alt": "alt", "option": "alt", "meta": "alt",
    "shift": "shift",
    "windows": "win", "win": "win", "super": "win", "start": "win",
}

NATO = {
    "alpha": "a", "alfa": "a", "bravo": "b", "charlie": "c", "delta": "d",
    "echo": "e", "foxtrot": "f", "golf": "g", "hotel": "h", "india": "i",
    "juliet": "j", "juliett": "j", "kilo": "k", "lima": "l", "mike": "m",
    "november": "n", "oscar": "o", "papa": "p", "quebec": "q", "romeo": "r",
    "sierra": "s", "tango": "t", "uniform": "u", "victor": "v", "whiskey": "w",
    "xray": "x", "x-ray": "x", "yankee": "y", "zulu": "z",
}

NAMED_KEYS = {
    "enter": "enter", "return": "enter", "newline": "enter",
    "escape": "escape", "esc": "escape",
    "tab": "tab", "space": "space", "spacebar": "space",
    "backspace": "backspace", "delete": "delete", "del": "delete",
    "insert": "insert", "home": "home", "end": "end",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "pageup": "pageup", "pagedown": "pagedown",
    "comma": ",", "period": ".", "dot": ".", "slash": "/", "backslash": "\\",
    "semicolon": ";", "quote": "'", "backtick": "`", "tick": "`",
    "minus": "-", "dash": "-", "equals": "=", "plus": "=",
    "bracket": "[", "leftbracket": "[", "rightbracket": "]",
}

_MULTIWORD = {
    ("page", "up"): "pageup",
    ("page", "down"): "pagedown",
    ("left", "bracket"): "[",
    ("right", "bracket"): "]",
    ("open", "bracket"): "[",
    ("close", "bracket"): "]",
    ("caps", "lock"): "capslock",
    ("print", "screen"): "printscreen",
    ("arrow", "up"): "up", ("arrow", "down"): "down",
    ("arrow", "left"): "left", ("arrow", "right"): "right",
}

#: Every word this module can consume, for the Vosk grammar.
KEY_WORDS = sorted(
    set(MODIFIER_WORDS) | set(NATO) | set(NAMED_KEYS)
    | {w for pair in _MULTIWORD for w in pair}
    | {chr(c) for c in range(ord("a"), ord("z") + 1)}
    | {"key", "function", "f"}
)


class KeyParseError(ValueError):
    pass


def spoken_to_chord(text: str) -> str:
    """Parse a spoken key description into a chord like ``ctrl+shift+p``."""
    tokens = [t for t in normalize(text) if t not in ("key", "the", "and", "then")]
    if not tokens:
        raise KeyParseError("nothing to press")

    modifiers: list[str] = []
    keys: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]

        pair = tuple(tokens[index:index + 2])
        if pair in _MULTIWORD:
            keys.append(_MULTIWORD[pair])
            index += 2
            continue

        if token in MODIFIER_WORDS:
            modifier = MODIFIER_WORDS[token]
            if index + 1 < len(tokens):
                if modifier not in modifiers:
                    modifiers.append(modifier)
            else:
                keys.append(modifier)  # trailing modifier is the key itself
            index += 1
            continue

        # "f four" / "function four" -> f4
        if token in ("f", "function") and index + 1 < len(tokens):
            number = parse_number([tokens[index + 1]])
            if number is not None and 1 <= number <= 24:
                keys.append(f"f{number}")
                index += 2
                continue

        if token in NATO:
            keys.append(NATO[token])
        elif token in NAMED_KEYS:
            keys.append(NAMED_KEYS[token])
        elif len(token) == 1 and (token.isalnum() or token in NAMED_KEYS.values()):
            keys.append(token)
        elif token.isdigit():
            keys.extend(list(token))
        else:
            number = parse_number([token])
            if number is not None and 0 <= number <= 9:
                keys.append(str(number))
            else:
                raise KeyParseError(f"don't know the key {token!r} (in {text!r})")
        index += 1

    if not keys:
        # "control" alone: press the modifier as the key.
        if modifiers:
            return modifiers[-1]
        raise KeyParseError(f"no key in {text!r}")

    prefix = "+".join(modifiers)
    # Several keys means a sequence, and only the first carries the modifiers:
    # "control a delete" -> "ctrl+a delete".
    chords = [("+".join([prefix, keys[0]]) if prefix else keys[0])] + keys[1:]
    return " ".join(chords)
