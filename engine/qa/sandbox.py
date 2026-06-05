"""Phase 3 — Sandbox execution. Subprocess hardened com CWD isolado.

Spec §5.3 + Decisão 30 (sandbox isolation):
  - ``subprocess.cwd = run_dir / "fixtures"`` (não toca projeto real)
  - ``os.chdir`` rejeitado via ``sitecustomize.py`` preload no ``PYTHONPATH``
  - Paths absolutos fora do sandbox raise ``SandboxBreachError``
  - Budget global + per-validator timeout configuráveis

Consumer canônico: ``engine/qa.py`` Phase 3 sandbox. API pública:

    from engine.qa.sandbox import run_sandbox, Fixture, SandboxResult
    results = run_sandbox(run_dir, fixtures, budget_total_s=60.0, per_validator_s=15.0)

Reusa pattern subprocess de ``engine/verify.py`` (Mandamento #3):
``[sys.executable, script, input]`` + ``capture_output=True`` + ``timeout=...``.
O delta é CWD hardening + budget tracking + chdir guard.

Nota técnica sobre o chdir guard (Decisão 30 hardening):
``PYTHONSTARTUP`` só dispara no REPL interativo do Python — para ``python
script.py`` não-interativo, é silenciosamente ignorado. Usamos
``sitecustomize.py`` posicionado via ``PYTHONPATH``, que é importado por
``site.py`` em qualquer invocação que não use ``-S``. Este é o mecanismo
canônico do CPython para customização per-environment.

Trade-off colateral (IN-01): o ``guard_dir`` prepended ao ``PYTHONPATH``
precede qualquer ``sitecustomize.py`` instalado no environment base
(conda activate, pyenv, virtualenv custom). Validators rodam num ambiente
onde apenas o nosso sitecustomize é executado — o do conda/pyenv/etc.
não dispara. Aceitável porque validators são determinísticos e não devem
depender de hooks de ambiente externo; mencionado aqui pra evitar
surpresa em debugging.

O guard cobre ``os.chdir`` E ``os.fchdir`` (defense-in-depth, WR-04).
Ambos são canais de mudança de CWD e violariam a invariante "CWD setado
externamente é imutável".
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_CHDIR_GUARD = """\
# sitecustomize.py preload — bloqueia mudança de CWD no subprocess do sandbox.
# Decisão 30: CWD foi setado externamente pelo orchestrator e é imutável.
# Cobre os.chdir E os.fchdir (defense-in-depth, WR-04). Ambos canais de
# mudança de CWD violariam a invariante.
import os as _forge_qa_os


def _forge_qa_blocked_chdir(_p, *_a, **_kw):
    raise RuntimeError(
        "os.chdir bloqueado pelo sandbox forge qa (Decisão 30). "
        "CWD foi setado externamente e é imutável."
    )


def _forge_qa_blocked_fchdir(_fd):
    raise RuntimeError(
        "os.fchdir bloqueado pelo sandbox forge qa (Decisão 30). "
        "CWD foi setado externamente e é imutável."
    )


_forge_qa_os.chdir = _forge_qa_blocked_chdir
_forge_qa_os.fchdir = _forge_qa_blocked_fchdir
"""


class SandboxBreachError(RuntimeError):
    """Validator subprocess tentou escapar do CWD do sandbox.

    Tipo distinto de ``RuntimeError`` genérico para que o caller diferencie
    entre breach de isolamento (Decisão 30) e erro de I/O ou validator bug.
    """


@dataclass(frozen=True)
class Fixture:
    """Entrada para o sandbox: validator + input + nome.

    ``input_path`` precisa resolver dentro do ``sandbox_cwd`` (run_dir/fixtures).
    ``validator_path`` pode ser absoluto fora — é o canon validator de
    produção, não conteúdo hostil.
    """

    name: str
    input_path: Path
    validator_path: Path


SandboxStatus = Literal["ok", "timeout", "skipped-budget", "sandbox-breach", "error"]


@dataclass
class SandboxResult:
    """Resultado de um run subprocess. Mutável pra permitir update parcial."""

    fixture: Fixture
    status: SandboxStatus = "ok"
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    error: str = ""


def _validate_paths_inside_sandbox(fixture: Fixture, sandbox_cwd: Path) -> None:
    """Confere que ``fixture.input_path`` resolve dentro do sandbox_cwd.

    ``validator_path`` é exceção legítima: o canon validator pode morar em
    ``validators/`` do projeto (absoluto fora). Apenas input precisa estar
    dentro do CWD isolado.
    """
    sandbox_resolved = sandbox_cwd.resolve()
    try:
        resolved_input = fixture.input_path.resolve()
    except OSError as exc:
        raise SandboxBreachError(
            f"fixture.input_path {fixture.input_path} não resolve: {exc}"
        ) from exc

    sandbox_str = str(sandbox_resolved)
    resolved_str = str(resolved_input)
    if resolved_str != sandbox_str and not resolved_str.startswith(
        sandbox_str + os.sep
    ):
        raise SandboxBreachError(
            f"fixture.input_path {fixture.input_path} fora do sandbox {sandbox_cwd} "
            f"(resolved={resolved_input}). Decisão 30: inputs devem morar em "
            f"run_dir/fixtures/."
        )


def _write_chdir_guard(run_dir: Path) -> Path:
    """Escreve sitecustomize.py em um diretório dedicado para PYTHONPATH preload.

    Retorna o diretório que deve ser prepended ao PYTHONPATH (não o arquivo).
    """
    guard_dir = run_dir / "_sandbox_guard"
    guard_dir.mkdir(parents=True, exist_ok=True)
    guard_file = guard_dir / "sitecustomize.py"
    guard_file.write_text(_CHDIR_GUARD, encoding="utf-8")
    return guard_dir


def _hardened_env(guard_dir: Path) -> dict[str, str]:
    """Constrói env com sitecustomize.py preload + marker FORGE_QA_SANDBOX=1."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    if existing:
        env["PYTHONPATH"] = f"{guard_dir}{os.pathsep}{existing}"
    else:
        env["PYTHONPATH"] = str(guard_dir)
    env["FORGE_QA_SANDBOX"] = "1"
    return env


def run_sandbox(
    run_dir: Path,
    fixtures: list[Fixture],
    *,
    budget_total_s: float = 60.0,
    per_validator_s: float = 15.0,
) -> list[SandboxResult]:
    """Loop subprocess pra cada fixture com hardening conforme Decisão 30.

    Cada validator roda em subprocess isolado (CWD = run_dir/fixtures, sem
    shell, com chdir guard preloaded). Budget global + per-validator
    enforçados via ``subprocess.run(timeout=...)``.

    Raises
    ------
    ValueError
        Se ``budget_total_s <= 0`` ou ``per_validator_s <= 0``.

    Returns
    -------
    list[SandboxResult]
        Um result por fixture, ordem preservada. Mesmo em breach/timeout/skip,
        o fixture correspondente aparece na lista com o status apropriado.
    """
    if budget_total_s <= 0:
        raise ValueError(
            f"budget_total_s deve ser > 0 (recebido {budget_total_s}). "
            "Decisão 30 exige budget finito para enforcement."
        )
    if per_validator_s <= 0:
        raise ValueError(
            f"per_validator_s deve ser > 0 (recebido {per_validator_s}). "
            "Decisão 30 exige timeout per-validator finito."
        )

    sandbox_cwd = run_dir / "fixtures"
    sandbox_cwd.mkdir(parents=True, exist_ok=True)

    # Caminho rápido: sem fixtures, retorna sem montar guard (economiza I/O).
    if not fixtures:
        return []

    guard_dir = _write_chdir_guard(run_dir)
    env = _hardened_env(guard_dir)

    results: list[SandboxResult] = []
    started = time.monotonic()

    for fixture in fixtures:
        elapsed = time.monotonic() - started
        if elapsed >= budget_total_s:
            results.append(SandboxResult(fixture=fixture, status="skipped-budget"))
            continue

        # IN-04: validator_path inexistente vira status=error com mensagem
        # nomeada — sem isso, OSError genérico no catch dificulta debug.
        if not fixture.validator_path.is_file():
            results.append(
                SandboxResult(
                    fixture=fixture,
                    status="error",
                    error=(
                        f"validator_path não é arquivo: {fixture.validator_path}"
                    ),
                )
            )
            continue

        try:
            _validate_paths_inside_sandbox(fixture, sandbox_cwd)
        except SandboxBreachError as exc:
            results.append(
                SandboxResult(fixture=fixture, status="sandbox-breach", error=str(exc))
            )
            continue

        # WR-01: status semantics na fronteira budget/timeout. Quando
        # remaining < ~50ms (spawn overhead do interpreter), o subprocess
        # nem ia conseguir começar trabalho útil — marca como
        # skipped-budget em vez de deixar o subprocess.run(timeout=tiny)
        # disparar TimeoutExpired e cair em status=timeout. Phase 4
        # synthesis depende dessa distinção (timeout = validator lento;
        # skipped-budget = orchestrator decidiu pular).
        remaining = min(per_validator_s, budget_total_s - elapsed)
        if remaining < 0.05:
            results.append(SandboxResult(fixture=fixture, status="skipped-budget"))
            continue

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(fixture.validator_path),
                    str(fixture.input_path),
                ],
                cwd=sandbox_cwd,
                capture_output=True,
                text=True,
                timeout=remaining,
                env=env,
                check=False,
            )
            results.append(
                SandboxResult(
                    fixture=fixture,
                    status="ok",
                    exit_code=proc.returncode,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    duration_s=time.monotonic() - t0,
                )
            )
        except subprocess.TimeoutExpired:
            results.append(
                SandboxResult(
                    fixture=fixture,
                    status="timeout",
                    duration_s=time.monotonic() - t0,
                )
            )
        except OSError as exc:
            results.append(
                SandboxResult(
                    fixture=fixture,
                    status="error",
                    error=f"OS error: {exc}",
                    duration_s=time.monotonic() - t0,
                )
            )

    return results
