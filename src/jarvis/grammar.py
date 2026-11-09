"""Build the restricted vocabulary handed to Vosk.

Vosk can be constrained to a fixed word list, and doing so is the single
biggest accuracy win available here: told that the only things anyone will
ever say are your ~400 command words, the decoder stops guessing at English
and starts choosing between commands.

The cost is that anything outside the list is unrecognisable — which is why
prose goes to Wispr Flow instead (see packs/dictation.yaml).

Only models with a dynamic graph support this: the ``small`` models do, as
does ``vosk-model-en-us-0.22-lgraph``. The plain large models do not, and
``Config.recognition.restrict_grammar: false`` turns it off.
"""

from __future__ import annotations

import json
from typing import Iterable

from .keymap import KEY_WORDS
from .matcher import Slot, normalize
from .numbers import NUMBER_WORDS

#: Vosk's out-of-vocabulary token. Without it the decoder must map every
#: sound onto some in-grammar word, and background speech fires commands.
UNKNOWN = "[unk]"


def collect_words(config) -> list[str]:
    """Every word the recogniser is allowed to emit, sorted and de-duplicated."""
    words: set[str] = set()

    for command in config.commands:
        for pattern in command.patterns:
            for part in pattern.parts:
                if isinstance(part, str):
                    words.update(normalize(part))
                elif isinstance(part, Slot) and part.type not in (
                    "number", "word", "rest"
                ):
                    for alias in config.lists.get(part.type, {}):
                        words.update(normalize(alias))

    words.update(config.wake_aliases)
    words.update(NUMBER_WORDS)
    words.update(KEY_WORDS)
    words.update(normalize(" ".join(config.get("fillers", []) or [])))
    words.update(normalize(" ".join(config.get("chain_separators", []) or [])))
    words.update(normalize(" ".join(config.get("recognition.extra_words", []) or [])))

    words = {w for w in words if w and not w.startswith("[")}
    return sorted(words)


def build_grammar(config) -> str:
    """JSON grammar string for ``KaldiRecognizer(model, rate, grammar)``."""
    return json.dumps(collect_words(config) + [UNKNOWN])


def describe(words: Iterable[str], limit: int = 24) -> str:
    words = list(words)
    head = ", ".join(words[:limit])
    suffix = f", … (+{len(words) - limit} more)" if len(words) > limit else ""
    return f"{len(words)} words: {head}{suffix}"
