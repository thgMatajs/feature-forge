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

import json as _json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


@dataclass(frozen=True)
class MemQuery:
    """Resultado de um wrapper de alto nível sobre ``mem_call``.

    ok:      True se o mem rodou e devolveu dado parseável (ou not-found
             contratual em ``get``). False em binário ausente / timeout /
             exit não-zero / JSON inválido.
    data:    JSON parseado (list|dict) quando ok; ``None`` em not-found ou
             em qualquer caminho degradado.
    message: mensagem 3-caminhos (mentor-calmo) quando ``ok`` é False.
    """

    ok: bool
    data: Any
    message: str = ""


def _degraded_message(result: MemResult) -> str:
    if not result.found:
        return (
            "mem indisponível. Três caminhos: "
            "(1) rode `forge init` pra vendorizar `.claude/bin/mem`; "
            "(2) instale o `mem` no PATH (dev/dogfood); "
            "(3) confira que `.claude/bin/mem` existe e é executável."
        )
    if result.timed_out:
        return (
            f"mem não respondeu a tempo ({result.stderr}). Tente de novo "
            "ou rode o subcomando direto em `.claude/bin/mem`."
        )
    return (
        f"mem falhou (exit {result.exit_code}): "
        f"{result.stderr.strip() or 'sem detalhe'}."
    )


def _parse_json(result: MemResult) -> MemQuery:
    try:
        return MemQuery(ok=True, data=_json.loads(result.stdout or "null"))
    except _json.JSONDecodeError as exc:
        return MemQuery(
            ok=False, data=None, message=f"mem devolveu JSON inválido: {exc}"
        )


def _run_or_degrade(project_root: Path, args: list[str]) -> MemQuery:
    result = mem_call(project_root, args)
    if not result.found or result.timed_out or result.exit_code != 0:
        return MemQuery(ok=False, data=None, message=_degraded_message(result))
    return _parse_json(result)


def mem_find(
    project_root: Path,
    query: str,
    *,
    limit: int = 10,
    mem_type: str | None = None,
) -> MemQuery:
    """`mem find` — busca ranqueada (títulos only). data = list de hits."""
    args = ["find", query, "-k", str(limit)]
    if mem_type:
        args += ["--type", mem_type]
    return _run_or_degrade(project_root, args)


def mem_get(project_root: Path, note_id: str) -> MemQuery:
    """`mem get` — corpo da nota. exit 2 (not-found) → ok=True, data=None."""
    result = mem_call(project_root, ["get", note_id])
    if not result.found or result.timed_out:
        return MemQuery(ok=False, data=None, message=_degraded_message(result))
    if result.exit_code == 2:
        return MemQuery(ok=True, data=None)
    if result.exit_code != 0:
        return MemQuery(ok=False, data=None, message=_degraded_message(result))
    return _parse_json(result)


def mem_stats(project_root: Path) -> MemQuery:
    """`mem stats` — counts + vitality + inbox. data = dict."""
    return _run_or_degrade(project_root, ["stats"])


def mem_brief(project_root: Path, *, budget: int | None = None) -> MemQuery:
    """`mem brief` — índice de alto valor. data = list de `{id,type,line}`."""
    args = ["brief"]
    if budget is not None:
        args += ["--budget", str(budget)]
    return _run_or_degrade(project_root, args)


def mem_evolve(project_root: Path, *, apply: bool = False) -> MemQuery:
    """`mem evolve` — curadoria do acervo. data = dict de proposals."""
    args = ["evolve"]
    if apply:
        args.append("--apply")
    return _run_or_degrade(project_root, args)


def mem_inbox_add(
    project_root: Path,
    title: str,
    body: str,
    mem_type: str,
    *,
    importance: int | None = None,
    tags: str | None = None,
    source: str | None = None,
    origin: str = "manual",
) -> MemQuery:
    """`mem inbox add` — enfileira candidato curado no inbox do mem.

    O conhecimento aprovado no ``forge evolve`` entra na fila de inbox
    (anti-envenenamento G11/R12) e só vira nota ativa após ``mem evolve`` /
    ``mem inbox promote``. Reusa ``_run_or_degrade`` — degrade soft 3-caminhos.

    O separador ``"--"`` antes do ``body`` posicional é OBRIGATÓRIO (lição
    W-RULES): body começando com ``-`` quebraria o argparse do mem sem ele.
    """
    args = ["inbox", "add", "--type", mem_type, "-t", title]
    if importance is not None:
        args += ["--importance", str(importance)]
    if tags is not None:
        args += ["--tags", tags]
    if source is not None:
        args += ["--source", source]
    args += ["--origin", origin]
    args += ["--", body]
    return _run_or_degrade(project_root, args)


def mem_context_hint(
    project_root: Path,
    query: str,
    *,
    limit: int = 5,
) -> str | None:
    """Consulta o acervo mem e formata resultado compacto pra context-pack/hint.

    Compõe sobre ``mem_find`` (de 6a) — sem subprocess novo, sem degrade própria.
    Retorna ``None`` em degrade (mem ausente, timeout, erro, lista vazia) pra que
    os callers omitam o bloco silenciosamente — sem crash, sem "forge init" nag.

    O formato de saída é texto plano multi-linha, adequado pra injeção direta em
    context-pack ou renderização como hint educacional:

        Memória relevante (mem find):
        · [feedback] use-stateflow — Use MutableStateFlow para screen state
        · [reference] mvvm-pattern — Padrão MVVM consistente nos ViewModels

    Args:
        project_root: raiz do projeto consumidor (resolve o binário vendorizado).
        query: termo de busca derivado do tema da feature/task.
        limit: máx. de hits a incluir no bloco (default 5 — bounded por design D1).

    Returns:
        Bloco de texto (str) quando há hits; ``None`` em degrade ou lista vazia.
    """
    res = mem_find(project_root, query, limit=limit)
    if not res.ok or not res.data:
        return None
    hits = res.data if isinstance(res.data, list) else []
    if not hits:
        return None
    lines: list[str] = ["Memória relevante (mem find):"]
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        kind = hit.get("type") or hit.get("kind") or "note"
        title = hit.get("title") or hit.get("id") or "?"
        lines.append(f"  · [{kind}] {title}")
    if len(lines) == 1:
        # Nenhum hit válido após parse.
        return None
    return "\n".join(lines)
