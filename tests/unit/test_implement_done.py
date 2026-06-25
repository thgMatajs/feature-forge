"""Regression test — Gap 9 W-002: state=done transition writes shipped-at.

The W-002 fix carimba ``shipped-at`` em ISO 8601 UTC dentro de
``status.raw`` quando ``engine.implement`` flippa o estado de uma
feature pra ``"done"`` (todos os tasks fechados). O campo é o que
``engine.plan._import_parent_context`` lê pra renderizar
``Parent shipped: <ISO>`` no bloco §Extension context do intake
(`templates/feature-intake.template.md`).

Sem este test, o contrato "parent done pós-Gap-9 carrega shipped-at"
não tem nenhuma defesa runtime — o agent de intake instrui "se absent
escreva `unknown`" e silently mascara o bug pra sempre.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from engine import implement
from engine.memory.l1 import read_l1_status


_ISO_8601_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _seed_feature_all_tasks_done(
    project_root: Path, slug: str = "lembrete-rega"
) -> Path:
    """Greenfield feature pronta pra transição final: 1 task em status=done.

    Quando ``implement.run`` rodar, ``_pick_next_task`` retorna None
    (zero pendentes) e a engine flippa o L1 pra ``state="done"``.
    """
    workflow_config = project_root / ".claude" / "workflow-config.yaml"
    if not workflow_config.exists():
        workflow_config.write_text("version: 1\n", encoding="utf-8")

    feature_root = (
        project_root
        / "docs"
        / "forge-specs"
        / "features"
        / slug
    )
    (feature_root / "tasks").mkdir(parents=True)

    (feature_root / "plan-feature-handoff.json").write_text(
        json.dumps({"readiness": {"status": "ready"}}),
        encoding="utf-8",
    )

    # única task já fechada — força _pick_next_task → None.
    (feature_root / "tasks" / "TASK-001.yaml").write_text(
        "task_id: TASK-001\n"
        "description: já entregue\n"
        "allowed_files: []\n"
        "validations: []\n"
        "gates: []\n"
        "dependencies: []\n"
        "status: done\n",
        encoding="utf-8",
    )

    memory_l1 = project_root / ".claude" / "memory" / "L1" / slug
    memory_l1.mkdir(parents=True, exist_ok=True)
    (memory_l1 / "status.json").write_text(
        json.dumps(
            {
                "feature-slug": slug,
                "state": "implementing",
                "subtype": "product",
                "last-action": "task-completed",
                "last-action-at": "2026-06-03T10:00:00Z",
                "phase-lock": None,
            }
        ),
        encoding="utf-8",
    )
    return feature_root


def test_state_done_transition_writes_shipped_at_iso(
    tmp_forge_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gap 9 W-002 — done flip stamps shipped-at ISO 8601 UTC em status.raw."""
    slug = "lembrete-rega"
    _seed_feature_all_tasks_done(tmp_forge_project, slug)
    monkeypatch.chdir(tmp_forge_project)

    # Pré-condição: shipped-at ausente antes da transição.
    pre = read_l1_status(slug, tmp_forge_project)
    assert pre is not None
    assert pre.status == "implementing"
    assert pre.raw.get("shipped-at") is None

    rc = implement.run([slug])
    assert rc == 0

    post = read_l1_status(slug, tmp_forge_project)
    assert post is not None
    assert post.status == "done"
    shipped_at = post.raw.get("shipped-at")
    assert isinstance(shipped_at, str) and shipped_at, (
        "shipped-at deve ser carimbado na transição state=done (W-002)"
    )
    assert _ISO_8601_UTC.match(shipped_at), (
        f"shipped-at {shipped_at!r} fora do formato ISO 8601 UTC "
        "(YYYY-MM-DDTHH:MM:SSZ)"
    )


def test_state_done_transition_preserves_existing_shipped_at(
    tmp_forge_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Idempotência: re-run em feature já done não sobrescreve o timestamp original."""
    slug = "lembrete-rega"
    _seed_feature_all_tasks_done(tmp_forge_project, slug)
    monkeypatch.chdir(tmp_forge_project)

    # Cara dupla: já tem shipped-at carimbado de uma execução anterior + state done.
    status_path = (
        tmp_forge_project / ".claude" / "memory" / "L1" / slug / "status.json"
    )
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    payload["state"] = "done"
    payload["shipped-at"] = "2026-05-28T18:00:00Z"
    status_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    rc = implement.run([slug])
    assert rc == 0

    post = read_l1_status(slug, tmp_forge_project)
    assert post is not None
    assert post.status == "done"
    # Timestamp original preservado — não reseta na re-execução.
    assert post.raw.get("shipped-at") == "2026-05-28T18:00:00Z"
