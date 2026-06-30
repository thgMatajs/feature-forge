"""Integração — content-gate nas waves do `forge plan` (Onda 2).

Reproduz, no nível do RUNNER de wave, os dois escapes do piloto MeoBonsai
que passavam pelo gate procedural (acknowledge cego após "continuar"):

- **Wave C / `_run_static_wave`**: tech-spec.md PARCIAL (stubs ``{{...}}``).
- **Wave D / `_run_wave_d`**: task-breakdown.yaml com DAG vazio (≥2 tasks).
- **Wave E / `_run_wave_e`**: readiness com ``{{...}}`` residual apesar de
  ``status: ready`` (content-check ANTES do parse de verdict — Task 3).

Semântica (acks H-002 + M-002): substância parcial = **PAUSA deferred**
(``WaveResult.deferred=True`` → exit 130 no ``_run_waves_for_subtype``), com
mensagem 3-caminhos acionável. NÃO é hard-fail; segue o padrão de pausa
existente. Harness espelha ``tests/unit/test_plan_deferred_exit_code.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import plan as plan_mod
from engine.memory.l1 import read_l1_status
from engine.plan import WaveResult


# ── Fixtures de monkeypatch comuns ───────────────────────────────────────────


def _force_continue(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_continue_or_pause`` sempre devolve 'continuar' (host avançou)."""
    monkeypatch.setattr(plan_mod, "_continue_or_pause", lambda *a, **k: "continuar")


def _stub_render_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutraliza o render real de templates — o teste escreve os artefatos."""
    monkeypatch.setattr(plan_mod, "_render_template", lambda *a, **k: True)


def _pick_path(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    """``question.ask_three_paths`` devolve o caminho `key` ('a'|'b'|'c')."""
    from engine.ui import question as q_mod

    monkeypatch.setattr(q_mod, "ask_three_paths", lambda *a, **k: key)
    monkeypatch.setattr(plan_mod.question, "ask_three_paths", lambda *a, **k: key)


# ── Wave C (estática) — tech-spec parcial é PEGO ─────────────────────────────


def test_wave_c_partial_tech_spec_defers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Wave C com tech-spec.md PARCIAL → content-gate ramifica pra pausa.

    HOJE (antes do fix) a wave faz acknowledge cego (deferred=False). DEPOIS:
    o content-check pega os stubs e, com o host escolhendo 'Pausar' (caminho
    c), a wave persiste deferred (deferred=True) com mensagem acionável.
    """
    feature_path = tmp_path / "feature"
    feature_path.mkdir(parents=True)
    (feature_path / "tech-spec.md").write_text(
        "## §3 ViewModels\nclass {{ConceptViewModel}}\n## §7 Riscos\n{{new_risk_1}}\n",
        encoding="utf-8",
    )
    _force_continue(monkeypatch)
    _stub_render_noop(monkeypatch)
    _pick_path(monkeypatch, "c")  # Pausar e investigar

    result = plan_mod._run_static_wave(
        "C",
        (("tech-spec.template.md", "tech-spec.md"),),
        "minha-feature",
        tmp_path,
        feature_path,
    )
    assert result.deferred is True, (
        "tech-spec parcial deve ramificar pra pausa, não acknowledge cego"
    )
    state = read_l1_status("minha-feature", tmp_path)
    assert state is not None and state.status == "deferred", (
        "content-gate pausado deve persistir deferred via _persist_deferred"
    )


def test_wave_c_complete_tech_spec_acknowledges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Happy-path: tech-spec.md completo → acknowledge direto (sem fricção)."""
    feature_path = tmp_path / "feature"
    feature_path.mkdir(parents=True)
    (feature_path / "tech-spec.md").write_text(
        "## §3 ViewModels\nclass ConceptViewModel\n## §7 Riscos\nFirestore index ausente\n",
        encoding="utf-8",
    )
    _force_continue(monkeypatch)
    _stub_render_noop(monkeypatch)

    result = plan_mod._run_static_wave(
        "C",
        (("tech-spec.template.md", "tech-spec.md"),),
        "feature-ok",
        tmp_path,
        feature_path,
    )
    assert result.deferred is False, "artefato completo passa o gate sem fricção"


# ── Wave D — task-breakdown com DAG vazio é PEGO ─────────────────────────────


def test_wave_d_empty_dag_defers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Wave D com dependency_graph vazio (≥2 tasks) → content-gate pausa.

    Reproduz o 2º escape do piloto. ``_run_wave_d`` renderiza o
    task-breakdown.yaml e as N tasks; aqui stubamos o render e escrevemos um
    breakdown com DAG vazio + 2 tasks reais.
    """
    feature_path = tmp_path / "feature"
    (feature_path / "tasks").mkdir(parents=True)
    (feature_path / "task-breakdown.yaml").write_text(
        "tasks:\n  - id: TASK-0001\n  - id: TASK-0002\n"
        "dependency_graph:\n  edges: []\ntopological_order: []\ncritical_path: []\n",
        encoding="utf-8",
    )
    _force_continue(monkeypatch)
    _stub_render_noop(monkeypatch)
    # Wave D pergunta a contagem de tasks; force 2 sem prompt.
    monkeypatch.setattr(plan_mod, "_ask_task_count", lambda: 0)
    _pick_path(monkeypatch, "c")

    result = plan_mod._run_wave_d("feature-d", tmp_path, feature_path)
    assert result.deferred is True, (
        "DAG vazio com 2 tasks deve ramificar pra pausa (2º escape do piloto)"
    )
    state = read_l1_status("feature-d", tmp_path)
    assert state is not None and state.status == "deferred"


def test_wave_d_populated_dag_acknowledges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Happy-path: task-breakdown com DAG coerente → acknowledge direto."""
    feature_path = tmp_path / "feature"
    (feature_path / "tasks").mkdir(parents=True)
    (feature_path / "task-breakdown.yaml").write_text(
        "tasks:\n  - id: TASK-0001\n  - id: TASK-0002\n"
        "dependency_graph:\n  edges:\n    - {from: TASK-0001, to: TASK-0002}\n"
        "  topological_order: [TASK-0001, TASK-0002]\n"
        "critical_path: [TASK-0001, TASK-0002]\n"
        "totals:\n  tasks_count: 2\n",
        encoding="utf-8",
    )
    _force_continue(monkeypatch)
    _stub_render_noop(monkeypatch)
    monkeypatch.setattr(plan_mod, "_ask_task_count", lambda: 0)

    result = plan_mod._run_wave_d("feature-d-ok", tmp_path, feature_path)
    assert result.deferred is False, "DAG populado passa o gate sem fricção"


# ── Wave E (readiness) — placeholder ANTES do parse de verdict (Task 3) ───────


def test_wave_e_placeholder_caught_before_verdict_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Wave E: readiness com {{...}} residual apesar de status=ready é PEGO.

    HOJE (antes do fix) a Wave E parseia 'ready' e retorna deferred=False —
    passa cego apesar do handoff incompleto. DEPOIS: o content-check pega o
    placeholder ANTES do parse de verdict e ramifica pra pausa.
    """
    feature_path = tmp_path / "feature"
    feature_path.mkdir(parents=True)
    (feature_path / "implementation-readiness-review.md").write_text(
        "readiness_verdict:\n  status: ready\n\n## Gaps\n{{remaining_gap}}\n",
        encoding="utf-8",
    )
    (feature_path / "plan-feature-handoff.json").write_text(
        '{"slug": "feature-e"}\n', encoding="utf-8"
    )
    _force_continue(monkeypatch)
    _stub_render_noop(monkeypatch)
    _pick_path(monkeypatch, "c")

    result = plan_mod._run_wave_e("feature-e", tmp_path, feature_path)
    assert result.deferred is True, (
        "readiness com placeholder residual deve ser pego ANTES do parse de "
        "verdict, não passar cego por status=ready"
    )
    state = read_l1_status("feature-e", tmp_path)
    assert state is not None and state.status == "deferred"


def test_wave_e_clean_ready_acknowledges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Happy-path: readiness completo + status=ready → deferred=False (regressão)."""
    feature_path = tmp_path / "feature"
    feature_path.mkdir(parents=True)
    (feature_path / "implementation-readiness-review.md").write_text(
        "readiness_verdict:\n  status: ready\n\n## Gaps\nnenhum gap aberto\n",
        encoding="utf-8",
    )
    (feature_path / "plan-feature-handoff.json").write_text(
        '{"slug": "feature-e-ok"}\n', encoding="utf-8"
    )
    _force_continue(monkeypatch)
    _stub_render_noop(monkeypatch)

    result = plan_mod._run_wave_e("feature-e-ok", tmp_path, feature_path)
    assert result.deferred is False, "readiness limpo + ready passa o gate"
