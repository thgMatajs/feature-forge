"""E2E tests — ``TtyAdapter`` caminho TTY humano via PTY real (Wave 2).

Substitui ``tests/e2e/test_tty_bridge_e2e.py`` (deletado no clean break da
Wave 2). O antigo suite spawnava ``python -m engine.ui.tty_bridge
engine.cli undo`` num PTY pra exercer o subprocess-loop do bridge. Aqui
spawnamos ``python -m engine.cli undo`` DIRETO num PTY — não há mais
bridge. O ``TtyAdapter`` (``engine/host/adapters/tty.py``) lê stdin
in-process, single-pass, e nunca escreve ``forge-pending.json``.

Cobertura:
  - AC-3 (TTY mode behaviour) — o prompt interativo aparece no PTY e o
    comando completa quando o usuário digita uma resposta válida.
  - Invariante do clean break — nenhum ``forge-pending.json`` é escrito
    (o TtyAdapter não usa intent_state; success criterion #5 da spec).

Por que ``pty`` stdlib (não ``pexpect``):
  - Decision 22 — sem novas deps de runtime em feature-forge.
  - ``pty.fork()`` + ``select.select`` cobre o que precisamos (read-until-
    pattern + escrita no master) sem arrastar lib externa.

Detecção do host no PTY
=======================

``detect_host`` só retorna ``HostName.TTY`` quando NÃO há ``host`` override
em ``forge-config.yaml``, NÃO há ``CLAUDECODE``, NÃO há nenhuma var
``OPENCODE_*``, e ``sys.stdin.isatty()`` é True. O ``pty.fork()`` garante
o ``isatty``; o ENV SCRUB abaixo garante o resto. Sem o scrub, um ambiente
que rode o pytest dentro de Claude Code/opencode/codex/cursor faria o
engine resolver o adapter errado (intent_file/CC) e o prompt nunca
apareceria no PTY.

Marker: ``e2e`` — fora da rapid lane por default.

Refs:
  - ``docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md`` §4,
    success criterion #5
  - ``engine/host/adapters/tty.py`` (TtyAdapter)
  - ``engine/host/detect.py`` (detect_host — precedência config > env > TTY)
  - ``engine/undo.py`` (menu top-level com opção ``c`` = cancelar → exit 0)
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
        reason="pty.fork() unavailable on Windows; TtyAdapter coberto via unit tests mock-based",
    ),
]


# Project root resolves from this file: tests/e2e/test_X.py → repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Subcommand de prompt leve: ``undo`` chega no menu top-level
# (``question.ask``) imediatamente, com a opção ``c`` (cancelar) → exit 0.
SUBCOMMAND = "undo"

# Bootstrap + primeiro prompt completam em ~2s no hot path; os dois tetos
# abaixo limitam quanto qualquer leitura ou poll de waitpid pode pendurar
# o teste se o subprocess travar. ``pytest-timeout`` não está nas dev deps,
# então esses budgets inline são a rede de segurança.
READ_PROMPT_TIMEOUT_S = 8.0
EXIT_WAIT_TIMEOUT_S = 6.0


# ── Env scrub ─────────────────────────────────────────────────────────────


# Prefixos/nomes de env que enviesariam ``detect_host`` pra longe do TTY.
# Reproduz o scrub do antigo test_tty_bridge_e2e.py, ampliado pra cobrir
# todos os hosts agentic que o engine reconhece (CLAUDECODE / OPENCODE_* /
# CODEX* / CURSOR_*), conforme MEMORY subprocess-env-scrub.
_SCRUB_EXACT = ("CLAUDECODE", "FORGE_FORCE_INTENT_MODE", "FORGE_FORCE_TTY_MODE")
_SCRUB_PREFIXES = ("OPENCODE_", "CODEX", "CURSOR_")


def _scrubbed_env() -> dict[str, str]:
    """Env limpo de sinais agentic + PYTHONPATH/FORGE_HOME do worktree.

    Sem o scrub, ``detect_host`` resolveria CLAUDE_CODE/OPENCODE em vez de
    TTY e o ``TtyAdapter`` nunca rodaria — o prompt não apareceria no PTY.
    """
    env = os.environ.copy()
    for name in _SCRUB_EXACT:
        env.pop(name, None)
    for key in list(env.keys()):
        if any(key.startswith(prefix) for prefix in _SCRUB_PREFIXES):
            env.pop(key, None)
    pythonpath = str(PROJECT_ROOT)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        pythonpath + os.pathsep + existing if existing else pythonpath
    )
    env["FORGE_HOME"] = str(PROJECT_ROOT)
    return env


# ── Helpers ─────────────────────────────────────────────────────────────────


def _scaffold_project(tmp_path: Path) -> Path:
    """Layout ``.claude/`` mínimo pra ``find_project_root``.

    Deliberadamente SEM ``forge-config.yaml`` com ``host:`` — qualquer
    override de host venceria a detecção TTY (precedência config > env >
    TTY em ``detect_host``), e este teste precisa do ramo TTY.
    """
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "workflow-config.yaml").write_text("{}\n", encoding="utf-8")
    (claude / "state").mkdir(exist_ok=True)
    return tmp_path


def _spawn_cli(project_root: Path) -> tuple[int, int]:
    """Fork um child rodando ``python -m engine.cli undo`` num PTY real.

    Retorna ``(pid, master_fd)``. O master fd lê o que o child escreve no
    seu stdout/stderr (ambos no mesmo PTY) e escritas voltam pro stdin do
    child. O cwd do child é ``project_root`` pra resolver o mesmo
    ``.claude/``. NÃO há bridge — o engine roda direto e o ``TtyAdapter``
    lê stdin in-process.
    """
    try:
        pid, fd = pty.fork()
    except OSError as exc:
        pytest.skip(f"pty.fork() unavailable in this environment: {exc!r}")

    if pid == 0:  # child
        try:
            os.chdir(str(project_root))
            env = _scrubbed_env()
            os.execvpe(
                sys.executable,
                [
                    sys.executable,
                    "-m",
                    "engine.cli",
                    SUBCOMMAND,
                ],
                env,
            )
        except Exception as exc:  # pragma: no cover — child-side error path
            # Se o exec falhar, escreve diagnóstico e sai non-zero pro
            # parent surfacar. Não dá pra usar pytest aqui.
            os.write(2, f"child exec failed: {exc!r}\n".encode("utf-8"))
            os._exit(127)
    return pid, fd


def _read_until(fd: int, *, timeout: float, until: bytes) -> bytes:
    """Lê do PTY master ``fd`` até ``until`` aparecer ou estourar timeout.

    Limitado por ``select.select`` com teto por iteração pra que um
    subprocess travado nunca pendure o teste indefinidamente. Levanta
    ``TimeoutError`` no timeout (callers envolvem em try/finally pra
    garantir cleanup).
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
            # PTY fechado (child saiu antes do pattern) — surfaca o que
            # temos pro assert ser informativo.
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
    """Bloqueia até ``pid`` sair, retornando o status cru de waitpid.

    Loop de poll limitado — ``os.waitpid(pid, os.WNOHANG)`` retorna
    ``(0, 0)`` enquanto o child roda. Levanta ``TimeoutError`` pra que o
    caminho de cleanup possa ``SIGKILL`` + reap.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        waited_pid, status = os.waitpid(pid, os.WNOHANG)
        if waited_pid == pid:
            return status
        time.sleep(0.05)
    raise TimeoutError(f"child pid={pid} did not exit within {timeout}s")


def _kill_and_reap(pid: int, fd: int) -> None:
    """Cleanup best-effort: mata o child se vivo, fecha o master fd."""
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        os.close(fd)
    except OSError:
        pass
    # Drena o zombie se ainda pendente. Limitado — nunca bloqueia num
    # processo que o kernel já limpou.
    for _ in range(20):
        try:
            waited_pid, _ = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return
        if waited_pid == pid:
            return
        time.sleep(0.05)


def _exit_status_code(status: int) -> int:
    """Traduz um status cru de ``waitpid`` no exit code humano.

    Cobre saídas limpas (``os.WIFEXITED``) e children terminados por sinal
    (``os.WIFSIGNALED``). Pra sinais, retorna a convenção Unix de
    ``128 + signum`` (SIGINT → 130), espelhando o ladder do engine.
    """
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return -1  # inalcançável na prática; surfaca como assertion clara


# ── AC-3 — TtyAdapter renderiza prompt e aceita stdin in-process ────────────


def test_tty_adapter_prompts_stdin_in_process(tmp_path):
    """AC-3 — engine roda DIRETO no PTY (sem bridge), o ``TtyAdapter``
    renderiza o primeiro prompt, aceita uma linha de stdin, e o loop
    completa com exit limpo.

    Resposta escolhida: ``"c"`` (cancelar) no menu top-level do ``undo``.
    O engine reconhece e sai 0 direto — continuação determinística mais
    simples. NÃO há round-trip por arquivo: o ``TtyAdapter`` lê stdin,
    resolve o value in-process, e o ``undo`` segue pro branch de cancel.

    Asserts:
      - O buffer recebido do PTY antes do cursor ``"> "`` é não-vazio (o
        adapter renderizou algo — o texto exato é dono do renderer e pode
        evoluir).
      - O exit code final é 0 (cancel limpo via ``undo``).
    """
    project_root = _scaffold_project(tmp_path)
    pid, fd = _spawn_cli(project_root)
    try:
        prompt_buf = _read_until(fd, timeout=READ_PROMPT_TIMEOUT_S, until=b"> ")
        assert prompt_buf, "engine produced no output before the prompt cursor"

        # Escreve a opção de cancel seguida de newline pra ``input()`` retornar.
        os.write(fd, b"c\n")

        status = _wait_for_exit(pid, timeout=EXIT_WAIT_TIMEOUT_S)
        exit_code = _exit_status_code(status)
        assert exit_code == 0, (
            f"expected clean exit 0 after typing 'c'; got {exit_code}. "
            f"Prompt buffer (head)={prompt_buf[:300]!r}"
        )
    finally:
        _kill_and_reap(pid, fd)


# ── Invariante clean break — TtyAdapter não escreve pending.json ────────────


def test_tty_adapter_never_writes_pending(tmp_path):
    """Success criterion #5 — o caminho TTY in-process NÃO escreve
    ``forge-pending.json`` em momento algum.

    Diferente dos adapters file-based (intent_file/CC) que emitem pending
    + exit 2 + re-invocação, o ``TtyAdapter`` lê stdin no mesmo processo.
    Não há arquivo de estado. Este teste prova a invariante driving o
    prompt real no PTY e inspecionando o filesystem depois do cancel.

    Asserts:
      - O prompt aparece no PTY (confirma que foi o TtyAdapter, não um
        no-op).
      - Exit 0 (cancel limpo).
      - ``.claude/forge/state/forge-pending.json`` NUNCA existe.
    """
    project_root = _scaffold_project(tmp_path)
    pid, fd = _spawn_cli(project_root)
    try:
        prompt_buf = _read_until(fd, timeout=READ_PROMPT_TIMEOUT_S, until=b"> ")
        assert prompt_buf, "engine produced no output before the prompt cursor"

        os.write(fd, b"c\n")

        status = _wait_for_exit(pid, timeout=EXIT_WAIT_TIMEOUT_S)
        exit_code = _exit_status_code(status)
        assert exit_code == 0, (
            f"expected clean exit 0 after typing 'c'; got {exit_code}. "
            f"Prompt buffer (head)={prompt_buf[:300]!r}"
        )

        pending = (
            project_root / ".claude" / "forge" / "state" / "forge-pending.json"
        )
        assert not pending.exists(), (
            f"TtyAdapter is in-process and must never write pending; "
            f"found {pending}"
        )
    finally:
        _kill_and_reap(pid, fd)
