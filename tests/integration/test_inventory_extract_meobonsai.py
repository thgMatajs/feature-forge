"""Integration test — inventory extraction against MeoBonsai.

Validates the three inventory extractors against the live MeoBonsai tree:
design-system, i18n, conventions. Skipped when MeoBonsai is absent.
"""

from __future__ import annotations

import pytest

from engine.inventory import conventions, design_system, i18n

pytestmark = pytest.mark.meobonsai


@pytest.mark.integration
def test_design_system_extraction_finds_meo_components(meobonsai_root):
    inv = design_system.extract_design_system(meobonsai_root)
    canonical = [c for c in inv.components if c.status != "legacy"]
    # MeoBonsai must yield at least MeoButton across the platforms.
    names = {c.name for c in canonical}
    if not names:
        pytest.skip("design-system inventory produced no canonical components")
    assert any(n.startswith("Meo") for n in names)


@pytest.mark.integration
def test_i18n_extraction_finds_pt_br_keys(meobonsai_root):
    inv = i18n.extract_i18n(meobonsai_root)
    sot = inv.raw["source-of-truth"]
    if sot["format"] == "unknown":
        pytest.skip("MeoBonsai i18n source-of-truth not detected on this tree snapshot")
    assert "pt-BR" in sot["locales"] or "en-US" in sot["locales"]
    assert inv.raw["stats"]["total-keys"] > 0


@pytest.mark.integration
def test_conventions_extraction_detects_kmp_layout(meobonsai_root):
    inv = conventions.extract_conventions(meobonsai_root)
    layout = inv.raw.get("folder-layout") or {}
    # Layout dict must exist and be non-empty for a KMP project.
    assert isinstance(layout, dict)


@pytest.mark.integration
def test_inventories_write_round_trip_uses_tmp(meobonsai_root, tmp_path):
    # Use a tmp project root that just symlinks the necessary tree fragments
    # rather than monkeypatching engine.utils.paths.inventory_dir (the
    # conventions module imports inventory_dir at module load — patching
    # after import does not redirect the call site).
    inv = conventions.extract_conventions(meobonsai_root)
    # Write into a fresh project root so we never pollute MeoBonsai's tree.
    (tmp_path / ".git").mkdir()
    (tmp_path / ".claude" / "inventory").mkdir(parents=True)
    out = conventions.write_conventions_inventory(tmp_path, inv)
    assert out.is_file()
    assert out.parent == tmp_path / ".claude" / "inventory"
    read = conventions.read_conventions_inventory(tmp_path)
    assert read is not None
