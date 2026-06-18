"""A4 REPLAY (card-removal) — cancelar o apply-confirm após escolher remover
um card NÃO deve ter movido o snapshot pra .bak.

Bug original: _cards_remove fazia shutil.move(snap → .bak) durante o menu,
antes do apply-confirm. Cancelar deixava o snapshot removido sem a config
correspondente → drift → forge verify hard-fail.

M-201 (re-audit r2): _pending_card_removals NÃO pode ser persistido pelo
_save_draft — senão um resume recarrega a lista e re-dispara o leak.
"""
from __future__ import annotations

from pathlib import Path

from engine import reconfigure


def _seed_card_snapshot(project_root: Path, name: str) -> Path:
    from engine.utils.paths import cards_dir

    snap = cards_dir(project_root) / name
    snap.mkdir(parents=True)
    (snap / "card.yaml").write_text(f"name: {name}\nversion: 1\n")
    return snap


def test_cards_remove_does_not_move_bak_before_confirm(tmp_path, monkeypatch):
    project_root = tmp_path
    (project_root / ".claude" / "forge").mkdir(parents=True)
    snap = _seed_card_snapshot(project_root, "telemetry")
    working = {"cards": {"active": [{"name": "telemetry"}]}}

    # Mocka as perguntas: escolhe remover 'telemetry'.
    monkeypatch.setattr(
        reconfigure.question, "ask_multi", lambda *a, **k: ["telemetry"]
    )
    # resolve() sem erros de dependência (remoção permitida).
    monkeypatch.setattr(
        reconfigure, "resolve",
        lambda remaining: type("R", (), {"errors": []})(),
    )

    reconfigure._cards_remove(project_root, working)

    # INVARIANTE: o snapshot AINDA existe (move deferido pra pós-confirm);
    # working registra a intenção de remoção.
    assert snap.is_dir(), (
        "o snapshot NÃO deve ter sido movido pra .bak antes do confirm"
    )
    assert not snap.with_name("telemetry.bak").exists()
    assert "telemetry" not in [
        c["name"] for c in working["cards"]["active"]
    ], "working deve registrar a remoção (active atualizado)"
    assert "telemetry" in working.get("_pending_card_removals", [])


def test_save_draft_does_not_persist_pending_card_removals(tmp_path):
    """M-201: o draft no disco NÃO carrega _pending_card_removals — senão um
    resume recarregaria a lista e re-dispararia o move (replay)."""
    from engine.utils.yaml_io import read_yaml

    draft_path = tmp_path / ".reconfigure-draft.yaml"
    working = {
        "cards": {"active": [{"name": "keep"}]},
        "_pending_card_removals": ["telemetry"],
    }

    reconfigure._save_draft(draft_path, working)

    on_disk = read_yaml(draft_path)
    assert "_pending_card_removals" not in on_disk, (
        "draft persistido não pode carregar a lista de remoções pendentes — "
        "um resume re-executaria o move (M-201 replay)"
    )
    # O resto do working sobrevive normalmente.
    assert on_disk["cards"]["active"] == [{"name": "keep"}]
