# Session Handoff

> Use este doc se você está **retomando feature-forge numa sessão nova** ou se
> é um agente cold-start sem contexto da conversa de design original.

**Última atualização:** 2026-06-04 (plan-auditor — auditoria pós writing-plans)
**Estado:** Plan auditor entregue (`.claude/rules/plan-auditor.md` + 7
touch points de integração). Em paralelo aos branches v1.2.x cumulativos.
Próximo: smoke real do auditor contra plano futuro pra validar mapping
de severity. Suite total inalterada (sem touch em `engine/` ou
`validators/`).

---
*Histórico v1.2.0 (Gap 5 + power-review PR #2 R1 + schema_version fix) preservado em git log — `git log --oneline main..HEAD` na branch de release v1.2.0 e CHANGELOG.md §[1.2.0] mantêm o detalhe.*

---

## TL;DR pra nova sessão

Cole este prompt no início da sessão nova:

```
Estou retomando feature-forge em ~/Documents/feature-forge/.
Leia, nesta ordem:
  1. docs/design/08-session-handoff.md (este doc)
  2. docs/design/01-decisions.md
  3. docs/design/06-command-surface.md
  4. docs/design/07-discipline.md
  5. docs/design/04-pending.md
Depois siga as instruções. Estou na Fase {N}.
```

---

## Estado atual (anchors)

```
~379 arquivos · ~50,700 linhas · 27 decisões locked + 7 direcionais (Fase 3.5)
v1.1.0 release: 508 tests passing (unit + integration, PR #1 R2 baseline) · 17 graph queries · 16 proposal kinds
```

| Categoria | Status |
|---|---|
| Phase 1 — schemas + filesystem | ✅ 100% |
| Phase 2 — UX roteiros + agent prompts | ✅ 100% |
| Phase 3 — templates + cards canônicos + preset | ✅ 100% |
| Phase 3.5 — refactor backend-agnostic + REST coverage | ✅ 100% |
| Phase 4 Wave 1 — foundation (bin + cli + utils + ui + persona) | ✅ 100% (16 arquivos, ~1440 LOC) |
| Phase 4 Wave 2 — state + integration (cards + memory + graph + inventory + mcp + vision) | ✅ 100% (28 arquivos, ~5400 LOC) |
| Phase 4 Wave 3 — commands handlers (13 módulos) | ✅ 100% (13 arquivos, ~6040 LOC). **Nota:** `forge implement` é stub manual em v1 — Apply Mode automatizado fica pra v2/Phase 6. |
| **Phase 4 total** | ✅ **57 arquivos, ~12880 LOC** |
| Phase 5 Wave A — hooks (8 .sh + 1 CI yml) | ✅ ~277 LOC |
| Phase 5 Wave B — validators Python (13 + 2 helpers) | ✅ 2622 LOC |
| Phase 5 Wave C — pytest suite (unit + integration + e2e) | ✅ ~3460 LOC, 258 passing |
| Phase 5 Cleanup — hooks install no init + 3 handlers ingest + validator tests | ✅ +838 LOC |
| **Phase 5 total** | ✅ **72 arquivos, ~6600 LOC, 258 tests passing** |
| **🎉 feature-forge v1.0 completa** | ✅ **~370 arquivos, ~28K LOC, 5 fases + cleanup** (2026-05-29) |
| v1.1 — Gap 1 (bugfix subtype) | ✅ shipped 2026-05-30 — `_VALID_SUBTYPES + ['bugfix']`, ticket-pattern detection, Wave B conditional, template intake-bugfix |
| v1.1 — Gap 2 (refactor subtype + non-product track) | ✅ shipped 2026-05-30 — `_VALID_SUBTYPES + ['refactor', 'spike', 'chore']` (refactor only completo), `non-product/{slug}/`, `check_no_behavior_change` validator, template intake-refactor |
| v1.1 — Gap 8 (blocked-on-external state) | ✅ shipped 2026-05-30 — L1 status enum, manual unblock via reconfigure |
| v1.1 — Gap 18 (reuse intelligence expansion) | ✅ shipped 2026-06-01 — 6 detection categories, schema v2, parser overhaul, gradle modules+deps, init Step 11.5+11.6, evolve dispatch, doctor check, incremental hook, forge plan integration. **+12.360 LOC, 55 arquivos, 20 unit tests novos.** |
| **🎉 feature-forge v1.1.0 completa** | ✅ **~379 arquivos, ~50.7K LOC, 458 tests passing (rapid lane)** (2026-06-01) |
| v1.1.0 — PR #1 bloqueadores resolvidos | ✅ shipped 2026-06-01 — 14 commits cobrindo C1–C4 (phase lock atomic O_EXCL, implement try/finally, `_reset_domain_tables` atomic, version bump 1.1.0) + A1/A2/A5/A6/A9/A12 (Swift `"""` brace counter, Groovy DSL parens, tie-breaker determinístico, root-level `test/` recognition, `forge plan` rc=130 em deferred) + review fixes (CR-01/CR-02/MD-01/HG-01/HG-02/HG-03). **+38 regression tests, total 458 (baseline 367 + 53)**. Detalhe em `CHANGELOG.md`. |

## Conhecidos limites v1.1 (atualizado)

A v1.1 entregue inclui o pipeline completo de planning + verify + memory + graph
+ reuse-intelligence + non-product feature track (refactor/bugfix). Limites
restantes ficam pra v1.2+ ou v2/Phase 6:

**v1.0 herdados (ainda válidos):**

- **`forge implement` não automatiza Apply Mode** — em v1 é um **stub manual**:
  `forge implement` renderiza Plan Mode (contract + allowed_files + gates) e
  emite handoff em texto. A edição dos arquivos é responsabilidade do usuário
  (ou da sessão Claude Code que está rodando o forge). Pre-commit Review
  automatizado, Atomic Commit com mensagem canônica, e detecção out-of-scope
  via hook real chegam em v2.
- **`forge init` Cena 7 (Jira/ticketing auth) não é prompted** — a configuração
  de provider de ticketing (Jira, Linear, GitHub Issues) sai com `provider=none`
  no `workflow-config.yaml` por default. Para configurar pós-init, use
  `forge reconfigure → ticketing`.
- **3 kinds de `apply_proposal_to_l2` ainda em fall-through** — `engine/memory/distiller.py`
  resolveu 6 kinds reuse-intelligence em v1.1, mas `tooling-update`,
  `card-version-bump` e `template-update` (entre outros retrospective kinds)
  continuam raise NotImplementedError até emergirem de uso real.
- **LLM/sub-agent hookup real** — `plan.py`/`implement.py` narram fluxo +
  renderam templates. Integração real com Anthropic API dentro do `forge`
  requer hooks + Claude integration (já documentado em §Out-of-scope abaixo).

**v1.1 novos (decisões deliberadas, não bugs):**

- **`kmp-migration-candidate` confidence é shallow** — token Jaccard sintático,
  não AST semântico. Pode flagar Swift function com nome igual a Kotlin shared
  mas semântica diferente. Mitigação: confidence 0.50–0.75 (manual review
  obrigatório), apply NUNCA auto-runs, rejection veto persiste.
- **Incremental detection hook wiring é manual** — `forge init` Step 11.6
  escreve `.claude/hooks/post-edit-detect-duplications.sh`, mas a referência
  em `.claude/settings.local.json` é **opt-in por design** — não modificamos
  settings.local.json automaticamente pra não surpreender o usuário.
- **Gradle dependency parsing** cobre `implementation(project(...))` e
  variantes comuns (`api`, `compileOnly`, `testImplementation`, etc.).
  `includeBuild`, DSL Kotlin avançado, ou versionCatalogs podem precisar
  extensão futura. Fallback: heurística estática (`:shared:core` como
  ancestor padrão pra cross-shared dups).
- **Spike + chore subtypes stubbed** — `_VALID_SUBTYPES` aceita `spike` e
  `chore`, mas só `refactor` tem flow completo (Gap 2 ship). Spike + chore
  caem no fluxo product por default; será implementado quando emergir.
- **MCP polling para external-dep resolution (Gap 8)** stubbed — v1.1 ship
  manual unblock via `forge reconfigure → external-deps`. Auto-polling via
  Jira/Linear webhook fica pra v1.2+.

**Rules system v1 (2026-06-01) — limites reconhecidos:**

- Per-tool-use Mandamento 0 detection é manual (depende de orchestrator obedecer regra textual). Hook bloqueante de main-vs-subagent depende de Claude Code expor distinção no hook protocol — anotado em `04-pending.md`.
- `forge audit-rules` (comando futuro pra verificar conformidade em git log) ainda não existe — anotado em `04-pending.md` pra v1.2+.
- Bloqueios opt-in (test-count regression, validator-cascade fail) estão documentados em `.claude/rules/doc-sync.md` mas comentados no script; ativar quando emergir necessidade real.

**Pré-existente em v1.1.0 (não bloqueia ship, fix agendado pra v1.1.1):**

- **`tests/integration/test_graph_build_meobonsai.py::test_build_full_creates_meta_schema_version`** assertava `meta.schema_version == "1"`, mas `engine/utils/sqlite_io.py:20` declara `SCHEMA_VERSION = "2"` desde o bump da reuse-intelligence schema (v1.1.0 Gap 18). Falha **não bloqueia** rapid lane (458 passing), `forge verify`, nem o ship v1.1.0 — só atinge a integration lane. Surfaced 2026-06-01 durante verification final do PR #1. Fix pequeno: ler `sqlite_io.SCHEMA_VERSION` em vez de hardcoded `"1"`. Gap completo em `docs/design/04-pending.md § Gaps pós-rules-system`.

**Round 2 surfaced (2026-06-02) — não bloqueiam merge do PR #1, agendados pra v1.1.1+:**

- **plan.py `phase_lock_held` CM migration deferred** — R2.7 (MD-03) migrou só `engine/implement.py` para `with phase_lock_held(...)`. `engine/plan.py` tem múltiplos deferred paths via `_persist_deferred` que precisam de brainstorm focado antes de migrar; happy path em `plan.py` (linha ~1108, `final_state`) seta `phase_lock=None` via `write_l1_status` mas **NÃO chama `release_phase_lock`**, deixando sentinel `.phase-lock` órfão no disco. Recovery manual: `rm .planning/<slug>/.phase-lock`. Fix proposto: chamar `release_phase_lock` no happy path antes da migração CM. Target v1.1.1.
- **A13 `IN`-clause >999 findings ceiling** (review IN-01) — `list_reuse_findings` agora usa `WHERE finding_id IN ({placeholders})` que falha com SQLite default `SQLITE_MAX_VARIABLE_NUMBER=999` se `findings > 999`. Chunking em batches de 500 quando relevante. Não atinge nenhum projeto conhecido hoje; target v1.1.2+.
- **`forge undo` coverage para reconfigure-external-deps** (review WR-01) — `_undo_reconfigure` em `engine/undo.py` não enumera per-task `.bak` files criados pelo loop de external-deps em `engine/reconfigure.py:754`. Recovery atualmente manual via `.bak` direto. Target v1.1.1.

**Gap 5 (card local overlay) surfaced (2026-06-02) — não bloqueia merge, target v1.2:**

- **Card local re-prompt** — fluxo `_card_local_add` em colisão de nome
  oferece 3-caminhos (rename / abort / listar) mas o "rename" não reabre
  o prompt do nome — encerra a operação. Gap pra v1.2; documentado em
  `docs/design/04-pending.md`.

## Fase 4 — completa (resumo)

```
57 arquivos · ~12.880 LOC · 13 commands handlers + hidden ingest
Smoke-tests verdes: ./bin/forge --version, all handlers resolve via cli._resolve
```

Wave 3 entregue (13 arquivos):
- `engine/init.py` (953 LOC) — greenfield/brownfield install, backend-candidates, snapshot, merge, inventory, graph build, workflow-config writer
- `engine/plan.py` (604 LOC) — planning-conductor waves A-E com auto-resume + phase_lock
- `engine/implement.py` (625 LOC) — execution-conductor task-by-task, topo-sort, plan mode + apply stub
- `engine/verify.py` (432 LOC) — validator cascade fail-fast com 3-caminhos
- `engine/doctor.py` (593 LOC) — 11 health checks (full) / 3 (quick), .bak overdue, MCP probes
- `engine/status.py` (285 LOC) — read-only board 6 sections
- `engine/reconfigure.py` (~600 LOC) — single mutation entrypoint, 10 submenus, history.jsonl
- `engine/ingest.py` (~210 LOC) — hidden hook entry, key-value parse, exit 0 always
- `engine/raw.py` (~210 LOC) — escape hatch (verify-card, edit-config, rebuild-templates, forge-debug, migrator-N-to-M stub)
- `engine/evolve.py` (455 LOC) — single-by-single apply, L2 overflow pause, fingerprint veto
- `engine/undo.py` (497 LOC) — 7 targets menu, last default
- `engine/graph_cli.py` (203 LOC) — Q1-Q10 read-only menu
- `engine/memory_cli.py` (373 LOC) — inspect L1/L2/L3 + search + forget + distill + export

### Cleanup final Fase 4 (29 FOLLOWUPs fechados em 2026-05-29)

Todos os FOLLOWUPs das Waves 1-3 foram fechados em uma rodada final de 4 sub-agents paralelos.

**Wave 3 commands (10 itens):**
1. ✅ `init.py` cria `.claude/forge-version-lock.yaml` (Step 12.5)
2. ✅ `init.py` cria `.claude/.gitignore` auto-managed (Step 12.6)
3. ✅ `init.py` append primeira entry em `workflow-config-history.jsonl` (schema HIST-001..012)
4. ✅ `doctor.py` escreve `metadata.last-doctor-run` + `last-doctor-status` (única mutação documentada)
5. ✅ `verify.py` atualiza L1 status.json + grava `verify-log.jsonl` (schema MEM-L1-VL-001..005)
6. ✅ `verify.py` expõe `run_scope(scope_type, scope_id, project_root, *, interactive=False)` API
7. ✅ `ingest.py` `pre-commit` event invoca `verify.run_scope` real
8. ✅ `raw.py rebuild-templates` re-renderiza templates reais com merger
9. ✅ `undo.py` schema canônico `commit-sha` (40-hex) + fallback graceful pra legacy
10. ✅ `memory_cli.distill` handler real com single-by-single apply

**Wave 2a cards (5 itens):**
11. ✅ Parser real do `capability-labels.md` (40 labels carregadas dinamicamente, 16 singular, 3 latent) com cache lazy
12. ✅ CARD-011/012 cross-check com frontmatter dos agents — detectou e corrigiu 3 bugs reais (auth-jwt-bearer, ktor-client, swiftui-navigation)
13. ✅ Categorias canônicas reconciliadas (`card.md` ↔ cards reais)
14. ✅ `firebase-auth/card.yaml` confidence sum 2.1 → 1.5 (CARD-016 compliant)
15. ✅ `merger.render_merged_template` suporta setext headings (`===` / `---`)

**Wave 2b memory (4 itens):**
16. ✅ Filelock cross-platform Windows (`msvcrt.locking` LK_LOCK/LK_UNLCK)
17. ✅ `record_rejection` schema canônico completo conforme `rejected-evolutions.md`
18. ✅ `append_verify_log` com validação MEM-L1-VL-001..005
19. ✅ L2 buckets auxiliares tipados (`naming-extras`, `contradictions-resolved`, `promotion-candidates`)

**Wave 2c graph (4 itens):**
20. ✅ `.gitignore` parser real (wildcards, negação, nested) em `discover_source_files`
21. ✅ Populate 6 tabelas faltantes: `di_graph`, `ds_usage`, `i18n_usage`, `screens`, `routes`, `tests`
22. ✅ Concurrency lock com `busy_timeout = 5s` + `GraphError` em deadlock
23. ✅ `to_file_id` resolution em `imports` (ALTER TABLE + post-pass; 39% resolved no MeoBonsai)

**Wave 2d inventory (5 itens):**
24. ✅ JUnit5 detection (`org.junit.jupiter` / `useJUnitPlatform`)
25. ✅ `tailwind.config.{js,ts}` parser regex (colors, spacing, borderRadius, fontFamily)
26. ✅ Component level fallback heurística (LOC + imports → atom/molecule/organism)
27. ✅ AndroidManifest.xml parser (package, label, main_activity, permissions)
28. ✅ `features-analyzed` counter real (union de paths convencionais)

**Wave 2e mcp/vision (1 item):**
29. ✅ `engine/mcp/types.py` — dataclass `Ticket`, `TicketComment`, `normalize_status` cross-provider

### Out-of-scope (decisões arquiteturais, não FOLLOWUPs)

Itens explicitamente fora de Fase 4 (esperados pra Fase 5/6 ou v1.1+):

- **LLM/sub-agent hookup real** — `plan.py`/`implement.py` v1 narram fluxo + renderam templates. Integração real com sub-agents Anthropic dentro do `forge` requer hooks + Claude API integration → Phase 5/6 escopo
- **Tree-sitter / AST parsing real** — regex parsers v1 por design (decisão de simplicidade); upgrade só se false positives críticos aparecerem em campo
- **MCP real connections** (Jira/Linear/GitHub/Context7 com credentials reais) — Phase 5 escopo; tipos `Ticket`/`TicketComment` prontos pra consumo
- **iOS pbxproj proper parser** — regex pragmático suficiente; tratar como bug quando aparecer
- **Marketplace de cards user-contributed** — v1 só canonical cards; v2+ escopo

Detalhamento granular em `docs/design/04-pending.md`.

---

## Ordem canônica de leitura (cold-start mandatory)

1. **README.md** — overview e índice
2. **THIS handoff** — você está aqui
3. **docs/design/01-decisions.md** — 27 decisões locked (NÃO REVISAR sem explícito pedido do usuário)
4. **docs/design/06-command-surface.md** — 12 comandos canônicos, zero flags
5. **docs/design/07-discipline.md** — 7 disciplines universais
6. **docs/design/00-vision.md** — filosofia (6 layers, capability cards)
7. **agents/planning-conductor.md** — orchestrator template
8. **docs/design/04-pending.md** — o que falta fazer

Para trabalhar em um schema/agent específico, leia também o file correspondente em `docs/schemas/` ou `agents/`.

---

## Persona e voz (carrega isso antes de qualquer ação)

- **mentor calmo**: warm em exploração, firme em gates, didático, nunca apressado
- **100% conversacional, NUNCA flags** — toda parametrização via menu interativo
- **3-caminhos em todo gate violation** — sempre 3 opções, nunca 2, nunca 4
- **Never invent** — se não há fonte (ticket, screenshot, memory, card default, codebase), marca `needs-elicitation`
- **PT-BR primário** — espelhar idioma do usuário quando ele usa outro

---

## Contexto crítico que NÃO está nos docs

Coisas decididas em auto-mode durante a sessão de design (já refletidas nos docs, mas que poderiam parecer revisáveis):

| Decisão | Por quê não revisar |
|---|---|
| 12 comandos LOCKED | Decision 9. Adicionar um 13º quebra tudo. Roteie por entrypoints existentes via menu. |
| `forge ingest` = hidden machine-only | Chamado só por hooks. Não conta nos 12. Não é typed pelo usuário. |
| Card management = `forge reconfigure` interactive | Não existe `forge card add/remove/upgrade`. Tudo via menu. |
| Migrations = `forge raw migrator-N-to-M` | `raw` é o escape hatch oficial. |
| L2 distill = automático OU menu de `forge memory` | Não existe `forge memory distill` standalone. |
| Auto-resume em `forge plan {slug}` / `forge implement {slug}` | Sem flag `--resume`. Detecta state e segue. |
| Sub-agents usam `model: sonnet` | Só planning-conductor usa opus. |
| `phase_lock` dual: agent-scoped (intake, prd, etc.) ou task-scoped (TASK-NNNN) | Documentado em memory.md §phase_lock canonical form. |
| Strictness matrix 14/10/5 enumerada | Documentada em workflow-config.md §strictness-matrix. |
| Extension-points formalizados nos frontmatters dos agentes | Não tem doc separado de registry — agente declara seu próprio. |

---

## Padrão de operação do usuário (importante)

| Aspecto | Preferência |
|---|---|
| Comandos curtos | "mete marcha", "continue de onde parou", "vai" — quer ação, não dúvida |
| Auto-mode | Quando ativo, fazer call razoável sem perguntar; redirect explícito vem do usuário |
| Sub-agents em paralelo | Dispatchar múltiplos quando os escopos não conflitam |
| Tipo de sub-agent | `general-purpose` (não usar os especializados a menos que perfeitamente alinhado) |
| Idioma | PT-BR no chat; mix EN+PT em docs OK |
| GitHub user | `thgMatajs` |
| Project home | `~/Documents/feature-forge/` (não `~/Code/`) |
| Outro projeto-alvo | Também KMP Android+iOS (modularizando agora) |
| TaskCreate | Geralmente skip — o usuário não pede tracking detalhado |

---

## Polish TODOs deferidos (não-bloqueantes, podem ser feitos junto com Fase 3)

1. **Bidirectional cross-links em 07-discipline §"Referenced from"** — cada doc alvo (roteiros, schemas, agents) deveria ter backlink → §X de 07-discipline
2. **Worked example multi-feature em retrospective-agent.md** — mostrar mesmo proposal evoluindo em 3 features com fingerprint mudando
3. **ASCII state-transition diagram em 07-discipline §7** — atualmente texto; diagrama clarifica pause vs deferred vs aborted
4. **`forge status`, `forge graph`, `forge memory`, `forge undo`, `forge raw` roteiros** — não escritos individualmente (são mais CLI-utility-style). Decidir: roteiros próprios ou 1 doc consolidado "CLI utility commands"?

---

## Anti-patterns conhecidos (não repetir)

| Anti-pattern | Por quê foi rejeitado |
|---|---|
| Adicionar 13º comando "pra conveniência" | Quebra decision 9. Use menu interativo em entrypoint existente. |
| Adicionar flag "só pra esse caso" | Quebra decision 10. Substitute por prompt interativo. |
| Inventar paths de arquivo | Pull de `inventory/conventions.yaml` + `paths.feature-roots`. |
| Auto-apply em memory L2 | Decision 26: review-and-apply via `forge evolve`. Nunca silencioso. |
| Skip 3-caminhos em gate violations | Universal discipline §1 de 07-discipline. Sempre 3 paths. |
| Sub-agent "decidir" produto/arquitetura | Sub-agents só executam decisões do conductor + user. |
| Stub artifact quando input é thin | Falhar com 3-caminhos é melhor que stub. |
| Drill-down infinito em pergunta vaga | Cap em 2 rounds. Decision 27 + planning-conductor §drill-down. |
| Mudança de preset via `reconfigure` | Decision 06-command-surface.md: preset change exige fresh `forge init` em branch dedicada. |

---

## Fase 3 + 3.5 — concluídas (resumo)

**Entregue Fase 3 (sessão 2026-05-29 manhã):**

```
Templates × 16  →  ~/Documents/feature-forge/templates/   ✅
Cards × 12      →  ~/Documents/feature-forge/cards/{name}/ ✅
Preset (inicial) → presets/kmp-mobile-firebase/           ✅ (depois arquivado em 3.5)
```

**Entregue Fase 3.5 — refactor backend-agnostic (sessão 2026-05-29 tarde):**

Motivação: v1 não pode assumir Firebase como o backend canônico — projetos reais usam REST mais frequentemente. Sem MVP, esta é a versão final.

```
Capability labels catalog → docs/schemas/capability-labels.md ✅ (35 labels, 9 famílias)
Cards Firestore split (3) → firestore-persistence/realtime/security-rules ✅
Cards Firebase patched (3) → firebase-auth (capabilities) + spot-check storage/crashlytics ✅
Cards REST novos (6)    →  ktor-client, rest-api-contract, kotlinx-serialization-json,
                            room-database, datastore-prefs, auth-jwt-bearer ✅
Templates refatorados (3) → data-contract-spec, tech-spec, test-strategy (agnósticos) ✅
Agents patchados (3)    → contract-planner, tech-spec, task-contract-writer ✅
Preset refactor          → kmp-mobile-firebase arquivado; kmp-mobile criado (só stack) ✅
docs/design patches      → 04-pending (Fase 3.5 entry), 05-filesystem-layout (cards/presets),
                            08-handoff (este doc) ✅
```

**7 decisões direcionais da Fase 3.5 (locked):**

| # | Decisão | Onde mora |
|---|---|---|
| D1 | Cobrir REST completo na v1 (não v1.1) | 6 cards REST novos |
| D2 | Refatorar Firebase em cards menores | split de firebase-firestore em 3 |
| D3 | Sem preset híbrido; cards livres em cima de kmp-mobile | preset kmp-mobile-firebase deletado |
| D4 | Split `firebase-firestore` em 3: persistence + realtime + security-rules | cards/ |
| D5 | Persistence local: Room (2.7+ KMP-stable) + DataStore | room-database + datastore-prefs |
| D6 | Preset `kmp-mobile-firebase` arquivado; só `kmp-mobile` base | presets/.archived/ |
| D7 | `realtime-stream` como capability formal | capability-labels.md |

## Fase 3 — fluxo de entrega (resumo histórico)

**Entregue na Fase 3 inicial (substituído/refinado pela Fase 3.5):**

```
Templates × 16  →  ~/Documents/feature-forge/templates/   ✅
Cards × 12      →  ~/Documents/feature-forge/cards/{name}/ ✅ (102 arquivos)
Preset manifest →  ~/Documents/feature-forge/presets/kmp-mobile-firebase/preset.yaml ✅ (arquivado em 3.5)
```

**Estratégia usada:**
- Templates: 3 batches sequenciais (Wave A+B narrativos / Wave B contract YAMLs / Wave C+D+E execution). Overlap de schema base resolvido inline (cross-references entre templates implementadas).
- Cards: 12 sub-agents `general-purpose` em paralelo. Cada um briefed com (a) catálogo canônico de capability labels inline, (b) referência viva ao MeoBonsai, (c) extension-points conforme frontmatters reais dos agents.

**Convenção canônica estabelecida em Fase 3:**
- **snake_case** em todos os YAML/JSON dos templates (`schema_version`, `feature_slug`, `generated_by`, `generated_at`)
- IDs: `SC-{NNN}` (BDD), `TASK-{NNNN}`, `Q-CP-{NN}` (open questions), `BE2E-{NNN}` (backend e2e)
- Cross-references: `screen_id`, `route_key`, `entity_name`, `event_name`, `test_id` conectam artefatos
- Fingerprints sha256 canonical-form per `07-discipline.md §4`

**FOLLOWUPs deferidos (não-bloqueantes p/ Fase 4):**

Lista completa em `04-pending.md § Fase 3 — FOLLOWUPs herdados`. Highlights:

- snake_case vs kebab-case mismatch entre agent prompts e templates — alinhar agent prompts
- `contract-planner-agent` sem extension-points no frontmatter (só tabela em §5) — padronizar
- `screen-analysis-agent` sem extension-points formais — definir
- Capability label catalog inline-only — criar `docs/schemas/capability-labels.md` em v1.1
- Labels úteis fora do v1 (`hilt-di`, `android-xml-views`, `ios-ui-uikit`, `navigation2-android`, `material3`) — decidir v1.1
- `card.md` schema cita extension-point exemplo (`section:Language Conventions`) que não existe no agent real — atualizar exemplo
- `evals.template.json` vs `evals/evals.json` — alinhar convenção de path

---

## Estrutura física do repo

```
~/Documents/feature-forge/
├── README.md
├── INFLUENCES.md
├── .git/                              (inicializado, sem commit ainda)
├── docs/
│   ├── design/      (8 docs: 00-vision, 01-decisions, ..., 08-handoff)
│   ├── schemas/     (8 docs: workflow-config, card, memory, graph, ...)
│   ├── ux/          (7 roteiros: init, plan, implement, ..., evolve)
│   └── lifecycle/   (1 doc: memory-and-graph)
├── agents/          (10 prompts: planning-conductor + 9 sub-agents)
└── presets/
    └── kmp-mobile-firebase/README.md  (placeholder)
```

Criado em Fase 3 + 3.5:
```
├── templates/                          ✅ (16 templates, 3 refatorados em 3.5)
├── cards/                              ✅ (17 cards canônicos ativos + 1 arquivado)
│   ├── kotlin-language/
│   ├── kmp-shared/
│   ├── compose-screens/
│   ├── swiftui-screens/
│   ├── koin-annotations/
│   ├── skie-bridge/
│   ├── nav3/
│   ├── swiftui-navigation/
│   ├── firebase-auth/                  (capabilities atualizadas em 3.5)
│   ├── firestore-persistence/          (NOVO 3.5)
│   ├── firestore-realtime/             (NOVO 3.5)
│   ├── firestore-security-rules/       (NOVO 3.5)
│   ├── firebase-storage/
│   ├── crashlytics/
│   ├── ktor-client/                    (NOVO 3.5)
│   ├── rest-api-contract/              (NOVO 3.5)
│   ├── kotlinx-serialization-json/     (NOVO 3.5)
│   ├── room-database/                  (NOVO 3.5)
│   ├── datastore-prefs/                (NOVO 3.5)
│   ├── auth-jwt-bearer/                (NOVO 3.5)
│   └── .archived/firebase-firestore-monolithic/
├── docs/schemas/capability-labels.md   (NOVO 3.5 — 35 labels v1)
└── presets/
    ├── kmp-mobile/                     (NOVO 3.5 — só stack, backend livre)
    └── .archived/kmp-mobile-firebase-pre-3.5/
```

Pendente criar (Fase 4+):
```
├── bin/forge        (Phase 4 — Bash dispatcher)
├── engine/          (Phase 4 — Python engine)
├── hooks/           (Phase 5 — hook scripts)
├── validators/      (Phase 5 — Python validators)
└── tests/           (Phase 5 — E2E)
```

---

## Como retomar limpo

1. Abra sessão nova
2. Cole o TL;DR prompt do topo deste doc
3. O agent novo lê os 5 docs canônicos (handoff + decisions + command-surface + discipline + pending)
4. Diz onde você quer continuar
5. Auto-mode dispatch dos sub-agents da fase escolhida

---

## Como atualizar este handoff

Toda vez que terminar uma fase ou tomar decisão arquitetural em auto-mode, **atualize este doc**:

- Mover phase de pendente → concluída na tabela de estado
- Adicionar novas decisões em "Contexto crítico que NÃO está nos docs"
- Atualizar Polish TODOs (riscar feitos, adicionar novos)
- Atualizar Anti-patterns se um novo foi tentado e rejeitado
- Anotar nova preferência do usuário se surgir

**Não duplicar conteúdo dos outros docs aqui** — este é um índice + nuances de sessão, não substituto de leitura.

---

## Última coisa: o que NÃO é este projeto

- Não é PRD/product. Não estima tempo. Não decide produto.
- Não é code review final. Detecta violações; veredito final é humano.
- Não é IDE plugin. É CLI-first.
- Não é skill auto-installer pra outros projetos (ainda). Snapshot copy manual via `forge init`.
- Não é hosted service. Tudo local; só MCPs externos (Jira, Context7) quando configurados.
