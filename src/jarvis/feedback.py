"""Audible and on-screen acknowledgement.

The point is latency, not information: you need to know within ~100ms whether
Jarvis heard you, without looking away from what you were doing.
"""

from __future__ import annotations

import sys
import threading
from typing import Optional

TONES = {"arm": (880, 70), "ok": (1320, 55), "err": (220, 160), "ignored": None}

COLOURS = {
    "arm": "\033[36m", "ok": "\033[32m", "err": "\033[31m",
    "ignored": "\033[90m", "heard": "\033[37m", "reset": "\033[0m",
}


class Feedback:
    def __init__(self, driver, config) -> None:
        self.driver = driver
        self.beep_enabled = bool(config.get("feedback.beep", True))
        self.log_enabled = bool(config.get("feedback.log", True))
        self.show_ignored = bool(config.get("feedback.show_ignored", True))
        overrides = config.get("feedback.beep_hz", {}) or {}
        self.tones = dict(TONES)
        for kind, hz in overrides.items():
            base = TONES.get(kind) or (880, 70)
            self.tones[kind] = (int(hz), base[1])
        self.colour = sys.stdout.isatty()

    def _paint(self, kind: str, text: str) -> str:
        if not self.colour:
            return text
        return f"{COLOURS.get(kind, '')}{text}{COLOURS['reset']}"

    def beep(self, kind: str) -> None:
        tone = self.tones.get(kind)
        if not self.beep_enabled or not tone:
            return
        frequency, duration = tone
        # Beep() blocks for its full duration; never on the decode loop.
        threading.Thread(
            target=self.driver.beep, args=(frequency, duration), daemon=True
        ).start()

    def __call__(self, kind: str, outcome) -> None:
        self.beep(kind)
        if not self.log_enabled:
            return
        if kind == "ignored" and not self.show_ignored:
            return
        marks = {"arm": "◉", "ok": "✓", "err": "✗", "ignored": "·"}
        heard = self._paint("heard", f'"{outcome.heard}"')
        detail = str(outcome)
        print(f"{self._paint(kind, marks.get(kind, '·'))} {heard}  {self._paint(kind, detail)}",
              flush=True)
