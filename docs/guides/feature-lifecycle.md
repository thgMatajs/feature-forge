<!-- generated-by: gsd-doc-writer -->
# Lifecycle de uma feature — do intake ao PR

Toda feature no feature-forge passa por um **pipeline de fases**. Cada fase
produz artefatos específicos, e o forge guia cada etapa com templates,
verificações e gates — sem improviso.

## Sumário

- [Fase 1 — Intake (captura da ideia)](#fase-1--intake-captura-da-ideia)
- [Fase 2 — PRD (documento de requisitos)](#fase-2--prd-documento-de-requisitos)
- [Fase 3 — Specs (contratos de comportamento)](#fase-3--specs-contratos-de-comportamento)
- [Fase 4 — Tech spec + task breakdown](#fase-4--tech-spec--task-breakdown)
- [Fase 5 — Implementação](#fase-5--implementação)
- [Fase 6 — Review + merge](#fase-6--review--merge)
- [Fase 7 — Retrospectiva](#fase-7--retrospectiva)
- [Variações por subtipo](#variações-por-subtipo)
- [Diagrama do fluxo](#diagrama-do-fluxo)

---

## Introdução

Quando você descreve uma ideia pro forge, ele não sai implementando na hora.
Cada feature percorre **sete fases** que constroem, em sequência:

- **O que** estamos fazendo
- **Por que** estamos fazendo
- **Como** o comportamento deve ser
- **Como** vamos implementar tecnicamente
- **Em quantas tarefas** o trabalho se divide
- **A execução** de cada tarefa
- **O que aprendemos** depois de entregar

O forge não pula fases. Mas ele adapta o pipeline conforme o tipo de
trabalho: um bugfix não precisa de PRD, e um refactor não gera specs de UI.
Isso é o **subtype system** — detalhado na seção de variações.

Toda a fase de planejamento (fases 1–4) é conduzida por um único comando:
`forge plan`. Ele executa **ondas (Waves A–E)**, cada uma produzindo
artefatos. Você preenche cada artefato entre as ondas, confirma, e o forge
passa pra próxima.

> **Primeiros passos:** Veja `getting-started.md` para instalar o forge no
> seu projeto. Veja `daily-workflow.md` para o ciclo do dia-a-dia.

---

## Fase 1 — Intake (captura da ideia)

**O que é:** Uma ideia, ticket, ou bug report vira um documento de intake que
captura a essência — sem detalhamento técnico nem de produto.

**Artefato gerado:** `feature-intake.md`

**Onde:** `docs/feature-implementation-workflow/features/{slug}/feature-intake.md`

**Comando:** `forge plan feature-slug` — Wave A

**Perguntas que o intake responde:**

- O que estamos considerando fazer?
- Por que isso importa agora?
- Qual o valor esperado?
- Quem é impactado?
- Existe um ticket Jira associado? (ex: IN-37234)

O forge detecta automaticamente se o texto parece descrever um bug, um
refactor, um spike ou uma feature de produto. Ele confirma com você antes
de seguir — **inferência, não imposição**.

> **Pra bugfix:** o template de intake é diferente: tem seções de
> "Problema", "Passos pra reproduzir", "Comportamento esperado vs real",
> "Hipótese de causa raiz" e "Estratégia de validação".

---

## Fase 2 — PRD (documento de requisitos)

**O que é:** O documento de produto propriamente dito. Define objetivo,
personas, critérios de sucesso, e o escopo funcional.

**Artefato gerado:** `feature-prd.md`

**Onde:** Mesmo diretório do intake.

**Comando:** `forge plan` continua — ainda na Wave A.

**Perguntas que o PRD responde:**

- Qual o objetivo de negócio?
- Quem são as personas envolvidas?
- Quais os critérios de sucesso (quantitativos e qualitativos)?
- O que está dentro e fora de escopo?
- Como sabemos que a feature está pronta?

O PRD só é gerado para features **product**. Bugfix, refactor e spike
**pulam** esta fase — cada um tem seu próprio template de intake adaptado.

> **Quando o subtipo é bugfix:** `forge plan` detecta o ticket Jira
> (ex: IN-37234), gera o template de intake-bugfix, e **não** gera PRD.
> Em vez disso, ele pergunta se o bug envolve UI observável — se sim,
> a Wave B roda; se não, pula direto pra Wave C (tech spec).

---

## Fase 3 — Specs (contratos de comportamento)

**O que é:** Antes de qualquer código, o forge modela o comportamento da
feature através de contratos formais. Isso inclui cenários BDD, eventos de
analytics, contratos de dados, navegação, estados de UI e estratégia de
testes.

**Artefatos gerados:**

| Artefato | Formato | O que contém |
|---|---|---|
| `bdd.md` | Markdown | Cenários Gherkin (Dado-Quando-Então) |
| `bdd.json` | JSON | Mesmos cenários em formato parseável |
| `ui-state-spec.yaml` | YAML | Estados de tela (loading, vazio, erro, sucesso) |
| `navigation-spec.yaml` | YAML | Fluxos de navegação e transições |
| `data-contract-spec.yaml` | YAML | Contratos de API, modelos, validações |
| `analytics-spec.yaml` | YAML | Eventos de analytics e propriedades |
| `test-strategy.yaml` | YAML | Estratégia de testes (unitários, integração, e2e) |
| `screen-analysis.md` | Markdown | Análise de telas existentes |

**Onde:** Mesmo diretório.

**Comando:** `forge plan` — Wave B

**Quando esta fase não roda:**

- **Refactor**: pula Wave B (comportamento não muda, contratos existentes
  continuam valendo)
- **Bugfix lógico**: pula Wave B (só roda se o bug envolve UI observável)
- **Spike / chore**: na v1.0, estas subtypes não têm implementação completa
  — o forge oferece 3 caminhos (tratar como product, pausar, abortar)

---

## Fase 4 — Tech spec + task breakdown

**O que é:** O documento técnico detalhado + a decomposição da feature em
tarefas atômicas. Cada tarefa tem escopo definido, arquivos permitidos,
critérios de aceite, validações e gates.

**Artefatos gerados:**

| Artefato | Formato | O que contém |
|---|---|---|
| `tech-spec.md` | Markdown | Especificação técnica: arquitetura, componentes, fluxos de dados, decisões |
| `task-breakdown.yaml` | YAML | Lista mestra de tarefas com dependências |
| `tasks/TASK-0001.yaml` | YAML | Contrato individual da tarefa 1 |
| `tasks/TASK-0002.yaml` | YAML | Contrato individual da tarefa 2 |
| ... | YAML | (quantas forem necessárias, até 30) |

**Comando:** `forge plan` — Waves C (tech spec) e D (task breakdown)

**O que cada task contract contém:**

- `task_id`: identificador único (TASK-0001, TASK-0002...)
- `description`: o que precisa ser feito
- `allowed_files`: quais arquivos podem ser editados (gate forte)
- `validations`: validações a rodar após implementação
- `gates`: gates de qualidade (complexidade ciclomática, secrets)
- `dependencies`: tarefas que precisam estar prontas antes
- `bdd_scenarios_covered`: quais cenários BDD esta task implementa

**Wave E — Readiness review:** Antes de liberar pra implementação, o forge
gera um `implementation-readiness-review.md` + `plan-feature-handoff.json`.
O status precisa estar `ready` (ou `ready-with-blocks`) para que
`forge implement` aceite começar. Se não estiver, o forge oferece 3
caminhos: re-revisar, marcar como deferred, ou pausar.

---

## Fase 5 — Implementação

**O que é:** A execução propriamente dita, tarefa por tarefa. O forge
implementa **uma task por invocação** — cada uma passa por um ciclo
completo de Plan Mode → Apply → gates → commit.

**Comando:** `forge implement feature-slug`

> **Apply Mode — v1 (atual):** O forge exibe o contrato da task e instrui o desenvolvedor; a escrita de código é manual. Apply Mode automatizado (engine escrevendo código via Claude Code) está planejado para Phase 6 e ainda não foi shipado.

**O ciclo de cada task:**

1. **Resolução**: forge descobre qual é a próxima task via ordenação
   topológica do DAG de dependências
2. **Plan Mode**: exibe o contrato da task — descrição, arquivos permitidos,
   BDD coberto, validações, gates
3. **Confirmação**: você confirma que entendeu o escopo ("sim")
4. **Apply Mode**: o dev implementa os arquivos listados em `allowed_files`
   conforme o contrato gerado pelo forge — qualquer edição fora dos arquivos
   permitidos vira um **Finding** (com 3 caminhos: atualizar contrato,
   reverter, ou split em nova task)
5. **Gates**: o forge roda automaticamente após a implementação:
   - `check_cyclomatic_complexity` — gate de complexidade ciclomática
   - `check_secrets` — gate de detecção de segredos (gitleaks)
6. **Handoff**: instruções pra commit + `forge verify` + passar pra
   próxima task

**Se uma task depende de algo externo** (ex: um ticket de backend que ainda
não foi resolvido), o forge recusa começar e oferece 3 caminhos: marcar
como resolvido via `forge reconfigure`, pegar outra task sem bloqueio, ou
pausar a feature inteira.

**Quando todas as tasks estão fechadas**, o forge automaticamente:
- Marca a feature como `done`
- Pergunta se quer rodar `forge qa` (se o auto-run estiver ativado)
- Libera o phase lock

---

## Fase 6 — Review + merge

**O que é:** O forge prepara o terreno para o code review humano, mas **não
substitui** o olhar humano (Decisão 5).

**Antes do PR:**

```bash
forge verify feature-slug
```

O `forge verify` roda uma **cascade de validadores** em sequência, com
política fail-fast (para no primeiro erro duro). Os validadores são
determinados pelos cards ativos no projeto — cada card pode declarar seus
próprios validadores.

**O que o forge NÃO faz:**
- Não abre o PR automaticamente (fora de escopo na v1)
- Não faz code review final (Decisão 5 explicita)
- Não faz merge

**O que o forge disponibiliza:**
- Histórico completo no `history.jsonl` de cada feature
- Evidência de que os validadores passaram
- Rastreabilidade entre BDD, contratos e tasks

---

## Fase 7 — Retrospectiva

**O que é:** Quando a última task é concluída, o `retrospective-agent`
analisa o que aconteceu durante a feature e propõe evoluções para a
**memória compartilhada do time** (L2).

**Artefato:** `evals.json` (insumo técnico) + propostas em
`proposed-evolutions.yaml`

**O que a retrospectiva produz:**

- Insights sobre padrões que se repetiram dentro da feature
- Candidatos a promover da memória L1 (feature) para L2 (projeto)
- Propostas de melhoria no fluxo, nos cards, ou nas convenções

**E daí?** O comando `forge evolve` te apresenta essas propostas uma a uma.
Você pode **aplicar** (vira memória do time), **rejeitar** (com motivo),
**adiar** ou **ver detalhes**. Tudo single-by-single — nunca em lote.

> A retrospectiva também gera o **5-whys** em bugfixes, ajudando o time
> a entender por que o bug aconteceu e como evitar.

---

## Variações por subtipo

O forge detecta automaticamente o subtipo da feature pela descrição que
você deu (e confirma com você). Cada subtipo ajusta o pipeline:

| Subtipo | Pipeline | Particularidades |
|---|---|---|
| **product** | Completo (7 fases) | Pipeline padrão, Waves A–E completas |
| **bugfix** | Pula PRD, usa intake próprio, Wave B condicional | Detecta ticket Jira (IN-37234, PD-1234). Exige 5-whys na retrospec. Wave B só roda se o bug é de UI observável |
| **refactor** | Pula PRD e Wave B, sem specs de UI | Contrato **no-behavior-change** é gate forte. `check_no_behavior_change` valida que comportamento não mudou |
| **spike** | Stub em v1.0 | Investigação técnica. Forge oferece 3 caminhos: tratar como product, pausar até v1.1+, ou abortar |
| **chore** | Stub em v1.0 | Manutenção (bump de dependência, cleanup). Mesmo tratamento de spike |

---

## Diagrama do fluxo

```
                    ┌─────────────────────────────────────────────┐
                    │              forge plan                     │
                    │                                             │
     ┌─── Intake ───┤  Wave A: feature-intake.md + feature-prd.md │
     │              │  (ou intake-bugfix / intake-refactor)       │
     │  PRD ────────┤                                             │
     │              │  Wave B: screen-analysis, bdd, ui-state,   │
     │  Specs ──────┤          navigation, data-contract,        │
     │              │          analytics, test-strategy           │
     │  Tech Spec ──┤                                             │
     │              │  Wave C: tech-spec.md                       │
     │ Task Break ──┤                                             │
     │              │  Wave D: task-breakdown + TASK-NNNN.yaml    │
     │  Readiness ──┤                                             │
     │              │  Wave E: readiness-review + handoff.json    │
     └──────────────┴─────────────────────────────────────────────┘
                           │
                           ▼
                    ┌──────────────────┐
                    │ forge implement  │──→ gates → commit → next task
                    │ (1 task/vez)     │
                    └──────────────────┘
                           │
                           ▼
               ┌──────────────────────┐
               │ Todas as tasks done? │──→ forge qa (opt-in) → retrospective
               └──────────────────────┘
                           │
                           ▼
               ┌──────────────────────┐
               │    forge evolve      │  ← propostas da retrospectiva
               │  (aplicar/rejeitar)  │
               └──────────────────────┘
```

---

## Comandos relacionados

| Comando | O que faz |
|---|---|
| `forge plan {slug}` | Planeja uma feature inteira (Waves A–E) |
| `forge implement {slug}` | Executa a próxima task disponível |
| `forge verify {slug}` | Roda a cascade de validadores |
| `forge status` | Mostra features em andamento |
| `forge evolve` | Revisa e aplica propostas de melhoria |
| `forge undo` | Reverte última ação mutante |
| `forge doctor` | Diagnóstico completo do projeto |
| `forge qa` | Auditoria adversarial (red-team) |

> **Veja também:**
> - `dot-claude-reference.md` — explica cada arquivo na pasta `.claude/`
> - `daily-workflow.md` — ciclo do dia-a-dia com forge
> - `getting-started.md` — instalação e primeira execução
