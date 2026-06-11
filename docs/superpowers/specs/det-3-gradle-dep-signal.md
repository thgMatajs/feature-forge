# DET-3 — `gradle-dep` signal type — Design Spec

**Date:** 2026-06-10
**Status:** Approved (brainstorm session 2026-06-10, design locked)
**Phase:** v1.2-dev Phase 0 (pilot remediation)
**Related:**
- `docs/design/04-pending.md` §"v1.2-dev pilot 2026-06-10 — findings + phase sequencing" → DET-3
- `cards/ktor-client/detection/signals.yaml` + `cards/retrofit-client/detection/signals.yaml` (exemplos canônicos do gap)
- `docs/schemas/card.md` §"Signal types" (schema atual)
- `engine/init.py:_eval_detection_signals` (avaliador vivo)

## Contexto

Cards canônicos declaram signals do tipo `file-content` com `glob: "**/build.gradle*"` e `contains: "io.ktor:ktor-client"` (ou equivalente Maven coordinate) — padrão Gradle Groovy/Kotlin DSL legado. Projetos KMP modernos usam **Gradle version catalogs** (`gradle/libs.versions.toml`) onde a dependency é declarada em formato TOML:

```toml
[libraries]
ktor-client-core = { module = "io.ktor:ktor-client-core", version.ref = "ktor" }
```

A coordenada Maven não aparece em nenhum `build.gradle*` — o módulo apenas referencia o alias (`implementation(libs.ktor.client.core)`). Resultado observado no pilot v1.2-dev (`docs/design/04-pending.md` DET-3): scanner cego, cards não matcham, todos os 4 backend-candidates do preset `kmp-mobile` mostram `(cards matched: 0/N)`, default vence por ser primeiro da lista — não por evidência.

## Goal

Novo signal type `gradle-dep` no schema de detection, que abstrai presença de uma coordenada Maven em qualquer formato Gradle suportado (build.gradle legado + libs.versions.toml). O engine resolve onde procurar; o card declara apenas a coordenada.

## Why (DET-3 do pilot)

Catálogo Gradle é o default moderno em projetos KMP/Android desde Gradle 7.0 (2021). Manter `file-content` com glob `**/build.gradle*` exige que cada card declare **N signals duplicados** (um por formato) — manutenção quebra com facilidade, e libs.versions.toml puro continua invisível. Ver `docs/design/04-pending.md` linha 2351-2355.

## Non-Goals (escopo contido)

Deliberadamente fora deste SPEC:

- **B1** (`identity.backend-choice` ↔ `backend.provider` desync) — Phase B (DET-6)
- **B2** (seção `firebase:` órfã pós-swap) — Phase B (DET-6)
- **DET-5** (`retrofit-client` fora do preset kmp-mobile) — depende de DET-6 (bundle model)
- **DET-6** (bundle-first vs multi-axis backend model) — Phase B
- **DRIFT-1** (`engine/ui/question.py` intent-based) — Phase A
- **UI/persona/microcopy do pilot** — deferred até Phase A
- **Outros signal types novos** além de `gradle-dep` (ex.: `npm-dep`, `swift-dep`, `pod-dep`) — não cobertos. Quando demanda concreta aparecer, design segue o mesmo template.
- **Resolução de catálogo TOML como graph completo** — não fazemos parse semântico do `[versions]` block pra resolver `version.ref`; comparação é apenas sobre a string Maven coordinate em `module = "..."`.
- **Schema migration tool** — overlays + cards canônicos ficam migrados manualmente neste SPEC. Cards locais que projetos consumidores tenham customizado continuam funcionando com `file-content` (backward compat).
- **`dependency` signal type que figura no schema mas é vapor** — está documentado em `docs/schemas/card.md:387` mas nunca foi implementado em `engine/init.py:_eval_detection_signals`. Este SPEC NÃO ressuscita `dependency`; introduz `gradle-dep` como tipo distinto e específico. Cleanup do vapor `dependency` cai num plano separado (não-bloqueante).

## Design contract

### Sintaxe do signal

```yaml
signals:
  - type:       gradle-dep
    coordinate: "io.ktor:ktor-client-core"
    confidence: 0.5
```

**Campos:**

| Campo | Tipo | Obrigatório | Semântica |
|---|---|---|---|
| `type` | string literal `gradle-dep` | sim | discriminator |
| `coordinate` | string `<group>:<artifact>` | sim | Maven coordinate sem version (versão é irrelevante pra detection) |
| `confidence` | float [0.0, 1.0] | sim | mesma semântica de `file-content` |
| `id` | string opcional | não | mesmo padrão de `retrofit-client/signals.yaml` (audit trail) |
| `rationale` | string opcional | não | mesmo padrão de audit trail |

**Coordinate format:** `<groupId>:<artifactId>`. NÃO aceita prefixo parcial (`io.ktor` sozinho) nem versão (`io.ktor:ktor-client-core:2.3.0`). Card que quiser cobrir uma família de artifacts declara N signals — explícito é melhor que mágico.

### Resolver behavior

`_eval_detection_signals` ganha um novo branch:

```
elif kind == "gradle-dep":
    ok = _eval_gradle_dep(project_root, sig.get("coordinate"))
```

`_eval_gradle_dep(project_root, coordinate)` retorna `True` se a coordenada existe em **qualquer um** dos formatos abaixo (curto-circuita no primeiro match):

1. **Catálogo TOML:** procura `gradle/libs.versions.toml` (e variantes `*.versions.toml` no diretório `gradle/`). Em cada arquivo, varre o bloco `[libraries]`:
   - Match positivo se aparecer entrada com `module = "<coordinate>"` (case-sensitive, aceita aspas simples/duplas)
   - Match positivo também se aparecer formato split: `group = "<group>"` + `name = "<artifact>"` na mesma entry (TOML spec permite ambas formas)
2. **Plugin block legado:** procura em `**/build.gradle` e `**/build.gradle.kts` (mesmo glob que `file-content` usava). Match positivo se o arquivo contém a string `"<coordinate>"` (com ou sem versão sufixada) em qualquer linha de dependencies block. Reusa scanner linha-a-linha de `_glob_any` por economia (não parse AST Groovy/Kotlin DSL).
3. **Fallback negativo:** se nenhum dos dois bateu, retorna `False`. Score do signal fica zerado, sem afetar outros signals do mesmo card.

**Ordem é deterministic** (catálogo primeiro, build.gradle depois) — necessário pra projetos híbridos onde a mesma dep aparece nos dois.

**Edge cases tratados:**

- Catálogo com `version.ref = "ktor"` separado: a entry ainda contém `module = "io.ktor:ktor-client-core"`, então match positivo sem precisar resolver a versão.
- TOML mal-formado: try/except silencioso (mesma postura defensiva de `_glob_any` em `OSError`). Não bloqueia init.
- Catálogo customizado em path não-canônico (ex.: `gradle/dependencies.toml`): coberto pelo glob `gradle/*.versions.toml` na fase 1. Catálogos fora desse padrão são out-of-scope v1 (deferred — observação real determinará se vale generalizar).
- `build.gradle` que importa dep via plugin DSL (`plugins { id "io.ktor.plugin" version "..." }`): NÃO conta como match — coordenada Maven do plugin é separada da coordenada da lib. Cards que precisam detectar o plugin declaram signal específico.
- Coordenada idêntica em múltiplos catálogos: primeiro match conta. Não somamos confidence por duplicação.

### Backward compatibility

`file-content` continua funcionando exatamente como hoje. Cards que NÃO migrarem permanecem válidos. Schema doc atualizado pra listar `gradle-dep` como tipo preferido para deps Gradle, mas `file-content` não é deprecated — continua útil pra:

- Strings em código (`**/*.kt` com `HttpClient(`, `**/*.kt` com `import io.ktor.client`)
- Arquivos não-Gradle (`**/Podfile*`, `**/Package.swift`, `**/google-services.json`)
- Qualquer match que NÃO seja declaração de Maven coordinate

### Migration policy

**Migrate signal → `gradle-dep`** se TODAS as condições baterem:

1. Signal atual tem `type: file-content`
2. Glob é `**/build.gradle*` (ou variação)
3. `contains` é uma Maven coordinate (`<group>:<artifact>` ou apenas `<artifact>` no caso de gradle DSL inferindo group)

**Preserve como `file-content`** se qualquer condição abaixo bater:

1. Glob é `**/*.kt`, `**/*.swift`, `**/*.ts`, `**/Podfile*`, `**/Package.swift`, `**/*.json`, etc. (não-Gradle)
2. `contains` é um símbolo de código (anotação, função, classe, import) — não uma coordenada
3. `contains` é uma string que pode aparecer fora de dependency declaration (regex parcial, comentário)

**Casos ambíguos** (apenas artifact-name sem group, ex.: `contains: "firebase-auth"`):

- Se em `**/build.gradle*`, há risco do legado declarar como `implementation("com.google.firebase:firebase-auth-ktx")` — a coordenada completa é `com.google.firebase:firebase-auth-ktx`. Migrate para `gradle-dep` com coordenada completa quando documentação do card permitir identificar group. Senão, **mantém file-content** por conservadorismo (Mandamento #4: em dúvida, não tocar).

Universo a avaliar: 16 cards canônicos com signals tocando `**/build.gradle*` (mapeado em `cards/*/detection/signals.yaml` via `grep -l "build.gradle"`). Cada card recebe avaliação 1-a-1 no PLAN; SPEC apenas estabelece a regra.

### Espelho card.yaml ↔ signals.yaml

Em `cards/<name>/card.yaml` o bloco `detection.signals` é o canonical; em `cards/<name>/detection/signals.yaml` é espelho com audit trail. Migration deve atualizar AMBOS os arquivos para cada card alterado, pra não introduzir desync (loader não cross-checka conteúdo, apenas shape — CARD-015/016).

### CARD-016 sanity

Soma de confidences ≤ 2.0 (`engine/cards/loader.py:653`) continua aplicável a `gradle-dep` (avaliação é shape-based, não type-based — apenas soma `sig.get("confidence")`). Migration não pode aumentar a soma; deve preservar valor numérico ou explicar mudança no commit body.

## Acceptance criteria

Cada critério é testável e ganha task explícita no PLAN.

**AC-1 — Catálogo TOML moderno (ktor-client):**
Fixture `tests/fixtures/gradle-dep-toml-only/` contém apenas `gradle/libs.versions.toml` com entry `ktor-client-core = { module = "io.ktor:ktor-client-core", version.ref = "ktor" }` e nenhum `build.gradle*` declarando io.ktor. `cards/ktor-client/` card retorna `auto-activate` (score ≥ threshold 0.5).

**AC-2 — Catálogo split format (group + name):**
Fixture `tests/fixtures/gradle-dep-toml-split/` contém `gradle/libs.versions.toml` com entry `ktor = { group = "io.ktor", name = "ktor-client-core", version.ref = "ktor" }`. Mesmo card retorna `auto-activate`.

**AC-3 — Build.gradle legado preservado:**
Fixture `tests/fixtures/gradle-dep-legacy/` contém `app/build.gradle.kts` com `implementation("io.ktor:ktor-client-core:2.3.0")` e nenhum `libs.versions.toml`. Card retorna `auto-activate` (mesmo path antigo, agora via `gradle-dep` em vez de `file-content`).

**AC-4 — Híbrido catálogo + build.gradle:**
Fixture `tests/fixtures/gradle-dep-hybrid/` declara dep nos dois formatos. Card retorna `auto-activate` exatamente uma vez (sem double-counting de confidence).

**AC-5 — Negative case:**
Fixture `tests/fixtures/gradle-dep-negative/` tem `gradle/libs.versions.toml` com outras deps mas NÃO ktor. Card retorna score < threshold (sem auto-activate).

**AC-6 — Backward compat de `file-content`:**
Fixture `tests/fixtures/gradle-dep-file-content-preserved/` tem `**/*.kt` com `import io.ktor.client`. Signal `file-content` no card ktor-client (não-migrado) ainda contribui 0.2 ao score.

**AC-7 — Migração não regride detecção em nenhum card alvo:**
Pra cada card migrado, fixture pre-existente (greenfield + brownfield em `tests/e2e/`) que detectava o card antes da migration continua detectando após. Sem regressão.

**AC-8 — Schema doc + loader validation:**
`docs/schemas/card.md` lista `gradle-dep` na tabela §"Signal types". `engine/cards/loader.py` valida shape (`coordinate` é string `<group>:<artifact>`, sem versão sufixada, sem espaços). Validation rule nova: CARD-019 (ou next free) — `detection.signals[*].coordinate` schema-valid quando `type == "gradle-dep"`.

**AC-9 — pytest baseline preservada:**
Suite cresce a partir de 1113 tests (baseline atual). Zero regressão em tests pré-existentes. Novos tests cobrem AC-1..AC-6 unitariamente + AC-7 via integration smoke.

## Open questions resolvidas no brainstorm

| Questão | Resposta locked |
|---|---|
| Nome do tipo | `gradle-dep` (não `maven-dep`, não `dependency`) — específico pro ecossistema Gradle |
| Resolver behavior | Engine resolve onde procurar (catálogo + build.gradle), card declara apenas coordinate |
| Catálogo path | `gradle/*.versions.toml` por convenção; non-canonical paths são deferred |
| Backward compat de `file-content` | Preservado; não-deprecated |
| Universo de migração | 16 cards canônicos hoje; avaliação 1-a-1 no PLAN |
| Vapor `dependency` no schema | Cleanup separado, fora deste SPEC |
| Outros ecossistemas (npm, swift, pod) | Out-of-scope; mesmo template quando demanda concreta aparecer |

## Anti-goals (deliberadamente fora do v1)

- Parse semântico de TOML com resolução de `version.ref` (basta string match em `module = "..."`).
- Detecção de plugin DSL coordinates (`plugins { id "io.ktor.plugin" }`).
- Resolução de `subprojects { }` ou catálogos transitivos.
- Promover signal type genérico `dependency` que cubra npm/cargo/pip — cada ecossistema tem signal type próprio se demanda aparecer.
- `forge graph` query nova pra cards-by-coordinate (audit pode usar grep).
- Auto-migration tool de cards canônicos (migration é manual no PLAN).
- Suporte a settings.gradle catalogs declarados via `versionCatalogs { ... }` block — primeiro v1 cobre apenas o path convencional `gradle/libs.versions.toml`.

## Considerações futuras (fora do v1)

- **Coordinate variants** (`io.ktor:ktor-client-core` vs `io.ktor:ktor-client-core-jvm` vs `io.ktor:ktor-client-core-android`): hoje cada card declara explicitamente; se padrão recorrer, considerar wildcard sufixado (`io.ktor:ktor-client-core-*`).
- **Cleanup do vapor `dependency`** no schema (`docs/schemas/card.md:245-248, 387`): plano separado pós-DET-3.
- **`npm-dep`, `swift-dep`, `pod-dep`** quando observação real apontar gap análogo em projetos consumidores.
- **Schema-version bump nos signals.yaml**: hoje `schema-version: 1` em alguns cards (ex.: retrofit-client), ausente em outros. Normalização cai em outro plano.
- **Performance**: TOML parsing acontece per-signal hoje (cada card faz seu pass). Em projetos com 30+ cards isso é re-parse desperdiçado. Cache por `_eval_detection_signals` session pode entrar quando profiling mostrar dor real.
