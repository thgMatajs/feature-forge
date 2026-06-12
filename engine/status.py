"""`forge status` — read-only project board.

Renders six sections, all without mutating state:

1. Project           — preset, cards count, last-reconfigure, forge-version
2. Active features   — slug, status, last-action + humanised delta
3. Memory            — L2 size/max, L1 active/archived count
4. Pending evolutions — top entries from `.claude/proposed-evolutions.yaml`
5. Doctor freshness  — `doctor.last-run` + a soft nudge when stale
6. Recent activity   — last 5 history events across L1s and workflow-config-history

Pure read. No prompts, no writes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.memory.l1 import (
    blocking_deps,
    list_active_features,
    list_archived_features,
    read_history,
    read_l1_status,
)
from engine.memory.l2 import l2_size_bytes
from engine.ui import renderer
from engine.utils.paths import (
    ProjectRootNotFoundError,
    claude_dir,
    find_project_root,
    memory_dir,
    memory_l2_path,
    workflow_config_path,
)
from engine.utils.yaml_io import YamlIOError, read_yaml

from engine import __version__ as FORGE_VERSION


# ── Public API ───────────────────────────────────────────────────────────────


def run(argv: list[str]) -> int:  # noqa: ARG001 — no args by design
    """Entry point. Always returns 0 unless the project root is missing."""
    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        renderer.write(renderer.colored(str(exc), "red"))
        renderer.write("Rode `forge init` antes.")
        return 1

    config = _safe_read_yaml(workflow_config_path(project_root)) or {}

    renderer.write("")
    renderer.write(renderer.bold("forge status"))
    renderer.write(renderer.dim("Read-only · board do projeto"))

    _render_project(project_root, config)
    _render_active_features(project_root)
    _render_memory(project_root, config)
    _render_pending_evolutions(project_root)
    _render_doctor_freshness(config)
    _render_recent_activity(project_root)
    return 0


# ── Section renderers ────────────────────────────────────────────────────────


def _render_project(project_root: Path, config: dict) -> None:
    identity = (config.get("identity") or {}) if isinstance(config, dict) else {}
    cards_active = (config.get("cards") or {}).get("active") or []
    body = [
        f"name:             {identity.get('project-name', project_root.name)}",
        f"slug:             {identity.get('project-slug', project_root.name)}",
        f"preset:           {identity.get('preset', '(unset)')}",
        f"cards active:     {len(cards_active)}",
        f"last-reconfigure: {identity.get('last-reconfigure', 'never')}",
        f"forge-version:    {identity.get('forge-version', FORGE_VERSION)}",
    ]
    renderer.write("")
    renderer.write(renderer.box("project", body))


_IN_FLIGHT_STATES = {"planning", "planned", "implementing", "verifying"}


def _render_active_features(project_root: Path) -> None:
    """Render the feature board, partitioned by lifecycle state.

    Discipline §9 — blocked-on-external is a sibling of deferred, surfaced
    in its own section so dev sees "what to chase externally" at a glance.
    """
    active = list_active_features(project_root)

    # Bucket by state. A feature with no status.json shows as "unknown".
    in_flight: list[tuple[str, Any]] = []
    blocked: list[tuple[str, Any]] = []
    deferred: list[tuple[str, Any]] = []
    other: list[tuple[str, Any]] = []
    for slug in active:
        st = read_l1_status(slug, project_root)
        if st is None:
            other.append((slug, None))
            continue
        if st.status == "blocked-on-external":
            blocked.append((slug, st))
        elif st.status == "deferred":
            deferred.append((slug, st))
        elif st.status in _IN_FLIGHT_STATES:
            in_flight.append((slug, st))
        else:
            other.append((slug, st))

    renderer.write("")
    renderer.write(renderer.section_header("in-flight features"))
    if not in_flight:
        renderer.write("  (nenhuma)")
    else:
        for slug, st in in_flight:
            delta = _humanize_delta(st.last_action_at)
            renderer.write(
                f"  · {slug:<28} {st.status:<12} "
                f"last: {st.last_action_kind or '—'}  ({delta})"
            )

    if blocked:
        renderer.write("")
        renderer.write(renderer.section_header("blocked on external"))
        for slug, st in blocked:
            deps = blocking_deps(slug, project_root)
            ticket_summary = _format_blocked_summary(deps)
            delta = _humanize_delta(st.last_action_at)
            renderer.write(f"  · {slug:<28} {ticket_summary}  ({delta})")
        renderer.write("")
        renderer.write(
            "  desbloqueio: forge reconfigure → external-deps → "
            "marcar dep externa como resolvida"
        )

    if deferred:
        renderer.write("")
        renderer.write(renderer.section_header("deferred"))
        for slug, st in deferred:
            delta = _humanize_delta(st.last_action_at)
            renderer.write(
                f"  · {slug:<28} {st.last_action_kind or '—'}  ({delta})"
            )

    if other:
        renderer.write("")
        renderer.write(renderer.section_header("other states"))
        for slug, st in other:
            if st is None:
                renderer.write(f"  · {slug}  (sem status.json)")
                continue
            delta = _humanize_delta(st.last_action_at)
            renderer.write(
                f"  · {slug:<28} {st.status:<12} "
                f"last: {st.last_action_kind or '—'}  ({delta})"
            )


def _format_blocked_summary(deps: list[dict[str, Any]]) -> str:
    """Compact single-line summary of unique tickets blocking a feature."""
    if not deps:
        return "(sem deps)"
    # Group by ticket so the same ticket across N tasks shows once.
    by_ticket: dict[str, dict[str, Any]] = {}
    for d in deps:
        ticket = str(d.get("ticket") or "?")
        if ticket not in by_ticket:
            by_ticket[ticket] = {
                "integration": d.get("integration") or "manual",
                "tasks": set(),
            }
        by_ticket[ticket]["tasks"].add(d.get("task") or "?")
    parts: list[str] = []
    for ticket, meta in by_ticket.items():
        n = len(meta["tasks"])
        suffix = "" if n == 1 else f" ({n} tasks)"
        parts.append(f"{ticket} ({meta['integration']}){suffix}")
    return " · ".join(parts)


def _render_memory(project_root: Path, config: dict) -> None:
    max_mb = _config_get_path(config, ["memory", "l2", "max-size-mb"], None)
    if max_mb is None:
        max_mb = _config_get_path(config, ["memory", "L2-project", "max-size-mb"], 0.5)
    try:
        max_bytes = float(max_mb) * 1024 * 1024
    except (TypeError, ValueError):
        max_bytes = 0.5 * 1024 * 1024
    l2_path = memory_l2_path(project_root)
    if l2_path.exists():
        size_bytes = l2_size_bytes(project_root)
        pct = (size_bytes / max_bytes * 100) if max_bytes else 0
        l2_summary = f"{size_bytes / 1024:.1f} KB / {max_mb} MB ({pct:.0f}%)"
    else:
        l2_summary = "(ainda não criado)"

    body = [
        f"L2 size:          {l2_summary}",
        f"L1 active:        {len(list_active_features(project_root))}",
        f"L1 archived:      {len(list_archived_features(project_root))}",
    ]
    renderer.write("")
    renderer.write(renderer.box("memory", body))


def _render_pending_evolutions(project_root: Path) -> None:
    path = claude_dir(project_root) / "proposed-evolutions.yaml"
    renderer.write("")
    renderer.write(renderer.section_header("pending evolutions"))
    if not path.exists():
        renderer.write("  (nenhuma)")
        return
    try:
        data = read_yaml(path)
    except YamlIOError as exc:
        renderer.write(renderer.colored(f"  parse error: {exc}", "yellow"))
        return
    proposals = (data or {}).get("proposals") or [] if isinstance(data, dict) else []
    if not proposals:
        renderer.write("  (nenhuma)")
        return
    renderer.write(f"  total: {len(proposals)}")
    for prop in proposals[:3]:
        if not isinstance(prop, dict):
            continue
        pid = prop.get("id") or "?"
        ptype = prop.get("type") or "?"
        rationale = str(prop.get("rationale") or "").split("\n", 1)[0]
        title = rationale[:60] or ptype
        renderer.write(f"  · {pid}  [{ptype}]  {title}")
    if len(proposals) > 3:
        renderer.write(f"  … +{len(proposals) - 3} mais — rode `forge evolve`")


def _render_doctor_freshness(config: dict) -> None:
    doctor_block = (config.get("doctor") or {}) if isinstance(config, dict) else {}
    last_run = doctor_block.get("last-run")
    last_status = doctor_block.get("last-status")
    body = [
        f"last-run:    {last_run or 'never'}",
        f"last-status: {last_status or '—'}",
    ]
    stale_msg = _doctor_stale_hint(last_run)
    if stale_msg:
        body.append(f"hint:        {stale_msg}")
    renderer.write("")
    renderer.write(renderer.box("doctor freshness", body))


def _render_recent_activity(project_root: Path) -> None:
    renderer.write("")
    renderer.write(renderer.section_header("recent activity (5)"))
    events: list[tuple[str, str, str]] = []  # (at, source, kind/title)

    for slug in list_active_features(project_root):
        try:
            history = read_history(slug, project_root)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
        for entry in history:
            at = str(entry.get("at") or "")
            kind = str(entry.get("kind") or entry.get("event") or "—")
            events.append((at, f"L1/{slug}", kind))

    wch = memory_dir(project_root).parent / "workflow-config-history.jsonl"
    if wch.is_file():
        try:
            with wch.open("r", encoding="utf-8") as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    at = str(obj.get("at") or obj.get("timestamp") or "")
                    kind = str(obj.get("kind") or obj.get("action") or "config-change")
                    events.append((at, "workflow-config", kind))
        except OSError:
            pass

    if not events:
        renderer.write("  (sem eventos registrados ainda)")
        return

    events.sort(key=lambda e: e[0], reverse=True)
    for at, source, kind in events[:5]:
        delta = _humanize_delta(at)
        renderer.write(f"  · {at[:19] or '?':<19} {source:<22} {kind}  ({delta})")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _safe_read_yaml(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = read_yaml(path)
    except YamlIOError:
        return None
    return data if isinstance(data, dict) else None


def _config_get_path(config: dict, keys: list[str], default: Any) -> Any:
    cursor: Any = config
    for key in keys:
        if not isinstance(cursor, dict):
            return default
        cursor = cursor.get(key)
        if cursor is None:
            return default
    return cursor


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    cleaned = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _humanize_delta(iso_at: str) -> str:
    """Return a short human delta like ``há 2h`` for an ISO timestamp."""
    dt = _parse_iso(iso_at)
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = now - dt
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "no futuro"
    if total_seconds < 60:
        return f"há {total_seconds}s"
    if total_seconds < 3600:
        return f"há {total_seconds // 60}m"
    if total_seconds < 86400:
        return f"há {total_seconds // 3600}h"
    days = total_seconds // 86400
    return f"há {days}d"


def _doctor_stale_hint(last_run: Any) -> str | None:
    if not isinstance(last_run, str) or not last_run:
        return "rode `forge doctor` (ainda nunca rodou aqui)"
    dt = _parse_iso(last_run)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    if age_days > 7:
        return f"última checagem há {int(age_days)}d — considere rodar `forge doctor`"
    return None
