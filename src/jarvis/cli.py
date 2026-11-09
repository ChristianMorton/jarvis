"""Command line: ``jarvis run`` and the tools you need to tune it."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

from . import __version__
from .config import Config, load_config, user_config_path
from .drivers import get_driver
from .engine import Engine
from .feedback import Feedback
from .grammar import build_grammar, collect_words, describe

MODELS = {
    "small-en-us": (
        "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        "vosk-model-small-en-us-0.15",
    ),
    "small-en-gb": (
        "https://alphacephei.com/vosk/models/vosk-model-small-en-gb-0.15.zip",
        "vosk-model-small-en-gb-0.15",
    ),
    "lgraph-en-us": (
        "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22-lgraph.zip",
        "vosk-model-en-us-0.22-lgraph",
    ),
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


# --- subcommands --------------------------------------------------------
def cmd_run(args, config: Config) -> int:
    from .listener import Listener, MissingModel

    driver = get_driver(dry_run=args.dry_run, echo=args.dry_run)
    feedback = Feedback(driver, config)
    engine = Engine(config, driver, on_feedback=feedback)

    restrict = bool(config.get("recognition.restrict_grammar", True))
    grammar = build_grammar(config) if restrict else None

    try:
        listener = Listener(
            model_path=config.get("model.path"),
            samplerate=int(config.get("audio.samplerate", 16000)),
            device=config.get("audio.device"),
            blocksize=int(config.get("audio.blocksize", 4000)),
            grammar=grammar,
            emit_partials=bool(config.get("recognition.use_partials", False)),
        )
    except MissingModel as exc:
        print(exc, file=sys.stderr)
        return 2

    wake = config.get("wake_word", "jarvis")
    print(f"Jarvis {__version__} — say \"{wake}\" (Ctrl+C to stop)")
    print(f"  model    {listener.model_path.name}")
    print(f"  driver   {driver.name}{'  [DRY RUN — nothing is sent]' if args.dry_run else ''}")
    print(f"  commands {len(config.commands)}"
          f"{'  grammar ' + str(len(collect_words(config))) + ' words' if restrict else '  (open recognition)'}")
    if config.path:
        print(f"  config   {config.path}")
    print()

    try:
        for utterance in listener.listen():
            if utterance.partial:
                continue
            engine.handle(utterance.text)
            if not engine.running:
                break
    except KeyboardInterrupt:
        print("\nstopped.")
    except ImportError as exc:
        print(f"missing dependency: {exc}\n  pip install -r requirements.txt", file=sys.stderr)
        return 2
    finally:
        listener.stop()
        if engine.grid is not None:
            engine.grid.close()
    return 0


def cmd_test(args, config: Config) -> int:
    """Feed phrases through the engine without a microphone."""
    driver = get_driver(dry_run=True, echo=True)
    feedback = Feedback(driver, config)
    engine = Engine(config, driver, on_feedback=feedback)
    if not args.require_wake:
        engine.require_wake_word = False

    phrases = args.phrase or []
    if not phrases:
        print("Type phrases to test them; blank line or Ctrl+D to finish.")
        try:
            while True:
                line = input("> ").strip()
                if not line:
                    break
                engine.handle(line)
        except (EOFError, KeyboardInterrupt):
            print()
        return 0

    failures = 0
    for phrase in phrases:
        outcome = engine.handle(phrase)
        if not outcome.handled:
            failures += 1
    return 1 if failures else 0


def cmd_commands(args, config: Config) -> int:
    needle = (args.search or "").lower()
    shown = 0
    for command in sorted(config.commands, key=lambda c: (c.source, c.id)):
        blob = f"{command.id} {command.description} {' '.join(command.phrases)}".lower()
        if needle and needle not in blob:
            continue
        shown += 1
        print(f"\n\033[1m{command.id}\033[0m  ({command.source} → {command.action})")
        if command.description:
            print(f"  {command.description}")
        for phrase in command.phrases:
            print(f"    · {phrase}")
    # App names live in `lists`, not in any phrase, so a search for "terminal"
    # would otherwise miss the very thing the user is looking for.
    if needle:
        for list_name, entries in sorted(config.lists.items()):
            hits = sorted(a for a in entries if needle in a.lower()
                          or needle in str(entries[a].get("label", "")).lower())
            if not hits:
                continue
            print(f"\n\033[1mlists.{list_name}\033[0m — say these after "
                  f"\"switch to\" / \"open\" / \"go to\"")
            for alias in hits:
                label = entries[alias].get("label", "")
                print(f"    · {alias}" + (f"  → {label}" if label else ""))

    print(f"\n{shown} command(s)"
          + (f" matching {args.search!r}" if needle else "")
          + f" from packs: {', '.join(config.get('packs', []))}")
    return 0


def cmd_words(args, config: Config) -> int:
    words = collect_words(config)
    if args.plain:
        print("\n".join(words))
    else:
        print(describe(words, limit=len(words) if args.all else 24))
    return 0


def cmd_devices(args, config: Config) -> int:
    try:
        from .listener import list_devices
    except ImportError as exc:  # pragma: no cover
        print(f"cannot query devices: {exc}", file=sys.stderr)
        return 2
    try:
        devices = list_devices()
    except Exception as exc:
        print(f"cannot query devices: {exc}", file=sys.stderr)
        return 2
    print(f"{'idx':>4}  {'in':>3}  {'rate':>6}  name")
    for device in devices:
        print(f"{device['index']:>4}  {device['inputs']:>3}  "
              f"{device['default_rate']:>6}  {device['name']}")
    print("\nSet audio.device in jarvis.yaml to an index or a name substring.")
    return 0


def cmd_doctor(args, config: Config) -> int:
    """Check everything Jarvis needs, and say what to do about what's missing."""
    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and passed
        mark = "\033[32m✓\033[0m" if passed else "\033[31m✗\033[0m"
        print(f"  {mark} {label}" + (f"  — {detail}" if detail else ""))

    def note(label: str, detail: str = "") -> None:
        """Worth knowing, but not a failure — the defaults are a valid setup."""
        print(f"  \033[90m·\033[0m {label}" + (f"  — {detail}" if detail else ""))

    print("platform")
    check("Windows", sys.platform.startswith("win"),
          "" if sys.platform.startswith("win")
          else f"on {sys.platform}; input will be simulated, not sent")
    check("Python >= 3.10", sys.version_info >= (3, 10), sys.version.split()[0])

    print("\ndependencies")
    for module, hint in (("vosk", "pip install vosk"),
                         ("sounddevice", "pip install sounddevice"),
                         ("yaml", "pip install PyYAML")):
        try:
            __import__(module)
            check(module, True)
        except ImportError:
            check(module, False, hint)

    print("\nmodel")
    try:
        from .listener import resolve_model_path
        path = resolve_model_path(config.get("model.path"))
        check(f"model at {path}", True)
    except Exception as exc:
        check("acoustic model", False, str(exc).splitlines()[0])

    print("\nmicrophone")
    try:
        from .listener import list_devices
        devices = list_devices()
        check(f"{len(devices)} input device(s)", bool(devices),
              devices[0]["name"] if devices else "none found")
    except Exception as exc:
        check("input devices", False, str(exc))

    print("\nconfig")
    check(f"{len(config.commands)} commands from {len(config.get('packs', []))} pack(s)",
          bool(config.commands))
    if config.path is not None:
        check("user config", True, str(config.path))
    else:
        note("user config", "none yet — running on the built-in defaults; "
                            "`jarvis init` writes one")
    unknown = _unknown_actions(config)
    check("all actions known", not unknown, ", ".join(unknown) if unknown else "")

    print("\n" + ("\033[32mready.\033[0m" if ok else "\033[31mnot ready — see above.\033[0m"))
    return 0 if ok else 1


def _unknown_actions(config: Config) -> list[str]:
    from .actions import known_actions

    known = set(known_actions())
    return sorted({c.action for c in config.commands if c.action not in known})


def cmd_init(args, config: Config) -> int:
    target = Path(args.path).expanduser() if args.path else Path.cwd() / "jarvis.yaml"
    if target.exists() and not args.force:
        print(f"{target} already exists (use --force to overwrite)", file=sys.stderr)
        return 1
    example = PROJECT_ROOT / "jarvis.example.yaml"
    if not example.is_file():
        print(f"template missing: {example}", file=sys.stderr)
        return 2
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example, target)
    print(f"wrote {target}\nEdit it, then run:  jarvis run")
    return 0


def cmd_download_model(args, config: Config) -> int:
    name = args.name
    if name not in MODELS:
        print(f"unknown model {name!r}; choose from {', '.join(MODELS)}", file=sys.stderr)
        return 1
    url, folder = MODELS[name]
    destination = Path(args.dest).expanduser() if args.dest else PROJECT_ROOT / "models"
    destination.mkdir(parents=True, exist_ok=True)
    final = destination / folder
    if final.is_dir() and not args.force:
        print(f"already present: {final}")
        return 0

    archive = destination / f"{folder}.zip"
    print(f"downloading {url}")
    try:
        with urllib.request.urlopen(url) as response, archive.open("wb") as handle:
            total = int(response.headers.get("Content-Length") or 0)
            read = 0
            while True:
                chunk = response.read(1 << 16)
                if not chunk:
                    break
                handle.write(chunk)
                read += len(chunk)
                if total:
                    print(f"\r  {read / 1e6:.1f} / {total / 1e6:.1f} MB", end="", flush=True)
        print()
    except Exception as exc:
        print(f"download failed: {exc}", file=sys.stderr)
        return 2

    print(f"extracting into {destination}")
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)
    archive.unlink(missing_ok=True)
    print(f"model ready: {final}\nSet model.path to  models/{folder}")
    return 0


# --- entry point --------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="Hands-free voice control for Windows.",
    )
    parser.add_argument("--config", help="path to a jarvis.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=f"jarvis {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="listen and act (the main mode)")
    run.add_argument("--dry-run", action="store_true",
                     help="recognise and match, but print actions instead of sending them")
    run.set_defaults(func=cmd_run)

    test = subparsers.add_parser("test", help="run phrases through the matcher, no mic")
    test.add_argument("phrase", nargs="*")
    test.add_argument("--require-wake", action="store_true",
                      help="require the wake word (off by default so you can type bare commands)")
    test.set_defaults(func=cmd_test)

    commands = subparsers.add_parser("commands", help="list every command and phrase")
    commands.add_argument("search", nargs="?", help="filter by substring")
    commands.set_defaults(func=cmd_commands)

    words = subparsers.add_parser("words", help="show the restricted recognition vocabulary")
    words.add_argument("--all", action="store_true")
    words.add_argument("--plain", action="store_true", help="one per line")
    words.set_defaults(func=cmd_words)

    devices = subparsers.add_parser("devices", help="list microphones")
    devices.set_defaults(func=cmd_devices)

    doctor = subparsers.add_parser("doctor", help="check the install")
    doctor.set_defaults(func=cmd_doctor)

    init = subparsers.add_parser("init", help="write a starter jarvis.yaml")
    init.add_argument("path", nargs="?")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    download = subparsers.add_parser("download-model", help="fetch a Vosk model")
    download.add_argument("name", nargs="?", default="small-en-us",
                          choices=sorted(MODELS))
    download.add_argument("--dest")
    download.add_argument("--force", action="store_true")
    download.set_defaults(func=cmd_download_model)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    if not getattr(args, "func", None):
        parser.print_help()
        return 0

    # download-model and init must work before any config exists.
    if args.func in (cmd_download_model, cmd_init):
        try:
            config = load_config(args.config)
        except Exception:
            config = Config(data={}, commands=[], lists={})
        return args.func(args, config)

    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    return args.func(args, config)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
