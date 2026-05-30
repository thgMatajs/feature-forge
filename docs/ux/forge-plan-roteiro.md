# `forge plan` — roteiro end-to-end

The cinematic UX of `forge plan`. Each line that appears in the terminal, with
real timing, voice in mentor-calmo. Sibling document to `forge-init-roteiro.md`
— same style, same density.

## Context

- Driven by the `planning-conductor` agent (6 phases, Waves A–E for dispatch)
- Assumes `forge init` already ran (workflow-config + inventories present)
- Output: complete feature package + readiness=ready handoff
- L1 per-feature memory is created and written throughout
- Total budget: 90–180 seconds end-to-end (longer than init: user interacts)

---

## Cena 1 — Entrada + pre-flight (0.0–2.5s)

```
$ forge plan

   ╭──────────────────────────────────────────╮
   │  feature-forge · plan                    │
   │  Mentor calmo. Sem invenção. Sem pressa. │
   ╰──────────────────────────────────────────╯

[0:01] Checando ambiente...
       ├ workflow-config.yaml                  ✓ (preset: kmp-mobile-firebase)
       ├ inventories                           ✓ (conventions · DS · i18n)
       ├ memory L2/L3                          ✓
       ├ graph.db                              ✓ (last update: 4h atrás)
       └ no other feature in-flight            ✓
```

**Note:** if `.claude/workflow-config.yaml` is missing → exits with
`forge init primeiro — sem config eu não invento o seu projeto.` If another
feature is in-flight, the script jumps straight to **Edge case: Auto-resume**
(see below).

---

## Cena 2 — Source inquiry (2.5–4.5s)

Single question, combinable answers. No flags, no menus.

```
[0:03] De onde vem essa feature?
       
       Pode combinar (ex: "ticket BONSAI-1284 + 2 screenshots na pasta /tmp"):
       
         • Jira ticket           (detectei Atlassian MCP configurado)
         • Screenshots           (cole paths ou arraste pro chat)
         • Descrição livre       (me conta em texto)
         • Tudo isso             (ticket + screenshots + contexto extra)
       
       > _
```

User answers, free-form. Conductor parses intent (slot-filling, not enum).
Resolution example:

> "BONSAI-1284 e esses 3 mockups: /tmp/lembrete-rega-*.png"

**Note:** intentionally a single open question. No multi-step modal. The
conductor is good enough to parse "ticket BONSAI-1284 + 3 screenshots" in one
shot. Mentor calmo doesn't force the user through a wizard.

---

## Cena 3 — Context load (silent, 4.5–8s)

Phase 1 of planning-conductor. Nothing shown to the user except a single
progress line — the work happens behind the scenes.

```
[0:05] Carregando contexto do projeto...
       ├ workflow-config + cards ativos (12)
       ├ inventory: conventions · design-system (28) · i18n (487 keys)
       ├ memory L2 (3 patterns · 1 FND · 2 decisions-frozen)
       ├ memory L3 (user prefs · pt-BR · feedback rules)
       └ active cards' agent-contributions.md  (12 cards)
```

**Note:** the workflow-config is loaded but **never paraded back to the user
verbatim**. Mentor calmo respects: "you already told me, I remember." If
something configured silently affects a decision later, the conductor surfaces
*the decision*, not the config.

---

## Cena 4 — Jira fetch (8–18s, conditional)

Only runs if the user mentioned a ticket.

```
[0:08] 🎫 Buscando BONSAI-1284 no Jira
       ├ summary                               ✓
       ├ description + acceptance criteria     ✓ (4 ACs)
       ├ attachments                           ✓ (3 imagens, baixando...)
       │   ├ mockup-list.png                   ✓ → screenshots/
       │   ├ mockup-detail.png                 ✓ → screenshots/
       │   └ mockup-empty.png                  ✓ → screenshots/
       ├ linked tickets                        ✓ (BONSAI-1210, BONSAI-1180)
       └ status / sprint                       ✓ (To Do · Sprint 24)
       
       Título: "Criar lembretes de rega por bonsai"
       Slug proposto: lembrete-rega
       
       Ok seguir com esse slug? [Y / sugerir outro]
```

User accepts → slug locked. Conductor creates
`.claude/memory/L1/lembrete-rega/` and writes the first `history.jsonl` entry.

**Note:** if the Jira MCP is configured but unreachable, the conductor degrades
gracefully — see **Edge case: Jira offline**. Linked tickets are noted but not
fetched eagerly (avoid bloating context pack).

---

## Cena 5 — Vision analysis (18–30s, conditional)

Only runs if screenshots are present (from ticket or supplied directly).

```
[0:18] 🔍 Analisando 3 mockups
       
       mockup-list.png:
         ├ Layout                              top-bar + lista vertical + FAB
         ├ MeoTopBar                           94% match (variante 'title')
         ├ MeoCard × 4                         91% match
         ├ MeoFab                              97% match
         └ ⚠ Ícone de gota d'água              não encontrado no DS
              proposta: novo componente `WaterDropletIcon` (atom)
       
       mockup-detail.png:
         ├ MeoTopBar                           97% match (variante 'back')
         ├ MeoTextField × 3                    93% match
         ├ MeoSegmentedChips                   88% match
         └ MeoButton                           96% match (variante 'primary')
       
       mockup-empty.png:
         ├ MeoFeedbackState                    92% match (tone 'empty')
         └ MeoButton                           96% match (variante 'primary' CTA)
       
       Textos detectados (vou propor i18n keys depois):
         · "Próximos lembretes"
         · "Sem lembretes ainda"
         · "Criar primeiro lembrete"
```

**Note:** matching against `inventory/design-system.yaml`. Anything < 85%
match is flagged for confirmation. New components are NOT silently created —
they enter the ambiguity map for explicit user approval.

---

## Cena 6 — Graph query (30–34s)

```
[0:30] 🗺️ Buscando features estruturalmente parecidas
       ├ query: shape=list+detail + persistence=firestore + reminders
       └ matches:
           · bonsai-list             (similar shape, sem notification)
           · water-tracker           (similar domain, sem detail screen)
       
       Vou usar ambas como referência de padrão (sem copiar comportamento).
```

**Note:** `forge graph query` returns top 1–2 features by structural similarity.
Conductor reads their tech-spec and screen-analysis silently to seed defaults
(folder layout, ViewModel shape, DI conventions). Does not copy feature
behavior — copies *patterns*.

---

## Cena 7 — Working hypothesis (34–42s)

Phase 1 ends with the conductor showing the structural read. User confirms or
corrects before any elicitation.

```
[0:34] 🧠 Hipótese de trabalho
       
       Forma estrutural:    list+detail+create
       Telas:               3 (lista · detalhe · criar/editar)
       Persistência:        Firestore (alinha com L2 do projeto)
       Real-time:           não (L2 mostra one-shot reads default)
       Auth obrigatória:    sim
       Componentes existentes que vou reusar:
         · MeoTopBar · MeoCard · MeoFab · MeoTextField
         · MeoSegmentedChips · MeoButton · MeoFeedbackState
       Componentes novos a propor:
         · WaterDropletIcon (atom)
       
       Confidence:          0.81
       
       Está correto? [Y / corrigir hipótese / detalhar]
```

User responds "Y". Conductor writes
`.claude/memory/L1/lembrete-rega/hypothesis.yaml` with confidence, shape,
identified-components, new-components-needed, similar-features.

**Note:** this is the **first interactive checkpoint** and it's deliberately
high-level. Mentor calmo: "I'm not going to ask you 27 questions before
showing what I understood." If user corrects shape (e.g., "não é
list+detail, é wizard"), conductor restarts Phase 1 with the new frame.

---

## Cena 8 — Ambiguity Map (silent, 42–48s)

Phase 2. No terminal output beyond a heartbeat line. Conductor walks the full
decision tree (27 nodes per `agents/planning-conductor.md` §Phase 2), resolves
what it can from ticket/screenshots/graph/L2/L3/cards, and counts unresolved.

```
[0:42] Computando árvore de decisão...
       (27 nós · resolvendo via ticket · grafo · L2 · cards)
       
       └ ambiguity-map.yaml gravado em .claude/memory/L1/lembrete-rega/
         · resolvidos:   23
         · pendentes:    4
         · confidence média: 0.91
```

**Note:** if more than 8 nodes are unresolved, conductor refuses to proceed
and re-examines sources (per planning-conductor §Phase 3 discipline). Likely
cause: missing screenshots, vague ticket, or stale memory.

---

## Cena 9 — Elicitation (48–80s)

Phase 3. Single AskUserQuestion with the 4 unresolved nodes, each carrying:
- what was detected as default (if any)
- WHY the question matters (which artifact it influences)
- mutually exclusive options

```
[0:48] Quatro coisas não consigo decidir sozinho. Vou perguntar todas juntas.
```

```
1. Estado vazio (sem lembretes ainda)
   Detectei MeoFeedbackState nos mockups (92% match). Mas o CTA varia.
   Influencia: ui-state-spec.yaml · screen-analysis.md
   
   • MeoFeedbackState com CTA "Criar primeiro lembrete" (match dos mockups)
   • Lista vazia + FAB destacado (sem feedback-state)
   • Mostrar exemplo/onboarding inline na primeira vez
   • Outra coisa (descrever)

2. Estratégia offline para CRIAR lembrete
   L2 mostra que 2/3 features usam outbox queue com retry. Confirma?
   Influencia: data-contract-spec.yaml · tech-spec.md · test-strategy.yaml
   
   • Outbox queue com retry (alinhado com L2)
   • Optimistic-write com rollback se falhar
   • Bloqueia criação quando offline (mensagem clara)
   • Depende — me ajuda a decidir

3. Push notification quando o lembrete dispara
   AC menciona "notificar usuário". Não detectei push setup nesta feature.
   Influencia: navigation-spec.yaml · feature-prd.md · tasks

   • Push local (AlarmManager + UNUserNotification, sem Firebase Cloud Messaging)
   • Push remoto via FCM (precisa Cloud Function)
   • Sem push — só badge no app quando abrir
   • Decidir depois (vira open-question NÃO bloqueante)

4. Permissão de notificação
   Quando pedir? Detectei que projeto ainda não tem fluxo de permissão.
   Influencia: navigation-spec.yaml · screen-analysis.md (estado pré-permission)
   
   • Pede no onboarding global (fora desta feature)
   • Pede na primeira vez que usuário cria lembrete
   • Pede no app launch, sem contexto (anti-pattern, vou registrar warning)
   • Pula — assume permissão concedida (frágil)
```

**Note:** AskUserQuestion is a **single panel** with 4 grouped questions. No
flag, no menu navigation. Each option is exhaustive. Each question cites the
artifact it influences — transparency on WHY.

User answers, e.g.:
> 1. MeoFeedbackState com CTA
> 2. Outbox queue
> 3. Push local
> 4. depende

---

## Cena 10 — Drill-down (80–95s)

Question 4's answer ("depende") is vague. Conductor drills down per the
discipline table in `agents/planning-conductor.md` §Phase 3.

```
[1:20] "Depende" é uma resposta legítima — mas vou precisar concretizar
       antes de seguir. Senão eu invento, e eu não invento.
       
       Vou propor o caminho mais comum em apps similares:
       
         Pedir permissão quando o usuário cria o PRIMEIRO lembrete.
         Motivo: contexto explícito ("você quer ser notificado disso?"),
         e usuário entende o pedido na hora do uso real.
       
       Riscos: se ele negar, o lembrete entra como "silencioso" e precisa
       de UI clara que avise que sem permissão o aviso não chega.
       
       Outras opções concretas:
         • Pedir no onboarding (mais agressivo, mas resolve cedo)
         • Pedir quando lembrete VAI disparar (raro — iOS bloqueia silent)
         • Configuração explícita em Settings (passivo, baixo opt-in)
       
       Qual encaixa? Pode também dizer "vai com o primeiro caminho".
```

User: "vai com o primeiro."

Conductor writes `elicitation.yaml`:

```yaml
rounds:
  - round: 1
    questions-asked: 4
    answers:
      - question-id: Q-empty-state
        answer: "MeoFeedbackState with CTA"
        drill-down-needed: false
      - question-id: Q-offline-write
        answer: "Outbox queue with retry"
        drill-down-needed: false
      - question-id: Q-push-strategy
        answer: "Push local (AlarmManager + UNUserNotification)"
        drill-down-needed: false
      - question-id: Q-push-permission
        answer: "vague (depende)"
        drill-down-needed: true
        drill-down-answer: "Pede no primeiro lembrete criado"
        drill-down-rounds: 1

remaining-ambiguity: 0
```

**Note:** drill-down is **never an interrogation**. Conductor proposes a
default with rationale + alternatives. User can accept the proposal or pick
another. The point is to collapse "depende" into a concrete choice with
traceable rationale.

---

## Cena 11 — Wave A dispatch (95–115s)

Phase 4 starts. Conductor dispatches sub-agents in parallel where safe. Each
gets a **minimal context pack** (not the whole folder).

```
[1:35] ⚡ Wave A — paralelo (2 sub-agentes)
       
       ├ feature-intake-agent
       │   context pack: 12kb (ticket + hypothesis + L2 patterns)
       │   ⠋ working...
       │
       └ feature-prd-agent
           context pack: 14kb (ticket + screenshots + elicitation)
           ⠋ working...
       
       [1:38] feature-intake-agent          ✓ feature-intake.md (validator: pass)
       [1:42] feature-prd-agent             ✓ feature-prd.md (validator: pass)
```

`dispatch-log.jsonl` records each dispatch + return + validator outcome.

**Note:** wave A is structural: PRD describes WHAT, intake confirms the
boundaries. They don't depend on each other so they run in parallel. The
context pack is filtered — feature-prd-agent gets the screenshots, intake
doesn't.

---

## Cena 12 — Wave B dispatch (115–145s)

```
[1:55] ⚡ Wave B — paralelo (2 sub-agentes)
       
       ├ screen-analysis-agent
       │   context pack: 18kb (PRD + screenshots + DS inventory filtered + L2)
       │   ⠋ working...
       │
       └ contract-planner-agent
           context pack: 16kb (PRD + intake + L2 + analytics conventions)
           ⠋ working...
       
       [2:01] screen-analysis-agent         ✓ screen-analysis.md
                                            ✓ ui-state-spec.yaml (validator: pass)
       [2:05] contract-planner-agent        ✓ bdd.md
                                            ✓ bdd.json
                                            ✓ navigation-spec.yaml
                                            ✓ data-contract-spec.yaml
                                            ✓ analytics-spec.yaml
                                            ✓ test-strategy.yaml
                                            (validators: 6/6 pass)
```

**Note:** wave B is behavioral. Screen-analysis captures per-screen states and
transitions; contract-planner emits the 5 spec YAMLs that downstream
implementation will read. Both consume wave A output but not each other's, so
they parallelize.

---

## Cena 13 — Wave C — tech-spec (145–160s)

```
[2:25] ⚡ Wave C — sequential
       
       └ tech-spec-agent
           context pack: 28kb (todos artefatos de A+B + cards filtrados +
                              conventions + tech-spec template)
           ⠋ working...
       
       [2:38] tech-spec-agent              ✓ tech-spec.md (validator: pass)
                                           · KMP shared layer detalhado
                                           · 3 telas mapeadas (Android + iOS)
                                           · Outbox queue + retry policy
                                           · Push local Android + iOS
```

**Note:** tech-spec is single-agent because it consolidates every prior
artifact. Largest context pack but still filtered — irrelevant cards (e.g.,
firebase-storage if no image upload) are not included.

---

## Cena 14 — Wave D — task contracts (160–180s)

```
[2:40] ⚡ Wave D — sequential
       
       └ task-contract-writer
           context pack: 34kb (tech-spec + all specs + task-contract template)
           ⠋ working...
       
       [3:00] task-contract-writer         ✓ task-breakdown.yaml
                                           ✓ tasks/TASK-0001.yaml
                                           ✓ tasks/TASK-0002.yaml
                                           ✓ tasks/TASK-0003.yaml
                                           ✓ tasks/TASK-0004.yaml
                                           ✓ tasks/TASK-0005.yaml
                                           ✓ tasks/TASK-0006.yaml
                                           ✓ tasks/TASK-0007.yaml
                                           (validators: 7/7 pass)
       
       3 tarefas paralelizáveis identificadas
       4 tarefas no caminho crítico
```

**Note:** each task YAML conforms to `validate_task_contract.py`. The breakdown
declares dependencies + parallelizability. Parallel marker is computed from the
DAG, not guessed.

---

## Cena 15 — Wave E — readiness review (180–195s)

```
[3:00] ⚡ Wave E — sequential
       
       └ readiness-reviewer
           context pack: 42kb (todos os 15 docs + tasks + open-questions)
           ⠋ working...
       
       [3:15] readiness-reviewer           ⚠ readiness: NEEDS-FIX
                                           · screen-analysis.md missing
                                             error state for offline+create
```

Validator caught a gap. Self-check loop activates.

---

## Cena 16 — Self-check + retry (195–215s)

Phase 5 — loop up to 3 retries. Conductor identifies the responsible agent
and re-dispatches with a verbatim correction message.

```
[3:15] 🔁 Re-dispatch
       
       └ screen-analysis-agent (retry 1/3)
           correction: |
             ui-state-spec.yaml carece de estado 'offline-create-pending'
             na tela de criação. data-contract-spec define outbox queue,
             logo a tela tem que mostrar que o lembrete está pending sync.
             Adicione o estado com: indicador visual + copy + transição
             para 'synced' quando outbox flush.
           ⠋ working...
       
       [3:25] screen-analysis-agent        ✓ ui-state-spec.yaml updated
                                           (validator: pass)
       
       [3:25] 🔁 Re-running readiness-reviewer...
       
       [3:32] readiness-reviewer           ✓ readiness: READY
```

**Note:** retry message is precise — it cites the gap, the source artifact
that demands the gap be filled, and the shape of the fix. Sub-agent doesn't
invent. After 3 failed retries on the same node, conductor escalates to user
(see **Edge case: retry exhausted**).

---

## Cena 17 — Plan ready (215–225s)

The cinematic summary box. Mentor calmo's didactic closing.

```
[3:35] ✨ Plan ready
       
       ╭───────────────────── feature-forge · lembrete-rega ──────────────────────╮
       │                                                                          │
       │   📦 ARTEFATOS    16 documentos                                          │
       │     feature-intake.md · feature-prd.md · screen-analysis.md              │
       │     bdd.md · bdd.json · ui-state-spec.yaml · navigation-spec.yaml        │
       │     data-contract-spec.yaml · analytics-spec.yaml · test-strategy.yaml   │
       │     tech-spec.md · task-breakdown.yaml · open-questions.yaml             │
       │     implementation-readiness-review.md · plan-feature-handoff.json       │
       │     evals/evals.json                                                     │
       │                                                                          │
       │   📋 TASKS         7 (TASK-0001 → TASK-0007)                             │
       │     · 3 paralelizáveis (TASK-0002, TASK-0003, TASK-0005)                 │
       │     · 4 caminho crítico                                                  │
       │                                                                          │
       │   🧠 DECISÕES TRAÇADAS                                                   │
       │     12 decisões (.claude/memory/L1/lembrete-rega/rationale-trace.yaml)   │
       │       · 4 user-elicitation                                               │
       │       · 6 memory-L2 (alinhadas com projeto)                              │
       │       · 2 codebase-graph (similar features)                              │
       │                                                                          │
       │   🛑 OPEN QUESTIONS                                                      │
       │     0 blocking                                                           │
       │     1 non-blocking (Q-fcm-future: FCM remoto, deferido pra v2)           │
       │                                                                          │
       │   ✓ READINESS      ready                                                 │
       │                                                                          │
       ╰──────────────────────────────────────────────────────────────────────────╯
```

**Note:** this is the screenshot moment for `forge plan`. Aesthetic parity
with `forge init`'s final canvas. Numbers are real and traceable to actual
files. Decision counts come from `rationale-trace.yaml`.

---

## Cena 18 — Jira post-back (225–240s, conditional)

If `ticketing.post-back.on-readiness-ready == true` and
`require-confirmation == true` (default per workflow-config schema).

```
[3:35] 🎫 Postar resumo do plano em BONSAI-1284?
       
       Vou colar:
         • Forma: list+detail+create
         • 7 tasks (3 paralelizáveis)
         • Persistência: Firestore + outbox queue
         • Push: local (AlarmManager + UNUserNotification)
         • Open questions: 0 blocking · 1 deferred (FCM)
         • Link: docs/feature-implementation-workflow/features/lembrete-rega/
       
       Postar? [Y / editar / pular]
       
       > Y
       
       [3:38] ✓ Comentário postado em BONSAI-1284
```

**Note:** never posts without confirmation. Edit option lets user trim the
summary before posting (useful when ticket is product-facing and engineering
detail is noise).

---

## Cena 19 — Closing (240–245s)

```
[3:38] 📝 Salvo:
       
       docs/feature-implementation-workflow/features/lembrete-rega/
         16 docs · 7 tasks · readiness=ready
       
       .claude/memory/L1/lembrete-rega/
         hypothesis.yaml · ambiguity-map.yaml · elicitation.yaml
         rationale-trace.yaml · dispatch-log.jsonl · history.jsonl
       
       Próximo passo sugerido:
         forge implement TASK-0001
       
       Quando o último TASK for verificado, a retrospectiva roda
       automaticamente — promove aprendizados pra L2 e fila propostas
       de evolução em proposed-evolutions.yaml (revisar com `forge evolve`).
       
       Pronto.
```

**Note:** the closing names the immediate next step and explains the
automatic retrospective trigger on last-task-verify. Mentor calmo: didactic,
not bossy. Nenhum comando extra precisa ser lembrado pelo usuário.

---

## Design points this script crystallizes

| Implicit decision | Practical implication |
|---|---|
| Single source-inquiry question | No multi-step wizard. Conductor parses combined input. |
| Hypothesis confirmation before elicitation | User sees structure FIRST, then narrow questions. |
| 4 grouped questions max | Per planning-conductor §Phase 3. If > 8 → detection failed. |
| Each question cites the artifact it influences | Transparency. User knows why this matters. |
| Drill-down proposes a default + alternatives | Mentor calmo. Never "I don't know, you tell me." |
| Sub-agent context packs are minimal + filtered | Token economy. Faster waves. |
| Self-check retry message is verbatim + precise | Sub-agents fix the right thing on first retry. |
| Final canvas is single screenshot-quality block | Aesthetic parity with `forge init`. |
| Total time 90–180s | Acceptable. User typed input, real waves ran. |
| Jira post-back requires confirmation | Never modifies external state silently. |

---

## Edge cases the script needs to handle

### 1. Auto-resume — feature already in-flight

User runs `forge plan` while `.claude/memory/L1/{some-slug}/status.json`
shows `aborted: false` and readiness is not yet `ready`.

```
[0:01] Detectei plano em andamento: lembrete-rega
       
       Estado:
         · iniciado 2h atrás
         · fase: Wave B (contract-planner-agent)
         · última pergunta respondida: Q-push-permission
         · ambiguidade pendente: 0
       
       Posso:
         • Retomar de onde parou (recomendado)
         • Começar feature nova (paralelo) — não recomendo, gera ruído
         • Abortar lembrete-rega e começar do zero
       
       O que você quer?
```

**Note:** retomar é o caminho rápido — todas as respostas anteriores estão em
`elicitation.yaml`, basta seguir das Waves pendentes.

### 2. Greenfield feature — só descrição, sem ticket nem screenshots

```
[0:04] Sem ticket nem screenshots, só descrição. Tudo bem — vou precisar
       te perguntar um pouco mais que o normal.
       
       Vou seguir esse roteiro:
         1. Você me conta a feature em texto livre (1-2 parágrafos)
         2. Eu proponho uma estrutura (forma + telas + persistência)
         3. Você corrige
         4. Aí entro nas perguntas detalhadas
       
       Vai a descrição.
```

**Note:** estrutura permanece (hypothesis → ambiguity → elicit → dispatch).
Diferença: hypothesis tem confidence inicial mais baixa (~0.4), elicitation
vira 2 rounds em vez de 1.

### 3. Ambiguity unresolvable — drill-down inconclusive

User says "não sei" three times in a row to the same node.

```
[1:35] Tudo bem. Vou registrar como open-question bloqueante e parar antes
       do dispatch das waves.
       
       Motivo: sem essa decisão, screen-analysis vai inventar comportamento
       e tech-spec vai inventar contrato. Eu não invento.
       
       Open-question gravada:
         Q-push-permission · blocking
         Quando pedir permissão de notificação?
       
       Próximo passo: levante isso com PM/designer e me chame de volta:
         forge plan lembrete-rega
       
       Estado salvo. Sem readiness=ready ainda.
```

**Note:** "não sei" sem caminho de resolução é a única razão pra produzir
readiness ≠ ready. Mentor calmo é firme: não inventa pra fechar.

### 4. Sub-agent retry exhausted (3 failed retries)

```
[3:15] 🛑 screen-analysis-agent falhou 3x na mesma correção.
       
       Última saída:
         (mostra o trecho relevante)
       
       Minha hipótese de por que está travado:
         · O ui-state-spec template não tem slot pra estado 'pending-sync'
         · O agente está tentando colocar em 'error', mas valida quebra
       
       Caminhos:
         • Atualizar o template (manual, fora deste forge plan)
         • Aceitar o estado em 'processing' e marcar com flag (workaround)
         • Pausar — eu não consigo passar disso aqui
       
       O que prefere?
```

**Note:** conductor não silencia falha repetida. Escala com hipótese da causa
+ caminhos de resolução. Decisão é humana.

### 5. User aborts mid-flow

User types `para` or hits Ctrl-C during Wave B.

```
[2:01] Pausando...
       
       Estado salvo:
         · hypothesis.yaml         ✓
         · ambiguity-map.yaml      ✓
         · elicitation.yaml        ✓
         · Wave A artefatos        ✓ (feature-intake.md · feature-prd.md)
         · Wave B interrompida    em screen-analysis-agent
       
       Pra retomar:
         forge plan lembrete-rega
       
       Tá tudo gravado.
```

**Note:** `forge plan {slug}` sem nova entrada = retoma automaticamente.
Conductor lê `history.jsonl` pra saber onde parou.

### 6. Card conflict detected mid-plan

Rare. Happens if user ran `forge reconfigure` in another terminal and changed
active cards while a plan was open.

```
[2:25] 🛑 Conflito de cards detectado.
       
       Quando esse plano começou, cards ativos eram:
         · firebase-firestore · firebase-storage · ...
       
       Agora workflow-config.yaml mostra:
         · firebase-firestore (firebase-storage removido)
       
       O artefato data-contract-spec.yaml gerado em Wave B referencia Storage.
       Continuar agora produz spec inconsistente com o projeto.
       
       Caminhos:
         • Reverter workflow-config (preferível — outro terminal pode estar
           no meio de algo que vai ser desfeito)
         • Recomeçar este plano com cards novos (descarta Wave A+B)
         • Pausar tudo e investigar
       
       O que você quer?
```

**Note:** card conflict é gate hard. Mentor calmo não atravessa.

### 7. Jira MCP configured but offline

```
[0:08] 🎫 Tentando buscar BONSAI-1284...
       ⠋ ⠙ ⠹ timeout (10s)
       
       Atlassian MCP configurado mas inacessível agora.
       
       Caminhos:
         • Você cola summary + AC manualmente aqui no chat
         • Pulamos o ticket e seguimos só com screenshots + descrição
         • Pausamos e voltamos quando MCP responder
       
       O que você quer?
```

**Note:** degradação suave. Conductor não bloqueia o plano por falha externa
— oferece caminhos. Se o usuário cola manualmente, conductor extrai os
campos esperados e registra a fonte como `user-paste` em vez de `jira-mcp`.

---

## Voice examples in this flow

| Moment | Tone | Example |
|---|---|---|
| Hypothesis presentation | Warm, exploratory | "Hipótese de trabalho. Está correto?" |
| Elicitation question | Contextual, transparent | "Influencia: data-contract-spec.yaml · tech-spec.md" |
| Drill-down on vague | Proposes default + alternatives | "Vou propor o caminho mais comum. Riscos: ..." |
| Self-check rejection | Internal, precise | (correction message to sub-agent) |
| Gate violation | Firm, cites rule | "Não invento. Open-question gravada como bloqueante." |
| Out-of-scope | Redirect with adjacent value | "Estimativa não é meu escopo. 7 tasks, 3 paralelizáveis. Útil?" |
| Closing | Didactic, next steps | "Pra retomar / Quando terminar / Pronto." |

---

## What this script does NOT do

- Does not estimate effort or time
- Does not auto-merge L1 → L2 (promotion is **proposed** by retrospective-agent, **applied** by `forge evolve` after user review)
- Does not approve or push PRs
- Does not modify code outside `docs/.../features/{slug}/` and `.claude/memory/L1/{slug}/`
- Does not call sub-agents in waves that violate the dependency DAG
- Does not silently accept vague answers — drill-down or open-question, no third path
