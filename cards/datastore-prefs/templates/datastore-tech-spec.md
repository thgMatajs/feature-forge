<!--
  Fragmento contribuído por: datastore-prefs
  Target: tech-spec.md
  Section: Local Prefs — DataStore
  Merge: append-section
  Extension-point anchor: <!-- extension-point: section:Local Prefs — DataStore -->
-->

### Local Prefs — DataStore

Esta seção é obrigatória sempre que a feature persiste **estado pequeno
chave-valor**: user settings (idioma, tema), feature flags por usuário,
last-screen-shown, onboarding-completed, último filtro aplicado, número
de execução para gating de tooltip, fragmentos leves de sessão.

Esta seção **não** cobre:

- **Entidades estruturadas** (`Bonsai`, `Task`, `Note` com múltiplos
  campos e queries) → ver subseção do card `room-database`
  (`persistence-local`). DataStore e Room coexistem por design.
- **Cache de query / lista paginada** → Room (com `Flow<List<Entity>>`
  observável e índices SQL).
- **Dados sensíveis / tokens de auth** → ver card de auth ativo
  (`firebase-auth` ou `auth-jwt-bearer`); credenciais não vão em
  Preferences plain.
- **Blobs binários (imagens, arquivos)** → ver card `firebase-storage`
  (server) ou storage local dedicado.

Se a feature não persiste KV small, marque "Não aplicável".

#### 1. Escopo — o que vai em Preferences

Critérios cumulativos para um valor ir em DataStore Preferences:

- Tipo primitivo Kotlin suportado: `Boolean`, `Int`, `Long`, `Float`,
  `Double`, `String`, `Set<String>`.
- Tamanho total da chave: bytes, não kilobytes (≤ 4 KB por valor é o
  guideline — ultrapassou, é Room).
- Sem estrutura relacional: leitura é "dame esse valor", não "dame todos
  os X onde Y > Z".
- Sem necessidade de transação atômica entre múltiplos registros (uma
  feature pode ter múltiplas chaves coordenadas via Mutex no Service —
  ver §3).
- Não classificado como dado sensível segundo
  `docs/specs/data/security-and-threat-model.md` (DataStore Preferences
  **não** criptografa em disco — secrets vão para keystore/keychain).

Lista no tech-spec EXATAMENTE quais chaves a feature adiciona:

| Chave canônica | Tipo | Default | Motivo do default |
|---|---|---|---|
| `<feature>_<concept>` | `Boolean`/`Int`/... | valor inicial | justificativa breve |

#### 2. Naming convention

- Pacote: `data/.../preferences/` dentro do feature module shared.
- Arquivo de chaves: `{Feature}PreferenceKeys.kt` — `object` com `val`
  imutáveis tipadas via `booleanPreferencesKey(...)`/etc.
- Nome da chave (string raw): `{feature}_{concept}` em snake_case,
  lowercase. Ex.: `bonsai_onboarding_completed`,
  `tasks_last_filter_applied`, `auth_remember_me`.
- Service: `{Feature}PreferencesService` — interface no domain +
  `{Feature}PreferencesServiceImpl` em data.
- API pública do service expõe **domain types**, nunca `Preferences`
  cru, nunca `PreferencesKey<T>` vazando.

#### 3. API do `{Feature}PreferencesService`

- Reads reativas → `fun observe{Concept}(): Flow<Value>`, derivado de
  `dataStore.data.map { it[KEY] ?: DEFAULT }`. Sempre aplicar
  `.catch { emit(DEFAULT) }` para tolerar `IOException` em leitura
  corrompida (loggar com Crashlytics se card `firebase-crashlytics` ativo).
- Read pontual single-shot → `suspend fun get{Concept}(): Value`, com
  `dataStore.data.first()`.
- Write → `suspend fun set{Concept}(value: Value)`, com
  `dataStore.edit { it[KEY] = value }`.
- Update coordenado de múltiplas chaves → bloco `dataStore.edit { prefs -> ... }`
  único (a `edit` já é transacional). Para coordenar **escritas e
  validações** em fluxo complexo, usar `Mutex.withLock {}` no Service
  e justificar no spec.
- `CoroutineDispatcher` injetado no construtor (`Dispatchers.IO` em
  produção, `UnconfinedTestDispatcher` em testes) — passar para
  `withContext(io)` em operações que envolvem cálculo extra antes do
  `edit`. NUNCA hardcode `Dispatchers.IO` no corpo.

#### 4. DataStore instance — escopo e injeção

- **Uma instância por feature** quando a feature isola sua persistência
  KV (`{Feature}PreferencesService` provê internamente).
- **Instância única global** quando settings transversais (idioma, tema)
  — vive em `shared/core/storage/` ou equivalente do projeto e é
  injetada via DI (Koin `@Single` provider; iOS/Web: factory function
  `create{Concept}DataStore()`).
- Arquivo `.preferences_pb` no disco: nome derivado do nome da
  instância (`name = "{feature}_prefs"`). Listar no tech-spec o nome
  do arquivo gerado.
- `produceFile` deve apontar para `context.preferencesDataStoreFile(name)`
  (Android) ou path equivalente em iOS/Web — não hardcode caminhos
  absolutos.

#### 5. Migração de schema

- Renomear uma chave → migração `SharedPreferencesMigration` (se vindo
  do `SharedPreferences` legado) OU migração custom
  `DataMigration<Preferences>` registrada na factory do DataStore.
- Mudança de tipo (`Int` → `Long`) → migração custom obrigatória que lê
  a chave antiga, converte, escreve sob a chave nova, remove a antiga.
- Cada migração documenta no tech-spec: chave afetada, versão de
  origem, regra de conversão, fallback se conversão falhar.
- Migrações são idempotentes (executar 2x → mesmo estado final).

#### 6. Threading / Main thread

- `dataStore.data` (Flow) e `dataStore.edit { }` são `suspend` / Flow
  cold — não bloqueiam Main por si só, mas chamada explícita no
  Service envolve `withContext(io)` quando há trabalho adjacente
  (parse, validação).
- Update do `StateFlow` no ViewModel volta para Main (default de
  `viewModelScope`).
- NUNCA `runBlocking` em código de produção (ver `kotlin-idioms.md`).

#### 7. Mapeamento de erro

| Erro | Domain mapping |
|---|---|
| `IOException` na leitura (arquivo corrompido) | emitir `DEFAULT` + log Crashlytics (não bloqueia UI) |
| `IOException` na escrita | propagar como `DomainError.Storage` para o ViewModel — UI mostra snackbar + retry |
| Chave ausente | retornar `DEFAULT` (nunca null em API pública do Service) |

Service nunca expõe `IOException` para ViewModel/UseCase — sempre mapeia
para `DomainError`.

#### 8. Testabilidade

- Service usa `DataStore<Preferences>` injetado — em teste, instanciar
  `PreferenceDataStoreFactory.create` com `produceFile = { tempFile }`
  ou um fake `DataStore<Preferences>` que mantém map em memória.
- Cobrir 5 cenários canônicos (`testing.md`): happy path, default na
  primeira leitura, escrita seguida de leitura (round-trip), IO failure
  na leitura → DEFAULT, IO failure na escrita → `DomainError.Storage`.

#### 9. Coexistência com Room (`persistence-local`)

DataStore e Room **não** competem — papéis distintos. Spec deve
explicitar a decisão para cada peça de estado da feature:

| Estado | Storage |
|---|---|
| User settings (theme, locale) | DataStore (este card) |
| Feature flags por usuário | DataStore |
| Last-shown / onboarding flags | DataStore |
| Entidade `Bonsai`/`Task` (campos múltiplos, queries) | Room (`persistence-local`) |
| Lista paginada com filtros | Room |
| Cache de resposta de rede estruturado | Room |

Se um valor parece ficar em fronteira ("é settings ou é entidade?"),
decidir pelo critério "preciso consultar como query?" — se sim, Room.

#### 10. Cross-feature reusability candidates

Helpers de DataStore promovidos para `shared/core/storage/` (ou pacote
canônico equivalente): adapters para tipos derivados (enum string-coded,
serialized JSON via `kotlinx-serialization-json`), Mutex helpers para
coordenação multi-chave. Promoção segue rule-of-three (ver
`mobile-engineering.md`) — só promove na 3ª ocorrência (exceto
SP-022 eager-extract).

<!-- /datastore-prefs — Local Prefs — DataStore -->
