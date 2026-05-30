<!-- Injected into: task-contract-writer
     Extension point: after:Allowed Files
     Source card: ktor-client v1.0.0
-->

## HTTP networking file patterns (card `ktor-client`)

Quando uma TASK cria/modifica `HttpClient`, Service que faz HTTP, ou
integration test contra MockEngine, use os padrões canônicos abaixo para
`allowed_files` e `validations`. Derive de
`inventory.conventions.folder-layout` + os padrões a seguir.

### `allowed_files` — globs canônicos

Código Ktor vive em `data/.../network/` e `data/.../service/` do shared
layer:

- HttpClient factories: `shared/**/src/commonMain/kotlin/**/network/HttpClientFactory*.kt`
- Engine expect/actual: `shared/**/src/commonMain/kotlin/**/network/HttpEngine*.kt`
  (+ `androidMain`, `iosMain`, `jsMain` actuals)
- Services REST: `shared/**/src/commonMain/kotlin/**/service/*Service.kt`
- Auth/Token plugins: `shared/**/src/commonMain/kotlin/**/network/auth/*.kt`
- Logging adapter: `shared/**/src/commonMain/kotlin/**/network/KtorAppLogger*.kt`
- Error mapper: `shared/**/src/commonMain/kotlin/**/network/error/*Mapper*.kt`
- Integration tests (MockEngine): `shared/**/src/commonTest/kotlin/**/network/*Test.kt`

**Sempre excluir** das `allowed_files`:

- `**/build/**`, `**/generated/**` — artefatos do compiler plugin
- Service em `androidMain/`/`iosMain/` — services canônicos moram em
  `commonMain/`; aparição em sourceSet específico exige justificativa no
  tech-spec.
- Engine real (`Darwin`, `OkHttp`, `Js`) referenciado fora de actuals —
  bloqueia portabilidade KMP.

### `validations` — comandos canônicos

Cada TASK que cria/modifica configuração de `HttpClient` ou Service REST
declara:

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
  - name: integration-test-mock-engine
    command: "./gradlew :shared:<module>:testAndroidHostTest --tests '*NetworkTest'"
    on-failure: block
  - name: check-no-blocking-http
    command: "python3 .claude/cards/ktor-client/validators/check-no-blocking-http.py"
    on-failure: block
```

TASK que adiciona engine novo (Android/iOS/Web actual) adiciona:

```yaml
  - name: compile-android
    command: "./gradlew :shared:<module>:compileDebugKotlinAndroid"
    on-failure: block
  - name: compile-ios
    command: "./gradlew :shared:<module>:compileKotlinIosSimulatorArm64"
    on-failure: block
```

### `gates`

- TASK criando/alterando Service REST → gate `lint-and-format` +
  `integration-test-mock-engine` (cobrindo happy path + 401/422/5xx).
- TASK criando HttpClientFactory ou alterando plugins instalados → gate
  `integration-test-mock-engine` + `check-no-blocking-http`.
- TASK adicionando engine actual em sourceSet específico → gate
  `compile-android` + `compile-ios` (paridade obrigatória).
- TASK alterando error mapping → gate `integration-test-mock-engine`
  exigindo cobertura simétrica de todos os status mapeados.

### Anti-patterns a sinalizar no `task-breakdown.yaml`

- TASK adicionando dependency `retrofit`, `okhttp` direto, `apollo`, ou
  qualquer client HTTP além do Ktor ao `commonMain` → erro de spec
  (viola contrato KMP do card).
- TASK criando `HttpClient {}` ad-hoc dentro de Repository/UseCase em vez
  de consumir a instância injetada → erro de spec.
- TASK com `runBlocking { httpClient.get(...) }` em qualquer lugar →
  erro de spec (capturado pelo validator).
- TASK hardcoding `Dispatchers.IO` no corpo da função em vez de receber
  no construtor → erro de spec.
- TASK com Service em `domain/` ou `presentation/` → erro de spec
  (Service vive em `data/`).
- TASK que muda `expectSuccess = false` para `true` sem revisar todo o
  error mapper → bloquear.
- TASK adicionando endpoint sem `error_mapping:` declarado no
  `data-contract-spec.yaml` → bloquear.
