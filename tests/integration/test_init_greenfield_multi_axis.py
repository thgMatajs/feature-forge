"""Integration: greenfield init flow via bundle picker + opt override.

W7.2 do plano DET-6. Cobre AC-7 do SPEC `det-6-multi-axis-backend.md`.

Cenário-âncora: projeto greenfield (zero signals) — o handler carrega
os 3 bundle YAMLs (W6.1), emite um picker de 4 opções (3 bundles + a
sentinela ``custom-from-scratch``) e, conforme a escolha:

  · "firebase-full" / "rest-with-firebase-telemetry" / "local-only" →
    pergunta se quer customizar algum eixo (opt override). Sem
    override, aplica o bundle direto. Com override, pergunta quais
    eixos ajustar (multi-select) e prompta o card por eixo selecionado.
  · "custom-from-scratch" → pula bundle e roda per-axis prompts pros 8
    eixos canônicos.

## Estratégia de teste

Dois pares complementares:

1. **Picker-emission test** — usa o contrato Phase A canônico do W7.1:
   primeira invocação levanta ``PausedForInputError``; lemos o pending e
   validamos shape (4 opções, kind=ask). Não exercita o resto do fluxo.

2. **Fluxo completo (3 tests)** — monkeypatch direto de
   ``engine.init.ui_question.ask`` / ``.confirm`` / ``.ask_multi`` pra
   feed values sequencialmente sem usar o intent-state file. Isso evita
   o pitfall de re-invocação Phase A em handlers multi-intent (o handler
   re-roda do topo a cada response, mas o response file só guarda 1
   intent-id por vez — re-prompt do mesmo ``ask`` no top do handler vê
   um intent-id stale e raises ``IntentMismatchError``). O wiring real
   Phase A é responsabilidade do W7.4; aqui validamos a lógica do
   handler isoladamente.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from engine.ui import intent_state
from engine.ui.question import PausedForInputError


REPO_ROOT = Path(__file__).resolve().parents[2]
assert (REPO_ROOT / "presets" / "kmp-mobile" / "bundles").is_dir(), (
    f"REPO_ROOT resolution broken: {REPO_ROOT} has no presets/kmp-mobile/bundles/."
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _scaffold_project(tmp_path: Path) -> Path:
    """Mínimo pro `_project_root_for_io` resolver `tmp_path` em vez de cwd.

    Replica `_scaffold_project` do test brownfield W7.1 — não dá pra
    reusar via import porque pytest test files não compartilham fixtures
    cross-file sem conftest.py local, e este pequeno helper não justifica
    promoção a conftest (escopo greenfield-only).
    """
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "workflow-config.yaml").write_text("{}\n", encoding="utf-8")
    (claude / "state").mkdir(exist_ok=True)
    return tmp_path


class _UIRecorder:
    """Captura calls de ask/confirm/ask_multi e responde com queues pre-seeded.

    Cada método mantém uma fila FIFO de responses. As filas pra `ask` são
    queryable por kind (picker vs per-axis), então o test scripta a
    sequência sem se preocupar com identidade de cada intent. Os calls
    são acumulados em ``calls`` pra introspection pós-fato.

    Per-axis prompts são identificados pela presença de "eixo" no texto
    da pergunta — convention que combina com o texto literal do handler.
    """

    def __init__(self) -> None:
        self.ask_responses: list[str] = []
        self.confirm_responses: list[bool] = []
        self.ask_multi_responses: list[list[str]] = []
        self.calls: list[dict[str, Any]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Monkeypatch das 3 funções no namespace do init.

        `engine.init.ui_question` é o mesmo objeto-módulo de
        `engine.init.question` (alias do source). Patchar `.ask`,
        `.confirm`, `.ask_multi` em qualquer um dos nomes muta o módulo
        e captura ambos caminhos.
        """
        from engine import init as init_module

        monkeypatch.setattr(init_module.ui_question, "ask", self._fake_ask)
        monkeypatch.setattr(init_module.ui_question, "confirm", self._fake_confirm)
        monkeypatch.setattr(
            init_module.ui_question, "ask_multi", self._fake_ask_multi
        )

    def _fake_ask(
        self,
        question: str,
        options: dict[str, str],
        *,
        default: str | None = None,
        allow_pause: bool = True,
    ) -> str:
        self.calls.append(
            {"kind": "ask", "question": question, "options": dict(options)}
        )
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
        if len(value) < min_selected:
            raise AssertionError(
                f"scripted ask_multi {value!r} violates min_selected={min_selected}"
            )
        return value


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_greenfield_emits_bundle_picker_with_four_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-7: primeiro intent é um picker de 4 opções (3 bundles + sentinela).

    O picker deve incluir as 3 keys dos bundles YAML (firebase-full,
    rest-with-firebase-telemetry, local-only) E a sentinela
    custom-from-scratch — total 4 opções. Sem nenhuma response no disco,
    o handler levanta PausedForInputError no primeiro call (contrato
    Phase A).
    """
    from engine.init import _handle_backend_multi_axis_greenfield

    _scaffold_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(PausedForInputError):
        _handle_backend_multi_axis_greenfield(
            project_root=tmp_path,
            available_cards=[],
        )

    pending = intent_state.read_pending(tmp_path)
    assert pending is not None, "handler must emit forge-pending.json on first call"
    assert pending["kind"] == "ask", (
        f"bundle picker should use ask() single-select, got {pending.get('kind')!r}"
    )

    options = pending["options"]
    assert set(options.keys()) == {
        "firebase-full",
        "rest-with-firebase-telemetry",
        "local-only",
        "custom-from-scratch",
    }, f"bundle picker must offer 3 bundles + sentinela, got {sorted(options)}"


@pytest.mark.integration
def test_greenfield_bundle_chosen_without_override_returns_bundle_cards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-7 happy path: bundle escolhido + sem override → aplica defaults.

    Sequência (via monkeypatch):
      1) picker = "firebase-full"
      2) confirm "quer customizar algum axis?" = False

    Esperado: result.choice == "bundle", selected_card_names contém todos
    os cards não-null do bundle firebase-full (ver YAML — firestore-
    persistence, firebase-auth, firebase-crashlytics, firebase-analytics,
    firebase-storage, room-database, sqldelight, fcm, firebase-remote-config).
    """
    from engine.init import _handle_backend_multi_axis_greenfield

    _scaffold_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    recorder = _UIRecorder()
    recorder.ask_responses = ["firebase-full"]
    recorder.confirm_responses = [False]
    recorder.install(monkeypatch)

    result = _handle_backend_multi_axis_greenfield(
        project_root=tmp_path,
        available_cards=[],
    )

    assert result["choice"] == "bundle", (
        f"expected choice=bundle, got {result.get('choice')!r}"
    )
    assert result.get("bundle_name") == "firebase-full"

    selected = result.get("selected_card_names") or []
    expected_subset = {
        "firestore-persistence",
        "firebase-auth",
        "firebase-crashlytics",
        "firebase-analytics",
        "firebase-storage",
        "room-database",
        "sqldelight",
        "fcm",
        "firebase-remote-config",
    }
    assert expected_subset.issubset(set(selected)), (
        f"firebase-full bundle missing cards; expected superset of "
        f"{sorted(expected_subset)}, got {sorted(selected)}"
    )

    # Only the picker + confirm were prompted — no per-axis prompts.
    kinds = [c["kind"] for c in recorder.calls]
    assert kinds == ["ask", "confirm"], (
        f"no-override flow must skip per-axis prompts; calls={kinds}"
    )


@pytest.mark.integration
def test_greenfield_custom_from_scratch_runs_per_axis_prompts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-7: custom-from-scratch sentinela pula bundle e prompta cada axis.

    Sequência:
      1) picker = "custom-from-scratch"
      2..9) per-axis prompt × 8 axes → cada resposta é "skip"

    Esperado: result.choice == "scratch", selected_card_names == [],
    8 calls de ask() per-axis (1 picker + 8 axes = 9 ask calls totais).
    """
    from engine.init import _handle_backend_multi_axis_greenfield

    _scaffold_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    recorder = _UIRecorder()
    recorder.ask_responses = [
        "custom-from-scratch",  # picker
        # 8 per-axis prompts:
        "skip", "skip", "skip", "skip", "skip", "skip", "skip", "skip",
    ]
    recorder.install(monkeypatch)

    result = _handle_backend_multi_axis_greenfield(
        project_root=tmp_path,
        available_cards=[],
    )

    assert result["choice"] == "scratch", (
        f"expected choice=scratch, got {result.get('choice')!r}"
    )
    selected = result.get("selected_card_names") or []
    assert selected == [], (
        f"scratch + all-skip must yield empty selection, got {selected!r}"
    )

    # 1 picker + 8 per-axis = 9 asks. Confirm NOT called (we skipped to scratch).
    ask_calls = [c for c in recorder.calls if c["kind"] == "ask"]
    assert len(ask_calls) == 9, (
        f"scratch path must run 1 picker + 8 per-axis prompts; "
        f"got {len(ask_calls)} ask calls: {[c['question'] for c in ask_calls]}"
    )
    confirm_calls = [c for c in recorder.calls if c["kind"] == "confirm"]
    assert confirm_calls == [], (
        f"scratch path bypasses opt-override confirm; got {confirm_calls}"
    )


@pytest.mark.integration
def test_greenfield_bundle_with_override_prompts_only_selected_axes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-7: bundle + override 'sim' + multiSelect 2 axes → prompta esses 2.

    Sequência:
      1) picker = "rest-with-firebase-telemetry"
      2) confirm override = True
      3) ask_multi axes a ajustar = ["data", "auth"]
      4..5) per-axis(data) = "skip", per-axis(auth) = "skip"

    Esperado: result.choice == "bundle-overridden", apenas 2 per-axis
    prompts (não 8), selected NÃO contém cards default dos eixos data/auth.
    """
    from engine.init import _handle_backend_multi_axis_greenfield

    _scaffold_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    recorder = _UIRecorder()
    recorder.ask_responses = [
        "rest-with-firebase-telemetry",  # picker
        "skip",                          # per-axis: data
        "skip",                          # per-axis: auth
    ]
    recorder.confirm_responses = [True]
    recorder.ask_multi_responses = [["data", "auth"]]
    recorder.install(monkeypatch)

    result = _handle_backend_multi_axis_greenfield(
        project_root=tmp_path,
        available_cards=[],
    )

    assert result["choice"] == "bundle-overridden", (
        f"expected choice=bundle-overridden, got {result.get('choice')!r}"
    )
    assert result.get("bundle_name") == "rest-with-firebase-telemetry"

    selected = result.get("selected_card_names") or []
    selected_set = set(selected)

    # 6 axes preservados → mantêm bundle defaults.
    preserved_subset = {
        "firebase-crashlytics",      # observability
        "firebase-analytics",        # analytics
        "room-database",             # persistence (android)
        "sqldelight",                # persistence (kmp)
        "fcm",                       # notifications
        "firebase-remote-config",    # flags
    }
    assert preserved_subset.issubset(selected_set), (
        f"non-overridden axes must keep bundle defaults; expected "
        f"superset of {sorted(preserved_subset)}, got {sorted(selected_set)}"
    )

    # 2 axes overridden com "skip" → cards default desses axes ausentes.
    overridden_out = {
        "retrofit-client",   # data/android (bundle)
        "ktor-client",       # data/kmp (bundle)
        "firebase-auth",     # auth (bundle)
    }
    assert overridden_out.isdisjoint(selected_set), (
        f"overridden axes with 'skip' must drop bundle cards; "
        f"unexpected overlap: {sorted(overridden_out & selected_set)}"
    )

    # Exactly 2 per-axis prompts ran (data + auth), NOT 8 (all axes).
    ask_calls = [c for c in recorder.calls if c["kind"] == "ask"]
    per_axis_calls = [c for c in ask_calls if "eixo" in c["question"]]
    assert len(per_axis_calls) == 2, (
        f"override flow must prompt ONLY selected axes; got "
        f"{len(per_axis_calls)} per-axis prompts: "
        f"{[c['question'] for c in per_axis_calls]}"
    )
