"""H-07 regression: unset-seed mentor_calmo RNG must NOT be module-global."""

from __future__ import annotations

from engine.persona import mentor_calmo


def test_rng_without_seed_is_isolated_per_call() -> None:
    """Two consecutive calls with seed=None can return different choices.

    With the old module-level _rng, set_seed(42) globally pinned ALL future
    calls. Post-fix, calling set_seed(None) resets to a fresh RNG per call
    so future code that depends on randomness isn't accidentally pinned.
    """
    mentor_calmo.set_seed(None)
    # Sample 20 greetings — with multiple options and unseeded RNG, we should
    # see at least 2 distinct values with overwhelming probability.
    samples = {mentor_calmo.greeting() for _ in range(20)}
    assert len(samples) >= 2, (
        "Unseeded RNG returned identical phrase on 20 calls — module-level "
        "state leak suspected."
    )


def test_rng_seed_locks_choice() -> None:
    """Seeded mode must still produce deterministic output (existing contract)."""
    mentor_calmo.set_seed(42)
    first = mentor_calmo.greeting()
    mentor_calmo.set_seed(42)
    second = mentor_calmo.greeting()
    assert first == second
    mentor_calmo.set_seed(None)
