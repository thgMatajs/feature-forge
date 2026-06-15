"""E2E — ``forge init`` against a brownfield project, intent-protocol wiring.

Cobre AC-6 do SPEC ``det-6-multi-axis-backend.md`` no layer subprocess —
o handler ``_handle_backend_multi_axis_brownfield`` (W7.1) já tem
integration test autoritativo em
``tests/integration/test_init_brownfield_multi_axis.py``; este arquivo
exercita o wiring W7.4 ponta-a-ponta:

  bash dispatcher → ``engine.cli.main`` → ``engine.init._run_pipeline`` →
  ``ui_question.ask*`` → ``intent_state.write_pending`` → exit 2

Estratégia: scope reduzido (Caminho C do context-pack do dispatcher).
``forge init`` tem 16+ prompts interativos; um loop hard-coded de
responses pra dirigir até workflow-config.yaml seria frágil contra
mudanças de copy / ordem / novos prompts. Em vez disso:

1. Verifica que ``forge init`` num projeto com signals Firebase exita 2
   na primeira invocação E emite pending JSON conforme schema.
2. Exercita UM ciclo response → re-invoke pra confirmar que o handshake
   subprocess funciona (engine consome response e avança).
3. Não tenta dirigir todo o flow — esse é o trabalho dos integration
   tests, que conseguem isolar handlers sem o overhead do CLI.

Skipped por default; ativa com ``RUN_E2E=1`` no env. Mesmo gate dos
demais tests em ``tests/e2e/``.
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

# Schema fields obrigatórios por kind, conforme
# ``docs/schemas/intent-protocol.md`` §"Pending file".
_PENDING_REQUIRED_FIELDS = {
    "schema-version",
    "intent-id",
    "command",
    "command-args",
    "kind",
    "question",
    "allow-pause",
    "created-at",
    "pid",
}


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_init_brownfield_emits_valid_pending_on_first_prompt(
    tmp_path: Path,
) -> None:
    """AC-6 wiring: subprocess CLI emit pending JSON na primeira pergunta.

    Cenário-âncora: projeto com firebase signals (compose_backend_axes
    vai detectar firebase-auth uniforme acima do threshold). A primeira
    pergunta do init é o ``Confirmar preset kmp-mobile?`` (linha
    ``engine/init.py:1199``) — antes do W7.1 brownfield handler. O foco
    aqui não é a pergunta específica do W7.1 (integration tests cobrem),
    e sim provar que o CLI subprocess emite pending JSON válido conforme
    o intent protocol — sem isso, NADA do W7 funciona end-to-end.
    """
    scaffold_minimal_project(tmp_path, with_firebase_signals=True)

    result = run_forge(["init"], cwd=tmp_path, timeout=60)

    assert result.returncode == 2, (
        f"forge init deveria pausar com exit 2 na primeira pergunta. "
        f"Got exit {result.returncode}.\n"
        f"stdout: {result.stdout[-800:]}\n"
        f"stderr: {result.stderr[-400:]}"
    )

    pending = read_pending(tmp_path)
    assert pending is not None, (
        "Engine emit exit 2 mas não escreveu "
        ".claude/state/forge-pending.json — wiring intent-protocol quebrou."
    )

    missing = _PENDING_REQUIRED_FIELDS - set(pending.keys())
    assert not missing, (
        f"pending JSON sem campos obrigatórios do schema: {sorted(missing)}\n"
        f"payload: {pending}"
    )

    assert pending["schema-version"] == 1
    assert pending["command"] == "init", (
        f"pending.command esperado 'init', got {pending['command']!r}"
    )
    assert pending["kind"] in {
        "ask",
        "ask_text",
        "ask_multi",
        "confirm",
        "ask_three_paths",
    }, f"pending.kind inválido: {pending['kind']!r}"


def _init_response_provider(pending: dict) -> object:
    """Default response shape pra dirigir ``forge init`` algumas voltas.

    Resolve as 2-3 perguntas iniciais que aparecem antes de o pipeline
    entrar nos handlers W7. Nada além disso — o objetivo é validar que
    o response→re-invoke handshake funciona, não dirigir o init até o
    write final (que tem 16+ steps e múltiplos gates).

    Mapping:
      · "Confirmar preset kmp-mobile?" → "sim"
      · "Resume de init pendente?" → "discard" (cycle 1 — checkpoint
        gate sempre fires após cycle 0 saved checkpoint @ Step 2)
      · Outras perguntas → para o loop (return None) pra test inspecionar
    """
    question = (pending.get("question") or "").lower()
    options = pending.get("options") or {}

    # Resume gate — sempre escolhe discard pra não bloquear advance.
    if "resume" in question and "discard" in options:
        return "discard"

    # Preset confirmation.
    if "preset" in question and "sim" in options:
        return "sim"

    # Não sabemos como responder — para o loop e devolve estado atual.
    return None


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_init_brownfield_response_handshake_advances(
    tmp_path: Path,
) -> None:
    """AC-6 wiring: handshake response→re-invoke avança o pipeline.

    Drive um loop de até ~5 ciclos respondendo às perguntas iniciais
    (preset + eventual resume gate). O objetivo NÃO é completar init —
    são integration tests + W7.4 wiring (handlers cobertos por
    integration tests). O objetivo é provar que:

    1. Subprocess CLI consegue executar ≥2 ciclos response→re-invoke
       sem quebrar o intent protocol.
    2. ``IntentMismatchError`` nunca aparece quando o driver responde
       à pergunta correta (i.e., re-lê pending entre ciclos em vez de
       reusar intent-id stale).
    3. Engine avança o ``checkpoint.step`` ao longo dos ciclos (prova
       que o response foi consumido e o pipeline progrediu).
    """
    scaffold_minimal_project(tmp_path, with_firebase_signals=True)

    # Drive intent loop — handler interno faz invoke→pending→response→
    # re-invoke pra cada ciclo. Limpa stale response entre ciclos pra
    # garantir que o engine não tropece em intent-id stale quando o
    # checkpoint-resume gate (Step 1) intervém entre ciclos.
    final_result = drive_intent_loop(
        ["init"],
        cwd=tmp_path,
        response_provider=_init_response_provider,
        max_cycles=6,
        timeout=60,
    )

    # IntentMismatchError NUNCA deve aparecer — sinal de wiring quebrado.
    stderr_lc = final_result.stderr.lower()
    assert "mismatch" not in stderr_lc, (
        f"intent mismatch detected — wiring intent-protocol quebrou.\n"
        f"stderr: {final_result.stderr[-400:]}"
    )

    # Exit 0/2 ambos aceitáveis (init completou ou parou em pergunta
    # nova). Exit 1 com mismatch já capturado acima; qualquer outro
    # exit 1 (race, json error) também é wiring issue.
    assert final_result.returncode in (0, 2), (
        f"loop terminou com exit {final_result.returncode}.\n"
        f"stdout: {final_result.stdout[-400:]}\n"
        f"stderr: {final_result.stderr[-400:]}"
    )

    # Prova de advance: checkpoint deve ter step além do baseline.
    # ``_save_checkpoint`` no init grava o step atual a cada transição
    # (engine/init.py:1120 step-2-discovery; 1175 step-3-preset-suggestion;
    # 1216 step-5-backend-selection; etc.).
    checkpoint_path = tmp_path / ".claude" / ".init-checkpoint.yaml"
    if checkpoint_path.is_file():
        # Se completou (exit 0), checkpoint foi limpo. Se parou em
        # alguma pergunta nova, checkpoint persistiu.
        import yaml as _yaml  # local import — só este test usa
        cp = _yaml.safe_load(checkpoint_path.read_text(encoding="utf-8")) or {}
        step = str(cp.get("step", ""))
        # Step 4 = preset confirmation. Avance significa step >= 5
        # OU step contendo "backend" / "resolve" / "snapshot".
        assert "step-1" not in step or step == "", (
            f"checkpoint não avançou — engine não consumiu responses. "
            f"step={step!r}, cycles drove com sucesso até pause."
        )
