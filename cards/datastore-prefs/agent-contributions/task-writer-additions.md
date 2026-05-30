<!-- Injected into: task-contract-writer
     Extension point: after:Allowed Files
     Source card: datastore-prefs v1.0.0
-->

## DataStore Preferences file patterns (card `datastore-prefs`)

Quando uma TASK toca persistência KV small (adicionar chave nova,
adicionar `{Feature}PreferencesService`, migrar SharedPreferences →
DataStore), use os padrões canônicos abaixo para `allowed_files` e
`validations`. Não invente caminhos: derive de
`inventory.conventions.folder-layout` + os padrões abaixo.

### `allowed_files` — globs canônicos

Preferences vivem em `data/.../preferences/` no shared layer:

- Chaves tipadas: `shared/**/src/commonMain/kotlin/**/preferences/*PreferenceKeys.kt`
- Service interface (domain): `shared/**/src/commonMain/kotlin/**/domain/**/PreferencesService.kt`
- Service impl (data): `shared/**/src/commonMain/kotlin/**/preferences/*PreferencesService*.kt`
- Glob mais genérico (cobre ambos): `shared/**/src/commonMain/kotlin/**/preferences/*.kt`
- Pacote DI factory (config global do DataStore quando aplicável):
  `shared/**/src/commonMain/kotlin/**/di/*Module.kt` ou
  `shared/**/src/commonMain/kotlin/**/storage/DataStore*.kt`
- Migrações: `shared/**/src/commonMain/kotlin/**/preferences/migration/*.kt`

**Sempre excluir** das `allowed_files`:

- `**/build/**` (gerado pelo compiler)
- `**/generated/**` (Koin Annotations, etc.)
- Preferences em `androidMain/` ou `iosMain/` — chaves canônicas moram
  em `commonMain/`. Aparição em sourceSet específico exige
  justificativa no tech-spec.
- `**/test/**`, `**/commonTest/**` fora do glob desta TASK (testes vão
  em allowed_files separados quando a TASK é de teste).

### `validations` — comandos canônicos

Cada TASK que cria/modifica chave OU Service declara:

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
```

TASK que adiciona/altera chave OU adiciona migração declara também:

```yaml
  - name: preferences-roundtrip-test
    command: "./gradlew :shared:<module>:testAndroidHostTest --tests '*PreferencesServiceTest'"
    on-failure: block
```

> Roundtrip mínimo: escreve chave → lê chave → valor igual ao escrito.
> Cobrir também: leitura sem write prévio → retorna DEFAULT;
> IOException na leitura → emite DEFAULT (com fake DataStore que lança).

### `gates`

- TASK criando chave nova → gate `lint-and-format` (detekt + ktlint).
- TASK criando `{Feature}PreferencesService` novo → gate
  `preferences-roundtrip-test` cobrindo os 5 cenários canônicos
  (`testing.md`).
- TASK adicionando migração (`DataMigration<Preferences>`) → gate
  `preferences-roundtrip-test` cobrindo: estado pré-migração → estado
  pós-migração; migração idempotente (rodar 2x = mesmo resultado);
  fallback se conversão falhar.
- TASK que renomeia chave OU muda tipo → migração obrigatória + gate
  `preferences-roundtrip-test`.

### Anti-patterns a sinalizar no `task-breakdown.yaml`

- TASK persistindo entidade estruturada (5+ campos serializados como
  JSON string em DataStore) → erro de spec; mover para card
  `room-database` (`persistence-local`).
- TASK persistindo token de auth / senha em DataStore Preferences plain
  → erro de spec; mover para keystore/keychain via card de auth.
- TASK com chave sem prefixo de feature (`onboarding_completed` em vez
  de `bonsai_onboarding_completed`) → erro de naming convention.
- TASK expondo `Flow<Preferences>` ou `PreferencesKey<T>` na API
  pública do Service → erro de arquitetura (domain não conhece
  DataStore).
- TASK com `runBlocking { dataStore.data.first() }` → erro
  (`kotlin-idioms.md` proíbe runBlocking em produção).
- TASK criando DataStore instance ad-hoc dentro de Repository/UseCase
  em vez de via DI → erro de spec.
- TASK declarando default da chave dentro do Service em vez do
  `{Feature}PreferenceKeys.kt` → fragmenta convenção.
- TASK renomeando chave SEM migração registrada → bloquear
  (usuários existentes perdem o valor).
- TASK que muda tipo de chave (`Int` → `Long`) sem migração custom →
  bloquear (leitura crasha em runtime).
