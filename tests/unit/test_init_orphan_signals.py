"""Unit tests — init Step 7.5: orphan signals detection + 3-caminhos.

Parte 1 (Task 10): _check_orphan_signals detection
Parte 2 (Task 11): _surface_three_paths UX
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.init import (
    OrphanSignal,
    _check_orphan_signals,
    _count_needle_hits,
)


@pytest.fixture
def project_with_hilt(tmp_path: Path) -> Path:
    """Project root com 3 arquivos .kt mencionando Hilt — orphan target."""
    proj = tmp_path / "proj"
    (proj / "app" / "src" / "main" / "kotlin" / "com" / "x").mkdir(parents=True)
    src = proj / "app" / "src" / "main" / "kotlin" / "com" / "x"
    (src / "App.kt").write_text(
        "package com.x\n\nimport dagger.hilt.android.HiltAndroidApp\n\n@HiltAndroidApp\nclass App\n",
        encoding="utf-8",
    )
    (src / "Module.kt").write_text(
        "package com.x\n\nimport dagger.hilt.android.AndroidEntryPoint\n",
        encoding="utf-8",
    )
    (src / "Helper.kt").write_text(
        "package com.x\n\nimport dagger.hilt.android.qualifiers.ApplicationContext\n",
        encoding="utf-8",
    )
    return proj


class _FakeCatalog:
    def __init__(self, reserved: set[str]) -> None:
        self.reserved = frozenset(reserved)


def test_count_needle_hits_finds_three_files(project_with_hilt):
    count = _count_needle_hits(project_with_hilt, "dagger.hilt.android")
    assert count == 3


def test_count_needle_hits_zero_for_absent_pattern(project_with_hilt):
    count = _count_needle_hits(project_with_hilt, "this-string-does-not-exist")
    assert count == 0


def test_check_orphan_signals_detects_hilt_when_no_card_covers_it(project_with_hilt):
    """Hilt detected, hilt-di label is reserved (canon roadmap) → is_reserved=True."""
    catalog = _FakeCatalog(reserved={"hilt-di"})
    orphans = _check_orphan_signals(project_with_hilt, canonical_cards=[], catalog=catalog)
    hilt_orphans = [o for o in orphans if o.suggested_capability == "hilt-di"]
    assert hilt_orphans, "Hilt orphan deveria ter sido detectado"
    o = hilt_orphans[0]
    assert o.is_reserved is True
    assert o.hit_count >= 1


def test_check_orphan_signals_returns_empty_when_card_covers_needle(project_with_hilt):
    """Card existente cobre `dagger.hilt.android` no detection.signals → não vira orphan."""
    from engine.cards.loader import CardManifest

    fake_card = CardManifest(
        name="hilt-di",
        version="1.0.0",
        schema_version=1,
        description="",
        category="dependency-injection",
        maturity="stable",
        provides=["hilt-di"],
        detection={
            "signals": [
                {"type": "file-content", "glob": "**/*.kt", "contains": "dagger.hilt.android", "confidence": 0.5}
            ],
            "threshold": 0.5,
        },
    )
    catalog = _FakeCatalog(reserved=set())
    orphans = _check_orphan_signals(
        project_with_hilt, canonical_cards=[fake_card], catalog=catalog
    )
    # `dagger.hilt.android` é o needle exato cobrendo — não vira orphan.
    # `@HiltAndroidApp` ainda é outro needle distinto na heurística; depende
    # se está coberto. Aqui só queremos confirmar que o needle coberto sai.
    needles_in_orphans = {o.signal_id for o in orphans}
    assert "orphan:dagger.hilt.android" not in needles_in_orphans


def test_check_orphan_signals_marks_non_reserved_when_not_in_catalog(tmp_path):
    """Suggested capability fora de reserved → is_reserved=False."""
    proj = tmp_path / "p"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "X.kt").write_text("import io.reactivex.rxjava3.core.Observable\n", encoding="utf-8")

    catalog = _FakeCatalog(reserved=set())  # vazio — nada é reservado
    orphans = _check_orphan_signals(proj, canonical_cards=[], catalog=catalog)
    rx = [o for o in orphans if o.suggested_capability == "rxjava3-streams"]
    assert rx and rx[0].is_reserved is False


def test_check_orphan_signals_empty_project_returns_no_orphans(tmp_path):
    proj = tmp_path / "empty"
    proj.mkdir()
    catalog = _FakeCatalog(reserved={"hilt-di"})
    orphans = _check_orphan_signals(proj, canonical_cards=[], catalog=catalog)
    assert orphans == []
