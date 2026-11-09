"""Actions that drive Jarvis itself rather than the desktop."""

from __future__ import annotations

from .registry import ActionContext, action, arg


@action("arm")
def arm(ctx: ActionContext, args: dict) -> str:
    seconds = arg(args, "seconds", None, float)
    ctx.engine.arm(seconds)
    return "listening"


@action("disarm")
def disarm(ctx: ActionContext, args: dict) -> str:
    ctx.engine.disarm()
    return "standing down"


@action("sleep")
def sleep(ctx: ActionContext, args: dict) -> str:
    """Stop acting on anything but the wake word until told to wake."""
    ctx.engine.set_paused(True)
    return "asleep"


@action("wake")
def wake(ctx: ActionContext, args: dict) -> str:
    ctx.engine.set_paused(False)
    return "awake"


@action("repeat")
def repeat(ctx: ActionContext, args: dict) -> str:
    times = arg(args, "times", 1, int) or 1
    return ctx.engine.repeat_last(times)


@action("quit")
def quit_action(ctx: ActionContext, args: dict) -> str:
    ctx.engine.stop()
    return "shutting down"
