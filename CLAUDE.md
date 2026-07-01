# CLAUDE.md — feature-forge

> Guia operacional pra Claude Code mantendo este repo.
> Voz: mentor calmo — firme nos gates, didático nos exemplos.
> Última atualização: 2026-06-25 · Versão do projeto: v1.6.1

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

Detalhe + edge cases: `.claude/bin/mem find "identidade orquestrador-mantenedor voz operacional"`.
Como despachar: `.claude/bin/mem find "qual subagent_type gsd-executor reviewer fixer"`.

---

## Os 7 mandamentos (não-negociáveis)

### 1. Decisões locked são imutáveis sem revisitar

Mexer numa decisão de `docs/design/01-decisions.md` = passo explícito de
"Revisita decisão N" no commit body + entrada em CHANGELOG. Nunca silent
drift. O hook `.claude/hooks/pre-commit-feature-forge.sh` faz HARD BLOCK
se este ritual não acontecer.

Detalhe: `.claude/bin/mem find "como revisitar decisão locked sem silent drift"`.

### 2. Verde antes de "pronto"

`pytest` verde + `forge verify` verde + validators sem hard fail. Sem
isso, não dizemos "implementado". Subagente que implementa SEMPRE recebe
`superpowers:verification-before-completion` como hard gate no context-pack.

Detalhe: `.claude/bin/mem find "TDD pytest gates verde antes de pronto"`.

### 3. Reuso antes de criar

Antes de escrever helper/função/template/card novo, consulte `forge graph`
(Q11–Q17), `engine/inventory/`, e `cards/`/`templates/`/`validators/`.
Inventar paralelo é falha.

Detalhe: `.claude/bin/mem find "reuso forge graph antes de criar helper"`.

### 4. Escopo contido na tarefa pedida

Não refator não solicitado, não editar arquivos não relacionados, não
expandir feature além do pedido. Em dúvida, **pergunte ao usuário** via
`AskUserQuestion` — não decida.

Detalhe: `.claude/bin/mem find "edite só o que a tarefa pede whitelist"`.

### 5. Voz mentor calmo em tudo que gera artefato

Templates, mensagens de gate, prompts de agent — todos seguem o tom de
`docs/design/07-discipline.md`. Sem voz corporativa, sem emoji decorativo.

### 6. Doc-sync na mesma mudança

Mexeu em `engine/`, `validators/`, `hooks/`, `templates/`, `cards/`,
`presets/`, `docs/schemas/`, `docs/guides/`, `docs/diagrams/` → atualizou
no MESMO commit: `CHANGELOG.md` (Unreleased) + `README.md` (se stats
mudaram) + guides/diagrams (se comportamento mudou).

O **estado de sessão** não é per-commit: no fim de trabalho significativo,
rode `.claude/bin/mem session` (handoff curado, committed, com git_meta
automático). O `docs/design/08-session-handoff.md` congelou — snapshot
histórico + fallback de bootstrap do SessionStart, não mais editado a cada
sessão.

Matriz código→docs: `.claude/bin/mem find "matriz código docs sincronizar ao tocar engine"`.

### 7. mem é a primeira fonte de contexto passado

Antes de responder perguntas de estado / status / "o que falta" / histórico,
e antes de despachar subagente ou decidir algo com precedente, consulte
`.claude/bin/mem find "<tema>"` — no PRIMEIRO turno, em paralelo com Read/git,
não depois. O mem carrega a disciplina de processo, o handoff de estado (via
`mem session`) e os temas abertos ativos (notas `reference` que apontam pro
backlog). Os docs (`04-pending.md`, specs) enumeram o detalhe canônico; o mem
surfa o relevante. Recall raso = falha de processo, não do mem.

Detalhe: `.claude/bin/mem find "mem-first primeira fonte de contexto estado status"`.

---

## Memória persistente (mem) — índice das rules

> O **Mandamento #7** (Tier-0) torna o mem-first invariante; esta seção é o
> índice de recuperação das rules por tema.

Este repo tem memória persistente curada via `.claude/bin/mem` (acervo curado:
decisões, disciplinas, despacho de subagente, reuso, testing, doc-sync,
plan-auditor, e learnings de sessão). As rules detalhadas de
`.claude/rules/` foram enxugadas pra ponteiros — o detalhe vive no acervo
e é recuperável por tema.

**Consulte `.claude/bin/mem find "<tema>"` ANTES de:** despachar subagente,
revisar código, decidir algo, ou tocar um tema que tem convenção. Recupere
o corpo acionável com `.claude/bin/mem get <id>`.

**Grave no acervo** (`.claude/bin/mem add` / `mem session`) em correções
que viram lição, decisões, e ao fim de sessão. O `--json` é flag GLOBAL
(vem antes do subcomando: `mem --json find "..."`).

**Após `git clone` ou `git pull` que traga JSONL novo**, rode
`.claude/bin/mem rebuild` pra reconstruir o índice (`mem.db` é gitignored —
derivado do JSONL commitado).

Queries de partida (tema → consulta):

| Vou… | Consulta |
|---|---|
| Despachar subagente | `.claude/bin/mem find "despacho subagente context-pack"` |
| Escolher subagent_type | `.claude/bin/mem find "qual subagent_type gsd-executor reviewer fixer"` |
| Reusar antes de criar | `.claude/bin/mem find "reuso forge graph antes de criar"` |
| Conferir gates de teste | `.claude/bin/mem find "TDD pytest gates verde antes de pronto"` |
| Sincronizar docs | `.claude/bin/mem find "matriz código docs sincronizar ao tocar engine"` |
| Auditar um plano | `.claude/bin/mem find "12 checks auditoria de plano"` |
| Revisitar decisão locked | `.claude/bin/mem find "como revisitar decisão locked sem silent drift"` |
| Aplicar 3-caminhos num gate | `.claude/bin/mem find "exatamente 3 caminhos em todo gate template"` |
| Escolher skill superpowers | `.claude/bin/mem find "10 skills superpowers triggers"` |
| Navegar o repo | `.claude/bin/mem find "onde cada coisa vive mapa de navegação"` |

O Tier-0 acima (Mandamento 0 + os 7 mandamentos + fluxo único) permanece
sempre-on e não depende do mem.

---

## Bootstrap

Após clonar, rode **uma vez**:

```bash
bash .claude/bootstrap.sh
```

Idempotente. Liga git hooks ao delegator canônico, marca scripts
executáveis. Em seguida, `.claude/bin/mem rebuild` reconstrói o índice da
memória a partir do JSONL commitado.

Detalhe + checklist pós-bootstrap: `.claude/bin/mem find "5 verificações de smoke pós-bootstrap"`.
