"""Tests for ``_suppress_superseded_validator_claims`` (A8 dedup).

WR-01 (review pr27 r3): a supressão do draft ``validator-claim`` ORIGINAL
(quando um ``validator-claim-unresolvable`` derivado o substitui) deve casar
pelo ``fixture_path`` COMPLETO, não pelo basename (``Path(...).stem``). Dois
validator-claim fixtures em diretórios distintos mas com o MESMO basename não
podem se canibalizar: se um é irresolvível, só o draft DELE é suprimido — o
outro claim legítimo sobrevive.
"""

from __future__ import annotations

from typing import Any

from engine.qa import _suppress_superseded_validator_claims


def _draft(fixture_path: str, fid: str) -> dict[str, Any]:
    return {
        "id": fid,
        "fingerprint": fid * 8,
        "vector": "validator-claim",
        "severity": "high",
        "title": "validator que mente",
        "description": "validator forge nao detecta o caso",
        "evidence": {
            "fixture_path": fixture_path,
            "sandbox_result": None,
        },
    }


def test_same_basename_distinct_paths_only_unresolvable_suppressed() -> None:
    """WR-01: dois drafts com mesmo basename, paths diferentes; um
    irresolvível → só o irresolvível é suprimido, o legítimo sobrevive."""
    unresolvable = _draft("fixtures/dir-a/validator-claim-foo.yaml", "a")
    legit = _draft("fixtures/dir-b/validator-claim-foo.yaml", "b")

    out = _suppress_superseded_validator_claims(
        [unresolvable, legit],
        {"fixtures/dir-a/validator-claim-foo.yaml"},
    )

    survived_paths = {
        f["evidence"]["fixture_path"]
        for f in out
        if f.get("vector") == "validator-claim"
    }
    assert "fixtures/dir-b/validator-claim-foo.yaml" in survived_paths, (
        "draft legítimo com mesmo basename foi suprimido por engano"
    )
    assert "fixtures/dir-a/validator-claim-foo.yaml" not in survived_paths, (
        "draft irresolvível deveria ter sido suprimido"
    )


def test_single_claim_unresolvable_still_suppressed() -> None:
    """Comportamento normal (1 claim) preservado: o draft é suprimido."""
    unresolvable = _draft("fixtures/validator-claim-bar.yaml", "c")
    out = _suppress_superseded_validator_claims(
        [unresolvable],
        {"fixtures/validator-claim-bar.yaml"},
    )
    assert out == [], "single-claim unresolvable não foi suprimido"


def test_empty_suppression_set_is_noop() -> None:
    """Set vazio → nada suprimido (no-op, lista nova)."""
    draft = _draft("fixtures/validator-claim-baz.yaml", "d")
    out = _suppress_superseded_validator_claims([draft], set())
    assert out == [draft]


def test_non_validator_claim_untouched() -> None:
    """Findings de outros vetores nunca são suprimidos."""
    other = {"vector": "coverage", "evidence": {"fixture_path": "x.yaml"}}
    out = _suppress_superseded_validator_claims([other], {"x.yaml"})
    assert out == [other]
