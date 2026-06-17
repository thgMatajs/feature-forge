"""Shared helpers for ``tests/e2e/`` subprocess-driven CLI tests.

Why this module exists:

- DET-6 W7 introduced ``backend.<axis>.<platform>`` cell wiring through
  ``forge init`` (brownfield via composer, greenfield via bundle picker)
  and ``forge reconfigure -> backend``. Integration tests
  (``tests/integration/test_init_*_multi_axis.py``,
  ``tests/integration/test_reconfigure_multi_axis.py``) cover the handler
  shape with direct function calls + monkeypatched ``question.*``. Those
  tests are authoritative for handler logic but bypass the CLI entry,
  the bash dispatcher, and the file-based intent protocol.
- The pre-W7 e2e stubs (``test_e2e_brownfield_init.py``,
  ``test_e2e_greenfield_init.py``) only exercised ``forge init help`` /
  ``--help`` / ``--version`` / unknown-arg paths. They proved nothing
  about the W7.4 wiring contract — subprocess CLI emitting valid
  pending JSON when a question is reached.
- These helpers let the new e2e tests drive the bash dispatcher with the
  same intent-protocol contract a Claude Code host would use: invoke,
  read pending, write response, re-invoke.

Anti-goals (deliberately not covered here):

- Driving ``forge init`` end-to-end through workflow-config creation.
  Init has 16+ interactive steps; a hard-coded response sequence is too
  brittle (mirrors the rationale in
  ``test_e2e_resume_after_pause.py``). Integration tests cover the
  handler logic; e2e covers wiring + intent-protocol contract.
- Reproducing the Claude Code host's full ``AskUserQuestion`` UX.

Refs:
- ``docs/schemas/intent-protocol.md`` (response schema)
- ``docs/superpowers/specs/drift-1-intent-protocol.md`` §2/§3
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

# Paths — resolved once at import time. ``REPO_ROOT`` is the worktree root
# (the directory containing ``bin/``, ``engine/``, ``cards/``). ``FORGE_BIN``
# is the canonical bash dispatcher; subprocess tests invoke it directly so
# the dispatcher's PYTHONPATH wiring is exercised too (not just the Python
# ``-m engine.cli`` path that the older e2e stubs used).
REPO_ROOT = Path(__file__).resolve().parents[2]
FORGE_BIN = REPO_ROOT / "bin" / "forge"


# ── Env scrub ─────────────────────────────────────────────────────────────────
#
# Variáveis que fariam ``detect_host`` resolver um adapter agentic
# (ClaudeCodeAdapter, OpenCodeAdapter, etc.) em vez do caminho determinístico
# não-agentic (IntentFileAdapter via stdin piped / non-tty). Quando a e2e
# lane roda DENTRO de uma sessão Claude Code/opencode, CLAUDECODE=1 (e/ou
# OPENCODE_* / CODEX* / CURSOR_*) está presente no env do pytest e seria
# herdado pelo subprocess ``bin/forge`` sem o scrub, forçando o engine pra
# emitir o marcador ``<FORGE_INTENT/>`` no stdout em vez de escrever
# ``forge-pending.json`` — quebrando os 4 testes que verificam o pending file.
#
# Mesma lista usada em ``test_tty_adapter_pty.py`` e
# ``test_per_host_dispatch.py`` (Mandamento #3 — reuse antes de criar).
# Testes que precisam exercitar um host agentic específico SETAM a variável
# DEPOIS de chamar ``env_with_forge_home()`` (override local, não afeta o
# default scrubado).

_SCRUB_EXACT = ("CLAUDECODE", "FORGE_FORCE_INTENT_MODE", "FORGE_FORCE_TTY_MODE")
_SCRUB_PREFIXES = ("OPENCODE_", "CODEX", "CURSOR_")


def _scrub_agentic_env(env: dict[str, str]) -> None:
    """Remove sinais agentic do env dict in-place.

    Garante que ``detect_host`` não resolva um adapter agentic quando a
    suite roda dentro de Claude Code / opencode / codex / cursor. O scrub
    é feito in-place (mutação direta) para que o chamador possa continuar
    adicionando variáveis após a chamada.
    """
    for name in _SCRUB_EXACT:
        env.pop(name, None)
    for key in list(env.keys()):
        if any(key.startswith(prefix) for prefix in _SCRUB_PREFIXES):
            env.pop(key, None)


def env_with_forge_home() -> dict[str, str]:
    """Build an env dict for the subprocess with ``FORGE_HOME`` exported.

    Mirrors the pattern used by ``test_qa_cli_smoke.py`` /
    ``test_e2e_greenfield_init.py``: the bash dispatcher infers
    ``FORGE_HOME`` from its own path normally, but we export it explicitly
    to guard against symlinked invocations from CI. ``PYTHONPATH`` is
    chained so any helper that bypasses ``bin/forge`` and uses
    ``python -m engine.cli`` still resolves ``engine.*`` without
    ``pip install -e .``.

    Agentic env vars (``CLAUDECODE``, ``OPENCODE_*``, ``CODEX*``,
    ``CURSOR_*``, ``FORGE_FORCE_INTENT_MODE``, ``FORGE_FORCE_TTY_MODE``)
    are scrubbed so that ``detect_host`` always falls through to the
    deterministic non-agentic path (``IntentFileAdapter`` via piped stdin)
    regardless of the host environment running the test suite. Tests that
    need to exercise a specific agentic host must set the relevant variable
    on the returned dict after this call — the scrub is a default, not a
    prohibition.
    """
    env = os.environ.copy()
    _scrub_agentic_env(env)
    env["FORGE_HOME"] = str(REPO_ROOT)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def scaffold_minimal_project(
    project_root: Path,
    *,
    with_firebase_signals: bool = False,
) -> Path:
    """Create the minimal layout ``forge init`` expects.

    Args:
        project_root: Directory to seed. Caller owns its creation; we
            only add ``.git/`` (so ``_is_git_repo`` passes) and, optionally,
            files that trigger the brownfield path.
        with_firebase_signals: When ``True``, materialize the same signals
            used by ``tests/integration/test_init_brownfield_multi_axis.py``
            so the composer fires the firebase-auth detection above the
            0.50 threshold. When ``False``, the project stays empty —
            zero signals, greenfield path.

    Returns:
        The same ``project_root`` (for fluent chaining).

    Notes:
        We do NOT pre-create ``.claude/workflow-config.yaml``. Init bails
        out early with a 3-paths block if config already exists (see
        ``engine/init.py:1026``), and the goal here is to exercise the
        actual greeting → discovery → preset confirmation flow that the
        new e2e tests assert on.
    """
    (project_root / ".git").mkdir(exist_ok=True)

    if with_firebase_signals:
        # Same signal set as the integration test
        # ``_build_uniform_firebase_project`` — 0.20 + 0.20 + 0.35 = 0.75,
        # well above the 0.50 threshold the composer applies for
        # firebase-auth detection.
        app_dir = project_root / "app"
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / "google-services.json").write_text(
            '{"project_info": {"project_id": "e2e-test"}}',
            encoding="utf-8",
        )
        (app_dir / "build.gradle.kts").write_text(
            'plugins { id("com.android.application") }\n'
            "\n"
            "dependencies {\n"
            '    implementation("com.google.firebase:firebase-auth:22.0.0")\n'
            "}\n",
            encoding="utf-8",
        )

        ios_dir = project_root / "ios"
        ios_dir.mkdir(parents=True, exist_ok=True)
        (ios_dir / "GoogleService-Info.plist").write_text(
            '<?xml version="1.0"?><plist></plist>',
            encoding="utf-8",
        )

    return project_root


def run_forge(
    cmd_args: list[str],
    *,
    cwd: Path,
    timeout: float = 60,
) -> subprocess.CompletedProcess:
    """Invoke ``bin/forge`` as a subprocess and return the result.

    The caller decides what to do with the exit code — we never assert
    here. Exit 2 means the engine emitted a pending intent (clean pause
    per DRIFT-1 §8); exit 0/1/130 mean the run completed / errored /
    cancelled respectively.

    ``capture_output=True`` keeps stdout/stderr out of the pytest
    transcript by default; the test prints them on assertion failure for
    diagnostic value.
    """
    return subprocess.run(
        [str(FORGE_BIN), *cmd_args],
        cwd=cwd,
        env=env_with_forge_home(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def read_pending(project_root: Path) -> dict[str, Any] | None:
    """Read ``.claude/state/forge-pending.json`` if present.

    Returns ``None`` when the engine has not paused (no pending file
    written yet, or the engine consumed and cleared after a successful
    run). Otherwise returns the decoded payload.
    """
    pending_path = project_root / ".claude" / "forge" / "state" / "forge-pending.json"
    if not pending_path.is_file():
        return None
    return json.loads(pending_path.read_text(encoding="utf-8"))


def write_response(
    project_root: Path,
    *,
    intent_id: str,
    kind: str,
    value: Any,
) -> None:
    """Write ``.claude/state/forge-response.json`` matching the contract.

    Schema fields per ``docs/schemas/intent-protocol.md`` §"Response file":

    - ``schema-version: 1``
    - ``intent-id``: must match the pending the engine emitted
    - ``kind``: echo the pending's ``kind``
    - ``value``: ``str`` (ask, ask_text, ask_three_paths) | ``list[str]``
      (ask_multi) | ``bool`` (confirm)
    - ``answered-at``: ISO-8601 UTC (a fixed string is fine for tests)
    """
    state_dir = project_root / ".claude" / "forge" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    response = {
        "schema-version": 1,
        "intent-id": intent_id,
        "kind": kind,
        "value": value,
        "answered-at": "2026-06-12T12:00:00Z",
    }
    (state_dir / "forge-response.json").write_text(
        json.dumps(response),
        encoding="utf-8",
    )


def clear_response(project_root: Path) -> None:
    """Delete ``.claude/state/forge-response.json`` if present.

    Why this exists: ``forge init`` saves a checkpoint at Step 2 (line
    ``engine/init.py:1120``) BEFORE the first question at Step 4. So
    cycle 1 (re-invocation after writing a response to the Step 4 prompt)
    always hits the checkpoint-resume gate (Step 1, lines 1054-1115) and
    emits a NEW ``ask("Resume de init pendente?")`` intent. The engine
    then reads the stale response file (from Step 4's intent-id) at the
    Resume gate's ``ask()``, hits ``IntentMismatchError``, and exits 1
    — without ever clearing the stale response.

    Real Claude Code hosts do not stumble on this because they only ever
    write responses against the LATEST pending the engine emitted. In a
    test driver, we have to coordinate manually: before re-invoking when
    we know the engine will encounter a different question first,
    explicitly clear the stale response.
    """
    response_path = project_root / ".claude" / "forge" / "state" / "forge-response.json"
    response_path.unlink(missing_ok=True)


def drive_intent_loop(
    cmd_args: list[str],
    *,
    cwd: Path,
    response_provider,
    max_cycles: int = 12,
    timeout: float = 60,
) -> subprocess.CompletedProcess:
    """Drive a multi-cycle invoke→pending→response→re-invoke loop.

    Each cycle:
      1. Invoke ``forge <cmd_args>`` in ``cwd`` and capture the result.
      2. If exit 0/1/130 → terminal; return the result.
      3. If exit 2 with no pending → unexpected; return the result.
      4. Otherwise read the latest pending, call ``response_provider(pending)``
         to obtain a value, write the response file, and loop.

    ``response_provider`` is a callable ``(pending_dict) -> value`` that
    returns the answer for the pending. Test cases override it to respond
    to specific question shapes (e.g. select ``"sim"`` for the preset
    confirmation, ``"discard"`` for the resume gate, etc.). Returning
    ``None`` from the provider signals "stop driving, return the current
    state" — useful when the test wants to assert on a specific pending
    mid-loop.

    After each cycle, the previous response file is cleared explicitly
    BEFORE the next invocation, so the engine's read_response never
    fights a stale response when the new pending's intent-id differs
    from the one we just answered.

    The ``max_cycles`` ceiling prevents runaway loops if the engine keeps
    asking forever (would be a real bug, but the test should fail loud
    instead of hanging). Mismatch-recovery iterations (exit 1 + "mismatch"
    in stderr) are NOT counted against ``max_cycles`` — they are automatic
    housekeeping, not genuine question-answer cycles. The ceiling is capped
    separately at ``max_cycles * 3`` total iterations (including recoveries)
    as a safety net against truly pathological loops.
    """
    last_result: subprocess.CompletedProcess | None = None
    _response_cycles = 0
    _total_iters = 0
    _max_total = max_cycles * 3  # safety cap including recovery iterations

    while _response_cycles < max_cycles and _total_iters < _max_total:
        _total_iters += 1
        result = subprocess.run(
            [str(FORGE_BIN), *cmd_args],
            cwd=cwd,
            env=env_with_forge_home(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        last_result = result

        # Exit 1 com "mismatch" no stderr = engine encontrou um gate
        # diferente do prompt cuja resposta gravamos no ciclo anterior
        # (cenário típico em ``forge init``: o checkpoint-resume gate
        # de Step 1 ``ask()`` antes do prompt onde paramos no ciclo
        # anterior). Recovery: limpa AMBOS pending + response stale.
        # O próximo ciclo vai re-rodar do topo, emit novo pending pro
        # gate que de fato bloqueia (Resume), exit 2 limpo, e o loop
        # pega a partir daí. Pending stale aqui é seguro de descartar:
        # o engine não consumiu ele neste ciclo (mismatch raised antes
        # do ``_emit_pending_and_raise``), e o próximo ciclo vai
        # re-emitir o pending da pergunta correta.
        # Recovery iterations do NOT consume the ``max_cycles`` budget —
        # they are housekeeping, not question-answer turns.
        if (
            result.returncode == 1
            and "mismatch" in (result.stderr or "").lower()
        ):
            clear_response(cwd)
            pending_path = cwd / ".claude" / "forge" / "state" / "forge-pending.json"
            pending_path.unlink(missing_ok=True)
            continue

        if result.returncode != 2:
            # Terminal — return whatever the engine exited with.
            return result

        pending = read_pending(cwd)
        if pending is None:
            # Exit 2 sem pending na pasta: contrato quebrado.
            return result

        value = response_provider(pending)
        if value is None:
            # Test pediu stop — devolve estado atual.
            return result

        # Limpa stale response do ciclo anterior antes de escrever o novo.
        clear_response(cwd)
        write_response(
            cwd,
            intent_id=pending["intent-id"],
            kind=pending["kind"],
            value=value,
        )
        _response_cycles += 1

    # Esgotou max_cycles (ou safety cap) sem terminar — devolve estado atual
    # pra test inspecionar (provavelmente vai falhar com asserção clara).
    assert last_result is not None  # ao menos 1 iteração executou
    return last_result
