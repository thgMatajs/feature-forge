"""`forge init` — greenfield/brownfield install command.

This is the MOST IMPORTANT command of feature-forge. It:

- detects whether the cwd is a fresh project (greenfield) or already has
  `.claude/workflow-config.yaml` (brownfield — defer to `forge reconfigure`);
- runs cinematic discovery (cards, stack detection, design system, i18n,
  conventions);
- proposes the canonical preset (`kmp-mobile`) and asks the user to confirm;
- asks the user to pick a `backend-candidate` (Cena 6.5 — explicit decision,
  never auto-selected);
- resolves card dependencies/conflicts via the resolver;
- snapshots cards into `.claude/cards/`;
- merges contributions, writes inventory snapshots, seeds memory L1/L2 dirs;
- builds the codebase graph (SQLite, deterministic);
- writes `.claude/workflow-config.yaml` (schema v1) + history JSONL seed;
- renders a final summary.

Decision 10 (zero flags): only positional `help` accepted. Everything else
is interactive.

Decision 27 (Ctrl+C = pause): on `KeyboardInterrupt` we save a deferred
checkpoint at `.claude/.init-checkpoint.yaml` so the next `forge init` can
auto-resume. Exit code 130 is returned to the dispatcher.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    import tomllib  # Python 3.11+ stdlib
except ImportError:  # pragma: no cover — defesa pra ambientes <3.11
    tomllib = None  # type: ignore[assignment]

if TYPE_CHECKING:
    # N5: type-annotate `_check_orphan_signals(catalog)` sem ativar import
    # eager (validators é layer-superior na arquitetura — engine consome
    # type-only).
    from validators._common import CapabilityCatalog  # noqa: F401

from engine import __version__ as FORGE_VERSION
from engine.cards.grant import (
    GrantDecision,
    UserAbortError,
    evaluate_sensitive_grants,
)
from engine.cards.loader import load_all_cards, CardManifest
from engine.cards.merger import merge_contributions
from engine.cards.resolver import resolve
from engine.cards.snapshotter import snapshot_card
from engine.graph.builder import build_full
from engine.inventory.conventions import (
    extract_conventions,
    write_conventions_inventory,
)
from engine.inventory.design_system import (
    extract_design_system,
    write_design_system_inventory,
)
from engine.inventory.i18n import extract_i18n, write_i18n_inventory
from engine.persona import mentor_calmo
from engine.ui import progress as ui_progress
from engine.ui import question as ui_question
from engine.ui import question  # alias para mock-friendly access (engine.init.question.ask)
from engine.ui import renderer
from engine.utils.paths import (
    cards_canonical_dir,
    cards_dir,
    claude_dir,
    ensure_dir,
    forge_home,
    graph_db_path,
    inventory_dir,
    memory_dir,
    memory_l2_path,
    workflow_config_path,
)
from engine.utils.sha256 import file_sha256
from engine.utils.yaml_io import read_yaml_or_default, write_yaml

PRESET_NAME = "kmp-mobile"
LATENT_CAPS = ["android-platform", "ios-platform", "swift-language"]
USAGE_HINT = "Uso: forge init"


# ── Errors ───────────────────────────────────────────────────────────────────


class InitError(RuntimeError):
    """Fatal init error — printed at top-level and translates to exit code 2."""


# ── Checkpoint (Decision 27) ─────────────────────────────────────────────────


@dataclass
class _InitCheckpoint:
    """State serialized on Ctrl+C, so a follow-up `forge init` can offer resume."""

    step: str
    at: str
    project_root: str
    preset: str | None = None
    selected_card_names: list[str] = field(default_factory=list)
    backend_choice: str | None = None


def _checkpoint_path(project_root: Path) -> Path:
    return claude_dir(project_root) / ".init-checkpoint.yaml"


def _save_checkpoint(cp: _InitCheckpoint) -> None:
    path = _checkpoint_path(Path(cp.project_root))
    ensure_dir(path.parent)
    write_yaml(
        path,
        {
            "schema-version": 1,
            "step": cp.step,
            "at": cp.at,
            "project-root": cp.project_root,
            "preset": cp.preset,
            "selected-card-names": cp.selected_card_names,
            "backend-choice": cp.backend_choice,
        },
        atomic=True,
    )


def _load_checkpoint(project_root: Path) -> dict[str, Any] | None:
    path = _checkpoint_path(project_root)
    if not path.exists():
        return None
    return read_yaml_or_default(path, None)


def _clear_checkpoint(project_root: Path) -> None:
    path = _checkpoint_path(project_root)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


# ── Helpers ──────────────────────────────────────────────────────────────────


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def _eval_detection_signals(
    project_root: Path, detection: dict[str, Any]
) -> tuple[float, list[str]]:
    """Evaluate detection signals against the project. Returns (score, matched).

    Supports `file-exists`, `file-content`, `directory-exists` signal types
    (same schema used by cards and presets — see docs/schemas/card.md
    §detection.signals).
    """
    signals = (detection or {}).get("signals") or []
    score = 0.0
    matched: list[str] = []
    for sig in signals:
        if not isinstance(sig, dict):
            continue
        kind = sig.get("type")
        conf = float(sig.get("confidence") or 0.0)
        ok = False
        if kind == "directory-exists":
            path = sig.get("path")
            if isinstance(path, str) and (project_root / path).is_dir():
                ok = True
        elif kind == "file-exists":
            ok = _glob_any(project_root, str(sig.get("glob") or ""), None)
        elif kind == "gradle-dep":
            coordinate = sig.get("coordinate")
            if isinstance(coordinate, str) and coordinate:
                ok = _eval_gradle_dep(project_root, coordinate)
        elif kind == "file-content":
            ok = _glob_any(
                project_root,
                str(sig.get("glob") or ""),
                str(sig.get("contains") or ""),
            )
        if ok:
            score += conf
            label = (
                sig.get("coordinate")
                or sig.get("contains")
                or sig.get("path")
                or sig.get("glob")
                or kind
            )
            matched.append(f"{kind}: {label}")
    return round(score, 3), matched


@dataclass
class OrphanSignal:
    """Signal que casou em scan mas não em nenhum card (canon ∪ local).

    Atributos:
      - signal_id: identificador (do detection/signals.yaml ou inline derivado)
      - source: arquivo onde o signal casou (relativo ao project_root)
      - suggested_capability: label que a heurística infere
      - is_reserved: True se suggested_capability ∈ canon.reserved
        (Step 7.5 muda o caminho 1 de "criar local" pra "abrir ADR")
      - hit_count: número de ocorrências (qualidade do signal)
    """

    signal_id: str
    source: str
    suggested_capability: str
    is_reserved: bool = False
    hit_count: int = 0


def _check_orphan_signals(
    project_root: Path,
    canonical_cards: list["CardManifest"],
    catalog: "CapabilityCatalog",
) -> list[OrphanSignal]:
    """Detecta signals que bateram em scan mas não em card algum (canon ∪ local).

    Heurística:
      - Para cada card carregado, registra o set de signal contains/globs.
      - Scan independente do project_root pega imports/anotações comuns que
        sugerem capabilities ausentes (hilt-di, apollo-graphql, rxjava3).
      - Cada miss vira um OrphanSignal com suggested_capability inferida
        por lookup numa tabela `_ORPHAN_HEURISTICS` (best-effort, não exaustiva).
      - Se suggested_capability ∈ catalog.reserved → marca is_reserved=True.

    Conservador: se nenhuma heurística bate, retorna lista vazia (não inventa).
    """
    project = project_root.resolve()
    matched_in_cards: set[str] = set()
    for card in canonical_cards:
        for sig in (card.detection or {}).get("signals") or []:
            contains = (sig or {}).get("contains")
            if isinstance(contains, str) and contains:
                matched_in_cards.add(contains)

    orphans: list[OrphanSignal] = []
    for needle, suggested in _ORPHAN_HEURISTICS.items():
        if needle in matched_in_cards:
            continue
        hits = _count_needle_hits(project, needle)
        if hits == 0:
            continue
        is_reserved = suggested in catalog.reserved
        orphans.append(
            OrphanSignal(
                signal_id=f"orphan:{needle}",
                source=f"detected in {hits} file(s)",
                suggested_capability=suggested,
                is_reserved=is_reserved,
                hit_count=hits,
            )
        )
    return orphans


# Heurística mínima — needle → suggested capability. Lista enxuta, foco em
# casos comuns que motivam Gap 5. Expansão fica pra próximas waves.
_ORPHAN_HEURISTICS: dict[str, str] = {
    "@HiltAndroidApp":              "hilt-di",
    "dagger.hilt.android":          "hilt-di",
    "import com.apollographql":     "apollo-graphql-client",
    "ApolloClient(":                "apollo-graphql-client",
    "io.reactivex.rxjava3":         "rxjava3-streams",
    "io.realm.kotlin":              "realm-local",
}


def _count_needle_hits(project_root: Path, needle: str, limit: int = 50) -> int:
    """Conta arquivos .kt/.gradle* que contêm `needle`. Cap em `limit` pra
    evitar varredura cara em monorepos grandes — qualquer valor >= 1 é
    suficiente pra Step 7.5 surface.
    """
    count = 0
    patterns = ("*.kt", "build.gradle", "build.gradle.kts", "settings.gradle*")
    for pattern in patterns:
        for path in project_root.rglob(pattern):
            try:
                parts = path.relative_to(project_root).parts
            except ValueError:
                continue
            # C16: filtra dirs ocultos (.git etc.) + monorepo culprits
            # declarados em `_SKIP_DIRS` (node_modules, build, .gradle,
            # Pods, DerivedData, dist). Sem isso, init trava em
            # monorepos varrendo deps/build artifacts.
            if any(part.startswith(".") or part in _SKIP_DIRS for part in parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if needle in text:
                count += 1
                if count >= limit:
                    return count
    return count


# ── Step 7.5 — orphan signal 3-caminhos UX (Gap 5) ──────────────────────────


@dataclass
class InitDecision:
    """Resultado do Step 7.5 — usado pelo loop principal pra decidir next step.

    `choice` ∈ {"create-local", "adr-required", "ignore", "abort", "noop"}.
    `exit_code` é usado quando choice="abort" (8 = orphan-signals aborted)
    ou choice="adr-required" (7 = pending decision / suspended).
    `note` carrega mensagem auxiliar pra render no log de init.
    """

    choice: str
    exit_code: int = 0
    note: str = ""


def _surface_three_paths(
    orphans: list[OrphanSignal],
    project_root: Path,
) -> InitDecision:
    """Apresenta 3-caminhos canônicos pra signals órfãos.

    Edge case reservada: se TODOS os orphans apontam capability reservada,
    caminho 1 muda de "criar card local" pra "abrir ADR pra promoção".
    Quando misturado (alguns reservados, outros não), caminho 1 ainda tenta
    criar local pros não-reservados e marca ADR-required pros reservados.

    Reprompt em escolha inválida (esperado [1-3], qualquer outro reabre).

    Pós-condição caminho 1 (não-reservada): cards locais são gravados em
    disco mas `activated` NÃO é recomputado nesta passagem — o catálogo
    expandido só entra em vigor no próximo `forge init`. Mensagem
    user-facing avisa explicitamente (N2 do power-review PR #2; behavior
    fix completo — re-roda detection inline — fica pra v1.2).
    """
    if not orphans:
        return InitDecision(choice="noop")

    all_reserved = all(o.is_reserved for o in orphans)

    # Header + listagem mentor calmo PT-BR
    renderer.write("")
    renderer.write(
        renderer.colored(
            "🛑  Stack ambígua — signals sem card correspondente", "yellow"
        )
    )
    renderer.write("")
    renderer.write(
        "Detectei sinais que apontam pra capabilities sem provider declarado:"
    )
    renderer.write("")
    for o in orphans:
        reserved_tag = " (label RESERVADA no catálogo canon)" if o.is_reserved else ""
        renderer.write(f"  · Signal {o.signal_id} ({o.source})")
        renderer.write(f"    → capability {o.suggested_capability!r}{reserved_tag}")
    renderer.write("")
    renderer.write("Onde:")
    renderer.write("  Detection cascade rodou mas não encontrou card canon nem local")
    renderer.write("  pra estes signals.")
    renderer.write("")
    renderer.write("Por que importa:")
    renderer.write("  Materializar o plan sem provider declarado deixa essas capabilities")
    renderer.write("  como \"comportamento inventado\" — viola o princípio \"never invents\"")
    renderer.write("  (docs/design/00-vision.md §What feature-forge is NOT) e quebra o")
    renderer.write("  contrato com validate_no_invented_behavior na Fase 5b.")
    renderer.write("")
    renderer.write("Três caminhos pra resolver:")
    renderer.write("")
    if all_reserved:
        renderer.write("  1) Abrir ADR pra promoção ao canon (recomendado)")
        renderer.write("     Cria entrada em docs/design/01-decisions.md \"Revisita roadmap")
        renderer.write("     do catálogo — promove <label> ao canon\" e suspende init até")
        renderer.write("     PR de promoção rodar.")
    else:
        renderer.write("  1) Criar card local agora (recomendado pra stack atual)")
        renderer.write("     Materializa card(s) local(is) em .claude/cards/local/ cobrindo")
        renderer.write("     os signals órfãos. Init segue com a `activated` corrente —")
        renderer.write("     re-rode `forge init` pra ativar com catálogo expandido.")
    renderer.write("")
    renderer.write("  2) Ignorar nesta init (registra decisão consciente)")
    renderer.write("     Grava .claude/inventory/ignored-signals.yaml versionado listando")
    renderer.write("     os signals + razão. Validators downstream respeitam o ignore.")
    renderer.write("     Reversível: removendo a entrada, signals voltam a ser órfãos.")
    renderer.write("")
    renderer.write("  3) Abortar init")
    renderer.write("     Exit code 8 (distinto de 5/7/130). Nenhum arquivo materializado.")
    renderer.write("     Use quando o time precisa decidir arquitetura antes de seguir.")
    renderer.write("")

    while True:
        choice = question.ask(
            "Escolha [1-3]:",
            {"1": "1", "2": "2", "3": "3"},
            default="1",
        )
        if choice in {"1", "2", "3"}:
            break
        renderer.write(
            renderer.colored("Escolha inválida — esperado 1, 2 ou 3.", "yellow")
        )

    if choice == "1":
        if all_reserved:
            labels = ", ".join(sorted({o.suggested_capability for o in orphans}))
            return InitDecision(
                choice="adr-required",
                exit_code=7,
                note=(
                    f"Labels reservadas detectadas: {labels}. "
                    "Abra ADR antes de prosseguir."
                ),
            )
        # Cria local pros não-reservados; reservados saem como note.
        # C14: agrupa por suggested_capability ANTES do loop — dois orphans
        # mapeando pra mesma capability geram um único card local com
        # signals consolidados (sem agrupar, o segundo write sobrescreve
        # o primeiro silenciosamente).
        from collections import defaultdict  # noqa: PLC0415 — lazy local

        non_reserved = [o for o in orphans if not o.is_reserved]
        reserved_labels = sorted(
            {o.suggested_capability for o in orphans if o.is_reserved}
        )
        grouped: dict[str, list[OrphanSignal]] = defaultdict(list)
        for o in non_reserved:
            grouped[o.suggested_capability].append(o)
        for cap_orphans in grouped.values():
            _card_local_add_inline(project_root, cap_orphans)
        # N2: avisa o user que catálogo expandido só entra em vigor na
        # próxima execução. Behavior fix completo (re-detection inline)
        # fica pra v1.2 (anotado em docs/design/04-pending.md).
        note_parts = [
            "Cards locais criados. Re-rode `forge init` pra ativar com "
            "catálogo expandido."
        ]
        if reserved_labels:
            note_parts.append(
                f"Reservadas pendentes de ADR: {', '.join(reserved_labels)}. "
                "Criados apenas os locais não-reservados."
            )
        return InitDecision(choice="create-local", note=" ".join(note_parts))

    if choice == "2":
        _write_ignored_signals(project_root, orphans)
        return InitDecision(choice="ignore")

    # choice == "3"
    return InitDecision(choice="abort", exit_code=8)


def _card_local_add_inline(
    project_root: Path,
    orphan_or_list: "OrphanSignal | list[OrphanSignal]",
) -> None:
    """Cria card local minimal cobrindo um ou mais orphan signals.

    Espelha skeleton de `_card_local_add` mas pre-preenche `name`,
    `provides`, e adiciona signals iniciais baseados no(s) orphan needle(s).
    Usado pelo Step 7.5 quando user escolhe caminho 1.

    Aceita `OrphanSignal` (legacy/backward-compat) OU `list[OrphanSignal]`
    pra consolidar múltiplos needles que apontam pra mesma capability num
    único card local (sem agrupar, o segundo write sobrescreveria o
    primeiro — bug N C14/C15 do power-review PR #2).

    Pressupõe que todos os orphans da lista compartilham
    `suggested_capability` (chamador agrupa antes). Se a lista for
    heterogênea, usa o `suggested_capability` do primeiro como referência.
    """
    import yaml as _yaml_lib  # noqa: PLC0415 — lazy
    from engine.cards import LOCAL_CARD_NAME_RE  # noqa: PLC0415 — lazy

    if isinstance(orphan_or_list, OrphanSignal):
        orphans: list[OrphanSignal] = [orphan_or_list]
    else:
        orphans = list(orphan_or_list)
    if not orphans:
        return

    capability = orphans[0].suggested_capability
    base_name = capability if LOCAL_CARD_NAME_RE.match(capability) else "orphan-card"

    # N3: se canon já tem card com o mesmo nome (não esperado em v1.1 — todas
    # as capabilities órfãs apontam pra labels SEM card canon — mas defensivo
    # caso o catálogo evolua), sufixa com `-local` pra evitar colisão silenciosa
    # com a cascade canon×local (que faria hard fail no próximo load).
    canon_root = project_root / ".claude" / "cards"
    canon_names: set[str] = set()
    if canon_root.is_dir():
        canon_names = {
            d.name
            for d in canon_root.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name != "local"
        }
    name = base_name if base_name not in canon_names else f"{base_name}-local"

    local_root = project_root / ".claude" / "cards" / "local" / name
    local_root.mkdir(parents=True, exist_ok=True)
    (local_root / "detection").mkdir(parents=True, exist_ok=True)

    signals: list[dict[str, Any]] = []
    needles_seen: list[str] = []
    for o in orphans:
        needle = o.signal_id.removeprefix("orphan:")
        signals.append(
            {
                "type": "file-content",
                "glob": "**/*.kt",
                "contains": needle,
                "confidence": 0.5,
            }
        )
        needles_seen.append(needle)

    card_data = {
        "schema-version": 1,
        "identity": {
            "name": name,
            "version": "0.1.0",
            "description": (
                f"Orphan-derived local card cobrindo {capability}."
            ),
            "category": "kmp",
            "maturity": "experimental",
            "maintainer": "team-local-auto",
            "created-at": _today_iso_for_init(),
            "last-updated": _today_iso_for_init(),
        },
        "legacy-marker": False,
        "provides": [capability],
        "requires": [],
        "conflicts-with": [],
        "contributes": {"config-defaults": {}},
        "detection": {
            "signals": signals,
            "threshold": 0.5,
        },
        "documentation": {"readme": "README.md"},
    }
    (local_root / "card.yaml").write_text(
        _yaml_lib.safe_dump(card_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    needle_list = ", ".join(f"`{n}`" for n in needles_seen)
    (local_root / "README.md").write_text(
        f"# {name}\n\n"
        f"Card local criado automaticamente pelo init Step 7.5 a partir "
        f"de signal(s) órfão(s) {needle_list}. Revise threshold e signals "
        f"adicionais em `card.yaml` antes do próximo `forge verify`.\n",
        encoding="utf-8",
    )
    (local_root / "detection" / "signals.yaml").write_text(
        "schema-version: 1\nsignals: []\nthreshold: 0.5\n", encoding="utf-8"
    )


def _write_ignored_signals(project_root: Path, orphans: list[OrphanSignal]) -> None:
    """Grava `.claude/inventory/ignored-signals.yaml` versionado."""
    import yaml as _yaml_lib  # noqa: PLC0415 — lazy

    inv = project_root / ".claude" / "inventory"
    inv.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema-version": 1,
        "generated-by": "feature-forge init Step 7.5",
        "ignored": [
            {
                "signal_id": o.signal_id,
                "suggested_capability": o.suggested_capability,
                "source": o.source,
                "hit_count": o.hit_count,
            }
            for o in orphans
        ],
    }
    (inv / "ignored-signals.yaml").write_text(
        _yaml_lib.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _today_iso_for_init() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _glob_any(project_root: Path, glob: str, needle: str | None) -> bool:
    """Best-effort glob walk with depth + count caps to keep init responsive."""
    if not glob:
        return False
    if glob.startswith("**/"):
        pattern = glob[3:]
        iterator = project_root.rglob(pattern)
    else:
        iterator = project_root.glob(glob)
    count = 0
    for path in iterator:
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if count > 800:
            break
        count += 1
        if not path.is_file():
            continue
        if needle is None:
            return True
        # Stream linha-a-linha — evita carregar arquivos grandes inteiros em
        # memória só para procurar uma substring.
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if needle in line:
                        return True
        except OSError:
            continue
    return False


def _eval_gradle_dep(project_root: Path, coordinate: str | None) -> bool:
    """True se a coordenada Maven existe em qualquer formato Gradle.

    Ordem: 1) catálogo gradle/*.versions.toml, 2) build.gradle(.kts) legado.
    Curto-circuita no primeiro match. Defensivo contra TOML mal-formado
    (try/except silencioso, alinhado a `_glob_any`).

    Format aceito do `coordinate`: `<groupId>:<artifactId>` sem version,
    sem espaços. Shape validation acontece em `engine/cards/loader.py`
    (regra CARD-020); aqui aceitamos None/vazio defensivamente.
    """
    if not coordinate or not isinstance(coordinate, str) or ":" not in coordinate:
        return False
    group, _, artifact = coordinate.partition(":")
    if not group or not artifact:
        return False

    # 1) Catálogo TOML (path canônico gradle/*.versions.toml)
    if tomllib is not None:
        gradle_dir = project_root / "gradle"
        if gradle_dir.is_dir():
            for toml_path in gradle_dir.glob("*.versions.toml"):
                try:
                    with toml_path.open("rb") as fh:
                        data = tomllib.load(fh)
                except (OSError, tomllib.TOMLDecodeError):
                    continue
                libraries = data.get("libraries") or {}
                if not isinstance(libraries, dict):
                    continue
                for entry in libraries.values():
                    if not isinstance(entry, dict):
                        continue
                    module = entry.get("module")
                    if isinstance(module, str) and module == coordinate:
                        return True
                    grp = entry.get("group")
                    nm = entry.get("name")
                    if (
                        isinstance(grp, str)
                        and isinstance(nm, str)
                        and grp == group
                        and nm == artifact
                    ):
                        return True

    # 2) build.gradle(.kts) legado — reusa _glob_any (substring match)
    if _glob_any(project_root, "**/build.gradle*", coordinate):
        return True

    return False


_SKIP_DIRS = {
    "node_modules",
    "build",
    ".git",
    ".gradle",
    ".idea",
    "DerivedData",
    "Pods",
    "dist",
    ".next",
    ".cache",
    ".venv",
    "venv",
    ".claude",
    "__pycache__",
}


def _load_preset(name: str) -> dict[str, Any]:
    """Load a preset definition from FORGE_HOME/presets/{name}/preset.yaml."""
    path = forge_home() / "presets" / name / "preset.yaml"
    if not path.is_file():
        raise InitError(f"preset not found: {path}")
    return read_yaml_or_default(path, {}) or {}


def _index_cards(canonical: list[CardManifest]) -> dict[str, CardManifest]:
    return {c.name: c for c in canonical}


# ── Hooks install (Step 13) ──────────────────────────────────────────────────


def _install_hooks(project_root: Path) -> int:
    """Copy canonical hooks from FORGE_HOME/hooks/ to .claude/hooks/.

    Rules:
    - `.sh` scripts and `git-*` wrappers → copied with +x preserved.
    - `.yml` files (e.g. ci-pr-ingest.yml) are NOT copied — they're opt-in CI
      workflows the user installs into `.github/workflows/` manually.
    - Idempotent: overwrites existing copies (canonical wins).

    Returns the number of hooks installed.
    """
    canonical = forge_home() / "hooks"
    if not canonical.is_dir():
        return 0

    target = claude_dir(project_root) / "hooks"
    ensure_dir(target)

    count = 0
    for src in sorted(canonical.iterdir()):
        if not src.is_file():
            continue
        if src.suffix == ".yml":
            continue
        dst = target / src.name
        shutil.copy2(src, dst)
        if src.suffix == ".sh" or src.name.startswith("git-"):
            try:
                dst.chmod(0o755)
            except OSError:
                pass
        count += 1
    return count


def _install_git_hooks(project_root: Path) -> None:
    """Symlink `.git/hooks/{pre-commit,post-commit,pre-push}` to canonical wrappers.

    Idempotent — pre-existing custom hooks get backed up to `<name>.bak` once
    before being replaced. On non-git projects this is a no-op.
    """
    git_hooks = project_root / ".git" / "hooks"
    if not git_hooks.is_dir():
        return

    mappings = {
        "pre-commit": "git-pre-commit",
        "post-commit": "git-post-commit",
        "pre-push": "git-pre-push",
    }
    for git_name, claude_name in mappings.items():
        source = claude_dir(project_root) / "hooks" / claude_name
        if not source.is_file():
            continue
        target = git_hooks / git_name

        if target.is_symlink() or target.exists():
            backup = target.with_name(target.name + ".bak")
            if not backup.exists():
                try:
                    target.replace(backup)
                except OSError:
                    try:
                        target.unlink()
                    except OSError:
                        continue
            else:
                try:
                    target.unlink()
                except OSError:
                    continue

        try:
            target.symlink_to(Path("../../.claude/hooks") / claude_name)
            target.chmod(0o755)
        except OSError:
            pass


# ── Entry point ──────────────────────────────────────────────────────────────


def run(argv: list[str]) -> int:
    """`forge init` entry point. Decision 10: no flags — argv must be `[]` or `['help']`."""
    if argv:
        first = argv[0].lower()
        if first in ("help", "-h", "--help"):
            renderer.write(USAGE_HINT)
            renderer.write("")
            renderer.write(
                "Faz install do feature-forge no projeto atual (cwd).\n"
                "Sem flags — todas as escolhas são interativas."
            )
            return 0
        renderer.write(
            renderer.colored(
                f"forge init não aceita argumentos (recebeu {argv!r}). {USAGE_HINT}",
                "yellow",
            )
        )
        return 2

    project_root = Path.cwd().resolve()
    try:
        return _run_pipeline(project_root)
    except ui_question.PromptAbortedError:
        renderer.write("")
        renderer.write(mentor_calmo.pause_message(resume_command="forge init"))
        return 130
    except KeyboardInterrupt:
        # Re-raise — the dispatcher in cli.py owns the 130 exit code path.
        raise
    except InitError as exc:
        renderer.write("")
        renderer.write(renderer.colored(f"forge init falhou: {exc}", "red"))
        return 2


def _run_pipeline(project_root: Path) -> int:
    """The 15-step sequence from docs/ux/forge-init-roteiro.md."""
    checkpoint = _InitCheckpoint(
        step="step-1-greeting",
        at=_utc_now_iso(),
        project_root=str(project_root),
    )

    # ── Step 1 — Greeting + brownfield/greenfield gate ───────────────────────
    renderer.write("")
    renderer.write(
        renderer.box(
            "feature-forge",
            [
                f"forge {FORGE_VERSION}",
                "Planning workflow for mobile features.",
            ],
            width=64,
        )
    )
    renderer.write("")
    renderer.write(mentor_calmo.greeting())
    renderer.write(
        "Vou conhecer este projeto antes de te perguntar qualquer coisa."
    )
    renderer.write("")

    if not _is_git_repo(project_root):
        renderer.write(
            renderer.colored(
                f"Aviso: {project_root} não parece ser um git repo. "
                "Vou seguir, mas recomendo `git init` antes pra rastrear "
                "o que o forge gera.",
                "yellow",
            )
        )

    if workflow_config_path(project_root).is_file():
        renderer.write(
            mentor_calmo.three_paths_block(
                "INIT-BROWNFIELD",
                what_failed="já existe .claude/workflow-config.yaml neste projeto",
                where=str(workflow_config_path(project_root)),
                why=[
                    "init é destrutivo — sobrescreveria cards/inventory já curados",
                    "reconfigure é a porta canônica pra mudar config existente",
                ],
                paths=[
                    {
                        "label": "rodar `forge reconfigure`",
                        "motive": "ajusta config sem reinstalar",
                    },
                    {
                        "label": "abortar agora e investigar manualmente",
                        "motive": "se você não esperava ver config aqui",
                    },
                    {
                        "label": "apagar .claude/ e rodar `forge init` de novo",
                        "motive": "só faça isso se quiser começar do zero",
                    },
                ],
            )
        )
        return 2

    existing_checkpoint = _load_checkpoint(project_root)
    if existing_checkpoint:
        renderer.write(
            renderer.colored(
                f"Encontrei um checkpoint anterior (step={existing_checkpoint.get('step')}) "
                f"em {_checkpoint_path(project_root)}.",
                "yellow",
            )
        )
        # Decision 27 — sempre 3 caminhos em gate violation legítimo. Resume
        # completo entra plenamente em Phase 5+; por enquanto resume = restart
        # mantendo o checkpoint pra audit, discard apaga, abort sai sem tocar.
        resume_choice = ui_question.ask(
            "Resume de init pendente?",
            {
                "resume": "começar do zero mantendo o checkpoint como audit",
                "discard": "apagar o checkpoint e começar limpo",
                "abort": "sair sem mexer em nada",
            },
            default="discard",
        )
        if resume_choice == "discard":
            _clear_checkpoint(project_root)
        elif resume_choice == "abort":
            renderer.write(
                "Ok, abortado. O checkpoint segue intacto pra inspeção manual."
            )
            return 2
        # resume → segue sem apagar o checkpoint; o pipeline regrava no
        # final via _clear_checkpoint quando completar com sucesso.

    # ── Step 2 — Discovery (cinematic) ───────────────────────────────────────
    checkpoint.step = "step-2-discovery"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    renderer.write("")
    renderer.write("[0:01] Scanning repo + cards canônicos…")

    canonical_dir = cards_canonical_dir()
    if not canonical_dir.is_dir():
        raise InitError(f"canonical cards directory missing: {canonical_dir}")

    discovery_steps = [
        "Lendo cards canônicos",
        "Detectando stack",
        "Mapeando design system",
        "Extraindo i18n",
        "Mapeando convenções",
    ]
    canonical_cards: list[CardManifest] = []
    ds_inv = None
    i18n_inv = None
    conv_inv = None

    with ui_progress.progress(len(discovery_steps), "discovery", width=24) as bar:
        canonical_cards = load_all_cards(canonical_dir)
        bar.update(1)

        # Stack detection happens per-card later; we just mark the step done.
        bar.update(1)

        try:
            ds_inv = extract_design_system(project_root)
        except Exception as exc:
            renderer.write(
                renderer.colored(
                    f"design-system extract skipped: {exc}", "dim_grey"
                )
            )
        bar.update(1)

        try:
            i18n_inv = extract_i18n(project_root)
        except Exception as exc:
            renderer.write(renderer.colored(f"i18n extract skipped: {exc}", "dim_grey"))
        bar.update(1)

        try:
            conv_inv = extract_conventions(project_root)
        except Exception as exc:
            renderer.write(
                renderer.colored(f"conventions extract skipped: {exc}", "dim_grey")
            )
        bar.update(1)

    renderer.write("")
    renderer.write(f"  {len(canonical_cards)} cards canônicos disponíveis em {canonical_dir}")

    checkpoint.step = "step-3-preset-suggestion"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    # ── Step 3 — Preset suggestion ───────────────────────────────────────────
    preset = _load_preset(PRESET_NAME)
    preset_detection = preset.get("detection") or {}
    preset_score, matched = _eval_detection_signals(project_root, preset_detection)
    threshold = float(preset_detection.get("threshold") or 0.6)

    summary_lines = [
        f"Preset proposto:  {PRESET_NAME}  (score {preset_score:.2f} / threshold {threshold:.2f})",
        "Sinais encontrados:",
    ]
    if matched:
        for m in matched:
            summary_lines.append(f"  · {m}")
    else:
        summary_lines.append("  (nenhum — projeto pode ser greenfield ou stack diferente)")
    renderer.write("")
    renderer.write(renderer.box("Resumo da detecção", summary_lines, width=78))

    # ── Step 4 — Preset confirmation ─────────────────────────────────────────
    renderer.write("")
    choice = ui_question.ask(
        "Confirmar preset kmp-mobile?",
        {
            "sim": f"confirmar {PRESET_NAME} (recomendado se signals casaram)",
            "outro": "escolher outro preset (não disponível no v1 — só kmp-mobile)",
            "abortar": "sair do init agora",
        },
        default="sim",
    )
    if choice == "abortar":
        renderer.write("ok, parado.")
        return 0
    if choice == "outro":
        raise InitError(
            "no v1 só existe o preset kmp-mobile. Os outros chegam no Phase 6."
        )

    checkpoint.preset = PRESET_NAME
    checkpoint.step = "step-5-backend-selection"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    # ── Step 5 — Backend selection (Cena 6.5) ────────────────────────────────
    preset_card_names = [c.get("name") for c in (preset.get("cards") or []) if c.get("name")]
    card_index = _index_cards(canonical_cards)

    backend_candidates = preset.get("backend-candidates") or {}
    if not backend_candidates:
        raise InitError("preset kmp-mobile sem backend-candidates declarados.")

    candidate_keys = list(backend_candidates.keys())
    candidate_summaries: dict[str, dict[str, Any]] = {}

    renderer.write("")
    renderer.write("[1:00] Backend — preciso da sua escolha")
    renderer.write("")
    for idx, key in enumerate(candidate_keys, start=1):
        spec = backend_candidates[key] or {}
        cards_extra = spec.get("cards") or []
        match_count = 0
        matched_signals_total: list[str] = []
        for card_name in cards_extra:
            card = card_index.get(card_name)
            if card is None:
                continue
            score, m = _eval_detection_signals(project_root, card.detection)
            if score >= float((card.detection or {}).get("threshold") or 0.5):
                match_count += 1
            matched_signals_total.extend(m)
        candidate_summaries[key] = {
            "spec": spec,
            "cards": cards_extra,
            "matches": match_count,
            "total": len(cards_extra),
            "signals": matched_signals_total[:6],
        }
        renderer.write(
            f"  [{idx}] {key}  (cards matched: {match_count}/{len(cards_extra)})"
        )
        desc = spec.get("description")
        if desc:
            renderer.write(f"        {desc}")
        for s in matched_signals_total[:3]:
            renderer.write(f"        · {s}")

    renderer.write(f"  [{len(candidate_keys)+1}] personalizar — selecionar cards manualmente")
    renderer.write("")

    options: dict[str, str] = {}
    for idx, key in enumerate(candidate_keys, start=1):
        options[str(idx)] = key
    custom_key = str(len(candidate_keys) + 1)
    options[custom_key] = "personalizar"

    backend_choice = ui_question.ask(
        "Qual cenário descreve este projeto?", options, default="1"
    )

    selected_card_names: list[str] = list(preset_card_names)
    if backend_choice == custom_key:
        all_card_options = {
            c.name: f"{c.category} · {c.description[:60]}…" for c in canonical_cards
        }
        picked = ui_question.ask_multi(
            "Selecione cards manualmente (mínimo 1):",
            all_card_options,
            min_selected=1,
        )
        selected_card_names = picked
        checkpoint.backend_choice = "custom"
    else:
        chosen_key = options[backend_choice]
        checkpoint.backend_choice = chosen_key
        extra = candidate_summaries[chosen_key]["cards"]
        for name in extra:
            if name not in selected_card_names:
                selected_card_names.append(name)

    checkpoint.selected_card_names = selected_card_names
    checkpoint.step = "step-6-resolve"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    selected_cards: list[CardManifest] = []
    missing_cards: list[str] = []
    for name in selected_card_names:
        card = card_index.get(name)
        if card is None:
            missing_cards.append(name)
        else:
            selected_cards.append(card)
    if missing_cards:
        renderer.write(
            renderer.colored(
                f"Atenção: cards declarados mas não encontrados no canonical: "
                f"{missing_cards}. Phase 4/5 ainda implementa esses cards — "
                "vou seguir sem eles.",
                "yellow",
            )
        )

    # ── Step 6 — Resolver ────────────────────────────────────────────────────
    renderer.write("")
    renderer.write("Resolvendo cards (deps + conflicts + topo-sort)…")
    res = resolve(selected_cards, user_provided_capabilities=LATENT_CAPS)
    if res.errors:
        renderer.write(
            mentor_calmo.three_paths_block(
                "RESOLVER-ERRORS",
                what_failed=f"resolver encontrou {len(res.errors)} erro(s) ao casar cards",
                where=", ".join(c.name for c in selected_cards),
                why=res.errors[:5],
                paths=[
                    {
                        "label": "voltar e escolher outro backend-candidate",
                        "motive": "alguns cards conflitam com a stack proposta",
                    },
                    {
                        "label": "personalizar (modo manual)",
                        "motive": "remover cards problemáticos um a um",
                    },
                    {
                        "label": "abortar e investigar os cards canônicos",
                        "motive": "pode ser um bug do card.yaml",
                    },
                ],
            )
        )
        return 2

    if res.warnings:
        for w in res.warnings:
            renderer.write(renderer.colored(f"warn: {w}", "yellow"))

    activated = res.activated
    renderer.write(
        f"  ✓ {len(activated)} cards ativados; "
        f"{len(res.resolved_capabilities)} capabilities resolvidas."
    )

    checkpoint.step = "step-7-snapshot"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    # ── Step 7 — Snapshot cards ──────────────────────────────────────────────
    renderer.write("")
    snapshots_root = cards_dir(project_root)
    ensure_dir(snapshots_root)
    card_sha_by_name: dict[str, str] = {}
    with ui_progress.progress(
        len(activated), "snapshotting cards", width=24
    ) as bar:
        for card in activated:
            project_card_dir = snapshots_root / card.name
            sha = snapshot_card(card.source_path, project_card_dir)
            card_sha_by_name[card.name] = sha
            bar.update(1)

    checkpoint.step = "step-7-5-orphan-signals"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    # ── Step 7.5 — Orphan signal handling (Gap 5) ───────────────────────────
    from validators._common import load_catalog as _load_overlay_catalog  # noqa: PLC0415

    try:
        overlay_catalog = _load_overlay_catalog(project_root)
    except Exception as exc:  # noqa: BLE001
        renderer.write(
            renderer.colored(
                f"warn: catálogo overlay inválido ({exc}); seguindo com canon-only",
                "yellow",
            )
        )
        overlay_catalog = None

    if overlay_catalog is not None:
        orphans = _check_orphan_signals(project_root, activated, overlay_catalog)
        if orphans:
            decision = _surface_three_paths(orphans, project_root=project_root)
            if decision.choice == "abort":
                return decision.exit_code
            if decision.choice == "adr-required":
                renderer.write(
                    renderer.colored(
                        f"⚠️  {decision.note} Init suspenso — re-run após promoção.",
                        "yellow",
                    )
                )
                return decision.exit_code or 7
            # "create-local" ou "ignore" → segue pra Step 8 com a `activated`
            # corrente. N2: catálogo expandido (no caso de create-local) só
            # entra em vigor no próximo `forge init` — o decision.note já
            # avisa o user. Re-detection inline fica pra v1.2.
            if decision.note:
                renderer.write(renderer.colored(decision.note, "yellow"))

    checkpoint.step = "step-7-6-qa"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    # ── Step QA — opt-in do verbo forge qa (Wave 7 — Task 7.4 / §9) ──────────
    # Pergunta interativa mentor-calmo PT-BR: enabled (default sim — comando
    # disponível) + auto-run-on-feature-done (default não — disparo manual).
    # Defaults vivem aqui; user mudar depois via `forge reconfigure -> qa`.
    renderer.write("")
    renderer.write(
        renderer.bold(
            "forge qa — gate adversarial multi-agente (red-team)"
        )
    )
    renderer.write(
        "Audita artefatos do lifecycle inventando cenários hostis "
        "(spec-vs-spec, chaos, coverage, validator-claim) e roda fixtures "
        "sintéticos em sandbox isolado. Verdict NÃO bloqueia retrospective "
        "nem commit — findings entram em proposed-evolutions pra forge evolve."
    )
    renderer.write("")
    qa_enabled = ui_question.confirm(
        "Ativar o comando `forge qa` neste projeto? "
        "(s = comando disponível, sem auto-run; N = desabilita o verbo)",
        default=True,
    )
    qa_auto_run = False
    if qa_enabled:
        qa_auto_run = ui_question.confirm(
            "Auto-run no feature-done (rodar qa antes do retrospective)? "
            "(s = projeto heavy-QA; N = disparo manual via `forge qa`)",
            default=False,
        )
    renderer.write(
        renderer.dim(
            f"qa.enabled={qa_enabled} · qa.auto-run-on-feature-done={qa_auto_run}"
        )
    )

    # ── Step 7.7 — Grant flow pra cards com sensitive env-needs (QA-11) ─────
    # Pergunta 3-caminhos (grant/deny/abort) por var sensitive declarada em
    # qa-extensions. Dedup cross-cards (var perguntada UMA vez). Decisão é
    # aplicada: cards com var denied saem de `activated`; vars granted são
    # persistidas em workflow-config.qa.sensitive-env-grants no Step 12.
    #
    # No primeiro init não há grants prévios (workflow-config ainda não
    # existe), então passamos dict vazio — evaluate só lê
    # `qa.sensitive-env-grants` que defaulta a [].
    try:
        grant_decision: GrantDecision = evaluate_sensitive_grants(activated, {})
    except UserAbortError as exc:
        renderer.write(
            mentor_calmo.pause_message(
                resume_command=f"forge init  # após reconciliar grants — {exc}"
            )
        )
        return 0  # aborta init sem persistir workflow-config

    # Aplica decisão: remove cards denied de `activated` (persist final
    # acontece em Step 12 via _build_workflow_config; new_grants_to_persist
    # é injetado em config['qa']['sensitive-env-grants'] logo depois).
    if grant_decision.denied_cards:
        activated = [c for c in activated if c.name not in grant_decision.denied_cards]
        renderer.write(
            renderer.colored(
                f"  ✓ {len(grant_decision.denied_cards)} card(s) removido(s) "
                f"por var sensitive denied: {', '.join(grant_decision.denied_cards)}",
                "yellow",
            )
        )

    checkpoint.step = "step-8-merge"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    # ── Step 8 — Merge contributions ────────────────────────────────────────
    merged = merge_contributions(activated)
    if merged.warnings:
        for w in merged.warnings[:5]:
            renderer.write(renderer.colored(f"merger warn: {w}", "yellow"))

    # ── Step 9 — Inventory snapshots ────────────────────────────────────────
    ensure_dir(inventory_dir(project_root))
    inv_written: list[str] = []
    if ds_inv is not None:
        write_design_system_inventory(project_root, ds_inv)
        inv_written.append("design-system.yaml")
    if i18n_inv is not None:
        write_i18n_inventory(project_root, i18n_inv)
        inv_written.append("i18n.yaml")
    if conv_inv is not None:
        write_conventions_inventory(project_root, conv_inv)
        inv_written.append("conventions.yaml")

    checkpoint.step = "step-10-memory"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    # ── Step 10 — Memory L1/L2 seed ──────────────────────────────────────────
    ensure_dir(memory_dir(project_root))
    ensure_dir(memory_dir(project_root) / "L1")
    ensure_dir(memory_dir(project_root) / "L1" / "archived")
    l2_path = memory_l2_path(project_root)
    if not l2_path.exists():
        write_yaml(
            l2_path,
            {
                "schema-version": 1,
                "project-slug": project_root.name,
                "last-updated": _utc_now_iso(),
                "patterns": [],
                "findings": [],
                "decisions-frozen": [],
            },
            atomic=True,
        )

    checkpoint.step = "step-11-graph"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    # ── Step 11 — Codebase graph ─────────────────────────────────────────────
    renderer.write("")
    renderer.write("[0:18] Building codebase graph…")
    with ui_progress.progress(100, "graph", width=24) as bar:
        last_pct = [0]

        def _cb(stage: str, done: int, total: int) -> None:
            pct = min(100, int((done / max(1, total)) * 100))
            if pct > last_pct[0]:
                bar.set(pct)
                last_pct[0] = pct

        graph_stats = build_full(
            project_root, db_path=graph_db_path(project_root), progress_cb=_cb
        )
        bar.set(100)
    renderer.write(
        f"  files={graph_stats['files_scanned']}  "
        f"symbols={graph_stats['symbols_extracted']}  "
        f"edges={graph_stats['edges_created']}  "
        f"{graph_stats['duration_ms']}ms"
    )

    checkpoint.step = "step-11.5-reuse-scan"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    # ── Step 11.5 — Reuse-intelligence proposals ────────────────────────────
    # Surfaces duplications, cross-module candidates, and cross-language KMP
    # migration hints detected by the graph builder. Queued as
    # DistillationProposals — user reviews via `forge evolve`.
    renderer.write("")
    renderer.write("[0:19] Scanning for reuse opportunities…")
    try:
        from engine.graph.duplicates import queue_proposals_from_table

        n_queued = queue_proposals_from_table(project_root)
    except Exception as exc:  # never fail init for a scan hiccup
        renderer.write(
            f"  ⚠ reuse scan errored: {type(exc).__name__}: {exc}"
        )
        n_queued = 0
    if n_queued:
        renderer.write(
            f"  ✓ {n_queued} reuse-intelligence proposal(s) queued — "
            "`forge evolve` to review"
        )
    else:
        renderer.write("  ✓ no reuse opportunities detected")

    # ── Step 11.6 — Incremental detection hook (opt-in) ─────────────────────
    # Writes a hook script in .claude/hooks/. Wiring it to Claude Code's
    # `tool-use:post:Edit` hook is left to the user — we print a one-liner
    # they can paste into .claude/settings.local.json.
    hooks_dir = claude_dir(project_root) / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_script = hooks_dir / "post-edit-detect-duplications.sh"
    hook_script.write_text(
        "#!/usr/bin/env bash\n"
        "# Post-edit hook: surface reuse-intelligence findings introduced by the edit.\n"
        "# Installed by `forge init` — wire it up in .claude/settings.local.json:\n"
        "#   { \"hooks\": { \"tool-use:post:Edit\": "
        "[{\"command\": \"$CLAUDE_PROJECT_DIR/.claude/hooks/post-edit-detect-duplications.sh \\\"$file_path\\\"\"}] } }\n"
        "set -e\n"
        "FILE=\"${1:-}\"\n"
        "[ -z \"$FILE\" ] && exit 0\n"
        "[ -f \"${CLAUDE_PROJECT_DIR:-$PWD}/.claude/graph.db\" ] || exit 0\n"
        "forge graph detect-incremental \"$FILE\" 2>/dev/null || true\n"
    , encoding="utf-8")
    try:
        import stat as _stat
        hook_script.chmod(hook_script.stat().st_mode | _stat.S_IXUSR | _stat.S_IXGRP)
    except OSError:
        pass
    renderer.write(
        "  · hook em `.claude/hooks/post-edit-detect-duplications.sh` "
        "(referencie em settings.local.json pra detection inline)"
    )

    checkpoint.step = "step-12-write-config"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    # ── Step 12 — workflow-config.yaml ───────────────────────────────────────
    config = _build_workflow_config(
        project_root=project_root,
        activated=activated,
        card_sha_by_name=card_sha_by_name,
        merged=merged,
        ds_inv=ds_inv,
        i18n_inv=i18n_inv,
        conv_inv=conv_inv,
        preset=preset,
        backend_choice=checkpoint.backend_choice or "unknown",
        qa_enabled=qa_enabled,
        qa_auto_run=qa_auto_run,
    )

    # QA-11: persist sensitive-env-grants decididos no Step 7.7
    if grant_decision.new_grants_to_persist:
        qa_cfg = config.setdefault("qa", {})
        existing = list(qa_cfg.get("sensitive-env-grants", []))
        for var in grant_decision.new_grants_to_persist:
            if var not in existing:
                existing.append(var)
        qa_cfg["sensitive-env-grants"] = existing

    write_yaml(workflow_config_path(project_root), config, atomic=True)

    checkpoint.step = "step-12.5-version-lock"

    # ── Step 12.5 — forge-version-lock.yaml ─────────────────────────────────
    # `forge doctor` checks this lock to detect engine/project version drift.
    version_lock_path = claude_dir(project_root) / "forge-version-lock.yaml"
    write_yaml(
        version_lock_path,
        {
            "schema-version": 1,
            "forge-version": FORGE_VERSION,
            "locked-at": _utc_now_iso(),
            "project": project_root.name,
        },
        atomic=True,
    )

    checkpoint.step = "step-12.6-gitignore"

    # ── Step 12.6 — .claude/.gitignore ──────────────────────────────────────
    # Auto-managed gitignore per docs/design/05-filesystem-layout.md so that
    # graph.db, archived L1 entries and checkpoints stay out of git.
    gitignore_path = claude_dir(project_root) / ".gitignore"
    gitignore_content = (
        "# feature-forge — auto-managed\n"
        "graph.db\n"
        "graph.db-journal\n"
        "graph.db-wal\n"
        "memory/L1/**/!archived/\n"
        "memory/L1/**/!archived/**\n"
        "*.bak\n"
        ".init-checkpoint.yaml\n"
        ".reconfigure-draft.yaml\n"
        ".evolve-checkpoint.yaml\n"
    )
    ensure_dir(gitignore_path.parent)
    gitignore_path.write_text(gitignore_content, encoding="utf-8")

    checkpoint.step = "step-14-history"

    # ── Step 13 — Hooks install ──────────────────────────────────────────────
    # Copy canonical shims into .claude/hooks/ and wire git hooks symlinks.
    ensure_dir(claude_dir(project_root) / "hooks")
    try:
        n_hooks = _install_hooks(project_root)
        _install_git_hooks(project_root)
        if n_hooks:
            renderer.write(f"  └─ {n_hooks} hooks instalados em .claude/hooks/")
    except Exception as exc:  # pragma: no cover - hooks must not block init
        renderer.write(
            renderer.colored(f"hooks install warn: {exc}", "yellow")
        )

    # ── Step 14 — workflow-config-history.jsonl seed ─────────────────────────
    # Schema HIST-001..012 per docs/schemas/workflow-config-history.md.
    # Greenfield init → before-snapshot-sha is null; after-snapshot-sha is the
    # sha256 of the workflow-config.yaml we just wrote.
    cfg_path = workflow_config_path(project_root)
    after_sha = file_sha256(cfg_path) if cfg_path.is_file() else ""
    history_path = claude_dir(project_root) / "workflow-config-history.jsonl"
    history_entry = {
        "schema-version": 1,
        "timestamp": _utc_now_iso(),
        "command": "forge init",
        "action": "init",
        "before-snapshot-sha": None,
        "after-snapshot-sha": after_sha,
        "user-confirmed": True,
        "notes": (
            f"Greenfield init · preset={PRESET_NAME} · "
            f"backend={checkpoint.backend_choice} · cards={len(activated)}"
        )[:280],
    }
    with history_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(history_entry, ensure_ascii=False) + "\n")

    _clear_checkpoint(project_root)

    # ── Step 15 — Final summary ──────────────────────────────────────────────
    n_caps = len(res.resolved_capabilities)
    n_components = len(ds_inv.components) if ds_inv else 0
    n_i18n = len(i18n_inv.keys) if i18n_inv else 0

    summary = [
        f"Projeto:        {project_root.name}",
        f"Preset:         {PRESET_NAME}  ·  backend: {checkpoint.backend_choice}",
        f"Cards ativos:   {len(activated)}",
        f"Capabilities:   {n_caps}",
        f"Inventories:    {', '.join(inv_written) if inv_written else '(none)'}",
        f"DS components:  {n_components}",
        f"i18n keys:      {n_i18n}",
        "",
        "Saved to .claude/:",
        "  workflow-config.yaml  ·  cards/  ·  inventory/  ·  memory/  ·  graph.db",
        "",
        "Próximos passos:",
        "  forge plan <slug>     começar uma feature",
        "  forge doctor          validar saúde do setup",
        "  forge status          panorama atual",
    ]
    renderer.write("")
    renderer.write(renderer.box("Forge ready", summary, width=78))

    return 0


# ── workflow-config builder ──────────────────────────────────────────────────


def _build_workflow_config(
    *,
    project_root: Path,
    activated: list[CardManifest],
    card_sha_by_name: dict[str, str],
    merged: Any,
    ds_inv: Any,
    i18n_inv: Any,
    conv_inv: Any,
    preset: dict[str, Any],
    backend_choice: str,
    qa_enabled: bool = True,
    qa_auto_run: bool = False,
) -> dict[str, Any]:
    """Assemble the workflow-config.yaml dict (schema v1).

    Follows docs/schemas/workflow-config.md. Optional blocks are populated
    with sane defaults when init can't infer them (ticketing, external-docs).
    """
    now = _utc_now_iso()
    preset_defaults = preset.get("defaults") or {}
    target = preset.get("target") or {}

    project_slug = project_root.name.lower().replace("_", "-")

    config: dict[str, Any] = {
        "schema-version": 1,
        "identity": {
            "project-name": project_root.name,
            "project-slug": project_slug,
            "preset": PRESET_NAME,
            "backend-choice": backend_choice,
            "created-at": now,
            "last-reconfigure": now,
            "forge-version": FORGE_VERSION,
        },
        "platforms": {
            "active": list(preset_defaults.get("platforms.active") or target.get("platforms") or []),
            "primary-language-per-platform": {
                "android": preset_defaults.get(
                    "platforms.primary-language-per-platform.android", "kotlin"
                ),
                "ios": preset_defaults.get(
                    "platforms.primary-language-per-platform.ios", "swift"
                ),
                "kmp": preset_defaults.get(
                    "platforms.primary-language-per-platform.kmp", "kotlin"
                ),
            },
        },
        "cards": {
            "source": "standalone-repo",
            "source-url": "thgMatajs/feature-forge",
            "snapshot-root": ".claude/cards/",
            "active": [
                {
                    "name": c.name,
                    "version": c.version,
                    "sha256": card_sha_by_name.get(c.name, ""),
                    "source": str(c.source_path),
                    "installed-at": now,
                }
                for c in activated
            ],
        },
        "paths": _build_paths(project_root, conv_inv),
        "conventions": _build_conventions(conv_inv, ds_inv, i18n_inv, preset_defaults),
        "backend": _build_backend(backend_choice),
        "validators": {"fail-fast": True},
        "cleanup": {"bak-retention-days": 7},
        "ticketing": {
            "provider": "none",
            "workspace": None,
            "default-project": None,
        },
        "external-docs": {
            "primary-provider": "none",
            "cache-ttl-days": {
                "library-docs": 7,
                "framework-patterns": 14,
                "convention-patterns": 30,
            },
            "privacy-mode": False,
        },
        "memory": {
            "layers-enabled": ["L1", "L2", "L3"],
            "l2": {
                "location": ".claude/memory/L2-project.yaml",
                "max-size-mb": 0.5,
            },
        },
        "graph": {
            "backend": "sqlite",
            "location": ".claude/graph.db",
            "rebuild-policy": "incremental",
        },
        "persona": {
            "name": "mentor-calmo",
            "primary-language": "pt-BR",
            "language-mirroring": True,
            "drill-down-aggressiveness": "medium",
            "explain-why-each-question": True,
            "closing-style": "didactic",
        },
        "workflow": {
            "readiness-strictness": "standard",
        },
        # Wave 7 Task 7.4 / spec §9 — bloco qa: completo com defaults.
        # User mexe via `forge reconfigure -> qa` (5 opções) ou edita
        # diretamente este arquivo. Schema canônico em §9 da spec.
        "qa": {
            "enabled": bool(qa_enabled),
            "auto-run-on-feature-done": bool(qa_auto_run),
            "sandbox-budget-seconds-total": 60,
            "agent-timeout-seconds": 15,
            "scope-defaults": {
                "paranoid-max-features": 10,
            },
            "extensions": {
                "disabled": [],
            },
            "retention-days": 14,
        },
    }
    return config


def _build_backend(backend_choice: str) -> dict[str, Any]:
    """Monta o bloco `backend:` baseado no backend-candidate escolhido (Cena 6.5).

    Mapeamento canônico (preset kmp-mobile):
    - firebase-stack → provider=firebase com services completos
    - rest-stack     → provider=rest
    - hybrid         → provider=hybrid (firebase só p/ auth + rest p/ dados)
    - local-only     → provider=local-only
    - custom/unknown → provider=none (usuário ajusta manualmente)
    """
    choice = (backend_choice or "").strip().lower()
    if choice == "firebase-stack":
        return {
            "provider": "firebase",
            "firebase": {
                "dev-project": None,
                "prod-project": None,
                "services": ["auth", "firestore", "storage", "crashlytics"],
            },
        }
    if choice == "rest-stack":
        return {
            "provider": "rest",
            "rest": {
                "base-url": None,
                "auth-mode": "jwt-bearer",
            },
        }
    if choice == "hybrid":
        return {
            "provider": "hybrid",
            "firebase": {
                "dev-project": None,
                "prod-project": None,
                "services": ["auth"],
            },
            "rest": {
                "base-url": None,
                "auth-mode": "jwt-bearer",
            },
        }
    if choice == "local-only":
        return {"provider": "local-only"}
    return {"provider": "none"}


def _build_paths(project_root: Path, conv_inv: Any) -> dict[str, Any]:
    """Best-effort path inference. Greenfield gets sensible defaults."""
    paths: dict[str, Any] = {
        "features-package-root": "docs/feature-implementation-workflow/features",
        "inventory-root": ".claude/inventory",
        "memory-root": ".claude/memory",
        "graph-path": ".claude/graph.db",
        "hooks-root": ".claude/hooks",
        "feature-roots": {},
        "tests-roots": {},
    }
    candidates: dict[str, list[str]] = {
        "android": ["androidApp/feature", "app/src/main/java"],
        "ios": ["iosApp/iosApp/Features", "iosApp/Features"],
        "shared": ["shared/feature", "shared"],
        "web": ["webApp/src/features", "web/src/features"],
    }
    test_candidates: dict[str, list[str]] = {
        "android": ["androidApp/feature/**/src/test", "app/src/test"],
        "ios": ["iosApp/iosAppTests", "iosApp/Tests"],
        "shared": ["shared/feature/**/src/commonTest", "shared/src/commonTest"],
        "web": ["webApp/src/__tests__", "web/src/__tests__"],
    }
    for plat, opts in candidates.items():
        for opt in opts:
            head = opt.split("**", 1)[0]
            if (project_root / head).exists():
                paths["feature-roots"][plat] = opt
                break
    for plat, opts in test_candidates.items():
        for opt in opts:
            head = opt.split("**", 1)[0]
            if (project_root / head).exists():
                paths["tests-roots"][plat] = opt
                break
    return paths


def _build_conventions(
    conv_inv: Any, ds_inv: Any, i18n_inv: Any, preset_defaults: dict[str, Any]
) -> dict[str, Any]:
    """Merge convention inventory + preset defaults into the config block."""
    conv: dict[str, Any] = {}
    if conv_inv is not None and getattr(conv_inv, "raw", None):
        raw = conv_inv.raw
        conv["folder-layout"] = raw.get("folder-layout") or {
            "android": preset_defaults.get("conventions.folder-layout.android"),
            "ios": preset_defaults.get("conventions.folder-layout.ios"),
        }
        conv["state-pattern"] = (raw.get("state-pattern") or {}).get("name", "stateui")
        conv["di-pattern"] = (raw.get("di-pattern") or {}).get(
            "name", preset_defaults.get("conventions.di-pattern", "koin-annotations")
        )
        conv["navigation"] = raw.get("navigation") or {
            "android": preset_defaults.get("conventions.navigation.android", "nav3"),
            "ios": preset_defaults.get(
                "conventions.navigation.ios", "swiftui-navigation-stack"
            ),
        }
        conv["test-pattern"] = raw.get("test-pattern") or {}
    else:
        conv["folder-layout"] = {
            "android": preset_defaults.get("conventions.folder-layout.android"),
            "ios": preset_defaults.get("conventions.folder-layout.ios"),
        }
        conv["state-pattern"] = "stateui"
        conv["di-pattern"] = preset_defaults.get(
            "conventions.di-pattern", "koin-annotations"
        )
        conv["navigation"] = {
            "android": preset_defaults.get("conventions.navigation.android", "nav3"),
            "ios": preset_defaults.get(
                "conventions.navigation.ios", "swiftui-navigation-stack"
            ),
        }

    if i18n_inv is not None and getattr(i18n_inv, "raw", None):
        sot = (i18n_inv.raw.get("source-of-truth") or {})
        conv["i18n"] = {
            "source-path": sot.get("path"),
            "locales": sot.get("locales") or [],
            "primary-locale": sot.get("primary-locale"),
        }
    else:
        conv["i18n"] = {"source-path": None, "locales": [], "primary-locale": None}

    if ds_inv is not None and getattr(ds_inv, "raw", None):
        det = ds_inv.raw.get("detection") or {}
        conv["design-system"] = {
            "naming-pattern": det.get("naming-pattern"),
            "base-paths": det.get("base-paths") or {},
        }

    conv["branch"] = {
        "pattern": "feature/{slug}",
        "requires-ticket": False,
    }
    return conv
