"""E2E tests — DRIFT-1 ``tty_bridge`` subprocess loop via real PTY.

Cobre AC-3 (TTY mode behaviour parity) e AC-5 (Ctrl+C + pause-token
semantics) da spec, driving the bridge through a pseudo-terminal so the
exact subprocess loop the dispatcher invokes for real-terminal users is
exercised end-to-end.

Why ``pty`` stdlib (not ``pexpect``):
  - Decision 22 — no new runtime deps in feature-forge.
  - ``pty.fork()`` + ``select.select`` covers what we need (read-until-
    pattern + signal injection) without dragging an external library.
  - The plan W5.T2 explicitly preserves the "no new dep unless stdlib
    cannot reach the case" stance.

Strategy:
  - Each test spawns ``python -m engine.ui.tty_bridge engine.cli undo``
    in a child of ``pty.fork()`` so the bridge sees a real PTY on
    stdin/stdout — the conditions under which the dispatcher would route
    here.
  - The ``undo`` subcommand reaches ``question.ask`` quickly (line 581
    of ``engine/undo.py``) with the cancel option ``"c"`` exposed in the
    menu, mirroring the W5.T1 integration tests.
  - Each test wraps the body in try/finally so a hung child is always
    reaped — PTY tests are notoriously easy to leak.

Marker: ``e2e`` — excluded from the rapid lane by default.

Refs:
  - ``docs/superpowers/specs/drift-1-intent-protocol.md`` §6, §7, §8,
    AC-3, AC-5
  - ``docs/superpowers/plans/drift-1-intent-protocol.md`` W5.T2
  - ``engine/ui/tty_bridge.py`` (subprocess loop + pause-token handling)
  - ``engine/ui/question.py`` (``_PAUSE_TOKENS``, ``UserPausedError``)
  - ``engine/cli.py`` (exit code ladder — 0 clean, 2 paused, 130 cancel)
"""

from __future__ import annotations

import os
import pty
import select
import signal
import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="pty.fork() unavailable on Windows; tty_bridge tested via mock-based unit tests",
    ),
]


# Project root resolves from this file: tests/e2e/test_X.py → repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Subcommand mirrored from W5.T1 (lightweight prompt path).
SUBCOMMAND = "undo"

# Bridge bootstrap + first prompt completes in ~2s on the hot path; the
# two per-call ceilings below cap how long any single read or waitpid
# poll can hang the test if the subprocess wedges. ``pytest-timeout`` is
# not in the dev deps, so these inline budgets are the safety net.
READ_PROMPT_TIMEOUT_S = 8.0
EXIT_WAIT_TIMEOUT_S = 6.0


# ── Helpers ──────────────────────────────────────────────────────────────────


def _scaffold_project(tmp_path: Path) -> Path:
    """Mirror W5.T1: minimal ``.claude/`` layout for ``find_project_root``."""
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "workflow-config.yaml").write_text("{}\n", encoding="utf-8")
    (claude / "state").mkdir(exist_ok=True)
    return tmp_path


def _spawn_bridge(project_root: Path) -> tuple[int, int]:
    """Fork a child running ``python -m engine.ui.tty_bridge engine.cli undo``.

    Returns ``(pid, master_fd)``. The master fd reads what the child
    writes to its (pty-backed) stdout and writes flow back to the child's
    stdin. The child's cwd is set to ``project_root`` so the bridge and
    the engine subprocess it spawns both resolve the same ``.claude/``.
    """
    try:
        pid, fd = pty.fork()
    except OSError as exc:
        pytest.skip(f"pty.fork() unavailable in this environment: {exc!r}")

    if pid == 0:  # child
        try:
            os.chdir(str(project_root))
            env = os.environ.copy()
            # Ensure the worktree is on sys.path so ``-m engine.ui.tty_bridge``
            # resolves regardless of where pytest was launched from.
            pythonpath = str(PROJECT_ROOT)
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                pythonpath + os.pathsep + existing if existing else pythonpath
            )
            env["FORGE_HOME"] = str(PROJECT_ROOT)
            # Strip any forced-intent override that might be leaking from
            # the parent — we want the bridge to drive the engine, not
            # the engine to think it's in intent-only mode.
            env.pop("FORGE_FORCE_INTENT_MODE", None)
            env.pop("CLAUDECODE", None)
            os.execvpe(
                sys.executable,
                [
                    sys.executable,
                    "-m",
                    "engine.ui.tty_bridge",
                    "engine.cli",
                    SUBCOMMAND,
                ],
                env,
            )
        except Exception as exc:  # pragma: no cover — child-side error path
            # If exec fails, write a diagnostic and exit non-zero so the
            # parent can surface it. We cannot use pytest here.
            os.write(2, f"child exec failed: {exc!r}\n".encode("utf-8"))
            os._exit(127)
    return pid, fd


def _read_until(fd: int, *, timeout: float, until: bytes) -> bytes:
    """Read from the PTY master ``fd`` until ``until`` appears or timeout.

    Bounded by ``select.select`` with a per-iteration cap so a stuck
    subprocess never hangs the test indefinitely. Raises ``TimeoutError``
    on timeout (callers wrap in try/finally to guarantee cleanup).
    """
    buf = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        rlist, _, _ = select.select([fd], [], [], min(remaining, 0.5))
        if not rlist:
            continue
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            # PTY closed (child exited before pattern arrived) — surface
            # whatever we got so the assertion error is informative.
            break
        if not chunk:
            break
        buf += chunk
        if until in buf:
            return buf
    raise TimeoutError(
        f"PTY read timeout after {timeout}s waiting for {until!r}; "
        f"buf so far={buf[:400]!r}"
    )


def _wait_for_exit(pid: int, *, timeout: float) -> int:
    """Block until ``pid`` exits, returning the raw waitpid status.

    Bounded poll loop — ``os.waitpid(pid, os.WNOHANG)`` returns ``(0, 0)``
    when the child is still running. Raises ``TimeoutError`` so the
    cleanup path can ``SIGKILL`` and reap.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        waited_pid, status = os.waitpid(pid, os.WNOHANG)
        if waited_pid == pid:
            return status
        time.sleep(0.05)
    raise TimeoutError(f"child pid={pid} did not exit within {timeout}s")


def _kill_and_reap(pid: int, fd: int) -> None:
    """Best-effort cleanup: kill the child if alive, close the master fd."""
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        os.close(fd)
    except OSError:
        pass
    # Drain the zombie if still pending. Bounded — never block on a
    # process the kernel has already cleaned up.
    for _ in range(20):
        try:
            waited_pid, _ = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return
        if waited_pid == pid:
            return
        time.sleep(0.05)


def _exit_status_code(status: int) -> int:
    """Translate a raw ``waitpid`` status into the human exit code.

    Handles both clean exits (``os.WIFEXITED``) and signal-terminated
    children (``os.WIFSIGNALED``). For signals, we return the canonical
    Unix convention of ``128 + signum`` so SIGINT shows up as ``130`` —
    matching the engine's ``return 130`` ladder when it catches
    ``KeyboardInterrupt`` itself.
    """
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return -1  # unreachable in practice, surfaces as a clear assertion failure


# ── AC-3 — TTY mode renders prompt and accepts stdin input ──────────────────


def test_tty_mode_prompts_stdin_like_legacy(tmp_path):
    """AC-3 — bridge spawns engine, renders the first prompt to the PTY,
    accepts a stdin line, and the loop completes with a clean exit code.

    Choosing ``"c"`` (cancelar) as the response: ``undo`` recognises it
    and exits 0 directly, which is the simplest deterministic
    continuation. The bridge writes the response file, re-invokes the
    engine, the engine consumes the response, runs the cancel branch,
    and exits 0. The bridge propagates exit 0 to the PTY parent.

    Assertions:
      - The prompt buffer received from the PTY is non-empty (the bridge
        rendered SOMETHING to the user — exact text is owned by the
        renderer / mentor_calmo modules and is allowed to evolve).
      - The buffer ends near a ``"> "`` input cursor (``input()`` echoed
        through the PTY).
      - The final exit code is 0 (clean cancel through ``undo``).
    """
    project_root = _scaffold_project(tmp_path)
    pid, fd = _spawn_bridge(project_root)
    try:
        prompt_buf = _read_until(fd, timeout=READ_PROMPT_TIMEOUT_S, until=b"> ")
        assert prompt_buf, "bridge produced no output before the prompt cursor"

        # Write the cancel option followed by newline so ``input()`` returns.
        os.write(fd, b"c\n")

        status = _wait_for_exit(pid, timeout=EXIT_WAIT_TIMEOUT_S)
        exit_code = _exit_status_code(status)
        assert exit_code == 0, (
            f"expected clean exit 0 after typing 'c'; got {exit_code}. "
            f"Prompt buffer (head)={prompt_buf[:300]!r}"
        )
    finally:
        _kill_and_reap(pid, fd)


# ── AC-5 — Ctrl+C in TTY mode exits 130 ──────────────────────────────────────


def test_tty_mode_ctrlc_exits_130(tmp_path):
    """AC-5 — SIGINT delivered to the bridge while it is at the
    ``input("> ")`` line surfaces as exit 130 (Decision 27, SPEC §8).

    The bridge catches ``KeyboardInterrupt`` inside the
    ``_prompt_user_via_stdin`` call, clears ``.claude/state/*``, and
    returns ``_EXIT_USER_CANCELLED`` (130). State cleanup is asserted
    via filesystem inspection — the pending file MUST be gone since the
    bridge took the cancel path.
    """
    project_root = _scaffold_project(tmp_path)
    pid, fd = _spawn_bridge(project_root)
    try:
        prompt_buf = _read_until(fd, timeout=READ_PROMPT_TIMEOUT_S, until=b"> ")
        assert prompt_buf, "bridge produced no output before SIGINT could fire"

        # Deliver SIGINT directly to the child PID. Writing ``\x03`` to
        # the PTY master would also work via line discipline, but
        # signalling the PID avoids ambiguity if the terminal mode has
        # drifted (the bridge's pty is in cooked mode by default).
        os.kill(pid, signal.SIGINT)

        status = _wait_for_exit(pid, timeout=EXIT_WAIT_TIMEOUT_S)
        exit_code = _exit_status_code(status)
        assert exit_code == 130, (
            f"expected exit 130 on SIGINT; got {exit_code}. "
            f"Prompt buffer (head)={prompt_buf[:300]!r}"
        )

        # State files cleaned up — bridge's KeyboardInterrupt handler
        # clears them before returning 130. Pending must be absent.
        pending = project_root / ".claude" / "forge" / "state" / "forge-pending.json"
        assert not pending.exists(), (
            f"bridge should have cleared pending on Ctrl+C; found {pending}"
        )
    finally:
        _kill_and_reap(pid, fd)


# ── AC-5 — Pause token routes through ``UserPausedError`` (exit 2) ───────────


def test_pause_token_propagates_as_paused_response(tmp_path):
    """AC-5 — typing a canonical pause token (``para``) at the prompt
    triggers the response-side pause channel and surfaces as exit 2.

    Flow:
      1. Bridge spawns engine; engine prints first pending + exits 2.
      2. Bridge reads the pending, renders the prompt to the PTY.
      3. We type ``para\\n``. Bridge's ``_build_response`` recognises
         it as a ``_PAUSE_TOKENS`` member and writes
         ``{"paused": true, ...}`` to ``forge-response.json``.
      4. Bridge re-invokes the engine. The chokepoint consumes the
         response, ``_check_pause_response`` raises ``UserPausedError``
         (allow_pause=True on the ``undo`` menu prompt).
      5. ``engine.cli::main()`` maps the sentinel to exit 2. Bridge
         reads exit 2, calls ``read_pending`` → returns ``None`` (state
         already cleared by ``_check_pause_response``) → bridge returns
         exit 2 verbatim.

    Assertions:
      - Final exit code is 2 (clean pause, resumable).
      - Both state files are absent — clean pause clears them.
    """
    project_root = _scaffold_project(tmp_path)
    pid, fd = _spawn_bridge(project_root)
    try:
        prompt_buf = _read_until(fd, timeout=READ_PROMPT_TIMEOUT_S, until=b"> ")
        assert prompt_buf, "bridge produced no output before the prompt cursor"

        # ``para`` is the first canonical token in ``_PAUSE_TOKENS``.
        os.write(fd, b"para\n")

        status = _wait_for_exit(pid, timeout=EXIT_WAIT_TIMEOUT_S)
        exit_code = _exit_status_code(status)
        assert exit_code == 2, (
            f"expected exit 2 (paused via response); got {exit_code}. "
            f"Prompt buffer (head)={prompt_buf[:300]!r}"
        )

        # Clean pause clears state on the engine side via
        # ``_check_pause_response`` → ``_clear_state``. Both files
        # must be absent so the next ``forge undo`` invocation starts
        # fresh (Decision 27 — pause is resumable via re-invoke, not
        # via stale on-disk state).
        pending = project_root / ".claude" / "forge" / "state" / "forge-pending.json"
        response = project_root / ".claude" / "forge" / "state" / "forge-response.json"
        assert not pending.exists(), (
            f"pending should be absent after clean pause; found {pending}"
        )
        assert not response.exists(), (
            f"response should be absent after clean pause; found {response}"
        )
    finally:
        _kill_and_reap(pid, fd)
