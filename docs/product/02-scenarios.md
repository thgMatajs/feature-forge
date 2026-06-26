# Cenários de uso do feature-forge

> **Cross-ref:** Este doc é referenciado por [`00-prd.md`](00-prd.md) §6. Personas citadas vivem em [`01-personas.md`](01-personas.md). Cada cenário cita roteiros UX em [`docs/ux/`](../ux/) e disciplinas em [`docs/design/07-discipline.md`](../design/07-discipline.md) quando relevante.

6 user journeys end-to-end, cada um seguindo o mesmo schema canônico. O propósito não é manual de uso (esses vivem em `docs/ux/` por comando específico, mais detalhados que o cenário aqui); é mostrar como o engine se conecta a uma persona específica num momento concreto de trabalho real. Cada cenário tem persona ancorada, estado inicial concreto, sequência de passos verificável, e outcome mensurável em tempo ou retrabalho evitado.

Schema canônico:

- **Persona principal:** quem dirige a sessão. Sempre uma das 8 personas catalogadas em [`01-personas.md`](01-personas.md).
- **Estado inicial:** o que existe no projeto + na cabeça da persona antes do primeiro comando. Inclui contexto técnico (cards aplicados, state L1/L2 atual) + contexto humano (mood, deadline implícito, pressão externa).
- **Estado final:** o que existe depois — artefatos persistidos, commits no histórico, state em L1/L2 atualizado, decisões registradas.
- **Passos:** numerados 1-N, ação concreta + outcome verificável de cada step. Quando relevante, sub-bullets nomeados destrincham detalhes operacionais.
- **Outcome:** uma frase ou parágrafo curto sobre o valor entregue — tempo poupado, retrabalho evitado, knowledge acumulado em L2, drift cross-feature reduzido.
- **Cross-ref:** `docs/ux/*.md` (roteiros operacionais detalhados), `docs/design/*.md` (decisões e disciplinas que ancoram o comportamento), `docs/lifecycle/*.md` (dataflow), `docs/schemas/*.md` (artefatos validados), `agents/*.md` (prompts canônicos).

Cenários estão numerados C1-C6 e referenciados nominalmente em [`01-personas.md`](01-personas.md) (seção "Cenários onde X é persona principal" por persona) e em [`00-prd.md`](00-prd.md) §6 (resumo de 1-linha por cenário com link de volta pra cá). Decisão deliberada: cenários não tentam cobrir 100% do espaço de uso — cobrem os 6 momentos canônicos onde o engine tem mais valor agregado mensurável.

---

## C1 — Brownfield init com reuse-intelligence

**Persona principal:** Bruno (tech lead).

**Persona secundária:** Marina, entrando no dia seguinte pra fazer triage das proposed-evolutions geradas pelo scan.

**Estado inicial**

- Projeto KMP existente em produção há ~3 anos.
- ~150 features históricas shipadas com sucesso.
- Helpers duplicados conhecidos pela squad mas nunca consolidados:
  - `validateName()` em 15 lugares
  - `formatPrice()` em 8 lugares
  - `parseISO()` em 6 lugares
- Stack: Kotlin + KMP shared + Compose + SwiftUI via expects + Koin Annotations + Retrofit + Room + DataStore.
- Sem disciplina forge instalada — `.claude/` ainda não existe no repo.
- Bruno acabou de aprovar adopt da skill após validação em PoC isolado num projeto menor.
- Mood: cauteloso. Bruno não quer impor disciplina mecânica que desacelera a squad — quer ferramenta que sirva, não que estorve.

**Estado final**

- `.claude/` inicializado com `workflow-config.yaml` válido.
- Preset `kmp-mobile` aplicado por detecção automática via signals positivos.
- Cards canon ativados conforme stack real (10 cards principais + 4 backend-candidates dormentes).
- L2 (memory project-level) populada com signals do reuse-intelligence scan.
- `proposed-evolutions.yaml` gerado em `.claude/memory/L2/` com 47 findings em 6 categorias.
- Marina dia seguinte fez triage via `forge evolve`: 30 accept, 12 reject, 5 defer.
- `.claude/cards/local/` ainda vazio — canon cobriu, overlay não foi necessário desta vez.
- Bruno confiante de que o investimento de adopt vai retornar via triage automatizada de duplicação.

**Passos**

1. **Run init.** Bruno roda `forge init` na raiz do `projeto-x`. Auto-detection escaneia o repositório:
   - lê `settings.gradle.kts` e detecta módulos `:shared`, `:androidApp`
   - encontra `iosApp/` com `*.xcodeproj` válido
   - identifica `commonMain` source set ativo
   - confirma signals positivos pra `kmp-mobile`
   - confirma REST como backend ativo via dependência declarada de Retrofit
   - confirma ausência de GraphQL (sem Apollo no classpath)
2. **Confirma preset interativo.** Conductor abre o menu interativo (zero flags — Decision 10 LOCKED). Apresenta o preset detectado + cards candidates. Bruno confirma `kmp-mobile` + REST. Conductor aplica os cards canon: `kmp-shared`, `kotlin-language`, `koin-annotations`, `compose-screens`, `compose-navigation`, `swiftui-screens`, `swiftui-navigation`, `retrofit-client`, `room-database`, `datastore-prefs`. Adicionalmente registra 4 backend-candidates como dormentes (Firebase, GraphQL, Apollo, gRPC) — disponíveis se demanda surgir, mas não ativam sem signal positivo.
3. **Step 11.5 — scan reuse-intelligence.** Init dispara o scan logo após aplicação dos cards. Engine percorre o catálogo de queries Q12-Q17 sobre a base de código existente e emite 47 findings agrupados em 6 categorias canônicas:
   - **consolidate-within-module** (8 findings): helpers duplicados dentro do mesmo módulo
   - **promote-to-shared** (15 findings): helpers duplicados cross-platform candidatos a virar shared
   - **redundant-platform** (4 findings): código repetido entre Android e iOS sem razão técnica
   - **near-duplicate** (12 findings): 80% similaridade com drift cosmético
   - **kmp-migration-candidate** (6 findings): código platform-specific migrável pra shared
   - **consolidate-ts-helpers** (2 findings): helpers de teste duplicados em fixtures
4. **Revisão inline sem veredito.** Bruno revisa uma amostragem inline (5-6 findings de categorias diferentes) sem aceitar ou rejeitar — só registra que viu o output. O caminho oficial é triage offline em `forge evolve`, não decisão na hora; init não força veredito imediato. Conductor reforça: "Revise com calma via `forge evolve` quando estiver pronto. Nada decidido aqui."
5. **Persistência da proposta.** Init grava `proposed-evolutions.yaml` em `.claude/memory/L2/` com os 47 findings. Cada finding tem fingerprint canônico sha256 sobre forma estável (`{kind, normalized-description, sorted-provenance-set}`) conforme `docs/design/07-discipline.md` §6 — o fingerprint protege contra re-propor a mesma coisa em scans futuros. Sai com mensagem mentor calmo: "47 reuse opportunities registradas pra triage. Roda `forge evolve` quando estiver pronto."
6. **Triage no dia seguinte.** Marina abre sessão Claude Code nova, roda `forge evolve`. Engine carrega as 47 propostas, agrupa por categoria, mostra contexto de cada (arquivos afetados, snippet do código duplicado, sugestão de consolidação, fingerprint). Marina decide:
   - **30 accept** — incluem promote-to-shared do `validateName` (será C6 em detalhe) e 4 outros helpers consolidados
   - **12 reject** com motivo registrado — "intencional" (drift proposital pra performance), "near-dup mas semântica difere" (mesmo nome, comportamento diferente)
   - **5 defer** — "decidir depois de feature 19 pra ter mais contexto"
   - Fingerprints dos 12 rejeitados ficam registrados em `.claude/memory/L2/rejected-fingerprints.yaml` — próximo scan não vai re-propor a mesma coisa silenciosamente

**Outcome**

Squad sai de "patterns repetidos como folclore oral" pra "30 reuse opportunities prontas pra puxar em PRs separados, com 5 deferred sem perder rastreabilidade e 12 rejeitadas com motivo versionado". Mudanças concretas mensuráveis no estado do projeto:

- Bruno reduz custo de PR-review-eterno-reescrevendo-as-mesmas-regras pra triage semanal de ~30min via `forge evolve`.
- L2 acumula learnings sem dev escrever doc manual — `proposed-evolutions.yaml` é o registro persistente.
- Próximo `forge init` em projeto irmão da empresa vai começar com baseline conceitual de 6 categorias canônicas — não é primeira-vez-toda-vez.
- Fingerprints dos 12 rejeitados protegem contra "engine insiste em propor o que já foi recusado" — ruído auto-silenciado.
- Helpers duplicados (validateName, formatPrice, parseISO) entram no radar de consolidação cross-feature; sem o scan, continuariam invisíveis até causar bug visível.

Este é o caminho oficial pra abrir disciplina forge em projeto brownfield — não há atalho "skip reuse-intel scan" porque o valor da descoberta inicial paga o overhead de Step 11.5 mesmo no primeiro uso.

**Cross-ref**

- [`docs/ux/forge-init-roteiro.md`](../ux/forge-init-roteiro.md) Cenas 5.5 + 5.6 cobrem o scan reuse-intel em detalhe operacional, incluindo o cabeçalho exato do menu interativo e formato do `proposed-evolutions.yaml`.
- [`docs/lifecycle/memory-and-graph.md`](../lifecycle/memory-and-graph.md) explica L1/L2/L3 + as 17 graph queries que alimentam o scan; Q12-Q17 são as relevantes pra reuse-intel; Q1-Q11 cobrem outras lentes (capabilities, cards, etc.).
- [`docs/design/07-discipline.md`](../design/07-discipline.md) §6 cobre o fingerprint anti-redundância usado pra silenciar propostas repetidas e a stability guarantee do hash canônico (mudanças em fingerprint só ocorrem quando conteúdo/evidência mudam, não cosmeticamente).

---

## C2 — Feature product nova end-to-end

**Persona principal:** Marina (mobile dev solo KMP/Android).

**Personas adjacentes:** Patricia (PM, passou o ticket); Diego (code reviewer, recebe o PR no fim do dia).

**Estado inicial**

- Squad em sprint normal, terça-feira de manhã.
- Ticket IN-42100 aberto pelo PM: "Lembrete de rega de planta".
- Patricia passou no thread do ticket:
  - 2 acceptance criteria em formato livre
  - 1 screenshot do Figma da tela proposta
  - 1 link pra discovery doc no Confluence (read-only)
- Sem PRD escrito, sem screen-analysis, sem tech-spec — só o ticket e o desenho.
- `.planning/lembrete-rega/` ainda não existe.
- Marina tem disciplina forge instalada no projeto há 3 meses, está confortável com Waves A-E.
- Mood: foco — quer entregar até fim do dia.

**Estado final**

- Feature `lembrete-rega` shipada em Android + iOS + KMP shared.
- 8 commits atômicos no histórico, mensagens canônicas no formato `<tipo>(<escopo>): <descrição>`.
- Artefatos completos em `.planning/lembrete-rega/`:
  - PRD, screen-analysis, BDD, analytics-spec, threat-model
  - tech-spec
  - 8 task-contracts com `allowed_files` declarados
- L1 status final: `state=done`, `shipped-at` timestamped, `subtype=product`.
- 3 evolutions L2 propostas pelo auto-retro; Marina aceitou 2 e rejeitou 1 com motivo registrado.
- PR mergeado com Diego dando +1 focado em arquitetura (WorkManager vs AlarmManager), não em compliance mecânico.

**Passos**

1. **Wave A — intake.** Marina roda `forge plan lembrete-rega` às 9:15. Conductor em Cena 2.5 analisa o slug + descrição do ticket pra propor subtype:
   - slug `lembrete-rega` — sem prefix `IN-` (não é ticket-pattern bugfix)
   - keywords da descrição PM — "feature de lembrete", "agendar", "notificação"
   - heurísticas product-shaped — substantivo + verbo, indica nova capacidade
   - Conductor propõe `subtype=product`. Marina confirma (poderia overridar pra `refactor` ou `chore` se a descrição enganasse, mas confirma).
   - Sub-agente renderiza `feature-intake-product.template.md`. Em <5min Marina preenche:
     - **user value**: "planta-owner não esquece de regar"
     - **scope**: "criar lembrete por intervalo de dias por planta cadastrada"
     - **persona alvo**: planta-owner casual (single-device user, sem multi-tenant)
     - **out-of-scope explícito**: lembrete por hora-do-dia específica (será extension futura — vide C5)
     - **out-of-scope explícito**: sincronização entre devices (single-device por enquanto)
     - **out-of-scope explícito**: lembrete por geolocalização (não pedido pelo PM)
   - Validator de presença passa silenciosamente.
2. **Wave B — PRD + screen-analysis.** Conductor pergunta:

   > "A feature envolve mudança de UI? (Figma anexado? estados nuns conhecidos?)"

   Marina responde "sim, Figma anexado pelo PM". Cola descrição PM + link do screenshot do Figma. Sub-agente Claude renderiza o PRD com base no intake + descrição PM, enquanto screen-analysis-agent em paralelo enumera os estados canônicos da tela proposta:
   - **loading** — busca da lista de plantas do repository
   - **empty** — sem plantas cadastradas (CTA pra cadastrar nova planta + ilustração)
   - **success** — lista com toggle de lembrete por planta + label "rega a cada N dias"
   - **error** — falha ao buscar do repository (mostrar retry + mensagem amigável)
   - **edge cases identificados pela agent**:
     - planta sem nome (não deveria ocorrer, mas defensive)
     - frequência negativa ou zero (validação rejeita)
     - notificação bloqueada pelo sistema operacional (fallback: in-app reminder)
     - planta deletada enquanto lembrete ativo (cleanup pendente)
   - Marina valida cada estado e ajusta wording de 2 deles (empty e error) pra alinhar com voz UX já estabelecida no app (não tom corporativo, não emoji decorativo).
3. **Wave C — contracts.** 4 artefatos preenchidos em paralelo conforme `docs/design/07-discipline.md` §2:
   - **BDD**: 3 scenarios Given-When-Then cobrindo happy path + estado vazio + notificação bloqueada
   - **analytics-spec**: 4 eventos com naming canônico (`lembrete_criado`, `lembrete_disparado`, `lembrete_visto`, `lembrete_dispensado`)
   - **threat-model**: analisado — não há dados sensíveis novos (sem PII além do nome da planta, que é local), só lembrete agendado no device
   - **data-contract-spec**: entidade `Lembrete(plantaId, intervaloDias, ultimoDisparoAt)` + relação 1:1 com `Planta` existente
   - Validators rodam silenciosamente em cascade fail-fast; nenhum falha.
4. **Wave D — tech-spec + tasks.** Tech-spec-agent renderiza a arquitetura em camadas:
   - **UI Compose** (Android) — toggle por item de lista + edit dialog pra intervalo
   - **UI SwiftUI** (iOS) — equivalente via expects
   - **ViewModel KMP shared** — `LembreteListViewModel` em commonMain
   - **Repository KMP shared** — abstração sobre Room (Android) + CoreData via expects (iOS)
   - **Scheduler** — WorkManager (Android) + BGTaskScheduler (iOS)
   - Task-contract-writer quebra em 8 tasks. Cada task com `allowed_files` declarados por arquivo. Nenhuma task cruza mais de 4 arquivos. Marina vê o breakdown, confirma.
5. **Wave E — readiness.** Readiness-reviewer-agent passa pelo checklist canônico:
   - artefatos completos? ✅
   - contracts coerentes entre si (BDD ↔ analytics-spec ↔ data-contract)? ✅
   - tasks com `allowed_files` declarados? ✅
   - validators de Wave E verde? ✅
   - dependencies externas declaradas (nenhuma — feature local)? ✅
   - Veredito: `readiness=ready` às 9:29. Tempo total Wave A-E: 14min.
6. **Implement.** Marina roda `forge implement lembrete-rega` às 10:45 (após coffee + standup). Conductor dispatcha por task em sequência:
   - cada task aplica diff dentro do `allowed_files` declarado na task-contract
   - cada task roda `forge verify` parcial (subset dos 15 validators relevantes pra os arquivos tocados)
   - cada task commita atomic com mensagem canônica `feat(lembrete-rega): <descrição>` + body explicando WHY
   - validators param a task se cascade falhar — fail-fast por default (Decision 23 LOCKED)
   - **Gate de escopo trava 1 tentativa de refactor lateral.** Na task 4, Marina ia renomear variável local em arquivo não declarado nos `allowed_files` (`PlantaListAdapter.kt` em vez de só `LembreteRepository.kt`). Sub-agente apresenta o 3-caminhos canônico:
     - **(1) fix forward** — adiciona `PlantaListAdapter.kt` aos allowed_files via reconfigure inline (não recomendado, expande escopo)
     - **(2) revert** — desfaz a edição e mantém só os files declarados
     - **(3) split** — abre task separada pra rename, deixa o current task focado
     - Marina escolhe (3) split. Conductor cria task 4.5 pendente; current task task 4 segue limpo.
7. **Verify final.** Após task 8, Marina roda `forge verify` global. Cascade dos 15 validators executa em sequência, fail-fast por default conforme Decision 23. Cascade verde em ~2min. Tempo total implement: 3h45min (terminou ~14:30).
8. **Auto-retro.** Verify verde dispara auto-retro automaticamente. Retrospective-agent analisa o histórico de commits + diffs + tempo por task + decisões tomadas durante Wave B-D e propõe 3 evolutions L2:
   - **(a)** padrão de naming pra eventos analytics em features de lembrete (prefix `lembrete_` + verbo no particípio)
   - **(b)** convenção de screen-state pra empty + loading reaproveitada em outras features futuras (componente compartilhável)
   - **(c)** addition no prompt do screen-analysis-agent pra perguntar sobre permissões de notificação proativamente
9. **Evolve triage.** Marina abre `forge evolve` no fim do dia (15h). Revisa as 3 propostas:
   - **(a) Aceita** — naming pattern entra em `proposed-evolutions.yaml` aprovado e propaga pra L2; próxima feature de lembrete vai herdar
   - **(b) Aceita** — convenção de screen-state idem
   - **(c) Rejeita** com motivo registrado: "perguntar proativamente sobre permissões vai criar fricção no caso geral em features que não usam notificação; deixa pra Onda 3 quando engine puder detectar via card automático"
   - Fingerprint da rejeitada (c) fica gravada; auto-retro futuro não vai re-propor sem mudança real no contexto.
10. **PR + merge.** Marina abre PR no GitHub. Diego (code reviewer downstream) revisa em ~20min. Foca em decisão arquitetural — "por que WorkManager e não AlarmManager?" Marina justifica em comment: WorkManager dá retry policy + battery-aware scheduling + survives reboot, AlarmManager exige permissões adicionais Android 12+. Compliance mecânico já passou (validators garantiram BDD + analytics + threat presentes). Diego dá +1 com 1 sugestão de naming, Marina aplica, merge.

**Outcome**

~15min de Wave A-E + ~4h de implement = feature shipada com analytics, threat, BDD e regression tests em ordem. Componentes mensuráveis do valor entregue:

- **Disciplina não sacrificada na correria** — sem "esqueci BDD", sem "deixei analytics pra depois", sem "threat-model fica pra depois quando der tempo". Validators e cascade fail-fast garantem que cada contract está presente antes do PR sair.
- **L2 acumula patterns reusáveis sem doc manual** — 2 das 3 evolutions propostas pelo auto-retro foram aceitas e propagam pra próximas features automaticamente.
- **Próxima feature lembrete-* começa mais rápida** — promessa central do PRD em [`00-prd.md`](00-prd.md) §2 sobre "feature N+30 mais rápida que feature N". Vide C5 sobre `lembrete-rega-hora` derivada desta mesma feature, custando ~3h em vez de ~5h.
- **Review focal em arquitetura, não compliance** — Diego revisou em ~20min em vez de ~60min porque compliance mecânico já estava verificado pelos validators. Trade-off WorkManager vs AlarmManager virou o foco real do review.
- **Ceremony proporcional ao tamanho** — Waves A-E somam <15min num caso normal; disciplina mecânica não atrasa, substitui retrabalho que viria depois (debug de BDD ausente em produção, audit de analytics faltando, threat post-mortem em incidente).

**Cross-ref**

- [`docs/ux/forge-plan-roteiro.md`](../ux/forge-plan-roteiro.md) cobre Waves A-E em detalhe operacional, com transcrições de prompts do conductor por wave.
- [`docs/ux/forge-implement-roteiro.md`](../ux/forge-implement-roteiro.md) cobre o loop task-por-task + atomic commits + gates de escopo + 3-caminhos em violation.
- [`docs/design/07-discipline.md`](../design/07-discipline.md) cobre a cascade dos 15 validators (§2), o pattern 3-caminhos em gates (§1), e o auto-retro pós-verify (§5).

---

## C3 — Bugfix com ticket IN-37234

**Persona principal:** Marina em modo P0 (stress, deadline implícito de horas — Crashlytics alarme ativo).

**Estado inicial**

- Crashlytics alerta às 9h: 12% das sessions Android 14 estão crashando nas últimas 6h.
- Ticket IN-37234 aberto urgente pelo PM (Patricia) com flag P0.
- Stack trace aponta `BonsaiForm.validateName()` — gera `NullPointerException` quando o usuário cola valor com whitespace só (input `" "` passa null check mas vira string vazia após trim implícito no serializer downstream, que então quebra).
- Squad inteira no Slack pedindo update; pressão de hotfix antes do almoço.
- Marina sabe que sem ferramenta dirigida ela pula PRD e foca só no fix — sem regression test, e o mesmo bug volta semanas depois quando alguém esquece a convenção informal de trim.
- Disciplina forge já está instalada no projeto; Marina tem acesso a `forge plan IN-37234`.

**Estado final**

- Fix aplicado e mergeado em <30min do ticket aberto ao PR aprovado.
- Regression test obrigatório presente (validator hard-fail garantiu — `subtype=bugfix` exige `tests/` no diff final).
- L2 atualizado com pattern canônico "trim() em validação de nome" + fingerprint sha256 estável.
- 5-whys retro registrado em L2 — causa raiz mapeada além do sintoma.
- Bug sem caminho de volta silencioso — qualquer regressão futura é pega no commit.
- Crashlytics rate cai pra 0% Android 14 na próxima release rollout dentro de 4h após o merge.

**Passos**

1. **Detect subtype.** Marina roda `forge plan IN-37234` às 9:08. Conductor em Cena 2.5 analisa o slug e detecta múltiplos signals fortes convergindo pra `subtype=bugfix`:
   - prefix `IN-` no slug é padrão de ticket-pattern (heurística canônica do canon de tickets internos da empresa)
   - keywords nas notes anexas do ticket — "crashing", "Android 14", "NullPointerException", "12% sessions"
   - severity P0 marcada no ticket pelo PM
   - stack trace anexo (mais signal de bugfix vs feature nova)
   - Conductor apresenta:

   > "Slug `IN-37234` matcha ticket-pattern. Keywords + severity sugerem bugfix. Proponho `subtype=bugfix`. Confirma? (alternativa: `product`, `refactor`, `chore`)"

   Marina confirma — não vai rodar fluxo product completo em P0 stress, e os signals batem com a realidade. State L1 grava `subtype=bugfix`.
2. **Wave B sub-question.** Conductor pergunta: "envolve mudança de UI?" Marina responde "não, é lógica de validação pura, nada visual muda do ponto de vista do usuário". Sub-agente registra `wave_b_required=false` em L1. Esse flag economiza Wave B inteira (PRD + screen-analysis) que seria irrelevante pra bugfix de validação pura. Decisão registrada em L1 status pra auditoria.
3. **Wave A intake-bugfix.** Sub-agente renderiza `feature-intake-bugfix.template.md` — formato bugfix dedicado, não o template product completo. Marina preenche em <3min:
   - **Reprodução**: passos exatos pra disparar o crash (1. abre BonsaiForm, 2. cola " " no campo name, 3. clica salvar, 4. crash)
   - **Expected vs actual**: esperado — validação falha graciosamente com mensagem "nome obrigatório"; atual — NPE no LoggerLib downstream
   - **Root-cause hypothesis**: trim ausente — input " " passa null check (string não é null), mas vira string vazia após trim no serializer, que então tenta indexar `[0]` e quebra
   - **Risk level**: P0 confirmado (12% sessions Android 14)
   - **Validation strategy**: regression test com 3 inputs de whitespace
4. **Wave C-D stripped.** Conductor renderiza tech-spec stripped (formato bugfix — sem arquitetura completa, só descrição do fix + área de impacto) + 2 tasks dedicadas:
   - **Task 1 — fix**: aplicar `String.trim()` antes do null check; `allowed_files: [src/.../BonsaiForm.kt]`
   - **Task 2 — regression test**: 3 cases cobrindo whitespace-only / leading-trailing / empty; `allowed_files: [src/.../BonsaiFormTest.kt]`
   - Sem PRD, sem screen-analysis (Wave B skipada), sem analytics-spec (não há eventos novos), sem threat-model (não há superfície de ataque nova).
5. **Implement task 1 — fix.** Marina aplica `String.trim()` antes do null check em `BonsaiForm.validateName()`. Diff cabe em 1 arquivo (`BonsaiForm.kt`). Diff de 3 linhas. Commit atômico canônico: `fix(bonsai-form): trim() input antes do null check (IN-37234)`.
6. **Implement task 2 — regression test.** Marina escreve 3 cases em `BonsaiFormTest.kt`:
   - `validateName(" ")` → retorna `ValidationResult.NameRequired` (não NPE)
   - `validateName("  John  ")` → retorna `ValidationResult.Valid("John")` (trimma extremos, preserva conteúdo)
   - `validateName("")` → retorna `ValidationResult.NameRequired`
   - Roda local — passa. Tenta commit. O validator de regression-test obrigatório (hard-fail em `subtype=bugfix` quando diff não inclui arquivo `tests/`) seria acionado se o teste estivesse ausente — neste caso passa porque o teste está presente. Commit atômico: `test(bonsai-form): regression IN-37234 — input com whitespace`.
7. **Verify.** Marina roda `forge verify`. Cascade dos 15 validators executa fail-fast; verde em ~90s. PR aberto às 9:32.
8. **Auto-retro 5-whys.** Verify verde dispara retrospective-agent em modo bugfix (5-whys, não retro completa product que rodaria em C2). Análise canônica em cascata:
   - **Por quê NPE?** — trim faltava antes do null check em `BonsaiForm.validateName()`
   - **Por quê faltava?** — convenção informal "fazer trim no caller" — nunca foi documentada como pattern do projeto
   - **Por quê informal?** — sem card canônico de validação de input string no catálogo mobile
   - **Por quê sem card?** — gap de canon mobile; validação de input string é assumida implicitamente sem detalhe específico
   - **Por quê não foi pego antes?** — sem regression test no commit original que introduziu `validateName` (commit de ~6 meses atrás)
   - Retro propõe evolution canônica:

   > "Adicionar pattern 'trim() canônico em validação de nome' em L2. Aplicar globalmente em features de cadastro futuras via card-local. Fingerprint sha256 estável."

   Marina aceita rápido via `forge evolve` antes de fechar o ticket — pattern fica registrado no canon do projeto. Próxima feature que tocar validação de nome herda o pattern automaticamente (vide C6 sobre validateName consolidado em :shared:core:validation).

**Outcome**

~25min ticket-aberto → PR-mergeado vs ~60min se Marina rodasse fluxo product completo. Componentes do valor entregue:

- **Velocidade preservada sem sacrifício de rigor** — Waves B + irrelevantes skipadas via `wave_b_required=false`; só intake-bugfix + 2 tasks operacionais. Stripped sem perder o essencial.
- **Regression test obrigatório** — validator hard-fail seria acionado se ausente. Bug não volta silenciosamente daqui a 2 sprints (cobertura cobrindo as 3 variantes de whitespace).
- **Retro evolui o canon sem doc manual** — pattern "trim() em validação de nome" entra em L2 com fingerprint sha256 estável; próxima feature que precisar de validateName herda automaticamente.
- **Disciplina mecânica não sacrificada em P0 stress** — engine torna o caminho rápido sem perder rigor. Marina perdeu menos tempo em ceremony do que perderia debuggando o mesmo NPE daqui a 3 meses.
- **Auditoria preservada** — todos os artefatos (intake-bugfix, tech-spec stripped, 2 task-contracts, 5-whys retro) ficam em L1 + L2 versionados. Auditor futuro consegue reconstruir por quê foi fixado assim.

**Cross-ref**

- [`docs/design/04-pending.md`](../design/04-pending.md) §Gap 1 documenta o subtype=bugfix completo com 9 sub-itens (detection, intake template, validators, retro mode).
- [`agents/planning-conductor.md`](../../agents/planning-conductor.md) cobre a detecção de subtype em Cena 2.5 + sub-question Wave B + critérios de skip de Waves não-aplicáveis.
- [`docs/design/07-discipline.md`](../design/07-discipline.md) cobre auto-retro 5-whys em modo bugfix (vs retro completa product) e o validator de regression-test obrigatório.

---

## C4 — Retomar trabalho pausado

**Persona principal:** Marina em cenário cold-start (sessão Claude Code zerada após dia anterior interrompido por Ctrl+C às 18h).

**Estado inicial**

- Wave D da feature `agenda-poda` terminou ontem (quarta) 18h.
- Marina deu Ctrl+C antes de rodar Wave E porque o dia acabou — compromisso fora do trabalho.
- Estado persistido em L1 (`.planning/agenda-poda/status.json`):
  - `state=deferred`
  - `subtype=product`
  - `last-wave=D`
  - `wave-a-done=true` (timestamp ontem 9:30)
  - `wave-b-done=true` (timestamp ontem 11:15)
  - `wave-c-done=true` (timestamp ontem 14:00)
  - `wave-d-done=true` (timestamp ontem 17:45)
  - `wave-e-pending=true`
  - timestamps por wave preservados pra auditoria
- Artefatos completos persistidos em disco (não voláteis):
  - `PRD.md`, `screen-analysis.md`, `bdd.md`, `analytics-spec.yaml`, `threat-model.md`, `tech-spec.md`, 6 `task-contracts/*.yaml`
- Sessão Claude Code de ontem encerrada normalmente — contexto não persiste entre sessões.
- Hoje (quinta) 9h, sessão nova — Claude não tem memória da conversa de ontem.
- Marina lembra que era `agenda-poda` mas não lembra exatamente os detalhes do tech-spec — qual era o trigger? quais entities? que cards aplicaram? que decisão tomei em Wave C sobre threat-model?
- Mood: leve ansiedade do cold-start. Marina confia no engine mas tem que provar a si mesma que nada se perdeu.

**Estado final**

- Sessão retoma `agenda-poda` exatamente do ponto de parada (Wave E pendente).
- Wave E roda sem reescrever Waves A-D — todos os artefatos preservados intactos em disco.
- Marina segue pra `forge implement agenda-poda` no mesmo dia, sem retrabalho mecânico.
- Zero "qual era mesmo o contract da analytics?".
- State transiciona suavemente `deferred → planning(ready) → implementing` sem fricção.
- Tempo total de retomada: ~5min (readiness review + consulta visual).

**Passos**

1. **Cold-start.** Marina abre sessão Claude Code nova hoje (quinta) 9h. Contexto zerado — Claude não lembra de ontem. Marina precisa orientar a sessão sem assumir que o engine sabe onde parou. Ela tem 2 opções mentais: rodar Wave A do zero (perde 1h) ou usar o status board pra ver o que existe. Ferramenta dirigida torna a segunda opção óbvia.
2. **Status board.** Roda `forge status`. Engine lê `.claude/forge/state/lifecycle/` (todos os slugs em estado não-done) + `.claude/memory/L2-project.yaml` (config + cards merged) e renderiza o board agrupado por estado:

   ```
   planning        (vazio)
   implementing    (vazio)
   verified        (vazio)
   blocked-on-external  (vazio)
   deferred        agenda-poda — última atividade 2026-06-03 17:45, último gate wave-d-done
   done            [lista das features históricas, 18 entries]
   ```

   Marina vê que tem trabalho parado, não está começando do zero. Saber visualmente o board reduz ansiedade do cold-start. Patricia (PM) também consulta este board read-only quando precisa do estado real do backlog (vide [`01-personas.md`](01-personas.md) §Camada C — Patricia).
3. **Resume via plan.** Marina roda `forge plan agenda-poda`. Engine pré-processa antes de dispatchar conductor:
   - lê L1 status da feature (`.planning/agenda-poda/status.json`)
   - detecta `state=deferred` + `last-wave=D` + `wave-d-done=true` + `wave-e-pending=true`
   - dispara o caminho auto-resume conforme Decision 27 (LOCKED, load-bearing) e [`docs/design/07-discipline.md`](../design/07-discipline.md) §7
   - Em vez de rodar Wave A do zero, conductor entra em modo `resume_from=E` com state preservado
4. **Conductor messaging.** Sub-agente Claude Code conductor responde com tom mentor calmo, factual, sem ceremony:

   > "Retomando agenda-poda. Wave D foi verificada em 2026-06-03 17:45. Continuando Wave E (readiness)..."

   Em seguida lista o que já está pronto + o que falta — pra Marina não precisar abrir cada arquivo manualmente pra verificar:
   - PRD ✅ (Wave B, 11:15 ontem)
   - screen-analysis ✅ (Wave B, 11:15 ontem)
   - BDD ✅ (Wave C, 14:00 ontem)
   - analytics-spec ✅ (Wave C, 14:00 ontem)
   - threat-model ✅ (Wave C, 14:00 ontem)
   - tech-spec ✅ (Wave D, 17:45 ontem)
   - 6 task-contracts ✅ (Wave D, 17:45 ontem)
   - **Falta:** readiness review (Wave E)
   - Marina lê a listagem e relaxa. Tudo está onde precisa estar.
5. **Wave E readiness.** Readiness-reviewer-agent passa pelo checklist canônico (mesmo checklist de C2 step 5):
   - artefatos completos? ✅
   - contracts coerentes entre si (BDD ↔ analytics-spec ↔ data-contract)? ✅
   - tasks com `allowed_files` declarados? ✅
   - validators de Wave E verde? ✅
   - dependencies externas declaradas? ✅
   - Marina não precisa preencher nada — todos os inputs já estão em L1 desde ontem. Veredito: `readiness=ready` em ~5min. State transiciona em L1 pra `state=planning, readiness=ready, wave-e-done=true` (timestamp hoje 9:08).
6. **Continua.** Marina segue pra `forge implement agenda-poda`. Loop task-por-task como em C2. Nada se perdeu por causa do Ctrl+C de ontem. A retomada custou ~5min — tempo de readiness review mais consulta visual ao status board. Se Marina tivesse rodado Wave A do zero por desconfiança, perderia ~1h — o `forge status` board ancorou a confiança correta.

**Outcome**

Zero retrabalho, zero "qual era mesmo o contract da analytics?". Componentes do valor entregue:

- **Auto-resume é estado normal, não exceção** — Ctrl+C às 18h ontem é fluxo padrão, não caso raro tratado com workaround. Engine assume que pause é a forma natural de terminar o dia, não interrupção catastrófica.
- **Confiança no comportamento de pause permite uso normal** — Marina não tem aversão a Ctrl+C; sem essa garantia, devs evitam pausar e acumulam contexto até estourar a janela cognitiva.
- **State persistido em disco, não em memória de sessão** — `.planning/agenda-poda/status.json` + artefatos são canônicos; sessão Claude Code é dispensável.
- **`forge status` ancora confiança visual** — Marina vê o board antes de prosseguir; reduz ansiedade do cold-start.
- **Distinção deferred vs aborted preservada** — `state=deferred` (auto-resumable, default em Ctrl+C) ≠ `state=aborted` (2-step explícito via `forge undo` interativo). Decision 27 foi locked exatamente pra preservar essa garantia.
- **Patricia (PM) consome o mesmo board read-only** — vê `agenda-poda` em deferred com timestamp; sabe que tem progresso parado sem perguntar à Marina em standup.

**Cross-ref**

- [`docs/design/07-discipline.md`](../design/07-discipline.md) §7 cobre pause vs deferred vs aborted em detalhe operacional, com transições de estado, quando cada uma ocorre, e a semântica do `forge undo` interativo (single-step abort vs 2-step abort permanente).
- [`docs/design/01-decisions.md`](../design/01-decisions.md) Decision 27 fixou auto-resumable como locked (load-bearing — quebrar essa garantia quebra retomada cross-session inteira; é uma das 8 decisões load-bearing listadas em [`.claude/rules/decisions.md`](../../.claude/rules/decisions.md)).

---

## C5 — Extension feature (Gap 9)

**Persona principal:** Marina.

**Persona adjacente:** Patricia, PM que pediu o follow-up. A parent feature `lembrete-rega` foi shipada por Marina em C2 — este cenário é continuação direta daquele.

**Estado inicial**

- Feature `lembrete-rega` shipped semana passada (state=done, `shipped-at` timestamped, todos os 8 commits no histórico).
- Patricia (PM) volta com follow-up no Slack: "lembrete por hora, não só por intervalo de dias — usuários pediram pra agendar pra horário específico (manhã/noite)".
- É refinamento natural da feature anterior — diferencial é só o trigger:
  - **Mesmo user value**: planta-owner não esquece de regar
  - **Mesma persona alvo**: planta-owner casual
  - **Mesmo business outcome**: engagement diário com o app
  - **Mesma arquitetura geral**: scheduler + repository + UI por planta
  - **Diferencial único**: trigger por hora-do-dia em vez de intervalo de dias
- Marina sabe que rodar Wave A completa de novo é desperdício — toda essa parte vem herdada do parent. Mas sem disciplina, ela faria copy-paste do PRD da `lembrete-rega` e adaptaria, gerando drift entre os 2 PRDs.
- Mood: focada, sem stress. É feature pequena com escopo claro.

**Estado final**

- Feature `lembrete-rega-hora` derivada com `extends-feature: lembrete-rega` registrado em L1 da nova feature.
- User value + persona + business outcome herdados do parent — Wave A skipa elicit redundante.
- Tech-spec contextualizada com parent (referencia entities + screens do parent explicitamente, em vez de re-declarar).
- Feature shipada mais rápida que feature do zero (~3h vs ~5h estimados).
- Pattern leve product-derived registrado em canon — não requer schema novo, não requer card novo, não requer mudança de canon mobile.
- L1 da feature filha aponta pra L1 do parent — abre porta pra reuse-intelligence detectar família de features no futuro.

**Passos**

1. **Plan com slug derivado.** Marina roda `forge plan lembrete-rega-hora`. Conductor olha o nome e detecta padrão de slug derivado:
   - substring do nome (`lembrete-rega`) matcha uma feature em L1 com `state=done`
   - sufixo `-hora` é candidato a diferencial de extension (não é prefix de ticket nem keyword de refactor)
   - timestamp de shipped-at do parent é recente (<30 dias) — fresh enough pra extension natural
   - parent não tem extension prévia ativa (sem `lembrete-rega-*-pending`)
   - Em Cena 1, sub-agente apresenta **4 caminhos** em vez de 3 padrão (o 4º só aparece neste conditional):
     - **Greenfield** — feature do zero (assume que slug é coincidência). Útil se Marina genuinamente quer criar feature independente
     - **Retomar** — state=deferred existente (não aplica aqui, parent já está done com shipped-at)
     - **Bugfix** — ticket-pattern (não aplica, sem prefix `IN-` no slug)
     - **Estender** ⭐ conditional — só aparece quando existe parent candidato com state=done; é o caminho recomendado pelo conductor pra esta situação
   - Conductor pergunta:

   > "Detectei `lembrete-rega` em L1 com state=done (shipped 2026-05-28). Slug `lembrete-rega-hora` parece extension natural. Confirma caminho 'Estender'? (alternativas: Greenfield, Retomar, Bugfix)"
2. **Marina escolhe Estender.** Indica `parent=lembrete-rega`. Validator `validate_extension_feature` roda os 4 checks EXT-001..004 conforme `docs/design/07-discipline.md` §10:
   - **EXT-001**: parent existe em L1? (sim, `.claude/forge/state/lifecycle/lembrete-rega/status.json` presente)
   - **EXT-002**: parent.state==done? (sim, com `shipped-at` válido timestamped)
   - **EXT-003**: `extends-feature` field setado em L1 da nova feature? (sim, registrado pelo conductor ao escolher caminho)
   - **EXT-004**: slug derivado tem forma válida `<parent>-<suffix>`? (sim, `lembrete-rega-hora` matcha o pattern `lembrete-rega-*`)
   - Validator aprova; conductor prossegue.
3. **Wave A — skip elicit redundante.** Sub-agente lê o intake do parent e renderiza em modo "context import" — não pergunta nada novo, só confirma:
   - **user value** (herdado do parent): "planta-owner não esquece de regar"
   - **persona alvo** (herdada): planta-owner casual
   - **business outcome** (herdado): engagement diário
   - **scope** (parcialmente herdado, parcialmente novo): mesma cobertura + trigger por hora
   - Conductor mostra esses campos pra Marina confirmar; Marina confirma em 30s que as heranças são corretas. State L1 grava `wave-a-skip-reason=inherited-from-parent`.
4. **Wave B — só delta.** Sub-agente pergunta apenas o que muda em relação ao parent:
   - "Trigger antes era intervalo em dias; agora é hora-do-dia específica. UI muda? (sim, picker de hora em vez de input de dias). Estado novo no scheduler? (sim, recorrência diária por hora em vez de intervalo entre disparos)."
   - Marina preenche o delta em ~3min.
   - PRD do parent é referenciado por link, não reescrito.
   - Screen-analysis renderiza só os 2 estados novos (hora-picker, recorrência diária); estados do parent (loading, empty, success, error) são referenciados como "inherited".
5. **Wave C — contracts atualizadas.** Atualização incremental dos 4 contracts:
   - **BDD**: ganha 2 cenários novos — (a) hora marcada + notificação dispara no horário; (b) hora alcançada + permissão revogada pelo sistema → fallback graceful
   - **analytics-spec**: herda evento `lembrete_disparado` do parent + ganha sub-evento `lembrete_disparado_por_hora` com property `hora_marcada`
   - **threat-model**: não muda (mesmas considerações do parent — sem PII nova, lembrete local-only)
   - **data-contract-spec**: ganha campo `hora_do_dia: LocalTime?` em `Lembrete` (nullable pra compatibilidade com lembretes por intervalo do parent); migração L1+L2 compatível com schema atual, validator de schema migration aprova sem flag.
6. **Wave D — tech-spec contextualiza parent.** Tech-spec renderiza referenciando explicitamente entities + screens do parent:

   > "Reusa a entidade `Lembrete` da feature `lembrete-rega`; adiciona campo nullable `hora_do_dia`; adiciona `LembreteHoraScheduler` implementando o mesmo contrato de `LembreteDiasScheduler`. UI reusa `LembreteListScreen` com toggle dual entre 'por intervalo' (parent) e 'por hora' (esta feature). Notification handling reusa a infraestrutura do parent — diferença é só no scheduler."

   Task-contract-writer quebra em 4 tasks (vs 8 em C2 — muita estrutura herdada): task 1 modelo + migração schema, task 2 scheduler novo, task 3 UI (toggle + hora-picker), task 4 regression suite cobrindo ambos os triggers. `allowed_files` declarados por task.
7. **Wave E + implement.** Readiness=ready em <10min total Waves A-E (vs ~15min de feature do zero em C2). Implement task-por-task como em C2. `forge verify` cascade verde. 4 commits atômicos no formato canônico. Tempo total implement: ~2.5h (menos que C2 porque menos código novo).
8. **Status persistido.** L1 da `lembrete-rega-hora` grava no final:
   - `state=done`
   - `subtype=product`
   - `extends-feature: lembrete-rega`
   - `extension-depth=1`
   - `shipped-at` timestamped
   - Próxima extension dessa cadeia (hipotética `lembrete-rega-hora-snooze`) vai herdar de `lembrete-rega-hora` recursivamente, registrando `extension-depth=2` automaticamente.

**Outcome**

Pattern leve product-derived sem custo arquitetural. Componentes do valor entregue:

- **Cards canon não mudam** — schema permanece o mesmo, enum platforms idem, canon mobile inteiro inalterado. Extension é semântica de produto, não de arquitetura.
- **User value / persona / business outcome herdados** — Marina não re-explica "por que essa feature existe"; herda do parent automaticamente.
- **Tempo total reduzido** — Waves A-E + implement: ~3h vs ~5h se rodasse feature do zero. Wave A skipada, Wave B só pergunta delta, Wave D tem menos task-contracts.
- **Knowledge acumulado em L1 da forma certa** — a feature filha sabe que tem parent (`extends-feature: lembrete-rega`, `extension-depth=1`), o que abre porta pra reuse-intelligence (vide C6) detectar família de features no futuro.
- **Review focal em delta** — Diego recebe PR que referencia o parent explicitamente. Review foca nos 2 cenários BDD novos e na migração de schema, não em ceremony repetido sobre user value já estabelecido.
- **Suporte recursivo** — extension de extension funciona naturalmente (`lembrete-rega-hora-snooze` herdaria de `lembrete-rega-hora` que herda de `lembrete-rega`). Cadeia de derivação não tem limite arquitetural; engine só pede ceremony quando há delta real a documentar.

**Cross-ref**

- [`docs/design/07-discipline.md`](../design/07-discipline.md) §10 cobre o pattern extension feature em detalhe operacional, incluindo os 4 validators EXT-001..004 e a regra de extension-depth.
- [`docs/design/04-pending.md`](../design/04-pending.md) §Gap 9 documenta a decisão de pattern leve product-derived (vs alternativas pesadas rejeitadas como template-fork ou novo subtype `extension`).
- [`agents/planning-conductor.md`](../../agents/planning-conductor.md) cobre o 4º caminho em Cena 1 (conditional sobre parent state=done) e o modo "context import" da Wave A.

---

## C6 — Reuse intelligence em ação

**Persona principal:** Bruno (tech lead) + Marina (mobile dev solo). Cenário de colaboração assíncrona — Marina propõe via planejamento de Wave B, Bruno aceita via `forge evolve` semanal.

**Estado inicial**

- Squad com 18 features shipadas ao longo do ano (sucesso modesto, codebase saudável).
- Pattern `validateName()` aparece em 15 lugares com leve drift, distribuído por plataforma:
  - **7 versões em módulos Android**: cada feature de cadastro tem sua própria validateName local
  - **5 versões em Swift puro pra iOS**: idem, escrito em SwiftUI/Combine
  - **3 versões em KMP shared**: quando feature começou em shared mas validator ficou módulo-local
- Ninguém promoveu o helper pra `:shared:core:validation` ainda — cada feature criou sua própria versão local, sem revisar se outras existiam.
- Drift entre as 15 versões é pequeno mas crescente:
  - 9 das 15 trimmam whitespace; 6 não trimmam
  - 4 das 15 validam tamanho mínimo (3 char); 11 não validam tamanho
  - 2 das 15 validam charset (ASCII only); 13 aceitam UTF-8
  - Drift não causou bug ainda mas é tempo até causar (regressão em ordenação ou comparação)
- Marina vai planejar feature 19 (`agenda-poda`); Bruno faz triage semanal de `proposed-evolutions.yaml` toda quinta às 14h.
- Disciplina forge instalada no projeto há ~6 meses; squad familiarizada com fluxo `forge evolve`.

**Estado final**

- Helper consolidado em `:shared:core:validation.validateName(name: String): ValidationResult`.
- Card-local `.claude/cards/local/validation-helpers/` atualizado pra autoinject o helper quando feature usa.
- 12 features migradas pra usar o helper consolidado em PRs separados ao longo das semanas — não atrasa o planejamento da feature 19.
- L2 acumula o pattern + decisão arquitetural; drift cross-feature reduzido a zero (todas as features convergem na mesma implementação).
- Bruno não repetiu "promova validateName" em PR review eterno — engine detectou + propôs + humano decidiu, no ritmo da triage semanal.
- Knowledge da decisão fica versionado em `proposed-evolutions.yaml` aprovado, não vira folclore oral perdido em huddle.

**Passos**

1. **Planejamento da feature 19 dispara o scan.** Marina roda `forge plan agenda-poda` numa terça pela manhã. Subtype detectado=product. Wave A intake passa normalmente. Wave B (PRD + screen-analysis) chega e o conductor, ao analisar os campos da nova feature, consulta `forge graph` em background sobre validação de input. Especificamente:
   - **Q12** (consolidate-within-module) — busca duplicação no mesmo módulo da feature em planejamento
   - **Q15** (near-duplicate) — busca patterns similares cross-module (cross-feature, neste caso)
   - Engine percorre o catálogo de funções com nome `validateName` ou similaridade semântica via heurística pragmática (regex em v1, AST quando Phase 7 ativar).
2. **Graph retorna.** Resposta canônica do graph query:

   > "validateName aparece em 15 lugares com drift leve (9/15 trimmam whitespace, 6/15 não; 4/15 validam tamanho; 2/15 validam charset). Distribuição: 7 Android + 5 Swift + 3 KMP shared. Sugere `promote-to-shared` pra `:shared:core:validation` consolidando trim + min-length + UTF-8 (padrão da maioria das versões)."

   Conductor não interrompe a Wave B — registra o finding em buffer pra apresentar a Marina no fim da wave, evitando context-switch no meio do planning.
3. **Conductor apresenta 3-caminhos.** Fim da Wave B (Marina terminou de validar o PRD + screen-analysis), sub-agente apresenta voz mentor calmo, gate canônico conforme [`docs/design/07-discipline.md`](../design/07-discipline.md) §1:

   > "Detectei reuse-opportunity durante o scan reuse-intel da Wave B. Pattern `validateName` aparece em 15 lugares (7 Android + 5 Swift + 3 KMP shared) com drift cosmético crescente. Sugiro 3 caminhos:
   >
   > **(1) Promover agora** — abrir PR separado pra promover validateName pra `:shared:core:validation` antes de seguir com a feature 19. Custo: ~1h. Benefício: feature 19 já usa o helper consolidado, evita migration cascade depois.
   >
   > **(2) Registrar pra triage** — continuar com feature 19, registrar proposal pra Bruno revisar via `forge evolve` na quinta. Custo: 0 agora; ~1h de Bruno na quinta. Benefício: foco mantido, decisão fica com tech lead que tem visão cross-projeto.
   >
   > **(3) Ignorar por enquanto** — revisitar no fim do trimestre quando outras prioridades acalmarem. Custo: drift continua crescendo, fingerprint no entanto protege contra re-propor antes do prazo. Benefício: zero ruído nesta semana.
   >
   > Recomendo (2) por equilíbrio entre foco e progresso, e por respeitar a divisão de papéis (Marina implementa, Bruno decide promoção arquitetural cross-feature). Mas decisão é sua."

   Voz: factual, opções com custo/benefício explícito, recomendação justificada mas não impositiva, decisão final do humano. Esse template é o pattern 3-caminhos canônico usado em todos os gates do engine.
4. **Marina escolhe caminho (2).** Quer manter foco na feature 19. Conductor registra a proposal em `proposed-evolutions.yaml` com fingerprint sha256 estável (sobre `{kind=promote-to-shared, normalized-description=validateName-15-call-sites, sorted-provenance-set=<15-paths>}`). Wave B continua normal. Marina termina o planejamento da feature 19 sem distração, sai pra implement no mesmo dia.
5. **Quinta — Bruno faz triage.** Bruno abre `forge evolve` na quinta às 14h (sua janela canônica). Vê 47 proposals fresh acumuladas na semana inteira. Filtra por categoria:
   - `kind=promote-to-shared` — 5 propostas
   - `kind=consolidate-within-module` — 18 propostas
   - `kind=near-duplicate` — 12 propostas
   - outras — 12 propostas
   - O validateName está entre as 5 promote-to-shared, com a contagem de 15 lugares + sugestão de target `:shared:core:validation` + breakdown do drift.
6. **Bruno aceita.** Engine gera o diff proposto:
   - extract da função canônica em `shared/src/commonMain/kotlin/.../validation/Validation.kt`
   - replace de 15 call-sites em 12 features distintas
   - import update em cada arquivo afetado
   - PR sugerido por feature (12 PRs separados em vez de 1 PR gigantesco que toca 15 arquivos cross-feature)
   - Bruno aprova a estratégia de PR separado por feature — mais fácil de revisar isoladamente, menos risco de conflito de merge se outra dev estiver mexendo na feature simultaneamente.
7. **Migration cascade.** Dia seguinte (sexta), Marina pega a proposal aceita e mergeia primeiro o PR de `:shared:core:validation` (introdução do helper canônico). Os 12 PRs subsequentes seguem ao longo das próximas 3-4 semanas conforme dev disponível por feature toca cada uma — não bloqueia roadmap nem cria refator cascade urgente. Marina atualiza `.claude/cards/local/validation-helpers/` pra registrar referência ao helper consolidado, garantindo que features futuras (incluindo `agenda-poda` em planejamento e quaisquer outras) autoinjetem automaticamente.

**Outcome**

Sem Bruno repetir "promova validateName pra shared" em PR review eterno — engine detecta + propõe + humano decide, no ritmo da triage semanal. Componentes do valor entregue:

- **15 lugares com drift → 1 lugar canônico** — promote-to-shared executado de forma controlada, em PRs separados por feature, ao longo de semanas, sem cascade refactor urgente que bloqueia roadmap.
- **Saída de "alguém precisa lembrar" pra "engine lembra e propõe"** — o trabalho cognitivo de detectar duplicação cross-feature sai do humano e entra no graph query Q12 + Q15.
- **Foco preservado durante planejamento** — Marina não foi distraída por refator lateral em Wave B; conductor apresentou 3-caminhos e ela escolheu "registrar pra triage" sem context-switch.
- **Triage offline preserva julgamento humano** — Bruno revisa 47 proposals num bloco semanal de quinta às 14h, no momento certo, não no meio do planejamento.
- **Fingerprint protege scans futuros** — pattern entra em L2 com fingerprint estável; próximo scan não vai re-propor a mesma coisa sem mudança real (drift maior, novas instâncias, target diferente).
- **Knowledge versionado, não folclore oral** — decisão arquitetural "validateName canônico em :shared:core:validation" fica em `proposed-evolutions.yaml` aprovado + L2; quando dev sai do time, knowledge fica.
- **Ciclo virtuoso do canon via L2** — esse é o coração do que diferencia v1.2 atual (Onda 1) de aspirações Onda 3. Engine detecta, humano decide, L2 acumula. Próxima feature herda baseline melhor.

**Cross-ref**

- [`docs/lifecycle/memory-and-graph.md`](../lifecycle/memory-and-graph.md) cobre o pipeline reuse-intelligence em detalhe, incluindo as 17 graph queries canônicas e como o scan se integra ao Wave B.
- [`docs/schemas/graph.md`](../schemas/graph.md) §Q12-Q17 documenta as 6 categorias de finding com fingerprint canônico e os campos exatos do output de cada query.

---

## Padrões transversais — o que estes 6 cenários ensinam juntos

Lidos em sequência, C1-C6 cobrem o ciclo natural de adopt + uso maduro do engine. Não substituem leitura dos roteiros UX em `docs/ux/` (que são operacionais com transcrições) — são lentes de produto que ancoram persona + momento + valor.

**Eixo temporal (de onboarding a maturidade):**

- **C1** é o dia zero — Bruno instala forge num projeto brownfield e Marina faz a primeira triage no dia seguinte.
- **C2** é o dia normal — Marina pega ticket, planeja, implementa, ship em <1 dia.
- **C3** é o dia de stress — bugfix P0 não sacrifica disciplina mecânica.
- **C4** é o dia interrompido — Ctrl+C ontem não custa progresso hoje.
- **C5** é o dia de iteração — feature shipped vira parent de extension natural.
- **C6** é o dia em que o engine começa a antecipar — scan detecta padrão em background e propõe consolidação sem Marina pedir.

**Eixo de complexidade (do simples ao composto):**

- Cenários simples — C2, C3, C4 — envolvem 1 persona principal e 1 feature em foco.
- Cenários compostos — C1, C5, C6 — envolvem múltiplas personas em colaboração assíncrona (Bruno + Marina via `forge evolve`) ou múltiplas features em cascata (parent → extension; feature 19 + 12 migrations).

**O que NÃO está nestes cenários (deliberado):**

- **Anti-personas** (Flutter / React Native / Java puro / squad rejeitando disciplina) — vivem em [`00-prd.md`](00-prd.md) §9. Não tem cenário porque o engine não serve a esses casos por design; tentar forçar cenário pra anti-persona seria mentir sobre adequação do produto.
- **Cenários multi-dev simultâneo** (2 devs na mesma feature, branches conflitantes) — está em [`docs/design/04-pending.md`](../design/04-pending.md) §Gap 6 deferred pra Onda 2. v1 assume single-user na feature; multi-dev é overlay opcional futuro.
- **Cenários cross-projeto** (Marina trabalhando em 3 projetos em paralelo simultaneamente) — fora do escopo v1 single-config-per-subproject (Decision 14 LOCKED). Cada projeto tem seu workflow-config.yaml; cross-projeto é caso composto, não cenário canônico.
- **Cenários Patricia/Diego como persona principal** — Patricia consome `forge status` read-only adjacente a C1-C6; Diego revisa PRs gerados em C2-C6. Ambos aparecem em personas adjacentes/downstream mas nunca operam comandos forge diretamente (vide [`01-personas.md`](01-personas.md) §Camada C). Persona principal nestes cenários seria sintética e fora do design.
- **Cenário refactor puro** — refactor entra como subtype `refactor` em fluxo similar a C2/C3 (Wave A intake-refactor, Wave D tech-spec com no-behavior-change attestation), mas não tem cenário dedicado porque é variação operacional, não user journey novo. Vide [`docs/design/04-pending.md`](../design/04-pending.md) §Gap 1 sobre subtypes.
- **Cenário Onda 3 aspiracional** (engine sugere subtype/cards/threat com base em L2+L3 history) — fora do v1 atual. Cenários aqui descrevem o que o engine FAZ hoje (Onda 1 + parcial Onda 2 via Gap 5 maduro), não o que aspira.

**Mapeamento rápido cenário → persona principal:**

| Cenário | Persona principal | Personas adjacentes | Subtype | Frequência típica no projeto |
|---|---|---|---|---|
| C1 — Brownfield init com reuse-intelligence | Bruno | Marina (dia seguinte) | n/a (init) | 1x por projeto (one-time) |
| C2 — Feature product nova end-to-end | Marina | Patricia (PM), Diego (reviewer) | `product` | 5-15x por sprint |
| C3 — Bugfix com ticket IN-37234 | Marina (modo P0) | Patricia (PM, abriu ticket) | `bugfix` | 2-8x por sprint |
| C4 — Retomar trabalho pausado | Marina (cold-start) | — | n/a (resume) | ~1x por semana |
| C5 — Extension feature (Gap 9) | Marina | Patricia (PM, pediu follow-up) | `product` derivado | 1-3x por mês |
| C6 — Reuse intelligence em ação | Bruno + Marina (colaboração assíncrona) | — | n/a (cross-feature) | 1x por mês |

Detalhes de cada persona em [`01-personas.md`](01-personas.md). Resumo de 1-linha por cenário em [`00-prd.md`](00-prd.md) §6.

**Métricas mensuráveis ancoradas nos cenários:**

| Métrica | Cenário-âncora | Target Onda 1 | Hoje sem forge |
|---|---|---|---|
| Time-to-ready (Waves A-E) | C2 | ≤15min product | ~30-60min PRD fragmentado |
| Time-to-merge (ticket → PR merged) | C2, C3 | ≤4h product, ≤30min bugfix | ~6-8h product, ~60-90min bugfix |
| Manual edits per task | C2 | 0 | 5-15 ajustes manuais |
| Regression rate cross-feature | C3 | ≤2% | sem medição (folclore) |
| Cold-start retomada | C4 | ~5min | ~1h reorientação |
| Extension overhead vs feature do zero | C5 | -40% | n/a (sem pattern) |
| Reuse-opportunity detection | C6 | engine detecta | humano lembra (raramente) |

Targets canônicos vêm de [`00-prd.md`](00-prd.md) §8 e [`03-roadmap.md`](03-roadmap.md) §2 Onda 1.

## Como ler estes cenários

**Pra mantenedor:** cenários são fonte de verdade pra "como o engine deve se comportar do ponto de vista do usuário". Se uma implementação técnica diverge do cenário sem revisita explícita, é drift silencioso — abre brainstorm pra alinhar ou ajustar.

**Pra Claude futuro (interno):** cenários ancoram o que conta como "fluxo normal" vs "fluxo de exceção" no engine. Ao receber context-pack pra wave dispatch, o sub-agente deve respeitar o pattern do cenário aplicável (subtype detection, gates, 3-caminhos, voz mentor calmo).

**Pra adopter avaliando:** ler os 6 cenários cobre ~90% do espaço de uso real. Se o caso de adopt do leitor não se encaixa em nenhum dos 6, é sinal pra investigar — pode ser cenário não-mapeado (anotar em `04-pending.md`) ou anti-padrão (forge não serve, vide [`00-prd.md`](00-prd.md) §9 anti-personas).

**Pra reviewer humano (Diego):** os cenários definem o que ele DEVE ver num PR forge-gerado. Compliance mecânico (atomic commits, allowed_files respeitado, contracts presentes) é garantido por cenário; o que ele revisa é decisão arquitetural e produto.

## Como adicionar novos cenários

Cenários têm peso load-bearing — toda decisão de produto e de UX assume a cobertura destes 6. Adicionar um 7º cenário NÃO é refator livre. Caminho oficial:

1. **Brainstorm explícito** via `superpowers:brainstorming` com mantenedor. Perguntas-âncora: qual persona principal? qual gap atual deixa o caso descoberto? como o engine se comportaria neste cenário vs comportamento atual?
2. **Justificativa em `docs/design/04-pending.md`** — abre gap registrando o cenário não coberto, com evidência concreta (não hipotético).
3. **Spec dedicado** se cenário é substantivo — `docs/superpowers/specs/YYYY-MM-DD-cenario-N-design.md`.
4. **Writing-plans** seguindo este pattern (skeleton + tasks + validation suite).
5. **Update bidirecional** — adiciona cenário aqui + cross-ref em [`01-personas.md`](01-personas.md) (persona principal ganha entrada "Cenário CN") + resumo em [`00-prd.md`](00-prd.md) §6.

Modificar cenário existente segue mesmo caminho — não edita esta página sem revisita explícita ao spec que originou. Drift entre cenário e implementação real é débito que aparece silenciosamente quando dev novo lê o doc esperando comportamento X e encontra Y.

Detalhes dos cenários em [`02-scenarios.md`](02-scenarios.md) self-reference (este doc). Resumos em [`00-prd.md`](00-prd.md) §6. Persona-mapping em [`01-personas.md`](01-personas.md) tabela final.

## Notas finais sobre voz e consistência

Cenários seguem a voz mentor calmo declarada em [`docs/design/07-discipline.md`](../design/07-discipline.md) §5 e ancorada em [`CLAUDE.md`](../../CLAUDE.md) Mandamento #5:

- **Warm em exploração** — descrição de mood ("foco", "leve ansiedade do cold-start", "modo P0 stress") é narrativa, não burocrática
- **Firme em gates** — quando conductor apresenta 3-caminhos, a voz é factual com custo/benefício explícito e recomendação justificada
- **Didático sem ser professoral** — cross-refs apontam onde o leitor pode aprofundar, sem reescrever o que já está em `docs/design/`
- **Concreto sem jargão** — tickets têm número real (IN-42100, IN-37234), slugs têm forma plausível (lembrete-rega, agenda-poda), tempos têm magnitude verificável

**Anti-padrões evitados** (lista completa em [`docs/design/07-discipline.md`](../design/07-discipline.md) §5):

- Voz corporativa-jargão (substantivos vazios e verbos de palco) — fica fora destes cenários inteiramente
- Emoji decorativo. Exceções permitidas onde carregam semântica (✅ pra wave done, ❌ pra signal negativo, ⭐ pra caminho recomendado)
- "Vou tentar", "talvez", "pode ser uma boa ideia" — compromisso ou redirecionamento explícito sempre
- Recap genérico do que já está em docs/design ou docs/ux — cross-ref e referência específica, não duplicação

**Consistência rígida:**

- Personas: Marina, Bruno, Sub-agente Claude, Carlos, Lucas, Carolina, Patricia, Diego — nomes canônicos não substituíveis por sinônimos genéricos
- Slugs: lembrete-rega (parent), lembrete-rega-hora (extension), agenda-poda (pausa em C4 + feature 19 em C6), validateName (helper consolidado em C6)
- Tickets: IN-42100 (C2 lembrete-rega) e IN-37234 (C3 bugfix) — não inventar novos sem revisita
- Categorias reuse-intel: consolidate-within-module, promote-to-shared, redundant-platform, near-duplicate, kmp-migration-candidate, consolidate-ts-helpers (Q12-Q17 canônicos)

Drift silencioso em qualquer um destes campos enfraquece o vocabulário compartilhado entre mantenedor + Claude futuro. Caso surja necessidade de adicionar ticket, slug ou persona, abre brainstorm explícito antes de mexer aqui.
