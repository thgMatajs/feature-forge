"""Tests for engine/cards/grant.py — sensitive env-need grant flow (QA-11 wave 3)."""

from __future__ import annotations

from typing import Any

import pytest

from engine.cards.grant import (
    GrantDecision,
    UserAbortError,
    _prompt_sensitive_grant,
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


# ---------------------------------------------------------------------------
# deep-019: dedup de cards_requesting quando mesmo card declara var 2x
# ---------------------------------------------------------------------------


def test_same_card_declares_same_var_twice_no_duplicate_in_prompt(monkeypatch):
    """Card com sensitive=('TOKEN', 'TOKEN') no prompt aparece UMA vez."""
    seen_card_names: list[str] = []

    def fake_prompt(*, card_name: str, var: str, **_kwargs) -> str:
        seen_card_names.append(card_name)
        return "grant"

    monkeypatch.setattr(
        "engine.cards.grant._prompt_sensitive_grant", fake_prompt
    )
    cards = [_make_card("c1", sensitive=("GITHUB_TOKEN", "GITHUB_TOKEN"))]
    evaluate_sensitive_grants(cards, {"qa": {}})

    assert seen_card_names == ["c1"], (
        f"esperado ['c1'] (sem duplicação); obtido {seen_card_names}"
    )


# ---------------------------------------------------------------------------
# deep-004: EOF e input não-reconhecido em _prompt_sensitive_grant
# ---------------------------------------------------------------------------


def test_prompt_returns_abort_on_eof(capsys):
    """deep-004: EOFError (stdin fechado) → 'abort' com mensagem explícita."""

    def eof_prompt(_msg: str) -> str:
        raise EOFError()

    result = _prompt_sensitive_grant(
        card_name="cardX", var="GITHUB_TOKEN", prompt_fn=eof_prompt
    )

    assert result == "abort"
    err = capsys.readouterr().err
    assert "stdin fechado" in err


def test_prompt_reprompts_on_typo_then_accepts_valid_choice(capsys):
    """deep-004: input inválido NÃO cai em abort imediato; re-prompta até 3x."""
    answers = iter(["x", "4", "1"])

    def stepped_prompt(_msg: str) -> str:
        return next(answers)

    result = _prompt_sensitive_grant(
        card_name="cardX", var="GITHUB_TOKEN", prompt_fn=stepped_prompt
    )

    assert result == "grant"
    err = capsys.readouterr().err
    # Avisos de input não-reconhecido aparecem antes do grant
    assert "'x' não reconhecida" in err or "'x'" in err


def test_prompt_returns_abort_after_3_invalid_attempts():
    """deep-004: três entradas inválidas seguidas → 'abort'."""
    answers = iter(["x", "y", "z"])

    def stepped_prompt(_msg: str) -> str:
        return next(answers)

    result = _prompt_sensitive_grant(
        card_name="cardX", var="GITHUB_TOKEN", prompt_fn=stepped_prompt
    )

    assert result == "abort"
