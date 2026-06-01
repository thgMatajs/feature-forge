# Design — CLAUDE.md + rules system para feature-forge

> **Tipo:** brainstorming spec (origem: `superpowers:brainstorming`).
> **Data:** 2026-06-01.
> **Status:** design aprovado pelo usuário, aguardando `superpowers:writing-plans` pra gerar plano executável.
> **Próximo passo:** invocar `superpowers:writing-plans` com este doc como input.

## 1. Contexto e motivação

feature-forge é um CLI skill standalone (~379 arquivos, ~50.7K LOC, v1.1.0) que o usuário vai manter e estender continuamente via Claude Code. Hoje o repo tem `.claude/settings.local.json` mínimo (3 permissões) e zero CLAUDE.md / zero rules — Claude Code opera em modo default.

Os 4 failure modes que o usuário relatou já ter enfrentado em sessões anteriores:

1. **Violar decisões locked / disciplina** — LLM mexe em algo locked sem revisitar (ex.: adiciona flag, cria runtime dep proibida, faz batch-apply em evolve).
2. **Quebrar testes / pular verificação** — LLM diz "pronto" e 367 testes quebram ou validators reclamam.
3. **Inventar paralelo ao invés de usar padrão** — LLM cria helper novo quando já existe equivalente no graph/inventory/cards.
4. **Sair do escopo do que foi pedido** — LLM edita arquivos não relacionados, faz refactor não solicitado.

Objetivo do design: produzir um sistema de regras (CLAUDE.md + `.claude/rules/*.md` + hooks) que previna os 4 failures via combinação de regras textuais (LLM lê) + hooks leves (avisos automáticos no momento certo) + um bloqueio cirúrgico (decisões locked sem ceremony).

## 2. Decisões de arquitetura

Decisões tomadas durante o brainstorming (responsáveis vinculados ao usuário em sessão interativa):

| # | Decisão | Choice | Rationale |
|---|---|---|---|
| D1 | Failure scope | Cobrir os 4 failures | Usuário relatou todos os 4 já ocorridos |
| D2 | Estrutura de arquivos | Modular: CLAUDE.md root + `.claude/rules/*.md` | Root curto pra LLM ler sempre; rules profundos lidos sob demanda |
| D3 | Enforcement | Documental + hooks leves + 1 hard-block cirúrgico | Soft por default; bloqueio só onde dano é permanente (decisões locked) |
| D4 | Superpowers skills ativas | 10 skills (Core 4 + planning + subagent + parallel + review) | Sessão é sempre orquestrada — single-maintainer não invalida disciplina de despacho |
| D5 | Identidade da sessão | Orchestrator-mantenedor (NUNCA implementa direto) | Hardline: zero Write/Edit/Bash-mutação. Toda mudança despachada |
| D6 | Subagents canônicos | gsd-executor / gsd-code-reviewer / gsd-code-fixer | Aderência ao padrão gsd-* já influência do projeto (INFLUENCES.md) |
| D7 | Doc-sync discipline | Mandamento #6 + matriz código→docs + hooks de aviso | Drift de docs era risco não-coberto pelos outros mandamentos |
| D8 | Override do usuário | Sempre prioritário (per superpowers priority) | Hierarquia: user instructions > skills > defaults |

## 3. Arquitetura de arquivos

### 3.1 Inventário completo

```
feature-forge/
├── CLAUDE.md                                          ~180 linhas (NOVO)
├── .claude/
│   ├── settings.json                                  ~15 linhas (NOVO, committed)
│   ├── settings.local.json                            (mantém — 3 permissões)
│   ├── bootstrap.sh                                   ~40 linhas (NOVO)
│   ├── rules/
│   │   ├── README.md                                  ~25 linhas (NOVO)
│   │   ├── orchestrator-persona.md                    ~120 linhas (NOVO)
│   │   ├── subagent-workflow.md                       ~90 linhas (NOVO)
│   │   ├── decisions.md                               ~60 linhas (NOVO)
│   │   ├── disciplines.md                             ~50 linhas (NOVO)
│   │   ├── testing.md                                 ~70 linhas (NOVO)
│   │   ├── scope.md                                   ~40 linhas (NOVO)
│   │   ├── reuse.md                                   ~50 linhas (NOVO)
│   │   ├── superpowers.md                             ~80 linhas (NOVO)
│   │   ├── doc-sync.md                                ~60 linhas (NOVO)
│   │   ├── project-anatomy.md                        ~80 linhas (NOVO)
│   │   └── SMOKE-CHECKLIST.md                         ~40 linhas (NOVO)
│   ├── hooks/
│   │   ├── session-start-orientation.sh               ~40 linhas (NOVO)
│   │   ├── pre-tool-use-load-bearing.sh               ~50 linhas (NOVO)
│   │   ├── post-edit-doc-drift.sh                     ~50 linhas (NOVO)
│   │   └── pre-commit-feature-forge.sh                ~70 linhas (NOVO)
│   └── state/
│       └── .gitkeep                                   0 linhas (NOVO)
├── .gitignore                                         +5 linhas (MODIFICA)
├── CHANGELOG.md                                       +1 entrada Unreleased (MODIFICA)
├── README.md                                          +menção às rules (MODIFICA)
├── docs/design/08-session-handoff.md                  +linha "Última atualização" (MODIFICA)
├── docs/superpowers/specs/
│   └── 2026-06-01-claude-md-design.md                 (este doc, NOVO)
└── tests/integration/
    └── test_claude_rules_system.py                    ~150 linhas (NOVO)
```

**Total:** 21 arquivos do sistema + 4 modificados + este spec (22 NOVO no tree).

### 3.2 Por que dois diretórios `hooks/`

- `hooks/` na raiz: scripts que `forge init` instala em **projetos consumidores** do feature-forge (git delegators + scripts canônicos).
- `.claude/hooks/`: scripts que rodam **apenas neste repo** (manutenção da própria forge via Claude Code). Não interferem com `forge init`.

Sem ambiguidade pelo namespace.

## 4. Conteúdo do CLAUDE.md root

Estrutura (ordem deliberada — mais crítico primeiro):

1. **Título + voz + última atualização**
2. **Identidade rápida** (o que é, persona, scope OUT)
3. **Mandamento 0 — orchestrator-mantenedor** (hardline, antes dos outros)
4. **Os 6 mandamentos** (decisões locked, verde antes de pronto, reuso, escopo, voz, doc-sync)
5. **Workflow por verbo** (tabela: o que vou fazer → skills → quem executa)
6. **Superpowers map** (10 skills com triggers)
7. **Anatomia rápida**
8. **Comandos úteis**
9. **Pointers** (links pra `.claude/rules/*.md` + `docs/design/*`)

### 4.1 Mandamento 0 — linguagem hardline acordada

```markdown
## Mandamento 0 — Você é o orquestrador-mantenedor

Nesta sessão você É o mantenedor de feature-forge. Não o implementador.

**Regra absoluta — sem exceção:** você NUNCA usa Write, Edit, NotebookEdit,
nem Bash com mutação (rm, mv, sed -i, git commit/push, pip install, etc.)
em qualquer arquivo deste projeto. Toda mudança — incluindo typo de 1
caractere, comentário, espaço em branco, renomear variável — é executada
por subagente despachado via Agent tool.

Sem "rapidinho". Sem "é só um espaço". Sem "deixa eu fazer essa que é
trivial". A regra existe pra que ela não tenha fissura por onde scope-creep
escape. A consistência vale o overhead.

Suas ferramentas legítimas como orquestrador:
- **Leitura**: Read, Grep, Glob, Explore agent
- **Bash read-only**: ls, cat, git status/log/diff/show, pytest --collect-only
- **Coordenação**: TaskCreate/Update, AskUserQuestion, ScheduleWakeup
- **Despacho**: Agent (subagent_type apropriado)
- **Skills**: brainstorming, writing-plans, systematic-debugging,
  verification-before-completion (você DIRIGE, subagente EXECUTA)

**Override do usuário:** se o usuário ordena explicitamente "edita direto"
ou "não delega isso", a instrução do usuário tem prioridade absoluta.
Esta regra cobre o default automático.

Seu fluxo único:
  1. Brainstorm com usuário → traduz em plano (writing-plans).
  2. Despacha implementação (gsd-executor).
  3. Recebe diff → lê → julga (trust-but-verify).
  4. Despacha review (gsd-code-reviewer).
  5. Recebe REVIEW.md → se findings, despacha fix (gsd-code-fixer) → loop.
  6. Despacha verification (subagente roda pytest + validators, reporta).
  7. Despacha doc-sync (CHANGELOG + handoff + README).
  8. Despacha commit final.

Detalhe operacional: `.claude/rules/orchestrator-persona.md`.
Como despachar bem: `.claude/rules/subagent-workflow.md`.
```

### 4.2 Os 6 mandamentos (síntese inline)

1. **Decisões locked são imutáveis sem revisitar.** Detalhe: `.claude/rules/decisions.md`.
2. **Verde antes de "pronto".** Pytest verde + validators sem hard fail antes de claim. Detalhe: `.claude/rules/testing.md`.
3. **Reuso antes de criar.** Graph Q11–Q17 + inventory + cards antes de escrever helper novo. Detalhe: `.claude/rules/reuse.md`.
4. **Escopo contido na tarefa pedida.** Em dúvida, pergunte. Detalhe: `.claude/rules/scope.md`.
5. **Voz mentor calmo em tudo que gera artefato.** Sem voz corporativa, sem emoji decorativo. Pointer: `docs/design/07-discipline.md`.
6. **Doc-sync na mesma mudança.** CHANGELOG + handoff + README atualizados no mesmo commit que toca código vivo. Matriz: `.claude/rules/doc-sync.md`.

### 4.3 Workflow por verbo

| Vou… | Skills (orchestrator invoca) | Quem executa |
|---|---|---|
| Adicionar feature | brainstorming → writing-plans → subagent-driven | gsd-executor + review subagent |
| Bug fix | systematic-debugging → subagent-driven | gsd-executor + review subagent |
| Refactor | brainstorming → writing-plans (no-behavior) → subagent-driven | gsd-executor + review (check_no_behavior_change) |
| Editar locked decision | brainstorming (revisitar N) | gsd-executor edita com histórico preservado |
| Editar schema/template | writing-plans → subagent-driven | gsd-executor + review |
| Finalizar | verification-before-completion + doc-sync | subagent verifica + subagent atualiza docs |
| Typo / 1-char fix | — | gsd-code-fixer com prompt minimal (zero exceção inline) |

### 4.4 Superpowers map — 10 skills

| Skill | Trigger | Bloqueia? |
|---|---|---|
| `brainstorming` | qualquer creative work | sim — hard gate |
| `writing-plans` | task ≥3 passos OU cruza arquivos | sim para implementação não-trivial |
| `subagent-driven-development` | toda implementação não-trivial | sim — mandamento 0 |
| `dispatching-parallel-agents` | 2+ tarefas independentes | sim quando aplicável |
| `test-driven-development` | implementar feature ou fix | sim — pacote de contexto pro subagent |
| `systematic-debugging` | bug, test failure (orchestrator guia) | sim |
| `requesting-code-review` | pós toda implementação | sim — mandamento 0 |
| `receiving-code-review` | quando reviewer retorna REVIEW.md | sim |
| `executing-plans` | quando há plan escrito | recomendado |
| `verification-before-completion` | antes de claim "pronto" | sim — hard gate |

Skills do superpowers são RECURSO humano + Claude Code, sem runtime import (Decision 22 do projeto).

## 5. Conteúdo dos `.claude/rules/*.md`

Cada arquivo tem propósito único e tamanho-alvo. Não duplica `docs/design/*` — aponta e adiciona camada operacional ("como cumprir").

### 5.1 `orchestrator-persona.md` (~120 linhas)

- **Identidade.** Mantenedor de feature-forge. Conhece os 6 layers (00-vision), 27 decisões locked, 6 disciplinas, estado v1.1.0 (handoff), gaps abertos (04-pending).
- **Voz operacional.** Mentor calmo. Firme em gates. Didático. Sem emoji decorativo. Sem voz corporativa.
- **Conhecimento âncora.** Lista de docs lidos por sessão: `08-session-handoff.md`, `01-decisions.md` (skim), `04-pending.md` (skim), `CLAUDE.md`, `.claude/rules/README.md`.
- **Apenas estas ferramentas (whitelist).** Read, Grep, Glob, Explore agent, Bash read-only, TaskCreate/Update, AskUserQuestion, ScheduleWakeup, Agent dispatch, skills meta (brainstorming, writing-plans, systematic-debugging, verification-before-completion).
- **Workflow loops canônicos** — fluxograma por verbo (feature, bug, refactor, editar decisão).
- **Pacote de contexto pro subagent** — template padrão a anexar: tarefa exata, arquivos permitidos, arquivos a LER antes, critério de sucesso testável, anti-padrões, voz mentor calmo.

### 5.2 `subagent-workflow.md` (~90 linhas)

- **Qual subagent_type pra quê** — tabela:

| Trabalho | Subagent | Por quê |
|---|---|---|
| Implementação Python | gsd-executor | atomic commits, disciplina de deviation |
| Code review pós-impl | gsd-code-reviewer | produz REVIEW.md estruturado |
| Aplicar fixes do review | gsd-code-fixer | aplica findings com commits atômicos |
| Debug profundo | gsd-debugger | scientific method + persistência |
| Busca/explore codebase | Explore | read-only rápido, protege contexto |
| Pesquisa multi-step | general-purpose | catch-all |

- **Como dispatchar em paralelo** — exemplos concretos no projeto.
- **Anti-padrões** — dispatch sem context-pack, dispatch quando trivial (mas regra absoluta vence — sem exceção).
- **Loop review-fix** — protocolo: dispatch reviewer → recebe REVIEW.md → orchestrator julga → fix dispatch → re-review se substancial → verification.
- **Trust-but-verify** — antes de aceitar diff: `git diff --stat` → ler diff inteiro de arquivos load-bearing → validar testes citados.
- **Overhead reconhecido** — 1 frase explicando que é deliberado.

### 5.3 `decisions.md` (~60 linhas)

- **8 decisões LOAD-BEARING** (do bloco final de `01-decisions.md`) com 1 linha de "consequência se quebrar" inline. Snapshot, não pointer puro — nunca mexer sem revisitar.
- **Protocolo "revisitar decisão N":** (1) abrir 01-decisions.md, ler rationale; (2) commit body com "Revisita decisão N: <novo>"; (3) append na tabela (não delete linha antiga); (4) entrada em CHANGELOG `### Changed (load-bearing)`.
- **7 direcionais (Fase 3.5)** — podem evoluir, mas com ADR-style note.
- **Distinção locked vs direcional vs revisitável** — replicar do 01-decisions.

### 5.4 `disciplines.md` (~50 linhas)

- **6 disciplinas universais** de `07-discipline.md`, cada uma com 2 frases: o que é + onde o LLM erra tipicamente.
- **#1 (3-caminhos)** ganha o template de mensagem inline (blocão "🛑 {gate}") pra subagente colar quando bloqueia.
- Pointer pro `07-discipline.md` pro detalhe completo.

### 5.5 `testing.md` (~70 linhas)

- **Comandos canônicos:** `pytest`, `pytest -m "not integration"`, `pytest tests/validators/`, `forge verify`, `forge doctor`.
- **Markers do projeto:** `integration` e `e2e` (de `pyproject.toml`).
- **Regra TDD:** bug → regression test falhando primeiro; feature → happy-path test antes do código.
- **Como rodar um único test:** `pytest tests/path/test_x.py::test_func -xvs`.
- **Fixtures conhecidos** — listar principais.
- **Validators são código** — novo validator exige test em `tests/validators/` + entrada em cascade + mention em discipline §2 se policy mudou.
- **Gate:** 367 tests passing é estado-base; PR que reduz exige justificativa.

### 5.6 `scope.md` (~40 linhas)

- **Regra cardinal:** edite só o que a tarefa pede. Em dúvida, pergunte.
- **Arquivos load-bearing — sempre confirmar antes de Write/Edit:**
  - `docs/design/00-vision.md`
  - `docs/design/01-decisions.md`
  - `docs/design/05-filesystem-layout.md`
  - `docs/design/06-command-surface.md`
  - `docs/design/07-discipline.md`
  - `docs/schemas/**`
  - `presets/**`
  - `cards/**`
  - `CLAUDE.md`
  - `.claude/rules/**`
- **Anti-padrões:** refactor não solicitado, rename "while I'm here", "vou aproveitar pra atualizar isso também" → todos viram entrada separada em `04-pending.md` ou nova feature/PR.
- **Exceção legítima:** doc-sync da mesma mudança (mandamento #6) — refactor obrigatório, não scope creep.

### 5.7 `reuse.md` (~50 linhas)

- **Antes de criar helper/função/template/card, comandos a rodar:**
  - `forge graph` Q11 (reusable-helpers) e Q12–Q17 (reuse-intelligence)
  - `grep -rn "<conceito>" engine/ validators/` — fallback
  - `ls templates/ cards/` — pra artefatos
- **Quando graph diz "near-duplicate":** abre candidato, avalia consolidar (3-caminhos: usar / promover pra shared / criar nova com justificativa).
- **Inventory:** DS components + i18n + conventions em `engine/inventory/` — consultar antes de pedir UI/string nova.
- Pointer: `docs/lifecycle/memory-and-graph.md`.

### 5.8 `superpowers.md` (~80 linhas)

- Tabela detalhada das 10 skills (versão expandida da do CLAUDE.md root).
- **Skills NÃO ativadas (deliberadamente):** using-git-worktrees, finishing-a-development-branch, writing-skills, using-superpowers. Razão: single-maintainer hoje (worktrees/finishing-branch), projeto é skill (writing-skills), meta-skill auto-invocada (using-superpowers); entram via `forge evolve` se padrão emergir.
- **Decision 22 reforço:** skills são recurso humano + Claude Code, nenhum runtime import.

### 5.9 `doc-sync.md` (~60 linhas)

- **Matriz código→docs (completa):**

| Mudou… | Atualize obrigatoriamente | Considere também |
|---|---|---|
| `engine/<command>.py` (handler) | CHANGELOG, handoff | README §Stats, docs/design/06-command-surface |
| `validators/<x>.py` | CHANGELOG, handoff stats | docs/design/07-discipline §2 (se policy mudou) |
| `hooks/*.sh` ou `.claude/hooks/*.sh` | CHANGELOG, handoff | docs/design/05-filesystem-layout |
| Novo card em `cards/` | README §Stats, handoff | docs/design/02-phases |
| Novo template em `templates/` | README §Stats, handoff | docs/design/02-phases |
| Schema em `docs/schemas/` | CHANGELOG, README §Schemas | qualquer template que use o schema |
| `presets/*.yaml` | CHANGELOG, README §Preset | docs/design/03-influences se rationale muda |
| `docs/design/01-decisions.md` | CHANGELOG `### Changed (load-bearing)` | sempre incrementar #, nunca deletar linha antiga |
| `docs/design/04-pending.md` | risca gap fechado, adiciona novo | handoff §Conhecidos limites |
| Release tag | CHANGELOG seção [vX.Y.Z], README versão | handoff §Estado |

- **Checklist pré-commit:** 5 itens (CHANGELOG Unreleased? handoff data + phase? README stats? rule específico? gap em pending?).
- **Como editar `08-session-handoff.md`:** campos canônicos (Última atualização, estado, tabela Status, Conhecidos limites). Sem inventar formato.
- **Como editar `CHANGELOG.md`:** seguir keep-a-changelog (Added/Changed/Fixed/Removed). Sempre `## [Unreleased]` no topo.
- **Quando NÃO precisa doc-sync:** typo em comentário, edição de string testada que não muda semântica, formatação. Lista enumerada de exceções.
- **Apêndice — bloqueios opt-in disponíveis** (não ativos):
  - Test-count regression
  - Validator-cascade fail
  - Per-tool-use Mandamento 0 (depende de detecção main-vs-subagent estável)

### 5.10 `project-anatomy.md` (~80 linhas)

- **Mapa "se procura X, vai em Y":** 12-15 linhas mapeando cada subsistema.
- **Smoke tests rápidos:** `./bin/forge --version`, `pytest -k smoke`, etc.
- **Onde NÃO mexer sem revisitar:** linka `decisions.md` e `scope.md`.

### 5.11 `README.md` da pasta rules (~25 linhas)

Índice navegável: tabela `nome do rule | uma frase de propósito | quando ler`.

### 5.12 `SMOKE-CHECKLIST.md` (~40 linhas)

Checklist manual de 5 itens pra primeira sessão pós-bootstrap (ver §7.2 abaixo).

## 6. Hooks

### 6.1 Hook 1 — `session-start-orientation.sh`

- **Evento:** SessionStart.
- **Ação:** lê `08-session-handoff.md` (Última atualização + estado), checa `.claude/state/drift-pending.json`, injeta 8-12 linhas no contexto inicial lembrando Mandamento 0 + estado factual.
- **Reset:** limpa `drift-warned.json` da sessão anterior.
- **Bloqueia:** não. Exit 0 sempre.

### 6.2 Hook 2 — `pre-tool-use-load-bearing.sh`

- **Evento:** PreToolUse com matcher `Edit|Write|NotebookEdit`.
- **Trigger:** `tool_input.file_path` match lista canônica de load-bearing (ver §5.6).
- **Ação:** aviso prominente em stderr + append em `.claude/state/load-bearing-edits.jsonl` (audit).
- **Bloqueia:** não. Exit 0.

### 6.3 Hook 3 — `post-edit-doc-drift.sh`

- **Evento:** PostToolUse com matcher `Edit|Write|NotebookEdit`.
- **Trigger:** path match `engine/**`, `validators/**`, `hooks/**`, `templates/**`, `cards/**`, `presets/**`, `docs/schemas/**`.
- **Ação:** checa `.claude/state/drift-warned.json` (já avisou nesta sessão?); se não, emite stderr listando docs a sync; append em `drift-warned.json` e `drift-pending.json`.
- **Bloqueia:** não. Exit 0.

### 6.4 Hook 4 — `pre-commit-feature-forge.sh`

- **Acionado por:** `.git/hooks/pre-commit` → `hooks/git-pre-commit` (delegator existente) → este script (canônico).
- **Bloco 4a (HARD BLOCK):** se `docs/design/01-decisions.md` está staged mas `CHANGELOG.md` staged não contém "Revisita decisão" (case-insensitive), `exit 1` com mensagem clara apontando override `--no-verify`.
- **Bloco 4b (SOFT WARNING):** se commit toca paths "vivos" mas não toca CHANGELOG/handoff/README, emite warning stderr listando arquivos.
- **Cleanup:** remove `.claude/state/drift-pending.json` no fim (consumido pelo commit).

### 6.5 Wiring — `.claude/settings.json` (committed)

```json
{
  "hooks": {
    "SessionStart": [
      { "command": ".claude/hooks/session-start-orientation.sh" }
    ],
    "PreToolUse": [
      { "matcher": "Edit|Write|NotebookEdit",
        "command": ".claude/hooks/pre-tool-use-load-bearing.sh" }
    ],
    "PostToolUse": [
      { "matcher": "Edit|Write|NotebookEdit",
        "command": ".claude/hooks/post-edit-doc-drift.sh" }
    ]
  }
}
```

### 6.6 Estado runtime — `.claude/state/`

```
.claude/state/
├── .gitkeep                       ← versionado
├── drift-warned.json              ← ignored (per-sessão)
├── drift-pending.json             ← ignored (consumido pelo pre-commit)
└── load-bearing-edits.jsonl       ← ignored (audit local)
```

`.gitignore` ganha:
```
.claude/state/*.json
.claude/state/*.jsonl
!.claude/state/.gitkeep
```

## 7. Bootstrap e verificação

### 7.1 Bootstrap — `.claude/bootstrap.sh`

Script idempotente que:
1. Garante `.claude/state/` existe com `.gitkeep`.
2. Linka `.git/hooks/pre-commit` → `../../hooks/git-pre-commit`.
3. Linka `.git/hooks/pre-push` → `../../hooks/git-pre-push`.
4. `chmod +x` em todos os `.claude/hooks/*.sh`.
5. Avisa se `.claude/settings.local.json` está tracked e precisa `git rm --cached`.

Usuário roda `bash .claude/bootstrap.sh` uma vez após clonar.

### 7.2 Smoke checklist pós-bootstrap

5 verificações comportamentais documentadas em `.claude/rules/SMOKE-CHECKLIST.md`:

1. SessionStart hook injeta orientação?
2. PostToolUse drift hook dispara em edit de arquivo vivo?
3. PreToolUse load-bearing hook dispara em edit de doc/design/00-vision.md?
4. Pre-commit hard block dispara stage de 01-decisions sem CHANGELOG entry?
5. Mandamento 0: modelo dispatcha subagent pra typo em vez de editar inline?

### 7.3 Testes automatizados — `tests/integration/test_claude_rules_system.py`

~10 testes Python (marker `integration`):
- `settings.json` parse válido
- Scripts `.sh` passam `bash -n`
- Todos rules `.md` existem e linkados em CLAUDE.md
- Cada rule tem H1 + propósito
- Pre-commit hard-block dispara em fixture
- Pre-commit doc-sync warning dispara em fixture
- `.gitignore` cobre `.claude/state/*.json`
- Bootstrap idempotente (rodar 2× = diff zero)

### 7.4 Auditoria comportamental contínua

Não automatizada por ora — documentada em `.claude/rules/README.md` §Auditoria:
- Mandamento 0 segura? `git log` mostra Co-Authored-By de subagents?
- Doc-sync rola? Frequência de updates em `08-session-handoff.md`.
- Locked decisions caem em ceremony? `git log -p -- 01-decisions.md | grep -c "Revisita"`.
- `load-bearing-edits.jsonl` cresce de forma esperada?

Comando futuro `forge audit-rules` anotado em `04-pending.md` como gap pra v1.2+.

## 8. Riscos residuais reconhecidos

| Risco | Mitigação |
|---|---|
| Subagent split commit (decisão + CHANGELOG em commits separados) → hard-block dispara errado | rule `decisions.md` instrui explicitamente "ambos no mesmo commit"; bootstrap doc deixa claro |
| Hooks Bash falham silenciosamente | `set -euo pipefail` + exit 0 explícito no caminho não-bloqueante; único exit 1 é o intencional |
| `settings.json` sobrescrito por engano | committed + reviewable em PR |
| `--no-verify` vira hábito | auditoria mensal do `git log` (item §7.4) |
| LLM ignora rules silenciosamente | mitigado por hooks de orientação (SessionStart) + repetição inline no CLAUDE.md root + per-tool-use warnings |
| Falsos positivos no PreToolUse load-bearing (subagent legítimo editando rule) | aviso, não bloqueio — apenas log + visibilidade |
| Hooks atrasam workflow | Bash puro, sub-30ms cada; pre-commit hard block ~100ms |

## 9. O que NÃO está no escopo (deliberado, YAGNI)

- **Lint de prosa das rules.** Manualmente revisado é suficiente.
- **Coverage de cada rule contra failure histórico.** Sem dataset disponível.
- **Detecção mecânica de main-agent-vs-subagent.** Adiada — depende de validar empiricamente.
- **Per-directory CLAUDE.md** (engine/CLAUDE.md, etc.). Escolhemos estrutura modular `.claude/rules/*` ao invés.
- **CI integration** (test_claude_rules_system roda em GitHub Actions). Marker `integration`, opt-in.
- **`forge audit-rules` comando.** Gap futuro em `04-pending.md`.
- **Bloqueios opt-in (test-count regression, validator cascade)** ativados agora. Documentados como evolução possível em `doc-sync.md`.

## 10. Ordem canônica de implementação

Para o `superpowers:writing-plans` produzir plano executável:

1. **Diretórios**: `.claude/rules/`, `.claude/hooks/`, `.claude/state/` (com `.gitkeep`).
2. **Rules** (12 arquivos `.md`) — paralelizável, são independentes.
3. **Hooks** (4 scripts `.sh`) — paralelizável.
4. **Settings + bootstrap**: `.claude/settings.json` + `.claude/bootstrap.sh`.
5. **`.gitignore`** — append bloco.
6. **`CLAUDE.md`** root — por último (referencia tudo acima).
7. **Bootstrap manual**: usuário roda `bash .claude/bootstrap.sh` uma vez.
8. **Doc-sync da própria entrega**: `CHANGELOG.md` (Unreleased: Added Claude Code rules system), `docs/design/08-session-handoff.md` (Última atualização), `README.md` (menção breve às rules).
9. **Testes**: `tests/integration/test_claude_rules_system.py`.
10. **Smoke checklist** manual conforme `SMOKE-CHECKLIST.md`.

A implementação em si será 100% delegada via Mandamento 0 — orchestrator não escreve nenhum dos 21 arquivos do sistema pessoalmente. Mas a regra só vale depois que o sistema estiver instalado; durante a implementação inicial (este step), ela é o **alvo**, não a restrição.

## 11. Critérios de sucesso (verificáveis)

Sistema considerado entregue quando:

- [ ] Todos os 20 arquivos novos criados nos paths corretos.
- [ ] `.gitignore` modificado.
- [ ] `CHANGELOG.md`, `08-session-handoff.md`, `README.md` atualizados (doc-sync da própria entrega).
- [ ] `bash .claude/bootstrap.sh` roda 2× sem efeito colateral (idempotência).
- [ ] `pytest tests/integration/test_claude_rules_system.py` passa.
- [ ] Smoke checklist (5 itens) executado manualmente com sucesso.
- [ ] Pre-commit hard-block dispara em fixture controlado.
- [ ] Nova sessão Claude Code mostra orientação no início.

---

**Próximo step:** invocar `superpowers:writing-plans` com este spec como input para produzir plano executável task-by-task.
