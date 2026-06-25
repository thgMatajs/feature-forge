# Integração mem ↔ feature-forge — design spec

> **Spec, não plano de execução.** Aterra decisões de arquitetura já
> tomadas pelo autor em algo acionável. O plano de implementação
> (writing-plans → tasks) é o passo seguinte.
> **Voz:** mentor calmo. **Status:** design aprovado (revisado pelo autor),
> pré-implementação. As 5 questões abertas da v1 viraram decisões (ver
> §Decisões resolvidas) e o rollout foi reorganizado em 3 fases (ver
> §Fases de rollout).
> **Data:** 2026-06-25.

---

## Contexto e objetivo

O `feature-forge` mantém hoje sua própria camada de memória-de-conhecimento
em `engine/memory/` — três níveis (L1 per-feature, L2 project-wide, L3 proxy
read-only sobre a auto-memory do Claude Code) mais um `distiller` de
proposals. É código load-bearing, testado, e funcional. Mas é **memória
caseira**: schema próprio, paths próprios, sem busca ranqueada, sem
compartilhamento multi-dev curado, e sem o padrão de mercado de
*context-on-demand*.

Em paralelo, o autor construiu o `mem` — uma CLI de arquivo único,
stdlib-pura, que resolve exatamente o problema que a memória do forge
tateia: **conhecimento sempre-on infla o system prompt** (a auditoria do
próprio `mem` mediu ~43k tokens sempre-on, >20% de uma janela de 200k,
gastos em toda interação). A resposta do `mem` é progressive disclosure:
um índice mínimo sempre-on (~250 tokens) + recuperação sob demanda via
`find`/`get`, com fonte versionada em git (`*.jsonl`) e índice derivado
descartável (`mem.db`, FTS5/BM25).

**Objetivo deste spec:** descrever como o `mem` **substitui** a camada de
memória-de-conhecimento do forge, preservando o que é genuinamente do forge
(o code graph, o lifecycle, cards, validators, conductor), com fronteira
limpa de *vendor + shell* — o mesmo padrão que o forge já usa pra chamar
ferramentas nativas (detekt/gradle via `dispatch_native_tool`). Nada de
`import mem`.

### Por que substituir, não coexistir

Duas camadas de memória paralelas seria exatamente o anti-padrão que o
Mandamento #3 (reuso) combate, em escala arquitetural. O `mem` é mais
maduro no eixo de memória-de-conhecimento (busca ranqueada, supersede,
captura via inbox, decay, hooks de injeção). O forge é mais maduro no
eixo de estrutura-de-código (graph.db, blast-radius, reuse-intelligence).
A divisão natural é por **eixo de responsabilidade**, não por duplicação.

---

## Decisões resolvidas

As 5 questões abertas da v1 deste spec viraram decisões na revisão do autor.
Resumo (detalhe nas seções referenciadas):

| # | Questão (v1) | Decisão | Onde |
|---|---|---|---|
| 1 | Onde cortar o L1 | A state-machine de lifecycle NÃO é memória — **move pra `.claude/forge/state/`** (fora de `.claude/memory/`). Só o conhecimento distilável vai pro mem. `.claude/memory/` fica 100% do mem. | §Divisão (nota), §Reconciliação (call-sites) |
| 2 | Tamanho da fronteira | Helper enxuto novo `engine/integrations/mem.py:mem_call` que reusa a espinha de `dispatch_native_tool`; não forçar o encaixe inteiro. | §Fronteira vendor+shell |
| 3 | Distribuição do mem | **Embarcar o asset pinado no repo forge** (`engine/assets/mem/mem`); init copia pra `.claude/bin/mem`. Sem download via `gh`. Migração L2→mem = migrador forge-side que emite `mem add` (lossy 11→5; campos extras preservados no corpo/tags). Extensão de schema do mem = follow-on. | §Fronteira, §Migração |
| 4 | Bug multi-passo do `forge memory` | NÃO assumir cura. TDD obrigatório: reproduzir BUG-M1 vermelho ANTES, confirmar que o wrapper o elimina. Os 11 callsites de checkpoint-resume (DRIFT-1) somem ao virar wrapper stateless — mas isso precisa de teste, não de fé. | §Superfície de comando |
| 5 | `forge evolve` vs `mem evolve` | Ortogonais. forge evolve = reuse-intelligence/cards/templates sobre código; mem evolve = ciclo-de-vida do acervo. Ponte ÚNICA: proposals `promote-to-l2` do forge → `mem inbox add`. | §Superfície de comando |

> Estas decisões são premissas das §Fases de rollout abaixo — o plano de
> implementação as executa, não as re-litiga.

---

## Fases de rollout

A integração rola em **3 fases**. As Fases 0 e 1 são escopo de produto
(implementação real); a Fase 2 é só referenciada.

### Fase 0 — dogfood (o forge usa o mem em si mesmo)

**O quê:** o PRÓPRIO repo `feature-forge` adota o `mem` pro conhecimento
dele. As fontes de conhecimento do forge viram notas mem; os docs
operacionais sempre-on são enxugados pra Tier-0 + índice mem.

**Por que primeiro:** dogfood real. Se o forge não consegue operar sua
própria manutenção com o conhecimento no mem, não tem por que impor isso a
consumidores. Valida o fluxo de redução de rules (Fase 1) no terreno mais
exigente que existe — o repo cujos rules ENFORÇAM o Mandamento 0.

**Mapeamento Tier-0 (fica injetado, lean) vs. → mem (Tier-1, sob demanda):**

| Fonte do forge | Destino |
|---|---|
| `CLAUDE.md` — Mandamento 0 + os 6 mandamentos (enunciado) + workflow-por-verbo essencial | **Tier-0** (enxugado pra o invariante; o resto vira ponteiro pro mem) |
| `.claude/rules/orchestrator-persona.md`, `subagent-workflow.md` (detalhe de despacho) | → mem (`reference`); Tier-0 mantém o ponteiro |
| `.claude/rules/decisions.md`, `disciplines.md`, `reuse.md`, `scope.md`, `testing.md`, `doc-sync.md`, `superpowers.md`, `plan-auditor.md` | → mem (`reference`/`feedback`) — recuperados via `find` quando o trabalho toca o tema |
| `docs/design/01-decisions.md` (decisões) | → mem (`decision`, uma nota por decisão); o arquivo CANÔNICO **permanece** (é fonte de verdade load-bearing + o hard-block do Mandamento #1 depende dele) — o mem é índice consultável, não substituto do arquivo |
| `docs/design/07-discipline.md` (disciplinas) | → mem (`reference`); arquivo canônico permanece |
| `docs/design/04-pending.md` (gaps) | → mem (`reference`); arquivo permanece |
| `docs/design/08-session-handoff.md` (estado/handoff) | → `mem session` (handoff curado) + o arquivo permanece pro SessionStart |
| Learnings da MEMORY.md auto-memory do autor (feedback recorrentes) | → mem (`feedback`) |

> **Distinção importante:** "→ mem" NÃO significa deletar o arquivo
> canônico. Os docs `docs/design/*` são fonte de verdade load-bearing e
> alguns têm enforcement acoplado (o hard-block de `01-decisions.md`, o
> SessionStart de `08-session-handoff.md`). O que muda é: eles deixam de ser
> **injetados sempre via CLAUDE.md/rules** e passam a ser **consultáveis via
> mem** quando relevantes. O CLAUDE.md + `.claude/rules/` é que enxugam.

**ALTO RISCO — por que esta fase é delicada:** mexe nos docs operacionais
load-bearing do PRÓPRIO forge. `CLAUDE.md` e `.claude/rules/**` estão na
whitelist load-bearing do `scope.md`. O SessionStart hook
(`session-start-orientation.sh`) e o enforcement do Mandamento 0 dependem
desses arquivos estarem presentes e legíveis. Enxugar errado = o
orquestrador-mantenedor perde os gates que o seguram.

**GATE DE ACEITE da Fase 0 (explícito, validar na branch ANTES de merge):**

1. Uma **sessão de manutenção fresca** (SessionStart limpo, sem contexto
   prévio) DEVE continuar funcionando: o Mandamento 0 é enforçado (o
   orquestrador despacha em vez de editar direto), e as rules são acessíveis
   via `mem find` quando o trabalho as exige.
2. Os 5 smoke checks do `SMOKE-CHECKLIST.md` que dependem de rules/hooks
   continuam passando (especialmente #5 — dispatch behavior do Mandamento 0).
3. O hard-block do Mandamento #1 (`pre-commit-feature-forge.sh`) continua
   disparando em edit de `01-decisions.md` sem ceremony (o arquivo canônico
   não foi removido).
4. **Tudo proposto, nunca silencioso:** a divisão Tier-0/Tier-1 é
   apresentada ao humano (3-caminhos) antes de qualquer `mem add` + enxugue;
   o `.claude/rules/` humano nunca é trucidado sem aprovação.

Falhou qualquer gate → a Fase 0 não merge; ajusta a classificação e
re-valida. Pré-produção permite clean break, mas o forge precisa continuar
se mantendo.

### Fase 1 — produto (todos os fluxos dos consumidores)

**O quê:** o `mem` substitui a memória-de-conhecimento pros projetos
**consumidores**. TODOS os fluxos do forge re-roteiam pro mem.

**Fluxos do forge que re-roteiam (enumerados):**

- **`init`** — vendoriza o mem (asset embutido → `.claude/bin/mem`) + roda o
  scaffold do mem + **executa a redução de rules** (fluxo abaixo).
- **`plan`** — consulta convenções/decisões via `mem find` (além do graph
  pra estrutura); escreve lifecycle em `.claude/forge/state/`.
- **`implement`** — append history/status em `.claude/forge/state/`;
  consulta `mem find` por gotchas.
- **`verify`** — verify-log em `.claude/forge/state/`.
- **`qa`** — consulta `mem find` por episodes/decisões relevantes ao
  red-team; nenhum validator chama mem (determinismo preservado).
- **`status`** — lista features do lifecycle (novo path); counts de
  conhecimento via `mem stats` se quiser.
- **`evolve`** — proposals de conhecimento (`promote-to-l2`) → `mem inbox
  add`; reuse-estrutural fica no distiller do forge.
- **`doctor`** — categoria nova: `mem doctor --json` + check de drift do pin.
- **Conductor / sub-agents:** `memory-distiller`, `feature-prd-agent`,
  `planning-conductor`, `contract-planner-agent`, `retrospective-agent`
  re-roteiam leitura→`mem find`, escrita→`mem inbox add` (ver §Re-roteamento).

**Migração:** brownfield consumidor migra via o migrador forge-side
(§Migração). Greenfield nasce no mem.

**O que NÃO vai pro mem (fica no forge):** `graph.db` (estrutura de código)
e a state-machine de lifecycle (`.claude/forge/state/`).

#### Fluxo do `init` pós-mem (com redução de rules)

Este é o fix do gap de assimilação de convenção do piloto:

1. **Vendoriza o mem** (asset embutido → `.claude/bin/mem`, chmod 755) +
   **`mem init`** (scaffold `.claude/memory/`, gitignore `mem.db*`, índice
   no `AGENTS.md`).
2. **LÊ os `.claude/rules/*` + `CLAUDE.md` existentes** do projeto
   consumidor (se houver). Este passo é o que falta hoje — convenção humana
   nunca era assimilada.
3. **Host/conductor CLASSIFICA cada fragmento** em **Tier-0** (invariante,
   fica injetado lean) vs. **Tier-1** (referência → vira nota mem).
4. **PROPÕE a divisão ao humano** (G1/G2: NUNCA trucida o `.claude/rules/`
   do humano em silêncio). Apresentação 3-caminhos: aceitar / ajustar /
   pular.
5. **Aprovado:** `mem add` dos fragmentos Tier-1 + **enxuga o núcleo
   injetado** + **escreve o índice de ~30 linhas** (o `RULE_INDEX` que
   ensina o agente a consultar a memória).

Nenhuma rule humana some sem aprovação; o que era sempre-on vira
sob-demanda só com o veredito do humano.

### Fase 2 — curadoria (só referência neste spec)

**Enriquecimento** de rules ao longo do tempo, distinto da redução one-time
do init:

- **web/init-enrich** — buscar convenções de fontes externas no init.
- **evolve→rules** — `forge evolve`/`mem evolve` promovendo aprendizados
  comprovados a rules.
- **comando `rules-update`** — curadoria ativa do acervo de rules.
- **version-awareness** — rules cientes de versão de stack/lib.

Este spec **habilita** a direção (a substituição é o pré-requisito) mas NÃO
a detalha. Ver §Fora de escopo.

---

## O que é o mem (grounded no código)

Fonte lida: `/Users/thg.inchurch/Documents/mem/README.md` +
`/Users/thg.inchurch/Documents/mem/mem` (script único, 2363 linhas,
`__version__ = "0.8.1"`, schema v4).

### Arquitetura

| Camada | Onde vive | Versionado? |
|---|---|---|
| Ferramenta (`mem`, script único) | upstream `inRadar/mem`; vendorizado em `<repo>/.claude/bin/mem` | sim (cópia commitada, pinada) |
| Dado fonte (`*.jsonl`, 1 por autor) | `<repo>/.claude/memory/<autor>.jsonl` | sim — fonte da verdade |
| Índice derivado (`mem.db`) | `<repo>/.claude/memory/mem.db` | **não** (gitignored, reconstruível) |
| Estado local (reforço, inbox, checkpoint) | dentro de `mem.db` | **não** (local-only) |

Princípio: o acervo cresce; a injeção não. Fonte = JSONL append-only
commitado (durabilidade + review em PR). Índice = SQLite FTS5/BM25,
`mem rebuild` o reconstrói byte-a-byte idêntico a partir do JSONL.

### Storage layout

- `MEMORY_SUBDIR = (".claude", "memory")` (`mem`:69)
- `author_jsonl(root, author)` → `.claude/memory/<autor-sanitizado>.jsonl`
  (`mem`:109-110); autor derivado de `git config user.email` sanitizado
  (`mem`:95-106) — ex.: `thiago.pacheco_at_inchurch.com.br.jsonl`.
- `db_path(root)` → `.claude/memory/mem.db` (`mem`:91-92), gitignored via
  linha `.claude/memory/mem.db*` que o scaffold adiciona (`mem`:1849).
- `triggers_path(root)` → `.claude/memory/triggers.jsonl` (`mem`:172-173),
  **commitado** (event-sourced, compartilhado pelo time).
- `find_project_root` sobe procurando `.git`/`.claude` (`mem`:79-84).

### Schema de uma nota (memory)

`@dataclass(frozen=True) Memory` (`mem`:118-143) e tabela SQLite derivada
(`mem`:270-275). Campos:

| Campo | Tipo | Significado |
|---|---|---|
| `id` | ULID (26 chars, time-ordered, merge-safe) | PK; gerado via stdlib (`mem`:47-58) |
| `type` | enum | `feedback`\|`reference`\|`episode`\|`decision`\|`session` (`VALID_TYPES`, `mem`:114) |
| `title` | str (1 linha) | o que o `find` mostra |
| `body` | str (markdown) | o fato atômico |
| `importance` | int 1–5 (default 3) | peso no score |
| `status` | enum | `active`\|`archived`\|`superseded` (`mem`:115) |
| `superseded_by` | str\|null | id da nota que substitui |
| `author` | str | proveniência (git email sanitizado) |
| `source` | str\|null | origem (PR/ticket/`inbox:<id>`/`import:<file>`) |
| `git_meta` | str(JSON)\|null | sessões: branch/head/commits/files (`mem`:1506-1516) |
| `tags` | tuple[str] | tags (sugeridas do título se omitidas) |
| `created_at` / `updated_at` | ISO-8601 Z | timestamps |

JSONL é **event-sourced**: um `id` pode ter vários snapshots (criação →
supersede/archive); estado corrente = último snapshot por `id`
(`current_memories`, `mem`:236-241). `to_jsonl` serializa com
`sort_keys=True` pra determinismo (`mem`:134-137).

**Tipos especiais:**
- `session` fica **fora** do `find` padrão e do `brief` — consumido só com
  `--type session` (`mem`:611, 634); decay agressivo.
- `INBOX_TYPES` exclui `session` (`mem`:926) — inbox só aceita
  feedback/reference/episode/decision.

### Score de recuperação (`mem`:400-416)

```
score = bm25_norm
      × (importance / 5)
      × exp(-lambda × dias_desde_acesso)        # decay (Ebbinghaus)
      × (1 + 0.2 × ln(1 + recall_count))        # reforço por uso (local)
      × (1 + 0.15 × tag_overlap)
lambda = 0.16 × (1 − importance × 0.8 / 5)      # importantes decaem devagar
```

Reforço conta só `mem get` explícito, nunca injeção automática (anti-viés,
`mem`:821 comment). `find` nunca devolve o corpo (≤150 tokens, só
`id·score·type·title·[author]`); `get` devolve corpo + registra acesso.

### Comandos relevantes pra integração

| Comando | O que faz | Ref |
|---|---|---|
| `init [--vendor]` | scaffold: cria `memory_dir`, adiciona gitignore, upsert bloco rule no `AGENTS.md`, instala skills (`mem-resume`/`-consolidate`/`-report`); `--vendor` também copia o script | `cmd_init` `mem`:1856-1862 / `_scaffold` 1847-1853 |
| `vendor` | `_vendor_into` (copia `Path(__file__)` → `.claude/bin/mem`, chmod 755) + `_scaffold` | `mem`:1865-1869 / 1839-1844 |
| `update [--check] [--ref TAG]` | self-update da cópia vendorizada da release tag canônica; **recusa clobber de cópia modificada à mão** (R13); nova versão roda na próxima invocação | `cmd_update` `mem`:1426-1456 |
| `add --type T -t TITLE [-i N] [--tags] [--source] BODY` | grava nota (filtro de segredos → near-dup check → append JSONL + index) | `cmd_add` `mem`:489-518 |
| `find QUERY [--type T] [-k N] [--since DUR] [--all]` | busca ranqueada, títulos only | `cmd_find` `mem`:596-661 |
| `get ID` | corpo completo + registra acesso; exit 2 se ausente | `cmd_get` `mem`:686-710 |
| `session SUMMARY [-i N]` | resumo de sessão com `git_meta` automático | `cmd_session` `mem`:1519-1553 |
| `supersede NEW_ID OLD_ID` | marca OLD superseded_by NEW (preserva histórico); só own-author em F0 | `cmd_supersede` `mem`:748-773 |
| `evolve [--apply] [--min-score] [--max-age-days]` | curadoria: propõe ARCHIVE + DUP clusters + INBOX pendente; `--apply` arquiva candidatos do próprio autor | `cmd_evolve` `mem`:876-922 |
| `inbox add\|list\|promote\|reject` | fila local de candidatos de captura (anti-envenenamento, por-item) | `cmd_inbox` `mem`:1038-1047 |
| `compact` | reescreve o JSONL próprio descartando `archived` (único cmd que reescreve JSONL, R10) | `cmd_compact` `mem`:1366-1403 |
| `rebuild` | apaga e recria `mem.db` do JSONL (determinístico) | `cmd_rebuild` `mem`:393-397 |
| `brief [--budget N]` | índice de alto valor (top feedback/decision por score, default 800 tokens); não registra acesso | `cmd_brief` `mem`:2056-2069 |
| `doctor` | diagnose install/schema/version-drift | `cmd_doctor` `mem`:1459-1493 |
| `import PATH` | ingere markdown nativo (file ou dir); **aditivo/one-shot** (re-rodar duplica) | `cmd_import` `mem`:1948-1973 |
| `stats` | counts + vitality (live/stale) + inbox | `cmd_stats` `mem`:713-745 |

### Como `import` funciona (load-bearing pra migração)

`cmd_import` (`mem`:1948-1973): aceita arquivo ou diretório (glob `*.md`),
pula `MEMORY.MD`, parseia frontmatter YAML, mapeia `type` via
`_NATIVE_TYPE_MAP` (`feedback`→`feedback`, resto→`reference`,
`mem`:1926-1931), aplica `scan_secrets` (pula se segredo), cria `Memory`
com `source="import:<file>"`, `importance=3`, append + rebuild final.
**Não há dedup contra acervo existente** — re-rodar duplica (warning
explícito no README §`import`).

**Consequência pra nós:** o forge L1/L2 NÃO são markdown frontmatter — são
YAML/JSON estruturados. `mem import` cru não os entende. Ver §Migração.

### Como `vendor`/`update` funcionam (load-bearing pra fronteira)

- `_vendor_into(root)` (`mem`:1839-1844): `shutil.copyfile` do próprio
  script pra `.claude/bin/mem` + chmod 755. Idempotente.
- `cmd_update` (`mem`:1426-1456): resolve tag (`--ref` ou
  `_latest_release_tag` via `gh api`), valida que a cópia atual não foi
  modificada à mão (sha256 vs release `v<version>`), baixa o script da tag,
  escreve atômico (tmp → `os.replace`). **Pin de versão = a tag baixada.**
  O `__version__` embutido no script é a fonte do pin efetivo.

---

## Arquitetura alvo

```
┌─────────────────────────────────────────────────────────────────┐
│                     feature-forge (orquestrador)                  │
│                                                                   │
│   lifecycle  ·  cards  ·  validators  ·  conductor  ·  presets    │
│                                                                   │
│   ┌───────────────────────────┐   ┌───────────────────────────┐  │
│   │  graph.db (FICA no forge)  │   │  forge memory (wrapper)    │  │
│   │  estrutura de código:      │   │  → shell out p/ mem        │  │
│   │  símbolos/imports/deps     │   └──────────────┬────────────┘  │
│   │  blast-radius / reuse-Q    │                  │ subprocess     │
│   └───────────────────────────┘                  │ (vendor+shell) │
└──────────────────────────────────────────────────┼───────────────┘
                                                    │
                                  ┌─────────────────▼─────────────────┐
                                  │   .claude/bin/mem (vendorizado)    │
                                  │   substrato de memória-de-          │
                                  │   conhecimento                      │
                                  │                                     │
                                  │   .claude/memory/<autor>.jsonl      │
                                  │   .claude/memory/mem.db (derivado)  │
                                  │   .claude/memory/triggers.jsonl     │
                                  └─────────────────────────────────────┘
```

- **forge = orquestrador + dono do code-graph.** Continua sendo a porta de
  entrada (`forge <cmd>`), o lifecycle, os gates, a inteligência de reuso
  estrutural.
- **mem = substrato de memória-de-conhecimento.** Dono único de learnings,
  decisões, bugs (episodes), sessões, e (milestone seguinte) convenções
  curadas.
- **Fronteira = shell.** O forge invoca `.claude/bin/mem` por subprocess,
  exatamente como `dispatch_native_tool` invoca detekt/gradle. Nunca
  `import mem`. O `mem` permanece um arquivo opaco, pinado por versão.

---

## Divisão de responsabilidade

| Capability | mem owns | forge owns |
|---|---|---|
| Learnings / feedback (como trabalhar) | ✅ `add --type feedback` | — |
| Decisões com rationale | ✅ `add --type decision` | — (exceto Decisões locked do *próprio* forge em `docs/design/01-decisions.md`, que são do projeto forge, não memória de consumidor) |
| Bugs resolvidos (root cause não-óbvio) | ✅ `add --type episode` | — |
| Resumos de sessão / handoff | ✅ `session` + checkpoint | — |
| Convenções/rules curadas (sob-demanda) | ✅ notas mem (two-tier, ver §Rules) | — |
| Busca ranqueada da memória | ✅ `find`/`get` (BM25 + score) | — |
| Captura curada (inbox, anti-envenenamento) | ✅ `inbox` + `evolve` | — |
| Injeção context-on-demand (brief/fire) | ✅ hooks do mem (opt-in) | — |
| **Estrutura de código** (símbolos, imports, deps) | — | ✅ `graph.db` (Decisão 20) |
| Blast-radius, orphans, DI-deps (Q2/Q3/Q8) | — | ✅ `forge graph` |
| Reuse-intelligence (Q11–Q17) | — | ✅ `engine/graph/reuse/` |
| Feature lifecycle state (status, phase-lock, history) | — | ✅ forge — move pra `.claude/forge/state/` (ver nota) |
| Cards / templates / presets / validators | — | ✅ forge |
| Conductor + sub-agents de planejamento | — | ✅ forge |

> **Nota sobre o corte do L1 (Decisão resolvida #1).** O L1 atual (`l1.py`)
> mistura DOIS conceitos: (a) **estado-de-lifecycle** (status.json,
> phase-lock, history.jsonl, verify-log, dispatch-log, blocking-deps,
> subtype, extends-feature) — isso é *mecânica de execução do forge*, NÃO
> memória-de-conhecimento; (b) **conhecimento destilável** (hypothesis,
> rationale-trace, elicitation) — candidato a virar nota mem na
> retrospectiva.
>
> **Decisão:** a parte (a) — a state-machine de lifecycle — NÃO é memória e
> **sai de `.claude/memory/` pra `.claude/forge/state/`** (o sub-namespace
> que o forge já usa pra estado operacional: `forge_state_dir`,
> `engine/utils/paths.py:285`; já abriga `forge-pending.json`,
> `cc-gate-bypass.jsonl`, `secrets-gate-bypass.jsonl`). A parte (b) vira
> nota mem na retrospectiva. **Resultado: `.claude/memory/` fica 100% do
> mem** — substituição limpa, sem coabitação de layouts. Os call-sites do
> corte estão na §Reconciliação.

---

## Fronteira vendor + shell

### Reuso do padrão `dispatch_native_tool`

O forge já tem o padrão canônico de fronteira-por-shell em
`validators/_gate_infra.py` (`dispatch_native_tool`). Assinatura confirmada:

```python
def dispatch_native_tool(
    *, language: str, files: list[str],
    cmd_builder: Callable[[str, list[str], Optional[str]], list[str]],
    project_root: Path, tool_bin: str,
    config_template: Optional[Path] = None,
    placeholders: Optional[dict[str, str]] = None,
    timeout: int = 60,
    benign_nonzero_codes: tuple[int, ...] = (),
) -> DispatchResult
```

`DispatchResult(language, tool_found, crashed, raw_stdout, error_message)`.
Pipeline: `check_tool_available` (shutil.which) → render config →
`cmd_builder` → `subprocess.run(timeout)` → cleanup.

**Decisão de reuso (Mandamento #3):** `dispatch_native_tool` é desenhado
pra *validators* (multi-file, config-template, código de retorno
benigno-vs-crash de linters). Chamar `mem` é mais simples (1 subcomando,
sem files, sem config-template, sai 0/1/2/3). Não force o encaixe.

**Decisão resolvida #2 (tamanho da fronteira):** extrair um helper menor —
`engine/integrations/mem.py` — que reusa a *espinha* do
`dispatch_native_tool` (locate binary, subprocess com timeout, captura
stdout/exit-code, fail-soft) mas com superfície enxuta; NÃO forçar o
encaixe inteiro do dispatcher de validators (multi-file/config-template não
se aplicam ao mem):

```python
def mem_call(project_root, subcmd_args, *, json=True, timeout=10) -> MemResult
# MemResult(found: bool, exit_code: int, stdout: str, stderr: str)
```

Toda invocação passa `--json` (o `mem` suporta `--json` em tudo,
`mem`:2223) → parsing determinístico. Exit codes do mem: `0` ok · `1` uso ·
`2` não-encontrado · `3` interno (README §6) — mapear pra `MemResult`.

### Localização do binário

Ordem de resolução (espelha o que o `mem` faz internamente, e o que os
hooks usam — `"$CLAUDE_PROJECT_DIR"/.claude/bin/mem`, `mem`:1880):

1. `<project_root>/.claude/bin/mem` (cópia vendorizada — caso normal)
2. `shutil.which("mem")` (dev clone no PATH — fallback)
3. Não encontrado → `MemResult(found=False)`. O wrapper degrada com
   mensagem 3-caminhos (instalar/vendorizar/skip), nunca crasha.

### Vendor no `forge init`

`engine/init.py` já scaffolda `.claude/memory/` (importa `memory_dir`,
`memory_l2_path`, init.py:94-95) e tem o padrão de instalar coisas em
projetos consumidores. O plano de implementação vai:

1. No fluxo de `forge init`, após criar `.claude/`, **vendorizar o mem**:
   copiar o `mem` pinado (asset embutido no repo forge — ver §Pin) pra
   `<project>/.claude/bin/mem` + chmod 755, e rodar o equivalente de
   `mem init` (scaffold do `.claude/memory/` no layout do mem).
2. **Decisão resolvida #3 (distribuição):** o forge **embarca uma cópia
   pinada do script `mem` como asset no próprio repo forge** — nada de
   download via `gh` no init. Embutir = clone-and-go, CI sem rede, alinhado
   com Decisão 15 (snapshot copy local) e Decisão 22 (zero runtime dep de
   skill). Local do asset: `engine/assets/mem/mem` (diretório versionado;
   `engine/assets/mem/VERSION` ou a constante `MEM_PINNED_VERSION` carrega o
   pin). O `forge init` copia esse asset pra `.claude/bin/mem`. O update vem
   por `forge upgrade` (abaixo).
3. Substituir o scaffold caseiro de `L1/L2` por scaffold do mem (o layout
   `.claude/memory/` muda — ver §Reconciliação).

### Update no `forge upgrade`

`engine/upgrade.py` opera sobre a instalação do forge (FORGE_HOME), não
sobre projetos, e hoje **não toca memória**. O update do mem pinado tem
duas faces:

- **Bump do pin no repo forge:** quando o forge adota uma versão mais nova
  do `mem`, atualiza o asset embutido (`engine/assets/mem/mem`) + a
  constante de versão pinada. Isso é manutenção do *próprio forge* (commit
  no repo forge), não runtime.
- **Propagação pro projeto consumidor (Decisão resolvida #4):** quando o
  usuário roda `forge upgrade` (ou `forge reconfigure`) num projeto, o forge
  **re-copia o asset embutido** pra `<project>/.claude/bin/mem` —
  offline-first, sem depender de `gh`/rede. NÃO chamar `mem update --ref`
  (que baixa da rede). Pra preservar a disciplina R13 do mem (não clobberar
  cópia modificada à mão), o forge faz um **sha-check próprio**: se a cópia
  vendorizada do projeto diverge do sha do asset pinado E não bate com
  nenhum pin conhecido anterior, avisa via 3-caminhos antes de sobrescrever
  (espelha R13 sem precisar de rede).

### Pin de versão

- Forge fixa UMA versão do `mem` por release do forge (ex.: `mem 0.8.1`).
- O pin vive numa constante (`engine/integrations/mem.py:MEM_PINNED_VERSION`)
  + o asset embutido (`engine/assets/mem/mem`) carrega esse `__version__`.
- `forge doctor` ganha um check de drift: compara `mem --version` da cópia
  vendorizada do projeto vs. o pin do forge → reporta `[drift]` se diferem
  (espelha o check `version` do próprio `mem doctor`, `mem`:1481-1486).

---

## Reconciliação do `.claude/memory/`

### Layout que o mem assume

```
.claude/memory/
├── <autor>.jsonl          # fonte commitada, 1 por autor (mem owns)
├── triggers.jsonl         # commitado, event-sourced (mem owns)
└── mem.db                 # derivado, GITIGNORED (.claude/memory/mem.db*)
```

### Layout atual do forge (a ser retirado)

```
.claude/memory/
├── L1/<feature-slug>/     # 8 arquivos por feature (status.json, history.jsonl,
│   └── ...                #   hypothesis.yaml, ambiguity-map.yaml, elicitation.yaml,
│                          #   rationale-trace.yaml, dispatch-log.jsonl, verify-log.jsonl)
├── L1/archived/<slug>.summary.yaml
└── L2-project.yaml        # 6 buckets (patterns, findings, decisions-frozen,
                           #   naming-extras, contradictions-resolved, promotion-candidates)
```

### Reconciliação

- **L2-project.yaml → retirado.** Conteúdo migra pra notas mem (§Migração).
  `memory_l2_path` (paths.py:136-138) deixa de existir como destino de
  escrita; vira (transitoriamente) só leitura pra o migrador.
- **L3 (`engine/memory/l3.py`) → retirado como camada própria.** O `mem`
  cobre o caso de uso (memória persistente consultável). A auto-memory do
  Claude Code (`~/.claude/projects/.../MEMORY.md`) continua existindo como
  feature nativa do host, mas o forge para de proxiá-la — o `mem brief`/
  hooks cobrem injeção. Como a retirada é clean-break (pré-produção, sem
  usuários reais), não há ponte de back-compat: o único consumidor de L3 é
  `engine/memory_cli.py` (ação "inspect L3"), que some quando o handler vira
  wrapper (§Superfície).
- **L1 → corte resolvido (Decisão #1).** A parte state-machine (status.json,
  phase-lock, history.jsonl, verify-log.jsonl, dispatch-log.jsonl,
  blocking-deps, subtype, extends-feature) **sai de `.claude/memory/L1/`
  pra `.claude/forge/state/`** (`forge_state_dir`, paths.py:285). A parte
  distilável (hypothesis/rationale-trace/elicitation) vira nota mem na
  retrospectiva via `forge evolve` → `mem add`. Depois do corte,
  `.claude/memory/` é 100% do mem.

  **Call-sites do L1 state-machine a re-apontar pro novo path:**

  | Arquivo | O que muda |
  |---|---|
  | `engine/utils/paths.py:131-138` | `memory_l1_path` deixa de derivar de `memory_dir`; passa a derivar de `forge_state_dir` (ex.: `.claude/forge/state/lifecycle/<slug>/`). `memory_l2_path` é removido. |
  | `engine/memory/l1.py` | módulo inteiro re-baseia o path-root (status/history/phase-lock/verify-log/dispatch-log/archive) em `forge_state_dir`; a parte distilável (hypothesis/rationale/elicitation) deixa de ser escrita em L1 — vira input do destilador→mem. `archive_feature` (l1.py:721) re-aponta. |
  | `engine/plan.py` | escreve hypothesis/ambiguity/elicitation/rationale/history → history+status vão pro novo path; hypothesis/rationale/elicitation alimentam a destilação pro mem |
  | `engine/implement.py` | append history + update status → novo path |
  | `engine/verify.py` | `append_verify_log` + read hypothesis → verify-log no novo path |
  | `engine/undo.py` | read/release phase-lock + remove L2 entry → phase-lock no novo path; remoção de L2 vira curadoria mem |
  | `engine/ingest.py` | read status + list active features → novo path |
  | `engine/reconfigure.py` | list features + check blocks/external-deps → novo path |
  | `engine/status.py` | list features + L2 size → features no novo path; L2-size some |
  | `engine/evolve.py` | apply proposals (L1 archive + L2 add) → archive no novo path; L2 add vira `mem inbox add` |
  | `engine/graph/reuse_apply.py` | apply L1State + update status → novo path |
- **Gitignore:** o scaffold do mem adiciona `.claude/memory/mem.db*`
  (`mem`:1849). O forge garante isso no init. O `.claude/forge/state/`
  (lifecycle WIP) é gitignored como WIP (a regra que hoje gitignora
  `.claude/memory/L1/` migra pro novo path).

---

## Migração

### Princípio

- **Greenfield nasce no mem.** Projeto novo: `forge init` vendoriza o mem,
  scaffolda o layout mem, nenhum L1/L2 caseiro é criado.
- **Brownfield migra one-time.** Projeto com `.claude/memory/L2-project.yaml`
  existente roda uma migração one-shot.

### Por que `mem import` cru não basta

`mem import` (`mem`:1948-1973) só entende **markdown com frontmatter**. O
L2 do forge é **YAML estruturado em 6 buckets** (`L2Entry`: id, kind,
title, body, provenance, confidence, ...). Os tipos também não batem
1:1 — o forge tem `kind ∈ {convention, pattern, anti-pattern, domain-fact,
tooling, risk, finding, decision-frozen, naming-extra,
contradiction-resolved, promotion-candidate}`; o mem tem
`type ∈ {feedback, reference, episode, decision, session}`.

### Estratégia: migrador forge-side que emite `mem add` (Decisão #3)

**Decisão:** a migração é um **migrador forge-side**, NÃO `mem import` cru.
Um comando one-time (`forge raw migrate-memory-to-mem`, ou passo opt-in no
`forge reconfigure`) que:

1. Lê `L2-project.yaml` via `engine/memory/l2.py:read_l2` (ainda existe
   durante a migração).
2. Mapeia cada `L2Entry.kind` → `mem type` (tabela determinística, lossy —
   11 kinds do forge → 5 tipos do mem):

   | forge L2 kind | → mem type | nota |
   |---|---|---|
   | `convention`, `naming-extra` | `feedback` se prescritivo (voz imperativa), senão `reference` | default conservador: prescritivo→feedback |
   | `pattern` | `reference` | |
   | `anti-pattern` | `feedback` | prescritivo por natureza |
   | `domain-fact` | `reference` | |
   | `tooling` | `reference` | |
   | `risk` | `reference` | |
   | `finding` | `episode` se bug-shaped, senão `reference` | |
   | `decision-frozen` | `decision` | |
   | `contradiction-resolved` | `decision` | |
   | `promotion-candidate` | (pular — meta-curadoria, não fato) | |

3. **Preservação dos campos sem equivalente 1:1** (o mem não tem
   `confidence`/`provenance`/`expires_at`/`promoted_from`). Como a extensão
   do schema do mem é **follow-on** (NÃO neste spec), o migrador preserva
   esses campos no **corpo** e nas **tags** da nota mem:
   - `importance` derivado de `confidence` (ex.: confidence≥0.9→4, senão 3).
   - `confidence`, `expires_at`, `promoted_from` → linha de rodapé no body
     da nota (ex.: `\n\n---\nmigrado-de: L2:<id> · confidence: 0.9 ·
     expires-at: <iso> · promoted-from: <feature>`).
   - `provenance` (feature slugs) → vira tags + `--source "migrate:L2:<id>"`.
   Nenhum campo do L2 se perde silenciosamente; ele migra pro corpo/tags
   até a extensão de schema (Fase 2 / follow-on) dar campos nativos.
4. Invoca `mem add --type <T> -t <title> --tags <derivadas>
   --source "migrate:L2:<id>" "<body+rodapé>"` via a fronteira shell.
5. **Idempotência:** o `mem add` tem near-dup check (Jaccard título ≥0.8,
   warning não-bloqueante) mas não é garantia. O migrador grava um sentinel
   (`.claude/memory/.migrated-from-l2`) e recusa re-rodar sem `--force`.
   (`mem import` é one-shot sem proteção — por isso NÃO o reusamos cru.)
6. A parte distilável do L1 ativo NÃO é migrada em massa — é transiente
   (WIP per-feature). Features `done` cuja retrospectiva ainda não rodou:
   a destilação normal (`forge evolve` → `mem inbox add`) cobre quando a
   retrospectiva rodar; não há migração em massa de rationale-trace
   histórico (evita poluir o acervo com WIP obsoleto).

### Pós-migração

Após confirmar o acervo no mem (`mem stats`), o `L2-project.yaml` vira
artefato histórico (mantido até o usuário confirmar via 3-caminhos no
reconfigure, espelhando a disciplina `.bak` da Decisão 24 — nunca
auto-deleta).

---

## Re-roteamento dos consumidores

Hoje a memória-de-conhecimento é lida/escrita em vários pontos. Cada um
re-roteia pra `mem find/get/add` via a fronteira shell. Call-sites
concretos (do mapeamento do código):

### Engine

| Call-site | Hoje | Vira |
|---|---|---|
| `engine/evolve.py` (retrospective) | aplica proposals → `distiller.apply_proposal_to_l2` → `l2.add_entry` | gera proposals → `mem inbox add --origin ...` (candidatos); promoção curada por `mem evolve` + `mem inbox promote` |
| `engine/memory_cli.py` (handler `forge memory`, cli.py:69) | menu interativo: inspect L1/L2/L3, search L1+L2+L3, forget L2, distill, export-for-context-pack | wrapper fino sobre o mem (ver §Superfície). `search` → `mem find`; `inspect` → `mem get`/`stats`; `export-for-context-pack` → `mem brief` |
| `engine/status.py` | lê L2 size, lista features | features (lifecycle) ficam; L2-size some; usar `mem stats` se quiser counts de conhecimento |
| `engine/doctor.py` (l43-44) | conta features, L2 size | adiciona check de drift do mem pinado; L2-size some |
| `engine/evolve.py` + `engine/graph/duplicates.py` (l880-1041) + `engine/graph/reuse_apply.py` | reuse-intelligence proposals → distiller queue → L2 | reuse-intelligence **fica** (é code-graph, forge owns). O que muda: proposals "promote-to-shared-helper" etc. continuam no distiller do forge; só proposals de **conhecimento** (promote-to-l2) re-roteiam pra `mem inbox` |
| `engine/plan.py`, `engine/implement.py`, `engine/verify.py`, `engine/undo.py`, `engine/ingest.py`, `engine/reconfigure.py` (consumidores de L1 state) | L1 state-machine (status/phase-lock/history/verify-log) | lifecycle **fica no forge**, mas re-aponta de `.claude/memory/L1/` → `.claude/forge/state/` (Decisão #1; call-sites na §Reconciliação) |

> **Distinção crítica:** o `distiller` do forge tem DOIS tipos de proposal
> (`DistillationProposal.kind`): (a) **conhecimento** (`promote-to-l2`,
> `consolidate-l2`, `distill-l2`) → re-roteiam pro mem; (b)
> **reuse-estrutural** (`consolidate-duplicate-helper`,
> `promote-to-shared-helper`, `kmp-migration-candidate`, etc.) → **ficam**
> no forge (são sobre código, não conhecimento). O fingerprint/veto
> (Decisão 25) continua valendo pros (b); pros (a) o anti-envenenamento
> passa a ser o inbox do mem (G11).

### Agentes (prompts)

Agentes que hoje instruem leitura de L2/inventory/memória → re-roteiam pra
`.claude/bin/mem find/get`:

| Agente | O que muda |
|---|---|
| `agents/memory-distiller.md` | era o agente que destila L1→L2; vira o que gera **candidatos de inbox** do mem (`mem inbox add --origin haiku`). A skill `mem-consolidate` que o mem instala cobre o caso genérico de captura; o `memory-distiller` do forge permanece como o destilador *específico do lifecycle* (lê hypothesis/rationale-trace/elicitation da feature e emite candidatos). Não duplicar a captura genérica — delegar a parte genérica à skill, manter só o que é forge-specific. |
| `agents/feature-prd-agent.md` | onde lê memória de convenções/decisões passadas → `mem find "<tema>" --type decision`/`--type reference` antes de redigir PRD |
| `agents/planning-conductor.md` | onde consulta L2/inventory pra contexto → `mem find` por área antes de planejar (além do graph pra estrutura) |
| `agents/contract-planner-agent.md` | idem — consulta de convenções/decisões → `mem find` |
| `agents/retrospective-agent.md` | em vez de escrever L2 direto, emite `mem inbox add` (candidatos curados via `mem evolve`) |

> **Nota:** `engine/inventory/` (DS components + i18n + conventions
> extraídos do código) é **estrutura derivada do projeto**, não
> memória-de-conhecimento. **Fica no forge.** Só re-roteia o que é
> learnings/decisões/episodes curados.

---

## Superfície de comando

### `forge memory` → wrapper fino

Hoje `forge memory` é um menu interativo (`engine/memory_cli.py`, registrado
em `engine/cli.py:69`) com 7 ações sobre L1/L2/L3 + checkpoint-resume
(DRIFT-1). Vira wrapper fino que delega ao mem:

| Ação atual | Vira |
|---|---|
| inspect L2-project | `mem find ""` / `mem stats` (paginado) |
| inspect L1 {slug} | inspeção de lifecycle **fica** (lê de `.claude/forge/state/`); pode separar pra `forge status` |
| inspect L3 auto-memory | removido (L3 retirado) |
| search (L1+L2+L3) | `mem find <query>` |
| forget L2 entry | `mem supersede`/`evolve --apply` (curadoria do mem) |
| distill L2 | `mem evolve` + `mem inbox promote/reject` |
| export L2 for context-pack | `mem brief` |

**Bug multi-passo do `forge memory` (BUG-M1) — Decisão #4: provar a cura,
não assumi-la.** O `engine/memory_cli.py` carrega complexidade de
checkpoint-resume (DRIFT-1 W2.T3b): **11 callsites interativos** com
save-before-`question.ask` (menu ask, search, forget-L2 com 2 confirms,
distill-L2 com iteração de proposals). Ao virar wrapper fino sobre comandos
`mem` não-interativos (todos aceitam `--json`, sem prompt em não-TTY), o
fluxo multi-passo frágil desaparece estruturalmente — o mem é stateless por
invocação, então os 11 callsites de checkpoint-resume somem com o handler
antigo.

**Mas o spec NÃO assume cura por fé.** O plano de implementação DEVE seguir
TDD sobre o bug:

1. **Reproduzir BUG-M1 com teste FALHANDO primeiro** — capturar o sintoma
   exato do comportamento multi-passo defeituoso no `memory_cli.py` atual
   (ex.: resume de checkpoint que pula um passo, ou re-prompt duplicado).
   Se o sintoma exato não for conhecido, o primeiro passo da implementação é
   investigá-lo (systematic-debugging) e escrever o regression test que o
   pega. Sem repro vermelho, não há prova de cura.
2. **Implementar o wrapper stateless.**
3. **Confirmar o teste passa** (o bug não pode mais ocorrer porque os
   callsites de checkpoint-resume não existem) + a suíte verde.

A eliminação dos 11 callsites é a hipótese de cura; o teste vermelho→verde
é a prova. O spec exige a prova, não a fé.

### Overlaps de comando entre os dois CLIs — quem ganha

| Comando | forge | mem | Resolução |
|---|---|---|---|
| `init` | `forge init` (scaffold projeto inteiro) | `mem init` (scaffold só memory) | **forge ganha** a porta de entrada; `forge init` *chama* o scaffold do mem internamente. Usuário nunca roda `mem init` direto. |
| `doctor` | `forge doctor` (17 categorias) | `mem doctor` (install/schema/version) | **forge ganha**; adiciona uma categoria que chama `mem doctor --json` e dobra o resultado no painel forge. |
| `import` | — | `mem import` (markdown) | **mem é a engine**; a migração L2→mem é um migrador forge-side que emite `mem add` (não usa `mem import` cru). |
| `stats` | embutido em status/doctor | `mem stats` | sem conflito — forge mostra stats de lifecycle/graph; mem stats de conhecimento. |
| **`evolve`** | `forge evolve` | `mem evolve` | **escopos DISTINTOS — ambos ficam, não colidem.** Ver abaixo. |

### `forge evolve` vs `mem evolve` — escopos distintos

Crítico não confundir:

- **`forge evolve`** = review-and-apply de **proposed-evolutions do forge**:
  promoção de reuse-intelligence (helpers compartilhados, KMP-migration,
  consolidação de duplicatas estruturais), template-patches, agent-prompt
  additions, new-card-suggestions. É curadoria sobre **código e
  artefatos do forge**. Decisões 25 (fingerprint) e 26 (single-by-single,
  proibido batch-apply) governam.
- **`mem evolve`** = curadoria do **acervo de memória-de-conhecimento**:
  propõe ARCHIVE (notas com standing baixo + sem acesso), DUP clusters,
  e lista a INBOX pendente; `--apply` arquiva own-author. Governado por
  R12 (gated) + G11 (promoção por-item).

São ortogonais. A única ponte: proposals de `forge evolve` cujo `kind` é
**conhecimento** (`promote-to-l2`) passam a emitir `mem inbox add` em vez de
escrever L2 — daí o conhecimento entra no ciclo do `mem evolve`. Reuse
estrutural nunca toca o mem.

---

## Rename `docs/feature-implementation-workflow` → `docs/forge-specs`

**Clean break, SEM back-compat, SEM alias** (projeto pré-produção, sem
usuários reais — pilot = teste). Resolve a colisão de namespace entre o
output de artefatos de feature dos consumidores e o vocabulário "specs".

> ⚠️ **NÃO confundir** com `docs/superpowers/specs/` (specs do PRÓPRIO
> forge, como este arquivo) — esse path NÃO muda.

### Call-sites enumerados (código que escreve/lê o path — load-bearing)

Estes governam comportamento e devem ser atualizados:

| Arquivo:linha | O que é |
|---|---|
| `engine/utils/paths.py:153` | `feature_workflow_root()` — literal `"docs"/"feature-implementation-workflow"` (CENTRAL) |
| `engine/utils/paths.py:203` | `_resolve_features_root()` default base literal |
| `engine/utils/paths.py:228` | `feature_path()` default-comparison literal |
| `engine/memory/l1.py:721` | `archive_feature`/path base literal (independente de paths.py) — nota: o archive em si re-baseia em `.claude/forge/state/` (Decisão #1); só o segmento `docs/feature-implementation-workflow` do path de *artefatos* renomeia |
| `engine/qa/scope.py:166` | `_features_root()` literal (independente) |
| `engine/graph/duplicates.py:935` | `target-file` string `docs/feature-implementation-workflow/non-product/(generated)` |
| `engine/graph/reuse_apply.py:28` | `_NON_PRODUCT_DIR = "docs/feature-implementation-workflow/non-product"` |
| `engine/init.py:3268` | `"features-package-root": "docs/feature-implementation-workflow/features"` (default config) |
| `validators/validate_task_contract.py:88` | base literal |
| `validators/check_files_in_allowed_files.py:48` | base literal |
| `validators/validate_feature_package.py:5` | docstring path (+ verificar corpo) |

> **Reuso (Mandamento #3) — consolidar (recomendação firme):** o rename
> consolida os literais hardcoded (l1.py, qa/scope.py, graph/*, validators/*,
> init.py) pra consumirem `paths.feature_workflow_root()` em vez de
> re-hardcodar. Reduz os call-sites de path de 11 pra ~3 (os de paths.py) e
> evita que o próximo rename precise caçar literais espalhados. O refactor
> de consolidação anda junto com o rename no mesmo plano (não é trabalho
> separado — é o jeito certo de fazer o rename uma vez só).

### Docs/prosa afetados (atualizar no mesmo PR, doc-sync)

`engine/plan.py:5` (docstring), `engine/graph/reuse_apply.py:5` (docstring),
`engine/qa/scope.py:5,62` (docstrings), `engine/utils/paths.py:152,157,217`
(docstrings/comments), `agents/planning-conductor.md` (l56,183,185,187,936),
`agents/screen-analysis-agent.md` (l66,67,69),
`agents/retrospective-agent.md` (l27,95,261,337,349),
`agents/feature-prd-agent.md` (l49,51,211,230),
`agents/feature-intake-agent.md` (l58,296),
`agents/task-contract-writer.md` (l83,84,360),
`agents/tech-spec-agent.md` (l208), `docs/design/04-pending.md:1363`,
`docs/design/07-discipline.md:988,1359`,
`docs/design/05-filesystem-layout.md:33,418,423,561,693`,
`docs/product/00-prd.md:487`, `docs/schemas/proposed-evolutions.md:224`,
`docs/schemas/memory.md:74,432`, `docs/schemas/forge-config.md:94`
(default `features-package-root`), `docs/ux/*-roteiro.md` (forge-evolve l722,
forge-implement l708, forge-plan l1051,1071),
`docs/guides/feature-lifecycle.md:56`, `docs/guides/dot-claude-reference.md`
(l177,197).

> Planos antigos em `docs/superpowers/plans/*.md` referenciam o path velho
> em conteúdo histórico — **NÃO reescrever planos consumidos** (são
> registro histórico, fora de escopo do rename de comportamento).

---

## Rules no mem — two-tier (redução entra na Fase 1)

O destino das rules/convenções no mem é **two-tier**:

1. **Tier-0 — núcleo lean sempre-on (invariante).** Um índice mínimo
   (~30 linhas, padrão `RULE_INDEX` do mem, `mem`:1736-1766) + os gates
   verdadeiramente invariantes (o que NÃO pode ser "sob demanda" sem quebrar
   enforcement). Fica injetado sempre.
2. **Tier-1 — convenções/aprendizados ricos sob-demanda.** Notas mem
   (`type=reference`/`feedback`) recuperadas via `find`/`fire` quando
   relevantes, em vez de injetadas sempre.

### A REDUÇÃO de rules está na Fase 1 (não é mais milestone seguinte)

A **redução** de rules no init — classificar Tier-0 vs Tier-1 e enxugar o
núcleo injetado — é parte da **Fase 1 (produto)**. É o fix do gap de
*assimilação de convenção* observado no piloto: hoje o `forge init` não lê
o `.claude/rules/*`/`CLAUDE.md` existentes do projeto, então convenção
humana fica sempre-on e nunca destilada. O fluxo de init pós-mem (detalhado
na §Fases de rollout → Fase 1) lê esses arquivos, classifica cada
fragmento, PROPÕE a divisão (nunca trucida o `.claude/rules/` do humano em
silêncio — G1/G2) e, aprovado, faz `mem add` do Tier-1 + enxuga o núcleo +
escreve o índice.

> **Fase 2 (só referência neste spec):** o **enriquecimento** de rules —
> três fontes (web/init-enrich, evolve→rules-comprovado, contribuição
> humana), o comando `rules-update`, e version-awareness. Isso é curadoria
> ativa do acervo de rules ao longo do tempo, distinta da redução one-time
> do init. Ver §Fases de rollout → Fase 2 e §Fora de escopo.

---

## Tratamento das Decisões 20 e 22 (ADR-note, sem revisita formal)

A substituição da camada de memória **toca o espírito** de duas decisões
locked, mas — por análise — **não as contradiz**, então entra como
**ADR-note no CHANGELOG `### Changed`, SEM o ritual de revisita formal**.
Justificativa por decisão:

- **Decisão 20** (texto exato, `01-decisions.md:31`): *"Persistence |
  SQLite (graph) + arquivos (config, memory, docs) | Best of both."* O
  `mem` **É exatamente esse modelo**: JSONL (arquivos, commitados) como
  fonte + `mem.db` (SQLite) como índice derivado. A memória continua
  "SQLite + arquivos"; só muda *quem* implementa. O graph (a outra metade
  de "SQLite") permanece intacto no forge. Decisão 20 é **honrada, não
  revisitada**.
- **Decisão 22** (texto exato, `01-decisions.md:33`): *"Dependencies on
  other skills | None at runtime; absorb patterns only | Portability +
  independence."* O `mem` entra como **ferramenta vendorizada via shell**
  (igual detekt/gradle em `dispatch_native_tool`), NÃO como import de
  skill. `engine/` nunca faz `import mem`. A cópia é snapshot local pinado
  (alinhado com Decisão 15). Decisão 22 é **honrada** — a fronteira shell é
  precisamente o mecanismo que a Decisão 22 endossa ("absorb patterns" via
  tool, zero runtime dep de skill).

### Texto da ADR-note (a ir no CHANGELOG `### Changed`)

```markdown
### Changed

- Camada de memória-de-conhecimento substituída pelo `mem` (CLI vendorizada
  via shell). O forge deixa de manter L1-distilável/L2/L3 caseiros em
  `engine/memory/`; o `mem` (vendorizado em `.claude/bin/mem`, pinado por
  versão, invocado por subprocess — mesmo padrão de `dispatch_native_tool`
  pra detekt/gradle) passa a ser o dono único de learnings, decisões,
  episodes, sessões e convenções curadas. O code graph (`graph.db`) e o
  L1 state-machine de lifecycle permanecem no forge.

  ADR-note (sem revisita formal — consistente com decisões locked):
  - Decisão 20 (Persistence = SQLite + arquivos) é HONRADA: o `mem` É esse
    modelo — JSONL commitado (arquivos) como fonte + `mem.db` (SQLite) como
    índice derivado. O graph segue como a outra metade SQLite.
  - Decisão 22 (zero runtime dep em skills; absorb patterns only) é
    HONRADA: o `mem` entra como TOOL vendorizada via shell, não import de
    skill. `engine/` nunca faz `import mem`. Snapshot local pinado alinha
    com Decisão 15.
  Nenhuma das duas é revisitada — a substituição opera dentro do que ambas
  já endossam.
```

> Como NÃO há edit em `docs/design/01-decisions.md` nesta mudança, o
> pre-commit hard-block do Mandamento #1 não dispara (ele só exige
> "Revisita decisão N" quando `01-decisions.md` é staged). ADR-note no
> CHANGELOG é a documentação correta pra "honra, não revisita".

---

## Estratégia de teste

### Fronteira shell (`mem_call` / wrapper)

- **Mock do mem:** um fake executável (`.claude/bin/mem` stub que ecoa
  JSON canônico por subcomando) OU monkeypatch do `subprocess.run` dentro
  do wrapper. Testar: binário ausente → `MemResult(found=False)` +
  mensagem 3-caminhos (não crasha); exit 0 → parse stdout JSON; exit 2 →
  not-found tratado; timeout → fail-soft.
- **Env scrub (lição operacional):** testes que subprocessam herdam
  `CLAUDECODE`/`OPENCODE_*`/`CODEX` etc. — scrub o env no fixture pra
  determinismo. Reusar o padrão já estabelecido em testes de subprocess do
  forge. Rodar com `.venv/bin/pytest` (canonical — tem deps).

### BUG-M1 do `forge memory` (TDD obrigatório — Decisão #4)

- **Teste vermelho ANTES:** regression test que reproduz o sintoma
  multi-passo do `memory_cli.py` atual (resume de checkpoint pulando passo /
  re-prompt duplicado — sintoma exato a confirmar via systematic-debugging
  no início da implementação). Sem vermelho, não há prova de cura.
- **Verde DEPOIS:** com o wrapper stateless, o teste passa (os callsites de
  checkpoint-resume não existem mais) + suíte verde.

### Migração L2→mem

- Fixture com `L2-project.yaml` de 6 buckets povoado → roda migrador →
  asserta N `mem add` emitidos com mapeamento de tipo correto + tags/source.
- **Preservação de campos:** assert que `confidence`/`expires_at`/
  `promoted_from` aparecem no rodapé do body da nota e `provenance` vira
  tags (nada se perde silenciosamente).
- Idempotência: re-rodar sem `--force` → recusa (sentinel
  `.migrated-from-l2`); com `--force` → não duplica além do esperado.
- Edge: L2 vazio, L2 com `promotion-candidate` (pulado), L2 com confidence
  variando (importance derivada).

### Fase 0 — gate de aceite do dogfood

- **Sessão de manutenção fresca:** teste/checklist manual de que o
  Mandamento 0 continua enforçado e as rules são acessíveis via `mem find`
  após a redução (rodar os 5 checks do `SMOKE-CHECKLIST.md`, com foco no #5).
- **Hard-block intacto:** `pre-commit-feature-forge.sh` ainda bloqueia edit
  de `01-decisions.md` sem ceremony (arquivo canônico preservado).
- **Proposta, não trucida:** assert que a divisão Tier-0/Tier-1 passa por
  aprovação humana antes de qualquer enxugue (nenhum `mem add` + corte de
  rule sem o veredito 3-caminhos).

### Re-roteamento dos consumidores

- `forge memory` wrapper: cada ação delega ao subcomando mem correto
  (assert no comando shell montado). `search` → `mem find`; `export` →
  `mem brief`.
- `forge evolve`: proposals `kind=promote-to-l2` emitem `mem inbox add`;
  proposals reuse-estruturais NÃO tocam o mem (assert zero chamadas mem).
- Agentes: testar via prompt-fixtures que a instrução de leitura aponta pra
  `.claude/bin/mem find` (não pra L2 path).

### Rename

- Asserções de path: `feature_workflow_root()` retorna
  `docs/forge-specs`; nenhum literal `feature-implementation-workflow`
  sobra em `engine/`/`validators/` (grep gate no teste). Feature packages
  são escritos/lidos no path novo end-to-end (reusar o e2e de snapshot que
  já existe — `docs/superpowers/plans/2026-06-19-...` cita o pattern).
- Validators (`validate_feature_package`, `validate_task_contract`,
  `check_files_in_allowed_files`) resolvem o path novo.

### Vendor/update/doctor

- `forge init` num tmp_project: vendoriza `.claude/bin/mem` (existe +
  executável) + scaffold mem (`.claude/memory/` no layout mem, gitignore
  com `mem.db*`).
- `forge doctor`: check de drift do pin (vendored `mem --version` vs pin
  forge) → reporta `[drift]` quando diferem.

---

## Fora de escopo deste spec

- **Enriquecimento de rules (Fase 2):** as três fontes (web/init-enrich,
  evolve→rules-comprovado, contribuição humana), o comando `rules-update`, e
  version-awareness. Só a **redução** de rules entra (Fase 1); o
  **enriquecimento** ativo do acervo ao longo do tempo é Fase 2. Este spec
  só habilita a direção.
- **Extensão do schema do mem** pra campos nativos de
  `confidence`/`provenance`/`expires_at` — follow-on. Até lá, a migração
  preserva esses campos no corpo/tags da nota (§Migração).
- **Hooks de injeção do mem** (`brief`/`fire`/`install-hooks`) como
  default — são opt-in do mem; ativar por padrão no `forge init` é decisão
  separada (custo de janela vs. valor; medir antes).
- **Captura automática via Haiku** (skill `mem-consolidate`, Stop hook) —
  o mem já a provê; integrá-la ao retrospective-agent do forge é
  refinamento pós-substituição.
- **`mem issue`/`mem-report`** (reportar bugs do próprio mem) — feature do
  mem, não da integração.

---

## Riscos

> As 5 questões abertas da v1 viraram decisões (§Decisões resolvidas). As
> sub-questões de implementação delas (mapeamento prescritivo vs descritivo,
> migrar rationale-trace de features done, memory-distiller vs
> mem-consolidate, rename puro vs consolidação) também foram resolvidas
> in-line nas seções respectivas. Resta a lista de riscos abaixo — coisas a
> monitorar, não decisões pendentes.

- **Autor (`git config user.email`) instável.** O mem nomeia o JSONL pelo
  email sanitizado. Drift de identidade git (já documentado: thgMatajs vs
  thgPacheco) produziria arquivos JSONL divergentes pro mesmo humano.
  Mitigação: documentar a expectativa; talvez pin de autor via env.
- **`mem` versiona o `triggers.jsonl` commitado** — entra no diff do
  consumidor. OK, mas o forge precisa garantir que o gitignore certo
  (`mem.db*` ignorado, `*.jsonl` + `triggers.jsonl` commitados) seja
  scaffoldado no init.
- **Perda de semântica na migração — mitigada.** O L2 tem `confidence`,
  `provenance`, `expires_at`, `promoted_from` sem equivalente 1:1 no mem. A
  Decisão #3 preserva esses campos no corpo/tags da nota (não achata em
  silêncio); a perda de *consulta estruturada* por esses campos persiste até
  a extensão de schema (follow-on). Risco residual: queries por `expires_at`
  não funcionam até lá — aceitável pré-produção.
- **Acoplamento ao schema do mem.** O wrapper parseia `--json` do mem; se o
  mem mudar o shape do JSON entre versões, o wrapper quebra. Mitigação: pin
  de versão + check de drift no doctor + testes contra o JSON pinado.
- **Sandbox da `forge qa` (Decisão 31).** Validators rodam em subprocess
  com CWD sandboxed; se algum validator vier a chamar `mem`, o
  `.claude/bin/mem` precisa estar acessível de dentro do sandbox. Hoje
  nenhum validator chama mem — manter assim (validators são determinísticos,
  sem dep de memória).
- **Fase 0 enxuga os gates do próprio forge (ALTO).** Enxugar CLAUDE.md +
  `.claude/rules/**` errado pode tirar do orquestrador-mantenedor os gates
  que enforçam o Mandamento 0. Mitigação: o gate de aceite da Fase 0
  (sessão fresca + 5 smoke checks + hard-block intacto + tudo proposto)
  valida ANTES do merge; a parte canônica (`docs/design/*` com enforcement
  acoplado) NÃO é deletada, só deixa de ser injetada sempre.
- **Corte do L1 toca 11 call-sites (MÉDIO).** Re-apontar a state-machine de
  `.claude/memory/L1/` → `.claude/forge/state/` mexe em paths.py + l1.py +
  9 consumidores. Risco de path stale silencioso. Mitigação: consolidar o
  path-root num helper (`forge_state_dir`-based) e cobrir com teste de path
  + grep-gate de que nenhum literal `memory/L1` sobra.

---

## Self-review

- **Placeholder scan:** sem TBD/TODO/FIXME pendentes; `<autor>`, `<repo>`,
  `<slug>`, `<T>`, `<pin>` são placeholders de template intencionais
  (paths/comandos genéricos), não lacunas. As 5 questões abertas da v1 viraram
  decisões (§Decisões resolvidas) — não há mais "QUESTÃO ABERTA" no corpo.
- **Consistência de nomes:** `mem` (ferramenta), `mem.db` (índice),
  `engine/integrations/mem.py:mem_call`/`MemResult` (wrapper, Decisão #2),
  `engine/assets/mem/mem` (asset embutido, Decisão #3),
  `.claude/forge/state/` (lifecycle, Decisão #1), `forge memory` (comando
  wrapper), `docs/forge-specs` (path novo), `docs/superpowers/specs/` (specs
  do forge — NÃO renomeado, alertado 2x), Fase 0/1/2 (rollout).
- **Ambiguidade resolvida:** `forge evolve` vs `mem evolve` (ortogonais);
  proposals-de-conhecimento vs proposals-reuse-estrutural no distiller;
  redução-de-rules (Fase 1) vs enriquecimento-de-rules (Fase 2);
  state-machine de lifecycle (forge/state) vs conhecimento distilável (mem);
  "→ mem" não significa deletar o arquivo canônico (Fase 0).
- **Grounding:** todas as refs de código verificadas no fonte real
  (`mem`:linha e `engine/*:linha`). O `forge_state_dir` (paths.py:285) e os
  call-sites do L1 foram confirmados via grep. Onde a implementação precisa
  investigar (sintoma exato do BUG-M1), o spec exige TDD em vez de assumir.
- **Voz:** mentor calmo, PT neutro, sem emoji decorativo, sem hedging
  corporativo.
