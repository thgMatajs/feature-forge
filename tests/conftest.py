"""Shared pytest fixtures for feature-forge tests.

Why these fixtures exist:
- `tmp_project_root` — bare greenfield (just `.git/`). Used by `forge init` tests.
- `tmp_forge_project` — already scaffolded `.claude/` tree. Used by plan/implement tests.
- `forge_home` — the canonical repo we're testing from (resolves cards/, agents/, etc.).
- `meobonsai_root` — optional real-world brownfield fixture; tests requiring it
  skip when the path isn't available (CI runners don't ship MeoBonsai).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make the engine importable from tests without `pip install -e .`.
#
# L-06 (REVIEW.md 2026-06-11): the preferred long-term solution is
# `pip install -e .` in CI, removing this sys.path mutation. Deferred
# until CI pipeline lands (gap tracked in docs/design/04-pending.md).
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Validators import `_common` directly (they run as standalone scripts), so the
# validators/ directory must be on sys.path for import-time resolution.
_VALIDATORS_DIR = _ROOT / "validators"
if str(_VALIDATORS_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS_DIR))

# Expose FORGE_HOME so utils.paths.forge_home() resolves the canonical repo
# in subprocess-style tests too. Tests that need to point at a different home
# can `monkeypatch.setenv("FORGE_HOME", ...)` inside their own scope.
os.environ.setdefault("FORGE_HOME", str(_ROOT))


@pytest.fixture
def tmp_project_root(tmp_path: Path) -> Path:
    """Empty greenfield project root (just `.git/` to mark it as a project)."""
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.fixture
def tmp_forge_project(tmp_path: Path) -> Path:
    """Project root with `.claude/` scaffolding pre-created (no workflow-config).

    Layout matches what `forge init` writes minus the YAML files:

        .git/
        .claude/
          memory/L1/
          memory/L1/archived/
          cards/
          inventory/
          hooks/
    """
    (tmp_path / ".git").mkdir()
    claude = tmp_path / ".claude"
    (claude / "memory" / "L1" / "archived").mkdir(parents=True)
    (claude / "cards").mkdir()
    (claude / "inventory").mkdir()
    (claude / "hooks").mkdir()
    return tmp_path


@pytest.fixture
def forge_home() -> Path:
    """Path to FORGE_HOME (the canonical feature-forge repo)."""
    return _ROOT


@pytest.fixture(scope="session")
def meobonsai_root() -> Path:
    """Path to MeoBonsai fixture (real project for integration tests).

    Skips dependent tests when the directory isn't present — keeps the suite
    runnable on CI machines that don't carry the brownfield fixture.
    """
    candidate = Path.home() / "Documents" / "MeoBonsai"
    if not candidate.is_dir():
        pytest.skip("MeoBonsai fixture not available at ~/Documents/MeoBonsai")
    return candidate


@pytest.fixture
def deterministic_persona(monkeypatch):
    """Pin the mentor-calmo RNG so phrase-picking is reproducible in assertions."""
    from engine.persona import mentor_calmo

    mentor_calmo.set_seed(42)
    yield
    mentor_calmo.set_seed(None)


@pytest.fixture
def no_color(monkeypatch):
    """Force renderer to strip ANSI (mirrors non-TTY environment)."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORGE_FORCE_COLOR", raising=False)
    yield


@pytest.fixture
def tmp_forge_project_with_feature(tmp_forge_project: Path, forge_home: Path) -> Path:
    """`tmp_forge_project` plus a minimal feature package rendered from templates.

    Used by validator tests that need a feature directory present (with the
    expected artefact filenames) without going through the full plan pipeline.
    Placeholders are filled minimally so happy-path tests do not crash on
    obviously missing fields.
    """
    slug = "lembrete-rega"
    feature_root = (
        tmp_forge_project
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
    )
    feature_root.mkdir(parents=True)
    (feature_root / "tasks").mkdir()
    (feature_root / "screen-analysis").mkdir()

    templates = forge_home / "templates"
    if templates.is_dir():
        for tpl in templates.iterdir():
            if not tpl.is_file():
                continue
            dest_name = tpl.name.replace(".template", "")
            try:
                content = tpl.read_text(encoding="utf-8")
            except OSError:
                continue
            (feature_root / dest_name).write_text(
                content.replace("{{feature_slug}}", slug),
                encoding="utf-8",
            )

    memory_l1 = tmp_forge_project / ".claude" / "memory" / "L1" / slug
    memory_l1.mkdir(parents=True, exist_ok=True)
    return tmp_forge_project
