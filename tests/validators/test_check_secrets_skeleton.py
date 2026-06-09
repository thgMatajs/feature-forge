"""Skeleton tests for `check_secrets` validator (R1.1 Task 1).

Cobre o esqueleto inicial do gate de secrets:

- `SecretFinding` — dataclass frozen, 5 campos exatos
  (`file: str`, `line: int`, `kind: str`, `snippet: str`, `verified: bool`).
- `_filter_ignored(files, patterns)` — paralelo de `_path_matches_ignore`
  do CC gate (regex inválida → skip silencioso; patterns vazio → input
  íntegro; pattern casa → path filtrado).

Tasks 2-6 vão acumular dispatch + parsers + override + render no mesmo
módulo. Aqui cobrimos só o piso.

Spec: docs/superpowers/specs/2026-06-05-check-secrets-design.md §2
Plan: docs/superpowers/plans/2026-06-05-check-secrets-implementation.md
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

import check_secrets as v


# ── SecretFinding dataclass shape ────────────────────────────────────────────


def test_secret_finding_is_frozen_dataclass_with_five_fields() -> None:
    """SecretFinding: dataclass(frozen=True) com exatamente 5 campos tipados."""
    finding = v.SecretFinding(
        file="app/auth/AuthRepository.kt",
        line=42,
        kind="aws_access_key",
        snippet="AKIAIOSFODNN7EXAMPLE",
        verified=True,
    )
    assert finding.file == "app/auth/AuthRepository.kt"
    assert finding.line == 42
    assert finding.kind == "aws_access_key"
    assert finding.snippet == "AKIAIOSFODNN7EXAMPLE"
    assert finding.verified is True

    field_names = [f.name for f in dataclasses.fields(v.SecretFinding)]
    assert field_names == ["file", "line", "kind", "snippet", "verified"]


def test_secret_finding_is_frozen_assignment_raises() -> None:
    """Atribuir a um campo levanta FrozenInstanceError — protege normalização downstream."""
    finding = v.SecretFinding(
        file="a.kt", line=1, kind="aws", snippet="x", verified=False
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        finding.file = "outro.kt"  # type: ignore[misc]


# ── _filter_ignored helper ────────────────────────────────────────────────────


def test_filter_ignored_empty_patterns_returns_files_unchanged() -> None:
    """Patterns vazio → caller recebe lista equivalente (sem filtragem)."""
    files = [Path("app/Foo.kt"), Path("src/index.ts")]
    out = v._filter_ignored(files, [])
    assert out == files


def test_filter_ignored_drops_matching_paths() -> None:
    """Pattern casa subset → filtra os matches, mantém o resto."""
    files = [
        Path("tests/fixtures/secrets/x.kt"),
        Path("app/Foo.kt"),
    ]
    out = v._filter_ignored(files, [r"tests/fixtures/secrets/.*"])
    assert out == [Path("app/Foo.kt")]


def test_filter_ignored_skips_invalid_regex_silently() -> None:
    """Regex inválida (`[`) não levanta — paralelo da blindagem em
    `_path_matches_ignore` do CC gate. Patterns válidos do resto continuam
    aplicando."""
    files = [
        Path("tests/fixtures/secrets/x.kt"),
        Path("app/Foo.kt"),
    ]
    out = v._filter_ignored(files, ["[", r"tests/fixtures/secrets/.*"])
    # Pattern inválido foi pulado; o válido eliminou o fixture.
    assert out == [Path("app/Foo.kt")]


def test_filter_ignored_union_across_multiple_patterns() -> None:
    """Multiple patterns → união de matches (qualquer pattern bate → drop)."""
    files = [
        Path("tests/fixtures/secrets/x.kt"),
        Path("app/Foo.kt"),
        Path("deps.lock"),
    ]
    out = v._filter_ignored(
        files,
        [r"tests/fixtures/secrets/.*", r".*\.lock$"],
    )
    assert out == [Path("app/Foo.kt")]
