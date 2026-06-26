# Personas do feature-forge

> **Cross-ref:** Este doc é referenciado por [`00-prd.md`](00-prd.md) §5, [`02-scenarios.md`](02-scenarios.md) (persona principal de cada cenário) e [`03-roadmap.md`](03-roadmap.md) (persona afetada por onda).

8 personas em 3 camadas. Camada A é dedicada (day-in-life completo); Camada B agrupa variantes da Marina com caveats; Camada C cobre consumidores downstream / read-only.

A organização em 3 camadas existe pra ancorar trade-offs de design do engine. Quando uma decisão atinge Marina, é direta; quando atinge Carlos / Lucas / Carolina, é via caveat documentado; quando atinge Patricia / Diego, é via interface read-only ou via output do engine consumido downstream. Toda decisão de produto declarada em [`00-prd.md`](00-prd.md) §3 (princípios) pode ser rastreada a uma persona específica desta tripla camada.

Nomes canônicos (consistência rígida — não trocar): **Marina** (primária), **Bruno** (tech lead), **Sub-agente Claude** (técnica não-humana), **Carlos** (Android-only), **Lucas** (iOS-only), **Carolina** (iniciante), **Patricia** (PM), **Diego** (code reviewer). Sub-agente Claude é a única persona não-humana — intencional, sublinha que é técnica e não tem desejos humanos, apenas contratos de comportamento.

---

## Camada A — Personas dedicadas

### Marina — Mobile dev solo KMP/Android (PRIMÁRIA)

**Perfil**

- 4-6 anos de experiência mobile
- Squad pequena (1-3 devs); dona de feature ponta-a-ponta — do PRD ao merge
- Usuário-âncora do feature-forge: tudo no engine é otimizado pra reduzir fricção dela primeiro
- Os demais arquétipos (Bruno / Carlos / Lucas / Carolina) são variações ou consequências do desenho centrado em Marina

**Stack típica**

- Kotlin + Coroutines + Flow como linguagem-âncora
- KMP shared module pra business logic
- Compose pra Android UI
- SwiftUI via shared expects pra iOS UI
- Koin Annotations pra DI (canon mobile uniforme KMP)
- Nav3 pra navegação
- REST (Retrofit) ou Firebase como backend (escolha por feature)
- Room pra persistência relacional Android
- DataStore pra preferences
- Conhece o canon dos 22 cards quase de cor; sabe quando precisa de overlay local (Gap 5) e quando o canon basta

**Contexto de trabalho**

- Projeto product-grade em produção
- Usuários finais reais com expectativa de qualidade
- SLA de release semanal ou quinzenal
- Backlog priorizado pelo PM (Patricia)
- Peer review eventual de outro dev sênior (Diego como reviewer downstream do PR)
- Marina opina sobre clean architecture mobile sem ser dogmática

**JTBD principal**

- Levar feature de ticket → shipado sem reinventar arquitetura toda vez. O custo mental de "como vou estruturar isso?" deve cair feature a feature, não subir.
- Não esquecer step crítico (BDD, analytics, threat model, regression test) na correria. Disciplina mecânica não pode depender de Marina lembrar — engine garante.
- Manter padrão consistente entre features (DI, navegação, contracts, naming, error handling). Drift entre features é débito acumulado que cresce silenciosamente.
- Reduzir cerimônia em bugfix / refactor sem perder rigor (regression test obrigatório em bugfix; no-behavior-change attestation em refactor).

**Frustrações sem forge**

- "Cada feature começa do zero — copio estrutura da feature anterior e adapto. Retrabalho mecânico que rouba tempo de decisões reais."
- "PRD fragmentado entre Confluence + Notion + comentário de PR; quando volto pra entender 'por quê assim', não acho. Decisão técnica perde rastreabilidade em 2-3 sprints."
- "Bugfix urgente pula PRD; semanas depois esqueço de adicionar regression test e o bug volta. Pressão de hotfix conflita com disciplina mecânica."
- "Hilt / Koin / Apollo / Retrofit / Room / DataStore — cada projeto novo tenho que decidir DI / network / cache do zero. Decisão default deveria existir, customização deveria ser exceção."

**Critérios sucesso com forge**

- `forge plan` → readiness=ready em ≤15min pra feature product nova (Waves A-E completas com sub-agentes preenchendo o que dá, Marina elicitando o que falta)
- Zero atalho-virou-hábito (regression test obrigatório em bugfix; analytics obrigatório em feature product; gates impossíveis de pular silenciosamente)
- Retros geram L2 patterns sem Marina escrever doc manualmente — proposed-evolutions são revisadas via `forge evolve` semanal
- Cards locais (Gap 5) cobrem stack-specific quando canon não cobre, sem fork upstream

**Day-in-life típico (terça-feira)**

- **9h** — standup da squad mostra que Marina vai pegar IN-42100 "Lembrete de rega de planta"; PM (Patricia) passou 2 acceptance criteria + screenshot Figma; sem PRD escrito
- **9:15** — `forge plan lembrete-rega` → subtype=product detectado em Cena 2.5 (keywords product-shaped); Wave A intake preenche user value + scope + persona em <5min
- **9:30-10h** — Wave B PRD + screen-analysis — PM cola descrição + screenshot Figma; Marina valida com conductor; sub-agente preenche estados (loading / empty / success / error)
- **10-10:30** — Wave C contracts (BDD scenarios + analytics-spec + threat model + data-contract-spec) + Wave D tech-spec + 8 tasks com `allowed_files` declarados
- **10:30** — Wave E readiness=ready, conductor confirma
- **10:45-14h** — `forge implement lembrete-rega` task-por-task, atomic commits, gates de escopo travam refactor "while I'm here"
- **14:30** — `forge verify` cascade dos 15 validators → verde
- **14:45** — auto-retro dispara após verify verde → 3 evolutions L2 sugeridas (analytics naming patch, screen-state convention reuse, agent prompt addition)
- **15h** — Marina revisa via `forge evolve`, aceita 2 e rejeita 1 com motivo registrado (fingerprint anti-redundância protege próxima retrospectiva)

**Cenários onde Marina é persona principal**

- C2 — Feature product nova end-to-end (lembrete-rega IN-42100)
- C3 — Bugfix com ticket IN-37234 (P0 Android crash)
- C4 — Retomar trabalho pausado (cold-start, agenda-poda)
- C5 — Extension feature Gap 9 (lembrete-rega-hora derivada do parent done)
- C6 — Reuse intelligence em ação (compartilhada com Bruno, validateName promotion)

Detalhe em [`02-scenarios.md`](02-scenarios.md) quando criado.

**Métricas que medem sucesso pra Marina (target Onda 1)**

- Time-to-merge (ticket → PR merged): ≤4h (hoje ~6-8h sem forge)
- Manual edits per task após implement: 0 (hoje 5-15)
- Regression rate cross-feature (bug que volta): ≤2%

### Bruno — Tech lead / staff engineer (SECUNDÁRIA)

**Perfil**

- 7-12 anos de experiência mobile
- Lidera squad de 3-8 devs; decide adopt de ferramentas pra time inteiro
- Não escreve toda feature — supervisiona, faz PR review crítico, garante coerência arquitetural cross-feature
- Avalia adoção de feature-forge em <1 dia: vale onboarding e disciplina pra squad inteira?

**Stack típica**

- Mesma da Marina, mas pivota entre projetos com stacks heterogêneas
- Hilt num projeto Android-only legado
- Koin no KMP novo
- Apollo num GraphQL B2B
- Retrofit noutro REST consumer
- Conhece trade-offs profundo de DI, navegação, persistência
- Decide quando promover helper pra shared base, quando virar card local (Gap 5), quando refatorar feature inteira

**Contexto de trabalho**

- Múltiplos projetos cliente OU squad interna grande
- Visão cross-cutting (não foca em 1 feature por vez como Marina)
- Participa de arquitetura review mensal
- Toma decisão de adopt de ferramenta nova (forge é uma destas decisões)

**Momentos de uso forge**

- Onboarding squad nova — roda `forge init` no projeto-x e configura preset + cards canon + overlay local quando aplica
- Configurar cards locais quando stack foge canon (Gap 5 — `.claude/cards/local/hilt-di/` num projeto Android-only legado, p.ex.)
- Revisar proposed-evolutions acumuladas semanalmente via `forge evolve` — accept / reject / defer 47 propostas numa sessão
- Supervisionar sem revisar cada PR manualmente — forge garante mecânica (`allowed_files`, contracts, analytics presença), Bruno foca em decisão arquitetural no PR review

**JTBD principal**

- Garantir que squad inteira segue o padrão sem PR review eterno reescrevendo as mesmas regras toda semana
- Acumular learnings em L2 (memory project) pra reuso por features futuras — sem dev escrever doc manual; retro dispara automático após verify verde
- Decidir adopt em <1 dia sem onboarding extenso pra cada dev novo — `forge init` + read pra `docs/design/00-vision.md` é suficiente
- Cards locais cobrem stack-specific quando canon não cobre (Hilt em projeto Android-only, Alamofire em projeto iOS-only) sem precisar PR upstream pro canon

**Frustrações sem forge**

- "Onboarding leva 2 semanas — cada dev novo aprende padrões via osmose de PR review, frágil e demorado; quando dev sai, conhecimento sai junto."
- "Mesma decisão de UI / contract / DI debatida em 4 PRs distintos por mês, todo mês. Não tem repositório de WHY centralizado."
- "Sem trilha WHY documentada — decisão tomada em huddle some quando dev sai do time; arquitetura vira folclore oral."

**Critérios sucesso com forge**

- `forge init` → squad alinhada com preset + cards em <1 dia (não 2 semanas)
- L2 captura ≥80% dos patterns repetidos sem dev escrever doc manual; retro auto-trigger garante
- Cards locais cobrem stack-specific quando canon não cobre (Gap 5 é o caminho oficial, não fork do canon)

**Day-in-life típico (quarta tarde)**

- **14h** — dev novo entra na squad — Bruno roda `forge init` no projeto-x KMP
- **14:30** — Step 11.5 dispara — scan reuse-intelligence retorna 47 findings em 6 categorias (consolidate-within-module, promote-to-shared, redundant-platform, near-duplicate, kmp-migration-candidate, consolidate-ts-helpers)
- **15h** — Bruno revisa amostragem inline; gera `proposed-evolutions.yaml` com os 47 findings sem aceitar/rejeitar ainda — só registra pra triage do dia seguinte
- **15:30** — deixa rodando — dia seguinte Marina vai fazer triage via `forge evolve` (filtra `kind=promote-to-shared`, aceita 30, rejeita 12, defer 5)
- **16h** — revisão de PR de outro dev — vê que `forge implement` gerou diff dentro de `allowed_files` da task; PR review foca em decisão arquitetural (naming, trade-off, edge case), não em compliance mecânico (console.log esquecido, BDD ausente)

**Cenários onde Bruno é persona principal**

- C1 — Brownfield init com reuse-intelligence (compartilhado com Marina dia seguinte)
- C6 — Reuse intelligence em ação (compartilhado com Marina, validateName promotion via `forge evolve`)

Detalhe em [`02-scenarios.md`](02-scenarios.md) quando criado.

**Métricas que medem sucesso pra Bruno (target Onda 1+2)**

- Onboarding cumulativo squad nova: ≤1 dia (hoje ~2 semanas sem forge)
- L2 capture rate de patterns repetidos: ≥80% (sem dev escrever doc manual)
- Cards locais aceitos por squad cumulativo: ≥5 (validação de Gap 5 maduro)

### Sub-agente Claude — Persona técnica não-humana

**Perfil**

- Persona técnica, não humana
- 3 roles distintos no engine:
  - **planning-conductor** — dirige Waves A-E e detecta subtype em Cena 2.5
  - **executor** — renderiza diffs em modo Apply quando Phase 6 ativar (v1.3+)
  - **readiness-reviewer** — valida readiness verdict ao fim de Wave E
- Única persona não-humana neste doc — sublinhar isso é intencional pra não confundir o Sub-agente Claude com Marina ou Bruno
- Tem critérios de sucesso e frustrações próprias que são contratos técnicos, não desejos humanos

**Contexto de trabalho**

- Instância Claude Code dispatchada via `Agent` tool pelo orchestrator-mantenedor humano
- Recebe context-pack estruturado pelo orchestrator
- Opera com state persistido em L1 (`.claude/forge/state/lifecycle/<slug>/status.json`) entre invocações
- Nunca decide de fato — sempre apresenta 3-caminhos quando há ambiguidade

**Inputs canônicos esperados**

- Context-pack do orchestrator:
  - `subtype` detectado em Cena 2.5
  - `wave_b_required` boolean
  - external-deps declaradas
  - `allowed_files` precisos da task
  - instrução literal de voz mentor calmo PT-BR neutro
- Agent prompt (frontmatter com role + extension-points conforme `agents/<name>.md` — 9 prompts canônicos hoje: planning-conductor, feature-intake-agent, prd-writer, screen-analysis-agent, tech-spec-agent, task-contract-writer, readiness-reviewer, retrospective-agent, executor)
- Cards merged (catálogo canon ∪ overlay local quando Gap 5 ativo no projeto-x — loader helper `validators/_common.load_catalog` aplica guards)
- L1 status atual lido de `.claude/forge/state/lifecycle/<slug>/status.json` (`intake` / `planning` / `implementing` / `verified` / `done` / `blocked-on-external` / `deferred`)

**Outputs canônicos esperados**

- Artefatos preenchidos respeitando schema (PRD, screen-analysis, tech-spec, task-contract, analytics-spec, BDD, threat-model — 16 artefatos em product subtype; subset em refactor / bugfix conforme `docs/design/07-discipline.md` §8)
- Diff respeitando `allowed_files` da task atual (sem refactor lateral, sem rename "while I'm here", sem doc-sync inline na mesma task)
- Feedback 3-caminhos em qualquer gate violation (exatamente 3 opções: fix forward / revert / split-escalate; nunca 2, nunca 4, nunca "consulte a documentação")

**5 critérios sucesso (não-negociáveis)**

1. **Determinismo:** mesma entrada (context-pack + L1 state + cards merged) → mesma saída. Sem invenção criativa que varia entre dispatches sucessivos da mesma feature.
2. **Escopo:** `allowed_files` respeitado em diff produzido. Sem refactor lateral, sem rename "while I'm here", sem doc-sync inline em task de feature.
3. **Voz:** mentor calmo PT-BR neutro — warm em exploração (Waves A-B com Marina elicitando contexto), firme em gates (escopo / validator / contract), didático sem ser professoral.
4. **Never-invent:** se fonte ausente (PRD vago, ticket sem repro, screen sem comportamento) → emite `needs-elicitation` pro humano preencher, NÃO chuta valor pra preencher campo. Inventar é falha grave.
5. **3-caminhos em qualquer gate violation:** ambiguidade ou contradição em contract sempre vira 3 opções (fix forward / revert / split-escalate). Inventar 4º caminho fake ou colapsar pra 2 = falha de disciplina.

**Frustrações do Sub-agente Claude sem forge (sem context-pack estruturado)**

- "Context-pack vago → improviso interpretação, drift entre dispatches da mesma feature; impossível reproduzir output."
- "Sem extension-points formais nos agent-prompts → cada subagente reinventa estrutura de output, comparação impossível entre dispatches."
- "Sem 3-caminhos canônico documentado em `07-discipline.md` §1 → silent skip vira hábito; usuário humano não percebe que escopo cresceu sob seus pés."

**Day-in-life típico (Wave A dispatch pra subtype=bugfix)**

- Sub-agente Claude recebe context-pack do orchestrator com `subtype=bugfix`, `ticket=IN-37234`, `wave_b_required=false` (Marina respondeu "não é UI, lógica pura")
- Renderiza `feature-intake-bugfix.template.md` com prompts pra Reproduction steps + Expected vs actual + Root-cause hypothesis + Regression risk + Validation strategy
- Marina preenche os campos via UI conversacional; Sub-agente Claude valida cada campo (Reproduction obrigatório, Expected vs actual obrigatório, Root-cause aceita `unknown` mas trigga drill-down do conductor antes da Wave C)
- Salva L1 status (`state=planning`, `subtype=bugfix`, `wave-a-done=true`, `wave-b-required=false`)
- Devolve controle pro orchestrator com state coerente; próximo dispatch (tech-spec stripped + 2 tasks task-breakdown) já vem com Wave A persistida em L1

**Onde Sub-agente Claude opera em cenários**

- Cada cenário C1-C6 envolve pelo menos 1 dispatch de Sub-agente Claude (Wave A intake, Wave B PRD, Wave C contracts, Wave D tasks, Wave E readiness — combinações variam por subtype)
- Em C3 (bugfix), `wave_b_required=false` reduz dispatches; em C5 (extension), Wave A skipa elicit redundante; em C6 (reuse intel), conductor consulta `forge graph` antes de propor Wave C

Detalhe em [`02-scenarios.md`](02-scenarios.md) quando criado.

**Como o engine mede sucesso do Sub-agente Claude**

- Determinismo: hash do output bate entre dispatches da mesma feature em ≥95% dos campos
- Escopo: `validate_no_invented_behavior` + `check_files_in_allowed_files` passam em ≥99% dos commits gerados via Apply Mode (Onda 1)
- Voz: spot-check humano em PRs amostrais (não automatizável v1)

---

## Camada B — Variantes da Marina

### Carlos — Android-only sem KMP

**Diferencial vs Marina**

- Stack 100% Android (Kotlin + Compose + Hilt OU Koin + Retrofit + Room + DataStore + Coroutines + Flow)
- Sem iOS, sem KMP shared
- Squad ou projeto-cliente é Android-only por opção arquitetural (não por restrição técnica)
- Frequentemente projetos enterprise B2B Android-first ou projetos legacy migrando gradualmente

**Posicionamento v1**

- "Funciona out-of-box; cards iOS/KMP que sobram são noise tolerável, não bloqueio"
- `forge init` aplica preset `kmp-mobile` mesmo assim — cards inúteis ficam dormentes (sem signal positivo na detection)
- Carlos não paga custo de pensar em paridade iOS / KMP a cada feature

**Caveats leves**

- `forge init` auto-detection funciona — preset `kmp-mobile` aplica normalmente (não há preset `android-only` dedicado em v1.2; entra na Onda 2 quando demanda concreta justificar)
- Cards `kmp-shared`, `skie-bridge` ficam ociosos no projeto Carlos (sem signal positivo — nenhum módulo `:shared` nem `commonMain` source set)
- Cards `swiftui-screens`, `swiftui-navigation` não ativam (sem signal positivo de iOS — sem `iosApp/` nem `*.xcodeproj`)
- Hilt **não tem card canon em v1.2** (Koin Annotations é o canon mobile por uniformidade KMP) — Carlos pode rodar Hilt via Gap 5 overlay local (`.claude/cards/local/hilt-di/`) sem fork upstream do canon
- Retrofit **já é canon** desde Gap 5 (v1.2.0) — sem caveat de network client

**JTBD herdado da Marina + nuance**

- Mesmo loop de planning + implement (Waves A-E + atomic commits + gates de escopo)
- Carlos não paga custo de pensar em paridade iOS / KMP a cada feature
- Tech-spec renderiza só a layer Android
- Wave C contracts pula `swiftui-screens` e `kmp-shared` por ausência de signal positivo
- Analytics-spec não precisa enumerar eventos iOS (Android-only)

**Roadmap-impact pra Carlos**

- Onda 1 (Autopilot, v1.3-v1.4): Carlos ganha igual que Marina — Apply Mode end-to-end pra `forge implement`
- Onda 2 (Catálogo evolutivo): preset `android-only` dedicado se demanda concreta justificar (não bloqueia v1)
- Hilt como card canon mobile: NÃO no roadmap (Koin Annotations é o canon uniforme; Hilt via Gap 5 permanente)

**Frustrações específicas do Carlos sem forge**

- "Tutoriais Android assumem Hilt; canon mobile assume Koin. Decisão de DI vira religião no time — sem doc canônico do projeto, debate volta a cada feature"
- "Quando o projeto começa a flertar com iOS via WebView ou React Native, a disciplina arquitetural some — não temos vocabulário canônico pra esta transição"

**Critério sucesso pra Carlos**

- Features Android shipam sem fricção de canon mobile assumir KMP
- Cards locais (Gap 5) cobrem Hilt + qualquer outra lib Android-specific quando aplica
- Auto-retro propõe evolutions Android-specific naturalmente (não força sub-agente a inventar paridade iOS)

### Lucas — iOS-only sem KMP

**Diferencial vs Marina**

- Stack 100% iOS / Swift (SwiftUI + Combine + Swift Packages + Alamofire ou URLSession + KeychainAccess + CoreData ou GRDB ou Realm)
- Sem Android, sem KMP
- Squad ou projeto-cliente é iOS-only por opção
- Frequentemente projetos consumer-facing com brand iOS-first, ou projetos onde Android é tratado por squad separada

**Posicionamento v1**

- "Funciona pra você com trabalho manual; v1.x+ entrega UX nativa quando demanda concreta justificar"
- Onda 2 do roadmap-produto (ver [`03-roadmap.md`](03-roadmap.md) §3 quando criado) cobre preset `ios-only` + cards canon iOS standalone

**Caveats v1**

| Aspecto | Estado v1.2 | Comportamento | Workaround |
|---|---|---|---|
| Preset dedicado `ios-only` | ❌ não existe | `forge init` não detecta auto | Manual via `forge reconfigure` |
| Auto-detection em `forge init` | ❌ retorna 0 signals positivos | Sem preset aplicado | Manual via menu |
| Cards canon utilizáveis | ✅ `swiftui-screens`, `swiftui-navigation`, `auth-jwt-bearer`, `crashlytics`, `firebase-storage` | Aplicam-se normalmente | — |
| Cards canon NÃO utilizáveis | ❌ `kmp-shared`, `koin-annotations`, `kotlin-language`, `skie-bridge`, `ktor-client`, `retrofit-client`, `room-database`, `datastore-prefs`, `shared-preferences-prefs` | Não ativam (sem signal) | — |
| Customização pra stack | ✅ Gap 5 cobre — `.claude/cards/local/` | Cards iOS locais (Alamofire, KeychainAccess, etc.) | Caminho oficial |
| Roadmap pra UX nativa | Onda 2 cobre preset `ios-only` | Quando demanda concreta justificar | — |

**JTBD herdado da Marina + nuance**

- Lucas reaproveita 100% da disciplina de planning (Waves A-E rolam normalmente)
- Lucas reaproveita 100% da disciplina de implementação (atomic commits + gates de escopo)
- O custo de v1 é configuração manual inicial via `forge reconfigure` + ausência de cards canon iOS-standalone
- Trabalho extra é one-time setup, não custo recorrente por feature
- Cards locais (Gap 5) cobrem o gap de canon iOS-only até Onda 2 chegar

**Roadmap-impact pra Lucas (mais explícito por ser persona com caveat tabular)**

- Onda 1 (Autopilot, v1.3-v1.4): Lucas ganha como qualquer persona — Apply Mode end-to-end (não específico de plataforma)
- Onda 2 (Catálogo evolutivo, v1.5-v2.0): preset `ios-only` dedicado shippa quando demanda concreta justificar
- Cards canon iOS standalone (sem assumir KMP) também entram na Onda 2
- Anti-roadmap relevante: marketplace pública de cards iOS NÃO entra (viola Decision 22); caminho fica Gap 5 local

**Frustrações específicas do Lucas sem forge**

- "Documentação mobile assume sempre 'Android + iOS via KMP' — pra projeto iOS-only, cards canon servem só metade"
- "Sem preset `ios-only` em v1, fluxo de onboarding com `forge init` exige configuração manual; menos amigável que o caminho default"
- "Cards iOS specifics (Alamofire, KeychainAccess, Realm) precisam ser construídos via Gap 5 sem benchmark canon de referência"

**Critério sucesso pra Lucas**

- Configuração manual one-time via `forge reconfigure` desbloqueia o projeto iOS-only sem fricção recorrente
- Cards locais cobrem stack iOS-native dentro de 1-2 sprints de Gap 5 maduro
- Onda 2 entrega preset `ios-only` quando demanda concreta acumular (squads iOS-only de produção justificam)

### Carolina — Dev iniciante / onboarding

**Diferencial vs Marina**

- 1-3 anos de experiência mobile
- Primeira squad mobile real depois de bootcamp ou estágio
- Aprendendo padrão arquitetural enquanto entrega feature
- Não só "executar tarefa", também "entender por quê o padrão é assim e não outro"
- forge não é só ferramenta de produtividade pra ela — é material didático embutido no fluxo de trabalho

**Contexto de trabalho**

- Squad com pelo menos 1 sênior (Marina ou Bruno)
- Responsabilidade gradual de features pequenas → médias → grandes
- Ramp-up esperado de ~2 meses até produtividade plena sem forge
- Com forge, ramp-up cai pra ~2 semanas

**JTBD diferenciado em relação à Marina**

- Não só "entregar feature" mas TAMBÉM "entender por quê o padrão é assim, não outro"
- Carolina precisa absorver a opinião arquitetural do projeto enquanto contribui
- Sem ferramenta dirigida, esse processo é por osmose lenta de PR review e huddles

**Forge usa também como material didático**

- Templates ensinam estrutura (intake → PRD → screen-analysis → contracts → tech-spec → tasks → readiness; cada artefato com schema documentado em `docs/schemas/*.md`)
- Validators ensinam regras (analytics obrigatório, BDD obrigatório, threat model em features sensíveis; rejeitam com mensagem explicando por quê — não só "fail")
- Cards explicam padrões com `README.md` substantivo por card (não só "use isso", mas "por quê isso e não aquilo" — trade-offs entre alternativas viáveis)
- Persona mentor calmo é didática por design (warm em exploração, firme em gates) — Carolina sente-se mentorada, não auditada
- 3-caminhos canônico é treino de raciocínio (Carolina é forçada a pensar trade-off em cada gate, não só "ok / cancelar"; aprende a articular trade-off arquitetural)

**Frustração sem forge**

- "Squad sênior decide tudo em PR review com comentário de 1 linha; trava o time todo no review, e eu não entendo o porquê da decisão."
- "Cada decisão arquitetural me chega como fato consumado, não como trade-off com alternativas — eu acato sem entender, e replico cego."

**Critério sucesso**

- PRs mergeáveis em <2 semanas após onboarding (vs ~2 meses típicos sem ferramenta dirigida)
- Carolina vira contribuidora produtiva quase imediatamente
- Sênior reduz revisão mecânica pra revisão arquitetural
- Carolina aprende padrão fazendo, não só revisando PR review

**Roadmap-impact pra Carolina**

- Onda 1 (Autopilot): Apply Mode reduz cerimônia mecânica — Carolina pode focar em entender trade-offs em vez de checar mecânica
- Onda 3 (Inteligência adaptativa, v2.x aspiracional): comando `forge ensina <pattern>` (verbo novo Onda 3) — explora cards + decisões com lente didática especificamente desenhada pra ramp-up
- Anti-roadmap relevante: forge NÃO substitui mentor humano (Onda 3 §Anti-feature explícito) — Carolina ainda aprende contexto/cultura via interação com sênior

---

## Camada C — Downstream / read-only

### Patricia — PM / Product Owner

**Posicionamento**

- **NÃO toca código.** Não opera forge diretamente
- Não escreve tech-spec, não roda `forge implement`, não revisa proposed-evolutions
- Persona downstream pura — consumidor do output do engine, não operador
- **Única interação com forge:** `forge status` read-only board

**Único uso de forge**

- `forge status` read-only board — vê quais features estão em planning / implementing / verified / blocked-on-external / deferred / done
- Sem precisar perguntar ao dev (Marina) em standup ou Slack diariamente
- Reduz síndrome de "tá pronto?" recorrente que rouba foco do dev e gera fricção PM-dev

**JTBD principal**

- Visibilidade real-time do estado de cada feature do backlog
- Sem ter que perguntar ao dev em standup ou Slack diariamente

**Frustração sem forge**

- "Standup 9h só pra saber 'tá pronto?'; backlog tem 12 features em estado desconhecido e eu adivinho prioridade no escuro; dev fica frustrado com pergunta repetida"

**Boundary explícito (importante)**

- forge NÃO faz estimativa de tempo
- forge NÃO faz schedule de release
- forge NÃO faz priorização de backlog
- Esses são domínio exclusivo do PM e estão out-of-scope **permanente** conforme `docs/design/00-vision.md` §What feature-forge is NOT
- Patricia ganha **visibility técnica precisa**, não **decision-making automation**
- Ela continua usando Linear / Jira / Confluence pra schedule + priorização + estimativa
- forge complementa com visibilidade técnica precisa em real-time, não substitui a ferramenta de PM
- Tentar expandir forge pra cobrir scheduling violaria a decisão de boundary e arriscaria virar PM-tool genérica (que existe aos montes no mercado)

**Roadmap-impact pra Patricia**

- Onda 2 (Catálogo evolutivo): `forge status --release-q3` ganha filtros temporais e por sprint (Patricia ganha lente filtrada)
- Anti-roadmap relevante: forge NÃO faz estimativa nem priorização (out-of-scope permanente conforme `00-vision.md`)

**O que Patricia vê em `forge status` (output canônico)**

- Lista de features agrupadas por estado (planning / implementing / verified / blocked-on-external / deferred / done)
- Por feature: slug, dono (dev assigned), última atividade (timestamp), próximo gate esperado
- Features `blocked-on-external` mostram ticket externo + integração (Jira / Linear / manual) + data de bloqueio
- Sem estimativa de release, sem priorização, sem schedule — apenas estado técnico real-time

**Critério sucesso pra Patricia**

- Reduz "tá pronto?" em standup pra zero
- Backlog tem 0 features em estado "desconhecido"
- Identificação proativa de blockers externos (deps esperando outro time)

### Diego — Code reviewer humano

**Posicionamento**

- Dev senior que revisa PRs no GitHub / GitLab
- NÃO opera forge diretamente
- Persona downstream — recebe PR criado por dev que rodou `forge implement` localmente

**Interação com forge (indireta)**

- PR chega com diff atômico (1 task = 1 commit)
- Mensagens canônicas (`<tipo>(<escopo>): <descrição>`)
- `allowed_files` respeitado pela task contract (validator `check_files_in_allowed_files` garante hard-fail se sair)
- Contracts + analytics + threat presentes (Wave E garante)
- Diego avalia arquitetura e produto — não compliance mecânico

**Expectativas em PR forge-gerado**

- Escopo respeitado (diff cabe em `allowed_files` declarados na task contract; validator `check_files_in_allowed_files` garante hard-fail se sair)
- Contracts seguidos (BDD bate com analytics-spec; tech-spec bate com tasks; data-contract-spec bate com schema real implementado)
- Analytics / threat-model / regression tests presentes onde aplicável (validator hard-fail em Wave E garante; PR não chega ao Diego sem isso)
- Mensagens de commit canônicas (`<tipo>(<escopo>): <descrição>` + body explicando WHY, não só WHAT)

**JTBD principal**

- Review focal em arquitetura e produto, não em compliance mecânico chato
- Diego quer pegar bug de design, trade-off arquitetural duvidoso, naming inconsistente
- Não console.log esquecido ou BDD ausente

**Frustração sem forge**

- "80% do review é console.log esquecido ou BDD ausente — ruído mecânico que rouba tempo do que importa"
- "Acabo gastando 1h revisando PR pra apontar 5 erros mecânicos e 30s no único trade-off arquitetural real que valeria discussão"

**Critério sucesso**

- Disciplina mecânica passa antes do PR chegar ao Diego (forge garante via `forge verify` cascade + validators em Wave E)
- Review humano dele debruça-se sobre decisão arquitetural, naming, trade-offs de design, edge cases não cobertos
- Reduz tempo médio de review e aumenta qualidade do feedback recebido pela Marina / Carolina

**Roadmap-impact pra Diego**

- Onda 1 (Autopilot): Apply Mode + atomic commits chegando ao PR — Diego ganha PRs mais clean direto
- Onda 3 (Inteligência adaptativa): proposed-evolutions ficam mais ricas (L3 cross-project signals) — Diego pode aceitar/rejeitar com mais contexto histórico
- Anti-roadmap relevante: forge NÃO automatiza veredito final de review (Diego decide; engine detecta violações mecânicas só)
- Out-of-scope explícito: integração hook PR-side (GitHub Action que comenta forge findings no PR) está em Open Questions §13 Q3 do 00-prd — não no roadmap v1.x

**O que Diego espera ver num PR forge-gerado (checklist mental do review)**

- Commit history atômico (1 task = 1 commit, 1 conceito = 1 commit body)
- Commit messages canônicas: `<tipo>(<escopo>): <descrição>` + body com WHY
- Diff dentro de `allowed_files` declarados (sem refactor "while I'm here")
- BDD + analytics + threat (quando aplica) presentes no PR description ou no diff
- Tests regressão presentes em bugfix; no-behavior-change attestation presente em refactor

**Critério sucesso pra Diego**

- 80% do review é arquitetura/produto (não compliance mecânico)
- Tempo médio de review cai 50% vs PRs não forge-gerados
- Diego pode dar +1 confiável sem rastreamento mecânico exaustivo

---

## Notas finais de design

**Por que estas 8 personas e não mais ou menos?**

8 é o número que cobre o espaço de uso real do feature-forge sem inflar com personas que não impactam decisão de produto. Marina ancora; Bruno é decisor de adopt; Sub-agente Claude é o consumidor técnico do output. Camada B (Carlos / Lucas / Carolina) cobre os 3 desvios mais comuns do perfil de Marina (plataforma reduzida, plataforma diferente, experiência reduzida). Camada C (Patricia / Diego) cobre os 2 consumidores downstream que justificam interfaces específicas (status board e mensagens de commit canônicas).

Adicionar uma 9ª persona "Henrique - QA mobile" foi considerado e rejeitado: QA não opera forge nem consome output específico (consome PR como qualquer reviewer, papel parcial coberto por Diego). Adicionar uma 10ª "Roberta - dev backend que apoia mobile" também foi rejeitada: forge é mobile-focused; backend dev não é audiência primária nem secundária.

**Anti-personas vivem em [`00-prd.md`](00-prd.md) §9**

Personas neste doc são "pra quem o forge faz sentido". Anti-personas (Flutter / React Native / Backend-only / PM operando direto / Squad rejeitando disciplina / Java-only sem Kotlin) vivem em [`00-prd.md`](00-prd.md) §9 quando criado — separar é proposital pra não diluir o foco deste doc.

**Como esta lista evolui**

Personas não mudam por capricho. Adição ou modificação substantiva requer:

- Brainstorming explícito (skill `superpowers:brainstorming` com mantenedor)
- Atualização do PRD (`docs/product/00-prd.md` §5) e dos cenários referentes (`docs/product/02-scenarios.md`)
- Entrada no `CHANGELOG.md` sob `### Changed` (ou `### Added` se persona nova)
- Cross-ref no `docs/design/08-session-handoff.md` se afetar estado-base

Personas têm peso load-bearing no design — toda decisão de produto e UX assume um conjunto fixo de arquétipos. Drift silencioso enfraquece o vocabulário compartilhado entre mantenedor + Claude futuro.

**Mapeamento rápido pra navegação**

| Persona | Camada | Opera forge? | Cenários onde aparece |
|---|---|---|---|
| Marina | A | Sim (primária) | C2, C3, C4, C5, C6 |
| Bruno | A | Sim (decisor adopt) | C1, C6 |
| Sub-agente Claude | A | É operado via context-pack | Todos (dispatchada por wave) |
| Carlos | B | Sim (variante Marina) | Derivado de C2-C5 |
| Lucas | B | Sim (variante Marina) | Derivado de C2-C5 + futuras Onda 2 |
| Carolina | B | Sim (variante Marina) | Derivado de C2 com ramp-up |
| Patricia | C | Não — read-only via `forge status` | Adjacente a C1-C6 (visibilidade) |
| Diego | C | Não — recebe PR | Adjacente a C2-C6 (downstream do PR) |

Detalhes dos cenários em [`02-scenarios.md`](02-scenarios.md) quando criado.

**Convenção de naming reforçada**

Reforço final pra evitar drift silencioso: os 8 nomes canônicos (Marina, Bruno, Sub-agente Claude, Carlos, Lucas, Carolina, Patricia, Diego) NÃO devem ser substituídos por sinônimos genéricos ("a dev primária", "o tech lead", "o sub-agente") em prosa de docs derivados. Usa o nome canônico — é parte do vocabulário compartilhado entre mantenedor + Claude futuro e perder o nome perde a especificidade da persona.

Caso surja necessidade de persona nova (cenário B nunca-antes-considerado), abre via brainstorming explícito + write-up em `04-pending.md` antes de mexer aqui. Personas têm peso load-bearing — toda decisão de produto e UX assume um conjunto fixo de arquétipos. Drift silencioso enfraquece o vocabulário compartilhado.
