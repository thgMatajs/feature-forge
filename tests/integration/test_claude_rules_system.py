"""Integration test for the Claude Code rules system.

Validates structural integrity of CLAUDE.md, .claude/rules/, .claude/hooks/,
settings.json, bootstrap script, and gitignore patterns.

Marker: integration (excluded from rapid lane).
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = REPO_ROOT / ".claude" / "rules"
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
STATE_DIR = REPO_ROOT / ".claude" / "state"

EXPECTED_RULES = [
    "README.md",
    "orchestrator-persona.md",
    "subagent-workflow.md",
    "decisions.md",
    "disciplines.md",
    "testing.md",
    "scope.md",
    "reuse.md",
    "superpowers.md",
    "doc-sync.md",
    "project-anatomy.md",
    "SMOKE-CHECKLIST.md",
]

EXPECTED_HOOKS = [
    "session-start-orientation.sh",
    "pre-tool-use-load-bearing.sh",
    "post-edit-doc-drift.sh",
    "pre-commit-feature-forge.sh",
]


pytestmark = pytest.mark.integration


# ───────────────────────────────────── structure


def test_claude_md_root_exists():
    assert (REPO_ROOT / "CLAUDE.md").exists()


def test_settings_json_exists_and_parses():
    path = REPO_ROOT / ".claude" / "settings.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert "hooks" in data
    assert "SessionStart" in data["hooks"]
    assert "PreToolUse" in data["hooks"]
    assert "PostToolUse" in data["hooks"]


def test_bootstrap_script_exists_and_executable():
    path = REPO_ROOT / ".claude" / "bootstrap.sh"
    assert path.exists()
    assert os.access(path, os.X_OK), "bootstrap.sh must be executable"


def test_state_dir_has_gitkeep():
    assert (STATE_DIR / ".gitkeep").exists()


# ───────────────────────────────────── rules


@pytest.mark.parametrize("rule_name", EXPECTED_RULES)
def test_rule_file_exists_with_h1(rule_name):
    path = RULES_DIR / rule_name
    assert path.exists(), f"missing rule: {rule_name}"
    content = path.read_text()
    assert re.match(r"^#\s+\S", content), f"{rule_name} must start with H1"


@pytest.mark.parametrize("rule_name", EXPECTED_RULES)
def test_rule_file_linked_in_claude_md(rule_name):
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text()
    assert rule_name in claude_md, f"CLAUDE.md does not reference {rule_name}"


# ───────────────────────────────────── hooks


@pytest.mark.parametrize("hook_name", EXPECTED_HOOKS)
def test_hook_script_exists_executable_valid_bash(hook_name):
    path = HOOKS_DIR / hook_name
    assert path.exists(), f"missing hook: {hook_name}"
    assert os.access(path, os.X_OK), f"{hook_name} must be executable"
    result = subprocess.run(
        ["bash", "-n", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{hook_name} bash syntax error: {result.stderr}"


# ───────────────────────────────────── pre-commit hard block


def test_pre_commit_hard_blocks_decisions_without_ceremony(tmp_path, monkeypatch):
    """If 01-decisions.md is staged and CHANGELOG.md does NOT contain
    'Revisita decisão', the hook must exit non-zero."""
    hook = HOOKS_DIR / "pre-commit-feature-forge.sh"
    assert hook.exists()

    fake_repo = tmp_path / "fake"
    fake_repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@x"], cwd=fake_repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=fake_repo, check=True)
    (fake_repo / "docs" / "design").mkdir(parents=True)
    (fake_repo / "docs" / "design" / "01-decisions.md").write_text("# fake\n+change\n")
    (fake_repo / "CHANGELOG.md").write_text("# Changelog\n## Unreleased\n- some change\n")
    subprocess.run(["git", "add", "-A"], cwd=fake_repo, check=True)

    # Copy hook into fake repo to allow it to run with that working dir
    fake_hook = fake_repo / "pre-commit-feature-forge.sh"
    shutil.copy(hook, fake_hook)
    os.chmod(fake_hook, 0o755)

    result = subprocess.run(
        ["bash", str(fake_hook)],
        cwd=fake_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, (
        f"hook should hard-block; got rc={result.returncode}, "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    assert "Revisita decisão" in result.stderr or "BLOCK" in result.stderr


def test_pre_commit_allows_decisions_with_ceremony(tmp_path):
    """If CHANGELOG.md staged includes 'Revisita decisão N', hook must pass."""
    hook = HOOKS_DIR / "pre-commit-feature-forge.sh"

    fake_repo = tmp_path / "fake"
    fake_repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@x"], cwd=fake_repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=fake_repo, check=True)
    (fake_repo / "docs" / "design").mkdir(parents=True)
    (fake_repo / "docs" / "design" / "01-decisions.md").write_text("# fake\n+change\n")
    (fake_repo / "CHANGELOG.md").write_text(
        "# Changelog\n## Unreleased\n- Revisita decisão 22: foo\n"
    )
    subprocess.run(["git", "add", "-A"], cwd=fake_repo, check=True)

    fake_hook = fake_repo / "pre-commit-feature-forge.sh"
    shutil.copy(hook, fake_hook)
    os.chmod(fake_hook, 0o755)

    result = subprocess.run(
        ["bash", str(fake_hook)], cwd=fake_repo, capture_output=True, text=True
    )
    assert result.returncode == 0, f"hook should pass; stderr={result.stderr!r}"


# ───────────────────────────────────── bootstrap idempotency


def test_bootstrap_is_idempotent():
    """Running bootstrap twice produces no diff."""
    bootstrap = REPO_ROOT / ".claude" / "bootstrap.sh"
    # First run
    r1 = subprocess.run(
        ["bash", str(bootstrap)], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert r1.returncode == 0, f"first run failed: {r1.stderr}"
    # Capture state
    r_status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    state_before = r_status.stdout
    # Second run
    r2 = subprocess.run(
        ["bash", str(bootstrap)], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert r2.returncode == 0, f"second run failed: {r2.stderr}"
    r_status2 = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    state_after = r_status2.stdout
    assert state_before == state_after, "bootstrap is not idempotent"


# ───────────────────────────────────── gitignore


def test_gitignore_covers_state_json():
    """`.claude/state/*.json` must be ignored, but `.gitkeep` must be tracked."""
    test_file = STATE_DIR / "_test_ignore_probe.json"
    test_file.write_text("{}")
    try:
        result = subprocess.run(
            ["git", "check-ignore", str(test_file.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"state/*.json should be gitignored; rc={result.returncode}"
        )
    finally:
        test_file.unlink()

    result_keep = subprocess.run(
        ["git", "check-ignore", ".claude/state/.gitkeep"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result_keep.returncode != 0, ".gitkeep must NOT be gitignored"
