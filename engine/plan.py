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

import json
import re
import shutil
import sys
from dataclasses import dataclass
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
from engine.ui.exit_codes import (
    ERR_ABORTED,
    ERR_LOCKED,
    ERR_PROJECT_NOT_FOUND,
    fail_with_tag,
)
from engine.ui.question import PromptAbortedError
from engine.utils.paths import (
    ProjectRootNotFoundError,
    claude_dir,
    ensure_dir,
    feature_dir,
    feature_path as _feature_path,
    find_project_root,
    workflow_config_path,
)
from engine.utils.yaml_io import read_yaml_or_default, write_yaml
from engine.utils.checkpoint_io import (
    clear_checkpoint as _clear_checkpoint_io,
    load_yaml_checkpoint as _load_yaml_checkpoint_io,
    save_yaml_checkpoint as _save_yaml_checkpoint_io,
)
from engine.utils.iso import utc_now_iso

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


# Os helpers abaixo são thin shims sobre ``engine.utils.checkpoint_io`` —
# consolidação dos 30 duplicates apontada pelos findings #5 e #21 do master
# review do PR #11. Os nomes ``_save_plan_checkpoint`` etc. permanecem como
# API privada do módulo para preservar os contracts dos testes em
# ``tests/unit/test_engine_plan_resume.py`` (Mandamento #2 — verde).
# L-03 (PR #remediation): ``_utc_now_iso_*`` shims removidos; callers
# usam ``utc_now_iso`` direto de ``engine.utils.iso``.


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


# ── Helpers ──────────────────────────────────────────────────────────────────


def _is_valid_slug(value: str) -> bool:
    """Slug: kebab-case lowercase, 2..50 chars, alphanum + hyphens."""
    return bool(_SLUG_PATTERN.match(value))


# Front-door (spec §4 C3): slug derivado de ticket/frase vive na casa
# canônica `engine.utils.slug`. Re-exportado com o nome interno usado por
# `run()`/`_elicit_slug`. Reuso no nível do módulo compartilhado (Mandamento 3) —
# mesma casa que `kebabify`, mas char-level (ver nota de divergência em slug.py).
from engine.utils.slug import derive_slug as _derive_slug  # noqa: E402


def _looks_like_ticket(text: str) -> bool:
    """True quando o argv INTEIRO é um ticket-id (ex.: `IN-37234`).

    Reusa `_TICKET_PATTERN` (~L163) — mesma fonte de verdade que o
    subtype-detection já usa; nenhum regex paralelo (Mandamento 3). Usa
    `fullmatch` (não `search`): uma frase que só MENCIONA um ticket (ex.:
    `"fix IN-123 agora"`) é frase livre, não um ticket-id — vira `text`, não
    `ticket`. Assim o `source-ref` do intake só carrega `ticket` quando o
    argv é, de fato, uma referência verificável.
    """
    return _TICKET_PATTERN.fullmatch((text or "").strip()) is not None


def _yaml_double_quote_safe(value: str) -> str:
    """Sanitiza `value` pra entrar num scalar YAML *double-quoted* do template.

    O `feature-intake.md` declara `source-ref: "{{source_ref_or_none}}"` (scalar
    entre aspas duplas, source-of-truth do conductor). Um valor cru com `"` ou
    newline fecharia o scalar e malformaria o frontmatter — ou pior, injetaria
    uma chave YAML nova (`"\\n<key>: <val>`). Colapsa runs de whitespace (incl.
    newlines) em um único espaço, faz strip, e escapa `\\` → `\\\\` depois `"`
    → `\\"` (nessa ordem — barra primeiro pra não duplicar o escape das aspas).
    Resultado: `source-ref: "<retorno>"` parseia como YAML válido pra QUALQUER
    argv.
    """
    collapsed = re.sub(r"\s+", " ", value).strip()
    return collapsed.replace("\\", "\\\\").replace('"', '\\"')


def _source_tokens_for(argv_slug: Optional[str]) -> dict[str, str]:
    """Tokens de source pro intake (spec §4 C3), computados do argv CRU.

    Sempre devolve `{{source_type}}` + `{{source_ref_or_none}}` preenchidos —
    isso mata o vazamento do token cru universalmente (mesmo quando o argv já
    é slug válido ou veio do prompt interativo). `argv_slug` é o valor cru
    (nunca reescrito em `run()`).

    `source-type` casa o enum do template (`feature-intake.template.md` L12:
    `ticket | text | screenshot | mixed`):

      - ticket            → type=ticket, ref=<ticket cru, YAML-safe>
      - frase / slug      → type=text,   ref=<texto cru, YAML-safe> | none
      - sem argv (interativo) → type=text, ref=none

    (`screenshot`/`mixed` ficam pra Task 2 — entrada visual.) O `source-ref`
    passa por `_yaml_double_quote_safe` porque o template quota o campo e o
    argv é frase livre do usuário/host (sem isso, `"`/newline malformam o
    frontmatter que o conductor consome — spec §6).
    """
    if not argv_slug:
        return {"{{source_type}}": "text", "{{source_ref_or_none}}": "none"}
    if _is_valid_slug(argv_slug):
        return {"{{source_type}}": "text", "{{source_ref_or_none}}": "none"}
    source_type = "ticket" if _looks_like_ticket(argv_slug) else "text"
    return {
        "{{source_type}}": source_type,
        "{{source_ref_or_none}}": _yaml_double_quote_safe(argv_slug),
    }


def _ingest_screenshot(raw_input: str, feature_path: Path) -> Optional[dict]:
    """Sanitiza + registra um screenshot fornecido conversacionalmente.

    spec §4 C3a — o engine NÃO interpreta pixel: normaliza o path
    (traversal-safe), valida formato/tamanho, copia pra
    ``{feature}/screenshots/`` e calcula o fingerprint sha256. Devolve
    ``None`` em qualquer rejeição (path inválido, formato inválido) —
    mensagem mentor-calmo no stderr, segue sem a imagem. ``platform_hint``
    é só hint de baixa confiança que o conductor pode sobrepor. Reuso puro
    de ``engine.vision.screenshot`` (Mandamento 3) — nunca crasha.

    Source externo (mockup do host): um path ABSOLUTO que existe e resolve
    FORA da feature dir é aceito com semântica copy-in — o gate real continua
    sendo ``validate_screenshot`` (rejeita não-imagem → None). Caminhos
    relativos/bare/internos passam por ``normalize_screenshot_path`` (estrito:
    traversal-safe, contido na feature) — esse contrato NÃO muda pros outros
    callers. Todo o corpo (resolve → validate → copy → fingerprint → load)
    roda sob um único ``try`` que captura ``(ValueError, FileNotFoundError,
    OSError)`` — qualquer falha de IO/TOCTOU degrada gracioso em vez de
    propagar traceback bruto (honra "nunca crasha" mesmo depois do lock).
    """
    from engine.vision import screenshot as _ss

    try:
        candidate = Path(raw_input)
        if (
            candidate.is_absolute()
            and candidate.exists()
            and not candidate.resolve().is_relative_to(feature_path.resolve())
        ):
            resolved = candidate.resolve()  # mockup externo — copy-in semantics
        else:
            # Estrito p/ relativo/bare/interno: traversal-safe, contido na feature.
            resolved = _ss.normalize_screenshot_path(raw_input, feature_path)

        issues = _ss.validate_screenshot(resolved)
        if issues:
            sys.stderr.write(
                "forge plan: screenshot ignorado — "
                + "; ".join(issues)
                + ". Sigo sem a imagem; marque needs-elicitation se for UI.\n"
            )
            return None

        screenshots_dir = feature_path / "screenshots"
        ensure_dir(screenshots_dir)
        dest = screenshots_dir / resolved.name
        if resolved.resolve() != dest.resolve():
            shutil.copy2(resolved, dest)

        fingerprint = _ss.compute_screenshot_fingerprint(dest)
        meta = _ss.load_screenshot(dest)
        # `platform_inference` é Optional no dataclass (default None) — `load_screenshot`
        # sempre popula, mas o guard é defense-in-depth contra o tipo.
        inference = meta.platform_inference
        platform = inference.platform if inference else "unknown"
        confidence = inference.confidence if inference else None
        return {
            "path": str(dest.relative_to(feature_path)),
            "fingerprint": fingerprint,
            "platform_hint": platform,
            "platform_confidence": confidence,
        }
    except (ValueError, FileNotFoundError, OSError) as exc:
        sys.stderr.write(
            f"forge plan: screenshot ignorado — {exc}. "
            "Sigo sem a imagem.\n"
        )
        return None


def _record_screenshot_manifest(feature_path: Path, result: dict) -> None:
    """Persiste o dict de `_ingest_screenshot` em `screenshots/manifest.json`.

    spec §4 C3a / WR-02 — `_ingest_screenshot` computa `fingerprint` (dedup da
    Wave B) + `platform_hint` (hint de baixa confiança que o conductor pode
    sobrepor). Antes esses campos eram descartados (o `run()` lia só path+count),
    tornando a computação trabalho morto e quebrando o link de provenance que o
    spec desenha. O manifest fecha o handoff: o conductor herda fingerprint +
    platform sem recomputar os pixels.

    Merge por `filename` (idempotente): re-ingerir o mesmo arquivo sobrescreve a
    entry em vez de duplicar; arquivos distintos acumulam. Um manifest
    pré-existente corrompido (JSON inválido) é re-semeado gracioso — nunca
    crasha (mesmo contrato "nunca crasha" de `_ingest_screenshot`). Falha de IO
    na escrita degrada com aviso mentor-calmo no stderr; o fluxo segue (o
    arquivo do screenshot já está em screenshots/, então o conductor o tem).
    """
    try:
        filename = Path(result["path"]).name
        manifest_path = feature_path / "screenshots" / "manifest.json"
        manifest: dict[str, Any] = {}
        if manifest_path.is_file():
            try:
                loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    manifest = loaded
            except (json.JSONDecodeError, ValueError, OSError):
                # Manifest corrompido → re-seed limpo (não propaga).
                manifest = {}
        manifest[filename] = {
            "fingerprint": result.get("fingerprint"),
            "platform_hint": result.get("platform_hint"),
            "platform_confidence": result.get("platform_confidence"),
            "ingested_at": utc_now_iso(),
        }
        ensure_dir(manifest_path.parent)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        sys.stderr.write(
            f"forge plan: manifest de screenshot não persistido — {exc}. "
            "O screenshot foi copiado; sigo sem o registro de provenance.\n"
        )


def _elicit_screenshot(
    feature_path: Path,
    subtype: str,
    starting_wave: str,
) -> Optional[dict]:
    """Source-inquiry: pergunta por material visual e ingere se houver.

    spec §4 C3a + §5 — só pergunta quando a feature é UI-capable e o render
    é fresco: ``subtype == "product"`` E ``starting_wave == "A"``. Refactor/
    bugfix não têm Wave B (sem mockup), e em resume (wave != A) não
    re-pergunta — devolve ``None`` em silêncio nesses casos. A resposta
    ``"none"`` (ou vazia, via default) também devolve ``None``. Reusa a infra
    de prompt (``question.ask_text``, como ``_ask_task_count``) — participa do
    intent loop/resume via o ``stable_intent_id`` que o adapter computa. A
    análise multimodal dos pixels é do conductor (Wave B), não daqui.
    """
    if subtype != "product" or starting_wave != "A":
        return None
    resp = question.ask_text(
        "Tem material visual pra essa tela? "
        "(path do screenshot/mockup, ou 'none')",
        default="none",
    )
    # `ask_text(default="none")` nunca devolve falsy (vazio resolve pro default),
    # então só o sentinel "none" precisa de check — o ramo `not resp` era morto.
    if resp.strip().lower() == "none":
        return None
    return _ingest_screenshot(resp.strip(), feature_path)


def _forge_home() -> Path:
    from engine.utils.paths import forge_home as _fh

    return _fh()


def _templates_dir() -> Path:
    return _forge_home() / _TEMPLATES_SUBDIR


def _render_template(
    template_name: str,
    target: Path,
    slug: str,
    *,
    extra_tokens: Optional[dict[str, str]] = None,
) -> bool:
    """Copy `templates/{template_name}` to `target`. Returns True if newly created.

    Templating leve: substitui os tokens que o engine conhece de forma
    confiável — slug (lowercase `{{feature_slug}}`, como os templates usam,
    74×; uppercase `{{FEATURE_SLUG}}` preservado p/ compat), timestamp, e —
    via `extra_tokens` — a origem (`{{source_type}}`/`{{source_ref_or_none}}`).
    Tudo o mais fica verbatim — a população completa é trabalho do host entre
    as waves. `extra_tokens` é kw-only com default None (backward-compat); os
    tokens de source só existem no intake — `.replace` é no-op nos demais
    templates (inofensivo). O guard `target.exists()` mantém o once-only no
    resume (não re-renderiza/re-preenche).
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
    substitutions: dict[str, str] = {
        "{{feature_slug}}": slug,
        "{{FEATURE_SLUG}}": slug,  # legacy uppercase — preservado p/ compat
        "{{generated_at_iso8601}}": utc_now_iso(),
    }
    if extra_tokens:
        substitutions.update(extra_tokens)
    # Substituição single-pass: um único `re.sub` escaneia o template UMA vez e
    # troca cada token pelo lookup no dict. Diferente do `.replace` em cascata,
    # NÃO re-escaneia valores já inseridos — então um valor (e.g. source-ref do
    # argv livre) contendo o literal de outro token (`{{screenshots_count}}`)
    # sobrevive intacto. `sorted(longest-first)` evita ambiguidade de prefixo;
    # o guard `if substitutions` evita um regex vazio (sempre há ao menos os 3
    # tokens base, mas o guard mantém o invariante explícito).
    if substitutions:
        _pat = re.compile(
            "|".join(re.escape(k) for k in sorted(substitutions, key=len, reverse=True))
        )
        raw = _pat.sub(lambda m: substitutions[m.group(0)], raw)
    target.write_text(raw, encoding="utf-8")
    return True


# A-006 (master review PR #15): `_resolve_features_root` foi promovido pra
# `engine/utils/paths.py` (leaf real, sem dep de plan.py). Mantemos shim aqui
# pra preservar callsites internos que faziam `from engine.plan import
# _resolve_features_root` antes da consolidação.
from engine.utils.paths import _resolve_features_root  # noqa: E402,F401


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
    *,
    extra_tokens: Optional[dict[str, str]] = None,
) -> WaveResult:
    """Render a wave's templates, narrate, then block on continuar/pausar.

    `extra_tokens` (kw-only, default None) é repassado a `_render_template` —
    a Wave A usa pra preencher os tokens de source no intake (spec §4 C3).
    """
    renderer.write("")
    renderer.write(renderer.bold(f"⚡ Wave {label}"))
    created: list[Path] = []
    for template_name, output_name in templates:
        target = feature_path / output_name
        was_new = _render_template(
            template_name, target, slug, extra_tokens=extra_tokens
        )
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
        if _is_valid_slug(argv_slug):
            return argv_slug
        # Não é slug válido → trata como ticket/frase: deriva + confirma.
        # Front-door (spec §4 C3) · Decisão 10: argv posicional, sem flag.
        # Slug-derivável NÃO é erro — só vira exit 1 se realmente impossível.
        try:
            derived = _derive_slug(argv_slug)
        except ValueError:
            sys.stderr.write(
                f"forge plan: não consegui derivar um slug de {argv_slug!r}. "
                "Tente uma frase com ao menos uma letra (ex.: 'lembrete de rega').\n"
            )
            raise SystemExit(1)
        return question.ask_text(
            f"Derivei '{derived}' do que você passou — confirma ou ajusta?",
            default=derived,
            validator=_is_valid_slug,
            validator_hint=(
                "kebab-case lowercase, 2..50 chars, deve começar com letra."
            ),
        )

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
                at=utc_now_iso(),
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
    return fail_with_tag(ERR_ABORTED)


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
    intake_tokens: Optional[dict[str, str]] = None,
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
            # Wave A renderiza o feature-intake.md — único ponto onde os
            # tokens de source (spec §4 C3) são preenchidos. B/C/D/E não
            # recebem (os tokens só existem no intake).
            result = _run_static_wave(
                "A",
                wave_a_templates,
                slug,
                project_root,
                feature_path,
                extra_tokens=intake_tokens,
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
        return fail_with_tag(ERR_PROJECT_NOT_FOUND)

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
            at=utc_now_iso(),
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
        return fail_with_tag(ERR_LOCKED)

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

    # Front-door (spec §4 C3): tokens de source preenchidos no intake da
    # Wave A. Computados do `argv_slug` CRU (nunca reescrito) — sempre
    # presentes, matando o vazamento do token cru universalmente.
    intake_tokens = _source_tokens_for(argv_slug)

    # Vision wire (spec §4 C3a): source-inquiry conversacional por material
    # visual — só em product + Wave A (UI-capable + render fresco). Os 3 nomes
    # de token de screenshot são SEMPRE preenchidos (product usa o nome puro;
    # refactor/bugfix usam o sufixo `_or_none`) — o `.replace` no-opa o ausente
    # por variante e nenhum token cru vaza em qualquer subtype. Fluem pelo MESMO
    # threading dos tokens de source (intake_tokens → _run_waves_for_subtype →
    # Wave A render). O engine só sanitiza/fingerprint; a análise é do conductor.
    screenshot_result = _elicit_screenshot(feature_path, subtype, starting_wave)
    if screenshot_result is not None:
        # WR-02: persiste fingerprint + platform_hint (senão descartados) pro
        # conductor herdar a provenance sem recomputar os pixels.
        _record_screenshot_manifest(feature_path, screenshot_result)
    _ss_count = "1" if screenshot_result else "0"
    _ss_paths = screenshot_result["path"] if screenshot_result else "none"
    intake_tokens.update(
        {
            "{{screenshots_count}}": _ss_count,
            "{{screenshots_relative_paths_csv}}": _ss_paths,
            "{{screenshots_relative_paths_csv_or_none}}": _ss_paths,
        }
    )

    # Wave dispatch loop (subtype-aware; bugfix branches on wave_b_required).
    try:
        rc = _run_waves_for_subtype(
            subtype,
            starting_wave,
            slug,
            project_root,
            feature_path,
            wave_b_required=wave_b_required,
            intake_tokens=intake_tokens,
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
        "captured-at": utc_now_iso(),
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
