"""Testes para o registro explicito de OPENCODE -> IntentFileAdapter (Veredito B).

Wave 2 Task 2.1: pesquisa W2.T0 concluiu que opencode nao e compativel com
adapter in-process (ver docs/research/opencode-tool-api.md). O registro em
``_resolve_adapter`` e agora explicito, nao mais um KeyError acidental.

Cobertura:
1. ``detect_host`` retorna ``HostName.OPENCODE`` quando uma var ``OPENCODE_*``
   esta presente e CLAUDECODE esta ausente (sem config override).
2. ``_resolve_adapter`` sob OPENCODE resolve para uma instancia de
   ``IntentFileAdapter`` (isinstance check — Veredito B).
3. Config ``host: opencode`` em forge-config.yaml tambem resolve
   ``IntentFileAdapter`` (caminho config override).

Nota de env scrub (memoria do projeto): todos os testes que chamam
``detect_host`` devem limpar vars CLAUDECODE / OPENCODE_* / CODEX* /
CURSOR_* para determinismo, e setar apenas o que o caso exige.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from engine.host.detect import detect_host, _clear_cache
from engine.host.adapter import HostName
from engine.host.adapters.intent_file import IntentFileAdapter


# Vars de ambiente que precisam de scrub para isolar deteccao
_AGENTIC_VARS = (
    "CLAUDECODE",
    "OPENCODE_VERSION",
    "OPENCODE_CONFIG",
    "OPENCODE_CONFIG_CONTENT",
    "OPENCODE_SERVER_PASSWORD",
    "OPENCODE_SERVER_USERNAME",
    "OPENCODE_DISABLE_AUTOUPDATE",
    "OPENCODE_DISABLE_MOUSE",
    "CODEX_CLI",
    "CODEX",
    "CURSOR_AGENT",
)


@pytest.fixture(autouse=True)
def _scrub_agentic_env(monkeypatch):
    """Remove vars de ambiente agentivas antes de cada teste neste modulo."""
    for var in _AGENTIC_VARS:
        monkeypatch.delenv(var, raising=False)
    _clear_cache()
    yield
    _clear_cache()


# ---------------------------------------------------------------------------
# 1. detect_host retorna OPENCODE quando OPENCODE_* esta presente
# ---------------------------------------------------------------------------


def test_detect_host_returns_opencode_via_opencode_prefix(tmp_path, monkeypatch):
    """detect_host retorna OPENCODE quando qualquer var OPENCODE_* esta setada.

    Sem config override, sem CLAUDECODE, sem TTY em pytest -> OPENCODE deve
    ganhar sobre o fallback intent-file.
    """
    monkeypatch.setenv("OPENCODE_VERSION", "1.0.0")
    assert detect_host(tmp_path) == HostName.OPENCODE


def test_detect_host_opencode_loses_to_claudecode(tmp_path, monkeypatch):
    """CLAUDECODE tem precedencia sobre OPENCODE_* na ordem de deteccao."""
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("OPENCODE_VERSION", "1.0.0")
    assert detect_host(tmp_path) == HostName.CLAUDE_CODE


def test_detect_host_opencode_loses_to_config_override(tmp_path, monkeypatch):
    """Config ``host: intent-file`` vence sobre env OPENCODE_*."""
    monkeypatch.setenv("OPENCODE_VERSION", "1.0.0")
    cfg = tmp_path / ".claude" / "forge" / "forge-config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("host: intent-file\n")
    assert detect_host(tmp_path) == HostName.INTENT_FILE


# ---------------------------------------------------------------------------
# 2. _resolve_adapter retorna IntentFileAdapter quando host e OPENCODE
# ---------------------------------------------------------------------------


def test_resolve_adapter_opencode_returns_intent_file_instance(tmp_path, monkeypatch):
    """_resolve_adapter retorna IntentFileAdapter (Veredito B — explicito).

    O registro de OPENCODE -> IntentFileAdapter em _resolve_adapter e
    agora intencional (nao mais um KeyError acidental). Este teste pina
    que o comportamento e mantido: OPENCODE usa o protocolo DRIFT-1 via
    arquivo, nao um adapter in-process.
    """
    from engine.ui.question import _resolve_adapter
    from engine.host.registry import clear_registry

    # Limpa registry para forcar re-bootstrap (garante que OPENCODE e registrado
    # pelo bloco lazy de _resolve_adapter, nao por estado de teste anterior).
    clear_registry()

    monkeypatch.setenv("OPENCODE_VERSION", "1.0.0")
    adapter = _resolve_adapter(tmp_path)
    assert isinstance(adapter, IntentFileAdapter), (
        "OPENCODE deve resolver para IntentFileAdapter (Veredito B). "
        "Se este teste falhar, um OpencodeAdapter dedicado foi registrado — "
        "revise docs/research/opencode-tool-api.md antes de aceitar."
    )


def test_resolve_adapter_opencode_uses_correct_project_root(tmp_path, monkeypatch):
    """IntentFileAdapter recebe o project_root correto quando host e OPENCODE."""
    from engine.ui.question import _resolve_adapter
    from engine.host.registry import clear_registry

    clear_registry()

    monkeypatch.setenv("OPENCODE_VERSION", "1.0.0")
    adapter = _resolve_adapter(tmp_path)
    # IntentFileAdapter armazena project_root como atributo
    assert adapter.project_root == tmp_path


# ---------------------------------------------------------------------------
# 3. Config host: opencode tambem resolve IntentFileAdapter
# ---------------------------------------------------------------------------


def test_resolve_adapter_config_opencode_resolves_intent_file(tmp_path, monkeypatch):
    """host: opencode em forge-config.yaml tambem usa IntentFileAdapter.

    Projetos que fixam ``host: opencode`` explicitamente devem obter o
    mesmo adapter que a deteccao automatica via env var.
    """
    from engine.ui.question import _resolve_adapter
    from engine.host.registry import clear_registry

    clear_registry()

    cfg = tmp_path / ".claude" / "forge" / "forge-config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("host: opencode\n")

    adapter = _resolve_adapter(tmp_path)
    assert isinstance(adapter, IntentFileAdapter), (
        "Config 'host: opencode' deve resolver para IntentFileAdapter (Veredito B)."
    )
