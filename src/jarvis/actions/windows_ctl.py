"""Window and application actions."""

from __future__ import annotations

import difflib
import re
import time

from ..drivers.base import WindowInfo
from .registry import ActionContext, action, arg


def _score(window: WindowInfo, spec: dict) -> float:
    """How well a live window matches an app spec from ``lists.apps``.

    Process name is trusted over title, because titles carry the document
    name ("config.py - Visual Studio Code") and drift constantly.
    """
    process = (window.process or "").lower()
    title = (window.title or "").lower()

    for name in _as_list(spec.get("process")):
        name = name.lower()
        if process == name or process == f"{name}.exe":
            return 1.0
    for pattern in _as_list(spec.get("title_regex")):
        if re.search(pattern, window.title, re.IGNORECASE):
            return 0.9
    best = 0.0
    for needle in _as_list(spec.get("title")) or _as_list(spec.get("match")):
        needle = needle.lower()
        if needle and needle in title:
            # Prefer the shortest title containing the needle: that is usually
            # the main window rather than a dialog or a browser tab naming it.
            best = max(best, 0.8 - min(len(title), 400) / 4000)
        elif needle:
            best = max(best, difflib.SequenceMatcher(None, needle, title).ratio() * 0.5)
    return best


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def find_windows(ctx: ActionContext, spec: dict) -> list[WindowInfo]:
    """Every window matching ``spec``, best first.

    Ties break on the window handle rather than enumeration order: EnumWindows
    returns windows in z-order, which changes the moment you focus one, and a
    ring that reorders itself as you walk it is not a ring you can walk.
    """
    scored = [(w, _score(w, spec)) for w in ctx.driver.list_windows()]
    scored = [(w, s) for w, s in scored if s >= 0.55]
    scored.sort(key=lambda pair: (-pair[1], pair[0].handle))
    return [window for window, _ in scored]


def find_window(ctx: ActionContext, spec: dict):
    windows = find_windows(ctx, spec)
    return windows[0] if windows else None


def next_window(ctx: ActionContext, spec: dict):
    """The window to focus, cycling if one of this app's windows already has focus.

    You usually have one browser but three terminals, so "switch to terminal"
    said twice has to reach the second one. Which window is next is derived
    from what is in front right now, so no state has to be kept in sync with
    a window list that changes underneath us.
    """
    windows = find_windows(ctx, spec)
    if not windows:
        return None
    foreground = ctx.driver.foreground_window()
    if foreground is not None:
        for index, window in enumerate(windows):
            if window.handle == foreground.handle:
                return windows[(index + 1) % len(windows)]
    return windows[0]


@action("focus_app")
def focus_app(ctx: ActionContext, args: dict) -> str:
    """Activate an app's window; launch it if it isn't running."""
    spec = args.get("app")
    if isinstance(spec, str):
        spec = {"title": spec, "process": spec}
    if not isinstance(spec, dict):
        raise ValueError("focus_app: needs an 'app' spec (from lists.apps)")

    label = spec.get("label") or spec.get("name") or spec.get("process") or spec.get("title")
    cycle = bool(args.get("cycle", True))
    window = (next_window if cycle else find_window)(ctx, spec)
    if window is not None:
        ctx.driver.activate(window)
        total = len(find_windows(ctx, spec))
        suffix = f" ({total} open)" if total > 1 else ""
        return f"focus {window.title}{suffix}"

    command = spec.get("launch")
    if not command:
        return f"no window for {label} (and no launch command)"
    ctx.driver.launch(str(command))

    # Give it a moment, then focus the window it opened.
    deadline = time.time() + float(arg(args, "launch_timeout", 8.0, float))
    while time.time() < deadline:
        time.sleep(0.4)
        window = find_window(ctx, spec)
        if window is not None:
            ctx.driver.activate(window)
            return f"launched and focused {label}"
    return f"launched {label}"


@action("window")
def window_action(ctx: ActionContext, args: dict) -> str:
    what = str(arg(args, "do", "maximize"))
    ctx.driver.window_action(what)
    return f"window {what}"


@action("switch_window")
def switch_window(ctx: ActionContext, args: dict) -> str:
    """Alt-tab style cycling, without relying on the alt-tab overlay."""
    steps = arg(args, "steps", 1, int) or 1
    ctx.driver.send_keys("alt+tab", repeat=steps)
    return f"switch window x{steps}"
