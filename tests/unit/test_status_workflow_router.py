"""H-002 + W-003 regression — workflow router covers all states, deterministic.

H-002: ``_suggested_next_command`` mapped only 6 of the 9 ``_VALID_STATES``;
the other 3 (``not-started``/``aborted``/``done``) fell into the ``doctor``
default, guiding the agent wrongly in common real states. The router is the
product of A2 NO-WORKFLOW-ROUTER — partial coverage is a detection-asymmetry
finding.

PHANTOM-STATES (W-DEBT): ``verified`` and ``paused`` were removed from
``_VALID_STATES`` — neither was ever written (verify restores the prior status;
implement goes ``implementing`` → ``done`` directly; pause is ``deferred`` per
Decisão 27). The router now covers exactly 9 states.

W-003: when multiple features have ``last_action_at = None`` the ``max(... or
"")`` tie-break collapsed every candidate to ``""`` and returned the first by
iteration order (filesystem/alphabetical), making the suggested verb a function
of ordering rather than recency. Tie-break must be deterministic and explicit.
"""

from __future__ import annotations

import pytest

from engine.memory.l1 import _VALID_STATES
from engine.status import _suggested_next_command


# Every state in _VALID_STATES must map to a concrete next-verb (never the
# bare "doctor" fallback). PHANTOM-STATES (W-DEBT): `verified`/`paused` removed
# from the enum, so the router covers exactly 9 states.
_EXPECTED = {
    "not-started": "plan",
    "planning": "implement",
    "planned": "implement",
    "implementing": "verify",
    "verifying": "verify",
    "done": "status",
    "deferred": "status",
    "aborted": "plan",
    "blocked-on-external": "reconfigure",
}


@pytest.mark.parametrize("state", sorted(_VALID_STATES))
def test_router_maps_every_valid_state(state):
    """Each of the 9 _VALID_STATES resolves to a concrete verb (never default)."""
    feature = {"feature_slug": "demo", "status": state, "last_action_at": "2026-06-18T00:00:00Z"}
    verb = _suggested_next_command([feature])
    assert verb == _EXPECTED[state], f"state {state!r} → {verb!r}, expected {_EXPECTED[state]!r}"


def test_router_covers_all_valid_states():
    """No state in _VALID_STATES is left unmapped (guard against future drift)."""
    assert set(_EXPECTED) == _VALID_STATES


def test_router_no_features_suggests_plan():
    assert _suggested_next_command([]) == "plan"


def test_router_unknown_state_falls_back_to_doctor():
    """An out-of-enum state (corrupt status.json) still degrades to doctor."""
    feature = {"feature_slug": "demo", "status": "garbage", "last_action_at": None}
    assert _suggested_next_command([feature]) == "doctor"


def test_router_deterministic_when_all_timestamps_none():
    """W-003: two features, both last_action_at=None → stable, not order-dependent.

    The tie-break must be explicit (feature slug) so the same input always
    yields the same verb regardless of iteration order of the input list.
    """
    a = {"feature_slug": "alpha", "status": "planning", "last_action_at": None}
    b = {"feature_slug": "beta", "status": "implementing", "last_action_at": None}
    forward = _suggested_next_command([a, b])
    reversed_ = _suggested_next_command([b, a])
    assert forward == reversed_, "router must be order-independent when timestamps tie"


def test_router_prefers_most_recent_timestamp():
    """A real timestamp wins over None regardless of position."""
    old = {"feature_slug": "old", "status": "planning", "last_action_at": None}
    new = {"feature_slug": "new", "status": "verifying", "last_action_at": "2026-06-18T10:00:00Z"}
    assert _suggested_next_command([old, new]) == "verify"
    assert _suggested_next_command([new, old]) == "verify"
