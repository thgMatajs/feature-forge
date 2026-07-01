"""B3 (Fase 1): investigação e dedup de compose_backend_axes no caminho brownfield.

Duas tasks neste arquivo:
- INVESTIGAÇÃO (B3.1): as 2 chamadas de compose_backend_axes no caminho
  brownfield ativo (L2507 e L3425) são redundantes ou semanticamente distintas?
- NO-BEHAVIOR-CHANGE (B3.2-A): com dedup aplicada (param composer_result),
  o handler NÃO recomputa e o output é idêntico ao baseline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import engine.init as init_mod
from engine.cards.loader import CardManifest
from engine.ui import intent_state
from engine.ui.question import PausedForInputError


def _make_firebase_card() -> CardManifest:
    """Carrega o card real firebase-auth do repo (mesma estratégia do integration test)."""
    import yaml as _yaml

    repo_root = Path(init_mod.__file__).resolve().parents[1]
    card_yaml = repo_root / "cards" / "firebase-auth" / "card.yaml"
    raw = _yaml.safe_load(card_yaml.read_text(encoding="utf-8"))
    identity = raw.get("identity") or {}
    return CardManifest(
        name=str(identity.get("name", "")),
        version=str(identity.get("version", "")),
        schema_version=int(raw.get("schema-version", 1)),
        description=str(identity.get("description", "")),
        category=str(identity.get("category", "")),
        maturity=str(identity.get("maturity", "")),
        provides=list(raw.get("provides") or []),
        requires=list(raw.get("requires") or []),
        conflicts_with=list(raw.get("conflicts-with") or []),
        contributes=dict(raw.get("contributes") or {}),
        detection=dict(raw.get("detection") or {}),
        documentation=dict(raw.get("documentation") or {}),
        raw=raw,
        source_path=card_yaml.parent,
    )


def _make_active_brownfield(tmp_path: Path, monkeypatch) -> list[CardManifest]:
    """Monta o harness brownfield ativo: .claude dir + host pin + firebase signals.

    Retorna canonical_cards com o card real firebase-auth. Deixa o cwd/host
    pinados pro intent-file protocol.
    """
    from engine.host import detect as _host_detect

    # Estrutura mínima pro host intent-file resolver.
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "workflow-config.yaml").write_text("{}\n", encoding="utf-8")
    (claude / "forge" / "state").mkdir(parents=True, exist_ok=True)
    (claude / "forge" / "forge-config.yaml").write_text(
        "host: intent-file\n", encoding="utf-8"
    )
    _host_detect._clear_cache()
    intent_state._reset_log_cache()
    monkeypatch.chdir(tmp_path)

    # Signals que disparam firebase-auth acima do threshold → has_signals=True.
    (tmp_path / "app").mkdir(parents=True, exist_ok=True)
    (tmp_path / "app" / "google-services.json").write_text(
        '{"project_info": {"project_id": "test"}}', encoding="utf-8"
    )
    (tmp_path / "ios").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ios" / "GoogleService-Info.plist").write_text(
        '<?xml version="1.0"?><plist></plist>', encoding="utf-8"
    )
    (tmp_path / "app" / "build.gradle.kts").write_text(
        'plugins { id("com.android.application") }\n'
        "dependencies {\n"
        '    implementation("com.google.firebase:firebase-auth:22.0.0")\n'
        "}\n",
        encoding="utf-8",
    )

    return [_make_firebase_card()]


def _run_handler_two_phase(
    tmp_path: Path,
    canonical_cards: list[CardManifest],
    *,
    composer_result=None,
) -> dict:
    """Roda o handler brownfield em 2 fases (Phase A raise + Phase B confirm).

    Fase A: handler emite forge-pending.json e levanta PausedForInputError.
    Fase B: após escrever forge-response.json com 'a', handler consome e retorna.
    Retorna o dict de result da Phase B.
    """
    state_dir = tmp_path / ".claude" / "forge" / "state"

    # Fase A.
    kwargs: dict = {"project_root": tmp_path, "active_cards": canonical_cards}
    if composer_result is not None:
        kwargs["composer_result"] = composer_result

    with pytest.raises(PausedForInputError):
        init_mod._handle_backend_multi_axis_brownfield(**kwargs)

    pending = intent_state.read_pending(tmp_path)
    assert pending is not None, "handler deve emitir forge-pending.json no 1º call"
    intent_id = pending["intent-id"]

    # Fase B: resposta 'a' (confirm).
    (state_dir / "forge-response.json").write_text(
        json.dumps({"schema-version": 1, "intent-id": intent_id, "value": "a"}),
        encoding="utf-8",
    )
    result = init_mod._handle_backend_multi_axis_brownfield(**kwargs)
    return result


# ── B3.1 — Investigação ───────────────────────────────────────────────────────


def test_investigate_compose_backend_axes_call_redundancy(tmp_path, monkeypatch, capsys):
    """B3 INVESTIGAÇÃO (Fase 1): as 2 chamadas de compose_backend_axes no
    caminho brownfield ativo são redundantes (mesmos args → mesmo resultado)
    ou semanticamente distintas (args diferentes)? Este teste OBSERVA e decide.

    Veredito:
    - same_args=True E same_result=True → Caminho A (dedup)
    - same_args=False OU same_result=False → Caminho B (não-dup)
    """
    canonical_cards = _make_active_brownfield(tmp_path, monkeypatch)

    # Spy: captura args + resultado a cada chamada de compose_backend_axes.
    observed: list[dict] = []
    real = init_mod.compose_backend_axes

    def _spy(*args, **kwargs):
        result = real(*args, **kwargs)
        observed.append(
            {
                "args_repr": repr(args),
                "kwargs_repr": repr(sorted(kwargs.items())),
                "result_repr": repr(result),
            }
        )
        return result

    monkeypatch.setattr(init_mod, "compose_backend_axes", _spy)

    # 1ª chamada — simula o que _run_pipeline faz em L2506-2507.
    normalized = init_mod._normalize_cards_for_composer(canonical_cards)
    composer_result_1 = init_mod.compose_backend_axes(tmp_path, normalized)
    has_signals = any(
        cell is not None
        for axis_map in composer_result_1.values()
        for cell in axis_map.values()
    )
    assert has_signals, (
        "harness não disparou has_signals=True — confirme que firebase signals "
        f"foram semeados acima do threshold; composer_result={composer_result_1!r}"
    )

    # 2ª chamada — via handler (L3424-3425).
    _run_handler_two_phase(tmp_path, canonical_cards)

    # Veredito.
    # Chamadas observadas: 1 direta (linha acima) + handler two-phase (2 calls,
    # uma por fase A e B). Total esperado: >= 2.
    # O handler chama compose_backend_axes em CADA fase (A e B) — são 2 chamadas
    # redundantes além da direta. A premissa de "2 chamadas totais no pipeline"
    # é: 1 direta (_run_pipeline) + 1 no handler por fase invocada.
    assert len(observed) >= 2, (
        f"esperava >= 2 chamadas no caminho brownfield ativo, vi {len(observed)}: "
        f"{observed}. Se 0 ou 1, o harness não alcançou o caminho ativo."
    )

    # Verifica que TODAS as chamadas têm os mesmos args e result (redundância).
    first_args = observed[0]["args_repr"]
    first_kwargs = observed[0]["kwargs_repr"]
    first_result = observed[0]["result_repr"]

    all_same_args = all(
        o["args_repr"] == first_args and o["kwargs_repr"] == first_kwargs
        for o in observed
    )
    all_same_result = all(o["result_repr"] == first_result for o in observed)

    print(
        "B3-INVESTIGAÇÃO:"
        f" all_same_args={all_same_args} all_same_result={all_same_result}"
        f" n_calls={len(observed)}\n"
        f"  args={first_args}"
        f"  result={first_result}"
    )

    # Todas as chamadas com os mesmos args e mesmo resultado → REDUNDÂNCIA REAL.
    # VEREDITO: CAMINHO A (deduplicar).
    assert all_same_args, (
        "B3 VEREDITO: args divergem entre chamadas → CAMINHO B (distinção semântica). "
        f"calls={[(o['args_repr'], o['kwargs_repr']) for o in observed]}"
    )
    assert all_same_result, (
        "B3 VEREDITO: results divergem → CAMINHO B (distinção semântica). "
        f"results={[o['result_repr'] for o in observed]}"
    )
    # Se chegou aqui: CAMINHO A (redundância real confirmada empiricamente).
    # O handler chama compose_backend_axes em cada fase — n_calls mostra o
    # total de chamadas redundantes no two-phase roundtrip.


# ── B3.2-A — No-behavior-change com dedup ────────────────────────────────────


def test_brownfield_handler_reuses_precomputed_composer_result(tmp_path, monkeypatch):
    """B3-A (Fase 1): com composer_result pré-computado, o handler NÃO recomputa
    compose_backend_axes (1 chamada em vez de 2 no caminho ativo). Saída idêntica
    ao baseline — no-behavior-change.

    Pré-requisito: B3.1 confirmou redundância (same_args=True, same_result=True).
    """
    canonical_cards = _make_active_brownfield(tmp_path, monkeypatch)

    calls = {"n": 0}
    real = init_mod.compose_backend_axes

    def _counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(init_mod, "compose_backend_axes", _counting)

    # Baseline: rodar handler SEM composer_result pré-computado → 1 call no handler.
    baseline = _run_handler_two_phase(tmp_path, canonical_cards, composer_result=None)
    calls_baseline = calls["n"]

    # Reseta o estado de intent entre runs (limpa TODOS os arquivos de state,
    # incluindo o intent log JSONL que cacheia respostas consumidas).
    from engine.host import detect as _host_detect

    intent_state._reset_log_cache()
    _host_detect._clear_cache()
    state_dir = tmp_path / ".claude" / "forge" / "state"
    # Remove todos os arquivos de state (JSON, JSONL, lock files).
    for fp in state_dir.glob("forge-*"):
        try:
            fp.unlink()
        except OSError:
            pass

    # Computa o result pré-dedup (como o pipeline faria).
    normalized = init_mod._normalize_cards_for_composer(canonical_cards)
    precomputed = init_mod.compose_backend_axes(tmp_path, normalized)
    calls_after_precompute = calls["n"]

    # Pós-dedup: rodar handler COM composer_result pré-computado.
    deduped = _run_handler_two_phase(
        tmp_path, canonical_cards, composer_result=precomputed
    )
    calls_after_deduped = calls["n"]

    # Dedup: o handler COM precomputed NÃO deve chamar compose_backend_axes de novo.
    # Antes da dedup: handler chama 1x internamente → calls_baseline == 1.
    # Depois da dedup: handler com precomputed → NÃO chama (calls_after_deduped ==
    #   calls_after_precompute, sem incremento adicional).
    assert calls_after_deduped == calls_after_precompute, (
        "com composer_result pré-computado, o handler NÃO pode chamar "
        f"compose_backend_axes de novo; chamadas antes={calls_after_precompute}, "
        f"depois={calls_after_deduped}"
    )

    # No-behavior-change: saída idêntica ao baseline.
    assert deduped.get("choice") == baseline.get("choice"), (
        f"choice diverge: deduped={deduped.get('choice')!r} "
        f"baseline={baseline.get('choice')!r}"
    )
    assert (deduped.get("selected_card_names") or []) == (
        baseline.get("selected_card_names") or []
    ), (
        f"selected_card_names diverge: deduped={deduped.get('selected_card_names')!r} "
        f"baseline={baseline.get('selected_card_names')!r}"
    )
    assert (deduped.get("composer_result") or {}) == (
        baseline.get("composer_result") or {}
    ), (
        f"composer_result diverge: deduped keys={list(deduped.get('composer_result', {}).keys())} "
        f"baseline keys={list(baseline.get('composer_result', {}).keys())}"
    )
