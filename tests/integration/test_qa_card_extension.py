"""Integration — card overlay declarando `qa-extensions` carrega no loader.

Wave 7 Task 7.1: stub mínimo confirmando que o cascade load_all_cards
exerce o hook `validate_qa_extensions` overlay-aware. Edge cases mais
profundos (colisão canon×local em auditor name, requires capability
ausente no catálogo) entram em Wave 8.5 com fixtures dedicadas.

Marker: integration (slow). Excluído da rapid CI lane.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.integration


def _write_card_with_qa_extension(
    project: Path,
    *,
    origin: str,
    name: str,
    auditor_name: str,
    provides: list[str],
) -> Path:
    """Escreve um card (canon ou local overlay) com bloco `qa-extensions`.

    Args:
        project: project root (tmp).
        origin: ``"canon"`` (em `.claude/cards/<name>/`) ou ``"local"``
            (em `.claude/cards/local/<name>/`).
        name: card name.
        auditor_name: nome do auditor declarado em qa-extensions.auditors[].
        provides: lista de capability labels válidas no catálogo canon.

    Returns:
        Diretório do card criado.
    """
    if origin == "canon":
        card_dir = project / ".claude" / "cards" / name
    else:
        card_dir = project / ".claude" / "cards" / "local" / name
    card_dir.mkdir(parents=True, exist_ok=True)

    # Cria stub do agent .md referenciado em contributes.agents (Regra 3).
    agent_rel = "agent-contributions/qa-stub.md"
    agent_path = card_dir / agent_rel
    agent_path.parent.mkdir(parents=True, exist_ok=True)
    agent_path.write_text("# qa-stub\n\nstub para teste.\n", encoding="utf-8")

    data = {
        "schema-version": 1,
        "identity": {
            "name": name,
            "version": "1.0.0",
            "description": f"stub {origin}",
            "category": "language",
            "maturity": "experimental",
        },
        "provides": provides,
        "requires": [],
        "conflicts-with": [],
        "qa-extensions": {
            "auditors": [
                {
                    "name": auditor_name,
                    "phase": "static",
                    "contributes": {"agents": [agent_rel]},
                    "requires": [],
                }
            ]
        },
    }
    (card_dir / "card.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (card_dir / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    return card_dir


@pytest.fixture
def qa_ext_project(tmp_path: Path) -> Path:
    proj = tmp_path / "qa-ext-pilot"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "cards").mkdir(parents=True)
    (proj / ".claude" / "inventory").mkdir(parents=True)
    return proj


def test_card_with_qa_extensions_loads_without_collision(qa_ext_project: Path) -> None:
    """Happy path: card canon declara qa-extensions, loader retorna sem raise."""
    from engine.cards.loader import load_all_cards

    _write_card_with_qa_extension(
        qa_ext_project,
        origin="canon",
        name="testing-stub-card",
        auditor_name="qa-stub-auditor",
        provides=["kotlin"],
    )

    manifests = load_all_cards(qa_ext_project)
    names = {m.name for m in manifests}
    assert "testing-stub-card" in names


def test_canon_local_auditor_name_collision_raises(qa_ext_project: Path) -> None:
    """Approach A (Decisão 28): mesmo auditor name em canon AND local → hard fail.

    Propaga `QAExtensionsCollisionError` do validator pelo loader (Task 7.1
    hook). Sem merge silencioso.
    """
    from engine.cards.loader import load_all_cards
    from validators.validate_qa_extensions import QAExtensionsCollisionError

    _write_card_with_qa_extension(
        qa_ext_project,
        origin="canon",
        name="canon-stub-card",
        auditor_name="shared-auditor-name",
        provides=["kotlin"],
    )
    _write_card_with_qa_extension(
        qa_ext_project,
        origin="local",
        name="local-stub-card",
        auditor_name="shared-auditor-name",
        provides=["jvm-language"],
    )

    with pytest.raises(QAExtensionsCollisionError):
        load_all_cards(qa_ext_project)
