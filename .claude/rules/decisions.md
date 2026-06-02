# Decisões — protocolo de manipulação

Como respeitar `docs/design/01-decisions.md`. Mandamento #1.

## As 8 decisões LOAD-BEARING (NÃO mexer sem revisitar)

Estas afetam toda a arquitetura — quebrar = retrabalho cascateado.

| # | Decisão | Consequência se quebrar silentemente |
|---|---|---|
| 14 | Config scope = um workflow-config por sub-projeto (monorepo) | quebra projetos monorepo, dados conflitam entre sub-projetos |
| 15 | Versioning model = snapshot copy local (fork-and-forget) | reintroduz runtime dep que Decision 22 rejeita |
| 18 | Skill location = standalone repo em `~/Documents/feature-forge/` | quebra `forge init` + per-project install |
| 19 | Language = Python core + Bash dispatcher + YAML/MD specs | requer reescrever 21K LOC se mudar |
| 20 | Persistence = SQLite (graph) + arquivos (config, memory, docs) | quebra hooks + 17 graph queries canônicas |
| 22 | No runtime deps em outras skills (absorb patterns only) | quebra portability + viola Decision 18 |
| 23 | Validator cascade = fail-fast por default | quebra UX dos 14 validators + cascade behavior |
| 27 | Pause = `deferred` auto-resumable; abort = 2-step via `forge undo` | quebra resume + perda de progresso silenciosa |

## As 7 direcionais (Fase 3.5) — podem evoluir com ADR note

Listadas em `docs/design/01-decisions.md` §Decisions deferred + §Decisions
that could be revisited. Mudança aceita SE acompanhada de:

- Commit body explicando rationale
- Entrada em CHANGELOG `### Changed`
- Sem promoção pra "locked" sem brainstorm explícito com user

## Protocolo "Revisita decisão N"

Quando há razão real pra revisitar uma locked (deve ser raríssimo):

### Passo 1 — brainstorming explícito

Use `superpowers:brainstorming` com user. Pergunta-âncora: "Por que esta
decisão foi tomada originalmente?" Leia o rationale em `01-decisions.md`
antes da conversa.

### Passo 2 — dispatch edit com instrução literal

```
Agent[gsd-executor] prompt:
  TAREFA: Revisita decisão N — atualiza tabela em
  docs/design/01-decisions.md.

  ARQUIVOS PERMITIDOS PARA EDIT: docs/design/01-decisions.md, CHANGELOG.md

  REGRAS:
    - APPEND nova linha à tabela; NÃO deleta a linha antiga
    - Marca a linha antiga como "(superseded by row X — YYYY-MM-DD)"
    - Adiciona entrada em CHANGELOG sob ### Changed (load-bearing)
      contendo TEXTO LITERAL "Revisita decisão N: <novo choice> — <rationale>"

  CRITÉRIO DE SUCESSO:
    - Linha histórica preservada em 01-decisions.md
    - CHANGELOG contém "Revisita decisão N"
    - Commit message contém "Revisita decisão N"

  ANTI-PADRÕES:
    - Não deletar linha antiga
    - Não mudar numeração das outras decisões
    - Não simplificar rationale antigo
```

### Passo 3 — review com foco específico

`Agent[gsd-code-reviewer]` prompt explícito: "verifica que linha antiga da
decisão N foi preservada em 01-decisions.md (append-only) + CHANGELOG
contém 'Revisita decisão N' textual + commit message idem".

### Passo 4 — commit naturalmente passa pelo hard-block

O hook `.claude/hooks/pre-commit-feature-forge.sh` faz hard-block se
`01-decisions.md` está staged sem "Revisita decisão" em CHANGELOG staged.
No fluxo correto, isso NUNCA dispara — só dispara se algo escapou.

## Distinção quick reference

| Tipo | Característica | Pode mudar via |
|---|---|---|
| **Locked** (27 items) | Imutável sem revisitar formal | Protocolo acima |
| **Locked load-bearing** (8 subset) | Quebra arquitetura inteira se mudar | Protocolo + revisita Phase plan |
| **Direcional** (7 Fase 3.5) | Pode evoluir | ADR-style commit note |
| **Revisitável** (3 mencionadas em 01-decisions.md "could be revisited") | Refator local | Commit com rationale |

Fonte canônica: `docs/design/01-decisions.md`. Em conflito, esse doc vence.
