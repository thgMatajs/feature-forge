"""E2E — ``forge init`` num projeto greenfield, intent-protocol wiring.

Cobre AC-7 do SPEC ``det-6-multi-axis-backend.md`` no layer subprocess —
o handler ``_handle_backend_multi_axis_greenfield`` (W7.2) já tem
integration test autoritativo em
``tests/integration/test_init_greenfield_multi_axis.py``; este arquivo
exercita o wiring W7.4 ponta-a-ponta via subprocess.

Pre-W7 stubs (commit-history) só testavam ``forge --help`` /
``--version`` / ``init bogus``. Esses paths NÃO exercitam o W7.4 wiring
— eles param em arg parsing antes de qualquer ``ui_question.ask*``.
Substitui aqueles stubs por tests que de fato carregam o pipeline.

Estratégia: scope reduzido (Caminho C do context-pack do dispatcher).
Init greenfield bate no mesmo flow inicial de brownfield até Step 5
(backend), onde se bifurca — então o subprocess emit pending pra
Step 4 (preset confirmation) é equivalente em ambos os caminhos. O
ponto deste arquivo é provar:

  · Subprocess CLI funciona em projeto VAZIO (greenfield path real).
  · Help / version / unknown-arg paths continuam corretos (regression
    guard contra mudanças em ``engine.cli`` que quebrem esses paths
    secundários).

Skipped por default; ativa com ``RUN_E2E=1`` no env.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.e2e.conftest import (
    drive_intent_loop,
    read_pending,
    run_forge,
    scaffold_minimal_project,
)

_RUN_E2E = os.environ.get("RUN_E2E") == "1"


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_init_greenfield_emits_pending_on_first_prompt(
    tmp_path: Path,
) -> None:
    """AC-7 wiring: subprocess CLI emit pending pra projeto sem signals.

    Greenfield path = projeto vazio (só ``.git/``). compose_backend_axes
    retorna zero signals, então ``_run_pipeline`` cai no W7.2 handler
    eventualmente. Mas a primeira pergunta antes do W7.2 é ainda o
    ``Confirmar preset kmp-mobile?`` (preset_score=0.00 < threshold mas
    handler emite mesmo assim — só o resumo dos sinais muda).

    Foco: provar que o subprocess + dispatcher + cli wiring + intent
    protocol funcionam end-to-end pra projeto greenfield. Se o init
    pre-W7 funcionava em greenfield mas o W7.4 quebrou alguma coisa do
    pipeline antes do backend selection, este test pega.
    """
    scaffold_minimal_project(tmp_path, with_firebase_signals=False)

    result = run_forge(["init"], cwd=tmp_path, timeout=60)

    assert result.returncode == 2, (
        f"forge init em greenfield deveria exit 2 na primeira pergunta. "
        f"Got {result.returncode}.\n"
        f"stdout: {result.stdout[-800:]}\n"
        f"stderr: {result.stderr[-400:]}"
    )

    pending = read_pending(tmp_path)
    assert pending is not None, (
        "Greenfield init exit 2 mas pending não foi emitido."
    )
    assert pending["command"] == "init"
    assert pending["schema-version"] == 1
    assert "intent-id" in pending and pending["intent-id"], (
        "pending sem intent-id — schema do intent protocol quebrou."
    )


def _init_greenfield_response_provider(pending: dict) -> object:
    """Mesma estratégia do brownfield (test_e2e_brownfield_init) —
    resolve as 2-3 perguntas iniciais e para no primeiro handler-
    específico W7."""
    question = (pending.get("question") or "").lower()
    options = pending.get("options") or {}

    if "resume" in question and "discard" in options:
        return "discard"
    if "preset" in question and "sim" in options:
        return "sim"
    return None


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_init_greenfield_response_handshake(tmp_path: Path) -> None:
    """AC-7 wiring: handshake response→re-invoke avança o pipeline.

    Mirror do equivalente em brownfield — drive um loop respondendo às
    perguntas iniciais e prove que (a) IntentMismatchError nunca aparece
    e (b) checkpoint.step avança além de step-1.
    """
    scaffold_minimal_project(tmp_path, with_firebase_signals=False)

    # Drive intent loop (mesma strategy do brownfield) — handler interno
    # faz invoke→pending→response→re-invoke cycle-by-cycle.
    final_result = drive_intent_loop(
        ["init"],
        cwd=tmp_path,
        response_provider=_init_greenfield_response_provider,
        max_cycles=6,
        timeout=60,
    )

    stderr_lc = final_result.stderr.lower()
    assert "mismatch" not in stderr_lc, (
        f"intent mismatch detected.\nstderr: {final_result.stderr[-400:]}"
    )
    assert final_result.returncode in (0, 2), (
        f"loop terminou com exit {final_result.returncode}.\n"
        f"stdout: {final_result.stdout[-400:]}\n"
        f"stderr: {final_result.stderr[-400:]}"
    )

    checkpoint_path = tmp_path / ".claude" / ".init-checkpoint.yaml"
    if checkpoint_path.is_file():
        import yaml as _yaml
        cp = _yaml.safe_load(checkpoint_path.read_text(encoding="utf-8")) or {}
        step = str(cp.get("step", ""))
        assert "step-1" not in step or step == "", (
            f"checkpoint não avançou; step={step!r}"
        )


# ── Regression guards pros stubs antigos ────────────────────────────────────
#
# Mantemos os 3 tests originais (help / version / unknown-arg) porque eles
# protegem paths secundários do CLI que NÃO passam pelo intent protocol —
# se ``--help`` quebrar, todos os tests novos ainda assim podem passar (o
# bug fica invisível). Esses três têm overhead trivial e endereçam regressão
# real do CLI.


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_help_exits_zero(tmp_path: Path) -> None:
    """Regression guard: ``forge --help`` continua exit 0."""
    result = run_forge(["--help"], cwd=tmp_path, timeout=15)
    assert result.returncode == 0, (
        f"--help exit {result.returncode}\nstderr: {result.stderr[-300:]}"
    )
    assert "Subcomandos" in result.stdout or "forge" in result.stdout


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_version_exits_zero(tmp_path: Path) -> None:
    """Regression guard: ``forge --version`` continua exit 0."""
    result = run_forge(["--version"], cwd=tmp_path, timeout=15)
    assert result.returncode == 0, (
        f"--version exit {result.returncode}\nstderr: {result.stderr[-300:]}"
    )
    assert "forge" in result.stdout


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_init_rejects_unknown_arg(tmp_path: Path) -> None:
    """Regression guard: ``forge init bogus`` continua exit 2 (rejeitado).

    NOTA: exit 2 aqui é o ``cli.py`` flagando arg desconhecido, distinto
    do exit 2 paused-for-input que os tests novos exercitam. Ambos os
    paths convergem no mesmo código mas têm semântica diferente —
    diferenciados pelo stderr / state files.
    """
    scaffold_minimal_project(tmp_path, with_firebase_signals=False)
    result = run_forge(["init", "bogus"], cwd=tmp_path, timeout=15)
    assert result.returncode == 2, (
        f"init bogus deveria exit 2 (arg inválido), got {result.returncode}.\n"
        f"stderr: {result.stderr[-300:]}"
    )
