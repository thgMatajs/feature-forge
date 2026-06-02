"""Regression: ``_check_reuse_findings`` closes the SQLite connection on
every exit path — including non-sqlite3 exceptions raised mid-query.

R3.6 bug: the previous shape used ``conn = sqlite3.connect(...)`` followed
by an inner ``try/finally conn.close()``. That was correct for the
happy path and for ``sqlite3.Error``, but if ``conn.execute(...)`` raised
a non-sqlite3 exception (MemoryError, KeyboardInterrupt, or a wrapper
exception type from a monkeypatched cursor), the connection close was
fragile. Conversion to ``contextlib.closing`` makes the guarantee
unconditional and idiomatic.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from engine import doctor


class _TrackedConn:
    """Wrap a real sqlite3 connection so the test can assert close() ran."""

    def __init__(self, real: sqlite3.Connection) -> None:
        self._real = real
        self.closed = False

    def execute(self, *args, **kwargs):  # noqa: D401
        # First call (PRAGMA) returns real cursor; second call (SELECT) blows up.
        if self._call_count == 0:
            self._call_count += 1
            return self._real.execute(*args, **kwargs)
        raise RuntimeError("simulated non-sqlite3 failure mid-query")

    def close(self) -> None:
        self.closed = True
        self._real.close()

    _call_count = 0


def _seed_graph(project_root: Path) -> Path:
    """Create a minimal graph SQLite with the reuse_findings table populated."""
    from engine.utils.paths import graph_db_path

    db_path = graph_db_path(project_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE reuse_findings (category TEXT, fingerprint TEXT)"
        )
        conn.execute(
            "INSERT INTO reuse_findings VALUES ('consolidate-within-module', 'abc')"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_check_reuse_findings_closes_conn_on_non_sqlite_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A RuntimeError raised by execute() must still close the connection."""
    db_path = _seed_graph(tmp_path)
    assert db_path.exists()

    tracked: list[_TrackedConn] = []
    real_connect = sqlite3.connect

    def tracked_connect(target: str, *args, **kwargs) -> _TrackedConn:
        wrapped = _TrackedConn(real_connect(target, *args, **kwargs))
        tracked.append(wrapped)
        return wrapped  # type: ignore[return-value]

    monkeypatch.setattr(doctor.sqlite3, "connect", tracked_connect)

    # Call the private function directly to drive the path under test.
    # The RuntimeError raised by `execute()` propagates out (it's not a
    # sqlite3.Error), but the close() must still have fired.
    with pytest.raises(RuntimeError, match="simulated non-sqlite3 failure"):
        doctor._check_reuse_findings(tmp_path)

    assert len(tracked) == 1
    assert tracked[0].closed, (
        "connection leaked — non-sqlite3 exception escaped without close()"
    )


def test_check_reuse_findings_closes_conn_on_happy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard: happy-path queries still close cleanly."""

    class _HappyConn:
        def __init__(self, real: sqlite3.Connection) -> None:
            self._real = real
            self.closed = False

        def execute(self, *args, **kwargs):
            return self._real.execute(*args, **kwargs)

        def close(self) -> None:
            self.closed = True
            self._real.close()

    _seed_graph(tmp_path)
    tracked: list[_HappyConn] = []
    real_connect = sqlite3.connect

    def tracked_connect(target: str, *args, **kwargs) -> _HappyConn:
        wrapped = _HappyConn(real_connect(target, *args, **kwargs))
        tracked.append(wrapped)
        return wrapped  # type: ignore[return-value]

    monkeypatch.setattr(doctor.sqlite3, "connect", tracked_connect)

    report = doctor._check_reuse_findings(tmp_path)
    assert report is not None
    assert tracked and tracked[0].closed, (
        "connection leaked on happy path — close() not called"
    )
