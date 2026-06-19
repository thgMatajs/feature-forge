"""C2 DEAD-VERIFY regression — o delegator git-pre-commit deve achar o hook
de validação tanto no sub-namespace (.claude/forge/hooks/) quanto no path
legado (.claude/hooks/).

Bug original: hooks/git-pre-commit:13 hardcodava só o path legado, então em
consumidores (onde forge init instala em .claude/forge/hooks/) o gate virava
no-op silencioso — exatamente o oposto do contrato fail-closed do Mandamento #1.

Diferente de test_claude_rules_system.py, que copia o hook INTERNO pra um
local arbitrário e o roda direto: aqui rodamos o DELEGATOR (git-pre-commit)
apontando pro hook instalado, exercitando a resolução de path real.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
DELEGATOR = REPO_ROOT / "hooks" / "git-pre-commit"
VALIDATOR = REPO_ROOT / ".claude" / "hooks" / "pre-commit-feature-forge.sh"


def _fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "consumer"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    # Stage uma edição de 01-decisions.md SEM ceremony — o validador deve
    # hard-block (exit 1). É o cenário que prova "o gate rodou".
    (repo / "docs" / "design").mkdir(parents=True)
    (repo / "docs" / "design" / "01-decisions.md").write_text("# fake\n+change\n")
    (repo / "CHANGELOG.md").write_text("# Changelog\n## Unreleased\n- sem ceremony\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    return repo


def _install_validator(repo: Path, subdir: str) -> None:
    """Copia o validador interno pra <repo>/<subdir>/pre-commit-feature-forge.sh."""
    dst_dir = repo / subdir
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "pre-commit-feature-forge.sh"
    shutil.copy(VALIDATOR, dst)
    os.chmod(dst, 0o755)


def _run_delegator(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(DELEGATOR)],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def test_delegator_finds_validator_in_subnamespace(tmp_path):
    """Consumidor real: validador em .claude/forge/hooks/ → gate roda → block."""
    repo = _fake_repo(tmp_path)
    _install_validator(repo, ".claude/forge/hooks")
    result = _run_delegator(repo)
    assert result.returncode == 1, (
        f"gate deveria ter bloqueado via sub-namespace; rc={result.returncode}, "
        f"stderr={result.stderr!r}"
    )
    assert "Revisita decisão" in result.stderr or "BLOCK" in result.stderr


def test_delegator_finds_validator_in_legacy_path(tmp_path):
    """Maintainer repo: validador em .claude/hooks/ → gate roda → block."""
    repo = _fake_repo(tmp_path)
    _install_validator(repo, ".claude/hooks")
    result = _run_delegator(repo)
    assert result.returncode == 1, (
        f"gate deveria ter bloqueado via path legado; rc={result.returncode}, "
        f"stderr={result.stderr!r}"
    )
    assert "Revisita decisão" in result.stderr or "BLOCK" in result.stderr


def test_delegator_noop_when_no_validator_installed(tmp_path):
    """Sem validador em nenhum dos dois paths → no-op, exit 0 (contrato)."""
    repo = _fake_repo(tmp_path)
    result = _run_delegator(repo)
    assert result.returncode == 0, (
        f"delegator deveria ser no-op (exit 0) quando o delegate falta; "
        f"rc={result.returncode}, stderr={result.stderr!r}"
    )
