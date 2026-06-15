"""M-12 regression: ignore patterns must anchor to directory boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from check_secrets import _filter_ignored, _DEFAULT_IGNORE_PATTERNS


def test_tests_root_fixtures_is_ignored(tmp_path: Path) -> None:
    files = [Path("tests/fixtures/secrets/leaked.py")]
    out = _filter_ignored(files, _DEFAULT_IGNORE_PATTERNS)
    assert out == []


def test_nested_src_fixtures_is_not_ignored(tmp_path: Path) -> None:
    """`src/tests/fixtures/secrets/x.py` is NOT the tests root and must be checked."""
    files = [Path("src/tests/fixtures/secrets/prod-config.py")]
    out = _filter_ignored(files, _DEFAULT_IGNORE_PATTERNS)
    assert out == files, (
        "src/tests/... was incorrectly ignored — pattern anchor regression."
    )
