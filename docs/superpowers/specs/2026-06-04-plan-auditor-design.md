# Plan Auditor — Design Spec

**Date:** 2026-06-04
**Status:** Approved (brainstorm session 2026-06-04)
**Related:** `docs/design/04-pending.md` (auditoria pós-plano), `.claude/rules/superpowers.md`, `superpowers:writing-plans` SKILL.md

## Contexto

O fluxo `superpowers:writing-plans` termina com Self-Review inline leve (spec coverage, placeholder scan, type consistency) e oferece, opcionalmente, o `plan-document-reviewer-prompt.md`. Para feature-forge — projeto com 6 mandamentos, 27 locked decisions e matriz doc-sync — esse review default é insuficiente: não captura load-bearing edits sem justificativa, ausência de cerimônia "Revisita decisão N", doc-sync gaps, reuse-first ignorado, voz quebrada.

Resultado observado: planos que parecem completos passam pro execution-handoff carregando débito que só aparece no review pós-implementação — ou, pior, quebram o pre-commit hard-block depois.

## Goal

Um auditor pós-plano que dispara automaticamente após writing-plans terminal-state, verifica 12 checks específicos do projeto, classifica findings por severity. Critical bloqueia execution-handoff até fix-dispatch resolver.

## Non-Goals

- Escrever validators Python novos. Auditor vive como rule + prompt.
- Criar novo agent type. Reusa `gsd-code-reviewer`.
- Bloquear pre-commit (já é coberto pelo hook existente pra `01-decisions.md`).
- Substituir code review pós-impl. Roda em momento diferente do ciclo.

## Architecture

### Componente

- `.claude/rules/plan-auditor.md` — prompt determinístico + checklist dos 12 checks + voz mentor calmo
- Output: `.planning/plan-reviews/<plan-slug>-review-r<N>.md` (gitignored, mesma política do `REVIEW.md` de code review)

### Trigger

Override do "Execution Handoff" do `superpowers:writing-plans` SKILL.md:

1. Plano escrito e salvo em `docs/superpowers/plans/<...>.md`
2. Self-review inline do SKILL.md concluído
3. **ANTES** do prompt "Two execution options", orquestrador OBRIGATORIAMENTE dispatcha:
   ```
   Agent[gsd-code-reviewer] com prompt de .claude/rules/plan-auditor.md
     input: plan path + spec path + git diff do plano
     output: .planning/plan-reviews/<plan-slug>-review-r1.md
   ```

### Fluxo decisório

Após auditor produzir `PLAN-REVIEW.md` com verdict:

- **PASS** (0 findings ou só Low) → orquestrador segue pro execution-handoff original.
- **PASS_WITH_WARNINGS** (High/Medium, sem Critical) → orquestrador apresenta findings ao user no formato 3-caminhos (✅ implementar / ⏭️ não implementar / 🤔 investigar). User decide cada finding. Findings aceitos → dispatch `gsd-code-fixer` no plano (não no código — fixer recebe prompt "atualiza o plano aplicando findings X, Y, Z").
- **BLOCK** (1+ Critical) → execution-handoff NÃO oferecido. Apresenta criticals ao user, dispatcha fix no plano, re-audita.

### Re-audit policy

- Limite: 3 rodadas.
- Na 4ª rodada com BLOCK, escala pro user via `AskUserQuestion` com 3 opções:
  1. Continuar fixing (rodada 5+)
  2. Aceitar com override expresso no plano
  3. Abortar plano e voltar pro brainstorming

### Override mechanism

User pode aceitar plano com Critical pendente registrando override em comentário no topo do plano:

```html
<!-- audit-override: C-001 — razão concreta da aceitação -->
```

Auditor na próxima rodada lê override e re-classifica esse finding como `acknowledged` (não bloqueia mais, mas é listado na seção "Acknowledged overrides").

## Os 12 checks com severity mapping

### Critical (bloqueia execution-handoff)

Falha aqui = retrabalho garantido downstream.

- **C1. Locked decision ceremony (Mandamento #1)** — plano edita `docs/design/01-decisions.md` sem task que adiciona "Revisita decisão N" em CHANGELOG + commit message. Pre-commit hard-block bate depois; melhor pegar agora.
- **C2. Spec coverage** — spec referenciado não existe OU requisito do spec sem task correspondente. Sem isso, plano voa cego.

### High (warn forte, orquestrador decide)

Falha aqui = scope creep ou disciplina quebrada.

- **H1. Load-bearing files sem justificativa (Mandamento #4)** — task toca `docs/design/00,05,06,07.md`, `CLAUDE.md`, `.claude/rules/**`, `presets/`, `cards/`, `docs/schemas/` sem explicar por quê.
- **H2. Doc-sync coverage (Mandamento #6)** — toca `engine/`, `validators/`, `hooks/`, `templates/`, `cards/`, `presets/`, `docs/schemas/` sem task explícita de CHANGELOG + handoff + README.
- **H3. Reuse-first ignorado (Mandamento #3)** — plano cria helper/validator/template novo sem mencionar consulta a `forge graph Q11-Q17` ou inventário.
- **H4. Testing gates (Mandamento #2)** — feature/fix sem tasks de test ANTES da impl, ou sem pytest path/validator referenciado.

### Medium (informativo, fix recomendado)

Falha aqui = atrito operacional, não débito arquitetural.

- **M1. Scope file whitelist** — task sem lista explícita de "ARQUIVOS PERMITIDOS PARA EDIT" (subagent vai improvisar).
- **M2. Pending gaps coverage** — plano fecha gap de `04-pending.md` sem task de update, ou introduz gap novo sem anotação.
- **M3. Subagent dispatchability** — task sem TAREFA + CRITÉRIO DE SUCESSO + ANTI-PADRÕES suficientes pro context-pack.

### Low (cosmético)

Falha aqui = polish, não correctness.

- **L1. Voice check (Mandamento #5)** — voz corporativa, emoji decorativo, hedging ("vou tentar", "considere").
- **L2. Placeholder scan** — TBD, TODO, "...", "implement here".
- **L3. Type/name consistency** — `clearLayers()` em task 3 vs `clearFullLayers()` em task 7.

## Output format

```markdown
# Plan Review: <plan-slug>
**Plano:** docs/superpowers/plans/<...>.md
**Spec:** docs/superpowers/specs/<...>.md
**Rodada:** N/3
**Verdict:** BLOCK | PASS_WITH_WARNINGS | PASS

## Critical (N) — bloqueia execution-handoff
- [C-001] {check ID}: {finding curto} — task #M, linha L
  Por que importa: {regra/contract violado}
  Caminho A: {fix forward}
  Caminho B: {revert/remover}
  Caminho C: {split/escalate}

## High (N) — orquestrador decide
[...mesma forma...]

## Medium (N) | ## Low (N)
[...mesma forma...]

## Acknowledged overrides (se houver)
- C-XXX: <razão do override inline>
```

## Integração no doc-sync

Updates obrigatórios no mesmo commit que entrega o auditor:

- `CLAUDE.md` §Workflow por verbo — coluna "Skills" das linhas "Adicionar feature/recurso" e "Refatorar" ganha `+ plan-auditor (dispatched)` após `writing-plans`.
- `.claude/rules/superpowers.md` — tabela "Superpowers map" ganha row `plan-auditor` com Trigger "pós writing-plans terminal-state" e Bloqueia "sim — critical findings".
- `.claude/rules/subagent-workflow.md` §"Qual subagent_type pra quê" — row novo: "Auditar plano pós-writing-plans" → `gsd-code-reviewer` com prompt `.claude/rules/plan-auditor.md`.
- `CHANGELOG.md` — entrada `## [Unreleased] ### Added — plan auditor (.claude/rules/plan-auditor.md) + integração pós writing-plans`.
- `docs/design/08-session-handoff.md` — "Última atualização" + estado.
- `docs/design/04-pending.md` — risca gap "auditoria pós-plano" se listado; senão, anota como fechado nesta release.
- `.gitignore` — adicionar `.planning/plan-reviews/` se ainda não coberto.

Sem mudança em `engine/`, sem validator Python novo, sem hook novo. Tudo é rule + protocolo de dispatch.

## Open questions resolvidas no brainstorm

| Questão | Resposta |
|---|---|
| Forma & peso | Subagent dispatchado |
| Trigger | Auto pós writing-plans |
| Checks selecionados | Todos os 12 |
| Severity model | 4 níveis com Critical bloqueando |
| Agent type | `gsd-code-reviewer` com prompt focado |
| Output location | `.planning/plan-reviews/` (gitignored) |

## Anti-goals (deliberadamente fora do v1)

- Severity overrides via config file (override é INLINE-ONLY no plano).
- Cross-plan auditing (auditor vê apenas o plano atual).
- Auto-fix mode (sempre dispatch separado pro fixer).
- Validação de qualidade do spec (auditor verifica plano vs spec, não audita o spec em si).

## Considerações futuras (fora do v1)

- `forge plan-audit` CLI wrapper, se o auditor provar valor em uso real (alternativa C rejeitada no brainstorm).
- Refinamento do severity mapping baseado em quais checks pegam bug real ao longo do tempo.
- Tracking estatístico: rodadas médias por auditoria, quais checks disparam mais.
