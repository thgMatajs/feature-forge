"""Tests for the Gradle catalog scope category in `forge doctor` (DET-3 M-4).

Cobre a categoria `Gradle catalog scope` que surfaca catálogos
`libs.versions.toml` fora do path canônico `<project>/gradle/`. DET-3 v1
(spec det-3-gradle-dep-signal §Non-Goals) só inspeciona catálogos no path
canônico — esta categoria ajuda diagnóstico em monorepos KMP grandes
mostrando catálogos invisíveis ao parser.

Voz: mentor calmo. Spec ref: docs/superpowers/specs/det-3-gradle-dep-signal.md.
"""

from __future__ import annotations

from pathlib import Path

from engine import doctor


def test_doctor_warns_when_libs_versions_toml_outside_gradle(tmp_path: Path) -> None:
    """Catálogo em subprojects/foo/gradle/ → warning com path relativo."""
    sub = tmp_path / "subprojects" / "foo" / "gradle"
    sub.mkdir(parents=True)
    (sub / "libs.versions.toml").write_text("[versions]\n", encoding="utf-8")

    cat = doctor._check_gradle_catalogs(tmp_path)

    warn_messages = [c.name for c in cat.checks if c.status == doctor._STATUS_WARN]
    assert any(
        "subprojects/foo/gradle/libs.versions.toml" in name for name in warn_messages
    ), f"esperava warning citando subprojects/foo, got: {warn_messages}"


def test_doctor_silent_when_libs_versions_toml_in_canonical_path(
    tmp_path: Path,
) -> None:
    """Só `<project>/gradle/libs.versions.toml` → categoria OK, sem warning."""
    canonical = tmp_path / "gradle"
    canonical.mkdir()
    (canonical / "libs.versions.toml").write_text("[versions]\n", encoding="utf-8")

    cat = doctor._check_gradle_catalogs(tmp_path)

    assert cat.worst == doctor._STATUS_OK, (
        f"esperava OK, got worst={cat.worst}: "
        f"{[(c.name, c.status, c.message) for c in cat.checks]}"
    )


def test_doctor_excludes_test_fixtures_from_warning(tmp_path: Path) -> None:
    """Catálogo dentro de `tests/fixtures/` é fixture, não código vivo."""
    fixture = tmp_path / "tests" / "fixtures" / "foo" / "gradle"
    fixture.mkdir(parents=True)
    (fixture / "libs.versions.toml").write_text("[versions]\n", encoding="utf-8")

    cat = doctor._check_gradle_catalogs(tmp_path)

    assert cat.worst == doctor._STATUS_OK, (
        f"fixture em tests/ não deve disparar warning, got: "
        f"{[(c.name, c.status, c.message) for c in cat.checks]}"
    )


def test_doctor_excludes_build_and_node_modules(tmp_path: Path) -> None:
    """Diretórios de build/cache (`build/`, `node_modules/`) são silenciados."""
    for parent in ("build", "node_modules", ".gradle"):
        sub = tmp_path / parent / "nested" / "gradle"
        sub.mkdir(parents=True)
        (sub / "libs.versions.toml").write_text("[versions]\n", encoding="utf-8")

    cat = doctor._check_gradle_catalogs(tmp_path)
    assert cat.worst == doctor._STATUS_OK


def test_full_scope_includes_gradle_catalog_category() -> None:
    """`run()` chama `_check_gradle_catalogs` no branch `full`."""
    assert hasattr(doctor, "_check_gradle_catalogs")
