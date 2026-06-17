# Relatório Consolidado de Auditoria LLM-First — feature-forge 1.4.0 (PR #17)

> **Data:** 2026-06-17
> **Provenance:** consolida e reconcilia DUAS auditorias independentes da mesma branch (`feat/v1.3-pilot-ready`, PR #17):
> - **Auditoria A (Claude / orquestrador):** 6 eixos paralelos + verificação trust-but-verify → `docs/reports/auditoria-llm-first-2026-06-17.md`.
> - **Auditoria B (opencode):** 8 fases, 22 gaps → `docs/reports/auditoria-pre-piloto.md`.
> **Método de consolidação:** cada alegação da Auditoria B foi fact-checada claim-by-claim contra o código (file:line), classificada REAL / FALSO / STALE / PARCIAL / WISHLIST, e cruzada com os achados da Auditoria A pra remover duplicidade.
> **Status:** este documento é a **fonte única de verdade** e supersede os dois relatórios de origem (mantidos como insumo histórico). É a base pro planejamento de evolução.
> **Adendo comportamental (2026-06-17):** análise de loops de comando + ambiguidade + design do "grill" em `docs/reports/analise-comportamental-2026-06-17.md` (fact-check do `loops-abertos.md` + cenários do `forge plan` + 6 findings novos: CASING-BUG, AMBIGUITY-DEAD, PHANTOM-STATES, CARDS-DISCONNECT, ABORTED-DEADEND, PLAN-FRONTDOOR).
> **Voz:** mentor calmo. Severidade determinística.

---

## 0. Veredito consolidado

O `forge` **não está agentic-ready** — mas por um motivo que **nenhuma** das duas auditorias isoladas acertou por completo. A Auditoria A identificou o bloqueador certo (sem driver de host); a Auditoria B errou o alvo (priorizou MCP/non-interactive) e teve ~75% das suas alegações críticas/altas refutadas pelo código.

**Quatro CRÍTICOS reais (gate do piloto):**
1. **DRIVER-001** — nenhum artefato ensina o host a dirigir o intent loop → produto interativo inteiro morre no 1º prompt num consumidor.
2. **DEAD-VERIFY** — gate pre-commit `forge verify` é no-op silencioso (bug de path).
3. **EXIT-2-COLLISION** — exit 2 significa "pausado" E "erro fatal"; escada 3/4/5/6/8 não-documentada com colisões.
4. **CONC-1** — processos forge paralelos corrompem state files (tempfile fixo + sem flock); o próprio teste do projeto assere a corrupção.

**Importante (correção da Auditoria B):** o tema central da opencode — "sem timeout → loop infinito / deadlock / `wait_for_intent` bloqueia pra sempre" — é **falso**. O engine não faz polling: ele `raise PausedForInputError` → **exit 2** e o host re-invoca. Não existe loop, sleep, nem espera bloqueante em lugar nenhum de `engine/host/` ou `intent_state.py`.

---

## 1. Como ler este relatório

- **§2** é a avaliação crítica da Auditoria B (o que é real, falso, duplicado) — responde diretamente "veja o que é real e o que não é".
- **§3** é a lista consolidada de findings **verificados** (a verdade única), já de-duplicada e re-severitizada.
- **§4** é o balanço autocrítico do que já está sólido.
- **§5/§6** são o catálogo de oportunidades e o roadmap — base do planejamento.
- **Apêndice A** traz o veredito claim-by-claim sobre toda a Auditoria B.

---

## 2. Avaliação crítica da Auditoria B (opencode / `auditoria-pre-piloto.md`)

### 2.1 Causa-raiz dos falsos-positivos: leitura arquitetural errada

O §5.1 da Auditoria B descreve o lifecycle como `write_pending → wait_for_intent (polling) → mark consumed → re-invoca`. **Esse modelo não existe no código.** O real é:

```
ask*() → adapter._ask_loop → (1ª vez) escreve pending + raise PausedForInputError → cli.py exit 2
  → [HOST lê, responde, re-invoca com argv idêntico]
  → ask*() → adapter._ask_loop → read_response (disco) acha resposta → retorna AskResult
```

Não há `wait_for_intent()`, `resolve()` bloqueante, `time.sleep`, `while True`, nem polling (`intent_file.py:193-303`, `claude_code.py:236-281`, `cli.py:330-337`). Como a Auditoria B assumiu um modelo de polling, toda a família "timeout / loop infinito / deadlock / 108 deadlock points / CPU 100%" desabou junto — é o grosso dos CRÍTICOS e ALTOS dela.

### 2.2 Falsos-positivos confirmados (refutados pelo código)

| Alegação B | Veredito | Por quê (evidência) |
|---|---|---|
| `wait_for_intent()` bloqueia pra sempre / poll infinito (§4.4, §5.2) | **FALSO** | Método não existe; `_ask_loop` termina em `raise PausedForInputError` → exit 2. |
| `resolve()` sem timeout → adapter trava (§4.1) | **FALSO** | Não há `resolve()` no adapter; nenhuma chamada bloqueante no caminho intent. |
| `engine/host/adapters/opencode_fallback.py` (§4.6, anexo D) | **FALSO** | Arquivo não existe; opencode → `IntentFileAdapter` via `detect.py:49-60`. |
| Marker `ECHO_LLM_RESPONSE` hardcoded (§4.3) | **FALSO** | Marker real é `<FORGE_INTENT .../>` (`claude_code.py:352`). |
| Cache em memória perdido entre resets (§4.3) | **FALSO** | Re-entry é on-disk (`read_response` + JSONL log), desenhado pra sobreviver resets. |
| Host detect miss → `None` → crash (§3.1) | **FALSO** | `detect_host` sempre cai em `INTENT_FILE` (`detect.py:59-60`); nunca retorna None. |
| `write_pending()` sem atomicidade (§4.4, §5.2) | **FALSO** | É atômico: tempfile→`flush`→`fsync`→`os.replace`→fsync-dir (`json_io.py:106-123`). |
| Sem cancelamento / Ctrl+C inconsistente (§3.14, §5.2) | **FALSO** | `UserCancelledError` + `KeyboardInterrupt` → exit 130 (`cli.py:350-362`). |
| Corrupted intent → loop infinito (§3.4) | **PARCIAL** | Na verdade → exit 1 limpo (`cli.py:373-379`). (nugget real adjacente em §3.4-nugget abaixo.) |
| Parser Kotlin `_RE_DECL` ReDoS (§8.1.2) | **FALSO** | Regex citado não existe; `_RE_DECL` real é VERBOSE/ancorado/bounded; corpos via char-scanner. Sem ReDoS realista. |
| Kotlin where-clause → body hash inconsistente (§8.1.3) | **FALSO** | `where` tratado como terminador de return-type (`parser_kotlin.py:398-419`). |
| Q12/Q14 "sempre vazias" + numeração (§8.1.4) | **FALSO** | Numeração errada; queries são SQL parametrizado real, data-dependent (`queries.py:329-452`). |
| graph.db WAL race em escrita paralela (§8.1.7) | **FALSO** | `busy_timeout=5000` + `BEGIN IMMEDIATE` + `GraphError` tipado (`sqlite_io.py:231-299`). |
| L1 `_mirror_phase_lock_to_status` race ("atomic gate mítico") (§8.2.2) | **FALSO** | Sentinel `O_CREAT|O_EXCL` É o gate cross-process (`l1.py:498-614`); sem comentário enganoso. |
| L1.json malformed → stack trace exposto (§3.2) | **FALSO** | `try/except JSONDecodeError` → `MemoryError` tipado + guarda `isinstance(dict)` (`l1.py:224-229`). |
| L3 carrega tudo em RAM → OOM (§3.13, §8.2.4) | **FALSO** | L3 é lazy/read-only; `evolve` opera em L2 YAML com cap 0.5MB (`l3.py:104-192`). |
| cards/loader.py fallthrough → None → TypeError (§8.3.1) | **FALSO** | loader não tem logger; levanta `CardError`. Caminho None-como-dict não existe. |
| composer.py 4 stubs spiking/chore (§8.6) | **FALSO** | `compose_backend_axes` totalmente implementado (`composer.py:125-247`). |
| implement docstring documenta flags `--mode/--component/--scope` (§7.3) | **FALSO** | Docstring fala de fases de lifecycle, não flags; `run(argv)` não parseia essas flags. |
| handoff diz "1761 tests baseline" (§7.5) | **FALSO (auto-referência)** | Handoff diz **1569/162/30**. A string "1761" só existe **dentro do próprio relatório opencode** — ele citou a si mesmo como se fosse o handoff. |
| MCP inexistente = CRÍTICO bloqueador AI-first (§3.8, §8.4, C1) | **MIS-SEVERITIZADO** | São 4 providers (context7/github_issues/jira/linear), não 6; `NotImplementedError` real porém **dormant/inalcançável** (importado só por 1 teste; registry retorna None se não configurado; é **non-goal explícito**). No máximo nota LOW de dead-code/doc. |

### 2.3 Inflação de findings

O §5.2 da Auditoria B lista ~30 linhas "Sem X" (Sem async, Sem `ask_with_preview`, Sem `question.examples`, Sem `mask_sensitive`, Sem streaming, Sem `ask_many`…). São **wishlist especulativa** contra uma API imaginada mais rica, não bugs. A ABC do adapter é deliberadamente mínima (5 métodos: `ask`/`ask_text`/`ask_multi`/`emit_progress`/`emit_warn`); ausência de async/streaming/preview é escopo-por-design, não defeito. (`mask_sensitive` já é mitigado por `mode=0o600` em `json_io.py:67-79`.) Inflar a contagem de gaps com missing-features dilui os achados reais.

### 2.4 O que a Auditoria B ACERTOU (real e valioso)

- **Concorrência / `.tmp` fixo (§3.3, §8.5):** REAL — mas o *rationale* dela está errado (diz "paths diferentes colidem no mesmo `.tmp`"; na verdade paths diferentes geram `.tmp` diferentes — a colisão real é **dois processos no mesmo path**, sem flock). Duplica e é menos preciso que **CONC-1** (Auditoria A).
- **Decision 10 "zero flags" violada + cli.py "12 canonical" (§7.1, §7.6, C3):** REAL — duplica **FLAG-CONTRACT-VIOLATION** + **HELP-COUNT-DRIFT** (Auditoria A). Nova instância: `reconfigure.py:6` também diz "Decision 9 (12 commands)".
- **Três nuggets NET-NEW reais** (não estavam na Auditoria A — incorporados em §3):
  1. **SCHEMA-LEAK** — `SchemaVersionMismatchError` (um `RuntimeError`) NÃO está na tupla de except do `cli.py:363-366` → vaza traceback cru em vez de mensagem mentor-calmo. Estende **SCHEMA-1**.
  2. **BROWNFIELD-DEADCODE** — `_detect_brownfield` (`init.py:203-228`) é dead-code (só testes chamam); pior, o handoff (`08-session-handoff.md`) **anuncia ela como em-uso** → mismatch doc↔código.
  3. **L2-RMW** — `write_l2`/`add_entry` fazem read-modify-write sem lock inter-processo (`l2.py:367-454`); baixa probabilidade (single-writer via `forge evolve`), mas mecanismo real.
- **`forge implement` é "stub manual" (§6.2, C4):** REAL que não gera código — **porém é BY-DESIGN** (forge orquestra; o LLM-host implementa — Decisão 22 + exec model canônico). Mis-framado como bug crítico. O legítimo aqui é clareza de docstring/naming (não "comando quebrado").
- Limitação do TypeScript parser (named-import não resolve a definição): REAL mas **by-design documentado** (CLAUDE.md "Limitações conhecidas") → BAIXO.

### 2.5 Meta-lição (reflexiva e importante pro objetivo)

A Auditoria B é, ela própria, **a melhor evidência de por que o trabalho LLM-first importa.** Um LLM auditando o forge alucinou ~75% dos seus achados críticos porque **teve que inferir a arquitetura de prosa + source** — inventou `wait_for_intent()`, `opencode_fallback.py`, `ECHO_LLM_RESPONSE`, um regex que não existe, e citou a si mesmo como fonte. Um forge que **emitisse estrutura machine-readable** (manifesto de comandos, `--json`, exit-codes documentados, contrato de protocolo carregável) teria ancorado o auditor e prevenido a maioria desses erros. **Os falsos-positivos da Auditoria B validam os findings ALTO da Auditoria A** (NO-MANIFEST, TOKEN-BLIND, DRIVER-001).

---

## 3. Findings consolidados verificados (fonte única)

Severidade re-calibrada após fact-check. Origem: **[A]** Auditoria A, **[B]** Auditoria B (verificado-real), **[A+B]** ambos.

### 3.1 CRÍTICO (gate do piloto)

**C1 · DRIVER-001 — host não sabe dirigir o intent loop [A]**
O engine emite `<FORGE_INTENT/>` + exit 2 e espera que o host leia o marker, chame `AskUserQuestion`, escreva `forge-response.json` com o `intent-id` casado e re-invoque com argv idêntico. Mas **nada ensina isso ao host**: `find -iname SKILL.md` → vazio; zero `AskUserQuestion` no que `forge init` instala; o protocolo só vive em comentários de `claude_code.py:8-38` e `bin/forge:38-44`. `forge init` registra só 4 hooks de manutenção (`init.py:763-820`).
> **E se** o dev roda `forge plan auth` no Claude Code sem skill carregada? Marker + exit 2 → o modelo não sabe que é protocolo → mostra XML cru ou trata como falha. Produto interativo inteiro morto na chegada. opencode é igual ou pior (não auto-faz poll do pending — DRIVER-003).
> **Fix:** ship `feature-forge` SKILL.md instalada por `forge init` (+ `AGENTS.md` opencode); estratégico: `McpAdapter` com elicitation nativa dissolve o teaching burden.

**C2 · DEAD-VERIFY — gate pre-commit `forge verify` é no-op silencioso [A]**
`hooks/git-pre-commit:13` hardcoda `$PROJECT_ROOT/.claude/hooks/pre-commit-feature-forge.sh` (path legado), mas o init instala em `.claude/forge/hooks/` (`paths.py:288`). `[[ -x "$HOOK" ]]` falso → `exit 0`. O teste stuba o hook interno e não pega.
> **E se** o LLM termina feature e commita confiando no gate? Nenhuma validação roda; artefato quebrado passa pro PR com falso "verificado". fail-open virou fail-silent.
> **Fix:** corrigir o path pra `.claude/forge/hooks/...` + teste do hook REAL.

**C3 · EXIT-2-COLLISION — exit 2 ambíguo + escada não-documentada [A]**
`plan.py:1396` e `implement.py:1138` retornam **2** (sinal load-bearing de "pausado") pra "não é projeto forge"; `verify.py:183` retorna **1** pro MESMO erro. Além disso 3/4/5/6/8 não estão no contrato (`06-command-surface.md` só lista 0/1/2/130), com colisões (exit 4 = "feature missing" no implement E "smoke failed" no upgrade; qa retorna 8).
> **E se** o LLM roda `forge plan x` fora de um projeto? Recebe exit 2 → caça um pending que não existe → loop/confusão. Envenena exatamente o sinal que o host precisa confiar.
> **Fix:** reservar exit 2 só pra pause; colapsar a escada → 1 + tag machine-readable em stderr; teste "nenhum handler retorna 2 exceto pause".

**C4 · CONC-1 — processos paralelos corrompem state files [A+B]**
`json_io.write_json` usa tempfile de nome fixo `path + ".tmp"` (`json_io.py:106`), sem PID/random; `detect_race`→`write_pending` tem janela TOCTOU (`intent_state.py:604` "flock deferred"). O próprio teste `test_concurrent_writers_document_torn_write_window` **assere que JSON corrompido é resultado possível.**
> **E se** dois agentes paralelos (padrão que o projeto incentiva via `dispatching-parallel-agents`) rodam forge no mesmo root? Mesmo `forge-pending.json.tmp` → torn write → cross-answer entre features. O padrão que o forge promove quebra o forge.
> *(Nota: a Auditoria B viu o sintoma mas com rationale errado — "paths diferentes colidem". A colisão real é mesmo-path.)*
> **Fix:** tempfile por-PID (`{pid}.{uuid}.tmp`) + `flock(LOCK_EX)` na seção crítica + namespacing por invocação.

### 3.2 ALTO

**A1 · TOKEN-BLIND — camada de output host-blind [A].** `renderer.write` nunca checa `detect_host`/`CLAUDECODE`. non-TTY só troca Unicode→ASCII (mesmo número de linhas — `status`=33 linhas/1812 chars, `doctor`=75/3908 num projeto vazio). Só `forge graph` tem `--json`; `status/doctor/verify/memory` forçam parse de prosa+glyphs. Dataclasses internas pra serializar já existem. **Fix:** renderer host-aware + `--json` nos read-commands + `FORGE_OUTPUT=json` global.

**A2 · NO-MANIFEST / NO-WORKFLOW-ROUTER [A].** Sem inventário machine-readable de comandos/args (`_print_help` é prosa apontando pra path que não resolve em XDG). `forge status` não sugere próximo passo. **Fix:** `forge --help --json` (manifesto) + `forge status --json` com `suggested_next_command`.

**A3 · ENV-1 — leak de env agêntico → adapter errado → hang [A].** `detect_host` keys puramente em `CLAUDECODE`/`OPENCODE_*` herdado; sem scrub em produção. **E se** forge roda como subprocess de dentro de uma sessão CC (teste/hook/tool)? Herda `CLAUDECODE=1` → emite marker + exit 2 esperando um harness que não dirige → hang. **Fix:** pin `host:` em config pra contextos não-interativos + scrub no boundary.

**A4 · REPLAY-1/2 — mutações antes do confirm [A].** `init` re-executa o pipeline inteiro a cada re-invocação (`init.py:937` "resume = restart"); `reconfigure` faz move irreversível de `.bak` antes do apply-confirm (`reconfigure.py:550-553`) e o cancel não restaura. **E se** o usuário escolhe "remover card X" e depois cancela? `cards/X/` some → drift com a config → `forge verify` hard-fail. **Fix:** deferir mutações pós-confirm / hoist asks pra frente.

**A5 · NO-ONBOARDING — forge não instala nada que ensine o LLM que ele existe [A].** Sem CLAUDE.md de consumidor, sem skill, sem guia. forge vira scaffolding invisível. (Mesma raiz de DRIVER-001; resolução compartilhada: a skill + um pointer no SessionStart.)

**A6 · DUP-FINGERPRINT — sha256 computado à mão pelo LLM em 3 lugares [A].** `retrospective-agent.md:213-232` + `qa-synthesizer.md:67-68` + `evals.template.json`. **LLMs não produzem sha256 confiável — alucinam hex.** Drift de normalização → dedup quebra. **Fix:** helper determinístico no engine; agentes referenciam, não re-derivam.

**A7 · DUP-DUAL-BDD — `bdd.md` e `bdd.json` autorados 2× pelo LLM [A].** "Dois encodings" do mesmo Gherkin, ambos required. Drift quase-certo. **Fix:** `bdd.json` canônico, gerar `bdd.md` deterministicamente.

### 3.3 MÉDIO

**M1 · Latência de hooks no loop [A].** `SubagentStop` roda validators `subprocess.run(timeout=30)` síncronos após cada subagente (`ingest.py:347-381`); `PostToolUse` roda SQLite por-edit (`graph_update_file`). **Fix:** timeout menor / async; debounce/batch do graph.

**M2 · SESSION-START-PATH [A].** Hooks chamam `forge` bare; se o env do hook não tem `~/.local/bin` no PATH, toda a camada morre silenciosa. **Fix:** assar path absoluto.

**M3 · FLAG-CONTRACT-VIOLATION + HELP-COUNT-DRIFT [A+B].** "Zero flags" contradito por `graph --json`/`--no-auto-build`, `verify --feature-slug`, `upgrade --force`, `ingest --key val`; `--help` só funciona em 3 de 14. `cli.py:3` "12 canonical" + `reconfigure.py:6` "Decision 9 (12 commands)" stale (são 14). **Fix:** carve-out documentado + listar no manifesto; sync dos docstrings.

**M4 · SKEL-DUP + BLOAT-CONDUCTOR [A].** 7 agentes de planejamento repetem o mesmo esqueleto (Voice/Discipline/Output/"Never invent"); `planning-conductor.md` = 1168 linhas/50KB com sub-prompts de outro agente embutidos. Os qa-auditors já provam o conserto (herdam overlay). **Fix:** extrair `forge-subagent-base`.

**M5 · SCHEMA-1 + SCHEMA-LEAK [A+B].** Guard de schema-version só roda em `read_response`, não em `read_pending`/`detect_race`; e `SchemaVersionMismatchError` (RuntimeError) não está na tupla de except do `cli.py:363-366` → vaza traceback. **Fix:** aplicar guard nas duas direções + adicionar a exception ao catch.

**M6 · BROWNFIELD-DEADCODE [B].** `_detect_brownfield` (`init.py:203-228`) é dead-code (só testes chamam); o handoff anuncia como em-uso → mismatch doc↔código. **Fix:** remover ou wirar; corrigir handoff.

**M7 · DETECT-1 + STALE-1 [A].** `detect_codex`/`detect_cursor` são dead-code em `detect_host`; pending de processo crashado trava a raia 10 min (PID gravado mas sem `os.kill(pid,0)`). **Fix:** wirar/deletar; probe de liveness.

**M8 · JSON-GUIDEKEY + ENUM-FREETEXT [A].** `qa-finding/report.template.json` sem `_template_rules`; spec YAMLs com free-text (`{{server_only_local_only_both_none}}`) onde comment-enums seriam determinísticos. **Fix:** padronizar `_template_rules` + comment-enums validáveis.

**M9 · DOCTOR-MASKS-FAILURE + HELP-DOC-PATH-FRAGILE [A].** `doctor` retorna 0 com warnings (strictness só via env não-documentada); `cli.py:250` aponta pra `~/Documents/...` que não resolve em XDG. **Fix:** `doctor --json` + path via `forge_home()`.

### 3.4 BAIXO

- **STDOUT-1 [A]** — UI cinematográfica compartilha stdout com o marker; rotear UI→stderr.
- **L-1 [A]** — docstrings citam anchor legado `.claude/state/` + helpers nativos mortos; limpar.
- **L2-RMW [B]** — read-modify-write sem lock (baixa prob., single-writer via evolve).
- **TS-IMPORT [B]** — named-import não resolve definição (by-design documentado).
- **REPLAY-3 [A]** — appends em `implement` mid-flow; auditar ordering vs ask.
- **PORT-CC-TOOLS [A]** — frontmatter de conductor nomeia tools CC-específicas.
- **IMPLEMENT-HANDOFF [B]** — `forge implement` não gera código (BY-DESIGN; só clarificar docstring/naming).
- **MCP-DORMANT [B]** — providers `NotImplementedError` dormentes (non-goal explícito; nota dead-code).
- **CI-PLACEHOLDER [A]** — `ci-pr-ingest.yml` com `<TBD-user>`.

---

## 4. O que já está sólido (balanço autocrítico)

- **Escrita de state é atômica** (tempfile→fsync→replace→fsync-dir, 0o600) — refuta o "sem atomicidade" da Auditoria B.
- **Cancelamento existe** (Ctrl+C / response cancelled → exit 130) — refuta "sem cancel".
- **Concorrência SQLite tratada** (busy_timeout + BEGIN IMMEDIATE) — refuta "WAL race".
- **Memory defensivo** (MemoryError tipado + isinstance guard; L3 lazy; cap 0.5MB) — refuta "crash/OOM".
- **`forge graph --json`** é o modelo LLM-first a generalizar (stdout só JSON, erros→stderr, aliases tolerantes).
- **Protocolo intent bem especificado** (`docs/schemas/intent-protocol.md`) — o gap é a contraparte (driver), não o protocolo.
- **Hooks fail-open + brownfield-safe merge** — fundamentos de segurança agêntica certos.
- **`renderer.write` é chokepoint único** — a maior parte do conserto de token é mudança de um arquivo.

---

## 5. Catálogo de oportunidades (skill / hook / agent / template / loop)

| Tipo | Oportunidade | Endereça | Prioridade |
|---|---|---|---|
| **Skill** | `feature-forge` driver SKILL.md (ensina o intent loop + re-invocação + exit codes), instalada por `forge init` | DRIVER-001, NO-ONBOARDING | **P0** |
| **Doc/Skill** | `AGENTS.md` opencode (mesmo loop, mecanismo opencode) | DRIVER-003 | P0 |
| **Skill** | `forge-subagent-base` (persona/disciplina/output compartilhados dos 7 agentes) | SKEL-DUP, BLOAT-CONDUCTOR | P1 |
| **Loop/Protocol** | `McpAdapter` com elicitation nativa (5º adapter) — dissolve o teaching burden | DRIVER-001 (estratégico) | P1 |
| **CLI** | `forge --help --json` (manifesto) + `forge status --json` (router) + `FORGE_OUTPUT=json` + `--json` nos read-commands | TOKEN-BLIND, NO-MANIFEST | **P0** |
| **Hook** | Corrigir DEAD-VERIFY + teste real; debounce graph; timeout/async no SubagentStop; path absoluto do forge; SessionStart pointer | DEAD-VERIFY, M1, M2, NO-ONBOARDING | **P0/P1** |
| **Engine** | Des-colidir exit codes; concorrência (PID tmp + flock); scrub de env + pin host; replay-safety | EXIT-2-COLLISION, CONC-1, ENV-1, REPLAY | **P0/P1** |
| **Template** | `bdd.json` canônico; `_template_rules`; comment-enums; fingerprint helper determinístico | DUP-DUAL-BDD, DUP-FINGERPRINT, M8 | P1 |

---

## 6. Roadmap priorizado (base do planejamento)

### P0 — gate do piloto
1. **`feature-forge` SKILL.md driver** + instalação por `forge init` (+ `AGENTS.md` opencode). *Sem isso o produto não funciona.*
2. **DEAD-VERIFY** — path do hook + teste real.
3. **EXIT-2-COLLISION** — reservar exit 2 pra pause; colapsar a escada.
4. **CONC-1** — tempfile por-PID (mínimo viável) + flock.
5. **TOKEN-BLIND + `--json`/`FORGE_OUTPUT`** — renderer host-aware + `--json` nos read-commands + `forge --help --json` manifesto + `forge status` router.

### P1 — robustez e adoção
6. ENV-1 (scrub + pin host); REPLAY-1/2 (deferir mutações); NO-ONBOARDING (SessionStart pointer).
7. Hooks: debounce graph, timeout/async subagent-validate, path absoluto.
8. Templates: bdd single-source, `_template_rules`, comment-enums; fingerprint helper.
9. `forge-subagent-base` (extrair esqueleto); BLOAT-CONDUCTOR.
10. **McpAdapter (estratégico)** — caminho que dissolve o teaching burden.

### P2 — polish e dívida
11. SCHEMA-1+LEAK, DETECT-1, STALE-1, M6 brownfield-deadcode, M8, M9, STDOUT-1, L-1, L2-RMW, IMPLEMENT-HANDOFF docstring, MCP-dormant note, PORT-CC-TOOLS.

---

## Apêndice A — Veredito claim-by-claim sobre a Auditoria B

**Refutados (FALSO/hallucination):** wait_for_intent-bloqueia (§4.4/§5.2), resolve()-sem-timeout (§4.1), opencode_fallback.py (§4.6), ECHO_LLM_RESPONSE (§4.3), cache-em-memória-perdido (§4.3), detect-miss→None→crash (§3.1), write_pending-não-atômico (§4.4), sem-cancelamento (§3.14), Kotlin-ReDoS (§8.1.2), Kotlin-where-clause (§8.1.3), Q12/Q14-vazias (§8.1.4), WAL-race (§8.1.7), L1-mirror-race (§8.2.2), L1-malformed-stacktrace (§3.2), L3-OOM (§3.13/§8.2.4), cards-loader-fallthrough (§8.3.1), composer-stubs (§8.6), implement-docstring-flags (§7.3), handoff-1761 (§7.5, auto-referência), ~30 "Sem X" (§5.2, wishlist).

**Parciais (sintoma real, rationale/severidade errados):** corrupted-intent→loop (§3.4, na verdade exit 1 + nugget SCHEMA-LEAK), .tmp-collision-paths-diferentes (§3.3/§8.5, colisão real é mesmo-path = CONC-1), L2-RMW (§8.2.3, baixa prob.), _detect_brownfield-3→2 (§7.7, dead-code real mas framing errado), MCP-CRÍTICO (§3.8/§8.4, dormant non-goal = LOW), implement-stub (§6.2, by-design).

**Reais & valiosos (incorporados em §3):** concorrência `.tmp`/TOCTOU (=CONC-1), Decision-10-flags (=M3), cli.py/reconfigure.py "12" (=M3), SCHEMA-LEAK (=M5), BROWNFIELD-DEADCODE (=M6), TS-import-nonresolution (=BAIXO).

**Contagem:** das ~22 alegações principais da Auditoria B, ~13 FALSAS/hallucination, ~6 PARCIAIS (mis-framadas), ~3 reais net-new (todas LOW/MEDIUM) + ~3 duplicatas de findings da Auditoria A. **Zero dos 4 "CRÍTICOS" da Auditoria B sobrevive como crítico real** (MCP=dormant, opencode-2nd-class=rationale-errado/=DRIVER-003, Decision-10=médio, implement-stub=by-design).

## Apêndice B — Índice por origem

- **Só Auditoria A (Claude):** DRIVER-001, DEAD-VERIFY, EXIT-2-COLLISION, TOKEN-BLIND, NO-MANIFEST, NO-WORKFLOW-ROUTER, ENV-1, REPLAY-1/2/3, NO-ONBOARDING, DUP-FINGERPRINT, DUP-DUAL-BDD, SKEL-DUP, BLOAT-CONDUCTOR, DETECT-1, STALE-1, SCHEMA-1, STDOUT-1, L-1, M1/M2/M8/M9, PORT-CC-TOOLS, CI-PLACEHOLDER.
- **Só Auditoria B (opencode), verificado-real:** SCHEMA-LEAK, BROWNFIELD-DEADCODE, L2-RMW, TS-IMPORT, MCP-DORMANT (note), IMPLEMENT-HANDOFF (note).
- **Ambos (convergência):** CONC-1, FLAG-CONTRACT-VIOLATION, HELP-COUNT-DRIFT.

> **Conclusão (mentor calmo):** as duas auditorias juntas contam uma história clara. A engenharia do PR #17 é boa — escrita atômica, cancelamento, concorrência SQLite, memory defensivo: tudo certo, e a Auditoria B errou ao alarmar sobre eles. O que falta é a *outra metade* do protocolo (o driver do host) e a *legibilidade por máquina* (manifesto, `--json`, exit-codes limpos) — e é exatamente a ausência dessa legibilidade que fez um LLM-auditor alucinar 75% dos seus próprios achados. Resolva o driver (uma skill, dias), conserte os bugs de path/exit-code/concorrência, e torne o output host-aware: o forge passa de "arquitetura elegante e inerte" pra "ferramenta que um LLM dirige de olhos fechados". Próximo passo: planejamento da evolução a partir do roadmap §6.
