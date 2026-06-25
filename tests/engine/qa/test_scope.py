"""Tests for engine.qa.scope — scope resolution for `forge qa`.

Cobre 6 casos canônicos (TDD): feature happy, screen happy, task happy,
paranoid lista features, ambiguity error com 3-caminhos, missing error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.qa.scope import (
    Scope,
    ScopeAmbiguityError,
    ScopeMissingError,
    resolve_scope,
)


# ---------------------------------------------------------------------------
# Helpers — constroi project_root sintético com layout canônico
# ---------------------------------------------------------------------------


def _features_dir(root: Path) -> Path:
    d = root / "docs" / "forge-specs" / "features"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_feature(root: Path, slug: str) -> Path:
    feature = _features_dir(root) / slug
    feature.mkdir(parents=True, exist_ok=True)
    (feature / "screens").mkdir(exist_ok=True)
    (feature / "tasks").mkdir(exist_ok=True)
    return feature


def _make_screen(root: Path, feature_slug: str, screen_id: str) -> Path:
    feature = _make_feature(root, feature_slug)
    screen = feature / "screens" / f"{screen_id}.yaml"
    screen.write_text("id: " + screen_id + "\n", encoding="utf-8")
    return screen


def _make_task(root: Path, feature_slug: str, task_id: str) -> Path:
    feature = _make_feature(root, feature_slug)
    task = feature / "tasks" / f"{task_id}.yaml"
    task.write_text("id: " + task_id + "\n", encoding="utf-8")
    return task


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_resolve_feature_scope_happy(tmp_path: Path) -> None:
    feature = _make_feature(tmp_path, "login-with-google")

    scope = resolve_scope("login-with-google", project_root=tmp_path)

    assert isinstance(scope, Scope)
    assert scope.type == "feature"
    assert scope.target == "login-with-google"
    assert scope.paths == (feature,)


def test_resolve_screen_scope_happy(tmp_path: Path) -> None:
    # Screen vive dentro de uma feature mas o slug "screen-login" NÃO casa em
    # feature dir — só em screens/<id>.yaml.
    _make_feature(tmp_path, "login-with-google")
    screen = _make_screen(tmp_path, "login-with-google", "screen-login")

    scope = resolve_scope("screen-login", project_root=tmp_path)

    assert scope.type == "screen"
    assert scope.target == "screen-login"
    assert scope.paths == (screen,)


def test_resolve_task_scope_happy(tmp_path: Path) -> None:
    _make_feature(tmp_path, "login-with-google")
    task = _make_task(tmp_path, "login-with-google", "TASK-0001")

    scope = resolve_scope("TASK-0001", project_root=tmp_path)

    assert scope.type == "task"
    assert scope.target == "TASK-0001"
    assert scope.paths == (task,)


def test_resolve_paranoid_lists_features(tmp_path: Path) -> None:
    f1 = _make_feature(tmp_path, "feat-alpha")
    f2 = _make_feature(tmp_path, "feat-beta")
    f3 = _make_feature(tmp_path, "feat-gamma")

    scope = resolve_scope("paranoid", project_root=tmp_path, paranoid_max_features=10)

    assert scope.type == "paranoid"
    assert scope.target == "paranoid"
    assert set(scope.paths) == {f1, f2, f3}


def test_scope_ambiguity_raises(tmp_path: Path) -> None:
    # Mesmo input casa em feature dir E screen file: cria feature `ambiguous`
    # e screen `ambiguous.yaml` dentro de outra feature.
    feat = _make_feature(tmp_path, "ambiguous")
    _make_feature(tmp_path, "other-feature")
    screen = _make_screen(tmp_path, "other-feature", "ambiguous")

    with pytest.raises(ScopeAmbiguityError) as excinfo:
        resolve_scope("ambiguous", project_root=tmp_path)

    msg = str(excinfo.value)
    # 3-caminhos enumerados no texto do erro
    assert "1)" in msg
    assert "2)" in msg
    assert "3)" in msg
    assert str(feat) in msg
    assert str(screen) in msg


def test_scope_missing_raises(tmp_path: Path) -> None:
    _features_dir(tmp_path)  # estrutura existe, mas sem matches

    with pytest.raises(ScopeMissingError) as excinfo:
        resolve_scope("does-not-exist", project_root=tmp_path)

    msg = str(excinfo.value)
    assert "does-not-exist" in msg


# ---------------------------------------------------------------------------
# QA-13 — paranoid scope filtra features com state aborted/archived
# ---------------------------------------------------------------------------


def test_paranoid_excludes_aborted_state(tmp_path: Path) -> None:
    """Features com state=aborted são filtradas do paranoid scope."""
    features_root = tmp_path / "docs" / "forge-specs" / "features"
    features_root.mkdir(parents=True)

    # Feature ativa
    (features_root / "alpha").mkdir()
    (features_root / "alpha" / "status.json").write_text(
        '{"state": "planning"}', encoding="utf-8"
    )

    # Feature aborted (deve ser excluída)
    (features_root / "beta").mkdir()
    (features_root / "beta" / "status.json").write_text(
        '{"state": "aborted"}', encoding="utf-8"
    )

    scope = resolve_scope("paranoid", project_root=tmp_path, paranoid_max_features=10)

    assert features_root / "alpha" in scope.paths, "alpha (planning) should be included"
    assert features_root / "beta" not in scope.paths, "beta (aborted) should be excluded"


def test_paranoid_excludes_archived_state(tmp_path: Path) -> None:
    """Features com state=archived são filtradas do paranoid scope."""
    features_root = tmp_path / "docs" / "forge-specs" / "features"
    features_root.mkdir(parents=True)

    (features_root / "alpha").mkdir()
    (features_root / "alpha" / "status.json").write_text(
        '{"state": "done"}', encoding="utf-8"
    )

    (features_root / "gamma").mkdir()
    (features_root / "gamma" / "status.json").write_text(
        '{"state": "archived"}', encoding="utf-8"
    )

    scope = resolve_scope("paranoid", project_root=tmp_path, paranoid_max_features=10)

    assert features_root / "alpha" in scope.paths, "alpha (done) should be included"
    assert features_root / "gamma" not in scope.paths, "gamma (archived) should be excluded"


def test_paranoid_includes_when_status_missing_or_malformed(tmp_path: Path) -> None:
    """Edge cases (fail-safe = include): status.json ausente, malformado, sem campo state."""
    features_root = tmp_path / "docs" / "forge-specs" / "features"
    features_root.mkdir(parents=True)

    # Sem status.json (legacy pre-Gap-8)
    (features_root / "legacy").mkdir()

    # status.json malformado
    (features_root / "broken").mkdir()
    (features_root / "broken" / "status.json").write_text(
        "{not valid json", encoding="utf-8"
    )

    # status.json sem campo state
    (features_root / "stateless").mkdir()
    (features_root / "stateless" / "status.json").write_text(
        '{"subtype": "feature"}', encoding="utf-8"
    )

    scope = resolve_scope("paranoid", project_root=tmp_path, paranoid_max_features=10)

    expected = {
        features_root / "legacy",
        features_root / "broken",
        features_root / "stateless",
    }
    assert set(scope.paths) == expected, (
        "fail-safe edge cases (missing/malformed status.json, missing state) "
        "devem todos ser incluídos; nada além disso deve aparecer"
    )
