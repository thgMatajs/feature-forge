"""E2E tests — per-host adapter dispatch (Wave 2, Task 2.4).

Valida end-to-end que cada host detectado resolve o adapter certo e produz
o comportamento esperado. Subprocessa ``python -m engine.cli undo`` num
projeto temporário com ENV determinístico por caso.

Hosts cobertos:
  1. ``claude_code`` (CLAUDECODE=1) — stdout marker ``<FORGE_INTENT`` + exit 2.
  2. ``intent_file`` (scrub total, stdin pipe, non-tty) — escreve
     ``forge-pending.json`` + exit 2.
  3. ``opencode`` (OPENCODE_VERSION=1.0) — fallback IntentFileAdapter por
     Veredito B — comportamento idêntico ao intent_file: escreve
     ``forge-pending.json`` + exit 2, sem ``<FORGE_INTENT`` no stdout.

Host TTY: coberto por ``tests/e2e/test_tty_adapter_pty.py`` via PTY real;
NÃO duplicado aqui.

Padrões reusados de ``test_tty_adapter_pty.py``:
  - ``_SCRUB_EXACT`` / ``_SCRUB_PREFIXES`` (env determinístico).
  - ``_scrubbed_env()`` + montagem de PYTHONPATH/FORGE_HOME.
  - ``_scaffold_project()`` com ``workflow-config.yaml`` mínimo.
  - Marker ``e2e`` + ``_RUN_E2E`` skipif por teste.

Por que ``subprocess.run`` (não PTY):
  Os adapters CC/intent_file/opencode não precisam de TTY — o test só
  precisa de stdin piped (non-tty). ``subprocess.run`` com
  ``capture_output=True`` garante ``sys.stdin.isatty() == False`` no filho,
  forçando o branch INTENT_FILE/CC em vez do TTY.

ENV scrub é obrigatório pra todos os casos:
  ``subprocess.Popen`` herda o env do pai, e o pytest normalmente roda
  dentro do Claude Code (CLAUDECODE=1) ou do opencode (OPENCODE_*). Sem o
  scrub, o engine resolveria o adapter errado independente do caso testado.

Exit code canônico:
  ``EXIT_PAUSED = 2`` de ``engine.ui.exit_codes``. Importado diretamente
  no arquivo de teste; se a importação falhar, hardcode 2 com comentário.

Refs:
  - ``docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md`` §4
  - ``engine/host/detect.py`` (precedência config > FORGE_FORCE_INTENT_MODE
    > CLAUDECODE > OPENCODE_* > isatty > intent_file)
  - ``engine/host/adapters/claude_code.py`` (marcador stdout)
  - ``engine/ui/question.py`` linhas 487+ (OPENCODE → IntentFileAdapter)
  - ``engine/utils/paths.py::forge_state_dir``
  - ``engine/ui/exit_codes.py``
  - ``tests/e2e/test_tty_adapter_pty.py`` (referência de padrão)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# ── Gate RUN_E2E ─────────────────────────────────────────────────────────────

_RUN_E2E = os.environ.get("RUN_E2E") == "1"

# Project root: tests/e2e/test_X.py → repo root (dois níveis acima).
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Subcomando de prompt leve — mesma escolha do test_tty_adapter_pty.py.
# ``undo`` chega no menu top-level imediatamente; é o caminho determinístico
# mais simples que dispara um prompt e exit 2 (ou 0 no TTY após cancel).
SUBCOMMAND = "undo"

# Exit code canônico importado da fonte de verdade; fallback hardcode com
# comentário de origem se o módulo não carregar (não deve ocorrer em .venv).
try:
    from engine.ui.exit_codes import EXIT_PAUSED as _EXIT_PAUSED
except ImportError:  # pragma: no cover — fallback de segurança
    _EXIT_PAUSED = 2  # engine/ui/exit_codes.py EXIT_PAUSED

EXIT_PAUSED: int = _EXIT_PAUSED  # 2 per SPEC §8 do drift-1-intent-protocol


# ── Env scrub ────────────────────────────────────────────────────────────────

# Mesmo conjunto de ``test_tty_adapter_pty.py`` — cobre todos os hosts
# agentic que ``detect_host`` reconhece (CLAUDECODE / OPENCODE_* / CODEX* /
# CURSOR_*), conforme MEMORY subprocess-env-scrub.
_SCRUB_EXACT = ("CLAUDECODE", "FORGE_FORCE_INTENT_MODE", "FORGE_FORCE_TTY_MODE")
_SCRUB_PREFIXES = ("OPENCODE_", "CODEX", "CURSOR_")


def _scrubbed_env() -> dict[str, str]:
    """Env limpo de sinais agentic + PYTHONPATH/FORGE_HOME do worktree.

    Ponto de partida compartilhado por todos os casos de teste. Cada
    caso adiciona SOMENTE as variáveis que o seu host exige após chamar
    esta função.
    """
    env = os.environ.copy()
    for name in _SCRUB_EXACT:
        env.pop(name, None)
    for key in list(env.keys()):
        if any(key.startswith(prefix) for prefix in _SCRUB_PREFIXES):
            env.pop(key, None)
    # Garante que ``import engine.*`` funciona no subprocess sem
    # ``pip install -e .``.
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(PROJECT_ROOT) + os.pathsep + existing_pp
        if existing_pp
        else str(PROJECT_ROOT)
    )
    env["FORGE_HOME"] = str(PROJECT_ROOT)
    return env


# ── Scaffold de projeto ──────────────────────────────────────────────────────


def _scaffold_project(tmp_path: Path) -> Path:
    """Layout ``.claude/`` mínimo para que ``find_project_root`` encontre
    um projeto válido (precisa de ``.claude/workflow-config.yaml``).

    Sem ``forge-config.yaml`` com ``host:`` — qualquer override de host
    ali venceria a detecção por env (precedência config > env em
    ``detect_host``), e os testes precisam controlar via env.
    """
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "workflow-config.yaml").write_text("{}\n", encoding="utf-8")
    (claude / "state").mkdir(exist_ok=True)
    return tmp_path


# ── Helpers de execução ──────────────────────────────────────────────────────


def _run_cli(project_root: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    """Executa ``python -m engine.cli undo`` como subprocess non-tty.

    ``capture_output=True`` implica stdin=PIPE + stdout=PIPE + stderr=PIPE,
    garantindo que ``sys.stdin.isatty()`` seja ``False`` no filho — exclui
    o ramo TTY de ``detect_host`` sem necessidade de PTY.

    ``timeout=15`` previne que um subprocess travado pendure o suite inteiro;
    valor generoso pra cobrir inicialização lenta em máquinas de CI.
    """
    return subprocess.run(
        [sys.executable, "-m", "engine.cli", SUBCOMMAND],
        cwd=str(project_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        input="",  # stdin fechado imediatamente — adapter intent-file não lê stdin
    )


# ── Casos ────────────────────────────────────────────────────────────────────


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_dispatch_claude_code(tmp_path):
    """CLAUDECODE=1 → ClaudeCodeAdapter → stdout marker + exit 2.

    Asserts:
      - stdout contém ``<FORGE_INTENT`` (marcador single-line do CC adapter).
      - returncode == EXIT_PAUSED (2) — engine levantou PausedForInputError
        que ``engine.cli`` traduz pra exit 2 conforme SPEC §8.
      - stdout NÃO contém ``forge-pending.json`` mencionado (CC adapter não
        escreve pending; o marcador stdout é o canal nativo).
    """
    project_root = _scaffold_project(tmp_path)
    env = _scrubbed_env()
    env["CLAUDECODE"] = "1"

    result = _run_cli(project_root, env)

    assert "<FORGE_INTENT" in result.stdout, (
        f"ClaudeCodeAdapter deve emitir marcador <FORGE_INTENT no stdout; "
        f"stdout={result.stdout[:400]!r} stderr={result.stderr[:300]!r}"
    )
    assert result.returncode == EXIT_PAUSED, (
        f"Expected EXIT_PAUSED={EXIT_PAUSED}; got {result.returncode}. "
        f"stdout={result.stdout[:400]!r} stderr={result.stderr[:300]!r}"
    )

    # CC adapter nao escreve pending.json — o marcador stdout eh o canal.
    pending = project_root / ".claude" / "forge" / "state" / "forge-pending.json"
    assert not pending.exists(), (
        "ClaudeCodeAdapter nao deve escrever forge-pending.json; "
        f"found {pending}"
    )


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_dispatch_intent_file_fallback(tmp_path):
    """Sem CLAUDECODE/OPENCODE_*/FORGE_FORCE_INTENT_MODE + stdin non-tty
    → detect_host cai em INTENT_FILE (fallback pós-scrub, isatty=False)
    → IntentFileAdapter → escreve forge-pending.json + exit 2.

    Asserts:
      - forge-pending.json existe em ``.claude/forge/state/``.
      - returncode == EXIT_PAUSED (2).
      - stdout NÃO contém ``<FORGE_INTENT`` (esse marcador é só do CC
        adapter; o fallback usa apenas pending file).
    """
    project_root = _scaffold_project(tmp_path)
    env = _scrubbed_env()
    # Nenhuma variável adicional — o scrub já removeu tudo que ativaria
    # CC/opencode/TTY. ``subprocess.run`` garante stdin non-tty.

    result = _run_cli(project_root, env)

    pending = project_root / ".claude" / "forge" / "state" / "forge-pending.json"
    assert pending.exists(), (
        f"IntentFileAdapter deve escrever forge-pending.json em "
        f"{pending}; stdout={result.stdout[:300]!r} "
        f"stderr={result.stderr[:300]!r}"
    )
    assert result.returncode == EXIT_PAUSED, (
        f"Expected EXIT_PAUSED={EXIT_PAUSED}; got {result.returncode}. "
        f"pending.exists={pending.exists()} "
        f"stdout={result.stdout[:300]!r} stderr={result.stderr[:300]!r}"
    )
    assert "<FORGE_INTENT" not in result.stdout, (
        "IntentFileAdapter nao deve emitir marcador CC no stdout; "
        f"stdout={result.stdout[:400]!r}"
    )


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_dispatch_opencode_fallback(tmp_path):
    """OPENCODE_VERSION=1.0 (sem CLAUDECODE) → detect_host retorna OPENCODE
    → registry mapeia OPENCODE para IntentFileAdapter (Veredito B) →
    comportamento idêntico ao intent_file: escreve forge-pending.json +
    exit 2, sem marcador CC no stdout.

    Este teste prova o fallback Veredito B end-to-end — garantia de que o
    mapeamento em ``engine/ui/question.py``
    (``register(HostName.OPENCODE, IntentFileAdapter)``) produz o contrato
    correto sem precisar de um adapter opencode nativo.

    Asserts:
      - forge-pending.json existe em ``.claude/forge/state/``.
      - returncode == EXIT_PAUSED (2).
      - stdout NÃO contém ``<FORGE_INTENT`` — opencode usa pending file,
        não o marcador nativo do CC adapter.
    """
    project_root = _scaffold_project(tmp_path)
    env = _scrubbed_env()
    # OPENCODE_VERSION aciona detect_opencode() → HostName.OPENCODE.
    # CLAUDECODE ja foi removido pelo scrub.
    env["OPENCODE_VERSION"] = "1.0"

    result = _run_cli(project_root, env)

    pending = project_root / ".claude" / "forge" / "state" / "forge-pending.json"
    assert pending.exists(), (
        f"opencode (fallback IntentFileAdapter) deve escrever "
        f"forge-pending.json em {pending}; "
        f"stdout={result.stdout[:300]!r} stderr={result.stderr[:300]!r}"
    )
    assert result.returncode == EXIT_PAUSED, (
        f"Expected EXIT_PAUSED={EXIT_PAUSED}; got {result.returncode}. "
        f"pending.exists={pending.exists()} "
        f"stdout={result.stdout[:300]!r} stderr={result.stderr[:300]!r}"
    )
    assert "<FORGE_INTENT" not in result.stdout, (
        "opencode (Veredito B via IntentFileAdapter) nao deve emitir "
        f"marcador CC; stdout={result.stdout[:400]!r}"
    )
