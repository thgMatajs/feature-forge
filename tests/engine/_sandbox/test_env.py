"""Tests for engine/_sandbox/env.py — safe env builder pra subprocess (QA-11)."""

from __future__ import annotations

import pytest

from engine._sandbox.env import CORE_ALLOWLIST, SENSITIVE_PATTERN
from engine._sandbox.env import is_sensitive


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


@pytest.mark.parametrize("name", [
    "GITHUB_TOKEN",
    "AWS_SECRET_ACCESS_KEY",
    "DB_PASSWORD",
    "OAUTH2_CREDENTIAL",
    "RSA_PRIVATE_KEY",
    "MY_API_KEY",
    "MY-API-KEY",
    "OAUTH_TOKEN",
])
def test_is_sensitive_matches_token_patterns(name):
    """Pattern bate em formatos canônicos de var sensitive."""
    assert is_sensitive(name) is True


@pytest.mark.parametrize("name", [
    "github_token",
    "Github_Token",
    "AWS_secret_access_key",
    "db_PASSWORD",
])
def test_is_sensitive_case_insensitive(name):
    """Case-insensitive: lowercase / mixed-case batem igual."""
    assert is_sensitive(name) is True


@pytest.mark.parametrize("name", [
    "PATH",
    "HOME",
    "JAVA_HOME",
    "MY_VAR",
    "LANG",
    "PYTHONHASHSEED",
])
def test_is_sensitive_negative_cases(name):
    """Vars non-sensitive não batem (PATH, HOME, JAVA_HOME, etc.)."""
    assert is_sensitive(name) is False
