"""Configuration loading: built-in packs layered under the user's own file."""

from __future__ import annotations

import copy
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from .matcher import Pattern, compile_pattern

PACKS_DIR = Path(__file__).parent / "packs"
TEMPLATE_RE = re.compile(r"\{([\w.]+)(?:\|([^}]*))?\}")

DEFAULTS: dict[str, Any] = {
    "wake_word": "jarvis",
    # Vosk small-model near-misses for "jarvis"; extend in your own config.
    "wake_aliases": ["jarvis", "javis", "jervis", "jarvis's", "harvest", "service"],
    "arm_seconds": 5.0,
    "arm_after_command": True,
    "require_wake_word": True,
    "chain_separators": ["then"],
    "fillers": ["um", "uh", "er", "please", "the", "okay", "ok", "now", "hey"],
    "model": {"path": "models/vosk-model-small-en-us-0.15"},
    "audio": {"device": None, "samplerate": 16000, "blocksize": 4000},
    "recognition": {
        "fuzzy_threshold": 0.75,
        "restrict_grammar": True,
        "use_partials": False,
        "extra_words": [],
    },
    "feedback": {"beep": True, "log": True, "beep_hz": {"arm": 880, "ok": 1320, "err": 220}},
    "packs": ["core", "navigation", "apps", "dictation", "claude_code"],
    "disable": [],
    "lists": {},
    "commands": [],
    # Values usable as {name} inside any command's args. Slots shadow these.
    "vars": {
        # Set this to whatever hotkey you have bound in Wispr Flow's settings.
        "wispr_hotkey": "ctrl+shift+space",
    },
}


@dataclass
class Command:
    id: str
    patterns: list[Pattern]
    action: str
    args: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    source: str = "user"
    confirm: bool = False

    @property
    def phrases(self) -> list[str]:
        return [p.raw for p in self.patterns]


@dataclass
class Config:
    data: dict[str, Any]
    commands: list[Command]
    lists: dict[str, dict[str, Any]]
    path: Optional[Path] = None

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for key in dotted.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    @property
    def wake_aliases(self) -> list[str]:
        aliases = list(self.get("wake_aliases", []))
        wake = self.get("wake_word", "jarvis")
        if wake and wake not in aliases:
            aliases.insert(0, wake)
        return [a.lower() for a in aliases]


def deep_merge(base: dict, overlay: dict) -> dict:
    """Recursive dict merge; lists are replaced, not concatenated."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _build_commands(raw_commands: Iterable[dict], source: str) -> list[Command]:
    commands: list[Command] = []
    for index, entry in enumerate(raw_commands):
        if not isinstance(entry, dict):
            raise ValueError(f"{source}: command #{index} is not a mapping")
        phrases = entry.get("phrases") or entry.get("phrase")
        if isinstance(phrases, str):
            phrases = [phrases]
        if not phrases:
            raise ValueError(f"{source}: command {entry.get('id', index)!r} has no phrases")
        action = entry.get("action")
        if not action:
            raise ValueError(f"{source}: command {entry.get('id', index)!r} has no action")
        command_id = entry.get("id") or f"{source}:{index}"
        commands.append(
            Command(
                id=command_id,
                patterns=[compile_pattern(p) for p in phrases],
                action=action,
                args=entry.get("args") or {},
                description=entry.get("description", ""),
                source=source,
                confirm=bool(entry.get("confirm", False)),
            )
        )
    return commands


def resolve_aliases(lists: dict[str, dict[str, Any]]) -> None:
    """Expand ``alias_of:`` entries in place.

    Lets several spoken names share one definition without copying it, which
    matters most where a spec is long: "terminal", "console" and "the shell"
    should not each carry their own eight-entry process list that can drift
    apart. Keys given alongside ``alias_of`` override the target's.
    """
    for list_name, entries in lists.items():
        for alias, spec in list(entries.items()):
            if not isinstance(spec, dict) or "alias_of" not in spec:
                continue
            seen = [alias]
            target_name = spec["alias_of"]
            while True:
                if target_name in seen:
                    raise ValueError(
                        f"lists.{list_name}: alias_of cycle {' -> '.join(seen + [target_name])}"
                    )
                seen.append(target_name)
                target = entries.get(target_name)
                if target is None:
                    raise ValueError(
                        f"lists.{list_name}.{alias}: alias_of {target_name!r} does not exist"
                    )
                if not isinstance(target, dict) or "alias_of" not in target:
                    break
                target_name = target["alias_of"]
            overrides = {k: v for k, v in spec.items() if k != "alias_of"}
            entries[alias] = {**target, **overrides}


def user_config_path(explicit: Optional[str] = None) -> Optional[Path]:
    """Resolve the user config: explicit flag, env var, CWD, then APPDATA/home."""
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("JARVIS_CONFIG")
    if env:
        return Path(env).expanduser()
    candidates = [Path.cwd() / "jarvis.yaml"]
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "Jarvis" / "config.yaml")
    candidates.append(Path.home() / ".config" / "jarvis" / "config.yaml")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_config(explicit: Optional[str] = None) -> Config:
    data = copy.deepcopy(DEFAULTS)
    path = user_config_path(explicit)
    user_data: dict[str, Any] = {}
    if path is not None:
        if not path.is_file():
            raise FileNotFoundError(f"config not found: {path}")
        user_data = _load_yaml(path)

    # Settings merge first so `packs:` can be overridden before we read packs.
    settings = {k: v for k, v in user_data.items() if k not in ("commands", "lists")}
    data = deep_merge(data, settings)

    commands: list[Command] = []
    lists: dict[str, dict[str, Any]] = {}
    for pack_name in data.get("packs", []):
        pack_path = PACKS_DIR / f"{pack_name}.yaml"
        if not pack_path.is_file():
            raise FileNotFoundError(f"unknown pack {pack_name!r} ({pack_path})")
        pack = _load_yaml(pack_path)
        for list_name, aliases in (pack.get("lists") or {}).items():
            lists.setdefault(list_name, {}).update(aliases or {})
        commands.extend(_build_commands(pack.get("commands") or [], source=pack_name))

    for list_name, aliases in (user_data.get("lists") or {}).items():
        lists.setdefault(list_name, {}).update(aliases or {})

    resolve_aliases(lists)

    user_commands = _build_commands(user_data.get("commands") or [], source="user")

    # User commands override built-ins with the same id; the rest are appended.
    overridden = {c.id for c in user_commands}
    disabled = set(data.get("disable") or [])
    merged = [c for c in commands if c.id not in overridden and c.id not in disabled]
    merged.extend(c for c in user_commands if c.id not in disabled)

    # Longer, more specific phrases are tried first so "scroll to top" beats
    # "scroll to {x}" on ties the scorer cannot break.
    merged.sort(key=lambda c: -max(p.literal_count for p in c.patterns))

    data["lists"] = lists
    return Config(data=data, commands=merged, lists=lists, path=path)


def resolve(values: dict[str, Any], dotted: str) -> Any:
    """Look up ``a.b.c`` through nested dicts; None if any hop is missing."""
    node: Any = values
    for key in dotted.split("."):
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return None
    return node


def render_args(args: Any, values: dict[str, Any]) -> Any:
    """Substitute ``{name}`` / ``{name.attr}`` / ``{name|default}`` into args."""
    if isinstance(args, dict):
        return {k: render_args(v, values) for k, v in args.items()}
    if isinstance(args, list):
        return [render_args(v, values) for v in args]
    if not isinstance(args, str):
        return args

    whole = TEMPLATE_RE.fullmatch(args)
    if whole:
        # A lone placeholder keeps the value's native type (int stays int,
        # and an app spec stays a dict).
        name, default = whole.group(1), whole.group(2)
        value = resolve(values, name)
        if value is None:
            return _coerce(default) if default is not None else None
        return value

    def replace(match: re.Match) -> str:
        value = resolve(values, match.group(1))
        if value is None:
            value = match.group(2) if match.group(2) is not None else ""
        return str(value)

    return TEMPLATE_RE.sub(replace, args)


def _coerce(text: str) -> Any:
    if text is None:
        return None
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            continue
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    return text
