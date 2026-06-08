"""Tests for engine/_sandbox/env.py — safe env builder pra subprocess (QA-11)."""

from __future__ import annotations

import pytest

from engine._sandbox.env import CORE_ALLOWLIST, SENSITIVE_PATTERN
from engine._sandbox.env import build_safe_env, is_sensitive


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


def test_build_safe_env_returns_core_allowlist_intersection(monkeypatch):
    """Output contém SÓ vars de CORE_ALLOWLIST ∩ os.environ."""
    # Limpa qualquer var poluente do ambiente do test runner
    for k in ("PATH", "HOME", "ARBITRARY_VAR", "EVIL_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/tmp/h")
    monkeypatch.setenv("ARBITRARY_VAR", "x")

    env = build_safe_env()

    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/tmp/h"
    assert "ARBITRARY_VAR" not in env


def test_build_safe_env_drops_arbitrary_var(monkeypatch):
    """Var fora de CORE_ALLOWLIST é dropada."""
    monkeypatch.setenv("MY_CUSTOM_FOO", "bar")
    env = build_safe_env()
    assert "MY_CUSTOM_FOO" not in env


def test_build_safe_env_drops_sensitive_pattern_match(monkeypatch):
    """Vars que batem SENSITIVE_PATTERN são dropadas (mesmo se não fosse arbitrária)."""
    monkeypatch.setenv("AWS_TOKEN", "AKIA...")
    monkeypatch.setenv("MY_SECRET", "shh")
    monkeypatch.setenv("DB_PASSWORD", "p4ssw0rd")
    env = build_safe_env()
    assert "AWS_TOKEN" not in env
    assert "MY_SECRET" not in env
    assert "DB_PASSWORD" not in env


def test_build_safe_env_includes_extras(monkeypatch):
    """Extras declarados são injetados se existirem em os.environ."""
    monkeypatch.setenv("JAVA_HOME", "/opt/java")
    env = build_safe_env(extras=["JAVA_HOME"])
    assert env["JAVA_HOME"] == "/opt/java"


def test_build_safe_env_extras_filtered_if_not_in_environ(monkeypatch):
    """Extras ausentes em os.environ silenciosamente filtrados (sem raise)."""
    monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
    env = build_safe_env(extras=["NONEXISTENT_VAR"])
    assert "NONEXISTENT_VAR" not in env


def test_build_safe_env_raises_typeerror_on_non_string_extras():
    """Extras não-string raise TypeError (cobertura indireta de _validate_extras)."""
    with pytest.raises(TypeError, match="int"):
        build_safe_env(extras=[1])  # type: ignore[list-item]


def test_build_safe_env_empty_extras_default(monkeypatch):
    """Chamada sem extras retorna só CORE ∩ os.environ."""
    # Limpa todas as CORE_ALLOWLIST vars do runner para garantir só PATH
    for k in CORE_ALLOWLIST:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PATH", "/bin")
    monkeypatch.setenv("RANDOM_VAR", "z")
    env = build_safe_env()
    assert env == {"PATH": "/bin"}


from engine._sandbox.env import inspect_dropped


def test_inspect_dropped_returns_sorted_list(monkeypatch):
    """Output determinístico (lista ordenada alfabeticamente)."""
    # Limpa para isolar
    for k in ("Z_VAR", "A_VAR", "M_VAR"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("Z_VAR", "z")
    monkeypatch.setenv("A_VAR", "a")
    monkeypatch.setenv("M_VAR", "m")

    dropped = inspect_dropped()

    # Pode haver outras vars no env do test runner; só checamos que
    # estas 3 aparecem ordenadas relativamente entre si.
    indices = [dropped.index(v) for v in ("A_VAR", "M_VAR", "Z_VAR")]
    assert indices == sorted(indices)
    assert dropped == sorted(dropped)


def test_inspect_dropped_respects_extras(monkeypatch):
    """Vars listadas em extras não aparecem em dropped."""
    monkeypatch.setenv("A_VAR", "a")
    monkeypatch.setenv("B_VAR", "b")

    dropped = inspect_dropped(extras=["A_VAR"])
    assert "A_VAR" not in dropped
    assert "B_VAR" in dropped
