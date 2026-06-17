"""E2E — ``forge upgrade`` pull cycle + rollback on smoke fail.

Testa ``engine.upgrade.run_upgrade`` end-to-end usando repos git locais
(file:// remote, sem rede). Cada cenário monta um ``fake_forge_home``
isolado com git init + origin bare repo, evitando qualquer acesso externo.

``_pip_refresh`` é sempre monkeypatched (não roda pip real — lento e
desnecessário pra testar a lógica de pull/rollback).

Skipped por default; ativa com ``RUN_E2E=1`` no env.

Cenários:
- ``test_forge_upgrade_no_op_at_latest``: HEAD == origin → retorna 0,
  "já no latest".
- ``test_forge_upgrade_pull_cycle``: origin tem 1 commit novo → pull
  acontece, HEAD avança, smoke ok, retorna 0.
- ``test_forge_upgrade_rollback_on_smoke_fail``: origin tem 1 commit novo,
  smoke falha → rollback executado, HEAD volta ao sha anterior, retorna 4.

Mentor calmo: falha clara, diagnóstico preciso.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

_RUN_E2E = os.environ.get("RUN_E2E") == "1"


# ── helpers ───────────────────────────────────────────────────────────────────


def _git(args: list[str], cwd: Path) -> str:
    """Executa um comando git e retorna stdout decodificado."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )
    return result.stdout.decode().strip()


def _make_forge_stub(bin_dir: Path, *, smoke_ok: bool = True) -> None:
    """Cria bin/forge stub que retorna 0 (smoke_ok) ou 1 (smoke fail)."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    forge_bin = bin_dir / "forge"
    exit_code = 0 if smoke_ok else 1
    forge_bin.write_text(
        f"#!/usr/bin/env bash\nexit {exit_code}\n",
        encoding="utf-8",
    )
    forge_bin.chmod(0o755)


def _setup_fake_forge_home(
    tmp_path: Path,
    *,
    smoke_ok: bool = True,
) -> tuple[Path, Path]:
    """Monta fake_forge_home com git init + origin bare.

    Retorna (fake_forge_home, origin_bare_path).

    Estrutura:
        tmp_path/
            origin/          ← bare repo (simula remote)
            fake_forge_home/ ← clone local com origin apontando pra origin/
    """
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(["init", "--bare", "."], cwd=origin)

    # Repo de trabalho com commit inicial
    fake_home = tmp_path / "fake_forge_home"
    fake_home.mkdir()
    _git(["init", "."], cwd=fake_home)
    _git(["config", "user.email", "test@test.local"], cwd=fake_home)
    _git(["config", "user.name", "Test"], cwd=fake_home)

    _make_forge_stub(fake_home / "bin", smoke_ok=smoke_ok)

    # Commit inicial
    _git(["add", "."], cwd=fake_home)
    _git(["commit", "-m", "initial"], cwd=fake_home)

    # Aponta main branch (git 2.28+ pode ser 'master' por default)
    try:
        current_branch = _git(["branch", "--show-current"], cwd=fake_home)
    except subprocess.CalledProcessError:
        current_branch = "main"
    if current_branch == "master":
        _git(["branch", "-M", "master", "main"], cwd=fake_home)

    # Adiciona origin e faz push inicial
    _git(["remote", "add", "origin", str(origin)], cwd=fake_home)
    _git(["push", "-u", "origin", "main"], cwd=fake_home)

    return fake_home, origin


def _push_new_commit_to_origin(fake_home: Path, origin: Path) -> str:
    """Cria 1 commit novo em fake_home e faz push pra origin.

    Retorna o SHA novo em origin/main (que o run_upgrade deve puxar).
    Reseta fake_home de volta pro commit anterior via reset --hard, de
    modo que o estado local está 1 commit atrás do origin — simula o
    cenário real de pull.
    """
    prev_sha = _git(["rev-parse", "HEAD"], cwd=fake_home)

    # Cria arquivo novo + commit
    (fake_home / "VERSION").write_text("v1.3.1\n", encoding="utf-8")
    _git(["add", "VERSION"], cwd=fake_home)
    _git(["commit", "-m", "bump to v1.3.1"], cwd=fake_home)
    new_sha = _git(["rev-parse", "HEAD"], cwd=fake_home)

    # Push pra origin
    _git(["push", "origin", "main"], cwd=fake_home)

    # Volta fake_home pro commit anterior (simula "não tenho o novo commit")
    _git(["reset", "--hard", prev_sha], cwd=fake_home)

    return new_sha


# ── testes ────────────────────────────────────────────────────────────────────


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_upgrade_no_op_at_latest(tmp_path: Path, capsys) -> None:
    """HEAD == origin/main → run_upgrade retorna 0, avisa 'já no latest'.

    Cenário: repo local sincronizado com origin. Nenhum commit novo.
    Expectativa: saída 0, mensagem informativa de 'já no latest'.
    """
    from engine.upgrade import run_upgrade

    fake_home, _origin = _setup_fake_forge_home(tmp_path)

    with patch("engine.upgrade._pip_refresh"):  # não roda pip real
        result = run_upgrade(forge_home=fake_home)

    assert result == 0, f"esperado 0, obtido {result}"
    captured = capsys.readouterr()
    assert "latest" in captured.out.lower() or "latest" in captured.err.lower(), (
        f"mensagem 'latest' ausente. stdout={captured.out!r}, stderr={captured.err!r}"
    )


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_upgrade_pull_cycle(tmp_path: Path, capsys) -> None:
    """origin tem 1 commit novo → pull acontece, HEAD avança, retorna 0.

    Cenário: fake_home está 1 commit atrás de origin/main. bin/forge stub
    retorna exit 0 (smoke ok). Expectativa: HEAD local avança para o SHA
    do commit novo após run_upgrade retornar 0.
    """
    from engine.upgrade import run_upgrade

    fake_home, _origin = _setup_fake_forge_home(tmp_path, smoke_ok=True)
    new_sha = _push_new_commit_to_origin(fake_home, _origin)

    sha_before = _git(["rev-parse", "HEAD"], cwd=fake_home)
    assert sha_before != new_sha, "setup incorreto: HEAD já aponta para o novo SHA"

    with patch("engine.upgrade._pip_refresh"):  # não roda pip real
        result = run_upgrade(forge_home=fake_home)

    sha_after = _git(["rev-parse", "HEAD"], cwd=fake_home)

    assert result == 0, f"esperado 0, obtido {result}"
    assert sha_after == new_sha, (
        f"HEAD não avançou após pull. antes={sha_before[:8]}, "
        f"depois={sha_after[:8]}, esperado={new_sha[:8]}"
    )
    captured = capsys.readouterr()
    assert "atualizado" in captured.out.lower() or "atualizado" in captured.err.lower(), (
        f"mensagem 'atualizado' ausente. stdout={captured.out!r}, stderr={captured.err!r}"
    )


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_upgrade_rollback_on_smoke_fail(tmp_path: Path) -> None:
    """Smoke falha após pull → rollback executado, HEAD volta ao sha anterior, retorna 4.

    Cenário: fake_home está 1 commit atrás de origin/main. bin/forge stub
    retorna exit 1 (smoke fail). Expectativa: run_upgrade retorna 4 e
    HEAD volta ao SHA que estava antes do pull.
    """
    from engine.upgrade import run_upgrade

    fake_home, _origin = _setup_fake_forge_home(tmp_path, smoke_ok=False)
    _push_new_commit_to_origin(fake_home, _origin)

    sha_before = _git(["rev-parse", "HEAD"], cwd=fake_home)

    with patch("engine.upgrade._pip_refresh"):  # não roda pip real
        result = run_upgrade(forge_home=fake_home)

    sha_after = _git(["rev-parse", "HEAD"], cwd=fake_home)

    assert result == 4, f"esperado 4 (smoke fail + rollback), obtido {result}"
    assert sha_after == sha_before, (
        f"HEAD não voltou ao sha anterior após rollback. "
        f"antes={sha_before[:8]}, depois={sha_after[:8]}"
    )
