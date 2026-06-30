# Plano — Onda 1: loop de correctness (P0 #1, Tema 6)

> **Plano executável**, derivado de `superpowers:writing-plans`.
> **Spec upstream:** `docs/superpowers/specs/2026-06-29-pilot-remediation-design.md` §"Onda 1".
> **Report-mãe:** `docs/reports/2026-06-25-piloto-meobonsai-gaps.md` §Tema 6.
> **Branch:** `docs/pilot-remediation`.
> **Voz:** mentor calmo. **Status:** pré-implementação (aguarda plan-auditor antes do handoff).
> **Data:** 2026-06-29.

---

## Objetivo

Dar dentes reais ao `forge verify` para que o "verde" pare de mentir. Hoje um
validator quebrado (off-contract) cega cinco validators iOS/KMP a jusante via
fail-fast, e o sumário do verify conta dez "pass" sem distinguir substância de
stub no-op / staged-blind. Esta onda fecha **os itens do gate de aceite** —
não o tema inteiro.

**Escopo deste plano (gate-bound, o que entra):**

1. **BUG-VERIFY-1** — validator quebrado deixa de cegar a cascade.
2. **Contrato canônico do koin** — `check-koin-modules.py` aceita
   `--scope`/`--id`/`--project-root`.
3. **BUG-VERIFY-2** — sumário honesto de cobertura (substantivo vs stub-no-op),
   observável no `--json`.

**Fora do escopo deste plano (vê §"Riscos & decisões em aberto"):** o vetor
impl-vs-spec no qa, os quality gates nativos (ktlint/detekt/swiftlint), o
primeiro nível de verificação runtime/visual, e BUG-VERIFY-3 (escopar warns ao
diff). São itens da spec mas **não** estão no gate de aceite; cada um é
substancial o bastante pra merecer plano/spec próprio. Mistura-los aqui
inflaria o plano além de um ciclo coeso (Mandamento #4 + YAGNI).

**Por que liderar com isto:** enquanto o verify reporta garantia que não
existe, toda outra correção das Ondas 2-4 fica sem prova observável.

---

## Estado do código (scout verificado 2026-06-29)

O scout read-only confirmou o terreno — registrado aqui pra o executor não
re-explorar:

- **O enum de status JÁ tem `degraded`.** `engine/verify.py:88` declara
  `"pass" | "warn" | "fail" | "skipped" | "degraded"`. As três condições de
  infra-quebrada (script ausente L933-938, timeout L969-975, OSError L976-981)
  JÁ retornam `degraded`. O glyph existe (`_STATUS_GLYPH`, L1038). O `degraded`
  NÃO é contado como hard fail em lugar nenhum (`overall` só olha
  `status == "fail"`, L401-404) — portanto **não para a cascade** (L909 só
  halta em `fail`). **Consistente com a Decisão 23** (halt em erro de CÓDIGO,
  não em quebra de infra).
- **O bug exato** está em `engine/verify.py:984-998`: quando o validator NÃO
  emite JSON tail, o exit-code mapeia `0→pass / 1→warn / else→fail`. Logo
  **exit 2 (argparse "unrecognized arguments") vira `fail`** → halta a cascade.
  É esse ramo `else→fail` que precisa virar `else→degraded` (validator quebrado
  ≠ código reprovado).
- **O contrato canônico de validator** vive em
  `validators/_common.build_argparser` (L147-172): `--project-root` / `--scope`
  {task,feature,inferred} / `--id`. `emit_and_exit` (L188-200) imprime JSON tail
  e usa exit 0=pass / 2=warn / 1=fail. O harness invoca cada validator com
  `--project-root <root> --scope <kind> --id <target>` (`verify.py:952-956`).
- **O koin está off-contract.** `cards/koin-annotations/validators/check-koin-modules.py`
  usa `argparse.ArgumentParser()` cru com `--root` / `--dsl-check` (L97-101).
  Recebe `--project-root/--scope/--id` → argparse exit 2 → sem JSON tail →
  hoje `fail` → halta. É o gatilho do BUG-VERIFY-1.
- **O sumário** é `_render_summary` (`verify.py:1065-1081`): conta
  pass/warn/fail/skipped/degraded mas NÃO distingue pass-substantivo de
  stub-no-op nem de staged-blind. O `--json` payload (`verify.py:422-428`)
  serializa cada `_ValidatorResult` via `asdict` — qualquer campo novo no
  dataclass aparece automaticamente no JSON.
- **A forma do stub no-op** está confirmada (ex.:
  `cards/firebase-auth/validators/check-auth-test-ids-canonical.py`): imprime
  `"STUB Phase 5"` + `"no-op"` em stderr, `return 0`, **sem JSON tail**. São 6
  desses (firebase/firestore/crashlytics/auth + koin enquanto stub).
- **Testes de verify** existentes: `tests/unit/test_commands_verify.py`,
  `tests/unit/test_verify_json.py` (asserta `payload["validators"][n]["status"]`
  e `overall`/`exit_code`), `tests/unit/test_engine_verify_resume.py`. O fixture
  `tmp_forge_project` roda os built-in validators dentro do próprio repo.

---

## Reuso-first (Mandamento #3 — antes de criar)

- **NÃO** reescrever o koin do zero. Migrar pro `validators/_common`:
  `build_argparser` + `run_cli`/`emit_and_exit` + `result_pass`/`result_fail`
  + `make_paths`. O scout confirmou que esses helpers existem e cobrem
  exatamente o contrato exigido.
- **NÃO** criar um enum/status novo pra "validator quebrado" — `degraded` já
  existe e já tem a semântica certa (não-hard, não-halta). Só estender o ramo
  de mapeamento exit-code.
- A infra compartilhada de validators (`_gate_infra` / `_diff` / `_common`) é
  preferível a copiar. O koin é um stub textual simples (regex), então só
  precisa de `_common` (argparser + result shape); `_gate_infra`/`_diff` não
  se aplicam aqui.
- O sumário honesto reusa `_render_summary` + o dataclass `_ValidatorResult`
  existente — estender, não substituir.

---

## Tasks

Ordem é dependência real: T1 (degraded) é o coração e desbloqueia o teste de
cascade; T2 (koin) é o caso concreto que T1 protege e fecha a prova
end-to-end; T3 (sumário) é ortogonal mas fecha o BUG-VERIFY-2 do gate. T1→T2
têm acoplamento de prova (o teste de regressão de T1 usa um validator
exit-2); T3 é independente e pode rodar em paralelo lógico, mas é um arquivo
compartilhado (`verify.py`), então roda sequencial pós-T1 pra evitar conflito
de edição.

---

### Task 1 — `degraded` para validator quebrado (não cega a cascade)

**Objetivo / fecha:** BUG-VERIFY-1 (parte engine). Classificar validator que
sai com exit-code ≠ {0,1} **e sem JSON tail** como `degraded`, não `fail` —
distinguindo "validator quebrado" (infra) de "código reprovado" (gate).
`degraded` não halta a cascade, então os validators a jusante rodam.

**Arquivos permitidos para EDIT:**
- `engine/verify.py` (só o ramo de mapeamento exit-code em `_invoke_validator`,
  L984-998, e — se preciso pra clareza — o docstring que diz "0 pass, 1 warn,
  2 fail").
- `tests/unit/test_commands_verify.py` (adicionar o teste de regressão).

**TDD — o teste que começa VERMELHO:** em `tests/unit/test_commands_verify.py`,
adicionar `test_broken_validator_degrades_not_halts_cascade`:
- Cria dois validators temporários (escritos no fixture / tmp, via cards
  snapshot OU invocando `_run_cascade`/`_invoke_validator` direto com
  `_ValidatorSpec` apontando pra scripts de teste):
  - validator-A: script que faz `import argparse; argparse cru` e sai com
    **exit 2** ao receber `--scope`/`--id` (reproduz o koin off-contract), sem
    JSON tail;
  - validator-B: script trivial que sai 0 (pass).
- Asserta:
  1. O resultado de validator-A tem `status == "degraded"` (hoje: `fail` →
     **vermelho**).
  2. validator-B **rodou** (não veio `skipped`) — i.e. a cascade NÃO halt
     (hoje: halta porque A é `fail` → B vem `skipped` → **vermelho**).
  3. `overall` resultante NÃO é `fail` por causa de A (degraded não conta como
     hard fail). Se B passa e nada mais falha, `overall == "pass"`.
- Preferir testar via `_run_cascade([specA, specB], fail_fast=True, ...)` —
  é o nível certo (unit, determinístico, sem depender de cards reais).

**Critério de sucesso (testável, do gate de aceite):**
> Um validator que sai com exit 2 (argparse error) produz veredito `degraded`
> e **não** interrompe a cascade — os validators a jusante rodam.

**Anti-padrões / escopo:**
- NÃO mexer no ramo JSON-tail (`status == "error" → fail`, L1000-1002) — esse
  é veredito estruturado legítimo do validator, não infra quebrada. O degraded
  é só pro caso **sem** JSON tail com exit-code anômalo.
- NÃO tocar a Decisão 23 nem `_resolve_fail_fast` — fail-fast continua haltando
  em `fail`. A mudança é o que conta como `fail`, não a política da cascade.
  (Vê §"Riscos & decisões em aberto" pra a nota de clarificação sobre Decisão
  23.)
- NÃO renomear `degraded` nem alterar `_STATUS_GLYPH`.
- NÃO tocar `verify.py` fora de `_invoke_validator`.

---

### Task 2 — koin ao contrato canônico (`--scope`/`--id`/`--project-root`)

**Objetivo / fecha:** BUG-VERIFY-1 (parte card). Migrar
`check-koin-modules.py` de `--root` (argparse cru) pro contrato canônico via
`validators/_common`. Depois desta task, o koin roda limpo quando o harness o
invoca — e o degraded de T1 vira a rede de segurança, não a regra.

**Arquivos permitidos para EDIT:**
- `cards/koin-annotations/validators/check-koin-modules.py` (única edição de
  produção).
- `tests/validators/test_check_koin_contract.py` (novo — teste de contrato).

**TDD — o teste que começa VERMELHO:** novo
`tests/validators/test_check_koin_contract.py`:
- `test_koin_accepts_canonical_flags`: invoca o script como subprocess (ou
  `main()` com argv monkeypatched) com
  `--project-root <tmp> --scope feature --id <slug>` e asserta que **NÃO** sai
  com exit 2 / "unrecognized arguments" (hoje: argparse morre → **vermelho**).
- `test_koin_emits_json_tail_on_pass`: num tmp project sem violações koin,
  asserta exit 0 + última linha de stdout é JSON com `"status": "pass"` (hoje:
  o stub só retorna 0 sem JSON tail → **vermelho** no assert do JSON).
- `test_koin_reports_failure_with_3paths` (se a checagem detectar `@Module` sem
  `@ComponentScan`): asserta `status == "fail"` + 3 paths no JSON
  (`result_fail` exige exatamente 3 — `_common` já enforça).

**Critério de sucesso (testável, do gate de aceite):**
> `check-koin-modules.py` invocado com `--scope feature --id <slug>` roda limpo
> (contrato canônico).

**Reuso-first:** usar `validators/_common.build_argparser`,
`run_cli`/`emit_and_exit`, `result_pass`, `result_fail`, `make_paths`.
Preservar a lógica de checagem existente (`check_module_componentscan_pair`,
`check_dsl_banned_in_production`, `is_production_path`) — é só trocar a casca
do `main()` e emitir JSON em vez de só `return`.

**Decisão de design dentro da task (documentar no commit body):** o `--root`
era a raiz a escanear; o canônico é `--project-root`. O `--dsl-check` era flag
posicional do card — preservar como `extra_args` (o `_common.run_cli` aceita
`extra_args` callable). O scope (`--scope feature --id slug`) é informacional
pro koin v1 (ele escaneia o root inteiro) — registrar como TODO-Phase-5
escopar ao diff da feature (alinha BUG-VERIFY-3, fora desta onda).

**Anti-padrões / escopo:**
- NÃO transformar o stub textual em parser tree-sitter (é TODO Phase 5,
  out-of-scope — over-engineering).
- NÃO tocar os outros 5 stubs no-op (firebase/firestore/crashlytics/auth) —
  são da Task 3 só como contagem, não como reescrita.
- NÃO mudar `card.yaml` do koin a menos que o nome do validator mude (não
  muda).

---

### Task 3 — sumário honesto de cobertura (substantivo vs stub vs staged-blind)

**Objetivo / fecha:** BUG-VERIFY-2. O `forge verify` reporta cobertura
substantiva, não só contagem de "pass". Distinguir, observável no `--json`:
pass-substantivo / stub-no-op / staged-blind / degraded.

**Arquivos permitidos para EDIT:**
- `engine/verify.py` (`_ValidatorResult` dataclass + `_render_summary` +
  o payload `--json` se precisar de campo agregado).
- `tests/unit/test_verify_json.py` (asserts do novo campo).

**TDD — o teste que começa VERMELHO:** em `tests/unit/test_verify_json.py`,
adicionar `test_json_summary_distinguishes_substantive_from_stub`:
- Roda verify com um mix: ≥1 validator stub-no-op (sem JSON tail, exit 0,
  marcador stub) + ≥1 validator substantivo (JSON tail `status=pass`).
- Asserta que o payload distingue os dois — campo novo por-validator
  (ex.: `"substantive": false` no stub vs `true`/ausente no real) OU bloco
  agregado `"coverage": {"pass_substantive": N, "stub_noop": M,
  "staged_blind": K, "degraded": J}` (hoje: ambos contam só como `pass` →
  **vermelho**).

**Decisão de design dentro da task (documentar no commit body + escolher 1 das
3):** como o verify distingue stub-no-op de pass-substantivo? Três caminhos —
o executor escolhe o **(A)** salvo se houver impedimento, e justifica:
- **(A) Validator auto-declara** (preferido, disciplinado): stubs emitem JSON
  tail `{"status":"pass","substantive":false,"message":"stub no-op Phase 5"}`.
  Verify lê `substantive` do payload. Custo: tocar os 6 stubs pra emitir o
  campo (edição mecânica, 1 linha cada). Vantagem: fonte da verdade é o
  validator, não heurística frágil.
- **(B) Heurística no verify**: detectar "STUB"/"no-op" no `message`/stderr +
  ausência de JSON tail → marcar `substantive=false`. Custo: zero edição nos
  stubs. Risco: frágil (acoplado ao texto), pode dar falso-positivo.
- **(C) Registro declarativo**: marcar stubs no `card.yaml`
  (`severity: stub` ou `coverage: none`) e verify lê do spec. Custo: tocar
  card.yaml dos 6. Risco: drift card.yaml ↔ script.

> **Nota de escopo:** se o caminho (A) for escolhido, os 6 stubs entram na
> whitelist de EDIT desta task (`cards/*/validators/check-*.py` dos 6
> firebase/firestore/auth + o koin já migrado em T2). Se passar de ~6 arquivos
> mecânicos, NÃO inflar — reportar pro orquestrador e considerar split.

**Critério de sucesso (testável, do gate de aceite):**
> O sumário de cobertura do `forge verify` distingue pass-substantivo de
> stub-no-op / staged-blind (observável no `--json`).

**Anti-padrões / escopo:**
- NÃO implementar staged-blind como detecção nova de git nesta task se for
  caro — o "staged-blind" hoje é os 4 built-in que olham staged numa feature
  commitada. Marcar como categoria observável é suficiente pro gate; a
  correção do staged-blind em si (escopar ao diff) é BUG-VERIFY-3, fora desta
  onda. Documentar a linha divisória no commit body.
- NÃO mexer no exit-code nem no `overall` — o sumário é observabilidade
  read-only, não muda o veredito.

---

## Gate de aceite (verde antes de pronto — Mandamento #2)

- [ ] `.venv/bin/pytest` verde (lane completa — `.venv/bin/pytest` é o
      canonical; system pytest dá falso negativo por falta de json5).
- [ ] `forge verify` sem hard fail no próprio repo.
- [ ] **T1:** teste de regressão — validator exit 2 → `degraded` + cascade NÃO
      halta (validators a jusante rodam). Vermelho ANTES do fix.
- [ ] **T2:** `check-koin-modules.py --scope feature --id <slug>` roda limpo +
      emite JSON tail.
- [ ] **T3:** `--json` distingue pass-substantivo de stub-no-op.
- [ ] Count de testes não regride (sobe — 3 testes novos no mínimo).
- [ ] Reviewer (`gsd-code-reviewer`, zero-tolerância) assinou off sem
      high/critical.

---

## Doc-sync (Mandamento #6 — no MESMO commit que fecha a onda)

- `docs/design/04-pending.md` — mover BUG-VERIFY-1 e BUG-VERIFY-2 de ABERTO →
  fechado (ou parcial, se T3 escolher caminho B/C com débito). Atualizar o §
  do report apêndice se o estado mudar.
- `CHANGELOG.md` (Unreleased) — entrada `### Fixed` para BUG-VERIFY-1/2.
- Se o comportamento documentado do verify mudou (sumário): conferir
  `docs/ux/forge-verify-roteiro.md` e `docs/design/07-discipline.md §2`
  (cascade) — atualizar se o roteiro de output mudou de forma observável.
- `README.md` — só se algum stat mudou (não deve).

---

## Riscos & decisões em aberto

### 1. Itens da spec FORA deste plano (over-broad — precisam de plano/spec próprio)

A spec lista seis "Itens" pra Onda 1, mas o **gate de aceite** só vincula três
(BUG-VERIFY-1, koin contract, sumário honesto). Os outros três NÃO estão no
gate e são grandes/exploratórios demais pra caber num ciclo coeso sem inflar.
Recomendação — 3 caminhos pro orquestrador/user decidir:

- **(A) Plano próprio por item** (recomendado): cada um vira plano
  independente, depois deste fechar.
- **(B) Onda 1b**: agrupar os três num plano "verify scope + native gates"
  separado.
- **(C) Reescopar a spec**: mover impl-vs-spec + runtime/visual pra uma onda
  nova (são de natureza diferente — qa/execução, não verify-cascade).

Os três, com o scout que justifica o tamanho:

- **Vetor impl-vs-spec no qa** — **substancial.** Hoje os 4 core auditors
  (`_CORE_AUDITORS`, `engine/qa/__init__.py:102-107`) são Phase 1 STATIC:
  leem specs do snapshot e cruzam spec-vs-spec. impl-vs-spec exige (1) novo
  auditor agent `agents/qa-auditor-impl-vs-spec.md` (~150 LOC, espelhando
  `qa-auditor-spec-vs-spec.md`), (2) wiring em `_CORE_AUDITORS` (flui pro
  handoff `auditors` automático), E (3) **plumbing nova no snapshot** — o
  `snapshot_artefacts` (`engine/qa/ingest.py:270`) só copia specs; impl-vs-spec
  precisa do **diff da implementação** no snapshot, o que hoje não existe.
  É feature, não fix de cega. Plano próprio.
- **Quality gates nativos (ktlint/detekt/swiftlint)** — **médio/grande.** São
  novos validators (ou um runner) que invocam ferramentas do projeto
  consumidor. Toca a fronteira "engine roda comando do projeto" (que hoje o
  forge evita — read-only). Decisão de design não trivial (onde rodam? card?
  built-in? como descobrem o binário?). Plano próprio com discovery.
- **1º nível de verificação runtime/visual** — **muito grande + vago.** É o
  item mais amplo da spec; nenhum dos 14 comandos faz execução. NÃO boiler o
  oceano. Recomendação forte: vira **spec própria** (decisão de produto sobre
  o que "1º nível" significa — build? smoke test? screenshot diff?), não tarefa
  de plano. YAGNI até a spec existir.

### 2. Decisão 23 — clarificação, não revisita

O fix de T1 introduz classificar validator-quebrado (argparse exit 2) como
`degraded`, que NÃO halta a cascade. **Avaliação do scout:** isto é
**consistente** com a Decisão 23, não uma revisita. A Decisão 23 diz "halt no
primeiro hard **error** (erro de CÓDIGO)"; um validator que morre por estar
off-contract é quebra de **infra**, não código reprovado. O `degraded` já
existe no enum e já é tratado como não-hard. Logo:

- **NÃO** disparar o ritual "Revisita decisão 23" (append em
  `01-decisions.md` + CHANGELOG) — não há mudança de política.
- **Recomendação (caminho do meio):** adicionar uma **nota de clarificação**
  no commit body e/ou um comentário em `engine/verify.py` explicitando que
  `degraded ≠ fail` e por que isso honra (não fere) a Decisão 23. Se o
  plan-auditor ou o reviewer julgar que a distinção infra-vs-código merece
  registro durável, aí sim escalar pra decisão — mas o default é clarificação.
- 3 caminhos se o reviewer discordar: (A) clarificação em comentário/CHANGELOG
  (default); (B) revisita formal da Decisão 23 com o ritual completo; (C)
  recusar o degraded e tratar exit-2 como warn (não-halta mas conta) — pior,
  porque polui o veredito com falso-warn.

### 3. Caminho de design do sumário (T3)

Aberto entre (A) validator auto-declara / (B) heurística / (C) card.yaml — vê
Task 3. Default (A); se (A) explodir o file-budget (>6 stubs mecânicos),
reportar e considerar split antes de inflar.

### 4. Risco de regressão nos testes de verify existentes

`test_verify_json.py::test_verify_json_clean_project_emits_pass` asserta
`all(v["status"] in ("pass", "skipped"))`. Se T3 adicionar campo por-validator,
o assert continua válido (campo é aditivo). Se algum validator do fixture virar
`degraded` por T1 (não deveria — built-in são canônicos), o assert quebra —
sinal de regressão real a investigar, não de ajustar o teste cegamente.
