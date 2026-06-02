# `forge implement` — roteiro end-to-end

The cinematic UX of `forge implement`. Each line that appears in the terminal,
with real timing, voice in mentor-calmo. Sibling document to
`forge-init-roteiro.md` and `forge-plan-roteiro.md` — same style, same density.

## Context

- Driven by the `execution-conductor` agent (single Task Contract per run)
- Assumes `forge plan` already completed with `readiness=ready` and at least
  one TASK-XXXX in `tasks/`
- Reads L1 `status.json` to auto-resume; never starts blind
- Runs through: resume → select → Plan Mode → confirm → Apply → Verify →
  Pre-commit Review → Evidence → Atomic Commit → Checkpoint
- Out-of-scope edits blocked at hook level; same-task fix loop only
- If last task → auto-trigger `retrospective-agent` (no separate command)
- Total budget per task: 90–300 seconds depending on size (Plan Mode is human-paced)

---

## Cena 1 — Entrada + auto-resume (0.0–2.5s)

```
$ forge implement

   ╭──────────────────────────────────────────╮
   │  feature-forge · implement               │
   │  Plan Mode antes de tudo. Sem improviso. │
   ╰──────────────────────────────────────────╯

[0:01] Checando ambiente...
       ├ workflow-config.yaml                  ✓ (preset: kmp-mobile-firebase)
       ├ hard-gates ativos                     ✓ (5 gates)
       ├ pre-commit-review                     ✓ blocking
       └ task-discipline                       ✓ plan-mode + verify + retry≤3

[0:02] 🧠 Lendo memory L1...
       ├ lembrete-rega/status.json             state: implementing
       ├ last-action                           task-0002-verified
       ├ last-action-at                        ontem 18:42
       └ current-task                          null  (TASK-0002 fechou limpo)

       Bom dia. Você parou ontem com TASK-0002 verificado e comitado.
       Sigo daqui?
```

**Note:** se `status.json.state == aborted` → recusa com motivo + caminhos. Se
`state == paused` → mostra exatamente em que sub-fase pausou (Plan Mode? Apply?
Fix loop?) e oferece retomar. Mentor calmo nunca começa às cegas.

---

## Cena 2 — Task selection (2.5–4.0s)

Sem argumento, conductor escolhe próxima task na ordem de dependência do
`task-breakdown.yaml`.

```
[0:03] 📋 Selecionando próxima task
       ├ Lendo task-breakdown.yaml             ✓ (7 tasks · DAG resolvido)
       ├ Done                                  TASK-0001 · TASK-0002
       ├ Dependências satisfeitas              TASK-0003, TASK-0005
       ├ Critical path                          TASK-0003 (4 downstream)
       └ Escolha                                TASK-0003
       
       TASK-0003 · Outbox queue + retry policy (shared)
         depende de:   TASK-0001 (done) · TASK-0002 (done)
         desbloqueia:  TASK-0004 · TASK-0006 · TASK-0007
         estimativa:   média (4 arquivos shared, 1 teste)
       
       Topa essa? [Y / outra task / listar todas]
```

**Note:** o conductor explica *por quê* essa task — não impõe. Se o usuário
disser "outra task" → mostra lista filtrada por "dependências satisfeitas". Se
pedir uma com dependência aberta → ver **Edge case 2**.

---

## Cena 2.5 — Blocked-on-external refusal (4s, conditional)

Discipline §9 — Cena renderizada apenas quando a task escolhida (ou a
única disponível) tem ≥ 1 entry em `depends_on_external` com
`blocking: true` e `resolved-at: null`. Sem dep externa → Cena pulada,
fluxo segue direto pra Cena 3 (Plan Mode).

### Caso happy path — outra task disponível na breakdown

```
[0:04] 🛑 TASK-0003 bloqueada por dependência externa
       
       O que falhou:
         BACKEND-1284 (jira) ainda está aberto. Sem o endpoint
         /api/weather eu não consigo planejar contra um shape de
         resposta que não existe.
       
       Onde:
         tasks/TASK-0003.yaml.depends_on_external[0]
       
       Por que importa:
         · Hard-gate readiness-must-be-ready exige dep externa resolvida
         · Implementar contra endpoint imaginário = invented behavior
         · Você perderia tempo refatorando quando o endpoint real chegar
       
       Três caminhos:
       
         1) Marcar dep externa como resolvida agora
            forge reconfigure → menu "marcar dep externa como resolvida"
            (use quando BACKEND-1284 fechou e você sabe disso — sai
             daqui, marca lá, volta pra implement)
         
         2) Pegar outra task que não dependa de BACKEND-1284
            TASK-0004 (Android UI · MeoCard list) já tem deps satisfeitas
            e zero deps externas. Quer ir nela em vez?
         
         3) Pausar a feature inteira
            state vira deferred, status.json salva o lugar. Você volta
            quando o ticket fechar — sem perda de progresso.
       
       Sem auto-fix aqui — escolha humana.
       
       > 2
       
[0:05] Beleza, indo pra TASK-0004. Estado da feature continua
       blocked-on-external (TASK-0003 ainda tem dep aberta) — forge
       status mostra o badge.
```

`engine.implement` flipa `status.json.state = "blocked-on-external"` no
primeiro refuse (já é idempotente em refuse subsequentes). Aceitar
caminho 2 escolhe outra task mas não muda o feature-state.

### Caso edge — nenhuma outra task disponível

```
[0:04] 🛑 TASK-0003 bloqueada por dependência externa
       (BACKEND-1284 · jira · ainda não resolvido)
       
       Não há outra task no DAG com deps satisfeitas e zero deps
       externas. Esta é a única candidata, e ela está bloqueada.
       
       Três caminhos:
       
         1) Marcar BACKEND-1284 como resolvida agora
            forge reconfigure → "marcar dep externa como resolvida"
         
         2) Pausar a feature
            state vira deferred. Volta quando o ticket fechar.
         
         3) Abortar a feature
            forge undo → "abort feature entirely". Mais drástico — use
            quando o ticket não vai fechar tão cedo e você quer
            limpar o board.
       
       > 1

[0:06] Saindo pra forge reconfigure. State da feature continua
       blocked-on-external — eu volto a aceitar implement assim que
       você marcar o ticket lá.
```

### Caso edge — dep externa resolvida durante o session

User volta de `forge reconfigure` (marcou BACKEND-1284 resolved) e
re-roda `forge implement {slug}`:

```
[0:00] forge implement lembrete-rega
       
[0:01] Status da feature: blocked-on-external (BACKEND-1284 ainda
       aberta?) — vou checar.
       
       ├ Re-scan tasks/                              ✓
       ├ BACKEND-1284 marcada resolved em 14:42      ✓
       ├ Tasks ainda com deps blocking abertas       0
       └ State: blocked-on-external → implementing   ✓
       
       Beleza, TASK-0003 destrancada. Seguindo Plan Mode normal.

[0:03] [Cena 3 — Plan Mode reveal]
```

Recompute do feature-state acontece em todo `forge implement` startup
quando state == blocked-on-external — barato (escaneia N task contracts
do feature), evita estado stale.

### Caso edge — múltiplas deps no mesmo ticket

TASK-0003 tem 2 entries em depends_on_external apontando pro mesmo
BACKEND-1284 (por design — uma dep pra read, outra pra write):

```
[0:04] 🛑 TASK-0003 bloqueada por dependência externa
       
       BACKEND-1284 (jira) cobre 2 deps nesta task:
         · GET /api/weather (leitura)
         · POST /api/weather/alert (escrita)
       
       Ambas marcadas como blocking — preciso de resolução completa
       desse ticket. Marcando o ticket via forge reconfigure resolve
       as duas entries de uma vez.
       
       [3-caminhos canônico]
```

`forge reconfigure` deduplica por `ticket` value quando marca: 1
prompt, 1 confirmação, N entries atualizadas atomicamente.

### Note operacional

- Cena 2.5 NÃO bloqueia o usuário forever. Sempre oferece 3 caminhos
  legítimos. Mentor calmo é firme no gate mas nunca cruel.
- O state da feature vai pra blocked-on-external no PRIMEIRO refuse
  de uma session. Refuses subsequentes não escrevem status.json
  (idempotente).
- `forge implement {slug}` em feature já em blocked-on-external SEMPRE
  faz re-scan dos task contracts no startup. Se o usuário marcou via
  reconfigure (ou editou na mão — discouraged), o destravamento é
  automático.

---

## Cena 3 — Plan Mode reveal (4.0–18s, cinematográfico)

Agent lê o Task Contract e enumera tudo que vai tocar, **antes de tocar em
nada**. Zero edição neste passo.

```
[0:05] 📋 Plan Mode · TASK-0003
       
       Lendo Task Contract...
       ├ tasks/TASK-0003.yaml                  ✓
       ├ allowed_files (3)                     declarados
       ├ validations (4)                       declaradas
       └ gates                                  4 ativos

[0:08] 🔍 Arquivos que VOU LER (contexto, sem editar)
       ├ shared/feature/lembrete-rega/.../domain/Reminder.kt
       ├ shared/feature/lembrete-rega/.../data/ReminderRepository.kt
       ├ shared/core/storage/Outbox.kt              (cross-feature, leitura)
       └ docs/.../features/lembrete-rega/data-contract-spec.yaml

[0:12] ⚡ Arquivos que VOU MODIFICAR (escopo desta task)
       ├ shared/feature/lembrete-rega/.../data/OutboxQueue.kt          NEW
       ├ shared/feature/lembrete-rega/.../data/ReminderRepositoryImpl.kt EDIT
       └ shared/feature/lembrete-rega/.../data/ReminderRepositoryImplTest.kt NEW
       
       Tudo dentro de allowed_files do contrato. Conferi.

[0:14] ⚠ Riscos que identifiquei
       ├ retry exponencial pode estourar limite de Firestore writes/min
       │   → mitigação: cap em 5 retries, backoff inicial 2s
       ├ outbox sem TTL pode acumular órfãos se app reinstalar
       │   → mitigação: TTL 72h documentado no spec
       └ teste depende de TestDispatcher pra avançar tempo
           → uso UnconfinedTestDispatcher + advanceTimeBy

[0:16] ✓ Validações que VOU RODAR após Apply
       ├ ./gradlew :shared:feature:lembrete-rega:testAndroidHostTest
       ├ python3 scripts/observability/check-no-hardcoded-auth-ids.sh
       ├ detekt no escopo modificado
       └ contract-conformance: ReminderRepositoryImpl ↔ data-contract-spec.yaml
```

**Note:** Plan Mode é o **gate humano antes do agente tocar código**. Cada
arquivo na lista é justificado. Mentor calmo: "você vê tudo que vai mudar."

---

## Cena 4 — User confirmation (18–22s)

```
[0:18] Confirmação
       
       3 arquivos a modificar (1 NEW, 1 EDIT, 1 NEW de teste).
       4 validações vão rodar antes do commit.
       Pre-commit review é bloqueante (workflow.pre-commit-review.blocking=true).
       
       Topa? [Y / ajustar plano / cancelar]
```

User responde `Y`. Conductor escreve em `history.jsonl`:

```jsonl
{"timestamp":"...","event":"plan-mode-approved","task":"TASK-0003","files-to-edit":3}
```

E transita `status.json.state` de `implementing` (idle) para `implementing`
com `current-task: "TASK-0003"` + `sub-state: "applying"`.

**Note:** "ajustar plano" abre conversa pra mudar escopo dentro do contrato
(ex.: "não preciso do teste agora, separa em outra task"). Não permite expandir
além de `allowed_files`. Cancelar volta pra estado idle sem mudar memory.

---

## Cena 5 — Apply Mode (22–55s)

Edição real. Cada arquivo aparece com diff resumido. Hook `post-edit` valida
contra `allowed_files` a cada gravação.

```
[0:22] ⚡ Apply Mode
       
       ├ [0:24] OutboxQueue.kt                  NEW  · 94 linhas
       │         scope check                    ✓ allowed_files
       │
       ├ [0:38] ReminderRepositoryImpl.kt       EDIT · +47 −12
       │         scope check                    ✓ allowed_files
       │         · outbox.enqueue(write) antes de Firestore call
       │         · retry policy injetada via constructor
       │
       └ [0:52] ReminderRepositoryImplTest.kt   NEW  · 138 linhas
                 scope check                    ✓ allowed_files
                 · 5 cenários obrigatórios cobertos
```

**Note:** o hook `pre-edit` checa cada Write/Edit contra
`tasks/TASK-0003.yaml.allowed_files` ANTES de o filesystem ser tocado. Se
falhar → ver **Cena 6**. Conductor não desliga hooks.

---

## Cena 6 — Out-of-scope attempt (55–60s, fluxo alternativo dentro de Apply)

Demonstração: o agent tenta editar `Reminder.kt` pra adicionar um campo. Hook
intercepta.

```
[0:55] ⚡ Apply Mode (continua)
       
       └ tentou editar shared/.../domain/Reminder.kt
       
       🛑 Pre-edit hook bloqueou.
       
       Reminder.kt NÃO está em allowed_files de TASK-0003.
       Regra citada: hard-gates.no-files-outside-allowed-files
                     (workflow-config.yaml:200)
       
       Três caminhos legítimos:
       
         • Atualizar o Task Contract pra incluir Reminder.kt
           (se a mudança REALMENTE pertence a esta task — revisamos o spec)
         
         • Reverter a tentativa
           (esquece o campo novo nesta task)
         
         • Split numa task nova
           (registro como TASK-0008 e implementamos depois, depende de TASK-0003)
       
       O que você quer?
```

User: `split`.

```
[0:58] ✓ Registrado como Finding pendente
       ├ findings/F-2026-05-28-001.yaml         NEW
       │   · context: TASK-0003 implementation
       │   · proposed-task: TASK-0008
       │   · scope: campo `lastSyncedAt` em Reminder
       │   · resolution: open
       └ rationale-trace.yaml                    + entry D-013
       
       Sigo TASK-0003 sem o campo. Você decide depois.
```

**Note:** out-of-scope nunca silencia. Vira artefato em `findings/` (input pro
retrospective). Mentor calmo: firme, mas oferece três saídas legítimas — nunca
só "não."

---

## Cena 7 — Verify Task (60–95s)

Validações declaradas no contrato rodam em sequência. Output real, não fake.

```
[1:00] ✓ Verify Task · TASK-0003
       
       ├ ./gradlew :shared:feature:lembrete-rega:testAndroidHostTest
       │   ⠋ ⠙ ⠹ ⠸ rodando...
       │   [1:18] BUILD SUCCESSFUL · 12 tests · 12 passed
       │
       ├ scripts/observability/check-no-hardcoded-auth-ids.sh
       │   [1:19] ✓ no hardcoded IDs in modified files
       │
       ├ detekt (escopo modificado)
       │   [1:24] ✓ 0 issues
       │
       └ contract-conformance check
           ReminderRepositoryImpl ↔ data-contract-spec.yaml
           [1:32] ✓ all contract operations implemented
                  ✓ no extra operations exposed
       
       Verify: 4/4 ✓
```

Conductor escreve `dispatch-log.jsonl`:

```jsonl
{"timestamp":"...","task":"TASK-0003","phase":"verify","validations":4,"passed":4}
```

**Note:** se um validator falhar → retry até 3x (workflow.task-discipline.
max-retry-on-validator-fail). 3 falhas → escala (ver Edge case 4). Não tem
"continua mesmo assim."

---

## Cena 8 — Pre-commit Review (95–135s)

Conductor despacha review-agent com diff + Task Contract + BDD + gates.

```
[1:35] 🔍 Pre-commit Review (blocking)
       
       └ review-agent
           context pack: 22kb (diff · contract · bdd · gates · L2 patterns)
           ⠋ analisando...
       
       [1:52] review-agent              ⚠ changes requested
       
       Achados:
         · OutboxQueue.kt:42  retry sem jitter — risco de thundering herd
                              se múltiplos clientes voltam online juntos
         · ReminderRepositoryImplTest.kt:96
                              cenário "outbox flush em background" não testa
                              cancelamento (BDD §3.4 exige)
       
       Severidade: medium · medium
       Recomendação: corrigir antes do commit.
```

**Note:** review-agent NÃO altera código. Ele descreve o gap citando o
artefato fonte (BDD §3.4, retry policy do tech-spec). Conductor decide se loop
ou escala.

---

## Cena 9 — Fix loop same-task (135–185s)

Conductor entra em ciclo: aplica correção → re-verify → re-review. Tudo dentro
de `allowed_files` da MESMA task.

```
[1:55] 🔁 Fix loop · TASK-0003
       
       ├ [1:58] OutboxQueue.kt                  EDIT · +11 −3
       │         · jitter ±25% no backoff
       │         scope check                    ✓ allowed_files
       │
       └ [2:08] ReminderRepositoryImplTest.kt   EDIT · +24
                 · cenário cancelamento adicionado
                 scope check                    ✓ allowed_files

[2:10] ✓ Verify Task (re-run)
       ├ testAndroidHostTest                    ✓ 13 tests · 13 passed
       ├ check-no-hardcoded-auth-ids            ✓
       ├ detekt                                 ✓
       └ contract-conformance                   ✓
       
       Verify: 4/4 ✓

[2:25] 🔍 Pre-commit Review (re-run)
       
       └ review-agent
           context pack: 24kb (diff atualizado · achados anteriores · BDD)
           ⠋ analisando...
       
       [2:38] review-agent              ✓ approved
                                        achados anteriores resolvidos
```

**Note:** se review pedir algo fora de `allowed_files` → vira Finding (como na
Cena 6). Same-task only. Conductor não "estica" o contrato pra agradar review.

---

## Cena 10 — Completion Evidence (185–195s)

```
[2:40] 📦 Escrevendo Completion Evidence
       
       evidence/TASK-0003-evidence.json
         {
           "task-id": "TASK-0003",
           "completed-at": "2026-05-28T18:14:22Z",
           "files-changed": [
             "shared/.../OutboxQueue.kt",
             "shared/.../ReminderRepositoryImpl.kt",
             "shared/.../ReminderRepositoryImplTest.kt"
           ],
           "validations": {
             "testAndroidHostTest": {"status": "pass", "tests": 13},
             "observability-check": {"status": "pass"},
             "detekt": {"status": "pass", "issues": 0},
             "contract-conformance": {"status": "pass"}
           },
           "review": {
             "rounds": 2,
             "final-status": "approved",
             "findings-spawned": ["F-2026-05-28-001"]
           },
           "gates-passed": [
             "readiness-must-be-ready",
             "no-files-outside-allowed-files",
             "validations-must-pass",
             "completion-evidence-required",
             "no-invented-behavior"
           ]
         }
       
       ✓ Evidence gravada
```

**Note:** evidence é input do retrospective-agent e do `forge undo`. Sem
evidence ≠ commit. Hard-gate `completion-evidence-required`.

---

## Cena 11 — Atomic Commit (195–205s)

Só os arquivos aprovados são staged. Mensagem segue branch convention do
workflow-config (`feature/{slug}` + ticket prefix).

```
[2:45] 📝 Atomic Commit
       
       Branch atual: feature/lembrete-rega
       
       Staging (apenas allowed_files aprovados):
         shared/.../OutboxQueue.kt                       (NEW)
         shared/.../ReminderRepositoryImpl.kt            (EDIT)
         shared/.../ReminderRepositoryImplTest.kt        (NEW)
       
       Commit:
       
         feat(lembrete-rega): outbox queue + retry policy
         
         Implements TASK-0003 from feature lembrete-rega:
         - OutboxQueue with cap=5 retries + jitter ±25%
         - Repository writes go through outbox.enqueue first
         - 13 tests covering happy path, retry, cancel, TTL
         
         Refs BONSAI-1284
         Task: TASK-0003
         Evidence: evidence/TASK-0003-evidence.json
       
       ✓ commit 7a3f9c2
```

**Note:** branch é validada contra `conventions.branch.pattern`. Se ficar
fora → conductor pergunta antes de commitar (não força um rename). Nunca usa
`--no-verify`, nunca skipa hook.

---

## Cena 12 — Checkpoint update (205–212s)

```
[2:50] 🧠 Atualizando memory
       
       ├ status.json
       │   state           → implementing  (mantém — ainda tem tasks)
       │   last-action     → task-0003-committed
       │   last-action-at  → 2026-05-28T18:15:00Z
       │   current-task    → null
       │   checkpoint-ref  → 7a3f9c2
       │
       ├ history.jsonl
       │   + task-0003-applied
       │   + task-0003-verified
       │   + task-0003-reviewed (rounds: 2)
       │   + task-0003-committed (sha: 7a3f9c2)
       │
       └ checkpoints/
           + TASK-0003.checkpoint.yaml         (resumível por forge undo)
       
       ✓ Checkpoint gravado
```

**Note:** checkpoint é o estado serializado pós-commit. `forge undo` lê
ele pra reverter task+commit+memory de forma atômica (a opção "last action"
é o default do menu interativo).

---

## Cena 13 — Continue ou fechar feature (212–225s)

Conductor consulta `task-breakdown.yaml` pra saber se sobrou task.

```
[2:53] 📋 Próxima task
       
       Status do feature: 3/7 done
         ✓ TASK-0001 · domain model
         ✓ TASK-0002 · repository skeleton
         ✓ TASK-0003 · outbox queue + retry policy  ← acabou
         · TASK-0004 · sync worker
         · TASK-0005 · push local trigger          (paralelizável)
         · TASK-0006 · list screen (Android+iOS)
         · TASK-0007 · create screen (Android+iOS)
       
       Dependências satisfeitas agora: TASK-0004, TASK-0005
       
       Continuar com TASK-0004? [Y / outra / parar aqui]
```

User: `parar aqui`.

```
[2:55] Tá. Salvei tudo. Pra retomar:
         forge implement lembrete-rega
       
       Pronto.
```

**Note:** "parar aqui" não é abort — é encerrar sessão limpa. `state` continua
`implementing`, sem `current-task`. Próximo `forge implement` retoma na lista
de tasks restantes.

---

## Cena 14 — Final task → retrospective auto-trigger (cenário alternativo da Cena 13)

Quando TASK-0007 (a última) acabou de commitar, conductor não pergunta —
roda retrospectiva.

```
[2:53] ✨ Última task do feature concluída.
       
       Status do feature: 7/7 done
         ✓ TASK-0001  ✓ TASK-0002  ✓ TASK-0003  ✓ TASK-0004
         ✓ TASK-0005  ✓ TASK-0006  ✓ TASK-0007
       
       Disparando retrospectiva automática...

[2:55] 🔁 retrospective-agent
       context pack: 56kb (todos os 7 evidence · L1 completo · L2 atual)
       ⠋ analisando padrões e candidatos a promoção...

[3:18] ✓ retrospective-agent finalizou
       
       ├ retrospective.md                       NEW
       │   · 4 patterns detectados
       │   · 2 FNDs registradas
       │   · 1 contradição resolvida
       │
       ├ proposed-evolutions.yaml               NEW
       │   · P-promote-outbox-pattern    confidence 0.92
       │   · P-promote-jitter-default    confidence 0.84
       │   · FND-push-permission-copy    severity medium
       │
       └ status.json
           state → done
           last-action → feature-done
           checkpoint-ref → 7a3f9c2 (último commit)
       
[3:20] 📦 L1 → summary
       
       .claude/memory/L1/lembrete-rega/ comprimido em summary.yaml
         (1 arquivo · 8kb · arquivado em archives/lembrete-rega/)
```

```
[3:22] ✨ Feature done · lembrete-rega
       
       ╭───────────────────── feature-forge · lembrete-rega ──────────────────────╮
       │                                                                          │
       │   📦 ENTREGUE                                                            │
       │     7 tasks · 19 arquivos modificados · 47 testes                        │
       │     2 telas Android + 2 telas iOS                                        │
       │     Outbox queue · Push local · Permission flow                          │
       │                                                                          │
       │   🧠 APRENDIZADOS                                                        │
       │     4 patterns candidatos à L2                                           │
       │     2 FNDs registradas                                                   │
       │     1 contradição resolvida                                              │
       │                                                                          │
       │   ⏱  TEMPO TOTAL                                                         │
       │     plan:        3 min                                                   │
       │     implement:   38 min (7 tasks)                                        │
       │     review:      9 min (12 rounds total · 11 approved · 1 fix-loop)      │
       │                                                                          │
       │   🛑 PENDÊNCIAS                                                          │
       │     1 Finding aberto (F-2026-05-28-001 · lastSyncedAt → TASK-0008)       │
       │     1 open-question deferida (FCM remoto)                                │
       │                                                                          │
       ╰──────────────────────────────────────────────────────────────────────────╯
       
       Próximos passos sugeridos:
         forge evolve              revisar 3 propostas de evolução de L2
         forge plan                começar feature nova
```

**Note:** retrospective NÃO promove direto pra L2 — escreve em
`proposed-evolutions.yaml`. `forge evolve` é o gate humano. Mentor calmo:
"aprendi essas coisas, você decide o que vira regra."

---

## Cena 15 — Closing (post-retrospective, ~3:25)

```
[3:25] 📝 Salvo:
       
       docs/feature-implementation-workflow/features/lembrete-rega/
         retrospective.md · proposed-evolutions.yaml
         7 evidence files · status: done
       
       .claude/memory/L1/lembrete-rega/
         arquivado em archives/lembrete-rega/summary.yaml
       
       💡 Dica: rode `forge evolve` em até 7 dias.
              Propostas envelhecem — confidence cai depois disso.
       
       Pronto.
```

---

## Design points this script crystallizes

| Implicit decision | Practical implication |
|---|---|
| Plan Mode é gate humano antes de Apply | Usuário VÊ tudo que vai mudar antes de mudar. |
| `allowed_files` é absoluto | Hook intercepta em pre-edit — não é checagem post-hoc. |
| Out-of-scope vira Finding, não bloqueio total | Sempre 3 caminhos: contract / revert / split. |
| Retry máximo 3 antes de escalar | workflow.task-discipline.max-retry-on-validator-fail. |
| Pre-commit review é blocking por default | workflow.pre-commit-review.blocking. |
| Evidence é hard-gate pra commit | completion-evidence-required no workflow-config. |
| Commit atômico = só allowed_files staged | Nunca `git add -A`. |
| Retrospective auto-dispara na última task | Sem comando extra (decisão #9 e #11). |
| `forge evolve` é gate humano pra L2 | retrospective propõe, usuário aprova. |
| Total por task: 90–300s | Plan Mode é o pacing — humano controla. |

---

## Edge cases the script needs to handle

### 1. No tasks remaining (feature já estava done)

```
[0:03] Detectei que lembrete-rega já está com state=done.
       
       7/7 tasks fechadas. Retrospectiva já rodou (2026-05-28).
       
       Caminhos:
         • forge plan — começar feature nova
         • forge status lembrete-rega — ver o resumo final
         • forge evolve — se ainda não revisou as propostas
       
       Nada pra implementar aqui.
```

### 2. Dependência não satisfeita

User: `forge implement TASK-0005`.

```
[0:04] 🛑 TASK-0005 tem dependência aberta.
       
       task-breakdown.yaml diz:
         TASK-0005 depende de TASK-0003 (status: done · ok)
                            TASK-0004 (status: pending · NÃO ok)
       
       Implementar TASK-0005 antes de TASK-0004 quebra a sequência
       declarada no plano — sync worker (TASK-0004) provê o callback
       que push local (TASK-0005) consome.
       
       Caminhos:
         • Implementar TASK-0004 primeiro (recomendado)
         • Revisar o task-breakdown se a dependência mudou
           (não rode forge plan de novo — usa forge evolve no contract)
         • Forçar mesmo assim → recuso. no-invented-behavior gate.
       
       O que prefere?
```

**Note:** mentor calmo é firme. "Forçar" não é caminho — fica explícito que o
gate barra.

### 3. Out-of-scope edit (cobre Cena 6 + extensão)

Já demonstrado na Cena 6. Variação: se o usuário tentar `Y, atualiza contract`
→ conductor pergunta:

```
       Atualizar o Task Contract requer revisitar o plano.
       
       Mudanças que vou aplicar:
         · tasks/TASK-0003.yaml.allowed_files += Reminder.kt
         · tech-spec.md §6.2: justificar campo lastSyncedAt aqui
         · rationale-trace.yaml: nova entry D-013
       
       Tem certeza? [Y / não, melhor split]
```

### 4. Validator falha 3x

```
[1:18] ⚠ testAndroidHostTest falhou.
       [1:25] Retry 1/3...
       [1:32] ⚠ falhou.
       [1:39] Retry 2/3...
       [1:46] ⚠ falhou.
       [1:53] Retry 3/3...
       [2:00] 🛑 falhou 3x na mesma causa.
       
       Última saída relevante:
         ReminderRepositoryImplTest > outbox flushes on reconnect
         expected: 3 writes, got: 2
       
       Minha hipótese:
         · TestDispatcher não está avançando o backoff (jitter random
           pode estar gerando delay > advanceTimeBy(10_000))
         · ou outbox.flush() está cancelando o último write antes do assert
       
       Caminhos:
         • Você inspeciona o teste e me orienta (cole o trecho que parece off)
         • Pausa — eu não consigo passar disso aqui
         • Reverter a task pro estado pré-Apply (forge undo — escolher "last action")
       
       Decisão é sua.
```

**Note:** conductor escala com hipótese — nunca silencia falha repetida.

### 5. Pre-commit review reprova (mostrada na Cena 9 happy path)

Variação: se o review ainda reprovar após 3 rounds de fix-loop → escala como
Edge case 4 ("review bloqueado, eu não consigo fechar isso aqui").

### 6. User aborts mid-task

User digita `para` durante Apply Mode.

```
[0:45] Pausando...
       
       Estado salvo:
         · plan-mode-approved             ✓
         · arquivos editados parcialmente:
             OutboxQueue.kt (94 linhas escritas)
             ReminderRepositoryImpl.kt (não tocado ainda)
         · status.json:
             state          → paused
             current-task   → TASK-0003
             sub-state      → applying
         · checkpoint salvo               ✓ (pre-apply state preservado)
       
       Pra retomar:
         forge implement lembrete-rega
       
       Vou retomar exatamente onde parou (OutboxQueue.kt parcial).
       Se preferir descartar e refazer:
         forge undo            (e escolher "last action" no menu)
       
       Tá tudo gravado.
```

**Note:** pausa é estado de primeira classe — não é abort. `state=paused`
libera o lock (memory.md §L1 lock) pra usuário rodar `forge reconfigure`
enquanto pausado (qualquer mutação de cards mora dentro do menu interativo
de reconfigure — ver `docs/design/06-command-surface.md`).

### 7. Card conflict mid-implement (não deveria acontecer)

Per memory.md, mutar cards com L1 ativo é refused. Mas se a integridade quebrar
(sha256 mismatch detectado pelo doctor durante run):

```
[1:05] 🛑 Conflito de cards detectado mid-implement.
       
       Quando esta task começou:
         firebase-firestore  sha256: e3b0c4...
       
       Agora no disco:
         firebase-firestore  sha256: 9a7d22...  ⚠ MUDOU
       
       Outro processo alterou um card local enquanto o agente estava no meio
       de TASK-0003. Continuar aqui = inconsistência entre o que foi planejado
       e o que está vigente.
       
       Estou parando. Sem commit.
       
       Caminhos:
         • Inspecionar o card no disco (.claude/cards/firebase-firestore/)
         • forge doctor — diagnosticar integridade geral
         • forge undo — reverter Apply parcial pro estado pré-task (opção "last action")
       
       Não invento.
```

**Note:** nunca deveria acontecer (lock mechanism existe). Mas se acontecer,
mentor calmo recusa. `forge undo` é a saída.

### 8. Retrospective auto-trigger com Findings pendentes

Quando última task fecha mas tem Findings de Cenas 6/9:

```
[2:55] 🔁 retrospective-agent
       
       ⚠ 1 Finding pendente detectado (F-2026-05-28-001).
       
       Vou registrar no retrospective.md mas NÃO vou promover automaticamente
       pra L2 — Findings pendentes precisam de resolução antes.
       
       proposed-evolutions.yaml vai marcar:
         F-2026-05-28-001 → action-required: resolve-or-task
       
       Continua normalmente.
```

**Note:** Finding aberto não bloqueia feature-done — mas marca a próxima
revisão. `forge evolve` vai surfacear isso.

---

## Voice examples in this flow

| Moment | Tone | Example |
|---|---|---|
| Entry / resume | Warm | "Bom dia. Você parou ontem com TASK-0002 verificado. Sigo daqui?" |
| Task selection rationale | Didactic | "Critical path · 4 downstream · sem dependência aberta. Topa essa?" |
| Plan Mode reveal | Transparent | "3 arquivos a modificar (1 NEW, 1 EDIT, 1 NEW de teste)." |
| Out-of-scope block | Firm + 3 paths | "Reminder.kt NÃO está em allowed_files. Três caminhos legítimos:" |
| Validator retry | Hypothesis-driven | "Minha hipótese: TestDispatcher não está avançando o backoff." |
| Review approve | Brief | "review-agent ✓ approved · achados anteriores resolvidos" |
| Commit | Quiet confidence | "✓ commit 7a3f9c2" |
| Retrospective on last task | Didactic | "Aprendi essas coisas, você decide o que vira regra." |
| Feature done | Expressive (closing-style) | "✨ Feature done · lembrete-rega" |
| Closing | Practical | "Pra retomar / Pronto." |

---

## What this script does NOT do

- Does not edit any file outside `tasks/TASK-{n}.yaml.allowed_files`
- Does not skip Plan Mode (workflow.task-discipline.require-plan-mode-before-apply)
- Does not skip Verify Task (workflow.task-discipline.require-verify-task-before-commit)
- Does not skip Pre-commit Review when blocking=true
- Does not auto-promote L1 patterns to L2 (retrospective proposes; `forge evolve` decides)
- Does not run `git add -A` — só allowed_files aprovados
- Does not use `--no-verify` ou pular hooks
- Does not silence validator failures — escala com hipótese
- Does not implement tasks com dependência aberta — gate firme
- Does not estimate effort/time — out-of-scope (decision #5)
