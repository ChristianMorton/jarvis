import pytest

from jarvis.numbers import parse_number, take_number


@pytest.mark.parametrize(
    "spoken,expected",
    [
        ("seven", 7),
        ("twenty three", 23),
        ("a hundred and five", 105),
        ("a hundred twenty three", 123),
        ("two thousand five hundred", 2500),
        ("hundred", 100),
        ("42", 42),
        ("third", 3),
        ("a", 1),
    ],
)
def test_parses(spoken, expected):
    assert parse_number(spoken.split()) == expected


@pytest.mark.parametrize("spoken", ["three five", "three twenty", "banana", "", "and"])
def test_rejects(spoken):
    assert parse_number(spoken.split()) is None


def test_take_number_is_greedy_but_stops_at_non_numbers():
    assert take_number("twenty three times".split()) == (23, 2)
    assert take_number("scroll down".split()) == (None, 0)


def test_take_number_prefers_the_longest_valid_prefix():
    # "twenty" alone parses, but "twenty three" is the better read.
    assert take_number("twenty three".split())[0] == 23
