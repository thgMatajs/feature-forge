# Relatório de Loops Abertos — feature-forge v1.4.0

> **Gerado em:** 2026-06-17 · **Branch:** feat/v1.3-pilot-ready
> **Foco:** Onde o loop não fecha — ambiguidade, dependência excessiva de input manual, valor prometido vs entregue

---

## Sumário Executivo

Esta análise viu o forge sob uma lente específica: **"onde a ferramenta promete algo mas não completa o ciclo?"**. Mapeamos 7 dimensões de loop aberto. Cada uma representa um ponto onde o forge transfere trabalho para o usuário em vez de executar autonomamente.

### Os loops abertos por severidade

| Loop | Dimensão | O que promete | O que entrega | Impacto |
|---|---|---|---|---|
| **L1** | Template placeholders | Auto-preenchimento de templates | **480 placeholders deixados raw** (0 populados) | Todo plano é um esqueleto vazio |
| **L2** | forge implement | Orquestração automatizada de implementação | **Stub manual** — só imprime instruções | O comando mais crítico não executa nada |
| **L3** | Resolução de ambiguidade | Fechamento de perguntas abertas | **Ambiguity-map existe mas nunca é populado nem lido** | Planos aprovados com ambiguidades não resolvidas |
| **L4** | State machine real | Ciclo `planned → verified → done` | **`verified` é fantasma; `implementing → done` diretamente** | Documentação diverge da implementação |
| **L5** | Cards → pipeline | Cards contribuem templates/validators | **plan.py e implement.py ignoram cards** zero referências | Investimento em cards não chega ao planejamento |
| **L6** | MCP providers | Integração com Jira/Linear/GitHub/Context7 | **12 métodos NotImplementedError** | Qualquer config de ticketing crasha |
| **L7** | forge qa sem LLM | QA pipeline completa | **Python engine = scaffold; inteligência = LLM agent prompts** | Sem dispatch externo, só cria diretório e sai |
| **L8** | forge verify pós-placeholder | Verifica que arquivos existem | **Não verifica se placeholders foram preenchidos** | Template vazio passa como "verificado" |
| **L9** | Gate futuro | 6 gates documentados em disciplina docs | **Nenhum implementado** | Promessa sem entrega |
| **L10** | Spike/chore subtypes | Suporte a investigation/maintenance tasks | **Stub 3-caminhos** — "trate como product ou aborte" | Caminho não existe |
| **L11** | Card recomendação | Descoberta automática de cards | **6 heurísticas hardcoded** no init | Usuário descobre cards manualmente |
| **L12** | forge status profundo | Status board com saúde real | **Só L1 state** — sem template fill, sem ambiguity, sem lock health | Visão superficial |
| **L13** | forge undo → aborted | Saída de estado aborted | **`aborted` é dead end — zero transições de saída** | Erro = restart do zero |
| **L14** | forge doctor sem coverage | Diagnóstico completo | **Sem verificação de template fill, ambiguity, lock health** | Doctor ignora os maiores problemas |
| **L15** | forge status sem verificado | Relatório de status | **não mostra template fill, não mostra ambiguity resolution, não mostra lock health** | Visão superficial do progresso real |
| **L16** | forge verify sem placeholder | Validação de template fill | **não verifica se placeholders foram preenchidos** | Template vazio passa como "verificado" |

---

## 1. Template System — O Loop Que Nunca Fecha

### 1.1 O Bug Central: `{{FEATURE_SLUG}}` vs `{{feature_slug}}`

O `plan.py` copia templates com uma substituição:

```python
# engine/plan.py:401
raw = raw.replace("{{FEATURE_SLUG}}", slug)   # UPPERCASE
```

Mas todos os templates usam `{{feature_slug}}` (lowercase):

```
$ grep -r "{{FEATURE_SLUG}}" templates/  # → 0 matches
$ grep -r "{{feature_slug}}" templates/  # → 74 occurrences
```

**Resultado:** A engine substitui **0 placeholders**. O template é copiado com todos os `{{placeholder}}` intactos.

### 1.2 Placeholder Matrix — 480 campos vazios

| Template | Placeholders | Populados pela engine | Manual |
|---|---|---|---|
| feature-intake.template.md | 27+ | **0** | 27+ |
| feature-prd.template.md | 35+ | **0** | 35+ |
| screen-analysis.template.md | 48+ | **0** | 48+ |
| bdd.template.md | 24+ | **0** | 24+ |
| bdd.template.json | 24+ | **0** | 24+ |
| ui-state-spec.template.yaml | 22+ | **0** | 22+ |
| navigation-spec.template.yaml | 14+ | **0** | 14+ |
| data-contract-spec.template.yaml | 20+ | **0** | 20+ |
| analytics-spec.template.yaml | 16+ | **0** | 16+ |
| test-strategy.template.yaml | 19+ | **0** | 19+ |
| tech-spec.template.md | 43+ | **0** | 43+ |
| task-breakdown.template.yaml | 18+ | **0** | 18+ |
| task-contract.template.yaml | 22+ | **0** | 22+ |
| implementation-readiness-review.template.md | 46+ | **0** | 46+ |
| plan-feature-handoff.template.json | 16+ | **0** | 16+ |
| **Total (17+ templates)** | **~480** | **0** | **~480** |

### 1.3 A Única Exceção: `reuse_apply.py`

O `engine/graph/reuse_apply.py` usa um renderizador Mustache-like que **realmente popula placeholders** — mas só para intakes de refactor propostos pelo reuse engine, NÃO para `forge plan`.

### 1.4 Validação Inexistente de Preenchimento

| Ponto de verificação | Checa placeholders? |
|---|---|
| `_run_static_wave("A", ...)` + "continuar" | ❌ — só espera input "continuar" |
| `_parse_readiness_status()` | ❌ — só procura `status: ready` no markdown |
| `forge verify` cascade | ❌ — nenhum validador escaneia `{{` |
| `validate_feature_package.py` | ❌ — `{{` em refs é **silenciosamente ignorado** |
| `check_files_in_allowed_files.py` | ❌ — `{{` em globs é **silenciosamente ignorado** |

### Valor efetivo entregue

```
forge plan <slug>
  → 17+ templates copiados
  → 480 placeholders deixados como {{literal}}
  → 0 populados pela engine
  → nenhuma validação pega
  → mensagem: "abra no editor, preencha, digite continuar"
```

---

## 2. State Machine Fantasma — 3 Estados Que Não Existem

### 2.1 `verified` — O Estado Prometido

**Documentado em:** `docs/design/ROADMAP.md`, `docs/design/07-discipline.md` como `implementing → verified → done`

**Realidade:** Nenhuma linha de código escreve `status = "verified"`. `implement.py` vai direto `implementing → done`.

3 estados declarados em `_VALID_STATES` (l1.py:40-56) mas **nunca escritos**:

| Estado | Declarado | Escrito por | Onde deveria ser escrito | Gap |
|---|---|---|---|---|
| `verified` | l1.py:46 | **Nunca** | `forge verify` após sucesso | Ghost state — documentado mas não implementado |
| `paused` | l1.py:50 | **Nunca** | Em qualquer `PromptAbortedError` | Pause é UI-level (exit 130), não persiste em L1 |
| `not-started` | l1.py:41 | **Nunca** | `forge init` cria feature nova | `_initialize_status` já cria como `planning` |

### 2.2 `aborted` — Dead End

`forge undo` → `status = "aborted"`. Nenhuma transição de saída existe. Se o usuário aborta acidentalmente, o único caminho é deletar o L1 e recomeçar.

### 2.3 Transições Completas (Diagrama Real)

```
START → planning  (AUTO: plan.py)
           ↓ planned  (AUTO: plan.py após waves A-E)
           ↓ implementing  (AUTO: implement.py)
           ↓ done  (AUTO: implement.py)
           ↻ planning  (MANUAL: plan.py 4-caminhos "Retomar")

planning → deferred → planning  (MANUAL pausar → AUTO resume)
planning → aborted  (MANUAL: forge undo)  ← DEAD END
implementing → blocked-on-external → implementing (AUTO ou MANUAL)
implementing → verifying → (restaura estado anterior)  (transient apenas)
```

### 2.4 Schema Docs Inconsistentes

MEM-L1-008 documenta 8 estados, mas omite `planned`, `deferred`, `verified`, `not-started` — enquanto inclui `paused` que nunca é escrito.

---

## 3. Pipeline Cards → Plan/Implement — Desconexão Total

### 3.1 cards → init (funciona)

```
card.yaml → loader → resolver → snapshotter → merger
    → templates/ mergeados
    → validators/ mergeados
    → agent_prompts/ mergeados
    → hooks/ mergeados
```

### 3.2 init → plan (NÃO FUNCIONA)

`plan.py` (1671 linhas): **zero referências a cards**. Usa `_render_template()` que copia templates planos do diretório `templates/` — não os mergeados do card.

### 3.3 init → implement (NÃO FUNCIONA)

`implement.py` (1439 linhas): **zero referências a cards**. Só lê task contracts + L1 state.

### 3.4 O Loop Não Fecha

```
[Usuário investe em criar cards]
    → init reconhece cards
    → merge produz templates/validators/prompts
    → forge plan IGNORA o merge
    → forge implement IGNORA o merge
    → templates canônicos (planos) são usados
    → esforço do card desperdiçado no pipeline
```

`forge raw rebuild-templates` existe para remediar isso, mas é um comando esotérico.

---

## 4. MCP — O Pingente Congelado

### 4.1 Status: 12/12 Métodos NotImplementedError

| Provider | Arquivo | Métodos | Status |
|---|---|---|---|
| `JiraProvider` | `engine/mcp/jira.py` | `fetch_ticket()`, `list_tickets()`, `post_comment()` | ❌ Todos NotImplementedError |
| `LinearProvider` | `engine/mcp/linear.py` | `fetch_ticket()`, `list_tickets()`, `post_comment()` | ❌ Todos NotImplementedError |
| `GitHubIssuesProvider` | `engine/mcp/github_issues.py` | `fetch_ticket()`, `list_tickets()`, `post_comment()` | ❌ Todos NotImplementedError |
| `Context7Provider` | `engine/mcp/context7.py` | `lookup_lib()`, `query()` | ❌ Todos NotImplementedError |

### 4.2 O Perigo

O registry (`engine/mcp/registry.py:60-69`) **consegue instanciar** os providers. O `forge-config.yaml` aceita `ticketing.provider: jira`. O `forge doctor` simplesmente skipa o probe MCP.

**Cenário:** usuário configura Jira em workflow-config → forge instantiate `JiraProvider` com sucesso → primeiro `fetch_ticket()` → `NotImplementedError` → crash.

### 4.3 Impacto na Pipeline

```mermaid
forge plan
  → detecta subtype (keywords + ticket pattern)
  → se ticket pattern reconhece IN-37234 → tenta JiraProvider.fetch_ticket()
  → NotImplementedError("Phase 5 (MCP wiring pending)")
  → CRASH
```

A referência a ticket pattern (`_TICKET_PATTERN` em `plan.py:163`) existe, mas o provider para buscá-lo não.

---

## 5. forge implement — O Stub Central

`implement.py` é o **comando mais crítico do pipeline** — e é um stub:

| O que promete | O que entrega |
|---|---|
| Condução autônoma de implementação | Instruções manuais impressas |
| Gate CC/Secrets automáticos | Gates existem, mas `apply_mode_handoff` retorna antes |
| Geração de código | Zero |
| Apply mode programático | Manual handoff instructions |

```python
# engine/implement.py:728-789
def _apply_mode_handoff(...):
    # Só imprime:
    print(f"Implemente {task.task_id} seguindo o contrato em {task_path}")
    print(f"1) forge verify")
    print(f"2) git add ...")
    print(f"3) git commit ...")
    return  # não executa nada
```

---

## 6. forge qa — Scaffold Sem Cérebro

### 6.1 O Que Existe (sólido)

- Engine Python: scope resolution, sandbox, checkpoint, emit, schema validation
- 4 agent prompts: spec-vs-spec, coverage, chaos, validator-claim
- Template para card extensions: qa-auditor.template.md
- 100+ testes

### 6.2 O Que Não Existe

| Funcionalidade | Código Python | LLM Prompt |
|---|---|---|
| Verificação de placeholders `{{}}` | ❌ | ❌ |
| Verificação de ambiguity-map | ❌ | ❌ |
| Consistência de state machine | ❌ | Apenas LLM qualitativo |
| Execução autônoma (sem LLM) | ❌ | N/A — scaffold não faz auditoria sem agentes |

### 6.3 O Loop Não Fecha

```
forge qa (sem dispatch de LLM)
  → cria run tree
  → faz Phase 0 (scope)
  → termina
  → nenhuma auditoria executada
  → nenhum finding produzido
  → saída: diretório vazio
```

---

## 7. Gate Futuros — Promessa sem Entrega

Discipline docs (`07-discipline.md §7`) lista gates planejados:

| Gate | Status no código |
|---|---|
| `check_deps_cve` (CVE dependency) | ❌ Não implementado |
| `check_duplication` (duplication) | ❌ Não implementado |
| `check_cognitive_complexity` | ❌ Não implementado |
| `check_dead_code` | ❌ Não implementado |
| `check_arch_rules` (arch rules) | ❌ Não implementado |
| `check_function_length_and_nesting` | ❌ Não implementado |

A infra (`_gate_infra.py`) está extraída, mas os validators não existem.

---

## 8. Mapa de Loops Abertos Cruzando Tudo

| Pipeline Stage | Input | Processamento Automático | Output | Loop Fechado? |
|---|---|---|---|---|
| **forge init** | Diretório do projeto | Detection de stack + card merge | forge-config.yaml + templates/ | ✅ Parcial (cards não chegam a plan) |
| **forge plan** | Jira card (via slug) | ~~parser de ticket~~ (MCP stub) + ~~popula placeholders~~ | **480 placeholders raw** | ❌ |
| **forge implement** | Plan artifacts (with `{{}}`) | Gates rodam, apply é stub | Instruções manuais | ❌ |
| **forge verify** | Código | Cascade de validators | Pass/Fail | ✅ (mas não verifica placeholders) |
| **forge status** | L1 state | Leitura de status.json | Board de features | ⚠️ Superficial |
| **forge doctor** | Projeto | 16 categorias de health | OK/WARN/FAIL | ⚠️ (sem coverage, sem placeholder) |
| **forge qa** | Feature artifacts | ~~4 auditorias LLM~~ (se sem dispatch) | Estrutura vazia | ❌ Sem LLM |
| **forge evolve** | L1/L2/L3 memory | Distillation | Propostas + apply | ✅ (exceto 6 kinds NotImplementedError) |
| **forge undo** | L1 slug | Remove feature | `aborted` (dead end) | ❌ |
| **forge graph** | Código fonte | Parser + queries | SQLite graph | ✅ |

---

## 9. Catálogo de Stubs e NotImplementedError

### NotImplementedError (13)

| Local | Método | Bloqueia |
|---|---|---|
| `engine/mcp/jira.py` | `fetch_ticket()` | Config Jira crasha |
| `engine/mcp/jira.py` | `list_tickets()` | Mesmo |
| `engine/mcp/jira.py` | `post_comment()` | Mesmo |
| `engine/mcp/linear.py` | `fetch_ticket()` | Config Linear crasha |
| `engine/mcp/linear.py` | `list_tickets()` | Mesmo |
| `engine/mcp/linear.py` | `post_comment()` | Mesmo |
| `engine/mcp/github_issues.py` | `fetch_ticket()` | Config GitHub Issues crasha |
| `engine/mcp/github_issues.py` | `list_tickets()` | Mesmo |
| `engine/mcp/github_issues.py` | `post_comment()` | Mesmo |
| `engine/mcp/context7.py` | `lookup_lib()` | Config Context7 crasha |
| `engine/mcp/context7.py` | `query()` | Mesmo |
| `engine/memory/distiller.py:527` | `apply_proposal_to_l2()` (6 kinds) | Propostas desses kinds travam evolve |
| `engine/raw.py:219` | `run("migrator-1-to-dois")` | Bloqueia limpeza de config legada |

### Stubs de Comportamento (5)

| Local | O Que Deveria Fazer | O Que Faz |
|---|---|---|
| `engine/implement.py:728` | Apply mode programático | Imprime instruções manuais |
| `engine/plan.py:1218` | Spike/chore workflow | 3-caminhos "trate como product ou aborte" |
| `engine/reconfigure.py:1690` | Distill manual de L2 | Mensagem "not integrated yet" |
| `engine/reconfigure.py:1706` | Re-merge de hooks | Cria diretório vazio |
| `engine/reconfigure.py:1056` | Card com signals | Cria card com signals.yaml vazio |

### TODOs sem Ticket (6)

| Local | TODO | Bloqueado Por |
|---|---|---|
| `engine/mcp/*.py` (17 TODOs) | `# TODO Phase 5:` | Fase não agendada |
| `engine/evolve.py:119` | Remover fallback config legada | `forge raw migrator-1-to-2` é stub |
| `engine/graph/reuse_apply.py:243` | Investigar root cause | Q-NNN literal — nunca vira ticket |
| `engine/qa/__init__.py:627` | Extrair grants para módulo próprio | Código duplicado |
| `engine/reconfigure.py:2203` | Delegar para doctor.run_quick() | API não existe |
| `engine/utils/sqlite_io.py:327` | Graph builder lives elsewhere | Informativo |

---

## 10. Recomendações

### Para Fechar Cada Loop

| # | Loop | Recomendação | Esforço |
|---|---|---|---|
| R1 | Template placeholders | Consertar `replace("{{FEATURE_SLUG}}", slug)` para `{{feature_slug}}` e adicionar substituições para campos comuns (slug, data, source) | 1 dia |
| R2 | forge implement | Substituir `_apply_mode_handoff` por execução real de sub-agentes com LLM | 2-3 semanas |
| R3 | Ambiguidade | Conectar `_elicit_open_questions()` ao ambiguity-map e criar gate de Q-NNN abertas | 3-5 dias |
| R4 | State machine | Remover `verified`, `paused`, `not-started` de `_VALID_STATES` OU implementar transições reais | 1 dia (remoção) |
| R5 | Cards → pipeline | Adicionar `merge_contributions()` antes de renderizar templates no plan.py | 2-3 dias |
| R6 | MCP providers | Implementar pelo menos `fetch_ticket()` para Jira (o mais crítico) | 1-2 semanas |
| R7 | forge qa standalone | Adicionar Phase 0.5 deterministic checks: placeholders, ambiguity, state machine | 3-5 dias |
| R8 | forge verify placeholder | Adicionar validador que escaneia `{{` em artefatos de feature | 1 dia |
| R9 | forge undo recovery | Adicionar `forge reconfigure --un-abort` que restaura de history.jsonl | 2 dias |
| R10 | Card recomendação | Expandir `_ORPHAN_HEURISTICS` de 6 para 30+ patterns + `forge suggest` | 1 semana |

### Prioridade

| Prioridade | Loop | Justificativa |
|---|---|---|
| **P0** | Template placeholders (L1) | Bug de 1 caractere invalida o output principal do forge. Sem isso, forge plan gera esqueletos vazios |
| **P0** | forge implement (L2) | O comando mais crítico não funciona. A pipeline termina em instruções, não em código |
| **P1** | Ambiguidade (L3) | Sem isso, planos podem ser aprovados com perguntas abertas não respondidas |
| **P1** | forge verify placeholder (L8) | Sem validação de preenchimento, o pipeline aceita lixo como "verificado" |
| **P2** | MCP Jira (L6) | Bloqueia ingestão automática de tickets |
| **P2** | Cards → pipeline (L5) | Torna o investimento em cards efetivo no pipeline |
| **P3** | State machine (L4) | Integridade de design — não bloqueia usuário |
| **P3** | forge undo recovery (L13) | Edge case — raro mas frustrante |

---

## 11. Conclusão

feature-forge tem uma **arquitetura excelente** e **testes robustos** (1779 passam). Mas a ferramenta **transfere trabalho para o usuário em praticamente todos os pontos críticos**:

1. **Plan**: 480 placeholders deixados raw — o usuário preenche manualmente
2. **Implement**: stub — o usuário segue instruções impressas
3. **Ambiguidade**: mapa existe mas ninguém pergunta nem valida
4. **Cards**: o investimento em contribuição de cards não chega ao pipeline
5. **MCP**: ticketing/external-docs configurável mas crasha no primeiro uso
6. **forge qa**: scaffold sólido mas sem LLM não produz valor
7. **verify**: não verifica placeholders — template vazio passa

O forge **abre muitos loops mas não os fecha**. Cada loop aberto significa uma decisão, um preenchimento, uma verificação que o usuário precisa fazer manualmente. Para ser verdadeiramente AI/LLM-first, cada um desses loops precisa ser fechado com automação.

---

*Relatório gerado em 2026-06-17. READ-ONLY + BUILD.*
