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

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from engine._sandbox.env import build_safe_env


# deep-007: spawn overhead floor — abaixo disso o subprocess nem começa
# trabalho útil; preferimos skipped-budget a um timeout near-instant.
# Tunable se portarmos pra plataforma com spawn mais lento (Windows +
# bundled Python).
_MIN_REMAINING_S_FOR_SPAWN = 0.05


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

    ``tree_rel_path`` (F-1): quando setado, o validator é invocado com o
    contrato real dos validators forge — ``--project-root <mini-tree>``, onde
    ``<mini-tree> = run_dir/fixtures/<name>``. O arquivo materializado mora em
    ``<mini-tree>/<tree_rel_path>`` e ``input_path`` deve apontá-lo. O validator
    escaneia o tree e pega a fixture (exit 1 = pegou). Sem isso, validators
    argparse rejeitam o input posicional com exit 2 e o vetor validator-claim
    fica inerte. Quando ``None``, mantém a invocação posicional legada
    (``[python, validator, input_path]``).
    """

    name: str
    input_path: Path
    validator_path: Path
    tree_rel_path: str | None = None
    extra_args: list[str] | None = None
    """Item 4 (R8): argumentos extra apendados à invocação do validator.

    Validators feature/task-scoped (ex.: ``validate_task_contract.py``)
    exigem ``--scope feature --id <slug>``; sem isso saem 2/warn. O auditor
    declara ``invocation_args`` no descritor da fixture quando o validator-alvo
    é scoped, e o engine threada pra cá.

    HARDENING (Decisão 30 — NÃO afrouxar): ``extra_args`` são APENDADOS APÓS o
    ``--project-root <mini-tree>`` que o engine controla. Qualquer tentativa de
    re-setar ``--project-root`` via ``extra_args`` é NEUTRALIZADA em
    ``run_sandbox`` (a fixture é gerada por LLM — não pode apontar o root pra
    fora do sandbox). Passam como LISTA pro ``subprocess.run`` (sem shell —
    sem injeção de shell)."""


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


def _assert_inside_sandbox(
    candidate: Path, sandbox_resolved: Path, *, label: str
) -> Path:
    """Resolve ``candidate`` e confirma que mora dentro de ``sandbox_resolved``.

    Levanta ``SandboxBreachError`` se o resolve falhar OU se o path escapar o
    sandbox. Retorna o path resolvido. Helper interno pra aplicar o mesmo
    containment check ao ``input_path`` e — pós-F-1 — ao mini-tree e ao arquivo
    materializado, sem afrouxar o guard (Decisão 30: adiciona cobertura, não
    remove).
    """
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise SandboxBreachError(f"{label} {candidate} não resolve: {exc}") from exc

    # Path.relative_to: containment check robusto (vs. startswith + os.sep
    # que falha em corner cases — ex.: sandbox=/tmp/a, input=/tmp/ab/x
    # passaria startswith("/tmp/a") incorretamente sem o +os.sep, e mesmo
    # com +os.sep ignora symlink resolution semantics em platforms onde
    # o path-string compare diverge da semantic-containment).
    try:
        resolved.relative_to(sandbox_resolved)
    except ValueError as exc:
        raise SandboxBreachError(
            f"{label} {candidate} fora do sandbox (resolved={resolved}). "
            f"Decisão 30: inputs/trees devem morar em run_dir/fixtures/."
        ) from exc
    return resolved


def _validate_paths_inside_sandbox(fixture: Fixture, sandbox_cwd: Path) -> None:
    """Confere que os paths da fixture resolvem dentro do sandbox_cwd.

    ``validator_path`` é exceção legítima: o canon validator pode morar em
    ``validators/`` do projeto (absoluto fora). Apenas input/tree precisam
    estar dentro do CWD isolado.

    F-1: quando ``tree_rel_path`` está setado, o containment cobre TAMBÉM o
    mini-tree (``sandbox_cwd/<name>``) e o arquivo materializado
    (``<mini-tree>/<tree_rel_path>``). Um ``tree_rel_path`` com traversal
    (``../../escape.kt``) resolve fora do sandbox e dispara
    ``SandboxBreachError`` — o guard fica MAIS estrito, não mais frouxo.
    """
    sandbox_resolved = sandbox_cwd.resolve()

    _assert_inside_sandbox(
        fixture.input_path, sandbox_resolved, label="fixture.input_path"
    )

    if fixture.tree_rel_path is not None:
        mini_tree = sandbox_cwd / fixture.name
        # O mini-tree em si precisa morar dentro do sandbox (defende contra
        # name com traversal, ex.: name="../escape").
        mini_tree_resolved = _assert_inside_sandbox(
            mini_tree, sandbox_resolved, label="mini-tree"
        )
        # O arquivo materializado (mini-tree/<tree_rel_path>) precisa morar
        # dentro do mini-tree — bloqueia tree_rel_path com traversal.
        materialized = mini_tree / fixture.tree_rel_path
        materialized_resolved = _assert_inside_sandbox(
            materialized, sandbox_resolved, label="fixture.tree_rel_path"
        )
        # Defense-in-depth extra: o arquivo materializado deve cair DENTRO do
        # mini-tree (não só dentro do sandbox), senão um tree_rel_path tipo
        # "../<outra-fixture>/x" vazaria pra fora do próprio tree mesmo
        # permanecendo no sandbox.
        try:
            materialized_resolved.relative_to(mini_tree_resolved)
        except ValueError as exc:
            raise SandboxBreachError(
                f"fixture.tree_rel_path {fixture.tree_rel_path} escapa o mini-tree "
                f"{mini_tree} (resolved={materialized_resolved}). Decisão 30: o "
                f"arquivo materializado deve morar dentro do próprio mini-tree."
            ) from exc


def _write_chdir_guard(run_dir: Path) -> Path:
    """Escreve sitecustomize.py em um diretório dedicado para PYTHONPATH preload.

    Retorna o diretório que deve ser prepended ao PYTHONPATH (não o arquivo).

    deep-020: aplica permissões restritivas (0700 no dir, 0600 no arquivo)
    em best-effort — em multi-tenant POSIX evita que co-tenant leia ou
    troque o guard entre write e subprocess spawn (TOCTOU). Windows ignora
    chmod silenciosamente (OSError swallowed).
    """
    guard_dir = run_dir / "_sandbox_guard"
    guard_dir.mkdir(parents=True, exist_ok=True)
    guard_file = guard_dir / "sitecustomize.py"
    guard_file.write_text(_CHDIR_GUARD, encoding="utf-8")
    try:
        guard_file.chmod(0o600)
        guard_dir.chmod(0o700)
    except OSError:
        pass  # best-effort; Windows não honra POSIX modes
    return guard_dir


def _hardened_env(
    guard_dir: Path,
    *,
    extras: Iterable[str] = (),
) -> dict[str, str]:
    """Constrói env safe + sitecustomize.py preload + marker.

    Refactor (QA-11): delega base pra build_safe_env(extras=...);
    adiciona PYTHONPATH guard e FORGE_QA_SANDBOX=1 por cima.

    SEGURANÇA (deep-001): NÃO herda PYTHONPATH do parent. PYTHONPATH é
    vetor de code-execution — qualquer módulo sob ele pode ser importado
    pelo validator subprocess, então herdar do parent burla a allowlist
    pro var que mais importa (defesa-em-profundidade quebrada).
    Callers que precisem de paths extras devem declará-los via `extras`,
    cruzando o grant flow primeiro.
    """
    # extras vem de _compute_allowed_extras (engine/qa/__init__.py), que
    # já filtrou contra workflow_config.qa.sensitive-env-grants — vars
    # sensitive presentes aqui são as explicitamente autorizadas pelo
    # user. allow_sensitive=True comunica essa pré-validação ao guard
    # de defense-in-depth (deep-003).
    env = build_safe_env(extras=extras, allow_sensitive=True)
    env["PYTHONPATH"] = str(guard_dir)
    env["FORGE_QA_SANDBOX"] = "1"
    return env


# Allowlist canônico de flags que a fixture (gerada por LLM) pode threadar
# pro validator. APENAS estes — o engine é o único dono de ``--project-root``.
# Validators scoped (ex.: ``validate_task_contract.py``) exigem ``--scope`` +
# ``--id``; nada além disso tem caso de uso legítimo numa fixture validator-claim.
_ALLOWED_EXTRA_FLAGS: frozenset[str] = frozenset({"--scope", "--id"})


def _scrub_extra_args(extra_args: list[str] | None) -> list[str]:
    """Item 4 (R8) + C1 (review pr27): ALLOWLIST de extra_args da fixture.

    HARDENING (Decisão 30 — sandbox escape): o engine é o único dono do
    ``--project-root`` — ele sempre aponta pro mini-tree dentro do sandbox.
    ``extra_args`` vêm de uma fixture gerada por LLM; um denylist de
    ``--project-root`` literal era insuficiente porque os validators forge
    usam argparse e, com abreviação honrada (``allow_abbrev``), ``--p``,
    ``--proj``, ``--project``, ``--project-roo`` (e formas ``=``) TODOS setam
    ``project_root`` e, como ÚLTIMA ocorrência, OVERRIDE o root do engine
    (last-wins) — escape total pra ``/etc`` etc.

    A defesa correta é allow-known, drop-rest: passamos SOMENTE os flags
    conhecidos-seguros (``--scope``, ``--id``) com seus valores; QUALQUER
    outro token — flag desconhecida, prefixo ``--p…``/``--project…``, ou
    bare value cujo flag dono foi dropado — é descartado. Não enumeramos
    grafias ruins; só reconhecemos as boas.

    Formas aceitas pra um flag allowed ``F``:
      - ``F valor`` (2 tokens) → ambos passam.
      - ``F=valor`` (1 token)  → passa inteiro.

    A defense-in-depth complementar (``allow_abbrev=False`` no argparser
    compartilhado, ``validators/_common.py``) garante que mesmo um flag que
    escapasse este filtro não seja interpretado como abreviação.

    Retorna lista nova — não muta o input.
    """
    if not extra_args:
        return []
    scrubbed: list[str] = []
    expect_value_for: str | None = None
    for tok in extra_args:
        if expect_value_for is not None:
            # Token anterior foi um flag allowed em forma de espaço → este é
            # o seu valor. Passa e zera o estado.
            scrubbed.append(tok)
            expect_value_for = None
            continue
        if tok in _ALLOWED_EXTRA_FLAGS:
            # Flag allowed forma-espaço: passa e espera o próximo token (valor).
            scrubbed.append(tok)
            expect_value_for = tok
            continue
        if tok.startswith("--"):
            head = tok.split("=", 1)[0]
            if head in _ALLOWED_EXTRA_FLAGS and "=" in tok:
                # Flag allowed forma ``=valor``: passa o token inteiro.
                scrubbed.append(tok)
            # Qualquer outro flag ``--…`` (inclusive abreviações de
            # --project-root e flags desconhecidas) é dropado.
            continue
        # Bare value sem flag dono allowed precedente → órfão, dropa.
    return scrubbed


def run_sandbox(
    run_dir: Path,
    fixtures: list[Fixture],
    *,
    budget_total_s: float = 60.0,
    per_validator_s: float = 15.0,
    extras: Iterable[str] = (),
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

    Parameters
    ----------
    extras : Iterable[str]
        Env vars declaradas em ``qa-extensions.env-needs`` dos cards
        ativos. Filtradas contra grants em workflow-config antes do
        caller chamar (QA-11).
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
    env = _hardened_env(guard_dir, extras=extras)

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
        if remaining < _MIN_REMAINING_S_FOR_SPAWN:
            results.append(SandboxResult(fixture=fixture, status="skipped-budget"))
            continue

        # F-1: invocação muda conforme tree_rel_path. Com tree_rel_path setado,
        # usa o contrato real dos validators forge (--project-root <mini-tree>);
        # o validator escaneia o tree e pega a fixture. Sem ele (legado),
        # mantém a invocação posicional [python, validator, input_path].
        # .resolve() em todos: subprocess roda com cwd=sandbox_cwd, e paths
        # relativos seriam interpretados relativos a esse cwd — quebrando se
        # validator_path for absoluto fora do sandbox (caso canon de produção)
        # ou input_path for path-relativo do caller. Resolver garante absolutos.
        # Item 4 (R8): extra_args (--scope/--id de validators scoped) são
        # apendados APÓS o --project-root que o engine controla. O scrub
        # neutraliza qualquer --project-root injetado pela fixture (Decisão 30).
        safe_extra_args = _scrub_extra_args(fixture.extra_args)
        if fixture.tree_rel_path is not None:
            mini_tree = sandbox_cwd / fixture.name
            cmd = [
                sys.executable,
                str(fixture.validator_path.resolve()),
                "--project-root",
                str(mini_tree.resolve()),
                *safe_extra_args,
            ]
        else:
            cmd = [
                sys.executable,
                str(fixture.validator_path.resolve()),
                str(fixture.input_path.resolve()),
                *safe_extra_args,
            ]

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
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
