<!-- generated-by: gsd-doc-writer -->

# Comandos do dia a dia

> **Nível:** intermediário  
> **Tempo de leitura:** 15 min  
> **Pré-requisito:** `forge init` já rodou no seu projeto (veja
> [Primeiros passos](getting-started.md))

---

Este guia cobre os 13 comandos user-facing do forge na prática. Para cada um você vai ver:

- **O que faz** — descrição direta
- **Quando usar** — cenário concreto do dia a dia
- **Exemplo** — input e output simulados
- **Fluxograma de decisão** textual

No final tem uma [árvore de decisão](#árvore-de-decisão) pra consulta rápida.

---

## forge plan — Planejar uma feature

**O que faz:** Conduz o pipeline de planejamento (Waves A–E) para transformar
uma ideia em artefatos rastreáveis: intake, PRD, specs, tech-spec, tasks.

**Quando usar:** Você tem uma feature nova, um bug pra corrigir, ou um
refactor. Em vez de sair codando, você planeja primeiro.

**Subtypes:**

| Subtype | Quando usar | Diferença |
|---|---|---|
| `product` | Feature nova (ex.: "tela de login") | Waves A–E completas, começa com PRD |
| `bugfix` | Bug reportado (ex.: "crash ao abrir tela") | Pula PRD, exige regression-test-que-falha antes da correção |
| `refactor` | Melhoria interna sem mudar comportamento | Contrato `no-behavior-change`, pula intake |
| `spike` | Investigação técnica | Waves leves, sem tasks |
| `chore` | Tarefa de infra/config | Waves mínimas |

**Exemplo:**

```bash
$ forge plan login-screen

┌─ feature-forge ─────────────────────────────────────┐
│ Planejando: login-screen                             │
│ Subtype: product                                     │
└──────────────────────────────────────────────────────┘

Wave A — Intake + PRD
  ✔ feature-intake.md escrito
  ✔ feature-prd.md escrito
  ──── Pressione Enter pra continuar ────

Wave B — Screens + Contracts (8 artefatos)
  ✔ screen-analysis.md escrito
  ✔ bdd.md + bdd.json escritos
  ✔ ui-state-spec.yaml escrito
  ✔ navigation-spec.yaml escrito
  ✔ data-contract-spec.yaml escrito
  ✔ analytics-spec.yaml escrito
  ✔ test-strategy.yaml escrito
  ──── Pressione Enter pra continuar ────

Wave C — Tech spec
  ✔ tech-spec.md escrito
  ──── Pressione Enter pra continuar ────

Wave D — Tasks
  ✔ task-breakdown.yaml escrito
  ✔ tasks/TASK-0001.yaml ... TASK-0005.yaml escritos
  ──── Pressione Enter pra continuar ────

Wave E — Readiness
  ✔ readiness-review.md escrito
  ✔ Status: ready ✅

Próximo passo: forge implement login-screen
```

**Fluxograma:**

```
forge plan <slug>
    │
    ├── Subtype?
    │   ├─ product  → Waves A(PRD) → B → C → D → E
    │   ├─ bugfix   → Wave B → C → D → E (+ regression test first)
    │   ├─ refactor → Waves B → C → D → E (no-behavior-change)
    │   ├─ spike    → Wave A (leve) → E
    │   └─ chore    → Wave D → E
    │
    └── Resultado: readiness=ready → "forge implement <slug>"
```

---

## forge implement — Executar tarefa por tarefa

**O que faz:** Pega a próxima tarefa do plano, mostra o contrato
(arquivos permitidos, BDDs cobertos, gates), e guia a execução.

**Quando usar:** Você tem um plano com `readiness=ready` e quer começar a
codar a primeira (ou próxima) tarefa.

> **Nota:** `forge implement` (v1) exibe o contrato da tarefa e instrui o dev sobre o que implementar; a escrita de código é manual. Automação completa via Claude Code está planejada para Phase 6 do roadmap (vide `docs/design/02-phases.md`) e ainda não foi entregue.

**Exemplo:**

```bash
$ forge implement login-screen

┌─ feature-forge ─────────────────────────────────────┐
│ Feature: login-screen                                │
│ Tarefa: TASK-0003 — Implementar LoginScreen composable│
│ Contrato:                                            │
│   📄 Arquivos: app/src/main/java/.../LoginScreen.kt  │
│   🧪 BDD: CT-001, CT-002 (login com sucesso)        │
│   🚫 Fora do escopo: forgotten-password, signup      │
└──────────────────────────────────────────────────────┘

Plano aprovado? (sim/nao/pular): sim
  ✔ Contrato exibido — implemente os arquivos listados
  ✔ Commit: feat(login): implementa LoginScreen composable
  ✔ TASK-0003 marcada como done ✅

Próxima: TASK-0004 — Conectar ViewModel ao Firebase Auth
Quer continuar? (sim/nao): sim
```

**Quando o implement detecta algo fora do escopo:**

```
🔍 EDIT DETECTADO fora dos arquivos permitidos:
   modified: app/src/main/java/.../SettingsScreen.kt
┌─ 3 caminhos ───────────────────────────────────────┐
│ 1. ✅ Está no escopo — ajustar contrato (add file)  │
│ 2. ⏸️  Pausar — investigar antes de continuar       │
│ 3. 🛑 Abortar tarefa e reverter mudanças            │
└─────────────────────────────────────────────────────┘
Escolha: 2
```

---

## forge status — Ver o que está rolando

**O que faz:** Board read-only com 6 seções: projeto, features ativas, memória,
evoluções pendentes, saúde do doctor, atividade recente.

**Quando usar:** "O que tem em andamento?" — no meio do dia, antes de começar
uma nova tarefa, ou pra mostrar pro time.

**Exemplo:**

```bash
$ forge status

┌─ forge status ──────────────────────────────────────┐
│ Projeto: MeuApp                                       │
│ Preset: kmp-mobile · Cards: 8 · forge: 1.2.0        │
│                                                       │
│ Features ativas:                                     │
│  login-screen      ── planning (ready)     há 2h     │
│  fix-crash-auth    ── implementing (WIP)   há 30min  │
│                                                       │
│ Memória: mem: 45 notas (32 live) · L1: 2 ativas · 0 arch │
│ Evoluções pendentes: 3                                │
│ Doctor: rodado há 15min (saudável ✅)                │
│                                                       │
│ Últimos eventos:                                     │
│  14:30  implement fix-crash-auth  TASK-0002 done     │
│  13:00  plan    login-screen      readiness=ready    │
│  11:00  doctor  —                 14/14 verde        │
└──────────────────────────────────────────────────────┘
```

**Fluxograma:**

```
Dúvida: "O que está rolando?"
    │
    └── forge status
        │
        ├── Feature pronta pra implementar? → forge implement <slug>
        ├── Nada em andamento?               → forge plan <nova-feature>
        ├── Algo parece errado?              → forge doctor
        └── Evoluções pendentes?             → forge evolve
```

---

## forge verify — Validar antes do PR

**O que faz:** Roda uma cascade de validators no escopo selecionado (tarefa,
feature, ou inferido). Fail-fast: para no primeiro erro duro.

**Quando usar:** Antes de abrir um PR. Ou depois de implementar uma tarefa,
pra garantir que não quebrou nada.

**Exemplo:**

```bash
$ forge verify

┌─ forge verify ──────────────────────────────────────┐
│ Escopo: login-screen (feature)                       │
├─ validate_workflow_config        ✓  210ms            │
├─ validate_card_yaml              ✓  180ms            │
├─ validate_inventory              ✓  95ms             │
├─ check_no_invented_behavior      ✓  120ms            │
├─ check_cyclomatic_complexity     ✓  1.2s             │
│    Kotlin: 3.1 avg · Swift: 2.8 avg · OK            │
├─ check_secrets                   ✓  4.5s             │
│    gitleaks: 0 findings · trufflehog: 0 findings     │
├─ validate_extension_feature      ✓  150ms            │
│    (sem extends-feature setado — skip)               │
└──────────────────────────────────────────────────────┘
  ✅ Todos os N validators passaram
```

> **Nota:** O `forge verify` roda 3 validators built-in (`check_no_invented_behavior`,
> `check_cyclomatic_complexity`, `check_secrets`) **mais** os validators contribuídos
> pelos cards ativos no projeto. O cascade real depende do preset — N é determinado
> em tempo de execução. O diretório `validators/` tem 21 validators canônicos no
> total; cards selecionam o subset relevante via `contributes.validators`.

**Quando um gate forte falha:**

```
├─ check_cyclomatic_complexity     🛑  1.2s  FAIL
│    LoginScreen.kt: função `handleLogin` tem
│    complexidade ciclomática 14 (limite: 10)
┌─ 3 caminhos ───────────────────────────────────────┐
│ 1. ✅ Refatorar — reduzir complexidade              │
│ 2. 🔰 Justificar — override com razão no commit     │
│ 3. 🚨 Bypass de emergência — logado em .claude/    │
└─────────────────────────────────────────────────────┘
```

**Escopos de verificação:**

- **task** — só os arquivos da tarefa atual
- **feature** — todos os arquivos tocados pela feature
- **inferido** — detecta automaticamente baseado no que mudou

---

## forge doctor — Diagnóstico da instalação

**O que faz:** Health check em 17 categorias. Lê tudo, não muda nada (exceto
marcar `doctor.last-run` no config). Tem modo `quick` (crítico) e `full`.

**Quando usar:** "Algo parece estranho." — o status mostra algo vermelho,
um comando não responde como esperado, ou você quer confirmar que a instalação
está saudável antes de começar uma feature importante.

**Exemplo:**

```bash
$ forge doctor

┌─ forge doctor ──────────────────────────────────────┐
│ Modo: full                                           │
│                                                       │
│  ✅ config              workflow-config.yaml OK      │
│  ✅ cards               8 cards ativos, 0 conflitos  │
│  ✅ inventory           DS + i18n + conventions OK   │
│  ✅ mem                 45 notas · 32 live            │
│  ✅ memory L1           2 features ativas            │
│  ✅ graph               graph.db: 2140 nós, OK       │
│  ⚠️  reuse findings      3 propostas pendentes       │
│  ✅ hooks               9 hooks instalados           │
│  ✅ mcps                ticketing OK                 │
│  ✅ i18n                catálogo coerente             │
│  ✅ bak overdue         0 backups vencidos           │
│  ✅ forge version lock  1.2.0 (compatível)           │
│  ✅ secrets tools       gitleaks + trufflehog OK     │
│  ✅ qa coherence        artefatos coerentes          │
│  ✅ cc-gate tools       detekt + swiftlint OK        │
│  ✅ gradle catalogs     libs.versions.toml OK        │
│                                                       │
│  Resumo: 15/16 verde · 1 warning · 0 hard fails      │
│  ⏱  3.2s                                             │
└──────────────────────────────────────────────────────┘
```

**Fluxograma:**

```
forge doctor
    │
    ├── Tudo verde? → instalação saudável
    ├── Warnings?   → pode ignorar ou olhar forge evolve
    └── Hard fail?  → o problema aparece na categoria
        │
        ├── config?          → workflow-config.yaml pode estar corrompido
        ├── graph?           → forge reconfigure → rebuild graph
        ├── cards?           → forge reconfigure → cards menu
        ├── cc-gate-tools?   → brew install detekt / swiftlint
        └── secrets-tools?   → brew install gitleaks / trufflehog
```

---

## forge graph — Consultar o codebase

**O que faz:** Menu interativo OU modo non-interactive (`--json`) com 17
queries canônicas sobre o grafo do codebase. Read-only — o graph é
construído no `bash .claude/bootstrap.sh` (ou via lazy rebuild na primeira
invocação) e atualizado por hooks incrementais ou `forge reconfigure`.

**Quando usar:** "Quais arquivos usam esse componente?", "Onde esse símbolo é
importado?", "Tem código duplicado entre módulos?". Em pipelines de IA
ou scripts CI, use o modo `--json` (vide abaixo).

**Exemplo:**

```bash
$ forge graph

┌─ forge graph ───────────────────────────────────────┐
│ Q1   similar-features                                │
│ Q2   blast-radius                                    │
│ Q3   orphan-files                                    │
│ Q4   symbols                                         │
│ Q5   ds-used-in                                      │
│ Q6   i18n-used-in                                    │
│ Q7   routes                                          │
│ Q8   di-deps                                         │
│ Q9   tests-for                                       │
│ Q10  commits                                         │
│ Q11  reusable-helpers                                │
│ Q12  dup-within-module                               │
│ Q13  dup-cross-module                                │
│ Q14  kmp-migration                                   │
│ Q15  near-duplicates                                 │
│ Q16  redundant-platform                              │
│ Q17  dup-ts-helpers                                  │
│ r    Combined view (todas as reuse queries)          │
└──────────────────────────────────────────────────────┘

Escolha: Q2
Arquivo: src/common/LoginViewModel.kt
Blast-radius: 8 arquivos → 3 módulos
  app/  → MainActivity.kt, LoginScreen.kt
  shared/ → LoginUseCase.kt
  tests/ → LoginViewModelTest.kt, LoginUseCaseTest.kt
```

**Dica:** Q12–Q17 são as queries de **reuse intelligence**. Elas alimentam o
`forge evolve` com propostas de melhoria. Rode `forge graph` e escolha `r` para
ver tudo de uma vez.

### Modo `--json` (non-interactive, IA-friendly)

Pra IA, scripts ou pipelines CI, use `forge graph --json <query> [args...]`.
Emite JSON parseável em stdout, sem prompts. Aceita aliases (`q1..q17`,
`r`), numeric keys (`1..17`) ou labels textuais.

```bash
forge graph --json q3                          # orphan-files (sem args)
forge graph --json q4 :feature:auth            # symbols num módulo
forge graph --json q2 src/LoginViewModel.kt    # blast-radius (positional file)
forge graph --json blast-radius src/Foo.kt     # idem via label
forge graph --json r                           # reuse-findings combinada
```

Stderr fica reservado pra erros (mensagens de "buildando…" do lazy
rebuild também vão pra stderr). Combine com `--no-auto-build` quando o
contexto for CI/determinístico — assim a flag falha rápido se o DB
ausente em vez de gastar minutos buildando:

```bash
forge graph --json --no-auto-build q3
```

Modelo de consumo + exemplos canônicos por query: `CLAUDE.md §Codebase
Graph — IA-ready`. Schema da coluna `symbols.body` (texto-fonte cru
preservado): `docs/schemas/graph.md §body column`.

---

## forge evolve — Revisar propostas de melhoria

**O que faz:** Apresenta uma a uma as propostas de evolução do código
(duplicação, helper promovível, candidato a KMP, etc.). Você decide: aplicar,
rejeitar, ou deixar pra depois.

**Quando usar:** O `forge status` ou `forge graph` mostrou findings de reuse,
ou o retrospective automático after-feature gerou propostas.

**Exemplo:**

```bash
$ forge evolve

┌─ forge evolve ──────────────────────────────────────┐
│ Proposta 1/3 (reuse-intelligence)                    │
│                                                       │
│ Kind: consolidate-duplicate-helper                   │
│ Arquivos:                                             │
│   app/src/main/.../formatDate.kt                     │
│   app/src/main/.../DateUtils.kt                      │
│   shared/src/commonMain/.../DateFormatter.kt         │
│                                                       │
│ Mesma função de formatação de data em 3 lugares.     │
│ Sugestão: consolidar em shared/src/commonMain/       │
│                                                       │
│ [a] Aplicar    [r] Rejeitar    [d] Depois    [v] Ver │
└──────────────────────────────────────────────────────┘
```

Quando você escolhe "aplicar", o forge:

1. Cria uma `feature-intake.md` stub em `non-product/refactor-consolidate-date/`
2. Marca L1 com `subtype=refactor`
3. Próximo passo: `forge plan refactor-consolidate-date`

---

## forge reconfigure — Mudar configuração

**O que faz:** Entrypoint único para **toda** mutação pós-init: adicionar ou
remover cards, mudar paths, rebuildar graph, re-extrair inventory, alterar
convenções, configurar MCPs de ticketing.

**Quando usar:** "Preciso adicionar um card novo" (ex.: Firebase Analytics),
"mudou o path do design system", "o graph parece desatualizado".

**Exemplo:**

```bash
$ forge reconfigure

┌─ forge reconfigure ─────────────────────────────────┐
│ O que você quer mudar?                               │
│                                                       │
│ [ ] cards        — adicionar/remover/atualizar cards │
│ [ ] paths        — ajustar diretórios do projeto     │
│ [ ] conventions  — mudar convenções de código        │
│ [ ] backend      — trocar configuração de backend    │
│ [ ] ticketing    — configurar MCP do Jira/Linear     │
│ [ ] workflow     — ajustar workflow config           │
│ [ ] persona      — mudar tom/persona das prompts     │
│ [ ] memory       — ajustar política de memória       │
│ [ ] hooks        — adicionar/remover hooks           │
│ [ ] rebuild graph — reconstruir graph.db do zero     │
│ [ ] re-extrair inventory — re-detectar DS/i18n       │
│                                                       │
│ Enter: selecionar · r: rodar · q: sair               │
└──────────────────────────────────────────────────────┘
```

Toda mutação é precedida por `.bak`, e o `reconfigure` roda um `doctor quick`
automático depois de aplicar. Se algo der errado:

```bash
forge undo
# → "reconfigure de 2026-06-12 14:30" → restaura do .bak
```

---

## forge undo — Reverter última ação

**O que faz:** Menu com 6 caminhos de reversão. A opção `last` (default) tenta
reverter a ação mais recente.

**Quando usar:** "Fiz um reconfigure que não era pra fazer", "aquele commit da
tarefa 3 quebrou tudo", "quero marcar uma feature como abortada".

**Exemplo:**

```bash
$ forge undo

┌─ forge undo ────────────────────────────────────────┐
│ O que desfazer?                                      │
│                                                       │
│ 1. last                — reverter ação mais recente  │
│ 2. reconfigure {date}  — restaurar config do .bak    │
│ 3. task commit (feat)  — git revert <sha>            │
│ 4. evolve apply (id)   — reverte apply: remove entry │
│ 5. abort feature       — marcar feature como aborted │
│ 6. delete feature      — rm -rf dos artefatos        │
│                                                       │
│ Escolha (default: 1): 2                               │
│ Data: 2026-06-12                                      │
│                                                       │
│ ✔ workflow-config.yaml restaurado de .bak            │
│ ✔ Histórico atualizado                                │
└──────────────────────────────────────────────────────┘
```

---

## forge memory — Gerenciar o acervo mem

**O que faz:** Wrapper fino arg-driven sobre o `mem` vendorizado (stateless).
Sem menu interativo; cada ação é um subcomando direto.

**Quando usar:** "Quero buscar o que o time aprendeu sobre autenticação",
"preciso exportar o context-pack pro agente", "a L2 estourou e quero curar".

**Subcomandos:**

```bash
# Buscar no acervo (ranqueado por relevância)
$ forge memory search "Firebase Auth timeout"

# Inspecionar uma nota pelo id, ou ver stats do acervo
$ forge memory inspect <id>
$ forge memory inspect

# Exportar índice de alto valor pro context-pack
$ forge memory export
$ forge memory export --budget 8000

# Curadoria do acervo (dry-run por padrão; --apply persiste)
$ forge memory distill
$ forge memory distill --apply
```

---

## forge qa — Gate adversarial (red-team)

**O que faz:** Audita os artefatos da feature inventando cenários hostis.
4 attack vectors × 4 scope targets. Executa em sandbox isolado. O veredito é
informativo (BLOCK/FLAG/PASS) — não bloqueia commit, mas findings vão pro
`forge evolve`.

**Quando usar:** "Antes de fechar a feature, bora testar se ela aguenta
pressão." Útil pra pegar inconsistências entre especificação e implementação.

**Exemplo:**

```bash
$ forge qa

┌─ forge qa ──────────────────────────────────────────┐
│ Scope: feature (login-screen)                        │
│ Sandbox: .planning/qa/a1b2c3d4/                     │
│                                                       │
│ ═══ spec-vs-spec ═══                                  │
│   Confronta PRD vs BDD vs tech-spec...              │
│   ✔ Nenhuma contradição encontrada                  │
│                                                       │
│ ═══ chaos ═══                                         │
│   Simula estados impossíveis...                      │
│   ⚠️ FLAG: UI-state-spec não cobre estado de rede   │
│                                                       │
│ ═══ coverage ═══                                      │
│   Verifica se cada CT tem teste...                   │
│   ✔ 5/5 CTs cobertos                                │
│                                                       │
│ ═══ validator-claim ═══                               │
│   Testa se validators realmente pegariam erros...    │
│   ✔ Validadores respondem como esperado             │
│                                                       │
│ Findings (1) → forge evolve pra revisar             │
└──────────────────────────────────────────────────────┘
```

---

## forge raw — Escape hatch

**O que faz:** Invocação direta de scripts internos sem a UX cinemática do
forge. Útil para automação e depuração.

**Quando usar:** Raramente. Só quando você precisa de um comando que não tem
cinemática própria — validar um card YAML, editar config no $EDITOR, debugar
caminhos.

**Exemplo:**

```bash
$ forge raw verify-card meucard.yaml
# → valida o YAML contra o schema CARD-001..018
# → output limpo, sem cinemática (componível com grep/jq)

$ forge raw edit-config
# → abre $EDITOR no workflow-config.yaml

$ forge raw rebuild-templates
# → re-merge das contribuições de cards em FORGE_HOME/templates/

$ forge raw forge-debug
# → dump de env + resolved paths + cards ativos
```

Subcomandos disponíveis hoje: `verify-card`, `edit-config`,
`rebuild-templates`, `forge-debug`. Verifique a lista atual com
`python -c "from engine import raw; print(raw._SUBCOMMANDS.keys())"`
se algum nome divergir.

---

## Árvore de decisão

```
Qual é o seu próximo passo?
│
├── Feature nova?
│   └── forge plan minha-feature
│
├── Bug reportado (ex.: IN-37234)?
│   └── forge plan --bugfix descricao-do-bug
│       (ou só forge plan — o subtype é perguntado interativamente)
│
├── Refatorar código existente?
│   └── forge plan refactor-slug
│       (entra com contrato no-behavior-change)
│
├── Investigar tecnologia/prova de conceito?
│   └── forge plan spike-slug
│
├── Tarefa de infra/config/manutenção?
│   └── forge plan chore-slug
│
├── Feature já planejada, quero executar?
│   └── forge implement minha-feature
│
├── Ver o que está rolando?
│   └── forge status
│
├── Pronto pra validar (antes do PR)?
│   └── forge verify
│
├── Algo parece errado na instalação?
│   └── forge doctor
│
├── O forge achou código duplicado / melhoria?
│   └── forge graph    (ver findings)
│   └── forge evolve   (revisar e aplicar)
│
├── Preciso mudar configuração / adicionar card?
│   └── forge reconfigure
│
├── Quero ver a memória do time?
│   └── forge memory
│
├── Fiz uma merda, quero desfazer?
│   └── forge undo
│
├── Antes de fechar, quero um gate adversarial?
│   └── forge qa
│
└── Preciso de um comando cru sem cinemática?
    └── forge raw <script>
```

> ⏱ **Dica:** Decore apenas 4 comandos para o dia a dia:
> `plan` → `implement` → `verify` → `status`. O resto você consulta quando
> precisar.

---

## Resumo dos 13 comandos user-facing

| Comando | O que faz | Quando usar |
|---|---|---|
| `forge init` | Bootstrap do workflow no projeto | Uma vez só, no início |
| `forge plan` | Planeja feature (5 waves) | Antes de implementar |
| `forge implement` | Executa tarefa por tarefa | Durante a feature |
| `forge verify` | Cascade de validators | Antes do PR |
| `forge status` | Board read-only | Qualquer hora |
| `forge doctor` | Health check | Diagnóstico |
| `forge reconfigure` | Muda configuração | Pós-init |
| `forge graph` | Consulta o graph | Investigação |
| `forge memory <ação>` | Gerencia o acervo mem (search/inspect/export/distill) | Aprendizado contínuo |
| `forge evolve` | Revisa propostas de melhoria | Quando há findings |
| `forge undo` | Reverte última ação | Erro |
| `forge raw` | Escape hatch | Raramente |
| `forge qa` | Gate adversarial red-team | Antes de fechar feature |

### `forge ingest` — comando interno (não digitado manualmente)

Existe um 14º entrypoint: `forge ingest`. Ele **não** é user-facing — é
invocado pelos git hooks e pelos Claude Code hooks que o `forge init`
instala (`post-edit`, `post-commit`, `pre-commit`, `session-start`,
`post-write-feature-artifact`). Roteia sinais pra graph delta, memory
append, inventory refresh e drift detection. Sempre sai com exit code 0
(hooks não devem bloquear git/edit), erros vão pra stderr como warnings.

Você não digita `forge ingest` no terminal. Documentado aqui só pra que,
ao ver o nome em logs ou no `engine/`, você saiba o que é. Detalhe em
`docs/design/06-command-surface.md §Hidden internal entrypoints`.
