# Integração mem ↔ feature-forge — design spec

> **Spec, não plano de execução.** Aterra decisões de arquitetura já
> tomadas pelo autor em algo acionável. O plano de implementação
> (writing-plans → tasks) é o passo seguinte.
> **Voz:** mentor calmo. **Status:** design aprovado, pré-implementação.
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
| Feature lifecycle state (status, phase-lock, history) | — | ✅ ver nota abaixo |
| Cards / templates / presets / validators | — | ✅ forge |
| Conductor + sub-agents de planejamento | — | ✅ forge |

> **Nota sobre L1 — fronteira fina e deliberada.** O L1 atual (`l1.py`)
> mistura DOIS conceitos: (a) **estado-de-lifecycle** (status.json,
> phase-lock, history.jsonl, verify-log, dispatch-log, blocking-deps) —
> isso é *mecânica de execução do forge*, NÃO memória-de-conhecimento, e
> **fica no forge**; (b) **conhecimento destilável** (hypothesis,
> rationale-trace, elicitation) — candidato a virar nota mem na
> retrospectiva. A substituição visa a **camada de
> memória-de-conhecimento** (L2 + a parte distilável de L1 + L3), não o
> state-machine de execução. **QUESTÃO ABERTA #1** abaixo trata onde
> exatamente cortar L1.

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

**QUESTÃO ABERTA #2:** extrair um helper menor — `_mem_shell.py` (ou
`engine/integrations/mem.py`) — que reusa a *espinha* do
`dispatch_native_tool` (locate binary via path conhecido `.claude/bin/mem`
com fallback `shutil.which("mem")`, subprocess com timeout, captura
stdout/exit-code, fail-soft) mas com superfície enxuta:

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
   copiar o `mem` pinado (que o forge carrega como asset — ver
   §Pin) pra `<project>/.claude/bin/mem` + chmod 755, e rodar o equivalente
   de `mem init` (scaffold do `.claude/memory/` no layout do mem).
2. **QUESTÃO ABERTA #3:** o forge embute uma cópia pinada do script `mem`
   como asset (ex.: `engine/assets/mem` ou `vendor/mem`), OU baixa via
   `gh api repos/inRadar/mem` no init? Embutir = clone-and-go, CI sem rede,
   alinhado com Decisão 15 (snapshot copy local). Baixar = sempre na última.
   **Recomendação:** embutir (asset pinado no repo forge), consistente com
   Decisões 15 e 22. O update vem por `forge upgrade` (abaixo).
3. Substituir o scaffold caseiro de `L1/L2` por scaffold do mem (o layout
   `.claude/memory/` muda — ver §Reconciliação).

### Update no `forge upgrade`

`engine/upgrade.py` opera sobre a instalação do forge (FORGE_HOME), não
sobre projetos, e hoje **não toca memória**. O update do mem pinado tem
duas faces:

- **Bump do pin no repo forge:** quando o forge adota uma versão mais nova
  do `mem`, atualiza o asset embutido (`engine/assets/mem`) + a constante
  de versão pinada. Isso é manutenção do *próprio forge* (commit no repo
  forge), não runtime.
- **Propagação pro projeto consumidor:** quando o usuário roda
  `forge upgrade` (ou `forge reconfigure`) num projeto, o forge re-vendoriza
  a cópia do mem pinada pra `<project>/.claude/bin/mem`. Reusar a disciplina
  R13 do próprio mem (recusar clobber de cópia modificada à mão) é
  desejável — **QUESTÃO ABERTA #4:** chamar `mem update --ref <pin>` (que
  já implementa R13, mas baixa da rede via gh) vs. re-copiar o asset
  embutido (offline, sem R13 sha-check)? Recomendação: re-copiar o asset
  embutido com um sha-check próprio análogo ao R13, mantendo offline-first.

### Pin de versão

- Forge fixa UMA versão do `mem` por release do forge (ex.: `mem 0.8.1`).
- O pin vive em uma constante (`engine/integrations/mem.py:MEM_PINNED_VERSION`
  ou similar) + o asset embutido carrega esse `__version__`.
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
  hooks cobrem injeção. **QUESTÃO ABERTA #5** trata se algum consumidor de
  L3 precisa de ponte temporária.
- **L1 → ver nota na §Divisão.** A parte state-machine (status.json,
  phase-lock, history, verify-log, dispatch-log) **fica** no forge sob
  `.claude/memory/L1/` OU migra pra um diretório que não colida com o
  layout do mem (ex.: `.claude/state/lifecycle/`). **QUESTÃO ABERTA #1.**
  A parte distilável (hypothesis/rationale/elicitation) vira nota mem na
  retrospectiva via `forge evolve` → `mem add`.
- **Gitignore:** o scaffold do mem adiciona `.claude/memory/mem.db*`
  (`mem`:1849). O forge deve garantir que isso entra no gitignore do
  consumidor no init (hoje o forge gitignora L1 como WIP — essa regra muda).

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

### Estratégia: migrador forge-side que emite `mem add`

Um comando one-time (ex.: `forge raw migrate-memory-to-mem`, ou um passo
opt-in dentro de `forge reconfigure`) que:

1. Lê `L2-project.yaml` via `engine/memory/l2.py:read_l2` (ainda existe
   durante a migração).
2. Mapeia cada `L2Entry.kind` → `mem type` (tabela de mapeamento
   determinística):

   | forge L2 kind | → mem type |
   |---|---|
   | `convention`, `naming-extra` | `reference` (ou `feedback` se prescritivo) |
   | `pattern` | `reference` |
   | `anti-pattern` | `feedback` |
   | `domain-fact` | `reference` |
   | `tooling` | `reference` |
   | `risk` | `reference` |
   | `finding` | `episode` (se bug) ou `reference` |
   | `decision-frozen` | `decision` |
   | `contradiction-resolved` | `decision` |
   | `promotion-candidate` | (pular — é meta-curadoria, não fato) |

   **QUESTÃO ABERTA #6:** o mapeamento `convention/anti-pattern →
   feedback vs reference` precisa de heurística ou triagem humana. Default
   conservador: tudo prescritivo (`anti-pattern`, `convention` com voz
   imperativa) → `feedback`; descritivo → `reference`.
3. Pra cada entry mapeada, invoca `mem add --type <T> -t <title>
   --tags <derivadas> --source "migrate:L2:<id>" "<body>"` via a fronteira
   shell. `importance` derivado de `confidence` (ex.: confidence≥0.9→4,
   senão 3). Provenance vira tag/source.
4. **Idempotência:** o migrador NÃO deve duplicar se re-rodado. O `mem add`
   tem near-dup check (Jaccard título ≥0.8, warning não-bloqueante), mas
   não é garantia. O migrador grava um sentinel
   (`.claude/memory/.migrated-from-l2`) e recusa re-rodar sem `--force`.
   (`mem import` é one-shot sem proteção — não reusar ele cru.)
5. A parte distilável do L1 ativo NÃO é migrada em massa — ela já é
   transiente (WIP per-feature). Features `done` cuja retrospectiva ainda
   não rodou: **QUESTÃO ABERTA #1/#7** — migrar rationale-trace de features
   done como `decision`/`reference`?

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
| `engine/plan.py`, `engine/implement.py`, `engine/verify.py`, `engine/undo.py`, `engine/ingest.py`, `engine/reconfigure.py` (consumidores de L1 state) | L1 state-machine (status/phase-lock/history/verify-log) | **NÃO mudam** — L1 lifecycle fica no forge (ver QUESTÃO ABERTA #1) |

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
| `agents/memory-distiller.md` | era o agente que destila L1→L2; vira o que gera **candidatos de inbox** do mem (ou é absorvido pela skill `mem-consolidate` que o próprio mem instala). **QUESTÃO ABERTA #8:** manter `memory-distiller` do forge OU delegar à skill `mem-consolidate`? |
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
| inspect L1 {slug} | **fica** (L1 lifecycle é forge) — OU separa em `forge status` |
| inspect L3 auto-memory | removido (L3 retirado) |
| search (L1+L2+L3) | `mem find <query>` |
| forget L2 entry | `mem supersede`/`evolve --apply` (curadoria do mem) |
| distill L2 | `mem evolve` + `mem inbox promote/reject` |
| export L2 for context-pack | `mem brief` |

**Bug multi-passo conhecido:** a Decisão 5 do prompt cita que o wrapper
"também resolve o bug multi-passo conhecido do comando". O
`engine/memory_cli.py` carrega complexidade de checkpoint-resume
(DRIFT-1 W2.T3b, 11 callsites interativos com save-before-`question.ask`).
Ao virar wrapper fino sobre comandos `mem` não-interativos (todos aceitam
`--json`, sem prompt em não-TTY), o fluxo multi-passo frágil **desaparece**
— o mem é stateless por invocação. **QUESTÃO ABERTA #9:** confirmar o
sintoma exato do bug multi-passo (reproduzir) pra garantir que o wrapper o
elimina e não só o mascara — o spec não deve assumir cura sem repro.

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
| `engine/memory/l1.py:721` | `archive_feature`/path base literal (independente de paths.py) |
| `engine/qa/scope.py:166` | `_features_root()` literal (independente) |
| `engine/graph/duplicates.py:935` | `target-file` string `docs/feature-implementation-workflow/non-product/(generated)` |
| `engine/graph/reuse_apply.py:28` | `_NON_PRODUCT_DIR = "docs/feature-implementation-workflow/non-product"` |
| `engine/init.py:3268` | `"features-package-root": "docs/feature-implementation-workflow/features"` (default config) |
| `validators/validate_task_contract.py:88` | base literal |
| `validators/check_files_in_allowed_files.py:48` | base literal |
| `validators/validate_feature_package.py:5` | docstring path (+ verificar corpo) |

> **Reuso (Mandamento #3):** idealmente o rename consolida os literais
> hardcoded (l1.py, qa/scope.py, graph/*, validators/*, init.py) pra
> consumirem `paths.feature_workflow_root()` em vez de re-hardcodar. Isso é
> escopo de *refactor* paralelo ao rename — **QUESTÃO ABERTA #10:** rename
> puro (trocar string em cada sítio) vs. rename + consolidação dos literais
> num helper único? O plano de implementação decide; o spec recomenda
> consolidar (reduz futuros call-sites de 11 pra ~3).

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

## Rules no mem — two-tier (REFERÊNCIA, não detalhar)

O destino das rules/convenções no mem é **two-tier**:

1. **Núcleo lean sempre-on** — um índice mínimo (~30 linhas, padrão
   `RULE_INDEX` do mem, `mem`:1736-1766) que ensina o agente a consultar a
   memória. Esse bloco já é o que `mem init`/`vendor` upserta no `AGENTS.md`.
2. **Convenções/aprendizados ricos sob-demanda** — notas mem
   (`type=reference`/`feedback`) recuperadas via `find`/`fire` quando
   relevantes, em vez de injetadas sempre.

> **Milestone SEGUINTE (fora deste spec):** a curadoria completa de rules —
> três fontes (web/init scaffolding, evolve-comprovado, contribuição
> humana) + comando `rules-update`. Este spec apenas **habilita** essa
> direção (a substituição da memória pelo mem é o pré-requisito); NÃO a
> detalha. Ver §Fora de escopo.

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

### Migração L2→mem

- Fixture com `L2-project.yaml` de 6 buckets povoado → roda migrador →
  asserta N `mem add` emitidos com mapeamento de tipo correto + tags/source.
- Idempotência: re-rodar sem `--force` → recusa (sentinel
  `.migrated-from-l2`); com `--force` → não duplica além do esperado.
- Edge: L2 vazio, L2 com `promotion-candidate` (pulado), L2 com confidence
  variando (importance derivada).

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

- **Curadoria de rules (milestone 2):** as três fontes (web/init,
  evolve-comprovado, humana), o comando `rules-update`, e o pipeline
  completo two-tier de rules. Este spec só **habilita** (a substituição da
  memória é pré-requisito).
- **Hooks de injeção do mem** (`brief`/`fire`/`install-hooks`) como
  default — são opt-in do mem; ativar por padrão no `forge init` é decisão
  separada (custo de janela vs. valor; medir antes).
- **Captura automática via Haiku** (skill `mem-consolidate`, Stop hook) —
  o mem já a provê; integrá-la ao retrospective-agent do forge é
  refinamento pós-substituição.
- **`mem issue`/`mem-report`** (reportar bugs do próprio mem) — feature do
  mem, não da integração.
- **Migração de L1 state-machine** pra qualquer outro lugar — fica onde
  está (QUESTÃO ABERTA #1 só decide o corte, não move agora).

---

## Riscos e questões abertas

### Questões abertas (precisam veredito antes/durante o plano)

1. **Onde cortar o L1.** O L1 mistura state-machine de lifecycle (fica no
   forge) com conhecimento distilável (vai pro mem na retrospectiva).
   Decidir: o state-machine permanece em `.claude/memory/L1/` (colide
   visualmente com o layout mem no mesmo dir) OU move pra
   `.claude/state/lifecycle/`? **Recomendação:** mover pra fora de
   `.claude/memory/` pra dar o dir inteiro ao mem — mas é refactor de
   paths não-trivial (l1.py + paths.py + ~6 consumidores).
2. **Tamanho da fronteira.** Extrair `mem_call` enxuto novo vs. forçar
   reuso de `dispatch_native_tool`. Recomendação: helper novo enxuto que
   reusa a *espinha* (locate/subprocess/fail-soft), não o encaixe inteiro.
3. **Distribuição do mem pinado.** Embutir asset no repo forge
   (offline, alinha Decisões 15/22) vs. baixar via `gh` no init.
   Recomendação: embutir.
4. **Mecanismo de update no `forge upgrade`.** `mem update --ref <pin>`
   (R13, mas baixa da rede) vs. re-copiar asset embutido com sha-check
   próprio (offline). Recomendação: re-copiar asset + sha-check.
5. **Consumidores de L3.** Algum consumidor depende de L3
   (`engine/memory/l3.py`) de forma que precise de ponte temporária na
   remoção? Mapear antes de retirar.
6. **Mapeamento de tipo L2→mem.** `convention`/`anti-pattern` →
   `feedback` vs `reference` precisa heurística (voz imperativa) ou
   triagem humana pós-migração.
7. **Migrar rationale-trace de features `done`?** Conhecimento real, mas
   pode estar obsoleto. Ligado à QA #1.
8. **`memory-distiller` do forge vs skill `mem-consolidate`.** Manter o
   agente do forge OU delegar à skill que o mem instala? Evitar duplicação
   (Mandamento #3).
9. **Repro do bug multi-passo do `forge memory`.** Confirmar o sintoma
   exato antes de afirmar que o wrapper o cura — não mascarar.
10. **Rename: puro vs. consolidação.** Trocar a string em 11 sítios vs.
    consolidar os literais hardcoded num helper único (`paths.py`). Spec
    recomenda consolidar.

### Riscos

- **Autor (`git config user.email`) instável.** O mem nomeia o JSONL pelo
  email sanitizado. Drift de identidade git (já documentado: thgMatajs vs
  thgPacheco) produziria arquivos JSONL divergentes pro mesmo humano.
  Mitigação: documentar a expectativa; talvez pin de autor via env.
- **`mem` versiona o `triggers.jsonl` commitado** — entra no diff do
  consumidor. OK, mas o forge precisa garantir que o gitignore certo
  (`mem.db*` ignorado, `*.jsonl` + `triggers.jsonl` commitados) seja
  scaffoldado no init.
- **Perda de semântica na migração.** O L2 tem `confidence`, `provenance`,
  `expires_at`, `promoted_from` — campos que o mem não tem 1:1. Migração
  achata pra source/tags/importance; aceitar a perda (pré-produção) ou
  preservar no body.
- **Acoplamento ao schema do mem.** O wrapper parseia `--json` do mem; se o
  mem mudar o shape do JSON entre versões, o wrapper quebra. Mitigação: pin
  de versão + check de drift no doctor + testes contra o JSON pinado.
- **Sandbox da `forge qa` (Decisão 31).** Validators rodam em subprocess
  com CWD sandboxed; se algum validator vier a chamar `mem`, o
  `.claude/bin/mem` precisa estar acessível de dentro do sandbox. Hoje
  nenhum validator chama mem — manter assim (validators são determinísticos,
  sem dep de memória).

---

## Self-review

- **Placeholder scan:** sem TBD/TODO/FIXME pendentes; `<autor>`, `<repo>`,
  `<slug>`, `<T>`, `<pin>` são placeholders de template intencionais
  (paths/comandos genéricos), não lacunas. Os 10 itens de "QUESTÃO ABERTA"
  são explícitos e numerados — decisões deferidas conscientemente pro
  veredito do autor, não buracos.
- **Consistência de nomes:** `mem` (ferramenta), `mem.db` (índice),
  `mem_call`/`MemResult` (wrapper proposto, nome tentativo marcado em QA
  #2), `forge memory` (comando wrapper), `docs/forge-specs` (path novo),
  `docs/superpowers/specs/` (specs do forge — NÃO renomeado, alertado 2x).
- **Ambiguidade resolvida:** a distinção `forge evolve` vs `mem evolve`
  (escopos ortogonais) e a distinção proposals-de-conhecimento vs
  proposals-reuse-estrutural no distiller estão explícitas — eram os dois
  pontos de maior risco de confusão. A nota L1 (state-machine vs distilável)
  evita a leitura errada de que "toda memória do forge morre".
- **Grounding:** todas as refs de código verificadas no fonte real
  (`mem`:linha e `engine/*:linha`). Onde não confirmei, marquei QUESTÃO
  ABERTA em vez de inventar (corte exato do L1, repro do bug, mecanismo de
  update).
- **Voz:** mentor calmo, PT neutro, sem emoji decorativo, sem hedging
  corporativo.
