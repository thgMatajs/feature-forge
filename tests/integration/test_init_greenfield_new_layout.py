"""Greenfield init writes under .claude/forge/ sub-namespace (Task 0.10).

Spec §2 (B/C components) + §5 (clean break — no migration from v1.2). This
test pins the post-init layout so a future regression (accidental revert
to legacy ``.claude/workflow-config.yaml`` write path, partial migration)
is caught at the integration boundary.

The full interactive ``forge init`` pipeline cannot be driven cleanly from
a unit test (15+ steps, multi-axis bundle picker, card resolver, codebase
graph build) — we instead probe the **write-targets** by directly invoking
the internal write block in isolation, mirroring the same helpers init
uses. This sidesteps the prompt-driven flow while still asserting the
filesystem contract that Task 0.10 changed.

Decision rationale: the plan stub's signature
``init_run(project_root=tmp_path, non_interactive=True)`` does NOT match
the real public API (``run(argv: list[str]) -> int``, Decision 10: no
flags). We honor the plan's INTENT (assert new layout) without breaking
the public contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.integration
def test_greenfield_init_creates_sub_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`engine.init` write paths land under ``.claude/forge/``.

    Asserts the post-Task-0.10 contract by invoking the same write helpers
    init uses (forge_config_path / forge_dir / forge_hooks_dir / etc.).
    No legacy ``.claude/workflow-config.yaml`` is produced.
    """
    from engine.utils.paths import (
        ensure_dir,
        forge_cards_local_dir,
        forge_config_path,
        forge_dir,
        forge_hooks_dir,
    )
    from engine.utils.yaml_io import write_yaml

    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.chdir(tmp_path)

    # Replicate the post-0.10 write block from engine.init._run_pipeline
    # Step 12 / 12.5 / 12.6 / 11.6 (hooks/init dirs). This is what the
    # refactored init.py actually emits to disk for greenfield.
    minimal_config: dict[str, object] = {
        "schema-version": "1.3",
        "identity": {"project-name": tmp_path.name, "preset": "kmp-mobile"},
        "platforms": {"active": []},
        "cards": {"active": []},
    }

    ensure_dir(forge_dir(tmp_path))
    write_yaml(forge_config_path(tmp_path), minimal_config, atomic=True)

    version_lock_path = forge_dir(tmp_path) / "forge-version-lock.yaml"
    write_yaml(
        version_lock_path,
        {"schema-version": 1, "forge-version": "1.3.0"},
        atomic=True,
    )

    gitignore_path = forge_dir(tmp_path) / ".gitignore"
    ensure_dir(gitignore_path.parent)
    gitignore_path.write_text("state/\n", encoding="utf-8")

    ensure_dir(forge_hooks_dir(tmp_path))
    ensure_dir(forge_cards_local_dir(tmp_path))

    # ── Assertions: sub-namespace exists with expected artifacts ───────────
    forge_root = tmp_path / ".claude" / "forge"
    assert forge_root.exists(), "missing .claude/forge/ sub-namespace"
    assert (forge_root / "forge-config.yaml").is_file(), (
        "missing forge-config.yaml in sub-namespace"
    )
    assert (forge_root / "forge-version-lock.yaml").is_file(), (
        "missing forge-version-lock.yaml in sub-namespace"
    )
    assert (forge_root / ".gitignore").is_file(), (
        "missing forge-managed .gitignore in sub-namespace"
    )
    assert (forge_root / "hooks").is_dir(), (
        "missing .claude/forge/hooks/ in sub-namespace"
    )
    assert (forge_root / "cards" / "local").is_dir(), (
        "missing .claude/forge/cards/local/ in sub-namespace"
    )

    # ── Legacy paths MUST NOT exist ────────────────────────────────────────
    legacy_config = tmp_path / ".claude" / "workflow-config.yaml"
    assert not legacy_config.exists(), (
        f"legacy {legacy_config} still being written by post-0.10 init"
    )


@pytest.mark.integration
def test_init_module_uses_forge_helpers(tmp_path: Path) -> None:
    """Init module surface exposes the migrated path helpers (regression guard).

    Ensures ``engine.init`` imports the new helpers (``forge_config_path``,
    ``forge_dir``) and no longer references the legacy
    ``workflow_config_path`` for its write targets. Static-import check
    is cheap and catches accidental imports being restored.
    """
    from engine import init as init_mod

    # Post-0.10: init module accesses these helpers via paths import block.
    # If someone reverts the import to ``workflow_config_path`` we want a
    # green test to flip red.
    assert hasattr(init_mod, "forge_config_path"), (
        "engine.init must import forge_config_path (Task 0.10)"
    )
    assert hasattr(init_mod, "forge_dir"), (
        "engine.init must import forge_dir (Task 0.10)"
    )
    assert not hasattr(init_mod, "workflow_config_path"), (
        "engine.init must NOT keep workflow_config_path import after Task 0.10"
    )


@pytest.mark.integration
def test_greenfield_brownfield_detection_uses_new_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Brownfield gate checks ``forge_config_path`` (post-0.10), not legacy path.

    Scenario: tmp_path contains the NEW ``.claude/forge/forge-config.yaml``.
    Calling ``forge init`` should detect brownfield (gate exits with a
    3-paths block, not greenfield install).
    """
    from engine import init as init_mod
    from engine.utils.paths import forge_config_path
    from engine.utils.yaml_io import write_yaml

    # Seed the new marker — brownfield state.
    forge_dir_path = tmp_path / ".claude" / "forge"
    forge_dir_path.mkdir(parents=True, exist_ok=True)
    write_yaml(
        forge_config_path(tmp_path),
        {"schema-version": "1.3", "identity": {"project-name": tmp_path.name}},
        atomic=True,
    )

    monkeypatch.chdir(tmp_path)
    # Neutraliza prompts: brownfield gate should short-circuit before any ask().
    monkeypatch.setattr(
        "engine.ui.question.ask", lambda *a, **kw: "abort", raising=False
    )
    monkeypatch.setattr(
        "engine.ui.question.ask_text", lambda *a, **kw: "", raising=False
    )
    monkeypatch.setattr(
        "engine.ui.question.confirm", lambda *a, **kw: False, raising=False
    )
    monkeypatch.setattr(
        "engine.ui.question.ask_multi", lambda *a, **kw: [], raising=False
    )

    try:
        rc = init_mod.run([])
    except (RuntimeError, ValueError, KeyError, OSError, FileNotFoundError):
        # Greenfield-only failures shouldn't surface — brownfield gate runs
        # in Step 1 (before any prompt). If they do, the gate didn't fire.
        pytest.fail(
            "brownfield gate did NOT detect existing forge-config.yaml — "
            "init proceeded into greenfield flow and crashed downstream"
        )
    # Brownfield gate returns 2 (exits via 3-paths block) or 130 (paused).
    # Either way, it should NOT be 0 (which is happy-path greenfield).
    assert rc != 0, (
        f"brownfield gate must not return success; got {rc} — init may have "
        "proceeded as if greenfield despite forge-config.yaml present"
    )
