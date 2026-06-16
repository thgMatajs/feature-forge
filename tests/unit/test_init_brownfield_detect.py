import pytest
from engine.init import _detect_brownfield


def test_detect_greenfield(tmp_path):
    """Empty project root → not brownfield."""
    assert _detect_brownfield(tmp_path) is False


def test_detect_brownfield_skills_present(tmp_path):
    """`.claude/skills/` with content → brownfield."""
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "test.md").write_text("---\nname: x\n---")
    assert _detect_brownfield(tmp_path) is True


def test_detect_brownfield_agents_present(tmp_path):
    """`.claude/agents/` with content → brownfield."""
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "test.md").write_text("test")
    assert _detect_brownfield(tmp_path) is True


def test_detect_brownfield_settings_json_with_content(tmp_path):
    """`.claude/settings.json` non-empty → brownfield."""
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text('{"hooks": {}}')
    assert _detect_brownfield(tmp_path) is True


def test_detect_greenfield_empty_settings(tmp_path):
    """`.claude/settings.json` zero bytes → still greenfield."""
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text("")
    assert _detect_brownfield(tmp_path) is False


def test_detect_greenfield_empty_subdirs(tmp_path):
    """`.claude/skills/` exists but empty → still greenfield."""
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    assert _detect_brownfield(tmp_path) is False
