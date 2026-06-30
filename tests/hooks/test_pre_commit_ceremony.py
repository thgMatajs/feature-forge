"""Gate do ritual de cerimônia no pre-commit (Decisão 33, Fase 0a).

O hook .claude/hooks/pre-commit-feature-forge.sh faz HARD BLOCK quando
docs/design/01-decisions.md é staged sem a cerimônia no CHANGELOG staged.
Cerimônia válida: 'revisita decisão' (decisão existente) OU 'nova decisão'
(decisão nova, como a 33). Mentor calmo: firme no gate, claro no porquê.

H-001: o repo temp tem commit inicial pra que o exit 1 só possa vir do ramo de
cerimônia (não de erro estrutural de repo sem HEAD), e o BLOCK-test asserta a
string literal do heredoc — não só returncode.
L-001: todos os fixtures vivem em tmp_path; jamais tocam o 01-decisions.md real.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / ".claude" / "hooks" / "pre-commit-feature-forge.sh"
# Prefixo literal do heredoc de BLOCK (espelha pre-commit-feature-forge.sh).
# Estável entre o hook atual (RED) e o reescrito por 0a.2 (GREEN).
BLOCK_MARKER = "🛑 BLOCK: docs/design/01-decisions.md"


def _init_repo(tmp_path: Path) -> Path:
    """Repo temp COM commit inicial (H-001): git diff --cached roda contra HEAD
    válido, então um exit 1 só pode vir do ramo de cerimônia, não de repo sem HEAD."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.st"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "init"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "docs" / "design").mkdir(parents=True)
    return tmp_path


def _stage(repo: Path, decisions_body: str, changelog_body: str) -> None:
    (repo / "docs" / "design" / "01-decisions.md").write_text(decisions_body, encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(changelog_body, encoding="utf-8")
    subprocess.run(
        ["git", "add", "docs/design/01-decisions.md", "CHANGELOG.md"],
        cwd=repo,
        check=True,
    )


def _run_hook(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(HOOK)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_blocks_without_ceremony(tmp_path: Path) -> None:
    # H-001: exit 1 ISOLADO ao ramo de cerimônia — confirmado pela string literal
    # do heredoc (se fosse exit 1 estrutural, o heredoc não teria rodado).
    repo = _init_repo(tmp_path)
    _stage(
        repo,
        "| 33 | stub | stub | stub |\n",
        "## [Unreleased]\n\n### Added\n- nada de cerimônia\n",
    )
    result = _run_hook(repo)
    assert result.returncode == 1, f"esperava BLOCK, veio {result.returncode}: {result.stderr}"
    assert BLOCK_MARKER in result.stderr, (
        "exit 1 sem a string literal do BLOCK = bloqueio estrutural, não do ramo de "
        f"cerimônia (H-001). STDERR: {result.stderr!r}"
    )
    # L-001: o 01-decisions.md REAL do repo nunca foi tocado pelo fixture.
    assert (REPO_ROOT / "docs" / "design" / "01-decisions.md").read_text(
        encoding="utf-8"
    ).count("| stub | stub | stub |") == 0


def test_passes_with_revisita(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, "| 33 | stub | stub | stub |\n", "### Changed\n- Revisita decisão 10: foo — bar\n")
    result = _run_hook(repo)
    assert result.returncode == 0, f"esperava PASS, veio {result.returncode}: {result.stderr}"


def test_passes_with_nova_decisao(tmp_path: Path) -> None:
    # Caso positivo complementar (H-001): MESMO setup estrutural do BLOCK-test
    # (repo COM commit inicial); a única diferença é a cerimônia presente → PASS.
    repo = _init_repo(tmp_path)
    _stage(
        repo,
        "| 33 | stub | stub | stub |\n",
        "### Changed (load-bearing)\n- Nova decisão 33: foo — bar\n",
    )
    result = _run_hook(repo)
    assert result.returncode == 0, f"esperava PASS pra nova decisão, veio {result.returncode}: {result.stderr}"


def test_non_decisions_file_passes(tmp_path: Path) -> None:
    # Controle: o gate de cerimônia só morde 01-decisions.md. Stage de outro
    # arquivo (sem cerimônia nenhuma) passa — prova que o hook não bloqueia o mundo.
    repo = _init_repo(tmp_path)
    (repo / "README.md").write_text("# qualquer coisa\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    result = _run_hook(repo)
    assert result.returncode == 0, f"esperava PASS pra arquivo não-decisions, veio {result.returncode}: {result.stderr}"
