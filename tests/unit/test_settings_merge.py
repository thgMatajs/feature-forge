import pytest

from engine.utils.settings_merge import _HAS_JSON5, merge_settings_json


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


@pytest.mark.skipif(
    not _HAS_JSON5,
    reason="json5 lib not installed in current Python environment",
)
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


def test_merge_tolerates_non_dict_hooks():
    """C-07b (PR18-R6): `hooks` num shape inesperado (string) não derruba o merge.

    Antes, `result.setdefault('hooks', {})` devolvia a string e `.setdefault`
    estourava AttributeError. Agora o valor não-dict é preservado sob backup e o
    merge segue."""
    existing = {"hooks": "garbage-string", "theme": "dark"}
    additions = {"hooks": {"PreToolUse": [{"command": "forge ingest"}]}}
    result = merge_settings_json(existing, additions)
    assert isinstance(result["hooks"], dict)
    assert result["hooks"]["__forge_backup__"] == "garbage-string"
    assert result["hooks"]["PreToolUse"] == [{"command": "forge ingest"}]
    assert result["theme"] == "dark"


def test_merge_tolerates_non_list_hook_stage():
    """C-07b: `hooks.<stage>` não-lista é preservado sob backup, stage vira lista."""
    existing = {"hooks": {"PreToolUse": "not-a-list"}}
    additions = {"hooks": {"PreToolUse": [{"command": "forge ingest"}]}}
    result = merge_settings_json(existing, additions)
    assert result["hooks"]["PreToolUse__forge_backup__"] == "not-a-list"
    assert result["hooks"]["PreToolUse"] == [{"command": "forge ingest"}]
