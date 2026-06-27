"""Testes do read de mem_context_hint em engine.qa.run_qa (W-ROUTE 6c Task 2).

Correções vs. plano (lição Task 1):
- Alvo do monkeypatch: _mem (módulo importado por qa/__init__.py) funciona
  porque qa/__init__.py faz ``from engine.integrations.mem import mem_context_hint``
  e o monkeypatch via setattr no módulo _mem NÃO intercepta binding local.
  Portanto patchamos ``engine.qa.mem_context_hint`` (namespace do handler).
- Os testes de degrade assertam sem forma vacuosa.
"""
from __future__ import annotations

import json
from typing import Any

import pytest


def _make_minimal_workflow_config() -> dict[str, Any]:
    return {"qa": {"enabled": True}}


def test_run_qa_injects_mem_context_in_handoff(tmp_path, monkeypatch):
    """run_qa injeta mem_context_hint no handoff JSON quando mem disponível."""
    import engine.qa as _qa

    # Patch no namespace do handler (onde o binding local vive após import).
    monkeypatch.setattr(
        _qa,
        "mem_context_hint",
        lambda root, query, **kw: "Memória relevante (mem find):\n  · [feedback] padrão-mvvm",
    )

    class _FakeScope:
        type = "feature"
        target = "minha-feature"
        paths: list = []

    class _FakeRunTree:
        run_id = "run-test-01"
        root = tmp_path / "run-01"
        snapshot_dir = tmp_path / "run-01" / "snapshot"
        findings_dir = tmp_path / "run-01" / "findings"

    fake_scope = _FakeScope()
    fake_tree = _FakeRunTree()
    fake_tree.root.mkdir(parents=True, exist_ok=True)
    fake_tree.snapshot_dir.mkdir(parents=True, exist_ok=True)
    fake_tree.findings_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(_qa, "resolve_scope", lambda *a, **kw: fake_scope)
    monkeypatch.setattr(_qa, "find_resumable_run", lambda *a, **kw: None)
    monkeypatch.setattr(_qa, "create_run_tree", lambda *a, **kw: fake_tree)
    monkeypatch.setattr(_qa, "snapshot_artefacts", lambda *a, **kw: [])
    monkeypatch.setattr(_qa, "_write_qa_report_skeleton", lambda *a, **kw: None)
    monkeypatch.setattr(_qa, "_maybe_alert_sensitive_drops", lambda *a, **kw: None)
    monkeypatch.setattr(_qa, "_compute_allowed_extras", lambda *a, **kw: ())

    _qa.run_qa(
        "minha-feature",
        project_root=tmp_path,
        workflow_config=_make_minimal_workflow_config(),
    )

    handoff_path = fake_tree.root / "conductor-handoff.json"
    assert handoff_path.exists(), "conductor-handoff.json não foi escrito"
    handoff = json.loads(handoff_path.read_text())
    assert "mem_context" in handoff, "campo mem_context ausente no handoff"
    assert "padrão-mvvm" in (handoff["mem_context"] or "")


def test_run_qa_handoff_sem_mem_context_quando_degrade(tmp_path, monkeypatch):
    """run_qa com mem indisponível: campo mem_context ausente ou None, sem crash."""
    import engine.qa as _qa

    # Spy: confirma que o caminho foi exercitado (não-vacuoso).
    hint_called = {"count": 0}

    def _fake_hint_none(*a: object, **kw: object) -> None:
        hint_called["count"] += 1
        return None

    monkeypatch.setattr(_qa, "mem_context_hint", _fake_hint_none)

    class _FakeScope:
        type = "feature"
        target = "feature-sem-mem"
        paths: list = []

    class _FakeRunTree:
        run_id = "run-test-02"
        root = tmp_path / "run-02"
        snapshot_dir = tmp_path / "run-02" / "snapshot"
        findings_dir = tmp_path / "run-02" / "findings"

    fake_scope = _FakeScope()
    fake_tree = _FakeRunTree()
    fake_tree.root.mkdir(parents=True, exist_ok=True)
    fake_tree.snapshot_dir.mkdir(parents=True, exist_ok=True)
    fake_tree.findings_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(_qa, "resolve_scope", lambda *a, **kw: fake_scope)
    monkeypatch.setattr(_qa, "find_resumable_run", lambda *a, **kw: None)
    monkeypatch.setattr(_qa, "create_run_tree", lambda *a, **kw: fake_tree)
    monkeypatch.setattr(_qa, "snapshot_artefacts", lambda *a, **kw: [])
    monkeypatch.setattr(_qa, "_write_qa_report_skeleton", lambda *a, **kw: None)
    monkeypatch.setattr(_qa, "_maybe_alert_sensitive_drops", lambda *a, **kw: None)
    monkeypatch.setattr(_qa, "_compute_allowed_extras", lambda *a, **kw: ())

    _qa.run_qa(
        "feature-sem-mem",
        project_root=tmp_path,
        workflow_config=_make_minimal_workflow_config(),
    )

    handoff_path = fake_tree.root / "conductor-handoff.json"
    assert handoff_path.exists()
    handoff = json.loads(handoff_path.read_text())
    # Degrade: campo pode ser None ou ausente — nunca causa crash.
    mem_ctx = handoff.get("mem_context")
    assert mem_ctx is None or isinstance(mem_ctx, str)
    # Prova não-vacuosa: o caminho foi exercitado.
    assert hint_called["count"] >= 1, (
        "mem_context_hint deve ser chamado pelo fluxo de run_qa"
    )
