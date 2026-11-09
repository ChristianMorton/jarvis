"""Importing this package registers every built-in action."""

from . import basic, control, grid, windows_ctl  # noqa: F401
from .registry import ActionContext, action, get_action, known_actions

__all__ = ["ActionContext", "action", "get_action", "known_actions"]
