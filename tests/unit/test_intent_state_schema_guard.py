"""Unit tests — SCHEMA-1: schema-version guard simétrico em intent_state.

`_check_schema_version` (intent_state.py) já rodava em `read_response`. SCHEMA-1
estende o guard pra `read_pending` e `detect_race`: version skew num pending
deve virar `SchemaVersionMismatchError` (mensagem mentor-calmo) em vez de
"race"/IO error confuso ou consumo silencioso do shape errado.

Refs:
- docs/superpowers/specs/2026-06-18-w-debt.md §2.2 (SCHEMA-1)
- docs/superpowers/plans/2026-06-18-w-debt.md Task 5
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.ui import intent_state


def _pending_payload(
    *,
    intent_id: str = "11111111-1111-4111-8111-111111111111",
    created_at: str | None = None,
    schema_version: int = 1,
) -> dict:
    return {
        "schema-version": schema_version,
        "intent-id": intent_id,
        "command": "init",
        "command-args": [],
        "kind": "ask",
        "question": "Qual preset?",
        "options": {"kmp-mobile": "Android + iOS + KMP shared"},
        "default": "kmp-mobile",
        "allow-pause": True,
        "created-at": created_at or "2026-06-10T18:42:11Z",
        "pid": 84210,
        "checkpoint-path": ".claude/.init-checkpoint.yaml",
    }


def _pending_path(project_root: Path) -> Path:
    return project_root / ".claude" / "forge" / "state" / "forge-pending.json"


def test_read_pending_raises_on_schema_version_mismatch(tmp_project_root):
    """Pending com schema-version estrangeiro → erro tipado, não consumo silencioso."""
    path = _pending_path(tmp_project_root)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(_pending_payload(schema_version=99)), encoding="utf-8"
    )

    with pytest.raises(intent_state.SchemaVersionMismatchError) as exc:
        intent_state.read_pending(tmp_project_root)
    message = str(exc.value)
    assert "99" in message
    assert "1" in message  # _SCHEMA_VERSION corrente renderizado
    # Forense: o arquivo é preservado.
    assert path.exists()


def test_read_pending_passes_with_current_schema_version(tmp_project_root):
    """Happy path: schema-version=1 round-trips limpo."""
    path = _pending_path(tmp_project_root)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_pending_payload()), encoding="utf-8")

    result = intent_state.read_pending(tmp_project_root)
    assert result is not None
    assert result["schema-version"] == 1


def test_read_pending_returns_none_when_absent(tmp_project_root):
    """Sem pending no disco → None (caminho exit-2 limpo), sem raise."""
    assert intent_state.read_pending(tmp_project_root) is None


def test_detect_race_raises_on_schema_version_mismatch(tmp_project_root):
    """Version skew num pending recente deve dar a mensagem friendly de schema,
    NÃO cair no sweep nem virar RaceDetectedError."""
    recent_iso = (datetime.now(timezone.utc) - timedelta(minutes=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    path = _pending_path(tmp_project_root)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            _pending_payload(
                intent_id="22222222-2222-4222-8222-222222222222",
                created_at=recent_iso,
                schema_version=99,
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(intent_state.SchemaVersionMismatchError) as exc:
        intent_state.detect_race(tmp_project_root, new_intent_id="brand-new")
    assert "99" in str(exc.value)
    # Pending preservado pra inspeção forense — não varrido.
    assert path.exists()
