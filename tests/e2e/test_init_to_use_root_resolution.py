"""E2E regression — ciclo init→uso resolve a raiz pelo marker v1.3+.

Fecha o gap real que o bug de `find_project_root` expunha: após um
`forge init` greenfield (que cria `.claude/forge/forge-config.yaml`, NÃO o
marker legacy `.claude/workflow-config.yaml`), ~12 comandos que chamam
`find_project_root` levantavam `ProjectRootNotFoundError` → "Rode `forge
init` antes." — mesmo o projeto estando inicializado.

Por que não foi pego antes: os testes que precisam de "raiz encontrada"
semeavam o marker legacy à mão; os testes de init paravam no primeiro
pending. Este teste subprocessa um comando real (`forge status`) num
projeto cujo ÚNICO marker é o v1.3+, de um SUBDIR, com ENV scrub.

Antes do fix: status não acha a raiz → exit 1 + "Rode `forge init`".
Depois do fix: status resolve a raiz N níveis acima → exit 0.

Padrões reusados de `tests/e2e/test_per_host_dispatch.py`:
  - `_SCRUB_EXACT` / `_SCRUB_PREFIXES` (env determinístico).
  - `_scrubbed_env()` + PYTHONPATH/FORGE_HOME do worktree.
  - Marker `e2e` + `_RUN_E2E` skipif por teste.

`forge status` é read-only (não dispara prompt/intent), então o ramo de
host adapter não importa aqui — basta stdin non-tty via `subprocess.run`.

Refs:
  - `engine/utils/paths.py::find_project_root` + `_is_project_root`
  - `engine/status.py` (linha 51 — ProjectRootNotFoundError → exit 1)
  - `tests/e2e/test_per_host_dispatch.py` (referência de padrão)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# ── Gate RUN_E2E ─────────────────────────────────────────────────────────────

_RUN_E2E = os.environ.get("RUN_E2E") == "1"

# tests/e2e/test_X.py → repo root (dois níveis acima).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ── Env scrub ────────────────────────────────────────────────────────────────

_SCRUB_EXACT = ("CLAUDECODE", "FORGE_FORCE_INTENT_MODE", "FORGE_FORCE_TTY_MODE")
_SCRUB_PREFIXES = ("OPENCODE_", "CODEX", "CURSOR_")


def _scrubbed_env() -> dict[str, str]:
    """Env limpo de sinais agentic + PYTHONPATH/FORGE_HOME do worktree."""
    env = os.environ.copy()
    for name in _SCRUB_EXACT:
        env.pop(name, None)
    for key in list(env.keys()):
        if any(key.startswith(prefix) for prefix in _SCRUB_PREFIXES):
            env.pop(key, None)
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(PROJECT_ROOT) + os.pathsep + existing_pp
        if existing_pp
        else str(PROJECT_ROOT)
    )
    env["FORGE_HOME"] = str(PROJECT_ROOT)
    return env


# ── Scaffold v1.3+ (marker primário, SEM legacy) ─────────────────────────────


def _scaffold_v13_project(tmp_path: Path) -> Path:
    """Layout que `forge init` greenfield (v1.3+) produz: o sub-namespace
    `.claude/forge/forge-config.yaml`, e DELIBERADAMENTE sem o marker legacy
    `.claude/workflow-config.yaml`.

    Reproduz a condição exata do bug — o ciclo init→uso só resolve a raiz
    pelo marker v1.3+ se `find_project_root` o reconhecer.
    """
    forge_dir = tmp_path / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text("{}\n", encoding="utf-8")
    (forge_dir / "state").mkdir(exist_ok=True)
    # Confirma a precondição: nenhum marker legacy presente.
    assert not (tmp_path / ".claude" / "workflow-config.yaml").exists()
    return tmp_path


# ── Caso ─────────────────────────────────────────────────────────────────────


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_status_resolves_root_from_forge_config_marker(tmp_path):
    """`forge status` de um subdir resolve a raiz pelo marker v1.3+.

    Asserts:
      - returncode == 0 (status encontrou a raiz e renderizou o board).
      - stdout NÃO contém "Rode `forge init`" (a mensagem do
        ProjectRootNotFoundError handler em status.py).
    """
    project_root = _scaffold_v13_project(tmp_path)
    subdir = project_root / "src" / "deep"
    subdir.mkdir(parents=True)

    env = _scrubbed_env()
    result = subprocess.run(
        [sys.executable, "-m", "engine.cli", "status"],
        cwd=str(subdir),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        input="",
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"`forge status` deveria resolver a raiz pelo marker "
        f".claude/forge/forge-config.yaml e sair 0; got {result.returncode}. "
        f"stdout={result.stdout[:500]!r} stderr={result.stderr[:500]!r}"
    )
    assert "forge init" not in combined, (
        "`forge status` não deveria pedir `forge init` num projeto já "
        f"inicializado (v1.3+ marker presente). combined={combined[:500]!r}"
    )
