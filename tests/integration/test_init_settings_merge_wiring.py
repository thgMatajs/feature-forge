"""Wiring test — init.py invokes settings_merge in brownfield branch.

Verifies the contract: after init runs on a brownfield project, the user's
.claude/settings.json contains BOTH the original user entries AND forge's
canonical CC hook registrations (SessionStart + PostToolUse + SubagentStop).
"""
import json
import shutil
from pathlib import Path

import pytest

from engine.utils.settings_merge import _HAS_JSON5


FIXTURE = Path(__file__).parent.parent / "fixtures" / "meobonsai-class"


@pytest.mark.integration
def test_brownfield_init_registers_forge_hooks_in_settings_json(tmp_path):
    """forge init brownfield branch appends forge CC hooks to settings.json."""
    proj = tmp_path / "project"
    shutil.copytree(FIXTURE, proj)

    # User's pre-existing settings (from fixture)
    settings_before = json.loads((proj / ".claude" / "settings.json").read_text())
    assert "PreToolUse" in settings_before["hooks"]  # user has this
    user_pre_count = len(settings_before["hooks"]["PreToolUse"])
    assert user_pre_count >= 1

    # Invoke the new wire helper (its exact name to be determined by impl)
    from engine.init import _merge_forge_hooks_into_settings
    _merge_forge_hooks_into_settings(proj)

    # Result
    settings_after = json.loads((proj / ".claude" / "settings.json").read_text())

    # User entries preserved byte-for-byte
    assert settings_after["hooks"]["PreToolUse"] == settings_before["hooks"]["PreToolUse"]

    # Forge entries appended
    # SessionStart should now contain forge's session-start-drift-check
    session_start = settings_after["hooks"].get("SessionStart", [])
    forge_session_cmds = [
        h["command"] for entry in session_start
        for h in entry.get("hooks", [])
    ]
    assert any("session-start-drift-check" in c for c in forge_session_cmds), \
        f"forge SessionStart hook not registered: {forge_session_cmds}"

    # PostToolUse should contain forge's hooks
    post_tool = settings_after["hooks"].get("PostToolUse", [])
    forge_post_cmds = [
        h["command"] for entry in post_tool
        for h in entry.get("hooks", [])
    ]
    assert any("post-edit-codebase-graph" in c for c in forge_post_cmds), \
        f"forge PostToolUse hook not registered: {forge_post_cmds}"

    # SubagentStop should contain forge's hook
    subagent = settings_after["hooks"].get("SubagentStop", [])
    forge_subagent_cmds = [
        h["command"] for entry in subagent
        for h in entry.get("hooks", [])
    ]
    assert any("post-subagent-validate" in c for c in forge_subagent_cmds), \
        f"forge SubagentStop hook not registered: {forge_subagent_cmds}"


@pytest.mark.integration
def test_merge_idempotent_on_second_invocation(tmp_path):
    """Calling _merge_forge_hooks_into_settings twice produces same state (dedup)."""
    proj = tmp_path / "project"
    shutil.copytree(FIXTURE, proj)

    from engine.init import _merge_forge_hooks_into_settings
    _merge_forge_hooks_into_settings(proj)
    after_first = json.loads((proj / ".claude" / "settings.json").read_text())

    _merge_forge_hooks_into_settings(proj)
    after_second = json.loads((proj / ".claude" / "settings.json").read_text())

    assert after_first == after_second  # idempotent (merge_settings_json dedup)


@pytest.mark.integration
def test_merge_creates_settings_json_if_missing(tmp_path):
    """Greenfield: no .claude/settings.json yet → create with just forge entries."""
    proj = tmp_path / "project"
    (proj / ".claude").mkdir(parents=True)
    # No settings.json yet

    from engine.init import _merge_forge_hooks_into_settings
    _merge_forge_hooks_into_settings(proj)

    settings_path = proj / ".claude" / "settings.json"
    assert settings_path.exists(), "settings.json should be created"
    data = json.loads(settings_path.read_text())
    forge_session_cmds = [
        h["command"] for entry in data["hooks"].get("SessionStart", [])
        for h in entry.get("hooks", [])
    ]
    assert any("session-start-drift-check" in c for c in forge_session_cmds)


@pytest.mark.integration
def test_corrupt_settings_json_backed_up_and_warned(tmp_path, capsys):
    """Parse-failure (invalid JSON) → backup do original + WARN + prossegue.

    Cross-AI review HIGH: settings.json não-parseável NÃO pode ser descartado
    silenciosamente. Antes de reescrever com as forge additions, o original
    corrompido é preservado em .bak e um aviso mentor-calmo é emitido.
    """
    proj = tmp_path / "project"
    (proj / ".claude").mkdir(parents=True)
    settings_path = proj / ".claude" / "settings.json"
    corrupt = "{ nao eh json"
    settings_path.write_text(corrupt)

    from engine.init import _merge_forge_hooks_into_settings
    _merge_forge_hooks_into_settings(proj)

    # Backup preserva o conteúdo ORIGINAL corrompido
    bak = settings_path.with_suffix(settings_path.suffix + ".bak")
    assert bak.exists(), "backup do settings.json corrompido deve existir"
    assert bak.read_text() == corrupt, "backup deve preservar o conteúdo original"

    # settings.json resultante contém as forge additions
    data = json.loads(settings_path.read_text())
    forge_session_cmds = [
        h["command"] for entry in data["hooks"].get("SessionStart", [])
        for h in entry.get("hooks", [])
    ]
    assert any("session-start-drift-check" in c for c in forge_session_cmds), \
        f"forge hooks devem estar presentes após recuperação: {forge_session_cmds}"

    # WARN foi emitido (mentor calmo, menciona o backup)
    captured = capsys.readouterr()
    assert "warn:" in captured.out
    assert ".bak" in captured.out or "backup" in captured.out


@pytest.mark.integration
def test_unreadable_settings_json_warns_and_proceeds(tmp_path, capsys, monkeypatch):
    """OSError ao ler settings.json → WARN best-effort, sem backup, prossegue.

    Quando o arquivo existe mas nem pode ser lido (OSError), não há conteúdo
    legível para backup. Init não falha: avisa e segue com as forge additions.
    """
    proj = tmp_path / "project"
    (proj / ".claude").mkdir(parents=True)
    settings_path = proj / ".claude" / "settings.json"
    settings_path.write_text('{"hooks": {}}')

    real_read_text = Path.read_text
    state = {"raised": False}

    def _boom(self, *args, **kwargs):
        if self == settings_path and not state["raised"]:
            state["raised"] = True
            raise OSError("permissão negada (simulada)")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _boom)

    from engine.init import _merge_forge_hooks_into_settings
    _merge_forge_hooks_into_settings(proj)

    monkeypatch.undo()

    # settings.json resultante contém as forge additions
    data = json.loads(settings_path.read_text())
    forge_session_cmds = [
        h["command"] for entry in data["hooks"].get("SessionStart", [])
        for h in entry.get("hooks", [])
    ]
    assert any("session-start-drift-check" in c for c in forge_session_cmds)

    # WARN foi emitido; nenhum backup (não havia conteúdo legível)
    captured = capsys.readouterr()
    assert "warn:" in captured.out
    bak = settings_path.with_suffix(settings_path.suffix + ".bak")
    assert not bak.exists(), "sem conteúdo legível → sem backup"


@pytest.mark.integration
@pytest.mark.skipif(
    not _HAS_JSON5,
    reason="json5 lib not installed in current Python environment",
)
def test_merge_tolerates_json5_comments_in_existing_settings(tmp_path):
    """If user wrote .claude/settings.json with comments, parser tolerates it."""
    proj = tmp_path / "project"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "settings.json").write_text("""{
        // user's comment
        "theme": "dark",
        "hooks": {
            "PreToolUse": [
                {"matcher": "Write", "hooks": [{"type": "command", "command": "x.sh"}]}
            ],
        }
    }""")

    from engine.init import _merge_forge_hooks_into_settings
    _merge_forge_hooks_into_settings(proj)

    data = json.loads((proj / ".claude" / "settings.json").read_text())
    assert data["theme"] == "dark"  # user's top-level key preserved
    assert data["hooks"]["PreToolUse"][0]["matcher"] == "Write"
    # Forge entries added
    forge_session_cmds = [
        h["command"] for entry in data["hooks"].get("SessionStart", [])
        for h in entry.get("hooks", [])
    ]
    assert any("session-start-drift-check" in c for c in forge_session_cmds)
