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


def _run_hook_with_tty(project_root: Path) -> tuple[int, str]:
    """Roda o hook com stdout E stderr ligados ao mesmo pty real, CLAUDECODE ausente.

    O lembrete é emitido em stderr (`} >&2`) e a detecção de host casa o stream
    usado: `[[ -t 2 && -z "${CLAUDECODE:-}" ]]`. Pra simular um terminal real,
    ligamos AMBOS os fds (stdout=1, stderr=2) ao slave do pty — assim `-t 1` e
    `-t 2` são verdadeiros, como num shell interativo onde os dois streams
    compartilham o mesmo TTY. Lemos do master (onde o lembrete chega).
    Retorna (returncode, saída-combinada-do-pty).
    """
    stub = project_root / "forge-stub.sh"
    stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    env = {
        "PATH": "/usr/bin:/bin",
        "FORGE_BIN": str(stub),
        # CLAUDECODE deliberadamente ausente → habilita o branch TTY/emoji.
    }

    master, slave = pty.openpty()  # stdout E stderr vão pro pty (faz `-t 1` e `-t 2` valerem)
    try:
        proc = subprocess.Popen(
            ["bash", str(_HOOK)],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=project_root,
            env=env,
            close_fds=True,
        )
        os.close(slave)

        chunks: list[bytes] = []
        while True:
            ready, _, _ = select.select([master], [], [], 5.0)
            if not ready:
                break
            try:
                data = os.read(master, 4096)
            except OSError:
                # EIO no master quando o slave fecha (filho terminou) — fim do stream.
                break
            if not data:
                break
            chunks.append(data)
        returncode = proc.wait(timeout=5)
    finally:
        os.close(master)

    return returncode, b"".join(chunks).decode("utf-8", errors="replace")


def test_hook_emits_emoji_prefix_on_tty_without_claudecode(tmp_path: Path) -> None:
    """Branch TTY/emoji: stdout+stderr num pty real + CLAUDECODE ausente → prefixo `🔎 graph`.

    Pareia com test_hook_emits_reminder_when_graph_db_present (branch ASCII via
    CLAUDECODE=1). Juntos exercitam AMBOS os ramos da condição composta —
    inverter `-z CLAUDECODE` por `-n CLAUDECODE` quebraria um destes dois testes.
    """
    (tmp_path / ".git").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "graph.db").write_text("", encoding="utf-8")
    returncode, output = _run_hook_with_tty(tmp_path)
    assert returncode == 0
    assert "🔎 graph" in output  # branch emoji exercitado
    assert "[graph]" not in output  # NÃO caiu no branch ASCII
    assert "forge graph --json" in output


def _run_hook_stderr_pty_stdout_pipe(project_root: Path) -> tuple[int, str]:
    """Regression I-2: stderr num pty real, stdout num pipe (NÃO-tty), CLAUDECODE ausente.

    O lembrete vai pra stderr. Como stderr É um terminal aqui, a detecção
    correta (`-t 2`) deve render emoji — mesmo com stdout redirecionado pra
    pipe. Com o bug antigo (`-t 1`), a detecção olhava o stream errado (stdout,
    não-tty) e caía no fallback ASCII. Este teste falha com `-t 1` e passa com
    `-t 2`. Retorna (returncode, stderr-do-pty).
    """
    stub = project_root / "forge-stub.sh"
    stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    env = {
        "PATH": "/usr/bin:/bin",
        "FORGE_BIN": str(stub),
        # CLAUDECODE ausente → habilita o branch TTY/emoji.
    }

    master, slave = pty.openpty()  # stderr vai pro pty (faz `-t 2` valer)
    out_r, out_w = os.pipe()  # stdout num pipe → `-t 1` é FALSO
    try:
        proc = subprocess.Popen(
            ["bash", str(_HOOK)],
            stdin=slave,
            stdout=out_w,
            stderr=slave,
            cwd=project_root,
            env=env,
            close_fds=True,
        )
        os.close(slave)
        os.close(out_w)

        chunks: list[bytes] = []
        while True:
            ready, _, _ = select.select([master], [], [], 5.0)
            if not ready:
                break
            try:
                data = os.read(master, 4096)
            except OSError:
                break
            if not data:
                break
            chunks.append(data)
        returncode = proc.wait(timeout=5)
    finally:
        os.close(master)
        os.close(out_r)

    return returncode, b"".join(chunks).decode("utf-8", errors="replace")


def test_hook_detects_tty_on_stderr_not_stdout(tmp_path: Path) -> None:
    """O lembrete vai pra stderr — a detecção de TTY precisa olhar o fd 2, não o fd 1.

    Cenário: stderr É um terminal (pty), stdout está redirecionado pra um arquivo
    (pipe não-tty). O usuário VÊ o lembrete num terminal real, então deve render
    emoji. O bug (`-t 1`) testava o stream errado e degradava pra ASCII.
    """
    (tmp_path / ".git").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "graph.db").write_text("", encoding="utf-8")
    returncode, stderr = _run_hook_stderr_pty_stdout_pipe(tmp_path)
    assert returncode == 0
    assert "🔎 graph" in stderr  # detecção correta no fd 2
    assert "[graph]" not in stderr  # NÃO degradou pra ASCII por olhar o fd errado
    assert "forge graph --json" in stderr
