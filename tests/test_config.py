import pytest
import yaml

from jarvis.config import deep_merge, load_config, render_args, resolve


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_CONFIG", "")
    monkeypatch.chdir(tmp_path)


def write(tmp_path, data):
    path = tmp_path / "jarvis.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_deep_merge_replaces_lists_and_merges_dicts():
    merged = deep_merge({"a": {"b": 1, "c": 2}, "l": [1, 2]},
                        {"a": {"c": 3}, "l": [9]})
    assert merged == {"a": {"b": 1, "c": 3}, "l": [9]}


def test_defaults_load_without_a_user_config():
    config = load_config()
    assert config.path is None
    assert len(config.commands) > 50


def test_user_command_overrides_a_builtin_by_id(tmp_path):
    path = write(tmp_path, {"commands": [
        {"id": "nav.scroll-down", "phrases": ["scroll down"],
         "action": "scroll", "args": {"direction": "down", "amount": 99}},
    ]})
    config = load_config(str(path))
    command = next(c for c in config.commands if c.id == "nav.scroll-down")
    assert command.args["amount"] == 99
    assert command.source == "user"
    assert sum(1 for c in config.commands if c.id == "nav.scroll-down") == 1


def test_disable_removes_a_builtin(tmp_path):
    path = write(tmp_path, {"disable": ["nav.grid-pick"]})
    config = load_config(str(path))
    assert not any(c.id == "nav.grid-pick" for c in config.commands)


def test_user_list_entries_extend_the_builtin_apps(tmp_path):
    path = write(tmp_path, {"lists": {"apps": {
        "my thing": {"label": "Thing", "process": "thing.exe"}}}})
    config = load_config(str(path))
    assert "my thing" in config.lists["apps"]
    assert "firefox" in config.lists["apps"], "built-ins must survive"


def test_packs_can_be_narrowed(tmp_path):
    path = write(tmp_path, {"packs": ["core"]})
    config = load_config(str(path))
    assert {c.source for c in config.commands} == {"core"}


def test_unknown_pack_is_an_error(tmp_path):
    path = write(tmp_path, {"packs": ["nope"]})
    with pytest.raises(FileNotFoundError):
        load_config(str(path))


def test_command_without_an_action_is_rejected(tmp_path):
    path = write(tmp_path, {"commands": [{"id": "x", "phrases": ["hi"]}]})
    with pytest.raises(ValueError, match="no action"):
        load_config(str(path))


def test_wake_aliases_always_include_the_wake_word(tmp_path):
    path = write(tmp_path, {"wake_word": "computer", "wake_aliases": ["compute"]})
    config = load_config(str(path))
    assert "computer" in config.wake_aliases and "compute" in config.wake_aliases


def test_vars_are_overridable(tmp_path):
    path = write(tmp_path, {"vars": {"wispr_hotkey": "f9"}})
    config = load_config(str(path))
    assert config.get("vars.wispr_hotkey") == "f9"


def test_render_keeps_native_types_for_a_lone_placeholder():
    assert render_args({"n": "{n}"}, {"n": 7}) == {"n": 7}
    assert render_args({"a": "{app}"}, {"app": {"x": 1}}) == {"a": {"x": 1}}


def test_render_supports_dotted_lookup_and_defaults():
    assert render_args("{app.launch}", {"app": {"launch": "go"}}) == "go"
    assert render_args("{missing|fallback}", {}) == "fallback"
    assert render_args("a {n} b", {"n": 3}) == "a 3 b"


def test_resolve_returns_none_for_a_missing_hop():
    assert resolve({"a": {"b": 1}}, "a.z") is None
    assert resolve({"a": 1}, "a.b") is None


def test_alias_of_copies_the_target_spec(tmp_path):
    config = load_config()
    assert config.lists["apps"]["console"] == config.lists["apps"]["terminal"]


def test_alias_of_keys_can_be_overridden(tmp_path):
    path = write(tmp_path, {"lists": {"apps": {
        "base": {"label": "Base", "process": "b.exe", "launch": "b"},
        "derived": {"alias_of": "base", "label": "Derived"},
    }}})
    config = load_config(str(path))
    derived = config.lists["apps"]["derived"]
    assert derived["process"] == "b.exe" and derived["label"] == "Derived"


def test_alias_of_follows_a_chain(tmp_path):
    path = write(tmp_path, {"lists": {"apps": {
        "a": {"label": "A", "process": "a.exe"},
        "b": {"alias_of": "a"},
        "c": {"alias_of": "b"},
    }}})
    config = load_config(str(path))
    assert config.lists["apps"]["c"]["process"] == "a.exe"


def test_alias_of_a_missing_target_is_an_error(tmp_path):
    path = write(tmp_path, {"lists": {"apps": {"x": {"alias_of": "nowhere"}}}})
    with pytest.raises(ValueError, match="does not exist"):
        load_config(str(path))


def test_alias_of_cycle_is_an_error(tmp_path):
    path = write(tmp_path, {"lists": {"apps": {
        "x": {"alias_of": "y"}, "y": {"alias_of": "x"}}}})
    with pytest.raises(ValueError, match="cycle"):
        load_config(str(path))
