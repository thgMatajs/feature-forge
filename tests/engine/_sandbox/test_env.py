"""Tests for engine/_sandbox/env.py — safe env builder pra subprocess (QA-11)."""

from __future__ import annotations

import pytest

from engine._sandbox.env import (
    CORE_ALLOWLIST,
    SENSITIVE_PATTERN,
    build_safe_env,
    inspect_dropped,
    is_sensitive,
)


def test_core_allowlist_is_immutable_and_contains_essentials():
    """deep-013: testa a invariante de segurança real — essenciais presentes,
    secrets ausentes — não a manifestação 'add raise AttributeError'."""
    assert isinstance(CORE_ALLOWLIST, frozenset)
    # Essenciais presentes
    for k in ("PATH", "HOME"):
        assert k in CORE_ALLOWLIST
    # Sensíveis canônicos ausentes
    for k in ("GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "DB_PASSWORD"):
        assert k not in CORE_ALLOWLIST


def test_sensitive_pattern_compiles_and_is_case_insensitive():
    """SENSITIVE_PATTERN é regex compilada e search é case-insensitive.

    deep-002: passou de ``.*(...).*`` + ``.match`` para boundary-anchored
    + ``.search`` (a API canônica do is_sensitive). Testes que usavam
    ``.match`` em nomes com prefixo (ex.: GITHUB_TOKEN) precisam usar
    ``.search`` agora — ou simplesmente chamar ``is_sensitive(...)``.
    """
    import re
    assert isinstance(SENSITIVE_PATTERN, re.Pattern)
    assert SENSITIVE_PATTERN.search("GITHUB_TOKEN") is not None
    assert SENSITIVE_PATTERN.search("github_token") is not None
    assert SENSITIVE_PATTERN.search("Github_Token") is not None


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
    # Limpa para isolar (symmetry com test_inspect_dropped_returns_sorted_list)
    monkeypatch.delenv("A_VAR", raising=False)
    monkeypatch.delenv("B_VAR", raising=False)
    monkeypatch.setenv("A_VAR", "a")
    monkeypatch.setenv("B_VAR", "b")

    dropped = inspect_dropped(extras=["A_VAR"])
    assert "A_VAR" not in dropped
    assert "B_VAR" in dropped


# ---------------------------------------------------------------------------
# deep-002: pattern boundary semantics — sem false-positive em AUTHOR/CO_AUTHOR
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", [
    "AUTHOR",
    "AUTHOR_NAME",
    "CO_AUTHOR",
    "CO_AUTHOR_EMAIL",
    "BASE_PATHTOKEN_NAME",  # TOKEN dentro de identificador maior — não-sensível
    "RUST_BACKTRACE",
    "PYTHONPATH",
])
def test_is_sensitive_negative_boundary_cases(name):
    """deep-002: nomes que apenas contêm substring AUTH/TOKEN não disparam."""
    assert is_sensitive(name) is False, (
        f"{name!r} não deve bater SENSITIVE_PATTERN (boundary semantics)"
    )


@pytest.mark.parametrize("name", [
    "AUTH",                       # bare AUTH
    "AUTH_USER",                  # AUTH prefixo
    "USER_AUTH",                  # AUTH sufixo
    "AUTHORIZATION_HEADER",       # AUTHORIZATION token full
    "AUTHORIZATION",              # bare AUTHORIZATION
    "GITHUB_TOKEN",
    "OAUTH_TOKEN",
])
def test_is_sensitive_positive_boundary_cases(name):
    """deep-002: nomes com sufixo/prefixo sensível canônico batem."""
    assert is_sensitive(name) is True, (
        f"{name!r} deve bater SENSITIVE_PATTERN (boundary semantics)"
    )


# ---------------------------------------------------------------------------
# deep-003: build_safe_env defense-in-depth contra sensitive em extras
# ---------------------------------------------------------------------------


def test_build_safe_env_rejects_sensitive_in_extras_by_default(monkeypatch):
    """deep-003: sem allow_sensitive=True, passar GITHUB_TOKEN em extras raise."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_xxx")
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        build_safe_env(extras=["GITHUB_TOKEN"])


def test_build_safe_env_allow_sensitive_lets_grant_pass_through(monkeypatch):
    """deep-003: caller pós-grant passa allow_sensitive=True e a var entra."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_xxx")
    env = build_safe_env(extras=["GITHUB_TOKEN"], allow_sensitive=True)
    assert env["GITHUB_TOKEN"] == "ghp_xxx"


def test_build_safe_env_non_sensitive_extras_default_safe(monkeypatch):
    """deep-003: extras não-sensitive (JAVA_HOME) passam sem allow_sensitive."""
    monkeypatch.setenv("JAVA_HOME", "/opt/java")
    env = build_safe_env(extras=["JAVA_HOME"])
    assert env["JAVA_HOME"] == "/opt/java"


# ---------------------------------------------------------------------------
# deep-008: is_sensitive fail-open em non-str (não TypeError)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, 42, 3.14, [], {}, ("TOKEN",)])
def test_is_sensitive_non_str_returns_false(value):
    """deep-008: non-str não TypeError; retorna False (fail-open)."""
    assert is_sensitive(value) is False
