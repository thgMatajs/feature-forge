"""Integration regression suite — 7 MeoBonsai pilot bugs (3 critical + 4 usability).

Este arquivo é o ponto de consolidação dos 7 bugs do relatório MeoBonsai
resolvidos nas Waves 2 e 3. Cada seção documenta o bug, o teste autoritativo
(se existir em outro arquivo), e contribui uma cobertura integration-level
complementar via subprocess ou via API direta numa fixture com estado realista.

Mapa de autoridade:
  Bug #1 (checkpoint × intent-id mismatch):
    Unidade:      tests/unit/test_ui_intent_state.py::test_read_response_stale_consumed_file_returns_none
                  tests/unit/test_ui_intent_state.py::test_read_response_re_entry_sequence_resolves_without_mismatch
    E2E:          tests/e2e/test_e2e_reconfigure_backend.py::test_forge_reconfigure_backend_response_advances
    Aqui:         cenário integration-level multi-pergunta via subprocess (fix verifica).

  Bug #2 (stale response poisoning):
    Aqui:         cenário integration-level direto (não duplicado em outros arquivos).

  Bug #3 (piped stdin → INTENT_FILE, não trava):
    E2E:          tests/e2e/test_per_host_dispatch.py::test_dispatch_intent_file_fallback (e2e gate)
    Aqui:         cenário integration-level via subprocess non-tty, sem RUN_E2E gate.

  Bug U1 (exit codes pre-init):
    Unidade:      tests/unit/test_exit_codes.py::test_pre_init_returns_exit_1 (parametrized)
    Aqui:         smoke integration multi-comando em tmp_path.

  Bug U2 (--help sem WARN):
    Unidade:      tests/unit/test_exit_codes.py::test_help_emits_zero_warn (parametrized)
    Aqui:         assert integration com PYTHONPATH scrubado e tmp_path isolado.

  Bug U3 (ASCII fallback non-TTY):
    Unidade:      tests/unit/test_renderer_ascii_fallback.py (cobertura unit completa)
    Aqui:         assert integration via subprocess capturando stdout non-tty.

  Bug U4 (forge qa sem args → 3-caminhos, sem traceback):
    Unidade:      tests/unit/test_qa_no_args.py::test_forge_qa_no_args_no_traceback
    Aqui:         assert integration em tmp_path brownfield completo com qa.enabled.

Refs:
  - docs/superpowers/specs/drift-1-intent-protocol.md §3 (re-entry, mismatch)
  - engine/ui/intent_state.py (stale-consumed guard)
  - engine/host/detect.py (detect_host precedência)
  - engine/ui/renderer.py (to_ascii_box / write)
  - engine/qa/__init__.py (resolve_scope guard)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

# ── Repo root ────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FORGE_BIN = PROJECT_ROOT / "bin" / "forge"

# ── Env scrub helpers ─────────────────────────────────────────────────────────
# Mesma lista de todos os outros testes que subprocessam bin/forge. Garante
# que detect_host não resolve um adapter agentic quando pytest roda dentro de
# Claude Code / opencode / codex / cursor.

_SCRUB_EXACT = ("CLAUDECODE", "FORGE_FORCE_INTENT_MODE", "FORGE_FORCE_TTY_MODE")
_SCRUB_PREFIXES = ("OPENCODE_", "CODEX", "CURSOR_")


def _clean_env() -> dict[str, str]:
    """Env scrubado com FORGE_HOME + PYTHONPATH apontando pro worktree."""
    env = os.environ.copy()
    for key in list(env.keys()):
        if key in _SCRUB_EXACT or any(key.startswith(p) for p in _SCRUB_PREFIXES):
            env.pop(key)
    env["FORGE_HOME"] = str(PROJECT_ROOT)
    env["PYTHONPATH"] = (
        str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    )
    return env


# ── Project scaffolding ───────────────────────────────────────────────────────


def _scaffold_brownfield(tmp_path: Path, *, pin_intent_file: bool = True) -> Path:
    """Layout mínimo que ``find_project_root`` + ``undo`` aceitam.

    ``pin_intent_file=True`` escreve ``forge-config.yaml`` com ``host: intent-file``
    para que o engine use o adapter on-disk mesmo quando pytest herda CLAUDECODE=1
    do Claude Code host — garante pending.json ao invés do marcador stdout CC.
    """
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "workflow-config.yaml").write_text("{}\n", encoding="utf-8")
    forge = claude / "forge"
    forge.mkdir(parents=True, exist_ok=True)
    if pin_intent_file:
        (forge / "forge-config.yaml").write_text(
            "host: intent-file\n", encoding="utf-8"
        )
    (forge / "state").mkdir(exist_ok=True)
    return tmp_path


def _scaffold_qa_project(tmp_path: Path) -> Path:
    """Layout brownfield com qa.enabled: true (para Bug U4)."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "workflow-config.yaml").write_text(
        "qa:\n  enabled: true\n", encoding="utf-8"
    )
    return tmp_path


def _state_dir(project_root: Path) -> Path:
    return project_root / ".claude" / "forge" / "state"


def _pending_path(project_root: Path) -> Path:
    return _state_dir(project_root) / "forge-pending.json"


def _response_path(project_root: Path) -> Path:
    return _state_dir(project_root) / "forge-response.json"


def _run_forge(
    project_root: Path,
    *args: str,
    stdin_pipe: bool = True,
    timeout: float = 30,
) -> subprocess.CompletedProcess:
    """Invoca ``python -m engine.cli <args>`` com stdin piped (non-tty).

    ``stdin=DEVNULL`` mantém sys.stdin.isatty() == False no subprocess,
    forçando detect_host para fora do ramo TTY. ``capture_output=True``
    coleta stdout e stderr sem vazar pro terminal.
    """
    return subprocess.run(
        [sys.executable, "-m", "engine.cli", *args],
        cwd=str(project_root),
        env=_clean_env(),
        stdin=subprocess.DEVNULL if stdin_pipe else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_forge_bin(
    project_root: Path,
    *args: str,
    stdin_bytes: bytes | None = None,
    timeout: float = 30,
) -> subprocess.CompletedProcess:
    """Invoca o dispatcher ``bin/forge`` diretamente."""
    return subprocess.run(
        [str(FORGE_BIN), *args],
        cwd=str(project_root),
        env=_clean_env(),
        stdin=subprocess.PIPE,
        input=stdin_bytes or b"",
        capture_output=True,
        timeout=timeout,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Bug #1 — checkpoint × intent-id mismatch (DRIFT-1 fix, commit 5827900)
# ══════════════════════════════════════════════════════════════════════════════


def test_bug1_multi_question_reentry_no_mismatch(tmp_path: Path) -> None:
    """Integration: ciclo multi-pergunta completo sem IntentMismatchError.

    Reproduz o contrato end-to-end que o DRIFT-1 W7-fix garantiu:
      1. Forge roda, pausa no primeiro prompt → pending.json com id-A, exit 2.
      2. Host escreve response para id-A.
      3. Forge re-invocado: consome id-A (log), avança, pausa no segundo
         prompt → pending.json com id-B, exit 2. Response stale (id-A) ainda
         no disco NÃO causa IntentMismatchError — o stale-consumed guard o
         trata como None e o engine emite novo pending.

    Autoridade unit: tests/unit/test_ui_intent_state.py
      ::test_read_response_re_entry_sequence_resolves_without_mismatch
      ::test_read_response_stale_consumed_file_returns_none
    Autoridade e2e: tests/e2e/test_e2e_reconfigure_backend.py
      ::test_forge_reconfigure_backend_response_advances

    Este teste verifica o mesmo contrato no nível integration via
    subprocess, usando ``engine.ui.intent_state`` diretamente para
    simular o handshake host-side sem a camada e2e skipif.
    """
    from engine.ui import intent_state

    project_root = _scaffold_brownfield(tmp_path)

    # Passo 1 — primeira invocação: engine pausa no primeiro prompt.
    result_1 = _run_forge(project_root, "undo")
    assert result_1.returncode == 2, (
        f"Esperava exit 2 (paused) na primeira invocação. "
        f"Got {result_1.returncode}.\nstderr: {result_1.stderr[-400:]}"
    )

    pending_path = _pending_path(project_root)
    assert pending_path.is_file(), "pending.json deve existir após exit 2."
    pending_1 = json.loads(pending_path.read_text(encoding="utf-8"))
    intent_id_a = pending_1["intent-id"]
    assert intent_id_a, "intent-id da primeira pergunta deve ser string não-vazia."

    # Passo 2 — host escreve response para intent-id-A.
    response_payload = {
        "schema-version": 1,
        "intent-id": intent_id_a,
        "kind": pending_1["kind"],
        "value": next(iter(pending_1.get("options") or {"discard": "x"})),
        "answered-at": "2026-06-16T12:00:00Z",
    }
    _response_path(project_root).write_text(
        json.dumps(response_payload), encoding="utf-8"
    )

    # Passo 3 — segunda invocação: engine consome id-A, avança.
    # Não testamos aqui o segundo prompt específico (isso é e2e territory)
    # mas garantimos que o engine NÃO emite "mismatch" no stderr e sai com
    # exit 0 ou 2 (não exit 1 de erro de protocolo).
    result_2 = _run_forge(project_root, "undo")
    stderr_lc = result_2.stderr.lower()
    assert "mismatch" not in stderr_lc, (
        f"IntentMismatchError detectado na segunda invocação — stale-consumed "
        f"guard não funcionou.\nstderr: {result_2.stderr[-500:]}"
    )
    assert result_2.returncode in (0, 2, 130), (
        f"Segunda invocação retornou exit code inesperado {result_2.returncode}. "
        f"Esperava 0 (ok), 2 (nova pausa) ou 130 (cancel).\n"
        f"stderr: {result_2.stderr[-400:]}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Bug #2 — stale forge-response.json não envenena próximo comando
# ══════════════════════════════════════════════════════════════════════════════


def test_bug2_stale_response_does_not_poison_fresh_command(tmp_path: Path) -> None:
    """Integration: response.json stale de comando anterior não causa mismatch.

    Cenário:
      1. Simula um comando anterior que deixou um forge-response.json com
         um intent-id que NÃO pertence ao próximo comando. O id já está no
         intent-log (foi consumido neste lifecycle).
      2. Roda ``forge undo`` — engine deve emitir o seu próprio pending.json
         com id fresco e sair exit 2 limpo, sem IntentMismatchError.

    O stale-consumed guard em ``engine.ui.intent_state.read_response``
    detecta que o id do arquivo já foi consumido (via log) e retorna None,
    permitindo que o engine emita um novo pending normalmente.
    """
    from engine.ui import intent_state

    project_root = _scaffold_brownfield(tmp_path)

    # Simula: comando anterior deixou response.json com id-stale consumido.
    stale_id = "stale-response-id-00000000-0000-4000-8000-000000000000"
    stale_response = {
        "schema-version": 1,
        "intent-id": stale_id,
        "kind": "ask",
        "value": "kmp-mobile",
        "answered-at": "2026-06-15T10:00:00Z",
    }
    state_dir = _state_dir(project_root)
    state_dir.mkdir(parents=True, exist_ok=True)
    _response_path(project_root).write_text(
        json.dumps(stale_response), encoding="utf-8"
    )

    # Simula que stale_id já está no log (foi consumido neste lifecycle).
    # Usa o helper público canônico (cross-AI review LOW) em vez dos
    # internos _reset_log_cache + _append_intent_log — o teste prova
    # COMPORTAMENTO (o stale-consumed guard) sem acoplar ao storage do log.
    intent_state.seed_consumed_log(
        project_root,
        intent_id=stale_id,
        response=stale_response,
    )

    # Roda ``undo`` com response.json stale no disco.
    result = _run_forge(project_root, "undo")

    # Engine deve emitir pending fresco e sair exit 2 — sem mismatch.
    stderr_lc = result.stderr.lower()
    assert "mismatch" not in stderr_lc, (
        f"IntentMismatchError detectado com response.json stale — "
        f"stale-poisoning guard não funcionou.\nstderr: {result.stderr[-500:]}"
    )
    assert result.returncode in (0, 2), (
        f"Esperava exit 2 (pausa com novo pending) ou 0. "
        f"Got {result.returncode}.\nstderr: {result.stderr[-400:]}"
    )

    # Se pausou com novo pending, o intent-id deve ser diferente do stale.
    if result.returncode == 2:
        pending_path = _pending_path(project_root)
        assert pending_path.is_file(), (
            "exit 2 sem pending.json — contrato quebrado."
        )
        fresh_pending = json.loads(pending_path.read_text(encoding="utf-8"))
        fresh_id = fresh_pending.get("intent-id", "")
        assert fresh_id != stale_id, (
            f"pending.json fresco tem o mesmo intent-id do stale response — "
            f"poisoning detectado.\nfresh_id={fresh_id!r}, stale_id={stale_id!r}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Bug #3 — piped stdin (non-tty) → INTENT_FILE, não trava nem traceback
# ══════════════════════════════════════════════════════════════════════════════


def test_bug3_piped_stdin_routes_to_intent_file_no_hang(tmp_path: Path) -> None:
    """Integration: stdin piped (non-tty) + env scrubado → IntentFileAdapter.

    ``echo "1" | forge <cmd>`` (stdin pipe, non-tty, sem env agentic) deve:
      - detect_host → INTENT_FILE (fallback determinístico)
      - escrever forge-pending.json
      - sair exit 2 limpo (PausedForInputError capturado pelo cli.main)
      - NÃO travar esperando stdin
      - NÃO emitir traceback

    Autoridade e2e: tests/e2e/test_per_host_dispatch.py::test_dispatch_intent_file_fallback
    (requer RUN_E2E=1 — porta para integration lane sem esse gate).

    Diferença aqui: usa ``python -m engine.cli`` com env explicitamente
    scrubado, sem o skipif RUN_E2E, cobrindo o contract no rapid+integration
    lane que roda em CI.
    """
    project_root = _scaffold_brownfield(tmp_path, pin_intent_file=False)

    # Remove forge-config.yaml se existia (queremos detect_host decidir via env).
    forge_cfg = project_root / ".claude" / "forge" / "forge-config.yaml"
    forge_cfg.unlink(missing_ok=True)

    # stdin=PIPE com input="" simula "echo '' | forge undo" — non-tty, dados
    # no pipe mas stdin imediatamente fecha (sem bloquear).
    env = _clean_env()
    # Garante que nenhuma var agentic sobrou (double-check).
    for key in ("CLAUDECODE", "FORGE_FORCE_INTENT_MODE", "FORGE_FORCE_TTY_MODE"):
        env.pop(key, None)

    # ``input=""`` implica stdin=PIPE (fecha imediatamente — adapter não lê stdin).
    # Usar input= ao invés de stdin=PIPE para evitar ValueError do subprocess.
    result = subprocess.run(
        [sys.executable, "-m", "engine.cli", "undo"],
        cwd=str(project_root),
        env=env,
        input="",           # fecha stdin imediatamente — adapter não lê stdin
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Sem traceback — exit via controle de fluxo limpo.
    assert "Traceback" not in result.stderr, (
        f"Traceback detectado em piped-stdin path.\nstderr: {result.stderr[-600:]}"
    )
    assert result.returncode != -9, (
        "Processo foi morto (SIGKILL) — possível hang detectado."
    )

    # O engine deve ter pausado (exit 2) escrevendo o pending file.
    assert result.returncode == 2, (
        f"Esperava exit 2 (paused) com piped stdin. "
        f"Got {result.returncode}.\nstderr: {result.stderr[-400:]}\n"
        f"stdout: {result.stdout[-400:]}"
    )

    pending_path = _pending_path(project_root)
    assert pending_path.is_file(), (
        "forge-pending.json deve existir após exit 2 via IntentFileAdapter."
    )
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    assert pending.get("schema-version") == 1
    assert "intent-id" in pending


# ══════════════════════════════════════════════════════════════════════════════
# Bug U1 — exit codes pre-init (graph / memory / reconfigure → exit 1)
# ══════════════════════════════════════════════════════════════════════════════


def test_bug_u1_pre_init_commands_exit_1_integration(tmp_path: Path) -> None:
    """Integration: graph, memory e reconfigure em dir pre-init retornam exit 1.

    Smoke multi-comando num tmp_path limpo (sem .claude/workflow-config.yaml).
    Complementa tests/unit/test_exit_codes.py::test_pre_init_returns_exit_1
    adicionando contexto de subprocess via bin/forge com env scrubado e
    tmp_path sem qualquer init.

    O exit 1 é o contrato SPEC §3 A.1 — pré-init não é "paused", é erro
    esperado com mensagem mentor-calmo.
    """
    # Authoritative unit coverage:
    # tests/unit/test_exit_codes.py::test_pre_init_returns_exit_1 (parametrized)
    # Aqui: smoke integration num único tmp_path, bin/forge real.

    pre_init_cmds = ["graph", "memory", "reconfigure"]
    failures = []

    for cmd in pre_init_cmds:
        r = subprocess.run(
            [str(FORGE_BIN), cmd],
            cwd=str(tmp_path),
            env=_clean_env(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 1:
            failures.append(
                f"forge {cmd}: got exit {r.returncode}, expected 1. "
                f"stderr={r.stderr[-200:]!r}"
            )

    assert not failures, (
        "Um ou mais comandos pre-init não retornaram exit 1:\n"
        + "\n".join(failures)
    )


# ══════════════════════════════════════════════════════════════════════════════
# Bug U2 — forge --help sem [WARN] no stderr
# ══════════════════════════════════════════════════════════════════════════════


def test_bug_u2_help_flag_no_warn_stderr_integration(tmp_path: Path) -> None:
    """Integration: ``forge --help`` não emite [WARN] cleanup no stderr.

    Autoridade unit: tests/unit/test_exit_codes.py::test_help_emits_zero_warn
    (parametrized com --help / -h / no-args).

    Aqui: assert integration via bin/forge num tmp_path limpo com env scrubado,
    garantindo que o caminho bin/ + dispatcher bash + engine.cli não reintroduz
    o [WARN] em nenhuma camada intermediária.
    """
    # Authoritative unit coverage:
    # tests/unit/test_exit_codes.py::test_help_emits_zero_warn

    r = subprocess.run(
        [str(FORGE_BIN), "--help"],
        cwd=str(tmp_path),
        env=_clean_env(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert "[WARN]" not in r.stderr, (
        f"`forge --help` emitiu [WARN] no stderr — cleanup noise regrediu.\n"
        f"stderr: {r.stderr!r}"
    )
    assert "failed to clear" not in r.stderr.lower(), (
        f"`forge --help` emitiu 'failed to clear' no stderr.\n"
        f"stderr: {r.stderr!r}"
    )
    assert "Traceback" not in r.stderr, (
        f"`forge --help` emitiu Traceback no stderr.\n"
        f"stderr: {r.stderr!r}"
    )
    # forge --help deve mencionar "forge" no stdout (smoke de conteúdo).
    assert "forge" in r.stdout.lower(), (
        f"`forge --help` não mencionou 'forge' no stdout.\n"
        f"stdout: {r.stdout!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Bug U3 — ASCII fallback em output non-TTY (subprocess capturando stdout)
# ══════════════════════════════════════════════════════════════════════════════


_BOX_CHARS = set("┌┐└┘─│├┤┬┴┼")


def test_bug_u3_non_tty_subprocess_output_no_box_chars(tmp_path: Path) -> None:
    """Integration: output non-TTY (subprocess capture) não contém box-drawing.

    ``subprocess.run`` com ``capture_output=True`` força sys.stdout.isatty()
    == False no filho. O renderer.write() deve aplicar to_ascii_box() e
    ANSI-strip. Nenhum char de "┌┐└┘─│├┤┬┴┼" deve escapar pro stdout.

    Autoridade unit: tests/unit/test_renderer_ascii_fallback.py
      (TestWriteNonTTY — cobertura via stream.isatty() in-process)

    Aqui: assert integration via subprocess real — cobre a cadeia completa
    (bin/forge → engine.cli → handler → renderer.write → sys.stdout) num
    cenário non-tty que o renderer detecta via sys.stdout.isatty() == False.

    Usa ``forge --help`` (caminho não-interativo, exit 0) pra ter output
    determinístico com box/header sem depender de perguntas interativas.
    """
    # Authoritative unit coverage:
    # tests/unit/test_renderer_ascii_fallback.py::TestWriteNonTTY

    r = subprocess.run(
        [str(FORGE_BIN), "--help"],
        cwd=str(tmp_path),
        env=_clean_env(),
        stdin=subprocess.DEVNULL,
        capture_output=True,        # stdout piped → isatty() == False no filho
        text=True,
        encoding="utf-8",
        timeout=30,
    )

    stdout = r.stdout
    leaked = [ch for ch in _BOX_CHARS if ch in stdout]
    assert not leaked, (
        f"Box-drawing chars {leaked!r} encontrados em stdout non-TTY. "
        f"ASCII fallback regrediu.\n"
        f"stdout (primeiros 600 chars): {stdout[:600]!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Bug U4 — forge qa sem args → 3-caminhos, sem traceback
# ══════════════════════════════════════════════════════════════════════════════


def test_bug_u4_forge_qa_no_args_three_paths_no_traceback(tmp_path: Path) -> None:
    """Integration: ``forge qa`` sem scope target → 3-caminhos mentor-calmo, sem traceback.

    Antes do fix: resolve_scope("") levantava ValueError não capturado por
    ``except ScopeError``, propagando traceback cru. Após o fix: guard em
    _qa_run detecta raw_target vazio, imprime 3-caminhos, retorna 0.

    Autoridade unit: tests/unit/test_qa_no_args.py::test_forge_qa_no_args_no_traceback

    Aqui: assert integration num projeto brownfield com qa.enabled e .git/,
    garantindo que o handler qa é alcançado (sem ProjectRootNotFoundError)
    e o guard de args dispara antes do resolve_scope. tmp_path inclui .git/
    e workflow-config com qa.enabled: true para refletir o contexto MeoBonsai.
    """
    # Authoritative unit coverage:
    # tests/unit/test_qa_no_args.py::test_forge_qa_no_args_no_traceback

    project_root = _scaffold_qa_project(tmp_path)

    r = subprocess.run(
        [str(FORGE_BIN), "qa"],
        cwd=str(project_root),
        env=_clean_env(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert "Traceback" not in r.stderr, (
        f"`forge qa` sem args emitiu Traceback.\nstderr: {r.stderr!r}"
    )
    assert "ValueError" not in r.stderr, (
        f"`forge qa` sem args emitiu ValueError.\nstderr: {r.stderr!r}"
    )
    # Mensagem 3-caminhos deve aparecer no stdout (mentor-calmo, PT).
    stdout_lc = r.stdout.lower()
    assert "caminhos" in stdout_lc or "caminho" in stdout_lc, (
        f"`forge qa` sem args não emitiu mensagem de 3-caminhos.\n"
        f"stdout: {r.stdout!r}\nstderr: {r.stderr!r}"
    )
    # Exit code informativo (não fatal): 0 ou 4.
    assert r.returncode in (0, 4), (
        f"`forge qa` sem args retornou {r.returncode} (esperava 0 ou 4).\n"
        f"stdout: {r.stdout!r}\nstderr: {r.stderr!r}"
    )
