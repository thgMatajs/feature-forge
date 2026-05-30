"""Unit tests — engine.cards.merger.

Drives `merge_contributions` with synthetic CardManifest fixtures to validate
grouping, deterministic ordering, and config-defaults conflict warnings.
"""

from __future__ import annotations

from pathlib import Path

from engine.cards.loader import CardManifest
from engine.cards.merger import merge_contributions


def _manifest(name: str, contributes: dict) -> CardManifest:
    return CardManifest(
        name=name,
        version="1.0.0",
        schema_version=1,
        description="",
        category="kmp",
        maturity="stable",
        provides=[],
        requires=[],
        conflicts_with=[],
        contributes=contributes,
        source_path=Path(f"/cards/{name}"),
    )


def test_merge_collects_templates_by_target():
    a = _manifest(
        "alpha",
        {
            "templates": [
                {"target": "AGENTS.md", "section": "DI", "file": "a.md"},
                {"target": "AGENTS.md", "section": "Nav", "file": "b.md"},
            ]
        },
    )
    b = _manifest(
        "beta",
        {"templates": [{"target": "CLAUDE.md", "section": "X", "file": "c.md"}]},
    )
    merged = merge_contributions([a, b])
    assert set(merged.templates.keys()) == {"AGENTS.md", "CLAUDE.md"}
    assert len(merged.templates["AGENTS.md"]) == 2


def test_merge_templates_sorted_by_order_then_name():
    a = _manifest(
        "alpha",
        {"templates": [{"target": "F.md", "section": "x", "file": "a", "merge-order": 50}]},
    )
    b = _manifest(
        "beta",
        {"templates": [{"target": "F.md", "section": "x", "file": "b", "merge-order": 10}]},
    )
    merged = merge_contributions([a, b])
    entries = merged.templates["F.md"]
    # Lower merge_order first.
    assert entries[0]["card_name"] == "beta"
    assert entries[1]["card_name"] == "alpha"


def test_merge_validators_carry_card_name():
    a = _manifest(
        "alpha",
        {"validators": [{"name": "v1", "file": "v.py", "severity": "warn"}]},
    )
    merged = merge_contributions([a])
    assert len(merged.validators) == 1
    assert merged.validators[0]["card_name"] == "alpha"
    assert merged.validators[0]["name"] == "v1"


def test_merge_agent_prompts_grouped_by_agent():
    a = _manifest(
        "alpha",
        {
            "agent-prompts": [
                {"inject-into": "planning-conductor", "file": "p.md"},
                {"inject-into": "feature-intake-agent", "file": "q.md"},
            ]
        },
    )
    merged = merge_contributions([a])
    assert set(merged.agent_prompts.keys()) == {"planning-conductor", "feature-intake-agent"}


def test_merge_hooks_collected():
    a = _manifest(
        "alpha",
        {"hooks": [{"file": "pre.sh", "events": ["pre-commit"]}]},
    )
    merged = merge_contributions([a])
    assert len(merged.hooks) == 1
    assert merged.hooks[0]["events"] == ["pre-commit"]


def test_merge_config_defaults_conflict_warning():
    a = _manifest("alpha", {"config-defaults": {"k": "v-alpha"}})
    b = _manifest("beta", {"config-defaults": {"k": "v-beta"}})
    merged = merge_contributions([a, b])
    # First wins.
    assert merged.config_defaults["k"] == "v-alpha"
    assert any("CONFIG-DEFAULT-CONFLICT" in w for w in merged.warnings)


def test_merge_config_defaults_same_value_no_warning():
    a = _manifest("alpha", {"config-defaults": {"k": "same"}})
    b = _manifest("beta", {"config-defaults": {"k": "same"}})
    merged = merge_contributions([a, b])
    assert not any("CONFIG-DEFAULT-CONFLICT" in w for w in merged.warnings)


def test_merge_empty_contributes_yields_empty_merge():
    a = _manifest("alpha", {})
    merged = merge_contributions([a])
    assert merged.templates == {}
    assert merged.validators == []
    assert merged.hooks == []
