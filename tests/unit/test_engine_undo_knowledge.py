"""Re-rota do `forge undo` de evolve-apply de conhecimento (W-ROUTE 6d Task 3).

Regression + honest-failure + preservação do path L2 legado para o
`_undo_evolve`. Antes de 6d, um undo de conhecimento era no-op silencioso:
o `_undo_evolve` sempre ia pro L2, mas o apply de conhecimento nunca mexeu
em L2 (foi pro `mem inbox add`). Pós-6d, o evento `evolve-apply` carrega
`routed-to: mem-inbox` + `mem-inbox-id`, e o undo lê de volta pra chamar
`mem inbox reject <id>`.

Os testes monkeypatcham nomes no namespace do módulo `undo`
(`_evolve_apply_event_for`, `mem_inbox_reject`, `l2_remove_entry`,
`memory_l2_path`) — esses nomes precisam existir como import direto no
namespace do módulo pra o monkeypatch pegar.
"""

from __future__ import annotations

from engine import undo as und
from engine.integrations.mem import MemQuery


def _ok_memquery() -> MemQuery:
    return MemQuery(ok=True, data={"status": "rejected"})


def _fail_memquery() -> MemQuery:
    return MemQuery(ok=False, data=None, message="mem indisponível.")


def test_undo_evolve_knowledge_rejects_mem_inbox(tmp_path, monkeypatch):
    # Dado um evento evolve-apply roteado pro mem-inbox, o undo deve chamar
    # mem_inbox_reject com o id capturado — NÃO l2_remove_entry (no-op atual).
    monkeypatch.setattr(
        und,
        "_evolve_apply_event_for",
        lambda root, pid: {
            "proposal-id": pid,
            "routed-to": "mem-inbox",
            "mem-inbox-id": "01INBOXID",
        },
    )
    reject_calls = []
    monkeypatch.setattr(
        und,
        "mem_inbox_reject",
        lambda root, iid: (reject_calls.append(iid) or _ok_memquery()),
    )
    l2_calls = []
    monkeypatch.setattr(und, "l2_remove_entry", lambda *a, **k: l2_calls.append(a))
    monkeypatch.setattr(und.question, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(und, "_append_undo_log", lambda *a, **k: None)

    ok = und._undo_evolve(tmp_path, "P-001")
    assert ok is True
    assert reject_calls == ["01INBOXID"]
    assert l2_calls == []  # caminho L2 NÃO é tocado pra knowledge


def test_undo_evolve_knowledge_reject_failure_reports_honest(tmp_path, monkeypatch):
    # reject falha (mem degrade OU candidato já promovido) → undo retorna False
    # e NÃO grava undo-log de sucesso (honest-failure, load-bearing num recovery).
    monkeypatch.setattr(
        und,
        "_evolve_apply_event_for",
        lambda root, pid: {
            "proposal-id": pid,
            "routed-to": "mem-inbox",
            "mem-inbox-id": "01INBOXID",
        },
    )
    monkeypatch.setattr(
        und,
        "mem_inbox_reject",
        lambda root, iid: _fail_memquery(),  # ok=False
    )
    undo_logs = []
    monkeypatch.setattr(
        und,
        "_append_undo_log",
        lambda *a, **k: undo_logs.append(k.get("target")),
    )
    monkeypatch.setattr(und.question, "confirm", lambda *a, **k: True)

    ok = und._undo_evolve(tmp_path, "P-001")
    assert ok is False
    assert undo_logs == []  # NÃO grava undo-log de sucesso


def test_undo_evolve_legacy_event_uses_l2_path(tmp_path, monkeypatch):
    # evento sem mem-inbox-id (pré-6d / kind não-conhecimento) → fallback L2.
    monkeypatch.setattr(und, "_evolve_apply_event_for", lambda root, pid: None)
    monkeypatch.setattr(und.question, "confirm", lambda *a, **k: True)
    removed = []
    monkeypatch.setattr(und, "l2_remove_entry", lambda root, tid: removed.append(tid))
    monkeypatch.setattr(und, "_append_undo_log", lambda *a, **k: None)
    # L2 path exige l2_path existente — mocke memory_l2_path pra um arquivo tmp.
    l2 = tmp_path / "L2.yaml"
    l2.write_text("entries: []\n")
    monkeypatch.setattr(und, "memory_l2_path", lambda root: l2)

    ok = und._undo_evolve(tmp_path, "P-001")
    assert ok is True
    assert removed == ["L2-001"]  # mangling P- → L2- preservado no path legado
