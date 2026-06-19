"""Brownfield-safe git hook install — chained delegator (Task 1.4, v1.3).

`_install_git_hooks` antes (Task 0.8) instalava symlinks de
``.git/hooks/{pre-commit,post-commit,pre-push}`` apontando direto para os
hooks canônicos sob ``.claude/forge/hooks/``. Hooks de usuário pré-existentes
eram renomeados pra ``<name>.bak`` (displaced) — ou seja, paravam de rodar.

Task 1.4 substitui isso por um wrapper bash (delegator) que carrega:

1. Hook do usuário (migrado pra ``<name>.user``) — se existe e é executável
2. Hook canônico do forge — sempre

Wrapper é idempotente (marker ``# FORGE_DELEGATOR_MARKER`` no script).
Esta integration suite documenta o contrato.

Spec: ``docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md`` §2.
Plan: ``docs/superpowers/plans/2026-06-16-v1-3-pilot-ready.md`` Task 1.4.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from engine.init import _install_git_hooks
from engine.utils.paths import forge_hooks_dir


def _seed_forge_hook(project_root: Path, name: str = "git-pre-commit") -> Path:
    """Planta um forge hook sintético no sub-namespace canônico."""
    hooks = forge_hooks_dir(project_root)
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / name
    hook.write_text("#!/usr/bin/env bash\necho 'FORGE_HOOK_MARKER'\n")
    hook.chmod(0o755)
    return hook


def _init_git(project_root: Path) -> None:
    (project_root / ".git" / "hooks").mkdir(parents=True)


@pytest.mark.integration
def test_delegator_chains_existing_user_hook(tmp_path: Path) -> None:
    """User hook pré-existente é migrado pra ``.user`` e segue rodando."""
    _init_git(tmp_path)
    _seed_forge_hook(tmp_path)

    user_hook = tmp_path / ".git" / "hooks" / "pre-commit"
    user_hook.write_text("#!/usr/bin/env bash\necho 'USER_HOOK_MARKER'\n")
    user_hook.chmod(0o755)

    _install_git_hooks(tmp_path)

    pc = tmp_path / ".git" / "hooks" / "pre-commit"
    assert pc.exists()
    content = pc.read_text()
    assert "# FORGE_DELEGATOR_MARKER" in content

    # User hook migrado pra .user
    assert (tmp_path / ".git" / "hooks" / "pre-commit.user").exists()

    # Os dois markers disparam ao rodar o wrapper
    output = subprocess.run(
        [str(pc)], capture_output=True, text=True, cwd=tmp_path
    )
    assert "USER_HOOK_MARKER" in output.stdout
    assert "FORGE_HOOK_MARKER" in output.stdout


@pytest.mark.integration
def test_delegator_idempotent(tmp_path: Path) -> None:
    """Instalar duas vezes mantém o mesmo estado — sem encadeamento duplo."""
    _init_git(tmp_path)
    _seed_forge_hook(tmp_path)

    user_hook = tmp_path / ".git" / "hooks" / "pre-commit"
    user_hook.write_text("#!/usr/bin/env bash\necho 'USER'\n")
    user_hook.chmod(0o755)

    _install_git_hooks(tmp_path)
    _install_git_hooks(tmp_path)  # segunda invocação

    pc_content = (tmp_path / ".git" / "hooks" / "pre-commit").read_text()
    # Marker exatamente uma vez
    assert pc_content.count("# FORGE_DELEGATOR_MARKER") == 1
    # .user.user NÃO foi criado (idempotência — só uma migração)
    assert not (
        tmp_path / ".git" / "hooks" / "pre-commit.user.user"
    ).exists()


@pytest.mark.integration
def test_delegator_no_pre_existing_hook(tmp_path: Path) -> None:
    """Sem hook pré-existente, wrapper é criado e exec'a o forge hook."""
    _init_git(tmp_path)
    _seed_forge_hook(tmp_path)

    # SEM pre-commit pré-existente
    _install_git_hooks(tmp_path)

    pc = tmp_path / ".git" / "hooks" / "pre-commit"
    assert pc.exists()
    content = pc.read_text()
    assert "# FORGE_DELEGATOR_MARKER" in content
    # Sem .user (nada pra migrar)
    assert not (tmp_path / ".git" / "hooks" / "pre-commit.user").exists()

    # Marker do forge dispara
    output = subprocess.run(
        [str(pc)], capture_output=True, text=True, cwd=tmp_path
    )
    assert "FORGE_HOOK_MARKER" in output.stdout


@pytest.mark.integration
def test_delegator_uses_relative_forge_hook_path(tmp_path: Path) -> None:
    """C-09 (PR18-R7): o wrapper resolve o forge hook RELATIVO ao próprio script
    (`$(dirname "$0")/../../.claude/forge/hooks/...`), NÃO um path absoluto —
    move/clone-safe."""
    _init_git(tmp_path)
    _seed_forge_hook(tmp_path)
    _install_git_hooks(tmp_path)

    content = (tmp_path / ".git" / "hooks" / "pre-commit").read_text()
    # Não embute o path absoluto do tmp_path.
    assert str(tmp_path) not in content, (
        "wrapper não pode embutir path absoluto (quebra em move/clone)"
    )
    # Usa dirname-relativo pro forge hook.
    assert 'exec "$(dirname "$0")/' in content
    assert "../../.claude/forge/hooks/git-pre-commit" in content


@pytest.mark.integration
def test_delegator_survives_repo_move(tmp_path: Path) -> None:
    """C-09: depois de mover o repo inteiro, o wrapper ainda exec'a o forge hook
    (path relativo resolve no novo local)."""
    src = tmp_path / "orig"
    src.mkdir()
    _init_git(src)
    _seed_forge_hook(src)
    _install_git_hooks(src)

    moved = tmp_path / "moved"
    src.rename(moved)

    pc = moved / ".git" / "hooks" / "pre-commit"
    output = subprocess.run(
        [str(pc)], capture_output=True, text=True, cwd=moved
    )
    assert "FORGE_HOOK_MARKER" in output.stdout, (
        "após mover o repo, o wrapper deve resolver o forge hook pelo path relativo"
    )


@pytest.mark.integration
def test_delegator_upgrades_old_style_symlink(tmp_path: Path) -> None:
    """Install antigo deixou symlink; novo install substitui por wrapper."""
    _init_git(tmp_path)
    forge_hook = _seed_forge_hook(tmp_path)

    pc = tmp_path / ".git" / "hooks" / "pre-commit"
    pc.symlink_to(forge_hook)  # estilo antigo

    _install_git_hooks(tmp_path)

    assert not pc.is_symlink(), "symlink antigo deve virar wrapper"
    content = pc.read_text()
    assert "# FORGE_DELEGATOR_MARKER" in content
