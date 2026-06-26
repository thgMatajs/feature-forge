"""Task A (W-RULES) — testes do intent-kind classify.

TDD RED: escritos PRIMEIRO, verificados como FAILING antes de qualquer
implementacao. Exercitam a API publica do classify end-to-end:
- AskKind.CLASSIFY existe e tem o valor correto.
- IntentFileAdapter.classify faz roundtrip (1a chamada pausa; 2a consome).
- TtyAdapter.classify retorna None (host sem LLM).
- Extensao aditiva: kinds existentes intocados.
"""
import pytest
from engine.ui import intent_state
from engine.utils.paths import forge_state_dir
from engine.host.adapter import AskKind, PausedForInputError
from engine.host.adapters.intent_file import IntentFileAdapter
from engine.host.adapters.tty import TtyAdapter

FRAGS = [{"id": "f1", "source": ".claude/rules/x.md", "heading": "## Reuso", "text": "consulte o graph antes"}]
SCHEMA = {"tiers": [0, 1]}


def _scrub(monkeypatch):
    for v in ("CLAUDECODE", "OPENCODE_BIN", "CODEX", "CURSOR_TRACE_ID"):
        monkeypatch.delenv(v, raising=False)


def test_classify_kind_exists():
    assert AskKind.CLASSIFY.value == "classify"


def test_classify_pending_then_response_roundtrip(tmp_path, monkeypatch):
    _scrub(monkeypatch)
    (tmp_path / ".git").mkdir()
    adapter = IntentFileAdapter(project_root=tmp_path)
    # 1a invocacao: sem response -> escreve pending classify + pausa (exit 2).
    with pytest.raises(PausedForInputError):
        adapter.classify(fragments=FRAGS, schema=SCHEMA)
    pending = intent_state.read_pending(tmp_path)
    assert pending["kind"] == "classify"
    assert pending["fragments"] == FRAGS
    iid = pending["intent-id"]
    # host fulfilla: escreve response (em forge_state_dir, ancorado por intent_state).
    # schema-version e obrigatorio (read_response valida estritamente - IN-03).
    intent_state.write_response(tmp_path, {
        "schema-version": 1,
        "intent-id": iid,
        "classification": [{"fragment_id": "f1", "tier": 1, "rationale": "ref",
                            "mem_note": {"type": "reference", "title": "Reuso x",
                                         "body": "consulte o graph antes", "tags": ["reuso"]}}],
    })
    # 2a invocacao (mesmos fragments -> mesmo intent-id): consome a response.
    result = adapter.classify(fragments=FRAGS, schema=SCHEMA)
    assert result is not None and result[0]["tier"] == 1 and result[0]["fragment_id"] == "f1"


def test_classify_tty_returns_none(tmp_path):
    # Host sem LLM (TTY) -> None (distinto de lista vazia). _reduce_rules pula com aviso.
    adapter = TtyAdapter(project_root=tmp_path)
    assert adapter.classify(fragments=FRAGS, schema=SCHEMA) is None


def test_existing_ask_kinds_unchanged():
    # H-102: extensao aditiva - os kinds existentes seguem.
    assert {k.value for k in AskKind} >= {"ask", "ask_multi", "ask_text", "ask_three_paths", "confirm", "classify"}
