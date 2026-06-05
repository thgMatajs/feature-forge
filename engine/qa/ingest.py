"""Phase 0 — Ingest. Resolve scope, le qa: config, cria run tree.

Spec §5.0 (Phase 0 Ingest) + §6.4 (qa section schema). Consumer canonico:
``engine/qa.py`` top-level handler (Task 4.1). API publica:

    from engine.qa.ingest import parse_qa_config, create_run_tree, QAConfig, RunTree
    cfg = parse_qa_config(workflow_config)
    if cfg.warnings:
        # caller decide: logar, propagar, ignorar
        ...
    tree = create_run_tree(scope, project_root=root)

Reusa ``engine.qa.scope.Scope`` (Task 3.1) e ``engine.qa.run_id.generate_run_id``
(Task 3.6). Defaults batem com ``docs/schemas/workflow-config.md §6.4`` —
nao duplique a lista de defaults em outro lugar; este modulo e a fonte
canonica em runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.qa.run_id import generate_run_id
from engine.qa.scope import Scope


@dataclass
class QAConfig:
    """Config resolvida da section ``qa:`` do workflow-config.

    Mutavel deliberadamente — ``warnings`` e coleta progressiva durante
    parse e o caller pode estender se detectar inconsistencias adicionais.
    Defaults batem com spec §6.4.

    Attributes:
        enabled: ``forge qa`` habilitado. Default ``True``.
        auto_run_on_feature_done: dispara qa pre-retrospective. Default ``False``.
        sandbox_budget_seconds_total: budget global Phase 3. Default ``60.0``.
        agent_timeout_seconds: timeout per-validator. Default ``15.0``.
        paranoid_max_features: cap pra paranoid scope. Default ``10``.
        extensions_disabled: tupla de auditor names desabilitados. Default ``()``.
        retention_days: ``.planning/qa/<run-id>/`` retidos por N dias. Default ``14``.
        warnings: lista mutavel de mensagens (voz mentor calmo). Default ``[]``.
    """

    enabled: bool = True
    auto_run_on_feature_done: bool = False
    sandbox_budget_seconds_total: float = 60.0
    agent_timeout_seconds: float = 15.0
    paranoid_max_features: int = 10
    extensions_disabled: tuple[str, ...] = ()
    retention_days: int = 14
    warnings: list[str] = field(default_factory=list)


def parse_qa_config(workflow_config: dict[str, Any] | None) -> QAConfig:
    """Le section ``qa:`` do workflow-config e devolve ``QAConfig`` populado.

    Comportamento defensivo: ``workflow_config`` None ou nao-dict sao
    tratados como "section ausente" -> defaults aplicados. Sub-dicts
    (``scope-defaults``, ``extensions``) tambem tolerados como ``None`` ou
    ausentes — type guards inline evitam ``AttributeError``.

    Inconsistencia ``enabled=false`` + ``auto-run-on-feature-done=true``
    e capturada em ``cfg.warnings`` (NAO raise) — caller (engine/qa.py
    Phase 0) decide se loga, propaga, ou ignora.

    Args:
        workflow_config: dict completo do workflow-config.yaml, ou None.

    Returns:
        ``QAConfig`` com valores resolvidos e ``warnings`` populado.
    """
    if not isinstance(workflow_config, dict):
        workflow_config = {}

    section = workflow_config.get("qa")
    if not isinstance(section, dict):
        section = {}

    scope_defaults = section.get("scope-defaults")
    if not isinstance(scope_defaults, dict):
        scope_defaults = {}

    extensions = section.get("extensions")
    if not isinstance(extensions, dict):
        extensions = {}

    disabled_raw = extensions.get("disabled") or []
    extensions_disabled = tuple(disabled_raw)

    cfg = QAConfig(
        enabled=bool(section.get("enabled", True)),
        auto_run_on_feature_done=bool(
            section.get("auto-run-on-feature-done", False)
        ),
        sandbox_budget_seconds_total=float(
            section.get("sandbox-budget-seconds-total", 60.0)
        ),
        agent_timeout_seconds=float(section.get("agent-timeout-seconds", 15.0)),
        paranoid_max_features=int(scope_defaults.get("paranoid-max-features", 10)),
        extensions_disabled=extensions_disabled,
        retention_days=int(section.get("retention-days", 14)),
    )

    if not cfg.enabled and cfg.auto_run_on_feature_done:
        cfg.warnings.append(
            "qa.enabled=false mas auto-run-on-feature-done=true — "
            "auto-run nunca dispara. Reconcilie via `forge reconfigure → qa`."
        )

    return cfg


@dataclass(frozen=True)
class RunTree:
    """Diretorios canonicos de uma run de ``forge qa``.

    Layout: ``.planning/qa/<scope.target>/<run-id>/{fixtures,findings,audit,snapshot}/``.
    Frozen porque, uma vez criada, a tree e contrato com Phases 1-5.

    Attributes:
        run_id: identificador da run (``YYYY-MM-DDTHH-MM-SSZ-<hex4>``).
        root: ``.planning/qa/<target>/<run-id>/``.
        fixtures_dir: subdir pra Phase 2 fixtures.
        findings_dir: subdir pra Phase 4 findings consolidados.
        audit_dir: subdir pra Phase 1-5 audit log per-step.
        snapshot_dir: subdir pra inventory/graph snapshot do momento.
    """

    run_id: str
    root: Path
    fixtures_dir: Path
    findings_dir: Path
    audit_dir: Path
    snapshot_dir: Path


def create_run_tree(scope: Scope, *, project_root: Path) -> RunTree:
    """Cria ``.planning/qa/<scope.target>/<run-id>/`` tree completa.

    Idempotente — ``mkdir(parents=True, exist_ok=True)`` tolera diretorios
    pre-existentes. Cada chamada gera novo ``run_id`` via
    ``engine.qa.run_id.generate_run_id``, entao re-invocacoes nao colidem.

    Args:
        scope: ``Scope`` resolvido (Phase 0 scope step). ``scope.target``
            vira parte do path.
        project_root: raiz do projeto consumidor (onde ``.planning/`` mora).

    Returns:
        ``RunTree`` com paths absolutos dos 4 subdirs criados.
    """
    run_id = generate_run_id()
    base = project_root / ".planning" / "qa" / scope.target / run_id
    fixtures = base / "fixtures"
    findings = base / "findings"
    audit = base / "audit"
    snapshot = base / "snapshot"
    for d in (fixtures, findings, audit, snapshot):
        d.mkdir(parents=True, exist_ok=True)
    return RunTree(
        run_id=run_id,
        root=base,
        fixtures_dir=fixtures,
        findings_dir=findings,
        audit_dir=audit,
        snapshot_dir=snapshot,
    )
