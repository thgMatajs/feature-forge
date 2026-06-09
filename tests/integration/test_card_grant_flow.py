"""Integration tests pra grant flow E2E em init/reconfigure (QA-11 wave 5 Task 5.2)."""

from __future__ import annotations

import pytest

from engine.cards.grant import evaluate_sensitive_grants
from engine.cards.loader import CardManifest


pytestmark = pytest.mark.integration


def _make_card(name: str, sensitive: tuple[str, ...] = ()) -> CardManifest:
    return CardManifest(
        name=name,
        version="1.0.0",
        schema_version=1,
        description=f"fixture {name}",
        category="testing",
        maturity="experimental",
        provides=["foundation.testing.unit-test-runner"],
        env_needs=sensitive,
        sensitive_env_needs=sensitive,
    )


def test_first_activation_prompts_and_persists_grant(monkeypatch):
    """1ª ativação: prompt dispara, grant decision tem new_grants_to_persist."""
    monkeypatch.setattr(
        "engine.cards.grant._prompt_sensitive_grant",
        lambda *, card_name, var: "grant",
    )
    cards = [_make_card("github-ci-card", sensitive=("GITHUB_TOKEN",))]
    cfg: dict = {"qa": {}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert decision.new_grants_to_persist == ("GITHUB_TOKEN",)
    assert decision.granted == ("GITHUB_TOKEN",)
    assert decision.denied_cards == ()


def test_second_activation_same_var_no_prompt(monkeypatch):
    """Re-ativação após grant persistido: zero prompts, zero new_grants."""
    prompts_seen: list[str] = []
    monkeypatch.setattr(
        "engine.cards.grant._prompt_sensitive_grant",
        lambda *, card_name, var: (prompts_seen.append(var) or "grant"),
    )
    cards = [_make_card("github-ci-card", sensitive=("GITHUB_TOKEN",))]
    cfg: dict = {"qa": {"sensitive-env-grants": ["GITHUB_TOKEN"]}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert prompts_seen == []
    assert decision.new_grants_to_persist == ()


def test_deny_path_disables_card_in_workflow_config(monkeypatch):
    """Deny: card aparece em denied_cards, caller deve removê-lo de active_cards."""
    monkeypatch.setattr(
        "engine.cards.grant._prompt_sensitive_grant",
        lambda *, card_name, var: "deny",
    )
    cards = [
        _make_card("github-card", sensitive=("GITHUB_TOKEN",)),
        _make_card("clean-card", sensitive=()),
    ]
    cfg: dict = {"qa": {}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert "github-card" in decision.denied_cards
    assert "clean-card" not in decision.denied_cards
    assert decision.granted == ()


def test_manual_revoke_via_reconfigure_removes_grant(monkeypatch):
    """User edita workflow-config removendo grant → próxima ativação re-pergunta."""
    cfg: dict = {"qa": {"sensitive-env-grants": ["GITHUB_TOKEN"]}}
    cards = [_make_card("github-card", sensitive=("GITHUB_TOKEN",))]

    # 1ª chamada: sem prompt (já granted)
    monkeypatch.setattr(
        "engine.cards.grant._prompt_sensitive_grant",
        lambda *, card_name, var: "grant",
    )
    d1 = evaluate_sensitive_grants(cards, cfg)
    assert d1.new_grants_to_persist == ()

    # User edita config manualmente — remove grant
    cfg["qa"]["sensitive-env-grants"] = []

    # 2ª chamada: prompt dispara de novo
    prompts_seen: list[str] = []
    monkeypatch.setattr(
        "engine.cards.grant._prompt_sensitive_grant",
        lambda *, card_name, var: (prompts_seen.append(var) or "grant"),
    )
    d2 = evaluate_sensitive_grants(cards, cfg)

    assert prompts_seen == ["GITHUB_TOKEN"]
    assert d2.new_grants_to_persist == ("GITHUB_TOKEN",)
