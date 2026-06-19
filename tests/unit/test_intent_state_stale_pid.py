"""Unit tests — STALE-1: liveness probe em detect_race.

`detect_race` (intent_state.py) lia o `pid` do pending mas nunca conferia se o
processo ainda vivia. Pending de processo crashado travava a raia até o stale
threshold (~10 min). STALE-1 adiciona `os.kill(pid, 0)` antes de levantar
`RaceDetectedError`: PID morto → varre (return None); PID vivo → race genuína.

Refs:
- docs/superpowers/specs/2026-06-18-w-debt.md §2.2 (STALE-1)
- docs/superpowers/plans/2026-06-18-w-debt.md Task 5
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.ui import intent_state


def _recent_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _pending_payload(*, intent_id: str, created_at: str, pid: int) -> dict:
    return {
        "schema-version": 1,
        "intent-id": intent_id,
        "command": "init",
        "command-args": [],
        "kind": "ask",
        "question": "Qual preset?",
        "options": {"kmp-mobile": "Android + iOS + KMP shared"},
        "default": "kmp-mobile",
        "allow-pause": True,
        "created-at": created_at,
        "pid": pid,
        "checkpoint-path": ".claude/.init-checkpoint.yaml",
    }


def _pending_path(project_root: Path) -> Path:
    return project_root / ".claude" / "forge" / "state" / "forge-pending.json"


def _write_pending(project_root: Path, payload: dict) -> Path:
    path = _pending_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_detect_race_sweeps_recent_pending_of_dead_pid(tmp_project_root, monkeypatch):
    """Pending recente mas de PID morto → varre, segue (não trava a raia)."""
    path = _write_pending(
        tmp_project_root,
        _pending_payload(
            intent_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            created_at=_recent_iso(),
            pid=84210,
        ),
    )

    def _fake_kill(pid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(intent_state.os, "kill", _fake_kill)

    assert intent_state.detect_race(tmp_project_root, new_intent_id="brand-new") is None
    assert not path.exists(), "pending de PID morto deve ser varrido"


def test_detect_race_raises_for_recent_pending_of_live_pid(tmp_project_root):
    """Pending recente de PID vivo (o próprio processo do teste) → race genuína."""
    live_pid = os.getpid()
    path = _write_pending(
        tmp_project_root,
        _pending_payload(
            intent_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
            created_at=_recent_iso(),
            pid=live_pid,
        ),
    )

    with pytest.raises(intent_state.RaceDetectedError) as exc:
        intent_state.detect_race(tmp_project_root, new_intent_id="other-id")
    assert str(live_pid) in str(exc.value)
    assert path.exists(), "pending de PID vivo é preservado (race real)"


def test_detect_race_treats_permission_error_as_alive(tmp_project_root, monkeypatch):
    """PermissionError em os.kill = processo vivo de outro dono → trata como vivo."""
    path = _write_pending(
        tmp_project_root,
        _pending_payload(
            intent_id="ffffffff-ffff-4fff-8fff-ffffffffffff",
            created_at=_recent_iso(),
            pid=99999,
        ),
    )

    def _fake_kill(pid, sig):
        raise PermissionError

    monkeypatch.setattr(intent_state.os, "kill", _fake_kill)

    with pytest.raises(intent_state.RaceDetectedError):
        intent_state.detect_race(tmp_project_root, new_intent_id="other-id")
    assert path.exists()


def test_detect_race_sweeps_when_pid_missing_or_invalid(tmp_project_root):
    """Pending recente sem pid usável → não dá pra provar vivo → varre."""
    path = _write_pending(
        tmp_project_root,
        _pending_payload(
            intent_id="abababab-abab-4bab-8bab-abababababab",
            created_at=_recent_iso(),
            pid=0,
        ),
    )
    # pid=0 é inválido pra os.kill(pid, 0) como probe de PID específico → varre.
    assert intent_state.detect_race(tmp_project_root, new_intent_id="brand-new") is None
    assert not path.exists()


def test_detect_race_sweeps_when_pid_non_integer(tmp_project_root):
    """C-49: pid não-inteiro (corrupção) → impossível provar vivo → varre."""
    payload = _pending_payload(
        intent_id="cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd",
        created_at=_recent_iso(),
        pid=0,
    )
    payload["pid"] = "not-a-pid"
    path = _write_pending(tmp_project_root, payload)
    assert intent_state.detect_race(tmp_project_root, new_intent_id="brand-new") is None
    assert not path.exists()


def test_pending_lock_no_ops_on_flock_oserror(tmp_project_root, monkeypatch):
    """C-28 (PR20-B1): flock que levanta OSError (NFS/CIFS/Docker) → no-op.

    Capturar só ImportError travava o comando nesses filesystems. O lock degrada
    pra no-op (tempfile + os.replace seguem como defesa) e a seção crítica roda.
    """
    import sys as _sys

    if _sys.platform == "win32":  # pragma: no cover - POSIX-only branch
        pytest.skip("branch POSIX flock")

    import fcntl

    def _flock_raises(fileno, op):
        raise OSError("lock não suportado neste filesystem")

    monkeypatch.setattr(fcntl, "flock", _flock_raises)

    ran = False
    with intent_state.pending_lock(tmp_project_root):
        ran = True
    assert ran, "a seção crítica deve rodar mesmo com flock indisponível"


def test_detect_race_on_windows_treats_live_pid_as_race(
    tmp_project_root, monkeypatch
):
    """C-49 (PR22-B-01): no Windows o probe os.kill(pid,0) não é confiável.

    Antes do fix, `os.kill(pid, 0)` levantava ValueError no Windows e o bloco
    juntava ValueError com 'processo morto' → apagava o pending SEMPRE →
    desativava a detecção de race na plataforma. Agora, com platform=win32 e
    pid>0, o probe é tratado como não-conclusivo (assume vivo) e a race é
    levantada — o pending é preservado.
    """
    path = _write_pending(
        tmp_project_root,
        _pending_payload(
            intent_id="11111111-1111-4111-8111-111111111111",
            created_at=_recent_iso(),
            pid=84210,
        ),
    )
    monkeypatch.setattr(intent_state.sys, "platform", "win32")

    # WR-02: o branch win32 NUNCA chama os.kill (assume vivo direto), então
    # não há probe pra monkeypatchar. Patchar os.kill aqui era código morto
    # que sugeria cobertura inexistente do caminho ValueError.

    with pytest.raises(intent_state.RaceDetectedError):
        intent_state.detect_race(tmp_project_root, new_intent_id="other-id")
    assert path.exists(), "no Windows, pending de PID vivo NÃO deve ser varrido"
