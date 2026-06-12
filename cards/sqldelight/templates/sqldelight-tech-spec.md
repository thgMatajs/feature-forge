<!--
  Template fragment contribuído por: sqldelight
  Target: tech-spec.md
  Merge: append-section "Local persistence (SQLDelight)"
-->

## Local persistence (SQLDelight)

Esta seção é injetada pelo card `sqldelight` e padroniza a camada de
persistência SQL KMP-native em features que consomem dados relacionais
locais.

### Camada `commonMain/sqldelight/`

```
shared/feature/<feature>/src/commonMain/sqldelight/<package>/
├── <Feature>.sq           (schema + queries — DSL SQLDelight)
└── migrations/
    └── 1.sqm              (migration v0 → v1, opcional)
```

Schema e queries vivem em `*.sq` files. SQLDelight gera o código Kotlin
type-safe em build time — sem reflection, sem runtime overhead.

### Drivers por plataforma

| Target | Driver | Onde |
|---|---|---|
| Android | `app.cash.sqldelight:android-driver` | `androidMain` — `AndroidSqliteDriver(schema, context, "<feature>.db")` |
| iOS | `app.cash.sqldelight:native-driver` | `iosMain` — `NativeSqliteDriver(schema, "<feature>.db")` |
| commonMain | — | `expect class DatabaseDriverFactory` (declara contrato; actual nos source sets per-platform) |

### Query DSL canônico

| Padrão | Quando |
|---|---|
| `selectAll()` em `Flow<List<T>>` via `asFlow().mapToList(...)` | Observabilidade reativa de tabelas (pareado com coroutines-extensions). |
| `selectById(id: Long)` retornando `T?` | Single-shot lookup. |
| `transaction { ... }` em queries write-heavy | Atomicidade de batch inserts/updates. |

### Migrations

| Estratégia | Quando |
|---|---|
| `*.sqm` files versionados | Sempre — SQLDelight aplica em ordem (1.sqm, 2.sqm, …) por `Schema.migrate`. |
| `Schema.create` + `Schema.migrate` callbacks | Setup inicial + upgrades acionados pelo driver factory. |

### Integração com coroutines

`app.cash.sqldelight:coroutines-extensions` adiciona `asFlow()` +
`mapToList()` / `mapToOne()` — pareie com kotlinx.coroutines em
`viewModelScope` / `presentationScope` para queries reativas.
