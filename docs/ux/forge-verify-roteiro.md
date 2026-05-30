# `forge verify` — roteiro end-to-end

The cinematic UX of `forge verify`. Read-only verification gate. Cada linha
que aparece no terminal, com timing real, voz em mentor-calmo. Sibling
document a `forge-init-roteiro.md` e `forge-plan-roteiro.md` — mesmo estilo,
mesma densidade. Mais curto: zero diálogo com usuário em caminho feliz.

## Context

- Read-only — NUNCA modifica código, package, ou memory L1/L2
- Roda os validadores na ordem do hard-gates set (workflow-config §workflow.hard-gates)
- Três escopos: task único · feature inteira · feature inferida (sem arg)
- Estado L1 `status.json` transita: `implementing` → `verifying` → (de volta a `implementing` se ✓, ou permanece `verifying` se 🛑)
- Total budget: 4–18s (fast feedback loop, sem diálogo no happy path)

---

## Modos de invocação

```text
forge verify                         # sem arg — verifica última task em curso
                                     # ou feature corrente (se entre tasks)
forge verify TASK-0003               # task específica
forge verify lembrete-rega           # feature inteira contra readiness gate (slug)
forge verify .                       # feature corrente (alias do diretório ativo)
```

Resolução de escopo (silenciosa, < 50ms):

1. Se arg começa com `TASK-` → task-scope
2. Se arg é `.` ou bate com um slug de feature ativa → feature-scope
3. Se sem arg → lê `.claude/memory/L1/*/status.json`, escolhe o único
   feature com `state ∈ {implementing, verifying}`. Se mais de um, pergunta.
4. Se nenhum feature ativo → ver **Edge case 5**

---

## Cena 1 — Entrada + scope resolution (0.0–0.4s)

```
$ forge verify TASK-0003

   ╭──────────────────────────────────────────╮
   │  feature-forge · verify                  │
   │  Read-only. Nada de mudar código.        │
   ╰──────────────────────────────────────────╯

[0:00] Resolvendo escopo...
       ├ arg                                  TASK-0003
       ├ feature                              lembrete-rega  (active)
       ├ task path                            docs/.../features/lembrete-rega/tasks/TASK-0003.yaml
       ├ task title                           "ReminderRepository + outbox queue"
       ├ task state                           applied (last edit: 2m atrás)
       └ allowed_files                        4 declarados
```

**Note:** scope resolution é instantâneo — só lê o YAML da task e o status.json
da feature. Nenhuma chamada externa, nenhum I/O pesado. Se a task não existe,
salta direto pra Edge case 1.

---

## Cena 2 — Status snapshot (0.4–0.6s)

Antes de rodar validadores, o conductor mostra o que vai verificar e contra
quais regras. Transparência — sem isso o usuário não confia no veredito.

```
[0:00] 🔍 Verificando TASK-0003
       
       Escopo:        task
       Feature:       lembrete-rega
       Strictness:    strict  (workflow.readiness-strictness)
       Hard gates:    5 (readiness · allowed-files · validators · evidence · no-invented)
       Validadores:   8 a rodar
       
       Vou rodar tudo e só te mostrar o que importa.
```

**Note:** "só te mostrar o que importa" é promessa: passes verbosos colapsam em
uma linha resumo; falhas explodem em detalhe. Não inunda terminal com green
checkmarks.

L1 `status.json` transita aqui: `implementing` → `verifying`. Estado salvo
antes do primeiro validador rodar — se algo crashar, próximo `forge verify`
sabe que estava no meio.

---

## Cena 3 — Validator cascade (0.6–4.2s, cinematográfico)

Cada validador roda sequencialmente. Tempos reais: 100ms–2s por validador.
Pass → linha resumo verde. Fail → para a cascade, expande em scene 4.

```
[0:01] Rodando validadores
       
       ├ validate_feature_package.py            ✓ 124ms
       │   16/16 documentos presentes
       │
       ├ validate_readiness.py                  ✓ 218ms
       │   readiness: ready · 0 blocking questions
       │
       ├ validate_task_contract.py              ✓ 156ms
       │   TASK-0003 conforma · schema-v1
       │
       ├ validate_data_contract.py              ✓ 312ms
       │   data-contract-spec.yaml válido · 3 entidades · 2 índices Firestore
       │
       ├ validate_screen_analysis.py            ✓ 245ms
       │   3 telas · 18 estados · todas transições documentadas
       │
       ├ validate_backend_e2e.py                ✓ 482ms
       │   backend_e2e em test-strategy · 4 cenários cobertos
       │
       ├ check_no_invented_behavior.py          ✓ 1.4s
       │   diff cross-referenced com contracts · zero termos vagos
       │
       └ check_files_in_allowed_files.py        ✓ 198ms
           diff tocou 4 arquivos · todos declarados em allowed_files
```

**Note:** ordem importa. `validate_feature_package` primeiro — se o package
está incompleto, nenhum outro validador faz sentido. `check_no_invented_behavior`
é o mais lento porque cruza diff × contracts. `check_files_in_allowed_files`
por último porque depende do diff git já estar coerente.

Cada linha aparece quando o validador termina (não simulado). O usuário vê o
ritmo real do trabalho — alguns rápidos, outros pensam.

---

## Cena 4 — Drill-down em falha (variante hard-fail)

Quando um validador falha, a cascade **para**. Conductor expande a falha em
detalhe didático: WHAT, WHERE, WHY, HOW. Mentor calmo — sem alarme, sem
moralizar.

```
[0:01] Rodando validadores
       
       ├ validate_feature_package.py            ✓ 124ms
       ├ validate_readiness.py                  ✓ 218ms
       ├ validate_task_contract.py              ✓ 156ms
       ├ validate_data_contract.py              ✓ 312ms
       ├ validate_screen_analysis.py            ✓ 245ms
       ├ validate_backend_e2e.py                ✓ 482ms
       │
       ├ check_no_invented_behavior.py          🛑 1.4s  FAIL
       │
       └ check_files_in_allowed_files.py        — não rodado (cascade parou)

[0:04] 🛑 check_no_invented_behavior.py
       
       O que falhou:
         Encontrei comportamento no diff que não tem fonte declarada nos
         contracts. Tradução: o código está fazendo algo que ninguém pediu.
       
       Onde:
         shared/feature/lembrete-rega/.../ReminderRepository.kt:87-94
       
         87  override suspend fun delete(id: String): Result<Unit> {
         88      return try {
         89          firestoreClient.collection("reminders")
         90              .document(id)
         91              .delete()
         92              .await()
         93          analytics.logEvent("reminder_deleted_soft")  // ← inventado
         94          Result.success(Unit)
       
       Por que importa:
         · analytics-spec.yaml lista 4 eventos:
             reminder_create_attempt · reminder_create_success
             reminder_create_error  · reminder_list_view
         · "reminder_deleted_soft" não está em nenhum lugar do plano
         · Hard gate: no-invented-behavior (workflow.hard-gates)
         · Se passar, métrica nova entra em prod sem schema, sem revisão
       
       Três caminhos pra resolver:
       
         1) Remover a linha 93 — evento não fazia parte da task.
            Mais provável se foi cópia de outra feature.
         
         2) Adicionar o evento ao analytics-spec.yaml + re-verificar.
            Pra propor mudança no plano com rastreabilidade: digite `para`
            pra abortar este verify, depois rode `forge plan lembrete-rega`
            de novo — auto-resume parte do checkpoint mais recente e você
            corrige `reminder_deleted_soft` no spec interativamente.
         
         3) Se o evento É necessário e estava implícito no ticket,
            abre o ticket pra revisão — sem plan amend, eu bloqueio.
       
       Sem auto-fix aqui — escolha humana.
```

**Note:** este é o coração do verify. Falha sem caminho de resolução é falha
inútil. Mentor calmo SEMPRE oferece 3 saídas — uma conservadora (remover),
uma estendendo escopo (amend), uma escalando (ticket). Nunca diz "consulte a
documentação." Cita o arquivo, a linha, o contract violado, a regra do gate.

Validadores que não rodaram aparecem com `—` (não com `?` ou em branco) — deixa
claro que foi a cascade que parou, não que estão broken.

---

## Cena 5 — Warning section (variante mixed)

Warnings são não-bloqueantes. Aparecem AGRUPADAS no fim do cascade, antes do
verdict. Não interrompem o fluxo.

```
[0:03] Rodando validadores
       
       ├ validate_feature_package.py            ✓ 124ms
       ├ validate_readiness.py                  ✓ 218ms
       ├ validate_task_contract.py              ⚠ 156ms  (1 warning)
       ├ validate_data_contract.py              ✓ 312ms
       ├ validate_screen_analysis.py            ✓ 245ms
       ├ validate_backend_e2e.py                ⚠ 482ms  (2 warnings)
       ├ check_no_invented_behavior.py          ✓ 1.4s
       └ check_files_in_allowed_files.py        ✓ 198ms

[0:03] ⚠ 3 warnings (não bloqueiam — pra você saber)

       validate_task_contract:
         · TASK-0003 não declara estimated-files-touched
           (campo opcional · ajuda no review pre-commit)
       
       validate_backend_e2e:
         · Cenário "delete reminder offline" tem assertions só na lista,
           não no documento Firestore — coverage parcial
         · test-strategy.yaml lista 4 cenários · só 3 têm @Tag("e2e")
           (não acha o tag no 4º? pode ter typo)
       
       Quer que eu mostre como ajustar cada um? Responde aqui.
```

**Note:** warnings agrupados por validador, com explicação humana. Pergunta de
ajuda no fim — não força, oferece. Se usuário ignora, segue pro verdict. Mentor
calmo respeita ritmo do leitor.

---

## Cena 6 — Verdict box (4.2–4.5s)

O resumo cinemático. Três sabores: ✅ green · ⚠ warn-only · 🛑 block. Sempre
single canvas.

### Variante green (todos passaram, sem warnings)

```
[0:04] ✅ Verify clean

       ╭───────────────── feature-forge · TASK-0003 ─────────────────╮
       │                                                              │
       │   📋 ESCOPO                                                  │
       │     task · lembrete-rega                                     │
       │                                                              │
       │   🔍 VALIDADORES                                             │
       │     8/8 pass · 0 warn · 0 fail                               │
       │                                                              │
       │   ⏱  TEMPO                                                   │
       │     3.5s total · check_no_invented_behavior foi o mais lento │
       │                                                              │
       │   📁 ARQUIVOS                                                │
       │     4 tocados · 4 em allowed_files (100%)                    │
       │                                                              │
       │   ✓ READY TO COMMIT                                          │
       │                                                              │
       ╰──────────────────────────────────────────────────────────────╯
       
       Próximo passo: 
         forge implement TASK-0004     próxima task da feature
         forge status                  ver o board completo
```

L1 `status.json` transita: `verifying` → `implementing`. Não vai pra `done`
porque a task não fechou a feature — só implement-conductor fecha.

**Note:** "READY TO COMMIT" é literal — pre-commit hook só passa nessa
condição. Mas verify **não commita** — separação clara entre verificar e
shipar.

### Variante warn-only (todos passam, mas N warnings)

```
[0:04] ⚠ Verify clean com avisos

       ╭───────────────── feature-forge · TASK-0003 ─────────────────╮
       │   📋 ESCOPO            task · lembrete-rega                  │
       │   🔍 VALIDADORES       8/8 pass · 3 warn · 0 fail            │
       │   📁 ARQUIVOS          4 tocados · 4 em allowed_files        │
       │   ⚠ WARNINGS           1 task_contract · 2 backend_e2e       │
       │   ✓ READY TO COMMIT  (warnings não bloqueiam)                │
       ╰──────────────────────────────────────────────────────────────╯
       
       Pode commitar. Warnings ficam no log
       (.claude/memory/L1/lembrete-rega/verify-log.jsonl).
```

**Note:** warnings ficam logados em `verify-log.jsonl`. Não somem entre runs.
v1 só loga; futura versão pode escalar tom se usuário ignorar repetido.

### Variante hard-fail (≥ 1 validador falhou)

```
[0:04] 🛑 Verify block

       ╭───────────────── feature-forge · TASK-0003 ─────────────────╮
       │                                                              │
       │   📋 ESCOPO            task · lembrete-rega                  │
       │   🔍 VALIDADORES       6 pass · 0 warn · 1 fail · 1 skipped  │
       │   📁 ARQUIVOS          4 tocados (allowed-files não checado) │
       │                                                              │
       │   🛑 BLOCKING                                                │
       │     check_no_invented_behavior                               │
       │       ReminderRepository.kt:93 · evento não declarado        │
       │                                                              │
       │   🛑 NOT READY TO COMMIT                                     │
       │                                                              │
       ╰──────────────────────────────────────────────────────────────╯
       
       Veja três caminhos detalhados acima. Sem auto-fix —
       a decisão de qual caminho seguir é sua.
       
       Quando ajustar, rode de novo:
         forge verify TASK-0003
```

L1 `status.json` permanece em `verifying` — sinaliza pro pre-commit hook que o
estado não está limpo. Próximo `forge verify` retoma daí.

**Note:** "skipped: 1" referencia o `check_files_in_allowed_files` que não
rodou porque cascade parou. Box mostra o que importa pra commit decision —
não bagunça com detalhes que já foram expandidos acima.

---

## Cena 7 — Mentor-calmo next-steps (4.5–4.6s)

Mensagem de fechamento varia conforme verdict. Sempre didática, nunca empurrando.

| Verdict | Closing |
|---|---|
| ✅ green (task) | `forge implement TASK-XXXX` ou `forge status` |
| ✅ green (feature) | `forge implement TASK-XXXX` (próxima) ou `git commit` se todas done |
| ⚠ warn-only | "Pode commitar" + log file location |
| 🛑 block | "Veja os 3 caminhos. Rode de novo quando ajustar." |

---

## Cena 8 — Feature-scope variant (slug ou `.`)

`forge verify lembrete-rega` muda a entrada e o output, mas o cascade é o
mesmo. Diferenças:

```
$ forge verify lembrete-rega

   ╭──────────────────────────────────────────╮
   │  feature-forge · verify                  │
   │  Read-only. Nada de mudar código.        │
   ╰──────────────────────────────────────────╯

[0:00] Resolvendo escopo...
       ├ arg                                  lembrete-rega  (feature slug)
       ├ feature state                        implementing
       ├ tasks total                          7
       ├ tasks done                           5 (TASK-0001 → TASK-0005)
       ├ tasks pending                        2 (TASK-0006, TASK-0007)
       └ readiness                            ready (last check: 2h)
```

```
[0:00] 🔍 Verificando feature inteira: lembrete-rega
       
       Escopo:        feature
       Inclui:        readiness gate + todas tasks done + cross-task consistency
       Validadores:   8 (mesmo set, mas com escopo expandido)
       
       Vou rodar tudo. Isso leva ~10s porque é a feature toda.
```

Cascade roda igual, mas:

- `validate_task_contract.py` roda **N vezes** (uma por task done) e o output
  resume: `7/7 task contracts conformes (ou X/Y se houver fail)`
- `check_files_in_allowed_files.py` agrega o diff total da feature contra
  union(allowed_files) de todas tasks
- `check_no_invented_behavior.py` cruza com contracts da feature inteira
- Tempo total: ~10s em vez de ~4s

Verdict box ganha campo extra:

```
       │   📋 TASKS                                                   │
       │     7 total · 5 done · 2 pending                             │
       │     Verify cobre só as 5 done — pendentes ficam de fora      │
```

**Note:** feature-scope é o gate de pre-merge. Costuma rodar antes de abrir PR.
v1 não tem comando próprio de ship (out-of-scope, ver
`docs/design/06-command-surface.md`) — o output do feature-verify é consumido
pelo CI ou pelo desenvolvedor abrindo PR manualmente.

---

## Cena 9 — Edge cases

### 1. Task não encontrada

```
$ forge verify TASK-9999

[0:00] 🔍 Tentando resolver TASK-9999...
       
       Não achei essa task na feature ativa (lembrete-rega).
       
       Tasks que existem na feature:
         · TASK-0001  Domain models + state
         · TASK-0002  Network layer
         · TASK-0003  ReminderRepository + outbox queue
         · TASK-0004  ViewModel + use cases
         · TASK-0005  Compose list screen
         · TASK-0006  SwiftUI list screen
         · TASK-0007  Push notification setup
       
       Você quis dizer TASK-0007? (mais próximo numericamente)
       
       Ou rode `forge status` pra ver tudo.
```

**Note:** fuzzy match numérico simples (distância ≤ 2 ou substring). Não tenta
adivinhar mais que isso — se o usuário digitou aleatório, lista as 7 e deixa
escolher.

### 2. Feature não está em estado implementing

```
$ forge verify TASK-0003

[0:00] Resolvendo escopo...
       ├ arg                                  TASK-0003
       ├ feature                              lembrete-rega
       └ feature state                        planning  🛑

[0:00] 🛑 Não posso verificar agora.
       
       lembrete-rega ainda está em `planning` — o forge plan não terminou
       ainda. Tasks só verificam depois que Apply Mode toca arquivos reais.
       
       O que isso significa:
         · plan-feature-handoff.json não foi assinado
         · readiness pode não estar `ready`
         · não tem código pra verificar — verify ia falhar tudo
       
       Caminhos:
         · Termina o plan: `forge plan lembrete-rega` (auto-resume)
         · Vê o status: `forge status`
         · Se planejou em outro lugar e quer pular pro implement,
           rode `forge plan lembrete-rega` — quando o plano detectar que
           os artefatos já estão escritos, o conductor pergunta se quer
           só validar o handoff (sem refazer waves).
       
       Estado não muda. Volta quando estiver pronto.
```

**Note:** verify NUNCA invalida estado. Se feature está em planning, sai sem
escrever nada. O hard gate `require-plan-mode-before-apply` (workflow §task-discipline)
funciona junto: o usuário não consegue NEM editar código sem readiness=ready,
então normalmente esse estado nem aparece.

### 3. Validador interno quebrado

Conductor isola o validador broken, segue rodando os outros, reporta no fim.

```
[0:04] ⚠ validate_task_contract.py crashou (não é falha da sua task)
       
       Erro do script:
         ImportError: cannot import name 'TaskContractV1'
         (.../validate_task_contract.py:47)
       
       O que isso significa:
         · O validador está quebrado, não a sua task
         · Os outros 7 validadores passaram
         · Não posso garantir que TASK-0003 conforma sem ele rodar
       
       Caminhos:
         · `forge doctor` pra checar ambiente
         · `forge update` pra reinstalar validador
         · Reportar bug com o traceback acima
       
       Verify não bloqueia commit aqui — você decide. Vou marcar como
       `degraded` no log.
```

L1 `status.json` ganha campo extra: `verify-degraded: true`. Próximo verify
limpa se rodar ok.

**Note:** isola problema sem dramatizar. Aceita seguir em modo degraded mas
marca pra rastreio.

### 4. Graph desatualizado

```
[0:00] Resolvendo escopo...
       ├ arg                                  TASK-0003
       ├ feature                              lembrete-rega
       └ ⚠ graph.db desatualizado  (4h · 8 arquivos modificados desde)

[0:00] 🔍 Verificando TASK-0003
       
       Graph stale. Posso:
         • Rebuild agora (~10s) — recomendado
         • Seguir com graph velho (marca verify como `graph-stale`)
         • Cancelar
       
       O que prefere?
```

**Note:** verify oferece rebuild inline mas não força. Hook
`post-edit-codebase-graph.sh` normalmente mantém quente — se stale, alguma
edição passou fora dele (git pull, branch switch). Alternativa: rodar
`forge reconfigure` e escolher "rebuild graph" no menu (sem flag).

### 5. Sem feature ativa

```
$ forge verify

[0:00] Resolvendo escopo...
       └ nenhuma feature em implementing nem verifying  🛑

[0:00] Sem feature em curso — não tenho o que verificar.
       
       Caminhos:
         · `forge plan` pra começar feature nova
         · `forge plan {slug}` pra retomar feature pausada
         · `forge status` pra ver o board
         · `forge verify {slug}` pra verificar mesmo
           sem estar ativa
       
       Estado não muda. Tudo limpo.
```

**Note:** mentor calmo lista os 4 caminhos prováveis. Não pergunta — sugere.
Sair sem fazer nada é melhor que chutar.

---

## Voice examples

| Momento | Tom | Exemplo |
|---|---|---|
| Cinematic intro | Calmo, contextual | "Read-only. Nada de mudar código." |
| Cascade per-validator | Telegráfico | "validate_data_contract.py ✓ 312ms" |
| Hard fail explanation | Didático, 3-caminhos | "Sem auto-fix — escolha humana." |
| Warning section | Informativo, não-alarmista | "não bloqueiam — pra você saber" |
| Verdict green | Conciso, satisfeito | "✓ READY TO COMMIT" |
| Verdict block | Firme, ofertando caminhos | "Quando ajustar, rode de novo." |
| Validator broken | Isolando problema | "É o validador, não a sua task" |
| Graph stale | Transparente | "vou marcar verify como `graph-stale`" |
| Sem feature ativa | Sem pressão | "Estado não muda. Tudo limpo." |

---

## Design points this script crystallizes

| Implicit decision | Practical implication |
|---|---|
| Verify é **estritamente read-only** | Nunca chama Edit, nunca propõe auto-fix. Mantém separação plan/implement/verify. |
| Cascade **para** no primeiro fail | Performance + clareza. Validadores depois do break ficam `—`. |
| Warnings agrupados no fim | Não interrompem flow. Aparecem em uma única seção, fácil scanning. |
| Falha sempre vem com **3 caminhos** | Mentor calmo. Nunca "consulte docs." |
| Sem diálogo no happy path | < 5s end-to-end. Fast feedback loop. |
| Verdict é **single canvas** | Aesthetic parity com init/plan. |
| L1 status.json transita explicit | `implementing` → `verifying` → de volta. Não cria estados fantasma. |
| Validator interno broken não bloqueia | Modo `degraded` registrado, mas verify segue. Isolamento de falha. |
| Feature-scope é mesma cascade, escopo expandido | Sem código duplicado conceitual. Mesmo set de gates. |
| Graph stale é opt-in rebuild | Verify não decide por você se vale 10s. Pergunta. |

---

## What this script does NOT do

- Não modifica código (read-only)
- Não modifica package (read-only)
- Não modifica L1/L2 memory (exceto `status.json` state transition e `verify-log.jsonl`)
- Não propõe auto-fix — só explica WHAT/WHERE/WHY/HOW
- Não commita — separação clara entre verify e shipar
- Não promove L1 → L2 (`forge evolve` faz isso depois)
- Não roda testes de integração de verdade (essa é responsabilidade do CI ou de `forge test`)
- Não fala com ticketing (Jira post-back só em plan/implement closing)
- Não decide entre os 3 caminhos numa falha — decisão é humana

---

## Sequência típica

```text
forge plan                    →  readiness=ready
forge implement TASK-0001     →  Apply Mode toca código
forge verify TASK-0001        →  ✓ green
forge implement TASK-0002     →  Apply Mode toca código
forge verify TASK-0002        →  🛑 block (3 caminhos · usuário ajusta)
forge verify TASK-0002        →  ✓ green
...
forge verify {slug}           →  pre-merge gate
git commit + abrir PR (manual)→  ship (sem comando próprio em v1)
```

Verify é o **loop interno mais frequente** do workflow. Rápido e silencioso no
caminho feliz, didático no caminho ruim.
