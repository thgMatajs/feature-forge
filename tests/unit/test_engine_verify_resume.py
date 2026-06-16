"""Resume-from-checkpoint tests for ``engine.verify`` (DRIFT-1 W2.T3b).

Outcome C per W2.T0: per-subcommand ``_VerifyCheckpoint`` dataclass
following ``_InitCheckpoint`` template (``engine/init.py:100-108``).
Lives in this module — NO import from ``engine.qa.checkpoint``.

Verify exposes 2 interactive callsites (``question.ask`` em
``_infer_active_feature`` + ``_scope_to_feature_slug``), ambas
disparam apenas quando ha multiplas features ativas. O resume cobre
o cenario em que o host pausou em uma dessas perguntas e re-invoca
com a response no disco.

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
- .planning/drift-1/checkpoint-audit.json (action=add-new, reuse_path=init-pattern)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import verify
from engine.ui import question


def test_verify_checkpoint_dataclass_exists() -> None:
    """_VerifyCheckpoint dataclass must mirror _InitCheckpoint shape."""
    cp_cls = getattr(verify, "_VerifyCheckpoint", None)
    assert cp_cls is not None, "_VerifyCheckpoint not declared in engine.verify"
    cp = cp_cls(
        step="step-scope-disambiguation",
        at="2026-06-10T00:00:00Z",
        project_root="/tmp/foo",
    )
    assert cp.step == "step-scope-disambiguation"
    assert getattr(cp, "intent_id", "<missing>") is None
    # Verify carrega contexto adicional pra resume: scope_kind + scope_target.
    assert getattr(cp, "scope_kind", "<missing>") is None
    assert getattr(cp, "scope_target", "<missing>") is None


def test_verify_save_load_clear_roundtrip(tmp_forge_project: Path) -> None:
    """_save/_load/_clear_verify_checkpoint sao idempotentes per outcome C."""
    save = getattr(verify, "_save_verify_checkpoint", None)
    load = getattr(verify, "_load_verify_checkpoint", None)
    clear = getattr(verify, "_clear_verify_checkpoint", None)
    assert save is not None, "_save_verify_checkpoint missing"
    assert load is not None, "_load_verify_checkpoint missing"
    assert clear is not None, "_clear_verify_checkpoint missing"

    cp = verify._VerifyCheckpoint(
        step="step-scope-disambiguation",
        at="2026-06-10T00:00:00Z",
        project_root=str(tmp_forge_project),
        intent_id="xyz-456",
        scope_kind="task",
        scope_target="TASK-001",
    )
    save(cp)
    loaded = load(tmp_forge_project)
    assert isinstance(loaded, dict)
    assert loaded.get("intent-id") == "xyz-456"
    assert loaded.get("scope-kind") == "task"
    assert loaded.get("scope-target") == "TASK-001"

    clear(tmp_forge_project)
    assert load(tmp_forge_project) is None


def _setup_two_active_features(project_root: Path) -> tuple[str, str]:
    """Cria 2 features ativas em status 'implementing' pra disparar o ask.

    Retorna (slug_a, slug_b) — slugs ordenados alfabeticamente pra resultado
    deterministico no test.
    """
    from engine.memory.l1 import L1State, write_l1_status

    cfg_dir = project_root / ".claude"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "workflow-config.yaml").write_text(
        "schema-version: 1\nidentity:\n  project-slug: verify-resume-test\n",
        encoding="utf-8",
    )

    slug_a = "alpha-feat"
    slug_b = "beta-feat"
    for slug in (slug_a, slug_b):
        write_l1_status(
            L1State(
                feature_slug=slug,
                status="implementing",
                last_action_at="2026-06-10T00:00:00Z",
                last_action_kind="plan-saved",
                phase_lock=None,
                raw={},
            ),
            project_root,
        )
    return slug_a, slug_b


def test_resume_from_checkpoint(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume canonico: checkpoint + response.json correspondente.

    Cenario:
      1. Invocacao A bateu em `_infer_active_feature` com 2 features
         ativas (multipla) → emitiu pending + gravou checkpoint com
         intent_id da pergunta.
      2. Host escreveu forge-response.json escolhendo uma das features.
      3. Invocacao B (este test): verify carrega checkpoint, prossegue
         pra _infer_active_feature; question.ask ve response.json,
         consome, retorna a feature escolhida. Verify roda cascade
         (sem validators ativos no greenfield, retorna 0).
      4. Checkpoint apagado apos clean completion.
    """
    slug_a, slug_b = _setup_two_active_features(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    # Task 0.7b — pin host: intent-file so question.ask delegate writes/reads
    # against .claude/forge/state/ (v1.3 sub-namespace), not stdout.
    forge_dir = tmp_forge_project / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "host: intent-file\n", encoding="utf-8"
    )
    from engine.host import detect as _host_detect

    _host_detect._clear_cache()

    # Calcula o intent-id da pergunta canonica do _infer_active_feature
    # com 2 candidatos (allow_prompt=True). Opcoes seguem o pattern em
    # verify.py:461 — {slug: f"feature {slug}" for slug in candidatos}.
    options = {slug_a: f"feature {slug_a}", slug_b: f"feature {slug_b}"}
    intent_id = question._stable_intent_id(
        "ask",
        "Mais de um feature ativo. Qual?",
        options,
        extra={"default": None, "min-selected": None, "validator-hint": None},
    )

    # Host escreveu response + checkpoint do verify.
    state_dir = tmp_forge_project / ".claude" / "forge" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    response_payload = {
        "schema-version": 1,
        "intent-id": intent_id,
        "value": slug_a,
        "responded-at": "2026-06-10T00:01:00Z",
    }
    (state_dir / "forge-response.json").write_text(
        json.dumps(response_payload), encoding="utf-8"
    )
    cp = verify._VerifyCheckpoint(
        step="step-scope-disambiguation",
        at="2026-06-10T00:00:30Z",
        project_root=str(tmp_forge_project),
        intent_id=intent_id,
        scope_kind="feature",
        scope_target="",
    )
    verify._save_verify_checkpoint(cp)
    assert verify._load_verify_checkpoint(tmp_forge_project) is not None

    # Invoca verify.run com argv vazio → ele chama _resolve_scope, que
    # detecta 2 features ativas, pergunta via question.ask, consome
    # response.json, e prossegue. Sem validators registrados → exit 0.
    rc = verify.run([])
    assert rc in (0, 1), f"unexpected exit code from verify.run: {rc}"

    # Task 0.7b — CR-002 invariant: state files MUST remain on disk
    # after happy-path consume. cli.py finally block performs the
    # terminal cleanup at handler exit, preserving forensic inspection.
    assert (state_dir / "forge-response.json").exists(), (
        "response file must survive happy-path consume (CR-002)"
    )

    # Checkpoint apagado apos clean completion.
    assert verify._load_verify_checkpoint(tmp_forge_project) is None, (
        "checkpoint should be cleared on clean completion"
    )
