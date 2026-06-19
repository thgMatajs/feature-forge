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


def test_apply_card_removals_derives_from_disk_vs_config(tmp_path):
    """C-22 (PR20-R1): _apply_card_removals move pra .bak os snapshots ausentes
    do cards.active final — fonte de verdade = diff disk-vs-config.

    Simula o cenário de resume: o `working` reconstruído do draft NÃO tem
    `_pending_card_removals`, mas o snapshot órfão (removido da config) ainda
    está em disco. A derivação por diff pega o órfão mesmo sem a lista transiente.
    """
    project_root = tmp_path
    (project_root / ".claude" / "forge").mkdir(parents=True)
    _seed_card_snapshot(project_root, "telemetry")  # órfão (removido da config)
    _seed_card_snapshot(project_root, "keep")       # ainda ativo
    # working SEM _pending_card_removals (resume): config final só tem 'keep'.
    working = {"cards": {"active": [{"name": "keep"}]}}

    reconfigure._apply_card_removals(project_root, working)

    from engine.utils.paths import cards_dir
    root = cards_dir(project_root)
    assert not (root / "telemetry").exists(), "órfão deveria ter ido pra .bak"
    assert (root / "telemetry.bak").is_dir(), "snapshot órfão preservado como .bak"
    assert (root / "keep").is_dir(), "card ativo NÃO deve ser tocado"
    assert not (root / "keep.bak").exists()


def test_apply_card_removals_idempotent_when_bak_exists(tmp_path):
    """C-22 (B2): se o destino .bak já existe, remove o velho antes do move —
    sem aninhar name/ dentro de name.bak/ (B2 nesting bug)."""
    project_root = tmp_path
    (project_root / ".claude" / "forge").mkdir(parents=True)
    from engine.utils.paths import cards_dir

    root = cards_dir(project_root)
    _seed_card_snapshot(project_root, "telemetry")
    # .bak velho de uma remoção anterior do mesmo nome.
    old_bak = root / "telemetry.bak"
    old_bak.mkdir(parents=True)
    (old_bak / "stale.txt").write_text("old", encoding="utf-8")

    working = {"cards": {"active": []}}
    reconfigure._apply_card_removals(project_root, working)

    assert (root / "telemetry.bak").is_dir()
    # Sem nesting: não existe telemetry.bak/telemetry/
    assert not (root / "telemetry.bak" / "telemetry").exists()
    # O .bak novo carrega o card.yaml atual, não o stale velho.
    assert (root / "telemetry.bak" / "card.yaml").is_file()
    assert not (root / "telemetry").exists()


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
