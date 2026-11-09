"""A driver that records calls instead of performing them.

Used by ``jarvis test`` / ``--dry-run`` and by the test-suite, so the whole
pipeline is exercisable on a machine that is not Windows.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .base import Driver, WindowInfo


class NullDriver(Driver):
    name = "null"
    available = True

    def __init__(self, echo: bool = True, windows: Optional[Sequence[WindowInfo]] = None):
        self.echo = echo
        self.calls: list[tuple] = []
        self._windows = list(windows or [
            WindowInfo(1, "Mozilla Firefox", "firefox.exe"),
            WindowInfo(2, "Visual Studio Code", "code.exe"),
            WindowInfo(3, "Windows PowerShell", "powershell.exe"),
        ])

    def _record(self, *call) -> None:
        self.calls.append(call)
        if self.echo:
            args = ", ".join(repr(a) for a in call[1:])
            print(f"    -> {call[0]}({args})")

    def send_keys(self, chord: str, repeat: int = 1) -> None:
        self._record("send_keys", chord, repeat)

    def type_text(self, text: str) -> None:
        self._record("type_text", text)

    def scroll(self, amount: int, horizontal: bool = False) -> None:
        self._record("scroll", amount, horizontal)

    def click(self, button: str = "left", count: int = 1) -> None:
        self._record("click", button, count)

    def move_to(self, x: int, y: int) -> None:
        self._record("move_to", x, y)

    def move_by(self, dx: int, dy: int) -> None:
        self._record("move_by", dx, dy)

    def cursor_position(self) -> tuple[int, int]:
        return (960, 540)

    def screen_size(self) -> tuple[int, int]:
        return (1920, 1080)

    def list_windows(self) -> Sequence[WindowInfo]:
        return list(self._windows)

    def activate(self, window: WindowInfo) -> bool:
        self._record("activate", window.title)
        return True

    def window_action(self, action: str, window: Optional[WindowInfo] = None) -> bool:
        self._record("window_action", action, window.title if window else None)
        return True

    def foreground_window(self) -> Optional[WindowInfo]:
        return self._windows[0] if self._windows else None

    def launch(self, command: str) -> None:
        self._record("launch", command)

    def beep(self, frequency: int = 880, duration_ms: int = 90) -> None:
        self._record("beep", frequency, duration_ms)
