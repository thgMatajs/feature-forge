"""WR-04 (pilot R6) — `forge undo` abort libera o sentinel `.phase-lock`.

Mesma classe latente do P-17: pós-fix sentinel-first, `current_phase_lock` é
autoritativo no arquivo `.phase-lock`. `_abort_feature` setava
`state.phase_lock = None` e gravava status.json, mas NUNCA removia o sentinel
em disco — então após `forge undo` de uma feature que segurava o lock, o
sentinel sobrevivia e `current_phase_lock` reportava o holder stale.

Agrava: a mensagem de erro do P-17 direciona o usuário a "Run `forge undo` to
release" — o workaround prescrito não liberava o lock por esse vetor.

Fix (WR-04): `_abort_feature` chama `release_phase_lock` (idempotente) após o
`write_l1_status`, cobrindo ambos os paths de set `phase_lock=None`.

Refs:
- .planning/pilot-r6/REVIEW.md §WR-04
"""

from __future__ import annotations

from pathlib import Path

from engine.memory.l1 import (
    L1State,
    _phase_lock_path,
    acquire_phase_lock,
    current_phase_lock,
    write_l1_status,
)
from engine.undo import _abort_feature


def test_abort_releases_phase_lock_sentinel(tmp_project_root: Path) -> None:
    """Após `_abort_feature`, o sentinel `.phase-lock` é removido e
    `current_phase_lock` reporta None — sem holder stale.
    """
    slug = "demo"
    write_l1_status(
        L1State(
            feature_slug=slug,
            status="implementing",
            last_action_at="2026-06-19T00:00:00Z",
            last_action_kind="seed",
        ),
        tmp_project_root,
    )
    # Semeia um lock vivo (sentinel em disco + mirror em status.json).
    assert acquire_phase_lock(slug, tmp_project_root, "implement:demo") is True
    assert _phase_lock_path(slug, tmp_project_root).exists()
    assert current_phase_lock(slug, tmp_project_root) == "implement:demo"

    # Abort deve liberar o lock como efeito colateral.
    assert _abort_feature(tmp_project_root, slug, reason="user abort") is True

    assert current_phase_lock(slug, tmp_project_root) is None, (
        "current_phase_lock deve reportar None após abort (sem holder stale)"
    )
    assert not _phase_lock_path(slug, tmp_project_root).exists(), (
        "o sentinel .phase-lock deve ser removido pelo abort"
    )


def test_abort_releases_lock_when_no_prior_status(tmp_project_root: Path) -> None:
    """Cobre o path `state is None` de `_abort_feature` (L1State construído do
    zero): mesmo sem status.json prévio, um sentinel órfão deve ser liberado.
    """
    slug = "orphan"
    # Sentinel órfão sem status.json correspondente (ex.: crash pós-acquire).
    assert acquire_phase_lock(slug, tmp_project_root, "plan:orphan") is True
    assert _phase_lock_path(slug, tmp_project_root).exists()

    # `read_l1_status` pode existir (acquire espelha status.json), mas o ponto
    # é garantir que o release roda independentemente do branch tomado.
    assert _abort_feature(tmp_project_root, slug, reason="cleanup") is True

    assert current_phase_lock(slug, tmp_project_root) is None
    assert not _phase_lock_path(slug, tmp_project_root).exists()
