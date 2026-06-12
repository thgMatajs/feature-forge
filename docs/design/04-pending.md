# Pending design artifacts

What still needs to be drafted, in dependency order. Use this as the
checklist for next sessions.

## Fechado em [Unreleased]

- **Auditoria pós-plano** — gap identificado em 2026-06-04 (não estava
  listado em `04-pending.md` antes, mas surgiu no fluxo: o
  `superpowers:writing-plans` Self-Review é leve demais pra capturar
  load-bearing edits sem justificativa, ausência de "Revisita decisão
  N", doc-sync gaps, reuse-first ignorado, voz quebrada). Resolvido via
  `.claude/rules/plan-auditor.md` + integração — ver CHANGELOG
  `[Unreleased]`. Spec: `docs/superpowers/specs/2026-06-04-plan-auditor-design.md`.

### B1 — `identity.backend-choice` ↔ `backend.provider` desync

**Status:** ✅ FECHADO via Phase B DET-6 (2026-06-11). Removeu o
acoplamento na raiz: `identity.backend-choice` deletado, `backend.provider`
substituído por cell structure. Desync é arquiteturalmente impossível agora.

### B2 — Seção `firebase:` órfã após swap

**Status:** ✅ FECHADO via Phase B DET-6 (2026-06-11). Schema novo não
tem subseção `firebase:` (substituído por `backend.<axis>.<platform>`
cells). Swap = mudança de cells; sem seção legacy órfã possível.

### DET-5 — `retrofit-client` fora do preset kmp-mobile

**Status:** ✅ FECHADO via Phase B DET-6 W4+W6 (2026-06-11). retrofit-client
agora carrega `category: data` (W2) e é referenciado pelo bundle
`rest-with-firebase-telemetry.yaml` como default para
`(data, android)` cell. Bundles substituem o conceito de "preset com
backend-candidates fechados".

### DET-6 — Modelo bundle-first é abstração errada

**Status:** ✅ FECHADO (2026-06-11). Redesign multi-axis backend
implementado integralmente conforme `docs/superpowers/specs/det-6-multi-
axis-backend.md`. AC-2/3/5/6/7/8 cobertos. Commits: rebase em
`origin/main` + W5 composer + W6 bundles + sqldelight card +
crashlytics→firebase-crashlytics rename + W7.1/W7.2/W7.3/W7.4 + este
W8 doc-sync. 29 commits sobre origin/main em `feat/det-6-multi-axis-backend`.

## Open Implementation Details — DET-6 resolution (Phase B closeout, 2026-06-11)

Os 8 itens "Open implementation details" da SPEC `det-6-multi-axis-backend.md`
foram resolvidos como segue:

1. **Bundle YAML path** — *Resolved inline*. Bundles vivem em
   `presets/kmp-mobile/bundles/<bundle-name>.yaml` (arquivo separado).
   Default proposto adotado por paridade com `card.yaml` per card.
2. **Detection composer module location** — *Resolved inline*. Composer
   em módulo separado `engine/detection/composer.py`. Default proposto
   adotado por testability + reuse.
3. **Status enum `deprecated` semantics** — *Resolved inline*. Cell
   `status: deprecated` significa "este card está deprecated NESTE
   projeto" independente de `card.yaml § identity.maturity`. Documentado
   em `docs/schemas/backend-axes.md` § cell shape.
4. **`firestore-realtime` fate** — *Deferred follow-up v1.3+*. Card
   mantém `category: data` (W2). Sub-axis formal "realtime" fica como
   follow-up (ver §"Follow-ups DET-6 v1.3+" abaixo).
5. **`rest-api-contract` + `firestore-security-rules` sub-cards** —
   *Deferred follow-up v1.3+*. Cards mantêm `category: data`. Sub-axes
   "data-contract"/"rules" como follow-ups (ver §abaixo).
6. **Phase A dependency API** — *Resolved*. Phase A entregou
   AskUserQuestion intent protocol via `engine/ui/question.py` +
   `intent_state.py` + `tty_bridge.py`. W7.1/W7.2/W7.3 consomem
   `ask_three_paths`, `ask`, `ask_multi`, `confirm` direto.
7. **`crashlytics` card rename** — *Resolved deviation*. Card renomeado
   pra `firebase-crashlytics` em commit dedicado (paridade firebase-*).
   25 arquivos atualizados.
8. **Platform-applicability source** — *Resolved inline*. Campo
   `identity.platforms: [android, ios, kmp]` adicionado ao card.yaml
   schema (CARD-022 — renumber de CARD-020 devido à colisão com DET-3).
   Composer consome esse campo via caller-supplied normalization
   (W7.1/W7.2 augmentam dict shape passado pro composer).

### Follow-ups DET-6 v1.3+

- **bootstrap.sh assume `.git/hooks/` é dir (worktree edge case)** —
  Descoberto 2026-06-12 durante test cleanup pós-`_SKIP_DIRS` fix.
  Sintoma: `tests/integration/test_claude_rules_system.py::test_bootstrap_is_idempotent`
  falha quando rodada de dentro de `.claude/worktrees/<branch>/` com
  `ln: .git/hooks/pre-commit: Not a directory`. Root cause: em git
  worktree, `.git` é um arquivo pointer com shape
  `gitdir: <real-gitdir>/worktrees/<branch>`, não um diretório.
  `bootstrap.sh` (linhas ~17-19) assume `.git/hooks/` é diretório
  direto. Workaround: rodar bootstrap apenas da main worktree (use
  case normal — bootstrap é setup inicial). Fix futuro (v1.3+):
  detectar se `.git` é file, resolver gitdir pointer e ajustar paths
  target. Refactor não-trivial. Não-bloqueador: afeta apenas test
  rodado de worktree; desenvolvimento normal não toca esse path.
- **Sub-axes formal** — `data` poderia ter sub-axes
  `transport/contract/realtime/rules`. v1.2 mantém flat; revisitar
  quando padrão emergir em projetos reais.
- **9º axis (messaging direta)** — chat/push interactivo não é eixo
  canônico v1.0. Revisitar se demanda surgir.
- **Card composability dentro da mesma cell** — v1.0 não suporta "2
  cards ativos na mesma (axis, platform) cell além de migrating-to".
  Use case: side-by-side multi-tenant Firebase. Revisitar follow-up.
- ~~**`_SKIP_DIRS` worktree bug** — engine walk filtra fixtures sob
  `.claude/worktrees/` causando 1 unit test pré-existente + 4
  integration tests pré-existentes a falharem do worktree (passam da
  main repo root). Fix dedicado pendente — possível via opt-out env
  var ou path normalization no walk.~~ **RESOLVIDO 2026-06-12:** fix em
  `engine/inventory/_walk_cache.py` + `engine/init.py:_glob_any` —
  match contra `path.relative_to(project_root).parts` em vez de
  `path.parts` absoluto. Top-level `.claude/` em project_root continua
  filtrado (caso legítimo); `.claude/` como parent do worktree não
  bloqueia walk. Regression test em
  `tests/unit/test__walk_cache_worktree.py`.
- **W7.2 Phase A multi-intent re-invocation pitfall** — ✅ FECHADO em
  2026-06-12 via consumed-intent log em `engine/ui/intent_state.py`.
  Quando handler emite 2+ intents em sequência, `read_response` agora
  consulta `.claude/state/forge-intent-log.jsonl` antes de tocar o
  response file: intents já consumidos retornam a response cacheada,
  fazendo re-entry idempotente. Schema doc atualizado em
  `docs/schemas/intent-protocol.md §4`. Lifecycle clear do log via
  `clear_intent_log_only` no `engine/cli.py::main()` `finally`,
  preservando pending/response (SPEC §3 forensic). Tests de regressão
  em `tests/unit/test_ui_intent_state.py` (cenários: cache hit, file
  overwrite, unknown-id mismatch, log preservation, log reset, full
  re-entry sequence, malformed lines). W7.x integration tests
  permanecem com monkeypatch — remover seria reescrita significativa
  sem redução de LOC; e2e tests já validam o wiring real.
- **Bundle YAMLs com card references inexistentes** — bundle
  `firebase-full.yaml` aponta pra `firebase-crashlytics` que ESTAVA
  ausente (resolvido via rename), e `sqldelight` que ESTAVA ausente
  (resolvido via criação). Pattern: bundle pode referenciar card a ser
  criado em wave futura. validate_presets.py enforça que refs existem
  no momento do validate.
- **Uniform-detection duplicada: `_summarize_backend_cells` vs
  `_render_axes_table`** — ambas implementam "detect uniform across
  platforms → render compact" em `engine/init.py`, mas shapes de input
  divergem genuinamente: `_render_axes_table` consome
  `composer_result` (Cell/Conflict dataclasses, atributo `.card_id` +
  `.candidates`); `_summarize_backend_cells` consome `cells` dict
  pós-adapter (`{"card": ..., "status": ...}`). Consolidar exige
  callable extractor genérico (~30-40 LOC infra) ou normalizar input
  num shape único. Reviewer W7 L-002 sugere extrair
  `_format_axis_compact(axis_map, get_card_id_fn)`, mas custo do
  paralelo é baixo (duplicação cosmética, não comportamental).
  Revisitar quando 3º callsite emergir ou refactor maior abrir
  oportunidade barata.
- **crashlytics rename — filenames de assets preservam nome antigo
  (v1.3+ cosmético)** — o rename `crashlytics → firebase-crashlytics`
  no commit `661b2d4` foi card-id-only por design. Os filenames internos
  ficaram intocados deliberadamente: `templates/crashlytics-tech-spec.md`,
  `templates/crashlytics-analytics.yaml`, e
  `validators/check_crashlytics_shared_exception.py`. Também o field name
  `crashlytics:` em contracts de analytics. Decisão consciente porque
  filenames são identidade de arquivo (não do card) — rename mecânico
  geraria diff massivo cross-referencing sem ganho funcional. Reviewer
  W7 nota que isso vai gerar 1 finding cosmético em cada futuro reviewer
  até alinharmos. Follow-up: rename cosmético `crashlytics-* →
  firebase-crashlytics-*` em filenames + field name, com migrator pra
  contracts existentes. Não-bloqueador, sem impacto runtime.

### DRIFT-1 — Intent Protocol (Engine intent-only + tty_bridge)

- **Branch:** `feat/drift-1-intent-protocol`
- **SPEC:** `docs/superpowers/specs/drift-1-intent-protocol.md`
- **PLAN:** `docs/superpowers/plans/drift-1-intent-protocol.md`
- **Resumo:** engine deixa de ler stdin diretamente; emite intent via
  state files (`.claude/state/forge-pending.json` /
  `forge-response.json`); `engine/ui/tty_bridge.py` faz fallback TTY
  subprocess loop; `bin/forge` dispatcher detecta contexto via TTY +
  env `CLAUDECODE`. Exit code 2 = paused-for-input; exit 130 =
  UserCancelledError / KeyboardInterrupt; exit 0/1 preservados.
  AC-1..AC-9 verificados em 15 integration + 3 e2e pty tests.
- **21 commits** (range `1b1d289..50203f3`) cobrindo W1 (foundation),
  W2 (chokepoint refactor + 10/10 intent-resume), W3 (tty_bridge),
  W4 (bin/forge dispatcher + hooks audit), W5 (integration + e2e
  tests), W6 (este doc-sync).

### Findings pós DRIFT-1 (a revisitar)

Follow-ups capturados durante Phase A pra reentrar quando dados
justificarem. Cada um tem critério explícito.

- **Race detection via `fcntl.flock`** — `engine/ui/intent_state.py`
  hoje detecta race via timestamp `created-at` (> 10 min = stale,
  varre; ≤ 10 min = erro mentor calmo apontando PID). Lock real via
  `fcntl.flock` foi considerado e deferido. Critério pra reentrar:
  race aparecer em produção (orquestrador OR usuário tropeçando em
  pending recente de outra sessão).
- **`_XxxCheckpoint` promotion pra `engine.utils.checkpoint`** —
  W2-FU-4 já documentado em `## Phase A W2 — Code review follow-ups`
  abaixo. Outcome C lockou per-subcommand dataclass (10 ocorrências);
  promoção a shared só se 3+ subcommands materializarem shape
  idêntico em waves futuras (DRIFT-2+ ou v1.3).
- **`engine.utils.paths.state_dir()` promotion** — `intent_state.py`
  define `_state_dir(project_root)` privado (`.claude/state/`).
  Promote-to-shared quando ≥2 consumidores aparecerem. Hoje é único.
- **`PromptAbortedError` dead-code cleanup em 10 callsite modules** —
  W2-FU-3 já documentado. Cleanup cross-cutting (10 subcommands)
  agendado pra sessão dedicada pós-W6 OU callsite-migration task
  futura. Remover agora arrisca quebrar hosts não-Claude-Code que
  dependiam do legacy raise.
- **W4-FU env var name `CLAUDECODE`** — confirmado empiricamente vs
  Claude Code 2.1.153 em W4-FU (commit `b149678`). Revisitar se
  Claude Code renomear OU expor distinção main-vs-subagent oficial
  no hook protocol (já gap separado em `.claude/rules/doc-sync.md`
  §Per-tool-use Mandamento 0 block).


### Follow-ups pós-master-review PR #11 (2026-06-11)

Findings #1..#28 endereçados em Wave 1+2 (10 commits sobre `e992e01`,
range `ad49c40..626a4f0`). Cinco follow-ups deliberadamente deferidos
ficam aqui — todos têm critério explícito pra reentrar.

- **FU-DRIFT-1-LOCK** (P3) — lock file real via `fcntl.flock` para race
  detection hard. SPEC §9 já mapeia o gap como DEFERIDO. Próximo passo:
  implementar `.claude/state/.forge-pending.lock`. Disparar quando race
  genuíno surgir em produção (concurrency test atual em
  `tests/integration/test_intent_state_concurrency.py` documenta a
  TOCTOU window mas não bloqueia merge — o protocolo é single-writer
  por design hoje).
- **FU-DRIFT-1-DEPRECATE-INTENT-ID-ALIAS** (P2) — remover alias
  deprecated `_stable_intent_id = stable_intent_id` em
  `engine/ui/question.py` na v1.3. Hoje preserva 4 test files
  referenciando o nome antigo (`test_ui_question_intent.py` e
  similares). Critério: bump pra v1.3 + migration dos 4 testes em uma
  task dedicada.
- **FU-DRIFT-1-CHECKPOINT-CONSOLIDATE** (P3) — shim de 1-linha por
  módulo nos 10 command handlers (init, plan, implement, verify,
  reconfigure, evolve, undo, memory_cli, graph_cli, doctor) ainda
  existe para preservar API pública dos tests. Wave 1 fix #5 já moveu
  o helper canônico pra `engine/utils/checkpoint_io.py`. Próxima major
  version pode deletar os wrappers e atualizar os tests pra importar
  direto do shared module. Critério: rodada de cleanup pós-DRIFT-2 OU
  v1.3.
- **FU-DRIFT-1-OBS** (P3) — observability channel pra `tty_bridge`.
  Module docstring atual referencia "engine can log 'we are driving
  this from a TTY fallback'" — não cumprido. Fix #14 removeu a env var
  dead (`FORGE_INTERNAL_TTY_BRIDGE`); reentrada quando
  `engine.utils.log` emergir como módulo de logging estruturado (hoje
  o projeto não tem log infrastructure formal).
- **FU-DRIFT-1-VERIFY-ISO** (P3) — `engine/verify.py::_utc_now_iso()`
  usa `.isoformat()` com microseconds, semantically distinto do shared
  helper `engine.utils.iso.utc_now_iso` que trunca pra seconds. Fix #21
  consolidou os 10 outros usos mas verify.py ficou de fora — migração
  mudaria shape de checkpoint files do `forge verify`. Diferir até bump
  de schema-version do verify checkpoint (não há schema-version formal
  hoje, então o bump abre o caminho).

### Gaps abertos pós plan-auditor v1

Deferidos no spec `docs/superpowers/specs/2026-06-04-plan-auditor-design.md`
§"Considerações futuras (fora do v1)":

- **`forge plan-audit` CLI wrapper** — comando first-class que invoca o
  auditor sem dependência do fluxo writing-plans. Implementação só se
  o auditor provar valor em uso recorrente. Target: v1.2+.
- **Refinamento do severity mapping baseado em smoke real** — após 5-10
  smokes em planos genuínos, avaliar se algum check mudou de severity
  por padrão observado. Inicial: 2 Critical / 4 High / 3 Medium / 3 Low.
  Target: contínuo (sem versão fixa — gatilho é frequência de dados).
- **Tracking estatístico** — coletar contagem média de rodadas por
  auditoria, quais checks disparam mais, distribuição de overrides
  aceitos. Target: v1.2+ se `forge plan-audit` materializar.

### Meta-findings r2 (refinements pra plan-auditor v1.1)

Observações dos smokes r1 + r2 que não foram acionadas no v1, anotadas
pra revisita quando padrão recorrer em smokes futuros (precisamos de
3-5 smokes em planos genuínos pra confirmar valor):

- **Sync verbatim quando rule refina durante implementação do próprio
  plano** — meta #1 r2. Caso degenerado: o plano-auditor cria o
  arquivo do auditor, e meta-findings do smoke r1 refinaram o arquivo,
  desincronizando o verbatim da Task 1. Resolvido em v1 via Caminho A
  manual; pra v1.1 considerar orientação no rule pra "atualizar
  verbatim no mesmo fix-dispatch" OU isenção do H1 quando refinement
  registrado em CHANGELOG/04-pending.
- **PASS_WITH_NOTES validado no piloto** — meta #2 r2. Tier introduzido
  no fix de r1 foi exercitado no r2 e cumpriu papel: orquestrador
  apresenta nota sem ritual de 3-caminhos formal. Mantém-se no v1.
- **"Triggers que não dispararam" valida-se como contramedida pro ruído
  de "0 findings"** — meta #3 r2. Seção nova permite distinguir
  no-trigger de trigger-passou. Mantém-se no v1.
- **Resolved count comprova loop de fix-dispatch** — meta #4 r2. r1 → r2
  fechou 3 findings via Caminho A em 100%. Hipótese do design
  (3-caminhos + verdict tier dão ao orquestrador material suficiente)
  confirmada no piloto. Mantém-se no v1.
- **Tensão plano-como-snapshot vs rule-como-vivo** — meta #5 r2. Plano
  é contrato histórico, rule é artefato vivo. Decisão implícita do
  projeto até aqui: plano não é re-editado pós-execução (refinements
  vivem em commits subsequentes ao rule). Se padrão recorrer (planos
  futuros + refinements pós-implementação criando H-002-like findings),
  registrar como decisão direcional em `docs/design/01-decisions.md`
  com ADR-style commit note.

  > **Case-1 (2026-06-05, power-review PR #6):** finding PR-001 [high
  > gap-spec] confirmou o gap factualmente — bloco verbatim Task 1 do
  > plano divergiu do rule vivo depois de 3 commits de refinement
  > (`b4676dd`, `95aa5a2`, `0d43b394`) que o sync r2 declarou cobrir
  > mas só patcheou parcialmente. Resolução nesta PR (commit `60cde77`)
  > sincronizou os blocos divergentes; gap permanece aberto pra
  > mecanismo preventivo (Caminhos B "verbatim → referência" ou C
  > "isenção H1 quando refinement registrado em CHANGELOG" do meta #1
  > r2). **Contagem: 1/3 (case-1).**

Target: contínuo (sem versão fixa — gatilho é dados de mais smokes).

## Phase 1 — Espinha dorsal (schemas + estrutura)

- [x] workflow-config.yaml schema → `docs/schemas/workflow-config.md`
- [x] Card schema → `docs/schemas/card.md`
- [x] Inventory schemas → `docs/schemas/inventories.md`
- [x] Memory schemas → `docs/schemas/memory.md`
- [x] Graph DB schema → `docs/schemas/graph.md`
- [x] Esqueleto de pastas + arquivos vazios → `docs/design/05-filesystem-layout.md`

### Auxiliary schemas (added during gap-fix)

- [x] proposed-evolutions.yaml schema → `docs/schemas/proposed-evolutions.md`
- [x] rejected-evolutions.yaml schema → `docs/schemas/rejected-evolutions.md`
- [x] workflow-config-history.jsonl schema → `docs/schemas/workflow-config-history.md`

**🎉 Fase 1 — 100% concluída**

## Phase 2 — Cérebros (agents)

- [x] forge init roteiro → `docs/ux/forge-init-roteiro.md`
- [x] planning-conductor prompt → `agents/planning-conductor.md`
- [x] forge plan roteiro end-to-end → `docs/ux/forge-plan-roteiro.md`
- [x] forge implement roteiro end-to-end → `docs/ux/forge-implement-roteiro.md`
- [x] forge verify roteiro → `docs/ux/forge-verify-roteiro.md`
- [x] forge doctor roteiro → `docs/ux/forge-doctor-roteiro.md`
- [x] forge reconfigure roteiro → `docs/ux/forge-reconfigure-roteiro.md`
- [x] forge evolve roteiro → `docs/ux/forge-evolve-roteiro.md`
- [x] Universal disciplines doc → `docs/design/07-discipline.md`
  - TODO v2 polish: cross-link cada §X.Referenced-from no documento alvo (roteiro/schema) para fechar o loop bidirecional.
- [x] Sub-agent prompts (Phase 2 complete):
  - [x] feature-intake-agent → `agents/feature-intake-agent.md` (334 lines)
  - [x] feature-prd-agent → `agents/feature-prd-agent.md` (296 lines)
  - [x] screen-analysis-agent → `agents/screen-analysis-agent.md` (431 lines)
  - [x] contract-planner-agent → `agents/contract-planner-agent.md` (620 lines)
  - [x] tech-spec-agent → `agents/tech-spec-agent.md` (456 lines)
  - [x] task-contract-writer → `agents/task-contract-writer.md` (450 lines)
  - [x] readiness-reviewer → `agents/readiness-reviewer.md` (318 lines)
  - [x] retrospective-agent → `agents/retrospective-agent.md` (490 lines)
  - [x] memory-distiller → `agents/memory-distiller.md` (331 lines)

**🎉 Fase 2 — 100% concluída** (7 roteiros UX + 10 agent prompts, ~7.000 linhas)

## Phase 3 — Conteúdo (templates + cards)

- [x] Templates × 16 → `templates/`
  - [x] feature-intake.template.md
  - [x] feature-prd.template.md
  - [x] screen-analysis.template.md
  - [x] bdd.template.md
  - [x] bdd.template.json
  - [x] ui-state-spec.template.yaml
  - [x] navigation-spec.template.yaml
  - [x] data-contract-spec.template.yaml
  - [x] analytics-spec.template.yaml
  - [x] test-strategy.template.yaml
  - [x] tech-spec.template.md
  - [x] task-breakdown.template.yaml
  - [x] task-contract.template.yaml
  - [x] implementation-readiness-review.template.md
  - [x] plan-feature-handoff.template.json
  - [x] evals.template.json
- [x] Cards canônicos × 12 → `cards/{name}/` (canonical home — siblings of presets/)
  - [x] kotlin-language
  - [x] kmp-shared
  - [x] compose-screens
  - [x] swiftui-screens
  - [x] koin-annotations
  - [x] skie-bridge
  - [x] nav3
  - [x] swiftui-navigation
  - [x] firebase-auth                       (capabilities atualizadas em Fase 3.5)
  - [x] firebase-firestore                  ARQUIVADO em Fase 3.5 → split em 3 cards
  - [x] firebase-storage                    (capabilities OK)
  - [x] crashlytics                         (capabilities OK)
- [x] Preset manifest → `presets/kmp-mobile-firebase/preset.yaml`  ARQUIVADO em Fase 3.5

## Phase 3.5 — Refactor backend-agnostic + REST coverage (entregue 2026-05-29)

Motivação: Fase 3 inicial calcificou Firebase como o backend canônico. Projetos reais usam REST com Retrofit/Ktor mais frequentemente — refactor pra v1 sair sem viés Firebase-first.

- [x] **Catálogo canônico de capability labels** → `docs/schemas/capability-labels.md` (35 labels v1, 9 famílias, 4 tipos: Singular / Latente / Auxiliar / Reservada)
- [x] **Arquivado** `cards/firebase-firestore/` → `cards/.archived/firebase-firestore-monolithic/`
- [x] **3 cards Firestore splittados:**
  - [x] `firestore-persistence` — provê `persistence-server`, `api-contract-firebase-sdk`
  - [x] `firestore-realtime` — provê `realtime-stream`, requires `persistence-server`
  - [x] `firestore-security-rules` — provê `firestore-rules-guarded`, requires `persistence-server`
- [x] **Patches em cards Firebase existentes:**
  - [x] `firebase-auth/card.yaml` — provides: `auth-provider`, `auth-token-bearer`, `auth-firebase-managed` (split do antigo `auth-server`)
  - [x] `firebase-storage/card.yaml` — confirmado: `file-storage`, `firebase-storage`
  - [x] `crashlytics/card.yaml` — confirmado: `crash-reporting`, `crashlytics`
- [x] **6 cards REST novos:**
  - [x] `kotlinx-serialization-json` — provê `serialization-json` (piloto)
  - [x] `ktor-client` — provê `http-client`
  - [x] `rest-api-contract` — provê `api-contract-rest`
  - [x] `room-database` — provê `persistence-local` (Room 2.7+ KMP-stable)
  - [x] `datastore-prefs` — provê `local-prefs-storage`
  - [x] `auth-jwt-bearer` — provê `auth-provider`, `auth-token-bearer` (alternativa REST a firebase-auth)
- [x] **Templates refatorados (3) pra agnóstico:**
  - [x] `data-contract-spec.template.yaml` — top-level `persistence_strategy` + sub-blocos `firestore_collections` / `rest_endpoints` / `local_tables` / `local_prefs` / `realtime_streams` populados via card merge-keys
  - [x] `tech-spec.template.md` — §7 Data layer split em §7.1-§7.7 por capability (server persistence / network http / REST contract / local persistence / realtime / security rules / auth)
  - [x] `test-strategy.template.yaml` — `backend_e2e.provider` agnóstico (`firestore-emulator | mock-server-rest | contract-tests | none`)
- [x] **Agent prompts patchados:**
  - [x] `contract-planner-agent.md` — extension-points formalizados no frontmatter; Data Contract com 2 variantes (Firestore + REST); Auth Contract com 2 variantes mutuamente exclusivas (firebase-auth XOR auth-jwt-bearer)
  - [x] `tech-spec-agent.md` — extension-points novos (`section:Network layer`, `section:Local Persistence`, `section:Auth layer`); Examples com stack Firestore E stack REST
  - [x] `task-contract-writer.md` — referências a `firebase-firestore` (deletado) atualizadas para `firestore-persistence`
- [x] **Preset refactor:**
  - [x] `presets/kmp-mobile-firebase/` arquivado em `presets/.archived/kmp-mobile-firebase-pre-3.5/`
  - [x] `presets/kmp-mobile/preset.yaml` + README criado — só 8 cards de stack; backend via `backend-candidates` (firebase-stack / rest-stack / hybrid / local-only)
- [x] **Patch `docs/design/05-filesystem-layout.md`** — lista de cards (20 ativos + 1 arquivado) e presets (kmp-mobile base + kmp-mobile-firebase arquivado) atualizadas em Step 4 da Fase 3.5
- [x] **PENDENTE** — Patch `docs/schemas/card.md` exemplo Firestore (agora 3 cards splittados em vez de monolítico)  — Cleanup 3.5: Example C reescrito para `firestore-persistence` (manifest completo com `provides: [persistence-server, api-contract-firebase-sdk]`, `conflicts-with: [persistence-server]`, signals sem firestore.rules); Example A corrigido (extension-point `section:Language Conventions` inexistente → `section:Shared (KMP) layer`); cross-ref para `docs/schemas/capability-labels.md` adicionada no topo do schema-version block.
- [x] **PENDENTE** — Patch `docs/ux/forge-init-roteiro.md` (backend selection UX com backend-candidates)  — Cleanup 3.5: Cena 6.5 inserida entre Cena 6 e Cena 7, apresentando os 4 backend-candidates (`firebase-stack`, `rest-stack`, `hybrid-firebase-auth-rest-data`, `local-only`) com signals casados, escolha + opção "personalizar cards manualmente". Cena 6 atualizada para anunciar a 6.5 e remover `firebase-*` do núcleo do preset.

### Fase 3.5 — FOLLOWUPs (não-bloqueantes p/ Fase 4)

- [x] **Normalizar snake_case nos fragments dos cards** — templates dos cards (`firestore-collections.yaml`, `rest-endpoints-data-contract.yaml`, etc) usavam kebab-case nas chaves top-level. Cleanup 3.5: 9 fragments normalizados para snake_case (`firestore_collections:`, `rest_endpoints:`, `room_tables:`, `storage_paths:`, `firestore_rules_tests:`, `crash_reporting:`, `firebase_auth_events:`, `allowed_files_koin_modules:`, `compose_file_patterns:`, `swiftui_file_patterns:` + sub-keys). Card names em comentários (`firestore-realtime`, `firestore-security-rules`) e capability labels (`auth-token-bearer`, `persistence-server`) permanecem kebab por convenção.
- [x] **Labels reservadas v1.1+** — sem provider v1, **por design**: `analytics-pipeline`, `graphql-client`, `websocket-realtime`, `sse-realtime`, `auth-oauth2-rest`. Documentadas no catálogo `capability-labels.md` como "Reservada — sem provider v1". Cards correspondentes virão em v1.1+ conforme demanda real (roadmap, não meia-bomba).
- [x] **Labels out-of-scope v1** — documentadas em `capability-labels.md` como "rejeitadas / out-of-scope". Decisão final: cards correspondentes virão em v1.1+ conforme demanda.
- [x] **Schema do `card.md`** — exemplo de detecção/contribuição ainda referenciava `firebase-firestore` monolítico. Cleanup 3.5: substituído por `firestore-persistence`. (mesmo escopo do PENDENTE 115 acima)
- [x] **`validate_data_contract.py`** — Fase 5b entregou (194 LOC). Reconhece `persistence_strategy`, `operations`, sub-blocos por capability (`firestore_collections`, `rest_endpoints`, `local_tables`, `local_prefs`, `realtime_streams`) + cross-check strategy×card.
- [x] **`validate_capability_labels.py`** — Fase 5b entregou (149 LOC). Parse de `capability-labels.md` + força conformidade em todos os `cards/*/card.yaml`. Reservadas → warn; out-of-catalog → fail.
- [x] **Card `crashlytics`** — confirmar que injeta nome canônico `Firebase{Feature}AnalyticsException` no rule:error-event-binding. Cleanup 3.5: `contract-planner-additions.md` reforça o naming canônico (era `exception-class:` em texto sem referência viva); link para `FirebaseAuthAnalyticsException.kt` em MeoBonsai adicionado como exemplo. `tech-spec-additions.md` já carrega a forma canônica.
- [x] **`evals.template.json` path** — mora em filesystem-layout como `evals/evals.json` (subpasta); template atual é single file. Cleanup 3.5: nota `_template_location` adicionada ao JSON deixando explícito que o template canônico vive em `templates/evals.template.json` e que o engine materializa em `{feature}/evals/evals.json`.
- [x] **Forge init UX** — `engine/init.py` implementa Cena 6.5 backend-candidates (firebase-stack / rest-stack / hybrid / local-only / personalizar). Roteiro `forge-init-roteiro.md` (Fase 4 implementa Python).
- [x] **`extension-points` no `screen-analysis-agent`** — frontmatter não declarava extension-points (card `compose-screens` reportou contribuição como documento preparatório fora de `agent-prompts`). Cleanup 3.5: 4 extension-points adicionados (`after:Component Detection`, `section:UI State Inference`, `section:Visual Ambiguities`, `after:i18n key candidates`).
- [x] **`nav3/card.yaml conflicts-with`** — label `navigation2-android` está fora do catálogo v1. Verificado em cleanup 3.5: `conflicts-with: []` já estava com FOLLOWUP comment apontando reativação em v1.1+. Spot-check cobre `swiftui-screens`, `compose-screens`, demais cards — nenhuma label fora do catálogo nos conflicts-with ativos.

## Phase 4 — Músculos (código) ✅ 57 arquivos, ~12.880 LOC

- [x] Bash dispatcher → `bin/forge`
- [x] Python engine entry → `engine/__init__.py` + `engine/cli.py` (argparse-less dispatcher)
- [x] `engine/init.py` — auto-detect + questionnaire + backend-candidates + inventory + graph build + workflow-config writer
- [x] `engine/plan.py` — planning-conductor Waves A-E + auto-resume + phase_lock
- [x] `engine/implement.py` — task executor topo-sort + plan mode + apply handoff
- [x] `engine/verify.py` — validator cascade fail-fast + `run_scope` API
- [x] `engine/doctor.py` — 11 health checks (full) / 3 (quick) + bak overdue
- [x] `engine/reconfigure.py` — single mutation entrypoint + 10 submenus
- [x] `engine/status.py` — read-only board 6 sections (não listado original)
- [x] `engine/raw.py` — escape hatch (verify-card, edit-config, rebuild-templates real, forge-debug, migrator stub)
- [x] `engine/graph/builder.py` + `incremental.py` + `queries.py` (Q1-Q10) + 3 parsers (Kotlin/Swift/TS)
- [x] `engine/memory/{l1,l2,l3,distiller}.py`
- [x] `engine/cards/{loader,resolver,merger,snapshotter}.py`
- [x] `engine/inventory/{design_system,i18n,conventions}.py`
- [x] `engine/mcp/{registry,types,jira,linear,github_issues,context7}.py`
- [x] `engine/vision/screenshot.py`
- [x] `engine/ingest.py` — single ingest entry pra hook events
- [x] `engine/evolve.py` — review proposed evolutions single-by-single
- [x] `engine/undo.py` — 7 targets menu
- [x] `engine/graph_cli.py` — Q1-Q10 read-only CLI
- [x] `engine/memory_cli.py` — inspect/search/forget/distill/export
- [x] `engine/utils/{paths,yaml_io,sha256,sqlite_io}.py`
- [x] `engine/ui/{renderer,progress,tree,question}.py`
- [x] `engine/persona/mentor_calmo.py`
- [x] `pyproject.toml`
- [x] **Cleanup final** — 29 FOLLOWUPs fechados (forge-version-lock, .gitignore init, history HIST-001..012, doctor last-run, verify L1+log+API, ingest pre-commit real, raw rebuild-templates real, undo commit-sha schema, memory_cli distill real, capability-labels parser, CARD-011/012 cross-check + 3 card bugs fix, categorias, firebase-auth confidence, setext headings, Windows filelock, rejected fingerprints schema, verify-log validation, L2 buckets aux, gitignore parser, 6 tabelas populate, concurrency lock, to_file_id resolution, JUnit5, tailwind parser, level fallback, AndroidManifest, features counter, Ticket dataclass)

## Phase 5 — Pele e validação ✅ 59+13 arquivos, ~6600 LOC

- [x] **Hooks** (9 arquivos, ~277 LOC em `hooks/`):
  - [x] `hooks/post-edit-codebase-graph.sh`
  - [x] `hooks/post-write-feature-artifact.sh`
  - [x] `hooks/pre-commit-feature-forge.sh`
  - [x] `hooks/post-subagent-validate.sh`
  - [x] `hooks/session-start-drift-check.sh`
  - [x] `hooks/git-pre-commit` + `git-post-commit` + `git-pre-push`
  - [x] `hooks/ci-pr-ingest.yml` (GitHub Actions workflow template)
- [x] **Validators Python** (15 arquivos, 2622 LOC em `validators/`):
  - [x] `validate_feature_package.py` (242 LOC) — completeness vs strictness-matrix
  - [x] `validate_readiness.py` (171 LOC) — parseia readiness_verdict
  - [x] `validate_task_contract.py` (247 LOC) — schema + gates + deps
  - [x] `validate_data_contract.py` (194 LOC) — persistence_strategy + strategy×card cross-check
  - [x] `validate_screen_analysis.py` (207 LOC) — StateUI + Meo* refs vs inventory
  - [x] `validate_backend_e2e.py` (207 LOC) — provider + scenarios coverage
  - [x] `check_no_invented_behavior.py` (184 LOC) — grep logEvent/testTag vs contracts
  - [x] `check_files_in_allowed_files.py` (193 LOC) — git diff vs allowed_files
  - [x] `validate_capability_labels.py` (149 LOC) — labels ∈ catalog
  - [x] `validate_workflow_config.py` (175 LOC) — schema + cards sha256
  - [x] `validate_card_yaml.py` (111 LOC) — wrapper CARD-001..018
  - [x] `validate_inventory.py` (161 LOC) — DS/i18n/conventions schemas
  - [x] `validate_memory.py` (197 LOC) — L1/L2/archived schemas
  - [x] Helpers: `__init__.py` + `_common.py` (3-paths + JSON output canônico)
- [x] **E2E test scenarios** (5 cenários em `tests/e2e/`):
  - [x] greenfield init (`test_e2e_greenfield_init.py`)
  - [x] brownfield init in MeoBonsai (`test_e2e_brownfield_init.py`)
  - [x] full plan (`test_e2e_full_plan.py`)
  - [x] implement-task gates (`test_e2e_implement_gates.py`)
  - [x] resume after pause (`test_e2e_resume_after_pause.py`)
- [x] **Tests extra** (30+ arquivos, ~3460 LOC em `tests/`):
  - [x] 20 unit tests (engine/utils, ui, persona, cards, memory, graph, inventory, mcp)
  - [x] 5 integration tests (init greenfield/brownfield, cards resolver MeoBonsai, graph build, inventory extract)
  - [x] 13 validator tests (smoke + happy + fail paths, +596 LOC)
  - [x] conftest.py com fixtures comuns (tmp_project_root, tmp_forge_project, meobonsai_root, tmp_forge_project_with_feature)
- [x] **Cleanup Fase 5** — 3 itens fechados:
  - [x] Hooks instalação automática durante `forge init` Step 13 (+92 LOC em init.py — `_install_hooks` + `_install_git_hooks` com symlinks relativos pra `.git/hooks/`)
  - [x] 3 handlers ausentes em `engine/ingest.py`: `post-subagent-validate`, `pre-push`, `ci-pr-ingest` (+150 LOC, 8 rotas totais)
  - [x] Tests dos 13 validators (13 arquivos novos em `tests/unit/test_validators_*.py`)

**Smoke gates finais:** 258 tests passing, 12 skipped (e2e por default — `RUN_E2E=1` ativa). Zero regressões.

### Out-of-scope Fase 5 (decisões arquiteturais, não FOLLOWUPs)

- `engine.doctor` não expõe `_run_quick_check` como API pública — `ingest._handle_pre_push` tem fallback gracioso; expor API quando v1.1 demandar
- Windows symlink fallback em `_install_git_hooks` — silent try/except OK; ADR formal quando Windows entrar
- `read_yaml_or_default` raise em YAML malformado — decisão validator-side; trocar requires patch coordenado nos 13 validators

## Stress-test 2026-05-29 — gaps a tratar

Stress test conversacional executado 2026-05-29 confrontou o pipeline contra 6
cenários cobrindo 5 famílias de estresse (cerimônia desproporcional, escopo
que rompe a unidade "feature", mutação durante execução, shape fora do happy
path, humano/time/compliance). Resultado: 1/6 bem coberto, 3/6 gaps remediáveis
sem quebrar decisões locked, 1/6 gap fundamental (precisa novo estado de
feature), 1/6 out-of-scope honesto v1.

A intenção dessa seção é virar fila de evolution candidates pra v1.1+, **não**
re-abrir decisões locked. Mentor calmo é firme nas bordas — as 27 decisões
permanecem como estão. Estes gaps são para **estender o forge dentro das
decisões**, não revisitar.

### Gap 1 — Cenário A1: Hotfix urgente sem fast-path ✅ resolvido 2026-05-30 (bugfix subtype completo)

**Severidade:** média. Bugfix realmente urgente (P0, 30min) força cerimônia
desproporcional (~6-10 min de waves + plan-mode + apply + review). Dev tende a
bypassar o forge — tensão entre disciplina e pressão de produção.

**Origem:** `forge-plan-roteiro.md` waves A-E rodam todas independente de
shape; `agents/planning-conductor.md` Phase 2 walk em 27 nós sem short-circuit;
shape canônico "bugfix" inexistente; auto-retrospective gera proposed-evolutions
mesmo pra fix trivial.

**Solução aplicada — `bugfix` subtype shipped completo:**

A solução constrói diretamente sobre o subtype mechanism do Gap 2 (refactor
ship 2026-05-30) e a state-orthogonal `blocked-on-external` do Gap 8 — sem
regredir nenhum dos dois. `bugfix` é o 5º valor do `subtype` enum (após
product / refactor / spike / chore), com semântica distinta de refactor:

- Refactor = comportamento inalterado por design; Wave B sempre skipada;
  `check_no_behavior_change` gate.
- Bugfix = restaurar comportamento correto; Wave B **conditional** (1 sub-
  question em Cena 2.5); sem `check_no_behavior_change` (mudança é
  inerente — de quebrado pra correto).

- [x] **Subtype `bugfix` no enum canônico** — `engine/memory/l1.py
      _VALID_SUBTYPES`, `docs/schemas/memory.md §subtype semantics by
      value`, MEM-L1-008 atualizada pra aceitar o 5º valor.
- [x] **Filesystem layout** — mesmo `non-product/{slug}/` subtree usado por
      refactor. Decisão: bugfix também é "não é nova product behavior", é
      "restaurar product behavior correto", então cabe no mesmo guarda-chuva.
- [x] **Cena 2.5 estendida** em `docs/ux/forge-plan-roteiro.md`:
      - Keyword detection: `bugfix`, `hotfix`, `P0`, `P1`, `crítico`, `bug `,
        `fix `, `falha`, `quebrado`, `não funciona`, `regression`, `crash`
      - **Ticket-pattern detection** (`IN-NNNNN`, `PD-NNNN`, `BUG-NNNN`
        prefixes only — `BACKEND-`/`BONSAI-` ambíguos não promovem)
      - 3 novos casos UX: happy path + P0/hotfix urgency + vague description
      - Sub-question da Wave B: "esse bug envolve mudança de UI ou de
        comportamento observável?" — única decisão extra do bugfix
- [x] **Engine wiring** em `engine/plan.py`:
      - `_SUBTYPE_KEYWORDS["bugfix"]` com 20 keywords
      - `_TICKET_PATTERN` regex + `_BUGFIX_TICKET_PREFIXES` whitelist
      - `detect_subtype_from_input` agora cobre keyword + ticket pattern
        (precedence: refactor > bugfix > spike > chore > ticket pattern)
      - `_WAVE_ORDER_BUGFIX_LOGIC_ONLY` (A·C·D·E) +
        `_WAVE_ORDER_BUGFIX_UI_OBSERVABLE` (A·B·C·D·E)
      - `_wave_order_for_subtype(subtype, wave_b_required=...)` runtime
        branching (única wave-dispatch que depende de sub-question)
      - `_elicit_bugfix_wave_b_required()` + `_persist_hypothesis_wave_b_required()`
        + `_read_hypothesis_wave_b_required()` helpers
      - `WAVE_A_BUGFIX_TEMPLATES` constant pointing at the new intake
      - `run()` chama Wave B sub-question pra bugfix antes do dispatch
      - Artifact-count message do closing reflete Wave B status
- [x] **Template novo** `templates/feature-intake-bugfix.template.md` —
      intake stripped com §Problem statement, §Reproduction steps (MANDATORY),
      §Expected vs actual behavior, §Root-cause hypothesis (with confidence),
      §Fix scope, §Regression risk (low/medium/high), §Validation strategy,
      §Links. Drop intencional: "user value", "scope OUT", "why now".
- [x] **`agents/planning-conductor.md`** patched:
      - Phase 1 step 4: bugfix keyword cues + urgency acknowledgment +
        Wave B sub-question
      - Phase 1 hypothesis.yaml bugfix variant (bug-ticket, repro-known,
        wave_b_required, root-cause-confidence, regression-risk, fix-shape)
      - Phase 2 "Ticket pattern detection" subsection (high-confidence
        bumps) + table de prefixes
      - Phase 4 wave-dispatch matrix com bugfix row + Bugfix branch
        section (Wave B conditional behavior)
      - Phase 6 auto-retrospective trigger com **5-whys prompt template**
        (Gap 1 mandatory — bugfix retro tem highest learning value)
      - Closing format ganha **bugfix variant** (Wave B ran/skipped flag,
        regression risk, retrospective notice)
- [x] **`agents/tech-spec-agent.md`** patched:
      - Context pack subtype field aceita "bugfix" + novo `wave_b_required`
        field documentado
      - Document structure: **subtype-conditional rendering** section
        ganha bugfix mode (sempre §§ 1·2·3-7·13·14; §11 conditional;
        §§ 8·9·10·12 skip)
      - Phase 2 ganha "Bugfix variant" (antes/depois of behavior path)
      - Phase 3 ganha bugfix two-modes (UI/observable vs logic-only)
      - **Example 4 — Bugfix subtype IN-37234** com context pack
        completo + tech-spec rendering + output JSON
- [x] **`docs/design/07-discipline.md` §8** estendida pra cobrir bugfix:
      - Tabela de subtypes ganha bugfix row
      - Nova subseção "Bugfix — comportamento detalhado (Gap 1, 2026-05-30)"
        com: quando aplica, distinção formal vs refactor (tabela 5-eixos),
        Wave A/B/C/D/E semantics, **Phase 6 5-whys template**
      - Filesystem layout atualizada
      - Keyword table ampliada com bugfix + ticket pattern regex
      - Cheat-sheet operacional preservada (sem nova entrada — bugfix
        cabe em §8)
- [x] **`tests/unit/test_plan_subtype.py`** estendido (não substituído):
      - 6 novos casos de bugfix keyword detection
      - 6 novos casos de ticket pattern detection (whitelist + non-whitelist)
      - 3 novos casos de priority (refactor vs bugfix, bugfix vs spike,
        product when only ticket)
      - 3 novos wave-order tests (logic-only / UI-observable / None default)
      - 2 novos L1State round-trip tests (bugfix + all-5 canonical)
      - 1 novo set_subtype bugfix persistence test
      - 3 novos intake template selection tests (constant pointing, distinct,
        file exists on disk)
      - 3 novos hypothesis.yaml wave_b_required round-trip tests
      - **+28 tests · 0 regressions · 365 passed, 1 skipped (baseline 337+1)**

**Princípio preservado:** zero flag (Decision 10), 12 comandos (Decision 9),
3-caminhos universal (discipline §1), pause-vs-abort (discipline §7),
never-invent (00-vision §What feature-forge is NOT), deterministic context
(sub-agents recebem subtype + wave_b_required via context pack).

**Gap 2 e Gap 8 NÃO foram regredidos:**

- Subtype enum estendido de 4 → 5 valores (refactor/spike/chore preservados)
- Wave order de refactor preservado (A·C·D·E)
- `check_no_behavior_change` continua rodando APENAS quando subtype=refactor
  (não roda em bugfix — bugfix muda comportamento por definição)
- `blocked-on-external` state preservado (ortogonal a subtype — bugfix
  pode ficar blocked esperando backend, exatamente como refactor pode)

**O que ficou como TODO residual (v1.1+):**

- [ ] **Smart 5-whys prompting** — atualmente o retrospective-agent recebe
      um template estático. v1.1+: agent lê root-cause unknown vs confirmed
      e adapta o prompt (mais drill-down quando confidence inicial era < 0.5).
- [ ] **Auto-detection de regression test missing** — quando bugfix
      implement.py finaliza sem adicionar test, validator novo emite warning
      ("bugfix sem regression test é bugfix cego"). Não bloqueia em v1.0;
      virou cheat de retro pra ser proposed-evolution.
- [ ] **Cross-feature bug pattern detection** — quando 2+ features tiveram
      bugfix com root cause similar (ex.: "trim falta em validador") em
      janela curta, retrospective emite proposta de promover guard pra
      shared/core/util/.
- [ ] **`forge graph` Q12 — bugs-similar-root-cause** — query nova pra
      reuso de fix patterns. v1.1+ quando houver dados suficientes pra
      similarity metric significativa.
- [ ] **Severity gating** — quando severity=P0/P1 em hypothesis, Wave E
      relaxa ainda mais (aceita partial root-cause confidence). v1.1+ —
      por ora P0 e P3 seguem o mesmo gate.
- [ ] **Anti-pattern: A2 small feature** — explicit non-goal aqui. Small
      product features ficam como product subtype. Plan tamanho é
      proporcional ao tamanho da feature; não há mecanismo especial.

**Validation pendente para piloto smoke test:**

- [ ] Smoke test bugfix UI/observable: planejar fix de UI real
      (ex.: BonsaiForm que aceita whitespace como nome vazio), confirmar
      `subtype=bugfix` + `wave_b_required=true`, verificar que Wave B
      roda + tech-spec foca §1·§2·§3-7·§13·§14.
- [ ] Smoke test bugfix logic-only: planejar fix de lógica pura
      (ex.: validador de email com regex incorreto), confirmar
      `subtype=bugfix` + `wave_b_required=false`, verificar que Wave B
      pula + intake-bugfix renderiza + tech-spec é stripped (similar a
      refactor mas com regression-risk).
- [ ] Smoke test ticket pattern detection: input `IN-37234 está
      crashing app no Android 14`, verificar que conductor sobe pra
      bugfix confidence alta na Cena 2.5.
- [ ] Smoke test urgency acknowledgment: input com "P0 em produção",
      verificar que conductor cumprimenta urgency + segue disciplina
      (não pula Wave B quando bug é UI).
- [ ] Smoke test 5-whys retrospective: completar implement de bugfix,
      verificar que retrospective-agent emite proposed-evolutions com
      walked-through analysis (não vazio, não "be more careful").
- [ ] Smoke test conductor vague drill-down: input "tem um bug, algo
      não funciona", verificar que conductor recusa rotear bugfix +
      apresenta 3-caminhos.

**Arquivos modified (Gap 1):**

- `docs/schemas/memory.md` — `bugfix` em subtype enum + semantics row + MEM-L1-008
- `docs/design/07-discipline.md` — §8 ganha bugfix subsection + tabela
  expandida + keyword table + cross-link refs
- `docs/ux/forge-plan-roteiro.md` — Cena 2.5 ganha 3 cenários bugfix
  (happy + P0 urgency + vague) + nota operacional sobre Wave B sub-question
- `agents/planning-conductor.md` — Phase 1 (bugfix keyword cues + Wave B
  sub-question + urgency ack) + Phase 1 hypothesis bugfix variant +
  Phase 2 (ticket pattern detection table) + Phase 4 (matrix row +
  Bugfix branch section) + Phase 6 (5-whys retro template) + Closing
  format (bugfix variant)
- `agents/tech-spec-agent.md` — context pack (subtype + wave_b_required) +
  subtype-conditional rendering (bugfix mode) + Phase 2 bugfix variant +
  Phase 3 bugfix two-modes + Example 4
- `engine/memory/l1.py` — `_VALID_SUBTYPES` ganha bugfix
- `engine/plan.py` — `_SUBTYPE_KEYWORDS["bugfix"]` + `_TICKET_PATTERN` +
  `_BUGFIX_TICKET_PREFIXES` + `_WAVE_ORDER_BUGFIX_*` + `_wave_order_for_subtype`
  com kwarg + `detect_subtype_from_input` com ticket pattern bump +
  `WAVE_A_BUGFIX_TEMPLATES` + `_elicit_bugfix_wave_b_required` +
  `_persist_hypothesis_wave_b_required` + `_read_hypothesis_wave_b_required` +
  `_confirm_subtype_inference` ganha bugfix pretty-name + `_run_waves_for_subtype`
  com kwarg + `run()` orquestra Wave B sub-question + artifact message
- `templates/feature-intake-bugfix.template.md` — NEW, 230 LOC
- `tests/unit/test_plan_subtype.py` — +28 tests (327 LOC adicionadas)

### Gap 2 — Cenários A3/A4: Non-product feature track (spike + refactor + chore) ✅ resolvido 2026-05-30 (refactor only; spike + chore stubbed)

**Severidade:** alta. Forge atualmente modela só features de produto. Cenários
"non-product feature" não cabem honestamente:

- **Spike (A3):** comportamento ainda desconhecido. Não tem PRD definitivo,
  não atinge `readiness=ready`. Forçar Wave B faria conductor "inventar".
- **Refactor (A4):** comportamento explicitamente inalterado por design.
  Sem PRD natural, sem screen-analysis (zero mudança visual), sem analytics.
  Forçar contract-planner-agent gera 5 specs vazias ou artificiais.
- **Chore:** atualização de dep, bump de versão, cleanup. Mesma classe.

Todas violam o princípio "eu não invento" (00-vision §What feature-forge
is NOT) quando passam pelo pipeline default.

**Origem:** estados de feature em 07-discipline §7 (`not-started → planning →
planned → implementing → verified → done`) não comportam non-product; waves
B-C-D obrigatórias geram artefatos sem matéria-prima; L1→archived polui
similarity-graph com tentativas descartadas (no caso de spike) ou refactors
internos (no caso de A4).

**Solução aplicada — `refactor` completo, `spike + chore` stub via 3-caminhos:**

- [x] **Novo guarda-chuva `non-product-feature track`** com subtipos
      `spike | refactor | chore`. `refactor` ship por completo nesta v1.0;
      `spike + chore` ficam como stub via 3-caminhos discipline §1 (caminhos
      legítimos: treat as product / wait v1.1+ / abort) — sem improviso.
- [x] **Filesystem-layout extension:**
      `docs/feature-implementation-workflow/non-product/{slug}/` paralelo a
      `features/{slug}/`. Tabela em `docs/design/05-filesystem-layout.md §3`
      mostra quais artefatos existem por subtipo. Não entra na
      similarity-graph automática (conductor §Phase 1 skipa Q1 quando
      subtype=refactor).
- [x] **Cena 2.5 do plan-roteiro** (nova seção inserida entre Cena 2 e
      Cena 3) detecta keywords ("spike", "POC", "viabilidade", "exploração",
      "refactor", "mover", "renomear", "extrair", "sem mudança visual",
      "bump", "atualizar dependência", "cleanup", "chore") e roteia para
      o subtipo apropriado interativamente. Zero flag — Decision 10
      preservada.
- [x] **Validator novo `check_no_behavior_change.py`** quando subtipo=refactor:
      rejeita se diff toca testes funcionais (indicador de mudança
      comportamental disfarçada). 3-caminhos canônico (fix/revert/split).
      Inactive quando subtype != refactor (no-op pass).
- [x] **Template novo `templates/feature-intake-refactor.template.md`** —
      variante stripped sem PRD: §Problem, §Root cause, §Files affected,
      §Architecture before→after, §No-behavior-change attestation
      (checklist explícito), §Validation strategy.
- [x] **`status.json` schema upgrade aditivo** — campo `subtype` em
      `docs/schemas/memory.md §status.json`. Default `"product"` quando
      ausente (forward compat para status.json escritos por engines
      pre-Gap-2). Validation rule MEM-L1-008 estendida.
- [x] **`L1State.subtype` em `engine/memory/l1.py`** + helpers
      `current_subtype()` / `set_subtype()`. Round-trip + invalid-value
      rejection cobertos por testes.
- [x] **`engine/plan.py` branch wave dispatch** — `_wave_order_for_subtype`
      retorna (A,B,C,D,E) para product e (A,C,D,E) para refactor;
      `_resolve_features_root` reroteia para `non-product/{slug}/` quando
      subtype != "product"; `_handle_stub_subtype` surface 3-caminhos
      para spike/chore.
- [x] **`agents/planning-conductor.md` Phase 1 + Phase 4** patched:
      Cena 2 source-inquiry agora documenta subtype detection (Phase 1
      step 4); Phase 4 declara wave matrix por subtype + bloco 3-caminhos
      para spike/chore; closing format ganha refactor variant.
- [x] **`agents/tech-spec-agent.md` context pack + Document structure**
      ganha campo `subtype`, lista artefatos ABSENT por subtype, e
      seção "Subtype-conditional rendering" declarando quais §§ vivem
      em refactor (§§ 1, 2, 3-7 modified-only, 14).

**Princípio preservado:** zero flag (Decision 10), 12 comandos
(Decision 9), 3-caminhos universal (discipline §1), pause-vs-abort
(discipline §7), never-invent (00-vision §What feature-forge is NOT).

**O que ficou como TODO residual (v1.1+):**

- [ ] **Spike subtype completo** — workspace livre + findings opcionais
      + UX de "promote spike to feature" quando user decide ir adiante.
      Stub atual surfaces 3-caminhos. Issue: workspace livre quebra a
      premissa de `readiness=ready` que vários comandos confiam — precisa
      novo estado `exploring` ortogonal antes de shippar.
- [ ] **Chore subtype completo** — intake-minimal + task-contract apenas.
      Stub atual surfaces 3-caminhos. Issue: chore frequentemente cruza
      múltiplas features (bump de dep toca N módulos) — fica acoplado a
      Gap 3 (migração grande).
- [ ] **`subtype-aware retrospective-agent`** — quando refactor termina,
      retrospective deve emit propostas de promoção de helpers
      identificados durante o move (não promoção de patterns de produto).
      Pendente de design.
- [ ] **`forge graph` query Q12 — refactors-similar-shape** — quando user
      planeja refactor novo, mostrar refactors anteriores similares
      (mover X→Y, rename A→B). Stub: usar Q1 existente filtrado por
      `non-product/`.
- [ ] **`status.json.subtype` migration tool** — para projetos que já
      têm features no L1 com status.json pre-Gap-2 e queiram explicitamente
      backfill `subtype: product`. v1.0 trata ausência como product
      automaticamente; tool seria opt-in.
- [ ] **Edge case documented**: feature começa como product, depois user
      percebe que é refactor mid-planning. Caminho atual: `forge undo`
      + replanejar. v1.1+: `forge reconfigure` → menu "trocar subtype"
      com validação que Wave B artifacts estão deletados.

**Validation pendente para piloto smoke test:**

- [ ] Smoke test refactor real no MeoBonsai: planejar mover `MeoButton`
      de `organisms/` → `atoms/`, verificar que Wave B skipa, intake-
      refactor renderiza, tech-spec stripped, allowed_files preciso na
      Wave D, check_no_behavior_change passa em diff limpo.
- [ ] Smoke test happy: planejar feature de produto normal (`lembrete-rega`)
      e verificar que `subtype: product` persiste e Wave B roda normal.
- [ ] Smoke test stub: tentar planejar com keyword "spike" e verificar
      que 3-caminhos block renderiza, option A (treat as product) flipa
      subtype e continua Wave B.
- [ ] Verificar que `forge status` board lê subtype corretamente quando
      feature já planejada (dependência cross-arquivo `engine/status.py`
      — não tocado em Gap 2; pode precisar ajuste cosmético em v1.1).
- [ ] Verificar que `forge implement` em refactor lê task-contract
      `validations: [check_no_behavior_change]` e roda o gate na cascade.

**Arquivos modified (Gap 2):**

- `docs/schemas/memory.md` — `status.json.subtype` field + MEM-L1-008
- `docs/design/07-discipline.md` — nova §8 "Non-product feature track"
- `docs/design/05-filesystem-layout.md` — `non-product/{slug}/` tree
  + artifact-per-subtype matrix
- `docs/ux/forge-plan-roteiro.md` — Cena 2.5 Subtype detection
- `agents/planning-conductor.md` — Phase 1 (subtype detection) + Phase 4
  (wave dispatch branching) + closing format (refactor variant)
- `agents/tech-spec-agent.md` — context pack subtype field + Document
  structure subtype-conditional rendering + Phase 2/3 patches
- `engine/plan.py` — `detect_subtype_from_input`, `_wave_order_for_subtype`,
  `_resolve_subtype_for_run`, `_handle_stub_subtype`,
  `_run_waves_for_subtype`, `_resolve_features_root` subtype param,
  `_feature_path` subtype param
- `engine/memory/l1.py` — `_VALID_SUBTYPES`, `L1State.subtype`,
  `current_subtype()`, `set_subtype()`, write/read validation
- `validators/check_no_behavior_change.py` — NEW, 175 LOC
- `templates/feature-intake-refactor.template.md` — NEW, 178 LOC
- `tests/unit/test_plan_subtype.py` — NEW, 31 tests

### Gap 3 — Cenário B1: Migração grande sem shape próprio

**Severidade:** média. Migrações (KMP migration, Nav2→Nav3, etc.) tocam N
features iguais. Modelar como 1 feature mãe (N tasks, retrospective só na
semana 8) OU N features paralelas (N plans, N retrospectives) — ambas geram
overhead que o forge poderia evitar com shape próprio. Caso real porque
01-decisions cita "estou modularizando outro projeto que também é Android +
iOS + KMP".

**Origem:** `task-breakdown.yaml` schema não tem conceito de "meta-task =
template + N alvos"; retrospective auto-trigger só na última task (decisão 11)
impede learning real-time durante migração longa; `proposed-evolutions.yaml`
single-file gera hotspot de merge em multi-dev.

**Remediação proposta (v1.1):**

- [ ] Card novo `migration-batch` com template "meta-task-breakdown"
      (1 template + lista de N alvos). Plan-mode mostra "vou aplicar template
      X em bonsai-list" pra cada alvo
- [ ] Retrospective incremental: a cada N=3 tasks fechadas em feature batch,
      retrospective parcial roda e queue learnings. Não substitui o final
- [ ] `status.json` schema upgrade pra `active-tasks: [list]` em vez de
      singular — abre caminho pra E1 também (multi-dev)

### Gap 4 — Cenário C1: PRD muda mid-implement, sem validação post-fact

**Severidade:** baixa. Decisão 9 + 06-command-surface §"Amend plan" cobrem o
fluxo. Gap pequeno no post-fact: tasks done antes do re-plan não são
validadas contra novo PRD — código legacy passa silentemente desalinhado.

**Origem:** Cena 1 do plan-roteiro oferece "Retomar/Começar feature nova/
Abortar e começar do zero", mas não há validator que confronta tasks done
existentes com novo plano gerado.

**Remediação proposta (v1.1):**

- [ ] Validator novo `validate_pre_existing_tasks_vs_new_plan.py` dispara no
      início do re-plan: (a) task done existe no novo task-breakdown?
      (b) allowed_files batem? (c) contracts batem? Gera findings STALE
- [ ] Documentar explicitamente em `task-contract.template.yaml` que IDs de
      tasks done são imutáveis em re-plan; tasks novas pegam IDs incrementais
      a partir de `max(done)`
- [ ] Novo finding type `STALE-DELIVERY-{n}` com proposed-remediation
      surfaceada em `forge evolve`

### Gap 5 — Cenário D2: Stack fora do catálogo ✅ RESOLVIDO em 2026-06-02

**Status:** Entregue via plan
`docs/superpowers/plans/2026-06-02-gap5-card-local-overlay.md`. Approach A
(cascade simples). 13 tasks, ~1910 LOC.

Gaps parcialmente destravados como side-effect:
- **Gap 9** (catálogo evolutivo): overlay dá caminho oficial pra labels
  ainda não promovidas.
- **Gap 14** (preset coverage): preset canônico errado fica mitigável via
  card local enquanto preset novo não é shipado.

---

**Histórico original (preservado pra ADR/rationale):**

**Severidade:** alta. Decisão 22 ("absorb essences, no dependencies") +
princípio "portabilidade" (00-vision) batem de frente com catálogo fechado.
Forge atual é portátil só dentro do espaço amostral coberto pelos 20 cards
canônicos. Projetos com Hilt (não Koin), Apollo GraphQL, Realm, etc., não
têm caminho oficial.

**Origem:** `card.md` §"Out of scope for v1" declara "Marketplace de cards"
out-of-scope; `validate_capability_labels.py` (Fase 5b) força "labels ∈
catalog"; `forge reconfigure` opção "adicionar card" referencia só
canonical; init detection com 0 matches em stack desconhecida pode propor
default conflitante.

**Remediação proposta (v1.1):**

- [ ] `.claude/cards/local/{name}/` como overlay aos canônicos. Documentar
      em `card.md` §"Where cards live"
- [ ] `.claude/inventory/capability-labels.local.yaml` que estende o catálogo;
      `validate_capability_labels.py` aceita catalog ∪ local
- [ ] `forge reconfigure` ganha opções "adicionar card local (criar do
      skeleton)" e "importar card de path"
- [ ] Init fail-safe quando stack ambígua: signals batem em label custom
      mas card ausente → 3-caminhos (criar local skeleton / `forge ignore` /
      abortar até v1.1+)
- [ ] Roadmap explícito de cards v1.1+ priorizando labels reservadas:
      `hilt-di`, `apollo-graphql-client`, `realm-database`,
      `auth-oauth2-rest`

### Gap 6 — Cenário E1: Multi-dev mesma feature (out-of-scope v1 honesto)

**Severidade:** —. `memory-and-graph.md` §"Out of scope for v1" declara
explícito "Single-user assumed in v1". Não é gap escondido — é decisão
arquitetural honesta. Mas é caso de uso real frequente em times mobile.

**Workaround atual:** features que precisam multi-dev → split em 2 features
com dependência declarada (`lembrete-rega-shared`, `lembrete-rega-android-ui`).

**Remediação proposta (v1.1+):**

- [ ] `status.json` schema upgrade pra `active-tasks: [{task, actor}]` (também
      atende Gap 3)
- [ ] `history.jsonl` schema com campo `actor` + estratégia de merge
      sort-by-timestamp (resiliente a git merge automático)
- [ ] L1 sync seletivo via L2 proposal proativa: Finding com `severity: high`
      → forge propõe promoção pra L2 em real-time
- [ ] ADR formal documentando trade-offs single-user vs multi-user

### Gap 7 — Cenário B2: Feature em múltiplos releases (time-shifted shipping)

**Severidade:** média. Forge assume 1 feature = 1 ship moment. Realidade
mobile é commonly multi-ship: Android sai em Q3, iOS sai em Q4. Mesma
feature, 3 meses entre shipments. Time real ships partial constantly.

**Origem:** retrospective auto-trigger só após ÚLTIMA task verificada
(decisão 11); estados de feature não comportam "parcialmente released";
`status.json.current-task=null` durante o vácuo confunde retomada;
`forge status` board mostra feature como `implementing` por meses com
last-action defasado.

**Remediação proposta (v1.1):**

- [ ] Estado intermediário `partial-released` entre `implementing` e `done`,
      disparado quando subset de tasks foi taggeado como release-shipped
- [ ] Retrospective incremental disparado por **release events** (não só
      "última task verificada"): após Q3 ship Android, retrospective Wave 1
      analisa tasks do ship-group. Compartilha implementação com Gap 3
      (migração incremental)
- [ ] `task-breakdown.yaml` ganha campo opcional `release-group:
      q3-android | q4-ios`. Tasks no mesmo group compartilham ship-moment
- [ ] `forge status` mostra "shipping schedule" — quais tasks já shipadas
      vs pending por grupo (substitui visão linear single-track)

### Gap 8 — Cenário B3: Dependência externa não pronta (estado `blocked-on-external`) ✅ resolvido 2026-05-30 (schema + engine + manual unblock; MCP polling stubbed)

**Severidade:** média-alta. Caso super comum em mobile (backend atrás de
mobile). Feature plan completo, readiness=ready, mas implement das tasks
dependentes do endpoint não pode rolar — backend só sai daqui 2 sprints.

**Origem:** lifecycle não tinha estado `blocked-on-external`; schema de
task-contract só tinha dependências internas (`depends-on: [TASK-0003]`);
forge não tinha mecanismo de unblock quando ticket externo fecha;
`forge status` não distinguia blocked vs idle — dev tentava task qualquer,
esbarrava na dep, perdia tempo.

**Solução aplicada — schema + engine ship completo, MCP polling stubbed:**

- [x] **Novo estado `blocked-on-external` no `status.json`**, paralelo a
      `deferred` (engine-driven, não pause humano). Documentado em
      `docs/schemas/memory.md §state.blocked-on-external` com semântica
      completa (quando trigga, quando libera, transitions allowed). `MEM-L1-008`
      estendida para aceitar o novo valor.
- [x] **`task-contract.template.yaml` ganhou `depends_on_external`** —
      campo opcional, lista de entries com schema:
      ```yaml
      depends_on_external:
        - ticket: BACKEND-1284
          integration: jira          # jira | linear | github-issues | manual
          description: "..."
          blocking: true
          declared-at: 2026-05-30T...
          resolved-at: null          # null until forge reconfigure
      ```
      `validators/validate_task_contract.py` valida shape (ticket required,
      integration ∈ enum, blocking bool, resolved-at ISO 8601 ou null).
- [x] **`forge status` board separa in-flight / blocked / deferred / done**
      (engine/status.py reescrito; nova seção "blocked on external" lista
      cada feature + ticket + integration + age).
- [x] **`forge implement` recusa task bloqueada com 3-caminhos canônico**:
      (a) marcar dep resolvida via reconfigure, (b) pegar outra task livre,
      (c) pausar feature. Flipa `state` pra `blocked-on-external` no
      primeiro refuse de uma session (idempotente em refuses subsequentes).
      Auto-recovery: feature em blocked-on-external faz re-scan no startup
      e flipa de volta pra `implementing` quando todas deps blocking estão
      `resolved-at`.
- [x] **`forge plan` em modo "partial-ready"**: readiness-reviewer ganha
      verdict `ready-with-blocks` quando ≥1 task tem dep externa mas o
      subset não-blocked é completo. `forge implement` aceita
      `ready-with-blocks` igual a `ready`; rejeita as tasks blocked
      individualmente (3-caminhos).
- [x] **`forge reconfigure` ganhou opção "marcar dep externa como resolvida"**
      (novo handler em `engine/reconfigure.py`). Lista features blocked,
      dedupe por ticket (mesmo ticket em N tasks = 1 confirmação =
      N entries atualizadas atomically), escreve `resolved-at` com
      backup `.bak` per file + re-scan + state flip + history entry.
- [x] **Discipline §9 nova** em `docs/design/07-discipline.md` —
      semantics formais, distinção de §7 (deferred = pause humano) e
      `aborted` (terminal), interação ortogonal com §8 (subtype),
      formato canônico do 3-caminhos block, scope-out explícito do
      MCP polling.
- [x] **Roteiros patcheados:**
  - `docs/ux/forge-plan-roteiro.md` — Cena 10.5 (External dep
    detection during elicitation) com 4 sub-cenários (happy/vague/
    resolved-mid-planning/multiple-deps-same-ticket)
  - `docs/ux/forge-implement-roteiro.md` — Cena 2.5 (Blocked task
    refusal) com 4 sub-cenários (happy/no-alternative/cleared-mid-
    session/multiple-deps-same-task)
  - `docs/ux/forge-reconfigure-roteiro.md` — sub-cena 5.6
    (External-deps) com 4 sub-cenários (happy/multi-task/empty/
    ticket-not-found)
- [x] **Agents patcheados:**
  - `planning-conductor.md` Phase 2 ganhou "External dependency
    drill-down" table com triggers e drill-down rules. Phase 4
    declara context-pack field `external-deps`. Closing format
    ganhou ready-with-blocks variant.
  - `task-contract-writer.md` Phase 4 ganhou step 6 (External
    dependencies) explicando task-hint resolution + dedupe rules.
    `external-deps` agora documentado no context pack input.
  - `readiness-reviewer.md` Phase 4.5 (External dependencies audit)
    + verdict matrix atualizada com `ready-with-blocks` distinto de
    `partial`. JSON output ganhou `external-blocks` array.
- [x] **`L1State` extendido em `engine/memory/l1.py`**:
  - `_VALID_STATES` aceita `blocked-on-external`
  - `is_blocked(slug, project_root) -> bool`
  - `blocking_deps(slug, project_root) -> list[dict]` (walks tasks/)
  - `list_blocked_features(project_root) -> list[str]`
  - Forward-compat: status.json sem blocked state parse normal (não
    requer migration)
- [x] **`engine/plan.py` ganhou `record_external_dep()`** helper para
      planning-conductor persistir em `elicitation.yaml.external-deps[]`
      com dedupe por (ticket, task-hint).
- [x] **`engine/implement.py`:**
  - `TaskContract.external_deps` field
  - `_task_blocking_deps()` helper
  - `_pick_next_task(skip_blocked=True)` para alternativa
  - `_print_blocked_refusal()` renderiza 3-caminhos canônico
  - Refusal flow com exit code 7 (distintinto de 130 pause / 5 not-ready)
  - Auto-recovery no startup quando state==blocked-on-external mas
    deps foram resolvidas externamente
- [x] **`engine/status.py` rewrite** — board partitionado por estado
      (in-flight / blocked on external / deferred / other), com helper
      `_format_blocked_summary` que agrupa por ticket.
- [x] **`engine/reconfigure.py`** ganhou `_handle_external_deps` +
      menu option "external-deps". Discovery → ticket selection →
      dedupe confirmation → atomic write (backup + write + re-scan +
      state flip + history append) com rollback em falha.
- [x] **Testes novos** em `tests/unit/test_l1_blocked_state.py`:
  19 testes cobrindo state enum, blocking_deps semantics,
  list_blocked_features, validator schema (accept/reject), record_external_dep
  helper, implement refusal + auto-recovery, status board rendering.

**Princípio preservado:** Decision 9 (12 commands — unblock vive dentro
de `forge reconfigure`), Decision 10 (zero flags — interactive menu),
discipline §1 (3-caminhos canônico no refusal), §3 (`.bak` per file
afetado), §7 (pause vs abort intactos — blocked-on-external é
sibling, não replacement).

**O que ficou como TODO residual (v1.1+):**

- [ ] **MCP polling pra auto-unblock** — Jira/Linear webhook →
      `forge ingest --event external-dep-resolved` → auto-flip. Stub
      documentado em `docs/lifecycle/memory-and-graph.md §Out of scope
      for v1`. Decisão consciente: trust gate requer human confirmation
      em v1.0; webhook misfire pode mentir pro implement.
- [ ] **`forge undo` para "external-dep-marked-resolved"** — engine
      grava `history.jsonl` com kind = "external-dep-marked-resolved" e
      ticket id, então undo poderia restaurar `resolved-at: null` nas N
      entries afetadas. Não implementado em v1.0; via edição manual
      do task-contract por enquanto.
- [ ] **`forge plan` mid-implement add external dep** — usuário descobre
      mid-task que precisa esperar backend. Atualmente: edit
      task-contract manualmente. v1.1+: `forge reconfigure` →
      "adicionar dep externa a task em flight" com confirmação que
      flippa state.
- [ ] **TTL/stale warnings** — quando uma dep está aberta há >14d, doctor
      poderia alertar. v1.1+ quando houver dados sobre o que "stale"
      significa em prática.
- [ ] **Cross-feature dedupe** — mesmo ticket afetando features
      diferentes (BACKEND-1284 em lembrete-rega + bonsai-detail).
      Hoje `forge reconfigure` resolve por feature. v1.1+: 1
      confirmação resolve em todas as features.
- [ ] **Retrospective awareness** — quando uma feature destrava via
      external-dep-resolved, retrospective deveria notar "tempo morto
      = X dias por dep externa" pra L2 promovendo padrão de planning
      (ex.: features que tocam weather API sempre adicionar BACKEND-deps).

**Validation pendente para piloto smoke test:**

- [ ] Smoke test happy: planejar feature com dep externa real (e.g.,
      lembrete-rega waiting on BACKEND-1284), verificar que Cena 10.5
      captura a dep, task-contract-writer emite `depends_on_external`
      em `TASK-NNNN.yaml`, readiness emite `ready-with-blocks`,
      `forge implement` rejeita TASK-bloqueada com 3-caminhos e
      aceita TASK-livre.
- [ ] Smoke test unblock: marcar BACKEND-1284 como resolved via
      `forge reconfigure`, verificar state flipa pra `implementing`,
      `.bak` criado, history.jsonl com kind=external-dep-marked-resolved,
      `forge implement` aceita a task agora destravada.
- [ ] Smoke test board: rodar `forge status` com feature blocked,
      verificar seção "blocked on external" com ticket id visível e
      hint de desbloqueio.
- [ ] Smoke test multi-dep-same-ticket: feature com TASK-A e TASK-B
      ambas deps de BACKEND-1284, verificar que reconfigure dedupa
      e marca as 2 atomically.
- [ ] Smoke test forward-compat: status.json escrito antes do Gap 8
      (sem `state: blocked-on-external` no enum, sem
      `depends_on_external` em task-contracts) carrega sem
      crash + state default funciona.
- [ ] Smoke test concorrência: `forge implement` retrieve refuse em
      task blocked enquanto outro processo escreve `resolved-at` —
      garantir que o file_lock em status.json (já existente) protege
      a transição.

**Arquivos modified (Gap 8):**

- `docs/schemas/memory.md` — `blocked-on-external` no state enum +
  semantics + MEM-L1-008 atualizada
- `docs/design/07-discipline.md` — nova §9 "External dependencies"
  + cheat-sheet entry
- `templates/task-contract.template.yaml` — `depends_on_external`
  field com schema documentado
- `agents/planning-conductor.md` — Phase 2 external-dep drill-down +
  Phase 4 context-pack injection + closing format ready-with-blocks
- `agents/task-contract-writer.md` — context pack `external-deps` +
  Phase 4 step 6 + cheat-sheet additions + `after:External Dependencies`
  extension-point
- `agents/readiness-reviewer.md` — Phase 4.5 external deps audit +
  verdict matrix + JSON output + Example 4
- `docs/ux/forge-plan-roteiro.md` — Cena 10.5 (4 sub-cenários)
- `docs/ux/forge-implement-roteiro.md` — Cena 2.5 (4 sub-cenários)
- `docs/ux/forge-reconfigure-roteiro.md` — sub-cena 5.6 + menu option
- `engine/memory/l1.py` — state enum + 3 helpers (`is_blocked`,
  `blocking_deps`, `list_blocked_features`) + `_feature_tasks_dir`
- `engine/plan.py` — `record_external_dep()` helper + reads/writes
  elicitation.yaml.external-deps
- `engine/implement.py` — `external_deps` field, refusal flow,
  auto-recovery, exit code 7
- `engine/status.py` — board reescrito com 4 sections + summary helper
- `engine/reconfigure.py` — `_handle_external_deps` + menu option
- `validators/validate_task_contract.py` — schema validation pra
  `depends_on_external`
- `tests/unit/test_l1_blocked_state.py` — NEW, 19 testes

### Gap 9 — Cenário C2: Plataforma nova mid-projeto (multi-target retroativo) ✅ resolvido 2026-06-03 (extends-feature mechanic; multi-target out-of-scope permanente)

**Severidade:** alta (histórico). Time decide adicionar Apple Watch (ou
Wear OS, TV) a features existentes + futuras. Cards canônicos atuais
cobrem só Android/iOS — Watch/TV/Wear caíam em Gap 5 (D2). Mas há
dimensão extra original: **features já feitas não ganham nova plataforma
retroativamente**, e forge não tinha mecânica explícita pra isso.

**Origem (histórico):** cards `watchos-screens`, `watchos-navigation`,
`wear-os-screens` inexistentes em catálogo v1; kmp-shared não declara
`watchOSArm64` target; inventory design-system não distingue componentes
por target; feature done é done — forge não tinha `forge extend-feature
{slug} --add-platform watchos` (proibido por decisão 9 + 10).

**Remediação proposta originalmente (v1.1, pré-revisita):**

- [ ] Cards multi-target v1.1: `watchos-screens`, `watchos-navigation`,
      `wear-os-screens`, `tv-screens` (paralelos a swiftui-screens,
      swiftui-navigation, compose-screens)
- [ ] `workflow-config.yaml.targets: [android, ios, watchos]` declarativo;
      cards condicionais por target ativado
- [ ] Inventory design-system schema upgrade:
      `components/MeoButton.platforms: [android, ios, watchos]` por
      componente
- [ ] Convenção "extension feature" pra features feitas que ganham nova
      plataforma: `forge plan {slug}-watch-extension` com
      `extends-feature: {slug}` no intake — auto-importa context da feature
      pai e gera só tasks da nova plataforma

**Solução aplicada — Re-escopo 2026-06-03 (extends-feature mechanic ship; multi-target out-of-scope):**

Revisita Gap 9 desacoplou a mecânica `extends-feature` (Opção A das
alternativas estudadas) do escopo multi-target. User explicitou
"feature-forge cobre mobile (Android + iOS + KMP), não tem planos pra
watchOS/Wear/TV". Resultado: **a mecânica de feature derivada virou um
pattern leve product-derived** (sem cards novos, sem mudança no enum
`platforms`, sem upgrade de inventory schema), e os 4 cards multi-target
+ workflow-config.targets aditivo + inventory.platforms field saíram
permanentemente do escopo do projeto. Sinergia confirmada com Gap 5:
plataforma exótica futura (improvável dado o positioning) entra via
overlay local, não via canon expansion.

- [x] **Schema `status.json` ganha 2 campos aditivos** —
      `extends-feature: null | "{parent-slug}"` + `parent-feature: null |
      "{parent-slug}"` (reverse pointer pra otimizar queries L1).
      `docs/schemas/memory.md` documenta + MEM-L1-008 ganha rule: se
      `extends-feature != null` → parent existe em
      `.claude/memory/L1/{parent-slug}/` E `parent.state == "done"`.
      Forward-compat: status.json pré-Gap 9 carregam normais (default null).
- [x] **`L1State` em `engine/memory/l1.py` ganha 2 fields + helpers** —
      `extends_feature`, `parent_feature`, `parent_state(slug, root)` +
      `list_extensions_of(parent_slug, root)`. Round-trip + invalid-value
      rejection cobertos por testes novos.
- [x] **Template novo bloco condicional** em
      `templates/feature-intake.template.md` — §Extension context
      renderizado quando `extends-feature` está setado (parent feature,
      parent shipped, scope of extension, reuse from parent,
      out-of-scope vs parent). Ausente quando null — feature standalone
      fica exatamente como antes.
- [x] **UX Cena 1 do `forge plan` ganha 4º caminho "Estender"** —
      `docs/ux/forge-plan-roteiro.md` Cena 1 detecta `state: done` e
      adiciona 4º caminho (Retomar / Nova / **Estender** / Abortar).
      Conductor sugere slug derivado `{parent}-extension`; user
      customiza pra suffix descritivo. Cena 1 não muda quando state
      != done.
- [x] **Engine `engine/plan.py` Cena 1 detection branch** — 4º caminho
      condicional + context-pack import (lê parent's `status.json`,
      `hypothesis.yaml`, `data-contract-spec.yaml`, `screen-analysis.yaml`,
      `tech-spec.md`, `existing-helpers.yaml`); popula extension's
      context-pack com baseline herdado + delta como intent.
- [x] **Validator novo `validators/validate_extension_feature.py`** —
      EXT-001 (parent slug existe), EXT-002 (parent.state == "done"),
      EXT-003 (slug derivado != parent), EXT-004 (dedupe: nenhum outro
      slug derivado declara o mesmo `extends-feature` + `extension-scope`).
      3-caminhos canônico no fail (discipline §1). Inativo quando
      `extends-feature` é null (no-op pass).
- [x] **Agents patcheados:**
  - `agents/planning-conductor.md` Phase 1 step 5 (Extension context
    import quando `extends-feature != null`); Phase 4 wave dispatch
    abreviado (Wave A intake variant, Wave B focado no delta, Wave D
    `allowed_files` herda baseline + delta); Phase 6 retrospective
    variant (herança vs adição, sem 5-whys); closing format ganha
    extension mention (parent + scope delta).
  - `agents/feature-intake-agent.md` — extension block instructions
    (elicita §Extension context fields quando hypothesis declara
    `extends-feature`).
  - `agents/tech-spec-agent.md` — context-pack ganha `extends-feature`
    + `parent-baseline` fields como read-only references; sem mudança
    em rendering (extension é product-derived, segue product rendering).
  - `agents/retrospective-agent.md` — extension semantics (4 perguntas:
    herdei literal / delta mínimo / criei do zero apesar de extension /
    sinais pra refactor pra shared base).
- [x] **Discipline §10 nova** em `docs/design/07-discipline.md` —
      formaliza quando aplica, distinção formal (tabela 4-eixos vs
      refactor/bugfix/standalone), wave dispatch semantics, filesystem
      layout (`L1/{parent}-{suffix}/`, **não** `non-product/`),
      hypothesis schema, Phase 6 retrospective (herança vs adição),
      cheat-sheet entry, cross-link com §8 + §9 + Gap 5.
- [x] **Tests** — `tests/unit/test_extension_feature.py` + extensão de
      `tests/unit/test_plan_extension.py` (round-trip L1State,
      `parent_state` + `list_extensions_of` helpers, validator happy
      path + 4 fail paths, Cena 1 4º caminho detection).

**Princípio preservado:** Decision 9 (12 verbos — sem `forge
extend-feature` novo; "estender" vive dentro de `forge plan` Cena 1),
Decision 10 (zero flags — drill-down conversational), Decision 22 (zero
deps em outras skills), Decision 28 (overlay não exigido — extension
não requer cards novos). Nenhuma decisão locked revisitada.

**OUT-OF-SCOPE explícito (decisão consciente, permanente):**

Itens da remediação original do Gap 9 que **não entram** neste ciclo —
e ficam permanentemente fora do escopo do projeto até demanda real
mudar a posição (improvável dado o positioning "feature-forge cobre
mobile = Android + iOS + KMP"):

- Cards canon `watchos-screens`, `watchos-navigation`, `wear-os-screens`,
  `tv-screens` — feature-forge cobre Android + iOS + KMP; watchOS / Wear
  OS / tvOS é out-of-scope deliberado. Quando surgir necessidade
  (improvável), o caminho oficial é Gap 5 overlay local — não canon
  expansion.
- `workflow-config.platforms.active` upgrade pra suportar watch / wear /
  tv — enum permanece `[android, ios, kmp, web]`. Web já é coberto;
  watch / wear / tv permanecem fora.
- `inventory.design-system.components.platforms: [list]` field — não
  agrega valor sem multi-target. Inventory schema permanece sem o field.
- Labels `watchos-*`, `wear-os-*`, `tv-*` no catálogo — **nem como
  Reservada** (Reservada implica "vem v1.x+ por demanda"; aqui é
  permanente out, não Reservada).
- `forge extend-feature {slug}` como verbo novo — Decision 9 (12 verbos)
  preservada; "estender" vive dentro de `forge plan` via detection no
  Cena 1 (4º caminho conditional quando state=done).

Este scope-out é **decisão arquitetural consciente**, não TODO
residual. Não há roadmap pra v1.x+ trazer watchOS/Wear/TV de volta —
demanda real teria que reabrir a revisita Gap 9 inteira.

**O que ficou como TODO residual (v1.x+):**

- [ ] **Wave A skipping logic completo no conductor** — Wave 2 cobriu a
      entrada Cena 1 (4º caminho detection) e patchou o agent prompt da
      planning-conductor com Phase 1 step 5 (extension context import).
      Lógica de skip de elicit no conductor (não re-perguntar user value
      / business outcome / persona que a pai já tem) está documentada no
      prompt mas execução real só é exercitada com piloto. Quando
      smoke test E2E real rolar, o agent prompt provavelmente ganha
      refinamento; documentado aqui pra não pular silente.
- [ ] **`validate_extension_feature` wiring na cascade `forge verify`** —
      hoje validator existe + roda standalone + tests pass. Cascade
      discovery é via cards (cada card declara que validators correm
      contra seus artefatos); extension validator é cross-cutting
      (roda em qualquer feature com `extends-feature != null`,
      independente de card). Wiring atual: validator não está cadastrado
      em `engine/verify.py` cascade explícita — espera card "core"
      transversal OU hook explícito em `engine/verify.py` quando feature
      tem `extends-feature` setado. Decisão consciente: shipping
      validator + testes verdes + smoke manual cobre o caso; cascade
      automatic em `forge verify` é refinamento que entra em v1.2 quando
      o pattern "cross-cutting validator" tiver 2+ casos (até hoje só
      este).
- [ ] **Smoke test E2E real** — Mandamento "verde antes de pronto"
      cumprido (unit + integration verdes; suite total 637 passing + 12
      skipped). E2E real (dummy parent feature done + `forge plan` +
      escolher Estender + verificar L1 + intake + validator) seria
      refinamento de fixture pra v1.2.x. Smoke manual abaixo cobre o
      gap até lá.

**Power-review fix loop (post-ship 2026-06-03) — findings menores
deferred:**

O REVIEW.md em `.planning/gap9-extends-feature/REVIEW.md` listou 12
findings (0 critical / 5 warning / 7 info). Fix loop aplicou W-002 +
W-003 + W-005 + I-002 + I-007 antes do doc-sync; W-004 (commit fora de
escopo `e0af68a chore(claude): migrate hooks`) foi aceito com nota no
commit body (Caminho B do REVIEW); W-001 ficou como o item dedicado
acima ("validate_extension_feature wiring") — decisão consciente
documentada. INFO findings remanescentes como TODOs leves v1.x+:

- [ ] **I-001** — Validator emite `EXT-001` quando `status.json` está
      ausente do parent_dir (parent dir existe mas incompleto).
      Tecnicamente o contrato do EXT-001 documentado é "parent slug
      exists as a sibling L1 directory" — o caso melhor casaria com um
      sub-código (e.g., `EXT-001b` ou `EXT-005 parent incompleto`).
      Mensagem é clara o suficiente hoje pra operador entender; refinar
      taxonomy é polish v1.x+.
- [ ] **I-003** — Validator EXT-004 com scope vazio: comportamento
      intencional (empty-scope-collision documentado no docstring) pode
      confundir operador que ainda não declarou `extension-scope` (sinal
      de "incompleto" mais do que "duplicado"). Trade-off: warn-shape
      permite passar verify; fail-shape (atual) força resolução agora.
      Avaliar warn-shape em v1.x+ se feedback de campo aparecer.
- [ ] **I-004** — Tests `tests/unit/test_plan_extension.py` usam
      `monkeypatch.setattr("engine.plan.question.ask", lambda ...)`
      direto na signature interna de `question.ask`. Funciona, cria
      acoplamento ao 3-arg + kwargs. Considerar v1.x+ um fake-input
      dispatcher dedicado (`tests/_fakes/question_fake.py`) com API
      estável. Não bloqueia merge.
- [ ] **I-005** — `docs/schemas/memory.md:288-307` exemplo `status.json`
      não mostra `shipped-at` (mesmo agora sendo escrito por
      `engine/implement.py` na transição state=done — fix W-002). Quando
      v1.x+ revisar o schema doc, adicionar `"shipped-at":
      "2026-05-28T18:00:00Z"` em features done e `null` em features
      pre-done. Mantém schema doc em sync com runtime.

**Validation pendente para piloto smoke test:**

- [ ] Smoke happy: feature parent done + `forge plan {parent}` oferece
      4º caminho "Estender" + L1 nova grava `extends-feature: {parent}` +
      intake renderiza §Extension context.
- [ ] Smoke negativo: parent em `state: implementing` → 4º caminho NÃO
      aparece (só 3 caminhos: Retomar / Nova / Abortar).
- [ ] Smoke negativo: slug derivado duplicate (extension já existe com
      mesmo slug) → 3-caminhos canônico.
- [ ] Smoke validator EXT-001: criar L1 extension apontando pra parent
      inexistente → validator emite `EXT-001` fail com 3-caminhos.
- [ ] Smoke validator EXT-002: parent em `state: implementing` →
      validator emite `EXT-002` fail com 3-caminhos.
- [ ] Smoke validator EXT-003: slug derivado == parent slug (sanity) →
      validator emite `EXT-003` fail.
- [ ] Smoke validator EXT-004: 2 extensions do mesmo parent com mesmo
      `extension-scope` → validator emite `EXT-004` fail (dedupe).

**Arquivos modified (Gap 9):**

- `docs/schemas/memory.md` — `extends-feature` + `parent-feature` em
  status.json + MEM-L1-008 atualizada
- `engine/memory/l1.py` — `L1State` ganha 2 fields + `parent_state` +
  `list_extensions_of` helpers
- `engine/plan.py` — Cena 1 4º caminho branch + context-pack import
- `templates/feature-intake.template.md` — §Extension context bloco
  condicional
- `docs/ux/forge-plan-roteiro.md` — Cena 1 ganha 4º caminho Estender
  com sub-cenários
- `agents/planning-conductor.md` — Phase 1 step 5 extension context +
  Phase 4 wave dispatch (variants A/B/D) + Phase 6 retrospective
  variant + closing format extension mention
- `agents/feature-intake-agent.md` — extension block elicitation
- `agents/tech-spec-agent.md` — context pack extends-feature +
  parent-baseline references
- `agents/retrospective-agent.md` — extension semantics (4 perguntas)
- `validators/validate_extension_feature.py` — NEW, EXT-001..EXT-004
- `tests/unit/test_extension_feature.py` — NEW, suite completa
- `tests/unit/test_plan_extension.py` — NEW, Cena 1 4º caminho
- `docs/design/07-discipline.md` — §10 nova (Extension feature) +
  cheat-sheet entry

### Gap 10 — Cenário D3: Monorepo cross-project UX

**Severidade:** média. Decisão 14 cobre o caso básico (1 config por
sub-projeto). Mas monorepos com forte cross-cutting (mobile+backend+web do
mesmo produto) sofrem com features cross-project, inventories sem
cross-reference, e ausência de status agregado.

**Origem:** L4 cross-project patterns out-of-scope v1 explícito em
`memory-and-graph.md`; features cross-project (endpoint+UI) viram 2 features
ligadas só por ticket externo (também afetado por Gap 8); inventories de
i18n entre sub-projects não são cross-checkáveis; CI hooks por sub-project
não correlacionam PRs.

**Remediação proposta (v1.1):**

- [ ] `forge status` ganha prompt interativo: "ver só esse sub-projeto ou
      varrer todos?" — escaneia `**/.claude/workflow-config.yaml` no parent
      dir (preserva decisão 10, zero flags)
- [ ] L4 cross-project habilitado por opt-in:
      `workflow-config.yaml.shared-memory-with: ['../backend']` permite L2
      patterns cruzarem
- [ ] Documento `monorepo-feature.yaml` no parent dir linkando feature-slug
      entre sub-projetos (e.g., `weather-integration` está em
      mobile+backend)
- [ ] Inventory cross-check validator opt-in: confere consistência de
      i18n keys entre sub-projects que opt-in via shared-memory-with

### Gap 11 — Cenário E4: Compliance regulatório (LGPD/PCI/HIPAA)

**Severidade:** média-específica. Forge cobre "security thinking" via
`security-contract.yaml` na Wave C mas não compliance formal. Casos reais:
checkout PCI-DSS, app saúde HIPAA, qualquer feature brasileira LGPD.
Compliance exige artefatos extras (DPIA, threat model dedicado, scope
marking de arquivos, audit trail formal).

**Origem:** security-contract.yaml schema provavelmente não cobre DPIA
completo (data flow + lawful basis + retention + DPO contact); sem
template de threat model (STRIDE, attack trees); scope marking de arquivos
não modelado em task-contract; history.jsonl é audit interno, não atende
audit formal externo (assinatura, WORM retention).

**Remediação proposta (v1.1+):**

- [ ] Cards regulatórios: `lgpd-track`, `pci-dss-scope-tracking`,
      `hipaa-track`. Cada um contribui:
      - templates: DPIA-template.md, threat-model-template.md,
        scope-marking.yaml
      - validators: `scope-leak-detection.py`,
        `encryption-at-rest-check.py`, `pii-not-logged.py`
      - agent-prompts: "compliance lawyer mode" pro contract-planner-agent
- [ ] `workflow-config.yaml.compliance-track: [lgpd, pci-dss]` — opt-in
      que ativa cards correspondentes
- [ ] `task-contract.yaml.scope-tags: [pci-dss]` por task: tasks em scope
      levam validators extra
- [ ] history.jsonl extension WORM-mode opcional via filesystem flags
      pra retention legal

### Gap 12 — Cenário B4: A/B test com 2 variantes da mesma feature

**Severidade:** média-específica. Forge não tem conceito de fork/variant.
Caso comum em apps de produto (checkout A vs B, onboarding A vs B). 1 feature
= 1 slug = 1 PRD; PRD com 2 variantes formal é ambíguo no schema atual.

**Origem:** screen-analysis-agent presume 1 mockup por tela (dual mockup
quebra); analytics-spec não declara `experiment-name` + `variant-id` como
dimensions obrigatórias quando feature é A/B; estado "experiment-running"
inexistente; sem flow "promote variant" pra promover vencedor + deprecar
loser quando experimento termina.

**Remediação proposta (v1.1+):**

- [ ] Card novo `experimentation-track` ou `ab-testing-track` contribui:
      - templates: `variant-comparison-spec.yaml` (A vs B side-by-side)
      - analytics-spec extension: `experiment-name` + `variant-id` como
        dimensions obrigatórias
      - task-contract field: `variant: a | b | shared`
- [ ] Feature pode declarar `variants: [a, b]` no intake — gera 2 PRDs
      ligados, 2 screen-analysis, mas tech-spec compartilhada
- [ ] Estado intermediário `experiment-running` entre verified e done — não
      promove até experiment terminar (gradual rollout 5% → 20% → 50%)
- [ ] "Promote variant" flow: `forge plan {slug}-finalize` quando experiment
      termina — migra winner pra mainline + marca loser como deprecated

### Gap 13 — Cenário C4: Engine forge sobe de versão (schema breaking)

**Severidade:** alta na primeira transição v1.0 → v1.1. UX de migration
atualmente é escape hatch via `forge raw migrator-N-to-M` — sem UX
cinematic, sem mentor calmo, scary pra user real.

**Origem:** `forge raw` é escape hatch por design (06-command-surface §12);
migration mid-feature não documentada explicitamente (`card.md` diz
reconfigure refuses com L1 ativo, migration deveria seguir mesmo princípio);
cards locais ficam `pinned: true` e não auto-update no upgrade do forge —
drift silencioso entre canonical v1.1 e snapshot v1.0; L2 schema breaking
exige distillation; history.jsonl format change cria audit trail confuso
sem marker line.

**Remediação proposta (v1.1):**

- [ ] `forge reconfigure` ganha opção interativa "atualizar versão do forge"
      (preserva os 12 comandos, sem `forge upgrade` novo): UX guiada com
      detecção de versão, diff de schema, opção de rollback
- [ ] Pre-flight obrigatório: bloqueia migration se features `state:
      implementing|planning` — força pause primeiro (paralelo à regra
      L1-lock do card.md)
- [ ] Auto-snapshot pré-migration ampliado: workflow-config + L2 + todos
      os cards + agents snapshots — todos com `.bak`
- [ ] Transação atomic: rolls forward TODAS as dimensões juntas
      (workflow-config + cards + L2 + agents) + history.jsonl marker line
      `{"event":"schema-migration","from":1,"to":2}`
- [ ] Doctor pós-migration roda automático e exige zero issues antes de
      marcar `forge-version-lock.yaml` como atualizado

### Gap 14 — Cenário D1: Preset coverage (web, android-only, ios-only)

**Severidade:** alta-específica. Projetos web puros (React+TS) ou
single-platform (Android-only legado pré-KMP) não têm preset apropriado em
v1. Cards canônicos v1 cobrem só stack KMP-mobile. Preset coverage gap é
explícito em `filesystem-layout §1` ("planejado v1.x") mas sem timeline ou
roadmap concreto.

**Origem:** 20 cards canônicos focados em Kotlin/KMP/Compose/SwiftUI;
agent prompts treinados com exemplos KMP (vocabulary "shared layer",
"SKIE bridge" não cabe em web puro); tech-spec template é
backend-agnostic (Phase 3.5) mas §Shared (KMP) layer / §iOS / §Android
não aplicam a single-platform; inventory design-system assume Meo* +
Compose + SwiftUI — React puro com Storybook não é coberto.

**Distinção do Gap 5 (D2):** Gap 5 é "stack canônica + algumas peças
exóticas" (init detecta maioria). Gap 14 é "preset canônico errado pra
começar" (init nem decola direito).

**Remediação proposta (v1.x):**

- [ ] Cards web canônicos: `react-screens`, `next-js`, `vite-build`,
      `typescript-language`, `tailwind-design-system` — paralelos a
      compose-screens / swiftui-screens
- [ ] Presets v1.x ativados (existem como placeholders, faltam conteúdo):
      `web/`, `android-only/`, `ios-only/`, `kmp-fullstack/`
- [ ] Agent prompts ganham target-aware sections via extension-points
      (mecânica já existe via card.md — só falta material)
- [ ] Inventory extractors ganham web variants em
      `engine/inventory/design_system.py` (parser de Storybook adicional
      aos parsers Compose/SwiftUI)

### Gap 15 — Cenário D4: Brownfield com vocabulary idiossincrático

**Severidade:** média. Princípio 5 ("vocabulário nativo — lê CLAUDE.md e
rules/, usa as palavras do projeto") declara intent mas a mecânica está
parcial. Inventory captura naming patterns via regex, mas vocabulário
semântico ("Cuidador" = "user que cuida do bonsai") precisa de tradução
declarada — não inferida.

**Origem:** mecanismo concreto de "ler CLAUDE.md" não documentado além de
captura de patterns; agent prompts fixos no canonical (vocabulary
substitution não é template-substitution declarada); validators rejeitam
naming não-padrão (`Cuidador.kt` em folder `cuidadores/` pode falhar regras
que esperam `users/`); graph similarity-queries podem não casar vocabulário
do projeto.

**Remediação proposta (v1.1):**

- [ ] `inventory/conventions.yaml` ganha seção `vocabulary` explícita:
      ```yaml
      vocabulary:
        user-entity: "Cuidador"
        service: "engine"
        use-case: "Trato"
      ```
- [ ] Agent prompts ganham template substitution:
      `{{ project.vocabulary.user-entity }}` — render dinâmico no
      dispatch
- [ ] Validators ganham vocabulary-aware mode: aceita "Cuidador" se
      conventions declara user-entity = Cuidador
- [ ] `forge init` questionnaire detecta vocabulário próprio: "Detectei
      'Cuidador', 'engine' — vocabulário do projeto?" → grava em
      vocabulary

### Gap 16 — Cenário E2: Persona modes pra não-dev (PM, designer)

**Severidade:** média. Decisão 6 ("Init reveals project map") + Mentor
calmo assume usuário técnico. PM rodando `forge plan` esbarra em
elicitations técnicas ("Outbox queue vs Optimistic-write") que não tem como
responder — drill-down propõe default mas PM pode aceitar coisa errada por
não entender alternativas.

**Origem:** vocabulário técnico embutido em prompts (Firestore, SKIE,
kmp-shared); decisões de arquitetura forçadas em ambiguity-map; hypothesis
cita similarity graph que non-dev não entende; ausência de persona-aware
prompt filtering; risco de plan "tecnicamente válido mas semanticamente
errado".

**Remediação proposta (v1.1+):**

- [ ] Persona modes opt-in via workflow-config:
      `interlocutor-persona: developer | product-manager | designer`
- [ ] Modo product-manager: hide arch decisions; drill-down em UX/scope/
      business value; defer técnicas pra "depois eng decide"
- [ ] Modo designer: focus em screen states, visual decisions; defer
      everything else
- [ ] Cruza com Gap 15: persona-mode também substitui jargão técnico por
      equivalentes do vocabulary
- [ ] Automatic open-question escalation: questions técnicas em non-dev
      mode → automaticamente vira open-question bloqueante pra dev
      resolver depois
- [ ] Documentar trade-off explícito: simplicidade pra non-dev vs
      cerimônia obrigatória pra correctness técnica

### Gap 17 — Cenário E3: Escalabilidade de feature visualmente complexa

**Severidade:** média. Features grandes (onboarding com 12 telas + 8 ramos
condicionais) batem em vários gates de threshold do planning-conductor.
Caso comum (todo app tem onboarding ou wizard multi-step).

**Origem:** ambiguity-map declara "27 nós + threshold 8 unresolved → refuse"
em planning-conductor §Phase 2 — pode bater em features grandes;
state-matrix com 8 ramos pode não ser modelado first-class no schema;
navigation-spec.yaml conditional branching pode não ser first-class;
screen-analysis-agent context pack infla com 12+ mockups; task-breakdown
12 tasks UI tecnicamente viável mas frágil em deps cross-screen.

**Remediação proposta (v1.1):**

- [ ] Ambiguity-map threshold adaptive: feature com N telas > 5 expandir
      threshold pra 8 × log(N) ou similar (vs 8 fixo). Documentar
      heurística
- [ ] `navigation-spec.yaml` schema first-class para conditional branching:
      ```yaml
      conditional-routes:
        - when: user.is-new
          to: screen-3
          else: screen-5
      ```
- [ ] screen-analysis-agent pipelining: processa mockups em batches
      paralelos quando N > 5, evitando context pack > 100kb
- [ ] task-breakdown ganha `screen-group` opcional (paralelo ao
      `release-group` do Gap 7) — agrupa tasks por tela
- [ ] Validator advisory: feature com >10 telas → sugere split
      ("onboarding tem 12 telas — considere split?"). Não bloqueia, só
      sugere via 3-caminhos discipline (07-discipline §1)

### Gap 18 — Detecção de helpers/extensions existentes no tech-spec ✅ resolvido 2026-05-30

**Severidade:** média. Brownfield (MeoBonsai, outros projetos modularizando)
acumula dezenas de extensions em `shared/core/util/`, `shared/feature/*/util/`.
Tech-spec-agent não detectava reuso — propunha helpers novos como se não
houvesse prior art, criando duplicação latente.

**Origem:** prompt do `tech-spec-agent` explicitamente proíbe consultar
codebase graph live ("never fetch from network, codebase graph, or Jira") —
restrição é deliberada (determinismo + reprodutibilidade do dispatch). Sem
mecanismo de prefetch, agente não tinha acesso ao inventário de helpers
existentes.

**Solução aplicada (não criar inventário novo, usar graph existente):**

- [x] **Q11 — `reusable-helpers`** adicionada ao catálogo canônico
      (`docs/schemas/graph.md`). Query lista funções `kind='fun'` no módulo
      `shared` cujos signatures referenciam entity types da feature OU vivem
      em paths de utility (`/util/`, `/extensions/`, `/core/`).
- [x] **`engine/graph/queries.find_reusable_helpers()`** implementa Q11
      programaticamente. Parâmetro `entity_types` extraído pelo conductor
      de `data-contract-spec.yaml`. ~70 LOC.
- [x] **`forge graph` menu** ganhou opção 11 (`reusable-helpers`) —
      interactive prompt pra tipos de entidade.
- [x] **`planning-conductor.md` Phase 4.5** (entre Wave B e Wave C):
      conductor parseia entities do data-contract-spec, roda Q11, persiste
      resultado em `.claude/memory/L1/{slug}/existing-helpers.yaml`. Empty
      result é normal — sempre escreve arquivo.
- [x] **`tech-spec-agent.md` context pack** atualizado para incluir
      `existing-helpers.yaml`. Phase 5 (CFR scan) reescrita em 2 steps:
      Step 1 checa reuse contra existing-helpers antes de Step 2 propor
      novos.
- [x] **`tech-spec.template.md` §14** splittado em 3 sub-seções: `14.1
      Reuse existing` (omitida em greenfield), `14.2 Propose new — qualifies`,
      `14.3 Propose new — defer to rule-of-three`. Output JSON do agent
      ganhou 3 counters distintos.

**Princípio preservado:** tech-spec-agent continua sem acesso live ao graph.
Conductor pré-computa via Q11 e injeta resultado no context pack
(deterministic-context discipline mantida — agente recebe sempre o mesmo
input dado o mesmo estado de repo).

**Arquivos modificados:**

- `docs/schemas/graph.md` — Q11 canonical query
- `agents/planning-conductor.md` — Phase 4.5
- `agents/tech-spec-agent.md` — context pack + Phase 5 (2 steps) + output JSON
- `templates/tech-spec.template.md` — §14 splittado em 14.1/14.2/14.3
- `engine/graph/queries.py` — `find_reusable_helpers()`
- `engine/graph_cli.py` — opção 11 no menu interativo

**Validação pendente:**

- [ ] Rodar `pytest tests/unit/test_graph_queries.py` (se existir cobertura
      pra queries.py) — atualmente sem teste pra `find_reusable_helpers`
- [ ] Smoke test: rodar `forge graph` → opção 11 num projeto com graph
      construído (precisa MeoBonsai com `.claude/graph.db`)
- [ ] Smoke test: rodar `forge plan` numa feature de teste e verificar
      que `existing-helpers.yaml` é escrito após Wave B

**Expansão 2026-06-01 — init-time + incremental + 6 categorias** ✅

A solução original cobria APENAS o momento de planejar uma feature
(prefetch de helpers via Q11 antes de tech-spec). Não cobria **duplicações
já existentes no codebase** nem **edits que introduzem novas duplicações**.

Expansão completa shipada em 2026-06-01 — feature-forge agora "nasce com
inteligência": primeira vez que vê o projeto (`forge init` Step 11.5), já
detecta o backlog acumulado.

- [x] **6 categorias de finding** (`engine/graph/duplicates.py`):
  - `duplicate-within-module` (Kotlin extension repetida em 1 módulo, conf 0.95)
  - `duplicate-cross-module` (sibling modules → smallest-common-ancestor
    via parsed Gradle dependency closure, conf 0.85)
  - `redundant-platform-specific` (Android Kotlin idêntico a
    `commonMain` shared, conf 0.90)
  - `near-duplicate` (mesma signature, body_hash diferente — drift signal,
    conf 0.40, manual review demanded)
  - `kmp-migration-candidate` (Swift extension ↔ Kotlin shared com token
    Jaccard ≥0.4, conf 0.50–0.75 escalando com similarity)
  - `duplicate-ts-helper` (TypeScript top-level duplicado num módulo,
    conf 0.95)
- [x] **Schema v2** (`engine/utils/sqlite_io.py`): colunas
  `files.source_set` + `symbols.{receiver_type, body_hash, body_tokens,
  modifiers}`, tabelas `module_deps` + `reuse_findings` +
  `reuse_finding_locations`.
- [x] **Parser overhaul** (Kotlin / Swift / TS): visibility agora
  persistida (era hardcoded "public"), signature normalizada, body
  extraction brace-aware em `engine/graph/_body_text.py`, body_hash
  (SHA-1[:16]) + body_tokens (JSON) para Jaccard cross-language. Swift
  two-pass captura receiver de `extension Type { func ... }`.
- [x] **Module inference** (`engine/graph/gradle_modules.py` +
  `gradle_deps.py`): settings.gradle parsing com longest-prefix match
  (suporta `:shared:feature:auth`, `:androidApp:feature:bonsai`, etc.) +
  build.gradle parsing → transitive closure → smallest-common-ancestor
  para `duplicate-cross-module` target inference.
- [x] **Q11 backward-compat**: filtro `f.module = 'shared'` → `LIKE
  'shared:%'` para multi-módulo shared.
- [x] **Q12–Q17 queries** (`engine/graph/queries.py`) + opções 12–17 no
  menu `forge graph` + `r` (combined view).
- [x] **Init Step 11.5** (`engine/init.py`):
  `queue_proposals_from_table` após graph build → 6 novos `kind` em
  `proposed-evolutions.yaml` reviewable via `forge evolve`.
- [x] **Init Step 11.6** (`engine/init.py`): escreve
  `.claude/hooks/post-edit-detect-duplications.sh` (opt-in via
  `.claude/settings.local.json`).
- [x] **Apply integration com Gap 2** (`engine/graph/reuse_apply.py`):
  6 novos `kind` no `_VALID_KINDS` do distiller. Apply renderiza
  `templates/feature-intake-refactor.template.md` + escreve L1
  `status.json` com `subtype="refactor"` → `forge plan {slug}` detecta e
  pula Wave A discovery (Gap 2 integration nativa).
- [x] **Reconfigure rebuild hook**: `_handle_graph` re-queue após
  rebuild — idempotente por fingerprint.
- [x] **Doctor** (`engine/doctor.py`): `_check_reuse_findings`
  aggregated por categoria.
- [x] **Incremental detection** (`engine/graph/incremental.py`):
  `detect_after_update` re-parsa arquivos editados, roda mini-detection
  e retorna findings novos. Subcomando `forge graph detect-incremental
  <file>` non-interactive para hook entrypoint.
- [x] **Tests**: 20 unit tests novos em
  `tests/unit/test_reuse_intelligence.py` (body extraction, gradle
  parsing, parser fields, end-to-end pipeline, apply + status.json).
  **367 passed / 0 regressões.**
- [x] **Smoke test MeoBonsai**: detecta
  `FirebaseAnalytics.logEventSafely` como `duplicate-cross-module`
  através de `:shared:feature:home/auth/bonsai`, suggested target via
  closure = `:shared:resources/.../util/` (493 files, 3528 symbols,
  10.3s).
- [x] **Schema docs**: `docs/schemas/graph.md` +
  `docs/schemas/proposed-evolutions.md` ganham seção "Reuse Intelligence
  (schema v2)".

**Princípios preservados**:
- Discipline §4 (deterministic context) — apply NUNCA mexe em código
  diretamente; só materializa intake stub e delega refactor flow.
- Discipline §5 (rejection veto) — fingerprints SHA-256 64-char
  compatíveis com `rejected-evolutions.yaml`. Rejeitar uma vez
  persiste.
- Decision 9 + 10 (12 verbos, zero flags) — `forge graph detect-incremental`
  é subcomando (positional argv), não flag.

**Conhecidos limites v1.1**:
- `kmp-migration-candidate` confidence é shallow (token Jaccard, não AST
  semântico). False positives possíveis — confidence baixa força revisão
  manual; rejection veto persiste decisão.
- Hook script é escrito no init, mas wiring em
  `.claude/settings.local.json` é manual (opt-in por design — não queremos
  surpreender o usuário).
- Gradle dependency parsing cobre `implementation(project(...))` e
  variantes comuns. DSL Kotlin avançado ou `includeBuild` exigem extensão
  futura.

### Gaps pós-rules-system (2026-06-01)

Itens emergidos durante a instalação do Claude Code rules system (CLAUDE.md
+ `.claude/rules/` + 4 hooks + 36 integration tests). Não bloqueiam o
rules system v1, mas merecem cobertura futura.

- **forge audit-rules** — comando que audita git log + `.claude/state/load-bearing-edits.jsonl` pra verificar conformidade com Mandamento 0 (orchestrator não escreveu direto) + ceremony de "Revisita decisão N" + doc-sync per commit. Mencionado em `.claude/rules/README.md` §Auditoria. Target v1.2+.
- **test_build_full_creates_meta_schema_version** — teste assume `meta.schema_version == "1"` mas `engine/utils/sqlite_io.py:20` declara `SCHEMA_VERSION = "2"` desde commit `65c358c` (reuse-intelligence schema bump). Fix: atualizar test pra ler `sqlite_io.SCHEMA_VERSION` em vez de hardcoded "1" — OU regenerar a fixture meobonsai pra schema v2. Pré-existente, não causado pelo rules system. **Re-surfaced 2026-06-01 em PR #1 final verification** — não bloqueia rapid lane (458 passing) nem `forge verify`, só atinge a integration lane com fixture MeoBonsai. Quick fix agendado pra v1.1.1.
- **Hooks Claude Code — observabilidade em subagente** — doc oficial (https://code.claude.com/docs/en/hooks) confirma que `PreToolUse`/`PostToolUse` disparam em subagentes; o JSON de input inclui `agent_id` e `agent_type` (presentes só em subagent context). Smoke 2026-06-01 confirmou via side-effect (`load-bearing-edits.jsonl` gravado de dentro de subagente) que **PreToolUse de fato dispara**; contudo investigação subsequente observou que a entrega ao hook script é **inconsistente em prática** — uma segunda passada de Edit no mesmo subagente não produziu side-effect nem entrada no debug log instrumentado, indicando que nem toda tool call de subagente é encaminhada aos hooks. Adicionalmente: stderr do hook não aparece de forma confiável no transcript do subagente mesmo quando o hook executou. Gaps menores pra revisão futura: (a) próximas revisões dos scripts devem logar `agent_id` no audit JSON quando presente, pra facilitar correlação com runs específicos; (b) ferramentas de audit do projeto devem priorizar side-effect persistente sobre stderr capture; (c) anotar reprodutor mínimo da inconsistência observada e considerar abrir bug-report upstream pra Anthropic se reproduzir consistentemente. Target v1.2+ (não bloqueia operação — Mandamento 0 segura o orchestrator via CLAUDE.md mesmo se hooks falharem silentemente).
- **D6 phase lock context-manager refactor (review MD-03)** — surfaced 2026-06-01 durante review do round PR #1 bloqueador. O atual flag-pattern de release em `engine/implement.py` (var `lock_released` + `finally` backstop) é **correto** e tem regression test (`tests/unit/test_implement_lock_release.py`), mas é estruturalmente frágil: futuros contributors adicionando return paths novos dentro do `try` block podem esquecer de setar a flag e introduzir leak. Refactor proposto: encapsular o lock como context manager (`with acquire_phase_lock(...) as lock:`) — release vira invariant da própria abstração. Não-bloqueante; agendado pra v1.1.1.
- **D1 swift `"""` test docstring cosmético (review LO-01)** — surfaced 2026-06-01. O test pin de A5 (`tests/unit/test_body_text_swift_triple_quote.py`) cobre o caso comportamental mas o docstring de uma das funções helper poderia ser mais explícito sobre por que Swift partilha o trigger de triple-quote com Kotlin. Pure cosmetic; sem impacto em comportamento ou cobertura. v1.1.1.

### Gaps surfaced em PR #1 round 2 (2026-06-02)

Itens emergidos durante o round 2 do PR #1 (30 commits aplicados sobre o que ficou do master review). Nenhum bloqueia merge; cobertura agendada pra v1.1.1+.

- **plan.py `phase_lock_held` context manager migration deferred** — surfaced 2026-06-02 durante R2.7 (MD-03). O refactor do flag-pattern pra CM ficou só em `engine/implement.py`; `engine/plan.py` tem múltiplos deferred paths via `_persist_deferred` que precisam de brainstorm focado antes de migrar (não dá pra trivial drop-in — alguns paths espalham release ao longo de várias funções). Target v1.1.1.
- **plan.py happy-path sentinel orphan** — surfaced 2026-06-02 durante R2-D13 análise. Linha ~1108 (`final_state`) seta `phase_lock = None` via `write_l1_status` mas **não remove o sentinel `.phase-lock` file**. Resultado: sentinel órfão no disco mesmo após happy path completar. Recovery atualmente manual: `rm .planning/<slug>/.phase-lock`. Fix: chamar `release_phase_lock` no happy path antes (ou junto da) migração CM acima. Target v1.1.1.
- **A13 `IN`-clause >999 findings ceiling** (review IN-01, 2026-06-02) — `list_reuse_findings` colapsou N+1 → single JOIN usando `WHERE finding_id IN ({placeholders})`. SQLite default `SQLITE_MAX_VARIABLE_NUMBER=999` quebra se `len(finding_ids) > 999`. Chunking em batches de 500 quando relevante. Não atinge projeto conhecido hoje; target v1.1.2+.
- **`forge undo` coverage para reconfigure-external-deps** (review WR-01, 2026-06-02) — `_undo_reconfigure` em `engine/undo.py` não enumera per-task `.bak` files criados pelo loop de external-deps em `engine/reconfigure.py:754` (per-task `.bak` em vez de single `.bak` no arquivo do submenu). Recovery atualmente manual via `.bak` direto no disco. Target v1.1.1.

### Gaps surfaced em PR #1 round 3 (2026-06-02)

- **`_simplify_generics` hardening pre-existing safe** (R3, parser_kotlin) — investigação durante R3 confirmou que o increment do índice no caminho normal já estava correto (não havia loop infinito real). Hardening defensivo aplicado preventivamente (ceiling de iteração tied a remaining text length + increment garantido em todos os branches) pra blindar input malformed (`"List<T"` sem fechamento) caso novo branch seja introduzido por contribuidores futuros. Sem regression real fechada — documenta o invariant "função sempre termina" como guard explícito. Tests com threading watchdog em `tests/unit/test_parser_kotlin_simplify_generics.py`.
- **R3 test hardening backlog** (defer v1.1.1) — itens identificados em review do round 3 mas adiados pra session de test-hardening dedicada: (a) `_TrackedConn.instances` global state precisa de fixture-scoped isolation pra suportar `pytest -n auto` (paralelização); (b) `time.sleep(0.030)` em phase_lock concurrency tests substituível por `threading.Event` (winner sinaliza antes do write); (c) `p.is_alive()` check pós-join em thread tests pra detectar joins incompletos. Tests passam consistentemente no setup atual (sequencial), mas refactor melhora confiabilidade quando CI migrar pra paralelização.
- **doctor.py + sqlite_io.py refactor opportunities** (defer v1.1.1) — (a) distinguir `database is locked` de outros `sqlite3.OperationalError` no doctor pra triagem mais rápida; (b) wrapping de `open_db` em `GraphError` pra API hardening. Não bloqueantes; momentum atual é shipping v1.1.

### Resumo da fila pós-stress-test (cumulativo)

Total: 18 gaps mapeados a partir de 20 cenários analisados (3 rounds).
**6 resolvidos** (Gap 18 em 2026-05-30 manhã; Gap 2 em 2026-05-30 tarde —
refactor only, spike+chore stubbed; Gap 8 em 2026-05-30 noite — schema +
engine + manual unblock, MCP polling stubbed; Gap 1 em 2026-05-30 noite — bugfix
subtype completo, A2 small-feature explicit non-goal; Gap 5 em 2026-06-02 —
card local overlay Approach A, destrava parcialmente Gap 14; Gap 9 em
2026-06-03 — extends-feature mechanic ship; watchOS/Wear/TV out-of-scope
permanente) · 12 pendentes.

| Gap | Cenário(s) | Severidade | Esforço estimado |
|---|---|---|---|
| ~~1~~ | ~~A1 — Hotfix urgente + A2 small feature~~ | ~~Média~~ | ~~1 card `quick-track` + 2 patches em prompts~~ — bugfix subtype ship 2026-05-30; A2 explicit non-goal (small features = product subtype) |
| ~~2~~ | ~~A3 + A4 — Non-product feature (spike/refactor/chore)~~ | ~~Alta~~ | ~~Novo guarda-chuva de estado + subdir + UX + 1 validator~~ — refactor ship 2026-05-30; spike+chore stubbed |
| 3 | B1 — Migração grande | Média | 1 card + schema upgrade + retrospective patch |
| 4 | C1 — PRD muda mid-implement | Baixa | 1 validator + doc + finding type |
| ~~5~~ | ~~D2 — Stack fora do catálogo~~ | ~~Alta~~ | ~~Overlay mechanism + capability ext + 4 menu options~~ — Approach A shipped 2026-06-02 (plan 13 tasks, ~1910 LOC); destrava parcialmente Gaps 9 + 14 |
| 6 | E1 — Multi-dev | — (v1.1+) | Schema upgrades + ADR |
| 7 | B2 — Feature em múltiplos releases | Média | Estado intermediário + release-group + status patch |
| ~~8~~ | ~~B3 — Dependência externa~~ | ~~Média-alta~~ | ~~Estado novo + schema task-contract + MCP polling~~ — schema + engine + manual unblock ship 2026-05-30; MCP polling stubbed para v1.1+ |
| ~~9~~ | ~~C2 — Plataforma nova mid-projeto~~ | ~~Alta~~ | ~~Cards multi-target + inventory schema + extension feature UX~~ — re-escopado 2026-06-03 pra extends-feature mechanic (Opção A); watchOS/Wear/TV out-of-scope permanente |
| 10 | D3 — Monorepo cross-project UX | Média | Status agregado + shared-memory opt-in + cross-checks |
| 11 | E4 — Compliance regulatório | Média-específica | 3 cards regulatórios + scope-tags + WORM mode |
| 12 | B4 — A/B test (2 variantes) | Média-específica | Card experimentation + analytics dimensions + estado `experiment-running` |
| 13 | C4 — Forge sobe de versão | Alta na 1ª transição | reconfigure UX + pre-flight + atomic transaction |
| 14 | D1 — Preset coverage (web/single-platform) | Alta-específica | 5 cards web + 4 presets ativados + inventory parsers |
| 15 | D4 — Brownfield vocabulary | Média | conventions.vocabulary + prompt substitution + validators |
| 16 | E2 — Persona modes (non-dev) | Média | interlocutor-persona config + prompt filtering + auto-escalation |
| 17 | E3 — Escala features visualmente complexas | Média | Threshold adaptive + conditional-routes schema + screen-group + pipelining |

Nenhum desses gaps demanda revisitar as 27 decisões locked. Todos cabem dentro
das disciplinas universais (07-discipline §1-7) e do command surface
(06-command-surface, 12 verbos, zero flags).

### Padrões cruzados — gaps que se reforçam mutuamente

Análise pós-stress-test revelou que vários gaps **compartilham mecânicas** —
atacar uma feature-base destrava múltiplos gaps:

| Mecânica base | Destrava |
|---|---|
| `status.json` schema upgrade (`active-tasks: [list]` + `state: blocked-on-external`) | Gaps 3, 6, 7, 8 |
| Card local overlay (`.claude/cards/local/` + capability-labels.local) | Gaps 5, 14 (Gap 9 re-escopado 2026-06-03 — extension mechanic é desacoplada de overlay) |
| Persona/vocabulary substitution em agent prompts | Gaps 15, 16 |
| Retrospective incremental disparado por eventos (não só "última task") | Gaps 3, 7 |
| Validators advisory com 3-caminhos (vs hard-fail) | Gaps 4, 17 |
| Non-product feature track | Gaps 1 (bugfix) + 2 (spike + refactor + chore) |

### Priorização sugerida (ordem de ataque)

Considerando severidade × esforço × multiplicador de destrancamento:

1. **`status.json` + lifecycle states upgrade** — destrava 4 gaps (3, 6, 7, 8)
   com 1 schema change + migrations
2. **Card local overlay** — destrava 3 gaps grandes (5, 9, 14), atende
   portabilidade real
3. **Non-product feature track (Gap 2)** — gap fundamental, alta severidade,
   custo médio
4. **Persona modes + vocabulary (Gaps 15+16)** — atende uso real por
   non-devs e brownfield, custo médio
5. **Migration UX (Gap 13)** — antes do primeiro v1.0 → v1.1 real

Gaps remanescentes (1, 4, 10, 11, 12, 17) podem ser endereçados conforme
demanda real surgir.

### Conclusão do stress-test

20 cenários analisados em 3 rounds. **18 gaps identificados**, dos quais
**6 foram resolvidos** dentro do ciclo v1.0+ (Gaps 1, 2, 5, 8, 9, 18) e
**10 permanecem acionáveis pra v1.1** (não-out-of-scope, não-bem-coberto-já).

Resultado positivo do stress-test: **as 27 decisões locked permanecem
intactas**. Nenhum cenário forçou revisitar princípios ou disciplinas
universais. Forge tem espinha dorsal sólida — os gaps são **superfície de
cobertura**, não fundação.

Resultado a observar: forge v1 é **excelente pro happy path** (feature de
produto Android+iOS+KMP com backend Firebase/REST, 1 dev, 5-10 tasks). Fora
do happy path, há cobertura parcial — o roadmap v1.1+ deve preencher essa
superfície sistematicamente.

## v1.2-dev follow-ups (CC gate shipping — defer-with-reason)

Itens identificados durante o ship do `check_cyclomatic_complexity` gate.
Cada um é decisão consciente de não-fazer-em-v1.2, com critério explícito
pra reentrar. Fingerprints sha256 estáveis pra silenciar re-proposals
sem mudança de conteúdo.

### Gap CC-1 — Whitelist persistente de overrides

**Categoria:** cc-gate
**Fingerprint:** `sha256(consolidate-within-module:cc-whitelist:override-no-commit-only)`
**Status:** deferred (v1.3+)

Hoje override é por commit no body (`CC-OVERRIDE: ...`). Eventualmente
projetos grandes podem querer "essa função tem cc=20 e é assim porque é
parser" como anotação permanente. v1.2-dev recusa pra evitar débito
invisível. Reentrar se ≥3 projetos consumidores pedirem em retro.

### Gap CC-2 — Cognitive Complexity (Sonar) como métrica alternativa

**Categoria:** cc-gate
**Fingerprint:** `sha256(redundant-platform:cognitive-vs-cyclomatic:v1.2-uses-cc)`
**Status:** deferred (v1.3+)

CC é métrica clássica mas Cognitive Complexity (Campbell, SonarSource)
reflete melhor leitura humana. Trocar tooling é trabalho não-trivial
(cada tool nativa tem variação) — deferido pra v1.3+ se sinal empírico
justificar.

### Gap CC-3 — CC trending em `forge graph` (Q18+)

**Categoria:** cc-gate
**Fingerprint:** `sha256(promote-to-shared:graph-q18:cc-trend-over-history)`
**Status:** deferred (v1.3+)

Adicionar query Q18+ que tabula CC por área do código e mostra trend ao
longo do histórico. Útil pra retrospective. Deferido pra v1.3+ junto com
expansão geral do graph.

### Gap CC-4 — Auto-suggest refactor LLM-powered (Phase 6)

**Categoria:** cc-gate
**Fingerprint:** `sha256(near-duplicate:cc-auto-refactor:phase-6-orchestration)`
**Status:** deferred (Phase 6)

Quando gate bloqueia, mostrar sugestão concreta de como refatorar (LLM
analisa função, propõe split). Fora de escopo v1.2-dev porque toca
subagent orchestration de forma não-trivial.

### Gap CC-5 — Per-function threshold inline annotation (REJECTED)

**Categoria:** cc-gate
**Fingerprint:** `sha256(consolidate-within-module:cc-inline-suppress:rejected-by-design)`
**Status:** rejected (não reentrar sem mudança de contexto)

Proposta de `// cc-threshold: 20` no código. **Rejeitada em favor de
override-no-commit + override-per-card**: inline espalha exceções pelo
código, dificulta auditoria, vira whitelist invisível. Documentado aqui
pra não reaparecer em retrospective.

### Gap CC-6 — CC gate delta rule (`cc_before` unpopulated) [F-001]

**Categoria:** cc-gate
**Fingerprint:** `sha256(consolidate-within-module:cc-delta-rule:cc-before-none)`
**Status:** deferred (v1.2.1+) — surfaced em PR #4 review (2026-06-04)

Estrutural presente (`CCResult.cc_before` field exists) mas funcionalmente
inerte — todos os parsers seteam `cc_before=None`. A regra `cc_after >
cc_before` nunca dispara, então funções modificadas só pegam a absolute
rule (`cc > threshold`), perdendo o sinal de regressão local.

**Por que defer:** implementar exige `git show <parent>:<file>` + re-run
de cada tool (Detekt/SwiftLint/eslint/Radon) sobre o estado anterior do
arquivo, parsing e diff. Não é fix de comentário — é feature substancial.
Roadmap provável v1.2.1 ou v1.3.

**Pré-requisito:** F-006 (rename detection `-M80%`) — JÁ aplicado no
Unreleased; sem rename detection, função renomeada vira `new` com absolute
rule e o delta nem é avaliado.

### Gap CC-7 — CC validator LOC bloat [F-003]

**Categoria:** cc-gate
**Fingerprint:** `sha256(promote-to-shared:cc-validator-split:loc-bloat)`
**Status:** deferred (próxima feature substantial do validator) — surfaced
em PR #4 review (2026-06-04)

`validators/check_cyclomatic_complexity.py` em 1067 LOC; SDD target
350-450 LOC (≈2.4x bloat).

**Por que defer:** refactor cross-cutting — extrair `_parsers/` (Detekt,
SwiftLint, eslint, Radon), `_dispatch.py`, `_override.py`,
`_classifier.py` módulos. Precisa de brainstorming + writing-plans + plano
de testes pra garantir zero behavior change. Não cabe em comment-resolution
scope.

**Sugestão:** próxima feature substancial no validator (Gap CC-6 / delta
rule F-001 ou similar) faz piggyback do refactor com test count + baseline
preserved.

## forge qa (v1.2 — entregue) — gaps deferred pra v1.x+

`forge qa` shipou na v1.2 como 13º comando (red-team adversarial gate).
Spec: `docs/superpowers/specs/2026-06-05-forge-qa-design.md`. Plano
executado: `docs/superpowers/plans/2026-06-05-forge-qa.md`. 6 itens
out-of-scope §17 do spec viraram gaps aqui + 7 deviations descobertos
durante implementação. Padrão consistente com Gap CC-* (fingerprint +
status + razão concreta pra defer).

### Gap QA-1 — Visual fidelity / a11y DOM auditors

**Categoria:** qa-extensions / opt-in
**Fingerprint:** `sha256(promote-to-shared:qa-visual-fidelity-auditor:dom-snapshot)`
**Status:** deferred (v1.x) — surfaced em §17.1 do spec qa-design

Auditor que faz snapshot de DOM/UI e compara com design-spec foge do
recorte v1 (audit de artefatos textuais). Vem como card opt-in em v1.x
(`qa-extensions: auditors: [{name: visual-fidelity, ...}]`).

**Por que defer:** card terá heavy deps (puppeteer/playwright) e expõe
matiz "QA visual" que merece release dedicado — mistura mal com a slice
textual de v1. Cumpre Decisão 22 ao manter deps pesados em card opt-in,
não no engine.

**Condição pra revisitar:** projeto consumidor pede explicitamente
auditoria visual; brainstorm separado pra escolher tooling + decidir
quando snapshot diff vira finding `qa-visual-drift` vs warning.

### Gap QA-2 — Convergence loop automatizado

**Categoria:** qa-flow
**Fingerprint:** `sha256(redundant-platform:qa-convergence-loop:auto-reqa)`
**Status:** deferred (YAGNI guard) — surfaced em §17.2 do spec qa-design

v1 = manual: user roda `forge qa` → revê findings em `forge evolve` apply
→ re-roda `forge qa` pra ver se sumiu. Loop automático "qa → evolve
apply → qa" é tentação YAGNI.

**Por que defer:** `forge evolve` é single-by-single (Decisão 26); tirar
o gate humano do meio quebra a disciplina. Loop "automatizado" só faz
sentido se houver custo real percebido — sem dado, é over-eng prematuro.

**Condição pra revisitar:** user reportar fricção concreta (ex.:
"rodei 5 vezes pra ver se sumiu, queria 1 comando"); então brainstorm
pra desenhar loop que preserva gate humano em cada apply.

### Gap QA-3 — CI / non-interactive mode

**Categoria:** qa-interface
**Fingerprint:** `sha256(promote-to-shared:qa-ci-mode:headless-output)`
**Status:** deferred (decisão 10 vale) — surfaced em §17.3 do spec qa-design

Decisão 10 vale — sem flags, sem `--ci`, sem `--quiet`. CI integration é
pattern emergente em v1.x quando alguém pedir; até lá, `forge qa` é
puramente conversacional.

**Por que defer:** adicionar `--ci` agora quebraria Decisão 10 (zero
flags) sem demanda concreta; CI run sem prompt interativo + render JSON
estruturado seria contrato novo de saída.

**Condição pra revisitar:** projeto consumidor pede integração em
pipeline (GitHub Actions / Jenkins). Brainstorm: como entregar
non-interactive sem flag? Provavelmente via hidden entrypoint (pattern
de `forge ingest`) acionado por hook CI, não comando typed pelo user.

### Gap QA-4 — Cross-project audit

**Categoria:** qa-scope
**Fingerprint:** `sha256(redundant-platform:qa-cross-project-audit:multi-inventory)`
**Status:** deferred (Decisão 14 vale) — surfaced em §17.4 do spec qa-design

Inventory + memory são per-project (Decisão 14). Auditar correlações
cross-project (ex.: 2 projetos compartilham backend e o spec deles
diverge) está fora do scope da skill standalone.

**Por que defer:** Decisão 14 (config scope = um workflow-config por
sub-projeto) é load-bearing. Cross-project audit exigiria registry
externo de specs + protocolo de sync — fora do escopo da skill que vive
dentro de cada projeto.

**Condição pra revisitar:** ferramenta separada de "spec consistency
across N projects" emerge como produto distinto; `forge qa` ganha hook
pra exportar findings num formato que essa ferramenta consome (não o
contrário).

### Gap QA-5 — Diff-aware mode

**Categoria:** qa-performance
**Fingerprint:** `sha256(promote-to-shared:qa-diff-aware:scope-since-last-run)`
**Status:** deferred (sem baseline de runtime) — surfaced em §17.5 do spec qa-design

v1 sempre audita o scope completo. "Auditar só o que mudou desde o
último run" é otimização de performance que ainda não tem dado pra
justificar (sem baseline de runtime real).

**Por que defer:** YAGNI até `forge qa` rodar lento o suficiente pra
incomodar. Diff-aware exige snapshot de inventory + tracking de mtime
por artefato — complexidade que multiplica edge cases (artefato deletado
e re-criado, rename, etc.).

**Condição pra revisitar:** user reportar `forge qa` lento numa codebase
real (>2min por scope=feature, por exemplo); então benchmark + decisão
sobre granularidade do diff (file-level vs spec-level).

### Gap QA-6 — Custom rubric per project

**Categoria:** qa-governance
**Fingerprint:** `sha256(consolidate-within-module:qa-custom-rubric:threshold-override)`
**Status:** deferred (guard-rail intencional) — surfaced em §17.6 do spec qa-design

Rubric (§5.4 do spec) é hardcoded em v1. Permitir overrides do threshold
BLOCK/FLAG/PASS via workflow-config abre porta pra "we don't fail on
critical" — anti-pattern.

**Por que defer:** rubric fixa é guard-rail intencional — alinhado com
Mandamento 4 (escopo contido). Permitir override por projeto é exatamente
o caminho pra erodir a disciplina que o gate existe pra proteger.

**Condição pra revisitar:** caso real onde rubric default produz falsos
positivos sistematicamente num projeto legítimo. Brainstorm pra distinguir
"override de threshold" (anti-pattern) de "auditor opt-out via card"
(legítimo via `qa-extensions`).

### Gap QA-7 — Plan template fix: PYTHONSTARTUP → sitecustomize.py

**Categoria:** qa-plan-template
**Fingerprint:** `sha256(consolidate-within-module:qa-sandbox-env-bootstrap:pythonstartup-vs-sitecustomize)`
**Status:** deferred (plan template) — surfaced 2026-06-05 durante exec da Task 3.3

Plan template (Task 3.3 sandbox) instruía usar `PYTHONSTARTUP` pra
injetar hooks no subprocess Python sandbox. Em subprocess
não-interativo o `PYTHONSTARTUP` é silenciado pelo CPython — não dispara.
Executor aplicou o fix correto durante implementação: `sitecustomize.py`
montado via `PYTHONPATH` (mecanismo que o CPython respeita sempre, em
qualquer modo de invocação).

**Por que defer:** o fix já está aplicado no código real. O plan template
ainda contém a instrução errada — revisão futura do plan precisa refletir
o caminho correto. Não é bug em produção, é divergência plan↔code.

**Condição pra revisitar:** próxima revisita do plan
`docs/superpowers/plans/2026-06-05-forge-qa.md` Task 3.3 — atualizar
instrução pra `sitecustomize.py` via `PYTHONPATH`.

### Gap QA-8 — Plan template fix: engine/qa.py → engine/qa/__init__.py

**Categoria:** qa-plan-template
**Fingerprint:** `sha256(consolidate-within-module:qa-engine-module-layout:flat-vs-package)`
**Status:** deferred (plan template) — surfaced 2026-06-05 durante exec da Task 4.1

Plan template (Task 4.1) instruía criar `engine/qa.py` flat, mas
`engine/qa/` já é package estruturado em Wave 3 (com submódulos
`auditors/`, `phases/`, `sandbox/`, etc.). Executor moveu o handler do
comando pra `engine/qa/__init__.py` durante implementação — caminho
canônico pra package Python.

**Por que defer:** o fix já está aplicado. Plan template ainda diz
"flat module"; revisão futura precisa refletir layout real.

**Condição pra revisitar:** próxima revisita do plan Task 4.1 —
atualizar instrução pra `engine/qa/__init__.py` (package handler).

### Gap QA-9 — Plan template obsoleto: Task 4.3 bin/forge verb list

**Categoria:** qa-plan-template
**Fingerprint:** `sha256(consolidate-within-module:qa-bin-forge-shim:verb-list-obsoleta)`
**Status:** deferred (plan template) — surfaced 2026-06-05 durante exec da Task 4.3

Plan instruía adicionar `qa` na verb list do `bin/forge`. Mas `bin/forge`
é shim "boring" (Decisão 19 — Bash dispatcher minimal, sem verb list
hardcoded; dispatcha tudo via `engine.cli`). Task 4.3 ficou funcionalmente
satisfeita por Task 4.2 (handler registrado em `engine/cli.py`), sem
mudança em `bin/forge` necessária.

**Por que defer:** o estado atual está correto (no-op em `bin/forge`).
Plan template ainda lista Task 4.3 como ação distinta; revisão futura
deve marcar Task 4.3 como obsoleta ou mergeá-la em Task 4.2.

**Condição pra revisitar:** próxima revisita do plan Task 4.3 —
remover ou marcar como "n/a (Decisão 19 — shim sem verb list)".

### Gap QA-10 — qa-finding `id` regex inconsistência (T/Z uppercase vs lowercase-only)

**Categoria:** qa-validator / qa-schema
**Fingerprint:** `sha256(consolidate-within-module:qa-finding-id-regex:case-mismatch)`
**Status:** open (decisão pendente) — surfaced 2026-06-05 durante exec das Tasks 2.2 + 3.4

`_ID_RE` em `validators/validate_qa_finding.py` aceita apenas lowercase.
`run.id` em `qa-report.json` é renderizado com `T`/`Z` uppercase (formato
ISO 8601 canônico). Dois pontos do mesmo sistema discordam sobre
case-sensitivity de IDs.

**Por que defer:** exige decisão consciente entre 2 caminhos —
(a) flexibilizar `_ID_RE` pra aceitar uppercase em segmentos timestamp,
(b) mudar `run.id` format pra lowercase pré-render. Ambos quebram alguma
expectativa (testes existentes vs convenção ISO 8601). Brainstorm
necessário.

**Condição pra revisitar:** brainstorm dedicado decidir o caminho.
Provavelmente (a) — ISO 8601 com `T`/`Z` é canônico e flexibilizar
regex é fix localizado.

### Gap QA-11 — Sandbox env hardening (allowlist vs blocklist)

**Categoria:** qa-sandbox / security
**Fingerprint:** `sha256(promote-to-shared:qa-sandbox-env-isolation:allowlist-vs-blocklist)`
**Status:** ✅ resolvido 2026-06-08 (allowlist core + per-card opt-in + grant explícito via spec `docs/superpowers/specs/2026-06-08-qa-sandbox-env-hardening-design.md` + impl em PR QA-11; 40+ tests adicionados; baseline 953 → ~995 tests; closeout commit referencia este resolvido).

Sandbox subprocess (Phase 3 do `forge qa`) herda env completo do processo
pai, incluindo possíveis secrets (`AWS_*`, `GITHUB_TOKEN`, etc.). Allowlist
estrita quebraria validators canon que dependem de `PATH` + `HOME` +
`LANG`. Blocklist exigiria consenso sobre o conjunto exato de variáveis
"perigosas" — moving target.

**Por que defer:** decisão de segurança não-trivial. Exige brainstorm
dedicado mapeando (a) lista mínima de env vars que validators canon
precisam, (b) política de blocklist com pattern `*_TOKEN`, `*_SECRET`,
`*_KEY`, (c) override per-project via workflow-config (com cautela —
ver Gap QA-6).

**Condição pra revisitar:** brainstorm sobre threat model do sandbox.
Provavelmente caminho híbrido: allowlist core + blocklist regex
configurável.

### Gap QA-12 — Pause/resume implementation (Decisão 27 + §16 edge 6) — ✅ FECHADO 2026-06-08 (CONF-004)

**Categoria:** qa-flow / state
**Fingerprint:** `sha256(consolidate-within-module:qa-pause-resume:checkpoint-json)`
**Status:** ✅ shipped 2026-06-08 — PR #8 CONF-004 (commits `5d50e3a` impl + `aa29a01` review fixes)

Resolvido via `engine/qa/checkpoint.py` (`Checkpoint` dataclass +
`CheckpointCorruptError` + `write_checkpoint`/`read_checkpoint`/
`find_resumable_run`). SIGINT salva checkpoint atomicamente; nova
invocação detecta e retoma sem criar novo `run_id`. Auto-resume; corrupt
checkpoint cai em 3-caminhos mentor calmo. Tests aspirational
desbloqueados (skip markers removidos). Findings deferidos do review
(M-1 SIGINT pré-signal-register; M-3 scope_type ignored) anotados em
Gap QA-15 abaixo.

### Gap QA-13 — Paranoid scope state filter

**Categoria:** qa-scope
**Fingerprint:** `sha256(consolidate-within-module:qa-paranoid-state-filter:feature-state)`
**Status:** ✅ resolvido 2026-06-08 (filter aborted/archived via status.json read em `engine/qa/scope.py._is_terminal_state`; fail-safe default-include pra legacy/malformado; 3 tests novos cobrindo positivos + edge cases).

`_list_features_for_paranoid` em `engine/qa/scope.py` enumera todos os
diretórios de feature sem filtrar por `state`. Spec §5.0 declara filter
state ∈ {planning, implementing, blocked-on-external, done} — paranoid
ignora `aborted` + `archived`.

**Por que defer:** padrão de feature state file (`status.json`) varia
por subtype + state machine (Gap 8 introduziu `blocked-on-external`).
Implementar filtro exige walkthrough cuidadoso da semantics atual de
`L1State` + `current_subtype` + edge cases (status.json malformado,
state legacy pre-Gap-8).

**Condição pra revisitar:** quando `L1State` ganha API estável
`list_features(filter_states=[...])` — momento natural pra plugar
filter aqui. Provavelmente piggyback de Gap 6 (multi-dev `active-tasks`
expansion) ou Gap 7 (partial-released state).

### Gap QA-14 — sandbox-results.json contract no qa-conductor.md

**Categoria:** qa-flow / conductor-contract
**Fingerprint:** `sha256(consolidate-within-module:qa-conductor-sandbox-results:phase-3-handoff)`
**Status:** deferred (Wave 4 documentou o contract; falta runs reais validarem) — surfaced 2026-06-08 PR #8

`engine/qa/synthesis.py` agora deriva findings determinísticos de
`SandboxResult` via `findings_from_sandbox_results`. `engine/qa/__init__.py`
lê `<run>/sandbox-results.json` se existir. PR #8 Wave 4 atualizou
`agents/qa-conductor.md` ensinando o conductor LLM a serializar
SandboxResults nesse arquivo após Phase 3. Antes desse update, CONF-003
funcionava em testes mas ficava dormente em produção (conductor LLM
atual escreve só findings/*.json).

Shape esperado: lista de dicts com `{fixture_name | fixture.name, status,
exit_code?, stdout?, stderr?, duration_s?, error?}`. Status reconhecidos:
`ok | timeout | sandbox-breach | skipped-budget | error`. Apenas
`sandbox-breach` (critical, always BLOCK) e `timeout` (medium) viram
findings automáticos.

**Por que defer:** doc-only change; validar serialização real exige
runs end-to-end com conductor LLM acionado. Eventual revisita pode
endurecer contrato (schema validator pra `sandbox-results.json`, alerta
no synthesizer quando arquivo missing).

**Condição pra revisitar:** primeiro run real onde conductor LLM
escreve `sandbox-results.json` e synthesis emite finding determinístico.
Se shape divergir do documentado, brainstorm pra schema explícito.

### Gap QA-15 — Findings deferidos do review CONF-004

**Categoria:** qa-state / qa-scope
**Fingerprint:** `sha256(consolidate-within-module:qa-pause-resume-followups:review-conf-004-deferred)`
**Status:** deferred (cross-cutting ou cosmético) — surfaced 2026-06-08 review CONF-004

Review CONF-004 (commit `aa29a01` aplicou H-1, M-2, M-4, M-5; restante
deferred):

- **M-1**: SIGINT durante Phase 0 (antes do `signal.signal` registrar)
  deixa run_dir órfão sem checkpoint nem cleanup → `find_resumable_run`
  não detecta. Zombie até retention. Cross-cutting (precisa decisão UX:
  cleanup vs preserve).
- **M-3**: `find_resumable_run` aceita `scope_type` mas ignora; layout
  `.planning/qa/<target>/` não discrimina scope_type → `feature/login` e
  `screen/login` colidem. Pre-existing herdado de ingest.
- **L-1**: `_phase = [0]` list-of-int hack em `engine/qa/__init__.py`
  (alternativa dataclass `_PhaseTracker` mais clara — style only).
- **L-2**: `test_checkpoint_written_on_sigint` mockado borderline entre
  unit e integration (marker discutível).
- **L-4**: `test_corrupt_checkpoint` não asserta
  `len(qa_dir.iterdir()) == 1` (que nenhum run dir novo foi criado).

**Por que defer:** M-1 e M-3 exigem brainstorm dedicado (UX policy + scope
discrimination); L-1/L-2/L-4 são cosméticos sem impacto funcional.

**Condição pra revisitar:** primeira vez que M-1 ou M-3 morder usuário em
run real, ou polish-pass dedicado pra L-* via subagent housekeeping.

### Gap QA-16 — `_utc_iso_z` duplicado em 10+ call-sites cross-engine

**Categoria:** code-quality / Mandamento #3 (reuso)
**Fingerprint:** `sha256(consolidate-within-module:utc-iso-z-helper:cross-engine-sweep)`
**Status:** deferred (cross-cutting refactor) — surfaced 2026-06-08 review CONF-004

Reviewer CONF-004 mencionou 10+ duplicações de
`datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")` em
`engine/{evolve,plan,undo,verify,init,memory/*,inventory/*,reconfigure,implement}.py`.
M-4 do review CONF-004 consolidou apenas em `engine/qa/_common.py`
(entre `engine/qa/__init__.py` e `engine/qa/checkpoint.py`).

**Por que defer:** cross-engine refactor (~30 file touches) sai do escopo
de PR #8 (forge qa hardening); promover `engine/qa/_common.utc_iso_z`
pra `engine/utils/timestamps.py` exige sweep + regression-test cuidadoso.

**Condição pra revisitar:** task dedicado de sweep cross-engine (promover
helper pra utils + atualizar todos os call-sites). Estimativa: 1 commit
médio (~30 file touches, regression-test-safe via grep+sed scriptado).

### Gap BOOTSTRAP-1 — `test_bootstrap_is_idempotent` falha em worktree

**Categoria:** bootstrap / test infrastructure
**Fingerprint:** `sha256(consolidate-within-module:bootstrap-test-worktree:dotgit-file-vs-dir)`
**Status:** deferred (v1.2-dev+), pre-existing — surfaced 2026-06-03

`tests/integration/test_bootstrap_is_idempotent` e scripts em
`.claude/bootstrap.sh` + hooks assumem que `.git` é um **diretório** (não
um arquivo). Em Claude Code worktrees (`git worktree add`), `.git` é um
arquivo apontando pro `gitdir` do parent — o que faz `[ -d .git ]`
falhar e os scripts tentarem reinstalar symlinks num path inexistente.
Não bloqueia ship de feature em worktree porque o gate principal
(pytest + forge verify rodam normal), mas degrada smoke-checklist
quando smoke é executado dentro de worktree. Fix proposto: detectar
worktree via `git rev-parse --git-dir` e resolver gitdir real antes de
fazer symlink. Onde: `.claude/bootstrap.sh` +
`tests/integration/test_bootstrap_is_idempotent.py` +
`.claude/rules/SMOKE-CHECKLIST.md § Check 1`.

## v1.2 follow-ups (power-review PR #2 — defer-with-reason)

Itens identificados no power-review do PR #2 (Gap 5 — card local overlay)
cuja resolução é genuinamente cross-cutting OU exige brainstorm separado.
Anotados aqui pra não procrastinar silenciosamente — cada um carrega
fingerprint próprio que volta a aparecer em `forge graph query Q12+` se
revisitado.

- **Step 7.5 caminho 1 — re-detection inline** (N2 fix opção `a`).
  Hoje (R1 power-review) o user-facing copy e docstring avisam que
  cards locais entram em vigor só no próximo `forge init`. Behavior fix
  completo exige rebind de `activated` após criar locais (chamar
  `_load_overlay_catalog` + recomputar matches contra os novos locais).
  Defer porque toca order-of-evaluation do pipeline init — quer
  brainstorm + plan separado pra confirmar invariants (Step 8 merge,
  Step 11 graph build). Onde: `engine/init.py` `_run_pipeline` Step 7.5
  + `_surface_three_paths` caminho 1.

- **ADR-suspension audit log** (N13). Quando `all_reserved=True` e user
  escolhe "abrir ADR", a função retorna `adr-required` (exit 7) sem
  persistir nada em disco. Próxima execução de `forge init` perde
  contexto do que estava pendente. Fix proposto: gravar
  `.claude/inventory/adr-suspension.yaml` listando labels que precisam
  de promoção; init detecta e oferece resume na próxima entrada.
  Defer porque exige schema novo + decisão sobre como `forge doctor`
  reporta o estado pending. Onde: `engine/init.py`
  `_surface_three_paths` + novo schema em `docs/schemas/`.

- **`load_catalog` refactor pra `engine/cards/catalog_overlay.py`** (N17).
  Hoje `engine/init.py` Step 7.5 importa `load_catalog` via lazy
  `from validators._common import ...`. Engine consome de validators —
  direção de dependency invertida da arquitetura canônica
  (engine → validators é a direção única). Hoje é lazy + 1 call site,
  baixo risco. Se proliferar, mover `load_catalog` + `CapabilityCatalog`
  pra `engine/cards/catalog_overlay.py` e validators passam a importar
  do engine. Defer porque exige mover + ajustar testes em duas
  camadas — não-trivial e sem urgência observável.

- **Lenient local loader** (C1). Hoje, `load_all_cards` em modo cascade
  hard-fails se QUALQUER card local for malformado (mesma severity de
  canon). Power-review sugere que canon mantenha fail-fast
  (Decision 23) mas que local seja lenient (warn + skip). Defer porque
  inverte contract testado pelo `test_cascade_raises_on_malformed_local_card_yaml`
  e exige decisão consciente: lenient pode mascarar bugs de overlay
  manual do time. Brainstorm: lenient default vs strict-via-flag
  (Decision 10 — zero flags — limita opções). Provavelmente fica como
  modo opt-in via `cleanup-bak`-style submenu em `forge reconfigure`
  ou flag no `card.yaml` próprio do local.

## Phase 0 follow-ups (gate-infra extraction — 2026-06-05)

### Gap GATE-INFRA-1 — Parametrize gate_threshold_lookup + format_three_paths_message

**Categoria:** gate-infra
**Severidade:** baixa (YAGNI — não bloqueia até 2º consumer numérico)
**Status:** ✅ **resolvido** (PR #7 review fixes — commit 152cae0, 2026-06-08).
Helpers aceitam kwargs `card_override_key` / `workflow_block_key` /
`defaults` (em `gate_threshold_lookup`) + `gate_title` / `why_lines` /
`override_example` / `format_annotation` (em `format_three_paths_message`).
Defaults preservam comportamento CC byte-a-byte; testes em
`tests/validators/test_common_cc_helpers.py` cobrem parametrização +
defaults. Cognitive Complexity (R2.2) já consome direto, sem reescrever.

**Histórico (preservado pra rastreabilidade):**

`gate_threshold_lookup` ainda hardcoda `"cc-gate-override"` / `"cc-gate"` /
`DEFAULTS_CC` internamente. Nome foi generalizado mas implementação permanece
CC-específica. Quando 2º gate consumer **numérico** arriver, parametrizar via
novos kwargs: `card_override_key` / `workflow_block_key` / `defaults` /
`gate_title` / `why_lines`. Similar pra `format_three_paths_message`
(parametrizar `gate_title`, `format_annotation`).

**Confirmação R1.1 (2026-06-05):** `check_secrets` shipou como 2º consumer da
infra Phase 0 e **NÃO** tocou `gate_threshold_lookup` — secrets é binário
(detectou = fail), não tem threshold numérico por linguagem. O render
3-caminhos do secrets é local (vocabulário próprio — "rotação"/"fixture" vs
"refactor"/"split-task" do CC), por decisão de spec §3: fundir os dois renderia
prose genérica que perde o ponto. Logo a parametrização permanece corretamente
deferida até o 2º consumer **numérico** — provavelmente Cognitive Complexity
(wave R2.2), que herda ~80% do CC gate e VAI precisar do threshold lookup
generalizado. `forge graph` Q12/Q14 não detectaram near-duplicate em R1.1
porque o secrets não copiou o helper — compôs `apply_overrides` /
`dispatch_native_tool` / `check_tool_available` direto.

### Gap GATE-INFRA-2 — extract_diff_hunks N+1 subprocess

**Categoria:** gate-infra
**Severidade:** baixa (performance — não bloqueia funcionalidade)
**Status:** deferred (YAGNI até 2º consumer de hunks aparecer)

Hoje `extract_diff_hunks` em `validators/_diff.py` dispara 1
`git diff --cached -U0 -- <file>` por arquivo. Pre-commit em projeto grande
(50+ arquivos staged) acumula 50 fork+exec — overhead linear na quantidade
de staged files. `git diff` aceita N paths posicionais e o parser sabe
separar por header `+++ b/<path>`, então a refator é mecânica.

Defer YAGNI porque (a) CC gate atualmente é o ÚNICO consumer de hunks
(secrets usa `staged_files` diretamente, sem hunk-level diffing) e
(b) overhead empírico é minor em features típicas (<10 staged files).
Revisitar quando consumer #2 de hunks chegar — provavelmente
Cognitive Complexity (R2.2) ou Function Length & Nesting (R2.4), ambos
precisam de classify_range_against_hunks pra delta-rule.

**Fix sugerido:** batched git invocation + parser por arquivo. Estrutura:

```python
proc = subprocess.run(
    ["git", "-C", root, "diff", "--cached", "-U0", "--", *rel_paths],
    ...
)
# Parser split por linhas `diff --git a/<path> b/<path>` ou `+++ b/<path>`
```

Self-review thread relacionada: PR #7 comment 3375391361.

### Gap SECRETS-1 — Custom rules per project (deferred v1.3+)

**Categoria:** secrets-gate
**Severidade:** baixa (default ruleset cobre o baseline)
**Status:** deferred (reentra com pedido empírico de ≥2 projetos consumidores)

`gitleaks` aceita regras customizadas via `gitleaks.toml`; `trufflehog` via
`--config`. v1.2-dev usa o **default ruleset** das duas tools (AWS, GCP, Stripe,
GitHub PATs, Firebase, etc.) — cobertura aceitável pra apps mobile e web sem
inflar complexity. Custom rules (ex.: token interno da empresa com formato
proprietário) ficam pra v1.3+. Critério pra reentrar: pedido empírico
documentado de ≥2 projetos consumidores. O `cmd_builder` já recebe
`rendered_config` (ignorado hoje) — o hook de extensão existe, falta só wirar
config → tempfile render quando a demanda chegar.

### Gap SECRETS-2 — History scan periódico (out-of-scope até phase 5)

**Categoria:** secrets-gate
**Severidade:** média (cobre vazamento histórico, não o diff atual)
**Status:** out-of-scope v1.2-dev

`check_secrets` é diff-mode — escaneia apenas staged files no commit atual.
Vazamentos no histórico (PR mergeado há meses contendo token ainda ativo) só
pegam num `trufflehog git --since=...` periódico. Forge não orquestra CI, então
isso vale um GitHub Action separado no projeto consumidor. Critério pra
reentrar: phase 5+ se forge ganhar componente de CI orchestration.

### Gap SECRETS-3 — Webhook/notify on detection (out-of-scope até phase 6)

**Categoria:** secrets-gate
**Severidade:** baixa (mitigação manual existe — rotação imediata no 3-caminhos)
**Status:** out-of-scope v1.2-dev

Quando um secret verificado é detectado, o ideal seria notificar canal de
segurança (Slack #security, email) automaticamente — assume comprometido até
prova em contrário. Out-of-scope v1.2-dev. Pode entrar em phase 6 (LLM hookup)
junto com auto-suggest-rotation. Critério pra reentrar: phase 6 quando a
infraestrutura de notify existir.

### Gap BOOTSTRAP-1 — test_bootstrap_is_idempotent falha em worktree context

**Categoria:** test-infra
**Severidade:** baixa (environmental, não regressão)
**Status:** deferred

`tests/integration/test_claude_rules_system.py::test_bootstrap_is_idempotent`
falha em qualquer worktree porque `.git` é arquivo (não diretório) — bootstrap
script tenta `ln .git/hooks/pre-commit` que falha com "Not a directory".

Fix: `bootstrap.sh` detectar worktree via `git rev-parse --git-dir` antes de
criar symlink — resolve gitdir real. Out-of-scope Phase 0; valid follow-up.

## Phase A W2 — Code review follow-ups (DRIFT-1 intent protocol, 2026-06-10) (resolved by Phase A — see "Fechado em [Unreleased]")

Itens identificados durante o fix-loop dos 10 findings do REVIEW de W2.T1+T2
(`.planning/drift-1-w2-review/REVIEW.md`) + integração T3b nos 10 subcommands.
Cada um é decisão consciente de não-fazer-em-W2, com critério explícito pra
reentrar. Referência cruzada: SPEC §5 (tabela final 10/10) +
`.planning/drift-1/checkpoint-audit.json`.

### W2-FU-1 — Docstring count drift em `test_ui_question_api_signatures.py`

**Categoria:** test-docs
**Severidade:** baixa (cosmético — não afeta behavior nem coverage)
**Status:** deferred (próxima task que tocar o arquivo)

`tests/unit/test_ui_question_api_signatures.py` cita "125 callsites" na docstring,
herdada de pre-W2 grep. O número atual após o refactor é 108 callsites (mensurado
em rapid lane pós-W2). O REVIEW fixer não atualizou porque o arquivo ficou fora
do FILE BUDGET do dispatch — touch fora do escopo do fix-loop.

**Por que defer:** atualizar exige re-medir e justificar metodologia (grep
pattern, scope dirs, exclusões); fora do escopo de doc-sync. Próxima task que
tocar o arquivo reconcilia o número ou substitui por "verificado contra
codebase atual em <data>".

### W2-FU-2 — TDD shape sem commit RED separado em commits 90d1463 / 9980f41

**Categoria:** process-learning
**Severidade:** baixa (process drift, não bug)
**Status:** acknowledged (não retrofit; aplicar regra prospectivamente)

REVIEW finding MD-003 apontou que os dois commits maiores do W2 (90d1463
question.py refactor, 9980f41 cli.py exit handler) carregaram test + impl no
mesmo commit em vez de RED commit separado. TDD shape do projeto pede commit
de teste falhando ANTES da implementação (rule `testing.md` §Para feature).

**Por que defer (não retrofit):** rewriting história pós-merge no W2 não vale o
ruído; aprendizado é prospectivo. Em refactors >300 LOC futuros (W3+? W5
integration?), executor deve fazer commit RED separado obrigatoriamente — o
context-pack do dispatch precisa exigir explicitamente. Anotado aqui pra
reentrar em retrospective do branch quando W6 fechar.

### W2-FU-3 — `PromptAbortedError` preservada como legacy export inerte

**Categoria:** dead-code-scaffolding
**Severidade:** baixa (cleanup, não afeta runtime)
**Status:** deferred (callsite-migration de W3+ ou sessão de cleanup pós-W6)

Os 10 callsite modules integrados em T3b mantêm `except PromptAbortedError:`
scaffolding herdado do pre-W2. No path intent-only atual, a sentinel é
preservada como re-export de `engine/ui/question.py` mas nunca raised internally
— os except blocks são dead code que silencia uma exceção que não chega a
ocorrer.

**Por que defer:** cleanup cross-cutting toca os 10 subcommands; faz sentido
fechar junto com callsite-migration task (W3+) ou em sessão dedicada de cleanup
pós-W6 quando todas as migrações estabilizarem. Remover agora arrisca quebrar
hosts não-Claude-Code que dependiam do legacy raise.

### W2-FU-4 — Outcome C revisitable se 3º+ subcommand emergir com pattern similar

**Categoria:** decision-direcional
**Severidade:** baixa (revisita programada, não débito ativo)
**Status:** deferred (gatilho de dados — 3+ ocorrências)

W2.T0 lockou outcome C (per-subcommand `_<Module>Checkpoint` dataclass + 3
helpers + path resolver) em vez de promover pra `engine/utils/checkpoint.py`
shared module. Decisão consciente: pattern apareceu em 10 subcommands MAS com
shape suficientemente variável (campos diferentes por handler) pra que abstração
prematura custasse mais que copy. Decision 22 (no runtime deps inter-skills)
não força mudança, mas regra de reuse (Mandamento #3) pede revisita se padrão
muito similar emergir 3+x nas próximas waves.

**Critério pra reentrar:** se W3-W6 (ou DRIFT-2+) adicionarem 3+ subcommands
com mesma shape de campos (intent_id + 2-3 campos contextuais + breadcrumb),
abrir brainstorming pra promote-to-shared. Senão, manter pattern atual e
revisitar em retrospective de v1.3+.

## v1.2-dev pilot 2026-06-10 — findings + phase sequencing

Pilot conduzido em projeto KMP real (inchurch-app-main, Android+iOS+KMP, módulos `androidApp`/`iosApp`/`shared`) em 2026-06-09/10. LLM-cobaia adotou postura "usuário comum descobrindo a ferramenta" sob orientação do orquestrador deste repo. Notas e relatório parcial capturados na sessão (não comitados; viver no histórico de conversa + memory persistente).

**Status do piloto:** parcial. `forge init` capturado até Prompt 2 (Backend, incompleto). `forge reconfigure` capturado integralmente. Inspeção pós-init (Passo 4), seção Voz/persona consolidada, sugestões e verdict final do init não foram preenchidos.

### Achado conceitual primário — DRIFT-1

`engine/ui/question.py:1` docstring declara "Interactive prompts — the local AskUserQuestion fallback" — design conceitual original do forge era engine emitindo intent estruturado pra Claude Code interceptar e surface via `AskUserQuestion`. Implementação atual (`sys.stdin.readline()` em :36) é stdin-only, sem protocolo de intent nem detecção de host. **Drift entre intent e impl.** User confirmou em 2026-06-10 que modo Claude-Code-fronted é canonical daqui pra frente.

Implicação: todos findings de UX/microcopy/persona/banner do piloto se aplicam SÓ ao modo fallback. Sobrevivem ao redesign apenas findings de dados/detecção (abaixo).

### Findings do piloto v1.2-dev — status

- **B1 / B2 / DET-5 / DET-6** — ✅ FECHADOS em [Unreleased] via Phase B
  DET-6 (2026-06-11). Ver §"Fechado em [Unreleased]" no topo deste doc
  pra rationale e refs de commits. Descrições históricas dos findings
  preservadas no git log da entrada original (commit pré-`b9c2c24`).
- **DET-3 — Scanner cego pra `libs.versions.toml`** — ✅ resolvido
  2026-06-10. Plan `docs/superpowers/plans/det-3-gradle-dep-signal.md`.
  Novo signal type `gradle-dep` + helper `_eval_gradle_dep` em
  `engine/init.py` + regra CARD-020 em `engine/cards/loader.py` +
  migration de 9 signals em 8 cards (crashlytics, firebase-auth ×2,
  firebase-storage, firestore-persistence, firestore-realtime,
  koin-annotations, kotlinx-serialization-json, ktor-client/core).
  Catálogo `gradle/libs.versions.toml` agora coberto. Audit
  determinístico em `.planning/det-3/migration-audit.json`. Suite:
  1125 passed.

### Phase sequencing decidido (2026-06-10)

User selecionou via AskUserQuestion: **Phase 0 → Phase A → Phase B série pura**.

- **Phase 0** — Captura (esta entrada) + DET-3 quick win (scanner glob extension)
- **Phase A — DRIFT-1** — Refactor `engine/ui/question.py` pra emitir intent estruturado + integração Claude-Code-fronted via AskUserQuestion. Stdin vira fallback genuíno detectado por TTY/env.
- **Phase B — DET-6** — Redesign multi-axis backend model usando AskUserQuestion como UX layer. Absorve B1, B2, DET-5 naturalmente. SPEC + waves: schema → presets → init flow → reconfigure flow → migration.

### Findings deferred até Phase A (DRIFT-1) ficar pronto

Todos UX/microcopy/persona do piloto fallback CLI:
- Persona inconsistente init↔reconfigure (banner "Cheguei./Tudo bem./Aqui.")
- Inputs híbridos (letras `a,c` vs texto `backend` vs pipe `firebase|rest`)
- Microcopy "ticketing, external-docs" como descrição de opção `backend`
- Dead option `[outro] escolher outro preset (não disponível no v1)`
- Prompt de ticketing aparece sem seleção no multi-select
- Draft pipe interception quebra automação
- `[0:01]` timestamp confunde com ETA
- `bin/forge:22` `FORGE_VERSION="1.0.0"` hardcoded (dead variable)

Quando Phase A entregar protocolo Claude-Code-fronted, essas UX issues desvanecem porque persona+microcopy passam a ser responsabilidade da Claude Code, não do Python. Não vale fixar enquanto o engine ainda emite as strings.

### DET-3 follow-ups não-bloqueantes (2026-06-10)

Anotados conforme SPEC §"Considerações futuras" pra rastreio sem bloquear shipping de DET-3.

#### Vapor cleanup — signal type `dependency` (follow-up de DET-3)

`docs/schemas/card.md` declara o signal type `dependency` mas
`engine/init.py:_eval_detection_signals` nunca implementou — cards com
`type: dependency` são silenciosamente ignorados. Sucessor canônico
pra Gradle deps é `gradle-dep` (DET-3, shipped 2026-06-10).

Decisão pendente: (A) implementar `dependency` cobrindo
npm/pip/swift/pod (multi-ecossistema), (B) remover do schema e marcar
como vapor histórico, (C) renomear `dependency` → `package-manager-dep`
pra esclarecer scope. Sem brainstorm aberto ainda.

Não-bloqueante. Anotado pra abrir 3-caminhos quando tiver bandwidth.

#### `signals.yaml` schema-version bump (follow-up de DET-3)

Hoje `cards/*/detection/signals.yaml` não declara schema-version uniforme
(alguns têm `schema-version: 1`, outros não). DET-3 migrou 9 signals em
8 cards de `file-content` → `gradle-dep` sem versionamento explícito,
dependendo do git log pra rastrear "antes/depois". Pra migrations
futuras (próximos signal types, mudanças de shape), adicionar
`schema-version: 2` no topo dos cards migrados (e `schema-version: 1`
default implícito nos não-tocados, ou explícito via reconfigure).

Decisão pendente: timing — bumpar nos 8 cards migrados agora (escopo
de DET-3) ou esperar próximo signal type e bumpar batched. Default
atual: esperar, registrar aqui.

Não-bloqueante. Anotado pra próxima rodada de migration cross-card.

### Follow-ups pós-master-review PR #11 (2026-06-10)

Master-review do PR #11 (`feat/gradle-dep-signal`) endereçou 9 findings de code-fix em Wave 1+2 (A-1, A-2, M-2, M-3, M-4, M-5, B-1, B-2, B-3). Restam 3 follow-ups de natureza estratégica/observabilidade que não bloqueiam merge e ficam aqui pra rastreio. Severities P3 — abrir quando padrão recorrer ou demanda concreta surgir.

#### FU-MR-1 (P3) — Schema-version bump trigger para signal types

**Context:** `cards/*/detection/signals.yaml` (e o bloco equivalente em `card.yaml.detection.signals`) hoje não carrega `schema-version` uniforme por signal type. DET-3 introduziu `gradle-dep` migrando 9 signals em 8 cards de `file-content` sem bumpar versionamento. Pra próximas migrations cross-card (próximo signal type novo, mudança de shape de existente), faltará trigger explícito de quando bumpar.

**Trigger proposto:** bumpar `signals.yaml` schema-version no próximo signal type novo (ex.: `pod-dep`, `npm-dep`, `swift-dep`). Default atual: esperar. Sem urgência v1.2-dev — anotado aqui pra evitar dívida silenciosa crescer fora do radar.

**Reference:** S-2 do master-review do PR #11; `docs/superpowers/specs/det-3-gradle-dep-signal.md` §"Considerações futuras".

**Outcome esperado (3-caminhos quando endereçar):**
- (a) Bumpar agora batched nos 8 cards migrados pra schema-version 2.
- (b) Bumpar no próximo signal type novo (trigger proposto acima).
- (c) Esperar até 2+ signal types acumulados pra evitar churn em single-bump.

#### FU-MR-2 (P3) — retrofit-client family-match decision

**Context:** O SPEC de DET-3 abre citando `retrofit-client` como exemplo do gap (scanner cego pra libs.versions.toml). O audit conservou `retrofit-client` com `file-content` substring `io.squareup.retrofit2:retrofit-` porque a coordenada captura toda a família (`-converters-gson`, `-converter-moshi`, `-mock`, etc.) por design. Migrar pra `gradle-dep` exato exigiria declarar cada variante separadamente OU introduzir wildcard. Resultado: `retrofit-client` continua com problema original do SPEC — projeto TOML-only puro ainda não detecta retrofit-client.

**Decisão pendente:** aceitar como tradeoff family-match preservado (retrofit-client é card pré-DET-3, comportamento idêntico) OU adicionar wildcard sufixado no signal schema (ex.: `coordinate: io.squareup.retrofit2:retrofit-*`).

**Reference:** S-3 do master-review do PR #11; audit em `.planning/det-3/migration-audit.json` entrada `retrofit-client`.

**Outcome esperado (3-caminhos quando endereçar):**
- (a) Aceitar tradeoff: documentar limitação em `retrofit-client/README.md` e `docs/schemas/card.md`; deixar como está.
- (b) Adicionar wildcard `coordinate: io.squareup.retrofit2:retrofit-*` ao signal schema; aplica a 2º card de família-multipla que surgir.
- (c) Declarar coordenadas explícitas por variante (`-converter-gson`, `-converter-moshi`, etc.) — explosão de signals mas exato.

Trigger: abrir quando 2+ cards de família-multipla pedirem o mesmo pattern.

#### FU-MR-3 (P3) — BOM em libs.versions.toml silenciosamente ignorado

**Context:** Surfaced por S-1.1 do master-review durante coverage de edge cases. `tomllib` (Py stdlib 3.11+) rejeita BOM UTF-8 (`\xEF\xBB\xBF`) por aderir estritamente à TOML 1.0 spec. Helper `_load_toml_catalog` engole `TOMLDecodeError` silenciosamente — resultado: catálogo com BOM vira invisível ao scanner, card não auto-ativa, usuário não tem indicação do porquê. Editores Windows às vezes salvam `.toml` com BOM por default (Notepad pre-Win10, alguns IDEs).

**Sugestão:** `forge doctor` deveria warn quando lê um catálogo cujo conteúdo começa com BOM. Não-bloqueante; ajuda diagnóstico no campo. Test de regressão `test_s1_toml_with_utf8_bom_silently_skipped` (em `tests/unit/test_eval_gradle_dep.py`, commit `e6305df`) trava se algum dia o helper strippar BOM — forçando revisita consciente.

**Reference:** S-1.1 do master-review do PR #11; `engine/init.py:_load_toml_catalog`; `tomllib` spec adherence.

**Outcome esperado (3-caminhos quando endereçar):**
- (a) Adicionar warn em `forge doctor` quando catálogo começa com BOM; documentar como diagnose-only.
- (b) Strippar BOM no helper antes de passar pro tomllib (afrouxa aderência à spec); test de regressão acima trava — exige revisita consciente.
- (c) Deixar como está; comportamento atual é spec-correct (TOML 1.0 não tem BOM).

### Phase 0b — Code review follow-ups (2026-06-10)

Discovered during DET-3 code review. None bloqueante — merge unlocked.
Cada um é fix-forward, capturado aqui pra evitar perda de contexto até
phase futura endereçar.

#### FU-1 — Custom catalog path discovery (Medium)

**Context:** `engine/init.py:_eval_gradle_dep` só procura
`<root>/gradle/*.versions.toml`. Catálogos declarados em path
customizado via `settings.gradle.kts versionCatalogs { from(...) }`
são invisíveis ao scanner. O fallback de `build.gradle*` ainda pega
deps declaradas inline, mas catálogos custom-path miss o caminho de
detecção via version-catalog.

**Reference:** `engine/init.py` (região de `_eval_gradle_dep`,
~linha 658).

**Outcome esperado (3-caminhos):**
- (a) Estender resolver pra parsear `settings.gradle*` por
  `versionCatalogs { from(...) }` e seguir o path.
- (b) Documentar limitação explicitamente, manter scope reduzido a
  `gradle/*.versions.toml` standard.
- (c) Deprecar `gradle-dep` em favor de signal v2 com declared
  catalog paths no card YAML.

#### FU-2 — `signals.yaml` mirror vs source-of-truth (Medium)

**Context:** Arquivos `cards/*/detection/signals.yaml` existem como
mirror documental de `card.yaml.detection.signals`. O card loader
(`engine/cards/loader.py:354`) lê SÓ `card.yaml` em runtime —
`signals.yaml` NUNCA é consumido. A migração da Phase 0b tocou 9
arquivos `signals.yaml` por paridade, mas o efeito funcional vem
exclusivamente das edições em `card.yaml`. Manter mirrors é
disciplina documental; risco real de drift existe.

**Reference:** `cards/*/detection/signals.yaml` (22 arquivos no repo
atual); `engine/cards/loader.py:354` (único consumer de `card.yaml`).

**Outcome esperado (3-caminhos):**
- (a) Formalizar `signals.yaml` como source-of-truth, refactor
  loader pra consumir, deprecar `card.yaml.detection`.
- (b) Remover mirrors `signals.yaml` inteiramente, apontar readers
  pra `card.yaml.detection` via tooling/doc.
- (c) Manter discipline atual de mirror, adicionar CI check
  enforcing parity entre `card.yaml.detection.signals` e
  `detection/signals.yaml`.

#### FU-3 — Substring match no fallback build.gradle (Low)

**Context:** `_glob_any("**/build.gradle*", coordinate)` faz
substring match. Coordenada `"io.ktor:ktor-client-core"` casa
também `"io.ktor:ktor-client-core-jvm"` (artifact diferente).
Comportamento pre-migration `file-content` era idêntico — zero
regression — mas o branding "exact coordinate" do novo signal
`gradle-dep` fica enganoso.

**Reference:** `engine/init.py` (fallback `_glob_any` após
`libs.versions.toml` miss, ~linha 686).

**Outcome esperado (3-caminhos):**
- (a) Renomear pra `gradle-dep-prefix` OU documentar semântica
  substring em `docs/schemas/card.md`.
- (b) Tighten pra word-boundary match (regex
  `(^|[^.\w-])<coord>([^.\w-]|$)`).
- (c) Deixar as-is, documentar caveat.

#### FU-4 — Cosmética post-review: naming + migration audit (Low)

**Context:** Dois itens S-001 e S-002 da code review de 2026-06-10
capturados aqui como deferidos:

- **S-001 — naming `_eval_gradle_dep`:** função retorna `bool` (semântica
  de predicate), mas segue convenção de nomenclatura de `_eval_*` que
  retornam tuple `(score, matched)`. Renomear pra `_has_gradle_dep` ou
  `_gradle_dep_matches` alinharia semântica, mas é breaking pra qualquer
  caller interno que já usa o nome. Deferido: rename cosmético.
- **S-002 — migration-audit.json sem `previous_signal`:** entradas
  `action: migrate` em `.planning/det-3/migration-audit.json` registram
  `coordinate` (after) mas não `previous_contains` (before). Rastreabilidade
  retroativa perdida pra re-auditoria automática. Deferido: melhoria de
  formato pra próxima migration mass.

**Reference:** `engine/init.py` (`_eval_gradle_dep` ~linha 639);
`.planning/det-3/migration-audit.json` (entradas `action: migrate`).

**Outcome esperado:**
- (a) Rename `_eval_gradle_dep` → `_has_gradle_dep` + update todos os
  callers (grep `_eval_gradle_dep` em engine/) + update tests que mockam.
- (b) Deixar nome as-is, adicionar docstring explícita que "retorna bool
  indicando presença, não score tuple".
- (c) Para S-002: se outra migração mass ocorrer, adicionar campo
  `previous_signal: {type, value}` ao audit schema.

#### FU-5 — Bootstrap idempotency em worktree context (Medium)

**Context:** `tests/integration/test_bootstrap.py::test_bootstrap_is_idempotent`
falha quando rodado de dentro de git worktree
(`.claude/worktrees/<...>/`). Root cause: `.claude/bootstrap.sh`
assume `.git` é diretório, mas em worktrees `.git` é ARQUIVO
contendo `gitdir: <path>`. Afeta: qualquer um rodando pytest
de worktree; Phase A W1 surfou isso em step de verificação.

**Reference:** `.claude/bootstrap.sh` (idempotency check);
`tests/integration/test_bootstrap.py::test_bootstrap_is_idempotent`;
Phase A W1 verification log em
`.planning/drift-1/w1-verification.md`.

**Outcome esperado:** bootstrap handles ambos `.git` dir AND
`.git` arquivo (worktree). Provável fix 1-2 linhas usando
`git rev-parse --git-dir` ou similar. Phase-independente —
pode ser endereçado a qualquer momento.

## Phase B — DET-6 multi-axis backend code review follow-ups (2026-06-10 W1)

Deferidos do review de Phase B W1 (`.planning/det-6-w1-review/REVIEW.md`)
durante doc-sync W1. Não-bloqueantes pro avanço W2; revisitar em W2 ou
cleanup pass dedicado dentro da própria branch `feat/det-6-multi-axis-backend`
antes do PR final ao fim de W8.

### W1-L-002 — Open-details #6/#7 em `workflow-config.md` em vez de `card.md` / `backend-axes.md`

**Categoria:** schema-foundation (doc placement)
**Severidade:** baixa (deviation cosmética; placement semanticamente correto)
**Status:** deferred — revisitar em W8 doc-sync se quisermos uniformizar

PLAN W1.4 nominou apenas `docs/schemas/card.md` e `docs/schemas/backend-axes.md`
como locais pra inline `<!-- open-detail -->` comments. Os anchors #6 (Phase A
API shape — referência ao formato de `signal-id`/`detector` que Phase A
consolidará) e #7 (rename `crashlytics` → `crash-reporting` discutido em
Phase B brainstorm) acabaram em `docs/schemas/workflow-config.md` porque
semanticamente pertencem ao contexto desse schema (axes-resolution + status
enum vivem lá). Não é regressão — só desvio do nominal do PLAN.

Fix forward: ao consolidar W8 (final doc-sync da Phase B antes do PR), mover
os 2 anchors pra `backend-axes.md` se a sentence ainda fizer sentido lá; ou
manter onde estão com nota cross-ref. Decisão fica pro W8.

### W1-L-003 — `docs/schemas/card.md:164` `# di OR dependency-injection` contradiz CARD-004

**Categoria:** schema-foundation (pre-existente fora W1)
**Severidade:** baixa (contradição interna do schema; sem efeito runtime)
**Status:** deferred — candidate fix em W2 (category cleanup) ou cleanup pass

`docs/schemas/card.md` linha 164 carrega um comentário pré-existente
`# di OR dependency-injection` que sugere alternância no enum de
`identity.category`. CARD-004 (revisado em W1) enumera apenas
`dependency-injection` — o "di" curto não está no enum canônico. Zero diff
sobre essa linha em W1 (`c60eeb1` + `26c0822` não tocaram a linha 164).

Fix forward: remover o `# di OR ` do comentário, deixando apenas
`# dependency-injection`. Trivial — pode entrar no próximo commit de W2
quando outras refinements em CARD-004 estiverem na mesa. Anti-padrão a
evitar: deixar pra W8 e arriscar drift adicional pelo caminho.

## RULE-023/024 — detecção de ciclo em `migrating-to` (deferred pós-DET-6)

PR #13 review (thgMatajs, 2026-06-12) apontou que `_check_backend` em
`validators/validate_workflow_config.py` valida que `cell.migrating-to`
referencia um card existente (RULE-024), mas não detecta ciclos do tipo
`card A` em `status=migrating-to` apontando pra `card B` enquanto `card B`
está em `status=migrating-to` apontando pra `card A`. Um config assim
passa pelo cascade atual sem warning.

Defer com razão: detecção de ciclo exige DFS 2-hop sobre todas as cells
backend, é feature menor e baixo impacto (config-malformed convive bem
com runtime — handlers downstream tratam `migrating-to` como hint, não
contrato). Entra quando RULE-019..024 receber pass dedicado de
hardening; até lá fica anotada aqui como gap conhecido.

## Reading order for new contributors

## Mypy rollout — advisory mode (2026-06-12)

**Baseline:** `17` errors across `engine/` + `validators/` (captured
via `mypy engine/ validators/` post-install of `mypy >= 1.8`; 113 source
files checked, 8 files com erros).

**Scope desta sessão:** apenas setup advisory. CI gate NÃO ativo. Comando
manual disponível: `mypy engine/ validators/`.

**Rollout incremental (próximas sessões):**
- Sub-phase 1: zero new errors policy (PR-level gate sem fail-on-existing).
- Sub-phase 2: top-3 módulos most-error (`engine/implement.py`,
  `engine/verify.py`, `engine/init.py`) ganham `strict = true` por seção
  isolada (`[[tool.mypy.overrides]] module = "engine.implement"`).
- Sub-phase 3: opt-in cascade até ≥80% módulos strict; ativar gate global.

**Why not strict now:** 17 errors → fix de cada um seria scope creep
além dos 22 findings do REVIEW.md. Setup baseline em advisory destrava o
pipeline pra abordar em phases dedicadas.

---

**For a fresh session retomando o projeto, use o handoff:**

→ `docs/design/08-session-handoff.md` (TL;DR + ordem mandatória + auto-mode prompt)

**Para revisão profunda, ordem completa:**

1. `docs/design/08-session-handoff.md` (start here!)
2. `README.md`
3. `docs/design/01-decisions.md` (27 decisões locked)
4. `docs/design/06-command-surface.md` (12 comandos, zero flags)
5. `docs/design/07-discipline.md` (7 disciplines universais)
6. `docs/design/00-vision.md`
7. `docs/design/02-phases.md`
8. `docs/design/03-influences.md`
9. `docs/design/05-filesystem-layout.md`
10. `docs/ux/forge-init-roteiro.md` (start UX docs here)
11. `docs/schemas/workflow-config.md` (start schemas here)
12. `agents/planning-conductor.md` (start agents here)
13. `docs/lifecycle/memory-and-graph.md`
14. This file (04-pending.md) to see what's left
