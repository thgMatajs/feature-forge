# GRAPH-REUSE-STAGE2 Implementation Plan — universo ampliado + piso de trivialidade (advise-only)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Converter a detecção de duplicata exata Kotlin quase-morta (travada em extension functions → 1 finding no app real) em **~65 findings acionáveis a ~98% de precisão**, ampliando o universo de símbolos (top-level `fun` + `composable_fun`, não só extensions), com um piso de trivialidade por `body_tokens` distintos e exclusão de código de teste, roteados pelo pipeline advisory existente (`reuse_findings → proposed-evolutions`). **Sem enforcement.**

**Architecture:** Três mudanças cirúrgicas, todas dentro do subsistema de reuse-intelligence, todas espelhadas entre a detecção build-time (`engine/graph/duplicates.py`) e o read-time interativo (`engine/graph/queries.py`) para que os dois caminhos fiquem consistentes:

1. **Universo ampliado** — as queries de dup within-module e cross-module deixam de exigir `receiver_type IS NOT NULL` e passam a filtrar `kind IN ('fun','composable_fun')`. Extension funs (fun com receiver) permanecem cobertas; entram top-level funs e composables. O `GROUP BY` passa a agrupar por `COALESCE(s.receiver_type, '')` (top-level funs têm receiver NULL) — espelha exatamente o probe SQL do precision spike (variantes C/D) que mediu 87 within + 4 cross.
2. **Piso de trivialidade** — constante nomeada `REUSE_MIN_BODY_TOKENS = 5`. Grupos **within-module** cujo corpo compartilhado tem menos de 5 `body_tokens` DISTINTOS são descartados (ruído: setter de 1 linha, boilerplate de adapter). Grupos **cross-module** (≥2 módulos) **bypassam** o piso — sinal mais forte, preserva ex.: `MutableState.update` (2 tokens, 3× cross android+shared). O piso lê uma coluna que já existe (`symbols.body_tokens`), replica a contagem do spike (`len(json.loads(body_tokens))`) e não depende de extensão JSON1 do SQLite (ver "Global Constraints").
3. **Exclusão de test-source** — símbolos em paths de teste (`src/test/`, `src/androidTest/`, `src/androidUnitTest/`, `src/androidHostTest/`, `src/commonTest/`, `src/iosTest/`, `src/jvmTest/`) NÃO entram na detecção (within OU cross). Predicado **path-based** — ver "Decisão de design: por que path, não source_set" abaixo.

**Advise-only (AC-4):** nenhum gate/hard-block novo. Os findings continuam materializando em `reuse_findings` e fluindo pela distillation pipeline existente (`queue_proposals_from_table → proposed-evolutions.yaml`) com o mesmo `confidence`. Top-level funs (sem receiver) já renderizam via o caminho existente `receiver or "(top-level)"` em `_build_proposal_title` — zero código novo de pipeline.

**Tech Stack:** Python 3.13, stdlib `sqlite3`, `pathspec` (já vendorizado). Testes via `.venv/bin/pytest`. Sem novas dependências.

---

## Decisão de design: por que a exclusão de teste é path-based, não source_set-based

O spec (AC-3) enumera os source-sets de teste (`commonTest`/`androidTest`/`iosTest`/`androidUnitTest`/`jvmTest`/`androidHostTest`) **OU** "path de teste", e a Approach delega o predicado exato ao plano. O plano escolhe **path-based** por duas razões empíricas, verificadas contra o `inchurch-app-main` e a implementação real do engine:

1. **`src/test/` tem `source_set = NULL`.** A tabela `KMP_SOURCE_SETS` (`engine/graph/gradle_modules.py`) NÃO contém o segmento `test` puro (só `androidTest`/`commonTest`/etc.). Os 7 grupos test-noise medidos no spike vivem majoritariamente em `.../src/test/java/...ExampleUnitTest.kt` e `.../src/test/java/...*Test.kt` (unit tests Android/JVM padrão) → `infer_module_and_source_set` retorna `source_set = None` pra eles. Um predicado só por source-set os **perderia** — near-inert gate (a lição do Stage 1: o C5 gate matchava uma forma sintética que não existia no dado real).
2. **`... NOT IN (...)` com NULL é um landmine.** Em SQL, `NULL NOT IN ('androidTest', ...)` avalia pra **NULL** (não TRUE), então a row é FILTRADA FORA. A maioria esmagadora dos arquivos de produção (Android em `src/main/`, não-KMP) tem `source_set = NULL` → um predicado `f.source_set NOT IN (...)` **descartaria quase todo o universo de produção**. Catastrófico e silencioso.

O predicado path-based (`f.path` é NOT NULL por construção — coluna `UNIQUE NOT NULL`) captura todos os 7 grupos test-noise reais (verificado em `groups.json`: idx 1/52/53/81/82/83/84, todos em `/src/test/` ou `/src/androidTest/`), sem falso-positivo em arquivos de produção nomeados `*Test.kt` (matchamos o **diretório** `/src/<sourceSet>/`, não o sufixo de arquivo). É o mesmo espírito da recomendação §4 do spike ("Exclude test source sets `src/test`, `src/androidTest`, `commonTest`").

---

## Global Constraints

- **Dependencies:** stdlib + `pathspec` only. NENHUMA dependência externa nova.
- **Piso via Python, não JSON1.** O piso conta `body_tokens` distintos em Python (`len(tokens_from_json(body_tokens))`), NÃO via `json_array_length(...)` no SQL. Motivos: (a) replica EXATAMENTE a contagem do precision spike (`len(json.loads(rep["body_tokens"]))` em `dump_groups.py`); (b) `tokens_from_json` já está importado em `duplicates.py` (linha 25) e a coluna já está deduplicada (`tokens_to_json(frozenset)` → array JSON de tokens únicos), então `len` == nº de tokens distintos; (c) não assume que o SQLite linkado tem a extensão JSON1 habilitada (conservador — algumas builds de SQLite do sistema não têm). O comma-count hack em SQL seria INCORRETO (string-literals podem conter vírgula → token com vírgula → contagem errada). **Não use SQL pra contar tokens.**
- **`body_tokens` semantics (confirmado empiricamente).** `symbols.body_tokens` (schema v2, `engine/utils/sqlite_io.py:69`) é um array JSON de tokens semânticos **distintos, lowercased, com noise filtrado** (`extract_body_tokens` → `frozenset` → `tokens_to_json`, ordenado). NULL quando o body não pôde ser tokenizado. `len(tokens_from_json(None)) == 0`.
- **Sem bump de `SCHEMA_VERSION`.** Nenhuma coluna nova. `body_tokens` já existe.
- **`kind IN ('fun','composable_fun')` é o universo completo do body_hash.** Confirmado no spike: só `fun` (3.040) e `composable_fun` (756) carregam `body_hash`; val/var/class/interface/enum/object têm `body_hash = NULL`. Member-functions dentro de classes NÃO estão neste universo (não medidas — follow-on).
- **Canonical test runner é `.venv/bin/pytest`** — o `pytest` do sistema não tem `json5`/deps e dá falsos negativos. Todo comando abaixo usa `.venv/bin/pytest`.
- **TDD obrigatório:** cada task de código escreve um teste FALHANDO primeiro, roda pra confirmar RED, escreve a impl mínima, roda GREEN, commita.
- **Commits atômicos, estilo do repo:** `feat(graph): …`, `docs(graph): …`.
- **Doc-sync no MESMO commit** (Mandamento #6): todo commit que toca `engine/**` também atualiza `CHANGELOG.md` (`## [Unreleased]`). A doc de comportamento (`docs/schemas/graph.md`), a stat do README e os follow-ons de `04-pending` são consolidados na Task 4 (a behavior-doc só fica 100% verdadeira quando build-time E read-time estão consistentes, i.e., após a Task 3 — mesmo padrão do consolidado de README no Stage 1).
- **Escopo é ESTRITAMENTE o incremento Stage 2.** NÃO planejar/tocar: o sub-track `kmp-migration` (defeito de match cross-lang — non-goal), similaridade fuzzy/token além do `body_hash` exato, ampliar o `near-duplicate` (`_q_near_duplicates`), member-functions dentro de classes, refactor dos parsers. NÃO tocar `_q_near_duplicate`, `_q_redundant_platform_specific`, `_q_kmp_migration_candidates` (nem seus espelhos read-side). Esses são non-goals/follow-ons do spec.
- **Voice:** comentários de código seguem a convenção mentor-calmo, pt-BR do repo (ver comentários vizinhos em `engine/graph/*.py`).

---

## File Structure

**Modificados (pelo executor — este plano é doc only):**
- `engine/graph/duplicates.py` — amplia `_q_duplicates_within_module` + `_q_duplicates_cross_module` (Task 1); adiciona `REUSE_MIN_BODY_TOKENS` + helper `_distinct_body_token_count` + exclusão de teste nas duas queries + floor-skip no loop within-module de `detect_all_reuse_findings` (Task 2). NÃO tocar `_q_near_duplicates`, `_q_redundant_platform_specific`, `_q_kmp_migration_candidates`, `_q_duplicate_ts_helpers`.
- `engine/graph/queries.py` — espelha universo ampliado + piso + exclusão em `find_duplicates_within_module` + `find_duplicates_cross_module` (Task 3); importa `REUSE_MIN_BODY_TOKENS` + `_distinct_body_token_count` de `duplicates.py`. NÃO tocar `find_near_duplicates`, `find_redundant_platform_specific`, `find_kmp_migration_candidates`.
- `tests/unit/test_query_q12_duplicates_within_module.py` — test-sync (semeia `body_tokens` ≥5), no MESMO commit da Task 3 (a mudança read-side é o que o quebra). Ver "Sweep de testes existentes".
- `docs/schemas/graph.md` — doc de comportamento da reuse-universe (Task 4).
- `README.md` — bump da contagem `rapid` (Task 4).
- `docs/design/04-pending.md` — 4 follow-ons do spec (Task 4).
- `CHANGELOG.md` — `## [Unreleased]` (todo commit que toca engine).

**Novos test files (pelo executor):**
- `tests/unit/test_reuse_universe_broadened.py` (Task 1)
- `tests/unit/test_reuse_triviality_floor_and_test_exclusion.py` (Task 2)
- `tests/unit/test_reuse_read_side_broadened.py` (Task 3)

**Dependency order:** Task 1 → Task 2 → Task 3 são sequenciais na mesma SQL (Task 2 edita o resultado da Task 1; Task 3 espelha o estado final na `queries.py`). Task 2 define a constante + helper que a Task 3 importa. Task 4 é doc-sync final (depende de Tasks 1–3 verdes). O gate final (re-spike) roda depois de tudo verde.

---

## Sweep de testes existentes (feito no planejamento — NÃO reexecutar às cegas)

Varredura de `tests/` por tudo que exercita a detecção within/cross-module (`detect_all_reuse_findings`, `find_duplicates_within_module`, `find_duplicates_cross_module`) ou depende da forma dos findings. Resultado (aprenda do Stage 1, onde um teste q16 foi perdido):

| Teste | Toca a detecção broadened? | Veredito | Ação |
|---|---|---|---|
| `test_query_q12_duplicates_within_module.py` | SIM (read-side within) | **QUEBRA na Task 3** — `_insert_kt_extension` semeia `body_tokens = NULL` → `_distinct_body_token_count(None) == 0 < 5` → o happy-path (espera 1 row) é **filtrado pelo piso** → 0 rows. | **Atualizar na Task 3** (semear `body_tokens` ≥5 tokens). Test-sync no MESMO commit que introduz o piso read-side (Mandamento #6). |
| `test_query_q13_duplicates_cross_module.py` | SIM (read-side cross) | **VERDE** — cross-module bypassa o piso (`body_tokens` NULL irrelevante); paths (`app/android/A.kt`, `shared/B.kt`, `feature/auth/C.kt`) não casam nenhum predicado de teste; receiver `String` (extension) segue matchado por `kind IN ('fun','composable_fun')`; `COALESCE(receiver)` não muda o agrupamento. | Nenhuma. Rodar como regression guard. |
| `test_reuse_intelligence.py` | SIM (`_scaffold_two_module_duplicate` → `build_full` + `detect_all_reuse_findings`) | **VERDE** — o dup (`FirebaseAnalytics.logEventSafely`, extension) é **cross-module** (`shared:feature:a`↔`shared:feature:b`, `src/androidMain/`) → bypassa o piso; `androidMain` não é path de teste; asserts são `n_queued >= 1` / `any(promote-to-shared-helper)` / idempotência — robustos a findings extras. | Nenhuma. Rodar como regression guard. |
| `test_platform_aware_reuse_queries.py` | SIM (`detect_all_reuse_findings` em `test_detection_materializes_redundant_finding`) | **VERDE** — o par `Long.formatTime` (common↔android) é claimado por **Q16 redundant-platform** (roda primeiro), que deduplica o Q13 cross via `claimed_exact`; o assert conta só `category='redundant-platform-specific'` (== 1). Paths não-teste. | Nenhuma. Rodar como regression guard. |
| `test_infer_suggested_target_categories.py` | NÃO (testa `infer_suggested_target`, função pura) | **VERDE** | Nenhuma. |
| `test_queries_list_reuse_findings_perf.py` | NÃO (semeia `reuse_findings` direto; testa list-query) | **VERDE** | Nenhuma. |
| `test_graph_parsers.py` | NÃO (testa parsers; `composable_fun` é produzido lá, mas o teste não roda detecção) | **VERDE** | Nenhuma. |

**Conclusão do sweep: 1 teste quebra (`test_query_q12`), corrigido na Task 3. Os outros 6 são verificados-verdes com raciocínio.** A Task 4 re-roda a lane inteira pra confirmar zero straggler.

---

## Task 1: Ampliar o universo de detecção (`duplicates.py`)

**Files:**
- Modify: `engine/graph/duplicates.py` — `_q_duplicates_within_module` (linhas 185-204) + `_q_duplicates_cross_module` (linhas 207-227)
- Modify: `CHANGELOG.md` (`## [Unreleased] > ### Changed`)
- Test: `tests/unit/test_reuse_universe_broadened.py` (create)

**Interfaces:**
- Consome: nada de outras tasks.
- Produz: as duas queries de detecção deixam de exigir `receiver_type IS NOT NULL` e incluem `kind IN ('fun','composable_fun')`; `GROUP BY`/`ORDER BY` usam `COALESCE(s.receiver_type, '')`. Assinatura dos helpers e shape das rows retornadas inalterados (mesmas colunas). O piso e a exclusão de teste chegam na Task 2.

**Current SQL to preserve (leia antes de editar).** `_q_duplicates_within_module` (linhas 185-204) hoje é:

```python
def _q_duplicates_within_module(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.name, s.receiver_type, s.signature, s.body_hash, s.modifiers,
               f.module AS module, f.source_set AS source_set,
               GROUP_CONCAT(f.id || ':' || s.line_start || ':' || f.path, char(31)) AS occurrences,
               COUNT(*) AS n
        FROM symbols s
        JOIN files f ON s.file_id = f.id
        WHERE s.kind = 'fun'
          AND s.receiver_type IS NOT NULL
          AND s.body_hash IS NOT NULL
          AND f.path LIKE '%.kt'
        GROUP BY f.module, COALESCE(f.source_set, ''),
                 s.receiver_type, s.name, s.signature, s.body_hash
        HAVING COUNT(*) > 1
        ORDER BY n DESC, f.module, s.receiver_type, s.name
        """
    ).fetchall()
    return [dict(r) for r in rows]
```

`_q_duplicates_cross_module` (linhas 207-227) hoje é:

```python
def _q_duplicates_cross_module(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.name, s.receiver_type, s.signature, s.body_hash, s.modifiers,
               GROUP_CONCAT(DISTINCT f.module) AS modules,
               GROUP_CONCAT(f.id || ':' || s.line_start || ':' || f.path, char(31)) AS occurrences,
               GROUP_CONCAT(COALESCE(f.source_set, '')) AS source_sets,
               COUNT(DISTINCT f.module) AS n_modules,
               COUNT(*) AS n_files
        FROM symbols s
        JOIN files f ON s.file_id = f.id
        WHERE s.kind = 'fun'
          AND s.receiver_type IS NOT NULL
          AND s.body_hash IS NOT NULL
          AND f.path LIKE '%.kt'
        GROUP BY s.receiver_type, s.name, s.signature, s.body_hash
        HAVING COUNT(DISTINCT f.module) > 1
        ORDER BY n_modules DESC, n_files DESC, s.receiver_type, s.name
        """
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 1: Escreve o teste de universo ampliado (RED)**

Create `tests/unit/test_reuse_universe_broadened.py`:

```python
"""Universo ampliado da detecção de dup exata (GRAPH-REUSE-STAGE2 Task 1).

A detecção deixa de ser travada em extension functions
(`receiver_type IS NOT NULL` + `kind='fun'`) e passa a cobrir top-level `fun`
e `composable_fun` (os únicos kinds que carregam `body_hash`). Extension funs
(fun com receiver) permanecem cobertas.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph.duplicates import detect_all_reuse_findings
from engine.utils.sqlite_io import open_db, transaction

# 5 tokens distintos → sobrevive ao piso REUSE_MIN_BODY_TOKENS introduzido na
# Task 2, mantendo este teste verde ao longo das Tasks 2 e 3.
_TOKENS5 = '["alpha","beta","gamma","delta","epsilon"]'


def _file(conn, path: str, module: str, source_set: str | None = "main") -> int:
    return conn.execute(
        "INSERT INTO files(path, language, module, source_set, platform) "
        "VALUES (?, 'kotlin', ?, ?, 'android')",
        (path, module, source_set),
    ).lastrowid


def _sym(conn, file_id: int, *, name: str, kind: str, receiver: str | None,
         body_hash: str, line: int, sig: str | None = None,
         tokens: str = _TOKENS5) -> None:
    conn.execute(
        "INSERT INTO symbols(file_id, name, kind, signature, line_start, "
        "receiver_type, body_hash, body_tokens, modifiers) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')",
        (file_id, name, kind, sig or f"{name}()", line, receiver, body_hash, tokens),
    )


def _within_names(conn) -> set[str]:
    return {
        r["symbol_name"]
        for r in conn.execute(
            "SELECT symbol_name FROM reuse_findings "
            "WHERE category = 'duplicate-within-module'"
        ).fetchall()
    }


def test_broadened_universe_detects_toplevel_composable_and_extension(tmp_path: Path) -> None:
    """Top-level fun + composable_fun (sem receiver) + extension, todos
    duplicados within-module, produzem finding após o broadening.

    RED (código atual): só `fmt` (extension) é detectado — `setupToolbar`
    (top-level) e `LoadingRow` (composable) têm receiver NULL e são barrados
    por `receiver_type IS NOT NULL` + `kind='fun'`.
    """
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            a1 = _file(conn, "app/src/main/kotlin/A1.kt", "app")
            a2 = _file(conn, "app/src/main/kotlin/A2.kt", "app")
            # (a) top-level fun, sem receiver — hoje NÃO detectado.
            _sym(conn, a1, name="setupToolbar", kind="fun", receiver=None,
                 body_hash="ht", line=10)
            _sym(conn, a2, name="setupToolbar", kind="fun", receiver=None,
                 body_hash="ht", line=20)
            # (b) composable_fun, sem receiver — hoje NÃO detectado.
            _sym(conn, a1, name="LoadingRow", kind="composable_fun", receiver=None,
                 body_hash="hc", line=40)
            _sym(conn, a2, name="LoadingRow", kind="composable_fun", receiver=None,
                 body_hash="hc", line=50)
            # (c) extension fun, com receiver — hoje JÁ detectado (regression guard).
            _sym(conn, a1, name="fmt", kind="fun", receiver="Long",
                 body_hash="he", line=70, sig="Long.fmt(): String")
            _sym(conn, a2, name="fmt", kind="fun", receiver="Long",
                 body_hash="he", line=80, sig="Long.fmt(): String")
            detect_all_reuse_findings(conn, gradle_modules={}, module_dep_rows=[])
        assert _within_names(conn) == {"setupToolbar", "LoadingRow", "fmt"}
    finally:
        conn.close()
```

- [ ] **Step 2: Roda o teste pra confirmar que falha (RED)**

Run: `.venv/bin/pytest tests/unit/test_reuse_universe_broadened.py -v`
Expected: FAIL — `_within_names(conn)` retorna `{"fmt"}` (só a extension), a asserção espera os 3.

- [ ] **Step 3: Amplia `_q_duplicates_within_module` (impl mínima)**

Substitui o corpo de `_q_duplicates_within_module` (linhas 185-204) por:

```python
def _q_duplicates_within_module(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.name, s.receiver_type, s.signature, s.body_hash, s.modifiers,
               f.module AS module, f.source_set AS source_set,
               GROUP_CONCAT(f.id || ':' || s.line_start || ':' || f.path, char(31)) AS occurrences,
               COUNT(*) AS n
        FROM symbols s
        JOIN files f ON s.file_id = f.id
        WHERE s.kind IN ('fun', 'composable_fun')
          AND s.body_hash IS NOT NULL
          AND f.path LIKE '%.kt'
        GROUP BY f.module, COALESCE(f.source_set, ''),
                 COALESCE(s.receiver_type, ''), s.name, s.signature, s.body_hash
        HAVING COUNT(*) > 1
        ORDER BY n DESC, f.module, COALESCE(s.receiver_type, ''), s.name
        """
    ).fetchall()
    return [dict(r) for r in rows]
```

Mudanças: `WHERE s.kind = 'fun' AND s.receiver_type IS NOT NULL` → `WHERE s.kind IN ('fun', 'composable_fun')` (dropa a trava de extension). `GROUP BY ... s.receiver_type ...` → `COALESCE(s.receiver_type, '')` (top-level funs têm receiver NULL; espelha o probe do spike). `ORDER BY ... s.receiver_type ...` → `COALESCE(s.receiver_type, '')` (NULL-safe sort).

- [ ] **Step 4: Amplia `_q_duplicates_cross_module` (impl mínima)**

Substitui o corpo de `_q_duplicates_cross_module` (linhas 207-227) por:

```python
def _q_duplicates_cross_module(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.name, s.receiver_type, s.signature, s.body_hash, s.modifiers,
               GROUP_CONCAT(DISTINCT f.module) AS modules,
               GROUP_CONCAT(f.id || ':' || s.line_start || ':' || f.path, char(31)) AS occurrences,
               GROUP_CONCAT(COALESCE(f.source_set, '')) AS source_sets,
               COUNT(DISTINCT f.module) AS n_modules,
               COUNT(*) AS n_files
        FROM symbols s
        JOIN files f ON s.file_id = f.id
        WHERE s.kind IN ('fun', 'composable_fun')
          AND s.body_hash IS NOT NULL
          AND f.path LIKE '%.kt'
        GROUP BY COALESCE(s.receiver_type, ''), s.name, s.signature, s.body_hash
        HAVING COUNT(DISTINCT f.module) > 1
        ORDER BY n_modules DESC, n_files DESC, COALESCE(s.receiver_type, ''), s.name
        """
    ).fetchall()
    return [dict(r) for r in rows]
```

Mudanças idênticas em espírito: `WHERE` amplia o universo; `GROUP BY`/`ORDER BY` usam `COALESCE(s.receiver_type, '')`.

- [ ] **Step 5: Roda o teste pra confirmar que passa (GREEN)**

Run: `.venv/bin/pytest tests/unit/test_reuse_universe_broadened.py -v`
Expected: `1 passed`.

- [ ] **Step 6: Regressão da lane de reuse (guard)**

Run: `.venv/bin/pytest tests/unit/test_reuse_intelligence.py tests/unit/test_query_q13_duplicates_cross_module.py tests/unit/test_platform_aware_reuse_queries.py -q`
Expected: all pass (sem regressão — ver o sweep: cross-module bypassa piso, paths não-teste; a Task 1 ainda não tem piso/exclusão). NÃO rodar `test_query_q12` aqui — ele só é tocado (e corrigido) na Task 3.

- [ ] **Step 7: CHANGELOG entry**

Em `CHANGELOG.md` sob `## [Unreleased] > ### Changed`:

```markdown
- **Reuse-intelligence: universo de dup exata ampliado (GRAPH-REUSE-STAGE2):** a detecção within/cross-module (`_q_duplicates_within_module` / `_q_duplicates_cross_module`) deixa de exigir `receiver_type IS NOT NULL` e passa a incluir `kind IN ('fun','composable_fun')` (os únicos kinds que carregam `body_hash`). Extension funs continuam cobertas; entram top-level funs e composables. Agrupamento por `COALESCE(receiver_type,'')`. Medido no precision spike vs `inchurch-app-main`: 1 finding → ~89 grupos brutos (piso + exclusão de teste na sequência).
```

- [ ] **Step 8: Commit**

```bash
git add engine/graph/duplicates.py tests/unit/test_reuse_universe_broadened.py CHANGELOG.md
git commit -m "feat(graph): amplia universo de dup exata (top-level fun + composable_fun)"
```

---

## Task 2: Piso de trivialidade + exclusão de test-source (`duplicates.py`)

**Files:**
- Modify: `engine/graph/duplicates.py` — nova constante `REUSE_MIN_BODY_TOKENS` + helper `_distinct_body_token_count` (após `CATEGORY_CONFIDENCE`, ~linha 51); `s.body_tokens` no SELECT + bloco de exclusão de teste no WHERE de `_q_duplicates_within_module`; bloco de exclusão de teste no WHERE de `_q_duplicates_cross_module`; floor-skip no loop within-module de `detect_all_reuse_findings` (linhas 106-123)
- Modify: `CHANGELOG.md`
- Test: `tests/unit/test_reuse_triviality_floor_and_test_exclusion.py` (create)

**Interfaces:**
- Consome: as queries ampliadas da Task 1.
- Produz: `REUSE_MIN_BODY_TOKENS = 5` (int, módulo `duplicates.py`); `_distinct_body_token_count(body_tokens_json: Optional[str]) -> int`. Ambos importados pela `queries.py` na Task 3. Detecção within-module filtra grupos com `< REUSE_MIN_BODY_TOKENS` tokens distintos; cross-module bypassa; código de teste excluído das duas.

- [ ] **Step 1: Escreve o teste de piso + exclusão (RED)**

Create `tests/unit/test_reuse_triviality_floor_and_test_exclusion.py`:

```python
"""Piso de trivialidade + exclusão de test-source (GRAPH-REUSE-STAGE2 Task 2).

- within-module: grupos com < REUSE_MIN_BODY_TOKENS (5) tokens distintos são
  descartados; >= 5 mantidos.
- cross-module (>=2 módulos): BYPASSA o piso (mantém mesmo com 2 tokens).
- símbolos em paths de teste (src/test, src/androidTest, ...) NÃO entram na
  detecção (within OU cross).
"""

from __future__ import annotations

from pathlib import Path

from engine.graph.duplicates import (
    REUSE_MIN_BODY_TOKENS,
    detect_all_reuse_findings,
)
from engine.utils.sqlite_io import open_db, transaction

# Piso calibrado no precision spike (72% → 98% de precisão em ntok >= 5).
assert REUSE_MIN_BODY_TOKENS == 5


def _file(conn, path: str, module: str, source_set: str | None = "main",
          platform: str = "android") -> int:
    return conn.execute(
        "INSERT INTO files(path, language, module, source_set, platform) "
        "VALUES (?, 'kotlin', ?, ?, ?)",
        (path, module, source_set, platform),
    ).lastrowid


def _sym(conn, file_id: int, *, name: str, body_hash: str, tokens: str,
         line: int, receiver: str | None = None, kind: str = "fun") -> None:
    conn.execute(
        "INSERT INTO symbols(file_id, name, kind, signature, line_start, "
        "receiver_type, body_hash, body_tokens, modifiers) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')",
        (file_id, name, kind, f"{name}()", line, receiver, body_hash, tokens),
    )


def _count(conn, category: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS c FROM reuse_findings WHERE category = ?",
        (category,),
    ).fetchone()["c"]


def _names(conn, category: str) -> set[str]:
    return {
        r["symbol_name"]
        for r in conn.execute(
            "SELECT symbol_name FROM reuse_findings WHERE category = ?",
            (category,),
        ).fetchall()
    }


def test_within_module_floor_filters_trivial_keeps_substantial(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _file(conn, "app/src/main/kotlin/A.kt", "app")
            f2 = _file(conn, "app/src/main/kotlin/B.kt", "app")
            # trivial: 4 tokens distintos (< 5) → deve ser filtrado.
            _sym(conn, f1, name="setToken", body_hash="ht",
                 tokens='["a","b","c","d"]', line=10)
            _sym(conn, f2, name="setToken", body_hash="ht",
                 tokens='["a","b","c","d"]', line=20)
            # substantial: 5 tokens distintos (>= 5) → deve ser mantido.
            _sym(conn, f1, name="resize", body_hash="hr",
                 tokens='["a","b","c","d","e"]', line=40)
            _sym(conn, f2, name="resize", body_hash="hr",
                 tokens='["a","b","c","d","e"]', line=50)
            detect_all_reuse_findings(conn, gradle_modules={}, module_dep_rows=[])
        assert _names(conn, "duplicate-within-module") == {"resize"}
    finally:
        conn.close()


def test_cross_module_bypasses_floor(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _file(conn, "androidApp/src/main/kotlin/State.kt", "androidApp")
            f2 = _file(conn, "shared/src/commonMain/kotlin/State.kt", "shared",
                       source_set="commonMain", platform="common")
            # 2 tokens distintos, mas cross-module (2 módulos) → mantido (bypass).
            _sym(conn, f1, name="update", body_hash="hu", tokens='["a","b"]',
                 line=5, receiver="MutableState")
            _sym(conn, f2, name="update", body_hash="hu", tokens='["a","b"]',
                 line=5, receiver="MutableState")
            detect_all_reuse_findings(conn, gradle_modules={}, module_dep_rows=[])
        assert _names(conn, "duplicate-cross-module") == {"update"}
    finally:
        conn.close()


def test_test_source_duplicate_not_reported(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            # byte-idêntico, >= 5 tokens, MESMO módulo, mas em src/test/ →
            # source_set NULL (o KMP set não tem `test`), captado por path.
            t1 = _file(conn, "app/src/test/java/FooTest.kt", "app", source_set=None)
            t2 = _file(conn, "app/src/test/java/BarTest.kt", "app", source_set=None)
            _sym(conn, t1, name="tearDown", body_hash="hd",
                 tokens='["a","b","c","d","e","f"]', line=10)
            _sym(conn, t2, name="tearDown", body_hash="hd",
                 tokens='["a","b","c","d","e","f"]', line=20)
            detect_all_reuse_findings(conn, gradle_modules={}, module_dep_rows=[])
        assert _count(conn, "duplicate-within-module") == 0
    finally:
        conn.close()
```

- [ ] **Step 2: Roda o teste pra confirmar que falha (RED)**

Run: `.venv/bin/pytest tests/unit/test_reuse_triviality_floor_and_test_exclusion.py -v`
Expected: FAIL na coleta — `ImportError: cannot import name 'REUSE_MIN_BODY_TOKENS' from 'engine.graph.duplicates'` (a constante ainda não existe). Esse é o RED válido (mesmo padrão do Stage 1 Task 2/3). Depois da impl, os três testes passam.

- [ ] **Step 3a: Adiciona a constante + helper**

Em `engine/graph/duplicates.py`, imediatamente após o dict `CATEGORY_CONFIDENCE` (após a linha 51, antes de `_KMP_SIMILARITY_FLOOR`), insere:

```python
# Piso de trivialidade (GRAPH-REUSE-STAGE2). Grupos within-module cujo corpo
# compartilhado tem menos de REUSE_MIN_BODY_TOKENS tokens DISTINTOS são
# descartados — ruído (setter de 1 linha, boilerplate de adapter, fixture de
# teste). Medido no precision spike vs inchurch-app-main: o piso >= 5 subiu a
# precisão de 72% (sem piso) pra ~98% sem perder nenhum finding REAL. Grupos
# CROSS-MODULE (>= 2 módulos) NÃO passam pelo piso (sinal mais forte; preserva
# ex.: MutableState.update, 2 tokens, 3x cross android+shared). Constante
# nomeada = tunável por-app sem edição espalhada.
REUSE_MIN_BODY_TOKENS = 5


def _distinct_body_token_count(body_tokens_json: Optional[str]) -> int:
    """Número de tokens DISTINTOS do corpo (base do piso de trivialidade).

    Replica a contagem do precision spike (``len(json.loads(body_tokens))``):
    ``symbols.body_tokens`` é um array JSON já deduplicado
    (``tokens_to_json(frozenset)``), então o tamanho do conjunto == nº de
    tokens distintos. Feito em Python de propósito — não assume a extensão
    JSON1 do SQLite e reusa ``tokens_from_json`` (já importado). NULL/malformado
    → 0 (degrade seguro; grupo abaixo de qualquer piso positivo).
    """
    return len(tokens_from_json(body_tokens_json))
```

`tokens_from_json` e `Optional` já estão importados (linhas 25 e 23). Nada a adicionar aos imports.

- [ ] **Step 3b: Adiciona `s.body_tokens` ao SELECT + exclusão de teste em `_q_duplicates_within_module`**

Substitui o corpo de `_q_duplicates_within_module` (estado pós-Task-1) por:

```python
def _q_duplicates_within_module(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.name, s.receiver_type, s.signature, s.body_hash, s.body_tokens, s.modifiers,
               f.module AS module, f.source_set AS source_set,
               GROUP_CONCAT(f.id || ':' || s.line_start || ':' || f.path, char(31)) AS occurrences,
               COUNT(*) AS n
        FROM symbols s
        JOIN files f ON s.file_id = f.id
        WHERE s.kind IN ('fun', 'composable_fun')
          AND s.body_hash IS NOT NULL
          AND f.path LIKE '%.kt'
          AND f.path NOT LIKE '%/src/test/%'
          AND f.path NOT LIKE '%/src/androidTest/%'
          AND f.path NOT LIKE '%/src/androidUnitTest/%'
          AND f.path NOT LIKE '%/src/androidHostTest/%'
          AND f.path NOT LIKE '%/src/commonTest/%'
          AND f.path NOT LIKE '%/src/iosTest/%'
          AND f.path NOT LIKE '%/src/jvmTest/%'
        GROUP BY f.module, COALESCE(f.source_set, ''),
                 COALESCE(s.receiver_type, ''), s.name, s.signature, s.body_hash
        HAVING COUNT(*) > 1
        ORDER BY n DESC, f.module, COALESCE(s.receiver_type, ''), s.name
        """
    ).fetchall()
    return [dict(r) for r in rows]
```

Mudanças: `s.body_tokens` adicionado ao SELECT (o loop lê ele pro piso); bloco de 7 `AND f.path NOT LIKE ...` adicionado ao WHERE (exclusão de teste path-based — ver "Decisão de design"). `s.body_tokens` é coluna bare num aggregate query: como todos os membros do grupo compartilham `body_hash`, compartilham o mesmo `body_tokens` (mesmo corpo normalizado → mesmos tokens), então a row representativa que o SQLite retorna é fiel.

- [ ] **Step 3c: Exclusão de teste em `_q_duplicates_cross_module`**

Substitui o corpo de `_q_duplicates_cross_module` (estado pós-Task-1) por:

```python
def _q_duplicates_cross_module(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.name, s.receiver_type, s.signature, s.body_hash, s.modifiers,
               GROUP_CONCAT(DISTINCT f.module) AS modules,
               GROUP_CONCAT(f.id || ':' || s.line_start || ':' || f.path, char(31)) AS occurrences,
               GROUP_CONCAT(COALESCE(f.source_set, '')) AS source_sets,
               COUNT(DISTINCT f.module) AS n_modules,
               COUNT(*) AS n_files
        FROM symbols s
        JOIN files f ON s.file_id = f.id
        WHERE s.kind IN ('fun', 'composable_fun')
          AND s.body_hash IS NOT NULL
          AND f.path LIKE '%.kt'
          AND f.path NOT LIKE '%/src/test/%'
          AND f.path NOT LIKE '%/src/androidTest/%'
          AND f.path NOT LIKE '%/src/androidUnitTest/%'
          AND f.path NOT LIKE '%/src/androidHostTest/%'
          AND f.path NOT LIKE '%/src/commonTest/%'
          AND f.path NOT LIKE '%/src/iosTest/%'
          AND f.path NOT LIKE '%/src/jvmTest/%'
        GROUP BY COALESCE(s.receiver_type, ''), s.name, s.signature, s.body_hash
        HAVING COUNT(DISTINCT f.module) > 1
        ORDER BY n_modules DESC, n_files DESC, COALESCE(s.receiver_type, ''), s.name
        """
    ).fetchall()
    return [dict(r) for r in rows]
```

Mudança: MESMO bloco de 7 `AND f.path NOT LIKE ...` (idêntico ao within-module). SEM `s.body_tokens` no SELECT e SEM piso — cross-module bypassa o piso por design.

- [ ] **Step 3d: Floor-skip no loop within-module de `detect_all_reuse_findings`**

Em `detect_all_reuse_findings`, o loop Q12 (linhas 107-123) hoje é:

```python
    # Q12 — within-module
    within_rows = _q_duplicates_within_module(conn)
    counts["duplicate-within-module"] = 0
    for row in within_rows:
        key = (
            row["receiver_type"] or "",
            row["name"],
            row["signature"] or "",
            row["body_hash"] or "",
        )
        if key in claimed_exact:
            continue
        claimed_exact.add(key)
        claimed_signature.add(
            (row["receiver_type"] or "", row["name"], row["signature"] or "")
        )
        _persist_within_module_finding(conn, row, gradle_modules, closure)
        counts["duplicate-within-module"] += 1
```

Substitui por (adiciona o floor-skip NO TOPO do corpo do loop, antes de computar/claimar a key):

```python
    # Q12 — within-module
    within_rows = _q_duplicates_within_module(conn)
    counts["duplicate-within-module"] = 0
    for row in within_rows:
        # Piso de trivialidade (GRAPH-REUSE-STAGE2): within-module abaixo de
        # REUSE_MIN_BODY_TOKENS tokens distintos é ruído. O `continue` fica
        # ANTES de claimar a key pra não bloquear um finding cross-module
        # legítimo com a mesma (receiver, name, sig, body_hash) — Q13 roda
        # depois e ainda pode capturá-lo (cross bypassa o piso).
        if _distinct_body_token_count(row.get("body_tokens")) < REUSE_MIN_BODY_TOKENS:
            continue
        key = (
            row["receiver_type"] or "",
            row["name"],
            row["signature"] or "",
            row["body_hash"] or "",
        )
        if key in claimed_exact:
            continue
        claimed_exact.add(key)
        claimed_signature.add(
            (row["receiver_type"] or "", row["name"], row["signature"] or "")
        )
        _persist_within_module_finding(conn, row, gradle_modules, closure)
        counts["duplicate-within-module"] += 1
```

Nota: o loop Q13 (cross-module, linhas 126-142) fica INALTERADO — cross-module bypassa o piso.

- [ ] **Step 4: Roda o teste pra confirmar que passa (GREEN)**

Run: `.venv/bin/pytest tests/unit/test_reuse_triviality_floor_and_test_exclusion.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Regressão da lane de reuse (guard)**

Run: `.venv/bin/pytest tests/unit/test_reuse_intelligence.py tests/unit/test_reuse_universe_broadened.py tests/unit/test_platform_aware_reuse_queries.py -q`
Expected: all pass. (`test_reuse_universe_broadened` da Task 1 continua verde: seus dups têm 5 tokens → sobrevivem ao piso; paths `src/main/` → não excluídos. `test_reuse_intelligence`: dup cross-module → bypassa piso.)

- [ ] **Step 6: CHANGELOG entry**

Em `CHANGELOG.md` sob `## [Unreleased] > ### Changed`, adiciona (após a entrada da Task 1, complementando-a):

```markdown
- **Reuse-intelligence: piso de trivialidade + exclusão de test-source (GRAPH-REUSE-STAGE2):** constante nomeada `REUSE_MIN_BODY_TOKENS = 5` filtra grupos **within-module** com menos de 5 `body_tokens` distintos (contagem em Python via `_distinct_body_token_count`, replicando o precision spike — sobe precisão 72%→98% sem perder finding REAL). Grupos **cross-module** (>=2 módulos) bypassam o piso (sinal mais forte). Símbolos em paths de teste (`src/test`, `src/androidTest`, `src/androidUnitTest`, `src/androidHostTest`, `src/commonTest`, `src/iosTest`, `src/jvmTest`) são excluídos da detecção — predicado **path-based** (o `src/test/` padrão tem `source_set` NULL, e `NULL NOT IN (...)` descartaria produção). Advise-only: nenhum gate novo; findings seguem pela pipeline de proposals existente.
```

- [ ] **Step 7: Commit**

```bash
git add engine/graph/duplicates.py tests/unit/test_reuse_triviality_floor_and_test_exclusion.py CHANGELOG.md
git commit -m "feat(graph): piso de trivialidade + exclusão de test-source na dup within-module"
```

---

## Task 3: Espelhar universo ampliado + piso no read-side (`queries.py`)

**Files:**
- Modify: `engine/graph/queries.py` — import de `REUSE_MIN_BODY_TOKENS` + `_distinct_body_token_count`; `find_duplicates_within_module` (linhas 441-474) + `find_duplicates_cross_module` (linhas 477-510)
- Modify: `tests/unit/test_query_q12_duplicates_within_module.py` — test-sync (semeia `body_tokens` ≥5), MESMO commit
- Modify: `CHANGELOG.md`
- Test: `tests/unit/test_reuse_read_side_broadened.py` (create)

**Interfaces:**
- Consome: `REUSE_MIN_BODY_TOKENS` + `_distinct_body_token_count` de `duplicates.py` (Task 2).
- Produz: `find_duplicates_within_module` / `find_duplicates_cross_module` (read-time, `forge graph`) espelham EXATAMENTE a detecção build-time — mesmo universo, mesma exclusão de teste (SQL idêntico), mesmo piso (Python idêntico, within-only). Shape das rows preservado (mais a coluna `body_tokens` no within-module, usada pelo filtro).

**Duplicação SQL `duplicates.py` ↔ `queries.py` (contexto).** As duas queries carregam SQL quase-idêntica — a extração num helper/constante compartilhada é o follow-on JÁ anotado no `04-pending` do Stage 1 e NÃO é do escopo aqui (Mandamento #4). Edite ambas; mantenha os blocos idênticos.

**Import (topo de `queries.py`, após `from engine.utils.sqlite_io import open_db`, linha 15):**

```python
from engine.graph.duplicates import REUSE_MIN_BODY_TOKENS, _distinct_body_token_count
```

Sem ciclo de import: `duplicates.py` não importa `queries.py`. (Cross-import de símbolo underscore-prefixado é padrão estabelecido no repo — `incremental.py` importa `_ensure_platform_column` de `builder.py`.)

- [ ] **Step 1: Escreve o teste de paridade read-side (RED)**

Create `tests/unit/test_reuse_read_side_broadened.py`:

```python
"""Paridade read-side do universo ampliado (GRAPH-REUSE-STAGE2 Task 3).

`find_duplicates_within_module` / `find_duplicates_cross_module` (read-time,
`forge graph`) espelham a detecção build-time: universo ampliado
(top-level fun + composable_fun), piso de trivialidade (within-only) e
exclusão de test-source.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph import queries
from engine.utils.sqlite_io import open_db, transaction


def _file(conn, path: str, module: str, source_set: str | None = "main",
          platform: str = "android") -> int:
    return conn.execute(
        "INSERT INTO files(path, language, module, source_set, platform) "
        "VALUES (?, 'kotlin', ?, ?, ?)",
        (path, module, source_set, platform),
    ).lastrowid


def _sym(conn, file_id: int, *, name: str, body_hash: str, tokens: str,
         line: int, receiver: str | None = None, kind: str = "fun") -> None:
    conn.execute(
        "INSERT INTO symbols(file_id, name, kind, signature, line_start, "
        "receiver_type, body_hash, body_tokens, modifiers) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')",
        (file_id, name, kind, f"{name}()", line, receiver, body_hash, tokens),
    )


def test_within_read_broadened_floored_and_test_excluded(tmp_path: Path) -> None:
    """RED: read-side hoje exige `receiver_type IS NOT NULL` → top-level e
    composable não aparecem (rows == []). Após o espelhamento: top-level e
    composable com >=5 tokens aparecem; o trivial (<5) é filtrado pelo piso;
    o dup em src/test/ é excluído.
    """
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _file(conn, "app/src/main/kotlin/A.kt", "app")
            f2 = _file(conn, "app/src/main/kotlin/B.kt", "app")
            # top-level fun, >= 5 tokens → mantido.
            _sym(conn, f1, name="setupToolbar", body_hash="ht",
                 tokens='["a","b","c","d","e"]', line=10)
            _sym(conn, f2, name="setupToolbar", body_hash="ht",
                 tokens='["a","b","c","d","e"]', line=20)
            # composable, >= 5 tokens → mantido.
            _sym(conn, f1, name="Row", kind="composable_fun", body_hash="hrow",
                 tokens='["a","b","c","d","e"]', line=30)
            _sym(conn, f2, name="Row", kind="composable_fun", body_hash="hrow",
                 tokens='["a","b","c","d","e"]', line=40)
            # trivial (<5 tokens) → filtrado pelo piso.
            _sym(conn, f1, name="setX", body_hash="hx", tokens='["a","b"]', line=50)
            _sym(conn, f2, name="setX", body_hash="hx", tokens='["a","b"]', line=60)
            # test-source dup (>=5 tokens) → excluído por path.
            t1 = _file(conn, "app/src/test/java/AlphaTest.kt", "app", source_set=None)
            t2 = _file(conn, "app/src/test/java/BetaTest.kt", "app", source_set=None)
            _sym(conn, t1, name="setUp", body_hash="hs",
                 tokens='["a","b","c","d","e"]', line=5)
            _sym(conn, t2, name="setUp", body_hash="hs",
                 tokens='["a","b","c","d","e"]', line=6)
    finally:
        conn.close()
    rows = queries.find_duplicates_within_module(tmp_path, db_path=db)
    assert {r["name"] for r in rows} == {"setupToolbar", "Row"}


def test_cross_read_broadened_bypasses_floor(tmp_path: Path) -> None:
    """Cross-module read-side bypassa o piso (2 tokens mantido). Regression
    guard do espelhamento cross-module."""
    db = tmp_path / "g.db"
    conn = open_db(db, create=True)
    try:
        with transaction(conn):
            f1 = _file(conn, "androidApp/src/main/kotlin/State.kt", "androidApp")
            f2 = _file(conn, "shared/src/commonMain/kotlin/State.kt", "shared",
                       source_set="commonMain", platform="common")
            _sym(conn, f1, name="update", body_hash="hu", tokens='["a","b"]',
                 line=5, receiver="MutableState")
            _sym(conn, f2, name="update", body_hash="hu", tokens='["a","b"]',
                 line=5, receiver="MutableState")
    finally:
        conn.close()
    rows = queries.find_duplicates_cross_module(tmp_path, db_path=db)
    assert {r["name"] for r in rows} == {"update"}
```

- [ ] **Step 2: Roda o teste pra confirmar que falha (RED)**

Run: `.venv/bin/pytest tests/unit/test_reuse_read_side_broadened.py -v`
Expected: `test_within_read_broadened_floored_and_test_excluded` FALHA — read-side atual exige `receiver_type IS NOT NULL` + `kind='fun'`, então `setupToolbar`/`Row`/`setX`/`setUp` (receiver NULL) não são detectados → `rows == []` → asserção espera `{"setupToolbar","Row"}`. (`test_cross_read_broadened_bypasses_floor` já passa — `update` é extension com receiver → regression guard.)

- [ ] **Step 3a: Espelha `find_duplicates_within_module` (queries.py)**

Estado atual (linhas 441-474): `WHERE s.kind = 'fun' AND s.receiver_type IS NOT NULL AND s.body_hash IS NOT NULL AND f.path LIKE '%.kt'`, SELECT sem `body_tokens`, `return [dict(row) for row in rows]`. Substitui o corpo da função (do `rows = conn.execute(` até o `return`) por:

```python
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT s.name, s.receiver_type, s.signature, s.body_hash, s.body_tokens, s.modifiers,
                   f.module AS module, f.source_set AS source_set,
                   GROUP_CONCAT(f.id || ':' || s.line_start || ':' || f.path, char(31)) AS occurrences,
                   COUNT(*) AS n
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE s.kind IN ('fun', 'composable_fun')
              AND s.body_hash IS NOT NULL
              AND f.path LIKE '%.kt'
              AND f.path NOT LIKE '%/src/test/%'
              AND f.path NOT LIKE '%/src/androidTest/%'
              AND f.path NOT LIKE '%/src/androidUnitTest/%'
              AND f.path NOT LIKE '%/src/androidHostTest/%'
              AND f.path NOT LIKE '%/src/commonTest/%'
              AND f.path NOT LIKE '%/src/iosTest/%'
              AND f.path NOT LIKE '%/src/jvmTest/%'
            GROUP BY f.module, COALESCE(f.source_set, ''),
                     COALESCE(s.receiver_type, ''), s.name, s.signature, s.body_hash
            HAVING COUNT(*) > 1
            ORDER BY n DESC, f.module, COALESCE(s.receiver_type, ''), s.name
            """
        ).fetchall()
        return [
            dict(row)
            for row in rows
            if _distinct_body_token_count(row["body_tokens"]) >= REUSE_MIN_BODY_TOKENS
        ]
    finally:
        conn.close()
```

Atualiza também a docstring (linhas 446-451) pra refletir o universo ampliado + piso:

```python
    """Q12 — mesma função Kotlin declarada 2+ vezes dentro de UM módulo Gradle.

    Universo ampliado (GRAPH-REUSE-STAGE2): top-level `fun`, `composable_fun` e
    extensions (`kind IN ('fun','composable_fun')`) — não só extensions.
    Agrupa por (module, source_set, receiver_type, name, signature, body_hash).
    Filtra grupos com < ``REUSE_MIN_BODY_TOKENS`` tokens distintos (piso de
    trivialidade) e exclui código de teste. Alimenta ``consolidate-duplicate-helper``.
    """
```

- [ ] **Step 3b: Espelha `find_duplicates_cross_module` (queries.py)**

Estado atual (linhas 477-510): `WHERE s.kind = 'fun' AND s.receiver_type IS NOT NULL ...`. Substitui o corpo da função por:

```python
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            """
            SELECT s.name, s.receiver_type, s.signature, s.body_hash, s.modifiers,
                   GROUP_CONCAT(DISTINCT f.module) AS modules,
                   GROUP_CONCAT(f.id || ':' || s.line_start || ':' || f.path, char(31)) AS occurrences,
                   COUNT(DISTINCT f.module) AS n_modules,
                   COUNT(*) AS n_files
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE s.kind IN ('fun', 'composable_fun')
              AND s.body_hash IS NOT NULL
              AND f.path LIKE '%.kt'
              AND f.path NOT LIKE '%/src/test/%'
              AND f.path NOT LIKE '%/src/androidTest/%'
              AND f.path NOT LIKE '%/src/androidUnitTest/%'
              AND f.path NOT LIKE '%/src/androidHostTest/%'
              AND f.path NOT LIKE '%/src/commonTest/%'
              AND f.path NOT LIKE '%/src/iosTest/%'
              AND f.path NOT LIKE '%/src/jvmTest/%'
            GROUP BY COALESCE(s.receiver_type, ''), s.name, s.signature, s.body_hash
            HAVING COUNT(DISTINCT f.module) > 1
            ORDER BY n_modules DESC, n_files DESC, COALESCE(s.receiver_type, ''), s.name
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
```

> **Fidelidade ao original:** confirme antes de editar que o SELECT de `find_duplicates_cross_module` NÃO tem a linha `GROUP_CONCAT(COALESCE(f.source_set, '')) AS source_sets` (o espelho read-side da `queries.py` não a carrega hoje — só o `duplicates.py` a tem). Preserve o SELECT existente e só troque WHERE/GROUP BY/ORDER BY. Cross-module NÃO recebe `s.body_tokens` nem piso (bypass por design).

Atualiza a docstring (linhas 482-486) pra o universo ampliado:

```python
    """Q13 — mesma função Kotlin declarada em 2+ módulos Gradle distintos.

    Universo ampliado (GRAPH-REUSE-STAGE2): `kind IN ('fun','composable_fun')`.
    Agrupa por (receiver_type, name, signature, body_hash) com COUNT(DISTINCT
    module) > 1. Exclui código de teste. Cross-module BYPASSA o piso de
    trivialidade (sinal mais forte). Alimenta ``promote-to-shared-helper``.
    """
```

- [ ] **Step 3c: Test-sync — `test_query_q12_duplicates_within_module.py`**

Este teste QUEBRA agora (o piso read-side filtra o happy-path porque `_insert_kt_extension` semeia `body_tokens = NULL` → 0 tokens < 5). É test-sync no MESMO commit da mudança que o quebra (Mandamento #6), NÃO scope creep. Edita o helper `_insert_kt_extension` (linhas 27-44) pra semear `body_tokens` com >=5 tokens distintos:

```python
def _insert_kt_extension(
    conn,
    file_id: int,
    *,
    name: str,
    receiver_type: str,
    signature: str,
    body_hash: str | None,
    line: int = 10,
    body_tokens: str = '["t1","t2","t3","t4","t5"]',
) -> None:
    conn.execute(
        """
        INSERT INTO symbols(file_id, name, kind, signature, line_start,
                            receiver_type, body_hash, body_tokens, modifiers)
        VALUES (?, ?, 'fun', ?, ?, ?, ?, ?, '')
        """,
        (file_id, name, signature, line, receiver_type, body_hash, body_tokens),
    )
```

(Os 3 testes existentes seguem corretos: `happy_path` — o grupo `h1` agora tem 5 tokens → sobrevive ao piso → 1 row; `cross_module_excluded` — módulos distintos → within-module vazio; `null_body_hash_excluded` — `body_hash IS NOT NULL` filtra antes. As paths `app/android/A.kt` não casam predicado de teste.)

- [ ] **Step 4: Roda os testes pra confirmar que passam (GREEN)**

Run: `.venv/bin/pytest tests/unit/test_reuse_read_side_broadened.py tests/unit/test_query_q12_duplicates_within_module.py -v`
Expected: `test_reuse_read_side_broadened` → `2 passed`; `test_query_q12` → `3 passed`.

- [ ] **Step 5: Regressão da lane de reuse inteira (guard)**

Run: `.venv/bin/pytest tests/unit/test_query_q12_duplicates_within_module.py tests/unit/test_query_q13_duplicates_cross_module.py tests/unit/test_reuse_intelligence.py tests/unit/test_platform_aware_reuse_queries.py tests/unit/test_infer_suggested_target_categories.py tests/unit/test_queries_list_reuse_findings_perf.py tests/unit/test_graph_parsers.py tests/unit/test_reuse_universe_broadened.py tests/unit/test_reuse_triviality_floor_and_test_exclusion.py -q`
Expected: all pass. Esta é a lane completa de reuse (o sweep inteiro + os 3 testes novos). Se algo além de `test_query_q12` falhar, PARE — o sweep perdeu um teste; reconcilie antes de commitar.

- [ ] **Step 6: CHANGELOG entry**

Em `CHANGELOG.md` sob `## [Unreleased] > ### Changed`:

```markdown
- **Reuse-intelligence: read-side espelha o universo ampliado (GRAPH-REUSE-STAGE2):** `find_duplicates_within_module` / `find_duplicates_cross_module` (`engine/graph/queries.py`, read-time do `forge graph`) recebem o mesmo universo ampliado + exclusão de teste (SQL idêntico ao `duplicates.py`) + piso `REUSE_MIN_BODY_TOKENS` (within-only, via `_distinct_body_token_count` importado de `duplicates.py`), pra que detecção build-time e read interativo fiquem consistentes. `test_query_q12` atualizado pra semear `body_tokens` (test-sync).
```

- [ ] **Step 7: Commit**

```bash
git add engine/graph/queries.py tests/unit/test_reuse_read_side_broadened.py tests/unit/test_query_q12_duplicates_within_module.py CHANGELOG.md
git commit -m "feat(graph): espelha universo ampliado + piso no read-side (queries.py)"
```

---

## Task 4: Doc-sync (graph.md + README + 04-pending) + confirmação do sweep

**Files:**
- Modify: `docs/schemas/graph.md` (seção reuse-intelligence, ~linhas 630-717)
- Modify: `README.md` (bump da contagem `rapid` — linhas 125 e 198)
- Modify: `docs/design/04-pending.md` (4 follow-ons)
- Modify: `CHANGELOG.md` (polish/consolidação, se necessário)

**Interfaces:** doc only. Depende de Tasks 1–3 verdes. Sem código, sem novo teste.

- [ ] **Step 1: Full-lane verde + confirmação do sweep**

Antes de tocar docs, confirma o estado real:

Run: `.venv/bin/pytest -m 'not integration and not e2e' -q | tail -3`
Expected: verde, sem regressão de contagem além dos 3 arquivos novos (+ os testes que eles adicionam). Anota o número `NNNN passed` reportado — é o input do bump do README (Step 3). NÃO hardcode; use a saída.

Também roda `forge verify` (ou `python -m engine ...` conforme o repo) e confirma sem hard fail.

- [ ] **Step 2: Doc de comportamento — `docs/schemas/graph.md`**

Na seção reuse-intelligence (localize com `grep -n "Q12\|Q13\|receiver_type\|duplicate-within-module" docs/schemas/graph.md` — âncoras: nota do `receiver_type` ~linha 643, tabela Q12–Q17 ~linhas 712-717). Documenta a mudança de comportamento do universo de reuse — o texto exato fica a cargo do executor, cobrindo:

1. A detecção de dup exata (Q12 within-module, Q13 cross-module) NÃO exige mais extension function (`receiver_type IS NOT NULL`). O universo agora é `kind IN ('fun','composable_fun')` — top-level funs, composables e extensions. (Os outros kinds não carregam `body_hash`.)
2. Piso de trivialidade `REUSE_MIN_BODY_TOKENS = 5` (`engine/graph/duplicates.py`): within-module com < 5 `body_tokens` distintos é descartado; cross-module (≥2 módulos) bypassa. Calibrado no precision spike (72%→98%).
3. Exclusão de test-source (path-based): `src/test`, `src/androidTest`, `src/androidUnitTest`, `src/androidHostTest`, `src/commonTest`, `src/iosTest`, `src/jvmTest`.
4. Advise-only: nada disso é enforcement; findings fluem pela pipeline de proposals.

Se a nota do `receiver_type` (~linha 643) diz "Non-NULL only for extension...", ela permanece factualmente correta (é sobre a coluna), mas adicione uma frase de que a detecção de dup não depende mais dela.

- [ ] **Step 3: Bump da contagem `rapid` no README**

Único bump de stat da wave (Mandamento #6), consolidado aqui. Usa o número confirmado no Step 1.

- `README.md:125` — a linha da tabela `Tests` (`rapid **NNNN passed** ...`). Atualiza o número e, no parêntese descritivo, acrescenta um marcador `GRAPH-REUSE-STAGE2: universo de dup ampliado + piso de trivialidade` junto do já-presente `GRAPH-REAL-REPO Stage 1`.
- `README.md:198` — o espelho no tree view (`rapid NNNN / integration NNN / e2e NN`). Mantém consistente com o mesmo número.

Se houver outros espelhos da stat `rapid`, mantém todos com o mesmo número (grep `rapid` no README).

- [ ] **Step 4: Follow-ons em `docs/design/04-pending.md`**

Registra os 4 follow-ons deferidos pelo spec (Mandamentos #6/#7 — não virar dívida silenciosa). Adiciona antes do bloco `---`/handoff no fim do arquivo:

```markdown
### GRAPH-REUSE-STAGE2 — follow-ons deferidos

- **(a) Parser gap `symbols.modifiers` vazio.** Todas as funções têm
  `modifiers` vazio → não dá pra special-casar `override`/`private` na
  detecção de reuse. O piso por token sidesteppa a necessidade hoje; fixar o
  parser é pré-requisito pra qualquer regra baseada em modifier.
- **(b) Parser gap `line_end == line_start` pra 100% das funções.** Sem extent
  de função rastreado → impossível piso baseado em linhas. O piso por
  `body_tokens` evita isso; um piso por linhas exige fixar o extent primeiro.
- **(c) `kmp-migration` sub-track (SEPARADO).** O match cross-lang atual
  (nome + `receiver_type` exato entre Kotlin/Swift) nunca casa. Precisa de
  match name-only + similaridade ou type-map. Non-goal do Stage 2.
- **(d) Member-functions no universo de reuse.** O Stage 2 mediu top-level
  `fun` + `composable_fun` (os kinds que carregam `body_hash` hoje). Membros de
  classe não foram medidos — considerar num incremento futuro, com re-spike.
```

- [ ] **Step 5: CHANGELOG polish (se necessário)**

Relê as 3 entradas Stage 2 adicionadas (Tasks 1-3) sob `## [Unreleased] > ### Changed`; garante que lêem coerentes como um bloco (universo → piso → read-side). Ajusta só se houver redundância/contradição — não reescreve.

- [ ] **Step 6: Commit**

```bash
git add docs/schemas/graph.md README.md docs/design/04-pending.md CHANGELOG.md
git commit -m "docs(graph): doc-sync do universo ampliado Stage 2 (graph.md/README/pending)"
```

---

## Final validation gate (orchestrator-run — NÃO é uma task de código)

Este é o check AC-5 no app real. O **orquestrador** (não um `gsd-executor`) roda depois das 4 tasks verdes. ZERO mutação no repo do app.

- [ ] **G1: Full-lane verde + `forge verify`**

Run: `.venv/bin/pytest -q` (lane completa, incluindo `-m integration` e `-m e2e`)
Expected: tudo passa, sem regressão de contagem vs. o baseline da branch. Depois `forge verify` → sem hard fail.

- [ ] **G2: Re-spike vs `inchurch-app-main` (isolado, read-only)**

Mesmo protocolo do precision spike: worktree isolado de feature-forge com `.venv` PRÓPRIO (trap de editable-install — verifique `python -c "import engine; print(engine.__file__)"` apontando DENTRO do worktree, não o repo principal), DB do graph escrito no scratchpad (nunca dentro do app). App `/Users/thg.inchurch/StudioProjects/inchurch-app-main` é input read-only.

```bash
python - <<'PY'
import sqlite3
from pathlib import Path
from engine.graph.builder import build_full
app = Path("/Users/thg.inchurch/StudioProjects/inchurch-app-main")
db = Path("/private/tmp/claude-503/-Users-thg-inchurch-Documents-feature-forge/aa8d73d7-b9fd-4fb3-b5a8-8720e724dca0/scratchpad/inchurch-stage2-gate.db")
stats = build_full(app, db_path=db)
print("BUILD:", stats)
conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
for r in conn.execute("SELECT category, COUNT(*) c FROM reuse_findings GROUP BY category ORDER BY c DESC"):
    print(f"  {r['category']:32s} {r['c']}")
tot = conn.execute(
    "SELECT COUNT(*) c FROM reuse_findings WHERE category IN "
    "('duplicate-within-module','duplicate-cross-module')").fetchone()["c"]
print("WITHIN+CROSS total:", tot)
conn.close()
PY
```

Reporte:
- **(a)** Build completa + tempo total.
- **(b)** `duplicate-within-module` + `duplicate-cross-module` somados = **~65** (target). Base do recompute contra o `groups.json` do spike: **~63 within** (nmod==1, `ntok≥5`, não-teste) + **~2–3 cross** (não-teste) ≈ 65–66. A dedução Q16→Q12→Q13 do engine (precedência por `claimed_exact`) pode deslocar por ±alguns; um desvio grande (ex.: <50 ou >90) sinaliza que uma das 3 mudanças (broaden/piso/exclusão) não pegou — investigar antes do go.
- **(c)** Precisão amostrada ~98%: amostre ~15-20 findings (spread por token-count) e confirme que são consolidações REAIS (fluxo Google-signin, `setupToolbar` em N fragments, `resize` em N dialogs). 0 FALSE é estrutural (agrupamento por `body_hash` exato não misgroupa).

Se G2 confirmar ~65 @ ~98%, o incremento Stage 2 está validado. NÃO iniciar sub-tracks (kmp-migration, fuzzy) a partir deste plano.

---

## Self-Review — Spec coverage (AC → task)

| AC | Requisito | Task(s) |
|---|---|---|
| **AC-1 — Universo ampliado** | `_q_duplicates_within_module` + `_q_duplicates_cross_module` (`duplicates.py`) e os espelhos `find_duplicates_within_module` + `find_duplicates_cross_module` (`queries.py`) dropam `receiver_type IS NOT NULL` e incluem `kind IN ('fun','composable_fun')`; extensions permanecem; fixture com top-level fun + composable não-extension produz finding, extension segue produzindo | **Task 1** (detecção) + **Task 3** (read-side); teste `test_reuse_universe_broadened` (top-level + composable + extension) + `test_reuse_read_side_broadened` |
| **AC-2 — Piso de trivialidade** | `REUSE_MIN_BODY_TOKENS = 5` filtra within-module com < 5 `body_tokens` distintos; cross-module (≥2 módulos) bypassa; contagem replica o spike | **Task 2** (constante + helper + floor-skip within, cross bypassa) + **Task 3** (piso read-side within-only); teste `test_reuse_triviality_floor_and_test_exclusion` (≤4 filtrado, ≥5 mantido, cross 2-token mantido) |
| **AC-3 — Exclusão de teste** | Símbolos em test source-sets/paths (`commonTest`/`androidTest`/`iosTest`/`androidUnitTest`/`jvmTest`/`androidHostTest` + `src/test`) não entram na detecção | **Task 2** (bloco path-based nas duas queries de `duplicates.py`) + **Task 3** (idêntico em `queries.py`); teste `test_test_source_duplicate_not_reported` + o caso `setUp` em `test_reuse_read_side_broadened` |
| **AC-4 — Advise-only (fronteira)** | Findings seguem por `reuse_findings → proposed-evolutions`; nenhum gate/hard-block novo | **Todas** — nenhuma task adiciona gate (reviewable no diff); top-level fun renderiza via `receiver or "(top-level)"` (código existente); `test_reuse_intelligence` (proposal-queuing, `n_queued >= 1`) permanece verde = pipeline intacta |
| **AC-5 — Verde + re-spike** | `pytest` full verde (testes existentes atualizados) + `forge verify` sem hard fail; re-spike ~65 @ ~98% | **Task 3** Step 5 (lane de reuse) + **Task 4** Step 1 (full rapid) + **Final gate** G1 (full lane + verify) + G2 (re-spike) |
| **Follow-ons** | (a) `modifiers` vazio; (b) `line_end==line_start`; (c) kmp-migration sub-track; (d) member-functions | **Task 4** Step 4 (`04-pending.md`) |

**Placeholder scan:** nenhum — cada step de código mostra o SQL/Python verbatim antes/depois contra as âncoras de linha reais (`duplicates.py:185-227`, `queries.py:441-510`, loop `detect_all_reuse_findings:107-123`); cada step de teste mostra o código de teste completo; cada step de run dá o comando `.venv/bin/pytest …` exato + saída esperada.

**Type/name consistency:** `REUSE_MIN_BODY_TOKENS` (int, `duplicates.py`) e `_distinct_body_token_count(body_tokens_json: Optional[str]) -> int` são definidos na Task 2 e importados identicamente pela `queries.py` na Task 3. O filtro de kind `kind IN ('fun', 'composable_fun')` é literal-idêntico nas 4 queries (2 em `duplicates.py`, 2 em `queries.py`). O bloco de 7 `AND f.path NOT LIKE '%/src/<test-set>/%'` é literal-idêntico nas 4 queries. `COALESCE(s.receiver_type, '')` no GROUP BY/ORDER BY é idêntico nas 4. O piso (Python) aparece só no caminho within-module (loop de detecção + list-comprehension read-side); cross-module NUNCA aplica piso nas 2 metades.

**Sweep completo (aprendizado do Stage 1):** varredura em `tests/` por `detect_all_reuse_findings`/`find_duplicates_within_module`/`find_duplicates_cross_module` retornou 7 arquivos. 1 quebra (`test_query_q12` — corrigido na Task 3, mesmo commit) + 6 verificados-verdes com raciocínio (tabela "Sweep de testes existentes"). A Task 3 Step 5 roda os 9 (6 do sweep + 3 novos) juntos como safety net.
