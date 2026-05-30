<!-- Injected into: tech-spec-agent
     Extension point: section:Shared (KMP) layer
     Source card: datastore-prefs v1.0.0
-->

## DataStore Preferences strategy (card `datastore-prefs`)

Sempre que a feature persiste **estado pequeno chave-valor** (settings,
flags, last-shown, onboarding-completed, último filtro aplicado),
registre as decisões abaixo na seção "Shared (KMP) layer" do tech-spec
ANTES de escrever código. Se a decisão recomenda algo que viola uma das
regras canônicas abaixo, sinalize como **3-caminhos failure** em
`open-questions.yaml` em vez de inventar.

### Escopo — quando este card aplica

Cabe em DataStore Preferences:

- Valor é primitivo Kotlin: `Boolean`, `Int`, `Long`, `Float`, `Double`,
  `String`, `Set<String>`.
- Tamanho ≤ 4 KB por chave; conjunto da feature na ordem de KB, não MB.
- Acesso é "dame esse valor" — sem queries relacionais.
- Não classificado como dado sensível (Preferences **não** criptografa
  em disco; secrets vão para keystore/keychain).

**Não cabe** em DataStore Preferences (mover para outro card):

- Entidade estruturada (`Bonsai`, `Task` com múltiplos campos e queries)
  → `room-database` (`persistence-local`).
- Cache de query / lista paginada → Room.
- Token de auth, refresh token, credenciais → card de auth ativo
  (`firebase-auth` ou `auth-jwt-bearer`).
- Blob binário, imagem, arquivo grande → `firebase-storage` ou storage
  local dedicado.

DataStore e Room **coexistem por design** — uma feature pode ter ambos.
Spec deve explicitar qual estado vai onde.

### Regras canônicas

- **Estrutura obrigatória**: pacote `data/.../preferences/` no feature
  module shared, com `{Feature}PreferenceKeys.kt` (object com chaves
  tipadas) + `{Feature}PreferencesService` (interface domain +
  `{Feature}PreferencesServiceImpl` em data).
- **Naming de chave (string raw)**: `{feature}_{concept}` em snake_case,
  lowercase. Ex.: `bonsai_onboarding_completed`,
  `tasks_last_filter_applied`, `auth_remember_me`. NUNCA prefixo
  ad-hoc; sempre incluir o nome da feature.
- **Chaves tipadas**: `booleanPreferencesKey("...")`,
  `intPreferencesKey("...")`, etc. Reuso da mesma chave com tipo
  diferente é erro de spec (renomear + migrar).
- **API pública do Service**: expõe **domain types**, nunca
  `Preferences` cru, nunca `PreferencesKey<T>` vazando.
  - Read reativa → `fun observe{Concept}(): Flow<Value>` com
    `dataStore.data.map { it[KEY] ?: DEFAULT }.catch { emit(DEFAULT) }`.
  - Read pontual → `suspend fun get{Concept}(): Value` com
    `dataStore.data.first()`.
  - Write → `suspend fun set{Concept}(value: Value)` com
    `dataStore.edit { it[KEY] = value }`.
- **Default obrigatório** em toda leitura — API pública nunca retorna
  null. Default registrado no `{Feature}PreferenceKeys.kt` como
  `const val` adjacente à chave.
- **`CoroutineDispatcher` injetado** no construtor do Service
  (`Dispatchers.IO` em produção, `UnconfinedTestDispatcher` em testes).
  NUNCA hardcode `Dispatchers.IO` no corpo.
- **DataStore instance**: uma por feature OU única global para settings
  transversais. Nome do arquivo (`{feature}_prefs`) declarado no spec.
  Injeção via Koin `@Single` (Android/JVM) ou factory function
  (iOS/Web).
- **Migração**: rename/retype documentado no spec com
  `DataMigration<Preferences>` custom registrado na factory. Migração
  é idempotente.
- **Mapeamento de erro**: `IOException` na leitura → emite DEFAULT +
  Crashlytics (não bloqueia UI). `IOException` na escrita →
  `DomainError.Storage` para o ViewModel. Service NUNCA expõe
  `IOException`.

### Escopo do que vai vs não vai (decisão registrada no spec)

Toda feature que usa este card lista no tech-spec:

| Estado da feature | Storage | Chave (se DataStore) |
|---|---|---|
| `<concept>` | `DataStore` ou `Room` | `<feature>_<concept>` |

Critério rápido: "preciso consultar como query / relacionar com outras
linhas?" → se sim, Room. Se não, DataStore.

### Anti-patterns críticos (bloquear no tech-spec)

- Persistir `Bonsai` ou outra entidade com 5+ campos em Preferences
  (serializando para JSON string) → mover para Room. Exceção: settings
  com 2-3 campos triviais.
- Token de auth / senha em DataStore Preferences plain → mover para
  keystore/keychain (card de auth ativo).
- Chave sem prefixo de feature (`onboarding_completed` em vez de
  `bonsai_onboarding_completed`) → conflito potencial com outra
  feature que use mesmo nome conceitual.
- API do Service expondo `Flow<Preferences>` ou `PreferencesKey<T>` →
  domain layer não conhece DataStore. Service traduz.
- `runBlocking { dataStore.data.first() }` em qualquer lugar → bloqueia
  Main. Sempre `suspend` ou `Flow`.
- `Json.encodeToString(model)` salvo como `String` em DataStore para
  contornar limite de tipos → erro de spec; isso é Room (ou um campo
  serializado dentro de uma entidade Room).
- DataStore instance criada ad-hoc dentro de Repository/UseCase em vez
  de injetada → erro de spec.
- Default da chave declarado no Service (não em
  `{Feature}PreferenceKeys.kt`) → fragmenta convenção.

### Quando registrar no tech-spec

Cada feature que usa este card aparece na seção "Shared (KMP) layer"
com:

- Lista de chaves novas (`{feature}_{concept}` → tipo Kotlin → default →
  motivo do default).
- Nome do arquivo DataStore (`{feature}_prefs`) e seu escopo
  (feature-only ou global).
- Migrações necessárias (rename, retype, vinda de SharedPreferences
  legado).
- Decisão registrada do que vai em DataStore vs Room (quando a feature
  também usa Room).
