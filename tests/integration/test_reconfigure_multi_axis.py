"""Integration: reconfigure multi-axis backend submenu.

W7.3 do plano DET-6. Cobre AC-8 do SPEC `det-6-multi-axis-backend.md`.

Cenário-âncora: `forge reconfigure` → categoria `backend` → submenu
8 axes × N platforms permite multi-select cells, prompts per-cell
(null / pick card / change status / edit migrating-to). Validation
de cell (card existe, status enum, migrating-to consistency).

## Estratégia de teste

Mesma do W7.2 (greenfield): monkeypatch direto de
``engine.reconfigure.question.ask`` / ``.confirm`` / ``.ask_multi`` /
``.ask_text`` pra feed responses sequencialmente sem usar intent-state
file. Isso evita o pitfall Phase A multi-intent (handler re-roda do
topo a cada response, mas o response file só guarda 1 intent-id por
vez — re-prompt do mesmo ``ask`` no top do handler vê um intent-id
stale e raises ``IntentMismatchError``).

Direct function call do ``_handle_backend_axes_submenu`` — não exercita
o ``run()`` end-to-end (que envolve draft + apply confirm + history).
``_run`` é coberto por outros tests; o foco aqui é a lógica do submenu.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from engine import reconfigure


REPO_ROOT = Path(__file__).resolve().parents[2]
assert (REPO_ROOT / "cards").is_dir(), (
    f"REPO_ROOT resolution broken: {REPO_ROOT} has no cards/ dir."
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _scaffold_project(tmp_path: Path) -> Path:
    """Estrutura mínima pra o handler resolver fixtures."""
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "workflow-config.yaml").write_text("{}\n", encoding="utf-8")
    (claude / "cards" / "local").mkdir(parents=True, exist_ok=True)
    (claude / "state").mkdir(exist_ok=True)
    return tmp_path


class _UIRecorder:
    """FIFO queues p/ ask, confirm, ask_multi, ask_text.

    Mesma estratégia do W7.2 (`test_init_greenfield_multi_axis.py`) — patcha
    via monkeypatch o namespace `engine.reconfigure.question.*`. Calls são
    registrados em ``calls`` pra introspection.
    """

    def __init__(self) -> None:
        self.ask_responses: list[str] = []
        self.confirm_responses: list[bool] = []
        self.ask_multi_responses: list[list[str]] = []
        self.ask_text_responses: list[str] = []
        self.calls: list[dict[str, Any]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # `engine.reconfigure.question` é o mesmo módulo importado em
        # `engine.ui.question` — patchar ali muta o namespace consumido
        # pelo handler.
        monkeypatch.setattr(reconfigure.question, "ask", self._fake_ask)
        monkeypatch.setattr(reconfigure.question, "confirm", self._fake_confirm)
        monkeypatch.setattr(
            reconfigure.question, "ask_multi", self._fake_ask_multi
        )
        monkeypatch.setattr(reconfigure.question, "ask_text", self._fake_ask_text)

    def _fake_ask(
        self,
        question: str,
        options: dict[str, str],
        *,
        default: str | None = None,
        allow_pause: bool = True,
    ) -> str:
        self.calls.append({"kind": "ask", "question": question, "options": dict(options)})
        if not self.ask_responses:
            raise AssertionError(
                f"ask() called without queued response; question={question!r} "
                f"options={list(options)!r}"
            )
        value = self.ask_responses.pop(0)
        if value not in options:
            raise AssertionError(
                f"scripted ask response {value!r} not in options {list(options)!r}"
            )
        return value

    def _fake_confirm(
        self,
        question: str,
        *,
        default: bool = False,
        allow_pause: bool = True,
    ) -> bool:
        self.calls.append({"kind": "confirm", "question": question})
        if not self.confirm_responses:
            raise AssertionError(
                f"confirm() called without queued response; question={question!r}"
            )
        return self.confirm_responses.pop(0)

    def _fake_ask_multi(
        self,
        question: str,
        options: dict[str, str],
        *,
        min_selected: int = 0,
    ) -> list[str]:
        self.calls.append(
            {"kind": "ask_multi", "question": question, "options": dict(options)}
        )
        if not self.ask_multi_responses:
            raise AssertionError(
                f"ask_multi() called without queued response; question={question!r}"
            )
        value = self.ask_multi_responses.pop(0)
        return value

    def _fake_ask_text(
        self,
        question: str,
        *,
        default: str | None = None,
        validator: Any = None,
        validator_hint: str | None = None,
    ) -> str:
        self.calls.append({"kind": "ask_text", "question": question})
        if not self.ask_text_responses:
            raise AssertionError(
                f"ask_text() called without queued response; question={question!r}"
            )
        return self.ask_text_responses.pop(0)


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_reconfigure_edits_cell_null_to_card(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-8 happy: editar cell (data, android) de null → retrofit-client.

    Sequência (via monkeypatch):
      1) ask_multi: cells a editar = ["data|android"]
      2) ask (per-cell): action = "edit"
      3) ask_text (card): "retrofit-client"
      4) ask (status): "active"

    Esperado: working["backend"]["data"]["android"] = {"card": "retrofit-client", "status": "active"}.
    """
    _scaffold_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    working: dict[str, Any] = {
        "platforms": {"active": ["android", "ios", "kmp"]},
        "backend": {},
    }

    recorder = _UIRecorder()
    recorder.ask_multi_responses = [["data|android"]]
    recorder.ask_responses = [
        "edit",     # per-cell action
        "active",   # per-cell status
    ]
    recorder.ask_text_responses = ["retrofit-client"]  # card name
    recorder.install(monkeypatch)

    reconfigure._handle_backend_axes_submenu(
        project_root=tmp_path,
        current={},
        working=working,
    )

    cell = working["backend"]["data"]["android"]
    assert cell == {"card": "retrofit-client", "status": "active"}, (
        f"expected new cell {{card=retrofit-client, status=active}}, got {cell!r}"
    )

    # Sanidade: ask_multi + per-cell action + status = 3 prompts; ask_text 1
    ask_calls = [c for c in recorder.calls if c["kind"] == "ask"]
    assert len(ask_calls) == 2, (
        f"expected 2 ask() calls (action + status), got {len(ask_calls)}: "
        f"{[c['question'] for c in ask_calls]}"
    )


@pytest.mark.integration
def test_reconfigure_validates_migrating_to_consistency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-8 validation: status=migrating-to + migrating-to vazio → rejeita.

    Cell anterior é null. User tenta criar cell com status=migrating-to mas
    deixa migrating-to vazio — validator rejeita, cell preserve o valor
    anterior (null). User vê warning mentor-calmo.

    Sequência:
      1) ask_multi: ["data|kmp"]
      2) ask (per-cell): "edit"
      3) ask_text (card): "retrofit-client"
      4) ask (status): "migrating-to"
      5) ask_text (migrating-to): "" (vazio)

    Esperado: backend["data"]["kmp"] permanece None (não criou).
    """
    _scaffold_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    working: dict[str, Any] = {
        "platforms": {"active": ["android", "kmp"]},
        "backend": {"data": {"kmp": None}},
    }

    recorder = _UIRecorder()
    recorder.ask_multi_responses = [["data|kmp"]]
    recorder.ask_responses = [
        "edit",          # per-cell action
        "migrating-to",  # per-cell status
    ]
    recorder.ask_text_responses = [
        "retrofit-client",  # card name
        "",                 # migrating-to vazio — viola schema
    ]
    recorder.install(monkeypatch)

    reconfigure._handle_backend_axes_submenu(
        project_root=tmp_path,
        current={},
        working=working,
    )

    # Validation rejeita → cell preserve valor anterior (None).
    assert working["backend"]["data"]["kmp"] is None, (
        f"validator must reject migrating-to without target; cell now: "
        f"{working['backend']['data']['kmp']!r}"
    )


@pytest.mark.integration
def test_reconfigure_edits_cell_status_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-8: muda status active → deprecated mantendo o card.

    Cell pré-existente `{card: ktor-client, status: active}` na (data, kmp).
    User edita pra `{card: ktor-client, status: deprecated}`.

    Sequência:
      1) ask_multi: ["data|kmp"]
      2) ask (per-cell): "edit"
      3) ask_text (card): "ktor-client" (mantém)
      4) ask (status): "deprecated"

    Esperado: working["backend"]["data"]["kmp"] = {card: ktor-client, status: deprecated}.
    Sem campo migrating-to (rule RULE-023: MUST be absent quando status != migrating-to).
    """
    _scaffold_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    working: dict[str, Any] = {
        "platforms": {"active": ["android", "kmp"]},
        "backend": {
            "data": {"kmp": {"card": "ktor-client", "status": "active"}},
        },
    }

    recorder = _UIRecorder()
    recorder.ask_multi_responses = [["data|kmp"]]
    recorder.ask_responses = [
        "edit",        # per-cell action
        "deprecated",  # per-cell status
    ]
    recorder.ask_text_responses = ["ktor-client"]  # card name (mantém)
    recorder.install(monkeypatch)

    reconfigure._handle_backend_axes_submenu(
        project_root=tmp_path,
        current={},
        working=working,
    )

    cell = working["backend"]["data"]["kmp"]
    assert cell == {"card": "ktor-client", "status": "deprecated"}, (
        f"expected status=deprecated mantendo card; got {cell!r}"
    )
    # RULE-023: MUST be absent quando status != migrating-to.
    assert "migrating-to" not in cell, (
        f"migrating-to MUST be absent when status={cell.get('status')!r}; got {cell!r}"
    )


@pytest.mark.integration
def test_reconfigure_opt_out_cell_to_null(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-8 defensive: opt-out (action="null") torna cell None mesmo se já ativa.

    Cell pré-existente `{card: retrofit-client, status: active}` na (data, ios).
    User decide opt-out (plataforma sem provider neste eixo).

    Sequência:
      1) ask_multi: ["data|ios"]
      2) ask (per-cell): "null"

    Esperado: working["backend"]["data"]["ios"] is None.
    """
    _scaffold_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    working: dict[str, Any] = {
        "platforms": {"active": ["android", "ios"]},
        "backend": {
            "data": {"ios": {"card": "retrofit-client", "status": "active"}},
        },
    }

    recorder = _UIRecorder()
    recorder.ask_multi_responses = [["data|ios"]]
    recorder.ask_responses = ["null"]  # opt-out
    recorder.install(monkeypatch)

    reconfigure._handle_backend_axes_submenu(
        project_root=tmp_path,
        current={},
        working=working,
    )

    assert working["backend"]["data"]["ios"] is None, (
        f"opt-out must set cell to None; got "
        f"{working['backend']['data']['ios']!r}"
    )
