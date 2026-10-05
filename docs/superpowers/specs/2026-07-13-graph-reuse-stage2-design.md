# GRAPH-REUSE-STAGE2 — Ampliação do universo de símbolos da reuse-intelligence (advise-only)

> **Status:** draft — design fixado pelo precision spike; acumula na branch `feat/graph-real-repo-readiness`
> **Data:** 2026-07-13
> **Plano:** `docs/superpowers/plans/2026-07-13-graph-reuse-stage2.md` (a escrever)
> **Release-target:** TBD
> **Revisita:** nenhuma decisão locked

---

## Contexto

O re-spike do Stage 1 (G2) contra o `inchurch-app-main` mostrou reuse-findings
= 1 porque a detecção de duplicata Kotlin é travada em extension functions
(`receiver_type IS NOT NULL`, ~198 símbolos elegíveis). O precision spike do
Stage 2 (2026-07-13, probe SQL externo contra o app real) mediu: dropar a trava
+ incluir `kind IN ('fun','composable_fun')` → **89 grupos de dup exata** (87
within-module, 4 cross-module), precisão bruta **64 REAL / 89 = 72%** (0 FALSE —
agrupamento por `body_hash` exato não tem como misgroup; 25 TRIVIAL, todos
pequenos: 24/25 com ≤4 `body_tokens` distintos, 7 são scaffolding de teste). Com
piso `body_tokens` distintos ≥5 (within-module) + cross-module mantido +
exclusão de test source-sets → **~65 grupos, ~98% precisão, 0 REAL perdido**.
Achados reais: fluxo Google-signin copy-pasteado em 2 Activities; `setupToolbar`
em 7 fragments; `resize` em 5 dialogs com base class já tendo a cópia canônica.

---

## Goal

Converter a detecção de dup exata quase-morta (1 finding) em **~65 findings
acionáveis a ~98% de precisão** no app real, ampliando o universo de símbolos
com um piso de trivialidade, roteados pelo pipeline advisory existente
(`reuse_findings → proposed-evolutions`). Sem enforcement. Validação final:
re-spike confirma ~65 findings + precisão amostrada.

---

## Non-goals

- Fix do `kmp-migration` (sub-track SEPARADO — defeito de match cross-lang:
  nome+receiver_type exato entre Kotlin/Swift nunca casa; precisa name-only +
  similaridade ou type-map).
- Similaridade fuzzy/token além do `body_hash` exato.
- Ampliar o `near-duplicate` (same-signature-diff-body).
- QUALQUER enforcement/hard-block — findings são advisory (alinha Decisão 5:
  code review final out-of-scope).
- Refactor dos parsers (gaps `modifiers`/`line_end` são follow-on, não fix).
- Member-functions dentro de classes — o spike mediu top-level `fun` +
  `composable_fun` (os kinds que carregam `body_hash` hoje); membros de classe
  ficam fora deste incremento (não medidos).

---

## Acceptance Criteria

- **AC-1 — Universo ampliado.** As queries de DETECÇÃO em
  `engine/graph/duplicates.py` (`_q_duplicates_within_module`,
  `_q_duplicates_cross_module`) e os equivalentes READ-side em
  `engine/graph/queries.py` deixam de exigir `receiver_type IS NOT NULL` e
  passam a incluir `kind IN ('fun','composable_fun')`. Extension funs (fun com
  receiver) permanecem cobertas. Verificável: fixture com dup de top-level `fun`
  e de `composable_fun` NÃO-extension agora produz finding (hoje não produz);
  dup de extension segue produzindo.
- **AC-2 — Piso de trivialidade.** Constante nomeada `REUSE_MIN_BODY_TOKENS = 5`
  filtra grupos within-module cujo corpo compartilhado tem menos de 5
  `body_tokens` distintos. Grupos CROSS-MODULE (≥2 módulos) NÃO são filtrados
  pelo piso (sinal mais forte; preserva `MutableState.update`, 2 tokens, 3×
  cross android+shared). Verificável: fixture within-module com ≤4 tokens é
  filtrado; ≥5 mantido; cross-module com 2 tokens mantido.
- **AC-3 — Exclusão de teste.** Símbolos em test source-sets
  (`commonTest`/`androidTest`/`iosTest`/`androidUnitTest`/`jvmTest`/`androidHostTest`)
  ou em path de teste NÃO entram na detecção. Verificável: dup byte-idêntico em
  código de teste não vira finding.
- **AC-4 — Advise-only (fronteira).** Findings continuam fluindo pelo pipeline
  existente `reuse_findings → proposed-evolutions` (confidence preservado);
  NENHUM enforcement/hard-block é adicionado. AC de fronteira: confirma que
  nenhum gate novo foi introduzido.
- **AC-5 — Verde + re-spike confirm.** `pytest` full verde (testes de reuse
  existentes atualizados p/ o universo ampliado) + `forge verify` sem hard fail.
  Re-spike vs `inchurch-app-main` reporta ~65 findings (within + cross) com
  precisão amostrada ~98%.
- **Follow-ons (registrar em `docs/design/04-pending.md`):** (a) parser gap
  `symbols.modifiers` vazio → não dá pra special-casar `override`; (b) parser
  gap `line_end==line_start` p/ 100% das funções → sem piso baseado em linhas;
  (c) `kmp-migration` sub-track (match name-only + similaridade/type-map); (d)
  considerar member-functions no universo (não medido neste incremento).

---

## Approach / design

- `duplicates.py`: nas queries de detecção, remover o predicado `receiver_type
  IS NOT NULL`; garantir `kind IN ('fun','composable_fun')`. Aplicar o piso
  sobre o número de `body_tokens` distintos do corpo compartilhado do grupo
  (todos do grupo têm o mesmo `body_hash`, logo o mesmo `body_tokens`) —
  within-module com < `REUSE_MIN_BODY_TOKENS` são descartados; cross-module
  bypassa o piso.
- Constante `REUSE_MIN_BODY_TOKENS = 5` junto de `CATEGORY_CONFIDENCE` (nomeada
  = tunável por-app sem edição espalhada).
- Exclusão de teste: predicado no WHERE que exclui os test source-sets (o plano
  define o predicado exato — via `files.source_set` no conjunto-de-teste e/ou
  `platform`/path).
- `queries.py`: espelhar as mudanças (as duas cópias ficam consistentes; a
  duplicação SQL `duplicates.py`↔`queries.py` é o follow-on JÁ anotado em
  04-pending no Stage 1).
- Pipeline advisory inalterado (já existe; nada a construir p/ AC-4 além de NÃO
  adicionar gate).

---

## Risks & limitations

- O piso = 5 foi calibrado na amostra do `inchurch-app-main`; outro app pode
  precisar de ajuste — a constante nomeada facilita. A precisão ~98% é
  amostrada, não exaustiva.
- `body_tokens` semantics: assume-se o conjunto dedup de tokens do corpo (o que
  o precision spike usou). O plano confirma empiricamente antes de assumir.

---

## Coverage (AC → tasks)

(A ser preenchida pelo plano `docs/superpowers/plans/2026-07-13-graph-reuse-stage2.md`.)
