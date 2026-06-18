"""C-001 regression — JSON-mode carve-out must NOT leak the intent protocol.

The holistic W3 review (2026-06-18) found that two read-commands on the JSON
allowlist — ``verify`` and ``graph`` — have a prompt path that was NOT gated on
``output_mode.is_json_mode()``. Under ``FORGE_OUTPUT=json`` (or ``--json``) the
global mode resolves JSON, ``renderer.write`` becomes a no-op, yet the handler
still reached ``question.ask`` — raising ``PausedForInputError`` (exit-2) with
the prompt prose swallowed. Exit-2 is reserved STRICTLY for the intent protocol
(DRIFT-1); a declared machine-readable consumption must never trigger it.

These tests reproduce the leak (red before the fix) and assert the contract:
JSON-mode ambiguity → exit 1 + stderr message, never ``PausedForInputError``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import verify, graph_cli
from engine.memory.l1 import L1State, write_l1_status
from engine.ui import output_mode as om
from engine.ui.question import PausedForInputError
from engine.utils.iso import utc_now_iso


def _seed_config(project_root: Path) -> None:
    forge_dir = project_root / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "schema-version: 1\nidentity:\n  project-name: demo\n",
        encoding="utf-8",
    )


def _seed_active_feature(project_root: Path, slug: str) -> None:
    (project_root / ".claude" / "memory" / "L1" / slug).mkdir(
        parents=True, exist_ok=True
    )
    write_l1_status(
        L1State(
            feature_slug=slug,
            status="implementing",
            last_action_at=utc_now_iso(),
            last_action_kind="implement-started",
        ),
        project_root,
    )


# ── verify ─────────────────────────────────────────────────────────────────


def test_verify_json_two_active_features_no_intent_leak(
    tmp_forge_project, capsys, monkeypatch
):
    """≥2 active features + JSON mode + no argv → exit 1 + stderr, never exit-2."""
    _seed_config(tmp_forge_project)
    _seed_active_feature(tmp_forge_project, "alpha-feature")
    _seed_active_feature(tmp_forge_project, "beta-feature")
    monkeypatch.chdir(tmp_forge_project)

    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        code = verify.run([])
    except PausedForInputError as exc:  # pragma: no cover - the bug, if present
        pytest.fail(f"verify --json leaked the intent protocol (exit-2): {exc}")
    finally:
        om.reset_output_mode(token)

    captured = capsys.readouterr()
    assert code == 1, "ambiguous scope in JSON mode must be a hard error (exit 1)"
    assert "forge verify" in captured.err
    # stdout stays pure: no orphan intent marker, no half-rendered prompt.
    assert "<FORGE_INTENT" not in captured.out


# ── graph ────────────────────────────────────────────────────────────────────


def test_graph_json_mode_without_query_no_intent_leak(
    tmp_forge_project, capsys, monkeypatch
):
    """FORGE_OUTPUT=json + ``forge graph`` (no --json positional) → exit 1 + stderr.

    The global mode resolves JSON (graph is on the allowlist), but argv has no
    ``--json`` token, so the legacy local detector would have fallen into the
    interactive menu → ``question.ask`` → exit-2. Must be a deterministic error.
    """
    # Seed config so find_project_root succeeds; a graph.db must exist so we get
    # past the missing-DB guard and would otherwise reach the interactive menu.
    _seed_config(tmp_forge_project)
    graph_db = tmp_forge_project / ".claude" / "graph.db"
    graph_db.parent.mkdir(parents=True, exist_ok=True)
    graph_db.write_bytes(b"")
    monkeypatch.chdir(tmp_forge_project)
    monkeypatch.setenv("FORGE_OUTPUT", "json")

    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        code = graph_cli.run(["--no-auto-build"])
    except PausedForInputError as exc:  # pragma: no cover - the bug, if present
        pytest.fail(f"graph leaked the intent protocol (exit-2): {exc}")
    finally:
        om.reset_output_mode(token)

    captured = capsys.readouterr()
    assert code == 1, "JSON mode without explicit query must be a hard error"
    assert "forge graph" in captured.err
    assert "<FORGE_INTENT" not in captured.out
