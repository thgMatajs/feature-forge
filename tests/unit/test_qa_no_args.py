"""Unit test — forge qa sem args (Bug U4).

Verifica que ``forge qa`` sem scope target imprime 3-caminhos mentor-calmo
no stdout e sai sem traceback (exit 0 ou exit 4).

Antes do fix: ``resolve_scope("")`` levanta ``ValueError`` que nao e capturado
por ``except ScopeError``, propagando traceback.

Apos o fix: guard em ``_qa_run`` (ou em ``run_qa``) detecta raw_target vazio
antes de chamar ``resolve_scope``, imprime 3-caminhos, retorna 0.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Canonical repo root (bin/forge lives here).
REPO_ROOT = Path(__file__).resolve().parents[2]
FORGE_BIN = REPO_ROOT / "bin" / "forge"

_SCRUB_EXACT = ("CLAUDECODE", "FORGE_FORCE_INTENT_MODE", "FORGE_FORCE_TTY_MODE")
_SCRUB_PREFIXES = ("OPENCODE_", "CODEX", "CURSOR_")


def _clean_env() -> dict[str, str]:
    """Scrubbed env with FORGE_HOME + PYTHONPATH wired to repo."""
    env = os.environ.copy()
    for key in list(env.keys()):
        if key in _SCRUB_EXACT or any(key.startswith(p) for p in _SCRUB_PREFIXES):
            env.pop(key)
    env["FORGE_HOME"] = str(REPO_ROOT)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def test_forge_qa_no_args_no_traceback(tmp_path: Path) -> None:
    """``forge qa`` sem args nao deve emitir traceback nem ValueError.

    Setup: diretorio temporario com ``.git/`` e ``.claude/workflow-config.yaml``
    minimo (qa.enabled: true) para que o handler qa seja alcancado (sem
    ProjectRootNotFoundError). O guard de args deve disparar ANTES do
    resolve_scope, entao a ausencia de features nao importa.

    Assertions:
    - ``Traceback`` ausente em stderr.
    - ``ValueError`` ausente em stderr.
    - ``caminhos`` ou ``caminho`` presente em stdout (mensagem 3-caminhos).
    - exit code em {0, 4} (informativo/nao-fatal).
    """
    # Projeto minimo: .git/ + workflow-config com qa habilitado.
    (tmp_path / ".git").mkdir()
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "workflow-config.yaml").write_text(
        "qa:\n  enabled: true\n", encoding="utf-8"
    )

    r = subprocess.run(
        [str(FORGE_BIN), "qa"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=_clean_env(),
    )

    assert "Traceback" not in r.stderr, (
        f"forge qa sem args emitiu traceback no stderr.\nstderr: {r.stderr!r}"
    )
    assert "ValueError" not in r.stderr, (
        f"forge qa sem args emitiu ValueError no stderr.\nstderr: {r.stderr!r}"
    )
    assert "caminhos" in r.stdout.lower() or "caminho" in r.stdout.lower(), (
        f"forge qa sem args nao emitiu mensagem 3-caminhos no stdout.\n"
        f"stdout: {r.stdout!r}\nstderr: {r.stderr!r}"
    )
    assert r.returncode in (0, 4), (
        f"forge qa sem args retornou {r.returncode} (esperava 0 ou 4).\n"
        f"stdout: {r.stdout!r}\nstderr: {r.stderr!r}"
    )
