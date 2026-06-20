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
from typing import Any, Iterable

from engine._sandbox.env import CORE_ALLOWLIST, inspect_dropped, is_sensitive
from engine.cards import CardError
from engine.cards.loader import load_all_cards
from engine.persona import three_paths_block
from engine.qa._common import utc_iso_z as _utc_iso_z
from engine.qa.checkpoint import (
    Checkpoint,
    CheckpointCorruptError,
    find_resumable_run,
    read_checkpoint,
    write_checkpoint,
)
from engine.qa.emit import emit_proposed_evolutions
from engine.ui.exit_codes import ERR_QA_BLOCK, fail_with_tag
from engine.qa.ingest import (
    QAConfig,
    RunTree,
    create_run_tree,
    parse_qa_config,
    snapshot_artefacts,
)
from engine.qa.sandbox import Fixture, SandboxResult, run_sandbox
from engine.qa.scope import (
    Scope,
    ScopeAmbiguityError,
    ScopeError,
    ScopeMissingError,
    resolve_scope,
)
from engine.qa.synthesis import (
    SandboxResultStub,
    SynthesisResult,
    findings_from_sandbox_results,
    hydrate_sandbox_results,
    hydrate_validator_claim_evidence,
    synthesize,
)

# Alias local pra preservar uso interno (`_utc_iso_z()`) sem espalhar a
# importacao publica em cada call-site. O helper canonico vive em
# engine.qa._common pra evitar duplicacao com checkpoint.py (M-4).


__all__ = ["run_qa"]


# Auditores canonicos do contrato qa-conductor.md (Phase 1+2). Sao os 4
# vetores estaticos+adversariais sempre presentes; extensoes de card entram
# por cima e podem ser desabilitadas via qa.extensions.disabled. Hard-coded
# aqui porque o contrato (agents/qa-conductor.md §Inputs) os trata como
# garantidos — o filtro extensions_disabled e defensivo (core nao costuma
# ser desabilitavel, mas documenta a intencao).
_CORE_AUDITORS: tuple[str, ...] = (
    "spec-vs-spec",
    "coverage",
    "chaos",
    "validator-claim",
)


def run_qa(
    raw_target: str,
    *,
    project_root: Path,
    workflow_config: dict[str, Any],
) -> int:
    """Entry-point chamado pelo CLI. Retorna exit code (0 ou 1+QA-BLOCK).

    Orquestra as phases na ordem canonica (§4 do spec):

    1. Phase 0 — ingest: parse config, resolve scope, cria run tree
    2. Escreve ``conductor-handoff.json`` pro dispatch externo
    3. Se ``findings/*.json`` ja presente (test/integration mode ou
       re-invocacao pos-conductor): Phase 4 synthesis + Phase 5 emit +
       render do verdict block
    4. Exit code 1 + ``[FORGE-ERR:QA-BLOCK]`` (via ``fail_with_tag``) se
       ``verdict == "BLOCK"``, 0 caso contrario

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
        dispatch pendente) ou 1 + ``[FORGE-ERR:QA-BLOCK]`` em stderr
        (verdict=BLOCK, via ``fail_with_tag(ERR_QA_BLOCK)``). O ``8`` antigo
        foi superseded pela convencao ``fail_with_tag`` (C3 EXIT-2-COLLISION
        / W2); ver ``docs/design/06-command-surface.md``.
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
            # Template canonico de Disciplina #1 (3-caminhos): "O que
            # falhou / Onde / Por que importa / Tres caminhos / Sem
            # auto-fix". Veja .claude/rules/disciplines.md §1 e
            # docs/design/07-discipline.md §1.
            print(
                f"\U0001f6d1 Checkpoint corrupto\n\n"
                f"O que falhou:\n"
                f"  {exc.reason}\n\n"
                f"Onde:\n"
                f"  {exc.path}\n\n"
                f"Por que importa:\n"
                f"  - Sem checkpoint valido, resume nao consegue retomar\n"
                f"  - A run anterior pode ter findings parciais ainda utilizaveis\n"
                f"  - Decisao 27: pause/resume e auto-resumable; corrupt quebra contrato\n\n"
                f"Tres caminhos pra resolver:\n\n"
                f"  1) Ignorar checkpoint e comecar nova run\n"
                f"     apague {exc.path.parent} e re-invoque `forge qa {scope.target}`\n\n"
                f"  2) Inspecionar o arquivo pra entender o que sobrou\n"
                f"     `cat {exc.path}` - pode revelar findings parciais salvaveis\n\n"
                f"  3) Apenas o checkpoint corrompeu - preservar findings, descartar marker\n"
                f"     `rm {exc.path}` mantem findings/*.json e qa-report.json intactos;\n"
                f"     proxima invocacao cria run nova mas voce ainda tem o registro\n\n"
                f"Sem auto-fix aqui - escolha humana.",
                file=sys.stderr,
            )
            return 0

    if resumed_checkpoint is not None and resumable_dir is not None:
        # Phase 5 ja completa — checkpoint nao devia existir, defensivo:
        # apaga + segue pra fresh run. Voz mentor calmo: avisa o user
        # antes de gastar budget de sandbox em re-run nao solicitado
        # (M-2 do review CONF-004).
        if resumed_checkpoint.last_phase_completed >= 5:
            print(
                f"⚠ Checkpoint encontrado em {resumable_dir.name} indica run completa\n"
                f"  (phase 5 finished) mas verdict ficou pending — provavelmente\n"
                f"  cleanup falhou. Descartando checkpoint stale e iniciando run nova.",
                file=sys.stderr,
            )
            try:
                (resumable_dir / "checkpoint.json").unlink()
            except FileNotFoundError:
                pass
            run_tree = create_run_tree(scope, project_root=project_root)
            snapshot_copied = snapshot_artefacts(
                scope, run_tree.snapshot_dir, project_root=project_root
            )
            _write_qa_report_skeleton(scope, run_tree, cfg)
            # QA-11 Wave 4: alert pre Phase 3 sandbox (informativo, nao bloqueia).
            _maybe_alert_sensitive_drops(project_root, workflow_config)
            # QA-11 CR-01: computa extras autorizados UMA vez e injeta no
            # handoff. Conductor consome esse campo pra propagar ao subprocess.
            allowed_extras = _compute_allowed_extras(project_root, workflow_config)
            _write_conductor_handoff(
                scope,
                run_tree,
                cfg,
                allowed_extras=allowed_extras,
                snapshot_paths=snapshot_copied,
                workflow_config=workflow_config,
            )
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

        # QA-11 Wave 4: alert pre Phase 3 sandbox (informativo, nao bloqueia).
        # Computa card_extras = union(env_needs) cross active cards, intersect
        # com (CORE_ALLOWLIST | grants). Se vars sensitive serao dropadas e
        # nenhum card cobre, dispara mentor_calmo three_paths em stderr.
        _maybe_alert_sensitive_drops(project_root, workflow_config)

        # Phase 1+2+4 sao Claude Code Agent dispatch — coordenados pelo
        # agente qa-conductor.md (criado em Wave 6 Task 6.1). Aqui apenas
        # registramos os caminhos pro conductor consumir.
        # QA-11 CR-01: computa extras autorizados e injeta no handoff pra
        # que o conductor propague ao subprocess (run_sandbox extras=...).
        allowed_extras = _compute_allowed_extras(project_root, workflow_config)
        _write_conductor_handoff(
            scope,
            run_tree,
            cfg,
            allowed_extras=allowed_extras,
            snapshot_paths=snapshot_copied,
            workflow_config=workflow_config,
        )

        # F-2 (B.2) — checkpoint na fronteira de Phase 0. Veredito do
        # mantenedor (Decisao 10 / row 32): resume e flagless. O checkpoint,
        # antes escrito so em SIGINT, passa a marcar a fronteira de Phase 0
        # do fluxo normal — assim re-invocar `forge qa <target>` PURO (mesmo
        # argv) reata esta run em andamento via find_resumable_run, em vez de
        # criar run nova. O skeleton ja gravou verdict=pending acima, entao o
        # par (checkpoint.json + qa-report.json pending) satisfaz o criterio
        # de find_resumable_run. last_phase_completed=0 leva o resume ao
        # branch _reattach_run_tree (nao ao branch stale >= 5). Cleanup na
        # conclusao (Phase 5) garante que a run concluida nao fica presa em
        # resume (M-002).
        write_checkpoint(
            run_tree.root,
            run_id=run_tree.run_id,
            scope_type=scope.type,
            scope_target=scope.target,
            last_phase_completed=0,
            findings_partial_count=0,
        )

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

        # CR-01: o ENGINE é dono da Phase 3. Quando há findings com fixtures
        # executáveis (vetor validator-claim, executable=true) E
        # sandbox-results.json AUSENTE, o engine reconstrói as Fixtures dos
        # findings, roda run_sandbox ELE MESMO e escreve sandbox-results.json.
        # Sem isso, run_sandbox era dead code no flow e o vetor "validator que
        # mente" (F-1/F-4) nunca executava — o synthesis settlava prematuro.
        #
        # Idempotente: só roda quando sandbox-results.json não existe. Sem
        # fixtures executáveis → run_sandbox([]) == [] → não escreve arquivo
        # vazio (não é settle "prematuro"; é legítimo não haver nada a rodar).
        sandbox_results_file = run_tree.root / "sandbox-results.json"
        if not sandbox_results_file.exists():
            fixtures = _reconstruct_fixtures_from_findings(
                all_findings, run_tree, project_root=project_root
            )
            if fixtures:
                _phase[0] = 2  # entrando na Phase 3 (sandbox)
                # Recomputa extras autorizados aqui (idempotente, fail-safe a
                # ()): o resume reattach não passa pelo branch que computa
                # allowed_extras pro handoff, então não dependemos da var de
                # branch. Mesma lista que o handoff carrega (QA-11).
                phase3_extras = _compute_allowed_extras(
                    project_root, workflow_config
                )
                sandbox_results = run_sandbox(
                    run_tree.root,
                    fixtures,
                    budget_total_s=cfg.sandbox_budget_seconds_total,
                    per_validator_s=cfg.agent_timeout_seconds,
                    extras=phase3_extras,
                )
                _write_sandbox_results(run_tree, sandbox_results)

        # CONF-003: sandbox breach/timeout viram findings deterministicos
        # (§5.3). Le sandbox-results.json escrito pelo engine na Phase 3
        # (CR-01) — ou, em estados degradados/legados, pelo conductor; injeta
        # findings derivados antes do synthesize pra que dedup + verdict
        # logic considerem os problemas de isolamento como first-class
        # findings (breach -> critical -> BLOCK).
        stubs: list[SandboxResultStub] = []
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

        # F-4: hidrata evidence.sandbox_result nos drafts validator-claim a
        # partir dos MESMOS stubs (casando por basename do fixture). No-op
        # quando stubs=[] (sandbox-results ausente) — drafts permanecem
        # sandbox_result=None, que e draft-valido.
        all_findings = hydrate_validator_claim_evidence(all_findings, stubs)

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

        if result.verdict == "BLOCK":
            return fail_with_tag(ERR_QA_BLOCK)
        return 0
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


def _normalize_iso_z(raw: str) -> str:
    """WR-03: troca SÓ o sufixo ``Z`` por ``+00:00`` antes do ``fromisoformat``.

    ``datetime.fromisoformat`` (3.11+) ja aceita ``Z`` sufixo, mas
    normalizamos por robustez. O cuidado e nao usar ``str.replace("Z", ...)``
    global — isso reescreveria qualquer ``Z`` interno de um timestamp
    migrado/malformado, mascarando o defeito num parse plausivel-mas-errado.
    Strip de sufixo preserva ``Z`` interno (que cai em degradacao graciosa no
    parse), em vez de corromper silenciosamente.
    """
    if raw.endswith("Z"):
        return raw[:-1] + "+00:00"
    return raw


def _compute_duration_s(started_raw: Any, finished_dt: datetime) -> float:
    """F-3: deriva run.duration_s de (finished - started).total_seconds().

    ``started_raw`` vem do skeleton (``run.started_at``, ISO-8601 com sufixo
    ``Z`` escrito por ``utc_iso_z``). Degradacao graciosa: se ausente ou
    malformado, retorna ``0.0`` em vez de derrubar finalize — audit trail
    incompleto e aceitavel (alinhado ao padrao "skeleton ausente" do metodo).

    Args:
        started_raw: valor de ``run.started_at`` (str ISO-Z esperado).
        finished_dt: ``datetime`` tz-aware usado pra ``finished_at`` —
            mesma referencia, sem jitter.

    Returns:
        Segundos decorridos (float, >= 0).
    """
    if not isinstance(started_raw, str):
        return 0.0
    try:
        # ``datetime.fromisoformat`` (3.11+) aceita ``Z``; pra robustez em
        # versoes anteriores, normalizamos o sufixo ``Z`` -> ``+00:00`` antes
        # do parse (WR-03: strip do sufixo, nao replace global).
        started_dt = datetime.fromisoformat(_normalize_iso_z(started_raw))
    except (ValueError, TypeError):
        return 0.0
    if started_dt.tzinfo is None:
        started_dt = started_dt.replace(tzinfo=timezone.utc)
    return max(0.0, (finished_dt - started_dt).total_seconds())


def _finalize_qa_report(
    run_tree: RunTree, result: SynthesisResult
) -> None:
    """Atualiza qa-report.json com verdict/findings/totals finais (Phase 4).

    Le o skeleton escrito em Phase 0 (preservando run.id, run.scope,
    run.config_snapshot, run.started_at), substitui ``verdict``,
    ``summary`` e ``findings`` pelos consolidados de Phase 4, e anexa
    ``run.finished_at`` + ``run.duration_s`` (F-3, derivado de
    finished - started; ``validate_qa_report`` exige ambos).

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

    # F-3: finished_at e duration_s derivam da MESMA referencia temporal
    # (sem jitter de duas chamadas). validate_qa_report:62 exige run.duration_s.
    finished_dt = datetime.now(timezone.utc)
    run_block["finished_at"] = finished_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    run_block["duration_s"] = _compute_duration_s(
        run_block.get("started_at"), finished_dt
    )

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


def _reconstruct_fixtures_from_findings(
    findings: list[dict[str, Any]],
    run_tree: RunTree,
    *,
    project_root: Path,
) -> list[Fixture]:
    """CR-01: reconstrói ``Fixture`` executáveis a partir dos findings emitidos.

    O coração do fix: o engine roda a Phase 3 (sandbox) ELE MESMO, então
    precisa reconstruir os objetos ``Fixture`` a partir do que o auditor
    validator-claim escreveu em ``findings/*.json`` + ``fixtures/``.

    Contrato dos findings validator-claim (``agents/qa-auditor-validator-claim.md``
    §Output + ``templates/qa-fixture-validator-claim.template.yaml``):
      - ``finding["executable"] is True`` (invariante do vetor; ``false`` é
        exceção documentada pra validator inexistente — pulamos).
      - ``evidence.fixture_path`` — descritor ``fixtures/validator-claim-<slug>.yaml``.
        O ``stem`` (basename sem extensão) é o ``fixture_id``, que casa com
        ``Fixture.name`` (IN-02) e com ``fixture_name`` em sandbox-results
        (matching do F-4).
      - ``evidence.validator_path`` — ``validators/<name>.py`` (canon de
        produção; resolvido contra ``project_root`` quando relativo).
      - ``evidence.tree_rel_path`` — onde o arquivo do contra-exemplo mora no
        mini-tree (``fixtures/<fixture_id>/<tree_rel_path>``). O auditor
        materializou o arquivo lá; ``run_sandbox`` invoca o validator com
        ``--project-root <mini-tree>``.

    O ``input_path`` aponta o arquivo materializado
    (``run_tree.fixtures_dir/<name>/<tree_rel_path>``) — ``run_sandbox`` exige
    que ``input_path`` resolva dentro de ``run_dir/fixtures`` (Decisão 30); o
    mini-tree mora exatamente ali.

    Conservador: só reconstrói validator-claim com os 3 campos de evidence
    presentes e ``executable`` não-``False``. Findings de outros vetores
    (chaos carrega payload+contract no descritor, não validator_path na
    evidence) ou sem os campos são pulados — sem invenção de Fixture.

    Args:
        findings: lista consolidada de findings draft (todos os auditores).
        run_tree: ``RunTree`` da run em curso.
        project_root: raiz do projeto consumidor (pra resolver validator_path
            relativo ao canon de produção).

    Returns:
        Lista de ``Fixture`` reconstruídas, ordem dos findings preservada.
        Vazia quando não há fixture executável reconstruível.
    """
    fixtures: list[Fixture] = []
    seen_names: set[str] = set()
    for f in findings:
        if not isinstance(f, dict) or f.get("vector") != "validator-claim":
            continue
        # executable=true é o invariante; false (validator inexistente) pula.
        if f.get("executable") is False:
            continue
        ev = f.get("evidence")
        if not isinstance(ev, dict):
            continue
        fixture_path = ev.get("fixture_path")
        validator_path = ev.get("validator_path")
        tree_rel_path = ev.get("tree_rel_path")
        if not (
            isinstance(fixture_path, str)
            and isinstance(validator_path, str)
            and isinstance(tree_rel_path, str)
            and fixture_path
            and validator_path
            and tree_rel_path
        ):
            # Campos insuficientes pra montar uma Fixture executável — pula
            # sem inventar (ex.: validator-claim de validator inexistente que
            # não declarou tree_rel_path). O finding ainda entra no synthesis
            # como draft; só não roda no sandbox.
            continue

        name = Path(fixture_path).stem
        if not name or name in seen_names:
            # Nome vazio ou duplicado (mesmo fixture_id em 2 findings) — pula
            # o duplicado pra não rodar o mesmo mini-tree 2x.
            continue
        seen_names.add(name)

        validator = Path(validator_path)
        if not validator.is_absolute():
            validator = project_root / validator

        input_path = run_tree.fixtures_dir / name / tree_rel_path
        fixtures.append(
            Fixture(
                name=name,
                input_path=input_path,
                validator_path=validator,
                tree_rel_path=tree_rel_path,
            )
        )
    return fixtures


def _write_sandbox_results(
    run_tree: RunTree, results: list[SandboxResult]
) -> None:
    """CR-01: serializa ``SandboxResult`` em ``sandbox-results.json``.

    O ENGINE escreve este arquivo na Phase 3 (antes era o conductor — veredito
    do mantenedor moveu a responsabilidade pro core). Shape segue o contrato
    de ``agents/qa-conductor.md`` (lista de dicts flat com ``fixture_name`` +
    campos de status), consumido logo a seguir por ``hydrate_sandbox_results``
    + ``findings_from_sandbox_results`` + ``hydrate_validator_claim_evidence``.

    Args:
        run_tree: ``RunTree`` da run em curso.
        results: lista de ``SandboxResult`` de ``run_sandbox``.
    """
    payload = [
        {
            "fixture_name": r.fixture.name,
            "status": r.status,
            "exit_code": r.exit_code,
            "stdout": r.stdout,
            "stderr": r.stderr,
            "duration_s": r.duration_s,
            "error": r.error,
        }
        for r in results
    ]
    (run_tree.root / "sandbox-results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _mask_var_name(name: str) -> str:
    """deep-005: mascara nome de var sensitive pra log/alert.

    Mantém 2 primeiros chars + asteriscos do tamanho restante. Em CI com
    log verboso, expor nomes (`STRIPE_LIVE_KEY`, `OAUTH_INTERNAL_VAULT_TOKEN`)
    é information disclosure mesmo sem expor valor — atacante aprende o
    namespace de secrets do host. Mascarar reduz superfície.
    """
    if len(name) <= 2:
        return name
    return name[:2] + "*" * (len(name) - 2)


def _alert_sensitive_drops(card_extras: Iterable[str]) -> None:
    """Pre Phase 3: alerta se vars sensitive serao dropadas (QA-11 Wave 4).

    Dispara um bloco mentor calmo (gate_violation_header + 3-caminhos) em
    stderr quando ``os.environ`` contem variaveis sensitive que NAO estao
    cobertas por:

      - ``CORE_ALLOWLIST`` (PATH/HOME/...),
      - ``extras`` declarados por algum card ativo (``env_needs``),
      - ``qa.sensitive-env-grants`` do workflow-config.

    Como Decisao 27 garante que pause = auto-resumable, o alert e
    informativo: nao bloqueia o run. O caminho oficial pra parar e
    Ctrl+C (registra deferred state); o caminho oficial pra cobrir e
    declarar no card ou granted no projeto (3-caminhos abaixo).

    Args:
        card_extras: vars ja autorizadas (union dos env_needs cross cards
            ativos, intersect com ``CORE_ALLOWLIST | granted``). E o mesmo
            ``extras`` que ``build_safe_env`` receberia em Phase 3.
    """
    extras_tuple = tuple(card_extras)
    dropped = inspect_dropped(extras=extras_tuple)
    sensitive = [v for v in dropped if is_sensitive(v)]
    if not sensitive:
        return

    masked = sorted(_mask_var_name(v) for v in sensitive)
    block = three_paths_block(
        "Variaveis sensitive serao dropadas no sandbox",
        what_failed=(
            f"Detectadas {len(sensitive)} vars sensitive no env do pai "
            f"nao declaradas por nenhum card ativo (nomes mascarados pra "
            f"evitar disclosure em CI log): "
            f"{', '.join(masked)}"
        ),
        where="engine/qa Phase 3 sandbox boot",
        why=[
            "subprocess de validators rodara sem essas vars",
            "se validator/card depende delas, vai falhar com erro de auth/config",
            "se NAO depende, o drop e a defesa funcionando (zero acao)",
        ],
        paths=[
            {
                "label": "Ignorar e seguir",
                "motive": "validator/card nao depende dessas vars — drop esperado",
            },
            {
                "label": "Declarar no card",
                "motive": "editar qa-extensions.env-needs do card relevante e re-rodar",
            },
            {
                "label": "Grant no projeto",
                "motive": "rodar `forge reconfigure` e adicionar em qa.sensitive-env-grants",
            },
        ],
    )
    print(block, file=sys.stderr)


def _compute_allowed_extras(
    project_root: Path,
    workflow_config: dict[str, Any] | None,
) -> tuple[str, ...]:
    """Computa env extras autorizados pra subprocess do sandbox (QA-11).

    Retorna union de ``card.env_needs`` (cross cards ativos) intersect com
    ``(non-sensitive ∪ granted)``. Vars sensitive sem grant sao dropadas
    aqui pra que NUNCA cheguem ao subprocess via handoff json.

    Fail-safe: erro de carga (cards malformados, perm error, etc.) vira
    tupla vazia. O sandbox sempre tem CORE_ALLOWLIST como baseline; tupla
    vazia significa "so o core, nada de extras", que e o estado seguro.

    Args:
        project_root: raiz do projeto consumidor.
        workflow_config: dict completo do workflow-config.yaml (ou None).

    Returns:
        Tupla ordenada determinismo pro handoff JSON (sorted).
    """
    try:
        active_cards = load_all_cards(project_root)
    except (CardError, OSError, ValueError, KeyError):
        return ()

    card_env_needs: set[str] = set()
    for card in active_cards:
        card_env_needs.update(card.env_needs)

    # deep-006: isinstance guard antes de set(). Sem isso, raw_grants
    # vindo como dict produz {chaves} (semantic drift silencioso) e
    # raw_grants string produz {char, ...} (cada caractere vira 'grant'
    # silencioso). grant.py._load_existing_grants já faz esse check —
    # duplicamos aqui para fechar gap até reuse explícito (TODO: extrair
    # pra engine/qa/_grants.py em PR separado — Mandamento #3).
    raw_grants = (workflow_config or {}).get("qa", {}).get("sensitive-env-grants", [])
    if not isinstance(raw_grants, list):
        print(
            f"⚠ qa.sensitive-env-grants tem shape {type(raw_grants).__name__}; "
            f"tratando como vazio.",
            file=sys.stderr,
        )
        raw_grants = []
    granted = {v for v in raw_grants if isinstance(v, str)}

    # Non-sensitive vars sempre passam (user instalou o card).
    # Sensitive vars so passam se ja tem grant explicito do user.
    allowed = {
        v for v in card_env_needs
        if not is_sensitive(v) or v in granted
    }
    return tuple(sorted(allowed))


def _maybe_alert_sensitive_drops(
    project_root: Path, workflow_config: dict[str, Any]
) -> None:
    """Computa ``card_extras`` e chama ``_alert_sensitive_drops``.

    Fail-safe wrapper: o alert layer NUNCA bloqueia QA run. Se qualquer
    coisa quebra (cards nao carregam, persona indisponivel, config
    malformada), emite um warning compacto e segue. A defesa real
    continua em Phase 3 (sandbox dropa por allowlist independentemente
    do alert).
    """
    try:
        allowed_extras = _compute_allowed_extras(project_root, workflow_config)
        _alert_sensitive_drops(allowed_extras)
    except (CardError, OSError, ValueError, KeyError, RuntimeError) as exc:
        # deep-022: RuntimeError adicionado pra cobrir corrupção de
        # catálogo via validate_qa_extensions (não-subclasse de Card/Value/
        # OSError). Contrato do alert layer é "NUNCA bloqueia QA run";
        # deixar RuntimeError escapar contradizia o docstring.
        print(
            f"⚠ Alert layer QA-11 falhou ({type(exc).__name__}: {exc}); "
            f"seguindo sem aviso de env vars sensitive.",
            file=sys.stderr,
        )


def _write_conductor_handoff(
    scope: Scope,
    run_tree: RunTree,
    cfg: QAConfig,
    *,
    allowed_extras: tuple[str, ...] = (),
    snapshot_paths: Iterable[Path] = (),
    workflow_config: dict[str, Any] | None = None,
) -> None:
    """Escreve ``<run_tree.root>/conductor-handoff.json``.

    Payload consumido pelo ``agents/qa-conductor.md`` (Wave 6) pra saber
    qual scope auditar, onde gravar fixtures/findings, e quais limites
    de sandbox respeitar.

    Args:
        scope: ``Scope`` resolvido em Phase 0.
        run_tree: ``RunTree`` criado em Phase 0.
        cfg: ``QAConfig`` parseado em Phase 0.
        allowed_extras: env vars autorizadas pelo card layer pra cruzar a
            barreira do sandbox (QA-11 CR-01). Lista pre-filtrada — vars
            sensitive sem grant ja foram removidas em
            ``_compute_allowed_extras``. O conductor DEVE repassar essa
            lista como ``extras=`` ao invocar ``run_sandbox`` (ver
            ``agents/qa-conductor.md §Sandbox env``).
        snapshot_paths: destinos efetivamente criados por
            ``snapshot_artefacts`` (P-20). Serializados como paths relativos
            a ``run_tree.root`` — portaveis no JSON, sem absolutos da maquina
            que rodou a Phase 0.
        workflow_config: workflow-config completo (P-20). A section ``qa:`` e
            congelada em ``config_snapshot`` per contrato §Inputs do
            qa-conductor (estado da config no momento da run).
    """
    snapshot_rel: list[str] = []
    for p in snapshot_paths:
        try:
            snapshot_rel.append(str(p.relative_to(run_tree.root)))
        except ValueError:
            # Defensivo: dest fora da run tree (nao deveria acontecer —
            # snapshot_artefacts grava sempre sob snapshot_dir). Cai pro
            # nome pra nao vazar absoluto.
            snapshot_rel.append(p.name)

    config_snapshot = (workflow_config or {}).get("qa", {})
    if not isinstance(config_snapshot, dict):
        config_snapshot = {}

    auditors = [a for a in _CORE_AUDITORS if a not in cfg.extensions_disabled]

    handoff: dict[str, Any] = {
        "scope": {
            "type": scope.type,
            "target": scope.target,
            "paths": [str(p) for p in scope.paths],
        },
        "run_id": run_tree.run_id,
        "root": str(run_tree.root),
        # Contrato qa-conductor.md §Inputs: snapshot paths (read-only),
        # config_snapshot (qa: section congelada), auditors ativos.
        "snapshot": snapshot_rel,
        "config_snapshot": config_snapshot,
        "auditors": auditors,
        "config": {
            "sandbox_budget_seconds_total": cfg.sandbox_budget_seconds_total,
            "agent_timeout_seconds": cfg.agent_timeout_seconds,
            "extensions_disabled": list(cfg.extensions_disabled),
            # QA-11 CR-01: contrato subprocess env. Conductor DEVE passar
            # essa lista como `extras=` ao invocar engine.qa.sandbox.run_sandbox
            # — sem isso, cards declarando JAVA_HOME/ANDROID_HOME/etc. quebram
            # mesmo com grants validos. Vars sensitive sem grant ja foram
            # filtradas no engine; lista aqui e tudo seguro pra repassar.
            "allowed_env_extras": list(allowed_extras),
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
