"""Tests for engine/_sandbox/env.py — safe env builder pra subprocess (QA-11)."""

from __future__ import annotations

import pytest

from engine._sandbox.env import CORE_ALLOWLIST, SENSITIVE_PATTERN


def test_core_allowlist_is_frozen():
    """CORE_ALLOWLIST é frozenset (imutável) — mutação deve raise AttributeError."""
    assert isinstance(CORE_ALLOWLIST, frozenset)
    with pytest.raises(AttributeError):
        CORE_ALLOWLIST.add("EVIL_VAR")  # type: ignore[attr-defined]


def test_sensitive_pattern_compiles_and_is_case_insensitive():
    """SENSITIVE_PATTERN é regex compilada e match é case-insensitive."""
    import re
    assert isinstance(SENSITIVE_PATTERN, re.Pattern)
    assert SENSITIVE_PATTERN.match("GITHUB_TOKEN") is not None
    assert SENSITIVE_PATTERN.match("github_token") is not None
    assert SENSITIVE_PATTERN.match("Github_Token") is not None
