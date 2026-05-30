# Card `datastore-prefs`

> Categoria: `persistence` · Maturidade: `stable` · Requires: `[kotlin, kotlin-multiplatform]`

`datastore-prefs` é o card canônico para **storage chave-valor pequeno**
(KV small) em projetos KMP do catálogo `feature-forge`. Empacota
`androidx.datastore` no modo Preferences — KMP-stable a partir da versão
1.1 — e ancora as convenções de `{Feature}PreferenceKeys.kt`,
`{Feature}PreferencesService`, naming de chave (`{feature}_{concept}`),
reads reativas via `Flow`, migração explícita e mapeamento de erro de IO
para `DomainError`.

Provê a capability auxiliar `local-prefs-storage`
(ver `docs/schemas/capability-labels.md §Persistence`). Como é label
**auxiliar**, este card **não força exclusividade**: coexiste lado a
lado com `room-database` (`persistence-local`) — papéis distintos por
design.

---

## DataStore vs Room — papéis distintos, coexistem

Confusão comum: "se já temos Room, por que DataStore?". A resposta é o
escopo do estado.

| Pergunta | DataStore Preferences (este card) | Room (`room-database`) |
|---|---|---|
| Tipo do valor | primitivo Kotlin (`Boolean`/`Int`/`String`/...) | entidade com múltiplos campos |
| Tamanho | bytes a KB (guideline ≤ 4 KB por chave) | KB a MB (centenas de linhas) |
| Acesso | "dame esse valor" | "dame todos os X onde Y > Z" + joins |
| Estrutura | sem schema relacional | schema relacional + índices SQL |
| Observação reativa | `Flow<Value>` por chave | `Flow<List<Entity>>` por query |
| Caso de uso típico | settings (idioma, tema), feature flags, last-shown, onboarding completed, último filtro aplicado | entidades de domínio (`Bonsai`, `Task`, `Note`), cache de listas paginadas |

Cabe em DataStore:

- User settings (idioma, tema, notificações ligadas/desligadas)
- Feature flags por usuário (`bonsai_show_advanced_view = true`)
- Estado de onboarding (`auth_onboarding_completed = true`)
- Last-screen-shown (`tasks_last_filter_applied = "today"`)
- Contadores leves (`tooltip_shown_count = 3`)

**Não** cabe em DataStore (vai para Room):

- Entidade `Bonsai` com 12 campos e queries
- Cache da resposta de uma lista paginada
- Histórico de eventos (cresce indefinidamente)
- Qualquer estado que você precisa consultar com `WHERE` / `ORDER BY` / `JOIN`

E NÃO vai em **nenhum** dos dois (vai para card específico):

- Token de auth / senha → keystore/keychain via card de auth
  (`firebase-auth` ou `auth-jwt-bearer`)
- Imagem / vídeo / blob → `firebase-storage` (server) ou storage local
  dedicado

Uma feature pode usar **ambos** os cards simultaneamente. O tech-spec
deve listar explicitamente qual estado vai onde.

---

## O que este card declara

| Item | Valor |
|---|---|
| `provides` | `local-prefs-storage` (auxiliar) |
| `requires` | `kotlin`, `kotlin-multiplatform` |
| `conflicts-with` | (nenhum — label auxiliar, coexiste com `persistence-local`) |
| `config-defaults` | `conventions.persistence.prefs: "datastore-preferences"`, `conventions.persistence.prefs-scope: "small KV — feature settings, last-shown, flags"` |
| Detecção (threshold 0.5) | `build.gradle*` contém `androidx.datastore` (0.5) + `*.kt` contém `PreferencesKey` (0.3) + `*.kt` contém `datastore` (0.2) |

A capability `local-prefs-storage` é auxiliar — múltiplos cards podem
prover. Este card é o provedor canônico v1 (próximo candidato seria um
hipotético `multiplatform-settings` em v1.1, sem conflito automático).

---

## Quando este card ativa

O `forge init` ativa automaticamente quando detecta:

1. `build.gradle*` referenciando `androidx.datastore` (0.5) — sinal
   forte e suficiente por si só para cruzar o threshold de 0.5.
2. Qualquer arquivo `.kt` com `PreferencesKey` (0.3) — confirma uso
   real de chaves tipadas, não só dependency declarada e esquecida.
3. Qualquer arquivo `.kt` com `datastore` (0.2) — captura uso geral
   (factory, builder, etc.).

Projetos KMP que usam DataStore cruzam o threshold com a presença do
dependency no Gradle. Se o sinal cair na faixa 0.3-0.5 (ex.: só
referência genérica em `.kt` sem dependency declarada), o init
pergunta para o usuário em vez de ativar automaticamente.

---

## O que este card contribui

### 1. Template — `tech-spec.md` § "Local Prefs — DataStore"

Arquivo: `templates/datastore-tech-spec.md`.

Append-section no `tech-spec.md` com a checklist canônica para qualquer
feature que persiste KV small:

- Escopo — o que vai em Preferences (critérios cumulativos)
- Tabela de chaves novas (chave canônica → tipo → default → motivo)
- Naming convention (`{feature}_{concept}` snake_case)
- API do `{Feature}PreferencesService` (Flow reativa, suspend pontual,
  edit transacional)
- DataStore instance — escopo (feature-only vs global) e injeção
- Migração de schema (rename, retype, vinda de SharedPreferences)
- Threading / Main thread
- Mapeamento de erro (`IOException` → `DomainError.Storage`)
- Testabilidade (5 cenários canônicos)
- Coexistência com Room (tabela explícita do que vai onde)
- Cross-feature reusability candidates (helpers promovidos para
  `shared/core/storage/`)

### 2. Agent prompt — `tech-spec-agent` → `section:Shared (KMP) layer`

Arquivo: `agent-contributions/tech-spec-additions.md`.

Injeta no shared layer do tech-spec as regras de DataStore Preferences:

- Escopo: critérios para um valor caber em Preferences
- Estrutura: pacote `data/.../preferences/`,
  `{Feature}PreferenceKeys.kt`, `{Feature}PreferencesService`
- Naming: `{feature}_{concept}` snake_case lowercase
- API do Service (domain types, nunca `Preferences` cru)
- Defaults obrigatórios na leitura
- `CoroutineDispatcher` injetado
- DataStore instance (feature-only vs global, injeção via DI)
- Migração idempotente
- Mapeamento de erro IOException
- Anti-patterns (entidade estruturada serializada, token plain, chave
  sem prefixo, `runBlocking`)

### 3. Agent prompt — `task-contract-writer` → `after:Allowed Files`

Arquivo: `agent-contributions/task-writer-additions.md`.

Orienta o writer sobre:

- Globs canônicos de `allowed_files` (`**/preferences/*.kt`,
  `**/*PreferenceKeys.kt`, `**/*PreferencesService*.kt`, migrações)
- Exclusões obrigatórias (`**/build/**`, `**/generated/**`, Preferences
  em sourceSet específico)
- Validações canônicas (`detekt`, `ktlintCheck`,
  `compileKotlinMetadata`, `preferences-roundtrip-test` quando muda
  chave/migração)
- Gates por tipo de mudança (chave nova → lint; service novo →
  roundtrip; migração → roundtrip cobrindo idempotência)
- Anti-patterns para sinalizar no `task-breakdown.yaml` (entidade
  estruturada, token plain, chave sem prefixo, rename sem migração,
  retype sem migração)

---

## O que este card NÃO contribui

Deliberadamente fora do escopo:

- **Validators executáveis** — Preferences são contract simples, sem
  script grep dedicado. Validações canônicas via gradle (detekt,
  ktlint, testes de roundtrip).
- **Hooks** — sem automação pós-edit.
- **Persistência relacional** (entidades, queries) → fica em
  `room-database` (`persistence-local`).
- **Persistência server** → fica em `firestore-persistence`
  (`persistence-server`).
- **File storage** (blobs, imagens) → fica em `firebase-storage`
  (`file-storage`).
- **Secret storage** (tokens, senhas) → fica em card de auth ativo
  (keystore/keychain).
- **DataStore Proto** (proto-typed DataStore com schema definido em
  `.proto`) — fora do escopo v1; cabe em v1.1 se aparecer demanda real.
  Este card cobre apenas o modo Preferences (KV).

---

## Referência viva (MeoBonsai)

Este card foi destilado a partir do projeto-fixture
`~/Documents/MeoBonsai/`. Exemplos canônicos de KV small no fixture:

- Settings de tema/idioma (estado pequeno, primitivo).
- Flags de onboarding (`auth_onboarding_completed`,
  `bonsai_first_run_completed`).
- Last-screen-shown (último filtro aplicado em listas).

Exemplo curto da estrutura prescrita:

```kotlin
object BonsaiPreferenceKeys {
    val ONBOARDING_COMPLETED = booleanPreferencesKey("bonsai_onboarding_completed")
    const val ONBOARDING_COMPLETED_DEFAULT = false

    val LAST_FILTER_APPLIED = stringPreferencesKey("bonsai_last_filter_applied")
    const val LAST_FILTER_APPLIED_DEFAULT = "all"
}

interface BonsaiPreferencesService {
    fun observeOnboardingCompleted(): Flow<Boolean>
    suspend fun setOnboardingCompleted(value: Boolean)
    suspend fun getLastFilterApplied(): String
    suspend fun setLastFilterApplied(value: String)
}

class BonsaiPreferencesServiceImpl(
    private val dataStore: DataStore<Preferences>,
    private val io: CoroutineDispatcher,
) : BonsaiPreferencesService {
    override fun observeOnboardingCompleted(): Flow<Boolean> =
        dataStore.data
            .map { it[BonsaiPreferenceKeys.ONBOARDING_COMPLETED] ?: BonsaiPreferenceKeys.ONBOARDING_COMPLETED_DEFAULT }
            .catch { emit(BonsaiPreferenceKeys.ONBOARDING_COMPLETED_DEFAULT) }

    override suspend fun setOnboardingCompleted(value: Boolean) = withContext(io) {
        dataStore.edit { it[BonsaiPreferenceKeys.ONBOARDING_COMPLETED] = value }
        Unit
    }

    override suspend fun getLastFilterApplied(): String = withContext(io) {
        dataStore.data
            .map { it[BonsaiPreferenceKeys.LAST_FILTER_APPLIED] ?: BonsaiPreferenceKeys.LAST_FILTER_APPLIED_DEFAULT }
            .first()
    }

    override suspend fun setLastFilterApplied(value: String) = withContext(io) {
        dataStore.edit { it[BonsaiPreferenceKeys.LAST_FILTER_APPLIED] = value }
        Unit
    }
}
```

Regras compiladas em `.claude/rules/architecture_kmp.md §Pacotes em shared:core`
(pacote `storage/` para DataStore wrappers cross-feature) e
`.claude/rules/kotlin-idioms.md §Dispatchers e Main Thread` (Dispatcher
injetado, NUNCA hardcode).

---

## Lifecycle

- **Install** (via `forge init` ou menu "adicionar card" no
  `forge reconfigure`): copia este diretório para
  `.claude/cards/datastore-prefs/`, registra sha256 em
  `workflow-config.yaml`.
- **Update**: recopia do canonical, mostra diff, requer aceite.
- **Remove**: bloqueado se algum card ativo ainda requer
  `local-prefs-storage` (raro — label auxiliar).

---

## Versionamento

`1.0.0` — primeira versão estável, alinhada com
`architecture_kmp.md §Pacotes em shared:core (storage/)` da fixture
MeoBonsai (mai/2026) e com o catálogo `capability-labels.md` v1
(`local-prefs-storage` auxiliar, provider canônico v1).
