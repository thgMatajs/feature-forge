"""Brownfield contract e2e — init scenario over the meobonsai-class fixture.

Strategy: since `engine.init.run` is interactive (Decision 10 — no flags), this
test SIMULATES init's brownfield path by:
  1. Copying the fixture to tmp
  2. Asserting `_detect_brownfield` returns True
  3. Running the WRITE helpers in pipeline order
  4. Invoking `merge_settings_json` as init's brownfield branch would (or should)
  5. Asserting the post-state matches the brownfield contract:
     - User files byte-unchanged
     - Forge sub-namespace populated
     - Settings.json merged append-only (user entries preserved + forge added)

Limitation: this is a "composition" test, not a true e2e through `init.run`.
A future task (Decision-10-respecting interactive harness) would replace this
with a real e2e via subprocess + automated host adapter responses.
"""
import hashlib
import json
import shutil
from pathlib import Path

import pytest


FIXTURE = Path(__file__).parent.parent / "fixtures" / "meobonsai-class"


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.mark.integration
def test_brownfield_detected_for_fixture(tmp_path):
    """_detect_brownfield returns True for the meobonsai-class fixture."""
    proj = tmp_path / "project"
    shutil.copytree(FIXTURE, proj)
    from engine.init import _detect_brownfield
    assert _detect_brownfield(proj) is True


@pytest.mark.integration
def test_brownfield_init_simulation_preserves_user_files(tmp_path):
    """Full brownfield pipeline simulation — user files survive byte-for-byte."""
    proj = tmp_path / "project"
    shutil.copytree(FIXTURE, proj)

    # Capture user-side shas BEFORE
    claude_md_sha = _sha256(proj / "CLAUDE.md")
    skill_shas = {p.name: _sha256(p) for p in (proj / ".claude" / "skills").iterdir()}
    agent_shas = {p.name: _sha256(p) for p in (proj / ".claude" / "agents").iterdir()}
    user_hook_pre_sha = _sha256(proj / ".claude" / "hooks" / "pre-commit-user.sh")
    user_hook_post_sha = _sha256(proj / ".claude" / "hooks" / "post-edit.sh")
    settings_before = json.loads((proj / ".claude" / "settings.json").read_text())

    # Run brownfield pipeline simulation
    from engine.init import _install_git_hooks
    from engine.utils.paths import (
        forge_dir, forge_config_path, forge_state_dir,
        forge_hooks_dir, forge_cards_local_dir,
    )
    from engine.utils.settings_merge import merge_settings_json

    # 1. Sub-namespace skeleton
    forge_dir(proj).mkdir(parents=True, exist_ok=True)
    forge_state_dir(proj).mkdir(parents=True, exist_ok=True)
    forge_cards_local_dir(proj).mkdir(parents=True, exist_ok=True)
    forge_hooks_dir(proj).mkdir(parents=True, exist_ok=True)

    # 2. Seed forge git-hook + install chained delegator
    (proj / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
    (forge_hooks_dir(proj) / "git-pre-commit").write_text(
        "#!/usr/bin/env bash\necho 'FORGE_PRECOMMIT_MARKER'\n"
    )
    (forge_hooks_dir(proj) / "git-pre-commit").chmod(0o755)
    _install_git_hooks(proj)

    # 3. Write forge config
    forge_config_path(proj).write_text('schema-version: "1.3"\npreset: kmp-mobile\n')

    # 4. Append-only settings.json merge
    forge_additions = {
        "hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": ".claude/forge/hooks/session-start.sh"}]}
            ],
        }
    }
    merged = merge_settings_json(settings_before, forge_additions)
    (proj / ".claude" / "settings.json").write_text(json.dumps(merged, indent=2))

    # === Brownfield contract assertions ===

    # User files byte-unchanged
    assert _sha256(proj / "CLAUDE.md") == claude_md_sha, "CLAUDE.md modified"
    for p in (proj / ".claude" / "skills").iterdir():
        assert _sha256(p) == skill_shas[p.name], f"skills/{p.name} modified"
    for p in (proj / ".claude" / "agents").iterdir():
        assert _sha256(p) == agent_shas[p.name], f"agents/{p.name} modified"
    assert _sha256(proj / ".claude" / "hooks" / "pre-commit-user.sh") == user_hook_pre_sha
    assert _sha256(proj / ".claude" / "hooks" / "post-edit.sh") == user_hook_post_sha

    # Forge sub-namespace populated
    assert forge_dir(proj).exists()
    assert forge_config_path(proj).exists()
    assert forge_state_dir(proj).exists()
    assert forge_cards_local_dir(proj).exists()
    assert forge_hooks_dir(proj).exists()
    assert (forge_hooks_dir(proj) / "git-pre-commit").exists()

    # Settings.json merged — user PreToolUse entry preserved + forge SessionStart added
    settings_after = json.loads((proj / ".claude" / "settings.json").read_text())
    assert len(settings_after["hooks"]["PreToolUse"]) == 1  # user entry intact
    assert settings_after["hooks"]["PreToolUse"][0]["matcher"] == "Write"
    assert "SessionStart" in settings_after["hooks"]
    # SessionStart now has user entry + forge entry (fixture had 1, we added 1)
    assert len(settings_after["hooks"]["SessionStart"]) == 2

    # Git hook chained
    pc = proj / ".git" / "hooks" / "pre-commit"
    content = pc.read_text()
    assert "# FORGE_DELEGATOR_MARKER" in content


@pytest.mark.integration
def test_brownfield_git_hook_actually_chains_both(tmp_path):
    """Run the installed wrapper — verify both user hook and forge hook fire."""
    import subprocess
    proj = tmp_path / "project"
    shutil.copytree(FIXTURE, proj)

    # Plant a user-owned .git/hooks/pre-commit BEFORE init
    (proj / ".git" / "hooks").mkdir(parents=True)
    user_hook = proj / ".git" / "hooks" / "pre-commit"
    user_hook.write_text("#!/usr/bin/env bash\necho 'USER_PRECOMMIT_MARKER'\n")
    user_hook.chmod(0o755)

    from engine.init import _install_git_hooks
    from engine.utils.paths import forge_hooks_dir

    forge_hooks_dir(proj).mkdir(parents=True, exist_ok=True)
    (forge_hooks_dir(proj) / "git-pre-commit").write_text(
        "#!/usr/bin/env bash\necho 'FORGE_PRECOMMIT_MARKER'\n"
    )
    (forge_hooks_dir(proj) / "git-pre-commit").chmod(0o755)
    _install_git_hooks(proj)

    # Run wrapper — both markers should appear in stdout
    result = subprocess.run(
        [str(proj / ".git" / "hooks" / "pre-commit")],
        capture_output=True, text=True, cwd=proj,
    )
    assert "USER_PRECOMMIT_MARKER" in result.stdout
    assert "FORGE_PRECOMMIT_MARKER" in result.stdout
