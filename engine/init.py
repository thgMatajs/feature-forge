"""`forge init` — greenfield/brownfield install command.

This is the MOST IMPORTANT command of feature-forge. It:

- detects whether the cwd is a fresh project (greenfield) or already has
  `.claude/forge/forge-config.yaml` (brownfield — defer to `forge reconfigure`);
- runs cinematic discovery (cards, stack detection, design system, i18n,
  conventions);
- proposes the canonical preset (`kmp-mobile`) and asks the user to confirm;
- asks the user to configure backend cells via bundle picker (greenfield)
  OR composer-driven detection (brownfield W7.1/W7.2 handlers, never
  auto-applied — auditor confirms cells before snapshot);
- resolves card dependencies/conflicts via the resolver;
- snapshots cards into `.claude/cards/`;
- merges contributions, writes inventory snapshots, seeds memory L1/L2 dirs;
- builds the codebase graph (SQLite, deterministic);
- writes `.claude/forge/forge-config.yaml` (schema v1.3) + history JSONL seed;
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

if TYPE_CHECKING:
    # N5: type-annotate `_check_orphan_signals(catalog)` sem ativar import
    # eager (validators é layer-superior na arquitetura — engine consome
    # type-only).
    from validators._common import CapabilityCatalog  # noqa: F401
    from engine.cards.merger import MergedContributions  # noqa: F401

from engine import __version__ as FORGE_VERSION
from engine.cards.grant import (
    GrantDecision,
    UserAbortError,
    evaluate_sensitive_grants,
)
from engine.cards.loader import load_all_cards, CardManifest
from engine.cards import CardError
from engine.cards.merger import merge_contributions, render_merged_template
from engine.cards.resolver import resolve
from engine.cards.snapshotter import snapshot_card
from engine.detection import _eval as _detection_eval
from engine.detection._axes import BACKEND_AXES
from engine.detection._eval import _SKIP_DIRS, _walk_recursive_pruned
from engine.detection.composer import Cell, Conflict, compose_backend_axes
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
from engine.ui.exit_codes import (
    ERR_ABORTED,
    ERR_INIT_FAILED,
    ERR_USAGE,
    fail_with_tag,
)
from engine.utils.paths import (
    FEATURE_WORKFLOW_DIRNAME,
    cards_canonical_dir,
    cards_dir,
    claude_dir,
    ensure_dir,
    forge_cards_local_dir,
    forge_config_path,
    forge_dir,
    forge_home,
    forge_hooks_dir,
    graph_db_path,
    inventory_dir,
    lifecycle_root,
    mem_asset_path,
    mem_asset_version_path,
    memory_dir,
    memory_l2_path,
    vendored_mem_path,
    vendored_mem_version_path,
)
from engine.utils.sha256 import file_sha256
from engine.utils.yaml_io import read_yaml_or_default, write_yaml
from engine.utils.checkpoint_io import (
    clear_checkpoint as _clear_checkpoint_io,
    save_yaml_checkpoint as _save_yaml_checkpoint_io,
)
from engine.utils.iso import utc_now_iso as _utc_now_iso_shared
from engine.integrations.mem import mem_call

PRESET_NAME = "kmp-mobile"
LATENT_CAPS = ["android-platform", "ios-platform", "swift-language"]
USAGE_HINT = "Uso: forge init"


# ── Errors ───────────────────────────────────────────────────────────────────


class InitError(RuntimeError):
    """Fatal init error — printed at top-level and translates to exit code 2."""


# ── Checkpoint (Decision 27) ─────────────────────────────────────────────────


@dataclass
class _InitCheckpoint:
    """State serialized on Ctrl+C, so a follow-up `forge init` can offer resume.

    DRIFT-1 W2.T3b — extend: campo ``intent_id`` adicionado pra correlacao
    com ``.claude/forge/state/forge-response.json`` no protocolo intent. Default
    ``None`` preserva o contract dos call sites legacy (Ctrl+C pause sem
    prompt ativo). Quando o pause vem do chokepoint (PausedForInputError),
    o handler grava intent_id ANTES do ask — re-invocacao usa esse campo
    pra confirmar que a response no disco corresponde ao prompt esperado.

    Outcome C: dataclass per-subcommand mantido — sem import de
    ``engine.qa.checkpoint`` (Decision 22).
    """

    step: str
    at: str
    project_root: str
    preset: str | None = None
    selected_card_names: list[str] = field(default_factory=list)
    # W7.4 — substitui ``backend_choice`` (legacy monolítico) por cells
    # multi-axis (``backend.<axis>.<platform>``). Default ``None`` cobre
    # checkpoint salvo antes do Step 5 (backend selection ainda não rodou).
    backend_cells: dict[str, Any] | None = None
    intent_id: str | None = None


def _checkpoint_path(project_root: Path) -> Path:
    return claude_dir(project_root) / ".init-checkpoint.yaml"


# Os 4 helpers abaixo são thin shims sobre ``engine.utils.checkpoint_io`` +
# ``engine.utils.iso`` — consolidação dos 30 duplicates + 10 cópias de
# ``_utc_now_iso_*`` apontada pelos findings #5 e #21 do master review do
# PR #11. ``init.py`` é o template canônico (citado em
# ``docs/superpowers/specs/drift-1-intent-protocol.md §3``) — preservamos
# os nomes não-sufixados ``_save_checkpoint`` / ``_load_checkpoint`` /
# ``_clear_checkpoint`` / ``_utc_now_iso`` que os testes em
# ``tests/unit/test_engine_init_resume.py`` consomem.
#
# Diferença sutil preservada vs. os 9 outros handlers: ``_load_checkpoint``
# em init **não** filtra ``dict`` defensivamente — ele retorna o que
# ``read_yaml_or_default`` retornar (potencialmente lista, string, etc.).
# Para preservar bit-a-bit esse comportamento histórico, mantemos a
# implementação local em vez de delegar para ``load_yaml_checkpoint``.


def _save_checkpoint(cp: _InitCheckpoint) -> None:
    _save_yaml_checkpoint_io(
        _checkpoint_path(Path(cp.project_root)),
        {
            "schema-version": 1,
            "step": cp.step,
            "at": cp.at,
            "project-root": cp.project_root,
            "preset": cp.preset,
            "selected-card-names": cp.selected_card_names,
            # W7.4 — cells multi-axis (vide adapters em
            # ``_composer_result_to_cells`` / ``_bundle_to_cells``).
            "backend-cells": cp.backend_cells,
            "intent-id": cp.intent_id,
        },
    )


def _load_checkpoint(project_root: Path) -> dict[str, Any] | None:
    path = _checkpoint_path(project_root)
    if not path.exists():
        return None
    data = read_yaml_or_default(path, None)
    if not isinstance(data, dict):
        return None
    return data


def _clear_checkpoint(project_root: Path) -> None:
    _clear_checkpoint_io(_checkpoint_path(project_root))
    # BUG-2: o discovery cache segue o lifecycle do checkpoint — limpa junto
    # (evita estado stale vazar entre features / pós-discard).
    _clear_discovery_cache(project_root)


# ── BUG-2 — discovery cache (persistente em disco, lifecycle=checkpoint) ──────
#
# O Step 2 (discovery) re-rodava os 3 extractors caros
# (extract_design_system/i18n/conventions) a CADA invocação do init —
# inclusive no loop mecânico (host replaying), onde cada response é um
# PROCESSO NOVO (CLI). Em monorepo real isso custa ~220s/ciclo. LRU
# intra-processo NÃO ajuda (cada processo zera o LRU); o cache TEM que ser
# persistente em disco.
#
# L-001: nome concreto, persistente, sob `.claude/`, coberto pelo
# `.claude/.gitignore` que `_write_claude_gitignores` semeia. Lifecycle =
# checkpoint (some com `_clear_checkpoint`).
_DISCOVERY_CACHE_NAME = ".init-discovery-cache.yaml"


def _discovery_cache_path(project_root: Path) -> Path:
    return claude_dir(project_root) / _DISCOVERY_CACHE_NAME


def _discovery_source_fingerprint(project_root: Path) -> str:
    """Fingerprint barato do estado top-level do projeto (B2 — hardening).

    Hash do (nome, mtime_ns) dos filhos de 1º nível do project_root,
    EXCLUINDO o diretório `.claude/` (gerenciado pelo forge — não é source do
    usuário; o cache fica lá e causaria instabilidade circular no fingerprint).
    Captura adições/remoções top-level SEM re-varrer a árvore (o custo que o
    cache evita). Trade-off consciente: não detecta edição PROFUNDA que não
    muda o mtime de um dir-pai top-level — cinto-e-suspensório sobre o
    lifecycle (não substituto). O lifecycle de checkpoint segue sendo a
    garantia primária; o fingerprint é o hardening fora do replay mecânico.
    """
    import hashlib

    _EXCLUDED = {".claude"}
    h = hashlib.sha256()
    try:
        for child in sorted(project_root.iterdir(), key=lambda p: p.name):
            if child.name in _EXCLUDED:
                continue
            try:
                h.update(child.name.encode())
                h.update(b"\x00")
                h.update(str(child.stat().st_mtime_ns).encode())
                h.update(b"\x00")
            except OSError:
                continue
    except OSError:
        return ""
    return h.hexdigest()


def _save_discovery_cache(
    project_root: Path,
    ds_inv: "DesignSystemInventory | None",
    i18n_inv: "I18nInventory | None",
    conv_inv: "ConventionsInventory | None",
) -> None:
    """Persiste o resultado de discovery (os 3 `.raw` + contagens) em disco.

    Cacheia o que o pipeline downstream consome dos inventories:
      - ds_inv: `.raw` + `len(.components)` (summary L2827, _build_* L3881).
      - i18n_inv: `.raw` + `len(.keys)` (summary L2828, _build_* L3871).
      - conv_inv: `.raw` (_build_* L3838).
    Não cacheia objetos ricos inteiros (DSComponent/I18nKey) — só o necessário
    pra reproduzir fielmente o output, mantendo o YAML enxuto e round-trippável.
    """
    payload: dict[str, Any] = {
        "schema-version": 1,
        "source-fingerprint": _discovery_source_fingerprint(project_root),
    }
    if ds_inv is not None:
        payload["design-system"] = {
            "raw": ds_inv.raw,
            "n-components": len(ds_inv.components),
        }
    if i18n_inv is not None:
        payload["i18n"] = {"raw": i18n_inv.raw, "n-keys": len(i18n_inv.keys)}
    if conv_inv is not None:
        payload["conventions"] = {"raw": conv_inv.raw}
    write_yaml(_discovery_cache_path(project_root), payload, atomic=True)


def _load_discovery_cache(
    project_root: Path,
) -> tuple[
    "DesignSystemInventory | None",
    "I18nInventory | None",
    "ConventionsInventory | None",
] | None:
    """Carrega o discovery cache; None em cache-miss (caller re-roda discovery).

    Reconstrói os inventories preservando exatamente os campos que o pipeline
    consome (contagens + `.raw`). `components`/`keys` viram listas de
    placeholders do tamanho correto — o downstream só usa `len(...)` deles.

    **Invariante de correção (WR-03 — com fingerprint barato top-level):**
    O lifecycle de checkpoint segue sendo a garantia primária:

      - O cache só é CARREGADO sob `host_is_replaying` (loop mecânico de replay):
        o host está respondendo prompts in-flight, NÃO editando source.
      - O lifecycle é ATADO ao checkpoint: `_clear_checkpoint` →
        `_clear_discovery_cache` (discard / abort / novo-init limpam).

    Adicionalmente (B2 — Fase 1): o cache armazena um fingerprint barato
    top-level (`_discovery_source_fingerprint`) para invalidação cinto-e-
    suspensório fora do replay mecânico. Caches pré-B2 sem `source-fingerprint`
    são automaticamente tratados como cache-miss (seguro: re-roda discovery
    uma vez e re-popula com fingerprint).
    """
    path = _discovery_cache_path(project_root)
    if not path.exists():
        return None
    data = read_yaml_or_default(path, None)
    if not isinstance(data, dict):
        return None

    # B2 (Fase 1): cache-miss se o fingerprint do source divergiu do gravado.
    # Hardening cinto-e-suspensório sobre o lifecycle de checkpoint.
    # Caches pré-B2 sem 'source-fingerprint' → cache-miss seguro (re-roda
    # discovery uma vez, re-popula com fingerprint).
    cached_fp = data.get("source-fingerprint")
    if cached_fp != _discovery_source_fingerprint(project_root):
        return None

    # Imports locais: evita custo no import-time do módulo + mantém a fronteira
    # com inventory clara (reuso das dataclasses canônicas, não re-derivação).
    from engine.inventory.conventions import ConventionsInventory
    from engine.inventory.design_system import (
        DesignSystemInventory,
        DSComponent,
        DSTokens,
    )
    from engine.inventory.i18n import I18nInventory, I18nKey

    ds_inv: DesignSystemInventory | None = None
    ds_data = data.get("design-system")
    if isinstance(ds_data, dict):
        raw = ds_data.get("raw") or {}
        n = int(ds_data.get("n-components") or 0)
        tokens_raw = raw.get("tokens") or {}
        ds_inv = DesignSystemInventory(
            components=[
                DSComponent(name="", level="unknown", status="unknown")
                for _ in range(n)
            ],
            tokens=DSTokens(
                colors=dict((tokens_raw.get("colors") or {}).get("values") or {}),
                spacing=dict((tokens_raw.get("spacing") or {}).get("values") or {}),
                radius=dict((tokens_raw.get("radii") or {}).get("values") or {}),
                typography=dict(
                    (tokens_raw.get("typography") or {}).get("values") or {}
                ),
            ),
            raw=raw,
        )

    i18n_inv: I18nInventory | None = None
    i18n_data = data.get("i18n")
    if isinstance(i18n_data, dict):
        raw = i18n_data.get("raw") or {}
        n = int(i18n_data.get("n-keys") or 0)
        sot = raw.get("source-of-truth") or {}
        i18n_inv = I18nInventory(
            keys=[I18nKey(key="") for _ in range(n)],
            languages=list(sot.get("locales") or []),
            source_of_truth=sot.get("path", "unknown"),
            generated_paths=dict((raw.get("generation") or {}).get("outputs") or {}),
            raw=raw,
        )

    conv_inv: ConventionsInventory | None = None
    conv_data = data.get("conventions")
    if isinstance(conv_data, dict):
        conv_inv = ConventionsInventory(raw=conv_data.get("raw") or {})

    return ds_inv, i18n_inv, conv_inv


def _clear_discovery_cache(project_root: Path) -> None:
    path = _discovery_cache_path(project_root)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _resume_option_labels() -> dict[str, str]:
    """Labels do prompt de resume — honestas pós pilot R1 (P-11).

    ``resume`` CONTINUA do step salvo (reaproveita o progresso); ``discard``
    recomeça limpo; ``abort`` sai sem mexer. Extraído pra função testável
    (o ``stable_intent_id`` do resume é derivado destas labels).
    """
    return {
        "resume": "continuar de onde o init parou (reaproveita o progresso salvo)",
        "discard": "descartar o checkpoint e recomeçar do zero",
        "abort": "sair sem mexer em nada",
    }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp — thin shim sobre ``engine.utils.iso``."""
    return _utc_now_iso_shared()


def _is_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


# M6 (W-DEBT): `_detect_brownfield` removido — era dead-code (zero caller em
# engine/, só testes) e seu docstring anunciava um switch de modo que não
# existe. O init JÁ é brownfield-safe por outros meios, sempre-ativos e
# independentes de detecção: merge_settings_json append-only, hook delegator
# encadeado, e isolamento via sub-namespace .claude/forge/. Não há "modo
# brownfield" condicional pra ligar.


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
        # BUG-5: `_walk_recursive_pruned` poda `_SKIP_DIRS` NA DESCIDA (não
        # materializa node_modules/.gradle inteiros antes de filtrar). O filtro
        # `startswith(".")` (H-002) PERMANECE pós-walk: cobre dirs ocultos
        # ARBITRÁRIOS (.hidden etc.) que não estão nomeados em `_SKIP_DIRS`.
        for path in _walk_recursive_pruned(project_root, pattern, _SKIP_DIRS):
            try:
                parts = path.relative_to(project_root).parts
            except ValueError:
                continue
            # C16: filtra dirs ocultos (.git etc.) — o helper já podou
            # `_SKIP_DIRS`; este filtro cobre o startswith(".") arbitrário.
            if any(part.startswith(".") for part in parts):
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
        renderer.write("     Materializa card(s) local(is) em .claude/forge/cards/local/ cobrindo")
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
    canon_root = cards_dir(project_root)
    canon_names: set[str] = set()
    if canon_root.is_dir():
        canon_names = {
            d.name
            for d in canon_root.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name != "local"
        }
    name = base_name if base_name not in canon_names else f"{base_name}-local"

    # Task 0.8 (v1.3 pilot-ready): local card vive em
    # ``.claude/forge/cards/local/<name>/`` (sub-namespace spec §2).
    local_root = forge_cards_local_dir(project_root) / name
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


def _load_preset(name: str) -> dict[str, Any]:
    """Load a preset definition from FORGE_HOME/presets/{name}/preset.yaml."""
    path = forge_home() / "presets" / name / "preset.yaml"
    if not path.is_file():
        raise InitError(f"preset not found: {path}")
    return read_yaml_or_default(path, {}) or {}


def _index_cards(canonical: list[CardManifest]) -> dict[str, CardManifest]:
    return {c.name: c for c in canonical}


def _close_provider_deps(
    selected_card_names: list[str],
    card_index: dict[str, CardManifest],
) -> list[str]:
    """Fecha deps de provider de 1 nível antes do resolver (pilot R1, P-09).

    Pra cada card selecionado, se algum label em `requires` não é provido por
    nenhum card já selecionado, procura no catálogo canônico um card que o
    provê e o inclui. Conservador: 1 nível (o provider incluído pode trazer
    seus próprios requires — esses caem no resolver, que reporta DEP-MISSING
    real se ainda faltar; daí o gate de recuperação do WS-B-3). NÃO inventa
    cards — só puxa do catálogo existente. Determinístico: ordem de inclusão
    alfabética por nome do provider.

    Latentes (android-platform/ios-platform/...) NÃO são fechados aqui — são
    user_provided_capabilities passados ao resolver.
    """
    closed = list(selected_card_names)
    selected_set = set(closed)
    # provider index: label -> sorted card names que o provêem (catálogo todo).
    label_providers: dict[str, list[str]] = {}
    for name, card in card_index.items():
        for label in (card.provides or []):
            label_providers.setdefault(label, []).append(name)
    for plist in label_providers.values():
        plist.sort()
    # Labels já cobertos pelos cards selecionados.
    covered: set[str] = set()
    for name in closed:
        card = card_index.get(name)
        if card:
            covered.update(card.provides or [])
    for name in list(closed):
        card = card_index.get(name)
        if not card:
            continue
        for need in (card.requires or []):
            if need in covered:
                continue
            providers = label_providers.get(need, [])
            if not providers:
                continue  # nenhum card canônico provê → resolver reporta DEP-MISSING
            provider = providers[0]
            if provider not in selected_set:
                closed.append(provider)
                selected_set.add(provider)
                covered.update(card_index[provider].provides or [])
    return closed


def _resolver_error_gate(
    errors: list[str],
    *,
    project_root: Path,
) -> str:
    """Gate de resolver-errors — PAUSA pra escolha (exit 2), não aborta (P-10).

    Retorna a escolha 'a'|'b'|'c'. Na primeira entrada, ask_three_paths emite
    o intent + levanta PausedForInputError (cli.main → exit 2); na re-entrada
    consome a response. Mantém exatamente 3 caminhos (disciplina §1).
    """
    paths = [
        {
            "label": "voltar e re-selecionar o backend",
            "motive": (
                "alguns cards ficaram sem dependência satisfeita — re-rodar o "
                "backend selection pode incluir o provider faltante"
            ),
        },
        {
            "label": "abortar e investigar os cards canônicos",
            "motive": (
                "pode ser um card.yaml com requires sem provider no catálogo "
                "(bug de card)"
            ),
        },
        {
            "label": "seguir só com os cards resolvíveis",
            "motive": (
                "descarta os cards problemáticos e instala o subconjunto que "
                "resolve (best-effort)"
            ),
        },
    ]
    # WR-02: o detalhe multi-linha dos erros NÃO vai embutido no gate_name —
    # senão vira um blob como "pergunta" no AskUserQuestion, o MESMO
    # anti-padrão que P-04 removeu do handler brownfield acima. Imprime os
    # erros via renderer como CONTEXTO antes do prompt; o gate_name fica curto
    # e estável ("RESOLVER-ERRORS").
    renderer.write("")
    renderer.write("Erros do resolver:")
    for e in errors[:5]:
        renderer.write(f"  · {e}")
    renderer.write("")
    return ui_question.ask_three_paths("RESOLVER-ERRORS", paths)


def _drop_unresolvable_cards(
    selected_cards: list[CardManifest],
    errors: list[str],
) -> list[CardManifest]:
    """Remove do conjunto os cards citados nos erros do resolver (best-effort).

    M2: parse ANCORADO aos prefixos estáveis das mensagens do resolver
    (``engine/cards/resolver.py``), em vez de varrer qualquer texto entre
    colchetes (que casaria listas não relacionadas se o wording mudasse).
    Só processamos linhas que começam com um marcador conhecido, e dentro
    delas extraímos os ofensores nas posições estruturais conhecidas:

    - ``DEP-MISSING: card '<name>' requires …``        → <name>
    - ``CONFLICT-NAME: card '<name>' declares … '<x>'…``→ <name> (e <x>)
    - ``CONFLICT-SINGULAR: … provided by multiple cards: [<list>]`` → lista
    - ``CONFLICT-LABEL: card '<name>' … also provided by: [<list>]``
      → <name> + lista

    Determinístico, preserva a ordem original. NÃO é resolução completa —
    só uma poda do subconjunto problemático pra um re-resolve no caminho "c"
    do gate.
    """
    import re

    # Marcadores conhecidos: só linhas com um destes prefixos são parseadas.
    _KNOWN_PREFIXES = (
        "DEP-MISSING:",
        "CONFLICT-NAME:",
        "CONFLICT-SINGULAR:",
        "CONFLICT-LABEL:",
    )
    _card_name_re = re.compile(r"card '([^']+)'")
    _bracket_list_re = re.compile(r"\[([^\]]*)\]")

    flagged: set[str] = set()
    for err in errors:
        stripped = err.strip()
        if not stripped.startswith(_KNOWN_PREFIXES):
            continue  # wording desconhecido — não arrisca poda incorreta
        # Nome do card ofensor (posição ``card '<name>'`` — primeiro match).
        for match in _card_name_re.finditer(stripped):
            flagged.add(match.group(1))
        # Listas de providers em colisão SÓ existem nos marcadores de
        # conflito singular/label — ancoradas a esses prefixos.
        if stripped.startswith(("CONFLICT-SINGULAR:", "CONFLICT-LABEL:")):
            for match in _bracket_list_re.finditer(stripped):
                for token in match.group(1).split(","):
                    name = token.strip().strip("'\"")
                    if name:
                        flagged.add(name)
    return [c for c in selected_cards if c.name not in flagged]


# ── Hooks install (Step 13) ──────────────────────────────────────────────────


def _install_hooks(project_root: Path) -> int:
    """Copy canonical hooks from FORGE_HOME/hooks/ to .claude/forge/hooks/.

    Rules:
    - `.sh` scripts and `git-*` wrappers → copied with +x preserved.
    - `.yml` files (e.g. ci-pr-ingest.yml) are NOT copied — they're opt-in CI
      workflows the user installs into `.github/workflows/` manually.
    - Idempotent: overwrites existing copies (canonical wins).

    Task 0.8 (v1.3 pilot-ready): destino migrado para sub-namespace
    ``.claude/forge/hooks/`` (spec §2).

    Returns the number of hooks installed.
    """
    canonical = forge_home() / "hooks"
    if not canonical.is_dir():
        return 0

    target = forge_hooks_dir(project_root)
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
    """Install `.git/hooks/{pre-commit,post-commit,pre-push}` as chained delegators.

    Each wrapper is a Bash script bearing ``# FORGE_DELEGATOR_MARKER``. Pre-existing
    user hooks (non-wrapper, non-symlink) são migrados pra ``<name>.user`` UMA vez
    e re-encadeados a partir do wrapper, preservando o que o usuário escreveu
    (brownfield-safe). Symlinks antigos (estilo Task 0.8 pré-1.4) são descartados
    porque apontam direto pro forge hook — o wrapper já cobre esse exec.

    Idempotente: re-rodar detecta o marker e no-op. Em projetos não-git é no-op.

    Substitui o install symlink-com-``.bak`` (Task 1.4, v1.3 pilot-ready).
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
        forge_hook = forge_hooks_dir(project_root) / claude_name
        if not forge_hook.is_file():
            continue
        target = git_hooks / git_name
        user_backup = git_hooks / f"{git_name}.user"

        # Idempotente: já é um forge delegator? (file, não symlink, com marker)
        if target.exists() and not target.is_symlink():
            try:
                content = target.read_text()
                if "# FORGE_DELEGATOR_MARKER" in content:
                    continue
            except (OSError, UnicodeDecodeError):
                pass

        # Migra hook pré-existente do usuário pra <name>.user
        if target.exists() or target.is_symlink():
            if target.is_symlink():
                # Symlink estilo antigo — descarta, wrapper substituirá
                try:
                    target.unlink()
                except OSError:
                    continue
            elif not user_backup.exists():
                # Primeira migração de um hook real do usuário
                try:
                    target.rename(user_backup)
                except OSError:
                    continue
            else:
                # .user já existe de migração anterior — preserva-o, descarta target
                try:
                    target.unlink()
                except OSError:
                    continue

        # C-09 (PR18-R7): resolve o forge hook RELATIVO ao wrapper (como o user
        # hook já faz com `$(dirname "$0")`). Antes embutia o path ABSOLUTO de
        # forge_hook → o wrapper quebrava se o repo fosse movido/clonado pra
        # outro caminho. `os.path.relpath` calcula `.git/hooks` → forge hooks
        # dir (tipicamente `../../.claude/forge/hooks/<name>`) — move/clone-safe.
        forge_hook_rel = os.path.relpath(forge_hook, target.parent)
        # Escreve o wrapper encadeado
        wrapper = (
            "#!/usr/bin/env bash\n"
            "# FORGE_DELEGATOR_MARKER\n"
            "set -e\n"
            "# Chain user hook if present (preserves brownfield content)\n"
            f'if [ -x "$(dirname "$0")/{git_name}.user" ]; then\n'
            f'    "$(dirname "$0")/{git_name}.user" "$@"\n'
            "fi\n"
            "# Then run forge hook (resolved relative to this wrapper — C-09)\n"
            f'exec "$(dirname "$0")/{forge_hook_rel}" "$@"\n'
        )
        try:
            target.write_text(wrapper)
            target.chmod(0o755)
        except OSError:
            continue
        if user_backup.exists():
            try:
                user_backup.chmod(0o755)  # preserva exec bit
            except OSError:
                pass


def _vendor_mem(project_root: Path) -> bool:
    """Vendoriza o mem no consumidor: copia o asset → .claude/bin/mem (755) +
    a VERSION (pin), e roda o scaffold do mem (gitignore mem.db*, índice no
    AGENTS.md) via a fronteira mem_call. Reusa o scaffold do próprio mem
    (Decisão #2) em vez de replicá-lo. Idempotente."""
    asset = mem_asset_path()
    if not asset.is_file():
        return False
    dst = vendored_mem_path(project_root)
    ensure_dir(dst.parent)
    shutil.copy2(asset, dst)
    dst.chmod(0o755)
    version = mem_asset_version_path()
    if version.is_file():
        shutil.copy2(version, vendored_mem_version_path(project_root))
    # Scaffold idempotente via a fronteira (mem init não aceita --json).
    # M-002: NÃO descartar o resultado — se o scaffold falhar, o binário foi
    # copiado mas o estado (.claude/memory, gitignore, AGENTS.md) pode estar
    # incompleto. Retorna o sucesso REAL (cópia + scaffold), pra não afirmar
    # vendorização completa quando o scaffold falhou. O init segue gracioso
    # (não crasha), e a categoria `mem` do doctor pega o estado depois.
    res = mem_call(project_root, ["init"], json=False)
    return res.found and res.exit_code == 0


def _merge_forge_hooks_into_settings(project_root: Path) -> None:
    """Append forge's CC hook registrations to `.claude/settings.json`.

    Brownfield-safe via ``merge_settings_json`` (append-only, dedup-via-deep-equal).
    JSON5-tolerant read via ``read_settings_tolerant``. Idempotent.

    Forge hooks live in ``.claude/forge/hooks/`` after init (Task 0.8); this
    function registers their CC events in the user's ``.claude/settings.json``
    so Claude Code dispatches them on SessionStart/PostToolUse/SubagentStop.

    Wave 1 Fix #1 (v1.3 pilot-ready): closes the gap where ``_install_hooks``
    copied the shims but didn't register them in CC settings.
    """
    from engine.utils.settings_merge import (
        merge_settings_json,
        read_settings_tolerant,
    )
    from engine.utils.yaml_io import backup_file

    settings_path = project_root / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            existing = read_settings_tolerant(settings_path.read_text())
        except ValueError:
            # Parse failure: o arquivo existe mas não é JSON válido. NÃO
            # descartamos silenciosamente o conteúdo do usuário — preservamos
            # em .bak antes de seguir com as forge additions (cross-AI review
            # HIGH, brownfield-safe).
            bak = backup_file(settings_path)
            if bak is not None:
                renderer.write(renderer.colored(
                    f"warn: .claude/settings.json não é JSON válido; "
                    f"original preservado em {bak}. Seguindo com as adições "
                    f"do forge sobre uma base vazia — revise e reintegre suas "
                    f"settings a partir do backup.",
                    "yellow",
                ))
            else:
                renderer.write(renderer.colored(
                    "warn: .claude/settings.json não é JSON válido e não pôde "
                    "ser preservado em backup. Seguindo com as adições do forge.",
                    "yellow",
                ))
            existing = {}
        except OSError:
            # Não conseguimos PARSEAR o arquivo via read_text (EACCES
            # transiente, lock momentâneo, EINTR) — mas o arquivo pode estar
            # fisicamente íntegro no disco. A função grava settings.json
            # incondicionalmente logo abaixo; sem backup isso DESTRÓI as
            # settings do usuário silenciosamente (HI-001).
            #
            # backup_file copia BYTES (shutil.copy2), não depende do read que
            # falhou — então funciona mesmo aqui. Tentamos preservar antes de
            # seguir com base vazia. Se nem a cópia der (disco realmente
            # inacessível), avisamos best-effort e seguimos: init não falha.
            from engine.utils.yaml_io import backup_file as _backup_file

            bak = None
            try:
                bak = _backup_file(settings_path)
            except OSError:
                bak = None
            if bak is not None:
                renderer.write(renderer.colored(
                    f"warn: não consegui parsear o .claude/settings.json "
                    f"existente; original preservado em {bak}. Seguindo com "
                    f"as adições do forge sobre uma base vazia — revise e "
                    f"reintegre suas settings a partir do backup.",
                    "yellow",
                ))
            else:
                renderer.write(renderer.colored(
                    "warn: não consegui ler nem preservar o "
                    ".claude/settings.json existente em backup; seguindo com "
                    "as adições do forge sobre uma base vazia.",
                    "yellow",
                ))
            existing = {}
    else:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}

    # Canonical forge hook entries (paths relative to project root; Task 0.8
    # migrated forge shims to .claude/forge/hooks/ sub-namespace).
    forge_additions = {
        "hooks": {
            "SessionStart": [
                {"matcher": "", "hooks": [
                    {"type": "command",
                     "command": ".claude/forge/hooks/session-start-drift-check.sh"}
                ]}
            ],
            "PostToolUse": [
                {"matcher": "Edit|Write|NotebookEdit", "hooks": [
                    {"type": "command",
                     "command": ".claude/forge/hooks/post-edit-codebase-graph.sh"}
                ]},
                {"matcher": "Write", "hooks": [
                    {"type": "command",
                     "command": ".claude/forge/hooks/post-write-feature-artifact.sh"}
                ]},
            ],
            "SubagentStop": [
                {"matcher": "", "hooks": [
                    {"type": "command",
                     "command": ".claude/forge/hooks/post-subagent-validate.sh"}
                ]}
            ],
        }
    }

    merged = merge_settings_json(existing, forge_additions)
    settings_path.write_text(json.dumps(merged, indent=2) + "\n")


# ── AI driver install (Step 13.5) ────────────────────────────────────────────

# Sentinel comum à SKILL.md (Claude Code) e ao bloco da AGENTS.md (opencode).
# Serve dois propósitos: (1) detectar "é a nossa SKILL.md" sem parsear
# front-matter (H-002); (2) marcar o bloco append-only na AGENTS.md
# (idempotência). A SKILL.md canônica carrega o marker no topo (L5);
# `templates/AGENTS.md.template` recebe o marker prefixado no install.
_FORGE_DRIVER_MARKER = "<!-- FORGE_AI_DRIVER -->"

# BUG-4/MEM-5 (T4): marker pra o bloco auto-gerido do .claude/.gitignore.
# Append-only + idempotente (mesma filosofia do AGENTS.md driver).
_FORGE_GITIGNORE_MARKER = "# >>> feature-forge — auto-managed (derived artifacts) >>>"
_FORGE_GITIGNORE_END = "# <<< feature-forge — auto-managed <<<"


def _write_claude_gitignores(project_root: Path) -> None:
    """Semeia os .gitignore que mantêm os artefatos derivados fora do git.

    Dois alvos (BUG-4/MEM-5):

    - ``.claude/forge/.gitignore`` — estado interno do forge (checkpoints,
      drafts, ``state/``, ``*.bak``). Reescrito (canonical wins, conteúdo
      totalmente gerido pelo forge neste sub-namespace).
    - ``.claude/.gitignore`` — irmãos derivados de ``forge/`` que um
      ``git add .`` commitaria por engano: ``graph.db`` (+ working files
      SQLite), ``cards/``, ``memory/``, ``locks/`` e o
      ``.memory-cli-checkpoint.yaml`` do mem-CLI. Este alvo é
      **append-only e idempotente**: se o usuário já tem um ``.gitignore``
      em ``.claude/``, o conteúdo dele é preservado e o bloco do forge é
      anexado via marker (no-op se o marker já existe).

    Os nomes a ignorar derivam dos helpers canônicos de ``paths`` (não
    hardcode que drifta do layout) — exceto ``locks/`` e o checkpoint do
    mem-CLI, que são artefatos de runtime do mem vendorizado sob ``.claude/``.
    """
    # ── Alvo 1: .claude/forge/.gitignore (gerido pelo forge) ────────────────
    forge_gi = forge_dir(project_root) / ".gitignore"
    ensure_dir(forge_gi.parent)
    forge_gi.write_text(
        "# feature-forge — auto-managed\n"
        "state/\n"
        ".init-checkpoint.yaml\n"
        ".reconfigure-draft.yaml\n"
        ".evolve-checkpoint.yaml\n"
        "*.bak\n",
        encoding="utf-8",
    )

    # ── Alvo 2: .claude/.gitignore (append-only, cobre os irmãos derivados) ──
    claude = claude_dir(project_root)
    graph_db_name = graph_db_path(project_root).name  # canonical (paths helper)
    cards_name = cards_dir(project_root).name
    memory_name = memory_dir(project_root).name
    block = "\n".join(
        [
            _FORGE_GITIGNORE_MARKER,
            f"{graph_db_name}",
            # SQLite sidecars. O graph.db roda em WAL mode (engine/assets/mem),
            # que cria -wal E -shm; -journal cobre o rollback-journal mode.
            # MED-02: -shm faltava → um `git add .` commitava o sidecar.
            f"{graph_db_name}-journal",
            f"{graph_db_name}-wal",
            f"{graph_db_name}-shm",
            f"{cards_name}/",
            f"{memory_name}/",
            "locks/",
            ".memory-cli-checkpoint.yaml",
            # BUG-2 (Onda 3): cache persistente de discovery (lifecycle =
            # checkpoint). Derivado — não deve vazar num `git add .`.
            _DISCOVERY_CACHE_NAME,
            _FORGE_GITIGNORE_END,
            "",
        ]
    )
    claude_gi = claude / ".gitignore"
    ensure_dir(claude)
    if not claude_gi.exists():
        claude_gi.write_text(block, encoding="utf-8")
        return
    try:
        existing = claude_gi.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        # Não-decodável → trata como do usuário; anexa em modo binário-safe
        # seria arriscado. Preserva e não anexa (raro; o usuário gerencia).
        return
    if _FORGE_GITIGNORE_MARKER in existing:
        return  # idempotente — bloco já presente
    sep = "" if existing.endswith("\n") else "\n"
    claude_gi.write_text(existing + sep + block, encoding="utf-8")


def _source_template_name(target: str) -> str:
    """Mapeia o `target` de um card (nome de OUTPUT) pro template-fonte.

    Convenção canônica (``docs/schemas/card.md`` + ``cards/*/card.yaml``): o campo
    ``target`` carrega o nome do documento de saída do pacote de feature
    (ex.: ``tech-spec.md``, ``task-contract.yaml``, ``data-contract-spec.yaml``).
    O template-fonte em ``FORGE_HOME/templates/`` carrega o sufixo ``.template``
    antes da extensão (ex.: ``tech-spec.template.md``) — a MESMA convenção que as
    tuplas ``WAVE_*_TEMPLATES`` em ``plan.py`` (``(template_name, output_name)``)
    encodam, e que ``plan._render_template`` procura por ``template_name``.

    Insere ``.template`` antes da última extensão. Se o nome já carrega
    ``.template.`` (target declarado no formato de template, defensivo), retorna
    inalterado pra não duplicar o sufixo.
    """
    if ".template." in target:
        return target
    stem, dot, ext = target.rpartition(".")
    if not dot:
        # Sem extensão — nada a inserir; devolve o nome cru (será pulado se
        # o base não existir, com aviso).
        return target
    return f"{stem}.template.{ext}"


def _materialize_merged_templates(
    project_root: Path, merged: "MergedContributions"
) -> list[Path]:
    """CARDS-DISCONNECT — materializa os templates mergeados per-projeto.

    Pra cada `target` em `merged.templates` (nome de OUTPUT do card, ex.
    ``tech-spec.md``), resolve o template-fonte correspondente
    (``tech-spec.template.md``) via ``_source_template_name`` — a MESMA convenção
    ``(template_name, output_name)`` que as tuplas ``WAVE_*_TEMPLATES`` de
    ``plan.py`` usam. Renderiza o base canônico do FORGE_HOME com as contribuições
    aplicadas (reusando ``render_merged_template`` — o MESMO render que
    ``forge raw rebuild-templates`` usa) e escreve em
    ``.claude/forge/templates/{template_name}``. O materializado carrega o nome do
    template-fonte (não o de output) porque ``plan._render_template`` resolve por
    ``template_name`` — assim o fluxo default `init`→`plan` enxerga as seções que
    os cards ativos contribuíram.

    Idempotente: re-init re-renderiza por cima. Targets cujo template-fonte não
    existe em FORGE_HOME/templates são pulados com aviso (mesma postura tolerante
    do `rebuild-templates`). Retorna a lista de paths materializados.
    """
    if not merged.templates:
        return []
    templates_root = forge_home() / "templates"
    if not templates_root.is_dir():
        renderer.write(
            renderer.colored(
                f"  ! templates dir não encontrado em {templates_root} — "
                "materialização de cards pulada.",
                "yellow",
            )
        )
        return []
    dest_root = forge_dir(project_root) / "templates"
    written: list[Path] = []
    # C-47 (PR22-R-005): falha de render de um card ATIVO (fragmento faltante,
    # conflito YAML) é FALHA DE INIT, não warning. Antes era rebaixada a aviso
    # amarelo + continue → template set parcial silencioso (o `forge plan`
    # downstream renderizava sem a seção contribuída, sem ninguém saber).
    # Coletamos as falhas e levantamos InitError APÓS o loop (mensagem agregada).
    render_failures: list[str] = []
    for target, contributions in sorted(merged.templates.items()):
        template_name = _source_template_name(target)
        base = templates_root / template_name
        if not base.is_file():
            # Base ausente em FORGE_HOME (clone parcial) = tolerância DOCUMENTADA
            # — pula com aviso (mantido do comportamento anterior, NÃO é falha de
            # card ativo). C-47 só promove a falha de RENDER.
            renderer.write(
                renderer.colored(
                    f"  ! template-fonte ausente em FORGE_HOME: {template_name} "
                    f"(target {target}) — pulado.",
                    "yellow",
                )
            )
            continue
        out = dest_root / template_name
        ensure_dir(out.parent)
        try:
            render_merged_template(base, contributions, out)
            written.append(out)
        except CardError as exc:
            render_failures.append(f"{target}: {exc}")
    if render_failures:
        raise InitError(
            "materialização de templates falhou — card(s) ativo(s) com "
            "fragmento/conflito (init NÃO pode shippar template set parcial):\n  · "
            + "\n  · ".join(render_failures)
        )
    return written


def _install_ai_driver(project_root: Path) -> None:
    """Instala a SKILL.md (Claude Code) + AGENTS.md (opencode) no consumidor.

    Brownfield-safe (spec §4 C1):
    - `SKILL.md` → `.claude/skills/feature-forge/SKILL.md`: copia do FORGE_HOME.
      Se já existe e NÃO carrega o marker do forge (``_FORGE_DRIVER_MARKER``),
      preserva a skill do usuário (não clobber); senão sobrescreve (canonical
      wins, idempotente). Detecção via marker — não substring de front-matter —
      pra evitar falso-positivo (skill homônima do usuário citando o nome) e
      falso-negativo (front-matter canônico que mude no futuro).
    - `AGENTS.md` (raiz): append-only via marker. Se o marker já existe, no-op;
      se o arquivo existe sem o marker, anexa o bloco do forge preservando o
      conteúdo do usuário; se ausente, cria.

    Decisão 22 (load-bearing): o engine NÃO importa nada da SKILL.md/AGENTS.md —
    são instruções de comportamento pro host. Esta função só COPIA arquivos.
    Decisão 18: o FORGE_HOME canônico é resolvido via ``forge_home()``, nunca
    hardcodado. Se o FORGE_HOME não carregar os artefatos (clone parcial), o
    install emite um aviso mentor-calmo (não falha) — o driver fica dormente
    até reinstalar, e o aviso converte um failure silencioso num sinal acionável.
    """
    home = forge_home()

    # SKILL.md
    skill_src = home / "skills" / "feature-forge" / "SKILL.md"
    if skill_src.is_file():
        skill_dst = project_root / ".claude" / "skills" / "feature-forge" / "SKILL.md"
        canonical = skill_src.read_text(encoding="utf-8")
        if not skill_dst.exists():
            ensure_dir(skill_dst.parent)
            skill_dst.write_text(canonical, encoding="utf-8")
        else:
            # C-07 (PR18-R6): o SKILL.md do usuário pode não decodar em UTF-8
            # (binário/encoding exótico). Ler pra checar o marker estouraria
            # UnicodeDecodeError → derrubava o init. Tratamos não-decodável como
            # "é do usuário" (sem marker confiável) → PRESERVA, não clobber.
            try:
                existing_skill = skill_dst.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                existing_skill = ""  # não-decodável → preserva (não é a nossa)
            if _FORGE_DRIVER_MARKER in existing_skill:
                # É a nossa skill (carrega o marker) → canonical wins (idempotente).
                skill_dst.write_text(canonical, encoding="utf-8")
            # else: existe mas é do usuário (sem marker) → preserva, não clobber.

    # AGENTS.md (append-only via marker)
    agents_tpl = home / "templates" / "AGENTS.md.template"
    if agents_tpl.is_file():
        block = _FORGE_DRIVER_MARKER + "\n" + agents_tpl.read_text(encoding="utf-8")
        agents_dst = project_root / "AGENTS.md"
        if not agents_dst.exists():
            agents_dst.write_text(block + "\n", encoding="utf-8")
        else:
            # C-07: AGENTS.md não-decodável → warn + skip (não corrompe o
            # arquivo do usuário com um append cego sobre bytes não-UTF8).
            try:
                current = agents_dst.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                renderer.write(
                    renderer.colored(
                        "AGENTS.md existente não decodável em UTF-8 — "
                        "driver opencode não anexado (preservando o arquivo). "
                        "Reinstale após normalizar o encoding.",
                        "yellow",
                    )
                )
                return
            if _FORGE_DRIVER_MARKER not in current:
                agents_dst.write_text(
                    current.rstrip("\n") + "\n\n" + block + "\n", encoding="utf-8"
                )
            # else: marker presente → idempotente, no-op.

    # M-002: no-op observável. Se o FORGE_HOME não carrega os artefatos
    # (clone parcial/sparse-checkout), o driver fica dormente — `forge plan`
    # morre no 1º prompt sem pista. Um aviso amarelo mentor-calmo converte
    # esse failure silencioso num sinal acionável. Não bloqueia o install.
    if not skill_src.is_file() or not agents_tpl.is_file():
        renderer.write(
            renderer.colored(
                f"driver AI-first não instalado — FORGE_HOME em {home} não "
                "carrega skills/feature-forge/SKILL.md ou templates/"
                "AGENTS.md.template (clone parcial?). forge plan vai falhar no "
                "1º prompt até reinstalar.",
                "yellow",
            )
        )


# ── Graph-first docs install (Step 11.7, W-GRAPH Camadas 1+3) ────────────────

_GRAPH_FIRST_MD = """\
# Graph-first — consulte o grafo antes de ler o source

> Instalado por `forge init`. Voz: mentor calmo.

Quando este projeto tem fontes suportadas indexadas, o codebase graph em
`.claude/graph.db` (SQLite, WAL mode) guarda símbolos, imports, body-text e
dependências. **Antes de ler arquivos fonte pra entender o projeto, consulte
o grafo** — ele responde em uma chamada o que custaria várias leituras de
arquivo, e protege seu contexto. Num projeto recém-iniciado (greenfield) o
grafo pode estar vazio até a primeira indexação; nesse caso as queries
retornam listas vazias e você lê o source normalmente.
Essa é a regra graph first: quando o grafo tem a resposta, ele vem antes do source.

## A regra

1. Vai mexer/entender uma área do código? Pergunte ao grafo primeiro.
2. O grafo respondeu com o que você precisava? Use a resposta — não abra o
   arquivo "só pra confirmar".
3. O grafo não cobre o que você precisa (string literal exata, contexto
   multi-linha, arquivo pedido explicitamente)? Aí sim leia o source.

A skill de referência completa — tabela tarefa→query→exemplo — está em
`.claude/forge/graph-skill.md`.

## Quick-start (as 5 queries de orientação)

Todas as queries rodam em modo non-interactive com `forge graph --json <query>`:

```bash
# q1 — features similares por slug (antes de criar uma feature nova)
forge graph --json q1 <slug>

# q2 — blast radius de um ou mais arquivos (o que quebra se eu mexer aqui?)
forge graph --json q2 path/to/File.kt [outro/Arquivo.swift ...]

# q3 — arquivos órfãos (sem referências de entrada)
forge graph --json q3

# q4 — símbolos de um módulo (o que esse módulo expõe?)
forge graph --json q4 <module>

# q8 — dependências de DI de uma classe (o que essa classe injeta?)
forge graph --json q8 <ClassName>
```

`<query>` aceita as três formas: numérica (`1`..`17`, `r`), com prefixo
(`q1`..`q17`, `qr`), ou o label textual (`orphan-files`, `blast-radius`, …).
O catálogo completo está em `.claude/forge/graph-skill.md`.

## Quando NÃO usar o grafo

- Precisa do texto exato de uma string literal ou comentário → use `Grep`.
- Precisa de contexto de múltiplas linhas em torno de um símbolo → use `Read`.
- O usuário pediu explicitamente "leia o arquivo X" → leia o arquivo.

Fora desses três casos: **grafo primeiro.**
"""


_GRAPH_SKILL_MD = """\
# Graph skill — tarefa → query → exemplo

> Instalado por `forge init`. Voz: mentor calmo. Referência das principais
> graph queries — a tabela abaixo cobre as de uso mais frequente; o catálogo
> completo (`q1`..`q17` + o alias combinado `r`) responde via
> `forge graph --json <query>`.

O grafo (`.claude/graph.db`) responde perguntas estruturais sobre o código
sem você abrir os arquivos. Toda query roda em modo non-interactive:

```bash
forge graph --json <query> [args...]
```

`<query>` aceita três grafias equivalentes:

- **Numérica:** `1`..`17`, `r`
- **Prefixo:** `q1`..`q17`, `qr`
- **Label textual:** `orphan-files`, `blast-radius`, `symbols`, …

## Tabela tarefa → query → exemplo

| Quero… | Query | Exemplo |
|---|---|---|
| Ver se já existe feature parecida | `q1` (similar-features) | `forge graph --json q1 lembrete-de-rega` |
| Saber o que quebra se eu mexer aqui | `q2` (blast-radius) | `forge graph --json q2 app/src/Login.kt` |
| Achar arquivos órfãos (dead code candidato) | `q3` (orphan-files) | `forge graph --json q3` |
| Listar símbolos de um módulo | `q4` (symbols) | `forge graph --json q4 :feature:auth` |
| Achar rotas de uma feature | `q7` (routes) | `forge graph --json q7 checkout` |
| Ver dependências de DI de uma classe | `q8` (di-deps) | `forge graph --json q8 LoginViewModel` |
| Achar os testes que cobrem um arquivo | `q9` (tests-for) | `forge graph --json q9 app/src/Login.kt` |
| Achar helper reusável antes de criar um | `q11` (reusable-helpers) | `forge graph --json q11` |
| Ver duplicação dentro do mesmo módulo | `q12` (dup-within-module) | `forge graph --json q12` |
| Ver duplicação entre módulos | `q13` (dup-cross-module) | `forge graph --json q13` |
| Ver candidatos a migração KMP | `q14` (kmp-migration) | `forge graph --json q14` |
| Ver todos os achados de reuso combinados | `r` (reuse-findings) | `forge graph --json r` |

## Reuso antes de criar (Mandamento 3)

Antes de escrever helper/função novo, rode `q11` (reusable-helpers) e `r`
(reuse-findings combinado, cobre `q12`/`q13`/`q14`). Se o grafo aponta um
equivalente, use-o; se aponta near-duplicate, decida entre consolidar,
promover pra shared, ou criar novo com justificativa.

## Quando NÃO usar o grafo

O grafo é estrutural — ele sabe quem chama quem, quem expõe o quê, e onde
há duplicação. Ele NÃO substitui ler o source quando:

- **String literal exata** — precisa do texto cru de uma mensagem,
  comentário ou constante? Use `Grep`.
- **Contexto multi-linha** — precisa entender o corpo de uma função, várias
  linhas em torno de um símbolo? Use `Read`.
- **Arquivo pedido explicitamente** — o usuário disse "leia o arquivo X"?
  Leia o arquivo X.

Fora desses três: **grafo primeiro** — é mais rápido e barato em contexto.
"""


def _write_graph_docs(project_root: Path) -> tuple[Path, Path]:
    """Escreve os docs graph-first no sub-namespace `.claude/forge/`.

    Camadas 1 + 3 (W-GRAPH): GRAPH-FIRST.md ensina a regra "consulte o grafo
    antes de ler o source"; graph-skill.md é a referência tarefa→query→exemplo.
    Canonical wins — re-escreve o conteúdo a cada init (idempotente).
    """
    forge_root = ensure_dir(forge_dir(project_root))
    graph_first = forge_root / "GRAPH-FIRST.md"
    graph_skill = forge_root / "graph-skill.md"
    graph_first.write_text(_GRAPH_FIRST_MD, encoding="utf-8")
    graph_skill.write_text(_GRAPH_SKILL_MD, encoding="utf-8")
    return graph_first, graph_skill


# ── _reduce_rules ─────────────────────────────────────────────────────────────


def _rules_fragment_id(source_name: str, heading: str) -> str:
    """Constrói o fragment_id base: '<filename>::<heading-slug>'.

    O slug é gerado a partir do texto do heading sem os marcadores Markdown
    (##/###): lowercase, sem espaços iniciais/finais. Espaços internos são
    preservados como-estão após strip — mantendo simplicidade e
    determinismo. Caracteres especiais não são removidos (slugs simples pra
    nomes de seção curtos, como são os de rules/).

    Nota: não desambigua headings repetidos — use _rules_slug_counter para
    gerar o fragment_id final quando múltiplas ocorrências são possíveis.
    """
    import re

    heading_text = re.sub(r"^#+\s*", "", heading).strip().lower()
    return f"{source_name}::{heading_text}"


def _rules_fragment_id_counted(
    source_name: str,
    heading: str,
    occurrence_counter: dict[str, int],
) -> str:
    """Constrói o fragment_id desambiguado por ocorrência no mesmo arquivo.

    WR-01: headings idênticos no mesmo arquivo geram slugs iguais → colisão
    de fragment_id → o trim casa AMBAS as ocorrências, destruindo Tier-0.
    Esta função incrementa `occurrence_counter[base_id]` a cada chamada e
    sufixo com `#N` (N>=2) a partir da 2ª ocorrência.

    Exemplo (mesmo arquivo, heading "## Reuso"):
      1ª chamada → "reuso.md::reuso"     (occurrence_counter["reuso.md::reuso"] == 1)
      2ª chamada → "reuso.md::reuso#2"   (occurrence_counter["reuso.md::reuso"] == 2)

    `occurrence_counter` deve ser um dict vazio passado pelo chamador e
    reutilizado dentro do mesmo arquivo (resetado entre arquivos).
    """
    base = _rules_fragment_id(source_name, heading)
    count = occurrence_counter.get(base, 0) + 1
    occurrence_counter[base] = count
    if count == 1:
        return base
    return f"{base}#{count}"


def _parse_rule_fragments(project_root: Path) -> list[dict]:
    """Lê .claude/rules/*.md + CLAUDE.md, fatia por heading (##/###).

    Determinismo (H-101 — critical for pause-resume):
    - arquivos ordenados com sorted().
    - *.bak e .rules-reduced excluídos.
    - Dentro de cada arquivo, os fragmentos aparecem na ordem do texto.

    Retorna lista de dicts: {id, source, heading, text}.
    Fragmentos sem heading (preâmbulo) são EXCLUÍDOS — só seções com
    heading ##/### são classificáveis. Preâmbulos sem heading não entram
    no payload do classify.
    """
    import re

    fragments: list[dict] = []

    def _slice_file(source_name: str, content: str) -> None:
        """Fatia <content> por headings ## ou ### e popula `fragments`."""
        lines = content.splitlines(keepends=True)
        current_heading = ""
        current_lines: list[str] = []
        # WR-01: contador de ocorrência por slug dentro deste arquivo.
        # Resetado por arquivo (local à função), garante que "reuso.md::x#2"
        # só aparece quando há 2 headings idênticos no MESMO arquivo.
        _occ: dict[str, int] = {}

        def _flush() -> None:
            body = "".join(current_lines).strip()
            if not current_heading:
                # Preambulo sem heading — nao e uma seção classificavel (sem ##/###).
                # Excluido do payload do classify (o host classificaria headings, nao
                # blocos de texto soltos). O conteudo permanece intacto no arquivo.
                return
            if not body:
                return
            fid = _rules_fragment_id_counted(source_name, current_heading, _occ)
            fragments.append(
                {
                    "id": fid,
                    "source": source_name,
                    "heading": current_heading,
                    "text": body,
                }
            )

        for line in lines:
            if re.match(r"^#{2,3}\s", line):
                _flush()
                current_heading = line.rstrip()
                current_lines = []
            else:
                current_lines.append(line)
        _flush()

    # Coleta .claude/rules/*.md (sorted, sem .bak).
    rules_dir = claude_dir(project_root) / "rules"
    rule_files: list[Path] = []
    if rules_dir.is_dir():
        rule_files = sorted(
            p for p in rules_dir.iterdir()
            if p.suffix == ".md" and not p.name.endswith(".bak")
        )

    # Coleta CLAUDE.md do project_root.
    claude_md = project_root / "CLAUDE.md"

    # Ordem: rules/ (sorted) depois CLAUDE.md (convenção — tier-0 tende
    # a estar em CLAUDE.md, mas o classify decide; a ordem é só estável).
    all_files: list[tuple[str, Path]] = [
        (p.name, p) for p in rule_files
    ]
    if claude_md.is_file():
        all_files.append(("CLAUDE.md", claude_md))

    for source_name, path in all_files:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        _slice_file(source_name, content)

    return fragments


class _MemAddError(InitError):
    """Falha de mem add — aborta ANTES de .bak/trim (H-104/M-201)."""


def _reduce_rules(project_root: Path) -> bool:
    """Passo de redução de rules: classifica fragmentos, propõe divisão Tier-0/1.

    Retorna True se a redução foi aplicada; False se pulada (greenfield,
    host sem LLM, sem Tier-1, ou usuário escolheu pular).

    Protocolo H-104 + M-201 (apply ordenado):
    1. mem add de TODOS os Tier-1 + verifica cada MemResult.
    2. Só com todos OK: .bak imediatamente antes do trim.
    3. Trim: substitui Tier-1 por ponteiro, escreve sentinel.

    PausedForInputError propaga até cli.py (exit 2) — NÃO capturada aqui.
    """
    import re

    # ── Guard: sentinel indica que a redução já foi feita ───────────────────
    sentinel = claude_dir(project_root) / ".rules-reduced"
    if sentinel.exists():
        return False

    # ── Parse determinístico de fragmentos ──────────────────────────────────
    fragments = _parse_rule_fragments(project_root)
    if not fragments:
        return False  # greenfield: sem rules nem CLAUDE.md

    # ── Classify via host LLM ────────────────────────────────────────────────
    # PausedForInputError propaga (NÃO capturada).
    classification = question.classify(fragments, project_root=project_root)

    if classification is None:
        # Host sem LLM (TTY) — pula com aviso (H-101 honesto).
        renderer.write(
            renderer.colored(
                "Aviso: redução de rules pulada — host sem LLM pra classificar "
                "(host TTY ou ambiente não-agentico).",
                "yellow",
            )
        )
        return False

    # Valida que TODO fragmento recebeu tier.
    classified_ids = {item["fragment_id"] for item in classification}
    fragment_ids = {f["id"] for f in fragments}
    missing = fragment_ids - classified_ids
    if missing:
        raise InitError(
            f"classify retornou resultado incompleto — fragmentos sem tier: {sorted(missing)}"
        )

    # ── Separa Tier-0 e Tier-1 ───────────────────────────────────────────────
    tier1_items = [item for item in classification if item.get("tier") == 1]
    if not tier1_items:
        # Todos Tier-0 — nada a mover.
        return False

    # ── 3-caminhos: proposta ao usuário ─────────────────────────────────────
    # Loop de ajuste com cap de 3 rodadas (M-202).
    _MAX_ADJUST = 3
    adjust_count = 0
    current_classification = classification

    while True:
        tier1_items = [item for item in current_classification if item.get("tier") == 1]
        n_tier1 = len(tier1_items)
        n_tier0 = len(current_classification) - n_tier1

        renderer.write("")
        renderer.write(
            f"Classificação de rules: {n_tier0} Tier-0 (invariante always-on) · "
            f"{n_tier1} Tier-1 (referência — vai pro mem)."
        )

        paths = [
            {
                "label": "aceitar a classificação e mover Tier-1 pro mem",
                "motive": "enxuga as rules mantendo o conteúdo acessível via mem find",
            },
            {
                "label": "ajustar a classificação (re-classificar com feedback)",
                "motive": "indica ao host que o split não está certo — re-classifica considerando o prior",
            },
            {
                "label": "pular a redução agora",
                "motive": "mantém as rules como estão — pode rodar manualmente depois",
            },
        ]
        choice = question.ask_three_paths("REDUCAO-DE-RULES", paths)

        if choice == "c":
            # pular
            return False

        if choice == "a":
            # aceitar — segue pro apply
            break

        # choice == "b": ajustar
        adjust_count += 1
        if adjust_count >= _MAX_ADJUST:
            renderer.write(
                renderer.colored(
                    "Cap de ajustes atingido — aceite ou pule a redução.",
                    "yellow",
                )
            )
            # Força aceitar ou pular na próxima rodada (não entra no ajuste).
            choice = question.ask_three_paths(
                "REDUCAO-DE-RULES-FINAL",
                [
                    {
                        "label": "aceitar a classificação atual",
                        "motive": "aplica o split resultante das rodadas de ajuste",
                    },
                    {
                        "label": "pular a redução",
                        "motive": "mantém as rules como estão — pode rodar manualmente depois",
                    },
                    {
                        "label": "inspecionar a classificação",
                        "motive": "exibe a lista de fragmentos e tiers propostos antes de decidir",
                    },
                ],
            )
            if choice == "a":
                break
            if choice == "c":
                # Inspecionar: re-renderiza a lista de fragmentos + tiers e
                # retorna ao 3-caminhos (outcome distinto — sem aplicar nem pular).
                _cur_tier1 = [
                    item for item in current_classification if item.get("tier") == 1
                ]
                _cur_tier0 = [
                    item for item in current_classification if item.get("tier") == 0
                ]
                renderer.write("")
                renderer.write("  Tier-0 (invariante always-on):")
                for _item in _cur_tier0:
                    renderer.write(f"    · {_item['fragment_id']}")
                renderer.write("  Tier-1 (vai pro mem):")
                for _item in _cur_tier1:
                    renderer.write(f"    · {_item['fragment_id']}")
                renderer.write("")
                continue
            return False

        # Re-classifica com revise=True + prior (M-202).
        prior = current_classification
        revised = question.classify(
            fragments,
            schema={"tiers": [0, 1], "revise": True, "prior": prior},
            project_root=project_root,
        )
        if revised is None:
            # Host perdeu LLM mid-flow — pula.
            return False
        current_classification = revised

        # Valida completude da classificação revisada (mesmo gate que a inicial).
        rev_ids = {item["fragment_id"] for item in current_classification}
        missing_rev = fragment_ids - rev_ids
        if missing_rev:
            raise InitError(
                f"classify (revise) retornou resultado incompleto — "
                f"fragmentos sem tier: {sorted(missing_rev)}"
            )

    # ── Apply ordenado (H-104 + M-201) ──────────────────────────────────────
    # Tier-1 final após loop de aceitar/ajustar.
    tier1_items = [item for item in current_classification if item.get("tier") == 1]

    # CR-02: valida ANTES de qualquer operação destrutiva que todo Tier-1
    # tem mem_note.body não-vazio. Tier-1 sem body é perda de conhecimento —
    # recusa o trim e aborta com mensagem clara.
    _MEM_NOTE_TYPE_ENUM = {"decision", "episode", "feedback", "reference", "session"}
    for item in tier1_items:
        note = item.get("mem_note") or {}
        if not (note.get("body") or "").strip():
            raise InitError(
                f"Tier-1 '{item['fragment_id']}' sem mem_note.body — "
                "recusando trim que perderia conteúdo. "
                "Refaça a classificação."
            )

    # Passo 1: mem add de TODOS os Tier-1 — verifica cada MemResult ANTES
    # de qualquer operação destrutiva (.bak / trim).
    # Se QUALQUER add falha → aborta imediatamente (dado intacto, sem .bak orfão).
    for item in tier1_items:
        note = item.get("mem_note") or {}
        note_type = note.get("type", "reference")
        # WR-02: valida --type contra o enum do mem; coage para "reference"
        # com aviso se fora do conjunto aceito.
        if note_type not in _MEM_NOTE_TYPE_ENUM:
            renderer.write(
                renderer.colored(
                    f"  aviso: mem_note.type '{note_type}' inválido para "
                    f"'{item['fragment_id']}' — coagindo para 'reference'.",
                    "yellow",
                )
            )
            note_type = "reference"
        title = note.get("title", item["fragment_id"])
        body = note.get("body", "")
        tags = note.get("tags", [])
        tags_str = ",".join(tags) if tags else ""

        args = ["add", "--type", note_type, "-t", title]
        if tags_str:
            args += ["--tags", tags_str]
        args += ["--", body]  # CR-01: `--` força body posicional (bullets com '-')

        res = mem_call(project_root, args, json=False)
        if not (res.found and res.exit_code == 0):
            raise _MemAddError(
                f"mem add falhou para '{title}' "
                f"(found={res.found}, exit_code={res.exit_code}): {res.stderr}"
            )

    # Passo 2: .bak — SÓ aqui (depois de todos os adds OK), nunca antes.
    # Identifica os arquivos fonte que têm Tier-1.
    tier1_sources: set[str] = {item["fragment_id"].split("::")[0] for item in tier1_items}

    for source_name in sorted(tier1_sources):
        if source_name == "CLAUDE.md":
            src_path = project_root / "CLAUDE.md"
        else:
            src_path = claude_dir(project_root) / "rules" / source_name
        if src_path.is_file():
            bak_path = src_path.with_suffix(src_path.suffix + ".bak")
            shutil.copy2(src_path, bak_path)

    # Passo 3: trim — substitui fragmentos Tier-1 por ponteiro, escreve sentinel.
    tier1_frag_ids = {item["fragment_id"] for item in tier1_items}

    # Agrupa Tier-1 fragments por fonte.
    tier1_by_source: dict[str, list[str]] = {}
    for item in tier1_items:
        source_name = item["fragment_id"].split("::")[0]
        tier1_by_source.setdefault(source_name, []).append(item["fragment_id"])

    for source_name, frag_ids_to_trim in tier1_by_source.items():
        if source_name == "CLAUDE.md":
            src_path = project_root / "CLAUDE.md"
        else:
            src_path = claude_dir(project_root) / "rules" / source_name

        if not src_path.is_file():
            continue

        content = src_path.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)

        # Reconstrói o arquivo: mantém Tier-0, substitui Tier-1 por ponteiro.
        out_lines: list[str] = []
        in_tier1_section = False
        current_heading = ""
        # WR-01: mesmo contador de ocorrência usado no parse, garante que o
        # fragment_id calculado no trim é idêntico ao do parse (determinismo).
        _trim_occ: dict[str, int] = {}

        for line in lines:
            if re.match(r"^#{2,3}\s", line):
                heading_text = line.rstrip()
                fid = _rules_fragment_id_counted(source_name, heading_text, _trim_occ)
                if fid in tier1_frag_ids:
                    # Inicia secão Tier-1: escreve o heading + ponteiro.
                    in_tier1_section = True
                    current_heading = heading_text
                    out_lines.append(line)
                    # Infere o tema do título pra o ponteiro.
                    tema = re.sub(r"^#+\s*", "", heading_text).strip()
                    # WR-03: normaliza apóstrofo — um ' no tema quebraria o
                    # template do ponteiro (aspas desbalanceadas). Remove.
                    tema_safe = tema.replace("'", "")
                    out_lines.append(
                        f"\nDetalhe: `mem find '{tema_safe}'`\n"
                    )
                else:
                    in_tier1_section = False
                    out_lines.append(line)
            else:
                if in_tier1_section:
                    # Suprime o corpo original do Tier-1 (substituído pelo ponteiro).
                    pass
                else:
                    out_lines.append(line)

        src_path.write_text("".join(out_lines), encoding="utf-8")

    # Escreve sentinel.
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("", encoding="utf-8")

    renderer.write("  └─ rules reduzidas: Tier-1 movido pro mem · .bak criado · ponteiros instalados")
    return True


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
        return fail_with_tag(ERR_USAGE)

    project_root = Path.cwd().resolve()
    try:
        return _run_pipeline(project_root)
    except ui_question.PromptAbortedError:
        renderer.write("")
        renderer.write(mentor_calmo.pause_message(resume_command="forge init", project_root=project_root))
        return 130
    except KeyboardInterrupt:
        # Re-raise — the dispatcher in cli.py owns the 130 exit code path.
        raise
    except InitError as exc:
        renderer.write("")
        renderer.write(renderer.colored(f"forge init falhou: {exc}", "red"))
        return fail_with_tag(ERR_INIT_FAILED)


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
    # P-07: o init é pipeline determinístico — abertura estável (não a
    # variação aleatória de greeting(), reservada a contextos conversacionais).
    renderer.write(mentor_calmo.greeting_stable())
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

    if forge_config_path(project_root).is_file():
        renderer.write(
            mentor_calmo.three_paths_block(
                "INIT-BROWNFIELD",
                what_failed="já existe .claude/forge/forge-config.yaml neste projeto",
                where=str(forge_config_path(project_root)),
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
        return fail_with_tag(ERR_ABORTED)

    # WS-A-2 (P-11): pontos de retomada derivados do checkpoint. Quando o
    # resume é honrado (escolha humana 'resume' OU loop mecânico do host com
    # checkpoint além do preset), o pipeline PULA os steps já completos em vez
    # de recomeçar do zero — honrando a promessa "auto-resumable" da Decisão
    # 27. Escopo conservador R1: cobrir o caminho linear até backend-selection
    # (onde o piloto trava). Steps após backend caem no pipeline normal.
    _STEPS_PAST_PRESET = {
        "step-5-backend-selection",
        "step-6-resolve",
        "step-7-snapshot",
        "step-7-5-orphan-signals",
    }
    _resume_step: str | None = None
    _resume_preset: str | None = None
    # BUG-2: default False — só vira True no ramo de loop mecânico (host
    # replaying). Inicializado FORA do `if existing_checkpoint` pra estar
    # sempre definido no Step 2 (decisão cache-hit vs re-discovery).
    _host_loop_in_progress = False

    existing_checkpoint = _load_checkpoint(project_root)
    if existing_checkpoint:
        # Gate do resume (pilot R1, P-01; generalizado em R4, P-15): durante o
        # loop mecânico do host existe uma ``forge-response.json`` pendente que
        # pertence a uma pergunta DOWNSTREAM (preset, backend, ...). Emitir o
        # prompt de resume aqui injetaria um intent cujo id NÃO casa com essa
        # response → IntentMismatchError (deadlock do piloto MeoBonsai). Só
        # emitimos o resume em re-entrada HUMANA genuína. O pipeline fresh
        # consome a response via o consumed-log (idempotência §4 do schema
        # intent-protocol). Aditivo a Decisão 27.
        #
        # R4: o gate agora usa o helper compartilhado ``host_is_replaying``
        # (§4.1 do schema) em vez de ``_response_path().exists()`` cru. Ganho
        # de precisão: quando a ÚNICA response no disco é pra o próprio intent
        # de resume (o usuário acabou de responder o resume), o gate NÃO
        # suprime — o pipeline consome essa resposta em vez de pular cego.
        from engine.ui import intent_state  # noqa: PLC0415

        _resume_options = _resume_option_labels()
        _resume_intent_id = ui_question.stable_intent_id(
            "ask",
            "Resume de init pendente?",
            _resume_options,
            extra={
                "default": "discard",
                "min-selected": None,
                "validator-hint": None,
            },
        )
        _host_loop_in_progress = intent_state.host_is_replaying(
            project_root, _resume_intent_id
        )

        if _host_loop_in_progress:
            renderer.write(
                renderer.colored(
                    f"Checkpoint anterior detectado (step={existing_checkpoint.get('step')}); "
                    "há response pendente — sigo o pipeline sem reabrir o prompt de resume.",
                    "dim_grey",
                )
            )
            # Loop mecânico: continua do step salvo (não re-pergunta o que já
            # foi confirmado num ciclo anterior do mesmo init).
            _resume_step = str(existing_checkpoint.get("step") or "step-1-greeting")
            _resume_preset = existing_checkpoint.get("preset")
        else:
            renderer.write(
                renderer.colored(
                    f"Encontrei um checkpoint anterior (step={existing_checkpoint.get('step')}) "
                    f"em {_checkpoint_path(project_root)}.",
                    "yellow",
                )
            )
            # Decision 27 — sempre 3 caminhos em gate violation legítimo.
            # DRIFT-1 W2.T3b — persist intent-id da pergunta de resume ANTES
            # de invocar ``ui_question.ask``. Mantemos o resto do payload do
            # checkpoint anterior intacto (preset, selected_card_names,
            # backend_cells) — só atualizamos o campo intent_id. Re-invocacao
            # apos exit 2 consome o response correspondente sem re-perguntar.
            # R4: reusa ``_resume_options`` / ``_resume_intent_id`` derivados
            # acima pro gate (DRY — não re-deriva o stable id).
            _saved_cells = existing_checkpoint.get("backend-cells")
            _save_checkpoint(
                _InitCheckpoint(
                    step=str(existing_checkpoint.get("step") or "step-1-greeting"),
                    at=_utc_now_iso(),
                    project_root=str(project_root),
                    preset=existing_checkpoint.get("preset"),
                    selected_card_names=list(
                        existing_checkpoint.get("selected-card-names") or []
                    ),
                    backend_cells=(
                        _saved_cells if isinstance(_saved_cells, dict) else None
                    ),
                    intent_id=_resume_intent_id,
                )
            )
            resume_choice = ui_question.ask(
                "Resume de init pendente?",
                _resume_options,
                default="discard",
            )
            if resume_choice == "discard":
                _clear_checkpoint(project_root)
            elif resume_choice == "abort":
                renderer.write(
                    "Ok, abortado. O checkpoint segue intacto pra inspeção manual."
                )
                return fail_with_tag(ERR_ABORTED)
            elif resume_choice == "resume":
                # WS-A-2 (P-11): resume — continua do step salvo reaproveitando
                # o PRESET salvo (pula só a confirmação do Step 4). O backend
                # (Step 5) é re-confirmado a partir desse preset; os
                # selected_card_names salvos NÃO são reaproveitados pra avançar
                # — só foram regravados acima pra manter o checkpoint de audit
                # íntegro. Escopo R1 "conservador": resume volta à seleção de
                # backend. O pipeline limpa o checkpoint ao completar.
                _resume_step = str(
                    existing_checkpoint.get("step") or "step-1-greeting"
                )
                _resume_preset = existing_checkpoint.get("preset")

    # ── Step 2 — Discovery (cinematic) ───────────────────────────────────────
    checkpoint.step = "step-2-discovery"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    renderer.write("")
    renderer.write(
        "[1/7] Lendo o repositório + cards canônicos "
        "(pode levar ~30s em monorepos grandes)…"
    )

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

    # BUG-2: no loop mecânico (host replaying — cada response é processo novo),
    # tenta carregar o resultado de discovery do cache persistente em vez de
    # re-rodar os 3 extractors caros (~220s/ciclo em monorepo). Cache-miss
    # (1ª invocação, ou pós-discard que limpou o checkpoint) cai no caminho
    # normal e re-popula o cache ao fim do Step 2.
    _cached_discovery = (
        _load_discovery_cache(project_root) if _host_loop_in_progress else None
    )

    with ui_progress.progress(len(discovery_steps), "discovery", width=24) as bar:
        canonical_cards = load_all_cards(canonical_dir)
        bar.update(1)

        # Stack detection happens per-card later; we just mark the step done.
        bar.update(1)

        if _cached_discovery is not None:
            # Cache-hit: reusa o discovery do ciclo anterior. Os 3 extractors
            # NÃO re-rodam (o custo cai de re-execução pra load do YAML).
            ds_inv, i18n_inv, conv_inv = _cached_discovery
            renderer.write(
                renderer.colored(
                    "discovery reaproveitado do cache (loop mecânico — "
                    "sem re-varrer o repositório).",
                    "dim_grey",
                )
            )
            bar.update(3)
        else:
            try:
                ds_inv = extract_design_system(project_root)
            except Exception as exc:  # noqa: BLE001 — broad catch: defensive at discovery-step boundary — heuristic scanner walks project tree parsing XML/Kotlin/Swift; init must not fail for any extract hiccup
                renderer.write(
                    renderer.colored(
                        f"design-system extract skipped: {exc}", "dim_grey"
                    )
                )
            bar.update(1)

            try:
                i18n_inv = extract_i18n(project_root)
            except Exception as exc:  # noqa: BLE001 — broad catch: defensive at discovery-step boundary — heuristic i18n scanner; init must not fail for any extract hiccup
                renderer.write(
                    renderer.colored(f"i18n extract skipped: {exc}", "dim_grey")
                )
            bar.update(1)

            try:
                conv_inv = extract_conventions(project_root)
            except Exception as exc:  # noqa: BLE001 — broad catch: defensive at discovery-step boundary — heuristic conventions scanner; init must not fail for any extract hiccup
                renderer.write(
                    renderer.colored(f"conventions extract skipped: {exc}", "dim_grey")
                )
            bar.update(1)

            # Persiste o resultado de discovery pro próximo ciclo mecânico
            # (lifecycle = checkpoint; some com `_clear_checkpoint`).
            _save_discovery_cache(project_root, ds_inv, i18n_inv, conv_inv)

    renderer.write("")
    renderer.write(f"  {len(canonical_cards)} cards canônicos disponíveis em {canonical_dir}")

    checkpoint.step = "step-3-preset-suggestion"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    # ── Step 3 — Preset suggestion ───────────────────────────────────────────
    preset = _load_preset(PRESET_NAME)
    preset_detection = preset.get("detection") or {}
    preset_score, matched = _detection_eval._eval_detection_signals(
        project_root, preset_detection
    )
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
    # WS-A-2 (P-11): em resume além do preset (checkpoint em step-5+), pula a
    # confirmação e reaproveita o preset salvo. Discovery (Step 2) re-roda
    # sempre — é idempotente e produz os canonical_cards que o pipeline usa.
    _resuming_past_preset = (
        _resume_step in _STEPS_PAST_PRESET and _resume_preset is not None
    )
    if _resuming_past_preset:
        renderer.write("")
        renderer.write(
            renderer.colored(
                f"Resume: preset {_resume_preset} já confirmado num ciclo "
                "anterior — re-confirmo o backend a partir dele (a seleção "
                "de cards é refeita aqui, não reaproveitada do checkpoint).",
                "dim_grey",
            )
        )
    else:
        renderer.write("")
        # P-08: removida a opção morta 'outro' — só existe o preset kmp-mobile,
        # então 'outro' sempre levantava InitError e vazava '(não disponível no
        # v1)' no menu (regressão F3 do v1.2). Menu fica sim/abortar.
        choice = ui_question.ask(
            "Confirmar preset kmp-mobile?",
            {
                "sim": f"confirmar {PRESET_NAME} (recomendado se signals casaram)",
                "abortar": "sair do init agora",
            },
            default="sim",
        )
        if choice == "abortar":
            renderer.write("ok, parado.")
            return 0

    checkpoint.preset = PRESET_NAME
    checkpoint.step = "step-5-backend-selection"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    # ── Step 5 — Backend selection (W7.4 — multi-axis cells) ─────────────────
    # Substitui o legacy "backend-candidates" picker monolítico (Cena 6.5)
    # por bifurcação composer-driven:
    #   · has_signals → brownfield handler (W7.1): confirm/adjust/scratch
    #     sobre composer_result. Adapter ``_composer_result_to_cells``
    #     converte pra ``backend.<axis>.<platform>`` cell shape.
    #   · sem signals → greenfield handler (W7.2): bundle picker (4
    #     opções) + opt override. Adapter ``_bundle_to_cells`` carrega o
    #     YAML do bundle escolhido e emite cells per axis.
    #
    # Preset card-set (``preset.cards[].name``) é UNIVERSAL — usado sempre,
    # independente do handler. Cards do bundle/composer entram POR CIMA.
    preset_card_names = [
        c.get("name") for c in (preset.get("cards") or []) if c.get("name")
    ]
    card_index = _index_cards(canonical_cards)

    normalized_for_composer = _normalize_cards_for_composer(canonical_cards)
    # D1 (Fase 1): spinner gateado por TTY (H-001 — zero-stdout em não-TTY).
    # B3 (Fase 1): resultado pré-computado passado ao handler (dedup).
    composer_result = _scan_backend_with_spinner(project_root, normalized_for_composer)
    has_signals = any(
        cell is not None
        for axis_map in composer_result.values()
        for cell in axis_map.values()
    )

    renderer.write("")
    renderer.write("[5/7] Backend — preciso da sua escolha")

    backend_cells: dict[str, Any] = {}
    if has_signals:
        # Brownfield path — W7.1 handler.
        # B3 (Fase 1): passa composer_result pré-computado pra evitar recompute
        # duplo no hot-path (a mesma varredura já foi feita acima).
        result = _handle_backend_multi_axis_brownfield(
            project_root=project_root,
            active_cards=canonical_cards,
            composer_result=composer_result,
        )
        backend_cells = _composer_result_to_cells(result.get("composer_result") or {})
        bundle_cards = list(result.get("selected_card_names") or [])
    else:
        # Greenfield path — W7.2 handler.
        result = _handle_backend_multi_axis_greenfield(
            project_root=project_root,
            available_cards=canonical_cards,
        )
        bundle_name = result.get("bundle_name")
        bundle_cards = list(result.get("selected_card_names") or [])
        backend_cells = _bundle_to_cells(
            bundle_name=bundle_name,
            selected_card_names=bundle_cards,
            forge_root=forge_home(),
            available_cards=canonical_cards,
        )

    # Compose final selection: preset universals + handler picks (dedup'd,
    # preserva ordem do preset primeiro, depois cards do bundle/composer).
    selected_card_names: list[str] = list(preset_card_names)
    for name in bundle_cards:
        if name not in selected_card_names:
            selected_card_names.append(name)

    # P-09: dep-closure de provider de 1 nível antes do resolver. Quando um
    # card detectado (ex.: firestore-security-rules) requer um label que a
    # detecção não puxou (persistence-server), incluímos o card canônico que
    # o provê — evitando um DEP-MISSING que abortaria o init. Deps genuinamente
    # órfãs (sem provider no catálogo) caem no gate de recuperação do resolver.
    selected_card_names = _close_provider_deps(selected_card_names, card_index)

    checkpoint.selected_card_names = selected_card_names
    checkpoint.backend_cells = backend_cells
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
                f"Atenção: cards declarados mas ausentes do catálogo canônico: "
                f"{missing_cards}. Bundle/handler referencia card que não está "
                "em cards/. Investigue presets/<preset>/bundles/ ou re-rode "
                "`forge init` após rebuild do catalog — sigo sem eles por ora.",
                "yellow",
            )
        )

    # ── Step 6 — Resolver ────────────────────────────────────────────────────
    renderer.write("")
    renderer.write("Resolvendo cards (deps + conflicts + topo-sort)…")
    res = resolve(selected_cards, user_provided_capabilities=LATENT_CAPS)
    if res.errors:
        # P-10: o gate de resolver-errors PAUSA (exit 2) pra o usuário escolher
        # recuperação, em vez de abortar (exit 1). Antes era three_paths_block
        # cosmético + fail_with_tag — o 3-caminhos não aceitava escolha.
        choice = _resolver_error_gate(
            res.errors,
            project_root=project_root,
        )
        if choice == "a":
            # Voltar ao backend selection — escopo R1: instrui o re-run limpo
            # (o loop estruturado fica pra rodada futura, se necessário).
            renderer.write(
                "Re-rode `forge init` após ajustar — o backend será "
                "re-perguntado."
            )
            return fail_with_tag(ERR_ABORTED)
        if choice == "b":
            return fail_with_tag(ERR_ABORTED)
        # choice == "c": filtra os cards citados em DEP-MISSING/CONFLICT e
        # re-resolve o subconjunto. Se o subconjunto resolve, segue; senão aborta.
        resolvable = _drop_unresolvable_cards(selected_cards, res.errors)
        # M3: se a filtragem removeu TODOS os cards, não re-resolvemos lista
        # vazia (resolve([]) instalaria zero cards silenciosamente). Aborta
        # com mensagem clara.
        if not resolvable:
            renderer.write(
                renderer.colored(
                    "Nada resta resolvível — abortado.", "yellow"
                )
            )
            return fail_with_tag(ERR_ABORTED)
        res = resolve(resolvable, user_provided_capabilities=LATENT_CAPS)
        if res.errors:
            renderer.write(
                renderer.colored(
                    "Subconjunto ainda não resolve — abortado.", "yellow"
                )
            )
            return fail_with_tag(ERR_ABORTED)
        selected_cards = resolvable

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
    from validators._common import (  # noqa: PLC0415
        CatalogOverlayError,
        load_catalog as _load_overlay_catalog,
    )

    try:
        overlay_catalog = _load_overlay_catalog(project_root)
    except (CatalogOverlayError, OSError) as exc:
        renderer.write(
            renderer.colored(
                f"warn: catálogo overlay inválido ({exc}); seguindo com canon-only",
                "yellow",
            )
        )
        overlay_catalog = None

    if overlay_catalog is not None:
        # D1 (Fase 1): spinner gateado por TTY (H-001 — zero-stdout em não-TTY).
        orphans = _scan_orphan_with_spinner(project_root, activated, overlay_catalog)
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
                resume_command=f"forge init  # após reconciliar grants — {exc}",
                project_root=project_root,
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
    # CARDS-DISCONNECT (W-DEBT): materializa os templates mergeados per-projeto
    # em .claude/forge/templates/ — o fluxo default init→plan passa a enxergar
    # as seções contribuídas pelos cards ativos (antes só rebuild-templates
    # global fazia a ponte).
    materialized = _materialize_merged_templates(project_root, merged)
    if materialized:
        renderer.write(
            renderer.colored(
                f"  ✓ {len(materialized)} template(s) de card materializado(s) "
                "em .claude/forge/templates/",
                "green",
            )
        )

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
    ensure_dir(lifecycle_root(project_root))
    ensure_dir(lifecycle_root(project_root) / "archived")
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
    except Exception as exc:  # noqa: BLE001 — broad catch: defensive at discovery-step boundary — never fail init for a scan hiccup
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
    # Writes a hook script in .claude/forge/hooks/. Wiring it to Claude Code's
    # `tool-use:post:Edit` hook is left to the user — we print a one-liner
    # they can paste into .claude/settings.local.json.
    # Task 0.8 (v1.3 pilot-ready): hooks vivem em sub-namespace .claude/forge/.
    hooks_local = forge_hooks_dir(project_root)
    hooks_local.mkdir(parents=True, exist_ok=True)
    hook_script = hooks_local / "post-edit-detect-duplications.sh"
    hook_script.write_text(
        "#!/usr/bin/env bash\n"
        "# Post-edit hook: surface reuse-intelligence findings introduced by the edit.\n"
        "# Installed by `forge init` — wire it up in .claude/settings.local.json:\n"
        "#   { \"hooks\": { \"tool-use:post:Edit\": "
        "[{\"command\": \"$CLAUDE_PROJECT_DIR/.claude/forge/hooks/post-edit-detect-duplications.sh \\\"$file_path\\\"\"}] } }\n"
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

    # ── Step 11.7 — Graph-first docs (W-GRAPH) ──────────────────────────────
    # Ensina o consumidor a usar o graph.db recém-construído (Steps 11/11.5).
    # Sem este step, o grafo nasce órfão (NO-ONBOARDING, auditoria §5/§6 P1).
    graph_first, _graph_skill = _write_graph_docs(project_root)
    renderer.write(
        f"  · graph-first docs em `{graph_first.parent.relative_to(project_root)}/` "
        "(GRAPH-FIRST.md + graph-skill.md)"
    )

    checkpoint.step = "step-12-write-config"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    # ── Step 12 — forge-config.yaml ──────────────────────────────────────────
    config = _build_workflow_config(
        project_root=project_root,
        activated=activated,
        card_sha_by_name=card_sha_by_name,
        merged=merged,
        ds_inv=ds_inv,
        i18n_inv=i18n_inv,
        conv_inv=conv_inv,
        preset=preset,
        # W7.4 — passa cells (backend.<axis>.<platform>) em vez do choice
        # legacy. Default {} cobre o caso degenerado (greenfield com
        # 0 bundle selecionado) — validator emite warn no review (RULE-019).
        backend_cells=checkpoint.backend_cells or {},
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

    # Task 0.10 (v1.3 pilot-ready): config vive em
    # ``.claude/forge/forge-config.yaml`` (sub-namespace spec §2).
    ensure_dir(forge_dir(project_root))
    write_yaml(forge_config_path(project_root), config, atomic=True)

    checkpoint.step = "step-12.5-version-lock"

    # ── Step 12.5 — forge-version-lock.yaml ─────────────────────────────────
    # `forge doctor` checks this lock to detect engine/project version drift.
    # Task 0.10: version-lock também migra pro sub-namespace.
    version_lock_path = forge_dir(project_root) / "forge-version-lock.yaml"
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

    # ── Step 12.6 — .gitignore (forge sub-namespace + irmãos derivados) ──────
    # Auto-managed gitignores per docs/design/05-filesystem-layout.md.
    # BUG-4/MEM-5 (T4): além do ``.claude/forge/.gitignore`` (estado interno),
    # semeia um ``.claude/.gitignore`` append-only cobrindo os artefatos
    # derivados que vivem como irmãos de ``forge/`` (graph.db, cards/, memory/,
    # locks/, .memory-cli-checkpoint.yaml) — senão um ``git add .`` commitava
    # ~2.3 MB de graph.db + snapshots.
    _write_claude_gitignores(project_root)

    checkpoint.step = "step-14-history"

    # ── Step 13 — Hooks install ──────────────────────────────────────────────
    # Copy canonical shims into .claude/forge/hooks/ and wire git hooks symlinks.
    # Task 0.8 (v1.3 pilot-ready): hooks live under .claude/forge/ sub-namespace.
    ensure_dir(forge_hooks_dir(project_root))
    try:
        # W-VENDOR Task 1: vendoriza o mem ANTES dos hooks/driver (que podem
        # usar mem internamente em ondas futuras).
        _vendor_mem(project_root)
        n_hooks = _install_hooks(project_root)
        _install_git_hooks(project_root)
        # Wave 1 Fix #1: register forge CC hooks in .claude/settings.json
        # (brownfield-safe, append-only, dedup via merge_settings_json).
        # Must run AFTER hooks are copied so settings.json points to real files.
        _merge_forge_hooks_into_settings(project_root)
        # Step 13.5 — driver AI-first (SKILL.md CC + AGENTS.md opencode).
        # Brownfield-safe, idempotente (spec §4 C1).
        _install_ai_driver(project_root)
        if n_hooks:
            renderer.write(f"  └─ {n_hooks} hooks instalados em .claude/forge/hooks/")
    except (OSError, shutil.Error, AttributeError, TypeError, ValueError) as exc:  # pragma: no cover - hooks must not block init
        # MD-03 (final review 2026-06-15): scope inicial era (OSError,
        # shutil.Error). C-07 (PR18-R6): ampliado pra
        # (AttributeError, TypeError, ValueError) porque este bloco agora cobre
        # tambem `_merge_forge_hooks_into_settings` (settings.json de shape
        # inesperado → AttributeError/TypeError) e `_install_ai_driver`
        # (UnicodeDecodeError ⊂ ValueError ao ler SKILL/AGENTS do usuario). O
        # contrato "hooks/driver não bloqueiam init" é preservado — qualquer
        # falha vira warn amarelo, nunca derruba o init. UnicodeDecodeError já é
        # tratado dentro de `_install_ai_driver`; este catch é defense-in-depth.
        renderer.write(
            renderer.colored(f"hooks install warn: {exc}", "yellow")
        )

    # ── Step 13.6 — _reduce_rules ────────────────────────────────────────────
    # W-RULES (H-105): APÓS vendoring, FORA do try/except que engole.
    # PausedForInputError propaga até cli.py (exit 2) — o init é resumível.
    _reduce_rules(project_root)

    # ── Step 14 — workflow-config-history.jsonl seed ─────────────────────────
    # Schema HIST-001..012 per docs/schemas/workflow-config-history.md.
    # Greenfield init → before-snapshot-sha is null; after-snapshot-sha is the
    # sha256 of the forge-config.yaml we just wrote.
    # Task 0.10: config lê de forge_config_path; history continua em claude_dir
    # (reconfigure/undo coupling — fora do escopo desta task).
    cfg_path = forge_config_path(project_root)
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
            f"backend=[{_summarize_backend_cells(checkpoint.backend_cells)}] · "
            f"cards={len(activated)}"
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
        f"Preset:         {PRESET_NAME}",
        f"Backend:        {_summarize_backend_cells(checkpoint.backend_cells)}",
        f"Cards ativos:   {len(activated)}",
        f"Capabilities:   {n_caps}",
        f"Inventories:    {', '.join(inv_written) if inv_written else '(none)'}",
        f"DS components:  {n_components}",
        f"i18n keys:      {n_i18n}",
        "",
        "Saved to .claude/:",
        "  forge/forge-config.yaml  ·  cards/  ·  inventory/  ·  memory/  ·  graph.db",
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
    backend_cells: dict[str, Any],
    qa_enabled: bool = True,
    qa_auto_run: bool = False,
) -> dict[str, Any]:
    """Assemble the forge-config.yaml dict (schema v1.3).

    Follows docs/schemas/forge-config.md (canonical reference — schema
    bumped to "1.3" in Task 0.9, artifact renamed to forge-config.yaml).
    Optional blocks are populated with sane defaults when init can't infer
    them (ticketing, external-docs).

    W7.4 — ``backend_cells`` substitui o legacy ``backend_choice``. Shape
    canônico em ``docs/schemas/backend-axes.md``:
    ``backend.<axis>.<platform> = {card, status, migrating-to?} | None``.
    """
    now = _utc_now_iso()
    preset_defaults = preset.get("defaults") or {}
    target = preset.get("target") or {}

    project_slug = project_root.name.lower().replace("_", "-")

    config: dict[str, Any] = {
        "schema-version": "1.3",
        "identity": {
            "project-name": project_root.name,
            "project-slug": project_slug,
            "preset": PRESET_NAME,
            # W7.4 — ``identity.backend-choice`` removido (legacy monolítico).
            # Backend agora vive em ``backend.<axis>.<platform>`` (block próprio).
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
        # W7.4 — cells multi-axis em vez do provider monolítico legacy.
        "backend": dict(backend_cells) if backend_cells else {},
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


# ── DET-6 W7.1 — Brownfield multi-axis backend handler ──────────────────────


def _card_platforms(card: CardManifest) -> list[str]:
    """Lê `identity.platforms` do card.yaml com fallback canônico KMP.

    Open Detail #8 do SPEC: nem todo card.yaml declara `identity.platforms`
    ainda — W7.1 não força backfill (W2/W4 lidam com schema). Quando ausente,
    usa o fallback canônico ``["android", "ios", "kmp"]`` (preset kmp-mobile)
    pra manter o composer com input não-vazio. Cards android-only / ios-only
    DEVEM declarar explicitamente quando schema for atualizado.
    """
    identity = (card.raw.get("identity") or {}) if card.raw else {}
    declared = identity.get("platforms")
    if isinstance(declared, list) and declared:
        return [str(p) for p in declared if isinstance(p, str) and p]
    # Fallback KMP-mobile — fonte canônica do preset v1.0.
    return ["android", "ios", "kmp"]


def _scan_backend_with_spinner(
    project_root: Path,
    normalized: list[dict[str, Any]],
) -> "dict[str, dict[str, Cell | None]]":
    """Roda compose_backend_axes com spinner gateado por TTY (D1 — Fase 1).

    Embute o gate `_is_tty` OBRIGATÓRIO: em não-TTY a varredura roda direto,
    sem spinner, sem nenhuma escrita em stdout — preserva o transcript IA-first
    (Decisão 22: stdout limpo no loop mecânico). Em TTY, envolve a varredura
    num spinner mentor-calmo (label "backend — varrendo signals").

    Motivo do helper fino em vez de if/else inline: evita duplicar o padrão
    nos dois lugares que chamam compose_backend_axes (reuso-first); facilita
    monkeypatching nos testes (gate + scan como contrato observável separado).
    """
    if renderer._is_tty(sys.stdout):
        with ui_progress.spinner("backend — varrendo signals"):
            return compose_backend_axes(project_root, normalized)
    else:
        return compose_backend_axes(project_root, normalized)


def _scan_orphan_with_spinner(
    project_root: Path,
    activated: list,
    overlay_catalog: Any,
) -> list:
    """Roda _check_orphan_signals com spinner gateado por TTY (D1 — Fase 1).

    Mesmo contrato de gate que `_scan_backend_with_spinner`: em não-TTY a
    varredura roda direto, sem spinner, sem escrita em stdout — preserva o
    transcript IA-first. Em TTY, envolve a varredura num spinner.
    """
    if renderer._is_tty(sys.stdout):
        with ui_progress.spinner("verificando orphan signals"):
            return _check_orphan_signals(project_root, activated, overlay_catalog)
    else:
        return _check_orphan_signals(project_root, activated, overlay_catalog)


def _normalize_cards_for_composer(
    cards: list[CardManifest],
) -> list[dict[str, Any]]:
    """Converte `CardManifest` para a shape de input do composer (W5).

    Composer espera dicts ``{card_id, axis, platforms, detection}`` — ver
    ``engine/detection/composer.py`` docstring + AC-5. Manifests com `axis`
    vazio (category não-canônica) são silenciosamente descartados aqui
    porque o composer já tem o mesmo guard com logging.warning — duplicar
    o log poluiria stderr. Cards sem nome são também descartados (o
    composer também guarda).
    """
    normalized: list[dict[str, Any]] = []
    for c in cards:
        if not isinstance(c, CardManifest):
            continue
        if not c.name or not c.category:
            continue
        normalized.append(
            {
                "card_id": c.name,
                "axis": c.category,
                "platforms": _card_platforms(c),
                "detection": dict(c.detection or {}),
            }
        )
    return normalized


def _detect_axis_uniformity(
    composer_result: dict[str, dict[str, Any]],
) -> dict[str, bool]:
    """Por axis: True se mesma card_id em TODAS as platforms ativas (não-None).

    Adaptive UX (SPEC §"Adaptive UX"): axes uniformes geram 1 linha
    compacta ("axis — card (todas)") em vez de 1 linha per platform.
    Conflict count como NÃO-uniforme (precisa expansão pra mostrar
    candidates). Axes com 0 cells ativas → uniform=True (vacuosamente
    — caller decide se mostra ou esconde).
    """
    uniformity: dict[str, bool] = {}
    for axis, axis_map in composer_result.items():
        active_card_ids: set[str] = set()
        has_conflict = False
        for cell in axis_map.values():
            if cell is None:
                continue
            # Conflict é dataclass com `candidates` tuple; Cell tem `card_id`.
            # isinstance preferível a hasattr (PR #13 review #3405253823) —
            # contrato explícito via types em vez de duck-typing sobre nomes.
            if isinstance(cell, Conflict):
                has_conflict = True
                break
            if isinstance(cell, Cell):
                active_card_ids.add(cell.card_id)
        if has_conflict:
            uniformity[axis] = False
        else:
            uniformity[axis] = len(active_card_ids) <= 1
    return uniformity


def _render_axes_table(
    composer_result: dict[str, dict[str, Any]],
    uniformity: dict[str, bool],
) -> str:
    """Render textual table — uma linha por axis (uniform) ou per platform.

    Voz: mentor calmo, formato denso pra caber no body do intent. Não
    é prose decorativa — é input pro auditor humano confirmar/ajustar.
    Determinístico: axes ordenados alfabeticamente; platforms idem.
    """
    if not composer_result:
        return "  (nenhum card detectado — composer retornou estrutura vazia)"

    lines: list[str] = []
    for axis in sorted(composer_result.keys()):
        axis_map = composer_result[axis]
        if uniformity.get(axis, False):
            # Compact line: 1 card ou 0 cards no axis inteiro.
            active = next(
                (
                    cell
                    for cell in axis_map.values()
                    if isinstance(cell, Cell)
                ),
                None,
            )
            if active is None:
                lines.append(f"  {axis}: (nenhum card detectado)")
            else:
                lines.append(f"  {axis}: {active.card_id} (todas plataformas)")
            continue

        # Expanded: per (axis, platform) row.
        lines.append(f"  {axis}:")
        for platform in sorted(axis_map.keys()):
            cell = axis_map[platform]
            if cell is None:
                lines.append(f"    · {platform}: (nenhum)")
            elif isinstance(cell, Conflict):
                # Conflict — expose ALL candidates so the auditor disambiguates.
                cand_ids = ", ".join(c.card_id for c in cell.candidates)
                lines.append(
                    f"    · {platform}: CONFLITO — {cand_ids}"
                )
            elif isinstance(cell, Cell):
                lines.append(f"    · {platform}: {cell.card_id}")
    return "\n".join(lines)


def _collect_confirm_selection(
    composer_result: dict[str, dict[str, Any]],
) -> list[str]:
    """Path A (confirm): cards selecionados = cards ativos no composer_result.

    Conflict cells contribuem TODOS os candidates — Path A confirma
    "como-is", que inclui o estado pré-resolução. Path B (adjust) é onde
    o usuário escolhe entre candidatos de uma Conflict. Determinístico:
    ordenação alfabética + dedup.
    """
    picked: set[str] = set()
    for axis_map in composer_result.values():
        for cell in axis_map.values():
            if cell is None:
                continue
            if isinstance(cell, Conflict):
                for cand in cell.candidates:
                    picked.add(cand.card_id)
            elif isinstance(cell, Cell):
                picked.add(cell.card_id)
    return sorted(picked)


def _handle_backend_multi_axis_brownfield(
    *,
    project_root: Path,
    active_cards: list[CardManifest],
    composer_result: "dict[str, dict[str, Cell | None]] | None" = None,
) -> dict[str, Any]:
    """Brownfield multi-axis backend handler — DET-6 W7.1, cobre AC-6.

    Chamado por ``_run_pipeline`` no hot-path brownfield ativo (Step 5, L2520).
    O wiring entrou em W7.4 (não é mais chamada isolada pelo integration test).

    Fluxo:
      1. Roda ``compose_backend_axes`` (W5) sobre ``active_cards``
         normalizados pra shape do composer. Se ``composer_result`` já foi
         pré-computado pelo caller (B3 — dedup: evita recompute duplo no
         hot-path ativo), reutiliza sem re-varrer. Integration tests que
         chamam o handler isolado passam o default ``None``.
      2. Detecta uniformity per axis (adaptive UX — SPEC §"Adaptive UX").
      3. Renderiza tabela (axis × platform → card / conflict / null).
      4. Emit ``ask_three_paths`` (Phase A) com 3 opções:
         a) confirmar detection como-is
         b) ajustar células divergentes
         c) começar do zero (custom-from-scratch — DEFERRED a W7.2)
      5. Processa resposta:
         - "a" (confirm) → aplica composer_result direto, retorna result
           com ``choice="confirm"`` + ``selected_card_names``.
         - "b" (adjust) / "c" (scratch) → DEFERRED a W7.2 (multi-select per
           cell / picker greenfield). WR-03 (Path A): em vez de retornar um
           set vazio (conjunto degradado silencioso), redireciona pra
           "confirmar como-is" — retorna ``choice="confirm"`` com a MESMA
           seleção do composer que "a" produziria + avisa o usuário (via
           renderer) que o ajuste/scratch ainda não está disponível.

    Args:
        project_root: raiz do projeto sob análise (composer + signals).
        active_cards: lista de ``CardManifest`` que o pipeline já tem em mão.
        composer_result: resultado pré-computado de ``compose_backend_axes``
            (B3 — dedup). Se ``None`` (default), o handler computa internamente.
            O caller (``_run_pipeline``) passa o resultado já computado pra
            ``has_signals`` — elimina o duplo-custo no hot-path brownfield.

    Returns:
        Dict com keys:
          - ``choice``: "confirm" (sempre, em R1 — b/c redirecionam pra
            confirmar como-is até W7.2 implementar adjust/scratch; WR-03)
          - ``selected_card_names``: list[str] (seleção do composer)
          - ``composer_result``: dict aninhado retornado pelo composer
            (passa adiante pro caller fazer downstream do label).

    Raises:
        PausedForInputError: quando não há ``forge-response.json`` casando
            o intent-id (primeiro call do par). Top-level handler do CLI
            sai com exit 2; o caller (W7.4) re-invoca após response.
    """
    # Cycle broken in Phase B (PR #13 review): _eval_detection_signals
    # moved to engine.detection._eval, composer now imports from there.
    # B3 (Fase 1): reutiliza composer_result pré-computado quando disponível
    # (evita o duplo-custo no hot-path brownfield ativo — L2507 + aqui).
    # Integration tests que chamam o handler isolado passam None → recomputa.
    if composer_result is None:
        normalized = _normalize_cards_for_composer(active_cards)
        composer_result = compose_backend_axes(project_root, normalized)
    uniformity = _detect_axis_uniformity(composer_result)
    table = _render_axes_table(composer_result, uniformity)

    # Three-paths block — labels carregam motive textual pro host renderizar
    # o bloco canônico de discipline §1.
    # P-02 / Mandamento 5: os motives de b/c não vazam roadmap interno
    # ("[W7.2 …]"). Esses caminhos ainda não estão disponíveis nesta versão;
    # o motive honesto orienta o usuário a confirmar como-is por ora. A
    # implementação real (multi-select per-cell / picker greenfield) está
    # anotada como gap deferido em docs/design/04-pending.md.
    paths = [
        {
            "label": "Confirmar detection como-is",
            "motive": (
                "Aceita a tabela detectada acima e segue com esses cards "
                "pro resolve. Caminho recomendado."
            ),
        },
        {
            "label": "Ajustar células divergentes",
            "motive": (
                "Escolher card por célula ainda não está disponível nesta "
                "versão — por ora, confirme como-is e ajuste depois com "
                "`forge reconfigure`."
            ),
        },
        {
            "label": "Começar do zero (custom)",
            "motive": (
                "O fluxo greenfield-style ainda não está disponível nesta "
                "versão — por ora, confirme como-is."
            ),
        },
    ]

    # P-04: a tabela (20+ linhas) ia embutida no gate_name → virava um blob
    # gigante como "pergunta" no AskUserQuestion. Agora imprime via renderer
    # como CONTEXTO antes do prompt; o gate_name fica curto e estável.
    renderer.write("")
    renderer.write("Detecção composta (axis × plataforma):")
    renderer.write(table)
    renderer.write("")
    choice_key = ui_question.ask_three_paths("init-brownfield-detection", paths)

    if choice_key == "a":
        return {
            "choice": "confirm",
            "selected_card_names": _collect_confirm_selection(composer_result),
            "composer_result": composer_result,
        }

    # WR-03 (Path A): os caminhos "b" (ajustar células) e "c" (começar do
    # zero) ainda não estão disponíveis nesta versão (deferred a W7.2). Antes
    # eles retornavam `selected_card_names: []`, o que produzia um conjunto
    # degradado SILENCIOSAMENTE no caller (dropava a detecção sem avisar) —
    # uma opção que mente sobre o que faz. Agora redireciona pra "confirmar
    # como-is": retorna a MESMA seleção que "a" produziria + avisa o usuário.
    # O motive já orienta isso ("por ora, confirme como-is"); aqui o
    # comportamento real passa a casar com o que o label promete.
    label = "Ajustar células" if choice_key == "b" else "Começar do zero"
    renderer.write(
        renderer.colored(
            f"'{label}' ainda não está disponível nesta versão — segui com a "
            "detecção como-is. Ajuste depois com `forge reconfigure`.",
            "yellow",
        )
    )
    return {
        "choice": "confirm",
        "selected_card_names": _collect_confirm_selection(composer_result),
        "composer_result": composer_result,
    }


# ── W7.2 greenfield bundle picker ───────────────────────────────────────────

# Os 8 axes canônicos vivem em engine.detection._axes.BACKEND_AXES
# (shared com reconfigure.py — PR #13 review #3405254057).

# Sentinela do picker — não corresponde a YAML, dispara o caminho per-axis.
_BUNDLE_SENTINEL_CUSTOM = "custom-from-scratch"


def _load_bundle_files(bundles_dir: Path) -> dict[str, dict[str, Any]]:
    """Carrega os bundle YAMLs em `bundles_dir/<name>.yaml`.

    Retorna ``{bundle_name: parsed_yaml_dict}``. Bundles inválidos (yaml
    parse error, schema-version != 1, name ausente) são silenciosamente
    pulados — ``validate_presets.py`` (W6.3) já é o gate canônico de
    schema; o handler aqui só carrega o que dá. Caller decide o que fazer
    se um bundle esperado faltar.
    """
    loaded: dict[str, dict[str, Any]] = {}
    if not bundles_dir.is_dir():
        return loaded
    for path in sorted(bundles_dir.glob("*.yaml")):
        try:
            data = read_yaml_or_default(path, default=None)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        name = data.get("name")
        if not isinstance(name, str) or not name:
            continue
        loaded[name] = data
    return loaded


def _bundle_cards_for_axis(bundle: dict[str, Any], axis: str) -> list[str]:
    """Extrai os cards não-null de um (bundle, axis) cell.

    Shape canônico (W6.1 / validate_presets W6.3):

      defaults:
        <axis>:
          all-platforms: <card-name | null>
          # ou
          android: <card-name | null>
          ios:     <card-name | null>
          kmp:     <card-name | null>

    Retorna lista de strings (ordenada, dedup'd) com os cards declarados.
    Vazia se cell inteira é null ou se axis ausente.
    """
    defaults = bundle.get("defaults") or {}
    cell = defaults.get(axis) or {}
    if not isinstance(cell, dict):
        return []
    cards: set[str] = set()
    for value in cell.values():
        if isinstance(value, str) and value:
            cards.add(value)
    return sorted(cards)


def _bundle_to_selected_cards(bundle: dict[str, Any]) -> list[str]:
    """União dos cards declarados em todos os axes do bundle (ordenada)."""
    picked: set[str] = set()
    for axis in BACKEND_AXES:
        picked.update(_bundle_cards_for_axis(bundle, axis))
    return sorted(picked)


def _render_axis_state(bundle: dict[str, Any], axis: str) -> str:
    """Formata o estado atual da cell `(bundle, axis)` pra label do ask_multi.

    Casos cobertos:
      · all-platforms: <card> → "<card>"
      · all-platforms: null → "(nenhum)"
      · per-platform shape → "android:<a> · kmp:<k>" (skip nulls)
    """
    defaults = bundle.get("defaults") or {}
    cell = defaults.get(axis) or {}
    if not isinstance(cell, dict) or not cell:
        return "(nenhum)"
    if "all-platforms" in cell:
        value = cell["all-platforms"]
        return str(value) if value else "(nenhum)"
    parts: list[str] = []
    for platform in sorted(cell.keys()):
        value = cell[platform]
        if value:
            parts.append(f"{platform}:{value}")
    return " · ".join(parts) if parts else "(nenhum)"


def _per_axis_options(
    available_cards: list[CardManifest],
    axis: str,
) -> dict[str, str]:
    """Monta options dict pro ask() per-axis prompt.

    Keys são card names (mesma convenção dos bundles); labels carregam a
    descrição curta. Inclui sempre key ``"skip"`` no fim — opt-out
    explícito, mantém cell None nesse axis.

    Filtra ``available_cards`` por ``category == axis``: card só aparece
    como opção do axis "data" se o YAML do card declarar ``identity.category:
    data``. Cards sem category compatível são silenciosamente excluídos.

    Quando ``available_cards`` está vazio (teste ou greenfield puro sem
    catalog carregado), retorna apenas a opção ``"skip"`` — o user só
    consegue optar por "deixar vazio".
    """
    options: dict[str, str] = {}
    for card in available_cards:
        if not isinstance(card, CardManifest):
            continue
        if card.category != axis:
            continue
        if not card.name:
            continue
        label = card.description or card.name
        options[card.name] = label
    options["skip"] = "(nenhum — deixar este eixo vazio)"
    return options


def _run_per_axis_prompts(
    available_cards: list[CardManifest],
    axes_to_prompt: tuple[str, ...] | list[str],
) -> list[str]:
    """Itera ``axes_to_prompt`` perguntando o card por axis.

    Retorna a lista (ordenada, dedup'd) de cards selecionados. Cada axis
    emite um ``ask`` independente (1 intent por axis). Response "skip"
    deixa o axis vazio. Compartilhável com W7.3 reconfigure no futuro
    — mantém o escopo privado em init.py por enquanto (W7.2 não promove).
    """
    picked: set[str] = set()
    for axis in axes_to_prompt:
        options = _per_axis_options(available_cards, axis)
        chosen = ui_question.ask(
            f"Qual card para o eixo '{axis}'?",
            options,
            default="skip",
        )
        if chosen and chosen != "skip":
            picked.add(chosen)
    return sorted(picked)


def _apply_axis_overrides(
    bundle: dict[str, Any],
    overridden_axes: list[str],
    overridden_cards: list[str],
    available_cards: list[CardManifest],
) -> list[str]:
    """Compõe o set final: bundle defaults nos axes preservados + overrides.

    Lógica:
      · Pra cada axis NÃO em ``overridden_axes`` → mantém cards do bundle.
      · Pra cada axis EM ``overridden_axes`` → descarta os cards default
        do bundle nesse axis, aplica os cards de ``overridden_cards`` cuja
        category == axis (filtrado via ``available_cards``).

    Retorna lista ordenada e dedup'd. Quando ``available_cards`` está
    vazia (teste sem catalog), o filtro por category falha gracefully e
    o axis overridden fica vazio (sem nenhum card — consistente com
    response "skip").
    """
    overridden_set = set(overridden_axes)
    picked: set[str] = set()
    # 1) Eixos preservados → bundle defaults.
    for axis in BACKEND_AXES:
        if axis in overridden_set:
            continue
        picked.update(_bundle_cards_for_axis(bundle, axis))
    # 2) Eixos overridden → cards do override casados ao axis via catalog.
    card_axis: dict[str, str] = {}
    for card in available_cards:
        if isinstance(card, CardManifest) and card.name and card.category:
            card_axis[card.name] = card.category
    for card_name in overridden_cards:
        axis = card_axis.get(card_name)
        if axis is None or axis in overridden_set:
            # Se sem catalog (axis=None), confia que o caller só passou
            # cards de axes overridden — adiciona direto.
            picked.add(card_name)
    return sorted(picked)


def _handle_backend_multi_axis_greenfield(
    *,
    project_root: Path,
    available_cards: list[CardManifest],
) -> dict[str, Any]:
    """Greenfield multi-axis backend handler — DET-6 W7.2, cobre AC-7.

    Roda quando o composer não emitiu signals (zero detection — caso
    típico de projeto novo). Substitui (em projetos sem signals) o legacy
    backend picker linha ~1264 do ``_run_pipeline``. W7.2 só ADICIONA esta
    função; wiring real entra em W7.4 com a remoção do legacy.

    Fluxo (SPEC §"Greenfield init com bundle picker"):

      1. Carrega os bundle YAMLs em ``$FORGE_HOME/presets/kmp-mobile/bundles/``.
      2. Emit ``ask()`` com 4 opções: 3 bundles + sentinela
         ``custom-from-scratch``.
      3. Se sentinela → roda per-axis prompts pros 8 axes canônicos.
         Retorna ``choice="scratch"``.
      4. Se bundle → ``confirm()`` "quer customizar algum axis?".
         · Não → aplica bundle.defaults direto. Retorna
           ``choice="bundle"`` + ``bundle_name``.
         · Sim → ``ask_multi()`` "quais axes?", depois per-axis prompts
           só pros selecionados. Retorna ``choice="bundle-overridden"``
           + ``bundle_name``.

    Args:
        project_root: raiz do projeto sob init (usado pelo intent state).
            Atualmente o handler resolve ``bundles_dir`` via ``forge_home()``
            (catálogo canônico, não per-project), mas o parâmetro fica na
            assinatura por simetria com o W7.1 brownfield e pra suportar
            W7.4 (que vai passar pra downstream do label).
        available_cards: catálogo carregado (mesma shape do W7.1). Usado
            pra mapear card→axis no per-axis prompt e no apply_overrides.
            Vazia em testes minimais — handler degrada gracefully (per-
            axis prompts mostram só "skip").

    Returns:
        Dict com keys:
          · ``choice``: "bundle" | "bundle-overridden" | "scratch"
          · ``bundle_name``: nome do bundle escolhido (None em "scratch")
          · ``selected_card_names``: list[str] (ordenada, dedup'd)

    Raises:
        PausedForInputError: na primeira chamada de cada intent emitido
            sem response ainda no disco. Top-level handler do CLI sai com
            exit 2; caller (W7.4) re-invoca após response.
    """
    bundles_dir = forge_home() / "presets" / PRESET_NAME / "bundles"
    bundles = _load_bundle_files(bundles_dir)

    # Opções fixas da SPEC §"Starter bundles". Não dependem da existência
    # física do YAML — se o YAML faltar, falhamos depois (no apply) com
    # mensagem clara; o picker apresenta as 4 opções canônicas.
    picker_options: dict[str, str] = {
        "firebase-full": "Firebase em todos os eixos (serverless-ready)",
        "rest-with-firebase-telemetry": (
            "REST API para dados + Firebase para identity, telemetria, push"
        ),
        "local-only": "Offline-first, sem backend remoto",
        _BUNDLE_SENTINEL_CUSTOM: (
            "Começar do zero — escolher cada eixo manualmente"
        ),
    }

    choice_key = ui_question.ask(
        "Qual stack inicial pra este projeto?",
        picker_options,
        default="firebase-full",
    )

    # Caminho A — sentinela: pula bundle, prompta cada axis.
    if choice_key == _BUNDLE_SENTINEL_CUSTOM:
        selected = _run_per_axis_prompts(available_cards, BACKEND_AXES)
        return {
            "choice": "scratch",
            "bundle_name": None,
            "selected_card_names": selected,
        }

    # Caminho B/C — bundle escolhido. Resolve o YAML.
    bundle = bundles.get(choice_key)
    if bundle is None:
        # Bundle YAML missing — degrada pra "scratch" com selected vazio.
        # Auditor humano vê o choice no commit body e ajusta manualmente.
        return {
            "choice": "scratch",
            "bundle_name": None,
            "selected_card_names": [],
        }

    wants_override = ui_question.confirm(
        f"Quer customizar algum eixo do bundle '{choice_key}'?",
        default=False,
    )

    # Caminho B — bundle como-is.
    if not wants_override:
        return {
            "choice": "bundle",
            "bundle_name": choice_key,
            "selected_card_names": _bundle_to_selected_cards(bundle),
        }

    # Caminho C — bundle com override seletivo.
    axis_options: dict[str, str] = {
        axis: f"{axis} (atual: {_render_axis_state(bundle, axis)})"
        for axis in BACKEND_AXES
    }
    overridden_axes = ui_question.ask_multi(
        "Quais eixos quer ajustar?",
        axis_options,
        min_selected=1,
    )
    overridden_cards = _run_per_axis_prompts(available_cards, overridden_axes)
    selected = _apply_axis_overrides(
        bundle, overridden_axes, overridden_cards, available_cards
    )
    return {
        "choice": "bundle-overridden",
        "bundle_name": choice_key,
        "selected_card_names": selected,
    }


# ── W7.4 — Backend cells adapters (composer_result / bundle → cells) ────────


def _composer_result_to_cells(
    composer_result: dict[str, dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any] | None]]:
    """W7.1 brownfield adapter: composer_result → backend cells shape.

    Shape de saída segue ``docs/schemas/backend-axes.md`` §"Cell object":

      backend.<axis>.<platform> = {card: <id>, status: "active"} | None

    Regras de conversão:
      · cell None → None (cell vazia preservada)
      · cell Cell(card_id=X, ...) → {card: X, status: "active"}
      · cell Conflict(candidates=(c1, c2, ...)) → {card: c1.card_id,
        status: "active"}. Convenção: pega primeiro candidate (já
        ordenado alfabeticamente por card_id em ``engine.detection.
        composer.Conflict`` — output determinístico). Auditor humano
        que escolheu Path A (confirm) implicitamente aceitou essa
        resolução; Path B (adjust — W7-future) é onde o user
        desambigua per-cell.

    Status sempre ``"active"`` neste adapter — Phase B não infere
    migration intent automaticamente. Migration entra via
    ``forge reconfigure`` (W7.3) quando o auditor edita manualmente.
    """
    out: dict[str, dict[str, dict[str, Any] | None]] = {}
    for axis in sorted(composer_result.keys()):
        axis_map = composer_result[axis]
        out_axis: dict[str, dict[str, Any] | None] = {}
        for platform in sorted(axis_map.keys()):
            cell = axis_map[platform]
            if cell is None:
                out_axis[platform] = None
                continue
            if isinstance(cell, Conflict):
                # Conflict — primeiro candidate por convenção (já ordenado
                # alfabeticamente). Auditor confirmou via Path A.
                if cell.candidates:
                    chosen = cell.candidates[0]
                    out_axis[platform] = {
                        "card": chosen.card_id,
                        "status": "active",
                    }
                else:
                    out_axis[platform] = None
                continue
            if isinstance(cell, Cell) and cell.card_id:
                out_axis[platform] = {"card": cell.card_id, "status": "active"}
            else:
                out_axis[platform] = None
        out[axis] = out_axis
    return out


def _bundle_to_cells(
    bundle_name: str | None,
    selected_card_names: list[str],
    *,
    forge_root: Path,
    available_cards: list[CardManifest] | None = None,
) -> dict[str, dict[str, dict[str, Any] | None]]:
    """W7.2 greenfield adapter: bundle YAML / selected cards → backend cells.

    Dois cenários cobertos:

    1. ``bundle_name`` corresponde a um YAML em
       ``$FORGE_HOME/presets/<preset>/bundles/<name>.yaml``: carrega o
       bundle e emite cells per (axis, platform) a partir de
       ``bundle.defaults``. Forma das cells segue
       ``docs/schemas/backend-axes.md`` — ``all-platforms`` é
       desempacotado pras plataformas declaradas no bundle. Cells
       null no bundle ficam null no output.

    2. ``bundle_name`` é None / sentinela ``custom-from-scratch`` /
       bundle YAML missing: cai no fallback ``available_cards`` —
       mapeia cada card selecionado pra (card.category, "all-platforms")
       como cell ativa. Fallback é silently degenerate quando
       ``available_cards`` está vazio (teste minimal) — emite cells
       vazias e o auditor ajusta via ``forge reconfigure``.

    Cards em ``selected_card_names`` mas NÃO referenciados pelo bundle
    (override-overridden caminho ou scratch) entram pelo fallback com
    ``all-platforms`` — caller é responsável por validar via cascade
    (RULE-021) downstream.
    """
    cells: dict[str, dict[str, dict[str, Any] | None]] = {}

    # Caminho 1: bundle YAML válido.
    bundle: dict[str, Any] | None = None
    if bundle_name and bundle_name != _BUNDLE_SENTINEL_CUSTOM:
        bundles_dir = forge_root / "presets" / PRESET_NAME / "bundles"
        bundle = _load_bundle_files(bundles_dir).get(bundle_name)

    if bundle is not None:
        defaults = bundle.get("defaults") or {}
        for axis in BACKEND_AXES:
            cell_block = defaults.get(axis)
            if not isinstance(cell_block, dict):
                continue
            axis_out: dict[str, dict[str, Any] | None] = {}
            if "all-platforms" in cell_block:
                card_val = cell_block["all-platforms"]
                axis_out["all-platforms"] = (
                    {"card": card_val, "status": "active"}
                    if isinstance(card_val, str) and card_val
                    else None
                )
            else:
                for platform, card_val in cell_block.items():
                    if not isinstance(platform, str):
                        continue
                    axis_out[platform] = (
                        {"card": card_val, "status": "active"}
                        if isinstance(card_val, str) and card_val
                        else None
                    )
            cells[axis] = axis_out

        # Cards em selected_card_names que NÃO estão no bundle (override
        # selected via _apply_axis_overrides) entram via available_cards.
        if available_cards:
            bundle_cards: set[str] = set()
            for axis_block in defaults.values():
                if not isinstance(axis_block, dict):
                    continue
                for v in axis_block.values():
                    if isinstance(v, str) and v:
                        bundle_cards.add(v)
            extras = [n for n in selected_card_names if n not in bundle_cards]
            if extras:
                _fold_extras_into_cells(cells, extras, available_cards)
        return cells

    # Caminho 2: fallback (custom-from-scratch ou bundle missing).
    if available_cards:
        _fold_extras_into_cells(cells, selected_card_names, available_cards)
    return cells


def _fold_extras_into_cells(
    cells: dict[str, dict[str, dict[str, Any] | None]],
    extra_card_names: list[str],
    available_cards: list[CardManifest],
) -> None:
    """Compõe cells dos cards listados via category (axis) → all-platforms.

    Override per-axis no W7.2 não declara platforms — assumimos
    ``all-platforms``. Quando ``forge reconfigure`` (W7.3) edita
    granularidade, o user ajusta a cell pra per-platform shape se
    quiser. Cards sem category ou category fora dos 8 axes canônicos
    são silenciosamente descartados — anti-padrão #6 (cards sem axis
    não pertencem ao bloco ``backend``).
    """
    by_name: dict[str, str] = {}
    for card in available_cards:
        if isinstance(card, CardManifest) and card.name and card.category:
            by_name[card.name] = card.category
    for card_name in extra_card_names:
        axis = by_name.get(card_name)
        if axis is None or axis not in BACKEND_AXES:
            continue
        axis_out = cells.setdefault(axis, {})
        # Se o axis já existe e tem per-platform shape, NÃO sobrescreve —
        # esse caminho só popula axes vazios. Caso seja override e o axis
        # já veio do bundle, o caller (_bundle_to_cells) já filtrou pra
        # extras-only, então fica simples.
        if not axis_out:
            axis_out["all-platforms"] = {"card": card_name, "status": "active"}


def _summarize_backend_cells(
    cells: dict[str, dict[str, dict[str, Any] | None]] | None,
) -> str:
    """Render compacto pro display (Step 14 history + Step 15 summary).

    Saída exemplo:
      data: retrofit-client(android), ktor-client(kmp) · auth: firebase-auth · …

    Vazio se ``cells`` é None / dict vazio.
    """
    if not cells:
        return "(sem cells configuradas)"
    parts: list[str] = []
    for axis in sorted(cells.keys()):
        axis_map = cells[axis] or {}
        if not isinstance(axis_map, dict):
            continue
        # Detect uniform "all-platforms" — emite "axis: card".
        if "all-platforms" in axis_map:
            cell = axis_map["all-platforms"]
            if cell and isinstance(cell, dict) and cell.get("card"):
                parts.append(f"{axis}: {cell['card']}")
            continue
        # Per-platform — emite "axis: card1(p1), card2(p2)".
        pieces: list[str] = []
        for platform in sorted(axis_map.keys()):
            cell = axis_map[platform]
            if cell and isinstance(cell, dict) and cell.get("card"):
                pieces.append(f"{cell['card']}({platform})")
        if pieces:
            parts.append(f"{axis}: {', '.join(pieces)}")
    return " · ".join(parts) if parts else "(sem cells configuradas)"


def _build_paths(project_root: Path, conv_inv: Any) -> dict[str, Any]:
    """Best-effort path inference. Greenfield gets sensible defaults."""
    paths: dict[str, Any] = {
        "features-package-root": f"docs/{FEATURE_WORKFLOW_DIRNAME}/features",
        "inventory-root": ".claude/inventory",
        "memory-root": ".claude/memory",
        "graph-path": ".claude/graph.db",
        "hooks-root": ".claude/forge/hooks",
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
