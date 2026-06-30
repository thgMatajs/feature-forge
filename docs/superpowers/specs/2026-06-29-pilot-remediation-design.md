# Remediação do piloto MeoBonsai — design spec

> **Spec, não plano de execução.** Aterra o backlog de correção que sobrou do
> piloto end-to-end (MeoBonsai, 2026-06-25) depois que a campanha mem fechou os
> temas de footprint/namespace/memória. Organiza os gaps ABERTOS em ondas,
> lideradas pelo loop de correctness. Cada onda vira um plano próprio via
> `superpowers:writing-plans`; esta spec é upstream dos planos.
> **Voz:** mentor calmo. **Status:** design pré-implementação.
> **Data:** 2026-06-29.

---

## Contexto e objetivo

O piloto IA-first do `forge` contra o MeoBonsai (KMP real — Android/iOS/shared,
~519 arquivos / 4582 símbolos) achou ~37 bugs em **8 temas cross-cutting**.
Registro durável: `docs/reports/2026-06-25-piloto-meobonsai-gaps.md`.

O veredito do piloto foi nítido: a **plumbing IA-first está sólida e provada**
(intent loop em stdout + exit 2 + response via arquivo, idempotência por
consumed-log, sem stdin em nenhum dos 14 comandos). A distância para "100%
IA-first" **não é de protocolo — é de substância e orquestração**: gates que
deveriam morder não mordem (verify verde inerte, koin cegando a cascade), gates
que não existem (impl-vs-spec, verificação runtime), e perf de init que bloqueia
o primeiro contato.

Desde o piloto, a **campanha mem (Fase 1, PR#32 MERGED em main, merge-commit
`03a9f9c`)** fechou os temas que dependiam do substrato de memória:
footprint/namespace (Tema 2), o motor de assimilação de convenção (Tema 3,
substrato), e os sub-intents quebrados da memory (Tema 4 parcial). Verificação
empírica também mostrou que **Tema 7 (orquestração da DAG) e BUG-A (doctor
schema-version) já estão fechados em main** por outras correções — o report os
tratava como abertos.

**Objetivo deste spec:** organizar o que o mem **não** toca — o track de
**correctness / orquestração de gate / performance estrutural** — em ondas
executáveis, lideradas pelo loop de correctness (o gap que deixa o "verde"
mentir). Fonte viva do backlog: `docs/design/04-pending.md` §"Piloto MeoBonsai
2026-06-25 — gaps". Esta spec é o plano de ataque por cima dela.

---

## Estado de partida (inventário verificado 2026-06-29)

A fonte viva é `docs/design/04-pending.md` §"Piloto MeoBonsai 2026-06-25 —
gaps", verificada contra o código de main pós-merge. Resumo:

- **Fechados (não entram em onda):** BUG-A (doctor schema-version,
  `engine/doctor.py:440` + `engine/init.py` gravam int), BUG-IMPL-1/Tema 7
  (`engine/implement.py` avança a DAG — `_pick_next_task` L374, deps+ciclo L361,
  checkpoint `task-id` L142), BUG-MEM-1/2 (`engine/memory_cli.py` reescrito em
  W-ROUTE 6a), BUG-1 (poda inline `_SKIP_DIRS` em `engine/detection/_eval.py:72`).
- **Parciais (entram onde fizer sentido):** BUG-1b, BUG-QA-4, BUG-UPGRADE-1,
  BUG-4/MEM-5.
- **Abertos (o objeto desta spec):** Tema 6 / BUG-VERIFY-1/2 (P0 #1), BUG-5,
  BUG-2, BUG-PLAN-1, BUG-G2, BUG-STATUS-1/2, BUG-IMPL-2, BUG-B + os P2 de polish.

> Não re-litigar os fechados. Se uma onda tocar um deles, é regressão a evitar —
> não trabalho a refazer.

---

## Ondas

A correção rola em 5 ondas. As Ondas 1-4 são o track de correctness/perf/
hardening (escopo desta spec). A Onda 5 é aditiva e paralela (mem Fase 2), só
referenciada. A liderança da Onda 1 é deliberada: é o gap que faz o "verde"
mentir, e sem ele as outras correções não têm como provar que funcionaram.

### Onda 1 — Loop de correctness (P0 #1, Tema 6)

**Objetivo:** dar dentes reais ao verify e fechar o loop impl-vs-spec, para que
"verde" pare de mentir. É a alavanca de maior valor: enquanto o verify reporta
garantia que não existe, toda outra correção fica sem prova observável.

**Itens (file:line de partida):**

- **BUG-VERIFY-1 — validator quebrado cega a cascade.** `engine/verify.py:985`
  trata exit 2 (argparse error / "unrecognized arguments") como `fail`; a
  fail-fast (Decisão 23) para a cascade e cega 5 validators iOS/KMP. Fix:
  classificar validator-quebrado como **`degraded`** (distinto de "código
  reprovado") e NÃO parar a cascade por ele. Atualizar `check-koin-modules.py:100`
  ao contrato canônico (`--scope`/`--id`, não `--root`).
- **BUG-VERIFY-2 — sumário honesto de cobertura.** Falta o sumário tipo
  "Pass: 10 — 6 stub no-op, 4 sem staged". Fix: o `forge verify` reporta
  cobertura substantiva, não só contagem de "pass".
- **BUG-VERIFY-3 — verify escopado ao diff da feature.** Warns Compose varrem o
  repo inteiro; escopar ao diff da feature.
- **Vetor impl-vs-spec no qa.** O qa red-teia contratos (spec-vs-spec), não o
  diff da implementação — um bug que viola o spec correto passa. Fix: adicionar
  vetor impl-vs-spec.
- **Quality gates nativos.** Rodar os gates do projeto (ktlint/detekt/swiftlint)
  — pegaram problemas reais que o forge não pegou.
- **Ao menos um nível de verificação runtime/visual.** Nenhum dos 14 comandos
  faz verificação de execução; estabelecer o primeiro nível.

**Gate de aceite (verde antes de pronto):**

- `.venv/bin/pytest` verde (lane completa) + `forge verify` sem hard fail.
- Teste de regressão: um validator que sai com exit 2 (argparse error) produz
  veredito `degraded` e **não** interrompe a cascade — os validators a jusante
  rodam. (Reproduz BUG-VERIFY-1 vermelho ANTES — TDD.)
- `check-koin-modules.py` invocado com `--scope feature --id <slug>` roda limpo
  (contrato canônico).
- O sumário de cobertura do `forge verify` distingue pass-substantivo de
  stub-no-op / staged-blind (observável no `--json`).

### Onda 2 — Gates com dentes (Tema 1)

**Objetivo:** portar a mecânica determinística do **plan-auditor** (12 checks)
para os gates de wave do plan no pipeline do **consumidor** — content-check leve
nas waves, não só "0 placeholders" superficial. Agora **FACTÍVEL** porque o mem
curou as rules do consumidor (o substrato era o pré-requisito): o auditor pode
consultar o acervo via `mem find` para ancorar os checks na convenção real.

**Itens (file:line de partida):**

- **Tema 1 — gates procedurais, não substantivos.** O plan-auditor (C1/C2
  critical, H1-H4, M1-M3, L1-L3) roda nos planos do próprio repo feature-forge,
  mas NÃO no pipeline do consumidor. O gate de wave do `engine/plan.py` checa
  presença (placeholders, status), não substância. Fix: content-check
  determinístico nas waves do plan do consumidor (tech-spec com §3-§7 ainda em
  stubs, `dependency_graph/critical_path` como `[]` default — o piloto pegou os
  dois passando pelo gate superficial).

**Gate de aceite:**

- `.venv/bin/pytest` verde + `forge verify` sem hard fail.
- Teste: um plano de wave do consumidor com tech-spec parcialmente preenchida
  (stubs `{{...}}` em §3-§7) ou `dependency_graph: []` é PEGO pelo content-check
  (verdict diferente de "pass") — reproduz o escape do piloto vermelho ANTES.
- A mecânica reusa a do plan-auditor (não reinventa os 12 checks).

### Onda 3 — P0s estruturais restantes

**Objetivo:** desbloquear o primeiro contato (perf do init) e tirar o crash do
gate de readiness do plan.

**Itens (file:line de partida):**

- **BUG-5 — rglob sem poda no hot-path de inventory.**
  `engine/inventory/design_system.py:444`, `conventions.py:308`, `i18n.py:101`
  (rglob cru antes do skip). Fix: **extrair helper compartilhado
  `_walk_recursive_pruned`** (poda `_SKIP_DIRS` na descida) e trocar todos os
  sites. **Reuso-first:** é extração compartilhada, não duplicação — checar a
  branch `fix/pilot-init-perf` (commit `4649d78`), que já tem uma versão do
  helper pronta para cherry-pick em vez de reimplementar do zero.
- **BUG-2 — discovery não cacheado no checkpoint.** `engine/init.py:190` re-roda
  ~220s a cada invocação (~18 min em 5 invocações; ~33 min wall total). Fix:
  cachear o resultado de discovery no checkpoint e reusar quando há response
  pendente.
- **BUG-PLAN-1 — recursão no gate de readiness.** `engine/plan.py:1058`: path A
  recursa síncrono (~979 níveis → RecursionError, exit 1 + 1.3MB stdout). Fix:
  re-renderizar + **PAUSAR (exit 2)** para o host ajustar — nunca recursar.
- **Decisão de housekeeping:** mergear-ou-descartar a branch `fix/pilot-init-perf`
  (o BUG-1 já foi fechado em main por impl diferente; o valor restante da branch
  é o helper para o BUG-5).

**Gate de aceite:**

- `.venv/bin/pytest` verde + `forge verify` sem hard fail.
- BUG-5: um único helper `_walk_recursive_pruned` é a fonte; grep confirma que
  os 3 sites de inventory + o `_glob_any` chamam o mesmo helper (sem rglob cru
  no hot-path).
- BUG-2: re-invocar o init com response pendente NÃO re-paga discovery
  (observável: o checkpoint carrega o resultado cacheado; tempo de re-invoke cai
  de ~220s para sub-s no passo de discovery).
- BUG-PLAN-1: responder `a` num readiness=partial re-renderiza e sai com exit 2
  (pausa), nunca RecursionError. Reproduz o crash vermelho ANTES (TDD).

### Onda 4 — Hardening P1

**Objetivo:** fechar a fricção IA-first séria e os papercuts de protocolo/
segurança/visibilidade.

**Itens (file:line de partida):**

- **BUG-STATUS-1/2 — status cego ao git/qa.** `engine/status.py:47` não
  reconcilia com git nem expõe qa verdict (commits da feature invisíveis, BLOCK
  sem rastro). Fix: reconciliar com o git e sinalizar descompasso; persistir e
  expor o qa verdict.
- **BUG-G2/MEM-4 — marker sem `response-schema-version`.**
  `engine/host/adapters/claude_code.py:422`: o `<FORGE_INTENT>` não anuncia o
  `response-schema-version` exigido na resposta. Fix: anunciar no marker (ou
  aceitar ausência como default 1).
- **BUG-UPGRADE-1 — upgrade destrutivo sem preview.** Sem `--dry-run` nem guard
  de branch antes do `checkout --detach` no FORGE_HOME. Fix: `--dry-run` +
  guard ("você está em `fix/...`, não numa release — continuar?").
- **BUG-4/MEM-5 — `.gitignore` incompleto.** Cobre `state/` + checkpoints;
  faltam `graph.db`, `cards/`, `memory/`, `locks/`, `.memory-cli-checkpoint.yaml`.
  Fix: cobrir todos os artefatos derivados do init.
- **BUG-IMPL-2 — build commands hardcoded.**
  `cards/swiftui-screens/templates/swiftui-allowed-files.yaml:59`
  (`run-ios-simulator.sh --build-only`); idem `testDebugUnitTest` no kotlin
  (KMP usa `testAndroidHostTest`). Fix: derivar do projeto (ler `gradlew tasks`).
- **BUG-B — version-lock path mismatch.** `engine/init.py:2654` grava em
  `.claude/forge/` mas `engine/doctor.py:881` lê em `.claude/` → check morto.
  Fix: alinhar o path de leitura/escrita.
- **BUG-QA-4 — SKILL.md não cobre todos os verbos.** SKILL.md cobre o intent
  loop, não os prompts de qa/verify/memory/reconfigure/upgrade/undo. Fix:
  expandir o mapa de verbos do SKILL.md instalado.

**Gate de aceite:**

- `.venv/bin/pytest` verde + `forge verify` sem hard fail.
- BUG-STATUS: `forge status` numa feature commitada reflete os commits do git e
  o qa verdict (observável no `--json`).
- BUG-G2: um host que omite `response-schema-version` é orientado pelo marker
  (ou aceito como default) — não toma exit 1 silencioso.
- BUG-UPGRADE-1: `forge upgrade --dry-run` faz preview sem mutar git; sem
  `--dry-run` numa branch não-release, o guard pausa antes do checkout.
- BUG-B: round-trip init→doctor lê o version-lock no mesmo path (check vivo).

### Onda 5 (paralela, aditiva) — mem Fase 2 (curadoria)

**Referência apenas** (escopo da spec mem §Fase 2, não desta): curadoria ativa
de convenção — web/init-enrich, evolve→rules, comando `rules-update`. Roda em
paralelo às Ondas 1-4 porque é aditiva (não toca o track de correctness). Tema 3
do report (assimilação de convenção) fecha aqui.

### P2 polish — dobrar nos pontos baratos

Os itens 16-21 do report (progress feedback no init; graph did-you-mean no Q4;
evolve SIGPIPE/EOF; reconfigure dashboard só no 1º passo; `--help` em todos os
subcomandos; undo exit-0 em no-op + raw aviso de escopo) não têm onda própria.
Dobre-os no commit da onda mais próxima do arquivo tocado — barato quando já se
está no arquivo, desperdício de contexto quando isolado.

---

## Princípio de execução

Mesma forma da campanha mem: **um spec → um plano por onda
(`superpowers:writing-plans`) → plan-auditor antes do "Execution Handoff" →
executor → review (`gsd-code-reviewer`, zero-tolerância) → verify**. Esta spec é
**upstream** dos planos: cada onda vira um plano próprio (ex.:
`docs/superpowers/plans/2026-06-29-pilot-onda1-correctness.md`), auditado antes
do handoff.

Disciplinas que valem em toda onda:

- **Verde antes de pronto (Mandamento #2):** `pytest` full verde + `forge verify`
  sem hard fail + reviewer assinou off. Count não regride sem justificativa no
  commit body.
- **TDD (Mandamento #2):** cada bugfix começa com regression test FALHANDO
  (reproduz o bug vermelho) antes do fix. Os gates de aceite acima já enunciam
  o vermelho-antes.
- **Reuso antes de criar (Mandamento #3):** na Onda 3, `_walk_recursive_pruned`
  é extração compartilhada — não duplicar; checar `fix/pilot-init-perf` para
  cherry-pick. Na Onda 2, reusar a mecânica do plan-auditor (não reinventar os
  12 checks).
- **Escopo contido (Mandamento #4):** cada plano edita só os arquivos da sua
  onda; os fechados (Tema 7, BUG-A, BUG-MEM, BUG-1) são regressão a evitar, não
  trabalho a refazer.
- **Doc-sync (Mandamento #6):** ao fechar cada onda, atualizar
  `docs/design/04-pending.md` (mover o item de ABERTO → fechado) + CHANGELOG no
  MESMO commit.
