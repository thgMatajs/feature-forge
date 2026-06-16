# GRAPH-IA — Codebase graph evolution for AI consumption + legacy language coverage

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evoluir o codebase graph do forge em duas frentes paralelas: (1) IA-ready — adicionar coluna `body` em `symbols` para expor texto-fonte cru + flag `--json` em `forge graph` pra consulta non-interactive por IAs (Claude Code, etc.), economizando tokens de contexto ao substituir leitura de fonte por consulta ao graph; (2) Cobertura legado — parsers Java, XML (Android), e Objective-C (legado mobile) para que projetos que misturam linguagens recebam a mesma cobertura de graph que Kotlin/Swift/TypeScript.

**Spec:** docs/superpowers/specs/2026-06-12-graph-ia-evolution.md

**Non-goals (explicitamente fora de escopo):**
- Tree-sitter (deixar pra depois, regex suficiente)
- MCP server (IA consulta via `forge graph --json`)
- Call graph completo pra ObjC
- Call graph preciso pra qualquer linguagem (regex atual é suficiente)
- Mudança de schema de versão (body column adicionada com migration, sem bump SCHEMA_VERSION)
- Visualização gráfica (D3.js, etc.)

**Release target:** v1.3.0 (bump menor)

---

## Architecture sketch

```
Onda 1 ────────────────────────────────────────
  symbols.body (TEXT) ← texto-fonte cru preservado
  ┌─ engine/utils/sqlite_io.py     ── nova tabela? não — ALTER TABLE ADD COLUMN body
  │                                  via _ensure_graph_body_column()
  ├─ engine/graph/builder.py       ── _persist_* recebem source_text + escrevem body
  ├─ engine/graph/incremental.py   ── _refresh_file passa source_text pra _persist_*
  └─ engine/graph/parsers_*.py     ── dataclasses ganham field body: Optional[str]

Onda 2 ────────────────────────────────────────
  forge graph --json <qN> [--file path]
  ┌─ engine/graph_cli.py           ── argv parseia --json; chama mesma _HANDLERS
  │                                  mas renderiza como dict/json.dumps
  └─ engine/graph/queries.py       ── nenhuma mudança (reusa Q1–Q17)

Onda 3 ────────────────────────────────────────
  Java parser (estrutura idêntica ao parser_kotlin.py)
  ┌─ engine/graph/parser_java.py   ── JavaFileInfo + parse_java_file()
  └─ tests/unit/test_parser_java.py

Onda 4 ────────────────────────────────────────
  XML parser (layout + resources Android)
  ┌─ engine/graph/parser_xml.py    ── XmlFileInfo + parse_xml_file()
  └─ tests/unit/test_parser_xml.py

Onda 5 ────────────────────────────────────────
  ObjC parser simplificado (imports + símbolos, SEM call graph)
  ┌─ engine/graph/parser_objc.py   ── ObjcFileInfo + parse_objc_file()
  └─ tests/unit/test_parser_objc.py

Onda 6 ────────────────────────────────────────
  Registrar extensões + hooks incrementais
  ┌─ engine/graph/builder.py       ── _LANGUAGE_EXTENSIONS +java +.xml +.m +.mm
  ├─ engine/graph/_body_text.py    ── _SUPPORTED_LANGS +java +xml +objc
  ├─ engine/ingest.py              ── _GRAPH_EXTENSIONS +java +xml +m +mm
  ├─ hooks/post-edit-codebase-graph.sh ── case match +java +xml +m +mm
  ├─ engine/graph/builder.py       ── _persist_java, _persist_xml, _persist_objc
  └─ engine/graph/incremental.py   ── _refresh_file dispatches novos languages

Onda 7 ────────────────────────────────────────
  Instrução pro modelo (IA consumption docs)
  ┌─ AGENTS.md ou CLAUDE.md
```

### Módulos novos

| Módulo | Linhas approx | Responsabilidade |
|---|---|---|
| `engine/graph/parser_java.py` | ~250 | Regex-based Java symbol + import extractor (classes, métodos, imports) |
| `engine/graph/parser_xml.py` | ~300 | XML parser: view IDs (`@+id/`, `@id/`), classes referenciadas, data binding, resource keys, binding actions |
| `engine/graph/parser_objc.py` | ~200 | ObjC simplificado: `@interface`, `@implementation`, `@protocol`, métodos, `#import`/`@import` |
| `tests/unit/test_parser_java.py` | ~150 | Testes unitários Java parser |
| `tests/unit/test_parser_xml.py` | ~150 | Testes unitários XML parser |
| `tests/unit/test_parser_objc.py` | ~100 | Testes unitários ObjC parser |

### Módulos modificados

| Módulo | Tipo de mudança |
|---|---|
| `engine/utils/sqlite_io.py` | Migration: add `body` column to `symbols` via `_ensure_graph_body_column()` |
| `engine/graph/builder.py` | Add `body` column insert in `_persist_kotlin`, `_persist_swift`, `_persist_typescript`; add `_LANGUAGE_EXTENSIONS` entries; add `_persist_java`, `_persist_xml`, `_persist_objc` |
| `engine/graph/incremental.py` | Pass `source_text` through `_refresh_file`; dispatch new languages |
| `engine/graph/parser_kotlin.py` | `KotlinSymbolInfo.body: Optional[str]` |
| `engine/graph/parser_swift.py` | `SwiftSymbolInfo.body: Optional[str]` |
| `engine/graph/parser_typescript.py` | `TypeScriptSymbolInfo.body: Optional[str]` |
| `engine/graph/_body_text.py` | `_SUPPORTED_LANGS` + `java` (body extraction via `{}` já funciona), + `xml`, + `objc` (se aplicável) |
| `engine/graph_cli.py` | `--json` flag + JSON render path |
| `engine/ingest.py` | `_GRAPH_EXTENSIONS` + `.java`, `.xml`, `.m`, `.mm` |
| `hooks/post-edit-codebase-graph.sh` | Case match novos extensions |
| `docs/schemas/graph.md` | Document `symbols.body` column; document `--json` flag |
| `AGENTS.md` ou `CLAUDE.md` | Instrução pro modelo consultar graph antes de ler fontes |

---

## Reuse-first evidence (Mandamento #3)

Antes de criar helpers novos, consultei o engine existente — combinando consulta canônica via `forge graph` (Q11/Q15 per `.claude/rules/reuse.md §1`) e fallback grep (`§2`):

```bash
# Consulta canônica via graph queries (Q11/Q15)
forge graph --json q11 parser
# → Q11 não retorna helper compartilhado pra brace-scan multi-lang;
#   `_body_text.extract_function_body` é o único helper genérico e já é reusado.

forge graph --json q15
# → Q15 confirma kotlin/swift/typescript não-near-duplicate à java/objc —
#   semanticamente distinto, duplicação cosmética via shared `_body_text` é
#   caminho consciente (Caminho C do 3-caminhos canônico do reuse.md).

# Migration pattern existente (body_hash, body_tokens)
grep -n "_ensure_reuse_intelligence_columns\|_ensure_imports_to_file_id" engine/graph/builder.py
# → :739 _ensure_imports_to_file_id_column, :748 _ensure_reuse_intelligence_columns

# _LANGUAGE_EXTENSIONS (registro de extensões)
grep -n "_LANGUAGE_EXTENSIONS" engine/graph/builder.py
# → :59 (dict .kt→kotlin, .swift→swift, .ts→typescript, .js→javascript)

# _GRAPH_EXTENSIONS em ingest.py
grep -n "_GRAPH_EXTENSIONS" engine/ingest.py
# → :45 (set dos mesmos)

# Post-edit hook case match
grep -n "case\|# " hooks/post-edit-codebase-graph.sh
# → :23 case match das extensões existentes

# Dispatcher em _ingest_file (builder.py)
grep -n "if language == " engine/graph/builder.py
# → :396 kotlin, :399 swift, :402 typescript/javascript

# Dispatcher similar em incremental.py
grep -n "if language == " engine/graph/incremental.py
# → :257 kotlin, :260 swift, :263 typescript/javascript

# _SUPPORTED_LANGS em _body_text.py
grep -n "_SUPPORTED_LANGS" engine/graph/_body_text.py
# → :22 frozenset({"kotlin", "swift", "typescript", "javascript"})

# forge graph handler map
grep -n "_HANDLERS" engine/graph_cli.py
# → :266 dict {'1': ..., '2': ..., ... '17': ..., 'r': ...}

# forge graph CLI arg parsing
grep -n "def run\|argv\|--json\|detect-incremental" engine/graph_cli.py
# → :336 run(argv), :340 non-interactive detect-incremental subcommand
```

Decisões de reuso:

- **`_ensure_*_column` pattern é reusado** para `_ensure_graph_body_column()` — mesmo padrão: `PRAGMA table_info`, `if "body" not in names`, `ALTER TABLE ADD COLUMN`.
- **`_persist_kotlin` / `_persist_swift` / `_persist_typescript`** — cada uma ganha `body` na INSERT columns list, com `symbol.body` (vindo do parser) no lugar de `None`.
- **Parsers existentes** (`parser_kotlin.py`, `parser_swift.py`, `parser_typescript.py`) — todos seguem o mesmo pattern: dataclass `*FileInfo` + `parse_*_file()` function. Java, XML, ObjC parsers novos seguem idêntico pattern.
- **`_body_text.py:extract_function_body`** — usa `{}` brace scanner. Java tem chaves idênticas ao Kotlin (`{}`). XML não usa chaves (não aplicável). ObjC usa `{}` para `@implementation` / `@interface`. `_SUPPORTED_LANGS` ganha `"java"` e `"objc"` (XML body extraction não se aplica — symbols são tags, não funções com corpo).
- **`forge graph --json`** — reusa `_HANDLERS` map existente. Cada handler chama `gq.*()` query que já retorna Python dicts/lists. Bypassa renderização tree/renderer e vai direto pra `json.dumps`. A flag `--json` é parseada no início de `run(argv)`.
- **Dispatcher em `_ingest_file` e `_refresh_file`** — ambos ganham branches novos no mesmo pattern `if language == "java": ... elif language == "xml": ... elif language == "objc": ...`.
- **`forge graph detect-incremental`** — subcommand já existe como non-interactive entrypoint (`run(argv)` linha 348). `--json` é subcommand diferente, parseado antes do menu interactivo.

---

## File Structure

| Ação | Arquivo | Responsabilidade |
|---|---|---|
| Modificar | `engine/utils/sqlite_io.py` | Migration: `_ensure_graph_body_column()` add `symbols.body TEXT` |
| Modificar | `engine/graph/builder.py` | `_persist_*` ganham column `body`; `_LANGUAGE_EXTENSIONS` +exts; `_ensure_graph_body_column` chamada em `build_full`; `_persist_java`, `_persist_xml`, `_persist_objc` |
| Modificar | `engine/graph/incremental.py` | `_refresh_file` passa `source_text` pros `_persist_*`; dispatch novos languages |
| Modificar | `engine/graph/parser_kotlin.py` | `KotlinSymbolInfo.body: Optional[str]` |
| Modificar | `engine/graph/parser_swift.py` | `SwiftSymbolInfo.body: Optional[str]` |
| Modificar | `engine/graph/parser_typescript.py` | `TypeScriptSymbolInfo.body: Optional[str]` |
| Criar | `engine/graph/parser_java.py` | `JavaFileInfo` + `parse_java_file()` |
| Criar | `engine/graph/parser_xml.py` | `XmlFileInfo` + `parse_xml_file()` |
| Criar | `engine/graph/parser_objc.py` | `ObjcFileInfo` + `parse_objc_file()` |
| Modificar | `engine/graph/_body_text.py` | `_SUPPORTED_LANGS` + `java`, `objc` |
| Modificar | `engine/graph_cli.py` | `--json` flag + JSON output path |
| Modificar | `engine/ingest.py` | `_GRAPH_EXTENSIONS` + `.java`, `.xml`, `.m`, `.mm` |
| Modificar | `hooks/post-edit-codebase-graph.sh` | Case match + `.java`, `.xml`, `.m`, `.mm` |
| Criar | `tests/unit/test_parser_java.py` | Tests Java parser (symbols + imports) |
| Criar | `tests/unit/test_parser_xml.py` | Tests XML parser (view IDs, classes, resources, binding) |
| Criar | `tests/unit/test_parser_objc.py` | Tests ObjC parser (interfaces, implementations, imports) |
| Criar | `tests/fixtures/java-*/` | Fixtures Java parser (minimal .java files) |
| Criar | `tests/fixtures/xml-*/` | Fixtures XML parser (layout .xml + resources .xml) |
| Criar | `tests/fixtures/objc-*/` | Fixtures ObjC parser (minimal .m + .h files) |
| Modificar | `docs/schemas/graph.md` | Doc `symbols.body` column + `--json` flag |
| Modificar | `AGENTS.md` ou `CLAUDE.md` | Instrução pro modelo: consulte graph antes de ler arquivos |
| Modificar | `CHANGELOG.md` | `### Added` — body column, --json, Java/XML/ObjC parsers |
| Modificar | `README.md` | Stats refletindo +26 tests (Java 7 + XML 5 + ObjC 6 + UX 8), 3 parsers Java/XML/ObjC, `--json` flag |
| Modificar | `docs/design/08-session-handoff.md` | "Última atualização" + estado: v1.3.0 graph-ia-evolution |
| Modificar | `docs/design/04-pending.md` | Marca item relacionado se houver |

Justificativa load-bearing (Mandamento #4):

- `docs/schemas/graph.md` — load-bearing per `.claude/rules/scope.md`. Schema doc é fonte canônica das tabelas; sem este edit a coluna `body` e a flag `--json` não entram no contrato.
- `AGENTS.md`/`CLAUDE.md` — load-bearing per scope.md. Instrução ao modelo é a entrega da Onda 7; sem ela a IA não sabe que o graph existe.

---

## Task 0: Pre-flight check (env + dep)

**Files:** none (read-only)

- [ ] **Step 0.1: Confirmar Python ≥3.11**

Run:
```bash
grep -n "python" pyproject.toml | head -3
python3 --version
```
Expected: `requires-python = ">=3.11"` (ou superior); `python3 --version` em 3.11+.

- [ ] **Step 0.2: Confirmar baseline pytest verde + registrar count**

Run: `pytest -q 2>&1 | tail -3` (confirmar zero failures)

Registrar count baseline:
```bash
pytest --collect-only -q | tail -1
```
Anotar o valor numérico (ex.: `1113 tests collected`) pra comparar em Step 10.1 — `count_final ≥ count_baseline + 26 (Java 7 + XML 5 + ObjC 6 + onboarding UX 8 — Java/XML/ObjC nas Tasks 4/5/6, UX nas Tasks 9.5.4/9.5.6 com 4+4 tests respectivamente)`.

Se vermelho, abort — não inicia plano em árvore verde-quebrada.

- [ ] **Step 0.3: Verificar working tree limpo + branch correta**

Run: `git status && git symbolic-ref --short HEAD`
Expected: working tree clean; feature branch dedicada (não `main` / `master` / `develop`). Confirmar via `git symbolic-ref --short HEAD`.

---

## Task 1: Body column — migration SQL + persist functions (Onda 1)

**Files:**
- Modify: `engine/utils/sqlite_io.py`
- Modify: `engine/graph/builder.py`
- Modify: `engine/graph/parser_kotlin.py`
- Modify: `engine/graph/parser_swift.py`
- Modify: `engine/graph/parser_typescript.py`

- [ ] **Step 1.1: Adicionar `_ensure_graph_body_column` em `builder.py`**

Próximo a `_ensure_reuse_intelligence_columns`, adicionar:

```python
def _ensure_graph_body_column(conn: sqlite3.Connection) -> None:
    """Migration: add `symbols.body TEXT` for IA-ready source text (schema v2 compat).

    Stores raw source text (with comments preserved) for symbol bodies.
    Added as ALTER TABLE so legacy DBs (v2 without body) get the column
    without a full rebuild.
    """
    cols = {c["name"] for c in conn.execute("PRAGMA table_info(symbols)").fetchall()}
    if "body" not in cols:
        conn.execute("ALTER TABLE symbols ADD COLUMN body TEXT")
```

Chamar em `build_full()` após `_ensure_reuse_intelligence_columns`:
```python
_ensure_graph_body_column(conn)
```

- [ ] **Step 1.2: Adicionar `body` no INSERT de `_persist_kotlin`**

Em `builder.py:_persist_kotlin`, adicionar `body` na coluna e `symbol.body` no VALUES:

```python
cur = conn.execute(
    "INSERT INTO symbols("
    "  file_id, name, kind, signature, line_start, line_end, visibility, "
    "  receiver_type, body_hash, body_tokens, modifiers, body"
    ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    (
        file_id,
        symbol.name,
        symbol.kind,
        symbol.signature,
        symbol.line,
        symbol.line,
        symbol.visibility,
        symbol.receiver_type,
        symbol.body_hash,
        symbol.body_tokens,
        " ".join(symbol.modifiers) if symbol.modifiers else None,
        symbol.body,
    ),
)
```

- [ ] **Step 1.3: Adicionar `body` no INSERT de `_persist_swift`**

Mesmo pattern: adicionar `body` na coluna e `s.body` no symbol_rows tuple.

- [ ] **Step 1.4: Adicionar `body` no INSERT de `_persist_typescript`**

Mesmo pattern: adicionar `body` na coluna e `s.body` no symbol_rows tuple.

- [ ] **Step 1.5: Adicionar `body: Optional[str]` nas dataclasses dos parsers**

Em `parser_kotlin.py:KotlinSymbolInfo`:
```python
body: Optional[str] = None
```

Em `parser_kotlin.py:KotlinFunctionInfo` (se `body` não estiver presente):
```python
body: Optional[str] = None
```

Em `parser_swift.py:SwiftSymbolInfo`:
```python
body: Optional[str] = None
```

Em `parser_typescript.py:TypeScriptSymbolInfo`:
```python
body: Optional[str] = None
```

Os parsers já extraem `body_text` via `_body_text.extract_function_body` antes de computar `body_hash`. Atribuir o `body_text` extraído ao field `body`:

Em `parser_kotlin.py` (~linha 261-263), onde `body_text` já é extraído:
```python
body_hash = hash_body(body_text) if body_text is not None else None
tokens = extract_body_tokens(body_text, language="kotlin") if body_text is not None else None
body_tokens_json = tokens_to_json(tokens) if tokens else None
```
Adicionar:
```python
body = body_text  # texto-fonte cru preservado
```

Em `parser_swift.py` e `parser_typescript.py`, mesmo pattern.

- [ ] **Step 1.6: Verificar INSERT columns + VALUES sincronizados**

Run:
```bash
grep -n "INSERT INTO symbols(" engine/graph/builder.py | head -5
```
Esperado: 3 ocorrências (_persist_kotlin, _persist_swift, _persist_typescript) com `body` na lista de colunas.

- [ ] **Step 1.7: Rodar pytest — sem regressão**

Run: `pytest -q 2>&1 | tail -3`
Expected: green (body column é adicionada via ALTER TABLE — zero quebra de schema). Se testes de graph falharem porque o column count mudou, ajustar.

**NÃO fazer:** bumpar `SCHEMA_VERSION` (body column é adicionada via migration, não muda o schema init). Alterar `_SCHEMA_DDL` em `sqlite_io.py` para incluir `body` no CREATE TABLE (já que `IF NOT EXISTS` + ALTER TABLE cobre legacy; o DDL canônico deve ter a coluna pra DBs novos).

---

## Task 2: Body column — incremental hook (Onda 1)

**Files:**
- Modify: `engine/graph/incremental.py`

- [ ] **Step 2.1: `_ensure_graph_body_column` em `update_file`**

Em `incremental.py:update_file`, adicionar chamada:
```python
from engine.graph.builder import (
    _LANGUAGE_EXTENSIONS,
    _ensure_graph_body_column,  # novo import
    _ensure_imports_to_file_id_column,
    _ensure_reuse_intelligence_columns,
    ...
)
```
No corpo de `update_file`:
```python
_ensure_imports_to_file_id_column(conn)
_ensure_reuse_intelligence_columns(conn)
_ensure_graph_body_column(conn)  # novo
```

- [ ] **Step 2.2: Confirmar que parsers populam `.body` (sem mudança em `_refresh_file`)**

**Decisão:** Body é extraído durante o parse — o parser lê o arquivo, extrai `body_text`, e atribui ao field `body` do dataclass (Task 1.5). O `_refresh_file` já chama `parse_kotlin_file(file_path)` seguido de `_persist_kotlin(conn, file_id, info)`. Como `info.symbols[N].body` já vem preenchido pelo parser, o `_persist` só precisa incluí-lo no INSERT (já coberto em Task 1.2–1.4). Nenhuma mudança extra no `_refresh_file`.

**Verificação:** Confirmar que parsers estão populando `.body` (Task 1.5) e `_persist_*` estão inserindo (Task 1.2-1.4).

- [ ] **Step 2.3: Rodar pytest — sem regressão**

Run: `pytest -q 2>&1 | tail -3`
Expected: green.

---

## Task 3: `forge graph --json` (Onda 2)

**Files:**
- Modify: `engine/graph_cli.py`

- [ ] **Step 3.1: Parse `--json` flag no início de `run(argv)`**

Em `engine/graph_cli.py:run()`, antes do bloco `if argv and argv[0] == "detect-incremental":`:

```python
json_mode = False
if argv and argv[0] == "--json":
    json_mode = True
    argv = argv[1:]
```

- [ ] **Step 3.2: Skip menu interactivo em `--json` mode**

Quando `json_mode` é True, pular o menu interactivo e o loop de `question.ask`. Em vez disso, parsear o próximo argumento como handler key (`q2`, `4`, `blast-radius`, etc.):

```python
if json_mode:
    if not argv:
        # Sem argumento → erro amigável
        renderer.write(
            "Uso: forge graph --json <query> [args...]\n"
            "  forge graph --json q2 --file LoginUseCase.kt\n"
            "  forge graph --json q4 symbols\n"
        )
        return 1

    query_or_key = argv[0]
    handler_args = argv[1:]

    # Resolver query key a partir de alias curto ou nome
    _resolve_and_run_json(project_root, query_or_key, handler_args)
    return 0
```

- [ ] **Step 3.3: Implementar `_resolve_and_run_json`**

Função que mapeia aliases como `q1`, `q2`, `q17`, `r` ou nomes como `symbols`, `blast-radius` pros handlers existentes, invoca o handler, captura o resultado, e printa como JSON:

```python
def _resolve_and_run_json(
    project_root: Path,
    query_or_key: str,
    args: list[str],
) -> None:
    """Resolve query identifier and print JSON result to stdout.

    Accepts:
      - Short key: ``q1`` .. ``q17``, ``r``
      - Handler label: ``symbols``, ``blast-radius``, etc.
      - Numeric key: ``1`` .. ``17``, ``r``

    Uses the same ``_HANDLERS`` dict (Q1–Q17 + r) and ``_HANDLER_ARGS``
    for argument resolution.
    """
    import json as _json

    # Normalize key: strip 'q' prefix, match label or numeric
    key = query_or_key
    if key.startswith("q") and len(key) > 1 and key[1:].isdigit():
        key = key[1:]
    elif key.startswith("q") and key[1:] == "r":
        key = "r"

    # Match numeric key
    if key in _HANDLERS:
        label, handler_fn = _HANDLERS[key]
    else:
        # Match by label (case-insensitive)
        matched = [(k, v) for k, v in _HANDLERS.items() if v[0] == key.lower()]
        if not matched:
            renderer.write(
                f"forge graph --json: unknown query {query_or_key!r}. "
                f"Use: q1..q17, r, ou label (e.g. symbols)"
            )
            exit(1)
        key, (label, handler_fn) = matched[0]

    # Invoke handler — but we need it to return data, not render.
    # Current handlers are void: they render inline via _render_result.
    # Solution: wrap with a JSON-aware version.
    # Since handler signature is (Path) -> None, we override _render_result
    # for JSON mode by monkey-patching before call.
    # Cleaner approach: extract the query call, collect result, JSON-serialize.

    # For Q1-Q17, the gq.* functions already return dicts/lists.
    # _HANDLERS currently wraps them in _render_result().
    # We bypass _render_result and call gq.* directly.
    _run_json_handler(project_root, key, args)
```

- [ ] **Step 3.4: Implementar `_run_json_handler`**

Mapeamento direto de key → `gq.*` function call + json.dumps:

```python
def _run_json_handler(project_root: Path, key: str, args: list[str]) -> None:
    """Execute the query function and print JSON result."""
    import json as _json
    from engine.graph import queries as gq

    try:
        if key == "1":
            slug = args[0] if args else question.ask_text("feature slug?")
            result = gq.find_similar_features(project_root, slug)
        elif key == "2":
            files = [Path(a) for a in args] if args else [Path(question.ask_text("file path?"))]
            result = gq.blast_radius(project_root, files)
        elif key == "3":
            result = gq.find_orphan_files(project_root)
        elif key == "4":
            module_filter = args[0] if args else None
            result = gq.list_prefixes(project_root, module_filter)
        elif key == "5":
            slug = args[0] if args else None
            result = gq.ds_used_in(project_root, slug)
        elif key == "6":
            slug = args[0] if args else None
            result = gq.i18n_used_in(project_root, slug)
        elif key == "7":
            slug = args[0] if args else None
            result = gq.routes_for(project_root, slug)
        elif key == "8":
            class_name = args[0] if args else None
            result = gq.di_deps(project_root, class_name)
        elif key == "9":
            file_str = args[0] if args else None
            result = gq.tests_for(project_root, file_str)
        elif key == "10":
            slug = args[0] if args else None
            result = gq.feature_commits(project_root, slug)
        elif key == "11":
            type_filter = args[0] if args else None
            result = gq.find_reusable_helpers(project_root, type_filter)
        elif key == "12":
            result = gq.find_dup_within_module(project_root)
        elif key == "13":
            result = gq.find_dup_cross_module(project_root)
        elif key == "14":
            result = gq.find_kmp_migration(project_root)
        elif key == "15":
            result = gq.find_near_duplicates(project_root)
        elif key == "16":
            result = gq.find_redundant_platform_specific(project_root)
        elif key == "17":
            result = gq.find_duplicate_ts_helpers(project_root)
        elif key == "r":
            result = gq.list_reuse_findings(project_root)
        else:
            result = {"error": f"Unknown query key: {key}"}

        print(_json.dumps(result, indent=2, default=str))
    except Exception as exc:
        print(_json.dumps({"error": str(exc)}))
        exit(1)
```

- [ ] **Step 3.5: Rodar smoke test do `--json`**

Run:
```bash
# Criar graph.db primeiro se não existir
forge reconfigure  # ou forge graph --json q3 se db existir

# Testar flags
forge graph --json q3 2>/dev/null | head -5
forge graph --json q4 LoginUseCase 2>/dev/null | head -5
```
Expected: JSON output válido, sem erros.

- [ ] **Step 3.6: Rodar pytest — sem regressão**

Run: `pytest -q 2>&1 | tail -3`
Expected: green.

**NÃO fazer:** refatorar handlers existentes; mudar API das queries `gq.*`; remover modo interactivo.

---

## Task 4: Java parser (Onda 3)

**Files:**
- Create: `engine/graph/parser_java.py`
- Create: `tests/fixtures/java-basic/com/example/LoginUseCase.java`
- Create: `tests/fixtures/java-annotations/com/example/InjectService.java`
- Create: `tests/unit/test_parser_java.py`

**Reuse-first via graph (Mandamento #3):**

```bash
forge graph --json q11 parser
forge graph --json q15
```

Análise: Q11 não retorna helper compartilhado pra brace-scan multi-lang — `_body_text.extract_function_body` é o único helper genérico e já é reusado nos parsers existentes (kotlin/swift/typescript). Q15 confirma que kotlin/swift/typescript não são near-duplicate à java/objc — semanticamente distinto, duplicação cosmética via shared `_body_text` é caminho consciente (Caminho C do 3-caminhos canônico do `reuse.md`).

- [ ] **Step 4.1: Criar fixtures Java**

**Fixture java-basic** — `tests/fixtures/java-basic/com/example/LoginUseCase.java`:
```java
package com.example;

import com.example.domain.User;
import com.example.repository.AuthRepository;
import java.util.List;

public class LoginUseCase {
    private final AuthRepository authRepo;

    public LoginUseCase(AuthRepository authRepo) {
        this.authRepo = authRepo;
    }

    public User execute(String email, String password) {
        return authRepo.login(email, password);
    }
}
```

**Fixture java-annotations** — `tests/fixtures/java-annotations/com/example/InjectService.java`:
```java
package com.example.service;

import com.example.di.Inject;
import com.example.di.Singleton;

@Singleton
public class InjectService {
    @Inject
    public InjectService() {}

    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

- [ ] **Step 4.2: Escrever tests `test_parser_java.py` FALHANDO primeiro (TDD)**

Antes de criar o parser, escrever os tests. Conteúdo do `tests/unit/test_parser_java.py`:

```python
"""Tests for engine.graph.parser_java."""

from pathlib import Path

import pytest

from engine.graph.parser_java import parse_java_file

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_java_basic_parses_package() -> None:
    info = parse_java_file(FIXTURES / "java-basic" / "com" / "example" / "LoginUseCase.java")
    assert info.package == "com.example"


def test_java_basic_parses_imports() -> None:
    info = parse_java_file(FIXTURES / "java-basic" / "com" / "example" / "LoginUseCase.java")
    assert "com.example.domain.User" in info.imports
    assert "com.example.repository.AuthRepository" in info.imports
    assert "java.util.List" in info.imports


def test_java_basic_parses_class() -> None:
    info = parse_java_file(FIXTURES / "java-basic" / "com" / "example" / "LoginUseCase.java")
    classes = [s for s in info.symbols if s.kind == "class"]
    assert len(classes) == 1
    assert classes[0].name == "LoginUseCase"


def test_java_basic_parses_methods() -> None:
    info = parse_java_file(FIXTURES / "java-basic" / "com" / "example" / "LoginUseCase.java")
    methods = [s for s in info.symbols if s.kind == "method"]
    method_names = {s.name for s in methods}
    assert "execute" in method_names


def test_java_annotations_parses_annotation() -> None:
    info = parse_java_file(FIXTURES / "java-annotations" / "com" / "example" / "InjectService.java")
    classes = [s for s in info.symbols if s.kind == "class"]
    assert len(classes) >= 1
    assert classes[0].name == "InjectService"


def test_java_methods_have_body() -> None:
    info = parse_java_file(FIXTURES / "java-basic" / "com" / "example" / "LoginUseCase.java")
    methods = [s for s in info.symbols if s.kind == "method"]
    for m in methods:
        if m.name == "execute":
            assert m.body is not None
            assert "authRepo.login" in m.body
            assert m.body_hash is not None


def test_java_constructor_body() -> None:
    info = parse_java_file(FIXTURES / "java-basic" / "com" / "example" / "LoginUseCase.java")
    ctors = [s for s in info.symbols if s.kind == "constructor"]
    assert len(ctors) >= 1
    assert ctors[0].body is not None
```

Run: `pytest tests/unit/test_parser_java.py -xvs`
Expected: **collection error ou ImportError** porque `engine.graph.parser_java` ainda não existe. Confirmar FAIL antes de prosseguir pro Step 4.3.

- [ ] **Step 4.3: Criar `parser_java.py`**

Estrutura idêntica ao `parser_kotlin.py`. Regex-based, extrai:
- Package (`package com.example;`)
- Imports (`import com.example.domain.User;` — suporta wildcard `.*`, import static)
- Classes: `public class Foo`, `public final class Foo`, `abstract class Foo`, `interface Foo`, `@interface Foo`, `enum Foo`, `record Foo`
- Methods: `public ReturnType methodName(args) { ... }` — inclui modifiers, signature, body text

```python
"""Pragmatic regex-based Java parser.

Extracts package, imports, top-level symbols with visibility, signature,
and body text. Mirrors the Kotlin parser pattern (KotlinFileInfo → JavaFileInfo).

Not an AST — best-effort, downstream consumers tolerate Optional fields.
Switch to tree-sitter for v2 if accuracy bites.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from engine.graph._body_text import (
    extract_body_tokens,
    extract_function_body,
    find_opening_brace,
    hash_body,
    tokens_to_json,
)

_RE_PACKAGE = re.compile(r"^\s*package\s+([\w\.]+)\s*;", re.MULTILINE)
_RE_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w\.\*]+)\s*;", re.MULTILINE)

# Class/interface/enum/record/regex
_RE_CLASS = re.compile(
    r"(?:(?:public|private|protected|abstract|final|static|sealed|non-sealed)\s+)*"
    r"(?:class|interface|@interface|enum|record)\s+"
    r"(\w+)"
    r"(?:\s*<\w+(?:,\s*\w+)*>)?"
    r"(?:\s+extends\s+\w+(?:\.\w+)*(?:<[^>]*>)?)?"
    r"(?:\s+implements\s+[\w\.,\s<>]+)?"
    r"\s*\{",
    re.MULTILINE,
)

_RE_METHOD = re.compile(
    r"(?:(?:public|private|protected|static|final|abstract|synchronized|native|default)\s+)*"
    r"(?:\w+(?:\[\])?(?:<[^>]*>)?\.)?"
    r"(\w+(?:<[^>]*>)?)"
    r"\s+"
    r"(\w+)\s*"
    r"\(([^)]*)\)"
    r"\s*(?:\{|\s*;)",
    re.MULTILINE,
)

# Visibility prefix detection
_VISIBILITY_RE = re.compile(r"(public|private|protected)")


@dataclass
class JavaSymbolInfo:
    name: str
    kind: str  # "class" | "interface" | "enum" | "record" | "method" | "constructor"
    visibility: str = "internal"  # alinhado com Kotlin internal (package-scoped)
    signature: Optional[str] = None
    line: int = 0
    body: Optional[str] = None
    body_hash: Optional[str] = None
    body_tokens: Optional[str] = None
    modifiers: list[str] = field(default_factory=list)
    receiver_type: Optional[str] = None


@dataclass
class JavaFileInfo:
    package: Optional[str]
    imports: list[str]
    symbols: list[JavaSymbolInfo]


def parse_java_file(path: Path) -> JavaFileInfo:
    source = path.read_text(encoding="utf-8")
    return _parse_java(source)


def _parse_java(source: str) -> JavaFileInfo:
    lines = source.split("\n")

    package: Optional[str] = None
    m = _RE_PACKAGE.search(source)
    if m:
        package = m.group(1)

    imports: list[str] = _RE_IMPORT.findall(source)

    symbols: list[JavaSymbolInfo] = []

    # Top-level types
    for m in _RE_CLASS.finditer(source):
        kind_raw = m.group(0)
        name = m.group(1)
        start = m.start()

        # Infer kind from keyword
        if "class " in kind_raw and "interface" not in kind_raw and "enum" not in kind_raw and "record" not in kind_raw:
            kind = "class"
        elif "interface" in kind_raw and "@interface" not in kind_raw:
            kind = "interface"
        elif "@interface" in kind_raw:
            kind = "annotation"
        elif "enum " in kind_raw:
            kind = "enum"
        elif "record " in kind_raw:
            kind = "record"
        else:
            kind = "class"

        line = source[:start].count("\n") + 1
        visibility = "internal"  # alinhado com Kotlin internal (package-scoped)
        vis_m = _VISIBILITY_RE.search(kind_raw)
        if vis_m:
            visibility = vis_m.group(1)

        mods_raw = kind_raw[: kind_raw.index(name)] if name in kind_raw else ""
        modifiers = [t for t in mods_raw.split() if t in {"abstract", "static", "final", "sealed", "non-sealed"}]

        # Body extraction
        brace_offset = find_opening_brace(source, m.end() - 1)
        body: Optional[str] = None
        if brace_offset is not None:
            body = extract_function_body(source, brace_offset, language="java")
        body_hash = hash_body(body) if body is not None else None
        body_tokens = None
        if body is not None:
            tokens = extract_body_tokens(body, language="java")
            body_tokens = tokens_to_json(tokens) if tokens else None

        symbols.append(JavaSymbolInfo(
            name=name,
            kind=kind,
            visibility=visibility,
            signature=kind_raw.strip()[:80] if len(kind_raw.strip()) > 80 else kind_raw.strip(),
            line=line,
            body=body,
            body_hash=body_hash,
            body_tokens=body_tokens,
            modifiers=modifiers,
        ))

    # Methods (top-level only, not nested inside class bodies matched above)
    # Simplified: extract methods from the full source, associating by approximate location
    class_names = {c.name for c in symbols if c.kind in {"class", "interface", "enum", "record", "annotation"}}
    for m in _RE_METHOD.finditer(source):
        preceding = source[max(0, m.start() - 200):m.start()]
        # Skip if inside a string or comment (approximate)
        raw_type = m.group(1)
        method_name = m.group(2)
        params = m.group(3)
        full_match = m.group(0)

        # Constructors: nome do método == nome de uma classe coletada acima.
        # Trate como kind="constructor" (sem skip — symbols de constructor são úteis).
        is_constructor = method_name in class_names

        # Determine if this is a method vs constructor
        kind = "constructor" if (is_constructor or full_match.strip().endswith(";")) else "method"

        line = source[:m.start()].count("\n") + 1

        visibility = "internal"  # alinhado com Kotlin internal (package-scoped)
        vis_m = _VISIBILITY_RE.search(preceding[-100:])
        if vis_m:
            visibility = vis_m.group(1)

        modifiers = []
        for token in preceding[-100:].split():
            if token in {"static", "final", "abstract", "synchronized", "native", "default"}:
                modifiers.append(token)
            if token in {"public", "private", "protected"}:
                pass  # already captured as visibility

        # Signature
        sig = f"{raw_type} {method_name}({params})"

        # Body extraction
        brace_start = full_match.rfind("{")
        if brace_start >= 0:
            brace_offset = m.start() + brace_start
            body = extract_function_body(source, brace_offset, language="java")
            body_hash = hash_body(body) if body is not None else None
            body_tokens = None
            if body is not None:
                tokens = extract_body_tokens(body, language="java")
                body_tokens = tokens_to_json(tokens) if tokens else None
        else:
            body = None
            body_hash = None
            body_tokens = None

        symbols.append(JavaSymbolInfo(
            name=method_name,
            kind=kind,
            visibility=visibility,
            signature=sig,
            line=line,
            body=body,
            body_hash=body_hash,
            body_tokens=body_tokens,
            modifiers=modifiers,
        ))

    return JavaFileInfo(package=package, imports=imports, symbols=symbols)
```

**Nota:** O regex de método associa constructor → class name após coleta de classes (set `class_names` montado antes do loop de métodos). Verifique em `test_parser_java.py` que constructors aparecem com `kind="constructor"` e métodos comuns com `kind="method"`. Esta task produz código compilável e testado.

- [ ] **Step 4.4: Rodar tests Java parser — confirmar PASS**

Run: `pytest tests/unit/test_parser_java.py -xvs 2>&1 | tail -30`
Expected: 7 tests green (mesmo arquivo criado em 4.2, agora com a impl de 4.3 satisfazendo).

- [ ] **Step 4.5: Rodar pytest — sem regressão**

Run: `pytest -q 2>&1 | tail -3`
Expected: green.

---

## Task 5: XML parser (Onda 4)

**Files:**
- Create: `engine/graph/parser_xml.py`
- Create: `tests/fixtures/xml-layout/res/layout/activity_login.xml`
- Create: `tests/fixtures/xml-layout/res/layout/fragment_profile.xml`
- Create: `tests/fixtures/xml-resources/res/values/strings.xml`
- Create: `tests/unit/test_parser_xml.py`

**Reuse-first via graph (Mandamento #3):**

```bash
forge graph --json q11 parser
forge graph --json q15
```

Análise: Q11 não retorna helper compartilhado pra XML — `_body_text` opera em corpos com `{}` (não aplicável a XML, cujos symbols são tags/atributos). Q15 confirma que XML não tem near-duplicate semântico com kotlin/swift/typescript/java/objc — parser dedicado é o caminho consciente (Caminho C do 3-caminhos canônico do `reuse.md`).

- [ ] **Step 5.1: Criar fixtures XML**

**xml-layout/activity_login.xml:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<androidx.constraintlayout.widget.ConstraintLayout
    xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    android:layout_width="match_parent"
    android:layout_height="match_parent">

    <EditText
        android:id="@+id/email_input"
        android:layout_width="0dp"
        android:layout_height="wrap_content"
        android:hint="@string/email_hint"
        app:layout_constraintTop_toTopOf="parent" />

    <EditText
        android:id="@+id/password_input"
        android:layout_width="0dp"
        android:layout_height="wrap_content"
        android:hint="@string/password_hint"
        android:inputType="textPassword" />

    <Button
        android:id="@+id/login_button"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="@string/login_action"
        android:onClick="onLoginClick" />

</androidx.constraintlayout.widget.ConstraintLayout>
```

**xml-layout/fragment_profile.xml:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<layout xmlns:android="http://schemas.android.com/apk/res/android">
    <data>
        <variable
            name="viewModel"
            type="com.example.profile.ProfileViewModel" />
    </data>
    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="match_parent"
        android:orientation="vertical">

        <TextView
            android:id="@+id/user_name"
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:text="@{viewModel.userName}" />

        <Button
            android:id="@+id/logout_button"
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:onClick="@{() -> viewModel.onLogout()}" />

    </LinearLayout>
</layout>
```

**xml-resources/strings.xml:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">MyApp</string>
    <string name="email_hint">Email address</string>
    <string name="password_hint">Password</string>
    <string name="login_action">Sign in</string>
</resources>
```

- [ ] **Step 5.2: Escrever tests `test_parser_xml.py` FALHANDO primeiro (TDD)**

Antes de criar o parser, escrever os tests. Conteúdo do `tests/unit/test_parser_xml.py`:

```python
"""Tests for engine.graph.parser_xml."""

from pathlib import Path

import pytest

from engine.graph.parser_xml import parse_xml_file

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_xml_layout_view_ids() -> None:
    info = parse_xml_file(FIXTURES / "xml-layout" / "res" / "layout" / "activity_login.xml")
    view_ids = {s.name for s in info.symbols if s.kind == "view_id"}
    assert "email_input" in view_ids
    assert "password_input" in view_ids
    assert "login_button" in view_ids


def test_xml_layout_class_refs() -> None:
    info = parse_xml_file(FIXTURES / "xml-layout" / "res" / "layout" / "activity_login.xml")
    assert "androidx.constraintlayout.widget.ConstraintLayout" in info.imports


def test_xml_layout_resource_keys() -> None:
    info = parse_xml_file(FIXTURES / "xml-layout" / "res" / "layout" / "activity_login.xml")
    assert "string/email_hint" in info.resource_keys
    assert "string/password_hint" in info.resource_keys
    assert "string/login_action" in info.resource_keys


def test_xml_fragment_data_binding() -> None:
    info = parse_xml_file(FIXTURES / "xml-layout" / "res" / "layout" / "fragment_profile.xml")
    # Binding variables
    assert len(info.binding_variables) == 1
    assert info.binding_variables[0][0] == "viewModel"
    assert info.binding_variables[0][1] == "com.example.profile.ProfileViewModel"

    # View IDs
    view_ids = {s.name for s in info.symbols if s.kind == "view_id"}
    assert "user_name" in view_ids
    assert "logout_button" in view_ids

    # Binding actions
    actions = [s for s in info.symbols if s.kind == "binding_action"]
    assert len(actions) >= 1


def test_xml_strings_resource() -> None:
    info = parse_xml_file(FIXTURES / "xml-resources" / "res" / "values" / "strings.xml")
    string_keys = {s.name for s in info.symbols if s.kind == "string_resource"}
    assert "app_name" in string_keys
    assert "email_hint" in string_keys
    assert "password_hint" in string_keys
    assert "login_action" in string_keys
```

Run: `pytest tests/unit/test_parser_xml.py -xvs`
Expected: **collection error ou ImportError** porque `engine.graph.parser_xml` ainda não existe. Confirmar FAIL antes de prosseguir pro Step 5.3.

- [ ] **Step 5.3: Criar `parser_xml.py`**

Parser específico para XML Android. Extrai:
- **View IDs:** `@+id/` e `@id/` → como símbolos de tipo "view_id"
- **Classes referenciadas:** nomes de tags fully-qualified (`androidx.constraintlayout.widget.ConstraintLayout`), `android:name` attributes, `class=` attributes, `type=` em `<variable>`
- **Data binding variables:** `<variable name="viewModel" type="com.example.profile.ProfileViewModel" />`
- **Resource keys:** `@string/`, `@color/`, `@dimen/`, `@drawable/`, `@mipmap/`, `@layout/`, `@anim/`, `@style/` → como imports (deps em resources)
- **Binding actions:** `@{viewModel::onClick}`, `@{() -> viewModel.onLogout()}` → como referências de binding

```python
"""XML parser for Android layouts and resources.

Extracts view IDs, referenced classes, data binding variables, resource
keys, and binding action references from Android XML files.

This is a regex-based parser — sufficient for the structured, predictable
format of Android XML. No full XML AST needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# View ID: @+id/foo, @id/foo, @android:id/foo
_RE_VIEW_ID = re.compile(r'@(?:\+)?(?:android:)?id/([\w_]+)')

# Fully-qualified class reference in tag names
_RE_TAG_CLASS = re.compile(r'<([a-z][\w.]+\.[A-Z]\w+(?:\.\w+)*)')

# android:name / class= attributes
_RE_ATTR_CLASS = re.compile(
    r'(?:android:name|class)\s*=\s*"([\w.]+(?:\.[A-Z]\w+)+)"'
)

# Data binding: <variable name="..." type="..." />
_RE_BINDING_VAR = re.compile(
    r'<variable\s+name="(\w+)"\s+type="([\w.]+(?:\.[A-Z]\w+)+)"\s*/>'
)

# Resource references: @string/foo, @color/bar, @dimen/baz, etc.
_RESOURCE_PREFIXES = (
    "string", "color", "dimen", "drawable", "mipmap", "layout",
    "anim", "style", "plurals", "integer", "bool", "array",
)
_RES_RE = re.compile(
    r'@(?:android:)?(' + '|'.join(_RESOURCE_PREFIXES) + r')/([\w_]+)'
)

# Data binding expression: @{viewModel.property}, @{viewModel::method}
_RE_BINDING_EXPR = re.compile(r'@\{([^}]+)\}')

# <string name="key">value</string> (resources files)
_RE_STRING_RESOURCE = re.compile(r'<string\s+name="([\w_]+)"[^>]*>(.*?)</string>', re.DOTALL)

# <color name="key">#hex</color>
_RE_COLOR_RESOURCE = re.compile(r'<color\s+name="([\w_]+)">(.*?)</color>')


@dataclass
class XmlSymbolInfo:
    name: str
    kind: str  # "view_id" | "class_ref" | "binding_variable" | "resource_key" | "binding_action"
    line: int = 0
    context: Optional[str] = None  # e.g., tag name for view IDs


@dataclass
class XmlFileInfo:
    is_layout: bool
    is_resources: bool
    symbols: list[XmlSymbolInfo]
    imports: list[str]  # class references → treated as edges
    resource_keys: list[str]  # @string/foo etc.
    binding_variables: list[tuple[str, str]]  # (name, type)


def parse_xml_file(path: Path) -> XmlFileInfo:
    source = path.read_text(encoding="utf-8")
    return _parse_xml(source, path)


def _parse_xml(source: str, path: Path) -> XmlFileInfo:
    lines = source.split("\n")
    symbols: list[XmlSymbolInfo] = []
    class_refs: list[str] = []
    resource_keys: list[str] = []
    binding_vars: list[tuple[str, str]] = []

    is_layout = "layout" in path.suffix or "/layout/" in str(path)
    is_resources = "values" in str(path) and path.name in ("strings.xml", "colors.xml", "dimens.xml", "themes.xml")

    if is_resources:
        # Resource files: extract string/color/dimen keys
        for m in _RE_STRING_RESOURCE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=m.group(1),
                kind="string_resource",
                line=line,
            ))
        for m in _RE_COLOR_RESOURCE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=m.group(1),
                kind="color_resource",
                line=line,
            ))

    if is_layout:
        # View IDs
        for m in _RE_VIEW_ID.finditer(source):
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=m.group(1),
                kind="view_id",
                line=line,
            ))

        # Tag names as class references
        for m in _RE_TAG_CLASS.finditer(source):
            class_name = m.group(1)
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=class_name,
                kind="class_ref",
                line=line,
            ))
            class_refs.append(class_name)

        # Attribute class references
        for m in _RE_ATTR_CLASS.finditer(source):
            class_name = m.group(1)
            class_refs.append(class_name)

        # Data binding variables
        for m in _RE_BINDING_VAR.finditer(source):
            var_name = m.group(1)
            var_type = m.group(2)
            line = source[:m.start()].count("\n") + 1
            symbols.append(XmlSymbolInfo(
                name=var_name,
                kind="binding_variable",
                line=line,
                context=var_type,
            ))
            binding_vars.append((var_name, var_type))
            class_refs.append(var_type)

        # Resource references in layout
        for m in _RES_RE.finditer(source):
            res_key = f"{m.group(1)}/{m.group(2)}"
            resource_keys.append(res_key)

        # Binding actions (@{...})
        for m in _RE_BINDING_EXPR.finditer(source):
            expr = m.group(1).strip()
            if "::" in expr or "->" in expr:
                line = source[:m.start()].count("\n") + 1
                symbols.append(XmlSymbolInfo(
                    name=expr,
                    kind="binding_action",
                    line=line,
                ))

    return XmlFileInfo(
        is_layout=is_layout,
        is_resources=is_resources,
        symbols=symbols,
        imports=class_refs,
        resource_keys=resource_keys,
        binding_variables=binding_vars,
    )
```

- [ ] **Step 5.4: Rodar tests XML parser — confirmar PASS**

Run: `pytest tests/unit/test_parser_xml.py -xvs 2>&1 | tail -30`
Expected: 5 tests green (mesmo arquivo criado em 5.2, agora com a impl de 5.3 satisfazendo).

- [ ] **Step 5.5: Rodar pytest — sem regressão**

Run: `pytest -q 2>&1 | tail -3`
Expected: green.

---

## Task 6: Objective-C parser (Onda 5)

**Files:**
- Create: `engine/graph/parser_objc.py`
- Create: `tests/fixtures/objc-basic/Models/UserModel.m`
- Create: `tests/fixtures/objc-basic/Models/UserModel.h`
- Create: `tests/unit/test_parser_objc.py`

**Reuse-first via graph (Mandamento #3):**

```bash
forge graph --json q11 parser
forge graph --json q15
```

Análise: Q11 não retorna helper compartilhado pra brace-scan multi-lang — `_body_text.extract_function_body` é o único helper genérico e já é reusado. ObjC usa `{}` em method bodies (idêntico a Java/Kotlin); `_SUPPORTED_LANGS` ganha `"objc"` pra body extraction. Q15 confirma que kotlin/swift/typescript/java não são near-duplicate à objc — semanticamente distinto (ObjC selectors são únicos), duplicação cosmética via shared `_body_text` é caminho consciente (Caminho C do 3-caminhos canônico do `reuse.md`).

- [ ] **Step 6.1: Criar fixtures ObjC**

**UserModel.h:**
```objc
#import <Foundation/Foundation.h>

@interface UserModel : NSObject
@property (nonatomic, strong) NSString *userId;
@property (nonatomic, strong) NSString *name;
- (instancetype)initWithId:(NSString *)userId name:(NSString *)name;
- (NSString *)displayName;
@end
```

**UserModel.m:**
```objc
#import "UserModel.h"
#import "../Services/AuthService.h"
@import Foundation;

@interface UserModel ()
@property (nonatomic, strong) NSString *internalToken;
@end

@implementation UserModel

- (instancetype)initWithId:(NSString *)userId name:(NSString *)name {
    self = [super init];
    if (self) {
        _userId = userId;
        _name = name;
    }
    return self;
}

- (NSString *)displayName {
    return [NSString stringWithFormat:@"%@ (%@)", self.name, self.userId];
}

+ (instancetype)anonymousUser {
    return [[self alloc] initWithId:@"0" name:@"Guest"];
}
@end
```

- [ ] **Step 6.2: Escrever tests `test_parser_objc.py` FALHANDO primeiro (TDD)**

Antes de criar o parser, escrever os tests. Conteúdo do `tests/unit/test_parser_objc.py`:

```python
"""Tests for engine.graph.parser_objc."""

from pathlib import Path

import pytest

from engine.graph.parser_objc import parse_objc_file

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_objc_header_parses_imports() -> None:
    info = parse_objc_file(FIXTURES / "objc-basic" / "Models" / "UserModel.h")
    assert any("Foundation.h" in imp for imp in info.imports)


def test_objc_header_parses_interface() -> None:
    info = parse_objc_file(FIXTURES / "objc-basic" / "Models" / "UserModel.h")
    classes = [s for s in info.symbols if s.kind == "class"]
    assert len(classes) >= 1
    assert classes[0].name == "UserModel"


def test_objc_implementation_parses_methods() -> None:
    info = parse_objc_file(FIXTURES / "objc-basic" / "Models" / "UserModel.m")
    methods = [s for s in info.symbols if s.kind == "method"]
    assert len(methods) >= 1


def test_objc_implementation_parses_imports() -> None:
    info = parse_objc_file(FIXTURES / "objc-basic" / "Models" / "UserModel.m")
    assert any("UserModel.h" in imp for imp in info.imports)


def test_objc_implementation_symbol() -> None:
    info = parse_objc_file(FIXTURES / "objc-basic" / "Models" / "UserModel.m")
    impls = [s for s in info.symbols if s.kind == "implementation"]
    assert len(impls) >= 1
    assert impls[0].name == "UserModel"


def test_objc_class_method_detection() -> None:
    info = parse_objc_file(FIXTURES / "objc-basic" / "Models" / "UserModel.m")
    methods = [s for s in info.symbols if s.kind == "method" and s.is_class_method]
    assert len(methods) >= 1  # +anonymousUser
```

Run: `pytest tests/unit/test_parser_objc.py -xvs`
Expected: **collection error ou ImportError** porque `engine.graph.parser_objc` ainda não existe. Confirmar FAIL antes de prosseguir pro Step 6.3.

- [ ] **Step 6.3: Criar `parser_objc.py`**

Simplificado — sem call graph. Extrai:
- `#import "..."` e `#import <...>` → imports
- `@import Module;` → module imports
- `@interface ClassName : SuperClass` → class symbol
- `@protocol ProtocolName` → protocol symbol
- `@implementation ClassName` → implementation symbol
- Methods: `- (returnType)methodName:(type)paramName ...` e `+ (returnType)methodName`
- Properties: `@property ... type name`

```python
"""Simplified Objective-C parser — imports + symbols only.

NO call graph (`[obj selector]` parsing). NO full AST. Regex-based,
best-effort. Covers the most common patterns found in iOS legacy code.

This is sufficient for graph queries (Q4 symbols, Q11/12/13 dup detection
via body_hash) without the complexity of a full ObjC AST walker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from engine.graph._body_text import (
    extract_body_tokens,
    extract_function_body,
    find_opening_brace,
    hash_body,
    tokens_to_json,
)

_RE_IMPORT = re.compile(r'^#import\s+[<"]([^>"]+)[>"]', re.MULTILINE)
_RE_MODULE_IMPORT = re.compile(r'^@import\s+(\w+)\s*;', re.MULTILINE)

_RE_INTERFACE = re.compile(
    r'@interface\s+(\w+)\s*(?::\s*(\w+(?:\s*<\w+>)?))?',
    re.MULTILINE,
)
_RE_PROTOCOL = re.compile(r'@protocol\s+(\w+)', re.MULTILINE)
_RE_IMPLEMENTATION = re.compile(r'@implementation\s+(\w+)', re.MULTILINE)

# Method: - (void)methodName or + (instancetype)methodName:(type)param
_RE_METHOD = re.compile(
    r'^([+-])\s*'
    r'(?:\(([\w\s\*<>,\[\]{}]+)\))?\s*'  # return type in parens
    r'(\w+)\s*'  # method name / first segment
    r'(?::\s*\(([\w\s\*<>]+)\)\s*(\w+)\s*)?'  # optional first param
    r'(?:\s*(?:\w+)\s*:\s*\(([\w\s\*<>]+)\)\s*(\w+)\s*)*',  # more params
    re.MULTILINE,
)

_RE_PROPERTY = re.compile(
    r'@property\s*(?:\([^)]*\))?\s*'
    r'(\w+(?:\s*\*)?)\s+'  # type
    r'(\w+)\s*;',  # name
    re.MULTILINE,
)


@dataclass
class ObjcSymbolInfo:
    name: str
    kind: str  # "class" | "protocol" | "implementation" | "method" | "property"
    is_class_method: bool = False  # True for + methods
    signature: Optional[str] = None
    line: int = 0
    body: Optional[str] = None
    body_hash: Optional[str] = None
    body_tokens: Optional[str] = None
    modifiers: list[str] = field(default_factory=list)
    receiver_type: Optional[str] = None


@dataclass
class ObjcFileInfo:
    imports: list[str]  # #import and @import targets
    symbols: list[ObjcSymbolInfo]


def parse_objc_file(path: Path) -> ObjcFileInfo:
    source = path.read_text(encoding="utf-8")
    return _parse_objc(source)


def _parse_objc(source: str) -> ObjcFileInfo:
    lines = source.split("\n")

    # Imports
    imports: list[str] = []
    for m in _RE_IMPORT.finditer(source):
        imports.append(m.group(1))
    for m in _RE_MODULE_IMPORT.finditer(source):
        imports.append(f"@module:{m.group(1)}")

    symbols: list[ObjcSymbolInfo] = []

    # @interface
    for m in _RE_INTERFACE.finditer(source):
        name = m.group(1)
        superclass = m.group(2)
        line = source[:m.start()].count("\n") + 1
        sig = f"@interface {name}" + (f" : {superclass}" if superclass else "")
        # Find body (up to @end)
        end_m = re.search(r'@end', source[m.end():])
        body = None
        if end_m:
            body = source[m.end():m.end() + end_m.start()]
        body_hash = hash_body(body) if body else None
        symbols.append(ObjcSymbolInfo(
            name=name,
            kind="class",
            signature=sig,
            line=line,
            body=body,
            body_hash=body_hash,
        ))

    # @protocol
    for m in _RE_PROTOCOL.finditer(source):
        name = m.group(1)
        line = source[:m.start()].count("\n") + 1
        end_m = re.search(r'@end', source[m.end():])
        body = source[m.end():m.end() + end_m.start()] if end_m else None
        symbols.append(ObjcSymbolInfo(
            name=name,
            kind="protocol",
            line=line,
            body=body,
        ))

    # @implementation
    for m in _RE_IMPLEMENTATION.finditer(source):
        name = m.group(1)
        line = source[:m.start()].count("\n") + 1
        end_m = re.search(r'@end', source[m.end():])
        body = source[m.end():m.end() + end_m.start()] if end_m else None
        symbols.append(ObjcSymbolInfo(
            name=name,
            kind="implementation",
            line=line,
            body=body,
        ))

    # Methods (simplified — best effort)
    for m in _RE_METHOD.finditer(source):
        is_class = m.group(1) == "+"
        ret_type = m.group(2) or "void"
        sel_parts = [m.group(3)]
        if m.group(4) and m.group(5):
            sel_parts.append(f"{m.group(3)}:{m.group(5)}")
        full_sel = ":".join(sel_parts)
        line = source[:m.start()].count("\n") + 1
        prefix = "+" if is_class else "-"
        sig = f"{prefix} ({ret_type}){full_sel}"

        # Body extraction via brace matching
        brace_offset = find_opening_brace(source, m.end())
        body = None
        if brace_offset is not None:
            body = extract_function_body(source, brace_offset, language="objc")
        body_hash = hash_body(body) if body else None

        symbols.append(ObjcSymbolInfo(
            name=full_sel,
            kind="method",
            is_class_method=is_class,
            signature=sig,
            line=line,
            body=body,
            body_hash=body_hash,
        ))

    # Properties
    for m in _RE_PROPERTY.finditer(source):
        prop_type = m.group(1)
        prop_name = m.group(2)
        line = source[:m.start()].count("\n") + 1
        symbols.append(ObjcSymbolInfo(
            name=prop_name,
            kind="property",
            signature=f"{prop_type} {prop_name}",
            line=line,
        ))

    return ObjcFileInfo(imports=imports, symbols=symbols)
```

- [ ] **Step 6.4: Rodar tests ObjC parser — confirmar PASS**

Run: `pytest tests/unit/test_parser_objc.py -xvs 2>&1 | tail -30`
Expected: 6 tests green (mesmo arquivo criado em 6.2, agora com a impl de 6.3 satisfazendo).

- [ ] **Step 6.5: Rodar pytest — sem regressão**

Run: `pytest -q 2>&1 | tail -3`
Expected: green.

---

## Task 7: Registrar extensões + hooks incrementais + persist functions (Onda 6)

**Files:**
- Modify: `engine/graph/builder.py`
- Modify: `engine/graph/incremental.py`
- Modify: `engine/graph/_body_text.py`
- Modify: `engine/ingest.py`
- Modify: `hooks/post-edit-codebase-graph.sh`

- [ ] **Step 7.1: Adicionar extensões em `_LANGUAGE_EXTENSIONS` em `builder.py`**

```python
_LANGUAGE_EXTENSIONS = {
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
    ".xml": "xml",
    ".m": "objc",
    ".mm": "objc",
}
```

- [ ] **Step 7.2: Adicionar `java` e `objc` em `_SUPPORTED_LANGS` em `_body_text.py`**

```python
_SUPPORTED_LANGS = frozenset({"kotlin", "swift", "typescript", "javascript", "java", "objc"})
```

**Nota:** XML não precisa de body extraction — seus "symbols" são tags/atributos, não funções com `{}`.

- [ ] **Step 7.3: Adicionar `_NOISE_TOKENS_PER_LANG` para `java` e `objc` em `_body_text.py`**

```python
"java": frozenset({
    "public", "private", "protected", "class", "interface", "enum",
    "return", "if", "else", "for", "while", "do", "switch", "case",
    "break", "continue", "new", "this", "super", "null", "true",
    "false", "void", "int", "long", "double", "float", "boolean",
    "char", "byte", "short", "final", "static", "abstract", "extends",
    "implements", "import", "package", "try", "catch", "finally",
    "throw", "throws", "synchronized", "volatile", "transient",
    "instanceof", "assert", "enum", "record", "sealed", "non-sealed",
    "var",
}),
"objc": frozenset({
    "self", "super", "return", "if", "else", "for", "while", "do",
    "switch", "case", "break", "continue", "nil", "NULL", "YES",
    "NO", "true", "false", "id", "instancetype", "void", "int",
    "BOOL", "NSInteger", "NSUInteger", "CGFloat", "NSString",
    "NSArray", "NSDictionary", "NSSet", "NSObject", "strong",
    "weak", "copy", "assign", "retain", "nonatomic", "atomic",
    "readwrite", "readonly", "in", "out", "inout", "byref",
    "bycopy", "oneway", "typedef", "struct", "union", "enum",
    "const", "static", "extern", "@public", "@protected",
    "@private", "@package", "@class", "@selector", "@protocol",
    "@required", "@optional", "@end", "@synthesize", "@dynamic",
    "@synchronized", "@try", "@catch", "@finally", "@throw",
    "@autoreleasepool", "@encode", "@compatibility_alias",
    "@defs", "@property", "@implementation", "@interface",
}),
```

- [ ] **Step 7.4: Adicionar `_persist_java`, `_persist_xml`, `_persist_objc` em `builder.py`**

```python
def _persist_java(conn: sqlite3.Connection, file_id: int, info: JavaFileInfo) -> dict:
    """Persist Java parse results. Same column shape as _persist_kotlin."""
    edges = 0
    for symbol in info.symbols:
        conn.execute(
            "INSERT INTO symbols("
            "  file_id, name, kind, signature, line_start, line_end, visibility, "
            "  receiver_type, body_hash, body_tokens, modifiers, body"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                file_id,
                symbol.name,
                symbol.kind,
                symbol.signature,
                symbol.line,
                symbol.line,
                symbol.visibility,
                symbol.receiver_type,
                symbol.body_hash,
                symbol.body_tokens,
                " ".join(symbol.modifiers) if symbol.modifiers else None,
                symbol.body,
            ),
        )

    import_rows = [(file_id, imp) for imp in info.imports]
    if import_rows:
        conn.executemany(
            "INSERT INTO imports(from_file_id, to_symbol, kind) VALUES(?, ?, 'import')",
            import_rows,
        )
        edges += len(import_rows)

    return {"symbols": len(info.symbols), "edges": edges}


def _persist_xml(conn: sqlite3.Connection, file_id: int, info: XmlFileInfo) -> dict:
    """Persist XML parse results.

    Class references → imports (edges). View IDs → symbols (kind=view_id).
    Resource keys → imports (resource_ref kind). Binding variables → symbols.
    """
    edges = 0

    for sym in info.symbols:
        conn.execute(
            "INSERT INTO symbols("
            "  file_id, name, kind, signature, line_start, line_end"
            ") VALUES(?, ?, ?, ?, ?, ?)",
            (
                file_id,
                sym.name,
                sym.kind,
                sym.context or sym.kind,
                sym.line,
                sym.line,
            ),
        )

    # Class references as imports
    for cls_ref in info.imports:
        conn.execute(
            "INSERT INTO imports(from_file_id, to_symbol, kind) VALUES(?, ?, 'xml_class_ref')",
            (file_id, cls_ref),
        )
        edges += 1

    # Resource keys as imports
    for res_key in info.resource_keys:
        conn.execute(
            "INSERT INTO imports(from_file_id, to_symbol, kind) VALUES(?, ?, 'resource_ref')",
            (file_id, res_key),
        )
        edges += 1

    return {"symbols": len(info.symbols), "edges": edges}


def _persist_objc(conn: sqlite3.Connection, file_id: int, info: ObjcFileInfo) -> dict:
    """Persist Objective-C parse results.

    Imports → edges. Class/protocol/implementation → symbols (kind=objc_*).
    Methods → symbols with body (for reuse-intelligence).
    """
    edges = 0

    for sym in info.symbols:
        kind = f"objc_{sym.kind}"
        conn.execute(
            "INSERT INTO symbols("
            "  file_id, name, kind, signature, line_start, line_end, visibility, "
            "  body_hash, body_tokens, body"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                file_id,
                sym.name,
                kind,
                sym.signature,
                sym.line,
                sym.line,
                "public",
                sym.body_hash,
                sym.body_tokens,
                sym.body,
            ),
        )

    import_rows = [(file_id, imp) for imp in info.imports]
    if import_rows:
        conn.executemany(
            "INSERT INTO imports(from_file_id, to_symbol, kind) VALUES(?, ?, 'import')",
            import_rows,
        )
        edges += len(import_rows)

    return {"symbols": len(info.symbols), "edges": edges}
```

- [ ] **Step 7.5: Adicionar dispatcher branches em `_ingest_file` (builder.py)**

Em `_ingest_file`, após o bloco `typescript/javascript`:

```python
    if language == "java":
        from engine.graph.parser_java import parse_java_file
        info = parse_java_file(file_path)
        return _persist_java(conn, file_id, info)
    if language == "xml":
        from engine.graph.parser_xml import parse_xml_file
        info = parse_xml_file(file_path)
        return _persist_xml(conn, file_id, info)
    if language == "objc":
        from engine.graph.parser_objc import parse_objc_file
        info = parse_objc_file(file_path)
        return _persist_objc(conn, file_id, info)
```

- [ ] **Step 7.6: Adicionar imports nos novos parsers em `builder.py`**

No topo de `builder.py`, adicionar imports para os novos tipos:

```python
from engine.graph.parser_java import JavaFileInfo, parse_java_file
from engine.graph.parser_xml import XmlFileInfo, parse_xml_file
from engine.graph.parser_objc import ObjcFileInfo, parse_objc_file
```

- [ ] **Step 7.7: Adicionar dispatcher branches em `_refresh_file` (incremental.py)**

Em `incremental.py:_refresh_file`, após o bloco `elif language in {"typescript", "javascript"}:`:

```python
    elif language == "java":
        from engine.graph.parser_java import parse_java_file
        info = parse_java_file(file_path)
        stats = _persist_java(conn, file_id, info)
    elif language == "xml":
        from engine.graph.parser_xml import parse_xml_file
        info = parse_xml_file(file_path)
        stats = _persist_xml(conn, file_id, info)
    elif language == "objc":
        from engine.graph.parser_objc import parse_objc_file
        info = parse_objc_file(file_path)
        stats = _persist_objc(conn, file_id, info)
```

E adicionar imports dos novos persist helpers em `incremental.py`:

```python
from engine.graph.builder import (
    _LANGUAGE_EXTENSIONS,
    _ensure_graph_body_column,
    _ensure_imports_to_file_id_column,
    _ensure_reuse_intelligence_columns,
    _infer_feature_slug,
    _infer_test_framework,
    _infer_test_target_file_id,
    _persist_kotlin,
    _persist_swift,
    _persist_typescript,
    _persist_java,
    _persist_xml,
    _persist_objc,
    _relpath,
    _resolve_import_targets,
    _screen_name_from_path,
)
```

- [ ] **Step 7.8: Adicionar extensões em `_GRAPH_EXTENSIONS` em `ingest.py`**

```python
_GRAPH_EXTENSIONS = {".kt", ".kts", ".swift", ".ts", ".tsx", ".js", ".jsx", ".java", ".xml", ".m", ".mm"}
```

- [ ] **Step 7.9: Atualizar `post-edit-codebase-graph.sh`**

```bash
case "$FILE" in
    *.kt|*.kts|*.swift|*.ts|*.tsx|*.js|*.jsx|*.java|*.xml|*.m|*.mm) ;;
    *) exit 0 ;;
esac
```

- [ ] **Step 7.10: Rodar pytest — sem regressão**

Run: `pytest -q 2>&1 | tail -3`
Expected: green. Se houver falhas, ajustar imports (imports circulares, names não encontrados).

---

## Task 8: Instrução pro modelo (Onda 7)

**Files:**
- Modify: `AGENTS.md` ou `CLAUDE.md`

AGENTS.md/CLAUDE.md é load-bearing per `.claude/rules/scope.md` — instrução pro modelo é a entrega da Onda 7; sem ela a IA não sabe que o graph existe — escopo direto da tarefa, alinhado com Mandamento #6 doc-sync.

- [ ] **Step 8.1: Verificar qual arquivo existe**

Run: `ls -la AGENTS.md CLAUDE.md 2>/dev/null`

- [ ] **Step 8.2: Adicionar seção no arquivo existente**

Adicionar (ou atualizar) bloco de instrução ao modelo:

```markdown
## Codebase Graph — IA-ready

O forge mantém um codebase graph em `.claude/graph.db` (SQLite, WAL mode)
com símbolos, imports, body-text, e dependências do projeto. **Consulte
o graph antes de ler arquivos fonte** — reduz tokens de contexto e acelera
a compreensão.

### Como consultar

```bash
# Listar símbolos de um módulo
forge graph --json q4 <module-name>

# Encontrar features similares por slug
forge graph --json q1 <feature-slug>

# Calcular blast radius de arquivos
forge graph --json q2 --file path/to/Foo.kt

# Encontrar imports de um símbolo
forge graph --json q4 LoginUseCase

# Encontrar orphand files (sem importers)
forge graph --json q3

# Listar depêndencias de DI
forge graph --json q8 <class-name>

# Listar todas as queries disponíveis
forge graph --help
```

### Linguagens cobertas

Kotlin, Swift, TypeScript, JavaScript, Java, XML (Android layouts +
resources), Objective-C (`.m`, `.mm`).

### Limitações conhecidas

- Call graph para ObjC não implementado (regex-based, sem AST)
- XML parser extrai apenas IDs de view, class refs, resource keys e binding vars
- Body text preserva comentários (cru, sem stripping)
```

---

## Task 9: Schema doc update + doc-sync (Mandamento #6)

**Files:**
- Modify: `docs/schemas/graph.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/design/08-session-handoff.md`
- Modify: `docs/design/04-pending.md`
- Modify: `README.md`

`docs/schemas/graph.md` é load-bearing per `.claude/rules/scope.md` — schema doc é fonte canônica do contrato; sem este edit a coluna `body` e a flag `--json` não entram no contrato, alinhado com Mandamento #6.

- [ ] **Step 9.1: Documentar `symbols.body` column em `docs/schemas/graph.md`**

Localizar tabela `symbols` no schema doc. Adicionar linha:

```markdown
| body | TEXT | null | Raw source text (with comments preserved) for the symbol body. Used by IA assistants to inspect implementation without reading source files. Populated for Kotlin, Swift, TypeScript, Java, ObjC symbols with brace-delimited bodies. |
```

- [ ] **Step 9.2: Documentar `--json` flag em `docs/schemas/graph.md`**

Adicionar seção ou nota:

```markdown
### forge graph --json

A flag `--json` permite consultas não-interativas para uso por ferramentas
automatizadas e assistentes IA:

```
forge graph --json <query> [args...]
```

Onde `<query>` é um alias curto (`q1`..`q17`, `r`), uma key numérica (`1`..`17`), ou o label
do handler (`symbols`, `blast-radius`, etc.). O output é JSON puro em stdout.

Exemplos:

```
forge graph --json q3                                         # orphan files
forge graph --json q4 LoginUseCase                            # symbols matching "LoginUseCase"
forge graph --json q2 --file src/main/kotlin/LoginUseCase.kt  # blast radius
```
```

- [ ] **Step 9.3: CHANGELOG.md entry**

Adicionar em `## [Unreleased]`:

```markdown
### Added

- `symbols.body` column — raw source text for each symbol body, preserved with comments. Added via ALTER TABLE migration (`_ensure_graph_body_column`) in `engine/utils/sqlite_io.py`. Populated by all parsers (Kotlin, Swift, TypeScript, Java, XML, ObjC).
- `forge graph --json <query> [args...]` — non-interactive JSON output for AI assistant consumption. Reuses existing Q1–Q17 queries.
- Java parser (`engine/graph/parser_java.py`) — regex-based extraction of package, imports, classes, methods, constructors with body text and reuse-intelligence metadata.
- XML parser (`engine/graph/parser_xml.py`) — Android layout and resource parser extracting view IDs (`@+id/`), class references, data binding variables, resource keys, and binding action expressions.
- Objective-C parser (`engine/graph/parser_objc.py`) — simplified symbol+import parser covering `@interface`, `@protocol`, `@implementation`, methods, properties, `#import`/`@import`. NO call graph.
- Language extension registration: `.java` → java, `.xml` → xml, `.m`/`.mm` → objc in `_LANGUAGE_EXTENSIONS`, `_GRAPH_EXTENSIONS`, `_SUPPORTED_LANGS`, and `post-edit-codebase-graph.sh`.
- AGENTS.md/CLAUDE.md section instructing AI models to query graph (`forge graph --json`) before reading source files.
- `bash .claude/bootstrap.sh` Step 6: build inicial do graph + inventory pós-clone (idempotente).
- `engine/cli.py` detecta bootstrap state ausente (`.git/hooks/pre-commit` symlink missing) e emite friendly error com instrução pra rodar bootstrap.
- `engine/graph_cli.py` auto-builda `graph.db` quando ausente/empty (lazy rebuild na primeira invocação).
- Flag `--no-auto-build` em `forge graph` desativa lazy rebuild (uso CI/scripts determinísticos).

### Documentation

- `docs/schemas/graph.md` documents `symbols.body` column and `--json` flag.
```

- [ ] **Step 9.4: handoff atualizado**

Em `docs/design/08-session-handoff.md`, atualizar:
- `**Última atualização:** 2026-06-12 (v1.3.0 — graph-ia-evolution: body column, --json flag, Java/XML/ObjC parsers)`
- `**Estado:** v1.3.0 graph-ia-evolution entregue`

- [ ] **Step 9.5: Verificar doc updates**

Run:
```bash
grep -c "body" docs/schemas/graph.md  # deve mostrar pelo menos 1 nova menção
grep -c "\-\-json" docs/schemas/graph.md  # deve mostrar >= 1
grep -c "\-\-json" CHANGELOG.md  # deve mostrar >= 1
```

- [ ] **Step 9.6: Atualizar `docs/design/04-pending.md` (H-001 + M-003)**

Antes de editar, mapear o que já existe no pending:

```bash
grep -n -i "java\|objc\|xml.*parser" docs/design/04-pending.md
grep -n -i "body.*column\|--json\|graph.*ia" docs/design/04-pending.md
```

(a) **Riscar gap fechado:** registrar v1.3.0 graph-ia-evolution shipped (body column + `--json` + Java/XML/ObjC parsers) e remover/riscar qualquer entrada que apontava cobertura legado (Java/XML/ObjC) ou body column como pendente.

(b) **Anotar follow-ups novos (M-003):** registrar os 6 non-goals deste plano como "follow-ups DET-graph-ia-evolution v1.4+" com critério pra reentrar:

- **(a) tree-sitter parsers** — reentrar quando regex insuficiente em projeto real (false positives ou misses críticos observados in-vivo).
- **(b) MCP server** — reentrar quando IA com runtime stateful (não apenas Claude Code via CLI) precisar de protocol-level integration.
- **(c) ObjC call graph** — reentrar quando legacy iOS estiver ativo em projeto adotante (`[obj selector]` parsing).
- **(d) call graph preciso (qualquer linguagem)** — escopo amplo, deferred até demanda concreta justificar refactor de Q1–Q17.
- **(e) SCHEMA_VERSION bump** — reentrar quando schema delta exigir migrator não-aditivo (ALTER TABLE não cobre).
- **(f) visualização gráfica (D3.js etc.)** — reentrar quando demanda real (humano pedindo, não inferida).

Run pra confirmar:
```bash
grep -c "graph-ia-evolution\|graph-ia v1.4" docs/design/04-pending.md  # >= 1 após edit
```

- [ ] **Step 9.7: Atualizar `README.md` (Mandamento #6 doc-sync — stats)**

Doc-sync per `.claude/rules/doc-sync.md §Checklist pré-commit` item 3: stats mudaram (test count, parser count, command surface), README precisa refletir no mesmo commit.

Antes do edit, localizar as seções pertinentes:

```bash
grep -n -i "tests\|parsers\|graph" README.md | head -20
```

Sub-atualizações:

(a) **§Stats** — bump de test count (de baseline pra baseline+26 — 26 tests novos: Java 7 + XML 5 + ObjC 6 + onboarding UX 8) + parser count (de 3 pra 6: kotlin/swift/typescript + java/xml/objc).

(b) **§Command surface** (ou equivalente) — mencionar `forge graph --json <query>` como entrypoint não-interativo pra consumo por IA/automação.

Texto-âncora: replicar pattern de releases anteriores (ver `git log --oneline -- README.md` antes do edit).

Run pra confirmar:
```bash
grep -c "\-\-json" README.md  # >= 1 após edit
grep -c "java\|xml\|objc" README.md  # >= 1 após edit (case-insensitive ok)
```

---

## Task 9.5: Onboarding UX — bootstrap detection + lazy graph build (Onda 7.5)

**Justificativa load-bearing (Mandamento #4):** `.claude/bootstrap.sh`
está em whitelist load-bearing per `.claude/rules/scope.md` (`.claude/**`).
Edit é necessário pra fechar o gap UX de onboarding de novos devs num
projeto que já tem forge — alinhado com Mandamento #6 doc-sync e com a
visão de Decision 18 (skill standalone instalável per-project).

**Files:**
- Modify: `.claude/bootstrap.sh` (adicionar graph + inventory build após install deps)
- Modify: `engine/cli.py` (detection: `.git/hooks/pre-commit` symlink missing/broken → friendly error)
- Modify: `engine/graph_cli.py` (lazy auto-build de graph.db quando ausente/empty + flag `--no-auto-build` pra opt-out CI)
- Create: `tests/engine/test_bootstrap_detection.py` (testes da detection logic)
- Create: `tests/engine/test_graph_lazy_build.py` (testes do lazy build + --no-auto-build)

**Reuse-first via graph (Mandamento #3):**

```bash
forge graph --json q11 bootstrap   # já existe helper de bootstrap detection?
forge graph --json q11 cli         # já existe pattern de CLI startup check?
forge graph --json q15             # near-duplicate scan
```

Esperado: Q11/Q15 confirmam ausência de helper compartilhado pra "detectar
estado de inicialização do projeto". Caminho C consciente (criar nova
função `_check_bootstrap_state()` em `engine/cli.py`) — sem near-duplicate.

- [ ] **Step 9.5.1: Adicionar build de graph + inventory em `.claude/bootstrap.sh`**

**Pré-requisito de subcommand:** Este Step assume que `forge graph build`
e `forge reconfigure --inventory-only` existem como subcommands non-interactive
e idempotentes. Se a impl detectar que NÃO existem (deviation), abrir
handoff ao orchestrator pra decidir: (a) criar os subcommands como parte
da Task 9.5; (b) usar `forge graph` (interactive sem args; aceita
redirect de stdin pra simular não-interactive) + `forge reconfigure`
(que faz inventory + graph juntos); ou (c) ship Task 9.5 sem o Step 6
do bootstrap (apenas detection + lazy build) e abrir gap em
`04-pending.md`. Recomendação se ambiguidade persistir: caminho (b)
é o mais reuse-first.

Após o bloco "5. Install runtime deps" já existente (que faz `pip install -e .`),
adicionar bloco 6:

```bash
# 6. Build inicial do graph + inventory (one-shot pós-clone).
# Idempotente — se DB já existe e está fresh, no-op rápido.
# Sem isto, primeira invocação `forge plan` triggera lazy rebuild (~30s-2min).
if command -v forge >/dev/null 2>&1; then
    echo "  ⏳ Building initial codebase graph (one-shot, ~30s-2min)..."
    forge graph build --quiet 2>/dev/null && echo "  ✓ graph.db built" || echo "  ⚠️  graph build falhou — primeira invocação 'forge graph' fará lazy rebuild"
    echo "  ⏳ Building inventory cache..."
    forge reconfigure --inventory-only --quiet 2>/dev/null && echo "  ✓ inventory cache built" || echo "  ⚠️  inventory falhou — execute 'forge reconfigure' manualmente"
fi
```

(Nota: subcommands `forge graph build --quiet` e `forge reconfigure --inventory-only` PODEM não existir ainda; se Step descobrir que precisam ser criados, ABRE deviation report ao orchestrator.)

- [ ] **Step 9.5.2: Detection no `engine/cli.py` — bootstrap state check**

Adicionar função `_check_bootstrap_state()` chamada no início de
`main()` (antes do dispatch pros handlers), exceto pra subcomando
`bootstrap` ou `--help`:

```python
def _check_bootstrap_state(project_root: Path) -> Optional[str]:
    """Detect if bootstrap was run. Returns error message if missing, None if OK.

    Check: `.git/hooks/pre-commit` symlink existe (criado por bootstrap.sh).

    NÃO bloqueia comandos read-only (`--version`, `--help`, `doctor`).
    """
    hooks_target = project_root / ".git" / "hooks" / "pre-commit"
    if not hooks_target.is_symlink() and not hooks_target.exists():
        return (
            "⚠️  forge não foi inicializado nesta máquina.\n"
            "   Rode: bash .claude/bootstrap.sh\n"
            "   (necessário uma vez após clone; idempotente)"
        )
    return None
```

Integração em `main()`:
```python
if subcommand not in {"bootstrap", "--version", "doctor", "--help"}:
    err = _check_bootstrap_state(project_root)
    if err:
        print(err, file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 9.5.3: Lazy auto-build em `engine/graph_cli.py`**

Antes de qualquer query handler em `run(argv)`, adicionar verificação:

```python
def _maybe_auto_build(project_root: Path, json_mode: bool, no_auto_build: bool) -> None:
    """Auto-build graph.db if missing or empty. Skip if --no-auto-build."""
    if no_auto_build:
        return

    db_path = project_root / ".claude" / "graph.db"
    needs_build = False
    if not db_path.exists():
        needs_build = True
    else:
        # Sanity check: DB exists but empty? (zero files indexed)
        with sqlite3.connect(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            if count == 0:
                needs_build = True

    if needs_build:
        if not json_mode:
            print("⏳ graph.db ausente/empty — buildando...", file=sys.stderr)
        from engine.graph.builder import build_full
        build_full(project_root)
```

Parse `--no-auto-build` flag no início de `run(argv)`:
```python
no_auto_build = False
if "--no-auto-build" in argv:
    no_auto_build = True
    argv = [a for a in argv if a != "--no-auto-build"]
```

Chamar `_maybe_auto_build` antes do dispatch.

- [ ] **Step 9.5.4: Escrever tests FALHANDO primeiro pra detection**

`tests/engine/test_bootstrap_detection.py`:
- `test_check_bootstrap_state_returns_none_when_symlink_exists` (tmpdir + symlink fixture)
- `test_check_bootstrap_state_returns_error_when_symlink_missing`
- `test_check_bootstrap_state_skips_for_bootstrap_subcommand` (integration smoke)
- `test_check_bootstrap_state_skips_for_version_help`

Run: `pytest tests/engine/test_bootstrap_detection.py -xvs` → confirmar FAIL (função não existe ainda).

- [ ] **Step 9.5.5: Implementar detection (Step 9.5.2) + rodar test**

Run: `pytest tests/engine/test_bootstrap_detection.py -xvs` → PASS.

- [ ] **Step 9.5.6: Escrever tests FALHANDO primeiro pra lazy auto-build**

`tests/engine/test_graph_lazy_build.py`:
- `test_lazy_build_triggers_when_db_missing` (tmpdir, no DB, run query → DB criado)
- `test_lazy_build_triggers_when_db_empty` (DB existe mas zero files indexed)
- `test_lazy_build_skipped_with_no_auto_build_flag`
- `test_lazy_build_quiet_in_json_mode` (não printa pra stderr em --json)

Run: `pytest tests/engine/test_graph_lazy_build.py -xvs` → confirmar FAIL.

- [ ] **Step 9.5.7: Implementar lazy build (Step 9.5.3) + rodar test**

Run: `pytest tests/engine/test_graph_lazy_build.py -xvs` → PASS.

- [ ] **Step 9.5.8: README + handoff doc-sync**

`README.md` §Bootstrap atualizar pra mencionar:
- "Após clonar, rode `bash .claude/bootstrap.sh` (faz install deps + builds graph + inventory)"
- "Para CI/scripts, use `forge graph --no-auto-build ...` pra desabilitar auto-rebuild"

`docs/design/08-session-handoff.md` §Conhecidos limites adicionar:
- "Graph é local per-dev (Decision 20). Primeira invocação `forge graph` em máquina sem bootstrap triggera lazy rebuild (~30s-2min). Bootstrap script `bash .claude/bootstrap.sh` faz o build inicial e setup de hooks."

- [ ] **Step 9.5.9: Rodar pytest full + verify**

Run: `pytest -q 2>&1 | tail -3` → 0 failures, count ≥ baseline + 8 tests novos (4 detection + 4 lazy build)
Run: `forge verify 2>&1 | tail -10` → cascade sem hard fails

**NÃO fazer:**
- Não auto-fixar bootstrap state (instalar symlinks silenciosamente é invasivo)
- Não mover `_check_bootstrap_state` pra fora de `engine/cli.py` (single entrypoint)
- Não implementar inventory rebuild em si — `forge reconfigure --inventory-only` é dispatch separado SE não existir (deviation report)
- Não bumpar versão pro v1.4 — esta Task entra em v1.3.0 acoplada às demais Ondas
- Não tocar `_LANGUAGE_EXTENSIONS` etc. (Onda 6 cobre)

---

## Task 10: Verification final (Mandamento #2)

**Files:** none (read-only)

- [ ] **Step 10.1: pytest full suite + verificar count_final**

Run: `pytest 2>&1 | tail -10`
Expected: green. Zero failures, zero skips novos.

Comparar count contra baseline registrado em Step 0.2:

```bash
pytest --collect-only -q | tail -1
```

Expected: `count_final ≥ count_baseline + 26 (Java 7 + XML 5 + ObjC 6 + onboarding UX 8 — Java/XML/ObjC nas Tasks 4/5/6, UX nas Tasks 9.5.4/9.5.6 com 4+4 tests respectivamente)`. Se count diverge pra baixo, identificar quais tests sumiram antes de declarar concluído.

- [ ] **Step 10.2: forge verify**

Run: `forge verify 2>&1 | tail -20`
Expected: cascade verde, sem hard fails.

- [ ] **Step 10.3: Smoke do CLI — parsers importáveis**

Run:
```bash
python -c "from engine.graph.parser_java import parse_java_file; print('java parser OK')"
python -c "from engine.graph.parser_xml import parse_xml_file; print('xml parser OK')"
python -c "from engine.graph.parser_objc import parse_objc_file; print('objc parser OK')"
```
Expected: todos importáveis sem erro.

- [ ] **Step 10.4: Smoke do `--json` flag**

Run:
```bash
forge graph --json q3 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'JSON OK: {len(d)} entries')"
```
Expected: JSON parseable, sem erro.

- [ ] **Step 10.5: Subagent reviewer (gsd-code-reviewer)**

Orquestrador dispatcha review com prompt focado em:
- Body column não quebra queries existentes que usam `body_hash`/`body_tokens`
- Java/XML/ObjC parsers seguem pattern dos parsers existentes
- `_persist_*` functions têm shape consistente com `_persist_kotlin`/`_persist_swift`/`_persist_typescript`
- `_SUPPORTED_LANGS` tem entradas corretas (java, objc; xml não precisa)
- `--json` não quebra modo interactivo existente
- `forge graph detect-incremental` continua funcionando
- Voz mentor calmo nos artefatos modificados

Findings high/critical → fix-dispatch loop.

---

## Verification (overall criteria)

| AC | Coberto por |
|---|---|
| AC-1 (body column) | Task 1 migration + persist + parsers body field |
| AC-2 (body readable via graph) | Task 1 + Task 9 schema doc |
| AC-3 (forge graph --json functional) | Task 3 smoke test |
| AC-4 (Java parser — symbols + imports) | Task 4 parser + tests (7 tests) |
| AC-5 (XML parser — view IDs + classes + resources + binding) | Task 5 parser + tests (5 tests) |
| AC-6 (ObjC parser — symbols + imports, NO call graph) | Task 6 parser + tests (6 tests) |
| AC-7 (novas extensões registradas) | Task 7.1-7.9 (builder, incremental, ingest, _body_text, hook) |
| AC-8 (instrução pro modelo) | Task 8 AGENTS.md/CLAUDE.md edit |
| AC-9 (pytest baseline) | Task 10.1 pytest green |
| AC-10 (CI verde) | Task 10 full verification |

## Commits esperados

Atomic per task ou grupos coesos:

1. `feat(graph-ia): body column + persist functions + parser body field` (Tasks 1–2)
2. `feat(graph-ia): forge graph --json non-interactive queries` (Task 3)
3. `feat(graph-ia): Java parser engine/graph/parser_java.py` (Task 4)
4. `feat(graph-ia): XML parser engine/graph/parser_xml.py` (Task 5)
5. `feat(graph-ia): ObjC parser engine/graph/parser_objc.py` (Task 6)
6. `feat(graph-ia): register extensions + persist functions + incremental hooks` (Task 7)
7. `docs(graph-ia): AI consumption instructions for graph queries` (Task 8)
8. `docs(graph-ia): schema doc + CHANGELOG + handoff` (Task 9)

Verification (Task 10) é leitura — não gera commit.

## Anti-padrões (NÃO fazer durante execução)

- Implementar tree-sitter parsers (escopo futuro, regex suficiente)
- Implementar MCP server (fora de escopo — IA consulta via `forge graph --json`)
- Implementar call graph completo pra ObjC (`[obj selector]` parsing)
- Bumpar `SCHEMA_VERSION` (body column adicionada via ALTER TABLE)
- Refatorar parsers existentes durante o trabalho
- Remover modo interactivo do `forge graph`
- Mudar API das queries `gq.*`
- Adicionar parsing de Gradle, npm, Podfile, etc. neste plano
- Voz corporativa, hedging ou emoji decorativo em CHANGELOG/handoff/schema
- Commit de fixtures com conteúdo não canônico (mínimo plausível apenas)

## Pending gaps coverage (Mandamento #4 / M2)

Este plano adiciona cobertura de linguagens que estavam implícitas como "futuro" na visão original do forge. As novas extensões `.java`, `.xml`, `.m`, `.mm` são registradas no mesmo padrão das existentes (Task 7). A coluna `body` é adicionada como ALTER TABLE sem mudança de schema version — mantendo compat retroativa com DBs v2 existentes. Nenhum pending gap é criado — o plano fecha o item de "expansão de cobertura de linguagem" que estava na visão do graph desde v1.0.
