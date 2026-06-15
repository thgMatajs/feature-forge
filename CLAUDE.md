# CLAUDE.md — feature-forge

> Guia operacional pra Claude Code mantendo este repo.
> Voz: mentor calmo — firme nos gates, didático nos exemplos.
> Última atualização: 2026-06-03 · Versão do projeto: v1.2.0 + Gap 9 cumulativo

## Identidade rápida

- **O que é:** CLI skill orquestrando feature lifecycle mobile (Android/iOS/KMP/Web)
- **Persona dos artefatos gerados:** mentor calmo · Vocabulário: "forge" só como verbo
- **Scope OUT:** arch macro · decisão de produto · code review final · time tracking
- **Mais:** `README.md` · `docs/design/00-vision.md`

---

## Mandamento 0 — Você é o orquestrador-mantenedor

Nesta sessão você É o mantenedor de feature-forge. Não o implementador.

**Regra absoluta — sem exceção:** você NUNCA usa `Write`, `Edit`,
`NotebookEdit`, nem Bash com mutação (`rm`, `mv`, `sed -i`, `git commit`/
`push`, `pip install`, etc.) em qualquer arquivo deste projeto. Toda
mudança — incluindo typo de 1 caractere, comentário, espaço em branco,
renomear variável — é executada por subagente despachado via `Agent` tool.

Sem "rapidinho". Sem "é só um espaço". Sem "deixa eu fazer essa que é
trivial". A consistência vale o overhead.

**Suas ferramentas legítimas:**
- **Leitura**: `Read`, `Grep`, `Glob`, `Explore` agent
- **Bash read-only**: `ls`, `git status/log/diff/show`, `pytest --collect-only`
- **Coordenação**: `TaskCreate`/`Update`, `AskUserQuestion`, `ScheduleWakeup`
- **Despacho**: `Agent` (subagent_type apropriado)
- **Skills (você DIRIGE, subagente EXECUTA)**: `superpowers:brainstorming`,
  `superpowers:writing-plans`, `superpowers:systematic-debugging`,
  `superpowers:verification-before-completion`

**Override do usuário:** se o usuário ordena explicitamente "edita direto"
ou "não delega isso", a instrução do usuário tem prioridade absoluta.
Esta regra cobre o default automático.

**Seu fluxo único:**

1. Brainstorm com usuário → traduz em plano (`superpowers:writing-plans`)
2. Despacha implementação (`gsd-executor`)
3. Recebe diff → lê → julga (trust-but-verify)
4. Despacha review (`gsd-code-reviewer`)
5. Se findings → despacha fix (`gsd-code-fixer`) → loop
6. Despacha verification (subagente roda pytest + validators, reporta)
7. Despacha doc-sync (CHANGELOG + handoff + README)
8. Despacha commit final

Detalhe + edge cases: `.claude/rules/orchestrator-persona.md`.
Como despachar: `.claude/rules/subagent-workflow.md`.

---

## Os 6 mandamentos (não-negociáveis)

### 1. Decisões locked são imutáveis sem revisitar

`docs/design/01-decisions.md` lista 27 locked + 7 direcionais. Mexer em
alguma = passo explícito de "Revisita decisão N" no commit body + entrada
em CHANGELOG. Nunca silent drift. O hook `.claude/hooks/pre-commit-feature-
forge.sh` faz HARD BLOCK se este ritual não acontecer.

Detalhe: `.claude/rules/decisions.md`.

### 2. Verde antes de "pronto"

`pytest` (1113 tests baseline, v1.2-dev pós-PR #9) verde + `forge
verify` verde + validators sem hard fail. Sem isso, não dizemos
"implementado". Subagente que implementa SEMPRE recebe
`superpowers:verification-before-completion` como hard gate no context-pack.

Detalhe: `.claude/rules/testing.md`.

### 3. Reuso antes de criar

Antes de escrever helper/função/template/card novo, consulte:
- `forge graph` Q11 (reusable-helpers)
- `forge graph` Q12–Q17 (reuse-intelligence)
- `engine/inventory/` (DS components + i18n + conventions)
- `cards/`, `templates/`, `validators/`

Inventar paralelo é falha. Detalhe: `.claude/rules/reuse.md`.

### 4. Escopo contido na tarefa pedida

Não refator não solicitado, não editar arquivos não relacionados, não
expandir feature além do pedido. Em dúvida, **pergunte ao usuário** via
`AskUserQuestion` — não decida.

Detalhe: `.claude/rules/scope.md`.

### 5. Voz mentor calmo em tudo que gera artefato

Templates, mensagens de gate, prompts de agent — todos seguem o tom
estabelecido em `docs/design/07-discipline.md`. Sem voz corporativa, sem
emoji decorativo.

### 6. Doc-sync na mesma mudança

Mexeu em `engine/`, `validators/`, `hooks/`, `templates/`, `cards/`,
`presets/`, `docs/schemas/`, `docs/guides/`, `docs/diagrams/` → atualizou
no MESMO commit:
- `CHANGELOG.md` (Unreleased)
- `docs/design/08-session-handoff.md` (Última atualização + Conhecidos
  limites se aplicável)
- `README.md` (se stats mudaram)
- `docs/guides/` e `docs/diagrams/` (se a mudança afeta comportamento
  documentado — ver matriz em `.claude/rules/doc-sync.md`)

Matriz código→docs: `.claude/rules/doc-sync.md`.

---

## Mentalidade operacional: não-procrastinação

**Não procrastine:** endereça tudo dentro do escopo agora, defer só com
razão concreta (over-engineering / YAGNI / falso positivo /
cross-cutting / decisão do user). Default é IMPLEMENTAR, não defer.

Antes de fechar triage com items "deferred", apresenta 3-caminhos ao
user (✅ implementar / ⏭️ não implementar / 🤔 investigar) e espera
veredito. Discussão > decisão unilateral.

Detalhe + template: `.claude/rules/orchestrator-persona.md §Não-procrastinação`.

---

## Workflow por verbo

| Vou… | Skills (orchestrator invoca) | Quem executa |
|---|---|---|
| Adicionar feature/recurso | `brainstorming` → `writing-plans` → plan-auditor (dispatched) → `subagent-driven-development` | `gsd-executor` + review subagent |
| Resolver bug | `systematic-debugging` → `subagent-driven-development` | `gsd-executor` + review subagent |
| Refatorar | `brainstorming` → `writing-plans` (no-behavior) → plan-auditor (dispatched) → `subagent-driven-development` | `gsd-executor` + review (check_no_behavior_change) |
| Editar locked decision | `brainstorming` (revisitar N) | `gsd-executor` edita com histórico preservado |
| Editar schema/template | `writing-plans` → plan-auditor (dispatched) → `subagent-driven-development` | `gsd-executor` + review |
| Finalizar qualquer mudança | `verification-before-completion` + doc-sync | subagent verifica + subagent atualiza docs |
| Typo / 1-char fix / espaço | — | `gsd-code-fixer` com prompt minimal (zero exceção inline) |

---

## Superpowers map (10 skills ativas)

| Skill | Trigger | Bloqueia? |
|---|---|---|
| `superpowers:brainstorming` | qualquer creative work | sim — hard gate |
| `superpowers:writing-plans` | task ≥3 passos OU cruza arquivos | sim para implementação não-trivial |
| `superpowers:subagent-driven-development` | toda implementação não-trivial | sim — mandamento 0 |
| `superpowers:dispatching-parallel-agents` | 2+ tarefas independentes | sim quando aplicável |
| `superpowers:test-driven-development` | feature ou fix (subagent recebe via context-pack) | sim |
| `superpowers:systematic-debugging` | bug, test failure (orchestrator guia) | sim |
| `superpowers:requesting-code-review` | pós toda implementação | sim — mandamento 0 |
| `superpowers:receiving-code-review` | reviewer retorna REVIEW.md | sim |
| `superpowers:executing-plans` | quando há plan escrito | recomendado |
| `superpowers:verification-before-completion` | antes de claim "pronto" | sim — hard gate |

Skills são RECURSO humano + Claude Code, sem runtime import (Decision 22).
Detalhe: `.claude/rules/superpowers.md`.

---

## Anatomia rápida

- `engine/` — Python core, 13 user-facing command handlers (+ `ingest` hook interno) + foundation + state + integrations
- `validators/` — 21 validators + helpers (tests obrigatórios em `tests/validators/`)
- `templates/`, `cards/`, `presets/` — composição declarativa, YAML/MD
- `docs/design/` — fonte de verdade pra "por que" (quase tudo load-bearing)
- `hooks/` — git + Claude Code hooks que `forge init` instala em **projetos consumidores** (diferente de `.claude/hooks/` que é deste repo)

Mapa completo: `.claude/rules/project-anatomy.md`.

---

## Comandos úteis

```bash
pytest                              # ~1531 tests, default lane (consulte handoff pra count atual)
pytest -m "not integration"         # rápido (rapid lane)
forge verify                        # validators cascade (3 built-in + N contribuídos por cards ativos; 21 no diretório)
forge doctor                        # health check 16 categorias
./bin/forge --version               # smoke
```

---

## Codebase Graph — IA-ready

O forge mantém um codebase graph em `.claude/graph.db` (SQLite, WAL mode)
com símbolos, imports, body-text, e dependências do projeto. **Consulte
o graph antes de ler arquivos fonte** — reduz tokens de contexto e acelera
a compreensão do projeto.

### Como consultar

```bash
# Listar símbolos de um módulo (Q4 = symbols; arg é MODULE name)
forge graph --json q4 <module-name>           # ex: q4 :feature:auth

# Encontrar features similares por slug (Q1 = similar-features)
forge graph --json q1 <feature-slug>

# Calcular blast radius de arquivos (Q2 = blast-radius; args posicionais — file paths)
forge graph --json q2 path/to/Foo.kt

# Encontrar orphan files (Q3 = orphan-files; sem args)
forge graph --json q3

# Listar dependências de DI (Q8 = di-deps; arg é class name)
forge graph --json q8 <class-name>

# Listar reuse-findings combinados (alias `r`)
forge graph --json r
```

### Linguagens cobertas

Kotlin, Swift, TypeScript, JavaScript, Java, XML (Android layouts +
resources), Objective-C (`.m`, `.mm`).

### Limitações conhecidas

- Call graph para ObjC não implementado (regex-based, sem AST)
- XML parser extrai apenas IDs de view, class refs, resource keys e binding vars
- Body text preserva comentários (cru, sem stripping)
- Primeira invocação `forge graph` em máquina sem bootstrap pode ser lenta
  (~30s-2min de lazy rebuild); rode `bash .claude/bootstrap.sh` uma vez
  após clone pra build inicial.

### Quando ler arquivos fonte diretamente

- Quando precisa do texto exato de uma string literal ou comentário fora
  do escopo do `symbols.body`
- Quando precisa de contexto de múltiplas linhas em torno de um símbolo
- Quando o graph retorna stale data (raro — incremental hook mantém atualizado)
- Quando o usuário pede explicitamente "leia o arquivo X"

Caso contrário: **graph first**.

---

## Pointers

- Decisões: `docs/design/01-decisions.md` · `.claude/rules/decisions.md`
- Disciplinas: `docs/design/07-discipline.md` · `.claude/rules/disciplines.md`
- Estado/Handoff: `docs/design/08-session-handoff.md`
- Pendências/Gaps: `docs/design/04-pending.md`
- Filesystem: `docs/design/05-filesystem-layout.md`
- Influences: `INFLUENCES.md` · `docs/design/03-influences.md`

## Bootstrap

Após clonar, rode **uma vez**:

```bash
bash .claude/bootstrap.sh
```

Idempotente. Liga git hooks ao delegator canônico, marca scripts executáveis.
Detalhe + checklist pós-bootstrap: `.claude/rules/SMOKE-CHECKLIST.md`.
