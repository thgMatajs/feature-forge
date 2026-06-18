# feature-forge

A standalone CLI skill that orchestrates end-to-end planning + implementation of mobile features across Android, iOS, KMP, and Web. Backend-agnostic (Firebase, REST, GraphQL, local-only).

> **State:** 1.4.0 pilot-ready + série de waves AI-first (unreleased/branch) · 2026-06-18 · rapid 1794 / integration 183 / e2e 30 passed (W-DEBT dívida residual: PHANTOM-STATES removido + CARDS-DISCONNECT + ABORTED-DEADEND + PLACEHOLDER-VERIFY + SCHEMA/STALE guards + readiness non-product + FORGE_HOME driver doctor + cleanup; W3 token economy: output-mode + read-commands `--json` + `--help --json` manifesto + workflow router, Revisita Decisão 10; W2 protocol robustness; camada de interação AI-first Wave 1: driver `SKILL.md`/`AGENTS.md` + front-door ticket/frase + grounded-challenge Phase 2.5 + readiness enforce + CASING-BUG fix; remediação cross-AI review PR #17; install.sh curl one-liner + forge upgrade + bash 3.2 portável; Wave 3 bug-fix sprint; Wave 2 host-aware execution; graph-ia-evolution ✅ shipped; PR #16 master review fix-pack Wave A+B+C aplicado integralmente) · 22 validators · 14 comandos · 29 cards · 4 bundles · 6 parsers (kotlin/swift/typescript + java/xml/objc) · driver `skills/feature-forge/SKILL.md` + `templates/AGENTS.md.template` · ~400 arquivos · ~52.5K LOC

## What it is

Skill CLI-first com 14 comandos canônicos (zero flags — toda parametrização via menu interativo) que dirige o ciclo completo de feature mobile:

1. **`forge init`** — bootstrap em qualquer projeto KMP/mobile (greenfield ou brownfield). Step 11.5 escaneia o codebase atrás de duplicações já existentes (6 categorias de finding).
2. **`forge plan {feature-slug}`** — 5 waves (intake/PRD → screen+contracts → tech-spec → tasks → readiness) com 16 templates. Subtypes: product / refactor / bugfix / spike / chore (cada um com waves específicas). No bugfix o pipeline detecta o ticket (ex: IN-37234), pula o PRD e exige um regression test que falha primeiro antes da correção; refactor entra com contrato no-behavior-change.
3. **`forge implement {feature-slug}`** — execução task-by-task com gates de scope + atomic commits
4. **`forge verify`** — cascade de 20 validators com 3-caminhos discipline (inclui `check_no_behavior_change` para refactor, `check_cyclomatic_complexity` multi-language, `check_secrets` multi-tool security gate, e `validate_extension_feature` cross-cutting pra Gap 9 extensions). Cascade fail-fast: para no primeiro erro duro; os gates fortes (complexity, secrets) aceitam override-justify auditável no commit body e bypass de emergência logado em `.claude/state/`.
5. **`forge doctor`** — health check em 17 categorias (inclui reuse-intelligence findings agregados + `cc-gate-tools` + `secrets-tools` + `FORGE_HOME driver`)
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

## Quick Start

### Instalar

```bash
curl -fsSL https://raw.githubusercontent.com/thgMatajs/feature-forge/main/scripts/install.sh | bash
```

O instalador (bash 3.2 portável, macOS/Linux):

1. Clona em `~/.local/share/feature-forge/` (XDG default; respeita `$XDG_DATA_HOME`)
2. Cria venv e instala dependências via `pip install -e .` (pyproject.toml)
3. Cria symlink `~/.local/bin/forge`
4. Detecta shell (zsh / bash / fish) e oferece 3-caminhos para adicionar `~/.local/bin` ao PATH
5. Detecta conflito de alias `forge` existente (3-caminhos: sobrescrever / instalar como `forge-cli` / abortar)

Pré-requisitos: `git` + `python3 >= 3.11`.

### Usar

```bash
# Entrar no projeto mobile
cd ~/code/seu-app

# Bootstrap interativo (.claude/forge/ + forge-config.yaml + hooks)
forge init

# Planejar uma feature
forge plan minha-feature

# Validar
forge verify
```

O `forge init` detecta a stack (KMP, Android, iOS, brownfield), aplica cards, e já constrói o graph do codebase.

> Sem flags. Tudo interativo. 5 minutos do clone ao primeiro `forge plan`.

### Atualizar

```bash
forge upgrade
```

Executa `git pull --ff-only` + venv refresh + smoke (`forge --version`). Rollback automático se o smoke falhar — instala estado anterior via `git reset --hard`.

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
6. **Engine Python** — Bash dispatcher + 14 commands + foundation + state + integrations + reuse-intelligence pipeline (parsers, body-hash, gradle modules/deps, detection, apply) + host-aware execution layer (`engine/host/` — 4 adapters: claude_code / opencode-fallback / tty / intent_file)

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
| Graph parsers | 6 (Kotlin / Swift / TypeScript + Java / XML / Objective-C — Java/XML/ObjC novos em v1.3.0 graph-ia-evolution). Body extraction (`symbols.body`) cobre brace-delimited bodies (5 linguagens; XML é NULL). |
| Tests | rapid **1794 passed** / integration **183 passed** / e2e **30 passed** na série de waves AI-first (unreleased/branch `feat/w-debt`: Wave 1 + W2 + W3 + W-DEBT empilhados; 0 falhas). Histórico: 1779/180/30 pós-W3; 1611/168/30 em 1.4.0 pilot-ready; 1619 collected pós PR #16 fix-pack. Baseline histórico em CHANGELOG.md. |
| LOC total | ~52.500 |
| Engine LOC | ~33.500 (Python; engine/ apenas — validators/ adicional ~7.300) |
| Files total | ~400 |
| Decisões locked | 27 + 7 direcionais (Fase 3.5) |
| Subtypes feature | 5 (product / refactor / bugfix / spike / chore) |
| Reuse finding categories | 6 (consolidate-within / promote-to-shared / redundant-platform / near-duplicate / kmp-migration / consolidate-ts) |

## Instalação

```bash
curl -fsSL https://raw.githubusercontent.com/thgMatajs/feature-forge/main/scripts/install.sh | bash
```

Instala em `~/.local/share/feature-forge/` (XDG default; respeita `$XDG_DATA_HOME`), cria venv, symlink `~/.local/bin/forge`, configura PATH. Pré-requisitos: git + python3 >= 3.11. Script portável bash 3.2 (macOS default).

```bash
# Após instalar
forge --version  # → forge 1.4.0

# Init num projeto
cd ~/code/my-project
forge init       # interativo, sem flags

# Revisar reuse-intelligence findings
forge evolve     # 6 kinds: consolidate / promote / kmp-migration / etc
forge graph      # opções 12–17 ou "r" (combined view)

# Atualizar o próprio forge
forge upgrade    # git pull + venv refresh + smoke + rollback automático
```

### Bootstrap (dev / contribuição)

Para quem clona o repo diretamente (desenvolvimento, contribuição):

```bash
bash .claude/bootstrap.sh
```

Idempotente. Liga git hooks, instala deps via `pip install -e .` e dispara
o build inicial do graph + inventory (one-shot, ~30s-2min). Sem isso, a
primeira invocação de `forge graph` triggera lazy rebuild silenciosamente
na mesma janela de tempo.

Para CI/scripts determinísticos, use `forge graph --no-auto-build <query>`
para desabilitar o auto-rebuild — útil quando o graph deve ser controlado
explicitamente.

## Where it lives

```
~/.local/share/feature-forge/           canonical install (XDG default; $XDG_DATA_HOME)
  bin/forge                             Bash dispatcher
  scripts/install.sh                    curl one-liner installer (bash 3.2)
  engine/                               Python engine (~33.500 LOC)
    host/                               host-aware execution — 4 adapters:
                                          claude_code / opencode-fallback / tty / intent_file
    graph/                              parsers (Kotlin/Swift/TS/Java/XML/ObjC) + builder +
                                        gradle_modules + gradle_deps +
                                        _body_text + duplicates + reuse_apply +
                                        incremental + queries (Q1–Q17)
    memory/                             L1/L2/L3 + distiller (16 proposal kinds)
    cards/  inventory/  ui/  persona/   utils/ (sqlite_io + template_render)
  docs/                                 design + schemas + UX roteiros + lifecycle
  agents/                               agent prompts (10 prompts)
  templates/                            18 canonical templates (16 + bugfix + refactor)
  cards/                                29 canonical cards (+ overlay em consumidor)
  presets/kmp-mobile/                   canonical preset v1
  validators/                           22 validators + 3 helpers (inclui check_cyclomatic_complexity + check_secrets + check_unfilled_placeholders + validate_extension_feature)
  hooks/                                9 hooks + reuse incremental script
  tests/                                rapid 1611 / integration 168 / e2e 30 (unit + integration + e2e)

[per project install via `forge init`]
{project}/.claude/forge/                sub-namespace forge (v1.3+)
  forge-config.yaml                     installed config (era .claude/workflow-config.yaml em v1.2)
  state/                                intent protocol state files
  cards/local/                          card local overlay
  hooks/                                forge-managed hooks
{project}/.claude/
  graph.db                              codebase graph (schema v2)
  proposed-evolutions.yaml              reuse + retrospective proposals
  hooks/post-edit-detect-duplications.sh    opt-in incremental detect
```

## Command surface (14 + 2 hidden)

14 comandos user-facing — zero flags — toda parametrização via prompts interativos (Decision 9 + 10 locked).

```
forge init           bootstrap workflow num projeto (greenfield/brownfield)
                     · Step 11.5 escaneia codebase pra reuse opportunities
forge plan           plan feature (waves A-E, subtype-aware)
                     · subtypes: product / refactor / bugfix / spike / chore
                     · `forge plan refactor-{slug}` lê L1 status e pula Wave A
forge implement      execute task-by-task
forge verify         validator cascade (22 validators no diretório; 3 built-in + N contribuídos por cards ativos)
                     · check_no_behavior_change gate quando subtype=refactor
                     · check_cyclomatic_complexity gate multi-language
                     · check_secrets gate multi-tool (gitleaks per-task / trufflehog cascade)
                     · validate_extension_feature cross-cutting quando feature tem extends-feature setado (Gap 9)
forge status         read-only board
forge doctor         health check (17 categorias)
                     · inclui reuse-intelligence findings agregados
                     · inclui cc-gate-tools (detekt/swiftlint/eslint/radon)
forge reconfigure    single mutation entrypoint
                     · graph rebuild re-queue reuse proposals automaticamente
forge graph          query graph (Q1-Q17, "r" combined view)
                     · Q12-Q17: 6 reuse-intelligence queries
                     · `forge graph --json <query> [args...]` — non-interactive JSON
                       (entrypoint pra IA/automação; aceita aliases/keys/labels);
                       combina com `--no-auto-build` em CI determinístico (v1.3.0+)
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
forge upgrade        atualiza o próprio forge (git pull --ff-only + venv refresh + smoke)
                     · rollback automático em falha de smoke (git reset --hard prev_head)
                     · opera sobre FORGE_HOME; não toca o projeto consumidor
```

Hidden entrypoints (invocados por hooks, nunca tipados pelo usuário):

- `forge ingest --event <type> [payload]` — graph/memory/inventory updater
- `forge graph detect-incremental <file>` — post-edit reuse detection

## Guias do usuário

| Guia | Pra quem | Lê em |
|---|---|---|
| [Primeiros passos](docs/guides/getting-started.md) | Quem nunca usou forge | 10 min |
| [Comandos do dia a dia](docs/guides/daily-workflow.md) | Quem já usa no dia a dia | 15 min |
| [Lifecycle de uma feature](docs/guides/feature-lifecycle.md) | Quem quer entender o fluxo completo | 10 min |
| [O que cada arquivo no .claude/ significa](docs/guides/dot-claude-reference.md) | Quem quer entender o que o forge criou | 5 min |

## Documentação

Start here:

- **`docs/product/00-prd.md`** — PRD consolidado (porta de entrada lente produto; complementa `docs/design/00-vision.md` arquitetural)
- **`docs/design/08-session-handoff.md`** — TL;DR completo + estado por fase + limites v1
- `docs/design/00-vision.md` — arquitetura (6 layers, capability cards)
- `docs/design/01-decisions.md` — 27 decisões locked
- `docs/design/06-command-surface.md` — 14 comandos canônicos + 2 hidden
- `docs/design/07-discipline.md` — 10 disciplinas universais (3-caminhos, fail-fast, pause/abort, vocabulário, fingerprint)
- `docs/design/04-pending.md` — gaps abertos + itens deferred por versão
- `docs/schemas/graph.md` — schema v2 com reuse_findings + module_deps + Q1-Q17 + `symbols.body` column (v1.3+) + `forge graph --json` non-interactive (v1.3+)
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
