# PRD do feature-forge (design)

**Data:** 2026-06-04
**Origem:** brainstorming session orchestrator-mantenedor + thiago.pacheco
**Status:** APROVADO — pronto pra `superpowers:writing-plans`
**Audiência do PRD:** mantenedor + Claude futuro (interno)

## Contexto e motivação

feature-forge v1.2.0 + Gap 9 está cumulativo em produção: ~400 arquivos, ~52.500 LOC, 637 tests passing + 12 skipped, 22 cards canon, 17 graph queries, 15 validators, 28 decisões locked. `docs/design/` cobre lente **arquitetura** (6 layers, decisões, phases técnicos, disciplinas) com profundidade — `00-vision.md` declara o quê o sistema **é** e o `ROADMAP.md` enumera phases técnicos pós-v1. Falta a lente complementar: **produto**.

A lacuna é concreta. Marina (mobile dev solo KMP/Android) chegando ao repo pela primeira vez consegue ler `00-vision.md` e entender "operating system for mobile feature development", mas não encontra **personas com nome**, **cenários de uso end-to-end**, **roadmap por onda de impacto**, nem **anti-personas explícitas**. Bruno (tech lead avaliando adopt) precisa decidir em <1 dia se vale para sua squad — sem PRD consolidado, ele tem que reconstruir o "para quem isso é" varrendo `04-pending.md` + `08-session-handoff.md` + roteiros UX. Sub-agente Claude futuro, recebendo context-pack pra escrever artefato, precisa de glossário canônico de termos (subtype, wave, card, L1/L2/L3, capability label, extension-feature) num lugar único.

A decisão tomada no brainstorming: **criar PRD consolidado paralelo** — não substituir nem absorver `docs/design/00-vision.md` (load-bearing, Mandamento #1) nem `docs/design/ROADMAP.md` (técnico). O PRD complementa a lente arquitetura com lente produto, e cross-refs bidirecionais explicitam a relação. Coexistência paralela é decisão consciente, não preguiça de refatorar.

## Decisões de design tomadas no brainstorming

1. **Audiência: mantenedor + Claude futuro (interno).** Não é open-source landing nem stakeholder-facing. Voz mentor calmo, PT-BR neutro. Diferencial em relação a 00-vision.md: didático sobre **personas humanas com nome** + **cenários narrativos**, não só princípios.

2. **4 artefatos em `docs/product/`.** Um PRD consolidado (00) como porta de entrada + 3 sub-docs detalhados (01-personas, 02-scenarios, 03-roadmap). Sub-docs são fonte de verdade pra detalhe; 00 é index + resumos com cross-refs.

3. **Localização: `docs/product/` novo diretório, numerado 00-03.** Coexiste paralelo com `docs/design/` (arquitetura) e `docs/ux/` (roteiros cinemáticos por comando). Cada um cobre um eixo: design = "por quê + como"; product = "para quem + cenários + ondas"; ux = "roteiro do comando X".

4. **Relação com docs existentes: COEXISTE EM PARALELO. Não mexer load-bearing.** `00-vision.md` e `ROADMAP.md` permanecem intactos. PRD apenas cross-refs. Tentar fundir geraria scope creep + risco de revisitar decisão locked.

5. **Idioma: PT-BR.** Preferência explícita do mantenedor; voz mentor calmo na superfície interna toda.

6. **Tamanho: Approach C "Comprehensive".** ~2370 LOC distribuídos: 00-prd ~600 + 01-personas ~600 + 02-scenarios ~770 + 03-roadmap ~400. Sem corte preventivo — o piloto do PRD é o próprio uso interno, então otimizar pra densidade narrativa, não pra brevidade.

## Seção 1 — Arquitetura geral dos 4 docs

```
docs/product/                                ← NOVO diretório (esta entrega)
├── 00-prd.md                                ~600 LOC — porta de entrada / consolidado
├── 01-personas.md                           ~600 LOC — 8 personas em 3 camadas
├── 02-scenarios.md                          ~770 LOC — 6 user journeys end-to-end
└── 03-roadmap.md                            ~400 LOC — 3 ondas + anti-roadmap + Eisenhower
```

**Coexistência em paralelo:**

| Diretório | Lente | Documentos âncora | Mudança nesta entrega |
|---|---|---|---|
| `docs/design/` | Arquitetura | 00-vision, 01-decisions, 02-phases, 04-pending, 05-filesystem-layout, 06-command-surface, 07-discipline, 08-session-handoff, ROADMAP | NENHUMA — intocado |
| `docs/ux/` | Roteiros cinemáticos por comando | 7 roteiros (init, plan, implement, verify, doctor, reconfigure, evolve) | NENHUMA — intocado |
| `docs/product/` | Produto (personas + cenários + ondas) | 00-prd, 01-personas, 02-scenarios, 03-roadmap | NOVO — criado nesta entrega |
| `docs/schemas/` | Schemas YAML/JSON | 9 schemas + capability-labels | NENHUMA — só cross-ref |
| `docs/lifecycle/` | Dataflow lifecycle | memory-and-graph | NENHUMA — só cross-ref |

**Princípio de cross-ref bidirecional:** cada doc do `docs/product/` referencia explicitamente os docs de `docs/design/` que ancoram seu conteúdo (ex.: 03-roadmap §7 mapeia 1:1 com `ROADMAP.md` técnico; 00-prd §10 lista todos os ponteiros canônicos). Bidirecional fica como TODO de polish — `docs/design/00-vision.md` ganhar nota "Lente produto complementar em `docs/product/00-prd.md`" é mudança em arquivo load-bearing e precisa de revisita explícita (Mandamento #1) — anotar em `04-pending.md` post-impl.

## Seção 2 — Estrutura detalhada `01-personas.md` (8 personas em 3 camadas)

### Camada A — Personas dedicadas (day-in-life completo, ~90 LOC cada)

**Marina — Mobile dev solo KMP/Android (PRIMÁRIA, ~90 LOC)**

- **Perfil:** 4-6 anos exp; squad pequena (1-3 devs); dona de feature ponta-a-ponta
- **Stack típica:** Kotlin/KMP/Compose/SwiftUI-via-shared/Koin Annotations/Nav3/REST-ou-Firebase/Room/DataStore
- **JTBD principal:**
  - Levar feature de ticket → shipado sem reinventar arquitetura
  - Não esquecer step crítico (BDD, analytics, threat model, regression test)
  - Manter padrão consistente entre features (DI, navegação, contracts)
  - Reduzir cerimônia em bugfix/refactor sem perder rigor
- **Frustrações sem forge:**
  - "Cada feature começa do zero — copio estrutura de feature anterior e adapto"
  - "PRD fragmentado entre Confluence + Notion + comentário de PR"
  - "Bugfix urgente pula PRD; semanas depois esqueço de adicionar regression test"
  - "Hilt/Koin/Apollo/Retrofit — cada projeto novo tenho que decidir do zero"
- **Critérios sucesso com forge:**
  - `forge plan` → readiness=ready em ≤15min para feature product nova
  - Zero atalho-virou-hábito (regression test obrigatório em bugfix; analytics obrigatório em feature product)
  - Retros geram L2 patterns sem ela escrever doc manualmente
- **Day-in-life típico (terça-feira):**
  - 9h: standup mostra Marina vai pegar IN-42100 "Lembrete de rega de planta"
  - 9:15: `forge plan lembrete-rega` → subtype=product detectado; Wave A (intake) preenche user value + persona + scope
  - 9:30-10h: Wave B (PRD + screen-analysis) — PM cola descrição + Figma, Marina valida
  - 10-10:30: Wave C (contracts) + Wave D (tech-spec + 8 tasks)
  - 10:30: Wave E (readiness=ready)
  - 10:45-14h: `forge implement lembrete-rega` task-por-task, atomic commits, gates de scope
  - 14:30: `forge verify` cascade verde
  - 14:45: auto-retro dispara → 3 evolutions L2 (analytics naming patch, screen-state convention, agent prompt addition)
  - 15h: revisa via `forge evolve`, aceita 2 reject 1

**Bruno — Tech lead/staff engineer (SECUNDÁRIA, ~90 LOC)**

- **Perfil:** 7-12 anos exp; lidera squad 3-8 devs; decide adopt de ferramentas
- **Stack típica:** mesma de Marina, mas pivota entre projetos com stacks heterogêneas (Hilt aqui, Koin lá, Apollo num, Retrofit noutro)
- **Momentos de uso forge:**
  - Onboarding squad nova (forge init)
  - Configurar cards locais quando stack foge canon (Gap 5 — `.claude/cards/local/`)
  - Revisar proposed-evolutions (`forge evolve`)
  - Supervisionar sem revisar cada PR manualmente
- **JTBD principal:**
  - Garantir que squad segue o padrão sem PR review eterno
  - Acumular learnings em L2 (memory project) pra reuso
  - Decidir adopt em <1 dia sem onboarding extenso pra cada dev
  - Cards locais cobrem stack-specific (Hilt em projeto Android-only, p.ex.)
- **Frustrações sem forge:**
  - "Onboarding leva 2 semanas — cada dev novo aprende padrões via osmose de PR review"
  - "Mesma decisão de UI / contract / DI debatida em 4 PRs distintos por mês"
  - "Sem trilha WHY — decisão tomada em huddle some quando dev sai"
- **Critérios sucesso com forge:**
  - `forge init` → squad alinhada com preset+cards em <1 dia
  - L2 captura ≥80% dos patterns repetidos sem dev escrever doc
  - Cards locais cobrem stack-specific quando canon não cobre (Gap 5)
- **Day-in-life típico (quarta tarde):**
  - 14h: dev novo entra na squad — Bruno roda `forge init` no projeto-x KMP
  - 14:30: Step 11.5 detecta 47 findings em 6 categorias de reuse-intelligence
  - 15h: Bruno revisa amostragem; gera proposed-evolutions
  - 15:30: deixa rodando, dia seguinte Marina vai aceitar/rejeitar
  - 16h: revisão de PR de outro dev — vê forge implement gerou diff dentro de allowed_files; review focal em arquitetura, não compliance mecânico

**Sub-agente Claude — Persona TÉCNICA não-humana (~90 LOC)**

- **Perfil:** 3 roles distintos: planning-conductor, executor, readiness-reviewer
- **Inputs canônicos esperados:**
  - Context-pack (subtype, wave_b_required, external-deps, allowed_files, voz mentor calmo)
  - Agent prompt (frontmatter + extension-points conforme `agents/<name>.md`)
  - Cards merged (catálogo canon ∪ local overlay)
  - L1 status atual (intake / planning / implementing / verified / done / blocked-on-external / deferred)
- **Outputs canônicos esperados:**
  - Artefatos preenchidos (PRD, screen-analysis, tech-spec, task-contract)
  - Diff respeitando allowed_files da task
  - Feedback 3-caminhos em qualquer gate violation
- **5 critérios sucesso (não-negociáveis):**
  1. **Determinismo:** mesma entrada → mesma saída (sem invenção criativa)
  2. **Escopo:** allowed_files respeitado (sem refactor "while I'm here")
  3. **Voz:** mentor calmo PT-BR, warm em exploração, firme em gates
  4. **Never-invent:** se fonte ausente → `needs-elicitation`, não chuta
  5. **3-caminhos:** em qualquer ambiguidade/violação, 3 opções exatas (nunca 2, nunca 4)
- **Frustrações sem forge:**
  - "Context-pack vago → improviso interpretação"
  - "Sem extension-points formais → drift entre dispatches"
  - "Sem 3-caminhos canônico → silent skip vira hábito"
- **Day-in-life típico (Wave A dispatch pra subtype=bugfix):**
  - Recebe context-pack com `subtype=bugfix`, `ticket=IN-37234`, `wave_b_required=false`
  - Renderiza `feature-intake-bugfix.template.md` com prompts pra repro + root cause + risk
  - Marina preenche, sub-agente valida, salva L1
  - Devolve `state=planning` pro orchestrator
  - Próximo dispatch (tech-spec stripped) já vem com state coerente

### Camada B — Variantes da Marina (formato + caveats, ~55 LOC cada)

**Carlos — Android-only sem KMP (~55 LOC)**

- **Diferencial:** stack 100% Android (Kotlin + Compose + Hilt-OU-Koin + Retrofit + Room); nada de iOS, nada de KMP shared
- **Posicionamento v1:** "funciona out-of-box; cards iOS/KMP que sobram são noise tolerável"
- **Caveats leves:**
  - `forge init` auto-detection funciona — preset kmp-mobile aplica
  - Cards `kmp-shared`, `skie-bridge` ficam ociosos (sem signal positivo)
  - Cards `swiftui-screens`, `swiftui-navigation` não ativam (sem signal)
  - Hilt **não tem card canon em v1.2** (Koin é o canon mobile) — pode rodar via Gap 5 (`.claude/cards/local/hilt-di/`)
  - Retrofit JÁ é canon desde Gap 5 (v1.2.0) — sem caveat
- **JTBD herdado da Marina + nuance:** mesmo loop de planning + implement, mas sem custo de pensar em paridade iOS/KMP

**Lucas — iOS-only sem KMP (~55 LOC)**

- **Diferencial:** stack 100% iOS/Swift (SwiftUI + Combine + Swift packages); nada de Android, nada de KMP
- **Posicionamento v1:** "funciona pra você com trabalho manual; v1.x+ entrega UX nativa quando demanda concreta justificar"
- **Caveats v1 (TABELA OBRIGATÓRIA no doc):**

| Aspecto | Estado v1.2 | Comportamento | Workaround |
|---|---|---|---|
| Preset dedicado `ios-only` | ❌ não existe | `forge init` não detecta auto | Manual via `forge reconfigure` |
| Auto-detection em `forge init` | ❌ retorna 0 signals positivos | Sem preset aplicado | Manual via menu |
| Cards canon utilizáveis | ✅ `swiftui-screens`, `swiftui-navigation`, `auth-jwt-bearer`, `crashlytics`, `firebase-storage` | Aplicam-se normalmente | — |
| Cards canon NÃO utilizáveis | ❌ `kmp-shared`, `koin-annotations`, `kotlin-language`, `skie-bridge`, `ktor-client`, `retrofit-client`, `room-database`, `datastore-prefs`, `shared-preferences-prefs` | Não ativam (sem signal) | — |
| Customização pra stack | ✅ Gap 5 cobre — `.claude/cards/local/` | Cards iOS locais (Alamofire, KeychainAccess, etc.) | Caminho oficial |
| Roadmap pra UX nativa | Onda 2 cobre preset `ios-only` | Quando demanda concreta justificar | — |

**Carolina — Dev iniciante / onboarding (~55 LOC)**

- **Diferencial:** 1-3 anos exp; primeira squad mobile real; aprendendo padrão arquitetural
- **JTBD diferenciado em relação à Marina:** não só "entregar feature" mas TAMBÉM "entender por quê assim"
- **Forge usa também como material didático:**
  - Templates ensinam estrutura (intake → PRD → screen → contracts → tech-spec → tasks → readiness)
  - Validators ensinam regras (analytics obrigatório, BDD obrigatório, threat model em features sensíveis)
  - Cards explicam padrões com `README.md` substantivo por card
  - Persona mentor calmo é didática por design (warm em exploração, firme em gates)
  - 3-caminhos é treino de raciocínio (forçada a pensar trade-off em cada gate)
- **Frustração sem forge:**
  - "Squad sênior decide tudo em PR review com comentário de 1-linha; trava o time"
  - "Cada decisão arquitetural me chega como fato consumado, não como trade-off"
- **Critério sucesso:** PRs mergeáveis em <2 semanas após onboarding (vs ~2 meses sem ferramenta dirigida)

### Camada C — Downstream / read-only (~30 LOC cada)

**Patricia — PM / Product Owner (~30 LOC)**

- **NÃO toca código.** Não opera forge diretamente
- **Única interação com forge:** `forge status` read-only board
- **JTBD principal:** visibilidade real-time do estado de cada feature sem perguntar ao dev
- **Frustração sem forge:** "standup 9h só pra saber 'tá pronto?'; backlog tem 12 features em estado desconhecido"
- **Boundary explícito:** forge NÃO faz estimativa de tempo, schedule, priorização. Esses são domínio do PM (00-vision §What feature-forge is NOT). Patricia ganha **visibility**, não **decision-making automation**.

**Diego — Code reviewer humano (~30 LOC)**

- **Dev senior** que revisa PRs no GitHub/GitLab. NÃO opera forge
- **Interação com forge:** indireta — recebe PR criado por dev que rodou forge implement
- **Expectativas em PR forge-gerado:**
  - Escopo respeitado (diff cabe em allowed_files declarados na task)
  - Contracts seguidos (BDD bate com analytics-spec; tech-spec bate com tasks)
  - Analytics/threat/regression tests presentes
  - Mensagens de commit canônicas
- **JTBD principal:** review focal em arquitetura/produto, não em compliance mecânico
- **Frustração sem forge:** "80% do review é console.log esquecido ou BDD ausente — ruído mecânico que rouba tempo do que importa"
- **Critério sucesso:** disciplina mecânica passa antes do PR chegar; review humano debruça-se em decisão arquitetural

## Seção 3 — Estrutura detalhada `02-scenarios.md` (6 user journeys)

Cada cenário segue a mesma estrutura:

```
**C{N}. {Título conciso}** (persona principal, ~LOC)
Estado inicial: ...
Estado final: ...
Passos (numerados): ...
Outcome (uma frase): ...
Cross-ref: docs/ux/<roteiro>.md + docs/design/<doc>.md
```

### C1 — Brownfield init com reuse-intelligence (~120 LOC)

- **Persona principal:** Bruno (+ Marina dia seguinte)
- **Estado inicial:** Projeto KMP existente, ~150 features históricas shipadas, helpers duplicados conhecidos (validateName, formatPrice, etc.), sem disciplina forge instalada
- **Estado final:** `.claude/` inicializado + workflow-config.yaml válido + L2 com signals do reuse-intel scan Step 11.5 (6 categorias de finding); cards-local manifest se necessário
- **Passos:**
  1. Bruno roda `forge init` em projeto-x
  2. Init confirma preset `kmp-mobile` + backend REST (auto-detect)
  3. Step 11.5 dispara — scan retorna 47 findings em 6 categorias (duplicates-within-module, promote-to-shared, redundant-platform, near-duplicate, kmp-migration-candidate, consolidate-ts-helpers)
  4. Bruno revisa amostragem inline (não aceita/rejeita ainda — só registra)
  5. Init gera `proposed-evolutions.yaml` com os 47 findings
  6. Marina dia seguinte roda `forge evolve` → review 47, accept 30, reject 12, defer 5 (fingerprint anti-redundância protege próxima execução)
- **Outcome:** 30 reuse opportunities prontas pra puxar; L2 acumula learnings sem dev escrever doc; Bruno reduz "learn-by-PR" pra "learn-by-card + local-pattern"
- **Cross-ref:** `docs/ux/forge-init-roteiro.md` Cenas 5.5 + 5.6; `docs/lifecycle/memory-and-graph.md`

### C2 — Feature product nova end-to-end (~150 LOC)

- **Persona principal:** Marina
- **Estado inicial:** Ticket IN-42100 "Lembrete de rega de planta" — PM passou 2 acceptance criteria + screenshot Figma; sem PRD/screen design escritos
- **Estado final:** Feature `lembrete-rega` shipada em Android + iOS + KMP shared; commits atômicos por task; L2 distill aplicado pós-retro
- **Passos:**
  1. `forge plan lembrete-rega` → subtype=product (default)
  2. Wave A intake (user value / scope / persona)
  3. Wave B PRD + screen-analysis (cola Figma + descrição PM)
  4. Wave C contracts (BDD, analytics-spec, threat model, data-contract-spec)
  5. Wave D tech-spec + 8 tasks (com `allowed_files` declarados)
  6. Wave E readiness=ready
  7. `forge implement lembrete-rega` task-por-task com gates de scope + atomic commits
  8. `forge verify` cascade 15 validators → verde
  9. Auto-retro dispara → 3 evolutions L2 sugeridas
  10. Marina revisa via `forge evolve`, aceita as relevantes
- **Outcome:** ~15min Wave A-E + ~4h implement = feature shipada com analytics/threat/tests; sem "esqueci BDD ou analytics na correria"
- **Cross-ref:** `docs/ux/forge-plan-roteiro.md` + `docs/ux/forge-implement-roteiro.md`; `docs/design/07-discipline.md`

### C3 — Bugfix com ticket IN-37234 (~120 LOC)

- **Persona principal:** Marina (modo P0 stress)
- **Estado inicial:** Crashlytics alerta 9h: 12% das sessions Android 14 estão crashando; ticket IN-37234 aberto urgente; stack trace aponta `BonsaiForm` validação do field "name" com NPE
- **Estado final:** Fix shipado em <30min com regression test obrigatório + 5-whys retro registrado em L2
- **Passos:**
  1. `forge plan IN-37234` → detecta ticket-pattern + keywords ("crashing", "Android 14") → propõe subtype=bugfix
  2. Cena 2.5 confirma subtype=bugfix com Marina
  3. Wave B sub-question: "envolve mudança de UI?" → não, lógica pura → `wave_b_required=false`
  4. Wave A renderiza `feature-intake-bugfix.template.md` (formato bugfix, não product)
  5. Marina preenche (repro / root cause / risk level)
  6. Wave C-D tech-spec stripped + 2 tasks (fix + regression test)
  7. `forge implement IN-37234` aplica fix + regression test **obrigatório** (validator hard-fail se ausente)
  8. Auto-retro 5-whys → evolution "trim() canônico em validação de nome" pra L2
- **Outcome:** ~25min ticket → merge vs ~60min se rodasse fluxo product completo; regression test garante o bug não voltar; retro evolui o canon sem Marina escrever doc manual
- **Cross-ref:** `docs/design/04-pending.md §Gap 1` (subtype=bugfix); `agents/planning-conductor.md`

### C4 — Retomar trabalho pausado (~100 LOC)

- **Persona principal:** Marina (cold-start cenário)
- **Estado inicial:** Wave D feature `agenda-poda` terminou ontem 18h; Marina deu Ctrl+C antes da Wave E (readiness); `.planning/agenda-poda/` tem `state=deferred`; sessão Claude Code de ontem encerrada
- **Estado final:** Feature continua de onde parou; readiness rola hoje sem reescrever Waves A-D
- **Passos:**
  1. Marina abre sessão Claude Code nova hoje 9h (contexto zerado — Claude não lembra de ontem)
  2. `forge status` → board mostra `agenda-poda` em estado deferred, Wave D verificada em ontem 18h
  3. `forge plan agenda-poda` → engine detecta `state=deferred` + `last-wave=D` → auto-resume
  4. Conductor: "Retomando agenda-poda. Wave D foi verificada em 2026-06-03 18:00. Continuando Wave E (readiness)..."
  5. Wave E readiness=ready em 5min
  6. Marina segue pra `forge implement`
- **Outcome:** zero retrabalho, zero "qual era mesmo o contract da analytics?"; auto-resume é estado normal do fluxo, não exceção
- **Cross-ref:** `docs/design/07-discipline.md §7` (pause vs deferred vs aborted); `docs/design/01-decisions.md` Decision 27

### C5 — Extension feature (Gap 9) (~130 LOC)

- **Persona principal:** Marina
- **Estado inicial:** Feature `lembrete-rega` shipped semana passada (state=done); PM volta pedindo "lembrete por hora, não só por intervalo de dias" — é follow-up natural da feature anterior, não feature nova do zero
- **Estado final:** Feature `lembrete-rega-hora` derivada com `extends-feature: lembrete-rega`; reusa user value + persona + business outcome herdados do parent; cards e analytics-spec contextualizados via parent
- **Passos:**
  1. `forge plan lembrete-rega-hora` → Cena 1 mostra 4 caminhos: Greenfield / Retomar / Bugfix / **Estender** (conditional state=done)
  2. Marina escolhe **Estender**, indica `parent=lembrete-rega`
  3. Validator `validate_extension_feature` (EXT-001..004) confere: parent existe + parent.state==done + `extends-feature` setado + slug derivado válido
  4. Wave A skipa elicit redundante (user value / business outcome / persona vêm herdados — render do parent em modo "context import")
  5. Wave B só pergunta delta (o que muda: novo trigger hora-do-dia)
  6. Wave C-D-E normais, mas tech-spec contextualiza parent (referencia entities + screens do parent)
  7. `forge implement` aplica fix + ajustes
  8. `status.json` grava `extends-feature: lembrete-rega` + `shipped-at` em transição state=done
- **Outcome:** Pattern leve product-derived sem cards canon novos, sem upgrade de schema, sem mudar enum platforms; Marina não re-explica "por que essa feature existe" — herda do parent
- **Cross-ref:** `docs/design/07-discipline.md §10`; `docs/design/04-pending.md §Gap 9`; `agents/planning-conductor.md` (4º caminho em Cena 1)

### C6 — Reuse intelligence em ação (~120 LOC)

- **Persona principal:** Bruno + Marina
- **Estado inicial:** Squad com 18 features shipadas; pattern `validateName()` aparece em 7 Android + 5 iOS Swift + 3 KMP shared (15 instâncias com leve drift); ninguém promoveu pra shared ainda
- **Estado final:** Helper consolidado em `:shared:core:validation` + cards-local atualizado pra autoinject; 12 features migradas em PRs separados (não atrasa a feature 19 em planejamento)
- **Passos:**
  1. Marina planejando feature 19 `agenda-poda`; Wave B conductor consulta `forge graph Q12` (consolidate-within-module) + `Q15` (near-duplicate)
  2. Graph retorna: "validateName aparece em 15 lugares; sugere promote-to-shared"
  3. Conductor: "Detectei reuse-opportunity. Sugiro PR separado pra promover validateName pra :shared:core:validation. Continuar com feature 19?"
  4. Marina: "sim, em PR separado" — registra proposal pra Bruno revisar
  5. Bruno quinta abre `forge evolve` → vê 47 proposals fresh; filtra `kind=promote-to-shared` → 5 propostas
  6. Aceita validateName promotion → engine gera diff (extract + replace calls + import update)
  7. Marina dia seguinte mergeia + atualiza `.claude/cards/local/` com referência ao helper consolidado
- **Outcome:** Sem Bruno repetir "promova validateName" em PR review eterno; engine detecta + propõe + humano decide. 15 lugares → 1 lugar pra manter (drift entre as 15 versões era pequeno mas crescente).
- **Cross-ref:** `docs/lifecycle/memory-and-graph.md`; `docs/schemas/graph.md §Q12-Q17`

## Seção 4 — Estrutura detalhada `03-roadmap.md` (3 ondas + anti-roadmap)

### §1 — Princípios do roadmap-produto

- **Demand-driven** — onda entra com base em demanda real de persona, não em "checklist técnico bonito"
- **Persona-impact** — cada onda lista qual persona ganha o quê (não só "Phase 6 done")
- **Backwards-compat** — schema migrators via `forge raw migrator-N-to-M`; nunca breaking change silencioso
- **Auditável** — cada onda fechada vira entry em CHANGELOG + handoff
- **Anti-roadmap explícito** — listar o que **NÃO** entrará é tão importante quanto o que entra

### §2 — Onda 1: "Autopilot completo" (v1.3 → v1.4)

- **Persona primária impactada:** Marina (mobile dev solo)
- **Personas secundárias:** Carlos, Lucas (caveats reduzidos), Carolina (didática operacional), Sub-agente Claude (pode aplicar diff end-to-end)
- **Phase técnico correspondente:** `ROADMAP.md` Phase 6 (Apply Mode + LLM hookup + Atomic Commit + Retro auto-trigger)
- **Outcome esperado:** `forge implement` deixa de ser stub manual → autopilot real. Marina passa de "ajuda metade" pra "dirige e confirma". Sub-agente Claude pode aplicar diff end-to-end (não só renderizar template).
- **OKRs aspiracionais:**
  - Time-to-merge (ticket → PR merged): ≤4h (hoje ~6-8h)
  - Manual edits per task: 0 (hoje 5-15)
  - Regression rate cross-feature (bug retornando): ≤2%
- **Anti-feature explícito (NÃO entra na Onda 1):**
  - Automatizar decisão de produto — usuário decide WHAT, engine dirige HOW
  - Pre-commit review humano automatizado — Diego (humano) ainda decide se PR merge
  - IDE plugin — CLI-first permanece

### §3 — Onda 2: "Catálogo evolutivo + colaboração" (v1.5 → v2.0)

- **Persona primária impactada:** Lucas (iOS-only ganha UX nativa) + Bruno (squad maior + multi-dev)
- **Personas secundárias:** Patricia (filtros em `forge status`), Carolina (mais material didático em cards)
- **Phase técnico correspondente:** `ROADMAP.md` Phase 7 (Tree-sitter AST) + Gap 5 maturity + multi-dev opcional
- **Outcome esperado:**
  - Preset `ios-only` shippa → Lucas tem UX nativa em vez de manual
  - Cards canon iOS standalone (sem assumir KMP)
  - Marketplace **LOCAL** de cards maduro (não pública — Gap 5)
  - Multi-dev opcional (2 devs simultâneos na mesma feature, merge-strategy resolvida)
  - Patricia: `forge status --release-q3` (filtros temporais e por sprint)
- **OKRs aspiracionais:**
  - Preset count: 1 → ≥3 (`kmp-mobile`, `ios-only`, `android-only`)
  - Cards locais aceitos por squad: ≥5 (vai indicar Gap 5 maduro)
  - Features merged sem conflict em multi-dev: ≥10 cumulativo
- **Anti-feature explícito (NÃO entra na Onda 2):**
  - Marketplace **pública** de cards — viola Decision 22 (no runtime deps em outras skills); Gap 5 cobre apenas local
  - Hosted service / SaaS — CLI-first permanece (Decision 18)
  - Multi-target watchOS/Wear/TV — Gap 9 revisita 2026-06-03 moveu pra **out-of-scope permanente**

### §4 — Onda 3: "Inteligência adaptativa" (v2.x — aspiracional)

- **Persona afetada:** TODAS (transversal)
- **Phase técnico correspondente:** `ROADMAP.md` Phase 7+ (AST semantic) + LLM real-time signals
- **Outcome esperado:**
  - Reuse-intelligence semantic, não syntactic (resolve `kmp-migration-candidate` shallow confidence)
  - Conductor lembra decisões cross-feature (L3 cross-project memory ativa)
  - Engine sugere subtype / cards / threat model com base em L2+L3 history (não só catálogo estático)
  - Carolina: `forge ensina <pattern>` (verbo novo Onda 3?) — explora cards + decisões com lente didática
  - Sub-agente Claude opera com confiança histórica (sabe que decisão X foi tomada 12x antes)
- **OKRs aspiracionais:**
  - Drill-down rounds (Wave A perguntas): 2 → 0.5 em média
  - Questions per Wave A: -30%
  - L2 patterns auto-inject: ≥60% das features
- **Anti-feature explícito (NÃO entra na Onda 3):**
  - Tomar decisões sem confirmação humana — sempre 3-caminhos antes de mutação
  - Substituir mentor humano — engine ensina padrões, humano ensina contexto/cultura

### §5 — Matriz Eisenhower (persona-impact × esforço)

|  | Low-effort | High-effort |
|---|---|---|
| **High-impact** | Onda 1 (Autopilot) — done now | Onda 2 (Catálogo) — strategic |
| **Low-impact** | Backlog 04-pending (gaps individuais) | Anti-roadmap (rejected — §6) |

**Onda 1 é low-effort, high-impact?** Sim, em termos relativos — Phase 6 técnico é L (large), mas no eixo persona-impact é direct hit em Marina (primária); a parte cara da arquitetura já foi feita em v1.0-v1.2.

### §6 — Anti-roadmap (NÃO entrará — explícito com rationale)

| Item | Por quê NÃO | Cross-ref |
|---|---|---|
| Multi-target watchOS / Wear OS / tvOS | Out-of-scope **permanente** (Gap 9 revisita 2026-06-03). Caminho oficial pra plataforma exótica é Gap 5 overlay local, não canon expansion. | `docs/design/04-pending.md §Gap 9 §OUT-OF-SCOPE explícito` |
| PM / scheduling / estimativa | Boundary explícito em `00-vision.md §What feature-forge is NOT`. Patricia ganha **visibility**, não decision-making | `docs/design/00-vision.md` |
| Code review final automático | Diego (humano) decide. Forge detecta violações; veredito final é humano | `docs/design/00-vision.md` |
| Hosted service / SaaS | CLI-first (Decision 18 + 22). Snapshot copy local via `forge init` | `docs/design/01-decisions.md` D18, D22 |
| Marketplace pública de cards | Viola Decision 22. Gap 5 cobre local; pública exige runtime registry → quebra portability | `docs/design/01-decisions.md` D22 |
| Auto-decidir produto / arquitetura | Decisão de produto e arquitetura é do usuário. Engine pode sugerir, nunca decidir | `docs/design/00-vision.md` |
| IDE plugin (VSCode/IntelliJ) | CLI-first permanece. Integração via shell hooks, não plugin nativo | `docs/design/00-vision.md` |
| Skill auto-installer cross-project (multi-skill orchestrator) | Snapshot via `forge init` (Decision 22). Cada projeto tem cópia local; sem dep runtime | `docs/design/01-decisions.md` D22 |

### §7 — Cross-ref bidirecional com `docs/design/ROADMAP.md` técnico

| Onda produto (este doc) | Phase técnico (`ROADMAP.md`) | Conexão |
|---|---|---|
| Onda 1 (Autopilot) | Phase 6 (Apply Mode + LLM hookup) | 1:1 — Onda 1 É Phase 6 visto pela lente persona |
| Onda 2 (Catálogo) | Phase 7 (Tree-sitter) + Gap 5 maturity | Phase 7 habilita semantic reuse; Gap 5 escala overlay local |
| Onda 3 (Inteligência) | Phase 7+ + LLM real-time signals | Aspiracional — não bloqueia v2.0 |

**Phases técnicos sem onda direta** (continuam relevantes no eixo técnico):
- Phase 8 (MCP real connections) — entra sob demanda, não casa com onda persona específica
- Phase 9 (cards reservados) — incremental por card
- Phase 10 (cards legacy) — demand-driven por projeto-alvo
- Phase 11 (Windows support) — demand-driven
- Phase 12 (validators expandidos) — incremental
- Phase 13 (marketplace pública) — ANTI-ROADMAP (não entrará)

## Seção 5 — Estrutura detalhada `00-prd.md` (13 seções, porta de entrada)

Cada seção é resumo + cross-ref pro sub-doc relevante. ~600 LOC totais.

### §1 — Por que feature-forge existe (~50 LOC)

- Problema observado em campo:
  - Cada feature começa do zero mesmo com squad madura
  - Disciplina mecânica (BDD / analytics / threat / regression) cai em PR review
  - Refactor + bugfix urgente vira atalho ("faço quick e depois adiciono test")
  - Onboarding lento (~2 semanas pra dev novo)
  - KMP + Android + iOS triplica esforço sem ferramenta dirigida
- WHY (1 parágrafo): "Operating system for mobile feature development" — sistema que absorve patterns, acumula knowledge, reduz ambiguidade a zero. Engine dirige HOW; usuário decide WHAT.

### §2 — Vision (lente produto, complementa 00-vision.md arquitetural) (~40 LOC)

- 2-3 parágrafos de posicionamento
- CLI-first / file-driven / conversacional (zero flags)
- Diferencial técnico: cards atômicos + memory L1/L2/L3 + reuse-intelligence
- Promessa: feature N+30 é mais rápida que feature N porque memory acumula
- Boundary: NÃO é PM, NÃO é arquiteto, NÃO é code reviewer

### §3 — Princípios não-negociáveis (7) (~60 LOC)

1. **Never invent** — sem fonte → `needs-elicitation`
2. **Files > Memory** — file-driven, resumível, inspecionável
3. **Usuário decide WHAT** — engine dirige HOW
4. **Mentor calmo voz** — warm em exploração, firme em gates, didático
5. **3-caminhos em qualquer gate violation** — sempre 3, nunca 2, nunca 4
6. **Reversibilidade** — toda action é undo-able; sem hidden state
7. **Persona-native vocabulary** — engine lê CLAUDE.md + rules + docs/design

### §4 — Escopo IN / OUT (tabela completa) (~60 LOC)

| Categoria | IN | OUT |
|---|---|---|
| Lifecycle | Planning + implementation | — |
| Disciplina | BDD, analytics, threat, regression, scope, atomic commits | — |
| Knowledge | L1/L2/L3 memory + graph + inventory + reuse-intel | — |
| Plataformas | Android + iOS + KMP + Web | watchOS, Wear OS, tvOS (Gap 9 permanente) |
| Backend | Firebase + REST + GraphQL (Reservada) + local-only | Hosted service / SaaS |
| Voz | Mentor calmo PT-BR neutro | Voz corporativa |
| Subtypes | product / refactor / bugfix (+ spike/chore stubbed) | — |
| Reversibilidade | `forge undo` per target | — |
| Decisões | Engine sugere | Engine **decide** produto/arch |
| Code review | Detecta violações | Veredito final humano |
| PM | `forge status` visibility | Estimativa / schedule / priorização |
| Marketplace | Cards locais (Gap 5) | Marketplace pública |
| Distribuição | Snapshot copy via `forge init` | Auto-installer cross-project |
| IDE | Integração via shell hooks | Plugin nativo |

### §5 — Personas (resumo + link → 01-personas.md) (~50 LOC)

- **Camada A (dedicadas):** Marina (primária), Bruno (tech lead), Sub-agente Claude (técnica)
- **Camada B (variantes Marina):** Carlos (Android-only), Lucas (iOS-only), Carolina (iniciante)
- **Camada C (downstream/read-only):** Patricia (PM), Diego (code reviewer)
- Cada uma com 1 linha de identidade + link "Detalhe em [01-personas.md §X]"

### §6 — Cenários de uso (resumo + link → 02-scenarios.md) (~50 LOC)

- C1. Brownfield init com reuse-intelligence (Bruno+Marina)
- C2. Feature product nova end-to-end (Marina)
- C3. Bugfix com ticket IN-37234 (Marina P0)
- C4. Retomar trabalho pausado (Marina cold-start)
- C5. Extension feature Gap 9 (Marina)
- C6. Reuse intelligence em ação (Bruno+Marina)
- Cada um com 1-linha outcome + link "Detalhe em [02-scenarios.md §CN]"

### §7 — Roadmap produto (resumo + link → 03-roadmap.md) (~40 LOC)

- 3 ondas (Autopilot / Catálogo / Inteligência) + anti-roadmap em 1-linha cada
- Matriz Eisenhower em mini-versão
- Link "Detalhe em [03-roadmap.md §X]"

### §8 — Success criteria & métricas (~70 LOC)

- **Qualitativos (sentimento por persona — uma frase cada das 8 personas):**
  - Marina: "Não preciso mais reinventar arquitetura por feature"
  - Bruno: "Onboarding em dias, não semanas"
  - Sub-agente Claude: "Context-pack determinístico me deixa entregar diff escopo-respeitado"
  - Carlos: "Funciona out-of-box mesmo sem KMP"
  - Lucas: "v1 entrega caminho manual; v1.x+ entrega UX nativa"
  - Carolina: "Aprendo padrão arquitetural fazendo, não só revisando PR review"
  - Patricia: "Vejo estado de cada feature sem perguntar"
  - Diego: "Reviews focados em arquitetura, não em compliance mecânico"
- **Quantitativos (aspiracionais v1.x+):**
  - Time-to-merge: ≤4h
  - Manual edits per task: 0
  - L2 auto-applied: ≥60%
  - Drill-down rounds: ≤1
  - Onboarding: ≤2 semanas
  - Regression cross-feature: ≤2%
- **Baseline atual (v1.2.0 + Gap 9):**
  - 637 tests passing, 22 cards, 15 validators, 17 graph queries
  - ~400 arquivos, ~52.500 LOC

### §9 — Anti-personas (quem NÃO usa — tabela) (~50 LOC)

| Anti-persona | Por quê não | O que faria sentido pra ela |
|---|---|---|
| Dev Flutter / React Native | Cards canon não cobrem; intent é Android+iOS nativo + KMP | Skill própria pra Flutter/RN |
| Backend-only / web puro React não-KMP | Assume Kotlin/Swift como linguagens-âncora; Web via `@JsExport` KMP, não React standalone | Skill backend ou skill web genérica |
| PM / designer operando diretamente | forge é dev-tool; downstream Patricia tem `forge status` | Confluence + Notion + Linear |
| Squad que rejeita disciplina mecânica | forge **é** a disciplina; sem ela perde sentido | — (não é uso adequado) |
| Projetos Java-only sem Kotlin moderno | Engine assume Kotlin como linguagem-âncora; templates/cards não cobrem Java puro | Skill Java/Spring genérica |

### §10 — Cross-refs docs técnicos (~50 LOC)

Tabela canônica:

| Doc | Lente | Quando consultar |
|---|---|---|
| `docs/design/00-vision.md` | Arquitetura (6 layers + capability cards) | Pra entender quê o sistema **é** |
| `docs/design/01-decisions.md` | 27 decisões locked + 7 direcionais + ADR 28 | Pra entender o **por quê** das escolhas |
| `docs/design/02-phases.md` | Phases técnicos entregues (1-5 + 3.5) | Pra ver o histórico de entrega |
| `docs/design/04-pending.md` | Gaps inventoriados | Pra entender o que falta |
| `docs/design/07-discipline.md` | 10 disciplinas universais | Pra aplicar gates corretos |
| `docs/design/08-session-handoff.md` | Estado canônico por versão | Pra retomar sessão fria |
| `docs/design/ROADMAP.md` | Phases técnicos pós-v1 (6, 7, 8, ...) | Pra ver o eixo técnico do roadmap |
| `docs/lifecycle/memory-and-graph.md` | Dataflow memory + reuse-intel | Pra entender L1/L2/L3 + 17 queries |
| `docs/schemas/*.md` | 9 schemas + capability-labels | Pra validar artefatos |
| `docs/ux/*.md` | 7 roteiros cinemáticos por comando | Pra ver UX do comando X |

### §11 — Glossary de termos canon (~80 LOC)

Tabela com ~15 termos. Cada um: definição 1-2 linhas + cross-ref pro schema/decision relevante.

| Termo | Definição | Cross-ref |
|---|---|---|
| **Subtype** | Variante de feature: `product` (default) / `refactor` / `bugfix` / `spike` / `chore`. Cada um tem waves específicas | `docs/design/04-pending.md §Gap 1, 2` |
| **Wave** | Fase de planning: A (intake), B (PRD+screen), C (contracts), D (tech-spec+tasks), E (readiness) | `docs/ux/forge-plan-roteiro.md` |
| **Card** | Unidade atômica de composição (templates+validators+agent-prompts). 22 canon + overlay local | `docs/schemas/card.md` |
| **Preset** | Alias para combinação de cards. v1.2: `kmp-mobile` (8 stack + 4 backend-candidates) | `docs/schemas/card.md` |
| **L1** | Memory per-feature (WIP). Grava estado intermediário em `.planning/<slug>/` | `docs/schemas/memory.md` |
| **L2** | Memory project-level (committed). Acumula learnings via retrospectivas | `docs/schemas/memory.md` |
| **L3** | Memory read-only (auto-memory cross-project, futuro) | `docs/schemas/memory.md` |
| **Capability label** | Abstração de capacidade (ex.: `http-client`, `auth-provider`, `persistence-local`) | `docs/schemas/capability-labels.md` |
| **Extension feature** | Pattern leve product-derived (Gap 9). Feature done estendida via slug derivado com `extends-feature` | `docs/design/07-discipline.md §10` |
| **Blocked-on-external** | L1 status pra feature esperando ação externa (auth provisioning, p.ex.) | `docs/design/04-pending.md §Gap 8` |
| **Backend-candidate** | Card sugerido mas não ativado até usuário escolher (REST vs Firebase, p.ex.) | `presets/kmp-mobile/preset.yaml` |
| **Reuse-intelligence** | 6 categorias de finding (Q12-Q17) que detectam reuse opportunities | `docs/lifecycle/memory-and-graph.md` |
| **Card local overlay** | `.claude/cards/local/<name>/` versionado, complementa canon (Gap 5) | `docs/superpowers/specs/2026-06-02-gap5-card-local-overlay-design.md` |
| **3-caminhos** | Padrão de gate-resolution: sempre 3 opções, nunca 2, nunca 4 | `docs/design/07-discipline.md §1` |
| **Phase lock** | Sentinel `.phase-lock` em `.planning/<slug>/` que previne concurrent operations | `docs/schemas/memory.md` |
| **Subagent (Claude Code)** | Distinto de `agent prompt` — subagent é instância Claude Code dispatchada via `Agent` tool; agent prompt é template em `agents/<name>.md` | `.claude/rules/subagent-workflow.md` |

### §12 — FAQ (~70 LOC, 9 perguntas)

| Q | A resumida |
|---|---|
| Por que zero flags? | Decision 10 LOCKED. Discoverability + persona-native vocabulary — toda parametrização via menu interativo |
| Por que Koin e não Hilt? | KMP + Android + iOS uniforme (Koin Annotations é multiplataforma; Hilt é Android-only). Hilt via Gap 5 quando demanda surgir |
| Como migro de feature-implementation-workflow? | `forge raw migrator-N-to-M` (stub v1 — implementação real demand-driven) |
| Multi-dev mesma feature? | v1 single-user; split em features menores como workaround. Onda 2 endereça merge-strategy |
| watchOS / Wear OS / tvOS? | Out-of-scope **permanente** (Gap 9). Caminho pra plataforma exótica é Gap 5 overlay local, não canon |
| Por que não automatiza decisão produto? | Engine dirige HOW (Decision principle 3); usuário decide WHAT |
| Java puro funciona? | Não — Kotlin é linguagem-âncora. Templates/cards/agents assumem Kotlin |
| Monorepo? | Sim (Decision 14 — config scope é um workflow-config por sub-projeto) |
| `forge implement` aplica diff auto? | v1 é stub manual (handoff em texto). Onda 1 (Phase 6) cobre apply mode real |

### §13 — Risks & Open questions (~80 LOC)

**Risks (6) com mitigação:**

| Risk | Mitigação |
|---|---|
| R1. "Mobile dev solo" perde relevância em squads grandes | Onda 2 cobre multi-dev opcional; v1 já funciona pra squad pequena (1-3 devs) |
| R2. Demanda real por marketplace pública | Gap 5 cobre local; pública viola Decision 22 — push-back firme com cross-ref |
| R3. Onda 1 (LLM hookup) tem custos não-escalonáveis | v1 mantém stub; Apply Mode é opt-in (user fornece API key); custo é do user, não do projeto |
| R4. Stack iOS/Swift puro pressiona preset `ios-only` antes da Onda 2 | Lucas com caveats v1; preset experimental v1.x+ se demanda concreta surgir antes |
| R5. Tree-sitter adoção implica dep externa + complexity | Regex pragmático v1 funciona; AST quando false-positive crítico aparecer (Phase 7) |
| R6. Squad grande adota → fricção com squad pequena (overhead) | Subtypes `bugfix`, `chore` (stubbed) dão fast-path; product subtype é opt-in implicitly via Cena 1 |

**Open questions (4):**

| Q | Status |
|---|---|
| Q1. Como migrar projeto que JÁ tem disciplina X (Confluence-driven, p.ex.)? | Brainstorm pendente; `forge ingest --event project-import`? Anotar em `04-pending.md` |
| Q2. Spike subtype real precisa "exploring" state ortogonal a normal | `04-pending §Gap 2` deferred v1.x+; spike stubbed mas não completo |
| Q3. Code review humano (Diego) ganha integração com forge? | Out-of-scope explícito v1; pode evoluir hook PR-side em v2+ se demanda surgir |
| Q4. Multi-dev mesma feature merge-strategy | `04-pending §Gap 6` deferred v1.x+ |

## Seção 6 — Cross-refs entre docs (matriz)

| De → Para | 00-prd.md | 01-personas.md | 02-scenarios.md | 03-roadmap.md | docs/design/* | docs/ux/* | docs/lifecycle/* | docs/schemas/* |
|---|---|---|---|---|---|---|---|---|
| **00-prd** | — | §5 personas resumo | §6 scenarios resumo | §7 roadmap resumo | §10 todos | §10 todos | §10 memory-and-graph | §10 capability-labels + schemas |
| **01-personas** | retorna ao 00 | — | persona em ação → §2 cenários | persona impactada por onda → §4 | 00-vision (Marina/Bruno), 01-decisions (Sub-agente Claude) | forge-plan-roteiro (Marina day-in-life) | — | card.md (Lucas caveats) |
| **02-scenarios** | retorna ao 00 | persona principal de cada C → §2 personas | — | onda que entrega cenário → §4 | 07-discipline (3-caminhos), 04-pending (Gap 1, 9), 01-decisions D27 | 7 roteiros (1:1 por scenario quando aplicável) | memory-and-graph (C1, C6) | graph.md Q12-Q17 (C6) |
| **03-roadmap** | retorna ao 00 | persona afetada por onda → §2 personas | exemplo de onda em ação → §3 scenarios | — | ROADMAP.md técnico (1:1 mapping) | — | — | — |

**Bidirecional como TODO de polish:** `docs/design/00-vision.md` e `docs/design/ROADMAP.md` permanecem sem mudança nesta entrega (load-bearing). Adicionar nota "Lente produto complementar em `docs/product/00-prd.md`" entra como polish item separado, com revisita explícita se necessário (`docs/design/00-vision.md` é load-bearing — qualquer edit aciona PreToolUse audit + considera Mandamento #1).

## Seção 7 — Voz e idioma

- **Idioma:** PT-BR neutro em todo o `docs/product/`. Não mistura EN-PT como `04-pending` ou `INFLUENCES` (esses são bilíngue por razões históricas).
- **Voz:** mentor calmo conforme `docs/design/07-discipline.md`:
  - **Warm** em exploração (personas com nomes próprios, day-in-life narrativos)
  - **Firme** em gates (anti-roadmap, anti-personas, boundary explícito)
  - **Didático** sem ser professoral (cross-refs canônicos, não explicação rasa)
  - **Concreto** sem jargão (Marina vs "primary persona", Lucas vs "iOS-only segment")
- **Nomeação de personas:** Marina, Bruno, Sub-agente Claude, Carlos, Lucas, Carolina, Patricia, Diego. Consistência rígida — não trocar Marina por Maria, Carlos por Carlitos, etc. Sub-agente Claude é a única não-humana (intencional — sublinha que ela é técnica).
- **Anti-padrões:**
  - Zero voz corporativa ("alavancamos", "value proposition", "stakeholder alignment")
  - Zero emoji decorativo. Exceções permitidas: ✅/❌/⭐/🛑 quando carregam semântica (status, indicador "Recommended", bloqueio). Sem inventar uso novo de emoji.
  - Zero "vou tentar", "talvez", "pode ser uma boa ideia" — compromete ou redireciona explicitamente
- **Tom em personas:** narrativo, não bullet-point seco. Day-in-life em prosa curta + dado concreto (hora, ticket ID).

## Seção 8 — Tamanho estimado e priorização de escrita

| Doc | LOC estimado | Densidade |
|---|---|---|
| `00-prd.md` | ~600 | Index + 13 seções resumidas + cross-refs |
| `01-personas.md` | ~600 | 8 personas (90×3 dedicadas + 55×3 variantes + 30×2 downstream) |
| `02-scenarios.md` | ~770 | 6 user journeys (120+150+120+100+130+120 + headers) |
| `03-roadmap.md` | ~400 | 7 seções (princípios, 3 ondas, Eisenhower, anti-roadmap, cross-ref) |
| **Total** | **~2370** | — |

**Ordem sugerida pra `superpowers:writing-plans` despachar:**

1. **Wave 1 — 01-personas.md** (sub-doc independente; fonte de verdade pra outras seções)
2. **Wave 2 — 02-scenarios.md** (depende de personas escritas pra cross-ref nomes)
3. **Wave 3 — 03-roadmap.md** (depende de personas pra "persona afetada por onda")
4. **Wave 4 — 00-prd.md** (porta de entrada — escreve por último com cross-refs estáveis pros sub-docs)

Cada wave é dispatch separado pra `gsd-executor` com context-pack contendo: este spec inteiro + arquivos load-bearing relevantes (00-vision, ROADMAP, 07-discipline, etc.) + ARQUIVOS PERMITIDOS estritamente o doc da wave + critério de sucesso testável (existe + LOC dentro do range + cross-refs canônicos + voz mentor calmo).

## Seção 9 — Out-of-scope deste spec

Pra desambiguar o escopo desta entrega vs próximas:

| Item | Status |
|---|---|
| Criar arquivos `docs/product/00-prd.md` + `01-personas.md` + `02-scenarios.md` + `03-roadmap.md` | **OUT-OF-SCOPE neste spec.** Spec é DESIGN; escrita real fica pra `superpowers:writing-plans` → `gsd-executor` em waves |
| Criar diretório `docs/product/` | OUT — vem na writing-plans dispatch |
| Mexer em `docs/design/00-vision.md` ou `docs/design/ROADMAP.md` | OUT — load-bearing, coexistência paralela é decisão tomada |
| Atualizar CHANGELOG.md, `08-session-handoff.md`, README.md, CLAUDE.md | OUT neste commit do spec — esses são doc-sync da **implementação real**, não do spec de design. Vai rolar quando os 4 docs forem efetivamente escritos |
| Refatorar `2026-06-02-gap5-card-local-overlay-design.md` (referência de formato) | OUT — usado só como referência canônica de header/seções/voz |
| Criar sub-arquivos auxiliares (figuras, snippets, glossário standalone) | OUT — spec é único MD self-contained |
| Decidir nomes finais de seções dentro dos 4 docs (não só estrutura) | IN-SCOPE com flexibilidade — writing-plans pode ajustar nomenclatura quando escrever, desde que preserve a substância declarada aqui |

## Próximos passos pós-spec

1. **User review do spec escrito** — checa fidelidade ao brainstorm + pontos não cobertos. Especialmente: nomes das personas Camada B/C aprovados? Ordem das ondas no roadmap aprovada? Tamanho ~2370 LOC ainda aprovado após ver o desenho em detalhe?
2. **Transição via `superpowers:writing-plans`** — produz plano executável em `docs/superpowers/plans/2026-06-04-prd-docs/PLAN.md` com 4 waves task-by-task, critério de sucesso testável por wave, allowed_files explícitos.
3. **Implementação dispatch-by-dispatch** — orchestrator-mantenedor dispatcha `gsd-executor` por wave (01-personas → 02-scenarios → 03-roadmap → 00-prd), trust-but-verify entre waves, review subagent ao final.
4. **Verification + doc-sync no commit final** — quando os 4 docs estiverem escritos e revisados: CHANGELOG.md `### Added` listando os 4 docs, `08-session-handoff.md` Última atualização + Estado refletindo entrega, README.md mantém stats (não muda — docs/product/ é novo eixo, não muda contagem de cards/tests/validators).
