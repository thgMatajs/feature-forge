"""`forge undo` — revert the last state-mutating action via interactive menu.

`last` is the default option of the menu, **not** a CLI suffix (decision
9 / `06-command-surface.md`). Six paths exist:

  1. last                    — best-effort reversal of the latest mutation
  2. reconfigure {date}      — restore `workflow-config.yaml` from `.bak`
  3. task commit (per feat)  — `git revert <sha>` after dual confirmation
  4. evolve apply (per id)   — restore L2 backup and drop the entry
  5. abort feature           — mark feature `aborted` (terminal)
  6. delete feature artifacts — `rm -rf {feature_dir}` after dual confirmation

Every reversal appends a `{kind: 'undo', target, ...}` event to the
matching feature's `history.jsonl` (or a synthetic `_undo` slug when the
target has no feature scope).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from engine.memory.l1 import (
    L1State,
    append_history,
    list_active_features,
    read_history,
    read_l1_status,
    write_l1_status,
)
from engine.memory.l2 import remove_entry as l2_remove_entry
from engine.ui import question, renderer
from engine.ui.question import PromptAbortedError
from engine.utils.paths import (
    ProjectRootNotFoundError,
    claude_dir,
    feature_dir,
    find_project_root,
    memory_l2_path,
    workflow_config_path,
)
from engine.utils.yaml_io import read_yaml_or_default

_HISTORY_FILE_NAME = "workflow-config-history.jsonl"
_UNDO_SLUG = "_undo"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Candidate detection ─────────────────────────────────────────────────────


def _last_reconfigure_entry(project_root: Path) -> Optional[dict[str, Any]]:
    path = claude_dir(project_root) / _HISTORY_FILE_NAME
    if not path.exists():
        return None
    last: Optional[dict[str, Any]] = None
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return None
    return last


def _last_task_commit(
    project_root: Path,
    feature_slug: str,
) -> Optional[dict[str, Any]]:
    """Return the most recent task-commit history entry for a feature.

    Canonical schema (v1) for a ``task-commit`` history entry, written by
    `engine.ingest` and consumed here:

        {
            "kind":       "task-commit",
            "task_id":    "TASK-NNNN",
            "commit_sha": "<40-char-hex-sha1>",
            "at":         "<ISO8601 UTC>",
            "by":         "forge implement",
            "branch":     "<git-branch-name>"
        }

    Legacy entries that used ``commit-sha`` (dash-form), ``sha``, or
    ``task-id`` keys are still recognised — `_pick_commit_sha` and
    `_pick_task_id` apply a graceful fallback and the caller emits a
    warning when the legacy shape is taken.
    """
    history = read_history(feature_slug, project_root, tail=0)
    for entry in reversed(history):
        if entry.get("kind") in {"task-commit", "commit", "task-committed"}:
            return entry
    return None


def _pick_commit_sha(entry: dict[str, Any]) -> tuple[str, bool]:
    """Extract the commit sha from a history entry, returning (sha, is_legacy).

    Canonical key is ``commit_sha``. Legacy fallbacks: ``commit-sha``, ``sha``.
    """
    sha = str(entry.get("commit_sha") or "")
    if sha:
        return sha, False
    legacy = str(entry.get("commit-sha") or entry.get("sha") or "")
    return legacy, bool(legacy)


def _pick_task_id(entry: dict[str, Any]) -> str:
    """Extract the task id from a history entry (canonical or legacy)."""
    return str(entry.get("task_id") or entry.get("task-id") or "")


def _last_evolve_apply(project_root: Path) -> Optional[dict[str, Any]]:
    history = read_history("_evolve", project_root, tail=0)
    for entry in reversed(history):
        if entry.get("kind") == "evolve-apply":
            return entry
    return None


# ── Reversal implementations ────────────────────────────────────────────────


def _undo_reconfigure(project_root: Path) -> bool:
    cfg_path = workflow_config_path(project_root)
    bak = cfg_path.with_suffix(cfg_path.suffix + ".bak")
    if not bak.exists():
        renderer.write(renderer.colored(
            "  Sem .bak de workflow-config.yaml — nada a reverter.", "yellow"
        ))
        return False

    renderer.write(f"  alvo: {cfg_path}")
    renderer.write(f"  backup: {bak}")
    if not question.confirm(
        "Restaurar workflow-config.yaml a partir do .bak?", default=False
    ):
        return False

    shutil.copy2(bak, cfg_path)
    renderer.write(renderer.colored(
        "  ✓ workflow-config.yaml restaurado.", "green"
    ))
    _append_undo_log(
        project_root,
        kind="undo",
        target="reconfigure",
        reverted_at=_utc_now_iso(),
        slug=_UNDO_SLUG,
    )
    return True


def _undo_task_commit(project_root: Path, feature_slug: str) -> bool:
    entry = _last_task_commit(project_root, feature_slug)
    if not entry:
        renderer.write(renderer.colored(
            f"  Sem commits registrados para {feature_slug}.", "yellow"
        ))
        return False
    sha, is_legacy = _pick_commit_sha(entry)
    if not sha:
        renderer.write(renderer.colored(
            "  Último commit não tem SHA — impossível reverter via git.", "yellow"
        ))
        return False
    if is_legacy:
        renderer.write(renderer.colored(
            "  ⚠ entry com schema legado (commit-sha/sha) — interpretado, "
            "mas próximos commits vão usar `commit_sha`.",
            "yellow",
        ))

    task_id = _pick_task_id(entry)
    renderer.write(f"  feature: {feature_slug}")
    if task_id:
        renderer.write(f"  task:    {task_id}")
    renderer.write(f"  commit:  {sha}")

    if not question.confirm(
        f"Confirma reverter o commit {sha[:10]}? (1ª confirmação)",
        default=False,
    ):
        return False
    if not question.confirm(
        "Tem certeza? `git revert` cria um novo commit. (2ª confirmação)",
        default=False,
    ):
        return False

    try:
        subprocess.run(
            ["git", "revert", "--no-edit", sha],
            cwd=str(project_root),
            check=True,
        )
    except FileNotFoundError:
        renderer.write(renderer.colored(
            "  git não está disponível neste ambiente.", "yellow"
        ))
        return False
    except subprocess.CalledProcessError as exc:
        renderer.write(renderer.colored(
            f"  git revert falhou ({exc.returncode}).", "yellow"
        ))
        return False

    renderer.write(renderer.colored(
        f"  ✓ commit {sha[:10]} revertido.", "green"
    ))
    _append_undo_log(
        project_root,
        kind="undo",
        target=f"task-commit:{sha}",
        reverted_at=_utc_now_iso(),
        slug=feature_slug,
    )
    return True


def _undo_evolve(project_root: Path, proposal_id: str) -> bool:
    l2_path = memory_l2_path(project_root)
    bak = l2_path.with_suffix(l2_path.suffix + ".bak")
    if not l2_path.exists():
        renderer.write(renderer.colored("  L2 não existe.", "yellow"))
        return False

    renderer.write(f"  proposal: {proposal_id}")
    renderer.write(f"  L2:       {l2_path}")
    if bak.exists():
        renderer.write(f"  backup:   {bak} (será usado pra restaurar)")

    if not question.confirm(
        f"Reverter aplicação de {proposal_id}?", default=False
    ):
        return False

    target_id = proposal_id.replace("P-", "L2-") if proposal_id.startswith("P-") else proposal_id
    try:
        l2_remove_entry(project_root, target_id)
    except Exception as exc:
        renderer.write(renderer.colored(
            f"  remoção da entrada falhou — {exc}", "yellow"
        ))

    if bak.exists() and question.confirm(
        "Restaurar L2 inteiro a partir do .bak (sobrescreve mudanças "
        "posteriores)?",
        default=False,
    ):
        shutil.copy2(bak, l2_path)
        renderer.write(renderer.colored("  ✓ L2 restaurado do .bak.", "green"))
    else:
        renderer.write(renderer.colored(
            f"  ✓ entrada {target_id} removida.", "green"
        ))

    _append_undo_log(
        project_root,
        kind="undo",
        target=f"evolve-apply:{proposal_id}",
        reverted_at=_utc_now_iso(),
        slug="_evolve",
    )
    return True


def _undo_init(project_root: Path) -> bool:
    cdir = claude_dir(project_root)
    if not cdir.exists():
        renderer.write(renderer.colored("  .claude/ não existe.", "yellow"))
        return False

    renderer.write(renderer.colored(
        "  ⚠ Reverter init apaga TODA a configuração local em .claude/.",
        "yellow",
    ))
    renderer.write(f"  alvo: {cdir}")

    if not question.confirm("Apagar .claude/? (1ª)", default=False):
        return False
    if not question.confirm("Confirma — não dá pra desfazer. (2ª)", default=False):
        return False
    if not question.confirm("Última chance. (3ª)", default=False):
        return False

    shutil.rmtree(cdir)
    renderer.write(renderer.colored("  ✓ .claude/ apagada.", "green"))
    return True


def _abort_feature(project_root: Path, feature_slug: str, reason: str) -> bool:
    state = read_l1_status(feature_slug, project_root)
    if state is None:
        state = L1State(
            feature_slug=feature_slug,
            status="aborted",
            last_action_at=_utc_now_iso(),
            last_action_kind="aborted",
            phase_lock=None,
        )
    else:
        state.status = "aborted"
        state.last_action_kind = "aborted"
        state.last_action_at = _utc_now_iso()
        state.phase_lock = None
        state.raw["aborted-reason"] = reason

    write_l1_status(state, project_root)
    _append_undo_log(
        project_root,
        kind="undo",
        target=f"abort-feature:{feature_slug}",
        reverted_at=_utc_now_iso(),
        slug=feature_slug,
        extras={"aborted-reason": reason},
    )
    renderer.write(renderer.colored(
        f"  ✓ feature {feature_slug} marcada como aborted.", "green"
    ))
    return True


def _delete_feature_artifacts(project_root: Path, feature_slug: str) -> bool:
    fpath = feature_dir(project_root, feature_slug)
    if not fpath.exists():
        renderer.write(renderer.colored(
            f"  Nada em {fpath} pra apagar.", "yellow"
        ))
        return False

    renderer.write(renderer.colored(
        f"  ⚠ Vai apagar {fpath} (irreversível).", "yellow"
    ))
    if not question.confirm("Apagar pasta da feature? (1ª)", default=False):
        return False
    if not question.confirm("Confirma — perde tudo. (2ª)", default=False):
        return False

    shutil.rmtree(fpath)
    renderer.write(renderer.colored("  ✓ artefatos apagados.", "green"))
    _append_undo_log(
        project_root,
        kind="undo",
        target=f"delete-feature:{feature_slug}",
        reverted_at=_utc_now_iso(),
        slug=feature_slug,
    )
    return True


# ── Logging ─────────────────────────────────────────────────────────────────


def _append_undo_log(
    project_root: Path,
    *,
    kind: str,
    target: str,
    reverted_at: str,
    slug: str,
    extras: Optional[dict[str, Any]] = None,
) -> None:
    event: dict[str, Any] = {
        "kind": kind,
        "target": target,
        "reverted-at": reverted_at,
        "command": "undo",
    }
    if extras:
        event.update(extras)
    try:
        append_history(slug, project_root, event)
    except Exception:
        pass


# ── Menu plumbing ───────────────────────────────────────────────────────────


def _pick_feature(project_root: Path, prompt: str) -> Optional[str]:
    features = list_active_features(project_root)
    if not features:
        renderer.write(renderer.colored(
            "  Nenhuma feature ativa em .claude/memory/L1/.", "yellow"
        ))
        return None
    options = {str(i): slug for i, slug in enumerate(features, start=1)}
    options["c"] = "cancelar"
    choice = question.ask(prompt, options, default="1", allow_pause=True)
    if choice == "c":
        return None
    return options.get(choice)


def _resolve_last(project_root: Path) -> Optional[str]:
    """Best-effort guess of the most recent reversible action."""
    candidates: list[tuple[datetime, str]] = []

    rec = _last_reconfigure_entry(project_root)
    if rec and rec.get("timestamp"):
        try:
            ts = datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00"))
            candidates.append((ts, "reconfigure"))
        except ValueError:
            pass

    evol = _last_evolve_apply(project_root)
    if evol and evol.get("at"):
        try:
            ts = datetime.fromisoformat(evol["at"].replace("Z", "+00:00"))
            candidates.append((ts, "evolve"))
        except ValueError:
            pass

    for slug in list_active_features(project_root):
        entry = _last_task_commit(project_root, slug)
        if entry and entry.get("at"):
            try:
                ts = datetime.fromisoformat(entry["at"].replace("Z", "+00:00"))
                candidates.append((ts, f"task:{slug}"))
            except ValueError:
                pass

    if not candidates:
        renderer.write(renderer.colored(
            "  Não encontrei nada reversível recente.", "yellow"
        ))
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def run(argv: list[str]) -> int:
    """Interactive menu — `last` is the default, never a suffix."""
    _ = argv
    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        sys.stderr.write(f"forge undo: {exc}\n")
        return 2

    renderer.write(renderer.bold("forge undo — escolha:"))
    options = {
        "1": "last — última ação reversível (default)",
        "2": "reconfigure — reverter último reconfigure",
        "3": "task commit — reverter commit (git revert)",
        "4": "evolve apply — reverter aplicação L2",
        "5": "abort feature — marcar feature como aborted (terminal)",
        "6": "delete feature artifacts — apagar pasta (irreversível)",
        "7": "init — apagar .claude/ inteira (raríssimo)",
        "c": "cancelar",
    }
    try:
        choice = question.ask(
            "O que deseja reverter?",
            options,
            default="1",
            allow_pause=True,
        )
    except PromptAbortedError:
        renderer.write("  cancelado.")
        return 130

    if choice == "c":
        renderer.write("  cancelado.")
        return 0

    try:
        if choice == "1":
            target = _resolve_last(project_root)
            if target is None:
                return 0
            renderer.write(renderer.dim(f"  last → {target}"))
            if target == "reconfigure":
                ok = _undo_reconfigure(project_root)
            elif target == "evolve":
                pid = question.ask_text(
                    "ID da proposta para reverter (ex.: P-001):"
                )
                ok = _undo_evolve(project_root, pid)
            elif target.startswith("task:"):
                ok = _undo_task_commit(project_root, target.split(":", 1)[1])
            else:
                ok = False
            return 0 if ok else 1

        if choice == "2":
            return 0 if _undo_reconfigure(project_root) else 1

        if choice == "3":
            slug = _pick_feature(project_root, "Qual feature?")
            if slug is None:
                return 0
            return 0 if _undo_task_commit(project_root, slug) else 1

        if choice == "4":
            pid = question.ask_text("ID da proposta (ex.: P-001):")
            return 0 if _undo_evolve(project_root, pid) else 1

        if choice == "5":
            slug = _pick_feature(project_root, "Qual feature abortar?")
            if slug is None:
                return 0
            reason = question.ask_text("Motivo do abort:")
            if not question.confirm(
                f"Confirma marcar {slug} como aborted?", default=False
            ):
                return 0
            return 0 if _abort_feature(project_root, slug, reason) else 1

        if choice == "6":
            slug = _pick_feature(project_root, "Qual feature apagar?")
            if slug is None:
                return 0
            return 0 if _delete_feature_artifacts(project_root, slug) else 1

        if choice == "7":
            return 0 if _undo_init(project_root) else 1

    except PromptAbortedError:
        renderer.write("  pausado.")
        return 130

    return 0


__all__ = ["run"]
