# Card `room-database`

> Categoria: `persistence` · Maturidade: `stable` · Requires: `[kotlin, kotlin-multiplatform]`

Room é a escolha **canônica v1** do feature-forge para persistência local
em projetos KMP. A partir de **Room 2.7+**, `@Entity`, `@Dao` e a classe
abstrata `RoomDatabase` ficam declarados em `commonMain` do shared
module — o suporte oficial a Kotlin Multiplatform passou a `stable`. Só a
construção do `RoomDatabase.Builder` permanece platform-specific (Android
recebe o `Context`; iOS usa `BundledSQLiteDriver()` + path absoluto).

Provê a capability singular `persistence-local` (ver
`docs/schemas/capability-labels.md §Persistence`). **Não há provedor
alternativo em v1**: `sqldelight` não entrou no catálogo v1. Esta é a
recomendação oficial até v1.1.

---

## O que este card declara

| Item | Valor |
|---|---|
| `provides` | `persistence-local` |
| `requires` | `kotlin`, `kotlin-multiplatform` |
| `conflicts-with` | `persistence-local` (singular — só um provedor por projeto) |
| `config-defaults` | `conventions.persistence.local: "room"`, `conventions.persistence.flow-queries: "Flow<List<Entity>>"`, `conventions.persistence.migrations: "AutoMigration"` |
| Detecção (threshold 0.5) | `build.gradle*` contém `androidx.room` (0.5) + `*.kt` contém `@Entity` (0.3) + `@Database` (0.3) + `@Dao` (0.3) + `RoomDatabase` (0.2) |

A capability `persistence-local` é singular — projetos não podem ativar
dois cards diferentes provendo a mesma label. Por isso `conflicts-with`
referencia a própria capability.

---

## Por que Room (e não SQLDelight) em v1

- **Estável em KMP** a partir do Room 2.7 (jun/2024) — Google é o
  responsável pelo suporte multiplataforma.
- **Anotações + KSP** geram código boilerplate previsível, alinhado com o
  resto do stack KMP do feature-forge (Koin Annotations, kotlinx.
  serialization).
- **Ecosistema maduro**: `androidx.paging` (Room-Paging), `Room.MigrationTestHelper`,
  `exportSchema` para diff em PR, `@AutoMigration` cobrindo maioria das
  mudanças de schema.
- **Decisão consciente**: SQLDelight ainda vai entrar em v1.1 como
  alternativa para projetos type-safe-SQL-first. Não há provedor
  concorrente em v1.

---

## Quando este card ativa

O `forge init` ativa automaticamente quando detecta:

1. `build.gradle*` referenciando `androidx.room` (0.5) — sinal mais
   forte.
2. Qualquer arquivo `.kt` com `@Entity` (0.3), `@Database` (0.3) ou
   `@Dao` (0.3).
3. `.kt` referenciando o tipo `RoomDatabase` (0.2) — captura projetos
   que importaram mas ainda não anotaram.

Em projetos com Room já configurado a soma cruza 0.5 trivialmente: a
dependência no Gradle (0.5) já cumpre sozinha; um único DAO somando
`@Entity + @Dao + @Database` adiciona +0.9 (total 1.4).

---

## O que este card contribui

### Templates

#### `tech-spec.md` → `section:Local Persistence — Room`

Arquivo: `templates/room-tech-spec.md`. Merge: `append-section`.

Bloco completo descrevendo:

- Estrutura de pastas canônica (`data/local/entity/`, `dao/`, `db/`,
  `db/migrations/`, `mapper/`).
- Naming canônico (`{Entity}Entity`, `{Feature}Dao`, `{Feature}DataBase`,
  `{Entity}LocalMapper`).
- Convenções de DAO (retorno `Flow<T>` para observabilidade, `suspend`
  para single-shot; `LiveData` proibido em commonMain).
- Configuração canônica do `@Database` (`version`, `entities`,
  `autoMigrations`, `exportSchema = true`).
- Estratégia de migrations (default `@AutoMigration`, manual quando
  necessário, `fallbackToDestructiveMigration()` proibido em produção).
- Threading (dispatcher injetado, `withContext(io)` no Repository,
  `Flow` coletado em `viewModelScope`).
- Anti-patterns bloqueantes no tech-spec.

#### `data-contract-spec.yaml` → `room-tables`

Arquivo: `templates/room-data-contract.yaml`. Merge: `merge-keys`.

Bloco YAML para declarar cada tabela tocada pela feature: schema (colunas
com tipo SQLite + nullable + primary-key + indexed), índices compostos,
foreign-keys intra-DB, DAO queries (signature + sql + bdd-ref),
operações CRUD com actor + bdd-ref, histórico de migrations,
estratégia de sincronização quando pareado com `persistence-server`.

### Agent prompts

#### 1. `tech-spec-agent` → `section:Shared (KMP) layer`

Arquivo: `agent-contributions/tech-spec-additions.md`.

Injeta regras KMP de Room na seção shared do tech-spec — convenções,
threading, migrations, pareamento com server, anti-patterns. Quando o
tech-spec prescreve algo que viola regra, o agent registra como
**3-caminhos failure** em `open-questions.yaml`.

#### 2. `contract-planner-agent` → `section:Data Contract`

Arquivo: `agent-contributions/contract-planner-additions.md`.

Orienta o planner sobre como popular `room-tables` no
`data-contract-spec.yaml`: cobertura exaustiva de tabelas, índices
compostos para queries com `WHERE + ORDER BY`, migrations versionadas,
pareamento server (`sync-strategy`), foreign-keys só intra-DB.

#### 3. `task-contract-writer` → `after:Allowed Files`

Arquivo: `agent-contributions/task-writer-additions.md`.

Orienta o writer sobre `allowed_files` (globs Room: `*Entity.kt`,
`*Dao.kt`, `*DataBase.kt`, migrations, mappers, schemas exportados),
exclusões obrigatórias (`build/`, `generated/`, Entity fora de
commonMain), validações canônicas (detekt + ktlint + compile +
`kspCommonMainKotlinMetadata` + `room-migration-test`), gates por tipo
de mudança e anti-patterns para sinalizar.

### Validators

#### `check-room-migrations` (stub Phase 5)

Arquivo: `validators/check-room-migrations.py`. Runs-on: `[verify-task]`.
Severity: `error`.

Objetivo: falhar quando o schema de uma `@Entity` mudou (campo
novo/removido/renomeado, tipo alterado, índice modificado) sem migration
declarada (`@AutoMigration` na `@Database` ou Migration manual em
`db/migrations/` registrada com `.addMigrations(...)`). Compara snapshot
atual da Entity contra `schemas/<DB>/<version>.json` exportado pelo Room
e cross-check com `data-contract-spec.yaml` `room-tables[*].migrations.history`.

Stub atual: `# TODO Phase 5` — retorna 0 (sucesso). Implementação real
prevista para Phase 5.

### Config defaults

```yaml
conventions.persistence.local:        "room"
conventions.persistence.flow-queries: "Flow<List<Entity>>"
conventions.persistence.migrations:   "AutoMigration"
```

Aplicados ao `workflow-config.yaml` quando nada mais sobrescreve.

---

## O que este card NÃO contribui

Deliberadamente fora do escopo:

- **Hooks** — sem automação pós-edit.
- **SDD/Plug-and-play de SQLDelight** — fora do v1, será card próprio em
  v1.1 com `conflicts-with: persistence-local`.
- **Field-level encryption / SQLCipher** — quando dados sensíveis exigem
  cifragem, fica em card de quality-gate dedicado (futuro). Este card
  apenas sinaliza no contract-planner que a feature precisa decidir
  (não-persistir vs cifrar).
- **Sincronização com `persistence-server`** — o card declara o **slot**
  `sync-strategy` no `data-contract-spec.yaml`, mas a estratégia
  concreta (write-through vs offline-first) é decidida no tech-spec
  pareando este card com `firestore-persistence` / `firestore-realtime`.
- **Templates de Repository** — formato de Repository é Kotlin
  idiomático coberto por `kotlin-language`; este card prescreve apenas
  como o DAO é consumido.

---

## Referência viva (MeoBonsai)

Este card destila convenções do projeto-fixture
`~/Documents/MeoBonsai/` mais a documentação oficial Room 2.7+ KMP.
Quando o MeoBonsai migrar features para Room (atualmente Firestore-only),
exemplos canônicos virão de `shared/feature/*/data/local/`.

Exemplo curto:

```kotlin
@Entity(
    tableName = "bonsai",
    indices = [Index(value = ["owner_uid", "created_at"])],
)
data class BonsaiEntity(
    @PrimaryKey val id: String,
    @ColumnInfo(name = "owner_uid") val ownerUid: String,
    val name: String,
    @ColumnInfo(name = "created_at") val createdAt: Long,
)

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

@Database(
    version = 1,
    entities = [BonsaiEntity::class],
    exportSchema = true,
)
abstract class BonsaiDataBase : RoomDatabase() {
    abstract fun bonsaiDao(): BonsaiDao
}
```

Mapper (Entity → Domain):

```kotlin
class BonsaiLocalMapper {
    fun toDomain(entity: BonsaiEntity): Bonsai = Bonsai(
        id = entity.id,
        ownerUid = entity.ownerUid,
        name = entity.name,
        createdAt = Instant.fromEpochMilliseconds(entity.createdAt),
    )

    fun toEntity(domain: Bonsai): BonsaiEntity = BonsaiEntity(
        id = domain.id,
        ownerUid = domain.ownerUid,
        name = domain.name,
        createdAt = domain.createdAt.toEpochMilliseconds(),
    )
}
```

---

## Lifecycle

- **Install** (via `forge init` ou menu "adicionar card" no
  `forge reconfigure`): copia este diretório para
  `.claude/cards/room-database/`, registra sha256 em
  `workflow-config.yaml`.
- **Update**: recopia do canonical, mostra diff, requer aceite.
- **Remove**: bloqueado se algum card ativo ainda requer
  `persistence-local`. Sem dependentes diretos em v1 — pode ser removido
  livremente quando a feature não precisa de cache local.

---

## Versionamento

`1.0.0` — primeira versão estável, alinhada com Room 2.7+ KMP, catálogo
`capability-labels.md` v1 (`persistence-local` singular), regras do
projeto-fixture MeoBonsai (`architecture_kmp.md §Nomenclatura`,
`kotlin-idioms.md §Dispatchers e Main Thread`).
