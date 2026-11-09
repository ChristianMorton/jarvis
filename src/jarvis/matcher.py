"""Turn a raw transcript into a concrete command invocation.

A *pattern* is a whitespace-separated string of literal tokens and slots:

    "scroll down"
    "scroll down {count:number}"
    "switch to {app:apps}"
    "type {text:rest}"

Slot types
    number   one or more tokens parsed as a spoken number ("twenty three")
    word     exactly one token
    rest     every remaining token, joined (must be last)
    <name>   a named list from the config; matches the longest alias in it

A trailing ``?`` on the type marks the slot optional: ``{count:number?}``.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .numbers import take_number

SLOT_RE = re.compile(r"^\{(?P<name>\w+)(?::(?P<type>\w+))?(?P<opt>\?)?\}$")
_PUNCT_RE = re.compile(r"[^\w\s'-]+")


def normalize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split into tokens."""
    text = _PUNCT_RE.sub(" ", text.lower())
    return text.split()


@dataclass(frozen=True)
class Slot:
    name: str
    type: str
    optional: bool = False


@dataclass
class Pattern:
    raw: str
    parts: list = field(default_factory=list)  # str literals and Slot objects

    @property
    def literal_count(self) -> int:
        return sum(1 for p in self.parts if isinstance(p, str))

    @property
    def slot_count(self) -> int:
        return sum(1 for p in self.parts if isinstance(p, Slot))


def compile_pattern(raw: str) -> Pattern:
    parts: list = []
    for token in raw.split():
        match = SLOT_RE.match(token)
        if match:
            parts.append(
                Slot(
                    name=match["name"],
                    type=(match["type"] or "word"),
                    optional=bool(match["opt"]),
                )
            )
        else:
            parts.append(normalize(token)[0] if normalize(token) else token.lower())
    if any(isinstance(p, Slot) and p.type == "rest" for p in parts[:-1]):
        raise ValueError(f"a 'rest' slot must be last: {raw!r}")
    return Pattern(raw=raw, parts=parts)


@dataclass
class MatchResult:
    command: Any
    pattern: Pattern
    slots: dict[str, Any]
    consumed: int          # tokens of the transcript this match used
    literal_score: int     # literal tokens matched (higher = more specific)
    fuzzy: bool = False    # True if any literal needed fuzzy equality


def _tokens_equal(spoken: str, literal: str, threshold: float) -> tuple[bool, bool]:
    """Return ``(matched, was_fuzzy)`` for one token against one literal.

    Fuzzy equality is deliberately asymmetric about where the slip may fall:
    the first character must agree. One substitution in a four-letter word
    scores only 0.75, so a threshold loose enough to catch "dowm" for "down"
    is also loose enough to catch "town" for "down" — and firing the wrong
    command is worse than missing one. Requiring the initial character rules
    out the whole family of "accept"/"except", "next"/"text", "town"/"down"
    confusions while still absorbing the tail-end errors a decoder actually
    makes.
    """
    if spoken == literal:
        return True, False
    if threshold >= 1.0 or len(literal) < 4 or len(spoken) < 4:
        return False, False
    if spoken[0] != literal[0]:
        return False, False
    ratio = difflib.SequenceMatcher(None, spoken, literal).ratio()
    return (ratio >= threshold), True


def _match_list(
    tokens: list[str], start: int, aliases: dict[str, Any], threshold: float
) -> Optional[tuple[Any, int, bool]]:
    """Longest-alias match from a named list. Returns (value, length, fuzzy)."""
    best: Optional[tuple[Any, int, bool]] = None
    for alias, value in aliases.items():
        alias_tokens = normalize(alias)
        if not alias_tokens or start + len(alias_tokens) > len(tokens):
            continue
        fuzzy = False
        ok = True
        for offset, alias_token in enumerate(alias_tokens):
            matched, was_fuzzy = _tokens_equal(
                tokens[start + offset], alias_token, threshold
            )
            if not matched:
                ok = False
                break
            fuzzy = fuzzy or was_fuzzy
        if ok and (best is None or len(alias_tokens) > best[1] or (fuzzy is False and best[2])):
            best = (value, len(alias_tokens), fuzzy)
    return best


def match_pattern(
    pattern: Pattern,
    tokens: list[str],
    lists: dict[str, dict[str, Any]],
    threshold: float = 1.0,
) -> Optional[tuple[dict[str, Any], int, int, bool]]:
    """Match ``pattern`` against a prefix of ``tokens``.

    Returns ``(slots, consumed, literal_score, fuzzy)`` or None.
    """
    slots: dict[str, Any] = {}
    index = 0
    literal_score = 0
    fuzzy_used = False

    for part in pattern.parts:
        if isinstance(part, str):
            if index >= len(tokens):
                return None
            matched, was_fuzzy = _tokens_equal(tokens[index], part, threshold)
            if not matched:
                return None
            fuzzy_used = fuzzy_used or was_fuzzy
            literal_score += 1
            index += 1
            continue

        # --- slot ---
        if part.type == "number":
            value, length = take_number(tokens, index)
            if value is None:
                if part.optional:
                    slots[part.name] = None
                    continue
                return None
            slots[part.name] = value
            index += length

        elif part.type == "word":
            if index >= len(tokens):
                if part.optional:
                    slots[part.name] = None
                    continue
                return None
            slots[part.name] = tokens[index]
            index += 1

        elif part.type == "rest":
            if index >= len(tokens):
                if part.optional:
                    slots[part.name] = None
                    continue
                return None
            slots[part.name] = " ".join(tokens[index:])
            index = len(tokens)

        else:  # named list
            aliases = lists.get(part.type)
            if aliases is None:
                raise KeyError(f"unknown slot list {part.type!r} in {pattern.raw!r}")
            found = _match_list(tokens, index, aliases, threshold)
            if found is None:
                if part.optional:
                    slots[part.name] = None
                    continue
                return None
            value, length, was_fuzzy = found
            fuzzy_used = fuzzy_used or was_fuzzy
            slots[part.name] = value
            index += length

    return slots, index, literal_score, fuzzy_used


class Matcher:
    """Matches transcripts against a compiled command set."""

    def __init__(
        self,
        commands: Iterable[Any],
        lists: Optional[dict[str, dict[str, Any]]] = None,
        fuzzy_threshold: float = 0.84,
        fillers: Iterable[str] = (),
    ) -> None:
        self.commands = list(commands)
        self.lists = lists or {}
        self.fuzzy_threshold = fuzzy_threshold

        # A word that some command uses as a literal is not a filler, whatever
        # the config says. Stripping "the" from the transcript while leaving it
        # in the pattern makes "show the plan" permanently unmatchable, and the
        # command looks fine right up until you say it out loud.
        self.fillers = set(fillers) - self._literal_vocabulary()

    def _literal_vocabulary(self) -> set[str]:
        words: set[str] = set()
        for command in self.commands:
            for pattern in command.patterns:
                words.update(p for p in pattern.parts if isinstance(p, str))
        return words

    def strip_fillers(self, tokens: list[str]) -> list[str]:
        return [t for t in tokens if t not in self.fillers] or tokens

    def match(self, text: str, allow_trailing: bool = False) -> Optional[MatchResult]:
        """Best match for ``text``, or None.

        With ``allow_trailing`` a match that leaves tokens unconsumed is
        permitted (used for chained utterances); otherwise the whole
        transcript must be consumed.
        """
        tokens = self.strip_fillers(normalize(text))
        if not tokens:
            return None

        # Exact pass first; only fall back to fuzzy if nothing matched cleanly,
        # so a crisp transcript can never lose to a fuzzy near-miss.
        for threshold in (1.0, self.fuzzy_threshold):
            best: Optional[MatchResult] = None
            for command in self.commands:
                for pattern in command.patterns:
                    result = match_pattern(pattern, tokens, self.lists, threshold)
                    if result is None:
                        continue
                    slots, consumed, literal_score, fuzzy = result
                    if consumed < len(tokens) and not allow_trailing:
                        continue
                    candidate = MatchResult(
                        command=command,
                        pattern=pattern,
                        slots=slots,
                        consumed=consumed,
                        literal_score=literal_score,
                        fuzzy=fuzzy,
                    )
                    if best is None or self._better(candidate, best):
                        best = candidate
            if best is not None:
                return best
            if threshold >= 1.0 and self.fuzzy_threshold >= 1.0:
                break
        return None

    @staticmethod
    def _better(candidate: MatchResult, incumbent: MatchResult) -> bool:
        """More literal tokens wins; then more transcript consumed; then fewer slots."""
        key_c = (candidate.literal_score, candidate.consumed, -candidate.pattern.slot_count)
        key_i = (incumbent.literal_score, incumbent.consumed, -incumbent.pattern.slot_count)
        return key_c > key_i

    def match_chain(self, text: str, separators: Iterable[str] = ("then",)) -> list[MatchResult]:
        """Split on separator words and match each segment.

        Falls back to matching the whole utterance if splitting yields nothing.
        """
        seps = set(separators)
        tokens = self.strip_fillers(normalize(text))
        segments: list[list[str]] = [[]]
        for token in tokens:
            if token in seps and segments[-1]:
                segments.append([])
            else:
                segments[-1].append(token)
        segments = [s for s in segments if s]

        if len(segments) > 1:
            results = [self.match(" ".join(s)) for s in segments]
            if all(r is not None for r in results):
                return [r for r in results if r is not None]

        whole = self.match(text)
        return [whole] if whole else []
