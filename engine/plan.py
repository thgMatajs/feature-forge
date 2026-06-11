"""`forge plan` — planning conductor (Waves A–E).

Orchestrates a single feature through 5 sequential planning waves, each one
emitting one or more artefacts under
`docs/feature-implementation-workflow/features/{slug}/`. Per-feature working
state lives in `.claude/memory/L1/{slug}/`.

v1 realism: this module does NOT invoke LLM sub-agents directly. It renders
the canonical templates as placeholder artefacts and walks the user through
each wave with cinematic prompts. The actual Claude Code session (running on
top of this engine) is expected to fill the placeholders interactively
between wave acknowledgements (`continuar`).

Waves:
    A  feature-intake.md + feature-prd.md
    B  screen-analysis.md + bdd.md + bdd.json + ui-state-spec.yaml +
       navigation-spec.yaml + data-contract-spec.yaml + analytics-spec.yaml +
       test-strategy.yaml
    C  tech-spec.md
    D  task-breakdown.yaml + tasks/TASK-NNNN.yaml * N
    E  implementation-readiness-review.md + plan-feature-handoff.json

Exit codes follow CLI convention:
    0    success (readiness=ready or clean deferred)
    130  paused via Ctrl+C / `para`
    other  hard gate violation
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from engine.memory.l1 import (
    L1State,
    acquire_phase_lock,
    append_history,
    current_subtype,
    list_active_features,
    read_elicitation,
    read_hypothesis,
    read_l1_status,
    release_phase_lock,
    set_subtype,
    write_elicitation,
    write_hypothesis,
    write_l1_status,
)
from engine.persona import mentor_calmo
from engine.ui import question, renderer
from engine.ui.question import PromptAbortedError
from engine.utils.paths import (
    ProjectRootNotFoundError,
    claude_dir,
    ensure_dir,
    feature_dir,
    find_project_root,
    workflow_config_path,
)
from engine.utils.yaml_io import read_yaml_or_default, write_yaml
from engine.utils.checkpoint_io import (
    clear_checkpoint as _clear_checkpoint_io,
    load_yaml_checkpoint as _load_yaml_checkpoint_io,
    save_yaml_checkpoint as _save_yaml_checkpoint_io,
)
from engine.utils.iso import utc_now_iso as _utc_now_iso_shared

# ── Constants ────────────────────────────────────────────────────────────────

_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,48}[a-z0-9]$")
_TEMPLATES_SUBDIR = "templates"

WAVE_A_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("feature-intake.template.md", "feature-intake.md"),
    ("feature-prd.template.md", "feature-prd.md"),
)

# Wave A variant for subtype=refactor: stripped intake (no PRD).
# Discipline §8 — non-product feature track.
WAVE_A_REFACTOR_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("feature-intake-refactor.template.md", "feature-intake.md"),
)

# Wave A variant for subtype=bugfix: bug-shaped intake (no PRD).
# Discipline §8 (Gap 1) — bugfix has §Problem statement + §Reproduction
# steps + §Expected vs actual + §Root-cause hypothesis + §Fix scope +
# §Regression risk + §Validation strategy.
WAVE_A_BUGFIX_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("feature-intake-bugfix.template.md", "feature-intake.md"),
)

# Subtype detection keywords. Inference, not imposition — conductor
# confirms interactively (Cena 2.5 in forge-plan-roteiro.md).
_SUBTYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "refactor": (
        "refactor",
        "refatorar",
        "refatorando",
        "mover ",
        "renomear",
        "extrair",
        "reorganizar",
        "sem mudança visual",
        "sem mudanca visual",
        "comportamento inalterado",
        "move from",
        "rename",
    ),
    "bugfix": (
        "bugfix",
        "bug-fix",
        "hotfix",
        "hot-fix",
        "p0",
        "p1",
        "crítico",
        "critico",
        "crítica",
        "critica",
        "bug ",
        "fix ",
        "falha",
        "quebrado",
        "quebrada",
        "não funciona",
        "nao funciona",
        "regression",
        "regressão",
        "regressao",
        "crash",
        "crasha",
    ),
    "spike": (
        "spike",
        "poc",
        "viabilidade",
        "prototipar",
        "prototype",
        "investigar se",
        "exploração",
        "exploracao",
        "exploration",
    ),
    "chore": (
        "bump ",
        "atualizar dependência",
        "atualizar dependencia",
        "update dependency",
        "cleanup",
        "limpeza",
        "chore",
    ),
}

# Ticket-pattern regex — high-confidence bugfix signal. Detected
# separately from keyword matching so the conductor can re-confirm
# product-vs-bugfix when only a ticket id appears.
# Examples that match: IN-37234, PD-1234, BUG-0001, BACKEND-1284.
_TICKET_PATTERN = re.compile(r"\b([A-Z]{2,6}-\d{2,6})\b")

# Ticket prefixes that strongly imply bugfix (vs feature/backend tickets).
# When a prefix is NOT in this set (e.g., BACKEND-, BONSAI-), conductor
# must ask the user to disambiguate — the regex match alone is not
# enough to bump subtype.
_BUGFIX_TICKET_PREFIXES: frozenset[str] = frozenset({"IN", "PD", "BUG"})

# Wave order for product subtype — full Waves A-E.
_WAVE_ORDER_PRODUCT: tuple[str, ...] = ("A", "B", "C", "D", "E")

# Wave order for refactor subtype — skip Wave B entirely.
# Discipline §8: refactor has no behavioral mockup and no new contracts.
_WAVE_ORDER_REFACTOR: tuple[str, ...] = ("A", "C", "D", "E")

# Wave order for bugfix subtype is RUNTIME-CONDITIONAL on
# `hypothesis.yaml.wave_b_required` — see _wave_order_for_subtype.
# Default order matches refactor (Wave B skipped) because logic-only
# bugfixes are the common case; the conductor flips back to the full
# product sequence when the Cena 2.5 sub-question answer is "sim".
_WAVE_ORDER_BUGFIX_LOGIC_ONLY: tuple[str, ...] = ("A", "C", "D", "E")
_WAVE_ORDER_BUGFIX_UI_OBSERVABLE: tuple[str, ...] = ("A", "B", "C", "D", "E")

WAVE_B_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("screen-analysis.template.md", "screen-analysis.md"),
    ("bdd.template.md", "bdd.md"),
    ("bdd.template.json", "bdd.json"),
    ("ui-state-spec.template.yaml", "ui-state-spec.yaml"),
    ("navigation-spec.template.yaml", "navigation-spec.yaml"),
    ("data-contract-spec.template.yaml", "data-contract-spec.yaml"),
    ("analytics-spec.template.yaml", "analytics-spec.yaml"),
    ("test-strategy.template.yaml", "test-strategy.yaml"),
)

WAVE_C_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("tech-spec.template.md", "tech-spec.md"),
)

WAVE_D_HEAD_TEMPLATE: tuple[str, str] = ("task-breakdown.template.yaml", "task-breakdown.yaml")
WAVE_D_TASK_TEMPLATE: str = "task-contract.template.yaml"

WAVE_E_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("implementation-readiness-review.template.md", "implementation-readiness-review.md"),
    ("plan-feature-handoff.template.json", "plan-feature-handoff.json"),
)

# Legacy alias preserved for backwards compatibility with tests/callers
# that reference _WAVE_ORDER directly. Production code routes through
# `_wave_order_for_subtype` instead.
_WAVE_ORDER: tuple[str, ...] = _WAVE_ORDER_PRODUCT


def _wave_order_for_subtype(
    subtype: str, *, wave_b_required: Optional[bool] = None
) -> tuple[str, ...]:
    """Return the wave sequence for a given subtype.

    Discipline §8 — non-product feature track:
      - product (default): A · B · C · D · E
      - refactor:           A · C · D · E (Wave B skipped — no screen-analysis,
                                            no contract-planner)
      - bugfix:             RUNTIME-CONDITIONAL on `wave_b_required`:
                              · True  → A · B · C · D · E (UI/observable bug —
                                          contracts must be respected)
                              · False → A · C · D · E (logic-only bug — same
                                          as refactor; no contracts to invent)
                              · None  → A · C · D · E (defensive default;
                                          conductor should always supply the
                                          flag from `hypothesis.yaml`)
      - spike / chore:      stubbed at the conductor level via 3-caminhos
                            BEFORE this function is called; if we reach it
                            with these subtypes, fall back to product
                            sequence (safe — sub-agents will surface the
                            mismatch upstream).
    """
    if subtype == "refactor":
        return _WAVE_ORDER_REFACTOR
    if subtype == "bugfix":
        return (
            _WAVE_ORDER_BUGFIX_UI_OBSERVABLE
            if wave_b_required is True
            else _WAVE_ORDER_BUGFIX_LOGIC_ONLY
        )
    return _WAVE_ORDER_PRODUCT


def detect_subtype_from_input(text: str) -> str:
    """Infer feature subtype from a free-form input string.

    Returns "product" (the default) when no keyword matches. Order of
    precedence: refactor > bugfix > spike > chore (longest semantic
    signal wins; refactor beats bugfix because "refactor"+"fix " can
    co-occur and the more structured signal should win).

    Bugfix is also bumped by a high-confidence **ticket-pattern**
    (e.g., `IN-37234`, `PD-1234`, `BUG-0001`) — see Gap 1 in
    `docs/design/04-pending.md`. The ticket prefix must be in the
    bugfix-tracker whitelist (`_BUGFIX_TICKET_PREFIXES`); generic
    feature tickets like BONSAI-1284 or BACKEND-1284 do not trigger
    the bump (conductor asks the user instead).

    Conductor MUST confirm interactively before persisting — this is
    inference, not imposition. Cena 2.5 in forge-plan-roteiro.md shows
    the confirmation flow.
    """
    if not isinstance(text, str) or not text.strip():
        return "product"
    lowered = text.lower()
    # Check in priority order; the test suite asserts this ordering.
    for subtype in ("refactor", "bugfix", "spike", "chore"):
        keywords = _SUBTYPE_KEYWORDS[subtype]
        if any(kw in lowered for kw in keywords):
            return subtype
    # Ticket-pattern detection. Applied AFTER keyword matching so an
    # explicit "feature de produto + IN-37234" still wins as product
    # via the absence of bugfix keywords (the regex alone is not
    # decisive — only the prefix whitelist).
    match = _TICKET_PATTERN.search(text)
    if match:
        prefix = match.group(1).split("-", 1)[0]
        if prefix in _BUGFIX_TICKET_PREFIXES:
            return "bugfix"
    return "product"


# ── Checkpoint (DRIFT-1 W2.T3b — intent-resume, outcome C) ───────────────────
#
# Per the T3a audit (.planning/drift-1/checkpoint-audit.json,
# action="add-new", reuse_path="init-pattern"), plan ganha checkpoint pra
# cobrir os 10 callsites interativos: ask_text de slug, ask em
# done-feature 4-paths + extension slug elicitation, ask em
# subtype-confirmation + bugfix-wave-b sub-question, ask de
# continuar/pausar a cada wave (A-E), ask_text de task-count em wave D,
# ask_three_paths em readiness-not-ready + subtype-stub. Mirrors
# ``_InitCheckpoint`` (engine/init.py:100-108) — outcome C, sem import
# de ``engine.qa.checkpoint`` (Decision 22).
#
# Refs:
#   - docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
#   - engine/init.py:100-108 (canonical template)


@dataclass
class _PlanCheckpoint:
    """State serialized before each ``question.ask*`` call in ``plan.run``.

    Carries ``feature_slug`` (quando ja resolvido), ``wave`` (label da
    wave corrente — "A".."E"), e ``ambiguity_id`` (identificador do
    sub-fluxo de ambiguidade quando aplicavel: ``"readiness-not-ready"``,
    ``"subtype-confirmation"``, ``"bugfix-wave-b"``, ``"done-feature"``,
    ``"subtype-stub-spike"`` etc.). Prompts antes da resolucao do slug
    recebem ``feature_slug=None``.
    """

    step: str
    at: str
    project_root: str
    intent_id: str | None = None
    feature_slug: str | None = None
    wave: str | None = None
    ambiguity_id: str | None = None


def _plan_checkpoint_path(project_root: Path) -> Path:
    return claude_dir(project_root) / ".plan-checkpoint.yaml"


# Os 4 helpers abaixo são thin shims sobre ``engine.utils.checkpoint_io`` +
# ``engine.utils.iso`` — consolidação dos 30 duplicates + 10 cópias de
# ``_utc_now_iso_*`` apontada pelos findings #5 e #21 do master review do
# PR #11. Os nomes ``_save_plan_checkpoint`` etc. permanecem como API
# privada do módulo para preservar os contracts dos testes em
# ``tests/unit/test_engine_plan_resume.py`` (Mandamento #2 — verde).


def _save_plan_checkpoint(cp: _PlanCheckpoint) -> None:
    """Persist the plan checkpoint atomically."""
    _save_yaml_checkpoint_io(
        _plan_checkpoint_path(Path(cp.project_root)),
        {
            "schema-version": 1,
            "step": cp.step,
            "at": cp.at,
            "project-root": cp.project_root,
            "intent-id": cp.intent_id,
            "feature-slug": cp.feature_slug,
            "wave": cp.wave,
            "ambiguity-id": cp.ambiguity_id,
        },
    )


def _load_plan_checkpoint(project_root: Path) -> dict[str, Any] | None:
    """Read the plan checkpoint, returning ``None`` when absent."""
    return _load_yaml_checkpoint_io(_plan_checkpoint_path(project_root))


def _clear_plan_checkpoint(project_root: Path) -> None:
    """Remove the checkpoint — best-effort; silent on OSError (idempotent)."""
    _clear_checkpoint_io(_plan_checkpoint_path(project_root))


def _utc_now_iso_plan() -> str:
    """ISO-8601 UTC timestamp — thin shim sobre ``engine.utils.iso``."""
    return _utc_now_iso_shared()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _is_valid_slug(value: str) -> bool:
    """Slug: kebab-case lowercase, 2..50 chars, alphanum + hyphens."""
    return bool(_SLUG_PATTERN.match(value))


def _forge_home() -> Path:
    from engine.utils.paths import forge_home as _fh

    return _fh()


def _templates_dir() -> Path:
    return _forge_home() / _TEMPLATES_SUBDIR


def _render_template(template_name: str, target: Path, slug: str) -> bool:
    """Copy `templates/{template_name}` to `target`. Returns True if newly created.

    Lightweight templating: replaces {{FEATURE_SLUG}} occurrences. Anything
    else stays verbatim — full template population is the user's (or Claude's)
    job between waves.
    """
    src = _templates_dir() / template_name
    if not src.is_file():
        raise FileNotFoundError(
            f"template '{template_name}' not found at {src}. "
            "Templates wave (1+2) must have shipped before forge plan can run."
        )
    if target.exists():
        return False
    ensure_dir(target.parent)
    raw = src.read_text(encoding="utf-8")
    raw = raw.replace("{{FEATURE_SLUG}}", slug)
    target.write_text(raw, encoding="utf-8")
    return True


def _resolve_features_root(project_root: Path, *, subtype: str = "product") -> Path:
    """Read workflow-config.paths.feature-roots if present, else default.

    When `subtype != "product"`, the path is rerooted under `non-product/`
    per `docs/design/05-filesystem-layout.md §3.5` — keeps refactor/spike/
    chore feature packages out of the product feature folder and out of
    the similarity-graph by convention.
    """
    cfg = read_yaml_or_default(workflow_config_path(project_root), {})
    custom_root: Path | None = None
    if isinstance(cfg, dict):
        paths = cfg.get("paths") or {}
        roots = paths.get("feature-roots") if isinstance(paths, dict) else None
        if isinstance(roots, list) and roots:
            head = roots[0]
            if isinstance(head, str):
                custom_root = (project_root / head).resolve()
        elif isinstance(roots, str):
            custom_root = (project_root / roots).resolve()

    if custom_root is not None:
        if subtype != "product":
            # Custom root is the *product* folder; non-product lives as
            # a sibling under the same parent.
            return (custom_root.parent / "non-product").resolve()
        return custom_root

    # Default per docs/design/05-filesystem-layout.md.
    base = project_root / "docs" / "feature-implementation-workflow"
    if subtype != "product":
        return (base / "non-product").resolve()
    return (base / "features").resolve()


def _feature_path(project_root: Path, slug: str, *, subtype: str = "product") -> Path:
    """Compute feature directory, honouring workflow-config override + subtype.

    For `subtype="product"` the layout is identical to the legacy v1.0
    path (`docs/feature-implementation-workflow/features/{slug}/`). For
    refactor/spike/chore the directory lives under `non-product/{slug}/`
    — see discipline §8 + filesystem-layout §3.5.
    """
    root = _resolve_features_root(project_root, subtype=subtype)
    # When subtype=product and override matches the default we still want
    # feature_dir's canonical layout.
    if subtype == "product":
        default = (
            project_root / "docs" / "feature-implementation-workflow" / "features"
        ).resolve()
        if root == default:
            return feature_dir(project_root, slug)
    return root / slug


def _initialize_status(slug: str, project_root: Path) -> L1State:
    """Ensure L1 status.json exists in `planning` and lock is held.

    Reads subtype from disk when status.json already exists (pre-Gap-2 files
    default to "product" automatically — see `engine.memory.l1`). The
    initial value isn't decided here — that happens via the conversational
    Cena 2.5 flow inside `run()`, which then calls
    `engine.memory.l1.set_subtype` to persist.
    """
    state = read_l1_status(slug, project_root)
    if state is None:
        state = L1State(
            feature_slug=slug,
            status="planning",
            last_action_at="",
            last_action_kind="plan-started",
            subtype="product",  # default; conductor may override via Cena 2.5
        )
        write_l1_status(state, project_root)
        return state
    if state.status not in {"planning", "deferred", "paused", "planned"}:
        # Status set by another command — refuse to clobber.
        raise SystemExit(
            f"forge plan: feature '{slug}' is in status '{state.status}'. "
            "Use the matching command (implement/verify/undo) instead."
        )
    if state.status == "deferred":
        state.status = "planning"
        state.last_action_kind = "plan-resumed"
        write_l1_status(state, project_root)
    return state


def _continue_or_pause(slug: str, wave_label: str) -> str:
    """Block on user input — accepts only `continuar` or `pausar`."""
    return question.ask(
        f"Status da Wave {wave_label}?",
        {"continuar": "seguir para próxima wave", "pausar": "salvar e parar"},
        allow_pause=True,
    )


def _persist_deferred(slug: str, project_root: Path, where: str) -> None:
    """Marca feature como deferred, libera phase_lock e emite copy de pausa.

    Libertar o lock é essencial — sem isso o próximo `forge plan {slug}` fica
    travado em "phase-locked by 'planning'" mesmo após pausa legítima.
    """
    state = read_l1_status(slug, project_root) or L1State(
        feature_slug=slug,
        status="deferred",
        last_action_at="",
        last_action_kind="plan-deferred",
    )
    state.status = "deferred"
    state.last_action_kind = f"plan-deferred-at-{where}"
    state.phase_lock = None
    write_l1_status(state, project_root)
    # Defensivo: garante que o lock saiu mesmo se write_l1_status acima
    # tiver pego raw com phase_lock antigo no payload.
    release_phase_lock(slug, project_root)
    append_history(
        slug,
        project_root,
        {"event": "plan-deferred", "where": where},
    )
    renderer.write("")
    renderer.write(mentor_calmo.pause_message(slug=slug, resume_command=f"forge plan {slug}"))


# ── Wave runners ─────────────────────────────────────────────────────────────


@dataclass
class WaveResult:
    artefacts: list[Path]
    deferred: bool


def _run_static_wave(
    label: str,
    templates: tuple[tuple[str, str], ...],
    slug: str,
    project_root: Path,
    feature_path: Path,
) -> WaveResult:
    """Render a wave's templates, narrate, then block on continuar/pausar."""
    renderer.write("")
    renderer.write(renderer.bold(f"⚡ Wave {label}"))
    created: list[Path] = []
    for template_name, output_name in templates:
        target = feature_path / output_name
        was_new = _render_template(template_name, target, slug)
        marker = "NEW " if was_new else "EXIST"
        renderer.write(f"  ├ {marker}  {target.relative_to(project_root)}")
        created.append(target)
    renderer.write("")
    renderer.write(
        f"Wave {label} — abra os artefatos no editor, preencha conforme "
        f"`agents/planning-conductor.md` §Phase 4, e digite 'continuar'."
    )
    append_history(
        slug,
        project_root,
        {
            "event": f"wave-{label.lower()}-rendered",
            "artefacts": [str(a.relative_to(project_root)) for a in created],
        },
    )

    choice = _continue_or_pause(slug, label)
    if choice == "pausar":
        _persist_deferred(slug, project_root, f"wave-{label.lower()}")
        return WaveResult(artefacts=created, deferred=True)

    append_history(slug, project_root, {"event": f"wave-{label.lower()}-acknowledged"})
    return WaveResult(artefacts=created, deferred=False)


def _ask_task_count() -> int:
    """Quantas tasks aprox? Aceita 1..30."""

    def _is_count(value: str) -> bool:
        try:
            n = int(value)
        except ValueError:
            return False
        return 1 <= n <= 30

    raw = question.ask_text(
        "Quantas tasks aproximadamente para essa feature? (1..30)",
        default="5",
        validator=_is_count,
        validator_hint="Digite um inteiro entre 1 e 30.",
    )
    return int(raw)


def _run_wave_d(
    slug: str,
    project_root: Path,
    feature_path: Path,
) -> WaveResult:
    """Wave D — task-breakdown + N task contracts."""
    renderer.write("")
    renderer.write(renderer.bold("⚡ Wave D — task contracts"))

    head_template, head_output = WAVE_D_HEAD_TEMPLATE
    breakdown_target = feature_path / head_output
    was_new = _render_template(head_template, breakdown_target, slug)
    marker = "NEW " if was_new else "EXIST"
    renderer.write(f"  ├ {marker}  {breakdown_target.relative_to(project_root)}")

    n = _ask_task_count()
    tasks_dir = ensure_dir(feature_path / "tasks")
    created: list[Path] = [breakdown_target]
    for idx in range(1, n + 1):
        task_id = f"TASK-{idx:04d}"
        target = tasks_dir / f"{task_id}.yaml"
        if target.exists():
            renderer.write(f"  ├ EXIST {target.relative_to(project_root)}")
            created.append(target)
            continue
        src = _templates_dir() / WAVE_D_TASK_TEMPLATE
        if not src.is_file():
            raise FileNotFoundError(
                f"template '{WAVE_D_TASK_TEMPLATE}' not found at {src}."
            )
        raw = src.read_text(encoding="utf-8")
        raw = raw.replace("{{FEATURE_SLUG}}", slug).replace("{{TASK_ID}}", task_id)
        target.write_text(raw, encoding="utf-8")
        renderer.write(f"  ├ NEW   {target.relative_to(project_root)}")
        created.append(target)

    renderer.write("")
    renderer.write(
        f"Wave D — {n} task contract(s) prontas pra preencher. "
        "Cada uma deve declarar allowed_files, validations e gates. "
        "Quando terminar, digite 'continuar'."
    )
    append_history(
        slug,
        project_root,
        {
            "event": "wave-d-rendered",
            "task-count": n,
            "artefacts": [str(p.relative_to(project_root)) for p in created],
        },
    )

    choice = _continue_or_pause(slug, "D")
    if choice == "pausar":
        _persist_deferred(slug, project_root, "wave-d")
        return WaveResult(artefacts=created, deferred=True)

    append_history(slug, project_root, {"event": "wave-d-acknowledged"})
    return WaveResult(artefacts=created, deferred=False)


def _parse_readiness_status(review_path: Path) -> str:
    """Look for the readiness_verdict.status block in the review markdown.

    Accepts either a fenced YAML block or a `status:` line nearby. Returns
    one of {ready, needs-fix, partial, blocked, unknown}. The template is
    expected to surface a fenced block with `readiness_verdict:` mapping.
    """
    if not review_path.exists():
        return "unknown"
    text = review_path.read_text(encoding="utf-8")
    match = re.search(
        r"readiness_verdict\s*:\s*[\s\S]*?status\s*:\s*['\"]?([a-z-]+)['\"]?",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().lower()
    fallback = re.search(r"^\s*status\s*:\s*([a-z-]+)\s*$", text, re.IGNORECASE | re.MULTILINE)
    return fallback.group(1).strip().lower() if fallback else "unknown"


def _run_wave_e(
    slug: str,
    project_root: Path,
    feature_path: Path,
) -> WaveResult:
    """Wave E — render readiness + handoff, then check verdict."""
    renderer.write("")
    renderer.write(renderer.bold("⚡ Wave E — readiness review"))
    created: list[Path] = []
    for template_name, output_name in WAVE_E_TEMPLATES:
        target = feature_path / output_name
        was_new = _render_template(template_name, target, slug)
        marker = "NEW " if was_new else "EXIST"
        renderer.write(f"  ├ {marker}  {target.relative_to(project_root)}")
        created.append(target)

    renderer.write("")
    renderer.write(
        "Wave E — preencha implementation-readiness-review.md (em especial "
        "o bloco `readiness_verdict.status`) e plan-feature-handoff.json. "
        "Digite 'continuar' quando estiver pronto."
    )
    append_history(slug, project_root, {"event": "wave-e-rendered"})

    choice = _continue_or_pause(slug, "E")
    if choice == "pausar":
        _persist_deferred(slug, project_root, "wave-e")
        return WaveResult(artefacts=created, deferred=True)

    review_path = feature_path / "implementation-readiness-review.md"
    verdict = _parse_readiness_status(review_path)
    renderer.write("")
    renderer.write(f"  readiness_verdict.status: {renderer.bold(verdict)}")
    append_history(
        slug,
        project_root,
        {"event": "wave-e-readiness-parsed", "verdict": verdict},
    )

    if verdict == "ready":
        return WaveResult(artefacts=created, deferred=False)

    # Not ready — surface the three legitimate paths.
    block = mentor_calmo.three_paths_block(
        gate_name="readiness não está em 'ready'",
        what_failed=(
            f"implementation-readiness-review.md tem status='{verdict}'. "
            "Sem readiness=ready, forge implement recusa começar."
        ),
        where=str(review_path.relative_to(project_root)),
        why=[
            "agents/readiness-reviewer.md exige readiness=ready pra dispatch",
            "task contracts não podem ser executados sem gate verde",
        ],
        paths=[
            {
                "label": "Re-revisar agora — eu re-renderizo as waves apontadas como gap",
                "motive": "se a falha é local (artefato A ou B), tem como fechar nesta sessão",
            },
            {
                "label": "Marcar como deferred — eu salvo o estado e você revisa offline",
                "motive": "use quando a decisão depende de outra pessoa ou input externo",
            },
            {
                "label": "Pausar e investigar manualmente",
                "motive": "mentor calmo não tenta heroicamente — você inspeciona e volta",
            },
        ],
    )
    renderer.write("")
    renderer.write(block)
    chosen = question.ask_three_paths("readiness-not-ready", [
        {"label": "Re-revisar agora", "motive": ""},
        {"label": "Deferir e salvar estado", "motive": ""},
        {"label": "Pausar e investigar", "motive": ""},
    ])
    if chosen == "a":
        renderer.write("Re-rodando Wave E após você ajustar os artefatos...")
        append_history(slug, project_root, {"event": "wave-e-rerun-requested"})
        return _run_wave_e(slug, project_root, feature_path)

    # b or c — both defer.
    _persist_deferred(slug, project_root, "wave-e-not-ready")
    return WaveResult(artefacts=created, deferred=True)


# ── Auto-resume ──────────────────────────────────────────────────────────────


def _next_wave_from_history(slug: str, project_root: Path) -> str:
    """Inspect history.jsonl and pick the next wave to (re)start."""
    from engine.memory.l1 import read_history

    events = read_history(slug, project_root)
    last_ack = ""
    for entry in reversed(events):
        kind = entry.get("kind", "")
        if kind.endswith("-acknowledged"):
            last_ack = kind
            break
    mapping = {
        "wave-a-acknowledged": "B",
        "wave-b-acknowledged": "C",
        "wave-c-acknowledged": "D",
        "wave-d-acknowledged": "E",
    }
    return mapping.get(last_ack, "A")


# ── Extension feature mechanic (Gap 9) ───────────────────────────────────────


def _default_extension_slug(parent_slug: str) -> str:
    """Heuristic default slug for an extension feature.

    Gap 9 — extends-feature mechanic. The conductor (Cena 1, 4º caminho)
    proposes ``{parent}-extension`` as a starting point; the user almost
    always customizes (e.g., ``lembrete-rega-push``) to reflect the actual
    delta scope. Validator EXT-003 guarantees the derived slug is never
    equal to the parent slug.
    """
    return f"{parent_slug}-extension"


def _import_parent_context(
    parent_slug: str, project_root: Path
) -> dict[str, Any]:
    """Read parent feature's L1 + key plan artefacts, return baseline dict.

    Gap 9 — extends-feature mechanic. The conductor calls this when the
    user chooses caminho 3 (Estender) in Cena 1 with state=done. The
    returned dict feeds the extension's context-pack so sub-agents
    (Wave A intake, Wave B/C/D) inherit baseline from the parent without
    re-eliciting — they only have to model the delta.

    Returns a dict with keys (any may be absent when parent's artefact
    wasn't written):

      - ``parent-slug``         : str (always present, mirrors input)
      - ``parent-state``        : str | None (status.json.state)
      - ``parent-shipped-at``   : str | None (status.json.shipped-at if set)
      - ``parent-hypothesis``   : dict | None (hypothesis.yaml)
      - ``parent-feature-dir``  : str | None (path to features/{parent}/ or
                                  non-product/{parent}/ as relative string;
                                  caller resolves vs project_root)

    Read-only; never writes. Best-effort: missing files do not raise — they
    just produce ``None`` entries (the extension feature can proceed; the
    sub-agent's context pack will say "parent's <artefact> absent").
    """
    out: dict[str, Any] = {
        "parent-slug": parent_slug,
        "parent-state": None,
        "parent-shipped-at": None,
        "parent-hypothesis": None,
        "parent-feature-dir": None,
    }
    parent_status = read_l1_status(parent_slug, project_root)
    if parent_status is not None:
        out["parent-state"] = parent_status.status
        # `shipped-at` lives in status.raw (free-form additive metadata) —
        # it isn't a canonical L1State field. Best-effort read.
        if isinstance(parent_status.raw, dict):
            shipped = parent_status.raw.get("shipped-at") or parent_status.raw.get(
                "shipped_at"
            )
            if isinstance(shipped, str) and shipped.strip():
                out["parent-shipped-at"] = shipped.strip()
    try:
        parent_hyp = read_hypothesis(parent_slug, project_root)
        if isinstance(parent_hyp, dict):
            out["parent-hypothesis"] = parent_hyp
    except Exception:  # noqa: BLE001 — best-effort: hypothesis may be malformed
        out["parent-hypothesis"] = None

    parent_subtype = current_subtype(parent_slug, project_root)
    parent_feature_dir = _feature_path(
        project_root, parent_slug, subtype=parent_subtype
    )
    if parent_feature_dir.is_dir():
        try:
            out["parent-feature-dir"] = str(
                parent_feature_dir.relative_to(project_root)
            )
        except ValueError:
            out["parent-feature-dir"] = str(parent_feature_dir)
    return out


def _create_extension_l1(
    parent_slug: str, child_slug: str, project_root: Path
) -> L1State:
    """Create the child's status.json + seed hypothesis.yaml as an extension.

    Gap 9 — extends-feature mechanic. Writes:
      - ``.claude/memory/L1/{child}/status.json`` with extends-feature +
        parent-feature pointing at ``parent_slug``, state=planning,
        subtype=product (extensions are always product-derived).
      - ``.claude/memory/L1/{child}/hypothesis.yaml`` seeded with the
        ``extends-feature`` + ``parent-feature`` fields so the conductor
        can read it on resume without re-asking.

    Does NOT acquire the phase lock — caller (`run()`) does that after
    this returns, per the engine's lifecycle. Does NOT write history —
    `run()` appends a ``plan-started`` entry after lock acquisition.

    Sanity guards (defensive — write-time enforcement reduz dependência
    do validator runtime, que pode não estar wired no cascade default):
      - ``child_slug != parent_slug`` (self-loop — EXT-003)
      - parent's status.json must exist (EXT-001)
      - ``parent_status.status == "done"`` (EXT-002 — extensions de
        feature ainda viva poluem a L1 da pai e quebram a invariante
        "1 feature = 1 ship moment")
    """
    if not parent_slug or not child_slug:
        raise ValueError("parent_slug and child_slug must be non-empty")
    if child_slug == parent_slug:
        raise ValueError(
            "extension slug cannot equal parent slug (sanity guard for EXT-003)"
        )
    parent_status = read_l1_status(parent_slug, project_root)
    if parent_status is None:
        raise ValueError(
            f"parent '{parent_slug}' has no status.json on disk; "
            "cannot create extension"
        )
    if parent_status.status != "done":
        raise ValueError(
            f"parent {parent_slug!r} has state={parent_status.status!r}; "
            "extension requires parent.state == 'done' (EXT-002)"
        )

    child_state = L1State(
        feature_slug=child_slug,
        status="planning",
        last_action_at="",
        last_action_kind="extension-created",
        subtype="product",  # extensions are product-derived (decided pra Gap 9)
        extends_feature=parent_slug,
        parent_feature=parent_slug,
    )

    # D-003: write hypothesis.yaml FIRST (planning artefact) and status.json
    # SECOND as the commit point. If hypothesis write fails, nothing is
    # persisted (no orphan status.json with extends-feature pointing nowhere
    # on resume). If the status.json write fails after a successful
    # hypothesis write, the orphan hypothesis is harmless — it has no
    # state.json sibling so resume won't activate the child L1, and the
    # next plan invocation overwrites it cleanly.
    write_hypothesis(
        child_slug,
        project_root,
        {
            "schema-version": 1,
            "feature-slug": child_slug,
            "subtype": "product",
            "extends-feature": parent_slug,
            "parent-feature": parent_slug,
            "shape": "extension",
            "confidence": 0.0,  # delta intent not elicited yet
        },
    )
    write_l1_status(child_state, project_root)
    return child_state


def _handle_done_feature_branch(
    parent_slug: str, project_root: Path
) -> Optional[str]:
    """Offer the 4-caminhos when user invokes `forge plan` on a done feature.

    Gap 9 — Cena 1 of forge-plan-roteiro.md, Edge case 1.5. Renders the
    four paths interactively, asks the user, and:
      - caminho 1 (Retomar): returns the parent slug — caller flips
        status back to planning and re-plans (existing behavior; rare).
      - caminho 2 (Nova): returns None — caller exits this branch and
        treats the run as a no-op (user must re-invoke with a fresh slug).
      - caminho 3 (Estender): elicits derived slug, creates child L1,
        returns the **child slug** so the caller continues with it.
      - caminho 4 (Abortar): returns None — caller exits cleanly.

    Returns the slug to continue with, or None when the caller should exit.
    Raises ``PromptAbortedError`` when user types ``para``.
    """
    parent_status = read_l1_status(parent_slug, project_root)
    if parent_status is None or parent_status.status != "done":
        # Defensive: caller should only invoke this when state=done. Treat
        # any other state as a no-op (return parent slug → caller proceeds
        # with normal flow, which will re-check state).
        return parent_slug

    renderer.write("")
    renderer.write(
        renderer.bold(
            f"Detectei feature '{parent_slug}' já feita (state=done)."
        )
    )
    renderer.write("")
    renderer.write("Quatro caminhos:")
    choice = question.ask(
        "O que você quer?",
        {
            "1": "Retomar (re-plan inteiro — descarta artefatos, recomeça)",
            "2": "Começar feature nova (saio agora — invoque com slug novo)",
            "3": "Estender (novo slug derivado herda contexto da pai — Gap 9)",
            "4": "Abortar",
        },
        allow_pause=True,
    )

    if choice == "1":
        # Replan — caller flips parent state back to planning + re-runs.
        # This is rare (replan of a done feature usually means a major
        # pivot) but legitimate.
        append_history(
            parent_slug,
            project_root,
            {"event": "done-feature-replan-requested"},
        )
        # Flip state so _initialize_status doesn't reject.
        parent_status.status = "planning"
        parent_status.last_action_kind = "done-feature-replan"
        write_l1_status(parent_status, project_root)
        return parent_slug

    if choice == "2":
        renderer.write("")
        renderer.write(
            renderer.dim(
                "Beleza. Re-invoque `forge plan {novo-slug}` quando estiver pronto."
            )
        )
        return None

    if choice == "3":
        # Extension branch — elicit derived slug, create child L1, return
        # the child slug so caller continues with it.
        default_child = _default_extension_slug(parent_slug)
        renderer.write("")
        renderer.write(
            f"Slug derivado proposto: {renderer.bold(default_child)}"
        )
        renderer.write(
            renderer.dim(
                "Aceita ou customiza? (digite o slug ou ENTER pra aceitar)"
            )
        )

        # Loop until we get a slug that's valid, != parent, and not already
        # in L1 (or user picks "abortar" via PromptAbortedError).
        while True:
            candidate = question.ask_text(
                "Slug derivado:",
                default=default_child,
                validator=_is_valid_slug,
                validator_hint=(
                    "kebab-case lowercase, 2..50 chars, deve começar com letra."
                ),
            )
            if candidate == parent_slug:
                renderer.write(
                    renderer.colored(
                        "Slug derivado não pode ser igual ao slug da pai. "
                        "Tente outro.",
                        "yellow",
                    )
                )
                continue
            existing = read_l1_status(candidate, project_root)
            if existing is not None:
                # Slug duplicate — surface 3-caminhos.
                renderer.write("")
                renderer.write(
                    renderer.bold(
                        f"🛑 Slug '{candidate}' já existe em L1 "
                        f"(state={existing.status})."
                    )
                )
                dup_choice = question.ask_three_paths(
                    "slug-duplicate-on-extension",
                    [
                        {"label": "Escolher outro slug derivado", "motive": ""},
                        {
                            "label": "Abortar a extension (volta ao prompt)",
                            "motive": "",
                        },
                        {
                            "label": (
                                "Pisar no L1 existente (raro — exige "
                                "`forge undo` antes; abortando aqui)"
                            ),
                            "motive": "",
                        },
                    ],
                )
                if dup_choice == "a":
                    continue
                # b or c — both abort the extension flow. Caminho c shown for
                # discipline §1 (exactly 3 paths) but resolution is manual.
                renderer.write("")
                renderer.write(
                    renderer.dim(
                        f"Abortado. Nada criado. Use `forge undo {candidate}` "
                        "se quiser limpar o L1 existente antes de tentar."
                    )
                )
                return None
            # Valid + unique — proceed to creation.
            break

        _create_extension_l1(parent_slug, candidate, project_root)
        append_history(
            candidate,
            project_root,
            {
                "event": "extension-created",
                "parent": parent_slug,
            },
        )
        append_history(
            parent_slug,
            project_root,
            {
                "event": "extension-spawned",
                "child": candidate,
            },
        )
        renderer.write("")
        renderer.write(
            renderer.dim(
                f"Extension '{candidate}' criada. extends-feature: "
                f"{parent_slug}. Continuando com Cena 2 (source inquiry)."
            )
        )
        return candidate

    # choice == "4"
    renderer.write("")
    renderer.write(renderer.dim("Abortado. Nada mais escrito."))
    return None


# ── Slug elicitation ─────────────────────────────────────────────────────────


def _elicit_slug(argv_slug: Optional[str], project_root: Optional[Path] = None) -> str:
    if argv_slug:
        if not _is_valid_slug(argv_slug):
            raise SystemExit(
                f"forge plan: slug '{argv_slug}' invalid. "
                "kebab-case lowercase, 2..50 chars, [a-z0-9-]."
            )
        return argv_slug

    # DRIFT-1 W2.T3b — persist checkpoint com intent-id determinado da
    # pergunta de slug ANTES de invocar ``question.ask_text``. On exit-2 +
    # re-invoke, ``question.ask_text`` finds the matching forge-response
    # and returns the value without re-prompting. Outcome C — per-subcommand
    # dataclass, no import from ``engine.qa.checkpoint``. ``project_root``
    # eh Optional pra preservar backward-compat com callers de teste que
    # invocavam ``_elicit_slug(argv_slug)`` sem o segundo arg; quando None,
    # o save eh pulado (smoke-call sem side-effect em disco).
    if project_root is not None:
        _save_plan_checkpoint(
            _PlanCheckpoint(
                step="step-elicit-slug",
                at=_utc_now_iso_plan(),
                project_root=str(project_root),
                intent_id=question.stable_intent_id(
                    "ask_text",
                    "Qual o slug da feature? (kebab-case, ex.: lembrete-rega)",
                    None,
                    extra={
                        "default": None,
                        "min-selected": None,
                        "validator-hint": (
                            "kebab-case lowercase, 2..50 chars, deve começar com letra."
                        ),
                    },
                ),
                feature_slug=None,
            )
        )
    return question.ask_text(
        "Qual o slug da feature? (kebab-case, ex.: lembrete-rega)",
        validator=_is_valid_slug,
        validator_hint="kebab-case lowercase, 2..50 chars, deve começar com letra.",
    )


def _confirm_subtype_inference(inferred: str) -> str:
    """Cena 2.5 — confirm or override subtype inference.

    Returns the final subtype string. Defaults to "product" when the user
    overrides ("não, é feature de produto"). Discipline §8 — non-product
    feature track lives behind conversational confirmation, not a flag.
    """
    if inferred == "product":
        return "product"
    pretty = {
        "refactor": "refactor (comportamento inalterado, sem Wave B, sem PRD)",
        "bugfix": (
            "bugfix (restaurar comportamento correto — intake compacto, "
            "Wave B conditional, retro 5-whys)"
        ),
        "spike": "spike (investigação técnica — stub em v1.0)",
        "chore": "chore (atualização de dep / cleanup — stub em v1.0)",
    }[inferred]
    choice = question.ask(
        f"Isso parece {pretty}. Confirma?",
        {
            "sim": f"trato como subtype={inferred}",
            "nao": "é feature de produto padrão (subtype=product)",
        },
        allow_pause=False,
    )
    if choice == "sim":
        return inferred
    return "product"


def _elicit_bugfix_wave_b_required() -> bool:
    """Cena 2.5 sub-question for subtype=bugfix.

    Discipline §8 (Gap 1) — bugfix Wave B is **conditional** on whether
    the bug touches UI/observable behavior:
      - True  → UI/observable bug; Wave B runs to model contracts
      - False → logic-only bug; Wave B skipped (refactor-like)

    Returns the boolean answer. Persisted by the caller into
    `hypothesis.yaml.wave_b_required` so resume reads from disk.
    """
    choice = question.ask(
        "Esse bug envolve mudança de UI ou de comportamento observável?",
        {
            "sim": "Wave B roda (modela contratos antes do fix)",
            "nao": "logic-only — Wave B skipada (sem screen-analysis / contracts)",
        },
        allow_pause=False,
    )
    return choice == "sim"


def _read_hypothesis_wave_b_required(
    slug: str, project_root: Path
) -> Optional[bool]:
    """Read `hypothesis.yaml.wave_b_required` (Gap 1 — bugfix sub-question).

    Returns:
      - True / False when the field is present and boolean
      - None when status.json's subtype != "bugfix", or when the field
        is absent / non-boolean (caller treats None as "not yet elicited"
        and re-asks; resume reads from disk after the first elicitation)
    """
    from engine.memory.l1 import read_hypothesis

    data = read_hypothesis(slug, project_root) or {}
    raw = data.get("wave_b_required")
    if isinstance(raw, bool):
        return raw
    return None


def _persist_hypothesis_wave_b_required(
    slug: str, project_root: Path, value: bool
) -> None:
    """Persist `wave_b_required` to `hypothesis.yaml` (additive write).

    Discipline §8 (Gap 1) — the bugfix Wave B sub-question answer is
    written here so resume reads it from disk without re-asking. Other
    fields in hypothesis.yaml are preserved (the conductor fills them
    during Phase 1 separately).
    """
    from engine.memory.l1 import read_hypothesis, write_hypothesis

    data = read_hypothesis(slug, project_root) or {}
    data["wave_b_required"] = bool(value)
    # Keep schema-version + subtype consistent when this is the first
    # hypothesis write (greenfield bugfix).
    data.setdefault("schema-version", 1)
    data.setdefault("feature-slug", slug)
    data.setdefault("subtype", "bugfix")
    write_hypothesis(slug, project_root, data)


def _handle_stub_subtype(subtype: str, slug: str, project_root: Path) -> int:
    """3-caminhos block for spike/chore stubs (v1.0).

    Discipline §8 documents that spike + chore land in v1.1+. This handler
    surfaces the three legitimate paths interactively and returns the
    appropriate exit code based on user choice. Does NOT acquire phase
    lock — caller has already done so.
    """
    renderer.write("")
    renderer.write(renderer.bold(f"🛑 Subtype '{subtype}' ainda não tem implementação completa em v1.0"))
    renderer.write("")
    renderer.write(
        f"v1.0 ship `refactor` por completo. `{subtype}` está programado pra "
        "v1.1+ — sem improviso aqui."
    )
    renderer.write("")
    renderer.write("Três caminhos:")
    renderer.write("")
    renderer.write(
        "  1) Tratar como feature padrão (subtype=product)\n"
        "     Você terá Waves B/C completas — sub-agentes vão pedir contexto\n"
        "     que pode parecer artificial pro caso. Faz sentido quando o\n"
        f"     {subtype} tem dimensão de comportamento real."
    )
    renderer.write("")
    renderer.write(
        "  2) Pausar e esperar v1.1+\n"
        "     Marco status como deferred — quando o subtype completo chegar\n"
        "     em v1.1+, retomamos daqui."
    )
    renderer.write("")
    renderer.write(
        "  3) Abortar\n"
        "     Sai do forge plan, faz o trabalho fora do pipeline. Não viola\n"
        "     disciplina; só não fica trackeado."
    )
    renderer.write("")
    chosen = question.ask_three_paths(
        f"subtype-stub-{subtype}",
        [
            {"label": "Tratar como product", "motive": ""},
            {"label": "Pausar até v1.1+", "motive": ""},
            {"label": "Abortar", "motive": ""},
        ],
    )
    if chosen == "a":
        set_subtype(slug, project_root, "product")
        append_history(
            slug,
            project_root,
            {"event": "subtype-stub-promoted-to-product", "from": subtype},
        )
        renderer.write("")
        renderer.write(
            renderer.dim(
                f"Subtype reclassificado para 'product'. Continuando Waves A-E "
                "padrão."
            )
        )
        return 0  # caller re-routes to product flow
    if chosen == "b":
        append_history(
            slug,
            project_root,
            {"event": "subtype-stub-deferred", "subtype": subtype},
        )
        _persist_deferred(slug, project_root, f"subtype-stub-{subtype}")
        return 130  # paused-like exit
    # chosen == "c"
    append_history(
        slug,
        project_root,
        {"event": "subtype-stub-aborted", "subtype": subtype},
    )
    release_phase_lock(slug, project_root)
    renderer.write("")
    renderer.write(renderer.dim("Abortado. Nada mais escrito."))
    return 3


# ── Entry point ──────────────────────────────────────────────────────────────


def _resolve_subtype_for_run(slug: str, project_root: Path) -> str:
    """Resolve subtype for this run.

    Precedence:
      1. Existing status.json.subtype (resume case — never re-ask).
      2. Inference from argv input via `detect_subtype_from_input` plus
         interactive confirmation via `_confirm_subtype_inference`.
      3. Fallback "product" when no signal.

    Cena 2.5 (forge-plan-roteiro.md) covers the user-facing flow. This
    helper is the engine-side implementation.
    """
    existing = current_subtype(slug, project_root)
    if existing != "product":
        return existing
    # First-time inference can be expanded to read source-inquiry input
    # captured in Cena 2 — for v1.0 the engine narrates and conductor
    # supplies the inference via the conversational layer. We bias
    # toward asking explicitly only when there's already a hint in the
    # slug itself (low-noise heuristic).
    inferred = detect_subtype_from_input(slug)
    if inferred == "product":
        return "product"
    return _confirm_subtype_inference(inferred)


def _run_waves_for_subtype(
    subtype: str,
    starting_wave: str,
    slug: str,
    project_root: Path,
    feature_path: Path,
    *,
    wave_b_required: Optional[bool] = None,
) -> int:
    """Dispatch waves according to subtype. Returns exit code (0 ok, 130 paused).

    Discipline §8: refactor skips Wave B unconditionally. Bugfix
    branches on `wave_b_required` (Cena 2.5 sub-question — see
    `agents/planning-conductor.md` Phase 1 step 4). Spike/chore land
    in the stub handler BEFORE this function is called — if we get
    here with those subtypes, treat as product (defensive — sub-agents
    will surface).
    """
    order = _wave_order_for_subtype(subtype, wave_b_required=wave_b_required)
    try:
        start_idx = order.index(starting_wave)
    except ValueError:
        # Starting wave from history isn't in this subtype's order (e.g.
        # resumed in Wave B but subtype is refactor). Restart from the
        # subtype's first wave.
        start_idx = 0
    if subtype == "refactor":
        wave_a_templates = WAVE_A_REFACTOR_TEMPLATES
    elif subtype == "bugfix":
        wave_a_templates = WAVE_A_BUGFIX_TEMPLATES
    else:
        wave_a_templates = WAVE_A_TEMPLATES

    for wave_label in order[start_idx:]:
        if wave_label == "A":
            result = _run_static_wave(
                "A", wave_a_templates, slug, project_root, feature_path
            )
        elif wave_label == "B":
            result = _run_static_wave(
                "B", WAVE_B_TEMPLATES, slug, project_root, feature_path
            )
        elif wave_label == "C":
            result = _run_static_wave(
                "C", WAVE_C_TEMPLATES, slug, project_root, feature_path
            )
        elif wave_label == "D":
            result = _run_wave_d(slug, project_root, feature_path)
        else:  # E
            result = _run_wave_e(slug, project_root, feature_path)

        if result.deferred:
            # Paused — caller distinguishes "done" (0) from "paused" (130)
            # per the run() docstring contract: '0=ok, 130=paused, other=hard'.
            # Returning 0 here previously caused the caller to mark a paused
            # feature as planned, silently losing the deferred state.
            return 130
    return 0


def run(argv: list[str]) -> int:
    """`forge plan [feature-slug]` — orchestrate Waves per subtype.

    Returns an integer exit code (0=ok, 130=paused, other=hard gate).
    """
    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        sys.stderr.write(f"forge plan: {exc}\n")
        return 2

    argv_slug = argv[0] if argv else None
    try:
        slug = _elicit_slug(argv_slug, project_root)
    except PromptAbortedError:
        sys.stderr.write("\n— interrompido antes do slug, nada salvo.\n")
        return 130

    # DRIFT-1 W2.T3b — agora que temos slug, atualiza checkpoint com
    # feature_slug; demais prompts deste handler herdam intent-resume via
    # question.ask*. Outcome C — sem import de engine.qa.checkpoint.
    _save_plan_checkpoint(
        _PlanCheckpoint(
            step="step-post-slug",
            at=_utc_now_iso_plan(),
            project_root=str(project_root),
            intent_id=None,
            feature_slug=slug,
        )
    )

    # Gap 9 — Cena 1 extension branch. When the requested slug exists in
    # L1 with state=done, offer the 4-caminhos (Retomar / Nova / Estender /
    # Abortar). The "Estender" path creates a NEW child slug + L1; the run
    # then continues with that child slug. Other paths either flip the
    # parent back to planning (Retomar) or exit cleanly.
    existing_status = read_l1_status(slug, project_root)
    if existing_status is not None and existing_status.status == "done":
        try:
            resolved_slug = _handle_done_feature_branch(slug, project_root)
        except PromptAbortedError:
            sys.stderr.write(
                "\n— interrompido no caminho extension, nada salvo.\n"
            )
            return 130
        if resolved_slug is None:
            # User chose "nova" or "abortar" — exit cleanly without touching
            # the parent's status (it remains in `done`).
            return 0
        slug = resolved_slug

    # Status + phase lock. Subtype resolved AFTER status is created so the
    # default ("product") seeds correctly for greenfield features.
    state = _initialize_status(slug, project_root)
    if not acquire_phase_lock(slug, project_root, "planning"):
        current = read_l1_status(slug, project_root)
        held = current.phase_lock if current else "?"
        sys.stderr.write(
            f"forge plan: '{slug}' phase-locked by '{held}'. "
            "Run `forge undo` to release, or wait for the other command to finish.\n"
        )
        return 3

    # Cena 2.5 — subtype inference + confirmation. Persisted before any
    # wave renders so resume sees the same subtype.
    try:
        subtype = _resolve_subtype_for_run(slug, project_root)
    except PromptAbortedError:
        _persist_deferred(slug, project_root, "subtype-prompt")
        return 130
    if subtype != state.subtype:
        set_subtype(slug, project_root, subtype)
        append_history(
            slug,
            project_root,
            {"event": "subtype-set", "subtype": subtype},
        )

    feature_path = _feature_path(project_root, slug, subtype=subtype)
    ensure_dir(feature_path)

    # Cinematic header.
    subtype_badge = "" if subtype == "product" else f" · subtype={subtype}"
    renderer.write("")
    renderer.write(
        renderer.box(
            f"feature-forge · plan · {slug}{subtype_badge}",
            [
                "Mentor calmo. Sem invenção. Sem pressa.",
                f"Artefatos em: {feature_path.relative_to(project_root)}",
            ],
            width=72,
        )
    )

    # Spike + chore stubs (discipline §8 — v1.0 ships refactor + bugfix only).
    if subtype in {"spike", "chore"}:
        rc = _handle_stub_subtype(subtype, slug, project_root)
        if rc != 0:
            return rc
        # User chose "treat as product" — recompute path + continue.
        subtype = "product"
        feature_path = _feature_path(project_root, slug, subtype=subtype)
        ensure_dir(feature_path)

    # Bugfix Wave B sub-question (Gap 1 — discipline §8). Asked once
    # right after subtype confirmation; persisted in hypothesis.yaml so
    # resume reads from disk and never re-asks.
    wave_b_required: Optional[bool] = None
    if subtype == "bugfix":
        wave_b_required = _read_hypothesis_wave_b_required(slug, project_root)
        if wave_b_required is None:
            try:
                wave_b_required = _elicit_bugfix_wave_b_required()
            except PromptAbortedError:
                _persist_deferred(slug, project_root, "bugfix-wave-b-prompt")
                return 130
            _persist_hypothesis_wave_b_required(slug, project_root, wave_b_required)
            append_history(
                slug,
                project_root,
                {
                    "event": "bugfix-wave-b-required-set",
                    "wave_b_required": wave_b_required,
                },
            )

    # Resume detection — when status was already planning + history exists.
    starting_wave = "A"
    if state.status == "planning" and (feature_path / "feature-intake.md").exists():
        starting_wave = _next_wave_from_history(slug, project_root)
        renderer.write("")
        renderer.write(
            renderer.dim(
                f"Detectei plano em andamento — retomando na Wave {starting_wave}."
            )
        )
        append_history(slug, project_root, {"event": "plan-resumed", "wave": starting_wave})

    # Wave dispatch loop (subtype-aware; bugfix branches on wave_b_required).
    try:
        rc = _run_waves_for_subtype(
            subtype,
            starting_wave,
            slug,
            project_root,
            feature_path,
            wave_b_required=wave_b_required,
        )
        if rc != 0:
            return rc
    except PromptAbortedError:
        _persist_deferred(slug, project_root, "user-pause")
        return 130

    # All waves consumed. Mark planned and close out.
    final_state = read_l1_status(slug, project_root) or state
    final_state.status = "planned"
    final_state.last_action_kind = "plan-completed"
    final_state.phase_lock = None
    write_l1_status(final_state, project_root)
    append_history(slug, project_root, {"event": "plan-completed"})

    if subtype == "product":
        artefact_count = "16"
    elif subtype == "refactor":
        artefact_count = "stripped (subtype=refactor)"
    elif subtype == "bugfix":
        artefact_count = (
            "focused (subtype=bugfix · Wave B "
            + ("rodou" if wave_b_required else "skipada")
            + ")"
        )
    else:
        artefact_count = f"variant (subtype={subtype})"
    renderer.write("")
    renderer.write(
        renderer.box(
            f"feature-forge · {slug} · plan ready{subtype_badge}",
            [
                f"{artefact_count} artefatos renderizados",
                "readiness_verdict.status: ready",
                "",
                "Próximo: forge implement " + slug,
            ],
            width=72,
        )
    )
    # DRIFT-1 W2.T3b — clean completion clears the intent-resume checkpoint
    # (Outcome C). Paused/deferred branches DELIBERATELY preserve it for
    # forensic resume; only the planned-and-ready path clears.
    _clear_plan_checkpoint(project_root)
    return 0


def record_external_dep(
    slug: str,
    project_root: Path,
    *,
    ticket: str,
    integration: str,
    description: str,
    task_hint: str,
    blocking: bool = True,
) -> dict[str, Any]:
    """Persist an external dependency captured during Phase 2/3 elicitation.

    Discipline §9 — engine helper invoked by planning-conductor when the
    user confirms a concrete external dep. Writes to
    `.claude/memory/L1/{slug}/elicitation.yaml.external-deps[]` so Wave D
    (task-contract-writer) can read it from the context pack and emit
    `depends_on_external` entries on the right tasks.

    Returns the entry written (with a `captured-at` ISO 8601 timestamp).

    Args:
        slug: feature slug.
        project_root: project root.
        ticket: ticket id (e.g., "BACKEND-1284"). Cannot be empty.
        integration: "jira" | "linear" | "github-issues" | "manual".
        description: free-form description.
        task_hint: TASK-NNNN id OR layer name ("shared-data", "android-ui",
            ...) that the dep applies to. task-contract-writer resolves
            this at Wave D.
        blocking: True (default) makes implement refuse; False is
            informational only.
    """
    if not ticket:
        raise ValueError("ticket id cannot be empty (discipline §9)")
    if not task_hint:
        raise ValueError("task_hint required so Wave D can place the dep")

    from typing import cast

    entry: dict[str, Any] = {
        "task-hint": task_hint,
        "ticket": ticket,
        "integration": integration,
        "description": description,
        "blocking": bool(blocking),
        "captured-at": _utc_now_iso(),
    }

    existing = read_elicitation(slug, project_root) or {}
    deps = existing.get("external-deps")
    if not isinstance(deps, list):
        deps = []
    # Dedupe by (ticket, task-hint) — re-elicitation should not create
    # phantom duplicates.
    sig = (entry["ticket"], entry["task-hint"])
    deps = [
        d for d in deps
        if not (
            isinstance(d, dict)
            and (d.get("ticket"), d.get("task-hint")) == sig
        )
    ]
    deps.append(entry)
    existing["external-deps"] = deps
    write_elicitation(slug, project_root, existing)
    append_history(
        slug,
        project_root,
        {
            "event": "external-dep-captured",
            "ticket": ticket,
            "task-hint": task_hint,
            "blocking": blocking,
        },
    )
    return cast(dict[str, Any], entry)


def _utc_now_iso() -> str:
    """ISO 8601 UTC with second precision and trailing Z — thin shim sobre ``engine.utils.iso``."""
    return _utc_now_iso_shared()


# Re-export for cli dispatcher + test surface.
__all__ = [
    "run",
    "detect_subtype_from_input",
    "record_external_dep",
    "_wave_order_for_subtype",
    # Gap 9 — extends-feature mechanic helpers (test surface).
    "_default_extension_slug",
    "_import_parent_context",
    "_create_extension_l1",
    "_handle_done_feature_branch",
]
