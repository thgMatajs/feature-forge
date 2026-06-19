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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from engine.memory.l1 import (
    _VALID_STATES,
    L1State,
    append_history,
    current_subtype,
    list_active_features,
    read_history,
    read_l1_status,
    write_l1_status,
)
from engine.memory.l2 import remove_entry as l2_remove_entry
from engine.ui import question, renderer
from engine.ui.exit_codes import ERR_PROJECT_NOT_FOUND, fail_with_tag
from engine.ui.question import PromptAbortedError
from engine.utils.paths import (
    ProjectRootNotFoundError,
    active_config_path,
    claude_dir,
    ensure_dir,
    feature_path,
    find_project_root,
    memory_l2_path,
)
from engine.utils.yaml_io import YamlIOError, read_yaml_or_default, write_yaml
from engine.utils.checkpoint_io import (
    clear_checkpoint as _clear_checkpoint_io,
    load_yaml_checkpoint as _load_yaml_checkpoint_io,
    save_yaml_checkpoint as _save_yaml_checkpoint_io,
)
from engine.utils.iso import utc_now_iso as _utc_now_iso_shared

_HISTORY_FILE_NAME = "workflow-config-history.jsonl"
_UNDO_SLUG = "_undo"


def _delete_feature_artifacts_guard(project_root: Path, target: Path) -> None:
    """H-06: refuse rmtree on paths outside the project tree.

    Resolves both `project_root` and `target` then verifies containment.
    Raises `ValueError` if `target` is not inside `project_root` after
    resolution — protects against `../../etc`-style slugs that survive
    `feature_dir()`.
    """
    project_resolved = project_root.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(project_resolved)
    except ValueError as exc:
        raise ValueError(
            f"Refusing to delete path outside project: {target_resolved}"
        ) from exc
    # A-001 (master review PR #15): `Path.relative_to` returns `Path('.')`
    # when target == project — i.e. it does NOT raise ValueError on equality.
    # A malicious slug like `../../..` could resolve to the project root and
    # slip past the containment check above, then `shutil.rmtree(project_root)`
    # would obliterate the entire project after the 2 confirms. Reject equality.
    if target_resolved == project_resolved:
        raise ValueError("Refusing to delete project root")


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp — thin shim sobre ``engine.utils.iso``."""
    return _utc_now_iso_shared()


# ── Checkpoint (DRIFT-1 W2.T3b — intent-resume, outcome C) ───────────────────
#
# Per the T3a audit (.planning/drift-1/checkpoint-audit.json,
# action="add-new", reuse_path="init-pattern"), undo ganha o segundo
# maior surface (16 callsites): menu ask, confirms multiplos em
# init/reconfigure/task-commit/evolve/delete-feature, ask_text em
# evolve-id/abort-reason. Mirrors ``_InitCheckpoint``
# (engine/init.py:100-108) — outcome C, sem import de
# ``engine.qa.checkpoint`` (Decision 22).
#
# Multi-prompt flow: undo tem fluxos onde N prompts encadeiam (ex.: init
# pede 3 confirms; delete-feature pede 2). Capturamos ``confirm_level``
# pra audit, mas o intent-id de cada confirm individual e calculado
# dentro do proprio ``question.confirm`` — re-invocacao consome a
# response correta pelo intent-id, nao pelo step. O step + extras
# servem pra forensics e pra que o host saiba em qual sub-prompt o
# fluxo estava.
#
# Refs:
#   - docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
#   - engine/init.py:100-108 (canonical template)


@dataclass
class _UndoCheckpoint:
    """State serialized before each ``question.ask*`` call in ``undo.run``.

    Carries ``target_kind`` (menu choice 1..7/c), ``feature_slug`` (when
    aplicavel), ``confirm_level`` (qual confirm da cadeia foi atingido
    no fluxo multi-prompt — ex.: ``confirm-1`` na 1ª confirmacao de
    ``delete-feature``).
    """

    step: str
    at: str
    project_root: str
    intent_id: str | None = None
    target_kind: str | None = None
    feature_slug: str | None = None
    confirm_level: str | None = None


def _undo_checkpoint_path(project_root: Path) -> Path:
    return claude_dir(project_root) / ".undo-checkpoint.yaml"


# Os 3 helpers abaixo são thin shims sobre ``engine.utils.checkpoint_io`` —
# consolidação dos 30 duplicates apontados pelo finding #5 do master review
# do PR #11. Os nomes ``_save_undo_checkpoint`` etc. permanecem como API
# privada do módulo para preservar os contracts dos testes em
# ``tests/unit/test_engine_undo_resume.py`` (Mandamento #2 — verde).


def _save_undo_checkpoint(cp: _UndoCheckpoint) -> None:
    """Persist the undo checkpoint atomically."""
    _save_yaml_checkpoint_io(
        _undo_checkpoint_path(Path(cp.project_root)),
        {
            "schema-version": 1,
            "step": cp.step,
            "at": cp.at,
            "project-root": cp.project_root,
            "intent-id": cp.intent_id,
            "target-kind": cp.target_kind,
            "feature-slug": cp.feature_slug,
            "confirm-level": cp.confirm_level,
        },
    )


def _load_undo_checkpoint(project_root: Path) -> dict[str, Any] | None:
    """Read the undo checkpoint, returning ``None`` when absent."""
    return _load_yaml_checkpoint_io(_undo_checkpoint_path(project_root))


def _clear_undo_checkpoint(project_root: Path) -> None:
    """Remove the checkpoint — best-effort; silent on OSError (idempotent)."""
    _clear_checkpoint_io(_undo_checkpoint_path(project_root))


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
    cfg_path = active_config_path(project_root)
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
    except (KeyError, OSError, YamlIOError, MemoryError) as exc:
        # A-012 (master review PR #15): narrow do broad-except residual no scrub
        # H-03. `l2_remove_entry` chama `read_l2`/`write_l2` (raise YamlIOError
        # via yaml_io, MemoryError via schema check, OSError via filesystem).
        # KeyError defensivo se entry layout mudar; bugs reais de schema agora
        # propagam em vez de virarem warning amarelo.
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
        # C-50 (PR22-B-03): guard de tipo — `state.raw` pode não ser dict
        # (status.json corrompido / shape inesperado) antes da mutação por chave.
        if not isinstance(state.raw, dict):
            state.raw = {}
        # ABORTED-DEADEND (W-DEBT): preserva o status pré-abort no raw ANTES do
        # overwrite, pra que `_undo_abort` possa restaurar de forma determinística
        # (sem reconstruir do history.jsonl). No branch `state is None` não há
        # status prévio — `_undo_abort` defaulta `deferred`.
        #
        # C-48 (PR22-R-006): só grava `pre-abort-status` se o estado atual NÃO é
        # já 'aborted'. Um double-abort (abortar uma feature já aborted)
        # sobrescrevia pre-abort-status com 'aborted' — envenenava o guard WR-01
        # de `_undo_abort` (o un-abort restauraria pra 'aborted', dead-end). Ao
        # pular a gravação no double-abort, o pre-abort-status original (o estado
        # real pré-1º-abort) é preservado.
        if state.status != "aborted":
            state.raw["pre-abort-status"] = state.status
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


def _undo_abort(project_root: Path, feature_slug: str) -> bool:
    """ABORTED-DEADEND recovery — restaura uma feature de 'aborted'.

    Restaura `status` a partir de `raw["pre-abort-status"]` (default `deferred`
    quando ausente — feature abortada por engine antigo). Limpa os markers
    `pre-abort-status`/`aborted-reason` e loga no undo-log. NÃO-destrutivo
    (só re-escreve o status), então confirm simples — não o 2-step do git revert.

    WR-01 (holistic review W-DEBT, T1×T3): valida `pre-abort-status` contra
    `_VALID_STATES` ANTES de restaurar. Um valor ausente OU não-membro do enum
    (abort legado, OR um estado removido por uma wave futura — exatamente o que
    T1 acabou de fazer com `verified`/`paused`) cai pro default seguro `deferred`
    com aviso mentor-calmo, em vez de propagar o `MemoryError` cru de
    `write_l1_status` como traceback no dispatch.
    """
    state = read_l1_status(feature_slug, project_root)
    if state is None or state.status != "aborted":
        renderer.write(renderer.colored(
            f"  Feature {feature_slug} não está em 'aborted' — nada a reverter.",
            "yellow",
        ))
        return False
    # C-50 (PR22-B-03): guard de tipo antes de `.get`/`.pop` — `state.raw`
    # corrompido (não-dict) estouraria AttributeError no recovery.
    if not isinstance(state.raw, dict):
        state.raw = {}
    raw_prior = state.raw.get("pre-abort-status") or "deferred"
    if raw_prior in _VALID_STATES:
        prior = raw_prior
    else:
        renderer.write(renderer.colored(
            f"  pre-abort-status '{raw_prior}' não é um estado válido "
            f"(provável abort legado ou estado removido) — restaurando para "
            f"'deferred', o estado seguro auto-resumável.",
            "yellow",
        ))
        prior = "deferred"
    if not question.confirm(
        f"Restaurar {feature_slug} de 'aborted' para '{prior}'?", default=False
    ):
        return False
    state.status = prior
    state.last_action_kind = "un-aborted"
    state.last_action_at = _utc_now_iso()
    state.raw.pop("pre-abort-status", None)
    state.raw.pop("aborted-reason", None)
    write_l1_status(state, project_root)
    _append_undo_log(
        project_root,
        kind="undo",
        target=f"un-abort:{feature_slug}",
        reverted_at=_utc_now_iso(),
        slug=feature_slug,
        extras={"restored-to": prior},
    )
    renderer.write(renderer.colored(
        f"  ✓ feature {feature_slug} restaurada para '{prior}'.", "green"
    ))
    return True


def _delete_feature_artifacts(project_root: Path, feature_slug: str) -> bool:
    # A-002 (master review PR #15): use `feature_path` honoring subtype so
    # non-product features (refactor/spike/chore/bugfix) — which live under
    # `non-product/{slug}/` per filesystem-layout §3.5 — are actually
    # deletable. The old `feature_dir(...)` always pointed to the product
    # folder, leaving non-product artifacts orphaned after `forge undo`.
    subtype = current_subtype(feature_slug, project_root)
    fpath = feature_path(project_root, feature_slug, subtype=subtype)

    # MD-02 (final review 2026-06-15): path-traversal guard runs FIRST,
    # before any branch that could leak the resolved path to the user
    # (existence message, "Vai apagar {fpath}" warning, confirm prompts).
    # If `fpath` escapes `project_root`, the guard raises and we never
    # disclose the resolved path in error messages.
    _delete_feature_artifacts_guard(project_root, fpath)

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
    except (OSError, ValueError) as exc:
        # A-011 (master review PR #15): narrow do broad-except residual no scrub
        # H-03. `append_history` faz JSONL append — OSError (filesystem, lock,
        # permissions); ValueError defensivo se payload virar não-serializável.
        # History append failure agora é visível ao usuário em vez de silenciosa
        # (auditabilidade do undo). Não propaga: undo principal já sucedeu.
        renderer.write(renderer.dim(
            f"  (aviso) append undo-log falhou — {exc}"
        ))


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
        # C3 EXIT-2-COLLISION (BL-01 do review W2): este site retornava `2`
        # puro — colidia com EXIT_PAUSED e o host lia como paused-for-input,
        # procurando um pending que nunca foi escrito (hang). Colapsa em
        # exit 1 + tag machine-readable, como os demais handlers.
        return fail_with_tag(ERR_PROJECT_NOT_FOUND, f"forge undo: {exc}")

    renderer.write(renderer.bold("forge undo — escolha:"))
    options = {
        "1": "last — última ação reversível (default)",
        "2": "reconfigure — reverter último reconfigure",
        "3": "task commit — reverter commit (git revert)",
        "4": "evolve apply — reverter aplicação L2",
        "5": "abort feature — marcar feature como aborted (terminal)",
        "6": "delete feature artifacts — apagar pasta (irreversível)",
        "7": "init — apagar .claude/ inteira (raríssimo)",
        "8": "un-abort feature — reverter abort, restaura o status anterior",
        "c": "cancelar",
    }

    # DRIFT-1 W2.T3b — persist checkpoint with the deterministic intent-id
    # for the menu ask BEFORE invoking ``question.ask``. On exit-2 +
    # re-invoke, ``question.ask`` finds the matching forge-response.json
    # and returns the value without re-prompting. Outcome C — per-subcommand
    # dataclass, no import from ``engine.qa.checkpoint``.
    _save_undo_checkpoint(
        _UndoCheckpoint(
            step="step-menu",
            at=_utc_now_iso(),
            project_root=str(project_root),
            intent_id=question.stable_intent_id(
                "ask",
                "O que deseja reverter?",
                options,
                extra={
                    "default": "1",
                    "min-selected": None,
                    "validator-hint": None,
                },
            ),
            target_kind=None,
        )
    )

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
        # DRIFT-1 W2.T3b — clear intent-resume checkpoint on clean completion.
        _clear_undo_checkpoint(project_root)
        return 0

    # DRIFT-1 W2.T3b — atualiza checkpoint pra refletir o target escolhido
    # ANTES de invocar o branch. Prompts internos (confirms multi-step,
    # ask_text de motivo/id) herdam intent-resume via question.ask* —
    # cada um calcula seu proprio intent-id deterministico.
    _save_undo_checkpoint(
        _UndoCheckpoint(
            step=f"step-target:{choice}",
            at=_utc_now_iso(),
            project_root=str(project_root),
            intent_id=None,
            target_kind=choice,
        )
    )

    try:
        if choice == "1":
            target = _resolve_last(project_root)
            if target is None:
                _clear_undo_checkpoint(project_root)
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
            _clear_undo_checkpoint(project_root)
            return 0 if ok else 1

        if choice == "2":
            rc = 0 if _undo_reconfigure(project_root) else 1
            _clear_undo_checkpoint(project_root)
            return rc

        if choice == "3":
            slug = _pick_feature(project_root, "Qual feature?")
            if slug is None:
                _clear_undo_checkpoint(project_root)
                return 0
            rc = 0 if _undo_task_commit(project_root, slug) else 1
            _clear_undo_checkpoint(project_root)
            return rc

        if choice == "4":
            pid = question.ask_text("ID da proposta (ex.: P-001):")
            rc = 0 if _undo_evolve(project_root, pid) else 1
            _clear_undo_checkpoint(project_root)
            return rc

        if choice == "5":
            slug = _pick_feature(project_root, "Qual feature abortar?")
            if slug is None:
                _clear_undo_checkpoint(project_root)
                return 0
            reason = question.ask_text("Motivo do abort:")
            if not question.confirm(
                f"Confirma marcar {slug} como aborted?", default=False
            ):
                _clear_undo_checkpoint(project_root)
                return 0
            rc = 0 if _abort_feature(project_root, slug, reason) else 1
            _clear_undo_checkpoint(project_root)
            return rc

        if choice == "6":
            slug = _pick_feature(project_root, "Qual feature apagar?")
            if slug is None:
                _clear_undo_checkpoint(project_root)
                return 0
            rc = 0 if _delete_feature_artifacts(project_root, slug) else 1
            _clear_undo_checkpoint(project_root)
            return rc

        if choice == "7":
            rc = 0 if _undo_init(project_root) else 1
            _clear_undo_checkpoint(project_root)
            return rc

        if choice == "8":
            slug = _pick_feature(project_root, "Qual feature reverter o abort?")
            if slug is None:
                _clear_undo_checkpoint(project_root)
                return 0
            rc = 0 if _undo_abort(project_root, slug) else 1
            _clear_undo_checkpoint(project_root)
            return rc

    except PromptAbortedError:
        renderer.write("  pausado.")
        _clear_undo_checkpoint(project_root)
        return 130

    _clear_undo_checkpoint(project_root)
    return 0


__all__ = ["run"]
