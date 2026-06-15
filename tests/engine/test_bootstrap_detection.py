"""Bootstrap-state detection in ``engine/cli.py`` (Task 9.5, graph-ia-evolution).

Contract (spec AC-11):

- ``_check_bootstrap_state(project_root)`` returns ``None`` quando
  ``.git/hooks/pre-commit`` é um symlink válido (state OK pós-bootstrap).
- Retorna mensagem mentor-calmo (string) quando o symlink está ausente
  ou broken, instruindo o usuário a rodar ``bash .claude/bootstrap.sh``.
- ``main()`` integra a checagem antes do dispatch pros handlers, mas
  **pula** pra subcommands read-only que precisam funcionar pré-bootstrap:
  ``--version``, ``--help``, ``help``, ``doctor``, e o próprio ``bootstrap``
  (caso seja exposto no futuro).

Refs:
- docs/superpowers/specs/2026-06-12-graph-ia-evolution.md AC-11
- docs/superpowers/plans/2026-06-12-graph-ia-evolution.md Task 9.5.2/9.5.4/9.5.5
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import cli


# ── Helpers ─────────────────────────────────────────────────────────────────


def _seed_hook_source(project_root: Path) -> None:
    """Cria ``hooks/git-pre-commit`` no source — marker de "este é o repo forge".

    ``_check_bootstrap_state`` só fires quando esse arquivo existe (cf. docstring
    do helper). Sem isso, todo check é skip → tests da error-path não disparam.
    """
    delegator = project_root / "hooks" / "git-pre-commit"
    delegator.parent.mkdir(parents=True, exist_ok=True)
    delegator.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    delegator.chmod(0o755)


def _install_hook_symlink(project_root: Path) -> Path:
    """Cria ``.git/hooks/pre-commit`` como symlink válido apontando pro target.

    Mirrors o que ``.claude/bootstrap.sh`` faz: cria symlink relativo
    ``../../hooks/git-pre-commit`` e garante que o alvo existe.
    """
    _seed_hook_source(project_root)
    git_hooks = project_root / ".git" / "hooks"
    git_hooks.mkdir(parents=True, exist_ok=True)

    target_rel = Path("..") / ".." / "hooks" / "git-pre-commit"
    link = git_hooks / "pre-commit"
    link.symlink_to(target_rel)
    return link


# ── Direct function tests ──────────────────────────────────────────────────


def test_check_bootstrap_state_returns_none_when_symlink_exists(
    tmp_forge_project: Path,
) -> None:
    """Symlink válido pra hooks/git-pre-commit → state OK, retorna None."""
    _install_hook_symlink(tmp_forge_project)

    result = cli._check_bootstrap_state(tmp_forge_project)

    assert result is None


def test_check_bootstrap_state_returns_error_when_symlink_missing(
    tmp_forge_project: Path,
) -> None:
    """Sem ``.git/hooks/pre-commit`` → mensagem mentor-calmo + instrução."""
    # tmp_forge_project só tem .git/ (não .git/hooks/pre-commit).
    # Source ``hooks/git-pre-commit`` precisa existir pra check fire.
    _seed_hook_source(tmp_forge_project)

    result = cli._check_bootstrap_state(tmp_forge_project)

    assert result is not None
    assert "bootstrap.sh" in result
    # Voz mentor-calmo: instrução clara, sem voz corporativa
    assert "Rode" in result or "rode" in result


# ── Integration: main() skipping logic ─────────────────────────────────────


def test_check_bootstrap_state_skips_for_version_help(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``forge --version`` e ``forge --help`` funcionam pré-bootstrap.

    Mesmo sem ``.git/hooks/pre-commit`` symlink, esses subcommands precisam
    completar com exit 0 — usuário pode estar inspecionando antes do bootstrap.
    """
    monkeypatch.chdir(tmp_forge_project)

    # --version
    rc = cli.main(["--version"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "forge" in out.lower()

    # --help
    rc = cli.main(["--help"])
    assert rc == 0


def test_check_bootstrap_state_skips_for_bootstrap_subcommand(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Comandos read-only (``doctor``) e meta (``help``) não bloqueiam pré-bootstrap.

    Integration smoke: garantimos que a skip-list em ``main()`` cobre o
    caso onde o subcommand é destinado a debuggar/operar sobre um repo
    ainda não bootstrap-ado. Usamos ``help`` porque é guaranteed-no-op
    sem precisar de project state real.
    """
    monkeypatch.chdir(tmp_forge_project)

    rc = cli.main(["help"])

    assert rc == 0
    # Não deve printar a mensagem de bootstrap-missing
    err = capsys.readouterr().err
    assert "bootstrap.sh" not in err
