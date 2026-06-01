"""Regression: ``_looks_like_test_file`` must recognize root-level test folders.

Bug A12 (PR #1): the heuristic compares against segments like ``"/test/"``
and ``"/tests/"`` (leading + trailing slash). A root-level path like
``test/MockData.kt`` does NOT contain ``"/test/"`` because there's no
leading slash, so it silently fell through to the suffix check — and
``MockData.kt`` has no recognized test suffix. Result: a root-level test
folder was treated as production code, weakening the refactor gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATORS_DIR = _REPO_ROOT / "validators"
if str(_VALIDATORS_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS_DIR))

from check_no_behavior_change import _looks_like_test_file  # noqa: E402


@pytest.mark.parametrize(
    "path",
    [
        "test/MockData.kt",
        "tests/MockData.kt",
        "test/integration/Helper.swift",
        "tests/util/MockData.kt",
        "__tests__/Foo.test.tsx",
        # Backslash-separated (Windows) variant — must normalise to forward slash.
        "test\\MockData.kt",
    ],
)
def test_root_level_test_folder_is_recognized(path: str):
    assert _looks_like_test_file(path), (
        f"Root-level test folder '{path}' must match — the leading-slash "
        "comparison silently missed it."
    )


@pytest.mark.parametrize(
    "path",
    [
        "src/test/kotlin/MockData.kt",
        "shared/feature/auth/src/commonTest/kotlin/AuthTest.kt",
        "ios/AppTests/AppTests.swift",
        "web/src/__tests__/Foo.test.ts",
    ],
)
def test_nested_test_paths_still_recognized(path: str):
    """Regression guard: nested test folders must keep matching."""
    assert _looks_like_test_file(path)


@pytest.mark.parametrize(
    "path",
    [
        "src/main/kotlin/AuthRepo.kt",
        "engine/cli.py",
        "ios/Sources/App.swift",
        "web/src/feature/auth/index.ts",
    ],
)
def test_production_paths_are_not_misclassified(path: str):
    assert not _looks_like_test_file(path)


def test_filename_suffix_still_recognized_outside_test_folder():
    """A file with a `Test.kt` suffix sitting in production tree is still test-like."""
    assert _looks_like_test_file("src/main/kotlin/AuthRepoTest.kt")
