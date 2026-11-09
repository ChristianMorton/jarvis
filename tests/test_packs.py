"""The shipped packs must be internally consistent — a typo in a YAML chord
is a command that silently does nothing until you say it out loud."""

import pytest

from jarvis.actions import known_actions
from jarvis.config import load_config
from jarvis.drivers.windows import parse_chord
from jarvis.grammar import collect_words
from jarvis.matcher import Slot


@pytest.fixture(scope="module")
def config(tmp_path_factory):
    import os

    os.environ["JARVIS_CONFIG"] = ""
    cwd = os.getcwd()
    os.chdir(tmp_path_factory.mktemp("empty"))
    try:
        yield load_config()
    finally:
        os.chdir(cwd)


def _chords(node):
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "chord" and isinstance(value, str):
                found.append(value)
            else:
                found += _chords(value)
    elif isinstance(node, list):
        for value in node:
            found += _chords(value)
    return found


def test_every_action_exists(config):
    unknown = {c.id: c.action for c in config.commands if c.action not in known_actions()}
    assert not unknown


def test_every_chord_parses(config):
    bad = []
    for command in config.commands:
        for chord in _chords(command.args):
            if "{" in chord:
                continue  # templated; resolved at dispatch time
            for step in chord.split():
                try:
                    parse_chord(step)
                except ValueError as exc:
                    bad.append((command.id, step, str(exc)))
    assert not bad


def test_command_ids_are_unique(config):
    ids = [c.id for c in config.commands]
    assert len(ids) == len(set(ids))


def test_every_slot_list_is_defined(config):
    missing = []
    for command in config.commands:
        for pattern in command.patterns:
            for part in pattern.parts:
                if isinstance(part, Slot) and part.type not in ("number", "word", "rest"):
                    if part.type not in config.lists:
                        missing.append((command.id, part.type))
    assert not missing


def test_no_two_commands_claim_the_same_literal_phrase(config):
    """Two identical literal phrases means one of them can never win."""
    seen = {}
    clashes = []
    for command in config.commands:
        for pattern in command.patterns:
            if pattern.slot_count:
                continue
            key = " ".join(pattern.parts)
            if key in seen and seen[key] != command.id:
                clashes.append((key, seen[key], command.id))
            seen[key] = command.id
    assert not clashes, f"duplicate phrases: {clashes}"


def test_grammar_covers_every_literal_in_every_pack(config):
    """Anything the grammar cannot emit is a command you can never say."""
    vocabulary = set(collect_words(config))
    missing = set()
    for command in config.commands:
        for pattern in command.patterns:
            for part in pattern.parts:
                if isinstance(part, str) and part not in vocabulary:
                    missing.add((command.id, part))
    assert not missing


def test_app_specs_have_something_to_match_on(config):
    thin = [alias for alias, spec in config.lists["apps"].items()
            if not (spec.get("process") or spec.get("title") or spec.get("title_regex"))]
    assert not thin


def test_every_shipped_phrase_reaches_its_own_command(config):
    """The end-to-end property: say a phrase, get that command.

    This is what catches a phrase shadowed by another command, and a literal
    that the filler list quietly eats before matching ever sees it.
    """
    from jarvis.matcher import Matcher

    matcher = Matcher(config.commands, config.lists,
                      fuzzy_threshold=float(config.get("recognition.fuzzy_threshold")),
                      fillers=config.get("fillers"))
    stand_ins = {"number": "seven", "word": "tab", "rest": "some words"}
    wrong = []
    for command in config.commands:
        for pattern in command.patterns:
            spoken = []
            for part in pattern.parts:
                if isinstance(part, str):
                    spoken.append(part)
                elif part.type in stand_ins:
                    spoken.append(stand_ins[part.type])
                else:
                    spoken.append(next(iter(config.lists[part.type])))
            phrase = " ".join(spoken)
            result = matcher.match(phrase)
            if result is None:
                wrong.append((command.id, phrase, "no match"))
            elif result.command.id != command.id:
                wrong.append((command.id, phrase, f"went to {result.command.id}"))
    assert not wrong


def test_a_filler_that_is_also_a_command_literal_is_not_stripped(config):
    from jarvis.matcher import Matcher

    matcher = Matcher(config.commands, config.lists, fillers=["the", "um"])
    assert "the" not in matcher.fillers, '"the" is a literal in several phrases'
    assert "um" in matcher.fillers
