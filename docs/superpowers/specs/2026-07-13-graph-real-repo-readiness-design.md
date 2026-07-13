# GRAPH-REAL-REPO — Prontidão do codebase graph para monorepo de produção

> **Status:** draft — design aprovado em brainstorming; aguarda review do spec
> **Data:** 2026-07-13
> **Plano:** `docs/superpowers/plans/2026-07-13-graph-real-repo-readiness.md` (a escrever)
> **Release-target:** TBD (bump menor)
> **Revisita:** nenhuma decisão locked

---

## Contexto / motivação

Spike empírico (2026-07-13) rodou o `build_full` do graph contra o
`inchurch-app-main` (monorepo KMP real: 18.607 arquivos-fonte, 86.362 símbolos
após .gitignore/exclusões). Dois achados bloqueiam o uso do graph em repo de
produção:

1. **`_resolve_import_targets` não completa.** É O(imports × symbols) ≈ 2,97
   bilhões de comparações via `LIKE '%.'||s.name` (wildcard à esquerda,
   não-indexável) + `ORDER BY` por-linha. Rodou >4 min sem terminar; abortado no
   cap de 180s. Está no caminho do `build_full` → **`forge init` trava** em
   qualquer repo dessa escala. Nunca apareceu porque o único piloto foi o
   MeoBonsai (minúsculo).
2. **Inferência de source-set cega ao layout Android padrão.** 18.192 de 18.607
   arquivos ficaram com `source_set = NULL`. Causa raiz confirmada:
   `infer_module_and_source_set` (engine/graph/gradle_modules.py) só reconhece
   nomes de source-set KMP (`commonMain`/`androidMain`/`iosMain` via
   `KMP_SOURCE_SETS`), mas o grosso do Kotlin do app vive em `/src/main/`
   (layout Android/JVM padrão) e o Swift em `iosApp/` (layout Xcode). Só o módulo
   `shared` usa naming KMP (322 commonMain detectados). Consequência: as
   reuse-queries plataforma-específicas (`redundant-platform-specific`,
   `kmp-migration-candidate`) ficam quase-cegas — recall ~zero (1 finding real
   em ~5.100 arquivos Kotlin+Swift).

Os parsers regex em si são sólidos e rápidos (18.6k arquivos / 12,2s, zero
crashes) — o problema não é parsing, é (1) escalabilidade do import-resolution e
(2) modelagem de plataforma.

---

## Goal

Deixar o codebase graph **construível e plataforma-consciente num monorepo
mobile de produção**, para que (a) `forge init`/rebuild complete em tempo
aceitável e (b) as reuse-queries plataforma-específicas enxerguem o código
Android/iOS/common real. Validação final é um **re-spike** contra o
`inchurch-app-main`. Este spec cobre **apenas o Stage 1** (as duas correções + o
re-spike de validação). Ampliar o universo de símbolos
(composables/members/classes, similaridade fuzzy) — Stage 2 — e integrar no app
— Stage 3 — são **gated**: só entram se o re-spike do Stage 1 mostrar que o
recall justifica.

---

## Non-goals (fora de escopo deste stage)

- Ampliar os kinds de símbolo cobertos pela reuse-intelligence (composables,
  member functions, classes, data classes) → Stage 2, decidido com o dado do
  re-spike.
- Similaridade fuzzy/token além do body_hash exato → Stage 2.
- Qualquer skill/hook/gatilho no `inchurch-app-main` → Stage 3, gated.
- Paralelizar o build (multiprocessing). O gargalo do Stage 1 é o
  import-resolution O(n²); o parse serial (~12s) e o walk (~30s) são aceitáveis
  por ora.
- Tree-sitter / troca de estratégia de parsing (parsers regex provaram robustez
  na escala).
- Novas dependências externas (mantém stdlib + pathspec).

---

## Acceptance Criteria

- **AC-1 — `_resolve_import_targets` completa em ~O(imports + symbols).** A
  resolução usa um índice pré-computado `{nome_símbolo → [file_id]}` (uma passada
  sobre `symbols`), resolvendo o segmento terminal de cada import contra o índice
  (match exato + sufixo), eliminando o correlated `LIKE '%.'||s.name`. **A
  semântica de resolução vigente é preservada** (o implementador lê o algoritmo
  atual e mantém o mesmo conjunto de edges resolvidas). Verificável: `build_full`
  contra o `inchurch-app-main` completa a fase de import-resolution em segundos
  (não >180s); as edges `imports.to_file_id` são equivalentes às do algoritmo
  anterior num fixture controlado (mesmo conjunto de pares (from_file,
  to_file)).
- **AC-2 — Coluna `platform` em `files`, populada por inferência
  plataforma-consciente.** Nova coluna `files.platform` ∈ `{common, android,
  ios, jvm, NULL}`, adicionada via ALTER idempotente (mesmo padrão do `body`
  column — sem bump de SCHEMA_VERSION). Um helper `infer_platform(module,
  source_set, rel_path, language)` deriva: source-set KMP explícito → plataforma
  correspondente (commonMain→common; androidMain/androidUnitTest/androidTest→
  android; iosMain/iosTest/variantes iOS→ios; jvmMain→jvm); `/src/main/` +
  source-sets de flavor Android + `.java` → android; Swift/ObjC em layout Xcode
  (`iosApp/`, sem source-set KMP) → ios; fallback → NULL. Verificável: fixture
  espelhando o layout do app (shared/commonMain, androidApp/src/main, iosApp
  Swift, um flavor dir) → cada arquivo recebe a plataforma correta; re-build do
  `inchurch-app-main` deixa a **maioria** dos arquivos com `platform` não-NULL
  (vs ~415 não-NULL hoje via source_set).
- **AC-3 — Reuse-queries plataforma-específicas usam `platform`.**
  `redundant-platform-specific` e `kmp-migration-candidate` passam a discriminar
  lado-Android / lado-iOS / lado-common via `files.platform` (em vez da
  heurística `module LIKE 'androidApp%'` + source_set literal). A semântica dos
  findings é preservada; o universo de comparação cresce para incluir o Android
  em `/src/main/` e o Swift do `iosApp`. Verificável: teste de detecção em
  fixture com dup android↔common em layout `/src/main/` produz o finding (hoje
  não produz).
- **AC-4 — Incremental honra `platform`.** O caminho incremental
  (`incremental.update_file`/`update_batch`) popula `platform` no re-insert,
  idêntico ao build full. Verificável: editar um arquivo em `/src/main/` e
  re-ingestar mantém `platform=android`.
- **AC-5 — Verde no forge + re-spike de validação.** `pytest` (lane completa)
  verde, `forge verify` sem hard fail. E o **re-spike** contra o
  `inchurch-app-main` (mesmo protocolo do spike original: worktree + venv
  isolado, db em scratch, zero mutação no app) reporta: (a) build completo +
  tempo total, (b) distribuição de `platform`, (c) contagem de reuse-findings
  por categoria — insumo pra decidir o Stage 2.

---

## Approach / design

### Fix A — import-resolution (perf, behavior-preserving)

Ler o `_resolve_import_targets` atual (engine/graph/builder.py) e preservar sua
semântica de resolução. Trocar o loop correlacionado por: (1) uma passada
`SELECT id, name FROM symbols` construindo um índice em memória `name →
[file_id]`; (2) para cada linha de `imports`, derivar o nome-alvo (segmento
terminal) e resolver via o índice (match exato + sufixo `.`+name), aplicando o
MESMO critério de desambiguação do algoritmo atual; (3) escrever
`imports.to_file_id` em batch numa transação. Um teste de equivalência num
fixture controlado é o guard contra regressão silenciosa de edges.

### Fix B — inferência de plataforma

Adicionar `files.platform` via ALTER idempotente (`_ensure_*` no padrão do `body`
column; índice em `platform`). Introduzir `infer_platform(...)` (em
gradle_modules.py ou helper adjacente) com as regras de AC-2. Popular a coluna no
build full (builder.py) e no incremental (incremental.py). Atualizar
`redundant-platform-specific` e `kmp-migration-candidate` (engine/graph/
duplicates.py + queries.py) pra discriminar por `platform`.

**Alternativa rejeitada (B2):** sobrecarregar `source_set` mapeando `/src/main/`
→ `'androidMain'`. Rejeitada por conflação semântica (source-set KMP literal vs
plataforma derivada) — mascara a distinção e arrisca resultados errados em
qualquer consumidor que trate `source_set` como literal. A coluna `platform`
dedicada é o modelo honesto.

### Doc-sync

- `docs/schemas/graph.md`: documentar a coluna `platform` + a inferência.
- `CHANGELOG.md` (Unreleased) na fase de implementação.

---

## Risks & limitations

- A inferência de plataforma é heurística por path/módulo; layouts exóticos podem
  cair em NULL (degrade seguro — queries ignoram NULL).
- Fix A muda o algoritmo de resolução; o teste de equivalência num fixture é o
  guard.
- O re-spike pode mostrar que, mesmo com plataforma consertada, o recall segue
  baixo — porque o universo de símbolos ainda é estreito (extension functions +
  body exato). Isso é **esperado** e é exatamente o gate pro Stage 2.

---

## Coverage (AC → tasks)

(A ser preenchida pelo plano de implementação —
`docs/superpowers/plans/2026-07-13-graph-real-repo-readiness.md`.)
