"""`forge verify` — read-only validator cascade.

Resolves the verification scope (task / feature / inferred), discovers the
registered validators for that scope from `workflow-config.yaml` (re-resolved
against the snapshotted cards), and runs them sequentially with the cascade
policy documented in `docs/design/07-discipline.md §2`:

- `fail-fast: true` (default) — stop at the first hard fail.
- `fail-fast: false`           — collect every error before returning.

Cinematic output per `docs/ux/forge-verify-roteiro.md`:

    ├ validator-name                         ✓ 124ms
    ├ validator-name                         🛑 1.4s  FAIL
    └ validator-name                         — não rodado (cascade parou)

v1 realism: validators are shipped by individual cards in Phase 5+ — until
then, the registry can be empty. In that case `verify` reports "Nenhum
validator pra este scope" and exits 0. Once cards land their validator
scripts, this module dispatches each one as a subprocess (`python3 <path>`)
and parses the structured JSON tail of stdout to extract the three-paths
block on hard fail.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from engine._sandbox.env import build_safe_env
from engine.memory import MemoryError as MemoryStoreError  # WR-02: avoid shadowing the CPython builtin OOM `MemoryError` (engine.memory.MemoryError is a domain subclass of Exception, NOT BaseException).
from engine.memory.l1 import (
    L1State,
    list_active_features,
    read_l1_status,
    write_l1_status,
)
from engine.integrations.mem import mem_context_hint
from engine.persona import mentor_calmo
from engine.ui import output_mode, question, renderer
from engine.ui.exit_codes import ERR_PROJECT_NOT_FOUND, fail_with_tag
from engine.ui.question import PromptAbortedError
from engine.utils.paths import (
    ProjectRootNotFoundError,
    active_config_path,
    cards_dir,
    claude_dir,
    ensure_dir,
    find_project_root,
    lifecycle_root,
    memory_dir,
)
from engine.utils.yaml_io import read_yaml_or_default, write_yaml
from engine.utils.checkpoint_io import (
    clear_checkpoint as _clear_checkpoint_io,
    load_yaml_checkpoint as _load_yaml_checkpoint_io,
    save_yaml_checkpoint as _save_yaml_checkpoint_io,
)
from engine.utils.iso import utc_now_iso

_DEFAULT_RUNS_ON = "verify-task"


@dataclass
class _ValidatorSpec:
    """One validator pulled from the resolved cards.

    `script_path` is absolute. `severity` defaults to `warn` to keep the
    cascade conservative when a card forgets to declare it.
    """

    name: str
    script_path: Path
    severity: str = "warn"
    card_name: str = ""
    runs_on: list[str] = field(default_factory=list)


@dataclass
class _ValidatorResult:
    name: str
    status: str  # "pass" | "warn" | "fail" | "skipped" | "degraded"
    duration_ms: int = 0
    message: str = ""
    paths: list[dict[str, str]] = field(default_factory=list)
    what_failed: str = ""
    where: str = ""
    why: list[str] = field(default_factory=list)
    # BUG-VERIFY-2 (T3) — classe de cobertura de um PASS (vazio p/ não-pass):
    #   "substantive"  — examinou artefatos reais e aprovou
    #   "stub"         — stub/no-op que sempre passa
    #   "staged-blind" — passou porque nada estava no escopo (vacuous)
    #   "opaque"       — pass via exit-code (sem JSON): substância indeterminável
    # Validators declaram via `coverage` no JSON tail; legados (sem JSON) caem
    # em "opaque" — o verify nunca afirma substância que não pode provar.
    coverage: str = ""


# As 3 categorias NOMEADAS que o sumário honesto distingue (ACK M-001) +
# "opaque" pro legado não-declarado. Ordem estável p/ render e p/ as chaves
# do coverage_summary no --json.
_COVERAGE_CLASSES: tuple[str, ...] = ("substantive", "stub", "staged-blind", "opaque")


# ── Checkpoint (DRIFT-1 W2.T3b — intent-resume, outcome C) ───────────────────
#
# Per the T3a audit (action="add-new", reuse_path="init-pattern"), verify
# needs a minimal checkpoint so the host can pause at the scope
# disambiguation ask and re-invoke cleanly. Mirrors ``_InitCheckpoint``
# at ``engine/init.py:100-108`` — per-subcommand dataclass, no import
# from ``engine.qa.checkpoint`` (Decision 22 + outcome C lock-in).
#
# Verify has 2 interactive callsites — both ``question.ask`` em
# ``_infer_active_feature`` (interactive scope resolution) e
# ``_scope_to_feature_slug`` (run_scope multi-feature disambiguation).
# Ambas disparam apenas quando ha multiplas features ativas; intent-
# resume garante que a escolha sobrevive a re-invocacao.
#
# Refs:
#   - docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
#   - engine/init.py:100-108 (canonical template)


@dataclass
class _VerifyCheckpoint:
    """State serialized before each ``question.ask`` call in ``verify.run``.

    Carrega ``scope_kind`` + ``scope_target`` adicionais (alem de step,
    at, project_root, intent_id) porque verify resolve esses dois antes
    de chegar nos prompts ambiguos — preservar evita re-resolucao na
    invocacao seguinte (e mantem auditoria do que ja foi inferido).
    """

    step: str
    at: str
    project_root: str
    intent_id: str | None = None
    scope_kind: str | None = None
    scope_target: str | None = None


def _verify_checkpoint_path(project_root: Path) -> Path:
    return claude_dir(project_root) / ".verify-checkpoint.yaml"


# Os helpers abaixo são thin shims sobre ``engine.utils.checkpoint_io`` —
# consolidação dos 30 duplicates apontada pelos findings #5 e #21 do master
# review do PR #11. Os nomes ``_save_verify_checkpoint`` etc. permanecem
# como API privada do módulo para preservar os contracts dos testes em
# ``tests/unit/test_engine_verify_resume.py`` (Mandamento #2 — verde).
# L-03 (PR #remediation): ``_utc_now_iso_*`` shims removidos; callers
# usam ``utc_now_iso`` direto de ``engine.utils.iso``.


def _save_verify_checkpoint(cp: _VerifyCheckpoint) -> None:
    """Persist the verify checkpoint atomically."""
    _save_yaml_checkpoint_io(
        _verify_checkpoint_path(Path(cp.project_root)),
        {
            "schema-version": 1,
            "step": cp.step,
            "at": cp.at,
            "project-root": cp.project_root,
            "intent-id": cp.intent_id,
            "scope-kind": cp.scope_kind,
            "scope-target": cp.scope_target,
        },
    )


def _load_verify_checkpoint(project_root: Path) -> dict[str, Any] | None:
    """Read the verify checkpoint, returning ``None`` when absent."""
    return _load_yaml_checkpoint_io(_verify_checkpoint_path(project_root))


def _clear_verify_checkpoint(project_root: Path) -> None:
    """Remove the checkpoint — best-effort; silent on OSError (idempotent)."""
    _clear_checkpoint_io(_verify_checkpoint_path(project_root))


# ── Public API ───────────────────────────────────────────────────────────────


def run(argv: list[str]) -> int:
    """Entry point. `argv`: ``task TASK-NNNN`` | ``feature {slug}`` | empty.

    Return codes: 0 OK / warn-only; 1 hard fail; 130 user paused (raised by
    cli.main on KeyboardInterrupt / `para`).
    """
    json_mode = output_mode.is_json_mode()

    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        # H-001: in JSON mode `renderer.write` is a no-op, so the friendly text
        # would silently vanish. Mirror status/doctor/memory — emit the full
        # message on stderr (stdout stays pure JSON) and exit 1.
        if json_mode:
            sys.stderr.write(f"forge verify: {exc}\n")
            return 1
        renderer.write(renderer.colored(str(exc), "red"))
        return fail_with_tag(ERR_PROJECT_NOT_FOUND)

    # C-001: in JSON mode we MUST NOT prompt — exit-2 is reserved strictly for
    # the intent protocol (DRIFT-1), and a machine consumer cannot answer an
    # interactive ask. Resolve scope without prompting; if it stays ambiguous
    # (≥2 active features, no argv to disambiguate), emit a deterministic JSON
    # error on stderr + exit 1 (the contract the other read-commands honour)
    # instead of pausing.
    if json_mode:
        try:
            scope_kind, scope_target = _resolve_scope(
                argv, project_root, allow_prompt=False
            )
            feature_hint = _extract_feature_slug_hint(argv)
            # C-34: pre-resolve o feature slug AQUI com raise_on_ambiguous=True
            # pra o path `task` também. Sem isso, `verify --json task TASK-N`
            # com ≥2 features ativas caía no fallback sorted(active)[0] DENTRO
            # de run_scope → mutava a L1 da feature errada (status=verifying +
            # verify-log). Resolvido eagerly: ou um slug determinístico (vira
            # hint pra run_scope não re-resolver), ou _AmbiguousScopeError →
            # exit 1 ZERO escrita.
            resolved_slug = _scope_to_feature_slug(
                scope_kind,
                scope_target,
                project_root,
                interactive=False,
                argv_hint=feature_hint,
                raise_on_ambiguous=True,
            )
        except _AmbiguousScopeError as exc:
            sys.stderr.write(
                f"forge verify: scope ambíguo em JSON mode ({exc}) — passe "
                "`feature <slug>` ou `task TASK-NNNN --feature-slug <slug>`.\n"
            )
            return 1
        return run_scope(
            scope_kind,
            scope_target,
            project_root,
            interactive=False,
            feature_slug_hint=resolved_slug or feature_hint,
        )

    try:
        scope_kind, scope_target = _resolve_scope(argv, project_root)
    except PromptAbortedError:
        return 130

    # Pesca opcional `--feature-slug X` que hooks às vezes anexam pra
    # desambiguar scope task em projetos com múltiplas features ativas.
    feature_hint = _extract_feature_slug_hint(argv)

    return run_scope(
        scope_kind,
        scope_target,
        project_root,
        interactive=True,
        feature_slug_hint=feature_hint,
    )


def _extract_feature_slug_hint(argv: list[str]) -> str | None:
    """Lê `--feature-slug X` (ou `--feature-slug=X`) de argv, sem mutar."""
    if not argv:
        return None
    for i, token in enumerate(argv):
        if token == "--feature-slug" and i + 1 < len(argv):
            return argv[i + 1].strip() or None
        if token.startswith("--feature-slug="):
            value = token.split("=", 1)[1].strip()
            return value or None
    return None


def run_scope(
    scope_type: str,
    scope_id: str | None,
    project_root: Path,
    *,
    interactive: bool = False,
    feature_slug_hint: str | None = None,
) -> int:
    """Public API for hook-driven verify invocations.

    Non-interactive (``interactive=False``) suppresses prompts and the
    three-paths block — returns only an exit code so hooks can branch
    silently. Hooks call this from `engine.ingest`.

    Behavior shared with `run()`:
    - Updates L1 status (task/feature scope) to ``verifying`` while running,
      restoring the previous status on pass; on fail leaves the previous
      status untouched but appends ``verify-failed`` to ``raw.notes``.
    - Appends one record per invocation to
      ``.claude/forge/state/lifecycle/{feature_slug}/verify-log.jsonl`` (schema
      MEM-L1-VL-001..005).
    """
    if scope_type not in ("task", "feature"):
        scope_type = "feature"
    scope_target = scope_id or ""

    # A-009 (master review PR #15): se `project_root` não existe, `read_yaml_or_default`
    # devolve `{}` silenciosamente e o cascade roda com config vazia, reportando
    # "0 validators registered" em vez de avisar que o caminho é inválido.
    # Espelha o guard já existente em `_run_validator`.
    if not project_root.is_dir():
        if interactive:
            renderer.write(
                renderer.colored(
                    f"forge verify: project_root inexistente — {project_root}",
                    "red",
                )
            )
        return 1

    config = read_yaml_or_default(active_config_path(project_root), {}) or {}

    if interactive:
        renderer.write("")
        renderer.write(
            renderer.bold(
                f"forge verify — {scope_type}: {scope_target or '(empty)'}"
            )
        )
        renderer.write(renderer.dim("Read-only. Nada de mudar código."))
        renderer.write("")

    # L1 status: park feature as `verifying` so concurrent commands see the
    # lock. We always record the previous status to restore on success.
    feature_slug = _scope_to_feature_slug(
        scope_type,
        scope_target,
        project_root,
        interactive=interactive,
        argv_hint=feature_slug_hint,
    )
    previous_state: L1State | None = None
    if feature_slug:
        previous_state = read_l1_status(feature_slug, project_root)
        if previous_state is not None and previous_state.status != "verifying":
            transient = L1State(
                feature_slug=previous_state.feature_slug,
                status="verifying",
                last_action_at=utc_now_iso(),
                last_action_kind="verify-started",
                phase_lock=previous_state.phase_lock,
                raw=dict(previous_state.raw or {}),
            )
            try:
                write_l1_status(transient, project_root)
            except (MemoryStoreError, OSError):  # pragma: no cover - defensive
                previous_state = None  # don't try to restore an inconsistent state

    validators = _discover_validators(project_root, config, scope_type)
    if not validators:
        if interactive:
            renderer.write(renderer.dim("Nenhum validator pra este scope."))
            renderer.write(
                "Cards reais publicam seus validators em Phase 5+. "
                "Sem nada registrado, verify só confirma estado."
            )
        _write_verify_log_entry(
            project_root,
            feature_slug=feature_slug,
            scope_type=scope_type,
            scope_id=scope_target,
            validators=[],
            result="pass",
            hard_fails=[],
            warnings_list=[],
        )
        _restore_l1_status(project_root, previous_state, failed=False, note="")
        # DRIFT-1 W2.T3b — clear intent-resume checkpoint on clean completion.
        _clear_verify_checkpoint(project_root)
        if output_mode.is_json_mode():
            payload = {
                "scope": {"type": scope_type, "target": scope_target or None},
                "overall": "pass",
                "exit_code": 0,
                # WR-02: shape estável — sem validators não há infra degradada.
                "infra_degraded": 0,
                # T3: shape estável — coverage_summary presente mesmo sem
                # validators (todas as classes zeradas).
                "coverage_summary": _coverage_breakdown([]),
                "validators": [],
            }
            print(json.dumps(payload, indent=2, default=str))
        return 0

    # W-ROUTE 6c: hint educacional pré-cascade — renderizado pro usuário ANTES
    # dos validators rodarem. NÃO passado pra _run_cascade (determinismo: validators
    # nunca recebem contexto de mem — invariante enforçado por test_validators_determinism).
    # Degrade soft: mem ausente → hint None → omitido silenciosamente, sem nag.
    if interactive:
        _hint_query = feature_slug or scope_target or scope_type
        _verify_hint = mem_context_hint(project_root, _hint_query, limit=5)
        if _verify_hint is not None:
            renderer.write("")
            renderer.write(renderer.dim(_verify_hint))
            renderer.write("")

    fail_fast = _resolve_fail_fast(config)
    results = _run_cascade(
        validators,
        fail_fast=fail_fast,
        project_root=project_root,
        interactive=interactive,
        scope_type=scope_type,
        scope_target=scope_target,
    )
    if interactive:
        _render_summary(results)

    hard_fail = next((r for r in results if r.status == "fail"), None)
    warnings_list = [r.name for r in results if r.status == "warn"]
    hard_fails = [r.name for r in results if r.status == "fail"]
    degraded_list = [r.name for r in results if r.status == "degraded"]
    # WR-02 (fix-forward) — gêmeo "cega o overall" do BUG-VERIFY-1: um run com
    # `degraded` (infra off-contract) NÃO pode reportar `overall=pass` silencioso.
    # Quando há degraded e nenhum fail/warn, o overall vira `degraded` — sinal
    # distinto que o host IA-first lê como "nem tudo foi verificado de fato".
    #
    # INVARIANTE PRESERVADA (H-001 + Decisão 23): `degraded` continua NÃO sendo
    # `fail` — não halta a cascade e NÃO vira hard-fail de exit-code. Infra
    # quebrada ≠ código reprovado, então o exit-code segue 0 (só `fail` → exit 1).
    # `fail`/`warn` têm precedência sobre `degraded` no rótulo do overall (um
    # fail genuíno é o veredito dominante); a saliência de degraded num run
    # warn/fail-misto fica garantida pelo campo `infra_degraded` do payload.
    overall = (
        "fail" if hard_fail
        else "warn" if warnings_list
        else "degraded" if degraded_list
        else "pass"
    )

    _write_verify_log_entry(
        project_root,
        feature_slug=feature_slug,
        scope_type=scope_type,
        scope_id=scope_target,
        validators=[v.name for v in validators],
        result=overall,
        hard_fails=hard_fails,
        warnings_list=warnings_list,
    )

    if output_mode.is_json_mode():
        # A1 — emit the machine-readable cascade result. The exit code matches
        # the interactive path (0 pass/warn, 1 hard fail). L1 restore + verify
        # log + checkpoint clear below stay identical (read-only observability
        # does not change between modes).
        payload = {
            "scope": {"type": scope_type, "target": scope_target or None},
            "overall": overall,
            "exit_code": (1 if hard_fail is not None else 0),
            # WR-02: contagem saliente de infra degradada no topo do payload, pra
            # o host branchar sem varrer `validators[]`. Loud mesmo num run
            # warn/fail-misto (onde `overall` carrega o veredito dominante).
            "infra_degraded": len(degraded_list),
            # BUG-VERIFY-2 (T3): sumário honesto de cobertura — distingue
            # pass-substantivo de stub-no-op / staged-blind / opaque pro host
            # IA-first não tratar "verde" como garantia que não existe.
            "coverage_summary": _coverage_breakdown(results),
            "validators": [asdict(r) for r in results],
        }
        print(json.dumps(payload, indent=2, default=str))

    if hard_fail is not None:
        if interactive:
            _render_hard_fail_block(hard_fail)
        _restore_l1_status(
            project_root,
            previous_state,
            failed=True,
            note=f"verify-failed: {hard_fail.name}",
        )
        # DRIFT-1 W2.T3b — hard fail is a normal verdict (not invalid response),
        # so clear the intent-resume checkpoint per ``_clear_state`` contract.
        # SPEC §3 forensic preservation applies to invalid-response branches,
        # not to validator hard fails.
        _clear_verify_checkpoint(project_root)
        return 1

    _restore_l1_status(project_root, previous_state, failed=False, note="")
    # DRIFT-1 W2.T3b — clear intent-resume checkpoint on clean completion.
    _clear_verify_checkpoint(project_root)
    return 0


# ── L1 + verify-log plumbing ────────────────────────────────────────────────


def _scope_to_feature_slug(
    scope_type: str,
    scope_target: str,
    project_root: Path,
    *,
    interactive: bool = True,
    argv_hint: str | None = None,
    raise_on_ambiguous: bool = False,
) -> str:
    """Resolve the feature slug owning a verify scope.

    For ``feature`` scope the target *is* the slug. For ``task`` scope o
    mapping task→feature ainda não é canônico; usamos fallbacks em ordem:

    1. ``argv_hint`` quando passado (chamada via hook com ``--feature-slug``).
    2. ``status='implementing'`` único — caso comum.
    3. Conjunto de features ativas (planning/implementing/verifying):
       - 1 ativa → retorna ela.
       - múltiplas + ``interactive=True`` → pergunta via ``question.ask``.
       - múltiplas + ``interactive=False`` → emite warn e retorna a 1ª em
         ordem alfabética (determinístico, não-bloqueante).
       - 0 ativas → string vazia.

    C-34 (PR21-I2): quando ``raise_on_ambiguous`` é True (JSON mode), o ramo
    "múltiplas ativas sem desambiguação" levanta ``_AmbiguousScopeError`` em vez
    de cair no ``sorted(active)[0]`` — esse fallback silencioso mutava a L1 da
    feature ERRADA (status=verifying transiente + verify-log) num consumidor
    machine que não pode responder o prompt. O guard C-001 cobria só o path de
    inferência de scope; ``verify --json task TASK-N`` escapava por aqui.
    """
    if scope_type == "feature":
        return scope_target or ""

    if argv_hint:
        return argv_hint

    active_states = {"planning", "implementing", "verifying"}
    active = [
        slug for slug in list_active_features(project_root)
        if (read_l1_status(slug, project_root) or L1State("", "", "", "")).status
        in active_states
    ]
    if not active:
        return ""
    if len(active) == 1:
        return active[0]

    # Múltiplas features ativas — preferir a única em 'implementing'.
    implementing = [
        slug for slug in active
        if (read_l1_status(slug, project_root) or L1State("", "", "", "")).status
        == "implementing"
    ]
    if len(implementing) == 1:
        return implementing[0]

    # C-34: ≥2 ativas, sem hint, sem mapping único → ambíguo. Em JSON mode
    # (raise_on_ambiguous), erro determinístico ANTES de qualquer escrita de L1
    # — nunca mutar a feature errada por fallback silencioso.
    if raise_on_ambiguous:
        raise _AmbiguousScopeError(
            f"{len(active)} features ativas: {', '.join(sorted(active))}"
        )

    if interactive:
        try:
            options = {slug: f"feature ativa ({slug})" for slug in active}
            # DRIFT-1 W2.T3b — persist checkpoint with the deterministic
            # intent-id for this ask BEFORE invoking ``question.ask``.
            _save_verify_checkpoint(
                _VerifyCheckpoint(
                    step="step-scope-disambiguation",
                    at=utc_now_iso(),
                    project_root=str(project_root),
                    intent_id=question.stable_intent_id(
                        "ask",
                        "Múltiplas features ativas — qual escopo da verificação?",
                        options,
                        extra={
                            "default": active[0],
                            "min-selected": None,
                            "validator-hint": None,
                        },
                    ),
                    scope_kind=scope_type,
                    scope_target=scope_target,
                )
            )
            return question.ask(
                "Múltiplas features ativas — qual escopo da verificação?",
                options,
                default=active[0],
            )
        except PromptAbortedError:
            return active[0]

    # Não-interativo (chamada via hook sem hint): determinístico + warn.
    first = sorted(active)[0]
    renderer.write(
        renderer.colored(
            f"⚠ verify: {len(active)} features ativas — usando '{first}' "
            "(passe --feature-slug pra desambiguar)",
            "yellow",
        )
    )
    return first


def _restore_l1_status(
    project_root: Path,
    previous_state: L1State | None,
    *,
    failed: bool,
    note: str,
) -> None:
    if previous_state is None:
        return
    try:
        if failed:
            raw = dict(previous_state.raw or {})
            existing_notes = str(raw.get("notes") or "")
            raw["notes"] = (existing_notes + ("\n" if existing_notes else "") + note).strip()
            failing = L1State(
                feature_slug=previous_state.feature_slug,
                status=previous_state.status,
                last_action_at=utc_now_iso(),
                last_action_kind="verify-failed",
                phase_lock=previous_state.phase_lock,
                raw=raw,
            )
            write_l1_status(failing, project_root)
            return
        restored = L1State(
            feature_slug=previous_state.feature_slug,
            status=previous_state.status,
            last_action_at=utc_now_iso(),
            last_action_kind="verify-passed",
            phase_lock=previous_state.phase_lock,
            raw=dict(previous_state.raw or {}),
        )
        write_l1_status(restored, project_root)
    except (MemoryStoreError, OSError):  # pragma: no cover - defensive
        pass


def _write_verify_log_entry(
    project_root: Path,
    *,
    feature_slug: str,
    scope_type: str,
    scope_id: str,
    validators: list[str],
    result: str,
    hard_fails: list[str],
    warnings_list: list[str],
) -> None:
    """Append one line to ``.claude/forge/state/lifecycle/{slug}/verify-log.jsonl``.

    Silently no-ops when there is no resolvable feature slug — the log is
    per-feature by design (schema MEM-L1-VL-001..005).
    """
    if not feature_slug:
        return
    ts = utc_now_iso()
    compact = ts.replace(":", "").replace("-", "").replace(".", "")
    entry = {
        "schema-version": 1,
        "verify-id": f"verify-{compact}",
        "at": ts,
        "scope": {"type": scope_type, "id": scope_id},
        "validators-run": list(validators),
        "result": result,
        "hard-fails": list(hard_fails),
        "warnings": list(warnings_list),
    }
    log_path = lifecycle_root(project_root) / feature_slug / "verify-log.jsonl"
    try:
        ensure_dir(log_path.parent)
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        pass


# ── Scope resolution ─────────────────────────────────────────────────────────


class _AmbiguousScopeError(Exception):
    """Raised when scope inference is ambiguous and prompting is disallowed.

    C-001: JSON mode never prompts. When ≥2 features are active and no argv
    disambiguates, the caller turns this into a deterministic hard error
    (stderr + exit 1) instead of either pausing (intent protocol leak) or
    silently picking the first feature.
    """


def _resolve_scope(
    argv: list[str], project_root: Path, *, allow_prompt: bool = True
) -> tuple[str, str]:
    """Return ``(scope_kind, target)``.

    ``scope_kind`` ∈ {task, feature}. ``target`` is the task id or feature
    slug. Asks the user when ambiguous (more than one active feature) — unless
    ``allow_prompt=False`` (C-001: JSON mode never prompts). With prompting
    disabled, an ambiguous inference raises ``_AmbiguousScopeError`` so the
    caller can emit a deterministic error rather than silently picking one
    feature; an empty target still means "no active feature" (valid: cascade
    runs with 0 validators).

    C-39 (PR21-I8): meta-flags reconhecidas (``--json``) são removidas de argv
    ANTES do parse posicional — senão ``forge verify --json`` resolveria
    ``--json`` como slug de feature. Espelha o tratamento de ``--no-auto-build``
    em ``graph_cli``. ``--feature-slug X`` é consumido por
    ``_extract_feature_slug_hint`` à parte; aqui só limpamos os tokens
    booleanos que não carregam valor posicional.
    """
    argv = [tok for tok in argv if tok != "--json"]
    if argv:
        first = argv[0]
        if first.upper().startswith("TASK-"):
            return "task", first.upper()
        if first == ".":
            return "feature", _infer_active_feature(
                project_root, allow_prompt=allow_prompt
            )
        if len(argv) >= 2 and argv[0] == "task":
            return "task", argv[1].upper()
        if len(argv) >= 2 and argv[0] == "feature":
            return "feature", argv[1]
        return "feature", first

    inferred = _infer_active_feature(project_root, allow_prompt=allow_prompt)
    return "feature", inferred


def _infer_active_feature(project_root: Path, *, allow_prompt: bool) -> str:
    """Choose the single in-progress feature, asking when there is more than one.

    When ``allow_prompt=False`` and the inference is ambiguous (≥2 candidates),
    raises ``_AmbiguousScopeError`` (C-001) — the JSON-mode caller turns this
    into a hard error instead of pausing or silently picking the first. No
    active feature still returns ``""`` (a valid empty scope).
    """
    active = list_active_features(project_root)
    candidates: list[str] = []
    for slug in active:
        state = read_l1_status(slug, project_root)
        if state is None:
            continue
        if state.status in {"implementing", "verifying", "planning"}:
            candidates.append(slug)
    if not candidates and active:
        candidates = active

    if not candidates:
        return ""
    if len(candidates) == 1:
        return candidates[0]
    if not allow_prompt:
        raise _AmbiguousScopeError(
            f"{len(candidates)} features ativas: {', '.join(sorted(candidates))}"
        )
    options = {slug: f"feature {slug}" for slug in candidates}
    # DRIFT-1 W2.T3b — persist checkpoint with the deterministic intent-id
    # for this ask BEFORE invoking ``question.ask``. On exit-2 + re-invoke,
    # ``question.ask`` finds the matching ``forge-response.json`` and
    # returns the value without re-prompting.
    _save_verify_checkpoint(
        _VerifyCheckpoint(
            step="step-infer-active-feature",
            at=utc_now_iso(),
            project_root=str(project_root),
            intent_id=question.stable_intent_id(
                "ask",
                "Mais de um feature ativo. Qual?",
                options,
                extra={
                    "default": None,
                    "min-selected": None,
                    "validator-hint": None,
                },
            ),
            scope_kind="feature",
            scope_target=None,
        )
    )
    return question.ask("Mais de um feature ativo. Qual?", options)


# ── Validator discovery ──────────────────────────────────────────────────────


def _discover_validators(
    project_root: Path,
    config: dict,
    scope_kind: str,
) -> list[_ValidatorSpec]:
    """Read validator declarations from each active card's snapshot.

    Filters by `runs-on` so only validators that match the current scope are
    returned. `task` → ``verify-task``; `feature` → ``verify-task`` plus
    ``forge-doctor`` (intentionally permissive so feature-scope sees more).
    """
    relevant = {"verify-task"}
    if scope_kind == "feature":
        relevant.add("forge-doctor")

    cards_root = cards_dir(project_root)
    out: list[_ValidatorSpec] = []
    for card in (config.get("cards") or {}).get("active") or []:
        if not isinstance(card, dict):
            continue
        card_name = str(card.get("name") or "")
        if not card_name:
            continue
        card_yaml = cards_root / card_name / "card.yaml"
        if not card_yaml.is_file():
            continue
        card_data = read_yaml_or_default(card_yaml, {}) or {}
        contribs = (card_data.get("contributes") or {}).get("validators") or []
        for entry in contribs:
            if not isinstance(entry, dict):
                continue
            runs_on = list(entry.get("runs-on") or [])
            if runs_on and not (set(runs_on) & relevant):
                continue
            script_rel = entry.get("file")
            if not isinstance(script_rel, str) or not script_rel:
                continue
            script_path = (cards_root / card_name / script_rel).resolve()
            out.append(
                _ValidatorSpec(
                    name=str(entry.get("name") or script_rel),
                    script_path=script_path,
                    severity=str(entry.get("severity") or "warn"),
                    card_name=card_name,
                    runs_on=runs_on or [_DEFAULT_RUNS_ON],
                )
            )
    out.sort(key=lambda v: (v.card_name, v.name))
    return _default_validator_specs(project_root) + out


# ── Default validators registry ──────────────────────────────────────────────
#
# Validators that ship with forge engine itself (multi-language,
# project-agnostic) and run on every verify scope regardless of which cards
# are active. Order is load-bearing — cascade fail-fast (Decision 23) honors
# this sequence.

_DEFAULT_VALIDATORS: list[dict[str, str]] = [
    {
        "name": "check_no_invented_behavior",
        "file": "check_no_invented_behavior.py",
        "severity": "fail",
    },
    {
        # PLACEHOLDER-VERIFY (W-DEBT): cheap scan de {{...}} crus em artefatos
        # de feature — bloqueia early (antes do CC gate, mais caro).
        "name": "check_unfilled_placeholders",
        "file": "check_unfilled_placeholders.py",
        "severity": "fail",
    },
    {
        "name": "check_cyclomatic_complexity",
        "file": "check_cyclomatic_complexity.py",
        "severity": "fail",
    },
    {
        "name": "check_secrets",
        "file": "check_secrets.py",
        "severity": "fail",
    },
]


def _default_validator_specs(project_root: Path) -> list[_ValidatorSpec]:
    """Build _ValidatorSpec entries for the engine's built-in validators.

    Resolved relative to ``<repo>/validators/``. Skips entries whose script
    file doesn't exist on disk (defensive — keeps verify usable durante
    partial snapshots / first-run states).
    """
    validators_dir = Path(__file__).resolve().parent.parent / "validators"
    out: list[_ValidatorSpec] = []
    for entry in _DEFAULT_VALIDATORS:
        script = validators_dir / entry["file"]
        if not script.is_file():
            continue
        out.append(
            _ValidatorSpec(
                name=entry["name"],
                script_path=script,
                severity=entry.get("severity", "warn"),
                card_name="<engine-default>",
                runs_on=["verify-task", "forge-doctor"],
            )
        )
    return out


def _resolve_fail_fast(config: dict) -> bool:
    block = config.get("validators")
    if not isinstance(block, dict):
        return True
    raw = block.get("fail-fast")
    if raw is None:
        return True
    return bool(raw)


# ── Cascade ──────────────────────────────────────────────────────────────────


def _run_cascade(
    validators: list[_ValidatorSpec],
    *,
    fail_fast: bool,
    project_root: Path,
    interactive: bool = True,
    scope_type: str | None = None,
    scope_target: str | None = None,
) -> list[_ValidatorResult]:
    """Dispatch each validator and collect results.

    Stops on the first ``fail`` when ``fail_fast`` is true; otherwise drains
    the whole list, marking nothing as ``skipped``. When ``interactive`` is
    False the cinematic per-line output is suppressed (hook callers don't
    want it on stderr).

    C-43 (PR22-R-001): ``scope_type``/``scope_target`` são threadados até
    ``_invoke_validator`` — sem isso, validators scope-aware (ex.:
    ``check_unfilled_placeholders``) recebiam kwargs vazios e ficavam inertes
    (gate shipped-but-vacuous). Os defaults ``None`` preservam call-sites
    legados (testes que invocam ``_run_cascade`` sem scope).
    """
    results: list[_ValidatorResult] = []
    halted = False
    for spec in validators:
        if halted:
            results.append(_ValidatorResult(name=spec.name, status="skipped"))
            if interactive:
                _render_line(results[-1])
            continue
        result = _invoke_validator(
            spec, project_root, scope_type=scope_type, scope_target=scope_target
        )
        results.append(result)
        if interactive:
            _render_line(result)
        if result.status == "fail" and fail_fast:
            halted = True
    return results


def _invoke_validator(
    spec: _ValidatorSpec,
    project_root: Path,
    *,
    scope_type: str | None = None,
    scope_target: str | None = None,
) -> _ValidatorResult:
    """Run a single validator as a subprocess.

    Convention: validators print human output to stderr/stdout freely and
    emit one final JSON line with ``{"status": ..., "message": ..., ...}`` on
    stdout when they want structured output. Missing JSON → degrade to the
    exit-code contract (0 pass, 1 warn, 2 fail).

    C-43: quando ``scope_type``/``scope_target`` chegam, são anexados como
    ``--scope <kind> --id <target>`` ao argv do subprocess (contrato de
    ``validators/_common.build_argparser``). Validators que ignoram scope
    simplesmente não usam os kwargs — backward-compatible.
    """
    if not spec.script_path.is_file():
        return _ValidatorResult(
            name=spec.name,
            status="degraded",
            message=f"script not found: {spec.script_path}",
        )

    # H-10: project_root must be a real directory before we hand it to
    # subprocess as cwd. Caller-controlled path apontando pra arquivo /
    # caminho inexistente vira NotADirectoryError opaco em subprocess.run
    # (OSError branch abaixo) — checagem explicita produz mensagem
    # auditavel e fecha o vetor cedo.
    if not project_root.is_dir():
        return _ValidatorResult(
            name=spec.name,
            status="degraded",
            message=f"project_root is not a directory: {project_root}",
        )

    cmd = [sys.executable, str(spec.script_path), "--project-root", str(project_root)]
    if scope_type:
        cmd += ["--scope", scope_type]
    if scope_target:
        cmd += ["--id", scope_target]

    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            env=build_safe_env(extras=("JAVA_HOME", "ANDROID_HOME", "GRADLE_USER_HOME")),     # QA-11: env reduzido pra subprocess de validator
            cwd=str(project_root),
        )
    except subprocess.TimeoutExpired:
        return _ValidatorResult(
            name=spec.name,
            status="degraded",
            duration_ms=60_000,
            message="timeout (>60s)",
        )
    except OSError as exc:
        return _ValidatorResult(
            name=spec.name,
            status="degraded",
            message=f"OS error: {exc}",
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    payload = _extract_json_tail(proc.stdout)
    if payload is None:
        # BUG-VERIFY-1 / ACK H-001 — INVARIANTE DE DETECTION (durável, não opcional):
        #
        #   validator quebrado / off-contract  ≠  código reprovado.
        #
        # Sem JSON tail, caímos na exit-code contract. Exit 2 é o sinal de
        # argparse para "unrecognized arguments" / "invalid choice": o script
        # está QUEBRADO ou FORA do contrato canônico (--project-root/--scope/
        # --id). Isso é falha de INFRAESTRUTURA do validator — não código que
        # o validator reprovou. Por isso vira `degraded`:
        #
        #   - `degraded` NÃO conta pro overall (run() só olha fail/warn) e NÃO
        #     para a cascade fail-fast (Decisão 23 — _run_cascade só halta em
        #     `fail`). Um validator off-contract não pode cegar os 5 validators
        #     iOS/KMP a jusante (foi exatamente o piloto MeoBonsai: koin só
        #     aceitava --root, estourava exit 2, virava `fail`, parava tudo).
        #   - Deliberadamente NÃO é `warn`: warn conta no overall (vira
        #     overall="warn") e mascararia o problema de infra como ressalva de
        #     código. O anti-padrão exit-2→warn está banido.
        #   - Exit 1 sem JSON permanece `warn` (ressalva leve); o hard fail
        #     canônico de código reprovado vem pelo JSON tail {"status":"fail"}.
        #
        # Guarda executável desta fronteira:
        #   tests/engine/test_verify_broken_validator_degraded.py
        if proc.returncode == 0:
            status = "pass"
        elif proc.returncode == 1:
            status = "warn"
        else:
            # exit 2 (ou qualquer código ≥2) = validator quebrado/off-contract.
            status = "degraded"
        return _ValidatorResult(
            name=spec.name,
            status=status,
            duration_ms=duration_ms,
            message=(proc.stderr or proc.stdout).strip()[:200],
            # T3: pass via exit-code (sem JSON) é "opaque" — o verify não tem
            # como afirmar que houve trabalho substantivo. Honesto por default.
            coverage="opaque" if status == "pass" else "",
        )

    status = str(payload.get("status") or "pass").lower()
    if status == "error":
        status = "fail"
    return _ValidatorResult(
        name=spec.name,
        status=status,
        duration_ms=duration_ms,
        message=str(payload.get("message") or ""),
        paths=list(payload.get("paths") or []),
        what_failed=str(payload.get("what-failed") or ""),
        where=str(payload.get("where") or ""),
        why=list(payload.get("why") or []),
        # T3: só PASS carrega classe de cobertura. Validator que declara
        # `coverage` no JSON tem sua palavra honrada; se passou e não declarou,
        # cai em "opaque" (o verify não inventa substância). Valor não-canônico
        # é normalizado pra "opaque" pra não poluir o breakdown.
        coverage=_normalize_coverage(payload.get("coverage")) if status == "pass" else "",
    )


def _normalize_coverage(raw: object) -> str:
    """Mapeia o `coverage` declarado por um validator pra uma das classes
    canônicas. Ausente / não-string / fora do vocabulário → "opaque" (default
    honesto — verify não afirma substância não-provada)."""
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in _COVERAGE_CLASSES:
            return value
    return "opaque"


def _coverage_breakdown(results: list[_ValidatorResult]) -> dict[str, int]:
    """Conta os PASSES por classe de cobertura (ACK M-001) + os degradados (WR-02).

    As 4 chaves canônicas (`_COVERAGE_CLASSES`) contam só `status == "pass"` —
    warn/fail/skipped não têm classe de cobertura. A chave `degraded` (gêmeo do
    overall, WR-02) conta os validators degradados pra que um run all-degraded
    exiba "0 substantivos / N degradados" em vez de um zero mudo que parece
    "nada a verificar = ok". `degraded` NÃO é classe de pass-coverage — fica
    numa chave separada pra não poluir a soma dos passes. Shape estável no
    --json e no render (zeros inclusos)."""
    breakdown = {cls: 0 for cls in _COVERAGE_CLASSES}
    breakdown["degraded"] = 0
    for r in results:
        if r.status == "degraded":
            breakdown["degraded"] += 1
            continue
        if r.status != "pass":
            continue
        cls = r.coverage if r.coverage in breakdown else "opaque"
        breakdown[cls] += 1
    return breakdown


def _extract_json_tail(stdout: str) -> dict | None:
    """Pull the last JSON object printed by the validator, if any."""
    stripped = stdout.strip()
    if not stripped:
        return None
    last_line = stripped.splitlines()[-1].strip()
    if not last_line.startswith("{"):
        return None
    try:
        data = json.loads(last_line)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


# ── Rendering ────────────────────────────────────────────────────────────────


_STATUS_GLYPH = {
    "pass": "✓",
    "warn": "⚠",
    "fail": "🛑",
    "skipped": "—",
    # WR-01: glyph PRÓPRIO pra degraded — não reusa o ⚠ do warn. A distinção
    # infra-vs-código (coração do H-001) tem que ser visível na linha-a-linha,
    # não só no sumário-box agregado.
    "degraded": "⛒",
}


def _render_line(result: _ValidatorResult) -> None:
    glyph = _STATUS_GLYPH.get(result.status, "?")
    if result.status == "skipped":
        renderer.write(
            f"├ {result.name:<40} {glyph} não rodado (cascade parou)"
        )
        return
    duration = _format_duration(result.duration_ms)
    suffix = "FAIL" if result.status == "fail" else ""
    line = f"├ {result.name:<40} {glyph} {duration:>6}"
    if suffix:
        line = f"{line}  {suffix}"
    # WR-01: warn (ressalva de código) E degraded (infra off-contract) imprimem
    # o motivo na linha — pro usuário ler na hora, junto do glyph distinto, que
    # foi infra quebrada e não código reprovado.
    if result.status in ("warn", "degraded") and result.message:
        line = f"{line}  ({result.message[:60]})"
    renderer.write(line)


def _format_duration(ms: int) -> str:
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms / 1000:.1f}s"


def _render_summary(results: list[_ValidatorResult]) -> None:
    passed = sum(1 for r in results if r.status == "pass")
    warns = sum(1 for r in results if r.status == "warn")
    fails = sum(1 for r in results if r.status == "fail")
    skipped = sum(1 for r in results if r.status == "skipped")
    degraded = sum(1 for r in results if r.status == "degraded")

    renderer.write("")
    title = "Verify clean" if fails == 0 else "Verify block"
    body = [
        f"Pass:      {passed}",
        f"Warn:      {warns}",
        f"Fail:      {fails}",
        f"Skipped:   {skipped}",
        f"Degraded:  {degraded}",
    ]
    # BUG-VERIFY-2 (T3): quebra honesta dos passes — "verde" não conta como
    # garantia uniforme. Só renderiza quando há pass que não é substantivo,
    # pra não nag em projeto 100% substantivo.
    if passed:
        cov = _coverage_breakdown(results)
        if cov["substantive"] != passed:
            body.append("")
            body.append("Pass por cobertura:")
            body.append(f"  substantive:  {cov['substantive']}")
            body.append(f"  stub:         {cov['stub']}")
            body.append(f"  staged-blind: {cov['staged-blind']}")
            body.append(f"  opaque:       {cov['opaque']}")
    renderer.write(renderer.box(title, body))


def _render_hard_fail_block(result: _ValidatorResult) -> None:
    """If the validator returned a structured 3-paths block, render it. Else
    fall back to a generic Fix/Revert/Split shape so the user still gets the
    discipline §1 affordance.
    """
    paths = result.paths
    if len(paths) != 3:
        paths = [
            {"label": "Fix", "motive": "Ajuste mínimo no código que falhou."},
            {"label": "Revert", "motive": "Volta ao último estado clean."},
            {"label": "Split", "motive": "Abre tarefa nova e segue."},
        ]
    block = mentor_calmo.three_paths_block(
        result.name,
        what_failed=result.what_failed
        or result.message
        or "Validador retornou falha sem contexto estruturado.",
        where=result.where or "(não informado pelo validador)",
        why=result.why
        or [
            "Hard gate da cascade.",
            "Sem auto-fix em verify — escolha humana (discipline §1).",
        ],
        paths=paths,
    )
    renderer.write("")
    renderer.write(block)
