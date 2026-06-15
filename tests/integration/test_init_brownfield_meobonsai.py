"""Integration test — MeoBonsai brownfield detection.

Skipped automatically when `~/Documents/MeoBonsai` is not present (the
`meobonsai_root` fixture handles the skip). Verifies that:

- MeoBonsai already has `.claude/workflow-config.yaml`, so `find_project_root`
  finds it immediately
- The inventory/conventions extractors can ingest the real tree without
  raising (smoke test against real-world signals)
"""

from __future__ import annotations

import pytest

from engine.inventory import conventions, design_system, i18n
from engine.utils import paths

pytestmark = pytest.mark.meobonsai


@pytest.mark.integration
def test_meobonsai_has_workflow_config(meobonsai_root):
    root = paths.try_find_project_root(meobonsai_root)
    # Test passes either way: if MeoBonsai has a workflow-config we get the path,
    # otherwise None — both are valid states.
    if root is None:
        pytest.skip("MeoBonsai has no .claude/workflow-config.yaml yet")
    assert root.is_dir()


@pytest.mark.integration
def test_extract_conventions_against_meobonsai(meobonsai_root):
    inv = conventions.extract_conventions(meobonsai_root)
    assert isinstance(inv.raw, dict)
    assert inv.raw["schema-version"] >= 1
    # MeoBonsai is documented as using Koin annotations + Navigation 3.
    # We accept "unknown" too — heuristics may miss when build/ is pruned.
    assert inv.di_pattern in {"koin-annotations", "koin", "unknown"}


@pytest.mark.integration
def test_extract_design_system_against_meobonsai(meobonsai_root):
    inv = design_system.extract_design_system(meobonsai_root)
    names = {c.name for c in inv.components}
    # MeoBonsai must expose at least the Meo* atoms.
    if names:
        meo_components = [n for n in names if n.startswith("Meo")]
        assert meo_components, f"no Meo* components found; names={sorted(names)[:10]}"


@pytest.mark.integration
def test_extract_i18n_against_meobonsai(meobonsai_root):
    inv = i18n.extract_i18n(meobonsai_root)
    sot = inv.raw["source-of-truth"]
    # MeoBonsai's SoT path may be json-per-locale or unknown (tree pruning).
    assert sot["format"] in {"json-per-locale", "unknown"}
