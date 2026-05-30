<!-- Fragmento contribuído por: room-database v1.0.0
     Target:  tech-spec.md
     Section: "Local Persistence — Room"
     Merge:   append-section
-->

## Local Persistence — Room

Esta feature usa Room para persistência local. Room 2.7+ é **KMP-stable**:
`@Entity`, `@Dao` e a classe `RoomDatabase` ficam em `commonMain`; a
construção do `RoomDatabase.Builder` é platform-specific (Android via
`Room.databaseBuilder(context, ..., name)` em `androidMain`, iOS via
`Room.databaseBuilder<DB>(name = path)` + `BundledSQLiteDriver()` em
`iosMain`). Toda interação com SQLite acontece através de DAO + dispatcher
explícito (`Dispatchers.IO`) — nunca queries cruas espalhadas em
Repository.

### Estrutura no shared module

```
shared/feature/<feature>/src/commonMain/kotlin/.../data/
├── local/
│   ├── entity/
│   │   ├── <Entity1>Entity.kt        @Entity, @PrimaryKey, @ColumnInfo, @Index
│   │   └── <Entity2>Entity.kt
│   ├── dao/
│   │   └── <Feature>Dao.kt           @Dao + @Query/@Insert/@Update/@Delete + Flow
│   ├── db/
│   │   ├── <Feature>DataBase.kt      @Database(version, entities, autoMigrations)
│   │   └── migrations/
│   │       └── <Feature>Migration<N>to<M>.kt   apenas quando @AutoMigration falha
│   └── mapper/
│       └── <Entity>LocalMapper.kt    Entity ↔ Domain (Entity NUNCA vaza para domain)
└── repository/
    └── <Feature>RepositoryImpl.kt    consome o DAO via construtor (injetado via DI)
```

Naming canônico (alinhado com `architecture_kmp.md §Nomenclatura`):

- `{Entity}Entity` para a Room entity (`BonsaiEntity`, não `Bonsai`).
- `{Feature}Dao` para o DAO (`BonsaiDao`).
- `{Feature}DataBase` para a classe abstrata `RoomDatabase` (`BonsaiDataBase`).
- `{Entity}LocalMapper` para o mapper Entity ↔ Domain.

### Convenções obrigatórias

- **`@Entity` em `commonMain`** — Entity nunca em `androidMain`/`iosMain`.
- **DAO retorna `Flow<T>` para observabilidade**; `suspend fun` para
  single-shot (insert, update, delete, single read). Nunca `LiveData`
  no shared (Android-only).
  ```kotlin
  @Dao
  interface BonsaiDao {
      @Query("SELECT * FROM bonsai WHERE owner_uid = :ownerUid ORDER BY created_at DESC")
      fun observeByOwner(ownerUid: String): Flow<List<BonsaiEntity>>

      @Query("SELECT * FROM bonsai WHERE id = :id LIMIT 1")
      suspend fun findById(id: String): BonsaiEntity?

      @Insert(onConflict = OnConflictStrategy.REPLACE)
      suspend fun upsert(entity: BonsaiEntity)

      @Delete
      suspend fun delete(entity: BonsaiEntity)
  }
  ```
- **`@Database`** declara `version` (inteiro monotonicamente crescente),
  `entities` (lista) e — sempre que possível — `autoMigrations`:
  ```kotlin
  @Database(
      version = 2,
      entities = [BonsaiEntity::class],
      autoMigrations = [AutoMigration(from = 1, to = 2)],
      exportSchema = true,
  )
  abstract class BonsaiDataBase : RoomDatabase() {
      abstract fun bonsaiDao(): BonsaiDao
  }
  ```
- **`exportSchema = true`** + diretório `schemas/` versionado: garante
  diff visível em PR e habilita testes de migration.
- **Dispatcher**: queries DAO consumidas via `withContext(io)` no
  Repository — não confiar que o driver troca de thread sozinho.
  Dispatcher injetado no construtor (nunca hardcoded — ver
  `kotlin-idioms.md §Dispatchers e Main Thread`).
- **Entity ≠ Domain**: campo extra/derivado, snake_case no SQL → Mapper
  traduz. Domain model recebe `LocalDate`/`Instant` tipados; Entity
  guarda `Long` (epoch millis) ou `String` (ISO-8601).

### Migrations

- **Default `@AutoMigration`** sempre que possível. Cobre add column,
  add table, rename simples (via `@AutoMigration` + `AutoMigrationSpec`
  para renames).
- **Migration manual** apenas quando `@AutoMigration` falha: rename
  complexo, mudança de tipo, split de tabela. Declarar em
  `db/migrations/{Feature}Migration<N>to<M>.kt` e registrar com
  `RoomDatabase.Builder.addMigrations(...)` no factory de DI.
- **PROIBIDO**: `fallbackToDestructiveMigration()` em produção — apaga
  dados do usuário silenciosamente. Aceito apenas em variantes de teste.
- Cada bump de `version` exige migration declarada + teste de migration
  cobrindo o schema antigo → novo.

### Threading e Main thread

Toda operação Room é I/O — sai da main:

- Repository envolve chamadas DAO em `withContext(ioDispatcher) { ... }`.
- `Flow<T>` retornado pelo DAO já é frio e é coletado em
  `viewModelScope` no shared — Room observa internamente em background.
- **NUNCA** `runBlocking` no Repository nem chamada de DAO `suspend`
  fora de coroutine.

### Anti-patterns (bloquear no tech-spec)

- `@Entity` em `androidMain` quando o módulo é KMP — sempre em
  `commonMain`.
- DAO retornando `LiveData<T>` — Android-only, quebra commonMain.
- Mapper inline dentro do DAO (`@Query` retornando domain model direto) —
  sempre Entity no DAO + Mapper no Repository.
- `Repository.fun queryX(): Flow<X>` consumindo `runBlocking` para
  agregar valores — usar `combine` / `map` de Flow.
- `fallbackToDestructiveMigration()` em build de produção.
- `exportSchema = false` — impossibilita revisão de migration.
- Múltiplas instâncias do `RoomDatabase` por feature — sempre singleton
  via DI (`@Single` em Koin Annotations, ou factory iOS/Web).

### O que registrar no tech-spec

Cada feature que usa Room declara explicitamente na seção
"Local Persistence — Room":

- Lista de Entities novas/alteradas e campos (`name → type → nullable`).
- DAO queries (signature + retorno: `Flow<List<X>>` vs `suspend fun`).
- `@Database.version` resultante + migration strategy
  (`@AutoMigration` simples ou manual com diff descrito).
- Estratégia de cache/invalidação (write-through, stale-while-revalidate)
  quando Room pareia com `persistence-server`.
- Threading: dispatcher injetado, escopo (`viewModelScope`,
  `applicationScope`).
