"""BUG-UPGRADE-1 (T3): upgrade ganha --dry-run + guard de branch nomeada.

Regressão: ``forge upgrade`` fazia ``git checkout --detach <tag>`` + pip no
FORGE_HOME sem preview nem guard. Numa branch de dev (``fix/...``,
``feat/...``) tiraria o HEAD silenciosamente.

Estes testes montam um repo git local (sem rede) e monkeypatcham fetch/pip
(read-only/efeito externo não desejado no teste).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.upgrade import run_upgrade


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _setup_repo(tmp_path: Path, *, on_branch: str | None) -> Path:
    """Repo com tag v1.4.0 + uma tag v1.4.1 mais nova já local.

    Se ``on_branch`` for None → detached HEAD na v1.4.0 (estado pós-install).
    Se for um nome → cria e fica nessa branch nomeada (estado de dev).
    """
    home = tmp_path / "forge_home"
    home.mkdir()
    _git(["init", "-q", "."], home)
    _git(["config", "user.email", "t@t.co"], home)
    _git(["config", "user.name", "t"], home)
    (home / "f.txt").write_text("a\n", encoding="utf-8")
    _git(["add", "-A"], home)
    _git(["commit", "-qm", "initial"], home)
    _git(["tag", "v1.4.0"], home)
    # Avança + tag v1.4.1 (release mais nova já presente localmente).
    (home / "f.txt").write_text("b\n", encoding="utf-8")
    _git(["add", "-A"], home)
    _git(["commit", "-qm", "bump"], home)
    _git(["tag", "v1.4.1"], home)
    if on_branch is None:
        _git(["checkout", "--detach", "v1.4.0"], home)
    else:
        # Branch nomeada ANCORADA na v1.4.0 (não na latest), de modo que um
        # checkout pra v1.4.1 SERIA necessário — é exatamente onde o guard
        # precisa pausar antes de mutar.
        _git(["checkout", "-q", "-b", on_branch, "v1.4.0"], home)
    return home


def test_upgrade_dry_run_does_not_mutate_git(tmp_path: Path, capsys) -> None:
    home = _setup_repo(tmp_path, on_branch=None)
    sha_before = _git(["rev-parse", "HEAD"], home)

    with patch("engine.upgrade._git_fetch"), patch("engine.upgrade._pip_refresh"):
        rc = run_upgrade(forge_home=home, dry_run=True)

    sha_after = _git(["rev-parse", "HEAD"], home)
    assert rc == 0, f"dry-run deveria sair 0, obtido {rc}"
    assert sha_before == sha_after, "dry-run mutou o git (não deveria)"
    out = capsys.readouterr().out.lower()
    assert "dry" in out or "preview" in out or "faria" in out, (
        "dry-run não anunciou que é preview"
    )


def test_upgrade_guards_named_dev_branch(tmp_path: Path, capsys) -> None:
    home = _setup_repo(tmp_path, on_branch="fix/algo")
    sha_before = _git(["rev-parse", "HEAD"], home)

    with patch("engine.upgrade._git_fetch"), patch(
        "engine.upgrade._pip_refresh"
    ) as pip, patch("engine.upgrade._git_checkout") as checkout:
        rc = run_upgrade(forge_home=home)

    sha_after = _git(["rev-parse", "HEAD"], home)
    assert sha_before == sha_after, "guard não impediu a mutação do git"
    checkout.assert_not_called()
    pip.assert_not_called()
    assert rc != 0, "guard deveria pausar com exit não-zero antes do checkout"
    # Mentor-calmo com 3-caminhos.
    err = capsys.readouterr().err.lower()
    assert "branch" in err


def test_upgrade_does_not_guard_detached_release(tmp_path: Path) -> None:
    """Em detached HEAD numa tag (estado canônico), o fluxo NÃO é guardado."""
    home = _setup_repo(tmp_path, on_branch=None)

    with patch("engine.upgrade._git_fetch"), patch("engine.upgrade._pip_refresh"), patch(
        "engine.upgrade._smoke_version", return_value=True
    ):
        rc = run_upgrade(forge_home=home)

    # Detached → sem guard; o fluxo segue (checkout real da v1.4.1) e sai 0.
    assert rc == 0, f"detached numa tag não deveria ser guardado, rc={rc}"
