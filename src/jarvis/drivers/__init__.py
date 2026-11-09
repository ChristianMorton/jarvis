"""Platform drivers."""

from __future__ import annotations

import sys

from .base import Driver, WindowInfo
from .null import NullDriver

__all__ = ["Driver", "WindowInfo", "NullDriver", "get_driver"]


def get_driver(dry_run: bool = False, echo: bool = True) -> Driver:
    """Best driver for this machine, or the recording NullDriver."""
    if dry_run or not sys.platform.startswith("win"):
        return NullDriver(echo=echo)
    from .windows import WindowsDriver

    return WindowsDriver()
