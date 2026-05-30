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
from pathlib import Path
from typing import Optional

from engine.memory.l1 import (
    L1State,
    acquire_phase_lock,
    append_history,
    read_l1_status,
    release_phase_lock,
    write_l1_status,
)
from engine.persona import mentor_calmo
from engine.ui import question, renderer
from engine.ui.question import PromptAbortedError
from engine.utils.paths import (
    ProjectRootNotFoundError,
    ensure_dir,
    feature_dir,
    find_project_root,
    workflow_config_path,
)
from engine.utils.yaml_io import read_yaml_or_default

# ── Constants ────────────────────────────────────────────────────────────────

_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,48}[a-z0-9]$")
_TEMPLATES_SUBDIR = "templates"

WAVE_A_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("feature-intake.template.md", "feature-intake.md"),
    ("feature-prd.template.md", "feature-prd.md"),
)

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

# Wave registry — single source of truth used by the loop + auto-resume.
_WAVE_ORDER: tuple[str, ...] = ("A", "B", "C", "D", "E")


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


def _resolve_features_root(project_root: Path) -> Path:
    """Read workflow-config.paths.feature-roots if present, else default."""
    cfg = read_yaml_or_default(workflow_config_path(project_root), {})
    if isinstance(cfg, dict):
        paths = cfg.get("paths") or {}
        roots = paths.get("feature-roots") if isinstance(paths, dict) else None
        if isinstance(roots, list) and roots:
            head = roots[0]
            if isinstance(head, str):
                return (project_root / head).resolve()
        elif isinstance(roots, str):
            return (project_root / roots).resolve()
    # Default per docs/design/05-filesystem-layout.md.
    return (project_root / "docs" / "feature-implementation-workflow" / "features").resolve()


def _feature_path(project_root: Path, slug: str) -> Path:
    """Compute feature directory, honouring workflow-config override."""
    root = _resolve_features_root(project_root)
    # When override matches the default we still want feature_dir's layout.
    default = (
        project_root / "docs" / "feature-implementation-workflow" / "features"
    ).resolve()
    if root == default:
        return feature_dir(project_root, slug)
    return root / slug


def _initialize_status(slug: str, project_root: Path) -> L1State:
    """Ensure L1 status.json exists in `planning` and lock is held."""
    state = read_l1_status(slug, project_root)
    if state is None:
        state = L1State(
            feature_slug=slug,
            status="planning",
            last_action_at="",
            last_action_kind="plan-started",
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


# ── Slug elicitation ─────────────────────────────────────────────────────────


def _elicit_slug(argv_slug: Optional[str]) -> str:
    if argv_slug:
        if not _is_valid_slug(argv_slug):
            raise SystemExit(
                f"forge plan: slug '{argv_slug}' invalid. "
                "kebab-case lowercase, 2..50 chars, [a-z0-9-]."
            )
        return argv_slug
    return question.ask_text(
        "Qual o slug da feature? (kebab-case, ex.: lembrete-rega)",
        validator=_is_valid_slug,
        validator_hint="kebab-case lowercase, 2..50 chars, deve começar com letra.",
    )


# ── Entry point ──────────────────────────────────────────────────────────────


def run(argv: list[str]) -> int:
    """`forge plan [feature-slug]` — orchestrate Waves A–E.

    Returns an integer exit code (0=ok, 130=paused, other=hard gate).
    """
    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        sys.stderr.write(f"forge plan: {exc}\n")
        return 2

    argv_slug = argv[0] if argv else None
    try:
        slug = _elicit_slug(argv_slug)
    except PromptAbortedError:
        sys.stderr.write("\n— interrompido antes do slug, nada salvo.\n")
        return 130

    feature_path = _feature_path(project_root, slug)
    ensure_dir(feature_path)

    # Status + phase lock.
    state = _initialize_status(slug, project_root)
    if not acquire_phase_lock(slug, project_root, "planning"):
        current = read_l1_status(slug, project_root)
        held = current.phase_lock if current else "?"
        sys.stderr.write(
            f"forge plan: '{slug}' phase-locked by '{held}'. "
            "Run `forge undo` to release, or wait for the other command to finish.\n"
        )
        return 3

    # Cinematic header.
    renderer.write("")
    renderer.write(
        renderer.box(
            f"feature-forge · plan · {slug}",
            [
                "Mentor calmo. Sem invenção. Sem pressa.",
                f"Artefatos em: {feature_path.relative_to(project_root)}",
            ],
            width=72,
        )
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

    # Wave dispatch loop.
    try:
        start_idx = _WAVE_ORDER.index(starting_wave)
        for wave_label in _WAVE_ORDER[start_idx:]:
            if wave_label == "A":
                result = _run_static_wave(
                    "A", WAVE_A_TEMPLATES, slug, project_root, feature_path
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
                return 0
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

    renderer.write("")
    renderer.write(
        renderer.box(
            f"feature-forge · {slug} · plan ready",
            [
                "16 artefatos renderizados",
                "readiness_verdict.status: ready",
                "",
                "Próximo: forge implement " + slug,
            ],
            width=72,
        )
    )
    return 0


# Re-export for cli dispatcher.
__all__ = ["run"]
