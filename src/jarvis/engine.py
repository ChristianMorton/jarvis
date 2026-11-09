"""The wake-word state machine and command dispatcher."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .actions import ActionContext, get_action
from .config import Config, render_args
from .drivers.base import Driver
from .matcher import MatchResult, Matcher, normalize

log = logging.getLogger("jarvis")

#: Actions that set the wake state themselves. Auto-re-arming after one of
#: these would undo it, so "stand down" would never stand anything down.
STATE_ACTIONS = frozenset({"arm", "disarm", "sleep", "wake", "quit"})


@dataclass
class Outcome:
    """What the engine did with one utterance."""

    heard: str
    handled: bool = False
    armed: bool = False
    notes: list[str] = field(default_factory=list)
    error: Optional[str] = None
    ignored_reason: Optional[str] = None

    def __str__(self) -> str:
        if self.error:
            return f"error: {self.error}"
        if self.notes:
            return " ; ".join(self.notes)
        return self.ignored_reason or "ignored"


class Engine:
    def __init__(
        self,
        config: Config,
        driver: Driver,
        on_feedback: Optional[Callable[[str, Outcome], None]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.driver = driver
        self.on_feedback = on_feedback
        self.clock = clock

        self.matcher = Matcher(
            commands=config.commands,
            lists=config.lists,
            fuzzy_threshold=float(config.get("recognition.fuzzy_threshold", 0.75)),
            fillers=config.get("fillers", []),
        )
        self.wake_aliases = set(config.wake_aliases)
        self.arm_seconds = float(config.get("arm_seconds", 5.0))
        self.arm_after_command = bool(config.get("arm_after_command", True))
        self.require_wake_word = bool(config.get("require_wake_word", True))
        self.chain_separators = config.get("chain_separators", ["then"])
        self.vars = dict(config.get("vars", {}) or {})

        self.armed_until = 0.0
        self.paused = False
        self.running = True
        self.grid = None
        self._last: Optional[list[MatchResult]] = None

    # --- wake state -----------------------------------------------------
    @property
    def is_armed(self) -> bool:
        return self.clock() < self.armed_until

    def arm(self, seconds: Optional[float] = None) -> None:
        self.armed_until = self.clock() + (
            self.arm_seconds if seconds is None else float(seconds)
        )

    def disarm(self) -> None:
        self.armed_until = 0.0

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        if paused:
            self.disarm()

    def stop(self) -> None:
        self.running = False

    # --- dispatch -------------------------------------------------------
    def strip_wake_word(self, text: str) -> tuple[bool, str]:
        """Return ``(saw_wake_word, remainder)``.

        The wake word may repeat ("jarvis jarvis scroll down") when the
        decoder splits an utterance, so consume every leading instance.
        """
        tokens = normalize(text)
        index = 0
        while index < len(tokens) and tokens[index] in self.wake_aliases:
            index += 1
        return index > 0, " ".join(tokens[index:])

    def handle(self, text: str) -> Outcome:
        """Process one final transcript."""
        outcome = Outcome(heard=text.strip())
        if not outcome.heard:
            return outcome

        saw_wake, remainder = self.strip_wake_word(text)

        if self.paused and not saw_wake:
            outcome.ignored_reason = "paused"
            return self._finish(outcome)

        if not saw_wake and not self.is_armed and self.require_wake_word:
            outcome.ignored_reason = "no wake word"
            return self._finish(outcome)

        if saw_wake and not remainder:
            # Bare "Jarvis": arm and wait for the follow-up.
            self.set_paused(False)
            self.arm()
            outcome.armed = True
            outcome.handled = True
            outcome.notes.append("listening")
            return self._finish(outcome)

        if saw_wake:
            self.set_paused(False)

        matches = self.matcher.match_chain(remainder, self.chain_separators)
        if not matches:
            outcome.ignored_reason = f"no command matched {remainder!r}"
            # Keep the window open: a misfire shouldn't force another wake word.
            if self.is_armed:
                self.arm()
            return self._finish(outcome)

        self._run(matches, outcome)
        manages_own_state = any(m.command.action in STATE_ACTIONS for m in matches)
        if self.arm_after_command and not outcome.error and not manages_own_state:
            self.arm()
            outcome.armed = True
        else:
            outcome.armed = self.is_armed
        return self._finish(outcome)

    def _run(self, matches: list[MatchResult], outcome: Outcome) -> None:
        repeatable = []
        for match in matches:
            command = match.command
            try:
                # Slots shadow config vars, so a spoken value always wins.
                args = render_args(command.args, {**self.vars, **match.slots})
                context = ActionContext(
                    driver=self.driver, config=self.config, engine=self, slots=match.slots
                )
                note = get_action(command.action)(context, args or {})
                outcome.handled = True
                if note:
                    outcome.notes.append(str(note))
                if command.action not in ("repeat", "quit"):
                    repeatable.append(match)
            except Exception as exc:  # a bad command must not kill the loop
                log.exception("command %s failed", command.id)
                outcome.error = f"{command.id}: {exc}"
                break
        if repeatable:
            self._last = repeatable

    def repeat_last(self, times: int = 1) -> str:
        if not self._last:
            return "nothing to repeat"
        scratch = Outcome(heard="<repeat>")
        for _ in range(max(1, min(int(times), 50))):
            self._run(list(self._last), scratch)
            if scratch.error:
                return scratch.error
        return f"repeated x{times}"

    def _finish(self, outcome: Outcome) -> Outcome:
        if self.on_feedback:
            kind = "err" if outcome.error else ("ok" if outcome.handled else "ignored")
            if outcome.armed and not outcome.notes[1:] and outcome.notes[:1] == ["listening"]:
                kind = "arm"
            self.on_feedback(kind, outcome)
        return outcome
