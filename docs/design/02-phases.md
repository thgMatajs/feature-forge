# Implementation phases

> **Estado:** Fases 1-5 entregues em 2026-05-29 ([CHANGELOG](../../CHANGELOG.md)).
> ~370 arquivos, ~28K LOC, 266 tests passing.
> Phase 6 (LLM hookup + tree-sitter + real MCP) listada no fim como roadmap.

Dependencies dictate the order. Each phase unblocks the next.

## Dependency diagram

```
                  ┌──────────────────────────────┐
                  │ workflow-config.yaml schema  │  ◀── foundation
                  └──────────────┬───────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
   ┌────────────────┐  ┌──────────────────┐  ┌────────────────┐
   │ Card schema    │  │ Inventory schemas│  │ Memory schemas │
   └────────┬───────┘  └─────────┬────────┘  └────────┬───────┘
            │                    │                    │
            │            ┌───────┴────────┐           │
            │            ▼                │           │
            │   ┌──────────────────┐      │           │
            │   │ Graph DB schema  │      │           │
            │   └─────────┬────────┘      │           │
            │             │               │           │
            └─────────────┼───────────────┼───────────┘
                          ▼
                ┌──────────────────────┐
                │ Esqueleto de pastas  │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │ forge plan roteiro   │
                │ end-to-end           │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │ Sub-agent prompts    │
                │ (8 agentes)          │
                └──────────┬───────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
   ┌──────────────┐  ┌──────────┐  ┌───────────────┐
   │ Templates    │  │ Cards    │  │ Validators    │
   └──────┬───────┘  └────┬─────┘  └───────┬───────┘
          │               │                │
          └───────────────┼────────────────┘
                          ▼
                ┌──────────────────────┐
                │ Python implementation│
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │ Bash forge dispatcher│
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │ Hooks + E2E tests    │
                └──────────────────────┘
```

## The 5 phases

### Phase 1 — Espinha dorsal (schemas + estrutura) ✅ done

Foundation. Nothing reads, writes, or composes until form is defined.

1. workflow-config.yaml schema ✅
2. Card schema ✅
3. Inventory schemas (DS, i18n, conventions) ✅
4. Memory schemas (L1, L2, L3) ✅
5. Graph DB schema (SQLite tables) ✅
6. Esqueleto de pastas + arquivos vazios ✅

→ **Output:** full filesystem layout exists in design before any Python.

### Phase 2 — Cérebros (agents) ✅ done

Agents need schemas first, otherwise their prompts are vague.

7. forge plan roteiro end-to-end ✅
8. forge implement roteiro end-to-end ✅
9. forge verify roteiro ✅
10. forge doctor roteiro ✅
11. Sub-agent prompts: ✅
    - feature-intake-agent ✅
    - feature-prd-agent ✅
    - screen-analysis-agent ✅
    - contract-planner-agent ✅
    - tech-spec-agent ✅
    - task-contract-writer ✅
    - readiness-reviewer ✅
    - retrospective-agent ✅
    - memory-distiller ✅

→ **Output:** system thinks completely on paper.

These 9 sub-agents can be designed in parallel (independent once
planning-conductor exists, which it does).

### Phase 3 — Conteúdo (templates + cards canônicos) ✅ done

12. Templates × 16 (adapt existing where possible) ✅
13. Cards canônicos (entregues iniciais + refactor 3.5): ✅
    - kotlin-language · kmp-shared · compose-screens · swiftui-screens ✅
    - koin-annotations · skie-bridge · nav3 · swiftui-navigation ✅
    - firebase-auth · firebase-storage · crashlytics ✅
    - firestore-persistence · firestore-realtime · firestore-security-rules ✅ (split do antigo `firebase-firestore` na Fase 3.5)
    - ktor-client · rest-api-contract · kotlinx-serialization-json ✅ (REST stack — Fase 3.5)
    - room-database · datastore-prefs · auth-jwt-bearer ✅ (REST stack — Fase 3.5)

→ **Output:** complete system as static files.

Cards and templates can be done in parallel.

### Phase 3.5 — Refactor backend-agnostic ✅ done

Não estava prevista mas executada entre 3 e 4. Removeu viés Firebase do preset
canônico, splittou `firebase-firestore` monolítico em 3, adicionou 6 cards REST,
formalizou catálogo de capability labels (40 labels v1) e arquivou preset
`kmp-mobile-firebase` em favor de `kmp-mobile` + 4 backend-candidates.

→ **Output:** backend-agnostic real. Ver `CHANGELOG.md § Fase 3.5`.

### Phase 4 — Músculos (código) ✅ done

14. Python: `engine/init.py` (auto-detect, questionnaire, inventory, graph builders) ✅
15. Python: `engine/plan.py` (planning-conductor invoker) ✅
16. Python: `engine/implement.py` (task executor) ✅
17. Python utilities (`graph/`, `memory/`, `cards/`, `mcp/jira.py`, `vision/`) ✅
18. Bash dispatcher (`forge`) — ~50 lines ✅
19. 13 commands handlers (init, plan, implement, verify, status, doctor, reconfigure, evolve, undo, graph_cli, memory_cli, raw, ingest) ✅

→ **Output:** 57 arquivos Python · ~12.880 LOC.

### Phase 5 — Pele e validação ✅ done

20. Hooks (5 Claude Code + 3 git + 1 GitHub Actions) ✅
21. 13 validators Python (+2 helpers) com 3-caminhos discipline ✅
22. Suite pytest: 266 tests passing (unit + integration + 13 commands smoke + validators) ✅

→ **Output:** install hooks automatically em `forge init`; CI bloqueia regressões.

### Phase 6 — Roadmap (não entregue em v1)

Não obrigatória pra v1 daily-driver, mas necessária pra "full automation":

- **LLM hookup real** — `plan.py`/`implement.py` hoje narram fluxo + renderizam templates; integração Anthropic API + dispatch de sub-agents reais é Phase 6.
- **`forge implement` Apply Mode automatizado** — hoje stub manual; precisa de patch writer + diff applier + rollback safety.
- **Tree-sitter / AST parsers** — substituir regex-based parsers em `inventory/` e `graph/` por AST real (cobertura cross-language).
- **MCP integrations reais** — `mcp/jira.py` e `mcp/context7.py` hoje são stubs; conectar transports MCP de verdade.
- **9 fall-through kinds em `apply_proposal_to_l2`** — atualmente `raise NotImplementedError` documentado; precisa de handlers reais.
- **`forge init` Cena 7 (Jira/ticketing prompts)** — hoje requer `forge reconfigure` pós-init.

Ver `docs/design/08-session-handoff.md § Conhecidos limites v1` pra lista canônica.

## Parallelism opportunities

| Can run in parallel | Why |
|---|---|
| Sub-agent prompts (9) between each other | Independent once conductor exists |
| Canonical cards (12) between each other | Each card is an isolated unit |
| Templates × Cards | Different content surfaces |
| Python engine modules | Isolated modules |

## What NOT to parallelize

- Schemas before any other thing (rewrites cascade)
- Cards before card schema (forms drift)
- Code before UX roteiros (code serves itself, not user)

## Effort estimate (rough — histórico)

| Phase | Artifacts | Effort | Output |
|---|---|---|---|
| 1 | 6 schemas + esqueleto | 2-3 sessions | "Sei onde tudo vive" ✅ |
| 2 | 4 roteiros + 9 prompts | 3-4 sessions | "Sei como o sistema pensa" ✅ |
| 3 | 16 templates + 12 cards | 4-5 sessions | "Conteúdo completo no papel" ✅ |
| 3.5 | refactor backend-agnostic | 1 session | "Sem viés Firebase" ✅ |
| 4 | ~15 Python files + dispatcher | 5-7 sessions | "Funciona" ✅ |
| 5 | 9 hooks + validators + tests | 2-3 sessions | "Funciona com confiança" ✅ |

Total entregue: **5 fases + 1 refactor + 2 cleanups formais** em ~28K LOC.
