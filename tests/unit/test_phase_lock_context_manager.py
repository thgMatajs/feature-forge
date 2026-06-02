"""Tests for ``phase_lock_held`` context manager (MD-03).

The context manager replaces the manual flag pattern in ``engine.implement``
(``lock_released = False`` + per-return flips). It must:
  - Release the lock on normal exit when it was acquired.
  - Release the lock on exception exit when it was acquired.
  - NOT release a foreign lock when acquisition lost the race (yields False).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.memory.l1 import (
    acquire_phase_lock,
    current_phase_lock,
    phase_lock_held,
    release_phase_lock,
)


@pytest.fixture
def feature_root(tmp_path: Path) -> tuple[str, Path]:
    """A bare feature slug + project_root that the lock primitives can use."""
    return "feature-x", tmp_path


def test_phase_lock_held_releases_on_normal_exit(
    feature_root: tuple[str, Path],
) -> None:
    slug, root = feature_root
    with phase_lock_held(slug, root, "test-id") as acquired:
        assert acquired is True
        assert current_phase_lock(slug, root) == "test-id"
    assert current_phase_lock(slug, root) is None, (
        "lock should be released after normal context-manager exit"
    )


def test_phase_lock_held_releases_on_exception(
    feature_root: tuple[str, Path],
) -> None:
    slug, root = feature_root
    with pytest.raises(RuntimeError, match="boom"):
        with phase_lock_held(slug, root, "test-id") as acquired:
            assert acquired is True
            raise RuntimeError("boom")
    assert current_phase_lock(slug, root) is None, (
        "lock should be released after exception propagates out of CM"
    )


def test_phase_lock_held_yields_false_on_contention(
    feature_root: tuple[str, Path],
) -> None:
    slug, root = feature_root
    # First holder acquires by direct call.
    assert acquire_phase_lock(slug, root, "first") is True
    try:
        with phase_lock_held(slug, root, "second") as acquired:
            assert acquired is False, "second acquire should have lost the race"
            # The first holder's lock is intact while we are inside this block.
            assert current_phase_lock(slug, root) == "first"
        # Leaving the CM with a lost-race acquisition must NOT release
        # the first holder's lock — guard against that exact regression.
        assert current_phase_lock(slug, root) == "first", (
            "CM must not release a lock it did not acquire"
        )
    finally:
        release_phase_lock(slug, root)


def test_phase_lock_held_is_reentrant_for_same_id(
    feature_root: tuple[str, Path],
) -> None:
    """Same lock id is reentrant per acquire_phase_lock contract."""
    slug, root = feature_root
    assert acquire_phase_lock(slug, root, "shared-id") is True
    try:
        # Reentrant: same id should still yield True. Whether the CM releases
        # on exit is an implementation choice; we just assert the lock is
        # cleared somewhere along the chain.
        with phase_lock_held(slug, root, "shared-id") as acquired:
            assert acquired is True
    finally:
        release_phase_lock(slug, root)
    assert current_phase_lock(slug, root) is None


def test_phase_lock_held_documented_non_reentrant_contract(
    feature_root: tuple[str, Path],
) -> None:
    """Pin the non-reentrant foot-gun (WR-02): CM releases on reentrant entry.

    Hoje, se um caller já segura o lock com o mesmo ``lock_id`` e *entra*
    em ``phase_lock_held`` com esse mesmo id, ``acquire_phase_lock`` devolve
    ``True`` (reentrant ack), o CM yielda ``True`` e — ao sair — chama
    ``release_phase_lock``. Resultado: o caller externo perde o lock sem
    saber.

    Este teste documenta esse comportamento como contrato VIGENTE da
    docstring ("NOT REENTRANT-SAFE"). Se você mudar o CM pra pular o
    release no caso reentrant (ex.: yieldar um sentinel "reentrant" e
    skipar ``release_phase_lock``), **atualize aqui e na docstring de
    ``phase_lock_held`` no mesmo commit** — esta asserção quebra de
    propósito pra alertar.
    """
    slug, root = feature_root
    # Outer holder acquires directly (NOT via CM).
    assert acquire_phase_lock(slug, root, "shared-id") is True
    assert current_phase_lock(slug, root) == "shared-id"
    try:
        # Inner CM with the SAME lock_id — reentrant ack.
        with phase_lock_held(slug, root, "shared-id") as acquired:
            assert acquired is True, (
                "reentrant acquire returns True — CM cannot distinguish"
            )
        # The CM exited and released the lock. The outer holder thought
        # it still owned it. This is the documented foot-gun.
        assert current_phase_lock(slug, root) is None, (
            "phase_lock_held releases on reentrant exit — non-reentrant "
            "contract; see docstring + WR-02"
        )
    finally:
        # Defensive cleanup — release_phase_lock is no-op when absent.
        release_phase_lock(slug, root)
