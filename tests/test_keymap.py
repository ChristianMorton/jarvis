import pytest

from jarvis.keymap import KeyParseError, spoken_to_chord


@pytest.mark.parametrize(
    "spoken,chord",
    [
        ("control c", "ctrl+c"),
        ("control shift p", "ctrl+shift+p"),
        ("alt f four", "alt+f4"),
        ("control alpha", "ctrl+a"),
        ("windows d", "win+d"),
        ("page down", "pagedown"),
        ("escape", "escape"),
        ("f twelve", "f12"),
        ("control", "ctrl"),
        ("alt tab", "alt+tab"),
        ("control a delete", "ctrl+a delete"),
        ("command shift bravo", "ctrl+shift+b"),
        ("control seven", "ctrl+7"),
    ],
)
def test_parses(spoken, chord):
    assert spoken_to_chord(spoken) == chord


@pytest.mark.parametrize("spoken", ["", "control aardvark", "the and"])
def test_rejects_nonsense(spoken):
    with pytest.raises((KeyParseError, ValueError)):
        spoken_to_chord(spoken)


def test_nato_disambiguates_letters_the_recogniser_confuses():
    # b/d/e/p/t/v are the classic collisions; their NATO words are not close.
    for word, letter in [("bravo", "b"), ("delta", "d"), ("echo", "e"),
                         ("papa", "p"), ("tango", "t"), ("victor", "v")]:
        assert spoken_to_chord(f"control {word}") == f"ctrl+{letter}"


def test_every_produced_chord_is_sendable():
    from jarvis.drivers.windows import parse_chord

    for spoken in ["control shift p", "alt f four", "page up", "windows left",
                   "control alpha delete", "shift tab"]:
        for step in spoken_to_chord(spoken).split():
            parse_chord(step)
