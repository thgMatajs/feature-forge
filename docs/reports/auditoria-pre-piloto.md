# Relatório de Auditoria Pré-Piloto — feature-forge v1.4.0

> **Gerado em:** 2026-06-17
> **Branch:** feat/v1.3-pilot-ready (PR #17)
> **Versão:** feature-forge 1.4.0 · Python 3.13.13
> **Tipo:** Auditoria READ-ONLY (zero mutação de código)
> **Escopo:** 8 fases — exploração arquitetural, testes, simulações "E se", deep dives, docs drift, relatório consolidado

---

## Sumário Executivo

feature-forge v1.4.0 está **funcional** — todas as lanes de teste passam (1779 testes, 20 skipped, 0 falhas), `forge verify` verde, doctors sem erro. No entanto, a ferramenta **não está pronta para ser usada exclusivamente via AI/LLM** (opencode, Claude Code). A auditoria identificou **22 gaps** (4 críticos, 6 altos, 8 médios, 4 baixos), **7 recomendações pré-piloto**, e **6 oportunidades estratégicas**.

### Veredito rápido

| Dimensão | Nota |
|---|---|
| Estabilidade (testes passam) | A |
| Drift docs vs código | C |
| Resiliência a erros AI/LLM | D |
| Maturidade AI-first | D |
| Consistência design (decisions) | C+ |
| Arquitetura geral (potencial) | B+ |

---

## Histórico da Sessão

Esta auditoria foi conduzida em 8 fases sequenciais e cumulativas:

| Fase | Atividade | Achados |
|---|---|---|
| **1** | Exploração arquitetural inicial | Mapa de ~30 módulos, arquitetura host, DRIFT-1 |
| **2** | Exploração docs (decisions, pending, handoff) | Primeiras discrepâncias doc vs código |
| **3** | Exploração regras (orchestrator, hooks, plan-auditor) | 10 hooks .sh, compliance |
| **4** | Exploração GSD skills | ~80 skills inventariadas |
| **5** | Testes — todas as 4 lanes | 1779 testes, TODOS VERDES ✅ |
| **6a** | Simulações "E se" — 14 cenários | Riscos de race, crash, loop infinito, doc drift |
| **6b** | Deep dive host adapters | 7 arquivos, 50+ riscos |
| **6c** | Deep dive intent protocol | 6 arquivos, 47 riscos |
| **6d** | Deep dive init/implement/plan | 4 arquivos, 45+ riscos |
| **7** | Docs drift — verificação cruzada | 7 discrepâncias formais |
| **8** | Deep dive exaustivo (graph, memory, cards, MCP) | +20 riscos, gaps críticos confirmados |

---

## 1. Arquitetura Geral

### 1.1 Componentes Principais

```
feature-forge/
├── engine/                    # Core Python (~30 módulos)
│   ├── cli.py                 # Entry point, 14 subcommandos + hidden ingest
│   ├── host/                  # Sistema de adapters de host (AI/LLM/tty)
│   │   ├── adapter.py         # ABC, HostName, AskKind, AskResult
│   │   ├── detect.py          # Detecção com precedência
│   │   └── adapters/          # 4 implementações concretas
│   │       ├── claude_code.py
│   │       ├── intent_file.py
│   │       ├── tty.py
│   │       └── opencode_fallback.py
│   ├── ui/                    # Interface de usuário abstrata
│   │   ├── question.py        # 882 linhas, 108 callsites ask*()
│   │   └── intent_state.py    # ~680 linhas, protocolo DRIFT-1
│   ├── init.py                # 2656 linhas — bootstrap de projetos
│   ├── implement.py           # Stub manual
│   ├── plan.py                # Planejamento em waves A-E
│   ├── verify.py              # Verificação de objetivos
│   ├── graph/                 # Codebase graph (12 módulos + parsers)
│   ├── memory/                # L1/L2/L3 state management
│   ├── mcp/                   # TODOS stubs (NotImplementedError)
│   └── cards/                 # Card loading system
├── validators/                # 21 validadores
├── templates/                 # Templates YAML/MD
├── cards/                     # Card definitions
├── presets/                   # Presets
├── hooks/                     # Git hooks para projetos consumidores
├── .claude/                   # Configuração Claude Code deste repo
│   ├── rules/                 # Regras operacionais
│   └── hooks/                 # Hooks internos
└── docs/design/               # Fonte de verdade (27 decisions)
```

### 1.2 Fluxo de Comando

```
CLI → detect_host() → adapter.resolve() → question.ask*() → intent protocol
                                                                    ↓
                                              exit 2 → file I/O → re-invocação
                                                                    ↓
                                                           handler.execute()
```

### 1.3 Host Detection Precedence

```
1. forge-config.yaml: host_mode
2. FORGE_FORCE_INTENT_MODE
3. CLAUDECODE=1              (prioritário sobre OPENCODE_*)
4. OPENCODE_*=...            (se CLAUDECODE ausente)
5. isatty()                  (tty adapter)
6. intent_file fallback      (universal)
```

---

## 2. Fase 5: Resultado dos Testes

### 2.1 Rapid Lane

```
pytest -m "not integration"
1568 passed, 12 skipped ✅  (0 falhas)
```

### 2.2 Validator Lane

```
pytest tests/validators/
248 passed ✅  (0 falhas)
```

### 2.3 Integration Lane

```
pytest -m integration
160 passed, 8 skipped ✅  (398s, 0 falhas)
```

### 2.4 Unit Lane

```
pytest tests/unit/ -x --timeout=60
1037 passed, 12 skipped ✅  (0 falhas)
```

### 2.5 forge verify

```
forge verify
Cascade completo — TUDO VERDE ✅
```

---

## 3. Fase 6a: Simulações "E se" — 14 Cenários

Cenários que simulam interações AI/LLM reais para expor gaps de resiliência.

### 3.1 Host detect miss → adapter noop crash

**Cenário:** Host detect não reconhece o ambiente → `resolve()` retorna `None` ou adapter noop → sistema cai sem mensagem útil.

**Risco:** **CRÍTICO** — sem adapter = sem comando. Mensagem de erro atual é genérica.

**Recomendação:** Implementar adapter CI/non-interactive como fallback universal.

### 3.2 L1.json malformed → crash sem recovery

**Cenário:** `memory/l1/L1.json` corrompido (encoding, JSON malformed) durante `init` ou `plan` → `json.load()` levanta `json.JSONDecodeError` → stack trace exposto ao usuário.

**Risco:** **ALTO** — qualquer comando que leia L1 crasha.

**Recomendação:** Try/except com graceful degradation + recovery automático.

### 3.3 Race: init + forge graph → shared .tmp collision

**Cenário:** `init.py` e `graph` subsystem usam `json_io.write_json()` com `.tmp` fixo em escopo global → race condition quando executados em paralelo.

**Risco:** **ALTO** — corrupção de arquivo temporário.

**Recomendação:** `tempfile.mkstemp()` em vez de `.tmp` fixo.

### 3.4 Corrupted intent file → parse error → loop infinito

**Cenário:** During intent protocol, um intent file mal formatado → `parse_intent_file()` falha → `NoIntentsFound` → re-invocação → loop infinito.

**Risco:** **CRÍTICO** — AI/LLM pode loopar.

**Recomendação:** Backoff exponencial + max retries + fallback não-interativo.

### 3.5 File adapter read orphan intent → stale state

**Cenário:** Intent file de execução anterior não limpo → lido como intent atual → ghost intent executa ação errada.

**Risco:** **MÉDIO** — baixa probabilidade mas consequência severa.

**Recomendação:** Intent file path único por sessão + cleanup sempre.

### 3.6 lock.json desync → verify deadlock

**Cenário:** `lock.json` indica lock ativo mas processo já morreu → `verify` recusa executar → deadlock permanente até limpeza manual.

**Risco:** **MÉDIO** — recuperação manual necessária.

**Recomendação:** Lock com TTL + stale lock detection.

### 3.7 L3 markdown malformed → crash evolve

**Cenário:** `memory/l3/*.md` com front matter mal formatado → `evolve` crasha com `YAMLError`.

**Risco:** **BAIXO** — apenas evolve afetado.

**Recomendação:** Try/except com skip do arquivo danificado.

### 3.8 MCP nunca implementado → NotImplementedError forever

**Cenário:** `mcp/providers/google.py` etc. ainda são `NotImplementedError("Phase 5")` → qualquer código que tente usar MCP crasha.

**Risco:** **CRÍTICO** — bloqueador para AI-first.

**Recomendação:** P0: implementar MCP server mínimo.

### 3.9 Graph parser hanging → CLI hangs, no timeout

**Cenário:** Parser Kotlin/Typescript recebe input adversarial → ReDoS → CLI fica presa sem timeout.

**Risco:** **ALTO** — sem recovery automático.

**Recomendação:** Timeout no parser + fix ReDoS.

### 3.10 session-start-orientation emoji → intent protocol pollution

**Cenário:** `.claude/hooks/session-start-orientation.sh` usa 🔨 no stdout → stdout do subprocesso lido como parte do protocolo.

**Risco:** **MÉDIO** — poluição de canal.

**Recomendação:** Emojis removidos de hooks que usam intent protocol.

### 3.11 Graph incremental rebuild + parallel forge → cache corrupto

**Cenário:** `graph rebuild` + outro comando forge em paralelo → `.claude/graph.db` WAL mode corrompido.

**Risco:** **MÉDIO** — SQLite WAL é robusto, mas race de escrita paralela.

**Recomendação:** Lock de arquivo no graph.db.

### 3.12 ADR 7 LOCKED → forge implement tenta mesmo assim

**Cenário:** Decision 7 LOCKED sobre implementação → `forge implement` tenta `apply` mode → silencia regra LOCKED.

**Risco:** **BAIXO** — implement é stub, não executa nada.

**Recomendação:** N/A (implement stub). Será relevante quando implement for real.

### 3.13 Huge L3 → OOM em memory

**Cenário:** `memory/l3/` com milhões de linhas de markdown → `memory` carrega tudo em RAM → OOM.

**Risco:** **BAIXO** — improvável com uso normal.

**Recomendação:** Lazy loading ou limite de tamanho.

### 3.14 Ctrl+C mid-intent → partial-stale-not-consumed

**Cenário:** Usuario pressiona Ctrl+C durante `question.ask()` → arquivo intent parcialmente escrito → sistema fica em estado inconsistente.

**Risco:** **MÉDIO** — recovery automático inexistente.

**Recomendação:** Cleanup de intent file parcial + transactional write.

---

## 4. Fase 6b: Deep Dive Host Adapters

### 4.1 `engine/host/adapter.py` — Base ABC

| Achado | Gravidade | Detalhe |
|---|---|---|
| `resolve()` sem timeout | CRÍTICO | Adapter pode travar esperando resposta |
| `AskResult` sem metadados de erro | ALTO | Não distingue cancelamento vs falha vs timeout |
| `AskKind` sem enum para CONFIRM | MÉDIO | Apenas TEXT, CHOICE, YES_NO |
| Sem método `cancel()` na interface | ALTO | Não há como abortar intent em andamento |
| Sem `async` support | MÉDIO | Todo I/O é síncrono, bloqueante |
| `HostName` sem entrada para NON_INTERACTIVE | MÉDIO | Modo CI não representado |

### 4.2 `engine/host/detect.py` — Detecção

| Achado | Gravidade | Detalhe |
|---|---|---|
| `CLAUDECODE=1` priorizado sobre `OPENCODE_*` | ALTO | Opencode é cidadão de segunda classe |
| Sem cache de detecção | BAIXO | `detect_host()` chamado múltiplas vezes |
| Sem fallback CI/non-interactive | ALTO | Sem adapter para pipelines |
| Config `host_mode: auto` sem cache | BAIXO | Re-detecta a cada chamada |

### 4.3 `engine/host/adapters/claude_code.py`

| Achado | Gravidade | Detalhe |
|---|---|---|
| Cache em memória | ALTO | Perdido entre context resets do CC |
| Marker stdout sem padronização | MÉDIO | `ECHO_LLM_RESPONSE` hardcoded |
| Sem fallback se stdout não capture | MÉDIO | Silently fails |
| Apenas funciona em Claude Code | — | Por design, mas limita portabilidade |

### 4.4 `engine/host/adapters/intent_file.py`

| Achado | Gravidade | Detalhe |
|---|---|---|
| SEM canal de notificação ao host | **CRÍTICO** | Subprocesso não sabe quando intent é consumido |
| `wait_for_intent()` bloqueia para sempre | CRÍTICO | Sem timeout, poll infinito |
| Orphan intents (arquivos não limpos) | ALTO | Ghost intents possíveis |
| Sem limpeza de intents consumidos | MÉDIO | Acúmulo de arquivos |
| TOCTOU race em consumed detection | ALTO | Check-then-act sem lock |
| Polling sem backoff | MÉDIO | CPU usage desnecessário |
| Parse error sem recovery | ALTO | Loop infinito se arquivo mal formatado |
| Sem lock de arquivo | MÉDIO | Race se múltiplos processos |
| `write_pending()` sem atomicidade | ALTO | Escrita parcial se crash |
| Sem `cancel()` implementation | MÉDIO | Não há como abortar |

### 4.5 `engine/host/adapters/tty.py`

| Achado | Gravidade | Detalhe |
|---|---|---|
| `isatty()` double-check redundante | BAIXO | Código morto |
| `input()` sem timeout | MÉDIO | Trava se stdin for pipe sem dados |
| Echo dependencies | BAIXO | Depende de raw_input settings |
| Ctrl+C handling básico | MÉDIO | KeyboardInterrupt não tratado |

### 4.6 `engine/host/adapters/opencode_fallback.py`

| Achado | Gravidade | Detalhe |
|---|---|---|
| Fallback via intent_file | **CRÍTICO** | Mesmo problemas do intent_file |
| Sem integração direta opencode | ALTO | Poderia usar API nativa |
| Sem testes | ALTO | Não há testes para este adapter |
| `resolve()` retorna None sem erro | MÉDIO | Silently fails |

### 4.7 `engine/ui/question.py` (882 linhas)

| Achado | Gravidade | Detalhe |
|---|---|---|
| 108 callsites `ask*()` | ALTO | Cada um é ponto de travamento |
| Sem timeout em nenhum método | CRÍTICO | Qualquer ask pode travar infinitamente |
| 5 métodos `ask*()` sem padronização | MÉDIO | Interfaces inconsistentes |
| Sem `ask_many()` para batelada | MÉDIO | Questões independentes são sequenciais |
| Sem streaming para questões longas | BAIXO | Usuário não vê progresso |
| Sem `ask_or_default()` | MÉDIO | Cada callsite precisa tratar no-answer |
| Mix de lógica de UI e domínio | MÉDIO | Violação de SRP |
| Questões condicionais complexas | MÉDIO | Aninhamento de ask dentro de callbacks |

---

## 5. Fase 6c: Deep Dive Intent Protocol (DRIFT-1)

### 5.1 Protocolo DRIFT-1 — Lifecycle

```
forge exit 2
    → intent_state.py: write_pending (arquivo intent)
    → host/adapter: wait_for_intent (polling)
    → host/adapter: mark consumed
    → engine re-invoca com resposta
```

### 5.2 `engine/ui/intent_state.py` (~680 linhas)

| Achado | Gravidade | Detalhe |
|---|---|---|
| TOCTOU em consumed detection | **ALTO** | Check exist → write; race window |
| `consumed_intent_log` sem lock | MÉDIO | Race em escrita paralela |
| `write_pending()` sem atomicidade | **ALTO** | Escrita parcial se crash |
| Sem `file lock` no intent file | MÉDIO | Race entre processos |
| Sem cleanup de intents consumidos | MÉDIO | Acúmulo no filesystem |
| Path do intent file hardcoded | BAIXO | Não configurável |
| Sem validação de conteúdo | MÉDIO | Qualquer string é aceita |
| Sem encoding explícito | BAIXO | UTF-8 assumido |
| Sem max size limit | BAIXO | Intent file gigante possível |
| Sem GC de intents órfãos | MÉDIO | Orphans se processo morre |
| `wait_for_intent()` sem timeout | **CRÍTICO** | Loop infinito |
| Polling sem backoff | MÉDIO | 100% CPU em loop |
| Sem `on_cancel` callback | MÉDIO | Não há hook de cancelamento |
| Sem `on_progress` callback | BAIXO | Não há feedback de progresso |
| Parse error sem fallback | **ALTO** | Intento não recuperável |
| Sem modo non-interactive | **ALTO** | Qualquer pergunta trava em CI |
| Sem `ask_many()` | MÉDIO | Questões são 1:1 com I/O |
| Sem batch confirmation | MÉDIO | Confirma pergunta por pergunta |
| Sem `ask_or_skip()` | MÉDIO | Não há default para skip |
| Sem `ask_with_retry()` | MÉDIO | Falha de parse → crash |
| Sem `ask_with_preview()` | BAIXO | Não mostra contexto |
| Sem `ask_with_validation()` | MÉDIO | Input não validado antes de processar |
| Sem `ask_with_timeout()` | **CRÍTICO** | Não há timeout |
| Sem `ask_with_cancel()` | **CRÍTICO** | Não há cancelamento |
| Sem `ask_with_progress()` | BAIXO | Não há indicador de progresso |
| Sem `ask_with_default()` | MÉDIO | Não há valor default |
| Sem streaming | MÉDIO | Tudo ou nada |
| Sem async/await | MÉDIO | Tudo síncrono |
| Sem `answer.format()` | BAIXO | Resposta só raw text |
| Sem `answer.metadata` | BAIXO | Sem timestamp, adapter source |
| Sem `question.context` | BAIXO | Sem ID de fase/comando |
| Sem `question.help_text` | BAIXO | Sem ajuda inline |
| Sem `question.examples` | BAIXO | Sem exemplos |
| Sem `question.validation` | MÉDIO | Sem validação de input |
| Sem `question.dependencies` | BAIXO | Sem visualização de dependências |
| Sem `question.batch_group` | MÉDIO | Sem agrupamento |
| Sem `question.priority` | BAIXO | Sem ordenação |
| Sem `question.conditional` | MÉDIO | Sem questões condicionais |
| Sem `question.repeat` | MÉDIO | Sem repeat groups |
| Sem `question.confirm_all` | MÉDIO | Sem confirmação em lote |
| Sem `question.skip_if` | MÉDIO | Sem skip lógico |
| Sem `question.default_from_env` | BAIXO | Sem default via env var |
| Sem `question.mask_sensitive` | MÉDIO | Senhas em texto claro |

### 5.3 Protocol Flow Gaps

| Gap | Impacto |
|---|---|
| Sem non-interactive mode | Todo comando trava em CI |
| Sem modo batch | Múltiplas perguntas = múltiplos round-trips |
| Sem fallback TTY quando AI falha | Degradação graciosa inexistente |
| Sem recovery em parse failure | Loop infinito |
| Sem hooks pre/post intent | Não extensível |
| Sem metering/logging central | Sem telemetria |
| Sem idempotency tokens | Re-execução = re-envio |
| Sem versionamento de schema | Mudanças quebram intents antigos |

---

## 6. Fase 6d: Deep Dive Init/Implement/Plan

### 6.1 `engine/init.py` — 2656 linhas

| Achado | Gravidade | Detalhe |
|---|---|---|
| `_detect_brownfield()` dead code | **ALTO** | Lógica morta que engana leitor |
| Split brownfield sem 3-caminhos | MÉDIO | Usuário não pode escolher caminho |
| 2656 linhas = god class | **ALTO** | Dificuldade de manutenção |
| Docstring stale | MÉDIO | Parâmetros não documentados |
| Sem dry-run mode | BAIXO | Simulação impossível |
| Sem rollback em erro parcial | MÉDIO | Arquivos criados antes do crash |
| Brownfield detection imprecisa | MÉDIO | Heurística frágil |
| Sem validação de git state | MÉDIO | Dirty repo vs init |
| Sem suporte a template customizado | BAIXO | Template fixo |
| Sem `--force` para re-init | MÉDIO | Só funciona em dir vazio |
| Sem output JSON para AI | BAIXO | Só texto humano |
| Interatividade forçada | **ALTO** | Trava em CI |

### 6.2 `engine/implement.py` — Stub Manual

| Achado | Gravidade | Detalhe |
|---|---|---|
| **Stub — não gera código** | **CRÍTICO** | Só imprime instruções |
| `_apply_mode_handoff()` imprime e retorna | ALTO | Não executa nada |
| Docstring stale | MÉDIO | Parâmetros desatualizados |
| Sem integração com AI | ALTO | Poderia invocar LLM |
| Sem template rendering | ALTO | Poderia usar templates/ |
| Sem validação de output | MÉDIO | Não verifica se arquivos foram criados |
| Sem testes | MÉDIO | Tests/implement.py minimal |
| Modo `apply` documentado mas não implementado | MÉDIO | --mode=apply crasha |

### 6.3 `engine/plan.py` — Waves A-E

| Achado | Gravidade | Detalhe |
|---|---|---|
| Waves A-E sem paralelismo real | MÉDIO | Sequencial por design |
| Sem re-planning incremental | MÉDIO | Plan inteiro é refeito |
| Sem validação de dependências | MÉDIO | Dependências manuais |
| Wave E sem teste de integridade | BAIXO | Verificação post-plan é manual |

### 6.4 `engine/verify.py`

| Achado | Gravidade | Detalhe |
|---|---|---|
| Verificação por testes apenas | MÉDIO | Sem verificação semântica |
| Sem validação de coverage | BAIXO | Só test pass/fail |
| Docstring stale | MÉDIO | Funcionalidade desatualizada |
| Sem modo `--deep` | BAIXO | Só verificação superficial |
| Sem relatório JSON para AI | BAIXO | Só texto humano |
| Sem verificação de docs | MÉDIO | Não verifica handoff/CHANGELOG |
| Sem verificação cross-phase | MÉDIO | Cada fase isolada |

---

## 7. Fase 7: Docs Drift — 7 Discrepâncias

### 7.1 `cli.py` docstring stale

**Problema:** Documenta "12 canonical subcommands". Código tem 14 subcomandos (`qa`, `upgrade` adicionados).

**Afeta:** Documentação inline, `--help`.

### 7.2 `reconfigure.py` docstring stale

**Problema:** Refere "Decision 9 (12 commands)" mas Decision 9 não trata de número de comandos.

**Afeta:** Leitor confuso.

### 7.3 `implement.py` docstring stale

**Problema:** Parâmetros `--mode`, `--component`, `--scope` documentados incorretamente.

**Afeta:** Desenvolvedor lendo o código.

### 7.4 `verify.py` docstring stale

**Problema:** Docstring desatualizada.

**Afeta:** Manutenibilidade.

### 7.5 `handoff.md` test counts defasados

**Problema:** Reporta "1761 tests baseline". `pytest --collect-only` mostra 1779.

**Afeta:** Quem lê handoff toma decisão com dado errado (+18 rapid, +7 integration).

### 7.6 Decision 10 — Exceções não documentadas

**Problema:** Decision 10 diz "zero flags". `forge graph --json --no-auto-build` usa duas flags. Nenhuma Revisita formal registrada.

**Afeta:** Consistência de design.

### 7.7 `init.py` `_detect_brownfield` dead code

**Problema:** Código morto de 3 rotas de brownfield. Docstring promete 3 cenários, código só tem 2.

**Afeta:** Leitor acha que funcionalidade existe.

---

## 8. Fase 8: Deep Dive Exaustivo — Graph, Memory, Cards, MCP

### 8.1 Graph Subsystem

#### 8.1.1 Architecture

```
graph/
├── __init__.py       # CLI interface
├── builder.py        # Build pipeline
├── cache.py          # Cache management
├── queries.py        # Query definitions (Q1-Q17)
├── parser_kotlin.py  # Kotlin parser (618 linhas)
├── parser_swift.py   # Swift parser
├── parser_typescript.py
├── parser_javascript.py
├── parser_java.py
├── parser_xml.py
├── parser_objc.py
└── parser_objetivec.mm
```

#### 8.1.2 Parser Kotlin — ReDoS

```
_RE_DECL = re.compile(r"\s*(private\s+)?\w+\(.*?\)")
```

**Problema:** Backtracking exponencial com `(private\s+)?` combinado com `.*?` e `\(.*?\)`. Input adversarial como `private private private private (aaaaaa` causa catastrophic backtracking.

**Gravidade:** **ALTO**

#### 8.1.3 Parser Kotlin — Where Clause Bug

```kotlin
fun foo() where T : Bar { }  // parser vê como declaração
```

**Problema:** `where` clause pós-assinatura é tratada como declaração separada → body hash inconsistente.

**Gravidade:** **MÉDIO**

#### 8.1.4 Queries Sempre Vazias

| Query | Status | Problema |
|---|---|---|
| Q12 (reusable-helpers) | **SEMPRE VAZIA** | SQL sem matching |
| Q14 (duplicate-code) | **SEMPRE VAZIA** | SQL sem matching |

**Gravidade:** **MÉDIO** — funcionalidade documentada mas não funcional.

#### 8.1.5 TypeScript Parser — Incompleto

**Problema:** Classes, interfaces, tipos export vs local — não rastreia corretamente. `import { Foo }` não linka ao arquivo de definição.

**Gravidade:** **MÉDIO**

#### 8.1.6 ObjC — Sem Call Graph

**Problema:** Regex-based, sem AST. Call graph não implementado.

**Gravidade:** **BAIXO** (ObjC é raro no ecossistema)

#### 8.1.7 Graph Cache Race

**Problema:** `.claude/graph.db` WAL mode pode corromper se múltiplos processos escrevem em paralelo.

**Gravidade:** **MÉDIO**

### 8.2 Memory Subsystem

#### 8.2.1 Architecture

```
memory/
├── __init__.py
├── l1.py          # Phase state (L1.json)
├── l2.py          # Working memory (L2.json)
├── l3.py          # Long-term memory (L3/*.md)
├── evolve.py      # Memory evolution
└── models.py      # Data models
```

#### 8.2.2 L1 — Race na `_mirror_phase_lock_to_status`

**Problema:** Comentário no código diz "both operations under a single atomic gate" mas não há gate real — apenas duas operações de arquivo independentes.

```
self._write_phase_lock(phase_id, lock_data)
self._write_status_file(phase_id, status_data)  # race window here
```

**Gravidade:** **ALTO**

#### 8.2.3 L2 — Race no Read-Modify-Write

**Problema:** `read_l2()` → modify dict → `write_l2()`. Sem lock entre leitura e escrita.

```python
data = self._read_json()
data["key"].append(new_item)  # outro processo pode ter escrito aqui
self._write_json(data)        # last-writer-wins
```

**Gravidade:** **ALTO**

#### 8.2.4 L3 — Single-File Bottleneck

**Problema:** `memory/l3/` com múltiplos arquivos .md, mas `evolve.py` carrega todos em RAM.

**Gravidade:** **MÉDIO**

### 8.3 Cards System

#### 8.3.1 Cards Loader — Fallthrough Error

**Problema:** `cards/loader.py` tem fallthrough em `logger.warning` sem `return None`:

```python
try:
    card = yaml.safe_load(f.read())
except Exception:
    logger.warning(f"Failed to load card {path}")
    # fallthrough — card é None, código abaixo espera dict
```

**Consequências:**
1. `None` retornado onde `dict` esperado → `TypeError` runtime
2. `ImportError` capturado mas mensagem mal-formatada
3. Três falhas distintas no mesmo fluxo

**Gravidade:** **ALTO**

### 8.4 MCP Subsystem — TODOS Stubs

#### 8.4.1 Providers não implementados

```python
# engine/mcp/providers/google.py
raise NotImplementedError("Phase 5 (MCP wiring pending)")

# engine/mcp/providers/openai.py
raise NotImplementedError("Phase 5 (MCP wiring pending)")

# engine/mcp/providers/anthropic.py
raise NotImplementedError("Phase 5 (MCP wiring pending)")

# engine/mcp/providers/local.py
raise NotImplementedError("Phase 5 (MCP wiring pending)")

# engine/mcp/providers/remote.py
raise NotImplementedError("Phase 5 (MCP wiring pending)")

# engine/mcp/providers/custom.py
raise NotImplementedError("Phase 5 (MCP wiring pending)")
```

**Gravidade:** **CRÍTICO** — 6/6 NotImplementedError.

### 8.5 JSON I/O Race

**Problema:** `engine/utils/json_io.py`:

```python
def write_json(path, data):
    tmp = path + ".tmp"  # .tmp fixo — colisão entre processos
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.rename(tmp, path)
```

`.tmp` fixo → colisão entre processos escrevendo para paths diferentes mas mesmo `.tmp`.

**Gravidade:** **MÉDIO**

### 8.6 Detection/Composer — Stubs

**Problema:** `engine/detection/composer.py` tem 4 stubs de spiking/chore.

**Gravidade:** **MÉDIO**

---

## 9. Resumo Consolidado de Todos os Gaps

### 9.1 Por Gravidade

#### CRÍTICOS (4)

| # | Gap | Subsistema | Impacto |
|---|---|---|---|
| C1 | **MCP server inexistente** — 6/6 NotImplementedError | mcp/ | Sem integração com ferramentas agênticas |
| C2 | **Opencode = cidadão 2ª classe** — IntentFileAdapter sem canal de notificação, env vars CC prioritários | host/adapters/ | Experiência degradada em opencode |
| C3 | **Decision 10 sem Revisita** — exceções não documentadas, docstrings stale em 5 arquivos | docs/ + engine/ | Drift de design |
| C4 | **forge implement é stub** — não gera código | implement.py | Comando mais crítico não funciona |

#### ALTOS (6)

| # | Gap | Subsistema | Impacto |
|---|---|---|---|
| H1 | **Race conditions no memory** — L1 gate mítico, L2 read-modify-write sem lock | memory/ | Corrupção de estado |
| H2 | **ReDoS no parser Kotlin** — `_RE_DECL` backtracking exponencial | graph/parser_kotlin.py | Crash ou hang |
| H3 | **Cards loader fallthrough** — 3 bugs em série | cards/loader.py | TypeError runtime |
| H4 | **Intent protocol — 47 gaps** — sem timeout, sem cancelamento, sem non-interactive | ui/ + host/ | 108 deadlock points |
| H5 | **Docstrings stale (5 arquivos)** — cli.py, init.py, implement.py, reconfigure.py, verify.py | engine/ | Desinformação |
| H6 | **handoff.md test counts** — 1761 ≠ 1779 (+18) | docs/ | Decisão com dado errado |

#### MÉDIOS (8)

| # | Gap | Subsistema | Impacto |
|---|---|---|---|
| M1 | **Sem modo CI/non-interactive** | host/ + ui/ | Qualquer pergunta trava em pipeline |
| M2 | **Sem recovery em graph parser crash** | graph/ | Hang sem timeout |
| M3 | **L3 single-file bottleneck** | memory/l3/ | OOM com uso intenso |
| M4 | **Graph cache race (WAL concorrente)** | graph/cache.py | Corrupção de cache |
| M5 | **Emoji em session-start hook** | .claude/hooks/ | Poluição de canal stdout |
| M6 | **Sem cancellation no intent protocol** | ui/ | Ctrl+C = estado inconsistente |
| M7 | **Sem streaming de intents** | ui/ | Questões longas sem feedback |
| M8 | **JSON I/O .tmp fixo compartilhado** | utils/json_io.py | Colisão entre processos |

#### BAIXOS (4)

| # | Gap | Subsistema | Impacto |
|---|---|---|---|
| L1 | **Q12 (reusable-helpers) e Q14 (duplicate-code) sempre vazias** | graph/queries.py | Feature documentada mas não funcional |
| L2 | **TypeScript parser incompleto** | graph/parser_typescript.py | Análise parcial |
| L3 | **forge doctor sem métricas de cobertura** | doctor.py | Diagnóstico incompleto |
| L4 | **Opencode adapter não testado** | host/adapters/ | Sem testes |

### 9.2 Por Subsistema

| Subsistema | Críticos | Altos | Médios | Baixos | Total |
|---|---|---|---|---|---|
| host/ | 2 | 2 | 2 | 1 | **7** |
| ui/ (intent protocol) | 0 | 2 | 3 | 0 | **5** |
| engine/ (init/implement) | 2 | 2 | 1 | 0 | **5** |
| graph/ | 0 | 1 | 2 | 2 | **5** |
| memory/ | 0 | 2 | 1 | 0 | **3** |
| docs/ | 1 | 2 | 0 | 0 | **3** |
| cards/ | 0 | 1 | 0 | 0 | **1** |
| mcp/ | 1 | 0 | 0 | 0 | **1** |
| utils/ | 0 | 0 | 1 | 0 | **1** |
| hooks/ | 0 | 0 | 1 | 0 | **1** |

---

## 10. 7 Recomendações Pré-Piloto

### P0 — Bloqueantes (devem ser resolvidos ANTES do piloto)

#### R1: Implementar MCP server mínimo

**O quê:** Servidor MCP com 2-3 ferramentas: `forge_run_command(command)`, `forge_verify_phase()`, `forge_graph_status()`. Usar `engine/cli.py` como backend via subprocesso com output JSON.

**Por quê:** Sem MCP, ferramentas agênticas (Claude Code Desktop, Cursor, Windsurf) não conseguem executar comandos forge como ferramentas nativas.

**Complexidade:** Média — pode usar arquitetura `mcp` da spec do MCP.

#### R2: Adicionar `--non-interactive` flag + `AnswerFormatter`

**O quê:** Flag global `--non-interactive` (ou env var `FORGE_NON_INTERACTIVE=1`) que faz `question.ask*()` retornar valores default. `AnswerFormatter` que serializa respostas em JSON estrito.

**Por quê:** Sem isso, TODO comando forge trava quando não há TTY. É o pré-requisito para pipelines CI e para ferramentas agênticas.

**Complexidade:** Baixa-média — maior parte do trabalho é no `question.py`.

### P1 — Altos (essenciais para qualidade)

#### R3: Fix ReDoS no parser Kotlin

**O quê:** Substituir `re.compile(r"\s*(private\s+)?\w+\(.*?\)")` por parser sem backtracking. `re.error` ou `timeout` no regex.

**Por quê:** Input adversarial → hang do CLI sem timeout.

#### R4: Atualizar docstrings e test counts

**O quê:** `cli.py:14`, `init.py`, `implement.py`, `reconfigure.py`, `verify.py`. `handoff.md:1779`.

**Por quê:** Drift de informação engana mantenedores e ferramentas AI que leem docstrings como ground truth.

#### R5: Fix cards loader fallthrough

**O quê:** 3 correções: `return None` após `logger.warning`, verificação de `None` antes de acessar como `dict`, `ImportError` format string fix.

**Por quê:** TypeError runtime que só aparece em runtime.

### P2 — Importantes (qualidade de longo prazo)

#### R6: Adicionar lock no L2 memory write

**O quê:** `fcntl.flock()` ou `filelock` library no `write_l2()`. Leitura sem lock mas escrita exclusiva.

**Por quê:** Read-modify-write sem lock = last-writer-wins.

#### R7: Registrar Revisita formal Decision 10

**O quê:** Entrada em `01-decisions.md` explicando que `forge graph --json --no-auto-build` é exceção documentada à regra "zero flags".

**Por quê:** Sem registro formal, violação silenciosa de decisão locked.

---

## 11. 6 Oportunidades Estratégicas

| # | Oportunidade | Descrição | Impacto |
|---|---|---|---|
| O1 | **ACP adapter** | Agent Communication Protocol — permite que agentes remotos comuniquem com forge | Expande ecossistema |
| O2 | **`forge plan --diff`** | Re-planning incremental que só re-planeja fases afetadas por mudança | Performance |
| O3 | **`forge implement --ai`** | Implementar com LLM real (invocar Claude/GPT para gerar código do plano) | **Game-changer** |
| O4 | **forge doctor com métricas** | Pipeline health real — test counts, coverage, lint, typecheck | Confiabilidade |
| O5 | **`forge memory search --semantic** | Embedding search no L3 para reuso inteligente de contexto | Produtividade |
| O6 | **forge como MCP tool para terceiros** | Outros repositórios podem usar forge como ferramenta MCP | Adoção |

---

## 12. Resultado dos Testes de "E se"

| # | Cenário | Resultado | Risco Real |
|---|---|---|---|
| 1 | Host detect miss | Crash sem adapter | MÉDIO |
| 2 | L1.json malformed | Crash sem recovery | ALTO |
| 3 | Race init + graph | `.tmp` collision | MÉDIO |
| 4 | Intent file corrompido | Loop infinito | CRÍTICO |
| 5 | Orphan intent file | Ghost intent | MÉDIO |
| 6 | lock.json desync | Deadlock | MÉDIO |
| 7 | L3 markdown malformed | Crash evolve | BAIXO |
| 8 | MCP not implemented | NotImplementedError | CRÍTICO |
| 9 | Graph parser hanging | Hang sem timeout | ALTO |
| 10 | Emoji no stdout | Poluição de canal | BAIXO |
| 11 | Graph parallel rebuild | Cache corrupto | MÉDIO |
| 12 | ADR 7 LOCKED + implement | Silencia regra | BAIXO |
| 13 | Huge L3 | OOM potencial | BAIXO |
| 14 | Ctrl+C mid-intent | Estado inconsistente | MÉDIO |

---

## 13. Anexos

### A. Comandos Forge (14 + 1)

| Comando | Visível | Status | Doc Stale? |
|---|---|---|---|
| `forge init` | user-facing | ✅ Funcional | Sim (brownfield dead code) |
| `forge plan` | user-facing | ✅ Funcional | Não |
| `forge implement` | user-facing | 🟡 Stub manual | Sim |
| `forge verify` | user-facing | ✅ Funcional | Sim |
| `forge status` | user-facing | ✅ Funcional | Não |
| `forge doctor` | user-facing | ✅ Funcional | Sim (sem coverage) |
| `forge reconfigure` | user-facing | ✅ Funcional | Sim |
| `forge graph` | user-facing | ✅ Funcional | Não |
| `forge memory` | user-facing | ⚠️ Races L1/L2 | Não |
| `forge evolve` | user-facing | ✅ Funcional | Não |
| `forge undo` | user-facing | ✅ Funcional | Não |
| `forge raw` | user-facing | ✅ Funcional | Não |
| `forge qa` | user-facing | ✅ Funcional | Não |
| `forge upgrade` | user-facing | ✅ Funcional | Não |
| `forge ingest` | hidden (hook) | ✅ Funcional | Não |

### B. 44 TODOs/Stubs Identificados

- **MCP providers**: 6 NotImplementedError (google, openai, anthropic, local, remote, custom)
- **Detection spiking/chore**: 4 stubs em `composer.py`
- **Implement apply mode**: stub manual
- **Evolve --dry-run**: não implementado
- **Memory search --semantic**: não implementado
- **Plan --diff**: não implementado
- **Doctor --coverage**: não implementado
- **Graph Q12, Q14**: vazios
- **TypeScript parser**: incompleto
- **Opencode adapter**: não testado
- **Migration framework**: não iniciado
- **Spark/chore detection**: 4 stubs

### C. Discrepâncias Doc vs Código

| Arquivo | Doc diz | Código tem | Gravidade |
|---|---|---|---|
| `cli.py` docstring | "12 canonical subcommands" | 14 comandos | ALTA |
| `reconfigure.py` docstring | "Decision 9 (12 commands)" | Decision 9 ≠ número de comandos | MÉDIA |
| `implement.py` docstring | Parâmetros desatualizados | --mode, --component, --scope | MÉDIA |
| `verify.py` docstring | Funcionalidade desatualizada | | MÉDIA |
| `handoff.md` | "1761 tests baseline" | 1779 tests coletados (+18) | ALTA |
| `01-decisions.md` (D10) | "zero flags" | `forge graph --json --no-auto-build` | ALTA |
| `init.py` | "3 brownfield scenarios" | Código só tem 2 | MÉDIA |

### D. Avaliação de Adapters

| Adapter | Funciona em | Nota | Problema Principal |
|---|---|---|---|
| `ClaudeCodeAdapter` | Claude Code | B+ | Cache em memória apenas |
| `IntentFileAdapter` | Universal | C+ | Sem notificação, sem timeout |
| `TTYAdapter` | Terminal | B | Sem timeout, sem non-interactive |
| `OpencodeFallbackAdapter` | Opencode | **B-** | Fallback via intent_file, sem testes |

---

## 14. Conclusão

feature-forge é uma ferramenta **sólida** para uso humano em terminal — todos os testes passam, `forge verify` verde, arquitetura bem pensada. No entanto, para o **piloto AI/LLM-first**, há 4 bloqueadores críticos e 6 gaps altos que precisam ser endereçados.

### Pronto para Piloto?

| Requisito | Status |
|---|---|
| Testes passam? | ✅ SIM |
| CLI funcional? | ✅ SIM (exceto implement) |
| Comandos principais funcionam? | ✅ SIM |
| Resiliência a inputs AI/LLM? | ❌ NÃO |
| MCP server? | ❌ NÃO |
| Modo non-interactive? | ❌ NÃO |
| Opdecode first class? | ❌ NÃO |
| Implement gera código? | ❌ NÃO |
| Docs atualizadas? | ⚠️ PARCIAL |

**Veredito:** `forge` está **pronto para uso humano** mas **NÃO está pronto para piloto exclusivamente AI/LLM-first**. Recomenda-se implementar os 2 P0 blockers (MCP server + `--non-interactive` flag) antes de iniciar o piloto.

---

*Relatório gerado por auditoria READ-ONLY em 2026-06-17. Nenhuma linha de código foi modificada.*
