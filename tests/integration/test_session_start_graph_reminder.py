"""Lembrete graph-first no session hook (W-GRAPH Camada 2).

Cobre: o hook instalado contém o bloco do lembrete (string assert no
conteúdo); invocação real via bash emite o lembrete em stderr quando
.claude/graph.db existe e fica silencioso quando não existe; exit 0 sempre.

Refs: docs/reports/auditoria-consolidada-2026-06-17.md §6 P1 (NO-ONBOARDING)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration

# FORGE_HOME desta worktree — o hook canônico vive aqui.
_HOOK = Path(__file__).resolve().parents[2] / "hooks" / "session-start-drift-check.sh"


def test_hook_source_has_graph_reminder_block() -> None:
    body = _HOOK.read_text(encoding="utf-8")
    # Guarda do graph.db + comando + regra graph-first + prefixo ASCII fallback.
    assert ".claude/graph.db" in body
    assert "forge graph --json" in body
    assert "[graph]" in body  # prefixo ASCII (host não-TTY / CLAUDECODE)


def _run_hook(project_root: Path) -> subprocess.CompletedProcess[str]:
    # FORGE_BIN aponta pra um stub que não faz nada (isola o lembrete do ingest
    # real); CLAUDECODE força o branch ASCII (determinístico, sem depender de TTY).
    stub = project_root / "forge-stub.sh"
    stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    env = {
        "PATH": "/usr/bin:/bin",
        "FORGE_BIN": str(stub),
        "CLAUDECODE": "1",
    }
    return subprocess.run(
        ["bash", str(_HOOK)],
        capture_output=True,
        text=True,
        cwd=project_root,
        env=env,
    )


def test_hook_emits_reminder_when_graph_db_present(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "graph.db").write_text("", encoding="utf-8")
    result = _run_hook(tmp_path)
    assert result.returncode == 0
    assert "[graph]" in result.stderr
    assert "forge graph --json" in result.stderr


def test_hook_silent_when_graph_db_absent(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".claude").mkdir()  # projeto forge, mas sem graph.db
    result = _run_hook(tmp_path)
    assert result.returncode == 0
    assert "[graph]" not in result.stderr
