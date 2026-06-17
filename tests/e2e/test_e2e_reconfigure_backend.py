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

import os
from pathlib import Path

import pytest

from tests.e2e.conftest import (
    drive_intent_loop,
    read_pending,
    run_forge,
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


def _reconfigure_backend_response_provider(pending: dict) -> object:
    """Response provider pra test_forge_reconfigure_backend_response_advances.

    Fluxo natural pós engine-fix (read_response trata file stale-consumido
    como None em vez de raise):

    - Cycle 1: o engine emite o category picker (ask_multi com "backend"
      nas options). O provider responde ``["backend"]``.
    - Cycle 2: re-invocado, o engine lê a resposta do category picker do
      response.json (match → consumed-log), avança pro backend submenu, e
      emite o pending do submenu (ask_multi "Quais cells?"). O response.json
      ainda carrega a resposta do category picker — mas o id dela já está no
      consumed-log, então ``read_response`` pro intent-id do submenu retorna
      None (stale-consumido) em vez de levantar IntentMismatchError. O engine
      emite o pending do submenu + exit 2 limpo.
    - O provider recebe esse pending de submenu e retorna None pra parar o
      loop — o teste assere sobre esse pending final.

    Sem _prime_intent_log, sem acoplamento ao formato JSONL interno: o
    drive_intent_loop limpo dirige o handshake ponta-a-ponta.
    """
    kind = pending.get("kind", "")
    options = pending.get("options") or {}

    # Category picker: ask_multi com "backend" nas options → responde.
    if kind == "ask_multi" and "backend" in options:
        return ["backend"]

    # Submenu backend (ou qualquer outro pending) → parar o loop.
    return None


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_reconfigure_backend_response_advances(tmp_path: Path) -> None:
    """AC-8 wiring: selecionar ``backend`` no menu top-level avança pro submenu.

    Usa drive_intent_loop limpo (mesmo padrão de
    ``test_e2e_greenfield_init::*_response_handshake``). Pós engine-fix
    (read_response trata file stale-consumido como None), o ciclo multi-intent
    do reconfigure funciona via fluxo natural — sem pre-prime do consumed-log.

    Ciclo:
    - Cycle 1: engine emite o category picker; provider responde ["backend"].
    - Cycle 2: engine lê o category picker do response.json, avança pro
      backend submenu, e emite o pending do submenu. O response.json stale
      (id já no consumed-log) NÃO causa IntentMismatchError — read_response
      retorna None pro intent-id do submenu. Provider retorna None → loop para.

    Asserções (AC-8):
    - Sem mismatch error: handshake funcionou.
    - Exit 0 (handler termina limpo) ou exit 2 (provider parou no submenu).
    - Se exit 2: pending final é do submenu backend (command="reconfigure",
      intent-id diferente do category picker).
    """
    _seed_project_with_config(tmp_path)

    final_result = drive_intent_loop(
        ["reconfigure"],
        cwd=tmp_path,
        response_provider=_reconfigure_backend_response_provider,
        max_cycles=4,
        timeout=60,
    )

    # Asserção principal: sem mismatch error — handshake do intent protocol
    # funcionou (response do category picker foi consumido pelo engine sem
    # que o stale response.json levantasse IntentMismatchError no submenu).
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
        # O pending final é o submenu backend — kind ask/ask_multi, mas NÃO o
        # category picker (que tinha "backend" nas options de top-level).
        final_options = pending_final.get("options") or {}
        assert "backend" not in final_options, (
            "pending final ainda é o category picker (tem 'backend' nas "
            "options) — engine não avançou pro submenu backend."
        )
