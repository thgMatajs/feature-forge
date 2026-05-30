"""Unit tests — engine.utils.sha256.

Covers `file_sha256`, `string_sha256`, and the canonical-form fingerprint
invariants from discipline §4 / Decision 25:
- normalised whitespace and case do not change the fingerprint
- substantive edits (name, description) do change it
- provenance set order/duplication does not affect the fingerprint
"""

from __future__ import annotations

from pathlib import Path

from engine.utils import sha256 as sha


def test_file_sha256_deterministic(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello world")
    h1 = sha.file_sha256(p)
    h2 = sha.file_sha256(p)
    assert h1 == h2
    assert len(h1) == 64
    # Known sha256 of b"hello world".
    assert h1 == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_string_sha256_is_utf8_hash():
    assert sha.string_sha256("") == sha.string_sha256("")
    assert sha.string_sha256("a") != sha.string_sha256("b")


def test_canonical_fingerprint_invariant_to_cosmetic_edits():
    base = {
        "type": "promote-to-l2",
        "name": "use-stateflow-for-state",
        "description": "Use MutableStateFlow for screen state",
        "provenance": {"feature-slugs": ["auth", "bonsai"]},
    }
    same = {
        **base,
        # Different whitespace / casing — must normalise away.
        "description": "  USE   MutableStateFlow   for   SCREEN   state ",
    }
    assert sha.canonical_form_fingerprint(base) == sha.canonical_form_fingerprint(same)


def test_canonical_fingerprint_changes_on_substantive_edit():
    base = {
        "type": "promote-to-l2",
        "name": "use-stateflow",
        "description": "Use StateFlow",
        "provenance": {"feature-slugs": ["a"]},
    }
    edited = {**base, "description": "Use SharedFlow instead"}
    assert sha.canonical_form_fingerprint(base) != sha.canonical_form_fingerprint(edited)


def test_canonical_fingerprint_provenance_set_normalised():
    base = {
        "type": "x",
        "name": "n",
        "description": "d",
        "provenance": {"feature-slugs": ["alpha", "beta"]},
    }
    reordered = {**base, "provenance": {"feature-slugs": ["beta", "alpha", "alpha"]}}
    assert sha.canonical_form_fingerprint(base) == sha.canonical_form_fingerprint(reordered)


def test_canonical_fingerprint_handles_missing_provenance():
    p1 = {"type": "x", "name": "n", "description": "d"}
    p2 = {"type": "x", "name": "n", "description": "d", "provenance": {}}
    p3 = {"type": "x", "name": "n", "description": "d", "provenance": {"feature-slugs": []}}
    f1 = sha.canonical_form_fingerprint(p1)
    f2 = sha.canonical_form_fingerprint(p2)
    f3 = sha.canonical_form_fingerprint(p3)
    assert f1 == f2 == f3


def test_canonical_fingerprint_grows_with_new_provenance():
    base = {
        "type": "x",
        "name": "n",
        "description": "d",
        "provenance": {"feature-slugs": ["a"]},
    }
    grown = {**base, "provenance": {"feature-slugs": ["a", "b"]}}
    # Decision 25 — new provenance entry triggers a new fingerprint.
    assert sha.canonical_form_fingerprint(base) != sha.canonical_form_fingerprint(grown)
