# Campanha — feature-forge 100% AI-first: fechar pendências pré re-piloto

> **Status:** design aprovado (brainstorm 2026-06-30). Esta spec é o contrato
> da campanha que fecha o débito acionável do piloto MeoBonsai e leva o forge a
> um fluxo 100% AI-first antes de um novo piloto. As tasks de implementação
> nascem desta spec via `superpowers:writing-plans`, fase a fase.
>
> **Voz:** mentor calmo. Firme nos gates, didático nos exemplos.

---

## 1. O que "100% AI-first" significa aqui

Todo passo do lifecycle dirigível pelo host AI sem que nenhum passo manual —
build, run, screenshot, lint no terminal — caia **fora** do forge. Hoje o
"verde" do forge cobre só artefatos estáticos (specs, validators); no piloto
MeoBonsai a confirmação de que a feature funcionava veio de fora (o dev compilou,
rodou os testes e bateu o screenshot na mão). Fechar **lint nativo + build-only**
traz a etapa de execução pra dentro do loop — é a peça que falta.

Escopo deliberadamente FORA desta definição: device farm, matriz de devices, CI
completo, smoke/screenshot (níveis 2/3 do Tema 6). Esses seguem responsabilidade
do consumidor e/ou de campanhas futuras, com critério de reentrada nas specs
irmãs.

## 2. Escopo (débito acionável + AI-first + docs)

IN-SCOPE — débito acionável catalogado em `docs/design/04-pending.md §Piloto
MeoBonsai 2026-06-25 §Follow-on` + limpeza herdada da Fase 1 mem + docs:

- **Tema 6** (execution verification), Nível 1 de cada face.
- **Papercuts:** upgrade ignora flags desconhecidas; discovery cache sem
  content-fingerprint; divergência scope dict/string no verify-log; BUG-1b
  parcial (dedup `compose_backend_axes`).
- **Limpeza mem (Fase 1 follow-on):** `_KNOWLEDGE_KINDS` cobre só 3 kinds;
  misnomer `apply_proposal_to_l2`; `engine/memory/l3.py` órfão.
- **P2 polish:** itens 16-21 do report do piloto.
- **Docs:** refresh de visão + command-surface + README + CHANGELOG.

OUT-OF-SCOPE — itens deferidos-por-design cujo gatilho de reentrada NÃO ocorreu
(reabri-los seria over-engineering especulativo): W-MIGRATE (migrador L2→mem,
espera brownfield real), MCP server / McpAdapter (norte estratégico pós-piloto),
tree-sitter parsers, call-graph preciso, e os demais follow-ups graph-ia-evolution
v1.4+. Permanecem rastreados em `04-pending.md` com seus critérios.

## 3. Estratégia de branch & PR

- **Uma** branch de campanha: `feat/aifirst-pendencias` (a partir de main) +
  **um** PR no fim. Padrão single-branch-para-trabalho-faseado, provado na
  remediação.
- Waves paralelas executam em **worktrees isolados com venv próprio** (gate
  anti-trap: confirmar `engine.__file__` dentro da worktree antes de rodar
  testes — o editable-install aponta pro repo principal). Cada wave merja
  `--no-ff` na branch de campanha **serialmente**, com doc-sync no mesmo merge.
- gh auth = `thgMatajs` verificado antes de cada push (drift thgPacheco↔thgMatajs
  reincide).

## 4. Fases

### Fase 0 — Fundação (serial)

A fronteira de execução externa é dependência das duas faces do Tema 6; e
`verify.py` precisa estar limpo antes de o Tema 6 construir sobre ele.

- **0a — Decisão 33 (ritual de NOVA decisão).** Append em
  `docs/design/01-decisions.md` + entrada em `CHANGELOG.md` + referência no
  commit body. Texto da decisão: *o engine pode executar binários externos do
  projeto consumidor (linters, build tools) via uma fronteira de execução
  dedicada, distinta do sandbox de validators da Decisão 30. Garantias: modo
  check read-only onde aplicável; env reduzido; timeout por gate com estouro →
  `degraded`; skip-se-ausente; sem auto-fix; sem instalar toolchain.* A Decisão
  30 segue valendo integralmente pro sandbox de validators — a 33 é fronteira
  separada, não afrouxa a 30.
- **0b — Helper de fronteira de execução externa (TDD).** Runner de subprocess
  reusável pra binário externo: descoberta (gradle/SwiftPM wrapper → chave em
  `forge-config.yaml` → `which` no PATH), env reduzido espelhando o de
  `engine/verify.py`, timeout configurável, classificação `degraded` (ausente
  ou estourado), skip-se-ausente com aviso mentor-calmo. Base reusada por A1 e A2.
- **0c — verify-log scope dict/string.** Primeiro INVESTIGAR
  (`superpowers:systematic-debugging`) se a divergência entre
  `_write_verify_log_entry` (escreve dict) e `append_verify_log` (valida string)
  é bug real latente. Se for, corrigir com regression test falhando primeiro; se
  não, documentar a intenção. Feito na Fase 0 porque toca `verify.py`, que o
  Tema 6 vai estender.

### Fase 1 — Fan-out paralelo (tracks concorrentes em worktrees)

- **Track A — Tema 6** (serial interno; ambas as faces entram via `verify`,
  reusando o helper 0b):
  - **A1 — Native gate ktlint** via `./gradlew ktlintCheck`. Informativo
    (não-reprovante no default), skip-se-ausente, saída estruturada
    (`--reporter=json`) → sumário do `verify`, `degraded` quando ausente/estourado.
  - **A2 — Runtime build-only** (`./gradlew assembleDebug` / `xcodebuild`
    conforme stack detectada no init) como step do `verify`, reusando o helper
    0b; `degraded` sem toolchain. Documenta que o build ESCREVE artefatos no
    working tree do projeto (esperado; o forge não versiona nem limpa).
- **Track B — Papercuts** (file-disjunto de `verify`):
  - upgrade ignora flags desconhecidas → aviso (não-fatal).
  - discovery cache content-fingerprint (hardening sobre o cache do replay).
  - BUG-1b: dedup `compose_backend_axes` na função W7.4 deferred.
- **Track C — Limpeza mem (Fase 1 follow-on):**
  - `_KNOWLEDGE_KINDS` cobre `convention-refinement` / `decay-signal` /
    `question-elimination` (hoje `NotImplementedError`).
  - rename `apply_proposal_to_l2` (ripple em callers/tests — sweep semântico).
  - remover `engine/memory/l3.py` órfão (clean-break; confirmar zero consumidores
    de produção por grep antes).
- **Track D — P2 polish** (itens 16-21 do report): progress feedback nos steps
  longos do init; graph "did-you-mean" no Q4; SIGPIPE/EOF no loop do evolve;
  reconfigure imprime dashboard só no 1º passo; `--help` em todos os subcomandos;
  undo exit 0 em no-op de `last` + aviso de escopo no `rebuild-templates`.

Tracks B/C/D são file-disjuntos de A e majoritariamente entre si → dispatch
concorrente em worktrees. Dentro de um track, tasks que compartilham arquivo
serializam.

### Fase 2 — Docs holistic + sync final (serial, após todas as waves merjadas)

- `docs/design/00-vision.md`: mem como substrato de conhecimento (a campanha mem
  substituiu memory L1/L2/L3 — o framing "memory L1-L5" está stale); registrar a
  camada de verificação de execução (Tema 6) no quadro de layers; framing
  AI-first explícito; revisar Layer 2 (MCP integrations seguem deferidas).
- `docs/design/06-command-surface.md`: novo comportamento do `verify` (gates
  nativos + step build-only).
- `README.md`: stats se mudaram.
- `CHANGELOG.md`: consolidação `[Unreleased]`.
- `04-pending.md`: mover os itens fechados pra Fechados; manter os OUT-OF-SCOPE.
- `mem session` no fim.

## 5. O loop por task (cadência da campanha)

Para cada task: plano → **plan-auditor** (12 checks) → dispatch impl
(`gsd-executor`, TDD) → review (`gsd-code-reviewer`, zero-tolerância, 11
dimensões + Caminho A/B/C por finding) → fix (`gsd-code-fixer`) → re-review → fix
→ **auditoria final** (READY_TO_MERGE) → fix se preciso → **checkpoint** (merge
`--no-ff` na branch de campanha + doc-sync no mesmo merge + push) → próxima task.
Cap de 3 rodadas de review; rodada 4 → ESCALATE ao usuário.

## 6. Gates / definition of done

- Por wave: `.venv/bin/pytest` verde (o canônico — tem json5 + deps) + `forge
  verify` sem hard fail + reviewer assinou (sem high/critical) + doc-sync no mesmo
  commit. Count de testes não regride sem justificativa no commit body.
- Decisão 33: ritual respeitado (append-only em 01-decisions; texto literal no
  CHANGELOG; "Nova decisão 33" no commit body).
- **Full-lane** (rapid + integration + e2e) antes do PR final — `verify`/`init`
  foram tocados; a raia rápida sozinha mascara regressão.

## 7. Riscos / decisões em aberto

- **Tema 6 não é e2e-testável no repo do forge** — não há projeto Kotlin/iOS real
  aqui. Os testes usam fixtures + subprocess mockado; a validação end-to-end real
  é o **re-piloto** contra o MeoBonsai. Isso é esperado e está consistente com o
  faseamento das specs irmãs ("provar valor contra consumer real antes de subir
  de nível").
- **verify-log (0c)** pode acabar não sendo bug — nesse caso a task degrada pra
  doc, sem fix de código.
- **Nível inicial do Tema 6 é decisão de produto** já batida: Nível 1 de cada
  (ktlint check + build-only). Níveis 2/3 (detekt/swiftlint, smoke/screenshot)
  ficam pra depois do re-piloto provar a fronteira.

## Cross-refs

- Backlog: `docs/design/04-pending.md §Piloto MeoBonsai 2026-06-25 §Follow-on`.
- Specs irmãs (fronteira de execução externa): `2026-06-30-native-quality-gates-design.md`,
  `2026-06-30-runtime-visual-verification-design.md`.
- Decisão 30/31 (sandbox Python-only): `docs/design/01-decisions.md`.
- Report do piloto: `docs/reports/2026-06-25-piloto-meobonsai-gaps.md §Tema 6`.
