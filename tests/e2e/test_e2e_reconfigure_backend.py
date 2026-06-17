"""E2E — ``forge reconfigure`` intent-protocol wiring.

Cobre AC-8 do SPEC ``det-6-multi-axis-backend.md`` no layer subprocess —
o handler ``_handle_backend_axes_submenu`` (W7.3) já tem integration
test autoritativo em ``tests/integration/test_reconfigure_multi_axis.py``;
este arquivo exercita o wiring W7.4 ponta-a-ponta via subprocess.

Gap fechado: pre-W7 não existia teste subprocess pra ``forge reconfigure``
de nenhuma natureza. O W7.3 wiring (categoria ``backend`` no menu →
``_handle_backend_axes_submenu``) precisava de cobertura no nível CLI pra
garantir que o submenu emit pending JSON correto via subprocess.

Estratégia: scope reduzido (Caminho C). Reconfigure tem múltiplos
submenus encadeados (cards / paths / backend / etc.) — não tentamos
dirigir até o write do workflow-config. Foco:

1. Subprocess ``forge reconfigure`` num projeto com workflow-config
   válido emite ``ask_multi`` (top-level category picker) como pending.
2. Selecionar ``backend`` no response avança pro submenu — segundo
   pending tem ``command="reconfigure"`` (re-entry preserva o cmd).

Skipped por default; ativa com ``RUN_E2E=1`` no env.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.e2e.conftest import (
    clear_response,
    drive_intent_loop,
    read_pending,
    run_forge,
    write_response,
)

_RUN_E2E = os.environ.get("RUN_E2E") == "1"


# Workflow-config mínimo válido pra reconfigure aceitar. Reconfigure só
# valida YAML-parse + presença do arquivo; não verifica schema. Usa o
# shape que init produziria pós-W7.4 (backend cells multi-axis) pra
# refletir realisticamente o estado pós-init.
_MINIMAL_CONFIG_YAML = """\
schema-version: 1
identity:
  project-slug: e2e-reconfigure
  preset: kmp-mobile
platforms:
  active: [android, ios, kmp]
backend:
  auth:
    all-platforms:
      card: firebase-auth
      status: active
  data:
    android: null
    ios: null
    kmp: null
cards:
  active: []
  snapshot-root: .claude/cards/snapshot
"""


def _seed_project_with_config(tmp_path: Path) -> Path:
    """Cria layout mínimo pra reconfigure aceitar: .git/ + workflow-config."""
    (tmp_path / ".git").mkdir()
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "workflow-config.yaml").write_text(
        _MINIMAL_CONFIG_YAML, encoding="utf-8"
    )
    return tmp_path


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_reconfigure_emits_category_menu_pending(tmp_path: Path) -> None:
    """AC-8 wiring: subprocess CLI emit ``ask_multi`` pro category picker.

    Reconfigure entrypoint (``engine/reconfigure.py:172``) carrega
    workflow-config, mostra snapshot, e logo emit
    ``ask_multi("O que mudar?", ...)``. Esse é o intent que prova o
    wiring subprocess do reconfigure pós-W7.3.

    Asserts:
    - exit 2 (paused-for-input)
    - pending kind == "ask_multi"
    - options contém "backend" (a categoria nova do W7.3)
    - command == "reconfigure" no pending
    """
    _seed_project_with_config(tmp_path)

    result = run_forge(["reconfigure"], cwd=tmp_path, timeout=60)

    assert result.returncode == 2, (
        f"forge reconfigure deveria exit 2 no category menu. "
        f"Got {result.returncode}.\n"
        f"stdout: {result.stdout[-800:]}\n"
        f"stderr: {result.stderr[-400:]}"
    )

    pending = read_pending(tmp_path)
    assert pending is not None, (
        "reconfigure exit 2 mas pending não foi emitido."
    )
    assert pending["kind"] == "ask_multi", (
        f"esperava kind=ask_multi pro category picker, "
        f"got {pending['kind']!r}"
    )
    assert pending["command"] == "reconfigure"

    options = pending.get("options") or {}
    assert "backend" in options, (
        f"category 'backend' (W7.3) ausente do menu. Options: "
        f"{sorted(options.keys())}"
    )


def _prime_intent_log(project_root: Path, intent_id: str, value: object) -> None:
    """Escreve uma entrada no consumed-intent log antes da próxima invocação.

    Permite que o engine "pule" um prompt já respondido (branch 1 de
    ``intent_state.read_response``) sem precisar de um response.json para
    esse intent-id. Uso legítimo em testes multi-intent onde o engine
    precisa avançar além do primeiro prompt sem causar ``IntentMismatchError``
    ao chegar no segundo prompt antes de haver response para ele no disco.

    Formato JSONL conforme ``engine/ui/intent_state.py:_append_intent_log``:
    ``{"intent-id": "...", "response": {...}, "consumed-at": "..."}``.

    O log sobrevive ao exit 2 (``PausedForInputError``) — a CLI limpa o log
    apenas em exits terminais (0, 1, 130). Portanto é seguro primá-lo
    após uma invocação que pausou e antes da próxima re-invocação.
    """
    state_dir = project_root / ".claude" / "forge" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "intent-id": intent_id,
        "response": {
            "schema-version": 1,
            "intent-id": intent_id,
            "kind": "ask_multi",
            "value": value,
            "answered-at": "2026-06-16T12:00:00Z",
        },
        "consumed-at": datetime.now(timezone.utc).isoformat(),
    }
    log_path = state_dir / "forge-intent-log.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _reconfigure_backend_response_provider(pending: dict) -> object:
    """Response provider pra test_forge_reconfigure_backend_response_advances.

    Após o consumed-log ter sido primado com a resposta do category picker
    (intent-id do category-menu), o drive_intent_loop invoca o engine. O
    engine lê o category picker do log (branch 1 — re-entry idempotency),
    avança pro backend submenu, e emite o pending do submenu (ask_multi
    "Quais cells?"). O provider recebe esse pending e retorna None pra parar
    o loop ali — o teste assere sobre o pending final.

    Casos adicionais:
    - Category picker re-emitido (log foi limpo por algum exit terminal
      inesperado): retorna ["backend"] pra responder normalmente.
    - Qualquer outro pending: retorna None (parar o loop).
    """
    kind = pending.get("kind", "")
    options = pending.get("options") or {}

    # Category picker: ask_multi com "backend" nas options.
    # Normalmente não chega aqui (log já pre-primado), mas como fallback
    # de segurança respondemos corretamente.
    if kind == "ask_multi" and "backend" in options:
        return ["backend"]

    # Qualquer outro pending (submenu backend ou terminal): parar o loop.
    return None


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_reconfigure_backend_response_advances(tmp_path: Path) -> None:
    """AC-8 wiring: selecionar ``backend`` no menu top-level avança pro submenu.

    Usa drive_intent_loop com pre-prime do consumed-intent log para tratar a
    limitação do ciclo multi-intent do reconfigure: o engine salva um
    ``.reconfigure-checkpoint.yaml`` antes do category-menu; ao ser re-invocado
    com a resposta do category picker no response.json, o engine avança pro
    backend submenu e emite um segundo intent (ask_multi "Quais cells?") sem
    ter response para ele — causando ``IntentMismatchError`` com o response.json
    ainda apontando para o category picker.

    O pre-prime resolve isso: antes de chamar drive_intent_loop, registramos a
    resposta do category picker no consumed-intent log
    (``forge-intent-log.jsonl``). O log sobrevive a exits 2
    (``PausedForInputError``) per DRIFT-1 spec §3. Na invocação do loop, o
    engine lê o category picker do log (branch 1 de ``read_response``), avança
    pro backend submenu sem mismatch, e emite o pending do submenu — onde o
    provider retorna None pra parar o loop e o teste assere.

    Asserções (AC-8):
    - Sem mismatch error: handshake funcionou.
    - Exit 0 (handler termina limpo) ou exit 2 (provider parou no submenu).
    - Se exit 2: pending final é do submenu backend (command="reconfigure",
      intent-id diferente do category picker).
    """
    _seed_project_with_config(tmp_path)

    # Invocação inicial pra obter o intent-id do category picker.
    # Exit 2 (PausedForInputError) — log não é limpo pela CLI.
    result_init = run_forge(["reconfigure"], cwd=tmp_path, timeout=60)
    assert result_init.returncode == 2, (
        f"invocação inicial: esperava exit 2 no category menu, "
        f"got {result_init.returncode}.\nstderr: {result_init.stderr[-400:]}"
    )
    pending_init = read_pending(tmp_path)
    assert pending_init is not None, "invocação inicial: pending ausente."
    intent_id_category = pending_init["intent-id"]
    assert pending_init.get("kind") == "ask_multi", (
        f"esperava kind=ask_multi no category picker, got {pending_init.get('kind')!r}"
    )
    assert "backend" in (pending_init.get("options") or {}), (
        "category 'backend' ausente do pending inicial — W7.3 wiring quebrado."
    )

    # Pre-prime: registra a resposta do category picker no consumed-intent log
    # ANTES de chamar drive_intent_loop. O engine vai ler do log (re-entry
    # idempotency branch 1) e avançar pro submenu backend sem mismatch.
    _prime_intent_log(tmp_path, intent_id_category, value=["backend"])

    # Limpa o pending.json deixado pela invocação inicial — o drive_intent_loop
    # começa com uma nova invocação e o engine detectaria o pending como race
    # condition se ele ainda estiver no disco.
    pending_path = tmp_path / ".claude" / "forge" / "state" / "forge-pending.json"
    pending_path.unlink(missing_ok=True)

    # drive_intent_loop: engine avança do category picker (lido do log) pro
    # backend submenu e emite o pending do submenu. O provider retorna None
    # pra parar o loop nesse ponto.
    final_result = drive_intent_loop(
        ["reconfigure"],
        cwd=tmp_path,
        response_provider=_reconfigure_backend_response_provider,
        max_cycles=4,
        timeout=60,
    )

    # Asserção principal: sem mismatch error — handshake do intent protocol
    # funcionou (response do category picker foi consumido pelo engine).
    stderr_lc = final_result.stderr.lower()
    assert "mismatch" not in stderr_lc, (
        f"intent mismatch detectado — handshake falhou.\n"
        f"stderr: {final_result.stderr[-400:]}"
    )

    # Exit 0 (handler terminou sem mudanças — zero cells editadas) ou exit 2
    # (provider retornou None no submenu backend). Ambos provam que o engine
    # avançou além do category picker pro submenu backend.
    assert final_result.returncode in (0, 2), (
        f"loop terminou com exit {final_result.returncode} inesperado.\n"
        f"stdout: {final_result.stdout[-400:]}\n"
        f"stderr: {final_result.stderr[-400:]}"
    )

    if final_result.returncode == 2:
        pending_final = read_pending(tmp_path)
        assert pending_final is not None, (
            "exit 2 mas pending ausente — contrato quebrado."
        )
        # Submenu backend emite seu próprio pending com command="reconfigure"
        # (re-entry preserva o cmd) e intent-id diferente do category picker.
        assert pending_final["command"] == "reconfigure", (
            f"pending final.command esperado 'reconfigure', "
            f"got {pending_final['command']!r}"
        )
        assert pending_final["intent-id"] != intent_id_category, (
            "pending final tem mesmo intent-id do category picker — "
            "engine não avançou pro submenu backend."
        )
