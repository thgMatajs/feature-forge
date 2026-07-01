# Vision — feature-forge

> **Status implementação:** v1 completa (2026-05-29) — todos os 6 layers entregues em código.
> Ver [`CHANGELOG.md`](../../CHANGELOG.md) e [`08-session-handoff.md`](08-session-handoff.md) pra estado factual por fase.

feature-forge is not a workflow skill. It is an **operating system for mobile
feature development** — a system that absorbs patterns, accumulates knowledge,
and reduces ambiguity to zero across feature lifecycles.

## The 6 layers

```
┌────────────────────────────────────────────────────────────────────┐
│ Layer 0: Engine Core (universal, agnostic)                         │
│  State machine, file-driven, plan→apply→verify→commit              │
├────────────────────────────────────────────────────────────────────┤
│ Layer 1: Knowledge Substrate                                       │
│  mem acervo curado (.claude/bin/mem — JSONL + SQLite)              │
│  codebase-graph.db (live)                                          │
│  inventory/{design-system, i18n, conventions}.yaml                 │
├────────────────────────────────────────────────────────────────────┤
│ Layer 2: External Integrations (MCP — DEFERIDO pós-piloto)         │
│  ticketing MCP (Jira/Linear/etc)                                   │
│  docs MCP (Context7)                                               │
│  vision (screenshot analysis)                                      │
│  find-skills (capability install)                                  │
├────────────────────────────────────────────────────────────────────┤
│ Layer 3: Capability Cards                                          │
│  templates, validators, agent-prompts per card                     │
│  dependency/conflict resolver                                      │
├────────────────────────────────────────────────────────────────────┤
│ Layer 4: Orchestration                                             │
│  planning-conductor (super-agent)                                  │
│  execution-conductor (implement super-agent)                       │
│  subagent dispatcher                                               │
├────────────────────────────────────────────────────────────────────┤
│ Layer 5: Self-Evolution                                            │
│  retrospective after each feature                                  │
│  proposed-evolutions.yaml                                          │
│  approval flow                                                     │
├────────────────────────────────────────────────────────────────────┤
│ Layer 6: UX                                                        │
│  init · plan · implement · verify · doctor · reconfigure · ...     │
│  evolve (review/apply proposals)                                   │
└────────────────────────────────────────────────────────────────────┘
```

### North star: AI-first lifecycle

O objetivo é um ciclo de feature **dirigível por host IA sem passos manuais
fora do forge**. O engine emite intents (exit 2 + marker `<FORGE_INTENT/>`);
o host fecha o loop via `AskUserQuestion` (Claude Code) ou intent-file
(opencode/CI). O usuário avalia decisões de produto — nunca roda CLIs
manualmente dentro de um ciclo em progresso.

### Capacidade de verificação de execução (Decisão 33, Nível 1)

`forge verify` agora roda gates externos junto da cascade de validators
(Layer 0). No Nível 1: **ktlint** (`./gradlew ktlintCheck`, leitura pura,
só em stacks android/kmp) e **build-only** (`./gradlew assembleDebug` para
android/kmp, `xcodebuild build` para ios), conforme `platforms.active`. Web
sem build-only no Nível 1. Violação é informativa por default; opt-in
`fail-on-violation: true` por gate. Tool ausente → `skipped`; timeout →
`degraded`. Fronteira de execução em `engine/external_exec.py` (Decisão 33
— camada separada do sandbox de validators da Decisão 30). Os Níveis 2
(smoke) e 3 (screenshot) têm spec escrita e impl pendente — ver
`docs/design/04-pending.md §Follow-on`.

## Capability cards (the composition unit)

Instead of pre-baked presets, feature-forge composes from atomic capability
cards. A preset is an alias for a card combination — not a fixed structure.

Each card declares:

```yaml
name: <card-name>
provides: [<capability-list>]
conflicts-with: [<incompatible-card-list>]
requires: [<dependency-card-list>]
contributes:
  templates:        # files this card adds to feature packages
  validators:       # checks this card enforces
  agent-prompts:    # instructions this card injects into sub-agents
```

The engine merges contributions of active cards declaratively. Conflicts
(e.g., `hilt-di` + `koin-di`) are detected and blocked at init time.

This gives:
- **Portability** — works in any combination, including ones nobody anticipated
- **Composability** — add/remove/swap cards atomically
- **Maintainability** — each card is small and isolated

## Self-evolution

After each completed feature, feature-forge runs a retrospective:
- Detect patterns repeated across features
- Suggest template patches, agent prompt additions, new cards
- Queue suggestions in `proposed-evolutions.yaml`
- User reviews via `forge evolve`

The engine never modifies itself without approval. Suggests, never decides.

## Zero-ambiguity elicitation

Every decision the engine asks about has:
- Pre-computed decision tree
- Memory-driven default detection
- Ambiguity detectors (vague terms trigger drill-down)
- Audit trace (every decision logged with rationale)

Goal: by feature N, the questionnaire is shorter than feature 1, because
memory has accumulated patterns.

## Key principles

1. **Patterns ≠ Dependencies.** Absorb essences from other skills; never
   require them at runtime.
2. **Files > Memory.** Everything is file-driven, resumable, inspectable.
3. **The user decides.** Engine never decides product or architecture.
4. **Mentor calmo voice.** Warm in exploration, firm at gates.
5. **Project-native vocabulary.** Engine reads CLAUDE.md and rules/, uses
   the project's words, not generic ones.
6. **Reversibility.** Every action is undo-able. No hidden state.

## What feature-forge is NOT

- Not a product manager. Doesn't decide WHAT the feature does.
- Not an architect. Doesn't decide WHICH tech stack to use.
- Not a code reviewer. Doesn't decide WHETHER code is good.
- Not a project manager. Doesn't estimate, schedule, or coordinate.

When asked any of these, redirects with adjacent value it CAN provide.
