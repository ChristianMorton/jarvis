"""The surface every platform driver implements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass
class WindowInfo:
    handle: int
    title: str
    process: str = ""

    def __str__(self) -> str:
        return f"{self.title} [{self.process}]"


class Driver:
    """Input synthesis and window control for one platform."""

    name = "base"
    available = False

    # --- keyboard -------------------------------------------------------
    def send_keys(self, chord: str, repeat: int = 1) -> None:
        """Press a chord such as ``ctrl+shift+p``. May be a space-separated
        sequence: ``"ctrl+a delete"``."""
        raise NotImplementedError

    def type_text(self, text: str) -> None:
        raise NotImplementedError

    # --- mouse ----------------------------------------------------------
    def scroll(self, amount: int, horizontal: bool = False) -> None:
        """Positive is up / right, in wheel notches."""
        raise NotImplementedError

    def click(self, button: str = "left", count: int = 1) -> None:
        raise NotImplementedError

    def move_to(self, x: int, y: int) -> None:
        raise NotImplementedError

    def move_by(self, dx: int, dy: int) -> None:
        raise NotImplementedError

    def cursor_position(self) -> tuple[int, int]:
        raise NotImplementedError

    def screen_size(self) -> tuple[int, int]:
        raise NotImplementedError

    # --- windows --------------------------------------------------------
    def list_windows(self) -> Sequence[WindowInfo]:
        raise NotImplementedError

    def activate(self, window: WindowInfo) -> bool:
        raise NotImplementedError

    def window_action(self, action: str, window: Optional[WindowInfo] = None) -> bool:
        """``minimize`` | ``maximize`` | ``restore`` | ``close``."""
        raise NotImplementedError

    def foreground_window(self) -> Optional[WindowInfo]:
        raise NotImplementedError

    def launch(self, command: str) -> None:
        raise NotImplementedError

    def beep(self, frequency: int = 880, duration_ms: int = 90) -> None:
        raise NotImplementedError
