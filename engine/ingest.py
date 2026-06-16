"""`forge ingest` — hidden hook entry.

Routes hook signals into the right handler (graph delta, memory append,
inventory refresh, drift detection). Not advertised in `--help`, never
typed manually — see `docs/design/06-command-surface.md §Hidden internal
entrypoints`.

Argv shape (key/value pairs parsed by hand, NO argparse per decision 10):

    forge ingest --event post-edit --file path/to/x.kt
    forge ingest --event post-commit --sha abc123 --feature-slug auth
    forge ingest --event pre-commit --scope feature --slug auth
    forge ingest --event post-write-feature-artifact --feature-slug auth --artifact spec
    forge ingest --event session-start

Always exits 0 — hooks must not block git/edit. Errors are logged to stderr
as warnings but never propagate up.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from engine.cards.snapshotter import compute_directory_sha256
from engine.graph.incremental import remove_file as graph_remove_file
from engine.graph.incremental import update_file as graph_update_file
from engine.utils.paths import (
    cards_dir,
    claude_dir,
    find_project_root,
    forge_home,
    graph_db_path,
    memory_dir,
    try_find_project_root,
    workflow_config_path,
)
from engine.utils.sqlite_io import open_db, transaction
from engine.utils.yaml_io import read_yaml

_GRAPH_EXTENSIONS = {
    ".kt", ".kts", ".swift", ".ts", ".tsx", ".js", ".jsx",
    ".java", ".xml", ".m", ".mm",
}


def run(argv: list[str]) -> int:
    """Hidden hook entry. Always exits 0; logs warnings to stderr.

    `argv` is key/value pairs: `--key value --key2 value2 …`.
    """
    args = _parse_kv(argv)
    event = args.get("event")
    if not event:
        _warn("forge ingest: missing --event")
        return 0

    try:
        project_root = find_project_root()
    except Exception as exc:
        _warn(f"forge ingest: no project root ({exc})")
        return 0

    try:
        _route(event, args, project_root)
    except Exception as exc:
        _warn(f"forge ingest: handler '{event}' failed: {exc}")
    return 0


# ── Argv parsing (no argparse) ───────────────────────────────────────────────


def _parse_kv(argv: list[str]) -> dict[str, str]:
    """Parse `--key value --key2 value2` into a dict.

    Lone `--key` becomes `key=""` (boolean flag). Unknown shapes are
    silently dropped — hooks must never crash forge.
    """
    out: dict[str, str] = {}
    i = 0
    while i < len(argv):
        token = argv[i]
        if token.startswith("--"):
            key = token[2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                out[key] = argv[i + 1]
                i += 2
            else:
                out[key] = ""
                i += 1
        else:
            i += 1
    return out


# ── Router ───────────────────────────────────────────────────────────────────


def _route(event: str, args: dict[str, str], project_root: Path) -> None:
    handler = _ROUTES.get(event)
    if handler is None:
        return  # Unknown events ignored — forward-compat with new hooks.
    handler(args, project_root)


def _handle_post_edit(args: dict[str, str], project_root: Path) -> None:
    """Re-parse a single file into the graph DB."""
    file_arg = args.get("file")
    if not file_arg:
        return
    path = Path(file_arg)
    if not path.is_absolute():
        path = (project_root / path).resolve()
    if path.suffix.lower() not in _GRAPH_EXTENSIONS:
        return
    if not path.exists():
        graph_remove_file(project_root, path)
        return
    graph_update_file(project_root, path)


def _handle_post_commit(args: dict[str, str], project_root: Path) -> None:
    """Record a commit in feature_commits or task_commits."""
    sha = args.get("sha", "")
    if not sha:
        return
    feature_slug = args.get("feature-slug") or args.get("feature_slug")
    task_id = args.get("task-id") or args.get("task_id")
    files_touched = args.get("files-touched") or args.get("files_touched") or "0"
    try:
        files_count = int(files_touched)
    except ValueError:
        files_count = 0
    ts = datetime.now(timezone.utc).isoformat()

    conn = open_db(graph_db_path(project_root), create=True)
    try:
        with transaction(conn):
            # Garante parent row em `features` SEMPRE que conseguirmos um slug —
            # mesmo no branch task_id, porque o L1 costuma estar acompanhando a
            # feature em paralelo. Idempotente via INSERT OR IGNORE.
            if feature_slug:
                conn.execute(
                    "INSERT OR IGNORE INTO features(slug, status, created_at, last_activity) "
                    "VALUES (?, 'in-flight', ?, ?)",
                    (feature_slug, ts, ts),
                )

            if task_id:
                conn.execute(
                    "INSERT OR IGNORE INTO task_commits"
                    "(task_id, commit_sha, files_touched_count, timestamp) "
                    "VALUES (?, ?, ?, ?)",
                    (task_id, sha, files_count, ts),
                )
                # Quando temos AMBOS, registra também no feature_commits — facilita
                # correlação por slug em relatórios (doctor/progress).
                if feature_slug:
                    conn.execute(
                        "INSERT OR IGNORE INTO feature_commits"
                        "(feature_slug, commit_sha, files_touched_count, timestamp) "
                        "VALUES (?, ?, ?, ?)",
                        (feature_slug, sha, files_count, ts),
                    )
            elif feature_slug:
                conn.execute(
                    "INSERT OR IGNORE INTO feature_commits"
                    "(feature_slug, commit_sha, files_touched_count, timestamp) "
                    "VALUES (?, ?, ?, ?)",
                    (feature_slug, sha, files_count, ts),
                )
    finally:
        conn.close()


def _handle_pre_commit(args: dict[str, str], project_root: Path) -> None:
    """Run validators of the given scope via `engine.verify.run_scope`.

    Resolução de escopo em cascata:
      1. Args explícitos do hook (``--scope task --task-id ...`` ou ``--slug``).
      2. Parse da branch atual (``feature/<slug>`` → ``<slug>``).
      3. Varredura de L1 — primeira feature em ``implementing``/``verifying``.

    Quando há slug mas o L1 indica ``phase_lock`` apontando para ``TASK-...``,
    o escopo automaticamente vira ``task`` (mais granular). Nunca bloqueia o
    commit — exit-code != 0 apenas vira warning no stderr.
    """
    marker = memory_dir(project_root) / ".last-pre-commit-ingest"
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        marker.write_text(
            datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8"
        )
    except OSError as exc:
        _warn(f"pre-commit marker failed: {exc}")

    # 1) Args explícitos (caminho preferido).
    scope = args.get("scope") or "task"
    task_id = args.get("task-id") or args.get("task_id")
    slug = (
        args.get("slug")
        or args.get("feature-slug")
        or args.get("feature_slug")
    )

    # 2) Fallback: parsear branch atual (`feature/<slug>` → `<slug>`).
    if not slug and not task_id:
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(project_root),
                text=True,
                timeout=5,
            ).strip()
            if "/" in branch:
                # Segmenta por "/": `feature/lembrete-rega/foo` → `lembrete-rega`.
                slug = branch.split("/", 1)[1].split("/")[0] or None
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
            pass

    # 3) Fallback final: ler L1 procurando feature ativa.
    if not slug and not task_id:
        try:
            from engine.memory.l1 import list_active_features, read_l1_status

            for active in list_active_features(project_root):
                state = read_l1_status(active, project_root)
                if state and state.status in ("implementing", "verifying"):
                    slug = active
                    break
        except Exception as exc:  # pragma: no cover - L1 ausente / corrompido
            _warn(f"pre-commit L1 lookup failed: {exc}")

    # Sem escopo identificável: silêncio (genuinamente nada a verificar).
    if not slug and not task_id:
        return

    # Se temos slug mas sem task_id, tenta promover a task via phase_lock do L1.
    if slug and not task_id:
        try:
            from engine.memory.l1 import read_l1_status

            state = read_l1_status(slug, project_root)
            if state and state.phase_lock and state.phase_lock.startswith("TASK-"):
                task_id = state.phase_lock
        except Exception:  # pragma: no cover - defensivo
            pass

    scope_type = "task" if task_id else "feature"
    scope_id = task_id or slug

    try:
        from engine import verify  # local import — keep ingest light when verify is unused

        code = verify.run_scope(
            scope_type=scope_type,
            scope_id=scope_id,
            project_root=project_root,
            interactive=False,
        )
    except Exception as exc:  # pragma: no cover - hooks must not crash
        _warn(f"pre-commit verify dispatch failed: {exc}")
        return
    if code != 0:
        _warn(
            f"forge: pre-commit verify {scope_type}={scope_id} reported issues "
            f"(exit={code}) — commit will proceed but flag risk"
        )


def _handle_post_write_artifact(args: dict[str, str], project_root: Path) -> None:
    """L1 history append + targeted graph incremental update for the artifact."""
    feature_slug = args.get("feature-slug") or args.get("feature_slug")
    artifact = args.get("artifact", "?")
    file_arg = args.get("file")
    if feature_slug:
        history = memory_dir(project_root) / "L1" / feature_slug / "history.jsonl"
        history.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "artifact-written",
            "artifact": artifact,
            "file": file_arg,
        }
        try:
            with history.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            _warn(f"history append failed: {exc}")
    if file_arg:
        path = Path(file_arg)
        if not path.is_absolute():
            path = (project_root / path).resolve()
        if path.suffix.lower() in _GRAPH_EXTENSIONS and path.exists():
            graph_update_file(project_root, path)


def _handle_session_start(args: dict[str, str], project_root: Path) -> None:
    """Drift check — snapshot sha256 vs canonical workflow-config card list."""
    cfg_path = workflow_config_path(project_root)
    if not cfg_path.is_file():
        return
    try:
        cfg = read_yaml(cfg_path) or {}
    except Exception:
        return
    drifted: list[str] = []
    for entry in (cfg.get("cards") or {}).get("active") or []:
        name = entry.get("name")
        expected = entry.get("sha256")
        if not name or not expected:
            continue
        snap = cards_dir(project_root) / name
        if not snap.is_dir():
            drifted.append(f"{name}: snapshot missing")
            continue
        actual = compute_directory_sha256(snap)
        if actual != expected:
            drifted.append(f"{name}: sha256 drift")
    if drifted:
        _warn(
            "session-start drift detected (run `forge doctor`): "
            + "; ".join(drifted[:5])
            + (f" …(+{len(drifted) - 5})" if len(drifted) > 5 else "")
        )


# ── New handlers (Phase 5) ───────────────────────────────────────────────────


_SUBAGENT_VALIDATOR_MAP: dict[str, list[str]] = {
    "feature-intake": ["validate_feature_package"],
    "feature-prd": ["validate_feature_package"],
    "screen-analysis": ["validate_screen_analysis"],
    "contract-planner": ["validate_data_contract", "validate_backend_e2e"],
    "tech-spec": ["validate_feature_package"],
    "task-contract-writer": ["validate_task_contract"],
    "readiness-reviewer": ["validate_readiness"],
}


def _handle_post_subagent_validate(args: dict[str, str], project_root: Path) -> None:
    """Run a subset of validators after a sub-agent (Claude Code Task) finishes.

    Args (via kv):
        --subagent <type>   e.g. ``feature-intake``, ``contract-planner``.
        --task-id TASK-NNNN (optional; forwarded to per-task validators).

    Never blocks — validator failures are logged to stderr only.
    """
    subagent = args.get("subagent", "unknown")
    task_id = args.get("task-id") or args.get("task_id")

    validators_to_run = _SUBAGENT_VALIDATOR_MAP.get(subagent, [])
    if not validators_to_run:
        return

    validators_root = forge_home() / "validators"
    for v_name in validators_to_run:
        v_path = validators_root / f"{v_name}.py"
        if not v_path.is_file():
            continue
        cmd = [
            sys.executable,
            str(v_path),
            "--project-root",
            str(project_root),
        ]
        if task_id:
            cmd.extend(["--id", task_id])
        try:
            subprocess.run(cmd, capture_output=True, timeout=30, check=False)
        except subprocess.TimeoutExpired:
            _warn(f"forge ingest: validator {v_name} timed out")
        except OSError as exc:  # pragma: no cover - defensive
            _warn(f"forge ingest: validator {v_name} failed to launch ({exc})")


def _handle_pre_push(args: dict[str, str], project_root: Path) -> None:
    """Quick doctor pass before `git push`. Warnings only — never blocks.

    Falls back silently when the doctor quick API is not available.
    """
    try:
        from engine import doctor

        quick = getattr(doctor, "_run_quick_check", None) or getattr(
            doctor, "run_quick_check", None
        )
        if quick is None:
            return
        result = quick(project_root)
    except Exception as exc:  # pragma: no cover - doctor must not block push
        _warn(f"forge ingest pre-push: doctor unavailable ({exc})")
        return

    if isinstance(result, dict) and result.get("status") not in (None, "ok", "pass"):
        summary = result.get("summary") or result.get("message") or "warnings detected"
        _warn(f"forge: pre-push doctor quick — {summary}")


_CI_VALIDATORS = (
    "validate_feature_package",
    "validate_readiness",
    "check_no_invented_behavior",
    "check_files_in_allowed_files",
)


def _handle_ci_pr_ingest(args: dict[str, str], project_root: Path) -> None:
    """CI workflow ingest — write `.claude/.ci-report.md` for PR comments.

    Args:
        --slug <feature-slug>   feature being reviewed (derived from branch).
        --pr-number <n>         GitHub PR number.

    Runs the canonical PR-time validators and emits a markdown summary table.
    """
    # Aceita várias formas de slug enviadas por hooks/CI (ci-pr-ingest.yml usa
    # --feature-slug; outros chamadores podem usar --slug ou --feature_slug).
    slug = (
        args.get("feature-slug")
        or args.get("feature_slug")
        or args.get("slug")
        or "unknown"
    )
    pr_number = args.get("pr-number") or args.get("pr_number") or "?"

    validators_root = forge_home() / "validators"
    reports: list[tuple[str, dict]] = []
    for v_name in _CI_VALIDATORS:
        v_path = validators_root / f"{v_name}.py"
        if not v_path.is_file():
            reports.append((v_name, {"status": "fail", "message": "validator missing"}))
            continue
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(v_path),
                    "--project-root",
                    str(project_root),
                    "--id",
                    slug,
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            tail = (proc.stdout or "").strip().split("\n")[-1] if proc.stdout else "{}"
            try:
                data = json.loads(tail)
            except json.JSONDecodeError:
                data = {"status": "fail", "message": "validator output unparseable"}
            reports.append((v_name, data))
        except subprocess.TimeoutExpired:
            reports.append((v_name, {"status": "fail", "message": "timed out"}))

    emoji = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
    lines = [
        f"## feature-forge — PR #{pr_number} ({slug})",
        "",
        "| Validator | Status | Message |",
        "|---|---|---|",
    ]
    for name, data in reports:
        status = str(data.get("status", "?"))
        message = str(data.get("message", ""))[:80]
        lines.append(f"| `{name}` | {emoji.get(status, '❓')} {status} | {message} |")

    report_path = claude_dir(project_root) / ".ci-report.md"
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        _warn(f"forge ingest ci-pr-ingest: report write failed ({exc})")


# ── Route table ──────────────────────────────────────────────────────────────


_ROUTES = {
    "post-edit": _handle_post_edit,
    "post-commit": _handle_post_commit,
    "pre-commit": _handle_pre_commit,
    "post-write-feature-artifact": _handle_post_write_artifact,
    "session-start": _handle_session_start,
    "post-subagent-validate": _handle_post_subagent_validate,
    "pre-push": _handle_pre_push,
    "ci-pr-ingest": _handle_ci_pr_ingest,
}


# ── Logging ──────────────────────────────────────────────────────────────────


def _warn(msg: str) -> None:
    """Hooks must never block, so warnings go to stderr — never raise."""
    try:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
    except OSError:
        pass


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run(sys.argv[1:]))
