"""Integration smoke tests — backward-compat preservation across 10 callsite modules (W5.T3).

Cobre AC-8 da spec: os 10 callsite modules do engine seguem funcionando
após o refactor intent-only do chokepoint (``engine/ui/question.py``).
Pra cada módulo, validamos UM cenário mínimo que ou:

  (a) dispara pelo menos um ``question.ask*`` → exit 2 + pending JSON
      bem-formado em ``.claude/forge/state/forge-pending.json``;
  (b) executa um caminho não-interativo (read-only / no-op / erro
      esperado) → exit code documentado, sem pending (ou pending
      claramente ausente).

Ambos cenários são válidos: o foco do AC-8 é "não regrediu". Um módulo
que historicamente sai 0 sem prompt continua saindo 0; um que pausa pra
input agora emite intent ao invés de bloquear no stdin.

Mapping (subcomando registrado em ``engine.cli.COMMANDS`` → módulo):

  init        → engine.init       — greenfield: pipeline atinge primeiro ask
  plan        → engine.plan       — brownfield (config presente): primeiro ask
  implement   → engine.implement  — brownfield: primeiro ask
  verify      → engine.verify     — read-only sem feature: exit 0 sem prompt
  reconfigure → engine.reconfigure— brownfield: primeiro menu
  evolve      → engine.evolve     — sem propostas pendentes: exit 0 sem prompt
  undo        → engine.undo       — brownfield: menu inicial
  memory      → engine.memory_cli — brownfield: menu inicial
  graph       → engine.graph_cli  — sem graph.db: exit 1 sem prompt (mensagem
                                    canônica de "rode forge reconfigure")
  doctor      → engine.doctor     — brownfield: scope ask

NOTE: ``status`` também existe no dispatcher mas NÃO entra no AC-8 — o
spec lista ``init/plan/implement/verify/reconfigure/evolve/undo/
memory_cli/graph_cli/doctor`` como os 10 callsites (``engine.status`` é
read-only stateless e nunca pediu input). Os 10 acima são canônicos.

Refs:
- ``docs/superpowers/specs/drift-1-intent-protocol.md`` §5 + AC-8
- ``docs/superpowers/plans/drift-1-intent-protocol.md`` W5.T3
- ``engine/cli.py::COMMANDS`` (subcomando → handler mapping)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUBPROCESS_TIMEOUT = 60  # generous — `init` greenfield runs full discovery


# ── Project scaffolding helpers ──────────────────────────────────────────────


def _scaffold_brownfield(tmp_path: Path) -> Path:
    """Project root with minimal ``.claude/workflow-config.yaml``.

    Empty mapping (``{}``) is enough for the YAML parsers + downstream
    ``read_yaml_or_default``. Each subcommand picks defaults from
    schemas + presets when fields are missing, so this fixture is
    deliberately spartan — exercises the "config loaded, no overrides"
    path without seeding stale state.
    """
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "workflow-config.yaml").write_text("{}\n", encoding="utf-8")
    forge = claude / "forge"
    forge.mkdir(parents=True, exist_ok=True)
    # Pin host=intent-file so subprocess emits via on-disk pending JSON
    # rather than Claude Code stdout marker (pytest inherits CLAUDECODE=1).
    (forge / "forge-config.yaml").write_text(
        "host: intent-file\n", encoding="utf-8"
    )
    (forge / "state").mkdir(exist_ok=True)
    return tmp_path


def _scaffold_greenfield(tmp_path: Path) -> Path:
    """Project root WITHOUT ``.claude/workflow-config.yaml`` — for ``init``.

    Creates ``.git/`` so ``_is_git_repo`` is happy (without it, ``init``
    prints a warning but continues — keeping the smoke tighter to avoid
    that extra branch).
    """
    (tmp_path / ".git").mkdir()
    return tmp_path


# ── Subprocess runner ────────────────────────────────────────────────────────


def _run_engine(
    project_root: Path,
    subcommand: str,
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``python -m engine.cli <subcommand>`` from ``project_root``.

    ``stdin=DEVNULL`` keeps the dispatcher in non-TTY territory; intent
    mode lights up on its own. ``PYTHONPATH`` includes the worktree so
    the engine module imports resolve regardless of pytest's path
    munging.
    """
    env = os.environ.copy()
    pythonpath = str(PROJECT_ROOT)
    env["PYTHONPATH"] = (
        pythonpath + os.pathsep + env["PYTHONPATH"]
        if env.get("PYTHONPATH")
        else pythonpath
    )
    env["FORGE_HOME"] = str(PROJECT_ROOT)
    # Strip agentic-host env hints so detect_host falls back to intent-file
    # (the on-disk DRIFT-1 protocol). Pytest inherits CLAUDECODE=1 from the
    # Claude Code session; without this strip the subprocess would emit
    # `<FORGE_INTENT>` stdout markers instead of writing the pending JSON.
    for var in (
        "CLAUDECODE",
        "CURSOR_AGENT",
    ):
        env.pop(var, None)
    for var in list(env.keys()):
        if var.startswith(("OPENCODE_", "CODEX", "CURSOR_")):
            env.pop(var, None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "engine.cli", subcommand],
        cwd=str(project_root),
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
    )


def _pending_path(project_root: Path) -> Path:
    return project_root / ".claude" / "forge" / "state" / "forge-pending.json"


def _assert_pending_schema(project_root: Path) -> dict:
    """Read pending JSON and validate canonical schema fields (SPEC §2.1)."""
    path = _pending_path(project_root)
    assert path.is_file(), f"expected pending at {path}"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload.get("schema-version") == 1, payload
    assert isinstance(payload.get("intent-id"), str), payload
    assert payload.get("kind") in (
        "ask",
        "ask_text",
        "ask_multi",
        "confirm",
        "ask_three_paths",
    ), payload.get("kind")
    assert isinstance(payload.get("question"), str) and payload["question"], payload
    assert isinstance(payload.get("allow-pause"), bool), payload
    return payload


# ── Module-by-module smokes ──────────────────────────────────────────────────


def test_smoke_init_greenfield_emits_intent(tmp_path):
    """``init`` em greenfield: pipeline alcança o primeiro ``ask`` (preset
    confirmation) e pausa via intent protocol. exit 2 + pending válido.
    """
    project_root = _scaffold_greenfield(tmp_path)
    result = _run_engine(project_root, "init")

    assert result.returncode == 2, (
        f"init greenfield: expected exit 2, got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    payload = _assert_pending_schema(project_root)
    assert payload.get("command") == "init", payload


def test_smoke_init_brownfield_aborts_no_pending(tmp_path):
    """``init`` em brownfield (config presente) renderiza 3-caminhos
    block e ABORTA SEM emitir pending. C3 EXIT-2-COLLISION: o abort não é
    pausa — exit 2 ficou reservado pra pausa, então este caminho colapsou em
    exit 1 + tag [FORGE-ERR:ABORTED].
    """
    project_root = _scaffold_brownfield(tmp_path)
    result = _run_engine(project_root, "init")

    assert result.returncode == 1, (
        f"init brownfield: expected exit 1 (ABORTED), got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    assert "[FORGE-ERR:ABORTED]" in result.stderr, (
        f"init brownfield abort deve carregar a tag ABORTED; stderr={result.stderr!r}"
    )
    assert not _pending_path(project_root).exists(), (
        "init brownfield should NOT emit pending — it short-circuits "
        "to the 3-caminhos block before any question.ask"
    )


def test_smoke_plan_emits_intent(tmp_path):
    """``plan`` em brownfield: pausa no primeiro prompt. exit 2 + pending."""
    project_root = _scaffold_brownfield(tmp_path)
    result = _run_engine(project_root, "plan")

    assert result.returncode == 2, (
        f"plan: expected exit 2, got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    payload = _assert_pending_schema(project_root)
    assert payload.get("command") == "plan", payload


def test_smoke_implement_emits_intent(tmp_path):
    """``implement`` em brownfield: pausa no primeiro prompt. exit 2 + pending."""
    project_root = _scaffold_brownfield(tmp_path)
    result = _run_engine(project_root, "implement")

    assert result.returncode == 2, (
        f"implement: expected exit 2, got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    payload = _assert_pending_schema(project_root)
    assert payload.get("command") == "implement", payload


def test_smoke_verify_runs_clean(tmp_path):
    """``verify`` em brownfield sem feature: read-only, exit 0 sem
    prompt. AC-8 contract = "não regrediu"; ``verify`` historicamente
    nunca pediu input no scope vazio, segue assim.
    """
    project_root = _scaffold_brownfield(tmp_path)
    result = _run_engine(project_root, "verify")

    assert result.returncode == 0, (
        f"verify: expected exit 0, got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    assert not _pending_path(project_root).exists(), (
        "verify should NOT emit pending in the no-feature read-only path"
    )


def test_smoke_reconfigure_emits_intent(tmp_path):
    """``reconfigure`` em brownfield: pausa no menu de categorias. exit
    2 + pending.
    """
    project_root = _scaffold_brownfield(tmp_path)
    result = _run_engine(project_root, "reconfigure")

    assert result.returncode == 2, (
        f"reconfigure: expected exit 2, got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    payload = _assert_pending_schema(project_root)
    assert payload.get("command") == "reconfigure", payload


def test_smoke_evolve_no_proposals_exits_clean(tmp_path):
    """``evolve`` sem propostas pendentes: exit 0 sem prompt. Mesmo
    contract de ``verify`` — não-regressão de comportamento pré-DRIFT-1.
    """
    project_root = _scaffold_brownfield(tmp_path)
    result = _run_engine(project_root, "evolve")

    assert result.returncode == 0, (
        f"evolve: expected exit 0, got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    assert not _pending_path(project_root).exists()


def test_smoke_undo_emits_intent(tmp_path):
    """``undo`` em brownfield: pausa no menu inicial. exit 2 + pending."""
    project_root = _scaffold_brownfield(tmp_path)
    result = _run_engine(project_root, "undo")

    assert result.returncode == 2, (
        f"undo: expected exit 2, got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    payload = _assert_pending_schema(project_root)
    assert payload.get("command") == "undo", payload


def test_smoke_memory_emits_intent(tmp_path):
    """``memory`` em brownfield: pausa no menu inicial. exit 2 + pending.

    NOTE: o subcomando registrado em ``engine.cli.COMMANDS`` é
    ``memory`` (mapeia pra ``engine.memory_cli``). O dispatch via
    ``python -m engine.cli memory`` é o caminho canônico.
    """
    project_root = _scaffold_brownfield(tmp_path)
    result = _run_engine(project_root, "memory")

    assert result.returncode == 2, (
        f"memory: expected exit 2, got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    payload = _assert_pending_schema(project_root)
    assert payload.get("command") == "memory", payload


def test_smoke_graph_no_db_exits_1(tmp_path):
    """``graph`` sem ``graph.db``: módulo emite mensagem mentor-calmo
    pedindo ``forge reconfigure → rebuild graph`` e sai com exit 1. Não
    é um prompt — é um erro previsível pré-DRIFT-1, preservado.

    Smoke aceita exit 1 OU exit 2 (caso o módulo evolua pra emitir um
    intent quando o db falta). Pending pode ou não existir; se existir,
    schema deve ser válido.
    """
    project_root = _scaffold_brownfield(tmp_path)
    result = _run_engine(project_root, "graph")

    assert result.returncode in (1, 2), (
        f"graph (no db): expected exit 1 or 2, got {result.returncode}; "
        f"stderr={result.stderr!r}; stdout={result.stdout!r}"
    )
    if result.returncode == 2:
        # If the module did emit a pending, the schema must hold.
        _assert_pending_schema(project_root)


def test_smoke_doctor_emits_intent(tmp_path):
    """``doctor`` em brownfield: pausa no ``scope`` ask. exit 2 + pending."""
    project_root = _scaffold_brownfield(tmp_path)
    result = _run_engine(project_root, "doctor")

    assert result.returncode == 2, (
        f"doctor: expected exit 2, got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    payload = _assert_pending_schema(project_root)
    assert payload.get("command") == "doctor", payload
