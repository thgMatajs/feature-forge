"""Fronteira de execução externa — engine → binário do projeto consumidor.

Decisão 33: caminho de execução dedicado pra binários externos (linters, build
tools), DISTINTO do sandbox de validators da Decisão 30. O sandbox de validators
é Python-only e hermético (sitecustomize.py preload); um binário externo não
passa pelo interpretador do forge, então esse hardening não o cobre. Aqui as
garantias são próprias e explícitas: env reduzido (build_safe_env), timeout com
estouro → degraded, skip-se-ausente (resolve_invocation → None), check=False
(classifica, não estoura), sem auto-fix, sem instalar toolchain.

GENÉRICO por design: este módulo só sabe rodar um argv e resolver candidatos de
invocação. Nada tool-específico (ktlint/gradle/swiftlint) vive aqui — isso é
responsabilidade dos callers (Fase 1, Tema 6).

Spec: docs/superpowers/specs/2026-06-30-native-quality-gates-design.md §3.
Pattern espelhado: engine/verify.py::_invoke_validator (env reduzido + timeout).
"""
from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from engine._sandbox.env import build_safe_env

# Mesmas extras do subprocess de validator (engine/verify.py:1024): toolchain
# Java/Android/Gradle precisa dessas pra rodar; nenhuma é sensitive.
_EXTERNAL_ENV_EXTRAS: tuple[str, ...] = ("JAVA_HOME", "ANDROID_HOME", "GRADLE_USER_HOME")

_DEFAULT_TIMEOUT = 120


@dataclass
class ExternalToolResult:
    """Resultado bruto de um binário externo. A semântica de veredito
    (warning vs fail, threshold por-projeto) é do caller (Fase 1)."""

    tool: str
    status: str  # "pass" | "fail" | "degraded" | "skipped"
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    skipped_reason: str = ""


def run_external_tool(
    argv: list[str],
    project_root: Path,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
) -> ExternalToolResult:
    """Roda ``argv`` como binário externo no working tree do projeto.

    - ``check=False``: nunca estoura por exit code; classifica.
    - exit 0 → ``pass``; exit ≠ 0 → ``fail`` (mapping bruto; threshold é do caller).
    - ``TimeoutExpired`` → ``degraded`` (não estoura): um gate que não terminou
      nem reprova nem finge passar (filosofia "verde inerte" do Tema 6).
    - ``OSError`` (binário some/não-executável) → ``degraded``.
    - env reduzido via ``build_safe_env`` (não vaza segredos pro linter).
    - ``cwd = project_root`` (o gate vê os arquivos reais — read-only por contrato
      do caller, que escolhe só subcomandos de check; ver Decisão 33).
    """
    tool = argv[0] if argv else ""
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=build_safe_env(extras=_EXTERNAL_ENV_EXTRAS),
            cwd=str(project_root),
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - started) * 1000)
        return ExternalToolResult(
            tool=tool,
            status="degraded",
            exit_code=None,
            stdout="",
            stderr="",
            duration_ms=duration_ms,
            skipped_reason=f"timeout (>{timeout}s) — o gate não terminou; classifiquei como degraded, não fail",
        )
    except OSError as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return ExternalToolResult(
            tool=tool,
            status="degraded",
            exit_code=None,
            stdout="",
            stderr=str(exc),
            duration_ms=duration_ms,
            skipped_reason=f"não consegui executar {tool!r}: {exc}",
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    status = "pass" if proc.returncode == 0 else "fail"
    return ExternalToolResult(
        tool=tool,
        status=status,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        duration_ms=duration_ms,
    )


def resolve_invocation(
    candidates: list[list[str] | str],
    project_root: Path,
) -> list[str] | None:
    """Resolve o primeiro candidato de invocação que existe, como argv.

    Candidatos em ordem de preferência (primeiro que resolver vence):

    - ``list[str]`` com primeiro elemento ``./...`` (wrapper relativo ao projeto,
      ex. ``["./gradlew", "task"]``) → resolve se ``project_root / first[2:]``
      é arquivo; retorna o argv inalterado.
    - ``list[str]`` com primeiro elemento path absoluto (ex. config bin) → resolve
      se o path existe; retorna inalterado.
    - ``list[str]`` com primeiro elemento nome simples → ``shutil.which``; se achar,
      retorna ``[resolved, *rest]``.
    - ``str`` (nome de tool) → ``shutil.which``; se achar, retorna ``[resolved]``.

    Nenhum resolve → ``None`` (skip-se-ausente — o caller emite o aviso
    mentor-calmo; o forge não reprova por ausência de toolchain).
    """
    for cand in candidates:
        argv = [cand] if isinstance(cand, str) else list(cand)
        if not argv:
            continue
        first = argv[0]
        if first.startswith("./"):
            if (project_root / first[2:]).is_file():
                return argv
            continue
        path = Path(first)
        if path.is_absolute():
            if path.exists():
                return argv
            continue
        resolved = shutil.which(first)
        if resolved:
            return [resolved, *argv[1:]]
    return None
