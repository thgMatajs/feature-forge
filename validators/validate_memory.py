#!/usr/bin/env python3
"""validate_memory.py — Memory layer structural check.

Validates `.claude/memory/`:

- Every L1/{slug}/status.json parses and has a valid `state` enum
  (MEM-L1-008)
- verify-log.jsonl lines parse and `result` ∈ {pass, warn, fail, degraded}
- L2-project.yaml parses, schema-version == 1, file size ≤ max-size-mb
  declared in workflow-config (default 0.5 MB)
- archived/{slug}/summary.yaml parses when present

Schema source: docs/schemas/memory.md (MEM-L1-001..008 / MEM-L2-001..007).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from _common import (
    make_paths,
    result_fail,
    result_pass,
    result_warn,
    run_cli,
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.memory.l1 import _VALID_STATES  # noqa: E402
from engine.utils.paths import (  # noqa: E402
    memory_dir,
    memory_l2_path,
    workflow_config_path,
)
from engine.utils.yaml_io import YamlIOError, read_yaml_or_default  # noqa: E402


# C-44 (PR22-R-002): fonte única de verdade — o enum canônico vive em
# engine.memory.l1._VALID_STATES (9 estados). O set paralelo anterior aceitava
# `paused` (removido em T1/74e4da5) e rejeitava estados canônicos
# (not-started/planned/deferred/blocked-on-external), tornando o gate
# dessincronizado com o writer. Aliasamos o canônico — sem cópia paralela.
_VALID_L1_STATES = _VALID_STATES
_VALID_VERIFY_RESULTS = {"pass", "warn", "fail", "degraded"}

# MEM-L2-003: kinds canônicos para L2 patterns/findings/decisions.
_VALID_L2_KINDS = {
    "pattern",
    "finding",
    "decision",
    "rule",
    "ambiguity",
    "anti-pattern",
    "metric",
}


def _l2_size_limit_mb(config: dict[str, Any]) -> float:
    """Lê `memory.l2.max-size-mb` (canônico) com fallback p/ `memory.L2-project.max-size-mb`.

    TODO v1.1: remover fallback legacy após migrator rodar.
    """
    mem = config.get("memory") if isinstance(config, dict) else None
    if not isinstance(mem, dict):
        return 0.5
    l2 = mem.get("l2") or mem.get("L2-project") or {}
    size = l2.get("max-size-mb") if isinstance(l2, dict) else None
    if isinstance(size, (int, float)) and size > 0:
        return float(size)
    return 0.5


def _check_l1_status(path: Path) -> list[str]:
    out: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (json.JSONDecodeError, OSError) as exc:
        return [f"{path.parent.name}/status.json parse error: {exc}"]
    if not isinstance(data, dict):
        return [f"{path.parent.name}/status.json: top-level not object"]
    state = data.get("state")
    if state not in _VALID_L1_STATES:
        out.append(f"{path.parent.name}/status.json: state {state!r} not in {sorted(_VALID_L1_STATES)}")
    sub_state = data.get("sub-state")
    if state == "implementing" and sub_state is None:
        out.append(f"{path.parent.name}/status.json: state=implementing requires non-null sub-state (MEM-L1-008)")
    if state != "implementing" and sub_state is not None:
        out.append(f"{path.parent.name}/status.json: sub-state={sub_state!r} only valid when state==implementing")
    return out


def _check_verify_log(path: Path) -> list[str]:
    out: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path.parent.name}/verify-log.jsonl read error: {exc}"]
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            out.append(f"{path.parent.name}/verify-log.jsonl L{lineno}: JSON error ({exc})")
            continue
        if not isinstance(obj, dict):
            out.append(f"{path.parent.name}/verify-log.jsonl L{lineno}: not an object")
            continue
        result = obj.get("result")
        if result not in _VALID_VERIFY_RESULTS:
            out.append(
                f"{path.parent.name}/verify-log.jsonl L{lineno}: result {result!r} "
                f"not in {sorted(_VALID_VERIFY_RESULTS)}"
            )
    return out


def _check_l2(project_root: Path, config: dict[str, Any]) -> list[str]:
    l2 = memory_l2_path(project_root)
    if not l2.is_file():
        return []  # L2 may not exist yet on greenfield projects
    out: list[str] = []
    try:
        data = read_yaml_or_default(l2, {}) or {}
    except (YamlIOError, OSError, UnicodeDecodeError) as exc:
        return [f"L2-project.yaml YAML error: {exc}"]
    if isinstance(data, dict) and data.get("schema-version") != 1:
        out.append(f"L2-project.yaml: schema-version must be 1, got {data.get('schema-version')!r}")
    try:
        size_mb = l2.stat().st_size / (1024 * 1024)
    except OSError:
        size_mb = 0.0
    max_mb = _l2_size_limit_mb(config)
    if size_mb > max_mb:
        out.append(
            f"L2-project.yaml size {size_mb:.2f}MB exceeds max-size-mb={max_mb} — distillation due"
        )
    return out


def _check_l1_slug_matches_dir(slug_dir: Path) -> list[str]:
    """MEM-L1-001: feature-slug em status.json deve casar com nome do diretório."""
    status = slug_dir / "status.json"
    if not status.is_file():
        return []
    try:
        data = json.loads(status.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    declared = data.get("feature-slug")
    if isinstance(declared, str) and declared != slug_dir.name:
        return [
            f"L1/{slug_dir.name}/status.json: feature-slug {declared!r} ≠ dir name {slug_dir.name!r} (MEM-L1-001)"
        ]
    return []


def _check_rationale_trace(project_root: Path, slug_dir: Path) -> list[str]:
    """MEM-L1-005: rationale-trace decisions devem referenciar arquivos reais."""
    path = slug_dir / "rationale-trace.yaml"
    if not path.is_file():
        return []
    try:
        data = read_yaml_or_default(path, {}) or {}
    except (YamlIOError, OSError, UnicodeDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    decisions = data.get("decisions") or []
    if not isinstance(decisions, list):
        return []
    out: list[str] = []
    for dec in decisions:
        if not isinstance(dec, dict):
            continue
        artifact = dec.get("artifact") or dec.get("artifact-path") or dec.get("source")
        if isinstance(artifact, str) and artifact.strip():
            # Aceita caminhos relativos ao project_root.
            candidate = (project_root / artifact).resolve()
            if not candidate.exists():
                out.append(
                    f"L1/{slug_dir.name}/rationale-trace.yaml: artifact {artifact!r} não existe (MEM-L1-005)"
                )
    return out


def _check_dispatch_log(slug_dir: Path) -> list[str]:
    """MEM-L1-007: dispatch-log.jsonl — todas as linhas devem parsear."""
    path = slug_dir / "dispatch-log.jsonl"
    if not path.is_file():
        return []
    out: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"L1/{slug_dir.name}/dispatch-log.jsonl read error: {exc}"]
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            out.append(
                f"L1/{slug_dir.name}/dispatch-log.jsonl L{lineno}: JSON error ({exc}) (MEM-L1-007)"
            )
            continue
        if not isinstance(obj, dict):
            out.append(
                f"L1/{slug_dir.name}/dispatch-log.jsonl L{lineno}: linha não-objeto (MEM-L1-007)"
            )
    return out


def _check_l2_kinds_and_provenance(project_root: Path, config: dict[str, Any]) -> list[str]:
    """MEM-L2-003 + MEM-L2-005:

    - Entries em listas L2 (patterns/findings/decisions) devem ter `kind`
      canônico quando o campo estiver presente.
    - `provenance.feature_slugs` deve referenciar dirs L1 reais (active ou
      archived) — refs órfãs sinalizam L2 desatualizada.
    """
    l2_path = memory_l2_path(project_root)
    if not l2_path.is_file():
        return []
    out: list[str] = []
    try:
        data = read_yaml_or_default(l2_path, {}) or {}
    except (YamlIOError, OSError, UnicodeDecodeError):
        return []
    if not isinstance(data, dict):
        return []

    # Conjunto de slugs L1 conhecidos (active + archived).
    mem = memory_dir(project_root)
    known_slugs: set[str] = set()
    l1_root = mem / "L1"
    if l1_root.is_dir():
        for child in l1_root.iterdir():
            if child.is_dir() and child.name != "archived":
                known_slugs.add(child.name)
    archived = mem / "archived"
    if archived.is_dir():
        for child in archived.iterdir():
            if child.is_dir():
                known_slugs.add(child.name)

    # Varre listas top-level conhecidas.
    for key in ("patterns", "findings", "decisions", "anti-patterns"):
        entries = data.get(key)
        if not isinstance(entries, list):
            continue
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            # MEM-L2-003: kind canônico (quando declarado).
            kind = entry.get("kind")
            if isinstance(kind, str) and kind not in _VALID_L2_KINDS:
                out.append(
                    f"L2-project.yaml {key}[{idx}].kind {kind!r} fora de {sorted(_VALID_L2_KINDS)} (MEM-L2-003)"
                )
            # MEM-L2-005: provenance.feature_slugs referenciam features reais.
            prov = entry.get("provenance")
            slugs: list[str] = []
            if isinstance(prov, dict):
                raw = prov.get("feature_slugs") or prov.get("feature-slugs") or []
                if isinstance(raw, list):
                    slugs = [s for s in raw if isinstance(s, str)]
            elif isinstance(prov, list):
                slugs = [s for s in prov if isinstance(s, str)]
            for slug in slugs:
                if known_slugs and slug not in known_slugs:
                    out.append(
                        f"L2-project.yaml {key}[{idx}].provenance: feature_slug {slug!r} não existe em L1 (MEM-L2-005)"
                    )
    return out


def _check_archived(project_root: Path) -> list[str]:
    out: list[str] = []
    archived = memory_dir(project_root) / "archived"
    if not archived.is_dir():
        return out
    for slug_dir in archived.iterdir():
        if not slug_dir.is_dir():
            continue
        summary = slug_dir / "summary.yaml"
        if not summary.is_file():
            out.append(f"archived/{slug_dir.name}/summary.yaml ausente")
            continue
        try:
            read_yaml_or_default(summary, {})
        except (YamlIOError, OSError, UnicodeDecodeError) as exc:
            out.append(f"archived/{slug_dir.name}/summary.yaml YAML error: {exc}")
    return out


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Validate L1/L2/archived memory structure."""
    config = read_yaml_or_default(workflow_config_path(project_root), {}) or {}
    mem = memory_dir(project_root)
    if not mem.is_dir():
        return result_pass("memory/ dir ausente — greenfield project (nada a checar)")

    violations: list[str] = []
    soft: list[str] = []
    l1_root = mem / "L1"
    if l1_root.is_dir():
        for slug_dir in l1_root.iterdir():
            if not slug_dir.is_dir():
                continue
            # Pular o "archived" pseudo-dir sob L1/ — checagem dedicada faz isso.
            if slug_dir.name == "archived":
                continue
            status = slug_dir / "status.json"
            if status.is_file():
                violations.extend(_check_l1_status(status))
            vlog = slug_dir / "verify-log.jsonl"
            if vlog.is_file():
                violations.extend(_check_verify_log(vlog))
            # MEM-L1-001 / MEM-L1-005 / MEM-L1-007 ─────────────────────────
            violations.extend(_check_l1_slug_matches_dir(slug_dir))
            violations.extend(_check_rationale_trace(project_root, slug_dir))
            violations.extend(_check_dispatch_log(slug_dir))

    violations.extend(_check_l2(project_root, config))
    # MEM-L2-003 + MEM-L2-005 ───────────────────────────────────────────────
    violations.extend(_check_l2_kinds_and_provenance(project_root, config))
    soft.extend(_check_archived(project_root))

    if violations:
        return result_fail(
            f"{len(violations)} violação(ões) em memory layers",
            what_failed="; ".join(violations[:3]) + (f" (+{len(violations)-3} more)" if len(violations) > 3 else ""),
            where=str(mem.relative_to(project_root)),
            why=[
                "MEM-L1-008 / MEM-L2-001..007 — sub-agents leem essas memórias direto.",
                "Memory corrompida = conductor não retoma corretamente.",
            ],
            paths=make_paths(
                "Editar os JSON/YAMLs manualmente conforme as violations",
                "MEM-* codes apontam o campo + valor errado.",
                "Forçar status.json válido — `forge undo` restaura último checkpoint",
                "L1 status pode ser reescrito do último resume point.",
                "Distill L2 — `forge memory distill` quando size estoura",
                "Se a violação for size, distill compress mantendo decisões críticas.",
            ),
        )

    if soft:
        return result_warn(
            f"{len(soft)} warning(s) em archived/ summaries",
            what_failed="; ".join(soft[:3]),
            where=str((mem / 'archived').relative_to(project_root)),
            why=["archived summaries ausentes/corrompidos não bloqueiam mas dificultam retrospect"],
        )

    return result_pass("memory layers OK (L1/L2/archived)")


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
