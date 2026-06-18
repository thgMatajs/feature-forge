"""Lembrete graph-first no session hook (W-GRAPH Camada 2).

Cobre: o hook instalado contém o bloco do lembrete (string assert no
conteúdo); invocação real via bash emite o lembrete em stderr quando
.claude/graph.db existe e fica silencioso quando não existe; exit 0 sempre.

Refs: docs/reports/auditoria-consolidada-2026-06-17.md §6 P1 (NO-ONBOARDING)
"""

from __future__ import annotations

import os
import pty
import select
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration

# FORGE_HOME desta worktree — o hook canônico vive aqui.
_HOOK = Path(__file__).resolve().parents[2] / "hooks" / "session-start-drift-check.sh"


def test_hook_source_has_graph_reminder_block() -> None:
    body = _HOOK.read_text(encoding="utf-8")
    # Guarda do graph.db + comando + AMBOS os prefixos (TTY emoji + ASCII fallback).
    assert ".claude/graph.db" in body
    assert "forge graph --json" in body
    assert "[graph]" in body  # prefixo ASCII (host não-TTY / CLAUDECODE)
    assert "🔎 graph" in body  # prefixo emoji (TTY interativo sem CLAUDECODE)


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


def _run_hook_with_tty_stdout(project_root: Path) -> tuple[int, str]:
    """Roda o hook com stdout ligado a um pty real e CLAUDECODE ausente.

    A condição `[[ -t 1 && -z "${CLAUDECODE:-}" ]]` só é verdadeira quando
    stdout É um terminal E CLAUDECODE não está setado — exatamente o branch
    emoji. Capturamos stderr (onde o lembrete é emitido) por um pipe separado,
    deixando stdout no pty pra `-t 1` valer. Retorna (returncode, stderr).
    """
    stub = project_root / "forge-stub.sh"
    stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    env = {
        "PATH": "/usr/bin:/bin",
        "FORGE_BIN": str(stub),
        # CLAUDECODE deliberadamente ausente → habilita o branch TTY/emoji.
    }

    master, slave = pty.openpty()  # stdout vai pro pty (faz `-t 1` ser verdade)
    err_r, err_w = os.pipe()  # stderr separado pra capturar o lembrete
    try:
        proc = subprocess.Popen(
            ["bash", str(_HOOK)],
            stdin=slave,
            stdout=slave,
            stderr=err_w,
            cwd=project_root,
            env=env,
            close_fds=True,
        )
        os.close(slave)
        os.close(err_w)

        chunks: list[bytes] = []
        while True:
            ready, _, _ = select.select([err_r], [], [], 5.0)
            if not ready:
                break
            data = os.read(err_r, 4096)
            if not data:
                break
            chunks.append(data)
        returncode = proc.wait(timeout=5)
    finally:
        os.close(master)
        os.close(err_r)

    return returncode, b"".join(chunks).decode("utf-8", errors="replace")


def test_hook_emits_emoji_prefix_on_tty_without_claudecode(tmp_path: Path) -> None:
    """Branch TTY/emoji: stdout num pty real + CLAUDECODE ausente → prefixo `🔎 graph`.

    Pareia com test_hook_emits_reminder_when_graph_db_present (branch ASCII via
    CLAUDECODE=1). Juntos exercitam AMBOS os ramos da condição composta —
    inverter `-z CLAUDECODE` por `-n CLAUDECODE` quebraria um destes dois testes.
    """
    (tmp_path / ".git").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "graph.db").write_text("", encoding="utf-8")
    returncode, stderr = _run_hook_with_tty_stdout(tmp_path)
    assert returncode == 0
    assert "🔎 graph" in stderr  # branch emoji exercitado
    assert "[graph]" not in stderr  # NÃO caiu no branch ASCII
    assert "forge graph --json" in stderr
