<!-- Injected into: task-contract-writer
     Extension point: after:Allowed Files
     Source card:     room-database v1.0.0
-->

## Room persistence file patterns (card `room-database`)

Quando uma TASK toca Entities, DAOs, `@Database`, migrations ou mappers
locais, use os padrões canônicos abaixo para `allowed_files` e
`validations`. Não invente caminhos: derive de
`inventory.conventions.folder-layout` + os globs abaixo.

### `allowed_files` — globs canônicos

Código Room vive em `data/local/` do shared layer:

- Entities:
  `shared/**/src/commonMain/kotlin/**/data/local/entity/*Entity.kt`
- DAOs:
  `shared/**/src/commonMain/kotlin/**/data/local/dao/*Dao.kt`
- `@Database`:
  `shared/**/src/commonMain/kotlin/**/data/local/db/*DataBase.kt`
- Migrations manuais:
  `shared/**/src/commonMain/kotlin/**/data/local/db/migrations/*Migration*.kt`
- Mappers Entity ↔ Domain:
  `shared/**/src/commonMain/kotlin/**/data/local/mapper/*LocalMapper*.kt`
- TypeConverters (datetime, enums, value classes):
  `shared/**/src/commonMain/kotlin/**/data/local/converter/*Converter*.kt`
- Schemas exportados pelo Room (versionados em PR):
  `shared/**/schemas/**/*.json`
- DI factory consumindo `RoomDatabase.Builder`:
  `shared/**/src/{androidMain,iosMain}/kotlin/**/di/*DatabaseFactory.kt`
  (a parte platform-specific do builder)

**Sempre excluir** das `allowed_files`:

- `**/build/**` (KSP gera DAO impls aqui — não editáveis manualmente).
- `**/generated/**` (Room compiler output).
- Entity/DAO em `androidMain/` ou `iosMain/` quando o módulo é KMP —
  o canônico é `commonMain/`. Aparição em sourceSet específico exige
  justificativa no tech-spec.

### `validations` — comandos canônicos

Cada TASK que cria/modifica Entity/DAO/Database declara:

```yaml
validations:
  - name: detekt
    command: "./gradlew detekt"
    on-failure: block
  - name: ktlint
    command: "./gradlew ktlintCheck"
    on-failure: block
  - name: compile-shared
    command: "./gradlew :shared:<module>:compileKotlinMetadata"
    on-failure: block
  - name: ksp-room
    command: "./gradlew :shared:<module>:kspCommonMainKotlinMetadata"
    on-failure: block
```

TASK que muda `@Database.version` (migration nova) adiciona:

```yaml
  - name: room-migration-test
    command: "./gradlew :shared:<module>:testAndroidHostTest --tests '*MigrationTest'"
    on-failure: block
  - name: check-room-migrations
    command: "python3 .claude/cards/room-database/validators/check-room-migrations.py"
    on-failure: block
```

> Migration test mínimo: usar `MigrationTestHelper`, criar DB no schema
> antigo a partir do JSON em `schemas/<DB>/<oldVersion>.json`, aplicar a
> migration, validar contagem de tabelas/colunas + integridade dos dados.

### `gates`

- TASK criando/alterando Entity ou DAO → gate `lint-and-format`
  (detekt + ktlint) + `compile-shared`.
- TASK alterando schema de Entity (campo novo/removido/renomeado, tipo
  mudado, índice modificado) → gate `room-migration-test` +
  `check-room-migrations`.
- TASK criando migration manual (`<Feature>Migration<N>to<M>.kt`) →
  gate `room-migration-test` obrigatório + KDoc explicando por que
  `@AutoMigration` não cobre.
- TASK alterando `@Database.version` → exige entrada em
  `data-contract-spec.yaml` `room-tables[*].migrations.history` na
  mesma PR.

### Anti-patterns a sinalizar no `task-breakdown.yaml`

- TASK adicionando `LiveData<T>` em DAO no `commonMain` → erro de spec
  (Android-only, quebra KMP).
- TASK criando `RoomDatabase.Builder` no Repository ou UseCase → erro
  de spec (builder vive na factory de DI platform-specific).
- TASK adicionando `fallbackToDestructiveMigration()` em variant de
  produção → bloquear.
- TASK alterando `exportSchema = false` → bloquear (impossibilita
  revisão de migration em PR).
- TASK adicionando Entity em `androidMain` quando o módulo é KMP →
  mover para `commonMain` ou justificar no tech-spec.
- TASK retornando domain model direto de `@Query` → erro de spec
  (sempre Entity no DAO + Mapper no Repository).
- TASK hardcodando `Dispatchers.IO` no Repository (sem injeção via
  construtor) → erro de spec (quebra testabilidade com
  `UnconfinedTestDispatcher`).
- TASK criando múltiplas instâncias do mesmo `RoomDatabase` → erro de
  spec (sempre singleton via DI).
- TASK que muda `@Database.version` sem entrada em
  `migrations.history` no `data-contract-spec.yaml` → erro de spec
  (contract incompleto, falha `check-room-migrations`).
