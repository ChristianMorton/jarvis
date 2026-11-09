"""Action registry: the verbs a command's ``action:`` field can name."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from ..drivers.base import Driver


@dataclass
class ActionContext:
    driver: Driver
    config: Any
    engine: Any = None          # set by Engine; lets actions touch wake state
    slots: dict[str, Any] = None  # type: ignore[assignment]


ActionFn = Callable[[ActionContext, dict], Optional[str]]
_REGISTRY: dict[str, ActionFn] = {}


def action(name: str) -> Callable[[ActionFn], ActionFn]:
    def decorator(fn: ActionFn) -> ActionFn:
        if name in _REGISTRY:
            raise ValueError(f"duplicate action {name!r}")
        _REGISTRY[name] = fn
        return fn

    return decorator


def get_action(name: str) -> ActionFn:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown action {name!r}; known: {', '.join(sorted(_REGISTRY))}"
        ) from None


def known_actions() -> list[str]:
    return sorted(_REGISTRY)


def arg(args: dict, key: str, default: Any = None, cast: Optional[type] = None) -> Any:
    value = args.get(key, default)
    if value is None:
        return default
    if cast is not None:
        try:
            return cast(value)
        except (TypeError, ValueError):
            return default
    return value
