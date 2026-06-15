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


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_forge_reconfigure_backend_response_advances(tmp_path: Path) -> None:
    """AC-8 wiring: selecionar ``backend`` no menu top-level avança pro submenu.

    Two-cycle test:
    1. Cycle 0: invoke → exit 2 → pending é o category picker (ask_multi).
    2. Write response com value=["backend"].
    3. Cycle 1: invoke → engine consome response, entra no
       ``_handle_backend_axes_submenu`` (W7.3) e emit outro pending OU
       termina (zero changes → exit 0).

    O assertion-chave: cycle 1 NÃO raises IntentMismatchError — o response
    foi consumido pelo engine. Cycle 1 exit 0 também é aceitável (handler
    pode terminar sem mudanças); ambos comprovam o handshake do intent
    protocol pelo subprocess.
    """
    _seed_project_with_config(tmp_path)

    # Cycle 0.
    result0 = run_forge(["reconfigure"], cwd=tmp_path, timeout=60)
    assert result0.returncode == 2, (
        f"cycle 0: esperava exit 2, got {result0.returncode}.\n"
        f"stderr: {result0.stderr[-400:]}"
    )

    pending0 = read_pending(tmp_path)
    assert pending0 is not None
    intent_id_0 = pending0["intent-id"]

    # Selecionar "backend" no ask_multi.
    write_response(
        tmp_path,
        intent_id=intent_id_0,
        kind="ask_multi",
        value=["backend"],
    )

    # Cycle 1 — engine consome response e avança pro submenu backend.
    result1 = run_forge(["reconfigure"], cwd=tmp_path, timeout=60)
    assert result1.returncode in (0, 2), (
        f"cycle 1: esperava advance (exit 0 ou 2), got {result1.returncode}.\n"
        f"stdout: {result1.stdout[-400:]}\n"
        f"stderr: {result1.stderr[-400:]}"
    )

    # Não pode ter mismatch error — sinal de wiring quebrado.
    stderr_lc = result1.stderr.lower()
    assert "mismatch" not in stderr_lc, (
        f"cycle 1 stderr menciona intent mismatch — response não foi "
        f"consumido pelo engine.\nstderr: {result1.stderr[-400:]}"
    )

    if result1.returncode == 2:
        pending1 = read_pending(tmp_path)
        assert pending1 is not None
        # Submenu backend deve estar emitindo seu próprio pending agora.
        # ``command`` continua "reconfigure" (mesma re-invocação).
        assert pending1["command"] == "reconfigure", (
            f"cycle 1 pending.command esperado 'reconfigure', "
            f"got {pending1['command']!r}"
        )
        # Intent-id diferente prova advance.
        assert pending1["intent-id"] != intent_id_0, (
            "cycle 1 emit pending com mesmo intent-id do cycle 0 — "
            "engine não avançou pro submenu."
        )
