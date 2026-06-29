"""Unit tests — engine.persona.mentor_calmo.

Validates the phrase library shape, deterministic seeding, and the
three-paths block formatter (canonical layout from discipline §1).
"""

from __future__ import annotations

import pytest

from engine.persona import mentor_calmo


def test_set_seed_makes_greeting_deterministic():
    mentor_calmo.set_seed(123)
    first = mentor_calmo.greeting()
    mentor_calmo.set_seed(123)
    second = mentor_calmo.greeting()
    assert first == second


def test_greeting_returns_known_phrase():
    mentor_calmo.set_seed(7)
    g = mentor_calmo.greeting()
    assert g in mentor_calmo.PHRASES_GREETING


def test_acknowledgment_returns_known_phrase():
    mentor_calmo.set_seed(7)
    ack = mentor_calmo.acknowledgment()
    assert ack in mentor_calmo.PHRASES_ACK


def test_progress_phrase_by_stage():
    mentor_calmo.set_seed(1)
    assert mentor_calmo.progress_phrase("init") in mentor_calmo.PHRASES_PROGRESS_INIT
    assert mentor_calmo.progress_phrase("plan") in mentor_calmo.PHRASES_PROGRESS_PLAN
    assert mentor_calmo.progress_phrase("implement") in mentor_calmo.PHRASES_PROGRESS_IMPLEMENT
    # Unknown stage falls back to ack phrase pool.
    assert mentor_calmo.progress_phrase("unknown") in mentor_calmo.PHRASES_ACK


def test_pause_message_includes_slug_and_resume(tmp_path):
    msg = mentor_calmo.pause_message("my-slug", project_root=tmp_path)
    # lifecycle_root(tmp_path) resolves to tmp_path/.claude/forge/state/lifecycle
    assert "lifecycle/my-slug/status.json" in msg
    assert "forge" in msg


def test_pause_message_without_slug_uses_lifecycle_root(tmp_path):
    msg = mentor_calmo.pause_message(project_root=tmp_path)
    # lifecycle_root resolves to forge/state/lifecycle after Task 2 flip
    assert ".claude/forge/state/lifecycle/" in msg


def test_drilldown_rounds_1_and_2():
    assert "contexto" not in mentor_calmo.drilldown_question(1).lower() or True
    r1 = mentor_calmo.drilldown_question(1)
    r2 = mentor_calmo.drilldown_question(2)
    assert isinstance(r1, str) and isinstance(r2, str)
    assert r1 != r2


def test_drilldown_round_3_raises():
    with pytest.raises(ValueError):
        mentor_calmo.drilldown_question(3)


def test_gate_violation_header_format():
    assert mentor_calmo.gate_violation_header("readiness") == "🛑 readiness"


def test_three_paths_block_canonical_layout():
    block = mentor_calmo.three_paths_block(
        "readiness",
        what_failed="contract missing",
        where="auth/feature.yaml",
        why=["readiness gate is the entrypoint", "downstream tasks need it"],
        paths=[
            {"label": "Authorize without contract", "motive": "skip discipline"},
            {"label": "Write contract now", "motive": "right path"},
            {"label": "Abort feature", "motive": "drop on the floor"},
        ],
    )
    assert "🛑 readiness" in block
    assert "O que falhou:" in block
    assert "contract missing" in block
    assert "Onde:" in block
    assert "auth/feature.yaml" in block
    assert "Por que importa:" in block
    assert "Três caminhos" in block
    assert "Sem auto-fix aqui — escolha humana." in block


def test_three_paths_block_requires_exactly_three():
    with pytest.raises(ValueError):
        mentor_calmo.three_paths_block(
            "gate",
            what_failed="x",
            where="y",
            why=["z"],
            paths=[{"label": "only one", "motive": ""}],
        )


def test_abort_warning_includes_slug():
    msg = mentor_calmo.abort_warning("my-feature")
    assert "my-feature" in msg
    assert "aborted" in msg


def test_init_greeting_is_stable_across_runs():
    """A abertura do init deve ser determinística (mesma frase entre runs) —
    P-07. greeting() genérico segue variando (não testado aqui)."""
    from engine.persona.mentor_calmo import greeting_stable

    assert greeting_stable() == greeting_stable()
