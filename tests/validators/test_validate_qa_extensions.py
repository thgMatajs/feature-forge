"""Tests for validators/validate_qa_extensions.py — overlay-aware (Gap 5).

Schema fonte: docs/schemas/qa-extensions.md.
Política colisão: canon×local → hard fail (Decisão 28 Approach A).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from validators.validate_qa_extensions import (
    QAExtensionsCollisionError,
    QAExtensionsValidationError,
    validate_qa_extensions,
)


def _agent_file(card_dir: Path, name: str = "auditor-visual-fidelity.md") -> str:
    """Cria um agent prompt fictício no diretório do card e devolve o path relativo."""
    agent_path = card_dir / name
    agent_path.write_text("# placeholder auditor prompt\n", encoding="utf-8")
    return name


def _card_dir(tmp_path: Path, name: str = "screens-defined") -> Path:
    """Cria estrutura cards/<name>/ e devolve o diretório do card."""
    cards_root = tmp_path / "cards"
    cards_root.mkdir(parents=True, exist_ok=True)
    card_dir = cards_root / name
    card_dir.mkdir(parents=True, exist_ok=True)
    return card_dir


def _minimal_card_data(
    *,
    name: str = "visual-fidelity",
    phase: str = "static",
    agent_rel: str = "auditor-visual-fidelity.md",
    requires: list[str] | None = None,
) -> dict:
    """Card top-level com 1 auditor válido shape-wise."""
    return {
        "identity": {"name": "screens-defined"},
        "qa-extensions": {
            "auditors": [
                {
                    "name": name,
                    "phase": phase,
                    "contributes": {"agents": [agent_rel]},
                    "requires": requires or [],
                }
            ]
        },
    }


# --- Happy path + opt-out ---------------------------------------------------


def test_happy_path_single_auditor(tmp_path: Path):
    """Card canon declara 1 auditor static válido — sem raise."""
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    validate_qa_extensions(card, _minimal_card_data(), project_root=tmp_path)


def test_qa_extensions_absent_returns_silently(tmp_path: Path):
    """Card sem campo qa-extensions: não raise (campo opcional)."""
    card_dir = _card_dir(tmp_path)
    card = card_dir / "card.yaml"
    validate_qa_extensions(
        card, {"identity": {"name": "screens-defined"}}, project_root=tmp_path
    )


def test_qa_extensions_empty_dict_returns_silently(tmp_path: Path):
    """Card com qa-extensions: {} (sem auditors) é equivalente a ausente."""
    card_dir = _card_dir(tmp_path)
    card = card_dir / "card.yaml"
    validate_qa_extensions(
        card,
        {"identity": {"name": "screens-defined"}, "qa-extensions": {}},
        project_root=tmp_path,
    )


# --- Defensive type guards (lição Task 2.1 HI-01) ---------------------------


def test_qa_extensions_must_be_dict(tmp_path: Path):
    """qa-extensions: 'string' → raise (não AttributeError)."""
    card_dir = _card_dir(tmp_path)
    card = card_dir / "card.yaml"
    with pytest.raises(QAExtensionsValidationError, match="qa-extensions deve ser dict"):
        validate_qa_extensions(
            card,
            {"identity": {"name": "x"}, "qa-extensions": "not a dict"},
            project_root=tmp_path,
        )


def test_auditors_must_be_list(tmp_path: Path):
    """qa-extensions.auditors = 'string' → raise."""
    card_dir = _card_dir(tmp_path)
    card = card_dir / "card.yaml"
    data = {"qa-extensions": {"auditors": "not a list"}}
    with pytest.raises(QAExtensionsValidationError, match="auditors deve ser lista"):
        validate_qa_extensions(card, data, project_root=tmp_path)


def test_auditor_entry_must_be_dict(tmp_path: Path):
    """Cada item em auditors[] deve ser mapping."""
    card_dir = _card_dir(tmp_path)
    card = card_dir / "card.yaml"
    data = {"qa-extensions": {"auditors": ["not-a-dict"]}}
    with pytest.raises(QAExtensionsValidationError, match="auditor.*deve ser mapping"):
        validate_qa_extensions(card, data, project_root=tmp_path)


def test_contributes_must_be_dict(tmp_path: Path):
    """auditor.contributes = list → raise."""
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    data = _minimal_card_data()
    data["qa-extensions"]["auditors"][0]["contributes"] = ["not-a-dict"]
    with pytest.raises(
        QAExtensionsValidationError, match="contributes deve ser mapping"
    ):
        validate_qa_extensions(card, data, project_root=tmp_path)


def test_requires_must_be_list(tmp_path: Path):
    """auditor.requires = 'string' → raise."""
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    data = _minimal_card_data()
    data["qa-extensions"]["auditors"][0]["requires"] = "screens-defined"
    with pytest.raises(QAExtensionsValidationError, match="requires deve ser lista"):
        validate_qa_extensions(card, data, project_root=tmp_path)


# --- Regra 1 indireta: name obrigatório -------------------------------------


def test_auditor_without_name_fails(tmp_path: Path):
    """Auditor sem campo name → raise."""
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    data = _minimal_card_data()
    del data["qa-extensions"]["auditors"][0]["name"]
    with pytest.raises(QAExtensionsValidationError, match="sem campo `name`"):
        validate_qa_extensions(card, data, project_root=tmp_path)


# --- Regra 2: phase enum strict ---------------------------------------------


def test_phase_enum_strict_static(tmp_path: Path):
    """phase='static' aceita."""
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    validate_qa_extensions(
        card, _minimal_card_data(phase="static"), project_root=tmp_path
    )


def test_phase_enum_strict_generative(tmp_path: Path):
    """phase='generative' aceita."""
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    validate_qa_extensions(
        card, _minimal_card_data(phase="generative"), project_root=tmp_path
    )


def test_phase_invalid_value_fails(tmp_path: Path):
    """phase='sandbox' (Phase 3 keyword core-only) → raise nomeando os 2 valores válidos."""
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    with pytest.raises(QAExtensionsValidationError, match=r"phase=.+inv.lida"):
        validate_qa_extensions(
            card, _minimal_card_data(phase="sandbox"), project_root=tmp_path
        )


# --- Regra 3: agents existem ------------------------------------------------


def test_agent_path_missing_fails(tmp_path: Path):
    """contributes.agents aponta arquivo inexistente → raise."""
    card_dir = _card_dir(tmp_path)
    # NÃO cria o agent file — path resolve mas não existe.
    card = card_dir / "card.yaml"
    with pytest.raises(QAExtensionsValidationError, match="agent inexistente"):
        validate_qa_extensions(
            card, _minimal_card_data(agent_rel="missing-agent.md"), project_root=tmp_path
        )


# --- Regra 4: requires capability no catálogo -------------------------------


def test_requires_capability_missing_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """requires aponta capability fora do catálogo → raise."""
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    data = _minimal_card_data(requires=["non-existent-capability"])

    # Stub catalog: vazio (zero labels).
    from validators import validate_qa_extensions as mod

    def _fake_load_catalog(_root: Path):
        class _Cat:
            active = frozenset()

        return _Cat()

    monkeypatch.setattr(mod, "load_catalog", _fake_load_catalog)
    with pytest.raises(
        QAExtensionsValidationError, match="requires capability.*n.o declarada"
    ):
        validate_qa_extensions(card, data, project_root=tmp_path)


def test_requires_capability_present_in_catalog_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """requires presente no catálogo efetivo → passa."""
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    data = _minimal_card_data(requires=["screens-defined"])

    from validators import validate_qa_extensions as mod

    def _fake_load_catalog(_root: Path):
        class _Cat:
            active = frozenset({"screens-defined"})

        return _Cat()

    monkeypatch.setattr(mod, "load_catalog", _fake_load_catalog)
    validate_qa_extensions(card, data, project_root=tmp_path)  # no raise


# --- Regra 1: colisão canon×local hard fail ---------------------------------


def test_collision_canon_local_raises_QAExtensionsCollisionError(tmp_path: Path):
    """2 cards declarando mesmo auditor name → QAExtensionsCollisionError nomeando ambos paths."""
    canon_card_dir = _card_dir(tmp_path, name="screens-defined")
    _agent_file(canon_card_dir)
    canon_card = canon_card_dir / "card.yaml"

    local_card_dir = _card_dir(tmp_path, name="custom-screens")
    _agent_file(local_card_dir)
    local_card = local_card_dir / "card.yaml"

    canon_data = _minimal_card_data(name="visual-fidelity")
    local_data = _minimal_card_data(name="visual-fidelity")

    other_cards = {str(local_card): local_data}

    with pytest.raises(QAExtensionsCollisionError) as excinfo:
        validate_qa_extensions(
            canon_card, canon_data, other_cards=other_cards, project_root=tmp_path
        )

    msg = str(excinfo.value)
    assert "visual-fidelity" in msg
    assert str(canon_card) in msg
    assert str(local_card) in msg


def test_collision_error_is_validation_subclass():
    """QAExtensionsCollisionError herda de QAExtensionsValidationError (gate único pro caller)."""
    assert issubclass(QAExtensionsCollisionError, QAExtensionsValidationError)


def test_no_collision_when_other_card_has_different_name(tmp_path: Path):
    """Auditor names distintos em 2 cards → sem raise."""
    canon_card_dir = _card_dir(tmp_path, name="screens-defined")
    _agent_file(canon_card_dir)
    canon_card = canon_card_dir / "card.yaml"

    local_card_dir = _card_dir(tmp_path, name="custom")
    _agent_file(local_card_dir)
    local_card = local_card_dir / "card.yaml"

    canon_data = _minimal_card_data(name="visual-fidelity")
    local_data = _minimal_card_data(name="analytics-event-coverage")

    other_cards = {str(local_card): local_data}
    validate_qa_extensions(
        canon_card, canon_data, other_cards=other_cards, project_root=tmp_path
    )


# --- Regra 5: extensions.disabled skip --------------------------------------


def test_extensions_disabled_skips_capability_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Auditor cujo name está em extensions_disabled passa mesmo com requires fora do catálogo.

    Disabled = runtime toggle (não roda) → não força capability check (Regra 5).
    Validação estrutural continua (defensive).
    """
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    data = _minimal_card_data(
        name="visual-fidelity", requires=["non-existent-capability"]
    )

    from validators import validate_qa_extensions as mod

    def _fake_load_catalog(_root: Path):
        class _Cat:
            active = frozenset()

        return _Cat()

    monkeypatch.setattr(mod, "load_catalog", _fake_load_catalog)

    # Com disabled vazio → raise.
    with pytest.raises(QAExtensionsValidationError, match="requires capability"):
        validate_qa_extensions(card, data, project_root=tmp_path)

    # Com auditor desabilitado → não raise (Regra 5).
    validate_qa_extensions(
        card,
        data,
        project_root=tmp_path,
        extensions_disabled={"visual-fidelity"},
    )


def test_extensions_disabled_still_enforces_structural_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Disabled NÃO suprime defensive guards — phase enum continua hard fail.

    Lição: skip de Regra 5 é só pra capability lookup, não pra shape.
    """
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    data = _minimal_card_data(name="visual-fidelity", phase="sandbox")

    with pytest.raises(QAExtensionsValidationError, match=r"phase=.+inv.lida"):
        validate_qa_extensions(
            card,
            data,
            project_root=tmp_path,
            extensions_disabled={"visual-fidelity"},
        )


# --- WR-01: Regra 1 intra-card collision ------------------------------------


def test_intra_card_name_collision_fails(tmp_path: Path):
    """Mesmo `name` declarado 2x no MESMO card → QAExtensionsCollisionError.

    Spec §6.3: "name único cross canon ∪ local" — cross inclui intra-card
    como subset trivial. Regra 1 deve fechar este buraco antes do loader
    Task 7.1.
    """
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    data = {
        "identity": {"name": "screens-defined"},
        "qa-extensions": {
            "auditors": [
                {
                    "name": "visual-fidelity",
                    "phase": "static",
                    "contributes": {"agents": ["auditor-visual-fidelity.md"]},
                    "requires": [],
                },
                {
                    "name": "visual-fidelity",
                    "phase": "generative",
                    "contributes": {"agents": ["auditor-visual-fidelity.md"]},
                    "requires": [],
                },
            ]
        },
    }
    with pytest.raises(QAExtensionsCollisionError, match="intra-card"):
        validate_qa_extensions(card, data, project_root=tmp_path)


# --- WR-02: Regra 3 — contributes/agents required ---------------------------


def test_auditor_without_contributes_fails(tmp_path: Path):
    """Auditor sem campo `contributes` → raise (não default silencioso).

    Reincidência da lição Task 2.2 HI-01..03: required subfields validados
    explicitamente, não assumidos como `{}`.
    """
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    data = _minimal_card_data()
    del data["qa-extensions"]["auditors"][0]["contributes"]
    with pytest.raises(
        QAExtensionsValidationError, match="sem campo `contributes`"
    ):
        validate_qa_extensions(card, data, project_root=tmp_path)


def test_auditor_without_contributes_agents_fails(tmp_path: Path):
    """contributes presente mas sem chave `agents` → raise."""
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    data = _minimal_card_data()
    data["qa-extensions"]["auditors"][0]["contributes"] = {}
    with pytest.raises(
        QAExtensionsValidationError, match="sem campo `contributes.agents`"
    ):
        validate_qa_extensions(card, data, project_root=tmp_path)


def test_auditor_with_empty_agents_list_fails(tmp_path: Path):
    """contributes.agents = [] → raise ('auditor sem prompt é inutilizável')."""
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    data = _minimal_card_data()
    data["qa-extensions"]["auditors"][0]["contributes"]["agents"] = []
    with pytest.raises(
        QAExtensionsValidationError, match="lista vazia"
    ):
        validate_qa_extensions(card, data, project_root=tmp_path)


# --- IN-01: simetria local→canon (espelha test existente) -------------------


def test_collision_local_to_canon_direction(tmp_path: Path):
    """Simetria: local_card sujeito, canon_card em other_cards → mesma colisão.

    Documenta que a Regra 1 não tem assimetria intrínseca; ordem de
    iteração do loader não muda o veredito.
    """
    canon_card_dir = _card_dir(tmp_path, name="screens-defined")
    _agent_file(canon_card_dir)
    canon_card = canon_card_dir / "card.yaml"

    local_card_dir = _card_dir(tmp_path, name="custom-screens")
    _agent_file(local_card_dir)
    local_card = local_card_dir / "card.yaml"

    canon_data = _minimal_card_data(name="visual-fidelity")
    local_data = _minimal_card_data(name="visual-fidelity")

    # Swap: agora local_card é o sujeito, canon_card está em other_cards.
    other_cards = {str(canon_card): canon_data}

    with pytest.raises(QAExtensionsCollisionError) as excinfo:
        validate_qa_extensions(
            local_card, local_data, other_cards=other_cards, project_root=tmp_path
        )

    msg = str(excinfo.value)
    assert "visual-fidelity" in msg
    assert str(canon_card) in msg
    assert str(local_card) in msg


# --- IN-02: other_cards Path-key normalization ------------------------------


def test_other_cards_with_path_key_does_not_self_collide(tmp_path: Path):
    """Caller esquece `str()`: passa `Path` como chave em other_cards.

    Antes do fix: `Path == str(card_path)` retorna False → card aparece
    em other_cards como se fosse OUTRO card → spurious self-collision.
    Após fix: normalização garante que o próprio card seja filtrado
    mesmo com chave Path.
    """
    card_dir = _card_dir(tmp_path)
    _agent_file(card_dir)
    card = card_dir / "card.yaml"
    data = _minimal_card_data(name="visual-fidelity")

    # Chave Path (em vez de str(card)): exercita o bug latente.
    other_cards = {card: data}  # type: ignore[dict-item]

    # Não deve raise — é o próprio card, normalização filtra.
    validate_qa_extensions(
        card, data, other_cards=other_cards, project_root=tmp_path
    )


# --- IN-03: CatalogOverlayError documentação ---------------------------------


def test_docstring_documents_catalog_overlay_error_propagation():
    """Docstring `Raises:` menciona propagação de CatalogOverlayError.

    Caller que faça `except QAExtensionsValidationError:` precisa saber
    que CatalogOverlayError NÃO é capturado (sobe direto do _common).
    """
    doc = validate_qa_extensions.__doc__ or ""
    assert "CatalogOverlayError" in doc, (
        "docstring deve mencionar propagação de CatalogOverlayError "
        "do _common.load_catalog (IN-03)"
    )
