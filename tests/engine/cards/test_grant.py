"""Tests for engine/cards/grant.py — sensitive env-need grant flow (QA-11 wave 3)."""

from __future__ import annotations

from typing import Any

import pytest

from engine.cards.grant import (
    GrantDecision,
    UserAbortError,
    evaluate_sensitive_grants,
)
from engine.cards.loader import CardManifest


def _make_card(
    name: str,
    env_needs: tuple[str, ...] = (),
    sensitive: tuple[str, ...] = (),
) -> CardManifest:
    """Helper: monta CardManifest mínimo pra tests."""
    return CardManifest(
        name=name,
        version="1.0.0",
        schema_version=1,
        description=f"fixture {name}",
        category="testing",
        maturity="experimental",
        provides=["foundation.testing.unit-test-runner"],
        env_needs=env_needs,
        sensitive_env_needs=sensitive,
    )


@pytest.fixture
def mock_three_paths(monkeypatch):
    """Mock pra _prompt_sensitive_grant: caller atribui responses por var."""
    calls: list[dict[str, Any]] = []
    responses: dict[str, str] = {}

    def fake_prompt(*, card_name: str, var: str, **kwargs) -> str:
        calls.append({"card_name": card_name, "var": var})
        return responses.get(var, "grant")

    monkeypatch.setattr(
        "engine.cards.grant._prompt_sensitive_grant", fake_prompt
    )
    return {"calls": calls, "responses": responses}


def test_no_sensitive_needs_skips_prompt(mock_three_paths):
    """Card sem sensitive_env_needs não dispara prompt nenhum."""
    cards = [_make_card("c1", env_needs=("JAVA_HOME",), sensitive=())]
    cfg: dict[str, Any] = {"qa": {}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert mock_three_paths["calls"] == []
    assert decision.granted == ()
    assert decision.denied_cards == ()
    assert decision.new_grants_to_persist == ()


def test_already_granted_skips_prompt(mock_three_paths):
    """Var já em workflow_config.qa.sensitive-env-grants não pergunta de novo."""
    cards = [_make_card("c1", env_needs=("GITHUB_TOKEN",), sensitive=("GITHUB_TOKEN",))]
    cfg = {"qa": {"sensitive-env-grants": ["GITHUB_TOKEN"]}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert mock_three_paths["calls"] == []
    assert decision.granted == ()
    assert decision.new_grants_to_persist == ()


def test_grant_path_adds_to_workflow_config(mock_three_paths):
    """Path 1 (grant) adiciona var em new_grants_to_persist."""
    mock_three_paths["responses"]["GITHUB_TOKEN"] = "grant"
    cards = [_make_card("c1", sensitive=("GITHUB_TOKEN",))]
    cfg: dict[str, Any] = {"qa": {}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert decision.granted == ("GITHUB_TOKEN",)
    assert decision.new_grants_to_persist == ("GITHUB_TOKEN",)
    assert decision.denied_cards == ()


def test_deny_path_deactivates_card(mock_three_paths):
    """Path 2 (deny) marca card como denied_cards."""
    mock_three_paths["responses"]["GITHUB_TOKEN"] = "deny"
    cards = [_make_card("c1", sensitive=("GITHUB_TOKEN",))]
    cfg: dict[str, Any] = {"qa": {}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert decision.denied_cards == ("c1",)
    assert decision.granted == ()


def test_abort_path_raises_user_abort(mock_three_paths):
    """Path 3 (abort) raise UserAbortError."""
    mock_three_paths["responses"]["GITHUB_TOKEN"] = "abort"
    cards = [_make_card("c1", sensitive=("GITHUB_TOKEN",))]
    cfg: dict[str, Any] = {"qa": {}}

    with pytest.raises(UserAbortError, match="GITHUB_TOKEN"):
        evaluate_sensitive_grants(cards, cfg)


def test_multiple_cards_same_var_single_prompt(mock_three_paths):
    """2 cards declaram GITHUB_TOKEN → prompt único, ambos cards 'granted'."""
    mock_three_paths["responses"]["GITHUB_TOKEN"] = "grant"
    cards = [
        _make_card("c1", sensitive=("GITHUB_TOKEN",)),
        _make_card("c2", sensitive=("GITHUB_TOKEN",)),
    ]
    cfg: dict[str, Any] = {"qa": {}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert len(mock_three_paths["calls"]) == 1
    assert decision.granted == ("GITHUB_TOKEN",)
    assert decision.denied_cards == ()


def test_grant_persistence_idempotent(mock_three_paths):
    """Re-running evaluate com grants já persistidos: zero new_grants."""
    mock_three_paths["responses"]["GITHUB_TOKEN"] = "grant"
    cards = [_make_card("c1", sensitive=("GITHUB_TOKEN",))]

    # 1ª chamada — grant
    cfg: dict[str, Any] = {"qa": {}}
    d1 = evaluate_sensitive_grants(cards, cfg)
    assert d1.new_grants_to_persist == ("GITHUB_TOKEN",)

    # Simula persist: caller copia new_grants_to_persist pra cfg
    cfg["qa"]["sensitive-env-grants"] = list(d1.new_grants_to_persist)

    # 2ª chamada — não pergunta de novo
    d2 = evaluate_sensitive_grants(cards, cfg)
    assert d2.new_grants_to_persist == ()
    assert d2.granted == ()
