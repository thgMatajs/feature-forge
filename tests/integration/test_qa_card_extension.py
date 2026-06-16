"""Integration — card overlay declarando `qa-extensions`.

Wave 7 Task 7.1: stubs mínimos (happy path canon + colisão canon×local).

Wave 8 Task 8.5: cobertura adicional do mecanismo qa-extensions:

- ``extensions_disabled`` skip respeitado (Regra 4 bypass quando auditor
  nomeado no toggle de workflow-config)
- Card local com qa-extensions carrega + manifest preserva ``qa-extensions``
  no raw payload (consumido pelo conductor pra registrar auditor extra)

Anti-padrão: testar shape do auditor LLM em execução (delegado a fixtures
sintéticas + Phase 4 synthesis tests). Aqui foco é loader + validator.

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
            (em `.claude/forge/cards/local/<name>/`).
        name: card name.
        auditor_name: nome do auditor declarado em qa-extensions.auditors[].
        provides: lista de capability labels válidas no catálogo canon.

    Returns:
        Diretório do card criado.
    """
    if origin == "canon":
        card_dir = project / ".claude" / "cards" / name
    else:
        # Task 0.8 (v1.3): local overlay vive em .claude/forge/cards/local/.
        card_dir = project / ".claude" / "forge" / "cards" / "local" / name
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


# ──────────────────────────────────────────────────────────────────────────
# Wave 8.5 — extensions_disabled toggle + manifest preserva qa-extensions
# ──────────────────────────────────────────────────────────────────────────


def test_local_card_with_qa_extensions_loads_and_preserves_raw_payload(
    qa_ext_project: Path,
) -> None:
    """Local card declara qa-extensions; manifest.raw preserva o bloco.

    Contrato: conductor (Phase 1/2) lê ``manifest.raw["qa-extensions"]``
    pra descobrir auditores extras a registrar. Sem isso, overlay vira
    no-op — confirma round-trip canon → manifest → consumer.
    """
    from engine.cards.loader import load_all_cards

    _write_card_with_qa_extension(
        qa_ext_project,
        origin="local",
        name="local-overlay-card",
        auditor_name="local-auditor-stub",
        provides=["serialization-json"],
    )

    manifests = load_all_cards(qa_ext_project)
    local_card = next(m for m in manifests if m.name == "local-overlay-card")
    assert local_card.origin == "local"

    qa_ext = local_card.raw.get("qa-extensions")
    assert isinstance(qa_ext, dict), (
        "manifest.raw deve preservar qa-extensions pra consumer downstream"
    )
    auditors = qa_ext.get("auditors", [])
    assert len(auditors) == 1
    assert auditors[0]["name"] == "local-auditor-stub"
    assert auditors[0]["phase"] == "static"


def test_validate_qa_extensions_skips_capability_check_for_disabled_auditor(
    qa_ext_project: Path,
) -> None:
    """``extensions_disabled`` faz validator pular Regra 4 (capability check).

    Cenário: auditor nomeado em ``qa.extensions.disabled`` no workflow-
    config + requires uma capability INEXISTENTE no catálogo. Sem o
    toggle, validate_qa_extensions raise. Com o toggle, retorna sem erro
    (auditor desabilitado não precisa do catálogo coerente — ele não vai
    rodar).
    """
    from validators.validate_qa_extensions import (
        QAExtensionsValidationError,
        validate_qa_extensions,
    )

    card_dir = _write_card_with_qa_extension(
        qa_ext_project,
        origin="canon",
        name="disabled-card",
        auditor_name="opt-out-auditor",
        provides=["kotlin"],
    )

    # Mutate card payload: requires capability bogus que NÃO existe.
    card_yaml = card_dir / "card.yaml"
    data = yaml.safe_load(card_yaml.read_text(encoding="utf-8"))
    data["qa-extensions"]["auditors"][0]["requires"] = ["bogus-capability-zzz"]
    card_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")

    # Sem disabled → Regra 4 dispara (capability inexistente)
    with pytest.raises(QAExtensionsValidationError) as exc_info:
        validate_qa_extensions(
            card_path=card_yaml,
            card_data=data,
            other_cards={},
            project_root=qa_ext_project,
        )
    assert "bogus-capability-zzz" in str(exc_info.value)

    # Com disabled={opt-out-auditor} → Regra 4 pula, validator passa silencioso
    validate_qa_extensions(
        card_path=card_yaml,
        card_data=data,
        other_cards={},
        project_root=qa_ext_project,
        extensions_disabled={"opt-out-auditor"},
    )  # não raise
