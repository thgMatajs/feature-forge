# Plan Auditor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar o auditor pós-plano (`.claude/rules/plan-auditor.md` + integração via CLAUDE.md e rules) que dispara automaticamente após writing-plans terminal-state, verifica 12 checks específicos do projeto, e classifica findings por severity (Critical bloqueia, High/Medium/Low não).

**Architecture:** Auditor vive como rule + protocolo de dispatch. Zero código Python, zero novo agent, zero novo hook. `gsd-code-reviewer` recebe o prompt de `.claude/rules/plan-auditor.md` quando o orquestrador dispatcha, antes do "Execution Handoff" do `superpowers:writing-plans`. Output em `.planning/plan-reviews/<plan-slug>-review-r<N>.md` (gitignored).

**Tech Stack:** Markdown rules + protocolo de dispatch. Worktree-based (já criada em `.claude/worktrees/plan-auditor` no branch `feat/plan-auditor`).

**Spec:** `docs/superpowers/specs/2026-06-04-plan-auditor-design.md` (commit `8c28229`).

---

## File Structure

| Ação | Arquivo | Responsabilidade |
|---|---|---|
| Criar | `.claude/rules/plan-auditor.md` | Prompt determinístico + 12 checks com severity + output format pro `gsd-code-reviewer` |
| Modificar | `CLAUDE.md` | Adicionar `+ plan-auditor (dispatched)` nas rows "Adicionar feature/recurso" e "Refatorar" da tabela §Workflow por verbo |
| Modificar | `.claude/rules/superpowers.md` | Nova linha `plan-auditor` na tabela "Superpowers map" + nota explicando que estende writing-plans terminal-state |
| Modificar | `.claude/rules/subagent-workflow.md` | Nova linha "Auditar plano pós writing-plans" → `gsd-code-reviewer` com prompt `.claude/rules/plan-auditor.md` na tabela §"Qual subagent_type pra quê" |
| Modificar | `.claude/rules/README.md` | Linha nova na Map table apontando pra `plan-auditor.md` |
| Modificar | `.gitignore` | Adicionar `.planning/plan-reviews/` na seção runtime artifacts |
| Modificar | `CHANGELOG.md` | Entrada `## [Unreleased] ### Added` documentando o plan auditor |
| Modificar | `docs/design/08-session-handoff.md` | Atualizar "Última atualização" + estado |
| Modificar | `docs/design/04-pending.md` | Anotar "auditoria pós-plano" como entregue nesta release |

Tudo num único commit atômico (doc-sync mandamento #6).

---

## Task 1: Criar `.claude/rules/plan-auditor.md`

**Files:**
- Create: `.claude/rules/plan-auditor.md`

- [ ] **Step 1.1: Escrever o arquivo com o prompt determinístico completo**

Conteúdo verbatim:

````markdown
# Plan Auditor — prompt template

Prompt determinístico que `gsd-code-reviewer` recebe ao auditar planos
pós-`superpowers:writing-plans`. Voz: mentor calmo. Output:
`PLAN-REVIEW.md` em `.planning/plan-reviews/<plan-slug>-review-r<N>.md`.

## Invocação canônica

Orquestrador dispatcha após writing-plans terminal-state (antes do
"Execution Handoff" do SKILL.md) com:

```
Agent[gsd-code-reviewer] prompt:
  CONTEXTO: auditoria pós-plano de feature-forge. Leia o arquivo inteiro
  `.claude/rules/plan-auditor.md` e aplique os 12 checks ao plano.

  INPUTS:
    - Plan: docs/superpowers/plans/<plan-slug>.md
    - Spec: docs/superpowers/specs/<spec-slug>.md
    - Rodada: <N> de 3

  OUTPUT: .planning/plan-reviews/<plan-slug>-review-r<N>.md
```

## Voz

Mentor calmo. Firme em findings, didático no rationale. PT neutro. Sem
emoji decorativo (exceto ✅⏭️🤔 do template 3-caminhos canônico do
projeto). Sem voz corporativa, sem hedging ("vou tentar", "considere",
"talvez"). Compromete-se ou redireciona — não suaviza.

## Os 12 checks

### Critical (bloqueia execution-handoff)

#### C1. Locked decision ceremony (Mandamento #1)

**Trigger:** plano edita `docs/design/01-decisions.md` em qualquer task.

**Detecção:**
1. Procure tasks com `01-decisions.md` em "**Files:**" ou "Modify:".
2. Se encontrado, busque em todas as tasks: existe task que adiciona
   entrada em `CHANGELOG.md` contendo o texto literal "Revisita decisão N"
   (substituindo N pelo número)?
3. Se encontrado, busque: o commit message especificado em alguma task
   contém "Revisita decisão N"?

**Falha:** alguma das 3 condições não satisfeita.

**Por que importa:** o pre-commit hard-block
(`.claude/hooks/pre-commit-feature-forge.sh`) vai bloquear depois.
Retrabalho cascateado.

#### C2. Spec coverage

**Trigger:** sempre.

**Detecção:**
1. Localize spec referenciado no header do plano (campo **Spec:** ou
   prosa equivalente).
2. Se spec path não existe no filesystem → falha.
3. Pra cada seção/requisito do spec, identifique pelo menos uma task no
   plano que implementa.

**Falha:** spec ausente OU requisito sem task correspondente.

**Por que importa:** sem cobertura completa do spec, o plano não entrega
o contrato aprovado.

### High (warn, orquestrador decide)

#### H1. Load-bearing files sem justificativa (Mandamento #4)

**Trigger:** task toca arquivo em load-bearing whitelist.

**Whitelist (de `.claude/rules/scope.md`):**
- `docs/design/00-vision.md`
- `docs/design/01-decisions.md` (já tratado em C1)
- `docs/design/05-filesystem-layout.md`
- `docs/design/06-command-surface.md`
- `docs/design/07-discipline.md`
- `docs/schemas/**`
- `presets/**`
- `cards/**`
- `CLAUDE.md`
- `.claude/rules/**`

**Detecção:** pra cada task tocando arquivo load-bearing, busque na
prose da task palavras-chave de justificativa: "porque", "necessário",
"alinha com", "revisita", "consequência de", "mandamento", "decisão N",
"escopo da tarefa". Se nenhuma justificativa textual → finding.

#### H2. Doc-sync coverage (Mandamento #6)

**Trigger:** plano toca diretórios de código vivo: `engine/`,
`validators/`, `hooks/`, `templates/`, `cards/`, `presets/`,
`docs/schemas/`.

**Detecção:**
1. Liste tasks que tocam esses diretórios.
2. Verifique se existe task explícita atualizando `CHANGELOG.md`.
3. Verifique se existe task atualizando
   `docs/design/08-session-handoff.md`.
4. Se mudança envolve nova stat (test count, validator count, card count,
   template count, LOC), verifique task atualizando `README.md`.

**Falha:** qualquer dos 3 ausente quando aplicável.

#### H3. Reuse-first ignorado (Mandamento #3)

**Trigger:** plano cria helper/função/validator/template/card novo.

**Detecção:**
1. Procure tasks com "Create:" em `engine/`, `validators/`, `templates/`,
   `cards/`.
2. Pra cada criação, busque no plano (qualquer task, qualquer step):
   menção a `forge graph` (queries Q11-Q17) OU `engine/inventory/` OU
   grep de precedente OU justificativa "near-duplicate analisado" OU
   "não existe equivalente em".

**Falha:** criação sem evidência de consulta a reuse intelligence.

#### H4. Testing gates (Mandamento #2)

**Trigger:** plano implementa feature ou fix em `engine/` ou
`validators/`.

**Detecção:**
1. Determine tipo: feature (Create em engine/validators), bugfix (Modify
   com test de regressão), refactor (no-behavior contract explícito).
2. Pra feature/bugfix:
   - Existe step "Write the failing test" ANTES de step "implement"?
   - Existe step "Run: pytest <path>" com path concreto?
3. Pra refactor: existe step rodando
   `validators/check_no_behavior_change.py` ou equivalente?

**Falha:** TDD shape ausente, pytest path placeholder, ou refactor sem
no-behavior validator.

**Nota:** planos puramente documentais (sem touch em `engine/` ou
`validators/`) não disparam H4.

### Medium (informativo, fix recomendado)

#### M1. Scope file whitelist

**Trigger:** sempre.

**Detecção:** pra cada task, existe seção "**Files:**" ou "ARQUIVOS
PERMITIDOS PARA EDIT" listando paths explícitos? Tasks com
Modify/Create sem path explícito → finding.

#### M2. Pending gaps coverage

**Trigger:** sempre.

**Detecção:**
1. Leia `docs/design/04-pending.md`.
2. O plano referencia gap aberto? Se sim, existe task atualizando
   `04-pending.md`?
3. O plano introduz limitação nova (anti-goal, deferred item)? Se sim,
   existe task anotando em `04-pending.md`?

**Falha:** gap fechado sem atualização OU gap novo sem anotação.

#### M3. Subagent dispatchability

**Trigger:** sempre.

**Detecção:** pra cada task com ≥3 steps, existe contexto suficiente pro
context-pack do subagent? Verifique presença de:
- Ação concreta no título da task
- Critério de sucesso (pytest path / validator / observável testável)
- Lista de anti-padrões ou "NÃO fazer" explícita

**Falha:** task ambígua pra dispatch independente.

### Low (cosmético)

#### L1. Voice check (Mandamento #5)

**Detecção:** grep no plano por:
- Emoji decorativo fora do template 3-caminhos canônico (✅⏭️🤔 são OK;
  outros sinalizam)
- "vou tentar", "considere", "talvez", "pode ser uma boa ideia"
- Inglês corporativo: "stakeholder", "leverage", "robust", "best effort"

**Finding por ocorrência.**

#### L2. Placeholder scan

**Detecção:** grep no plano por:
- "TBD", "TODO", "FIXME"
- "..." em blocos de código (não em prose)
- "implement here", "fill in", "similar to Task N" sem repetição inline

#### L3. Type/name consistency

**Detecção:** colete todas as referências a funções/classes/arquivos
novos no plano. Verifique grafia consistente entre tasks
(case-sensitive). Ex: `clearLayers()` em task 3 vs `clearFullLayers()`
em task 7 é finding.

## Override mechanism

Antes de aplicar checks, leia o topo do plano (primeiras 50 linhas) por:

```html
<!-- audit-override: C-XXX — razão concreta -->
```

Pra cada match:
- Marque o finding correspondente como `acknowledged`.
- Não bloqueia mais (re-classifica como Low independente da severity
  original).
- Lista na seção "Acknowledged overrides" do output, preservando a
  razão textual.

## Verdict logic

Após processar 12 checks:

- Se `count(Critical não-acknowledged) > 0` → **BLOCK**
- Senão, se `count(High) + count(Medium) > 0` → **PASS_WITH_WARNINGS**
- Senão (0 findings ou só Low) → **PASS**

## Output format

Escreva em `.planning/plan-reviews/<plan-slug>-review-r<N>.md`:

```markdown
# Plan Review: <plan-slug>
**Plano:** docs/superpowers/plans/<...>.md
**Spec:** docs/superpowers/specs/<...>.md
**Rodada:** N/3
**Verdict:** BLOCK | PASS_WITH_WARNINGS | PASS

## Critical (N) — bloqueia execution-handoff
- [C-001] {check ID}: {finding curto} — task #M, linha L
  Por que importa: {regra/contract violado}
  Caminho A: {fix forward concreto}
  Caminho B: {revert/remover}
  Caminho C: {split/escalate}

## High (N)
[...mesma forma...]

## Medium (N)
[...mesma forma...]

## Low (N)
[...mesma forma...]

## Acknowledged overrides
- C-XXX: <razão textual do override inline>
```

Se uma severity tem 0 findings, mantenha a seção com `(0 findings)` em
vez de omitir — facilita parsing.

## Anti-padrões do reviewer

- NÃO modifique o plano. Auditor é read-only contra o plano.
- NÃO escreva código Python, hook, ou validator.
- NÃO invente checks fora dos 12 listados.
- NÃO suavize severity ("é só medium, deixa passar") — siga o mapping
  determinístico.
- NÃO crie findings duplicados — se um problema dispara 2 checks (ex.:
  H1 + M1 no mesmo arquivo), reporte apenas no de severity mais alta.
- NÃO escreva voz corporativa — você está sob mandamento #5 igual o
  resto do projeto.

## Re-audit (rodadas N>1)

Quando o orquestrador dispatcha rodada 2+, você recebe o caminho do
review anterior. Compare:

1. Findings da rodada N-1 que sumiram → marque como `resolved` na nova
   review.
2. Findings novos (impacto do fix dispatch) → liste normalmente.
3. Findings persistentes → repita, mas indique `(persistente desde
   r<N-1>)`.

Limite: rodada 3. Na rodada 4, escale pro orquestrador via verdict
especial `ESCALATE` no header — orquestrador apresenta 3-caminhos ao
user.

## Quando NÃO há spec

Planos quick-fix podem não ter spec. Nesse caso:
- C2 (Spec coverage) → automaticamente finding Medium com nota "plano
  sem spec — aceitável pra quick-fix, mas verifique se escopo justifica
  ausência".
- Demais checks rodam normalmente.
````

**Justificativa load-bearing:** este rule é o artefato canônico do
auditor pós-plano (escopo da tarefa). Sem este arquivo, o dispatch
documentado em CLAUDE.md (Task 2) e superpowers.md (Task 3) não tem
prompt pra carregar.

- [ ] **Step 1.2: Verificar conteúdo escrito**

Run: `cd .claude/worktrees/plan-auditor && wc -l .claude/rules/plan-auditor.md`
Expected: ≥ 200 linhas (arquivo completo).

Run: `cd .claude/worktrees/plan-auditor && grep -c "^####" .claude/rules/plan-auditor.md`
Expected: 12 (um cabeçalho `####` por check).

---

## Task 2: Atualizar `CLAUDE.md` §Workflow por verbo

**Files:**
- Modify: `CLAUDE.md` (tabela §Workflow por verbo)

- [ ] **Step 2.1: Localizar a tabela**

Run: `cd .claude/worktrees/plan-auditor && grep -n "Workflow por verbo" CLAUDE.md`

- [ ] **Step 2.2: Editar a tabela**

Na coluna "Skills (orchestrator invoca)", adicionar `→ plan-auditor (dispatched)` ao final das células das rows:
- "Adicionar feature/recurso"
- "Refatorar"

Resultado esperado (rows alteradas):

```markdown
| Adicionar feature/recurso | `brainstorming` → `writing-plans` → plan-auditor (dispatched) → `subagent-driven-development` | `gsd-executor` + review subagent |
| Refatorar | `brainstorming` → `writing-plans` (no-behavior) → plan-auditor (dispatched) → `subagent-driven-development` | `gsd-executor` + review (check_no_behavior_change) |
```

Justificativa (não vai no arquivo, mas explica edit em load-bearing
`CLAUDE.md`): integração canônica do auditor no fluxo. Sem esta linha o
orquestrador não sabe que precisa dispatch.

- [ ] **Step 2.3: Verificar**

Run: `cd .claude/worktrees/plan-auditor && grep -c "plan-auditor (dispatched)" CLAUDE.md`
Expected: 2 (uma por row alterada).

**NÃO fazer:** editar arquivos fora de **Files** acima; refator
não-solicitado em outras seções do arquivo; quebrar formatação
tabela/estrutura existente.

---

## Task 3: Atualizar `.claude/rules/superpowers.md`

**Files:**
- Modify: `.claude/rules/superpowers.md` (tabela "Superpowers map" + nota)

- [ ] **Step 3.1: Adicionar linha na tabela Superpowers map**

Após a linha do `superpowers:verification-before-completion` (última row
da tabela), adicionar:

```markdown
| `plan-auditor` (rule local) | pós writing-plans terminal-state, antes do execution-handoff | **sim — critical findings bloqueiam** |
```

- [ ] **Step 3.2: Adicionar nota explicativa**

Após a seção "Skills NÃO ativadas (deliberadamente)" e antes de
"Hierarquia de prioridade", adicionar:

```markdown
## Extensão local: plan-auditor

`plan-auditor` não é skill do superpowers — é rule deste projeto
(`.claude/rules/plan-auditor.md`). Estende o terminal-state do
`superpowers:writing-plans`: antes do "Execution Handoff" do SKILL.md,
o orquestrador OBRIGATORIAMENTE dispatcha `gsd-code-reviewer` com o
prompt do auditor. Critical findings bloqueiam o handoff até fix-dispatch
resolver.

Detalhe completo: `.claude/rules/plan-auditor.md`.
```

- [ ] **Step 3.3: Verificar**

Run: `cd .claude/worktrees/plan-auditor && grep -c "plan-auditor" .claude/rules/superpowers.md`
Expected: ≥ 3 (linha da tabela + nota + referência).

Justificativa load-bearing: este rule documenta o conjunto de skills
ativas; auditor é skill local que precisa estar listada.

**NÃO fazer:** editar arquivos fora de **Files** acima; refator
não-solicitado em outras seções do arquivo; quebrar formatação
tabela/estrutura existente.

---

## Task 4: Atualizar `.claude/rules/subagent-workflow.md`

**Files:**
- Modify: `.claude/rules/subagent-workflow.md` (tabela "Qual subagent_type pra quê")

- [ ] **Step 4.1: Adicionar linha na tabela**

Após a linha "Plano de feature/refactor", adicionar:

```markdown
| Auditar plano pós writing-plans | `gsd-code-reviewer` | prompt em `.claude/rules/plan-auditor.md`; produz `PLAN-REVIEW.md` com 12 checks classificados |
```

- [ ] **Step 4.2: Verificar**

Run: `cd .claude/worktrees/plan-auditor && grep -c "plan-auditor.md" .claude/rules/subagent-workflow.md`
Expected: ≥ 1.

Justificativa load-bearing: este rule é o mapa "qual subagent_type pra
quê"; auditor reusa `gsd-code-reviewer` mas com prompt diferente — precisa
ser listado pra orquestrador encontrar.

**NÃO fazer:** editar arquivos fora de **Files** acima; refator
não-solicitado em outras seções do arquivo; quebrar formatação
tabela/estrutura existente.

---

## Task 5: Atualizar `.claude/rules/README.md`

**Files:**
- Modify: `.claude/rules/README.md` (Map table)

- [ ] **Step 5.1: Adicionar linha na Map table**

Após a linha `doc-sync.md`, adicionar (mantendo ordenação semântica do
arquivo):

```markdown
| [plan-auditor.md](plan-auditor.md) | Prompt + 12 checks pra auditoria pós writing-plans | antes/depois de dispatch do auditor |
```

- [ ] **Step 5.2: Verificar**

Run: `cd .claude/worktrees/plan-auditor && grep -c "plan-auditor.md" .claude/rules/README.md`
Expected: ≥ 1.

Justificativa load-bearing: README é o index oficial dos rules; novo rule
sem entrada aqui é invisível pra navegação.

**NÃO fazer:** editar arquivos fora de **Files** acima; refator
não-solicitado em outras seções do arquivo; quebrar formatação
tabela/estrutura existente.

---

## Task 6: Atualizar `.gitignore`

**Files:**
- Modify: `.gitignore` (seção runtime artifacts)

- [ ] **Step 6.1: Adicionar entrada**

Na seção `# Claude Code — runtime state (per-session, não versionado)`,
após a linha `!.claude/state/.gitkeep`, adicionar:

```gitignore

# Plan auditor — review outputs (per-rodada, não versionado)
.planning/plan-reviews/
```

- [ ] **Step 6.2: Verificar**

Run: `cd .claude/worktrees/plan-auditor && grep -c "plan-reviews" .gitignore`
Expected: 1.

**NÃO fazer:** editar arquivos fora de **Files** acima; refator
não-solicitado em outras seções do arquivo; quebrar formatação
tabela/estrutura existente.

---

## Task 7: Atualizar `CHANGELOG.md`

**Files:**
- Modify: `CHANGELOG.md` (seção `## [Unreleased]`)

- [ ] **Step 7.1: Adicionar entrada Added**

Sob `## [Unreleased]` (que hoje está vazia), adicionar:

```markdown
### Added

- **Plan auditor** — `.claude/rules/plan-auditor.md` define prompt
  determinístico + 12 checks com severity (2 Critical / 4 High / 3
  Medium / 3 Low) pra auditoria pós-`superpowers:writing-plans`.
  Orquestrador dispatcha `gsd-code-reviewer` com este prompt antes do
  "Execution Handoff" do SKILL.md; Critical findings bloqueiam o handoff
  até fix-dispatch resolver. Output em `.planning/plan-reviews/<plan-slug>-review-r<N>.md`
  (gitignored). Re-audit cap em 3 rodadas, override inline via
  `<!-- audit-override: C-XXX — razão -->` no topo do plano. Integração
  documentada em `CLAUDE.md` §Workflow por verbo,
  `.claude/rules/superpowers.md`, `.claude/rules/subagent-workflow.md`,
  `.claude/rules/README.md`. Spec:
  `docs/superpowers/specs/2026-06-04-plan-auditor-design.md`. Plano:
  `docs/superpowers/plans/2026-06-04-plan-auditor.md`.
```

- [ ] **Step 7.2: Verificar**

Run: `cd .claude/worktrees/plan-auditor && grep -A2 "## \[Unreleased\]" CHANGELOG.md | head -5`
Expected: mostra a seção Added preenchida.

**NÃO fazer:** editar arquivos fora de **Files** acima; refator
não-solicitado em outras seções do arquivo; quebrar formatação
tabela/estrutura existente.

---

## Task 8: Atualizar `docs/design/04-pending.md`

**Files:**
- Modify: `docs/design/04-pending.md`

- [ ] **Step 8.1: Adicionar entrada de fechamento**

Procure a seção de "fechados nesta release" ou equivalente. Se não
existir, adicionar no topo do arquivo (após o front-matter, antes da
primeira seção):

```markdown
## Fechado em [Unreleased]

- **Auditoria pós-plano** — gap identificado em 2026-06-04 (não estava
  listado em `04-pending.md` antes, mas surgiu no fluxo: o
  `superpowers:writing-plans` Self-Review é leve demais pra capturar
  load-bearing edits sem justificativa, ausência de "Revisita decisão
  N", doc-sync gaps, reuse-first ignorado, voz quebrada). Resolvido via
  `.claude/rules/plan-auditor.md` + integração — ver CHANGELOG
  `[Unreleased]`. Spec: `docs/superpowers/specs/2026-06-04-plan-auditor-design.md`.
```

Se já existir seção equivalente, adicione apenas o bullet point dentro
dela.

- [ ] **Step 8.2: Verificar**

Run: `cd .claude/worktrees/plan-auditor && grep -c "Auditoria pós-plano" docs/design/04-pending.md`
Expected: ≥ 1.

**NÃO fazer:** editar arquivos fora de **Files** acima; refator
não-solicitado em outras seções do arquivo; quebrar formatação
tabela/estrutura existente.

---

## Task 9: Atualizar `docs/design/08-session-handoff.md`

**Files:**
- Modify: `docs/design/08-session-handoff.md` (header — "Última atualização" e "Estado")

- [ ] **Step 9.1: Atualizar header**

Localize as linhas:

```markdown
**Última atualização:** 2026-06-03 (v1.2.0 — Gap 5 + power-review PR #2 R1 + tag release)
**Estado:** v1.2.0 entregue. ...
```

Atualize para:

```markdown
**Última atualização:** 2026-06-04 (plan-auditor — auditoria pós writing-plans)
**Estado:** Plan auditor entregue (`.claude/rules/plan-auditor.md` + 7
touch points de integração). Em paralelo aos branches v1.2.x cumulativos.
Próximo: smoke real do auditor contra plano futuro pra validar mapping
de severity. Suite total inalterada (sem touch em `engine/` ou
`validators/`).
```

(Mantenha o resto do arquivo intacto.)

- [ ] **Step 9.2: Verificar**

Run: `cd .claude/worktrees/plan-auditor && grep "Última atualização" docs/design/08-session-handoff.md | head -1`
Expected: contém "2026-06-04".

Justificativa load-bearing: handoff é o doc canônico de estado da
sessão; toda mudança que entrega artefato precisa atualizar aqui
(mandamento #6).

**NÃO fazer:** editar arquivos fora de **Files** acima; refator
não-solicitado em outras seções do arquivo; quebrar formatação
tabela/estrutura existente.

---

## Task 10: Smoke test do auditor

**Files:**
- (sem write — apenas leitura/dispatch)

- [ ] **Step 10.1: Dispatch manual do auditor contra o próprio spec**

Este step é executado pelo orquestrador (não pelo executor desta task) —
documentado aqui pra rastreabilidade. Após Task 9 completar, orquestrador
deve:

1. Despachar `gsd-code-reviewer` com prompt customizado:

   ```
   CONTEXTO: smoke test do plan auditor recém-implementado. Leia
   `.claude/rules/plan-auditor.md` inteiro e aplique os 12 checks ao
   plano `docs/superpowers/plans/2026-06-04-plan-auditor.md`.

   INPUTS:
     - Plan: docs/superpowers/plans/2026-06-04-plan-auditor.md
     - Spec: docs/superpowers/specs/2026-06-04-plan-auditor-design.md
     - Rodada: 1 de 3

   OUTPUT: .planning/plan-reviews/2026-06-04-plan-auditor-review-r1.md
   ```

2. Ler o output. Verdict esperado: PASS ou PASS_WITH_WARNINGS (este
   plano foi escrito sob a disciplina; findings High/Medium pontuais
   são aceitáveis e validam o mapping).

3. Se Verdict = BLOCK por bug no auditor (não no plano), abrir issue de
   refinement em `04-pending.md`. Se BLOCK por bug no plano, dispatchar
   fix.

- [ ] **Step 10.2: Não bloquear o commit deste plano em smoke**

O smoke é validação pós-merge da feature. Não é gate do commit deste
plano em si — o commit segue mesmo que o smoke aponte ajustes (que
viram follow-up).

---

## Task 11: Commit atômico

**Files:**
- (sem write — apenas git operations)

- [ ] **Step 11.1: git add tudo**

Run:

```bash
cd .claude/worktrees/plan-auditor
git add .claude/rules/plan-auditor.md \
        CLAUDE.md \
        .claude/rules/superpowers.md \
        .claude/rules/subagent-workflow.md \
        .claude/rules/README.md \
        .gitignore \
        CHANGELOG.md \
        docs/design/04-pending.md \
        docs/design/08-session-handoff.md \
        docs/superpowers/plans/2026-06-04-plan-auditor.md
```

- [ ] **Step 11.2: Confirmar status**

Run: `cd .claude/worktrees/plan-auditor && git status --short`
Expected: 10 arquivos staged (9 modified/added + 1 plano novo), nada
unstaged.

- [ ] **Step 11.3: Commit com mensagem canônica**

```bash
cd .claude/worktrees/plan-auditor
git commit -m "$(cat <<'EOF'
feat(rules): plan auditor — 12 checks pós writing-plans

Entrega .claude/rules/plan-auditor.md como rule + protocolo de
dispatch: gsd-code-reviewer recebe o prompt e aplica 12 checks
classificados em 4 severities (2 Critical / 4 High / 3 Medium /
3 Low) ao plano alvo. Critical findings bloqueiam execution-handoff
do superpowers:writing-plans até fix-dispatch resolver. Re-audit cap
em 3 rodadas, override inline via comentário no topo do plano.

Integração: CLAUDE.md (workflow table), .claude/rules/superpowers.md
(map + nota), .claude/rules/subagent-workflow.md (nova row),
.claude/rules/README.md (index), .gitignore (.planning/plan-reviews/).
Doc-sync: CHANGELOG [Unreleased], 04-pending fechamento,
08-session-handoff atualização.

Sem touch em engine/ ou validators/. Suite total inalterada.

Spec: docs/superpowers/specs/2026-06-04-plan-auditor-design.md
Plan: docs/superpowers/plans/2026-06-04-plan-auditor.md
EOF
)"
```

- [ ] **Step 11.4: Verificar commit**

Run: `cd .claude/worktrees/plan-auditor && git log -1 --stat`
Expected: commit com 10 arquivos no stat, mensagem canônica.

Run: `cd .claude/worktrees/plan-auditor && git status`
Expected: "nothing to commit, working tree clean".

---

## Self-Review summary

Após executar Task 11, verifique:

1. **Spec coverage:** todas 6 questões da tabela "Open questions resolvidas
   no brainstorm" do spec têm correspondência nas tasks 1-9? ✓
2. **Placeholder scan:** nenhuma task contém TBD/TODO sem código inline.
3. **Type consistency:** `plan-auditor`, `gsd-code-reviewer`,
   `.planning/plan-reviews/`, `audit-override` aparecem com grafia
   idêntica em todas as tasks.

---

## Notas pro executor

- Cada task tem "ARQUIVOS PERMITIDOS PARA EDIT" implícito na seção
  **Files:**. Não toque nada fora.
- Tasks 2-5 e 8-9 mexem em load-bearing (CLAUDE.md, rules, design docs).
  Justificativa textual já está em cada task — não é scope creep.
- Smoke (Task 10) é orchestrator-driven, não executor-driven.
- Commit é único e atômico (Task 11). Mandamento #6 doc-sync exige
  mesma-commit.
