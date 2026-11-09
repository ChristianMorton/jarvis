import pytest

from jarvis.config import load_config
from jarvis.drivers.null import NullDriver
from jarvis.engine import Engine


class Clock:
    """A hand-cranked clock so arming windows are testable without sleeping."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_CONFIG", "")
    monkeypatch.chdir(tmp_path)  # no stray jarvis.yaml from the repo root
    config = load_config()
    driver = NullDriver(echo=False)
    clock = Clock()
    return Engine(config, driver, clock=clock), driver, clock


def test_wake_word_prefixed_command_runs(setup):
    engine, driver, _ = setup
    outcome = engine.handle("jarvis scroll down")
    assert outcome.handled
    assert ("scroll", -3, False) in driver.calls


def test_command_without_wake_word_is_ignored(setup):
    engine, driver, _ = setup
    outcome = engine.handle("scroll down")
    assert not outcome.handled
    assert outcome.ignored_reason == "no wake word"
    assert driver.calls == []


def test_bare_wake_word_arms_without_acting(setup):
    engine, driver, _ = setup
    outcome = engine.handle("jarvis")
    assert outcome.armed and engine.is_armed
    assert driver.calls == []


def test_armed_window_accepts_a_bare_command(setup):
    engine, driver, _ = setup
    engine.handle("jarvis")
    assert engine.handle("scroll down").handled


def test_armed_window_expires(setup):
    engine, driver, clock = setup
    engine.handle("jarvis")
    clock.advance(engine.arm_seconds + 0.1)
    assert not engine.is_armed
    assert not engine.handle("scroll down").handled


def test_a_command_extends_the_window(setup):
    engine, driver, clock = setup
    engine.handle("jarvis scroll down")
    clock.advance(engine.arm_seconds - 0.5)
    assert engine.handle("scroll down").handled  # window was extended
    clock.advance(engine.arm_seconds - 0.5)
    assert engine.handle("scroll down").handled


def test_stand_down_is_not_undone_by_the_auto_rearm(setup):
    engine, driver, _ = setup
    engine.handle("jarvis scroll down")
    engine.handle("stand down")
    assert not engine.is_armed
    assert not engine.handle("scroll down").handled


def test_repeated_wake_words_are_all_stripped(setup):
    # The decoder sometimes doubles the wake word across a segment boundary.
    engine, _, _ = setup
    assert engine.handle("jarvis jarvis scroll down").handled


def test_unmatched_speech_keeps_the_window_open(setup):
    engine, _, _ = setup
    engine.handle("jarvis")
    engine.handle("something the grammar cannot possibly contain")
    assert engine.is_armed, "a misfire must not cost you the wake word"


def test_sleep_ignores_bare_commands_but_the_wake_word_still_works(setup):
    engine, _, _ = setup
    engine.handle("jarvis go to sleep")
    assert not engine.handle("scroll down").handled
    assert engine.handle("jarvis scroll down").handled


def test_chained_commands_both_run(setup):
    engine, driver, _ = setup
    engine.handle("jarvis scroll down then next tab")
    assert ("scroll", -3, False) in driver.calls
    assert ("send_keys", "ctrl+tab", 1) in driver.calls


def test_repeat_replays_the_last_command(setup):
    engine, driver, _ = setup
    engine.handle("jarvis scroll down")
    driver.calls.clear()
    engine.handle("again three times")
    assert driver.calls.count(("scroll", -3, False)) == 3


def test_repeat_does_not_recurse_into_itself(setup):
    engine, driver, _ = setup
    engine.handle("jarvis scroll down")
    engine.handle("again")
    driver.calls.clear()
    engine.handle("again")  # must replay the scroll, not the repeat
    assert driver.calls == [("scroll", -3, False)]


def test_a_failing_action_is_reported_not_raised(setup):
    engine, _, _ = setup
    bad = next(c for c in engine.config.commands if c.id == "core.press")
    bad.args = {"spoken": "not a key at all"}
    outcome = engine.handle("jarvis press whatever")
    assert outcome.error and not outcome.handled
    assert engine.running, "a bad command must not stop the loop"


def test_number_slot_reaches_the_driver(setup):
    engine, driver, _ = setup
    engine.handle("jarvis scroll down seven")
    assert ("scroll", -7, False) in driver.calls


def test_app_focus_activates_a_matching_window(setup):
    engine, driver, _ = setup
    engine.handle("jarvis switch to firefox")
    assert ("activate", "Mozilla Firefox") in driver.calls


def test_quit_stops_the_engine(setup):
    engine, _, _ = setup
    engine.handle("jarvis shut down")
    assert not engine.running


# --- focusing an app that has several windows ---------------------------
@pytest.fixture
def terminals(monkeypatch, tmp_path):
    """Three terminals and a browser — the shape a real desktop has."""
    from jarvis.drivers.base import WindowInfo

    monkeypatch.setenv("JARVIS_CONFIG", "")
    monkeypatch.chdir(tmp_path)
    windows = [
        WindowInfo(11, "hub — Claude Code", "WindowsTerminal.exe"),
        WindowInfo(22, "npm run dev", "WindowsTerminal.exe"),
        WindowInfo(33, "Windows PowerShell", "powershell.exe"),
        WindowInfo(44, "Mozilla Firefox", "firefox.exe"),
    ]
    driver = NullDriver(echo=False, windows=windows)
    focused = {"window": windows[3]}
    driver.foreground_window = lambda: focused["window"]

    def activate(window):
        driver.calls.append(("activate", window.title))
        focused["window"] = window
        return True

    driver.activate = activate
    return Engine(load_config(), driver, clock=Clock()), driver, focused


def test_switch_to_terminal_finds_a_terminal(terminals):
    engine, _, focused = terminals
    engine.handle("jarvis switch to terminal")
    assert focused["window"].process == "WindowsTerminal.exe"


def test_terminal_aliases_all_resolve_to_the_same_app(terminals):
    engine, _, focused = terminals
    for phrase in ["the terminal", "console", "the shell", "my terminal"]:
        focused["window"] = engine.driver.list_windows()[3]  # back to Firefox
        engine.handle(f"jarvis switch to {phrase}")
        assert focused["window"].process == "WindowsTerminal.exe", phrase


def test_saying_it_again_cycles_to_the_next_terminal(terminals):
    engine, _, focused = terminals
    seen = []
    for _ in range(3):
        engine.handle("jarvis switch to terminal")
        seen.append(focused["window"].handle)
    assert seen == [11, 22, 33], "each repeat must reach a different terminal"


def test_the_cycle_wraps_around(terminals):
    engine, _, focused = terminals
    for _ in range(4):
        engine.handle("jarvis switch to terminal")
    assert focused["window"].handle == 11


def test_returning_from_another_app_starts_at_the_first_window(terminals):
    engine, _, focused = terminals
    engine.handle("jarvis switch to terminal")
    engine.handle("jarvis switch to terminal")   # now on the second
    engine.handle("jarvis switch to firefox")
    engine.handle("jarvis switch to terminal")
    assert focused["window"].handle == 11


def test_a_single_window_app_does_not_cycle_away_from_itself(terminals):
    engine, _, focused = terminals
    engine.handle("jarvis switch to firefox")
    engine.handle("jarvis switch to firefox")
    assert focused["window"].process == "firefox.exe"


def test_naming_a_specific_shell_ignores_the_other_terminals(terminals):
    engine, _, focused = terminals
    engine.handle("jarvis switch to powershell")
    assert focused["window"].handle == 33
