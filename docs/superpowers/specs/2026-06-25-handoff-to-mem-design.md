# Handoff de sessão → mem (Fase 0.5 — dogfood) — design spec

> **Spec, não plano de execução.** Aterra um design já aprovado (brainstorming
> com o autor) em algo acionável. O plano de implementação (writing-plans →
> tasks) é o passo seguinte.
> **Voz:** mentor calmo. **Status:** design aprovado, pré-implementação.
> **Data:** 2026-06-25.
> **Escopo:** o PRÓPRIO repo `feature-forge` — distinto da Fase 1, que
> re-roteia os consumidores. Esta é uma **Fase 0.5**: re-rotear o handoff de
> sessão pro mem, dando sequência à Fase 0 (que já migrou o conhecimento do
> forge pro mem e enxugou `CLAUDE.md` + rules, commits até `ef8fc02`).

---

## Contexto e objetivo

O `docs/design/08-session-handoff.md` é hoje a **fonte viva** do estado de
sessão. O SessionStart hook (`.claude/hooks/session-start-orientation.sh`)
lê dele dois campos — `**Última atualização:**` e `**Estado:**` — e os
injeta na orientação que abre cada sessão de manutenção. Toda vez que código
vivo muda, o Mandamento #6 exige sincronizar esse arquivo no mesmo commit.

Com o `mem` adotado na Fase 0 como substrato de memória-de-conhecimento, o
handoff é o candidato natural seguinte: estado-de-sessão é exatamente o que
as primitivas `checkpoint` e `session` do mem cobrem. O `mem session`
inclusive já existe como destino de "handoff curado" na tabela de
mapeamento da Fase 0.

**Objetivo deste spec:** o `mem` assume o estado de sessão usando suas três
primitivas nativas (`checkpoint`, `session`, `brief`), sem nada custom. O
arquivo `08-session-handoff.md` **deixa de ser fonte viva** mas
**PERMANECE** — congela como snapshot histórico (até a Fase 0) + rede de
bootstrap pra clone fresco. Não se deleta (estado-final **hybrid**).

---

## Decisões resolvidas

As decisões do brainstorming que este spec aterra:

| # | Questão | Decisão | Onde |
|---|---|---|---|
| 1 | Estado-final do arquivo | **HYBRID** — o `08-session-handoff.md` vira arquivo-morto histórico + fallback de bootstrap; **não deletar**. | §Papel novo do arquivo |
| 2 | Fallback do SessionStart | SessionStart **tenta** injetar o último `mem session`; **se o mem está vazio ou ausente, cai pro grep** dos 2 campos do arquivo (comportamento de hoje). | §SessionStart re-route |
| 3 | Cadência de escrita | A favor do **grão do mem** — as 3 primitivas nativas (`checkpoint`/`session`/`brief`); **SEM checkpoint-por-commit custom** (briga com o grão; ver §Design — 3 cadências). | §Design — 3 cadências |
| 4 | Escopo | **P1 + P2 juntos** neste spec/plano. | §Fasamento |

> Estas decisões são premissas das seções abaixo — o plano de implementação
> as executa, não as re-litiga.

---

## O que o mem oferece (grounded no script vendorizado)

Fonte lida: `engine/assets/mem/mem` (asset pinado no repo forge) +
`/Users/thg.inchurch/Documents/mem/mem`. Fatos verificados, não inventados:

| Primitiva | O que é | Versionado? | Verificado |
|---|---|---|---|
| `mem checkpoint` | View **read-only** do singleton de continuidade de sessão (tabela `checkpoint`, `id=1`, dentro do `mem.db`). Guarda `session_id` + `last_prompt` + `status` (`open`/`closed`) + `branch`/`head`. Escrito pelos **hooks do próprio mem** (prompt/post-tool/Stop), consumido pela skill `mem-resume`. É **rede de continuidade pós-kill** — upsert de um singleton, **NÃO acumulador por commit**. Um `Stop` limpo **fecha** o checkpoint (sem falso-resume na sessão seguinte). | **NÃO** (vive no `mem.db`, que é gitignored, nunca committed) | `cmd_checkpoint` (read-only), `_hook_stop` fecha em Stop limpo |
| `mem session` | Grava um **resumo de sessão curado** no JSONL **committed** (com `git_meta` automático: branch/head/commits/files). O tipo `session` **decai agressivamente** e fica **fora** do `find`/`brief` padrão — consumido só com `--type session`. | **SIM** (JSONL committed; índice derivado descartável) | `cmd_session`; `session` fora de `find`/`brief`, `INBOX_TYPES` exclui `session` |
| `mem-consolidate` (skill) | No fim de trabalho significativo, **propõe candidatos** de conhecimento durável pro **inbox** (→ `evolve`). **Distinta do `mem session`** — uma curadoria de learnings, não um resumo de estado. | (skill instalada na Fase 0 T2) | skill instalada por `mem init` |
| `mem brief` | Índice de **alto valor** desenhado pra session-start (top `feedback`/`decision` por score, **~800 tokens default**). **Não registra acesso** (anti-viés). | n/a (derivado) | `cmd_brief`, default 800 tokens |
| `mem install-hooks` | Instala os **hooks do próprio mem** (prompt/Stop/post-tool, e o session-start do mem) no `.claude/settings.json` (merge, com `--apply`). | n/a | `cmd_install_hooks` (só `claude-code`) |

> **Distinção que sustenta o design:** o `checkpoint` é **local e efêmero**
> (singleton no `mem.db` gitignored, rede de kill-recovery); o `session` é
> **durável e committed** (handoff curado no JSONL, listável via
> `--type session`). São cadências diferentes, não redundantes.

---

## Consumidores atuais do handoff (mapa — load-bearing)

Três hooks tocam `08-session-handoff.md`. Re-rotear o handoff sem entender
esse mapa quebraria gates do próprio forge.

| Hook | Linha | O que faz hoje | Relação com o handoff |
|---|---|---|---|
| `.claude/hooks/session-start-orientation.sh` | 30–33 | `grep -m1` de `**Última atualização:**` e `**Estado:**` (com `sed`), injeta na orientação de sessão. Contrato: sempre exit 0, fallback `(handoff missing)` se ausente. | **fonte viva** (lê o estado) |
| `.claude/hooks/post-edit-doc-drift.sh` | 110 | Aviso de drift (stderr) manda atualizar `docs/design/08-session-handoff.md` no mesmo commit ao tocar doc vivo. | aponta pro arquivo como destino de sync |
| `.claude/hooks/pre-commit-feature-forge.sh` | 46 | **SOFT WARNING** (não bloqueia): se código vivo é staged sem `CHANGELOG`/`08-session-handoff.md`/`README` → avisa. | exige o arquivo no gate per-commit |

Além dos hooks: `CLAUDE.md` Mandamento #6 e `.claude/rules/doc-sync.md` (já
enxugada pra ponteiro na Fase 0) referenciam o handoff na matriz doc-sync.

---

## Design — modelo de 3 cadências (a favor do grão do mem, zero custom)

O estado de sessão tem três cadências distintas. Cada uma cai numa
primitiva nativa — nenhuma exige código custom:

| Cadência | Quando | Trilho | Escrita nova no mem? |
|---|---|---|---|
| **Per-commit** | a cada commit | `git log` + `CHANGELOG.md` | **Nenhuma.** O histórico per-commit já vive no git + CHANGELOG. |
| **Continuidade (resume)** | recuperar de kill/interrupt no meio | `mem checkpoint` (singleton) + skill `mem-resume`, mantido pelos **hooks do mem** (P2) | escrita feita pelos hooks do mem, não pelo forge |
| **Fim-de-sessão** | fechar trabalho significativo | `mem session` (handoff curado, committed) + `mem-consolidate` (learnings → inbox) | `mem session` 1×/sessão |

**Decisão explícita (#3): SEM checkpoint-por-commit custom.** Um acumulador
de checkpoint por commit brigaria com o grão do mem — o `checkpoint` é um
**singleton local** (upsert id=1, não acumulador) e é mantido pelos hooks do
próprio mem, não pelo forge. Inventar um checkpoint-por-commit custom
poluiria o acervo e duplicaria o que o git/CHANGELOG já fazem no per-commit.
O design fica a favor do grão: 3 cadências, 3 primitivas nativas, zero
custom.

---

## Design — SessionStart re-route

O `session-start-orientation.sh` passa a operar em dois níveis, com fallback
gracioso:

1. **Tenta injetar o corpo do último `mem session`** — estado + próximos
   passos + `git_meta` (branch/head/commits). A invocação exata (ex.: query
   do `session` mais recente via `--type session`) fica pro plano de
   implementação; o contrato aqui é "pega o handoff curado mais recente do
   mem".
2. **Se o mem está vazio OU ausente** (ex.: clone fresco antes do
   `mem rebuild`, ou repo sem nenhum `mem session` ainda) → **FALLBACK** pro
   `grep` dos dois campos (`**Última atualização:**`/`**Estado:**`) do
   arquivo `08-session-handoff.md` — exatamente o comportamento de hoje.

**Invariantes preservados:**

- O bloco hardcoded de **Mandamento 0 + fluxo** (linhas 42–60 do hook)
  **PERMANECE** no hook — NÃO vem do mem. O orquestrador-mantenedor não pode
  depender de o mem estar populado pra saber que é o orquestrador.
- **Contrato de exit 0 intacto:** o hook nunca trava, em nenhum dos dois
  caminhos. Se a invocação do mem falha (binário ausente, JSON inesperado,
  timeout), degrada pro fallback do arquivo, depois pro `(handoff missing)`
  de hoje — sempre exit 0.

---

## Design — mudanças de hook + docs

| Alvo | Hoje | Vira |
|---|---|---|
| `session-start-orientation.sh` | grep dos 2 campos do arquivo | lê o último `mem session` (estado + próximos passos + `git_meta`); **fallback** pro grep do arquivo se mem vazio/ausente; Mandamento 0 + contrato exit 0 preservados |
| `post-edit-doc-drift.sh` (l110) | aviso manda editar `08-session-handoff.md` | o aviso **para de mandar editar o handoff-arquivo**; passa a apontar "rode `mem session` no fim da sessão". CHANGELOG/README seguem no aviso (são per-commit). |
| `pre-commit-feature-forge.sh` (l46) | gate per-commit exige CHANGELOG **ou handoff ou** README | **tira o handoff** do gate per-commit; fica `CHANGELOG`/`README` (stats de código). O handoff vira fim-de-sessão (`mem session`), não per-commit. |
| `CLAUDE.md` Mandamento #6 + nota mem de `doc-sync` + `.claude/rules/doc-sync.md` (ponteiro) | handoff listado como sync per-commit | refletem: **per-commit = CHANGELOG/README** (stats de código); **handoff = `mem session` no fim de sessão**. |

> **Nota de escopo (Mandamento #4):** `CLAUDE.md` e `.claude/rules/**` estão
> na whitelist load-bearing do `scope.md`. As edições acima são as
> estritamente necessárias pra refletir o re-route do handoff — não é janela
> pra re-enxugar o resto. O plano lista os arquivos permitidos
> explicitamente.

---

## Design — papel novo do arquivo + arco durável

O `08-session-handoff.md` **congela** como:

- **Snapshot histórico** do estado até a Fase 0 (registro do que o projeto
  era no ponto da migração).
- **Fallback de bootstrap** pro SessionStart quando o mem ainda não tem
  `session` (clone fresco antes do `mem rebuild`, ou repo recém-adotado).

A partir daqui, o arquivo **não é mais editado a cada sessão**. O arco
durável de estado passa a ser:

- **`CHANGELOG.md`** — o registro de releases (o que mudou, por versão).
- **Notas `mem session`** no JSONL **committed** — uma por sessão
  significativa. Decaem no `find`/`brief` padrão (não poluem a injeção
  sob-demanda), mas **ficam no git** (durabilidade + review em PR) e são
  **listáveis** via `mem find --type session`.

**Sem perda de informação:** o estado de cada sessão passa do arquivo
único-sobrescrito pra uma série de notas append-only versionadas — mais
histórico, não menos.

---

## Design — adoção dos hooks do mem (P2) + coexistência

`mem install-hooks --apply` (tool `claude-code`) instala os handlers do mem
no `.claude/settings.json`. Os eventos que o mem registra (verificados no
`_HOOK_WIRING`): `UserPromptSubmit` (prompt), `Stop`, `SessionStart`, e
`PostToolUse` (matcher `Edit|Write`).

**Coexistência com os hooks do forge.** O forge já registra
`SessionStart` (orientação), `PreToolUse` (load-bearing), `PostToolUse`
(drift) e o git `pre-commit`. A coexistência é **aditiva** — o mem adiciona
`UserPromptSubmit`/`Stop` (eventos novos pro projeto) e **soma** handlers em
`SessionStart`/`PostToolUse` (eventos que o forge já usa).

**Ponto que pede mais cuidado: o merge no `.claude/settings.json`.** Como o
mem registra `SessionStart` e `PostToolUse(Edit|Write)` — eventos onde o
forge **já tem** seus próprios hooks — o merge precisa **somar** os handlers
do mem aos do forge, **nunca sobrescrever**. O `_merged_settings` do mem faz
merge (não clobber), mas o plano DEVE verificar, num `settings.json` com os
hooks do forge presentes, que os hooks do forge (orientação, drift,
load-bearing, pre-commit) **continuam intactos** após `install-hooks
--apply`. Este é o gate de coexistência.

**Continuidade/consolidação como prática.** As skills `mem-resume` e
`mem-consolidate` (já instaladas na Fase 0 T2) passam a ser a prática
canônica: `mem-resume` lê o `checkpoint` pra retomar após kill;
`mem-consolidate` propõe learnings pro inbox no fim de trabalho. Com os hooks
do mem ativos (P2), o `checkpoint` é mantido automaticamente
(prompt/post-tool atualizam, `Stop` limpo fecha).

---

## Fasamento

Escopo aprovado pelo autor (Decisão #4): **P1 + P2 juntos** neste spec/plano.

- **P1 — re-route core.** Entrega o pedido central:
  - SessionStart lê `mem session` (fallback arquivo).
  - As três mudanças de hook/docs (`post-edit-doc-drift`,
    `pre-commit-feature-forge`, `CLAUDE.md`/`doc-sync`).
  - O `08-session-handoff.md` congela (snapshot + fallback).
- **P2 — adoção dos hooks do mem.**
  - `mem install-hooks --apply` (continuidade via `checkpoint` +
    consolidação automática).
  - Coexistência verificada no `.claude/settings.json` (hooks do forge
    intactos).

---

## Anti-goals

- **Sem checkpoint-por-commit custom** (briga com o grão do mem — Decisão #3).
- **Sem deletar o arquivo** — estado-final hybrid (Decisão #1).
- **Não toca `docs/design/01-decisions.md`** — nenhuma decisão locked é
  revisitada; o hard-block do Mandamento #1 não dispara.
- **Não é a Fase 1** — re-route de consumidores fica fora; aqui é só o
  dogfood do PRÓPRIO repo forge.
- **Não muda o que o SessionStart injeta de Mandamento 0** — o bloco de
  Mandamento 0 + fluxo permanece hardcoded no hook.

---

## Validação / gate de aceite

### Lógica de hook (testável onde der)

Invocação sintética dos hooks (no espírito do `SMOKE-CHECKLIST.md` — JSON
sintético via `bash <hook>`), confirmando:

- (a) **mem populado** → SessionStart injeta o corpo do último `mem session`
  (estado + próximos passos).
- (b) **mem vazio/ausente** → SessionStart cai pro `grep` do arquivo
  (comportamento de hoje preservado).
- (c) **sempre exit 0** — em ambos os caminhos, e mesmo se a invocação do mem
  falhar (degrada graciosamente).
- (d) **Mandamento 0 intacto** — o bloco hardcoded de orientação aparece em
  qualquer caminho.

### Gate de aceite (espelhando a Fase 0 — não fecha por subagente)

- **Sessão de manutenção fresca** (SessionStart limpo): confirma orientação
  via mem + fallback funcional + Mandamento 0 intacto.
- **Coexistência de settings:** após `mem install-hooks --apply` num
  `.claude/settings.json` com os hooks do forge, os hooks do forge
  (orientação/drift/load-bearing/pre-commit) continuam registrados e
  funcionais.

### Doc-sync + verde

- `pytest` verde (`.venv/bin/pytest` — canonical, tem deps).
- Doc-sync: `CHANGELOG` (Unreleased) + uma **última atualização** do
  `08-session-handoff.md` (o ato de congelar é, ele mesmo, a última edição
  viva — registra o congelamento) + `README` se stats mudaram.

---

## Self-review

- **Placeholder scan:** sem TBD/TODO/FIXME pendentes. `<hook>` e os
  `**Campo:**` citados são referências literais a símbolos reais do código,
  não lacunas. A invocação exata do "último `mem session`" é deliberadamente
  deixada pro plano (anotada como tal em §SessionStart re-route), não é
  placeholder não-resolvido.
- **Consistência de nomes:** `mem checkpoint` (singleton local, gitignored),
  `mem session` (handoff committed), `mem brief` (índice), `mem install-hooks`
  (P2), `mem-resume`/`mem-consolidate` (skills), `08-session-handoff.md`
  (arquivo congelado), `.claude/hooks/session-start-orientation.sh` /
  `post-edit-doc-drift.sh` / `pre-commit-feature-forge.sh` (os 3
  consumidores), P1/P2 (fasamento).
- **Ambiguidade resolvida inline:** (1) `checkpoint` (local/efêmero) vs
  `session` (durável/committed) — cadências diferentes, não redundantes; (2)
  "congela" ≠ "deleta" — hybrid explícito; (3) o gate de coexistência foi
  ancorado no fato verificado de que o mem registra `SessionStart` e
  `PostToolUse(Edit|Write)` — eventos que o forge JÁ usa —, então o merge do
  `settings.json` precisa **somar, não sobrescrever** (o design dizia
  "aditivo"; aterrei no overlap concreto pra que o gate seja testável).
- **Grounding:** hooks lidos no fonte real (`session-start-orientation.sh`
  l30–33, `post-edit-doc-drift.sh` l110, `pre-commit-feature-forge.sh` l46);
  primitivas do mem verificadas no script (`cmd_checkpoint` read-only,
  `_hook_stop` fecha em Stop limpo, `cmd_session`, `cmd_brief` 800 tokens,
  `cmd_install_hooks` + `_HOOK_WIRING` com os 4 eventos).
- **Voz:** mentor calmo, PT neutro, sem emoji decorativo, sem hedging
  corporativo.
