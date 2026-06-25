"""Fronteira shell pro `mem` — o substrato de memória do forge (Fase 0).

O `mem` é embarcado como asset opaco (`engine/assets/mem/mem`, pinado em
v0.8.1) e vendorizado em projetos consumidores como `.claude/bin/mem`. Esta
fronteira o invoca SEMPRE por subprocess — nunca `import mem` — preservando a
disciplina de Decisão 22 (zero runtime dep em outra ferramenta) e o desenho
de substituição L1/L2/L3.

A espinha de subprocess segue o padrão de
`validators/_gate_infra.py:dispatch_native_tool`: localiza o binário,
`subprocess.run` com timeout, captura stdout/stderr/exit-code, e degrada
soft (sem propagar exceção) quando o binário falta ou estoura o timeout. O
scrub de env reusa `engine.host.env.scrubbed_subprocess_env` — a deny-list
canônica de sinais de host agêntico (Mandamento #3: composição > cópia).

Voz: mentor calmo. PT neutro.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from engine.host.env import scrubbed_subprocess_env

# Versão do `mem` que o forge embarca e contra a qual a integração foi
# desenhada. Pin explícito — o asset em `engine/assets/mem/VERSION` carrega o
# mesmo valor pra verificação por filesystem.
MEM_PINNED_VERSION = "0.8.1"

# Sentinela de exit-code pra "binário não encontrado". Distinto de qualquer
# exit-code real do mem (0 sucesso, 1 erro, 2 not-found, 3 erro de uso) e
# negativo pra nunca colidir com um returncode de processo.
_BINARY_NOT_FOUND = -1

# Sentinela de exit-code pra timeout — o processo foi morto antes de produzir
# um returncode próprio.
_TIMEOUT = -2


@dataclass(frozen=True)
class MemResult:
    """Resultado de uma invocação ao `mem` por subprocess.

    Campos:
        found:     True se o binário foi localizado e rodou (mesmo que o mem
                   tenha retornado exit não-zero, como o exit 2 = not-found,
                   que é contrato e não falha de execução). False só quando o
                   binário não existe no filesystem.
        exit_code: returncode do processo; ``_BINARY_NOT_FOUND`` (-1) quando o
                   binário falta; ``_TIMEOUT`` (-2) quando estourou o timeout.
        stdout:    stdout capturado (vazio em not-found/timeout).
        stderr:    stderr capturado, ou uma mensagem descritiva em
                   not-found/timeout.
        timed_out: True só no caso de ``subprocess.TimeoutExpired`` — sinaliza
                   fail-soft de timeout sem obrigar o caller a inspecionar o
                   exit-code sentinela.
    """

    found: bool
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _resolve_binary(project_root: Path) -> str | None:
    """Localiza o binário do `mem`, na ordem de precedência do desenho.

    1. ``<project_root>/.claude/bin/mem`` — a cópia vendorizada (caso normal
       num projeto consumidor que rodou o scaffold).
    2. ``shutil.which("mem")`` — um clone de desenvolvimento no PATH (fallback
       pra dogfood/dev).
    3. ``None`` — nenhum dos dois; o caller degrada soft.
    """
    vendored = project_root / ".claude" / "bin" / "mem"
    if vendored.is_file():
        return str(vendored)
    return shutil.which("mem")


def mem_call(
    project_root: Path,
    subcmd_args: list[str],
    *,
    json: bool = True,
    timeout: int = 10,
) -> MemResult:
    """Invoca o `mem` por subprocess e devolve um ``MemResult`` estruturado.

    Args:
        project_root: raiz do projeto consumidor — usada pra resolver o binário
            vendorizado e como ``cwd`` do subprocesso.
        subcmd_args: o subcomando do mem e seus argumentos (ex.: ``["doctor"]``,
            ``["get", "<id>"]``).
        json: quando True, prefixa ``--json`` ANTES do subcomando. O mem é um
            parser argparse com flag global: ``--json`` depois do subcomando
            quebra com ``unrecognized arguments: --json``. Por isso a ordem é
            ``[<bin>, "--json", *subcmd_args]`` — nunca ``[<bin>, *subcmd_args,
            "--json"]``.
        timeout: teto em segundos pro subprocesso; estouro vira fail-soft.

    Returns:
        ``MemResult``. Nunca propaga exceção: binário ausente, timeout e exit
        não-zero são todos mapeados pra campos do dataclass.
    """
    binary = _resolve_binary(project_root)
    if binary is None:
        return MemResult(
            found=False,
            exit_code=_BINARY_NOT_FOUND,
            stdout="",
            stderr=(
                "mem não encontrado — nem vendorizado em "
                f"{project_root}/.claude/bin/mem nem no PATH"
            ),
        )

    # `--json` é flag GLOBAL do mem: precede o subcomando obrigatoriamente.
    argv = [binary, "--json", *subcmd_args] if json else [binary, *subcmd_args]

    try:
        proc = subprocess.run(
            argv,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=scrubbed_subprocess_env(),
        )
    except subprocess.TimeoutExpired:
        return MemResult(
            found=True,
            exit_code=_TIMEOUT,
            stdout="",
            stderr=f"mem timeout (>{timeout}s)",
            timed_out=True,
        )

    # Binário rodou: found=True independente do exit-code. exit 2 (not-found)
    # é contrato do mem, não falha de execução — o caller interpreta a
    # semântica pelo exit_code.
    return MemResult(
        found=True,
        exit_code=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )
