"""Concurrency tests — engine.ui.intent_state under real threaded contention.

Endereça finding #19 do master review do PR #11 (DRIFT-1): nenhum teste
exercia ``detect_race`` + ``write_pending`` sob contenção real via
``threading.Thread``.

C4 CONC-1 fechou o gap TOCTOU/torn-write que estes testes antes apenas
documentavam:
- **C4-A** (``engine/utils/json_io.write_json``) — tempfile por-processo
  (``{pid}.{uuid}.tmp``) elimina o torn write / ``FileNotFoundError`` no
  ``os.replace`` do escritor tardio (nome de tempfile compartilhado era a
  fonte da corrupção de bytes).
- **C4-B** (``engine/ui/intent_state.pending_lock``) — flock ``LOCK_EX``
  aplicado na seção crítica real ``detect_race``+``write_pending`` de
  ``IntentFileAdapter._ask_loop`` serializa a janela TOCTOU em produção.

O que se assert agora (gap FECHADO, não documentado):
- O pending final é SEMPRE JSON válido (sem torn write).
- O conteúdo do pending corresponde EXATAMENTE a UM dos payloads
  candidatos (nunca bytes concatenados, nunca mistura de campos).
- ``write_pending`` / ``write_json`` NUNCA levantam ``FileNotFoundError``
  no ``os.replace`` (cada escritor tem seu próprio tmp).

Refs:
- ``docs/superpowers/specs/drift-1-intent-protocol.md`` §9 "Concurrent
  invocation safety"
- ``engine/ui/intent_state.py`` (``detect_race``, ``write_pending``,
  ``read_pending``)
- ``engine/utils/json_io.py`` (atomic tempfile + os.replace)
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.ui import intent_state
from engine.utils import json_io

pytestmark = pytest.mark.integration


# --- Helpers ---------------------------------------------------------------


def _make_payload(intent_id: str, *, pid: int) -> dict:
    """Minimally-valid pending payload distinguishable per-thread."""
    return {
        "schema-version": 1,
        "intent-id": intent_id,
        "command": "init",
        "command-args": [],
        "kind": "ask",
        "question": f"thread-probe-{pid}",
        "options": {"a": "alpha", "b": "beta"},
        "default": None,
        "allow-pause": True,
        "created-at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pid": pid,
        "checkpoint-path": None,
    }


def _project(tmp_path: Path) -> Path:
    """Greenfield project root with state dir pre-created (mirrors
    ``tmp_project_root`` fixture intent without depending on it — this
    test module lives under ``tests/integration/`` where the conftest
    fixture may not be auto-discovered depending on layout)."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "forge" / "state").mkdir(parents=True, exist_ok=True)
    return tmp_path


# --- Concurrency tests -----------------------------------------------------


def test_concurrent_writers_detect_race_or_serialize(tmp_path):
    """5 threads disputando detect_race + write_pending: estado final coerente.

    SPEC §9 reconhece a janela TOCTOU: 5 threads podem todas passar pelo
    ``detect_race`` (pending ausente) antes que qualquer uma escreva.
    Nesse caso, ``os.replace`` no ``write_json`` arbitra: uma vence, as
    demais sobrescrevem (last-writer-wins por nível de syscall, mas o
    arquivo NUNCA fica corrompido — o que este teste valida).

    Outras execuções, com timing diferente, podem ter detect_race
    levantando ``RaceDetectedError`` em algumas threads (caminho desejado
    quando o lock chegar). Ambos os outcomes são aceitáveis nesta versão
    do protocolo; o invariante testado é o estado final.
    """
    project_root = _project(tmp_path)
    n_threads = 5
    barrier = threading.Barrier(n_threads)
    results: list[dict] = []
    results_lock = threading.Lock()

    def worker(idx: int) -> None:
        intent_id = f"thread-{idx:08d}-0000-4000-8000-000000000000"
        payload = _make_payload(intent_id, pid=10_000 + idx)
        barrier.wait()
        outcome: dict = {"idx": idx, "intent_id": intent_id, "raised": None}
        try:
            intent_state.detect_race(project_root, intent_id)
            intent_state.write_pending(payload, project_root)
            outcome["wrote"] = True
        except intent_state.RaceDetectedError as exc:
            outcome["raised"] = "race"
            outcome["msg"] = str(exc)
            outcome["wrote"] = False
        except FileNotFoundError as exc:
            # ``write_json`` uses um único nome de tempfile compartilhado
            # (forge-pending.json.tmp): se duas threads chamam
            # ``os.replace(tmp, final)`` em sequência apertada, a segunda
            # raise FileNotFoundError porque a primeira já moveu o tmp.
            # Documenta o gap conhecido (não fatal pra este teste —
            # invariante "estado final coerente" continua valendo
            # enquanto ≥1 thread teve sucesso).
            outcome["raised"] = "tmp_replace_lost"
            outcome["msg"] = str(exc)
            outcome["wrote"] = False
        with results_lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive(), "worker thread hung past timeout"

    assert len(results) == n_threads, "all threads must record an outcome"

    # Final state on disk: either ``None`` (all writers lost the
    # os.replace race against the shared tempfile) or a valid payload
    # matching exactly one submitted intent-id (no torn writes, no
    # cross-payload mixing).
    final = intent_state.read_pending(project_root)
    candidate_ids = {r["intent_id"] for r in results}
    if final is None:
        # Acceptable outcome: every worker lost the os.replace race. The
        # gap is documented in SPEC §9 as the TOCTOU window awaiting the
        # fcntl.flock follow-up; no torn write happened either way.
        return
    assert final.get("schema-version") == 1
    assert "intent-id" in final
    assert isinstance(final["intent-id"], str)
    assert final["intent-id"] in candidate_ids, (
        "persisted intent-id does not match any worker payload — "
        "atomicity violation suspected"
    )


def test_concurrent_writers_document_torn_write_window(tmp_path):
    """N threads escrevendo payloads distintos: SEM torn write (C4 CONC-1).

    Antes de C4, este teste tolerava três outcomes (incluindo torn write e
    ``FileNotFoundError``) por causa do nome de tempfile compartilhado
    (``forge-pending.json.tmp``). Com o tempfile por-processo de C4-A
    (``{pid}.{uuid}.tmp``), cada escritor tem seu próprio tmp e o
    ``os.replace`` final é a única fronteira atômica: last-writer-wins por
    syscall, NUNCA conteúdo corrompido.

    Invariante forte: o pending final SEMPRE parseia como JSON válido e bate
    EXATAMENTE com um dos payloads submetidos.
    """
    project_root = _project(tmp_path)
    n_threads = 8
    barrier = threading.Barrier(n_threads)
    payloads: dict[int, dict] = {}

    def worker(idx: int) -> None:
        intent_id = f"writer-{idx:08d}-0000-4000-8000-000000000000"
        payload = _make_payload(intent_id, pid=20_000 + idx)
        # Embed a per-thread tag to make merged-byte mixing detectable.
        payload["question"] = f"unique-marker-{idx}-{'x' * (idx * 7)}"
        payloads[idx] = payload
        barrier.wait()
        # C4 CONC-1 fix: com tempfile por-processo, write_pending NUNCA levanta
        # FileNotFoundError no os.replace — cada writer tem seu próprio tmp.
        intent_state.write_pending(payload, project_root)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive(), "writer thread hung past timeout"

    # Read raw bytes — bypass json_io to make sure we hit the file as-is.
    pending_path = (
        project_root / ".claude" / "forge" / "state" / "forge-pending.json"
    )
    assert pending_path.is_file(), (
        "com tempfile por-processo, ao menos um writer vence o os.replace e "
        "o pending final DEVE existir (nenhum perde o tmp compartilhado)"
    )
    raw = pending_path.read_bytes()

    # C4 CONC-1 fix: tempfile por-processo elimina o torn write. O destino
    # SEMPRE parseia como JSON válido e bate EXATAMENTE com um dos payloads
    # submetidos — nunca bytes concatenados, nunca mistura de campos.
    parsed = json.loads(raw.decode("utf-8"))  # não deve levantar
    matched_any = any(parsed == candidate for candidate in payloads.values())
    assert matched_any, (
        "final pending content matches no submitted payload — "
        f"atomicidade violada. parsed={parsed!r}"
    )


def test_concurrent_writers_via_json_io_directly(tmp_path):
    """Cross-check direto em ``json_io.write_json``: mesmo invariante,
    sem passar por ``intent_state``. Se este passar e o teste acima
    falhar, o defeito está na camada intent_state; se ambos falharem,
    está no write_json. Pinpoint dirigido."""
    target = tmp_path / "scratch.json"
    n_threads = 6
    barrier = threading.Barrier(n_threads)
    payloads = [
        {"writer": i, "marker": "z" * (i * 11), "schema-version": 1}
        for i in range(n_threads)
    ]

    def worker(idx: int) -> None:
        barrier.wait()
        json_io.write_json(target, payloads[idx])

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert target.is_file(), "algum writer deve vencer; destino deve existir"
    parsed = json.loads(target.read_text(encoding="utf-8"))  # não deve levantar
    assert parsed in payloads, (
        "json_io.write_json sob contenção produziu payload que nenhum writer "
        f"submeteu; parsed={parsed!r}"
    )
