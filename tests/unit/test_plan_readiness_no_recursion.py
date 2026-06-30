"""Regression: BUG-PLAN-1 — o path A do gate de readiness NÃO recursa (Onda 3).

`engine.plan._run_wave_e`, no path A do gate "readiness não está em 'ready'"
(escolha 'a' = "re-revisar agora"), fazia `return _run_wave_e(...)` síncrono.
Se o verdict continua `partial` (o usuário respondeu 'a' mas NÃO ajustou os
artefatos), isso recursa infinito → RecursionError (~979 níveis, exit 1,
~1.3 MB stdout, history acumulando N× `wave-e-rerun-requested`).

Fix: re-renderizar as waves UMA vez + PAUSAR (deferred). O host ajusta os
artefatos e re-invoca pelo loop canônico. Contrato de pausa = o mesmo dos
irmãos (b/c do gate, wave-d, wave-e): `_persist_deferred` +
`WaveResult(deferred=True)` → caller mapeia pra exit **130** (NÃO exit 2, que
é reservado ao intent loop).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import plan as plan_mod
from engine.memory.l1 import read_l1_status
from engine.plan import WaveResult, _run_wave_e, _run_waves_for_subtype


def _wire_partial_path_a(monkeypatch, feature_path, render_counter):
    """Cenário: usuário escolhe 'a', mas verdict fica 'partial' (imutável)."""
    monkeypatch.setattr(plan_mod, "_continue_or_pause", lambda *a, **kw: "continuar")
    monkeypatch.setattr(plan_mod, "_parse_readiness_status", lambda *a, **kw: "partial")
    monkeypatch.setattr(plan_mod, "_run_content_gate", lambda *a, **kw: None)
    monkeypatch.setattr(plan_mod.question, "ask_three_paths", lambda *a, **kw: "a")

    def fake_render(template_name, target, slug, project_root):
        render_counter["n"] += 1
        return False

    monkeypatch.setattr(plan_mod, "_render_template", fake_render)


def test_plan_readiness_path_a_does_not_recurse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Path A com verdict='partial' imutável: RETORNA deferred, NÃO recursa.

    RED (antes do fix): `return _run_wave_e(...)` → RecursionError.
    GREEN: retorna WaveResult(deferred=True) sem re-entrar em _run_wave_e
    (rastreado por contador de chamadas).
    """
    feature_path = tmp_path / "feature"
    feature_path.mkdir(parents=True)
    render_counter = {"n": 0}
    _wire_partial_path_a(monkeypatch, feature_path, render_counter)

    # Spy: _run_wave_e só pode ser entrado UMA vez (sem auto-recursão).
    enter_counter = {"n": 0}
    real_run_wave_e = plan_mod._run_wave_e

    def spy(slug, project_root, fp):
        enter_counter["n"] += 1
        if enter_counter["n"] > 5:
            raise AssertionError("recursão detectada — _run_wave_e re-entrado")
        return real_run_wave_e(slug, project_root, fp)

    monkeypatch.setattr(plan_mod, "_run_wave_e", spy)

    result = plan_mod._run_wave_e("slug-x", tmp_path, feature_path)

    assert isinstance(result, WaveResult)
    assert result.deferred is True, "path A com partial imutável deve deferir"
    assert enter_counter["n"] == 1, (
        f"_run_wave_e foi re-entrado {enter_counter['n']}× — esperado 1 (sem recursão)"
    )


def test_plan_readiness_path_a_persists_deferred(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Path A com partial: status L1 = deferred, phase_lock liberado."""
    feature_path = tmp_path / "feature"
    feature_path.mkdir(parents=True)
    render_counter = {"n": 0}
    _wire_partial_path_a(monkeypatch, feature_path, render_counter)

    slug = "deferred-readiness"
    result = _run_wave_e(slug, tmp_path, feature_path)

    assert result.deferred is True
    state = read_l1_status(slug, tmp_path)
    assert state is not None, "status.json deve existir após defer"
    assert state.status == "deferred", f"esperado deferred, obtido {state.status!r}"
    assert state.phase_lock is None, "_persist_deferred deve liberar o phase_lock"


def test_plan_readiness_path_a_returns_130_via_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Via _run_waves_for_subtype, path A com partial → exit 130 (pausa canônica).

    NÃO exit 1 (crash), NÃO exit 2 (reservado ao intent loop).
    """
    feature_path = tmp_path / "feature"
    feature_path.mkdir(parents=True)
    render_counter = {"n": 0}
    _wire_partial_path_a(monkeypatch, feature_path, render_counter)

    # Waves A-D passam limpas; Wave E entra no gate de readiness.
    def ok_wave(*_args, **_kwargs) -> WaveResult:
        return WaveResult(artefacts=[], deferred=False)

    monkeypatch.setattr(plan_mod, "_run_static_wave", ok_wave)
    monkeypatch.setattr(plan_mod, "_run_wave_d", ok_wave)

    rc = _run_waves_for_subtype(
        subtype="product",
        starting_wave="A",
        slug="readiness-130",
        project_root=tmp_path,
        feature_path=feature_path,
    )
    assert rc == 130, (
        f"path A deferido deve mapear pra exit 130 (pausa), obtido {rc}"
    )
