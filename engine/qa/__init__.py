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
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.qa.checkpoint import (
    Checkpoint,
    CheckpointCorruptError,
    find_resumable_run,
    read_checkpoint,
    write_checkpoint,
)
from engine.qa.emit import emit_proposed_evolutions
from engine.qa.ingest import (
    QAConfig,
    RunTree,
    create_run_tree,
    parse_qa_config,
    snapshot_artefacts,
)
from engine.qa.scope import (
    Scope,
    ScopeAmbiguityError,
    ScopeError,
    ScopeMissingError,
    resolve_scope,
)
from engine.qa.synthesis import (
    SynthesisResult,
    findings_from_sandbox_results,
    hydrate_sandbox_results,
    synthesize,
)


def _utc_iso_z() -> str:
    """Timestamp ISO 8601 UTC com sufixo ``Z`` (sem offset numerico).

    Pattern espelha helpers de ``engine.evolve._now_utc_iso``,
    ``engine.memory.l1._now`` etc. Centralizado aqui pra evitar drift
    futuro: qa-report.json exige formato ``Z``-suffixed (§6.1 spec).
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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

    # Resume detection (Decisao 27 — pause = auto-resumable).
    # Procura um run dir previo com checkpoint pendente ANTES de criar
    # uma nova run tree. Se encontrar e o checkpoint for valido, reusa o
    # dir; se corrupto, cai em 3-caminhos mentor calmo e retorna 0.
    resumable_dir = find_resumable_run(project_root, scope.type, scope.target)
    resumed_checkpoint: Checkpoint | None = None
    if resumable_dir is not None:
        try:
            resumed_checkpoint = read_checkpoint(resumable_dir)
        except CheckpointCorruptError as exc:
            print(
                f"⚠ Checkpoint encontrado mas invalido em {exc.path}.\n\n"
                f"  Motivo: {exc.reason}\n\n"
                f"  Tres caminhos pra continuar:\n"
                f"    1) Ignorar checkpoint e comecar nova run — "
                f"apague {exc.path.parent} e re-invoque\n"
                f"    2) Inspecionar manualmente — `cat {exc.path}` "
                f"pra entender o que sobrou\n"
                f"    3) Restaurar do .bak se existir — "
                f"`ls {exc.path}.bak`\n\n"
                f"  Sem auto-fix aqui — escolha humana.",
                file=sys.stderr,
            )
            return 0

    if resumed_checkpoint is not None and resumable_dir is not None:
        # Phase 5 ja completa — checkpoint nao devia existir, defensivo:
        # apaga + segue pra fresh run.
        if resumed_checkpoint.last_phase_completed >= 5:
            try:
                (resumable_dir / "checkpoint.json").unlink()
            except FileNotFoundError:
                pass
            run_tree = create_run_tree(scope, project_root=project_root)
            snapshot_copied = snapshot_artefacts(
                scope, run_tree.snapshot_dir, project_root=project_root
            )
            _write_qa_report_skeleton(scope, run_tree, cfg)
            _write_conductor_handoff(scope, run_tree, cfg)
            resumed_checkpoint = None
        else:
            run_tree = _reattach_run_tree(resumable_dir, resumed_checkpoint)
            snapshot_copied = []
            print(
                f"Retomando run {resumed_checkpoint.run_id} "
                f"(Phase {resumed_checkpoint.last_phase_completed} completa)..."
            )
    else:
        run_tree = create_run_tree(scope, project_root=project_root)

        # Phase 0 — snapshot dos artefatos resolvidos (§5.0). Hardlink quando
        # possivel, fallback copy2. Best-effort: paths inexistentes ou
        # falhas de I/O nao quebram a run.
        snapshot_copied = snapshot_artefacts(
            scope, run_tree.snapshot_dir, project_root=project_root
        )

        # Phase 0 — escreve skeleton de qa-report.json com verdict=pending
        # antes de qualquer dispatch (§5.0). Phase 4 finaliza in-place
        # preservando started_at/config.
        _write_qa_report_skeleton(scope, run_tree, cfg)

        # Phase 1+2+4 sao Claude Code Agent dispatch — coordenados pelo
        # agente qa-conductor.md (criado em Wave 6 Task 6.1). Aqui apenas
        # registramos os caminhos pro conductor consumir.
        _write_conductor_handoff(scope, run_tree, cfg)

    # Track phase progresso pro SIGINT handler. List-of-int pra mutar
    # dentro do closure (nonlocal nao funciona em handler registrado via
    # signal.signal pq frame e diferente).
    _phase = [0]

    def _sigint_checkpoint(_signum: int, _frame: Any) -> None:
        try:
            findings_count = len(list(run_tree.findings_dir.glob("*.json")))
            write_checkpoint(
                run_tree.root,
                run_id=run_tree.run_id,
                scope_type=scope.type,
                scope_target=scope.target,
                last_phase_completed=_phase[0],
                findings_partial_count=findings_count,
            )
            print(
                f"\n⏸ Interrompido — checkpoint salvo em "
                f"{run_tree.root / 'checkpoint.json'}.\n"
                f"  Re-invoque `forge qa {scope.target}` pra retomar.",
                file=sys.stderr,
            )
        finally:
            sys.exit(130)

    prev_handler = signal.signal(signal.SIGINT, _sigint_checkpoint)
    try:
        # Phase 0 ja completa (run tree + skeleton + handoff escritos OU
        # reattach do resume). Marca pra checkpoint capturar caso SIGINT
        # chegue antes das phases seguintes terminarem.
        _phase[0] = 0

        # Phase 3 sandbox + Phase 5 emit sao executados quando o conductor
        # devolve findings em findings/*.json. Em invocacao sincrona, este
        # handler termina aqui e o conductor e dispatched externamente.
        # Quando rodando em test/integration mode com findings ja presentes,
        # segue direto pra synthesis + emit.
        findings_files = sorted(run_tree.findings_dir.glob("*.json"))
        if not findings_files:
            snapshot_line = (
                f"  snapshot: {len(snapshot_copied)} artefatos copiados\n"
                if snapshot_copied
                else ""
            )
            print(
                f"Run tree criada em {run_tree.root}.\n"
                f"  scope:  {scope.type} {scope.target}\n"
                f"  run:    {run_tree.run_id}\n"
                f"{snapshot_line}"
                f"Dispatch `agents/qa-conductor.md` pra rodar phases 1-4."
            )
            return 0

        all_findings: list[dict[str, Any]] = []
        for ff in findings_files:
            # Degradação graciosa: arquivo malformado (JSON quebrado) ou
            # ilegível (perm error) não derruba synthesis — outros auditores
            # podem ter contribuído findings válidos. Logamos em stderr pra
            # o user ver o draft problemático e decidir manualmente.
            try:
                data = json.loads(ff.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                print(
                    f"⚠ Falha ao ler findings de {ff.name} ({exc}). "
                    "Ignorando este arquivo para degradação graciosa.",
                    file=sys.stderr,
                )
                continue
            if isinstance(data, list):
                all_findings.extend(data)
            elif isinstance(data, dict):
                nested = data.get("findings", [])
                if isinstance(nested, list):
                    all_findings.extend(nested)

        # CONF-003: sandbox breach/timeout viram findings deterministicos
        # (§5.3). Le sandbox-results.json escrito pelo conductor; injeta
        # findings derivados antes do synthesize pra que dedup + verdict
        # logic considerem os problemas de isolamento como first-class
        # findings (breach -> critical -> BLOCK).
        sandbox_results_file = run_tree.root / "sandbox-results.json"
        if sandbox_results_file.exists():
            try:
                raw = json.loads(sandbox_results_file.read_text(encoding="utf-8"))
                stubs = hydrate_sandbox_results(
                    raw if isinstance(raw, list) else raw.get("results", [])
                )
                derived = findings_from_sandbox_results(
                    stubs, run_id=run_tree.run_id
                )
                all_findings.extend(derived)
            except (json.JSONDecodeError, OSError) as exc:
                print(
                    f"⚠ sandbox-results.json malformado ({exc}). "
                    "Ignorando — sandbox findings nao serao gerados nesta run.",
                    file=sys.stderr,
                )

        _phase[0] = 3  # findings + sandbox-results processados
        result = synthesize(all_findings)
        _phase[0] = 4  # synthesis done
        emit_summary = emit_proposed_evolutions(
            result.findings, project_root=project_root
        )

        # Phase 4 — finaliza qa-report.json escrito em Phase 0 com verdict,
        # findings consolidados, totals, e completed_at. Preserva campos
        # load-bearing do skeleton (run.id, run.scope, run.config_snapshot,
        # run.started_at) — idempotente em re-invocacoes (re-le antes de
        # escrever).
        _finalize_qa_report(run_tree, result)
        _phase[0] = 5  # emit + finalize done

        _print_verdict_block(scope, run_tree, result, emit_summary)

        # Cleanup do checkpoint: run completou, checkpoint nao e mais
        # relevante. Atomic delete tolerante a ausencia.
        try:
            (run_tree.root / "checkpoint.json").unlink()
        except FileNotFoundError:
            pass

        return 8 if result.verdict == "BLOCK" else 0
    finally:
        signal.signal(signal.SIGINT, prev_handler)


def _reattach_run_tree(run_dir: Path, _checkpoint: Checkpoint) -> RunTree:
    """Reconstroi RunTree a partir de um dir existente sem criar nada.

    Usado no resume path: o run dir ja foi criado em invocacao anterior,
    precisamos so reativar os paths canonicos pra Phase 4/5 continuarem.
    Tolerante a subdirs ausentes — mkdir defensivo pra cobrir cleanup
    parcial entre interrupcao e resume.

    Args:
        run_dir: dir raiz da run resumivel (ja existente em disco).
        _checkpoint: checkpoint lido (reservado pra extensao futura; hoje
            so usamos ``run_id`` do nome do dir).

    Returns:
        ``RunTree`` espelhando os paths canonicos de ``create_run_tree``.
    """
    fixtures = run_dir / "fixtures"
    findings = run_dir / "findings"
    audit = run_dir / "audit"
    snapshot = run_dir / "snapshot"
    for d in (fixtures, findings, audit, snapshot):
        d.mkdir(parents=True, exist_ok=True)
    return RunTree(
        run_id=run_dir.name,
        root=run_dir,
        fixtures_dir=fixtures,
        findings_dir=findings,
        audit_dir=audit,
        snapshot_dir=snapshot,
    )


def _write_qa_report_skeleton(
    scope: Scope, run_tree: RunTree, cfg: QAConfig
) -> None:
    """Escreve qa-report.json inicial com verdict='pending' (Phase 0).

    Shape segue ``docs/schemas/qa-report.md`` (envelope canonico):
    ``schema_version`` + ``run`` (id/scope/config_snapshot/started_at)
    + ``verdict`` + ``summary`` (total_findings/by_severity/by_vector)
    + ``findings`` (lista vazia ate Phase 4 popular).

    Phase 4 chama ``_finalize_qa_report`` que LE este arquivo, ATUALIZA
    verdict/findings/summary e ADICIONA ``run.finished_at`` +
    ``run.duration_s``. ``run.started_at`` e ``run.config_snapshot``
    sao preservados — auditoria pode reconstruir a config sob a qual a
    run iniciou mesmo se workflow-config mudou depois.

    Args:
        scope: ``Scope`` resolvido em Phase 0.
        run_tree: ``RunTree`` criado em Phase 0.
        cfg: ``QAConfig`` parseado em Phase 0.
    """
    report: dict[str, Any] = {
        "schema_version": 1,
        "run": {
            "id": run_tree.run_id,
            "scope": {
                "type": scope.type,
                "target": scope.target,
                "paths": [str(p) for p in scope.paths],
            },
            "config_snapshot": {
                "sandbox_budget_seconds_total": cfg.sandbox_budget_seconds_total,
                "agent_timeout_seconds": cfg.agent_timeout_seconds,
                "extensions_disabled": list(cfg.extensions_disabled),
                "retention_days": cfg.retention_days,
                "paranoid_max_features": cfg.paranoid_max_features,
            },
            "started_at": _utc_iso_z(),
        },
        "verdict": "pending",
        "summary": {
            "total_findings": 0,
            "by_severity": {},
            "by_vector": {},
        },
        "findings": [],
    }
    (run_tree.root / "qa-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _finalize_qa_report(
    run_tree: RunTree, result: SynthesisResult
) -> None:
    """Atualiza qa-report.json com verdict/findings/totals finais (Phase 4).

    Le o skeleton escrito em Phase 0 (preservando run.id, run.scope,
    run.config_snapshot, run.started_at), substitui ``verdict``,
    ``summary`` e ``findings`` pelos consolidados de Phase 4, e anexa
    ``run.finished_at``.

    Tolerante a skeleton ausente — degradacao graciosa: se o file nao
    existe (caller chamou finalize sem skeleton previo, ou disk error em
    Phase 0), reconstroi o envelope basico com o que tem do
    ``run_tree``. Audit trail completo so existe quando skeleton foi
    persistido.

    Args:
        run_tree: ``RunTree`` da run em curso.
        result: ``SynthesisResult`` da Phase 4.
    """
    report_path = run_tree.root / "qa-report.json"
    try:
        existing = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            existing = {}
    except (json.JSONDecodeError, OSError):
        existing = {}

    run_block = existing.get("run") if isinstance(existing.get("run"), dict) else {}
    run_block = dict(run_block)  # shallow copy pra evitar mutacao do dict lido
    run_block.setdefault("id", run_tree.run_id)
    run_block["finished_at"] = _utc_iso_z()

    report: dict[str, Any] = {
        "schema_version": existing.get("schema_version", 1),
        "run": run_block,
        "verdict": result.verdict,
        "summary": {
            "total_findings": len(result.findings),
            "by_severity": dict(result.by_severity),
            "by_vector": dict(result.by_vector),
        },
        "findings": list(result.findings),
    }
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


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
