<!-- Injected into: tech-spec-agent
     Extension point: section:Shared (KMP) layer
     Source card:     room-database v1.0.0
-->

## Local persistence conventions — Room (card `room-database`)

A partir de Room 2.7+ o framework é **KMP-stable**: `@Entity`, `@Dao` e a
classe `RoomDatabase` ficam em `commonMain` do shared module. A construção
do `RoomDatabase.Builder` permanece platform-specific (Android usa
`Room.databaseBuilder(context, ..., name)`; iOS usa
`Room.databaseBuilder<DB>(name = path)` + `BundledSQLiteDriver()`). Esta é
a escolha canônica v1 do feature-forge para `persistence-local` —
`sqldelight` não está no catálogo v1.

Se o tech-spec prescrever algo que viola uma das regras abaixo, registre
como **3-caminhos failure** em `open-questions.yaml` em vez de inventar.

### Estrutura canônica

```
shared/feature/<feature>/src/commonMain/kotlin/.../data/local/
├── entity/<Entity>Entity.kt         @Entity / @PrimaryKey / @ColumnInfo / @Index
├── dao/<Feature>Dao.kt              @Dao + @Query / @Insert / @Update / @Delete
├── db/<Feature>DataBase.kt          @Database(version, entities, autoMigrations)
└── db/migrations/<Feature>Migration<N>to<M>.kt   apenas quando @AutoMigration falha
```

Mapper Entity ↔ Domain fica em `data/.../mapper/<Entity>LocalMapper.kt`.
Repository (`data/.../repository/<Feature>RepositoryImpl.kt`) consome o
DAO via construtor — DAO **nunca** vaza para `domain/` ou `presentation/`.

### Regras canônicas

- **Naming**: `{Entity}Entity`, `{Feature}Dao`, `{Feature}DataBase`,
  `{Entity}LocalMapper` (alinhado com `architecture_kmp.md §Nomenclatura`).
  Entity name termina em `Entity` para distinguir de domain model.
- **DAO retorna `Flow<T>` para observabilidade reativa**; `suspend fun`
  para single-shot. `LiveData<T>` é proibido em commonMain (Android-only).
- **`@Database`** declara `version` (inteiro monotonicamente crescente),
  `entities` (lista exaustiva), `autoMigrations` (sempre que possível)
  e `exportSchema = true`. Diretório `schemas/` versionado em PR.
- **Dispatcher injetado**: Repository envolve chamadas DAO em
  `withContext(ioDispatcher) { ... }`. Nunca hardcodar `Dispatchers.IO`
  no corpo — sempre via construtor (ver
  `kotlin-idioms.md §Dispatchers e Main Thread`).
- **Singleton por feature**: uma instância de `RoomDatabase` por feature,
  obtida via DI (`@Single` em Koin Annotations no Android; factory
  function `create<Feature>DataBase()` em `di/<Feature>Factory.kt` no
  iOS/Web).
- **Entity ≠ Domain**: snake_case no SQL, valores brutos (Long epoch
  millis para datetime, String para enum). Mapper traduz para tipos
  ricos (`Instant`, `LocalDate`, sealed enum).

### Migrations

- **Default `@AutoMigration`** para `from → to` consecutivos (add column
  nullable, add table, add index). Renames simples cobertos via
  `@AutoMigration` + `AutoMigrationSpec`.
- **Migration manual** apenas quando `@AutoMigration` não cobre: rename
  complexo, mudança de tipo, split de tabela, foreign-key nova. Arquivo
  em `db/migrations/<Feature>Migration<N>to<M>.kt`, registrado com
  `.addMigrations(...)` no builder.
- **PROIBIDO em produção**: `fallbackToDestructiveMigration()` —
  destrói dados do usuário silenciosamente. Aceito apenas em variants de
  teste.
- Cada bump de `@Database.version` exige migration declarada **e**
  teste de migration cobrindo a transição com schema real exportado.

### Pareamento com persistência server-side

Quando a feature combina Room (local) com `persistence-server` (ex.:
Firestore), declare explicitamente no tech-spec:

- **Modo**: `write-through` (escreve local + remoto em paralelo),
  `stale-while-revalidate` (serve cache, dispara fetch), `offline-first`
  (UI lê só do local; remoto é background sync), `local-only` (sem
  server).
- **Invalidação**: trigger (push, polling, listener realtime, write
  remoto local-first).
- **Fonte da verdade**: qual lado vence em conflito de timestamps.

### Threading

- Toda chamada DAO é I/O — Repository envolve em `withContext(io)`.
- `Flow<T>` retornado pelo DAO é frio; coleta acontece em
  `viewModelScope`. Room internamente observa a tabela em background — UI
  recebe emissão atualizada quando há `insert`/`update`/`delete`.
- **NUNCA** `runBlocking` em Repository ou UseCase. **NUNCA** chamar
  DAO `suspend` fora de coroutine.

### Anti-patterns (bloquear no tech-spec)

- `@Entity` em `androidMain` quando o módulo é KMP — sempre em
  `commonMain`.
- DAO retornando `LiveData<T>` — Android-only, quebra `commonMain`.
- DAO retornando domain model direto via `@Query` (mapper inline) —
  sempre Entity no DAO + Mapper no Repository.
- `Repository.fun queryX(): Flow<X>` usando `runBlocking` para combinar
  emissões — usar `combine` / `map` de Flow.
- `fallbackToDestructiveMigration()` em build de produção.
- `exportSchema = false` — impossibilita revisão de migration em PR.
- Múltiplas instâncias do mesmo `RoomDatabase` por feature — sempre
  singleton via DI.
- `@Entity` com `var` mutável — sempre `val` + `data class`.
- Hardcode de `Dispatchers.IO` no Repository — injetar dispatcher no
  construtor (testabilidade com `UnconfinedTestDispatcher`).

### O que registrar no tech-spec

Para cada feature usando Room, declare na seção "Local Persistence — Room":

- Entities novas/alteradas (`{Entity}Entity`) e campos
  (`name → SQL type → nullable → indexed`).
- DAO queries (signature + retorno `Flow<List<X>>` vs `suspend fun`).
- `@Database.version` resultante + migration strategy
  (`@AutoMigration` simples, `@AutoMigration` + `AutoMigrationSpec`, ou
  Migration manual com diff descrito).
- Pareamento com `persistence-server` (se houver): modo + invalidação +
  fonte da verdade.
- Threading: dispatcher injetado, escopo (`viewModelScope`,
  `applicationScope`).
