"""Unit test — suprimir WARN de cleanup quando project root ausente (Bug U2 residual).

Verifica que ``forge graph`` (e outros comandos) em dir pre-init nao emitem
``[WARN] forge: failed to clear intent log on exit`` no stderr.

Antes do fix: o ``finally`` de ``cli.main()`` chama ``find_project_root()``
que levanta ``ProjectRootNotFoundError``; o except-Exception generico captura
e escreve o WARN — ruido confuso logo apos a mensagem limpa de nao-inicializado.

Apos o fix: ``ProjectRootNotFoundError`` e capturado silenciosamente no finally
(nao ha intent-log a limpar em dir pre-init; WARN suprimido).

Refs:
  - engine/cli.py finally block (W7-fix lifecycle clear)
  - Bug U2 (WARN em --help path ja corrigido; este cobre pre-init commands)
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


def test_pre_init_command_no_warn_noise(tmp_path: Path) -> None:
    """``forge graph`` em dir pre-init nao deve emitir ``[WARN]...clear intent log``.

    O diretorio temporario e uma raiz pre-init (sem ``.claude/workflow-config.yaml``).
    O handler ``graph`` (skip-list de bootstrap) vai tentar resolver o project root,
    falhar, e emitir a mensagem canonica de nao-inicializado. O WARN do finally de
    cleanup NAO deve aparecer.

    Assertions:
    - exit code 1 (pre-init normalizado pelo Bug U1 fix).
    - ``failed to clear intent log`` ausente em stderr.
    - ``[WARN]`` ausente em stderr.
    """
    r = subprocess.run(
        [str(FORGE_BIN), "graph"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=_clean_env(),
    )

    assert r.returncode == 1, (
        f"`forge graph` pre-init retornou {r.returncode} (esperava 1).\n"
        f"stderr: {r.stderr!r}\nstdout: {r.stdout!r}"
    )
    assert "failed to clear intent log" not in r.stderr.lower(), (
        f"`forge graph` pre-init emitiu WARN de cleanup.\n"
        f"stderr: {r.stderr!r}"
    )
    assert "[WARN]" not in r.stderr, (
        f"`forge graph` pre-init emitiu [WARN] no stderr.\n"
        f"stderr: {r.stderr!r}"
    )
