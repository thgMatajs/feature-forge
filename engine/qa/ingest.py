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
(Task 3.6). Defaults batem com ``docs/schemas/forge-config.md §6.4`` —
nao duplique a lista de defaults em outro lugar; este modulo e a fonte
canonica em runtime.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.qa.run_id import generate_run_id
from engine.qa.scope import Scope


# Whitelist conservadora pra scope.target virar componente de path
# (.planning/qa/<target>/<run-id>/). Aceita alfanumericos + ._- pra cobrir
# IDs comuns ("TASK-0007", "feature-name", "screen.id"). Qualquer outro
# caractere e substituido por "_" — defense em profundidade contra
# traversal ("../") ou separadores de path embutidos no input do usuario.
_TARGET_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_scope_target(target: str) -> str | None:
    """Sanitiza ``scope.target`` pra componente de path seguro.

    Source of truth pra duas chamadas no projeto:

    1. :func:`create_run_tree` — usa o helper e converte ``None`` em
       ``ValueError`` (input invalido derruba a Phase 0 imediatamente).
    2. ``engine.qa.checkpoint.find_resumable_run`` — usa o helper e
       converte ``None`` em retorno ``None`` (input invalido significa
       "nenhuma run resumivel a ser encontrada", sem raise).

    Regra: aplica whitelist ``[A-Za-z0-9._-]`` (qualquer outro vira
    ``"_"``). Rejeita resultado vazio (sanitizacao consumiu todo o input)
    ou que comece com ``.`` (mascararia hidden dir).

    Args:
        target: ``scope.target`` bruto conforme entrada do user.

    Returns:
        String sanitizada quando representavel como componente de path;
        ``None`` quando o resultado seria vazio ou comecaria com ``.``.
    """
    safe = _TARGET_SAFE_RE.sub("_", target)
    if not safe or safe.startswith("."):
        return None
    return safe


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

    # Cast defensivo: se o YAML carregou string ao inves de numero
    # (ex.: `agent-timeout-seconds: "15"` por engano), nao queremos
    # ValueError vazar — emite warning mentor-calmo e usa o default.
    # Pattern espelha o approach de engine.reconfigure._qa_adjust_budgets.
    warnings_collected: list[str] = []

    disabled_raw = extensions.get("disabled")
    if disabled_raw is None:
        extensions_disabled: tuple[str, ...] = ()
    elif not isinstance(disabled_raw, list):
        warnings_collected.append(
            f"qa.extensions.disabled={disabled_raw!r} não é lista — "
            f"usando default (). Ajuste via `forge reconfigure → qa`."
        )
        extensions_disabled = ()
    else:
        extensions_disabled = tuple(v for v in disabled_raw if isinstance(v, str))

    def _safe_float(key: str, default: float, source: dict[str, Any]) -> float:
        raw = source.get(key, default)
        try:
            return float(raw)
        except (TypeError, ValueError):
            warnings_collected.append(
                f"qa.{key}={raw!r} nao e numero — usando default {default}. "
                f"Ajuste via `forge reconfigure → qa`."
            )
            return float(default)

    def _safe_int(key: str, default: int, source: dict[str, Any]) -> int:
        raw = source.get(key, default)
        try:
            return int(raw)
        except (TypeError, ValueError):
            warnings_collected.append(
                f"qa.{key}={raw!r} nao e inteiro — usando default {default}. "
                f"Ajuste via `forge reconfigure → qa`."
            )
            return int(default)

    cfg = QAConfig(
        enabled=bool(section.get("enabled", True)),
        auto_run_on_feature_done=bool(
            section.get("auto-run-on-feature-done", False)
        ),
        sandbox_budget_seconds_total=_safe_float(
            "sandbox-budget-seconds-total", 60.0, section
        ),
        agent_timeout_seconds=_safe_float(
            "agent-timeout-seconds", 15.0, section
        ),
        paranoid_max_features=_safe_int(
            "paranoid-max-features", 10, scope_defaults
        ),
        extensions_disabled=extensions_disabled,
        retention_days=_safe_int("retention-days", 14, section),
    )

    # Anexa warnings coletados durante cast — preserva o default mesmo
    # quando o YAML carrega tipo errado, em vez de explodir o handler.
    cfg.warnings.extend(warnings_collected)

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
    # Sanitiza scope.target antes de virar componente de path. Helper
    # canonico em sanitize_scope_target (mesma logica reusada por
    # checkpoint.find_resumable_run). None significa "input
    # irrepresentavel" — aqui derrubamos Phase 0 com mensagem util.
    safe_target = sanitize_scope_target(scope.target)
    if safe_target is None:
        raise ValueError(
            f"scope.target inválido após sanitização: {scope.target!r}. "
            f"Use slug/id que contenha apenas [A-Za-z0-9._-] e não "
            f"comece com ponto."
        )

    run_id = generate_run_id()
    base = project_root / ".planning" / "qa" / safe_target / run_id
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


def snapshot_artefacts(
    scope: Scope, snapshot_dir: Path, *, project_root: Path
) -> list[Path]:
    """Copia (hardlink-preferido) os artefatos resolvidos de ``scope.paths``.

    Spec §5.0 (Phase 0 Ingest): "Snapshot dos artefatos resolvidos em
    <run_id>/snapshot/ (hardlinks ou copy)". Permite que a run conserve
    uma copia imutavel dos specs / validators / outras fontes consumidas,
    de forma que auditoria pos-fato consiga reproduzir o que os auditores
    viram mesmo se o working tree mudou.

    Estrategia de copia:

    1. ``os.link`` (hardlink) e tentado primeiro — instantaneo, sem custo
       de disco, e o conteudo fica genuinamente imutavel (file e o mesmo
       inode).
    2. Em ``OSError`` ou ``NotImplementedError`` (cross-device, FS sem
       suporte a hardlink — ex. tmpfs sobre overlayfs, Windows em alguns
       casos, paths em volumes diferentes) cai pra ``shutil.copy2``,
       preservando metadata.

    Layout preservado: estrutura relativa a ``project_root`` espelhada
    dentro de ``snapshot_dir``. Path absoluto fora do project_root (caso
    raro — scope custom) vira ``snapshot_dir / src.name`` (achatado).

    Paths inexistentes sao silenciosamente puladas — Phase 0 nao quebra
    porque um path em scope.paths nao foi achado (Phase 2/3 auditores
    reportam isso se for relevante).

    Args:
        scope: ``Scope`` resolvido (consome ``scope.paths``).
        snapshot_dir: ``RunTree.snapshot_dir`` (ja criado por
            ``create_run_tree``).
        project_root: raiz do projeto consumidor pra calcular paths
            relativos.

    Returns:
        Lista de ``Path`` dos destinos efetivamente criados em
        ``snapshot_dir``. Lista vazia significa que nenhum path em
        ``scope.paths`` existia ou que ``scope.paths`` estava vazio.
    """
    copied: list[Path] = []
    project_root_resolved = project_root.resolve()

    for src in scope.paths:
        src_path = Path(src)
        if not src_path.exists():
            continue

        # Determina path relativo pra preservar layout dentro do snapshot.
        try:
            rel = src_path.resolve().relative_to(project_root_resolved)
        except ValueError:
            # Path absoluto fora do project_root — achata pro nome do
            # arquivo. Caso raro mas defensivo (Scope custom pode
            # carregar paths absolutos de fora).
            rel = Path(src_path.name)

        dest = snapshot_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            os.link(src_path, dest)
        except (OSError, NotImplementedError):
            # Fallback: copy2 preserva metadata (mtime, permissions).
            # OSError cobre cross-device link (EXDEV), permission errors,
            # FS sem suporte. NotImplementedError em platforms exoticas.
            try:
                shutil.copy2(src_path, dest)
            except OSError:
                # Disk full / perm error mid-copy — silenciamos pra nao
                # explodir Phase 0; snapshot e best-effort.
                continue

        copied.append(dest)

    return copied
