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


def _pending_payload_no_schema(**kwargs) -> dict:
    """Pending malformed/legado — pré-protocolo, sem o campo `schema-version`."""
    payload = _pending_payload(**kwargs)
    payload.pop("schema-version", None)
    return payload


# ── WR-02: campo-ausente tratado SIMETRICAMENTE em read_pending e detect_race ──
#
# Holistic review (W-DEBT) flagou assimetria: `read_pending` levantava em
# `schema-version` AUSENTE (written=None != _SCHEMA_VERSION) enquanto `detect_race`
# tolerava (guard `if "schema-version" in existing:`). O contrato canônico é:
# AUSÊNCIA = malformed/legado, NÃO version-skew — ambos os caminhos toleram
# idêntico. `SchemaVersionMismatch` significa "versão errada", não "sem versão".


def test_read_pending_tolerates_absent_schema_version(tmp_project_root):
    """Campo AUSENTE não levanta `SchemaVersionMismatch` — simétrico a detect_race.

    Antes do WR-02, `read_pending` levantava aqui (written=None != 1). Agora o
    guard `if "schema-version" in payload:` só checa quando o campo está presente.
    """
    path = _pending_path(tmp_project_root)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(_pending_payload_no_schema()), encoding="utf-8"
    )

    # Não levanta — devolve o payload (malformed/legado é decisão do caller).
    result = intent_state.read_pending(tmp_project_root)
    assert result is not None
    assert "schema-version" not in result


def test_detect_race_tolerates_absent_schema_version(tmp_project_root):
    """Campo AUSENTE não levanta `SchemaVersionMismatch` — mesmo contrato de
    read_pending (segue pro fluxo normal de race).

    Pending recente + intent-id diferente + PID VIVO (os.getpid()) → race
    genuína. O ponto do teste é que o caminho NÃO levanta
    `SchemaVersionMismatchError` por campo-ausente — idêntico a `read_pending`;
    a ausência cai no sweep/race normal, não numa mensagem de skew enganosa.
    """
    import os

    recent_iso = (datetime.now(timezone.utc) - timedelta(minutes=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    payload = _pending_payload_no_schema(
        intent_id="33333333-3333-4333-8333-333333333333",
        created_at=recent_iso,
    )
    payload["pid"] = os.getpid()  # PID vivo → alcança o branch de race genuína.
    path = _pending_path(tmp_project_root)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    # Não levanta SchemaVersionMismatch por campo-ausente — chega na race real.
    with pytest.raises(intent_state.RaceDetectedError):
        intent_state.detect_race(tmp_project_root, new_intent_id="brand-new")


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


# ── M5/M6/B1 (PR #26 review): non-dict root + non-str intent-id guards ─────────
#
# Contrato "nunca vaza traceback bruto": cli.py só mapeia JsonIOError /
# IntentMismatchError / RaceDetectedError. Um forge-response.json ou
# forge-pending.json corrompido (root lista/escalar, ou intent-id não-string
# unhashable) NÃO pode estourar AttributeError/TypeError cru.


def _response_path(project_root: Path) -> Path:
    return project_root / ".claude" / "forge" / "state" / "forge-response.json"


def test_read_response_non_dict_root_raises_typed(tmp_project_root):
    """M5: response root não-dict (lista) → IntentMismatchError tipado +
    arquivo preservado, em vez de AttributeError cru em `_check_schema_version`.
    """
    path = _response_path(tmp_project_root)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(["nao", "sou", "dict"]), encoding="utf-8")

    with pytest.raises(intent_state.IntentMismatchError):
        intent_state.read_response(tmp_project_root, intent_id="alvo")
    assert path.exists()  # forense


def test_read_response_non_str_intent_id_raises_typed(tmp_project_root):
    """M6: intent-id não-string (lista unhashable) → IntentMismatchError tipado,
    não TypeError cru em `written_id in log`.
    """
    path = _response_path(tmp_project_root)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"schema-version": 1, "intent-id": ["a", "b"], "value": 1}),
        encoding="utf-8",
    )

    with pytest.raises(intent_state.IntentMismatchError):
        intent_state.read_response(tmp_project_root, intent_id="alvo")
    assert path.exists()


def test_host_is_replaying_non_dict_root_returns_false(tmp_project_root):
    """host_is_replaying já tolerava non-dict — trava o invariante (não raise)."""
    path = _response_path(tmp_project_root)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps("escalar"), encoding="utf-8")

    assert intent_state.host_is_replaying(tmp_project_root, "guard-id") is False


def test_host_is_replaying_non_str_intent_id_returns_false(tmp_project_root):
    """M6: intent-id não-string em host_is_replaying → False (degrada pro
    caminho humano), não TypeError cru em `written_id in log`.
    """
    path = _response_path(tmp_project_root)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"schema-version": 1, "intent-id": {"k": "v"}}),
        encoding="utf-8",
    )

    assert intent_state.host_is_replaying(tmp_project_root, "guard-id") is False


def test_read_pending_non_dict_root_raises_jsonio(tmp_project_root):
    """B1: pending root não-dict (lista) → JsonIOError tipado (mapeado por
    cli.py), simétrico ao contrato dict da response.
    """
    from engine.utils import json_io

    path = _pending_path(tmp_project_root)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(json_io.JsonIOError):
        intent_state.read_pending(tmp_project_root)
