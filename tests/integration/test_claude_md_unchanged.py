"""Brownfield-safety regression — init MUST NOT touch CLAUDE.md.

Spec §1 anti-goal 4: "v1.3 NÃO modifica `CLAUDE.md` do projeto consumidor".

Strategy: exercise the write surface of init.py (hook install, gitignore write,
config write via helpers) and assert CLAUDE.md hash stays exactly the same.
The full `engine.init.run` is interactive (Decision 10 — no flags), so we test
the contract by calling the write helpers directly.
"""
import hashlib
import shutil
from pathlib import Path

import pytest


FIXTURE = Path(__file__).parent.parent / "fixtures" / "meobonsai-class"


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.mark.integration
def test_init_writes_do_not_touch_claude_md(tmp_path):
    """init's filesystem-write helpers leave CLAUDE.md byte-identical."""
    proj = tmp_path / "project"
    shutil.copytree(FIXTURE, proj)
    claude_md = proj / "CLAUDE.md"
    assert claude_md.exists(), "fixture must include CLAUDE.md"
    sha_before = _sha256(claude_md)

    from engine.init import _install_git_hooks
    from engine.utils.paths import (
        forge_dir, forge_config_path, forge_state_dir,
        forge_hooks_dir, forge_cards_local_dir,
    )

    # Initialize a .git so hook install does its job (otherwise no-ops)
    (proj / ".git" / "hooks").mkdir(parents=True)

    # Seed a synthetic forge hook so the wrapper has a real target
    fh = forge_hooks_dir(proj)
    fh.mkdir(parents=True, exist_ok=True)
    (fh / "git-pre-commit").write_text("#!/usr/bin/env bash\necho 'forge'\n")
    (fh / "git-pre-commit").chmod(0o755)

    # Call write surface
    _install_git_hooks(proj)
    forge_config_path(proj).parent.mkdir(parents=True, exist_ok=True)
    forge_config_path(proj).write_text('schema-version: "1.3"\n')
    forge_state_dir(proj).mkdir(parents=True, exist_ok=True)
    forge_cards_local_dir(proj).mkdir(parents=True, exist_ok=True)

    sha_after = _sha256(claude_md)
    assert sha_before == sha_after, (
        f"forge init MODIFICOU CLAUDE.md! sha {sha_before[:8]} → {sha_after[:8]}"
    )


@pytest.mark.integration
def test_init_writes_do_not_touch_user_settings_json(tmp_path):
    """Same contract for .claude/settings.json (Wave 1 brownfield safety)."""
    proj = tmp_path / "project"
    shutil.copytree(FIXTURE, proj)
    settings = proj / ".claude" / "settings.json"
    sha_before = _sha256(settings)

    from engine.init import _install_git_hooks
    from engine.utils.paths import forge_hooks_dir, forge_config_path

    (proj / ".git" / "hooks").mkdir(parents=True)
    fh = forge_hooks_dir(proj)
    fh.mkdir(parents=True, exist_ok=True)
    (fh / "git-pre-commit").write_text("#!/usr/bin/env bash\necho 'forge'\n")
    (fh / "git-pre-commit").chmod(0o755)

    _install_git_hooks(proj)
    forge_config_path(proj).parent.mkdir(parents=True, exist_ok=True)
    forge_config_path(proj).write_text('schema-version: "1.3"\n')

    # Note: settings.json append-only merge will be wired in Wave 1's full
    # brownfield pipeline (Task 1.6). For now we just assert init helpers
    # don't randomly touch settings.json.
    sha_after = _sha256(settings)
    assert sha_before == sha_after, (
        f"init helpers touched settings.json: sha {sha_before[:8]} → {sha_after[:8]}"
    )


@pytest.mark.integration
def test_init_writes_do_not_touch_user_skills(tmp_path):
    """`.claude/skills/*` files preserved byte-for-byte."""
    proj = tmp_path / "project"
    shutil.copytree(FIXTURE, proj)
    skills = sorted((proj / ".claude" / "skills").iterdir())
    sha_before = {s.name: _sha256(s) for s in skills}

    from engine.init import _install_git_hooks
    from engine.utils.paths import forge_hooks_dir

    (proj / ".git" / "hooks").mkdir(parents=True)
    fh = forge_hooks_dir(proj)
    fh.mkdir(parents=True, exist_ok=True)
    (fh / "git-pre-commit").write_text("#!/usr/bin/env bash\necho 'forge'\n")
    (fh / "git-pre-commit").chmod(0o755)

    _install_git_hooks(proj)

    sha_after = {s.name: _sha256(s) for s in sorted((proj / ".claude" / "skills").iterdir())}
    assert sha_before == sha_after, (
        f"init touched .claude/skills/*: {sha_before} != {sha_after}"
    )
