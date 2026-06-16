from engine.utils.settings_merge import merge_settings_json


def test_merge_appends_to_existing_arrays():
    existing = {
        "hooks": {
            "PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "user.sh"}]}],
        }
    }
    additions = {
        "hooks": {
            "PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "forge.sh"}]}],
        }
    }
    result = merge_settings_json(existing, additions)
    assert len(result["hooks"]["PreToolUse"]) == 2
    assert result["hooks"]["PreToolUse"][0]["matcher"] == "Write"  # user preserved first
    assert result["hooks"]["PreToolUse"][1]["matcher"] == "Edit"  # forge appended


def test_merge_preserves_unrelated_keys():
    existing = {"theme": "dark", "hooks": {}}
    additions = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "x.sh"}]}]}}
    result = merge_settings_json(existing, additions)
    assert result["theme"] == "dark"
    assert "SessionStart" in result["hooks"]


def test_merge_idempotent_dedupe_identical_entries():
    existing = {"hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "forge.sh"}]}]}}
    additions = {"hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "forge.sh"}]}]}}
    result = merge_settings_json(existing, additions)
    assert len(result["hooks"]["PreToolUse"]) == 1  # idempotent


def test_read_settings_tolerant_handles_comments():
    from engine.utils.settings_merge import read_settings_tolerant
    content = """{
        // line comment
        "theme": "dark",
        "hooks": {},  // trailing comma below ↓
    }"""
    result = read_settings_tolerant(content)
    assert result["theme"] == "dark"
    assert result["hooks"] == {}


def test_read_settings_tolerant_plain_json_still_works():
    from engine.utils.settings_merge import read_settings_tolerant
    content = '{"theme": "light"}'
    result = read_settings_tolerant(content)
    assert result["theme"] == "light"
