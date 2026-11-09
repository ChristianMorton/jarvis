"""Keyboard, mouse and process actions."""

from __future__ import annotations

import time

from ..keymap import spoken_to_chord
from .registry import ActionContext, action, arg


@action("keys")
def keys(ctx: ActionContext, args: dict) -> str:
    """Send a chord or space-separated sequence: ``ctrl+s``, ``ctrl+a delete``."""
    chord = args.get("chord") or args.get("keys")
    if not chord:
        raise ValueError("keys: needs a 'chord'")
    repeat = arg(args, "repeat", 1, int) or 1
    ctx.driver.send_keys(str(chord), repeat=repeat)
    return f"keys {chord}" + (f" x{repeat}" if repeat > 1 else "")


@action("type")
def type_text(ctx: ActionContext, args: dict) -> str:
    text = args.get("text")
    if text is None:
        raise ValueError("type: needs 'text'")
    ctx.driver.type_text(str(text))
    return f"type {text!r}"


@action("scroll")
def scroll(ctx: ActionContext, args: dict) -> str:
    direction = str(arg(args, "direction", "down")).lower()
    amount = arg(args, "amount", 3, int) or 3
    signs = {"up": (1, False), "down": (-1, False), "right": (1, True), "left": (-1, True)}
    if direction not in signs:
        raise ValueError(f"scroll: bad direction {direction!r}")
    sign, horizontal = signs[direction]
    ctx.driver.scroll(sign * abs(amount), horizontal=horizontal)
    return f"scroll {direction} {abs(amount)}"


@action("click")
def click(ctx: ActionContext, args: dict) -> str:
    button = str(arg(args, "button", "left"))
    count = arg(args, "count", 1, int) or 1
    ctx.driver.click(button, count)
    return f"{button} click x{count}"


@action("mouse_move")
def mouse_move(ctx: ActionContext, args: dict) -> str:
    if "x" in args and "y" in args:
        x, y = arg(args, "x", 0, int), arg(args, "y", 0, int)
        ctx.driver.move_to(x, y)
        return f"move to {x},{y}"
    direction = str(arg(args, "direction", "")).lower()
    distance = arg(args, "distance", 100, int) or 100
    deltas = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
    if direction not in deltas:
        raise ValueError(f"mouse_move: needs x/y or a direction, got {direction!r}")
    dx, dy = deltas[direction]
    ctx.driver.move_by(dx * distance, dy * distance)
    return f"move {direction} {distance}px"


@action("mouse_center")
def mouse_center(ctx: ActionContext, args: dict) -> str:
    width, height = ctx.driver.screen_size()
    fraction_x = float(arg(args, "x_fraction", 0.5, float))
    fraction_y = float(arg(args, "y_fraction", 0.5, float))
    ctx.driver.move_to(int(width * fraction_x), int(height * fraction_y))
    return "centre mouse"


@action("launch")
def launch(ctx: ActionContext, args: dict) -> str:
    command = args.get("command")
    if not command:
        raise ValueError("launch: needs 'command'")
    ctx.driver.launch(str(command))
    return f"launch {command}"


@action("wait")
def wait(ctx: ActionContext, args: dict) -> str:
    seconds = float(arg(args, "seconds", 0.5, float))
    time.sleep(min(seconds, 10.0))  # capped: a voice loop must stay responsive
    return f"wait {seconds}s"


@action("sequence")
def sequence(ctx: ActionContext, args: dict) -> str:
    """Run several actions in order: ``steps: [{action: keys, args: {...}}, ...]``."""
    from .registry import get_action

    steps = args.get("steps") or []
    notes = []
    for index, step in enumerate(steps):
        name = step.get("action")
        if not name:
            raise ValueError(f"sequence: step #{index} has no action")
        notes.append(get_action(name)(ctx, step.get("args") or {}))
    return " ; ".join(n for n in notes if n)


@action("noop")
def noop(ctx: ActionContext, args: dict) -> str:
    return str(args.get("note", "noop"))


@action("press")
def press(ctx: ActionContext, args: dict) -> str:
    """Press a chord described in words: ``press control shift p``."""
    spoken = args.get("spoken") or args.get("text")
    if not spoken:
        raise ValueError("press: needs 'spoken'")
    chord = spoken_to_chord(str(spoken))
    repeat = arg(args, "repeat", 1, int) or 1
    ctx.driver.send_keys(chord, repeat=repeat)
    return f"press {chord}" + (f" x{repeat}" if repeat > 1 else "")
