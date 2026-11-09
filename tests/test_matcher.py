import pytest

from jarvis.config import Command
from jarvis.matcher import Matcher, compile_pattern, normalize


def make(command_id, *phrases, action="noop"):
    return Command(id=command_id, patterns=[compile_pattern(p) for p in phrases],
                   action=action)


@pytest.fixture
def matcher():
    return Matcher(
        commands=[
            make("scroll", "scroll down"),
            make("scroll-n", "scroll down {amount:number}"),
            make("top", "scroll to top"),
            make("focus", "switch to {app:apps}"),
            make("type", "type {text:rest}"),
            make("click", "click"),
        ],
        lists={"apps": {"firefox": {"label": "Firefox"},
                        "vs code": {"label": "VS Code"}}},
        fillers=["please", "um"],
        fuzzy_threshold=0.75,
    )


def test_normalize_strips_punctuation():
    assert normalize("Scroll, down!") == ["scroll", "down"]


def test_exact_match(matcher):
    result = matcher.match("scroll down")
    assert result.command.id == "scroll"


def test_number_slot(matcher):
    result = matcher.match("scroll down twenty three")
    assert result.command.id == "scroll-n"
    assert result.slots["amount"] == 23


def test_more_literals_beats_fewer(matcher):
    # "scroll to top" must not lose to a pattern that only matches "scroll".
    assert matcher.match("scroll to top").command.id == "top"


def test_list_slot_matches_longest_alias(matcher):
    result = matcher.match("switch to vs code")
    assert result.slots["app"]["label"] == "VS Code"


def test_rest_slot_takes_everything(matcher):
    result = matcher.match("type hello there world")
    assert result.slots["text"] == "hello there world"


def test_unmatched_trailing_tokens_are_rejected(matcher):
    assert matcher.match("click the thing over there") is None


def test_fillers_are_ignored(matcher):
    assert matcher.match("um please scroll down").command.id == "scroll"


def test_fuzzy_recovers_a_misheard_word(matcher):
    result = matcher.match("scroll dowm")
    assert result is not None and result.command.id == "scroll"
    assert result.fuzzy is True


def test_fuzzy_will_not_cross_a_different_first_letter(matcher):
    # "town" must never be accepted for "down": that is a wrong command,
    # not a recovered one.
    assert matcher.match("scroll town") is None


def test_exact_is_preferred_over_fuzzy(matcher):
    # "click" is exact; nothing fuzzy should outrank it.
    result = matcher.match("click")
    assert result.command.id == "click" and result.fuzzy is False


def test_nonsense_does_not_match(matcher):
    assert matcher.match("what shall we have for lunch") is None


def test_chain_splits_on_then(matcher):
    results = matcher.match_chain("scroll down then click")
    assert [r.command.id for r in results] == ["scroll", "click"]


def test_chain_falls_back_to_whole_phrase_when_a_segment_fails(matcher):
    # "type a then b" is one command, not a chain: the rest slot swallows "then".
    results = matcher.match_chain("type a then b")
    assert [r.command.id for r in results] == ["type"]
    assert results[0].slots["text"] == "a then b"


def test_optional_slot_binds_none():
    matcher = Matcher([make("s", "scroll {n:number?}")])
    assert matcher.match("scroll").slots["n"] is None
    assert matcher.match("scroll four").slots["n"] == 4


def test_rest_slot_must_be_last():
    with pytest.raises(ValueError):
        compile_pattern("say {text:rest} loudly")
