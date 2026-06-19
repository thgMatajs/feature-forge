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

W-003 + C-33: when multiple features have ``last_action_at = None`` the tie-break
must be deterministic. C-33 (PR21-I1) caught that the tie-break key was DEAD —
it read ``feature_slug`` but the ``_status_payload`` payload uses the key
``slug``, so the tie-break always collapsed to ``""`` and the verb depended on
iteration order. These fixtures now mirror the REAL payload shape (key ``slug``)
so the tie-break is actually exercised — testar a ficção ``feature_slug``
mascarava o bug.
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
    feature = {"slug": "demo", "status": state, "last_action_at": "2026-06-18T00:00:00Z"}
    verb = _suggested_next_command([feature])
    assert verb == _EXPECTED[state], f"state {state!r} → {verb!r}, expected {_EXPECTED[state]!r}"


def test_router_covers_all_valid_states():
    """No state in _VALID_STATES is left unmapped (guard against future drift)."""
    assert set(_EXPECTED) == _VALID_STATES


def test_router_no_features_suggests_plan():
    assert _suggested_next_command([]) == "plan"


def test_router_unknown_state_falls_back_to_doctor():
    """An out-of-enum state (corrupt status.json) still degrades to doctor."""
    feature = {"slug": "demo", "status": "garbage", "last_action_at": None}
    assert _suggested_next_command([feature]) == "doctor"


def test_router_deterministic_when_all_timestamps_none():
    """W-003: two features, both last_action_at=None → stable, not order-dependent.

    The tie-break must be explicit (feature slug) so the same input always
    yields the same verb regardless of iteration order of the input list.
    """
    a = {"slug": "alpha", "status": "planning", "last_action_at": None}
    b = {"slug": "beta", "status": "implementing", "last_action_at": None}
    forward = _suggested_next_command([a, b])
    reversed_ = _suggested_next_command([b, a])
    assert forward == reversed_, "router must be order-independent when timestamps tie"
    # Tie-break por slug: "beta" > "alpha" → beta (implementing) → verify.
    assert forward == "verify", (
        "tie-break deve preferir o maior slug deterministicamente (C-33)"
    )


def test_router_prefers_most_recent_timestamp():
    """A real timestamp wins over None regardless of position."""
    old = {"slug": "old", "status": "planning", "last_action_at": None}
    new = {"slug": "new", "status": "verifying", "last_action_at": "2026-06-18T10:00:00Z"}
    assert _suggested_next_command([old, new]) == "verify"
    assert _suggested_next_command([new, old]) == "verify"
