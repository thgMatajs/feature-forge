"""forge qa — adversarial red-team gate (13o comando).

Top-level handler do verbo ``forge qa``. Orquestra as 6 phases do
red-team gate delegando aos modules de ``engine.qa.*`` (Wave 3).

Nota estrutural: o template do plan (Task 4.1) apontava ``engine/qa.py``
flat module, mas isso colide em Python com o package ``engine/qa/`` ja
criado em Wave 3 (scope, ingest, sandbox, synthesis, emit, run_id). O
contrato publico exigido por Task 4.2 — ``from engine.qa import run_qa``
— resolve corretamente quando o handler vive aqui em ``__init__.py``,
preservando os 6 submodules como API privada do package. Pattern
idiomatico Python: handler publico em ``__init__``, helpers em submods.

Phase 1+2+4 (audit + adversarial + synthesis dispatch) sao coordenados
pelo agente ``qa-conductor.md`` via Claude Code Agent — este handler NAO
invoca dispatch direto (Decisao 30: zero runtime deps em outras skills).
Em vez disso, escreve ``conductor-handoff.json`` no run tree e termina,
deixando o orchestrator externo dispatchar o conductor.

Quando o conductor escreve findings em ``<run>/findings/*.json``, uma
re-invocacao subsequente (ou modo test/integration com findings ja
presentes) executa Phase 4 synthesis local + Phase 5 emit + render do
verdict block.

Spec: ``docs/superpowers/specs/2026-06-05-forge-qa-design.md`` §4
(architecture macro), §5 (phase contracts), §10.2 (verdict block UX).

Voz: mentor calmo. Sem auto-fix — verdict BLOCK exige escolha humana via
``forge evolve``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from engine.qa.emit import emit_proposed_evolutions
from engine.qa.ingest import (
    QAConfig,
    RunTree,
    create_run_tree,
    parse_qa_config,
)
from engine.qa.scope import (
    Scope,
    ScopeAmbiguityError,
    ScopeError,
    ScopeMissingError,
    resolve_scope,
)
from engine.qa.synthesis import SynthesisResult, synthesize


__all__ = ["run_qa"]


def run_qa(
    raw_target: str,
    *,
    project_root: Path,
    workflow_config: dict[str, Any],
) -> int:
    """Entry-point chamado pelo CLI. Retorna exit code (0 ou 8).

    Orquestra as phases na ordem canonica (§4 do spec):

    1. Phase 0 — ingest: parse config, resolve scope, cria run tree
    2. Escreve ``conductor-handoff.json`` pro dispatch externo
    3. Se ``findings/*.json`` ja presente (test/integration mode ou
       re-invocacao pos-conductor): Phase 4 synthesis + Phase 5 emit +
       render do verdict block
    4. Exit code 8 se ``verdict == "BLOCK"``, 0 caso contrario

    Comportamento defensivo:
    - ``workflow_config`` None ou nao-dict e tratado como section ausente
      (delegado a ``parse_qa_config``)
    - ``qa.enabled=false`` -> mensagem + ``return 0`` (NAO raise)
    - ``ScopeError`` (incluindo ``ScopeAmbiguityError`` /
      ``ScopeMissingError``) e capturado, mensagem em stderr + ``return 0``;
      o subclasse ja carrega remediation no texto (3-caminhos quando
      ambiguo)
    - Warnings de ``parse_qa_config`` sao printados em stderr antes do
      scope resolve, pra user ver inconsistencias mesmo se scope falhar

    Args:
        raw_target: input bruto do user (slug, screen id, ``TASK-NNNN``,
            ou ``"paranoid"``). Passado direto pra ``resolve_scope``.
        project_root: raiz do projeto consumidor (onde ``.planning/``
            mora). Path absoluto preferido.
        workflow_config: dict completo do ``workflow-config.yaml``.
            Pode vir None (tratado defensivamente como ``{}``).

    Returns:
        Exit code: 0 (PASS/FLAG, qa desabilitado, scope error, conductor
        dispatch pendente) ou 8 (verdict=BLOCK).
    """
    # Type guard defensivo — workflow_config pode chegar None de callers
    # que ainda nao migraram (ex.: testes legados, smoke scripts).
    if not isinstance(workflow_config, dict):
        workflow_config = {}

    cfg = parse_qa_config(workflow_config)

    if not cfg.enabled:
        print(
            "qa esta desabilitado em workflow-config (qa.enabled: false). "
            "Rode `forge reconfigure -> qa` se quiser ativar.",
            file=sys.stderr,
        )
        return 0

    for warning in cfg.warnings:
        print(f"⚠ {warning}", file=sys.stderr)

    try:
        scope = resolve_scope(
            raw_target,
            project_root=project_root,
            paranoid_max_features=cfg.paranoid_max_features,
        )
    except ScopeError as exc:
        # ScopeAmbiguityError e ScopeMissingError ja trazem mensagens
        # com voz mentor calmo + 3-caminhos (quando aplicavel) no texto
        # do exception — caller so precisa repassar pra stderr.
        print(f"\U0001f6d1 {exc}", file=sys.stderr)
        return 0

    run_tree = create_run_tree(scope, project_root=project_root)

    # Phase 1+2+4 sao Claude Code Agent dispatch — coordenados pelo
    # agente qa-conductor.md (criado em Wave 6 Task 6.1). Aqui apenas
    # registramos os caminhos pro conductor consumir.
    _write_conductor_handoff(scope, run_tree, cfg)

    # Phase 3 sandbox + Phase 5 emit sao executados quando o conductor
    # devolve findings em findings/*.json. Em invocacao sincrona, este
    # handler termina aqui e o conductor e dispatched externamente.
    # Quando rodando em test/integration mode com findings ja presentes,
    # segue direto pra synthesis + emit.
    findings_files = sorted(run_tree.findings_dir.glob("*.json"))
    if not findings_files:
        print(
            f"Run tree criada em {run_tree.root}.\n"
            f"  scope:  {scope.type} {scope.target}\n"
            f"  run:    {run_tree.run_id}\n"
            f"Dispatch `agents/qa-conductor.md` pra rodar phases 1-4."
        )
        return 0

    all_findings: list[dict[str, Any]] = []
    for ff in findings_files:
        data = json.loads(ff.read_text(encoding="utf-8"))
        if isinstance(data, list):
            all_findings.extend(data)
        elif isinstance(data, dict):
            nested = data.get("findings", [])
            if isinstance(nested, list):
                all_findings.extend(nested)

    result = synthesize(all_findings)
    emit_summary = emit_proposed_evolutions(
        result.findings, project_root=project_root
    )

    _print_verdict_block(scope, run_tree, result, emit_summary)

    return 8 if result.verdict == "BLOCK" else 0


def _write_conductor_handoff(
    scope: Scope, run_tree: RunTree, cfg: QAConfig
) -> None:
    """Escreve ``<run_tree.root>/conductor-handoff.json``.

    Payload consumido pelo ``agents/qa-conductor.md`` (Wave 6) pra saber
    qual scope auditar, onde gravar fixtures/findings, e quais limites
    de sandbox respeitar.

    Args:
        scope: ``Scope`` resolvido em Phase 0.
        run_tree: ``RunTree`` criado em Phase 0.
        cfg: ``QAConfig`` parseado em Phase 0.
    """
    handoff: dict[str, Any] = {
        "scope": {
            "type": scope.type,
            "target": scope.target,
            "paths": [str(p) for p in scope.paths],
        },
        "run_id": run_tree.run_id,
        "root": str(run_tree.root),
        "config": {
            "sandbox_budget_seconds_total": cfg.sandbox_budget_seconds_total,
            "agent_timeout_seconds": cfg.agent_timeout_seconds,
            "extensions_disabled": list(cfg.extensions_disabled),
        },
    }
    (run_tree.root / "conductor-handoff.json").write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _print_verdict_block(
    scope: Scope,
    run_tree: RunTree,
    result: SynthesisResult,
    emit_summary: dict[str, Any],
) -> None:
    """Render simplificado do verdict block (§10.2 spec).

    Versao cinematica completa vem em Wave 10/11 via roteiro UX. Aqui
    pontas essenciais — verdict, scope, run id, contagens por severity,
    emit summary, lembrete de "sem auto-fix".

    Args:
        scope: ``Scope`` resolvido.
        run_tree: ``RunTree`` da run.
        result: ``SynthesisResult`` da Phase 4.
        emit_summary: dict retornado por ``emit_proposed_evolutions``.
    """
    icon = {"BLOCK": "\U0001f6d1", "FLAG": "⚠", "PASS": "✓"}.get(
        result.verdict, "?"
    )
    total = sum(result.by_severity.values())
    print(f"\n{icon} forge qa verdict: {result.verdict}")
    print(f"  scope:    {scope.type} {scope.target}")
    print(f"  run:      {run_tree.run_id}")
    print(f"  findings: {total} total")
    for sev in ("critical", "high", "medium", "low", "info"):
        count = result.by_severity.get(sev, 0)
        print(f"    {sev:<8} · {count}")

    written = emit_summary.get("written", 0)
    skipped = emit_summary.get("skipped", 0)
    write_failed = emit_summary.get("write_failed", False)
    if write_failed:
        print(
            "\n  ⚠ emit falhou (disk full ou perm error). "
            "Findings nao foram persistidos em proposed-evolutions.yaml."
        )
    else:
        print(
            f"\n  emitted: {written} actionable findings -> "
            f"proposed-evolutions.yaml ({skipped} skipped)"
        )
    print("  Sem auto-fix — escolha humana via `forge evolve`.")
