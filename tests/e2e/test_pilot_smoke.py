"""E2E — pilot smoke: brownfield init safety + upgrade no-op.

Valida os dois contratos centrais do piloto v1.3:

1. ``test_pilot_end_to_end_brownfield_init``: forge init em projeto
   brownfield denso (fixture meobonsai-class) não corrompe assets do
   usuário. Itens verificados:

   - O wiring subprocess funciona: init emite pending JSON válido
     (exit 2 + forge-pending.json com schema correto).
   - Brownfield safety: ``.claude/skills/`` e ``.claude/agents/``
     preservados byte-a-byte após a invocação inicial.
   - settings.json preservado (presença + validade JSON, append-only).
   - ``.claude/forge/`` criado no sub-namespace correto (Task 0.10).
   - Nenhum arquivo de user assets foi criado/modificado/removido.

   Estratégia: Scope reduzido — mesmo raciocínio de
   ``test_e2e_brownfield_init.py``. Init tem 16+ prompts; um driver
   end-to-end seria frágil. O objetivo do piloto é provar que o
   wiring subprocess + brownfield isolation funcionam, não exaurir
   todos os gates. Arranca o loop até o primeiro pending e asserta
   as invariantes.

2. ``test_pilot_forge_upgrade_noop``: Referência leve ao contrato
   "já no latest". ``test_forge_upgrade.py::test_forge_upgrade_no_op_at_latest``
   cobre o cenário em detalhe; este teste é um smoke alias para deixar
   claro no relatório do piloto que o upgrade no-op está verde. Reutiliza
   ``_setup_fake_forge_home`` do módulo upgrade ao invés de duplicar setup.

Marker: e2e. Skipped por default; ativa com ``RUN_E2E=1``.

Refs:
- ``docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md`` §3/§4
- ``tests/e2e/test_e2e_brownfield_init.py`` (padrão de wiring)
- ``tests/e2e/test_forge_upgrade.py`` (setup fake repo)
- ``tests/fixtures/meobonsai-class/`` (fixture brownfield)
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.conftest import (
    REPO_ROOT,
    drive_intent_loop,
    env_with_forge_home,
    read_pending,
    run_forge,
)

_RUN_E2E = os.environ.get("RUN_E2E") == "1"

# Fixture brownfield — projeto meobonsai-class com skills/agents/settings pré-existentes.
_MEOBONSAI_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "meobonsai-class"

# Schema fields obrigatórios por ``docs/schemas/intent-protocol.md`` §"Pending file".
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


def _snapshot_dir(directory: Path) -> dict[str, bytes]:
    """Retorna {relative_path_str: file_bytes} de todos os arquivos em ``directory``.

    Usado para comparar snapshots antes/depois de uma invocação e garantir
    que nenhum arquivo foi criado, modificado ou removido (brownfield safety).
    """
    snapshot: dict[str, bytes] = {}
    if not directory.is_dir():
        return snapshot
    for p in sorted(directory.rglob("*")):
        if p.is_file():
            key = str(p.relative_to(directory))
            snapshot[key] = p.read_bytes()
    return snapshot


def _setup_brownfield_project(tmp_path: Path) -> Path:
    """Copia a fixture meobonsai-class pra ``tmp_path/pilot-project``.

    A fixture já contém:
      - ``.claude/skills/`` (5 skills)
      - ``.claude/agents/`` (3 agents)
      - ``.claude/settings.json`` (hooks registrados)
      - ``.claude/hooks/`` (post-edit.sh, pre-commit-user.sh)
      - ``CLAUDE.md`` raiz

    O init é brownfield-safe por construção (merge append-only + delegator
    encadeado + isolamento via sub-namespace), sem switch de modo: o
    ``.claude/forge/`` deve ser criado sem tocar nos assets acima.

    Adiciona ``.git/`` pra ``_is_git_repo`` passar — a fixture não inclui
    ``.git/`` pra não comprometer o git do repo de testes.
    """
    project = tmp_path / "pilot-project"
    shutil.copytree(str(_MEOBONSAI_FIXTURE), str(project))
    # Adiciona .git/ mínimo pra engine._is_git_repo passar
    (project / ".git").mkdir(exist_ok=True)
    return project


def _init_first_response_provider(pending: dict[str, Any]) -> object:
    """Responde os prompts iniciais de ``forge init`` de forma previsível.

    Mapeamento:
      - Resume gate ("resume" na pergunta + "discard" nas opções) →
        "discard". Aparece no ciclo 1+ quando o checkpoint de Step 2
        já foi gravado.
      - Preset confirmation ("preset" na pergunta + "sim" nas opções) →
        "sim".
      - Qualquer outra pergunta → None (para o loop; test asserta o estado).

    Mesmo mapeamento de ``_init_response_provider`` em test_e2e_brownfield_init.py
    (mandamento #3 reuse — lógica idêntica, reusada com nome local para
    deixar o smoke auto-suficiente sem import cross-test).
    """
    question = (pending.get("question") or "").lower()
    options = pending.get("options") or {}

    if "resume" in question and "discard" in options:
        return "discard"

    if "preset" in question and "sim" in options:
        return "sim"

    # Pergunta desconhecida — para o loop; test inspeciona estado atual.
    return None


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_pilot_end_to_end_brownfield_init(tmp_path: Path) -> None:
    """Piloto: forge init em brownfield não corrompe assets do usuário.

    Contrato central do piloto v1.3:
    - Wiring subprocess funciona (exit 2 + pending JSON válido).
    - ``.claude/skills/`` e ``.claude/agents/`` idênticos ao snapshot pré-init.
    - ``.claude/settings.json`` preservado (ainda é JSON válido após merge).
    - ``.claude/forge/`` criado no sub-namespace correto (Task 0.10).
    """
    project = _setup_brownfield_project(tmp_path)

    # Snapshots ANTES da invocação — brownfield safety invariant.
    skills_before = _snapshot_dir(project / ".claude" / "skills")
    agents_before = _snapshot_dir(project / ".claude" / "agents")
    settings_before = (project / ".claude" / "settings.json").read_bytes()

    assert skills_before, "fixture precisa ter skills para disparar detecção brownfield"
    assert agents_before, "fixture precisa ter agents para disparar detecção brownfield"

    # Invoca forge init — expect exit 2 (pausa na primeira pergunta)
    # ou exit 0 se o init completou sem interação (cenário menos provável
    # com brownfield denso, mas aceitável como smoke).
    result = run_forge(["init"], cwd=project, timeout=60)

    # ── Assert: wiring subprocess ─────────────────────────────────────────────
    assert result.returncode in (0, 2), (
        f"forge init retornou exit {result.returncode} (esperado 0 ou 2).\n"
        f"stdout: {result.stdout[-800:]}\n"
        f"stderr: {result.stderr[-400:]}"
    )

    if result.returncode == 2:
        # Saída esperada: pending JSON emitido conforme intent protocol.
        pending = read_pending(project)
        assert pending is not None, (
            "Engine emitiu exit 2 mas não escreveu "
            ".claude/forge/state/forge-pending.json — wiring intent-protocol quebrou."
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

    # ── Assert: brownfield safety — user assets intactos ─────────────────────
    skills_after = _snapshot_dir(project / ".claude" / "skills")
    agents_after = _snapshot_dir(project / ".claude" / "agents")

    assert skills_after == skills_before, (
        "BROWNFIELD SAFETY VIOLATION: forge init modificou .claude/skills/.\n"
        f"Antes: {sorted(skills_before)}\n"
        f"Depois: {sorted(skills_after)}\n"
        f"Adicionados: {sorted(set(skills_after) - set(skills_before))}\n"
        f"Removidos: {sorted(set(skills_before) - set(skills_after))}\n"
        f"Modificados: {[k for k in skills_before if k in skills_after and skills_before[k] != skills_after[k]]}"
    )

    assert agents_after == agents_before, (
        "BROWNFIELD SAFETY VIOLATION: forge init modificou .claude/agents/.\n"
        f"Antes: {sorted(agents_before)}\n"
        f"Depois: {sorted(agents_after)}\n"
        f"Adicionados: {sorted(set(agents_after) - set(agents_before))}\n"
        f"Removidos: {sorted(set(agents_before) - set(agents_after))}\n"
        f"Modificados: {[k for k in agents_before if k in agents_after and agents_before[k] != agents_after[k]]}"
    )

    # settings.json: deve continuar existindo e ser JSON válido.
    # Append-only merge pode adicionar campos; não esperamos identidade de bytes,
    # apenas validade estrutural e preservação dos campos originais.
    settings_path = project / ".claude" / "settings.json"
    assert settings_path.exists(), (
        "BROWNFIELD SAFETY VIOLATION: .claude/settings.json foi removido."
    )
    settings_current_bytes = settings_path.read_bytes()
    try:
        settings_after_dict = json.loads(settings_current_bytes)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"BROWNFIELD SAFETY VIOLATION: .claude/settings.json corrompido (JSON inválido).\n"
            f"erro: {exc}\n"
            f"conteúdo: {settings_current_bytes[:400]!r}"
        ) from exc

    # Conteúdo original deve estar contido no merged (append-only garante isso).
    settings_original_dict = json.loads(settings_before)
    original_hooks = settings_original_dict.get("hooks", {})
    merged_hooks = settings_after_dict.get("hooks", {})
    for event, registrations in original_hooks.items():
        assert event in merged_hooks, (
            f"BROWNFIELD SAFETY VIOLATION: hook event '{event}' do settings.json original "
            f"sumiu após forge init. merged hooks keys: {list(merged_hooks)}"
        )
        # Verifica que os registros originais ainda estão presentes (subset).
        for reg in registrations:
            assert reg in merged_hooks[event], (
                f"BROWNFIELD SAFETY VIOLATION: registro de hook original perdido "
                f"em event '{event}'.\n"
                f"Registro esperado: {reg}\n"
                f"Registros presentes: {merged_hooks[event]}"
            )

    # ── Assert: sub-namespace .claude/forge/ criado (se init progrediu) ───────
    # Se init chegou a escrever config (exit 0) ou passou do Step 2 (checkpoint),
    # .claude/forge/ deve existir. Em exit 2 imediato (antes do Step 2), pode
    # ainda não ter sido criado — asserção condicional para não tornar o smoke
    # frágil contra a ordem interna de prompts.
    forge_dir = project / ".claude" / "forge"
    checkpoint_path = project / ".claude" / ".init-checkpoint.yaml"
    init_progressed_past_step2 = checkpoint_path.exists() or forge_dir.exists()

    if result.returncode == 0:
        # Init completou — .claude/forge/ com forge-config.yaml devem existir.
        assert forge_dir.exists(), (
            "forge init retornou exit 0 mas .claude/forge/ não foi criado."
        )
        forge_config = forge_dir / "forge-config.yaml"
        assert forge_config.exists(), (
            "forge init retornou exit 0 mas .claude/forge/forge-config.yaml não existe."
        )
    elif init_progressed_past_step2:
        # Checkpoint gravado → Step 2 (discovery) concluiu → forge_dir deve existir.
        assert forge_dir.exists(), (
            ".init-checkpoint.yaml existe (Step 2 concluiu) mas .claude/forge/ ausente — "
            "sub-namespace não foi criado antes do checkpoint."
        )


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_pilot_forge_upgrade_noop(tmp_path: Path, capsys) -> None:
    """Piloto: forge upgrade retorna 0 quando HEAD == origin (no-op).

    Smoke alias do contrato coberto em detalhe por
    ``tests/e2e/test_forge_upgrade.py::test_forge_upgrade_no_op_at_latest``.
    Este teste existe para que o relatório do piloto inclua "upgrade no-op
    verde" sem duplicar o setup; reutiliza ``_setup_fake_forge_home`` do
    mesmo módulo de upgrade para montar o fake repo local.

    Se ``test_forge_upgrade_no_op_at_latest`` já passou, este smoke
    confirma que o mesmo contrato é válido no contexto do piloto (mesma
    engine, mesmo forge_home fake, sem rede).
    """
    from engine.upgrade import run_upgrade
    from unittest.mock import patch

    # Importa helper de setup do módulo de upgrade sem duplicar código.
    from tests.e2e.test_forge_upgrade import _setup_fake_forge_home

    fake_home, _origin = _setup_fake_forge_home(tmp_path)

    with patch("engine.upgrade._pip_refresh"):  # não roda pip real
        result = run_upgrade(forge_home=fake_home)

    assert result == 0, (
        f"forge upgrade deveria retornar 0 (já no latest), obtido {result}"
    )
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert "latest" in combined, (
        f"mensagem 'latest' ausente no output de upgrade no-op.\n"
        f"stdout={captured.out!r}\nstderr={captured.err!r}"
    )
