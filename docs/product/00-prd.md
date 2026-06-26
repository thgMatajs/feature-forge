# PRD — feature-forge

> **Audiência:** mantenedor + Claude futuro (interno). Voz mentor calmo PT-BR neutro.
> **Status:** v1.2.0 + Gap 9 cumulativo (637 tests passing + 12 skipped, 22 cards canon, 15 validators, 17 graph queries, ~400 arquivos, ~52.500 LOC).
> **Cross-ref:** Este doc é a porta de entrada do PRD. Sub-docs: [`01-personas.md`](01-personas.md) (8 personas), [`02-scenarios.md`](02-scenarios.md) (6 cenários), [`03-roadmap.md`](03-roadmap.md) (3 ondas). Docs técnicos: ver §10.

PRD complementa [`docs/design/00-vision.md`](../design/00-vision.md) (lente arquitetura) com lente produto. Não substitui — coexiste em paralelo conforme decisão tomada no spec [`docs/superpowers/specs/2026-06-04-prd-design.md`](../superpowers/specs/2026-06-04-prd-design.md). Mesmo eixo de conhecimento, lente diferente.

`docs/design/` responde "como funciona arquiteturalmente"; este doc responde "pra quem isso é, em que cenário, e por quê esta onda agora". Os dois eixos andam juntos via cross-refs canônicos (§10) — não disputam autoridade.

---

## §1 — Por que feature-forge existe

Antes da síntese WHY, vale ancorar o problema concreto. feature-forge não surge de "vamos criar uma ferramenta legal de boilerplate"; surge de fricção repetida observada em squads mobile product-grade em produção. Cada bullet abaixo é um problema visto em campo, não hipotético — Marina, Bruno, Carolina, Diego sentem cada um deles no fluxo de trabalho semanal.

**Problema observado em campo (motivação concreta):**

- **Cada feature começa do zero** mesmo em squad madura. Dev copia estrutura da feature anterior e adapta — retrabalho mecânico que rouba tempo de decisões reais. Marina (mobile dev solo KMP/Android) sente isso a cada novo ticket; sem ferramenta dirigida, custo mental de "como vou estruturar isso?" sobe feature a feature em vez de cair. Boilerplate generator genérico (scaffolders, IDE templates) não resolve porque não acumula knowledge — cada projeto novo refaz as mesmas decisões sem trilha histórica.
- **Disciplina mecânica cai em PR review.** BDD ausente, analytics esquecido, threat-model adiado, regression test pulado em bugfix urgente — tudo vira ruído no review humano e custa 60% do tempo do Diego (code reviewer). Compliance mecânico deveria estar verificado antes do PR chegar; sem isso, review focal em arquitetura não existe. Diego acaba investindo 1h em PR pra apontar 5 erros mecânicos e 30s no único trade-off arquitetural real que valeria discussão. Sem cascade de validators automatizados em verify, esse desbalanceamento permanece estrutural — nenhuma boa intenção do Diego resolve.
- **Refactor + bugfix urgente vira atalho.** "Faço quick e adiciono test depois" — depois não chega. Bug volta semanas depois quando convenção informal (trim, null check, validação) é esquecida; sem regression test obrigatório, fica débito silencioso. Em P0 stress (Crashlytics alerta às 9h, 12% sessions crashando), Marina pula PRD e foca só no fix — comportamento racional sob pressão, mas custa caro daqui a 3 meses quando o mesmo bug volta porque convenção informal "fazer trim no caller" nunca foi documentada como pattern do projeto. Vide cenário C3 (IN-37234) em [`02-scenarios.md`](02-scenarios.md) — engine torna o caminho rápido sem perder rigor.
- **Onboarding lento** (~2 semanas pra dev novo em squad mobile, ~2 meses pra atingir produtividade plena de fato). Padrão arquitetural absorvido por osmose de PR review; frágil e demorado. Carolina (iniciante) leva 2 meses pra atingir produtividade plena sem ferramenta dirigida. Quando dev sai do time, conhecimento sai junto — arquitetura vira folclore oral. Sem repositório de WHY centralizado (cards com README substantivo, decisões locked com rationale escrito, retros L2 acumuladas), nova contratação repete o caminho da Carolina: 2 meses de osmose.
- **KMP + Android + iOS triplica esforço** sem ferramenta dirigida. Decisão de DI, navegação, persistência re-debatida em cada projeto novo; sem canon documentado por projeto, Bruno (tech lead) revisa as mesmas regras em 4 PRs distintos por mês todo mês. Hilt vs Koin, Retrofit vs Ktor vs Apollo, Room vs SQLDelight, Navigation 2 vs Nav3 vs custom — cada decisão sem trilha WHY vira religião no time. Quando o dev original que tomou a decisão sai, ninguém lembra do trade-off original, e o time acaba revisitando do zero ou pior: drift silencioso entre features porque ninguém quer reabrir o debate.

**WHY (síntese):**

feature-forge é um **operating system for mobile feature development** — sistema que absorve patterns, acumula knowledge em L1/L2/L3 memory, e reduz ambiguidade a zero via 3-caminhos canônico em qualquer gate. Engine **dirige HOW** (template + validator + agent prompt + atomic commit + retro automático); usuário **decide WHAT** (user value, persona, business outcome, trade-off arquitetural). A divisão de responsabilidade é load-bearing — Decision 22 ([`docs/design/01-decisions.md`](../design/01-decisions.md)) e §3 deste doc reforçam.

Sem essa ferramenta, padrões arquiteturais viram folclore oral, conhecimento sai junto com o dev que pediu demissão, e cada projeto novo refaz as mesmas decisões. Com ela, feature N+30 é mais rápida que feature N porque memory acumula — promessa central do produto.

**Por quê agora, e não daqui a 2 anos:** o ecossistema mobile (KMP + Compose + SwiftUI + Coroutines + Flow) atingiu maturidade suficiente pra ter canon documentável; LLMs como Claude Code atingiram capacidade pra rodar sub-agents determinísticos com 5 critérios de contrato (determinismo, escopo, voz, never-invent, 3-caminhos); e a fricção de "cada feature começa do zero" em squad mobile ficou alta o bastante pra justificar uma ferramenta dedicada com voz e disciplina próprias — não um boilerplate generator nem um yet-another-scaffolder.

**Por quê agora, e não há 5 anos:** KMP só ficou production-grade ~2023 (Compose Multiplatform 1.x stable; SKIE bridging maduro; expects/actuals em stable); LLMs com janela suficiente pra rodar sub-agents complexos (Claude 3.5+ / GPT-4+) só apareceram ~2024; disciplina mecânica via validators + retrospective auto-trigger só ficou viável quando o LLM podia rodar análise de diff cross-file. Ferramenta deste tipo em 2019 teria sido scaffolder genérico; hoje pode ser operating system real.

**Por quê mobile-focused, e não generalista:** generalizar pra qualquer linguagem/plataforma diluiria foco e geraria canon raso. Mobile native (Android + iOS) + KMP + Web (`@JsExport`) é um espaço técnico coeso com padrões compartilhados (lifecycle, navegação, persistência local, networking, analytics, threat-model mobile-specific). Cobrir esse espaço com profundidade vale mais que cobrir 10 espaços com superficialidade.

**Por quê coexistência paralela com `docs/design/`, e não absorção/substituição:**

`docs/design/` é fonte de verdade arquitetural — lente "como funciona". Substituir seria perda de detalhe técnico necessário pra manutenção. Absorver geraria PRD inflado (>5000 LOC) com mistura de lente arquitetural + lente produto, impossível de manter coerente. Coexistência paralela permite cada eixo evoluir no seu ritmo: arquitetura muda raramente (decisões locked); produto muda mais rápido (ondas, métricas, baseline). Cross-refs em §10 garantem navegação cruzada quando mantenedor precisa.

**O que feature-forge NÃO promete (counter-promises):**

- **Não promete eliminar manual edits permanente.** Onda 1 mira ≤0 edits per task em fluxo automatizado; edge cases ainda existem onde dev intervém. Promessa é "edit manual = exceção esporádica, não fluxo principal".
- **Não promete acertar arquitetura ideal.** Engine sugere com base em catálogo + history; dev escolhe. Arquitetura "errada" se o dev escolher mal — engine não substitui julgamento.
- **Não promete substituir code review humano.** Diego decide veredito final; forge passa compliance mecânico, libera Diego pra focal em arquitetura.
- **Não promete onboarding zero.** Ramp-up cai de ~2 meses pra ~2 semanas; ainda há ramp-up. Carolina precisa entender padrão arquitetural via templates + cards + 3-caminhos; engine acelera, não elimina.
- **Não promete cobertura 100% de stack possível.** Stack que sai de canon mobile (Hilt, Alamofire, etc.) entra via Gap 5 overlay local — caminho oficial, não fallback. Squad com stack totalmente exótica continua se servindo do canon parcialmente.

---

## §2 — Vision (lente produto)

A vision em [`docs/design/00-vision.md`](../design/00-vision.md) é arquitetural (6 layers + capability cards + what feature-forge is NOT). A vision deste PRD é a mesma estratégia vista pela lente persona — "operating system for mobile feature development" não como camadas técnicas, mas como redução de fricção sentida por Marina no dia-a-dia. Os dois docs coexistem em paralelo conforme decisão tomada no spec.

**Posicionamento:** feature-forge é CLI-first, file-driven, conversacional via menu interativo (zero flags — Decision 10 LOCKED). Toda parametrização vive em menu PT-BR neutro; toda transição de estado é persistida em disco; toda decisão fica auditável em L1/L2/L3 + commits atômicos canônicos.

**Por quê CLI e não plataforma web/IDE plugin:** CLI permite snapshot copy local via `forge init` (Decision 18 + 22 LOCKED), zero runtime dep, portabilidade total entre projetos consumidores. Plataforma web exigiria hosted service (anti-roadmap §6 + [`03-roadmap.md`](03-roadmap.md) §6); IDE plugin exigiria IDE-coupling com multiplicação de superfície de manutenção. CLI é caminho que coexiste com qualquer editor (VSCode, IntelliJ, Xcode, Vim, Emacs) e qualquer OS (POSIX-first em v1; Windows demand-driven Phase 11).

**Diferencial técnico (vs ferramentas adjacentes):**

- **Cards atômicos (22 canon + overlay local via Gap 5)** — unidades de composição com schema declarativo (templates + validators + agent prompts) em vez de scaffold monolítico genérico
- **Memory em 3 níveis (L1 per-feature WIP / L2 project-level committed / L3 cross-project read-only futuro)** — feature N+30 é mais rápida que feature N porque L2 absorve patterns sem dev escrever doc manual; retrospective auto-trigger faz o trabalho mecânico
- **Reuse-intelligence (6 categorias via Q12-Q17 do graph)** — engine detecta duplicação cross-feature em scan `forge init` Step 11.5 + `forge graph` queries em tempo de planejamento; humano decide via `forge evolve`

**Promessa central:** feature N+30 é mais rápida que feature N. Engine acumula, dev colhe. Disciplina mecânica nunca cai na correria (validators hard-fail em gates obrigatórios); disciplina criativa fica com Marina/Bruno (decisões de produto e arquitetura).

A promessa "feature N+30 mais rápida" não é hipótese; é consequência mecânica de:

- L2 acumula patterns via retrospective auto-trigger (Onda 1) sem dev escrever doc manual
- Reuse-intelligence (Q12-Q17) detecta duplicação cross-feature antes dela existir
- Cards locais (Gap 5) absorvem stack-specific da squad sem fork upstream do canon
- `forge graph` Q11 lista reusable helpers; conductor consulta antes de gerar tech-spec
- Auto-retro dispara após verify verde; learnings entram em L2 com fingerprint sha256 anti-redundância

Sem essas mecânicas, "feature mais rápida" depende de dev individual lembrar de revisar features anteriores — esquecível e frágil. Com elas, é estrutural.

**Boundary explícito (NÃO é):**

- **NÃO é PM tool.** Patricia (PM) ganha visibility via `forge status` read-only; estimativa, schedule, priorização são domínio dela com Linear/Notion/Confluence. Tentar expandir engine pra PM-tool genérica violaria boundary documentado em [`docs/design/00-vision.md`](../design/00-vision.md) §What feature-forge is NOT.
- **NÃO é arquiteto automático.** Engine sugere com base em L2+L3 history e catálogo de cards; usuário decide arquitetura. 3-caminhos preserva esse contrato em qualquer gate — mesmo em Onda 3 aspiracional com confidence > 95%, gate humano permanece. Confidence alta ≠ permissão pra pular gate.
- **NÃO é code reviewer final.** Diego (reviewer humano) decide se PR merge. Forge detecta violações mecânicas (escopo, contracts, analytics, regression test); veredito arquitetural é humano. Forge complementa code review, não substitui.
- **NÃO é IDE-coupled.** CLI-first permanece em todas as ondas; integração via shell hooks distribuídos por `forge init` cobre dispatch transparente; plugin nativo VSCode/IntelliJ/Xcode é IDE-coupling que viola portability ([`docs/design/00-vision.md`](../design/00-vision.md)).
- **NÃO é hosted SaaS.** Decision 18 + 22 LOCKED — snapshot copy local via `forge init` é o modelo de distribuição. Cada projeto consumidor tem cópia em `~/Documents/feature-forge/` ou equivalente; sem runtime dep, sem registry, sem cloud state.

Plugin IDE nativo, hosted SaaS, marketplace pública de cards — todos out-of-scope permanente conforme [`03-roadmap.md`](03-roadmap.md) §6 anti-roadmap, com cross-ref pro contract canônico (decisão locked + visão) que ancora o veto.

---

## §3 — Princípios não-negociáveis

7 princípios que ancoram toda decisão de produto + arquitetura. Cada um tem cross-ref pro contract canônico que o sustenta.

Princípios são "não-negociáveis" no sentido literal: quebrá-los em nome de feature nova ou shortcut operacional invalida a coerência da ferramenta inteira. Quando uma proposta chegar pedindo X que viola algum dos 7, o caminho é revisita formal do princípio (brainstorm explícito + writing-plan + dispatch), não exceção pontual silenciosa. Cada princípio tem um custo (overhead operacional, fricção de gates, dispatch obrigatório); aceitar o custo é parte do contrato com o produto, não bug a remover.

**1. Never invent**

Se fonte ausente (PRD vago, ticket sem repro, screen sem comportamento documentado), sub-agente Claude emite `needs-elicitation` pra humano preencher — NÃO chuta valor pra completar campo. Inventar é falha grave; quebra determinismo e gera artefato não-reprodutível. Validator `check_no_invented_behavior` hard-fail em verify cascade se valor inventado for detectado. Cross-ref: [`docs/design/07-discipline.md`](../design/07-discipline.md) §validator `check_no_invented_behavior`.

**2. Files > Memory**

State persistido em disco é fonte de verdade; sessão Claude Code é volátil e dispensável. Tudo em `.claude/forge/state/lifecycle/<slug>/` + `.claude/memory/L2-project.yaml` + `.planning/<slug>/`. Auto-resume cross-session funciona porque arquivo é canon (Decision 27 LOCKED). Marina pode dar Ctrl+C às 18h e retomar no dia seguinte em sessão Claude Code nova sem reescrever Waves A-D — vide cenário C4 em [`02-scenarios.md`](02-scenarios.md). Princípio Files > Memory também protege auditoria: tudo que aconteceu durante o planning fica versionável em git, inspeccionável por humano, e migrável entre versões via `forge raw migrator-N-to-M`.

**3. Usuário decide WHAT, engine dirige HOW**

Decisão de produto e arquitetura é do usuário (Marina ou Bruno). Engine sugere subtype, cards, threat-model com base em L2 history + catálogo canon; nunca decide sem confirmação humana via 3-caminhos. Engine apresenta hipótese rotulada com confidence ("85% via 12 features anteriores em Onda 3"); humano confirma ou redireciona. Esse princípio mantém forge útil sem virar PM-tool nem arquiteto-automático. Cross-ref: Decision 22 + [`docs/design/00-vision.md`](../design/00-vision.md) §What feature-forge is NOT.

**4. Mentor calmo voz**

Voz warm em exploração (Waves A-B com Marina elicitando contexto, persona com nome próprio, day-in-life narrativo), firme em gates (validator hard-fail, escopo violado, contract ausente), didática sem ser professoral (cross-refs canônicos em vez de explicação rasa). Sem "vou tentar", sem "talvez", sem buzzwords corporativos genéricos, sem emoji decorativo. Exceções de emoji permitidas (✅/❌/🛑/⭐) só quando carregam semântica (status, indicador "recommended", bloqueio explícito). Cross-ref: [`docs/design/07-discipline.md`](../design/07-discipline.md) §5 + voz operacional do projeto.

**5. 3-caminhos em qualquer gate violation**

Sempre 3 opções, nunca 2 nunca 4 nunca "consulte a documentação". Em validator fail, escopo violado, contract ausente, ambiguidade entre cards: sub-agente apresenta exatamente 3 caminhos (fix forward / revert / split-escalate). Estrutura padronizada de gate-resolution evita silent skip de validação importante e treina raciocínio sobre trade-offs (Carolina aprende fazendo). Quando um caminho genuinamente não existe, abort explícito é caminho legítimo — não inflar pra 4 caminhos fake. Cross-ref: [`docs/design/07-discipline.md`](../design/07-discipline.md) §1.

**6. Reversibilidade**

Toda action é undo-able; sem hidden state. `forge undo` interativo cobre rollback per-target; abort terminal é 2-step explícito (Decision 27). Pause via Ctrl+C grava `state=deferred` (auto-resumable); abort grava `state=aborted` (não-resumável, exige confirmação). Princípio existe pra reduzir custo de erro — dev experimenta sem medo de "estragar o state-do-projeto" porque toda mudança é audita-trail + reversível. Vide cenário C4 (retomar trabalho pausado) em [`02-scenarios.md`](02-scenarios.md). Cross-ref: [`docs/design/07-discipline.md`](../design/07-discipline.md) §3 + §7.

**7. Persona-native vocabulary**

Engine lê `CLAUDE.md` + `.claude/rules/*` + `docs/design/*` do projeto consumidor. Vocabulário do projeto vence vocabulário genérico. "Forge" só como verbo (Decision 4). Voz mentor calmo em todos artefatos gerados; sem voz corporativa, sem emoji decorativo (✅/❌/🛑 só quando carregam semântica). Quando um termo aparece divergente entre `CLAUDE.md` do projeto e canon do feature-forge, **projeto vence** (hierarquia documentada em hierarquia superpowers: user instructions > skills > defaults). Cross-ref: [`docs/design/07-discipline.md`](../design/07-discipline.md) §5.

**Conflitos entre princípios (resolução):**

Princípios podem aparentar conflito em casos limite. Resolução canônica:

- **Princípio 1 (Never invent) vs Princípio 4 (Mentor calmo voz)** — sub-agente não inventa, mas precisa ser warm em exploração. Resolução: warm é em TOM, não em CONTEÚDO. "Vamos pensar juntos sobre o user value" (warm) ≠ inventar user value (violation). Tom acolhedor + admissão honesta de falta de fonte = compatível.
- **Princípio 3 (Usuário decide WHAT) vs Princípio 5 (3-caminhos em qualquer gate)** — quem decide se gate tem 3 caminhos é engine, mas WHAT-decisão final é humano. Resolução: 3-caminhos é técnica de apresentação de opções; usuário escolhe entre as 3. Engine não pula a apresentação pra "decidir por usuário", e usuário não inflama pra "4 ou 5 caminhos".
- **Princípio 6 (Reversibilidade) vs Princípio 2 (Files > Memory)** — toda action undo-able implica history persistente em disco, o que pode conflitar com "elegância de não acumular lixo". Resolução: `.bak` retention 7 dias default (configurável); `forge doctor` reporta overdue mas não auto-deleta; limpeza via menu em `forge reconfigure`.
- **Princípio 7 (Persona-native vocabulary) vs canon do feature-forge** — quando projeto declara "usamos 'feature' como sinônimo de 'épico'" em `CLAUDE.md`, e canon do forge usa "feature" pra "slug específico planejável", há tensão. Resolução: projeto vence (hierarquia superpowers); engine adapta prompts ao vocabulário declarado em `CLAUDE.md`.

---

## §4 — Escopo IN / OUT

Matriz canônica do que feature-forge cobre e do que deliberadamente NÃO cobre. Linha "OUT vazio" usa "—" quando não há contraponto explícito (escopo IN sem boundary específico definido). Anti-roadmap detalhado em [`03-roadmap.md`](03-roadmap.md) §6.

Esta tabela é defesa contra scope creep — quando uma demanda nova chega pedindo "engine deveria fazer X", retornar primeiro pra esta matriz. Se X cabe em "IN" não-documentado, atualizar matriz via revisita formal. Se X é a coluna "OUT" de uma linha já existente, push-back com rationale + cross-ref pra Decision/Visão violada. Se X é genuinamente fora de toda a matriz (categoria nova), brainstorm explícito antes de promover.

| Categoria | IN | OUT |
|---|---|---|
| Lifecycle | Planning (Waves A-E) + implementation (atomic commits + gates) | — |
| Disciplina | BDD, analytics, threat-model, regression test, scope (`allowed_files`), atomic commits | — |
| Knowledge | L1 per-feature + L2 project-level + L3 cross-project (futuro) + graph (17 queries) + inventory + reuse-intel (Q12-Q17) | — |
| Plataformas | Android + iOS + KMP + Web (`@JsExport`) | watchOS / Wear OS / tvOS (Gap 9 out-of-scope permanente) |
| Backend | Firebase + REST + GraphQL (Apollo reservado v1+) + local-only | Hosted service / SaaS feature-forge |
| Voz | Mentor calmo PT-BR neutro (warm exploração / firme gates / didática sem professoral) | Voz corporativa / emoji decorativo / "vou tentar" |
| Subtypes | product (default) / refactor / bugfix (+ spike + chore stubbed) | — |
| Reversibilidade | `forge undo` per-target interativo + auto-resume `deferred` cross-session | — |
| Decisões | Engine sugere subtype/cards/threat com base em L2+L3 history | Engine **decide** produto ou arquitetura sem confirmação humana |
| Code review | Detecta violações mecânicas (escopo, contracts, analytics) via cascade fail-fast | Veredito final humano (Diego decide merge) |
| PM | `forge status` read-only board (visibility técnica real-time) | Estimativa / schedule / priorização de backlog |
| Marketplace | Cards locais via Gap 5 (`.claude/cards/local/<name>/` versionado por projeto) | Marketplace pública (viola Decision 22) |
| Distribuição | Snapshot copy local via `forge init` (Decision 18 + 22) | Auto-installer cross-project / hosted SaaS |
| IDE | Integração via shell hooks já distribuídos por `forge init` | Plugin nativo VSCode/IntelliJ/Xcode (viola portability) |

**Linhas mais defendidas (mais propensas a virarem demanda recorrente):**

- **Plataformas — watchOS/Wear/TV**: aparece em discussão de squad como "queremos também relógio/TV"; revisita formal Gap 9 em 2026-06-03 fechou como out-of-scope **permanente**. Caminho oficial pra plataforma exótica é Gap 5 overlay local. Quando alguém pedir "vamos absorver no canon", retornar a esta linha + cross-ref pra `04-pending.md §Gap 9`.
- **Decisões**: tensão constante "engine não deveria decidir X automaticamente?" — não. Engine sugere com base em L2+L3; humano decide via 3-caminhos. Princípio non-negociável §3 §3. Confidence alta em Onda 3 NÃO é permissão pra pular gate.
- **Marketplace**: comunidade pede registry pública de cards user-contributed em massa (R2 em §13). Gap 5 local cobre substância da demanda; pública viola Decision 22. Push-back firme.
- **IDE**: integração via shell hooks (POSIX-first) cobre dispatch transparente; plugin nativo é IDE-coupling com multiplicação de superfície de manutenção. CLI-first é load-bearing.

Linhas menos defendidas (podem evoluir com demanda concreta):

- **Backend**: GraphQL Apollo é reservado (card v1.1+ candidato); demanda concreta de squad GraphQL pode promover; sem demanda, fica dormente em backend-candidate.
- **Plataformas — Web**: `@JsExport` KMP cobre baseline; React standalone não-KMP fica em anti-persona §9; revisita possível se squad híbrida mobile+web aparecer formalmente.

---

## §5 — Personas (resumo)

8 personas em 3 camadas conforme [`01-personas.md`](01-personas.md). Cada uma com 1 linha de identidade aqui; detalhe completo (day-in-life, jobs-to-be-done, frustrações, critérios sucesso, roadmap-impact) no sub-doc canônico.

A organização em 3 camadas existe pra ancorar trade-offs de design do engine. Quando uma decisão atinge Marina, é direta; quando atinge Carlos/Lucas/Carolina, é via caveat documentado; quando atinge Patricia/Diego, é via interface read-only ou via output do engine consumido downstream. Toda decisão de produto declarada em §3 (princípios) pode ser rastreada a uma persona específica desta tripla camada — quando não consegue, é sinal de scope creep ou de persona oculta que precisa entrar formalmente em [`01-personas.md`](01-personas.md) via brainstorm.

**Mapeamento rápido de persona ↔ comando** (operação default):

| Persona | Opera forge? | Comando principal | Cenários onde aparece |
|---|---|---|---|
| Marina | Sim (primária) | `forge plan / implement / verify / evolve` | C2, C3, C4, C5, C6 |
| Bruno | Sim (decisor adopt) | `forge init / evolve / status` | C1, C6 |
| Sub-agente Claude | É operado via context-pack | (dispatchada por wave do orchestrator humano) | Todos (dispatch por wave) |
| Carlos | Sim (variante Marina) | `forge plan / implement / verify` | Derivado de C2-C5 |
| Lucas | Sim (variante Marina + caveats v1) | `forge reconfigure / plan / implement` | Derivado de C2-C5 + futuras Onda 2 |
| Carolina | Sim (variante Marina com didática) | `forge plan / implement / verify / ensina` (Onda 3) | Derivado de C2 com ramp-up |
| Patricia | Não — read-only via board | `forge status` | Adjacente a C1-C6 (visibility) |
| Diego | Não — recebe PR forge-gerado | (consome PR no GitHub/GitLab) | Adjacente a C2-C6 (downstream do PR) |

**Camada A — Personas dedicadas (day-in-life completo)**

- **Marina** — Mobile dev solo KMP/Android, **PRIMÁRIA**. 4-6 anos exp, squad pequena (1-3 devs), dona de feature ponta-a-ponta — do PRD ao merge. Stack Kotlin/KMP/Compose/SwiftUI/Koin Annotations/Nav3/REST-ou-Firebase/Room/DataStore. Usuário-âncora do engine: tudo no engine é otimizado pra reduzir fricção dela primeiro; os outros perfis são variantes ou consequências do desenho centrado em Marina. [Detalhe em [`01-personas.md`](01-personas.md) §Marina]
- **Bruno** — Tech lead / staff engineer, **SECUNDÁRIA**. 7-12 anos exp, lidera squad de 3-8 devs, decide adopt de ferramentas, pivota entre projetos com stacks heterogêneas (Hilt aqui, Koin lá, Apollo num, Retrofit noutro). Faz triage semanal via `forge evolve`; supervisiona sem revisar cada PR manualmente. [Detalhe em [`01-personas.md`](01-personas.md) §Bruno]
- **Sub-agente Claude** — Persona TÉCNICA não-humana. 3 roles distintos no engine (planning-conductor, executor, readiness-reviewer). Recebe context-pack estruturado pelo orchestrator; opera com state persistido em L1 entre invocações. 5 critérios sucesso non-negociáveis (determinismo / escopo / voz / never-invent / 3-caminhos). Única persona não-humana intencional — sublinha que é técnica e não tem desejos humanos, apenas contratos de comportamento. [Detalhe em [`01-personas.md`](01-personas.md) §Sub-agente Claude]

**Camada B — Variantes da Marina (caveats por desvio do perfil)**

- **Carlos** — Android-only sem KMP. Stack 100% Android (Kotlin + Compose + Hilt-OU-Koin + Retrofit + Room + DataStore + Coroutines + Flow). Sem iOS, sem KMP shared. Cards iOS/KMP ficam dormentes (sem signal positivo na detection), sem custo extra de pensar em paridade. Hilt não tem card canon em v1.2 (Koin é o canon mobile por uniformidade KMP); pode rodar Hilt via Gap 5 overlay local. [Detalhe em [`01-personas.md`](01-personas.md) §Carlos]
- **Lucas** — iOS-only sem KMP. Stack 100% iOS/Swift (SwiftUI + Combine + Swift Packages + Alamofire ou URLSession + KeychainAccess + CoreData/GRDB/Realm). v1.2 funciona com workaround manual via `forge reconfigure` (auto-detection retorna 0 signals positivos); Onda 2 entrega preset `ios-only` dedicado quando demanda concreta justificar. Tabela de caveats v1 em [`01-personas.md`](01-personas.md) §Lucas é obrigatória — 6 linhas Aspecto/Estado v1.2/Comportamento/Workaround. [Detalhe em [`01-personas.md`](01-personas.md) §Lucas]
- **Carolina** — Dev iniciante / onboarding. 1-3 anos exp, primeira squad mobile real depois de bootcamp ou estágio. Aprendendo padrão arquitetural enquanto entrega feature — forge usa também como material didático embutido no fluxo de trabalho (templates ensinam estrutura, validators ensinam regras, cards explicam padrões, 3-caminhos treina raciocínio em trade-offs). Ramp-up de ~2 meses → ~2 semanas. [Detalhe em [`01-personas.md`](01-personas.md) §Carolina]

**Camada C — Downstream / read-only**

- **Patricia** — PM / Product Owner. **NÃO toca código.** Não escreve tech-spec, não roda `forge implement`, não revisa proposed-evolutions. Única interação com forge: `forge status` read-only board pra visibility técnica real-time. Boundary explícito: forge NÃO faz estimativa de tempo, schedule de release, priorização de backlog — esses são domínio exclusivo do PM com Linear/Notion/Confluence. Patricia ganha visibility técnica precisa, não decision-making automation. [Detalhe em [`01-personas.md`](01-personas.md) §Patricia]
- **Diego** — Code reviewer humano. **NÃO opera forge.** Dev senior que revisa PRs no GitHub/GitLab; interação com forge é indireta — recebe PR criado por dev que rodou `forge implement` localmente. Expectativas em PR forge-gerado: escopo respeitado (`allowed_files`), contracts seguidos (BDD bate com analytics-spec), analytics/threat/regression tests presentes, mensagens de commit canônicas. Review focal em decisão arquitetural, naming, trade-offs — não compliance mecânico. [Detalhe em [`01-personas.md`](01-personas.md) §Diego]

Anti-personas (quem NÃO usa) vivem em §9 deste doc — separação proposital pra não diluir foco do roster acima. Adicionar uma 9ª persona requer brainstorm explícito + update do PRD + cross-ref nos cenários e roadmap. Personas têm peso load-bearing — drift silencioso enfraquece o vocabulário compartilhado entre mantenedor + Claude futuro.

---

## §6 — Cenários de uso (resumo)

6 user journeys end-to-end conforme [`02-scenarios.md`](02-scenarios.md). Cada um com persona principal ancorada + outcome mensurável; detalhe operacional (estado inicial/final + passos numerados + cross-refs UX) no sub-doc canônico.

Decisão deliberada: cenários não tentam cobrir 100% do espaço de uso — cobrem os 6 momentos canônicos onde o engine tem mais valor agregado mensurável. C1 cobre adoção (brownfield init); C2-C5 cobrem operação cotidiana de Marina nos 4 modos principais (feature product, bugfix, retomada, extension); C6 cobre colaboração entre tech lead e dev (reuse-intelligence). Adicionar um C7 hipotético requer demanda concreta de persona — não shippa preventivo.

**Padrão schema dos cenários** (mantido consistente em todos C1-C6):

- **Persona principal**: quem dirige a sessão (sempre uma das 8 personas catalogadas em [`01-personas.md`](01-personas.md)).
- **Estado inicial**: o que existe no projeto + na cabeça da persona antes do primeiro comando (contexto técnico + contexto humano).
- **Estado final**: o que existe depois (artefatos persistidos + commits no histórico + state em L1/L2 atualizado + decisões registradas).
- **Passos**: numerados 1-N, ação concreta + outcome verificável de cada step.
- **Outcome**: uma frase ou parágrafo curto sobre valor entregue (tempo poupado, retrabalho evitado, knowledge acumulado, drift cross-feature reduzido).
- **Cross-ref**: `docs/ux/*.md` (roteiros operacionais detalhados) + `docs/design/*.md` (decisões e disciplinas que ancoram comportamento) + `docs/lifecycle/*.md` (dataflow) + `docs/schemas/*.md` (artefatos validados) + `agents/*.md` (prompts canônicos).

- **C1 — Brownfield init com reuse-intelligence** (Bruno + Marina dia seguinte). `forge init` em projeto KMP existente com ~150 features históricas; scan Step 11.5 retorna 47 findings em 6 categorias (consolidate-within-module / promote-to-shared / redundant-platform / near-duplicate / kmp-migration-candidate / consolidate-ts-helpers); Marina faz triage no dia seguinte via `forge evolve` (30 accept / 12 reject / 5 defer). Outcome: 30 reuse opportunities prontas pra puxar em PRs separados; L2 acumula learnings sem doc manual; fingerprints dos 12 rejeitados protegem contra re-proposta silenciosa. [Detalhe em [`02-scenarios.md`](02-scenarios.md) §C1]
- **C2 — Feature product nova end-to-end** (Marina). Ticket IN-42100 "Lembrete de rega de planta" — PM passou acceptance criteria + screenshot Figma; sem PRD/screen design escritos. Wave A intake → Wave B PRD + screen-analysis → Wave C contracts (BDD + analytics + threat + data-contract) → Wave D tech-spec + 8 tasks → Wave E readiness=ready em ~15min total. Implement task-por-task com gates de escopo (1 tentativa de refactor lateral travada por 3-caminhos) + atomic commits ~4h. Outcome: feature shipada com BDD/analytics/threat/regression sem "esqueci na correria"; review do Diego focal em arquitetura (WorkManager vs AlarmManager), não compliance mecânico. [Detalhe em [`02-scenarios.md`](02-scenarios.md) §C2]
- **C3 — Bugfix com ticket IN-37234** (Marina P0). Crashlytics alerta 9h: 12% sessions Android 14 crashando — `BonsaiForm.validateName()` NPE quando input " " (whitespace only) é passado. Subtype=bugfix detectado por keywords + ticket-pattern (prefix `IN-` + "crashing" + "Android 14" + severity P0); Wave B skipada (`wave_b_required=false`, lógica pura); intake-bugfix dedicado em ~3min; Wave C-D tech-spec stripped + 2 tasks (fix + regression test obrigatório); validator hard-fail garantiria se regression test estivesse ausente. Outcome: ~25min ticket → PR vs ~60min se rodasse fluxo product completo; regression test cobre 3 variantes whitespace; auto-retro 5-whys propõe pattern "trim() canônico em validação de nome" em L2 com fingerprint sha256 estável. [Detalhe em [`02-scenarios.md`](02-scenarios.md) §C3]
- **C4 — Retomar trabalho pausado** (Marina cold-start). Wave D feature `agenda-poda` terminou ontem 18h; Ctrl+C antes da Wave E pra terminar o dia; `state=deferred` persistido em L1 com timestamps por wave. Sessão Claude Code de ontem encerrada — contexto não persiste cross-session. Hoje 9h sessão nova: `forge status` mostra board com `agenda-poda` em deferred; `forge plan agenda-poda` detecta `state=deferred + last-wave=D + wave-e-pending=true` e dispara auto-resume conforme Decision 27 LOCKED; conductor: "Retomando agenda-poda. Wave D foi verificada em 2026-06-03 17:45. Continuando Wave E (readiness)...". Outcome: zero retrabalho; readiness em ~5min; State persistido em disco protege Marina de "qual era mesmo o contract da analytics?". [Detalhe em [`02-scenarios.md`](02-scenarios.md) §C4]
- **C5 — Extension feature (Gap 9)** (Marina). Feature `lembrete-rega` shipped semana passada (state=done com `shipped-at` timestamped); PM volta com follow-up "lembrete por hora-do-dia, não só por intervalo de dias" — refinamento natural, não feature nova do zero. `forge plan lembrete-rega-hora` em Cena 1 mostra 4 caminhos (4º "Estender" conditional sobre parent state=done); Marina escolhe Estender com `parent=lembrete-rega`; validator `validate_extension_feature` confere EXT-001..004 (parent existe + parent.state==done + `extends-feature` setado + slug derivado válido); Wave A skipa elicit redundante (user value/persona/business outcome herdados do parent em modo "context import"); Wave B só pergunta delta (trigger hora-do-dia em vez de intervalo de dias); Wave C-D-E normais com tech-spec contextualizando parent (referencia entities + screens explicitamente). Outcome: pattern leve product-derived sem cards canon novos, sem schema novo, sem mudar enum platforms; ~3h vs ~5h se rodasse feature do zero. [Detalhe em [`02-scenarios.md`](02-scenarios.md) §C5]
- **C6 — Reuse intelligence em ação** (Bruno + Marina). Squad com 18 features shipadas; pattern `validateName` aparece em 15 lugares (7 versões em módulos Android + 5 versões em Swift puro pra iOS + 3 versões em KMP shared) com leve drift cosmético crescente (9/15 trimmam whitespace; 6 não; 4/15 validam tamanho; 2/15 validam charset). Marina planejando feature 19; Wave B conductor consulta `forge graph Q12` (consolidate-within-module) + `Q15` (near-duplicate); graph retorna "validateName 15 lugares — sugere promote-to-shared pra `:shared:core:validation`". Conductor apresenta 3-caminhos (promover agora / registrar pra triage / ignorar); Marina escolhe "registrar pra triage"; Bruno quinta abre `forge evolve`, filtra `kind=promote-to-shared`, aceita validateName promotion; engine gera diff (extract + replace calls + import update); Marina dia seguinte mergeia + atualiza `.claude/cards/local/`. Outcome: engine detecta + propõe + humano decide; 15 lugares → 1 lugar pra manter; drift cross-feature reduzido a zero. [Detalhe em [`02-scenarios.md`](02-scenarios.md) §C6]

---

## §7 — Roadmap produto (resumo)

3 ondas agrupadas por outcome de persona conforme [`03-roadmap.md`](03-roadmap.md). Detalhe operacional (princípios, OKRs aspiracionais, anti-features explícitas por onda, sinais de prontidão, cenários ilustrativos) no sub-doc canônico.

A lente "produto" responde "quem ganha o quê, e quando" — a lente "técnica" em [`docs/design/ROADMAP.md`](../design/ROADMAP.md) responde "qual Phase entrega isso, e como". Os dois eixos andam juntos via cross-ref bidirecional em [`03-roadmap.md`](03-roadmap.md) §7 — não disputam autoridade. Uma onda produto pode compor 1 ou mais Phases técnicos (Onda 2 = Phase 7 + Gap 5 + multi-dev); um Phase técnico pode ficar fora de qualquer onda (Phase 8 MCP é demand-driven sem persona-âncora dedicada).

- **Onda 1 — "Autopilot completo" (v1.3 → v1.4)** — Marina ancora. Phase 6 técnico em 4 sub-fases (6.1 LLM/sub-agent invocation real, 6.2 Apply Mode automatizado + pre-commit review automatizado interno, 6.3 Atomic commit + completion evidence + L1 status update automático, 6.4 Retrospective auto-trigger). `forge implement` deixa de ser stub manual → autopilot real; sub-agente Claude aplica diff end-to-end com `allowed_files` respeitado por validator real, não só anotação na agenda. OKRs: time-to-merge ≤4h (hoje ~6-8h), manual edits per task=0 (hoje 5-15), regression rate cross-feature ≤2% (hoje ~5-8%), L1 auto-status updates=100%. Anti-features: NÃO automatiza decisão produto (engine sugere, humano confirma); NÃO pre-commit review humano (Diego decide); NÃO IDE plugin (CLI-first permanece). [Detalhe em [`03-roadmap.md`](03-roadmap.md) §2]
- **Onda 2 — "Catálogo evolutivo + colaboração" (v1.5 → v2.0)** — Lucas + Bruno ancoram. Phase 7 técnico (Tree-sitter AST pra Kotlin + Swift + TypeScript com cobertura ≥90%) + Gap 5 maturity (cards locais como caminho oficial pra stack-specific) + multi-dev opcional (resolve `04-pending.md §Gap 6` deferred). Preset `ios-only` shippa com auto-detection em `forge init` retornando signal positivo; cards canon iOS standalone (Alamofire/KeychainAccess/Combine/CoreData) viram canon, não overlay obrigatório; marketplace LOCAL maduro (≥5 cards locais por squad sobrevivendo ≥2 retros); multi-dev opcional via phase-lock cross-dev visível em `forge status`; Patricia ganha filtros temporais (`--release-q3`) e por sprint sem violar boundary. OKRs: preset count 1→≥3 (`kmp-mobile` / `ios-only` / `android-only`), cards locais aceitos por squad ≥5, features merged sem conflict em multi-dev ≥10 cumulativo. Anti-features: NÃO marketplace pública (Decision 22); NÃO hosted SaaS (Decision 18+22); NÃO multi-target watchOS/Wear/TV (Gap 9 OUT-permanente). [Detalhe em [`03-roadmap.md`](03-roadmap.md) §3]
- **Onda 3 — "Inteligência adaptativa" (v2.x aspiracional)** — Todas personas (transversal). Phase 7+ semantic ativo + LLM real-time signals (sub-agent consulta L2+L3 durante wave, não só no final em retrospective). Reuse-intelligence semantic com false-positive rate <5% (vs ~20-30% empírico do parser regex v1); conductor lembra decisões cross-feature via L3 cross-project memory (read-only, auto-injetada em context-pack); engine sugere subtype/cards/threat com confidence rotulado ("85% via 12 features anteriores"); Carolina ganha `forge ensina <pattern>` (verbo experimental Onda 3, pode virar `forge explica` ou `forge porque` na implementação); Sub-agente Claude opera com confiança histórica preservando 3-caminhos em qualquer gate. OKRs: drill-down rounds 2→0.5, questions per Wave A −30%, L2 patterns auto-inject ≥60%. Anti-features: NÃO tomar decisões sem confirmação humana (3-caminhos preserved); NÃO substituir mentor humano (engine ensina padrões mecânicos, humano ensina contexto/cultura). [Detalhe em [`03-roadmap.md`](03-roadmap.md) §4]

**Matriz Eisenhower (mini-versão):**

|  | Low-effort | High-effort |
|---|---|---|
| **High-impact** | Onda 1 (Autopilot) — done now | Onda 2 (Catálogo) — strategic |
| **Low-impact** | Backlog `04-pending.md` (gaps individuais) | Anti-roadmap §6 (rejected) |

Onda 1 em low-effort relativo: parte cara da arquitetura (cards, memory, reuse-intel, validators, graph) já entregue em v1.0-v1.2; Phase 6 é "fechar última perna do tripé". Time-to-merge ≤4h corta fricção diária de Marina de modo direto; toda outra onda só importa depois disso fechar. Onda 2 em high-effort high-impact: Tree-sitter exige adoção de dep externa + migration cuidadosa; multi-dev exige merge-strategy formal; preset `ios-only` exige cards iOS standalone novos com validators próprios. Esforço L+M+M = High; impacto também High porque libera Lucas, amplia adoção em Bruno+squads maiores, dá Patricia visibility filtrada. [Detalhe em [`03-roadmap.md`](03-roadmap.md) §5]

**Cross-ref bidirecional onda ↔ Phase técnico:**

| Onda produto | Phase técnico ([`docs/design/ROADMAP.md`](../design/ROADMAP.md)) | Conexão |
|---|---|---|
| Onda 1 (Autopilot) | Phase 6 (Apply Mode + LLM hookup + Atomic commit + Retro auto-trigger) | 1:1 — Onda 1 É Phase 6 visto pela lente persona |
| Onda 2 (Catálogo) | Phase 7 (Tree-sitter AST) + Gap 5 maturity + multi-dev opcional (Gap 6) | Compositiva — Phase 7 habilita semantic reuse pra UX nativa iOS; Gap 5 escala overlay local; multi-dev resolve Gap 6 deferred |
| Onda 3 (Inteligência) | Phase 7+ (semantic ativo) + LLM real-time signals (extensão Phase 6.1) | Aspiracional — não bloqueia v2.0; depende de Phase 7 entregue + dados L2+L3 acumulados em campo |

Phases técnicos sem onda direta (continuam relevantes no eixo técnico mas demand-driven sem persona-âncora dedicada): Phase 8 (MCP real connections), Phase 9 (cards reservados), Phase 10 (cards legacy), Phase 11 (Windows support), Phase 12 (validators expandidos), Phase 13 (marketplace pública = anti-roadmap). [Detalhe em [`03-roadmap.md`](03-roadmap.md) §7]

**Critérios pra promover um Phase técnico a onda produto:**

- Demanda real observada em squad consumidora (≥1 squad pedindo formalmente, não hipotético).
- Persona declarada se beneficia diretamente (não "Phase ficou pronto, vamos onda" — precisa articular "X persona deixa de fazer Y" ou "X persona passa a conseguir Z em N min vs antes").
- Outcome de produto articulável em 1 frase (não capability técnica re-embalada em marketing).
- OKR observável (não "ficaria legal" — algo medível com baseline + target).
- Anti-feature explícito (o que essa onda NÃO entrega, mesmo que pareça relacionado).

Sem os 5 critérios casando, Phase técnico fica em eixo técnico sem virar onda. Phase 8 (MCP) é exemplo — útil tecnicamente, mas sem persona-âncora ("Marina ganha o quê?" — resposta vaga); fica demand-driven incremental.

---

## §8 — Success criteria & métricas

Sucesso do feature-forge não se mede por número de cards/validators/queries shipados isoladamente — se mede por mudança observável na fricção sentida pela persona declarada. As 8 frases qualitativas abaixo (uma por persona) são o critério primário; as métricas quantitativas (9 abaixo) são secundárias e instrumentadas pra confirmar empiricamente que o qualitativo aconteceu.

**Por que qualitativo vem primeiro e quantitativo vem segundo:**

Métrica fora de contexto persona pode iludir. "Time-to-merge ≤4h" sozinho não diz nada — pode significar "engine ágil" OU "qualidade comprometida pra ganhar velocidade". Quando ancorada em "Marina sente que não preciso reinventar arquitetura por feature", a métrica vira evidência de outcome, não vaidade isolada. Frases qualitativas por persona protegem contra "métrica acertada mas persona ainda travada".

Risco específico: medir só quantitativo e ignorar qualitativo → engine ganha eficiência métrica mas perde voz mentor calmo, ganha velocidade mas perde rigor de validators, ganha automatização mas perde 3-caminhos. Persona ancorada em qualitativo evita esse tradeoff disfarçado de progresso.

**Qualitativos (por persona — uma frase "sente que..." cada):**

- **Marina** sente que "não preciso mais reinventar arquitetura por feature" — copy-paste de estrutura anterior some, custo mental por ticket cai feature a feature.
- **Bruno** sente que "onboarding em dias, não semanas" — dev novo entra na squad e atinge produtividade plena com `forge init` + read pra `docs/design/00-vision.md`, sem aprendizado por osmose de PR review.
- **Sub-agente Claude** sente que "context-pack determinístico me deixa entregar diff escopo-respeitado" — `allowed_files` é contrato auditável, não anotação na agenda; output é reproduzível entre dispatches.
- **Carlos** sente que "funciona out-of-box mesmo sem KMP" — cards iOS/KMP ficam dormentes sem custo extra; preset `kmp-mobile` aplica e o trabalho rola.
- **Lucas** sente que "v1 entrega caminho manual, v1.x+ entrega UX nativa" — workaround via `forge reconfigure` desbloqueia projeto iOS-only em v1.2; Onda 2 entrega preset dedicado quando demanda concreta justificar.
- **Carolina** sente que "aprendo padrão arquitetural fazendo, não só revisando PR review" — templates ensinam estrutura, validators ensinam regras, cards explicam padrões, 3-caminhos treina raciocínio em trade-offs.
- **Patricia** sente que "vejo estado de cada feature sem perguntar" — `forge status` read-only board reduz "tá pronto?" em standup pra zero; backlog tem 0 features em estado desconhecido.
- **Diego** sente que "reviews focados em arquitetura, não em compliance mecânico" — disciplina mecânica passa antes do PR chegar; review humano debruça-se sobre decisão arquitetural e trade-offs reais.

**Quantitativos (targets aspiracionais Onda 1+):**

| Métrica | Target | Baseline (sem forge) | Onda que entrega |
|---|---|---|---|
| Time-to-merge (ticket → PR mergeado) | ≤ 4h | ~6-8h | Onda 1 (Apply Mode) |
| Manual edits per task após implement | 0 | 5-15 | Onda 1 (Apply Mode) |
| Drill-down rounds (perguntas Wave A médias) | ≤ 1 | 2-3 | Onda 3 (L2+L3 auto-inject) |
| Onboarding squad nova (dev novo → produtivo) | ≤ 2 semanas | ~2 meses | Onda 1 + Onda 2 (cards locais maduros) |
| L2 patterns auto-inject | ≥ 60% das features | 0% (manual) | Onda 3 (LLM real-time signals) |
| Regression rate cross-feature (bug retornando em 3 sprints) | ≤ 2% | ~5-8% | Onda 1 (regression test obrigatório + L2 patterns) |
| Preset count | ≥ 3 | 1 (kmp-mobile) | Onda 2 (ios-only + android-only) |
| Cards locais aceitos por squad madura | ≥ 5 | 0 | Onda 2 (Gap 5 maturity) |
| Multi-dev features sem conflict cumulativo | ≥ 10 | 0 (single-dev) | Onda 2 (Gap 6 resolved) |

Targets são aspiracionais; baselines são empíricos (observados em projetos canon antes da Onda 1 entregar Apply Mode). A diferença entre baseline e target define o valor de fechar cada onda — não fechamos onda porque "Phase técnico está done", fechamos porque a métrica empírica em campo aproxima do target aspiracional. Métrica empírica ainda longe do target = onda incompleta, mesmo com Phase técnico shipado. Auditoria mensal cobre o gap entre "código entregue" e "outcome de persona observado" — quando os dois divergem, o gap entra em [`04-pending.md`](../design/04-pending.md) como ajuste subsequente.

**Como métrica nova entra neste registro:**

- Onda fechada em [`03-roadmap.md`](03-roadmap.md) declara métrica empírica observada → adiciona linha aqui se ainda não existir.
- Métrica que estava aspiracional vira empírica observada → atualiza coluna "Onda que entrega" pra refletir o que foi feito.
- Métrica que ficou irrelevante (target atingido + sem variação observável em 6+ meses) → remove com cross-ref no commit body.
- Adicionar métrica nova sem onda planejada → fica como aspiracional sem coluna "Onda que entrega"; entra em brainstorm pra justificar valor mensurável.

**Instrumentação atual vs futura:**

- v1.2 hoje instrumenta L1 status timestamps (Wave A done at, Wave B done at, etc.) — permite cálculo manual de "duração média de Wave A-E" por feature concluída em retrospective.
- Onda 1 entrega instrumentação adicional via Phase 6.3 (atomic commit + completion evidence): time-to-merge se torna observável automaticamente. Manual edits per task também via diff comparison entre output do sub-agente e commit final.
- Onda 3 entrega telemetria de drill-down rounds + questions per Wave A via conductor — sub-agente registra count de iterações por wave, observável em L2 sem dev escrever doc.
- Métricas que dependem de longa janela observacional (regression rate em 3 sprints, multi-dev features cumulativo, cards locais aceitos por squad madura ≥ 2 retros) só ficam disponíveis após meses de uso real em produção.

**Baseline atual (v1.2.0 + Gap 9):**

- **637 tests passing + 12 skipped** (e2e + integration). Default lane verde via `pytest`; rapid lane via `pytest -m "not integration and not e2e"`.
- **22 cards canon** + 4 backend-candidates dormentes em preset `kmp-mobile`. Cards stack: `kmp-shared`, `koin-annotations`, `kotlin-language`, `compose-screens`, `compose-navigation`, `swiftui-screens`, `swiftui-navigation`, `retrofit-client`, `room-database`, `datastore-prefs`. Cards backend/observability: `auth-jwt-bearer`, `crashlytics`, `firebase-storage`. Cards bridging/networking: `skie-bridge`, `ktor-client`, `shared-preferences-prefs`. Backend-candidates dormentes: Firebase + GraphQL/Apollo + gRPC + REST adicionais (ativam quando feature concreta declarar).
- **15 validators** em cascade fail-fast (`forge verify`). Cobrem escopo (`check_files_in_allowed_files`), invenção de comportamento (`check_no_invented_behavior`), no-behavior-change attestation em refactor (`check_no_behavior_change`), regression test em bugfix obrigatório, BDD/analytics/threat presença em wave E, etc.
- **17 graph queries** (Q1-Q11 capabilities + Q12-Q17 reuse-intelligence). Q1-Q11 navegam ontology de capabilities (`http-client`, `auth-provider`, `persistence-local`, etc); Q12-Q17 alimentam scan reuse-intel em init + planning.
- **~400 arquivos, ~52.500 LOC** (engine Python core + validators + templates + cards + agents + docs + tests).
- **28 decisões locked + 7 direcionais** em [`docs/design/01-decisions.md`](../design/01-decisions.md). 8 são load-bearing (D14 config scope monorepo / D15 versioning snapshot fork-and-forget / D18 standalone repo location / D19 Python+Bash+YAML/MD / D20 SQLite graph + arquivos / D22 no runtime deps em outras skills / D23 validator cascade fail-fast / D27 pause `deferred` auto-resumable + abort 2-step) — mudar silentemente quebra arquitetura inteira.

Baseline real, não aspiração — verificável via `pytest` + `forge doctor` + leitura de `docs/design/08-session-handoff.md` no commit atual. Quando este PRD diverge da baseline (ex: contagem de tests mudar pós-Onda 1), o sub-doc canônico vence — atualizar este PRD em paralelo é trabalho de doc-sync (Mandamento #6 do projeto).

---

## §9 — Anti-personas

Quem NÃO usa feature-forge. Listagem deliberada — separar do roster de personas em [`01-personas.md`](01-personas.md) evita diluição do foco. 5 perfis com rationale explícito + sugestão de alternativa adequada.

Anti-personas existem pra defender o produto contra scope creep "vamos cobrir também esse caso". Cada anti-persona tem fronteira clara (linguagem-âncora não-Kotlin, plataforma não-mobile-nativa, papel não-dev, rejeição da disciplina) e alternativa razoável fora do feature-forge. Quando aparece pressão "vamos absorver perfil X também" sem rationale forte de persona declarada, retornar a esta tabela e validar — se X cabe em uma das 5 linhas, push-back firme; se X é categoria nova, brainstorm explícito.

| Anti-persona | Por quê não | O que faria sentido pra ela |
|---|---|---|
| **Dev Flutter / React Native** | Cards canon assumem Android/iOS/KMP nativo; intent não cobre Flutter (Dart) nem React Native (TS+JS) como linguagens-âncora. Catálogo focado em Kotlin+Swift; expandir pra Dart/JS quebraria foco sem ganho proporcional. | Skill própria pra Flutter (Dart-first canon + widget hierarchy templates) ou React Native (TypeScript + JSX components + RN-specific patterns). |
| **Backend-only / web puro React não-KMP** | Engine assume Kotlin/Swift como linguagens-âncora pra mobile + KMP shared; Web via `@JsExport` KMP, não React standalone. Backend puro (Node/Spring/Django) sem mobile não tem persona declarada. | Skill backend genérica (REST/GraphQL contracts + database migrations) ou skill web React standalone (component patterns + state management + routing). |
| **PM / designer operando diretamente** | forge é dev-tool; downstream Patricia tem `forge status` read-only apenas. Operar `forge plan` / `forge implement` exige conhecimento de Kotlin/Swift/KMP que PM não tem. | Confluence + Notion + Linear cobrem schedule/priorização/discovery doc; Figma cobre design; `forge status` complementa com visibility técnica em tempo real. |
| **Squad que rejeita disciplina mecânica** | forge **é** a disciplina mecânica (BDD obrigatório / analytics obrigatório / regression test obrigatório em bugfix). Sem aceitação dos gates, a ferramenta sobra — squad gasta tempo brigando contra validators em vez de colhendo benefícios. | — (não é uso adequado da ferramenta; sem desejo de disciplina, qualquer ferramenta que a impõe vira fricção). |
| **Projetos Java-only sem Kotlin moderno** | Engine assume Kotlin como linguagem-âncora; templates/cards/agents-prompts não cobrem Java puro (sem Coroutines, sem Flow, sem KMP). Lib Java tradicional (RxJava, AndroidX antigo) não tem card canon. | Skill Java/Spring genérica ou skill Android-legacy específica pra projetos pre-Kotlin (XML views + AsyncTask + RxJava patterns). |

**Por que separar anti-personas de personas (e não fundir tudo num roster único):**

Personas em [`01-personas.md`](01-personas.md) são "pra quem o forge faz sentido"; anti-personas neste doc são "pra quem o forge NÃO faz sentido". Separar protege foco do roster principal — diluir as 8 personas com mais 5 "personas reversas" tornaria leitura confusa e enfraqueceria a narrativa por persona. Marina, Bruno, Sub-agente Claude, Carlos, Lucas, Carolina, Patricia, Diego têm vocabulário compartilhado e cenários coerentes; misturar "Dev Flutter / RN" no mesmo roster geraria ruído sem ganho.

Separação também permite tratamento diferente: personas em [`01-personas.md`](01-personas.md) ganham day-in-life narrativo, jobs-to-be-done, frustrações específicas, critérios sucesso; anti-personas aqui ganham só rationale + alternativa adequada. Densidade de detalhe é proporcional à relevância no design do produto.

**Por que estas 5 anti-personas e não mais ou menos:**

- **Dev Flutter/RN** — cobre "linguagem-âncora não-Kotlin/Swift" (Dart, TypeScript+JSX). Inclui também Ionic/Capacitor por extensão (mesma família de hybrid frameworks).
- **Backend-only / web puro não-KMP** — cobre "stack não-mobile-nativa" + "stack não-KMP shared". Backend Spring/Django/Node + web React standalone (sem KMP `@JsExport`) ficam fora.
- **PM / designer operando diretamente** — cobre "papel não-dev tentando operar ferramenta dev". Patricia (PM) e equivalentes design ficam read-only via `forge status` board; operação direta é fora do escopo.
- **Squad que rejeita disciplina mecânica** — cobre "cultura incompatível". Forge **é** a disciplina; rejeitar gates remove a razão de existir da ferramenta.
- **Projetos Java-only** — cobre "linguagem-âncora pre-Kotlin moderno". Inclui projetos Android legacy que ainda usam XML views + AsyncTask + RxJava sem migração planejada pra Kotlin/Compose.

Adicionar uma 6ª anti-persona "QA mobile dedicado" foi considerado e rejeitado — QA não opera forge nem consome output específico (consome PR como reviewer qualquer, papel parcial coberto por Diego). Adicionar "Dev backend que apoia mobile" também foi rejeitado — backend dev não é audiência primária nem secundária; consome contracts mas não opera forge.

Adicionar anti-persona nova exige brainstorm explícito + revisita do PRD — não silent drift. Lista é deliberadamente curta (5 perfis); cada um cobre uma fronteira clara do produto, não inflação defensiva contra qualquer não-usuário hipotético.

**Como anti-persona vira persona** (transição inversa): se uma anti-persona acumular demanda concreta com revisita formal de boundary, pode entrar em [`01-personas.md`](01-personas.md) Camada B ou C via brainstorm + writing-plan + dispatch. Por exemplo, "dev React Native sênior em squad híbrida mobile-RN" não tem persona declarada hoje; se squads híbridas começarem a adotar feature-forge cumulativamente, a anti-persona "Dev Flutter / React Native" pode se dividir em "RN-only não-elegível" + "RN-mixed-with-native elegível via card local" — exige revisita formal, não drift silencioso.

---

## §10 — Cross-refs docs técnicos

Tabela canônica dos 10 docs técnicos que ancoram o conteúdo deste PRD. Cada linha: doc + lente + quando consultar. Quando este PRD entra em conflito com algum desses, **doc técnico vence** (hierarquia explícita — PRD orquestra, não declara).

Esta tabela é a porta de entrada pra navegação cruzada do projeto. Mantenedor que precisa entender "como o engine sabe disso?" sai do PRD via cross-ref específico; Claude futuro que recebe context-pack pra escrever artefato encontra na tabela qual doc consultar primeiro. Cross-refs no PRD são unidirecionais (PRD → docs técnicos) por decisão consciente do spec — adicionar bidirecional ("docs/design/00-vision.md ganha nota apontando pra docs/product/00-prd.md") seria edit em arquivo load-bearing e exige revisita formal (Mandamento #1 do projeto).

**Cross-refs unidirecionais como decisão arquitetural:**

PRD aponta pra docs técnicos, mas docs técnicos NÃO apontam de volta pra PRD nesta entrega v1.2. Motivo: editar `docs/design/00-vision.md` ou `docs/design/ROADMAP.md` pra adicionar "Lente produto complementar em docs/product/00-prd.md" exigiria mudança em arquivo load-bearing — Mandamento #1 do projeto requer revisita explícita pra essa categoria de mudança. Bidirecional fica como polish item separado em [`docs/design/04-pending.md`](../design/04-pending.md), abertura por brainstorm subsequente quando demanda concreta de navegação cruzada justificar.

**Hierarquia de autoridade entre docs (em conflito, quem vence):**

1. **`CLAUDE.md` + `.claude/rules/*` do projeto consumidor** — instruções diretas do user/projeto. Vencem qualquer canon do feature-forge (hierarquia superpowers: user > skills > defaults).
2. **`docs/design/01-decisions.md` (decisões locked + load-bearing)** — Mandamento 1 do projeto. Mudar exige revisita formal com "Revisita decisão N" em CHANGELOG.
3. **`docs/design/00-vision.md`** — declara o que feature-forge **é** + boundary OUT-OF-SCOPE permanente. Load-bearing.
4. **`docs/design/07-discipline.md`** — 10 disciplinas universais. Quebrar = quebra UX consistency.
5. **`docs/design/04-pending.md`** — gaps inventoriados (abertos + deferred + closed + permanent OUT). Fonte de verdade pra "o que falta".
6. **Outros docs em `docs/design/`** + `docs/schemas/` + `docs/lifecycle/` + `docs/ux/` — referência operacional.
7. **`docs/product/` (este eixo)** — orquestração de produto; em conflito, doc técnico vence.

| Doc | Lente | Quando consultar |
|---|---|---|
| [`docs/design/00-vision.md`](../design/00-vision.md) | Arquitetura (6 layers + capability cards + What feature-forge is NOT) | Pra entender quê o sistema **é** arquiteturalmente; boundary OUT-OF-SCOPE permanente; visão original do produto |
| [`docs/design/01-decisions.md`](../design/01-decisions.md) | 27 decisões locked + 7 direcionais + ADR 28 | Pra entender o **por quê** das escolhas arquiteturais; 8 decisões load-bearing (D14/D15/D18/D19/D20/D22/D23/D27) que quebrariam arquitetura inteira se mudadas silenciosamente |
| [`docs/design/02-phases.md`](../design/02-phases.md) | Phases técnicos entregues (1-5 + 3.5) | Pra ver o histórico de entrega; correlação Onda produto ↔ Phase técnico em [`03-roadmap.md`](03-roadmap.md) §7 |
| [`docs/design/04-pending.md`](../design/04-pending.md) | Gaps inventoriados (abertos + deferred + closed + permanent OUT) | Pra entender o que falta + por quê algumas demandas viraram anti-roadmap (§9 + [`03-roadmap.md`](03-roadmap.md) §6) |
| [`docs/design/07-discipline.md`](../design/07-discipline.md) | 10 disciplinas universais (3-caminhos, validator cascade, pause/abort, .bak retention, project-native vocabulary, fingerprint, etc.) | Pra aplicar gates corretos; 3-caminhos canônico; cascade fail-fast; auto-retro 5-whys; pattern extension feature (§10) |
| [`docs/design/08-session-handoff.md`](../design/08-session-handoff.md) | Estado canônico por versão (Última atualização / Estado / Conhecidos limites) | Pra retomar sessão fria; verificar baseline atual (count de tests/cards/validators); ver próximos passos |
| [`docs/design/ROADMAP.md`](../design/ROADMAP.md) | Phases técnicos pós-v1 (6, 7, 8, ...) | Pra ver o eixo técnico do roadmap; correlação 1:1 (Onda 1 ↔ Phase 6) ou compositiva (Onda 2 ↔ Phase 7 + Gap 5 + multi-dev) em [`03-roadmap.md`](03-roadmap.md) §7 |
| [`docs/lifecycle/memory-and-graph.md`](../lifecycle/memory-and-graph.md) | Dataflow memory + reuse-intel + 17 graph queries | Pra entender L1/L2/L3 lifecycle; Q1-Q11 capabilities; Q12-Q17 reuse-intelligence; fingerprint sha256 anti-redundância |
| [`docs/schemas/`](../schemas/) | 9 schemas YAML/JSON (card, capability-labels, status, memory, workflow-config, etc.) | Pra validar artefatos gerados; entender shape de cada YAML/JSON do projeto; canon schema de cards locais (Gap 5) |
| [`docs/ux/`](../ux/) | 7 roteiros cinemáticos por comando (init, plan, implement, verify, doctor, reconfigure, evolve) | Pra ver UX do comando X em detalhe operacional (prompts do conductor, transcrições de wave, fluxo de menu interativo); complementa cenários em [`02-scenarios.md`](02-scenarios.md) |

---

## §11 — Glossary de termos canon

15 termos canônicos usados ao longo do PRD + sub-docs. Cada definição é curta (1-2 linhas) com cross-ref pro schema/decision/disciplina que ancora o termo. Drift de vocabulário enfraquece comunicação compartilhada entre mantenedor + Claude futuro — usar nome canônico, não sinônimo genérico.

Termos são organizados em camadas conceituais: subtype/wave/card/preset cobrem o modelo declarativo (o quê o engine compõe); L1/L2/L3/capability label cobrem dataflow (onde o engine guarda knowledge); extension feature / blocked-on-external / backend-candidate cobrem estados e variantes (como o engine modela exceções); reuse-intelligence / card local overlay / 3-caminhos / phase lock / subagent cobrem mecânicas de disciplina (como o engine garante invariantes).

**Como termos viram canon:**

- Termo aparece em discussão técnica recorrente entre mantenedor + Claude futuro.
- Termo é registrado em [`docs/design/01-decisions.md`](../design/01-decisions.md) (se locked) ou [`docs/design/07-discipline.md`](../design/07-discipline.md) (se disciplina) ou [`docs/schemas/*.md`](../schemas/) (se schema).
- Termo entra neste glossário com cross-ref pro contract canônico.
- Sub-docs + agent prompts + templates usam o termo consistentemente; drift = scope creep silencioso.

**Termos que entraram no canon recentemente:**

- **Extension feature** entrou via Gap 9 shipado v1.2 (commit `7976686`); pattern leve product-derived sem custo arquitetural. Vide cenário C5.
- **Backend-candidate** entrou via Decision 28 ADR (cards reservados); cards Apollo/GraphQL/gRPC ficam dormentes até signal positivo.
- **Card local overlay** entrou via Gap 5 spec'd em `2026-06-02-gap5-card-local-overlay-design.md`; caminho oficial pra stack-specific.

**Termos rejeitados (não entraram no canon):**

- "Epic" / "story" / "task" no sentido scrum — vocabulário PM, conflita com "feature" + "task" do forge (que tem semântica técnica diferente).
- "Sprint" / "release" / "milestone" — domínio PM, out-of-scope (§9 anti-personas).
- "Component" no sentido React/Vue — conflita com "card" + "screen-state" do forge.
- "Service" no sentido microservices — não há analogia direta em mobile; "card" cobre composição declarativa de capability.

| Termo | Definição | Cross-ref |
|---|---|---|
| **Subtype** | Variante de feature: `product` (default) / `refactor` / `bugfix` / `spike` / `chore`. Cada um tem waves específicas e validators dedicados; detecção via keywords + ticket-pattern em Cena 2.5 do `forge plan`. | [`docs/design/04-pending.md`](../design/04-pending.md) §Gap 1, 2 |
| **Wave** | Fase de planning: A (intake), B (PRD + screen-analysis, conditional via `wave_b_required`), C (contracts — BDD + analytics + threat + data-contract), D (tech-spec + tasks com `allowed_files`), E (readiness review). | [`docs/ux/forge-plan-roteiro.md`](../ux/forge-plan-roteiro.md) |
| **Card** | Unidade atômica de composição: templates + validators + agent prompts. 22 canon em v1.2 + overlay local (Gap 5). README substantivo por card explicando trade-offs vs alternativas. | [`docs/schemas/card.md`](../schemas/card.md) |
| **Preset** | Alias para combinação canônica de cards. v1.2 tem `kmp-mobile` (10 cards stack + 4 backend-candidates dormentes). Onda 2 introduz `ios-only` e `android-only`. | [`docs/schemas/card.md`](../schemas/card.md) |
| **L1** | Memory per-feature (WIP). Grava estado intermediário em `.claude/forge/state/lifecycle/<slug>/status.json` + artefatos em `.planning/<slug>/`. Resumível cross-session via Decision 27 (auto-resume `deferred`). | [`docs/schemas/memory.md`](../schemas/memory.md) |
| **L2** | Memory project-level (committed em repo). Acumula learnings via retrospective auto-trigger pós-verify; `proposed-evolutions.yaml` revisado em `forge evolve`. | [`docs/schemas/memory.md`](../schemas/memory.md) |
| **L3** | Memory cross-project read-only (futuro — Onda 3 aspiracional). Auto-injetado em context-pack quando aplicável; sub-agente consome, não escreve. | [`docs/schemas/memory.md`](../schemas/memory.md) |
| **Capability label** | Abstração de capacidade técnica (ex: `http-client`, `auth-provider`, `persistence-local`, `analytics-emitter`). Cards declaram quais capabilities providenciam; queries Q1-Q11 do graph operam sobre essa abstração. | [`docs/schemas/capability-labels.md`](../schemas/capability-labels.md) |
| **Extension feature** | Pattern leve product-derived (Gap 9, shipado v1.2). Feature done estendida via slug derivado (`<parent>-<suffix>`) com `extends-feature` em L1 + `extension-depth` automático; validators EXT-001..004 conferem invariantes. | [`docs/design/07-discipline.md`](../design/07-discipline.md) §10 |
| **Blocked-on-external** | L1 status pra feature esperando ação externa (auth provisioning, ticket externo, integração de outro time). State auto-resumível quando dep externa resolver; reaparece em `forge status` board. | [`docs/design/04-pending.md`](../design/04-pending.md) §Gap 8 |
| **Backend-candidate** | Card sugerido em preset mas não ativado até usuário escolher (REST via Retrofit vs Firebase Storage vs GraphQL Apollo). Fica dormente sem signal positivo; ativa por demanda concreta da feature. | [`presets/kmp-mobile.yaml`](../../presets/kmp-mobile.yaml) |
| **Reuse-intelligence** | 6 categorias de finding detectadas via Q12-Q17 do graph: consolidate-within-module / promote-to-shared / redundant-platform / near-duplicate / kmp-migration-candidate / consolidate-ts-helpers. Engine sugere; humano decide via `forge evolve`. | [`docs/lifecycle/memory-and-graph.md`](../lifecycle/memory-and-graph.md) |
| **Card local overlay** | `.claude/cards/local/<name>/` versionado em repo do projeto consumidor; complementa canon sem fork upstream. Gap 5 cobre o pattern oficial; cards locais têm mesmos garantias de canon (validators, README, agent-contributions). | [`docs/superpowers/specs/2026-06-02-gap5-card-local-overlay-design.md`](../superpowers/specs/2026-06-02-gap5-card-local-overlay-design.md) |
| **3-caminhos** | Padrão de gate-resolution canônico: sempre 3 opções (fix forward / revert / split-escalate), nunca 2, nunca 4, nunca "consulte a documentação". Aplicado em qualquer validator fail / escopo violado / ambiguidade entre cards. | [`docs/design/07-discipline.md`](../design/07-discipline.md) §1 |
| **Phase lock** | Sentinel `.phase-lock` em `.planning/<slug>/` que previne concurrent operations na mesma feature (proteção contra dispatch paralelo acidental do orchestrator). Tornado visível em multi-dev (Onda 2). | [`docs/schemas/memory.md`](../schemas/memory.md) |
| **Subagent (Claude Code)** | Instância Claude Code dispatchada via `Agent` tool. Distinto de `agent prompt` (template em `agents/<name>.md` consumido pelo subagent). Em [`01-personas.md`](01-personas.md) "Sub-agente Claude" é a persona técnica que executa esses dispatches. | [`.claude/rules/subagent-workflow.md`](../../.claude/rules/subagent-workflow.md) |

---

## §12 — FAQ

9 perguntas canônicas + respostas curtas (2-3 linhas cada). Cross-refs pro contract canônico quando aplicável.

Perguntas vivem aqui quando aparecem repetidamente em onboarding (Bruno avaliando adopt, Carolina entendendo padrão, Marina pesquisando capability) e quando a resposta cabe em poucas linhas com cross-ref pro detalhe. Perguntas mais profundas viram capítulos em [`docs/design/01-decisions.md`](../design/01-decisions.md) ou [`docs/design/04-pending.md`](../design/04-pending.md) (gaps em discussão). FAQ não é exaustivo — é o subset que aparece em primeiro contato com o produto e merece resposta de 30s.

**Como FAQ evolui:**

- Pergunta nova aparece repetidamente em onboarding (≥3 squads/devs distintos perguntando o mesmo) → adiciona aqui.
- Pergunta velha some da circulação (resolvida via doc canônico ou tornou-se obsoleta com nova onda) → remove com cross-ref no commit body.
- Pergunta entra em discussão mais profunda → migra de FAQ pra [`docs/design/04-pending.md`](../design/04-pending.md) como gap aberto.

**Perguntas que apareceram em onboarding mas foram resolvidas via docs canônicos** (não viraram FAQ aqui):

- "Por que monorepo é Decision 14 LOCKED?" — resposta em [`docs/design/01-decisions.md`](../design/01-decisions.md) D14 com rationale escrito; FAQ §12 cobre apenas "Monorepo funciona?" com 2-linha + cross-ref.
- "Quais commands existem em forge?" — resposta em [`docs/design/06-command-surface.md`](../design/06-command-surface.md); FAQ não duplica command surface.
- "O que é a diferença entre L1/L2/L3?" — resposta em glossário §11 deste doc + [`docs/schemas/memory.md`](../schemas/memory.md); FAQ não duplica termos do glossário.

**Perguntas relacionadas mas que NÃO viraram FAQ aqui** (estão em outros docs):

- "Como instalar feature-forge num projeto novo?" → resposta em README.md + `bash .claude/bootstrap.sh`; instrução operacional, não pergunta de produto.
- "Quais comandos forge disponíveis?" → resposta em [`docs/design/06-command-surface.md`](../design/06-command-surface.md); referência técnica.
- "Como abrir um issue no projeto feature-forge?" → resposta em README.md / CONTRIBUTING.md; instrução operacional projeto-mantenedor.
- "Como debuggar quando `forge verify` falha?" → resposta em [`docs/ux/forge-verify-roteiro.md`](../ux/forge-verify-roteiro.md); UX detalhado.

| Q | A resumida |
|---|---|
| **Por que zero flags?** | Decision 10 LOCKED. Discoverability + persona-native vocabulary — toda parametrização via menu interativo PT-BR neutro. Marina não precisa decorar flags; aprende via UI conversacional. Cross-ref: [`docs/design/01-decisions.md`](../design/01-decisions.md) D10. |
| **Por que Koin e não Hilt?** | KMP + Android + iOS uniforme — Koin Annotations é multiplataforma (commonMain + iosMain + androidMain); Hilt é Android-only. Canon mobile prioriza uniformidade KMP; Hilt entra via Gap 5 overlay local quando squad demanda concreta justificar. Cross-ref: [`presets/kmp-mobile.yaml`](../../presets/kmp-mobile.yaml). |
| **Como migro de forge-specs?** | `forge raw migrator-N-to-M` (stub v1.2 — implementação real demand-driven). Migrators são entregues per-upgrade quando schema muda; v1.2→v1.3 vai ter migrator dedicado quando Onda 1 shippar Apply Mode + L1 schema mudar. Cross-ref: Decision 9 LOCKED. |
| **Multi-dev mesma feature?** | v1 single-user assumido; workaround é split em features menores (1 dev por feature). Onda 2 endereça merge-strategy formal (Gap 6 deferred → resolved) com phase-lock cross-dev visível. Cross-ref: [`docs/design/04-pending.md`](../design/04-pending.md) §Gap 6. |
| **watchOS / Wear OS / tvOS?** | Out-of-scope **permanente** (Gap 9 revisita 2026-06-03). Canon focado em Android + iOS + KMP + Web preserva qualidade; plataforma exótica via Gap 5 overlay local (cards locais standalone). Cross-ref: [`docs/design/04-pending.md`](../design/04-pending.md) §Gap 9. |
| **Por que não automatiza decisão produto?** | Engine dirige HOW (template + validator + agent prompt + atomic commit + retro automático); usuário decide WHAT (user value, persona, business outcome, trade-off arquitetural). Princípio non-negociável — Decision 22 + §3 deste doc. Sugestão com confidence ≠ decisão automática. |
| **Java puro funciona?** | Não — Kotlin é linguagem-âncora. Templates/cards/agents assumem Kotlin (Coroutines, Flow, KMP, expects/actuals). Java puro entra em anti-persona §9; squad Java-only precisa de skill genérica diferente. Cross-ref: §9 anti-personas. |
| **Monorepo?** | Sim — Decision 14 LOCKED (config scope é um `workflow-config.yaml` por sub-projeto). Cada sub-projeto KMP/Android/iOS dentro do monorepo tem seu próprio `.claude/` + L1 + L2; sem conflito entre sub-projetos. Cross-ref: [`docs/design/01-decisions.md`](../design/01-decisions.md) D14. |
| **`forge implement` aplica diff auto?** | v1.2 é stub manual — engine renderiza handoff em texto, dev aplica diff à mão. Onda 1 (Phase 6) cobre Apply Mode real: sub-agente Claude aplica diff dentro de `allowed_files` + pre-commit review automatizado + atomic commit + L1 transitions automáticas. Cross-ref: [`03-roadmap.md`](03-roadmap.md) §2. |

---

## §13 — Risks & Open questions

Risks são cenários hipotéticos onde a estratégia atual pode falhar; cada um tem mitigação preventiva já em vigor ou planejada. Open questions são perguntas legítimas onde decisão final ainda não foi tomada — ficam em "decide quando aparecer demanda real" pra evitar over-engineering preventivo (Mandamento "não procrastinação" do projeto vale pra implementação, não pra antecipação de demanda).

Risks que viram realidade entram em [`docs/design/04-pending.md`](../design/04-pending.md) como gap a endereçar. Open questions que recebem demanda concreta entram em brainstorm + writing-plan. Nenhum dos dois fica em "anotado e esquecido" — auditoria mensal manual re-verifica os 10 itens abaixo (6 risks + 4 open Qs).

**Risks (6) com mitigação:**

| Risk | Mitigação |
|---|---|
| **R1.** "Mobile dev solo" perde relevância em squads grandes — feature-forge fica niche se mercado pivota pra squads de 10+ devs como norma. | Onda 2 cobre multi-dev opcional (Gap 6 resolved) com merge-strategy formal e phase-lock cross-dev visível; v1 já funciona pra squad pequena (1-3 devs) que é maioria empírica em projetos product-grade; persona Bruno cobre o caso squad maior expandindo escopo gradualmente (3-8 devs). Mercado mobile não pivotando ainda; quando pivotar, Onda 2 estará pronta. |
| **R2.** Demanda real por marketplace pública aparece em escala — comunidade pede registry de cards user-contributed em massa. | Gap 5 cobre overlay LOCAL versionado em `.claude/cards/local/<name>/`; pública viola Decision 22 (no runtime deps em outras skills). Push-back firme com cross-ref pro contract violado; rationale escrito em [`03-roadmap.md`](03-roadmap.md) §6 + anti-personas §9 deste PRD. Cards compartilháveis entre squads via cópia explícita, não fetch dinâmico de registry. |
| **R3.** Onda 1 (LLM hookup) tem custos não-escalonáveis — API key cost por feature implementada via Apply Mode vira inviável em volume. | v1.2 mantém stub manual (handoff em texto, dev aplica diff à mão); Apply Mode (Phase 6) é opt-in — user fornece API key própria (Anthropic ou similar). Custo é do user, não do projeto. Engine não vira SaaS hosted (anti-roadmap permanente, Decision 18 + 22 LOCKED). Volume vira problema do user, não risco do projeto. |
| **R4.** Stack iOS/Swift puro pressiona preset `ios-only` antes da Onda 2 entregar — squad iOS-only crescer e workaround manual ficar insustentável. | Lucas com caveats v1 documentados em [`01-personas.md`](01-personas.md) tabela obrigatória (6 linhas Aspecto/Estado v1.2/Comportamento/Workaround). Gap 5 cobre cards iOS locais (Alamofire, KeychainAccess) como caminho oficial até preset shippar. Se demanda concreta acumular antes da Onda 2 planejada, preset experimental v1.x+ pode shippar fora de batch — exige brainstorm + writing-plan + dispatch como qualquer onda. |
| **R5.** Tree-sitter adoção implica dep externa + complexity — Phase 7 não viabiliza se mantenedor escolher não adicionar dep grande. | Regex pragmático v1 funciona em ~70-80% dos casos detectáveis em projetos canon; AST entra quando false-positive crítico aparecer empíricamente (Phase 7 é demand-driven, não obrigatório). Onda 3 aspiracional fica condicional a Phase 7 entregue; se Phase 7 ficar bloqueada, Onda 3 não shippa — escala não é compromisso firme. |
| **R6.** Squad grande adota → fricção com squad pequena (overhead) — disciplina mecânica que serve squad de 5 devs pode ser overhead pra dev solo. | Subtypes `bugfix` + `chore` (stubbed v1.2, completo v1.x+) dão fast-path em casos onde fluxo product completo seria over-engineering; product subtype é opt-in implicitly via Cena 1 (slug + keywords decidem); `wave_b_required=false` skipa wave inteira em casos certos (vide C3 bugfix em [`02-scenarios.md`](02-scenarios.md)). Marina (dev solo) e Bruno (squad maior) compartilham ferramenta, mas usam diferentes subtypes/skips conforme contexto. |

**Como cada risk seria mitigado se virar realidade:**

- **R1** (mobile dev solo perde relevância) → Onda 2 já planeja multi-dev; se demanda chegar antes da Onda 2 planejada, multi-dev pode shippar fora de batch (igual R4 com preset `ios-only`).
- **R2** (demanda marketplace pública escalar) → push-back firme + amplificar comunicação sobre Gap 5 local; se demanda atingir massa crítica (10+ squads pedindo), revisita formal Decision 22 — possivelmente nunca, dado peso load-bearing.
- **R3** (custo LLM não-escalonável) → API key do user é arquitetura intencional; volume vira problema do user. Engine fica neutro ao custo. Se vendor Anthropic mudar pricing brutamente, Apply Mode pode ser refatorado pra LLM local (Llama, Mistral) sem mudar contrato com user.
- **R4** (pressão iOS antes da Onda 2) → preset experimental v1.x+ via brainstorm + writing-plan + dispatch fora de batch; risk de tornar canon ad-hoc em troca de adoção.
- **R5** (Tree-sitter bloqueia Phase 7) → regex pragmático segue como default; AST entra incremental por linguagem (Kotlin primeiro, Swift depois, TypeScript por último).
- **R6** (squad grande gera fricção pra squad pequena) → completar subtypes stubbed (`spike`, `chore`) e shippar fast-paths sob demanda concreta; preset ad-hoc pra perfis específicos (`single-dev-mode` hipotético).

**Open questions (4):**

Open questions são perguntas legítimas onde decisão final ainda não foi tomada por falta de demanda concreta ou contexto suficiente. Diferente de risks (que têm mitigação preventiva), open questions ficam em "decide quando aparecer demanda real". Anotadas aqui pra evitar amnésia em sessões futuras.

| Q | Status |
|---|---|
| **Q1.** Como migrar projeto que JÁ tem disciplina X (Confluence-driven, Notion-based, in-house wiki, etc.)? | Brainstorm pendente; possível `forge ingest --event project-import` que parsea Confluence/Notion existente e popula L2 inicial via mapping declarativo. Anotado em `04-pending.md` pra discussão futura; sem prazo definido. Demanda concreta de projeto-consumidor X ainda não chegou. |
| **Q2.** Spike subtype real precisa "exploring" state ortogonal a planning/implementing/verified — spike típica não cabe no fluxo linear product. | [`docs/design/04-pending.md`](../design/04-pending.md) §Gap 2 deferred v1.x+; spike stubbed em v1.2 mas não completo. Decisão tomada: spike entra quando demanda real surgir (não shippa preventivo). Spike é típica de squad maior fazendo PoC; squad pequena raramente spike formal. |
| **Q3.** Code review humano (Diego) ganha integração com forge — hook PR-side (GitHub Action que comenta forge findings no PR)? | Out-of-scope explícito v1; pode evoluir em v2+ se demanda surgir. Brainstorm não iniciado; Diego hoje opera 100% via PR review nativo do GitHub/GitLab sem dep no forge. Integração GitHub Action seria opcional, não default, pra não comprometer CLI-first. |
| **Q4.** Multi-dev mesma feature merge-strategy formal — qual o pattern canônico quando 2 devs paralelizam na mesma slug? | [`docs/design/04-pending.md`](../design/04-pending.md) §Gap 6 deferred v1.x+. Onda 2 endereça via phase-lock cross-dev + merge-strategy documentada em `docs/design/07-discipline.md §novo`. Sem decisão prévia ao planejamento da Onda 2 — depende de smoke test multi-dev em fixture real (2 contas Claude Code paralelas). |

---

## Notas finais de design

**Por que este doc é a porta de entrada, e não capítulo único:**

A escolha de fazer 00-prd como porta de entrada + 3 sub-docs detalhados foi deliberada conforme spec [`docs/superpowers/specs/2026-06-04-prd-design.md`](../superpowers/specs/2026-06-04-prd-design.md). Alternativa rejeitada: PRD monolítico de ~2370 LOC num arquivo só. Razões:

- **Densidade de leitura por contexto** — Marina onboarding precisa de §5 personas + §6 cenários em sessão de 30min; PM Bruno avaliando adopt precisa de §1+§2+§3+§8 em sessão de 1h; Carolina iniciante precisa de §11 glossary + §12 FAQ ao longo de 2 semanas. Monolítico forçaria todos a scroll cross-context.
- **Cross-refs estáveis** — sub-docs com path conhecido (01-personas.md, 02-scenarios.md, 03-roadmap.md) permitem cross-ref desde outros docs (`docs/design/*`, `docs/ux/*`) sem acoplar a anchors internos do 00-prd que podem mudar.
- **Manutenção independente** — atualizar persona Lucas (caveats v1) não toca PRD inteiro; só [`01-personas.md`](01-personas.md) §Lucas. Idem cenário C3 (bugfix retrabalho) e onda 2 (catálogo).
- **Spec coexistência** — `docs/design/`, `docs/ux/`, `docs/product/` paralelos seguem o mesmo padrão (vários arquivos numerados); inconsistência seria PRD monolítico vs design fragmentado.

**Como este doc evolui:**

- **Trigger automático** — onda fecha em [`03-roadmap.md`](03-roadmap.md), métricas baseline mudam, baseline stats em §8 desatualiza → doc-sync paralelo neste PRD + sub-doc correspondente.
- **Trigger explícito** — persona nova ou anti-persona reconsiderada → brainstorm + writing-plan + dispatch (não edit silent). Personas/anti-personas têm peso load-bearing.
- **Trigger documentação técnica** — quando doc canônico em §10 muda load-bearing (ex: Decision N revisitada), revisita formal sobe a cadeia: contract → PRD → sub-docs.

**Quando este PRD perde autoridade:**

Em qualquer conflito com doc técnico canônico (§10), **doc técnico vence**. PRD é orquestração e síntese de produto; decisão arquitetural definitiva vive em `docs/design/`. Mandamento 1 do projeto (decisões load-bearing imutáveis sem revisita formal) é absoluto.

Se este PRD declarar algo que diverge de [`docs/design/00-vision.md`](../design/00-vision.md) ou [`docs/design/01-decisions.md`](../design/01-decisions.md), o erro está aqui — abrir doc-sync pra realinhar.

**Sinais de drift entre PRD e docs técnicos:**

- Baseline stats em §8 desatualiza (test count em PRD vs `pytest --collect-only` empírico no commit atual diverge).
- Persona em [`01-personas.md`](01-personas.md) ganha mudança substantiva sem update no resumo §5 daqui.
- Onda em [`03-roadmap.md`](03-roadmap.md) transita estado (planned → in-progress → done) sem update no resumo §7.
- Decisão locked em [`docs/design/01-decisions.md`](../design/01-decisions.md) é revisitada sem update em §3 princípios ou §4 escopo.
- Anti-roadmap em [`03-roadmap.md`](03-roadmap.md) ganha item novo sem update em §4 OUT ou §9 anti-personas.

Auditoria mensal manual (ver `.claude/rules/README.md §Auditoria contínua`) checa esses 5 sinais. Drift detectado vira task de doc-sync; gap de auditoria entra em [`docs/design/04-pending.md`](../design/04-pending.md).

**Cabeçalho deste doc evolui:**

- **Audiência** muda só se este PRD virar open-source landing ou marketing-facing (não é o caso v1.2).
- **Status** atualiza a cada versão fechada (v1.2.0 + Gap 9 → próximo v1.3 + Onda 1).
- **Baseline stats** (637/22/15/17) atualizam quando `pytest --collect-only` + count de cards/validators/queries mudar empíricamente.

Manter o cabeçalho sincronizado com state real do projeto é Mandamento #6 (doc-sync na mesma mudança).

---

> **Próxima revisão deste doc:** quando uma onda completar em [`03-roadmap.md`](03-roadmap.md) e alterar baseline; quando persona nova entrar em [`01-personas.md`](01-personas.md) (exige brainstorm); quando anti-persona ou anti-roadmap item for reconsiderado via revisita formal do contract referenciado. Em qualquer caso, doc passa por brainstorm + writing-plan + dispatch — não edit silent.
>
> **Auditoria continuada:** este PRD é orquestração; em conflito com docs técnicos canônicos (§10), **doc técnico vence**. Mandamento 1 do projeto (decisões load-bearing imutáveis sem revisita formal) é absoluto — PRD complementa, não substitui.
>
> **Fonte canônica do design:** [`docs/superpowers/specs/2026-06-04-prd-design.md`](../superpowers/specs/2026-06-04-prd-design.md) (commit `2e1a266`). Plano de implementação: [`docs/superpowers/plans/2026-06-04-product-docs.md`](../superpowers/plans/2026-06-04-product-docs.md). Quando este PRD diverge do spec/plan canônico, abre brainstorm pra realinhar — não silent drift entre o que foi spec'd e o que está shipado.
