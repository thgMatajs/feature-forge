# feature-forge

A standalone CLI skill that orchestrates end-to-end planning + implementation of mobile features across Android, iOS, KMP, and Web. Backend-agnostic (Firebase, REST, GraphQL, local-only).

> **State:** v1.2-dev · 2026-06-12 · 1310 tests rapid lane + 133 integration + 21 e2e (~1480 total collected, Phase B DET-6 multi-axis backend SHIPPING-READY + REVIEWED + E2E COVERED em worktree `det-6-w1`; Phase A DRIFT-1 PR #11 master-review remediado integralmente; DET-3 gradle-dep signal type mergido de `main`) · 25 validators · 13 comandos · 29 cards · 4 bundles · ~400 arquivos · ~52.5K LOC

## What it is

Skill CLI-first com 13 comandos canônicos (zero flags — toda parametrização via menu interativo) que dirige o ciclo completo de feature mobile:

1. **`forge init`** — bootstrap em qualquer projeto KMP/mobile (greenfield ou brownfield). Step 11.5 escaneia o codebase atrás de duplicações já existentes (6 categorias de finding).
2. **`forge plan {feature-slug}`** — 5 waves (intake/PRD → screen+contracts → tech-spec → tasks → readiness) com 16 templates. Subtypes: product / refactor / bugfix / spike / chore (cada um com waves específicas). No bugfix o pipeline detecta o ticket (ex: IN-37234), pula o PRD e exige um regression test que falha primeiro antes da correção; refactor entra com contrato no-behavior-change.
3. **`forge implement {feature-slug}`** — execução task-by-task com gates de scope + atomic commits
4. **`forge verify`** — cascade de 20 validators com 3-caminhos discipline (inclui `check_no_behavior_change` para refactor, `check_cyclomatic_complexity` multi-language, `check_secrets` multi-tool security gate, e `validate_extension_feature` cross-cutting pra Gap 9 extensions). Cascade fail-fast: para no primeiro erro duro; os gates fortes (complexity, secrets) aceitam override-justify auditável no commit body e bypass de emergência logado em `.claude/state/`.
5. **`forge doctor`** — health check em 14 categorias (inclui reuse-intelligence findings agregados + `cc-gate-tools` + `secrets-tools`)
6. **`forge reconfigure`** — single entrypoint pra TODA mutação post-init (cards, paths, conventions, graph rebuild que re-queue reuse proposals)
7. **`forge qa`** — gate adversarial multi-agente (red-team). 4 attack vectors × 4 scope targets em sandbox isolado. Verdict informativo (BLOCK/FLAG/PASS), findings → `forge evolve`.
8. Outros: `status`, `evolve` (review proposals — 16 kinds), `undo`, `graph` (Q1-Q17), `memory`, `raw`

## Identity

| | |
|---|---|
| Name | feature-forge |
| Command alias | `forge` |
| Persona | mentor calmo |
| Vocabulary | "forge" só como verbo; resto neutro |
| Scope OUT | arch macro · decisão de produto · code review final · time tracking |

## Stack alvo

Backend-agnostic — qualquer combinação:

- **Firebase stack**: firebase-auth + firestore-persistence + firestore-realtime + firestore-security-rules + firebase-storage + crashlytics
- **REST stack**: ktor-client + rest-api-contract + kotlinx-serialization-json + room-database + datastore-prefs + auth-jwt-bearer
- **Híbrido**: Firebase Auth + REST API + Room local cache
- **Local-only**: Room + DataStore (offline-first)
- **UI**: Compose (Android) + SwiftUI (iOS) + React (Web via @JsExport)
- **KMP shared**: Kotlin Multiplatform + SKIE bridge
- **Navigation**: Nav3 (Android) + NavigationStack (iOS)
- **DI**: Koin Annotations (KMP/Android) + factory functions (iOS/Web)

## Manutenção via Claude Code

Este repo tem rules system ativo (`CLAUDE.md` + `.claude/rules/` + 4 hooks) que disciplina toda sessão Claude Code mantendo o projeto. Orchestrator-mantenedor delega 100% das mudanças via `Agent` tool (`gsd-executor` / `gsd-code-reviewer` / `gsd-code-fixer`). Hooks: SessionStart injeta orientação, PreToolUse audita load-bearing edits, PostToolUse lembra doc-sync, git pre-commit hard-blocks edits em `docs/design/01-decisions.md` sem "Revisita decisão" no CHANGELOG.

Após clonar:

```bash
bash .claude/bootstrap.sh
```

Detalhe: `CLAUDE.md` + `.claude/rules/README.md`.

## Arquitetura

6 layers (ver `docs/design/00-vision.md` pra detalhe):

1. **Cards** — unidades atômicas de composição (22 cards canônicos v1.2 + overlay local em `.claude/cards/local/`)
2. **Templates** — esqueletos dos 18 artefatos por feature (16 produto + bugfix-intake + refactor-intake)
3. **Memory** — L1 per-feature (WIP) + L2 project (committed) + L3 read-only (auto-memory)
4. **Graph** — SQLite com 17 queries canônicas (Q1–Q10 estruturais, Q11 reusable-helpers, Q12–Q17 reuse-intelligence: duplicates within/cross-module, KMP-migration, near-duplicates, redundant-platform, TS-helpers)
5. **Inventory** — DS components + i18n + conventions extraídos do projeto
6. **Engine Python** — Bash dispatcher + 13 commands + foundation + state + integrations + reuse-intelligence pipeline (parsers, body-hash, gradle modules/deps, detection, apply)

## Stats

| Categoria | Conteúdo |
|---|---|
| Schemas | 14 schemas (inclui `intent-protocol.md` novo em v1.2-dev / Phase A DRIFT-1 + `backend-axes.md` v1.2-dev Phase B) + capability-labels catalog + schema v2 (reuse_findings, module_deps) |
| Agent prompts | 10 (planning-conductor + 9 sub-agents) |
| UX roteiros | 7 (init, plan, implement, verify, doctor, reconfigure, evolve) — todos cobrem subtypes + reuse intelligence |
| Templates canônicos | 18 (16 produto + feature-intake-bugfix + feature-intake-refactor) |
| Cards canônicos | 29 (8 stack + 5 Firebase + firebase-crashlytics + 4 REST + retrofit-client + room-database + sqldelight + datastore-prefs + shared-preferences-prefs com `legacy-marker` + firebase-analytics + posthog-analytics + fcm + onesignal + firebase-remote-config + posthog-flags); overlay local em `.claude/cards/local/<name>/` desde Gap 5 (2026-06-02). Phase B DET-6 acresceu 6 cards de analytics/notifications/flags + sqldelight (axis persistence/kmp) + rename `crashlytics → firebase-crashlytics`. |
| Preset | kmp-mobile (8 stack cards + 4 bundles: firebase-full + rest-with-firebase-telemetry + local-only + custom-from-scratch sentinela) — substitui o bloco `backend-candidates` monolítico desde Phase B DET-6 |
| Validators Python | 25 + 3 helpers (`_gate_infra`, `_diff`, `_common`) — inclui `check_cyclomatic_complexity` (Kotlin/Swift/TS/Python via Detekt/SwiftLint/eslint/Radon), `check_secrets` (gitleaks + trufflehog), `check_no_behavior_change` (refactor), `validate_extension_feature` (extends-feature cross-cutting), `validate_presets` (Phase B DET-6 — bundle YAML schema) |
| Hooks | 9 + 1 reuse incremental (`post-edit-detect-duplications.sh`) |
| Tests | ~1480 collected / 1310 rapid lane + 133 integration + 21 e2e (unit + integration + e2e · ~20 skipped · baseline histórico em CHANGELOG.md). Phase A DRIFT-1 acresceu +118 sobre o pré-W2 1046; Phase B DET-6 acresceu W4-W7 (~88 unit + 12 integration) + W8 polish (+23 rapid + 3 integration + 4 e2e) chegando a 1310 rapid + 133 integration + 21 e2e. |
| LOC total | ~52.500 |
| Engine LOC | ~22.000 (Python) |
| Files total | ~400 |
| Decisões locked | 27 + 7 direcionais (Fase 3.5) |
| Subtypes feature | 5 (product / refactor / bugfix / spike / chore) |
| Reuse finding categories | 6 (consolidate-within / promote-to-shared / redundant-platform / near-duplicate / kmp-migration / consolidate-ts) |

## Instalação

```bash
# Clone canonical
git clone <repo> ~/Documents/feature-forge
export FORGE_HOME=~/Documents/feature-forge
export PATH="$FORGE_HOME/bin:$PATH"

# Verifica
forge --version  # → forge 1.2.0

# Init num projeto novo (Step 11.5 já escaneia duplicações existentes)
cd ~/code/my-project
forge init  # → interactive, sem flags

# Revisar reuse-intelligence findings
forge evolve     # 6 kinds: consolidate / promote / kmp-migration / etc
forge graph      # opções 12–17 ou "r" (combined view)
```

Requer Python 3.11+ + PyYAML (única dep externa).

## Where it lives

```
~/Documents/feature-forge/              canonical source (this repo)
  bin/forge                             Bash dispatcher
  engine/                               Python engine (~21.900 LOC)
    graph/                              parsers (Kotlin/Swift/TS) + builder +
                                        gradle_modules + gradle_deps +
                                        _body_text + duplicates + reuse_apply +
                                        incremental + queries (Q1–Q17)
    memory/                             L1/L2/L3 + distiller (16 proposal kinds)
    cards/  inventory/  ui/  persona/   utils/ (sqlite_io + template_render)
  docs/                                 design + schemas + UX roteiros + lifecycle
  agents/                               agent prompts (10 prompts)
  templates/                            18 canonical templates (16 + bugfix + refactor)
  cards/                                22 canonical cards (+ overlay em consumidor)
  presets/kmp-mobile/                   canonical preset v1
  validators/                           20 validators + helpers (inclui check_cyclomatic_complexity + check_secrets + validate_extension_feature)
  hooks/                                9 hooks + reuse incremental script
  tests/                                ~1125 collected tests (unit + integration + e2e) + 20 skipped

[per project install via `forge init`]
{project}/.claude/
  workflow-config.yaml                  installed config
  graph.db                              codebase graph (schema v2)
  proposed-evolutions.yaml              reuse + retrospective proposals
  hooks/post-edit-detect-duplications.sh    opt-in incremental detect
```

## Command surface (13 + 2 hidden)

13 comandos user-facing — zero flags — toda parametrização via prompts interativos (Decision 9 + 10 locked).

```
forge init           bootstrap workflow num projeto (greenfield/brownfield)
                     · Step 11.5 escaneia codebase pra reuse opportunities
forge plan           plan feature (waves A-E, subtype-aware)
                     · subtypes: product / refactor / bugfix / spike / chore
                     · `forge plan refactor-{slug}` lê L1 status e pula Wave A
forge implement      execute task-by-task
forge verify         validator cascade (20 validators)
                     · check_no_behavior_change gate quando subtype=refactor
                     · check_cyclomatic_complexity gate multi-language
                     · check_secrets gate multi-tool (gitleaks per-task / trufflehog cascade)
                     · validate_extension_feature cross-cutting quando feature tem extends-feature setado (Gap 9)
forge status         read-only board
forge doctor         health check (14 categorias)
                     · inclui reuse-intelligence findings agregados
                     · inclui cc-gate-tools (detekt/swiftlint/eslint/radon)
forge reconfigure    single mutation entrypoint
                     · graph rebuild re-queue reuse proposals automaticamente
forge graph          query graph (Q1-Q17, "r" combined view)
                     · Q12-Q17: 6 reuse-intelligence queries
forge memory         inspect L1/L2/L3
forge evolve         review propostas (single-by-single) — 16 kinds
                     · 10 retrospective + 6 reuse-intelligence
forge undo           reverter última ação
forge raw            escape hatch (verify-card, edit-config, debug)
forge qa             gate adversarial multi-agente (red-team)
                     · 4 attack vectors (spec-vs-spec, chaos, coverage, validator-claim)
                     · 4 scope targets (feature / screen / task / paranoid)
                     · sandbox isolado em .planning/qa/<run-id>/fixtures/
                     · verdict informativo (BLOCK/FLAG/PASS); findings → forge evolve
```

Hidden entrypoints (invocados por hooks, nunca tipados pelo usuário):

- `forge ingest --event <type> [payload]` — graph/memory/inventory updater
- `forge graph detect-incremental <file>` — post-edit reuse detection

## Documentação

Start here:

- **`docs/product/00-prd.md`** — PRD consolidado (porta de entrada lente produto; complementa `docs/design/00-vision.md` arquitetural)
- **`docs/design/08-session-handoff.md`** — TL;DR completo + estado por fase + limites v1
- `docs/design/00-vision.md` — arquitetura (6 layers, capability cards)
- `docs/design/01-decisions.md` — 27 decisões locked
- `docs/design/06-command-surface.md` — 13 comandos canônicos + 2 hidden
- `docs/design/07-discipline.md` — 10 disciplinas universais (3-caminhos, fail-fast, pause/abort, vocabulário, fingerprint)
- `docs/design/04-pending.md` — gaps abertos + itens deferred por versão
- `docs/schemas/graph.md` — schema v2 com reuse_findings + module_deps + Q1-Q17
- `docs/schemas/proposed-evolutions.md` — 16 proposal kinds (10 retrospective + 6 reuse-intelligence)
- `docs/schemas/capability-labels.md` — catálogo canônico de capabilities
- `docs/lifecycle/memory-and-graph.md` — dataflow reuse-intelligence + idempotência
- `docs/ux/forge-init-roteiro.md` — UX cinemática do init (Cenas 5.5+5.6 reuse scan)
- `docs/ux/forge-evolve-roteiro.md` — Cenas 15-20 para os 6 reuse kinds
- `agents/planning-conductor.md` — super-agent prompt (subtypes + waves)
- `presets/kmp-mobile/README.md` — preset base v1
- `CHANGELOG.md` — release notes + histórico de mudanças

**PRD sub-docs** (lente produto detalhada):

- `docs/product/01-personas.md` — 8 personas em 3 camadas
- `docs/product/02-scenarios.md` — 6 user journeys end-to-end
- `docs/product/03-roadmap.md` — 3 ondas + Eisenhower + anti-roadmap

## Limites conhecidos

Documentados em `docs/design/08-session-handoff.md § Conhecidos limites v1` + `CHANGELOG.md § Conhecidos limites v1.1`:

**v1.0 herdados:**
- **`forge implement` é stub manual** — Apply Mode automatizado é Phase 6
- **`forge init` Cena 7 (Jira/ticketing)** não prompted — use `forge reconfigure` pós-init
- **3 kinds de `apply_proposal_to_l2`** ainda em fall-through (retrospective kinds — reduzido de 9 para 3 com os 6 reuse-intelligence kinds implementados)
- **LLM/sub-agent hookup real** — `plan.py`/`implement.py` narram fluxo + renderizam templates; integração Anthropic API é Phase 6
- **Tree-sitter / AST real** — regex parsers v1 por design

**v1.1 novos:**
- **`kmp-migration-candidate` confidence é shallow** — token Jaccard, não AST semântico. False positives possíveis; apply NUNCA auto-runs.
- **Incremental hook wiring é manual** — script é escrito em `.claude/hooks/`, mas referência em `.claude/settings.local.json` é opt-in por design.
- **Gradle dependency parsing** cobre `implementation(project(...))` e variantes comuns; `includeBuild` ou DSL Kotlin avançado podem precisar extensão.
- **Spike + chore subtypes** stubbed (refactor + bugfix shipados completos).
- **MCP polling para external-dep resolution** stubbed — Gap 8 ship manual unblock; auto-polling fica pra v1.2+.

## Origin

Extraído de `MeoBonsai/.agents/skills/feature-implementation-workflow/` em maio 2026 e generalizado pra portabilidade cross-project. Ver `INFLUENCES.md` pra atribuições.

## License

MIT (ver `LICENSE`).
