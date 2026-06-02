"""Regression test for ``detect_after_update``'s sqlite connection lifecycle.

Before R2.5, ``conn = open_db(...)`` was opened ahead of the try/finally,
so if ``load_gradle_modules`` or ``parse_module_dependencies`` raised, the
connection was leaked. The fix moves the call into a try/finally that
always closes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from engine.graph import incremental, gradle_deps
from engine.graph.builder import build_full


@pytest.fixture
def seeded_project(tmp_path: Path) -> tuple[Path, Path]:
    """Build a minimal graph DB so ``detect_after_update`` can proceed
    past its existence check. Returns (project_root, db_path)."""
    project_root = tmp_path / "proj"
    project_root.mkdir()
    # Seed a trivial Kotlin source so build_full has something to ingest.
    src = project_root / "module" / "src"
    src.mkdir(parents=True)
    (src / "Foo.kt").write_text(
        "package demo\nfun foo() { return }\n", encoding="utf-8"
    )
    db = tmp_path / "graph.db"
    build_full(project_root, db_path=db)
    return project_root, db


class _TrackedConn:
    """Light wrapper that tracks close() calls on a real sqlite3 connection."""

    instances: list["_TrackedConn"] = []

    def __init__(self, inner: sqlite3.Connection) -> None:
        self._inner = inner
        self.closed = False
        _TrackedConn.instances.append(self)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)

    def __enter__(self) -> "_TrackedConn":
        self._inner.__enter__()
        return self

    def __exit__(self, *exc: Any) -> Any:
        return self._inner.__exit__(*exc)

    def close(self) -> None:
        self.closed = True
        self._inner.close()


def _patch_open_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``open_db`` so we can observe close() on the returned object."""
    _TrackedConn.instances = []
    real_open_db = incremental.open_db

    def tracking_open_db(path: Any, *, create: bool = True) -> _TrackedConn:
        inner = real_open_db(path, create=create)
        return _TrackedConn(inner)

    monkeypatch.setattr(incremental, "open_db", tracking_open_db)


def test_detect_after_update_closes_conn_on_load_gradle_modules_failure(
    seeded_project: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If load_gradle_modules raises after open_db, the function must still
    close the connection (no leak) and degrade gracefully (return [])."""
    project_root, db = seeded_project

    _patch_open_db(monkeypatch)

    def boom(*_a: Any, **_kw: Any) -> dict[str, str]:
        raise RuntimeError("simulated gradle-discovery failure")

    monkeypatch.setattr(incremental, "load_gradle_modules", boom)

    result = incremental.detect_after_update(
        project_root,
        [project_root / "module" / "src" / "Foo.kt"],
        db_path=db,
    )

    assert result == [], (
        "expected best-effort empty list when discovery raises; got " + repr(result)
    )
    assert _TrackedConn.instances, "open_db never called — test setup wrong"
    leaked = [c for c in _TrackedConn.instances if not c.closed]
    assert not leaked, (
        f"detect_after_update leaked {len(leaked)}/{len(_TrackedConn.instances)} "
        "sqlite connection(s) after load_gradle_modules raised"
    )


def test_detect_after_update_closes_conn_on_parse_module_dependencies_failure(
    seeded_project: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same guarantee when the second pre-try call (parse_module_dependencies)
    is the one to raise."""
    project_root, db = seeded_project

    _patch_open_db(monkeypatch)

    def boom(*_a: Any, **_kw: Any) -> dict[str, Any]:
        raise RuntimeError("simulated dep-graph parse failure")

    monkeypatch.setattr(gradle_deps, "parse_module_dependencies", boom)

    result = incremental.detect_after_update(
        project_root,
        [project_root / "module" / "src" / "Foo.kt"],
        db_path=db,
    )

    assert result == []
    leaked = [c for c in _TrackedConn.instances if not c.closed]
    assert not leaked, (
        f"detect_after_update leaked {len(leaked)} sqlite connection(s) "
        "after parse_module_dependencies raised"
    )
