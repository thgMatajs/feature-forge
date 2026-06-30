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
import subprocess
import sys
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
from engine.integrations.mem import mem_stats
from engine.ui import output_mode, renderer
from engine.utils.paths import (
    ProjectRootNotFoundError,
    active_config_path,
    claude_dir,
    find_project_root,
    memory_dir,
)
from engine.utils.yaml_io import YamlIOError, read_yaml

from engine import __version__ as FORGE_VERSION


# ── Public API ───────────────────────────────────────────────────────────────


def run(argv: list[str]) -> int:  # noqa: ARG001 — no args by design
    """Entry point. Always returns 0 unless the project root is missing."""
    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        if output_mode.is_json_mode():
            sys.stderr.write(f"forge status: {exc}\n")
            return 1
        renderer.write(renderer.colored(str(exc), "red"))
        renderer.write("Rode `forge init` antes.")
        return 1

    config = _safe_read_yaml(active_config_path(project_root)) or {}

    if output_mode.is_json_mode():
        payload = _status_payload(project_root, config)
        print(json.dumps(payload, indent=2, default=str))
        return 0

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
            # BUG-STATUS-1/2: reconciliação git + qa verdict (read-only).
            recon = _feature_reconcile_line(project_root, slug, st.status)
            if recon:
                renderer.write(f"      {recon}")

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


def _render_memory(project_root: Path, config: dict) -> None:  # noqa: ARG001
    l1_active = len(list_active_features(project_root))
    l1_archived = len(list_archived_features(project_root))

    stats_res = mem_stats(project_root)
    if stats_res.ok and isinstance(stats_res.data, dict):
        s = stats_res.data
        mem_line = (
            f"mem total={s.get('total', 0)}  live={s.get('live', 0)}"
            f"  stale={s.get('stale', 0)}"
        )
        by_type = s.get("by_type") or {}
        by_type_parts = "  ".join(f"{t}={n}" for t, n in sorted(by_type.items()))
        mem_detail = f"  ({by_type_parts})" if by_type_parts else ""
    else:
        mem_line = "mem: indisponível"
        mem_detail = ""

    body = [
        f"{mem_line}{mem_detail}",
        f"L1 active:        {l1_active}",
        f"L1 archived:      {l1_archived}",
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
        except (MemoryError, OSError, UnicodeDecodeError):
            # B-001 (master review PR #15): `read_history` wraps
            # `JSONDecodeError` in `MemoryError` (engine/memory/l1.py).
            # JSONDecodeError directly is never raised from this path —
            # catching it was a no-op and a malformed JSONL crashed the
            # status render. Now we tolerate the wrapped error and skip
            # the offending feature's history (best-effort observability).
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


def _mem_stats_snapshot(project_root: Path) -> dict | None:
    """Snapshot de mem stats pro JSON payload. None se mem indisponível."""
    res = mem_stats(project_root)
    if not res.ok or not isinstance(res.data, dict):
        return None
    s = res.data
    return {
        "total": s.get("total", 0),
        "by_type": s.get("by_type") or {},
        "live": s.get("live", 0),
        "stale": s.get("stale", 0),
    }


# ── Machine-readable payload (A1 + A2) ────────────────────────────────────────


def _status_payload(project_root: Path, config: dict) -> dict:
    """Machine-readable snapshot of the project board (A1 + A2)."""
    identity = (config.get("identity") or {}) if isinstance(config, dict) else {}
    cards_active = (config.get("cards") or {}).get("active") or []
    features: list[dict] = []
    for slug in list_active_features(project_root):
        st = read_l1_status(slug, project_root)
        status_value = st.status if st is not None else None
        feature: dict[str, Any] = {
            "slug": slug,
            "status": status_value,
            "last_action_kind": (st.last_action_kind if st is not None else None),
            "last_action_at": (st.last_action_at if st is not None else None),
            # BUG-STATUS-2: qa verdict reconciliado do qa-report.json (H-001).
            "qa_verdict": _read_qa_verdict(project_root, slug),
        }
        # BUG-STATUS-1: bloco git só quando há repo (None → omite, honesto).
        git_block = _feature_git_block(project_root, slug, status_value)
        if git_block is not None:
            feature["git"] = git_block
        features.append(feature)
    doctor_block = (config.get("doctor") or {}) if isinstance(config, dict) else {}
    return {
        "project": {
            "name": identity.get("project-name", project_root.name),
            "slug": identity.get("project-slug", project_root.name),
            "preset": identity.get("preset"),
            "cards_active": len(cards_active),
            "forge_version": identity.get("forge-version", FORGE_VERSION),
        },
        "active_features": features,
        "memory": {
            "l1_active": len(features),
            "l1_archived": len(list_archived_features(project_root)),
            "mem": _mem_stats_snapshot(project_root),
        },
        "pending_evolutions": _pending_evolutions_count(project_root),
        "doctor": {
            "last_run": doctor_block.get("last-run"),
            "last_status": doctor_block.get("last-status"),
        },
        "suggested_next_command": _suggested_next_command(features),
    }


def _pending_evolutions_count(project_root: Path) -> int:
    path = claude_dir(project_root) / "proposed-evolutions.yaml"
    if not path.exists():
        return 0
    try:
        data = read_yaml(path)
    except YamlIOError:
        return 0
    proposals = (data or {}).get("proposals") or [] if isinstance(data, dict) else []
    return len(proposals)


def _suggested_next_command(features: list[dict]) -> str:
    """Workflow router (A2 NO-WORKFLOW-ROUTER).

    Maps the most-recently-active feature state to the next verb. Falls back
    to ``plan`` when no feature is active and ``doctor`` for an out-of-enum
    state (corrupt status.json).

    H-002: covers ALL 9 states of ``engine.memory.l1._VALID_STATES`` — partial
    coverage routed real states (``not-started``/``aborted``/``done``/etc.)
    to the bare ``doctor`` default and mis-guided the agent.

    W-003: the recency selection uses an explicit, stable tie-break — features
    that tie on ``last_action_at`` (e.g. all ``None``) are broken by feature
    slug, so the suggested verb is a deterministic function of the input rather
    than of iteration/filesystem order.
    """
    if not features:
        return "plan"
    # Pick the most recently active feature. Tie-break (W-003): missing/empty
    # timestamps sort below real ones, and ties resolve by slug so the result
    # is order-independent. Sort key returns (timestamp_or_empty, slug); max
    # then prefers the latest timestamp, then the highest slug — both stable.
    recent = max(
        features,
        key=lambda f: (
            f.get("last_action_at") or "",
            # C-33 (PR21-I1): o payload de _status_payload usa a chave "slug"
            # (não "feature_slug"), então o tie-break antigo era dead-code —
            # sempre "" → tie resolvido por ordem de iteração, não determinístico.
            f.get("slug") or "",
        ),
    )
    state = recent.get("status")
    # H-002: one entry per _VALID_STATES (9 states). PHANTOM-STATES fork
    # resolved in W-DEBT — `verified`/`paused` removed (never written: verify
    # restores the prior status; implement goes implementing→done; pause is
    # `deferred` per Decisão 27).
    mapping = {
        "not-started": "plan",
        "planning": "implement",
        "planned": "implement",
        "implementing": "verify",
        "verifying": "verify",
        "done": "status",
        "deferred": "status",
        "aborted": "plan",
        "blocked-on-external": "reconfigure",
    }
    return mapping.get(state, "doctor")


# ── Git reconcile + qa verdict (BUG-STATUS-1/2 — read-only) ───────────────────


# In-flight states where invisible git commits indicate drift (a feature still
# marked implementing/verifying while the code is already committed).
_GIT_DRIFT_STATES = {"implementing", "verifying", "planning", "planned"}


def _git_feature_commits(project_root: Path, slug: str) -> int | None:
    """Count commits on HEAD touching CODE paths containing the feature slug.

    BUG-STATUS-1: ``forge status`` was forge-faithful but git-blind. This is a
    PURE READ — only ``git log`` (never a mutating subcommand). Returns ``None``
    when the project is not a git repo (or git is unavailable), so the caller
    can omit the git block honestly instead of inventing a count.

    MED-01: the pathspec ``*<slug>*`` alone double-counted — it matched BOTH
    ``src/<slug>/…`` AND ``.planning/qa/<slug>/…`` / ``.claude/.../<slug>``, so a
    commit touching only planning/qa artefacts inflated ``feature_commits`` (a
    signal meant to track CODE work). We exclude the planning/claude artefact
    trees via negative pathspecs (``:(exclude)``) so the count reflects real
    code commits. Slug is sanitised to a git pathspec literal by rejecting
    empty/whitespace.
    """
    if not slug or not slug.strip():
        return None
    try:
        proc = subprocess.run(
            [
                "git",
                "log",
                "--format=%H",
                "--",
                f"*{slug}*",
                ":(exclude).planning/**",
                ":(exclude).claude/**",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return None
    if proc.returncode != 0:
        # Not a git repo / bad ref / no commits yet → no git observation.
        return None
    return sum(1 for line in proc.stdout.splitlines() if line.strip())


def _read_qa_verdict(project_root: Path, target: str) -> str | None:
    """Read the verdict of the most recent qa run for ``target``.

    BUG-STATUS-2: the qa verdict IS persisted (H-001) at
    ``.planning/qa/<target>/<run-id>/qa-report.json`` (top-level ``verdict``).
    Run-ids are ISO-timestamp-prefixed, so the lexically-greatest run dir is
    the most recent. Returns ``None`` when no run exists for the target (no
    fabricated "sem registro" — absence is honest absence).
    """
    qa_dir = project_root / ".planning" / "qa" / target
    if not qa_dir.is_dir():
        return None
    run_dirs = sorted(
        (d for d in qa_dir.iterdir() if d.is_dir()),
        key=lambda d: d.name,
    )
    for run_dir in reversed(run_dirs):
        report = run_dir / "qa-report.json"
        if not report.is_file():
            continue
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
        verdict = data.get("verdict") if isinstance(data, dict) else None
        if verdict is not None:
            return str(verdict)
    return None


def _feature_git_block(
    project_root: Path, slug: str, status_value: str | None
) -> dict | None:
    """Git observation block for a feature, or ``None`` when not a git repo."""
    commits = _git_feature_commits(project_root, slug)
    if commits is None:
        return None
    # Drift: an in-flight feature already has committed work in git — the board
    # is lagging behind reality (signal, never an auto-advance — Tema 7 stays
    # closed).
    drift = bool(commits) and (status_value in _GIT_DRIFT_STATES)
    return {"feature_commits": commits, "drift": drift}


def _feature_reconcile_line(
    project_root: Path, slug: str, status_value: str | None
) -> str | None:
    """Human one-liner reconciling a feature with git + qa (read-only).

    Returns ``None`` when there is nothing to reconcile (no git repo and no qa
    verdict) so the board stays quiet on greenfield/no-qa features.
    """
    parts: list[str] = []
    git_block = _feature_git_block(project_root, slug, status_value)
    if git_block is not None and git_block["feature_commits"]:
        n = git_block["feature_commits"]
        if git_block["drift"]:
            parts.append(
                f"git: {n} commit(s) já no histórico — board atrás da realidade "
                f"(avance com forge implement/verify)"
            )
        else:
            parts.append(f"git: {n} commit(s)")
    verdict = _read_qa_verdict(project_root, slug)
    if verdict is not None:
        parts.append(f"qa: {verdict}")
    if not parts:
        return None
    return "  ·  ".join(parts)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _safe_read_yaml(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = read_yaml(path)
    except YamlIOError:
        return None
    return data if isinstance(data, dict) else None


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
