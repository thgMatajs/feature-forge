"""Unit tests — engine.memory.distiller.

Drives the proposal queue lifecycle, fingerprint guards against re-queuing
vetoed proposals, and rejection record creation.
"""

from __future__ import annotations

import pytest

from engine.memory import MemoryError
from engine.memory import distiller
from engine.memory.distiller import DistillationProposal


def _make_proposal(id_: str = "P-001") -> DistillationProposal:
    return DistillationProposal(
        id=id_,
        kind="promote-to-l2",
        title="use-stateflow",
        description="Use MutableStateFlow for screen state",
        provenance=["auth"],
        confidence=0.8,
    )


def test_queue_proposal_appends(tmp_path):
    p = _make_proposal()
    distiller.queue_proposal(tmp_path, p)
    queue = distiller.read_proposals_queue(tmp_path)
    assert len(queue) == 1
    assert queue[0].id == "P-001"
    assert queue[0].title == "use-stateflow"


def test_queue_proposal_invalid_kind_raises(tmp_path):
    bad = DistillationProposal(
        id="P-x",
        kind="bogus-kind",
        title="x",
        description="d",
    )
    with pytest.raises(MemoryError):
        distiller.queue_proposal(tmp_path, bad)


def test_queue_proposal_empty_id_raises(tmp_path):
    bad = DistillationProposal(id="", kind="promote-to-l2", title="x", description="d")
    with pytest.raises(MemoryError):
        distiller.queue_proposal(tmp_path, bad)


def test_queue_proposal_duplicate_id_raises(tmp_path):
    p = _make_proposal()
    distiller.queue_proposal(tmp_path, p)
    with pytest.raises(MemoryError):
        distiller.queue_proposal(tmp_path, p)


def test_remove_from_queue_drains_id(tmp_path):
    distiller.queue_proposal(tmp_path, _make_proposal("P-1"))
    distiller.queue_proposal(tmp_path, _make_proposal("P-2"))
    distiller.remove_from_queue(tmp_path, "P-1")
    queue = distiller.read_proposals_queue(tmp_path)
    assert [p.id for p in queue] == ["P-2"]


def test_remove_from_queue_noop_for_missing(tmp_path):
    distiller.remove_from_queue(tmp_path, "ghost")
    assert distiller.read_proposals_queue(tmp_path) == []


def test_compute_proposal_fingerprint_stable():
    payload = {
        "type": "promote-to-l2",
        "name": "x",
        "description": "y",
        "provenance": {"feature-slugs": ["a"]},
    }
    f1 = distiller.compute_proposal_fingerprint(payload)
    f2 = distiller.compute_proposal_fingerprint(payload)
    assert f1 == f2 and len(f1) == 64


def test_record_rejection_persists(tmp_path):
    fingerprint = "a" * 64
    distiller.record_rejection(
        tmp_path,
        fingerprint,
        rationale="not aligned with project",
        proposal_snapshot={
            "id": "P-001",
            "type": "promote-to-l2",
            "name": "x",
            "description": "y",
            "provenance": {"feature-slugs": ["a"]},
        },
    )
    assert distiller.is_fingerprint_rejected(tmp_path, fingerprint) is True


def test_record_rejection_invalid_fingerprint_raises(tmp_path):
    with pytest.raises(MemoryError):
        distiller.record_rejection(tmp_path, "short")


def test_record_rejection_idempotent(tmp_path):
    fingerprint = "b" * 64
    distiller.record_rejection(tmp_path, fingerprint, rationale="r")
    # Second call must not raise nor duplicate the entry.
    distiller.record_rejection(tmp_path, fingerprint, rationale="r")
    assert distiller.is_fingerprint_rejected(tmp_path, fingerprint) is True


def test_queue_proposal_skips_when_rejected(tmp_path):
    p = _make_proposal()
    # Compute the fingerprint that queue_proposal will derive.
    fingerprint = distiller.compute_proposal_fingerprint(
        {
            "type": p.kind,
            "name": p.title,
            "description": p.description,
            "provenance": {"feature-slugs": list(p.provenance)},
        }
    )
    distiller.record_rejection(tmp_path, fingerprint, rationale="vetoed")
    # Now queue — should silently skip.
    distiller.queue_proposal(tmp_path, p)
    assert distiller.read_proposals_queue(tmp_path) == []


# ── Task 2 (6b): re-rota dos branches de conhecimento ────────────────────


def test_apply_promote_to_l2_calls_mem_inbox_add(tmp_path, monkeypatch):
    """promote-to-l2 deve chamar mem_inbox_add com campos mapeados (D3)."""
    import engine.memory.distiller as _dist
    called: dict = {}

    def _fake_inbox_add(project_root, title, body, mem_type, **kw):
        called["title"] = title
        called["body"] = body
        called["mem_type"] = mem_type
        called["importance"] = kw.get("importance")
        called["tags"] = kw.get("tags")
        called["source"] = kw.get("source")
        called["origin"] = kw.get("origin")
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=True, data="01ABC")

    monkeypatch.setattr(_dist, "mem_inbox_add", _fake_inbox_add)

    p = DistillationProposal(
        id="P-001",
        kind="promote-to-l2",
        title="use-stateflow",
        description="Use MutableStateFlow para screen state",
        provenance=["auth", "profile"],
        confidence=0.8,
        fingerprint="",
    )
    _dist.apply_proposal_to_l2(tmp_path, p)

    assert called["title"] == "use-stateflow"
    assert called["body"] == "Use MutableStateFlow para screen state"
    assert called["mem_type"] == "reference"
    assert called["importance"] == 4  # round(0.8 * 4) + 1 = round(3.2) + 1 = 4, clamp 1-5
    assert called["tags"] == "auth,profile"
    assert called["source"] == "forge-evolve:P-001"
    assert called["origin"] == "manual"


def test_apply_l1_to_l2_promotion_calls_mem_inbox_add(tmp_path, monkeypatch):
    """l1-to-l2-promotion (alias) segue o mesmo caminho que promote-to-l2."""
    import engine.memory.distiller as _dist
    called: list = []

    def _fake_inbox_add(project_root, title, body, mem_type, **kw):
        called.append(True)
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=True, data="01XYZ")

    monkeypatch.setattr(_dist, "mem_inbox_add", _fake_inbox_add)

    p = DistillationProposal(
        id="P-002",
        kind="l1-to-l2-promotion",
        title="mvvm-pattern",
        description="Padrão MVVM consistente",
        provenance=["onboarding"],
        confidence=0.7,
    )
    _dist.apply_proposal_to_l2(tmp_path, p)
    assert len(called) == 1


def test_apply_consolidate_l2_calls_mem_inbox_add(tmp_path, monkeypatch):
    """consolidate-l2 colapsa no mesmo caminho (merge-semantic moot com L2 abandonado)."""
    import engine.memory.distiller as _dist
    called: list = []

    def _fake_inbox_add(project_root, title, body, mem_type, **kw):
        called.append(True)
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=True, data="01DEF")

    monkeypatch.setattr(_dist, "mem_inbox_add", _fake_inbox_add)

    p = DistillationProposal(
        id="P-003",
        kind="consolidate-l2",
        title="repo-pattern",
        description="Padrão de repositório unificado",
        provenance=["payment", "cart"],
        confidence=0.9,
    )
    _dist.apply_proposal_to_l2(tmp_path, p)
    assert len(called) == 1


def test_apply_knowledge_does_not_call_l2_add_entry(tmp_path, monkeypatch):
    """6c: a invariante de 6b ('conhecimento não chama l2.add_entry') vira mais
    forte — add_entry nem existe mais em l2 após o orphan-cleanup."""
    import engine.memory.l2 as _l2
    assert not hasattr(_l2, "add_entry"), (
        "add_entry deveria ter sido removida de l2 em 6c — a invariante de 6b "
        "('conhecimento não escreve L2 direto') é garantida por inexistência."
    )


def test_apply_knowledge_raises_on_mem_inbox_add_failure(tmp_path, monkeypatch):
    """Se mem_inbox_add retorna ok=False, raise MemoryError (não drena a queue)."""
    import engine.memory.distiller as _dist
    from engine.memory import MemoryError as _MemError

    def _fake_inbox_add(project_root, title, body, mem_type, **kw):
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=False, data=None, message="mem indisponível. Três caminhos: ...")

    monkeypatch.setattr(_dist, "mem_inbox_add", _fake_inbox_add)

    p = DistillationProposal(
        id="P-004",
        kind="promote-to-l2",
        title="t",
        description="d",
        provenance=["auth"],
        confidence=0.5,
    )
    # Enfileira primeiro pra testar que não é drenada
    _dist.queue_proposal(tmp_path, p)

    with pytest.raises(_MemError):
        _dist.apply_proposal_to_l2(tmp_path, p)

    # Queue não deve ter sido drenada (raise antes do remove_from_queue)
    queue = _dist.read_proposals_queue(tmp_path)
    assert any(q.id == "P-004" for q in queue), "queue foi drenada indevidamente"


def test_apply_knowledge_importance_clamp(tmp_path, monkeypatch):
    """importance via round(confidence*4)+1, clamp [1,5]. Midpoint 0.5 → 3
    (não 2 — a fórmula evita o banker's rounding de round(0.5*5)==round(2.5)==2)."""
    import engine.memory.distiller as _dist
    importances: list = []

    def _fake_inbox_add(project_root, title, body, mem_type, **kw):
        importances.append(kw.get("importance"))
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=True, data="01JKL")

    monkeypatch.setattr(_dist, "mem_inbox_add", _fake_inbox_add)

    for confidence, expected in ((0.0, 1), (1.0, 5), (0.5, 3)):
        _dist.apply_proposal_to_l2(
            tmp_path,
            DistillationProposal(
                id=f"P-conf{int(confidence*10)}",
                kind="promote-to-l2",
                title="t",
                description="d",
                confidence=confidence,
            ),
        )

    assert importances == [1, 5, 3]


# ── Task 4 (6c): cleanup de órfãos ────────────────────────────────────────────


def test_apply_consolidate_l2_does_not_exist() -> None:
    """_apply_consolidate_l2 foi deletada em 6c — não deve existir mais."""
    import engine.memory.distiller as _dist
    assert not hasattr(_dist, "_apply_consolidate_l2"), (
        "_apply_consolidate_l2 ainda existe em distiller.py; "
        "deveria ter sido removida na Task 4 de 6c (W-ROUTE orphan-cleanup)."
    )


def test_distiller_does_not_import_add_entry() -> None:
    """distiller.py não deve importar add_entry de l2 (import órfão removido em 6c)."""
    import ast
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    distiller_src = (repo_root / "engine" / "memory" / "distiller.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(distiller_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "l2" in node.module:
                imported_names = [alias.name for alias in node.names]
                assert "add_entry" not in imported_names, (
                    f"distiller.py ainda importa 'add_entry' de l2 "
                    f"(linha {node.lineno}); deveria ter sido removido em 6c."
                )


def test_distiller_does_not_import_l2entry() -> None:
    """WR-01: distiller.py não deve importar L2Entry (morto após deletar _apply_consolidate_l2).

    L2Entry era usado APENAS em _apply_consolidate_l2 (instanciação + anotações locais).
    Após a deleção da função, o import fica órfão.
    """
    import ast
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    distiller_src = (repo_root / "engine" / "memory" / "distiller.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(distiller_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "l2" in node.module:
                imported_names = [alias.name for alias in node.names]
                assert "L2Entry" not in imported_names, (
                    f"distiller.py ainda importa 'L2Entry' de l2 "
                    f"(linha {node.lineno}); import morto após remover "
                    f"_apply_consolidate_l2 — deveria ter sido removido em 6c."
                )


def test_apply_forget_l1_unchanged_no_mem_call(tmp_path, monkeypatch):
    """forget-l1 NÃO toca mem_inbox_add — branch estrutural inalterado."""
    import engine.memory.distiller as _dist

    inbox_add_calls: list = []

    def _spy_inbox_add(*args, **kwargs):
        inbox_add_calls.append(args)
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=True, data="x")

    monkeypatch.setattr(_dist, "mem_inbox_add", _spy_inbox_add)

    # forget-l1 exige target — simula via payload
    p = DistillationProposal(
        id="P-forget",
        kind="forget-l1",
        title="archive auth",
        description="feature obsoleta",
        provenance=["auth"],
        payload={"target": "auth"},
    )
    # O _apply_forget_l1 pode falhar sem estrutura de L1 real; catching MemoryError
    # (target não existe) é ok — o importante é que inbox_add não foi chamado.
    try:
        _dist.apply_proposal_to_l2(tmp_path, p)
    except Exception:
        pass

    assert inbox_add_calls == [], "forget-l1 não deve chamar mem_inbox_add"
