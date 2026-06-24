"""E2E — `forge plan <slug>` dirigido pelo loop canônico (acceptance P-15).

Critério macro do round 4 (plano pilot-r4-generalize-reentry): dirigir
``forge plan <slug>`` via loop canônico do host — responder o prompt em-voo
e re-invocar argv IDÊNTICO SEM apagar checkpoint/state — avança pelas waves
sem ``IntentMismatchError``.

Causa-raiz (P-15): ``forge plan`` cria a L1 (status=planning) já na 1ª
invocação, antes da intake terminar. Na re-invocação mecânica, o guard de
colisão de slug (``_handle_active_slug_collision``) emitia um intent NOVO
que colidia com a response downstream → mismatch → exit 1. O fix (T3, helper
``host_is_replaying``) suprime o guard durante o replay; este e2e prova o
contrato end-to-end via subprocess + intent-protocol file loop.

Subprocessa o CLI → marker ``e2e``. Reusa o harness de
``tests/e2e/conftest.py`` (env scrub agentic + run_forge + read_pending +
write_response), seguindo MEMORY ``feedback_subprocess_env_scrub`` +
``feedback_venv_pytest_canonical``.

Refs:
- docs/superpowers/plans/2026-06-19-pilot-r4-generalize-reentry.md (T6)
- docs/reports/pilot-meobonsai-2026-06-19/report.md §P-15
- docs/schemas/intent-protocol.md §4.1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.conftest import (
    read_pending,
    run_forge,
    scaffold_minimal_project,
    write_response,
)

pytestmark = pytest.mark.e2e


def _scaffold_initialized_project(project_root: Path) -> Path:
    """Projeto mínimo que ``forge plan`` aceita como inicializado.

    ``find_project_root`` reconhece ``.claude/forge/forge-config.yaml`` (v1.3)
    ou ``.claude/workflow-config.yaml`` (compat). Semeamos ambos + pin
    ``host: intent-file`` pra o loop file-based ser determinístico (o env
    scrub de conftest já garante que detect_host não resolva um adapter
    agentic). NÃO rodamos ``forge init`` (16+ steps interativos — brittle).
    """
    project_root.mkdir(parents=True, exist_ok=True)
    scaffold_minimal_project(project_root)
    cfg = project_root / ".claude"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "workflow-config.yaml").write_text(
        "schema-version: 1\nidentity:\n  project-slug: demo-plan-loop\n",
        encoding="utf-8",
    )
    forge_dir = cfg / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "host: intent-file\n", encoding="utf-8"
    )
    return project_root


def _answer_for(pending: dict) -> object:
    """Resposta mínima pro prompt em-voo, por kind."""
    kind = pending.get("kind")
    if kind == "ask_multi":
        return []
    if kind == "confirm":
        return True
    # ask / ask_text / ask_three_paths — "-" é aceito como "sem material".
    return "-"


def test_forge_plan_advances_through_canonical_loop(tmp_path: Path) -> None:
    """Acceptance P-15: dirigir `forge plan <slug>` via loop canônico
    (responder + re-invocar argv idêntico, SEM apagar state) avança sem
    IntentMismatchError. A 1ª invocação cria a L1 (planning) e pausa no 1º
    prompt downstream; a re-invocação NÃO deve bater no guard de colisão."""
    project = _scaffold_initialized_project(tmp_path / "proj")
    slug = "demo-feature"

    # Invocação 1: cria a L1 (planning), pausa no 1º prompt downstream (exit 2).
    r1 = run_forge(["plan", slug], cwd=project)
    assert r1.returncode == 2, (
        f"1ª invocação devia pausar (exit 2); veio {r1.returncode}\n"
        f"stderr={r1.stderr}"
    )
    pending = read_pending(project)
    assert pending is not None, "engine pausou sem emitir pending"

    # Responde o prompt em-voo e re-invoca argv IDÊNTICO, state preservado
    # (NÃO apagamos checkpoint/response — é o que o host canônico faz).
    write_response(
        project,
        intent_id=pending["intent-id"],
        kind=pending["kind"],
        value=_answer_for(pending),
    )
    r2 = run_forge(["plan", slug], cwd=project)

    # Acceptance: NÃO exit 1 / NÃO IntentMismatchError. Avança (exit 2 =
    # próxima pausa) ou completa (exit 0). Nunca o deadlock de P-15 — onde a
    # re-invocação batia no guard de colisão e o id NÃO casava com a response.
    assert r2.returncode in (0, 2), (
        f"loop canônico travou: exit={r2.returncode}\nstderr={r2.stderr}"
    )
    assert "IntentMismatchError" not in (r2.stderr or "")
    assert "intent-id mismatch" not in (r2.stderr or "")
