# Card `ktor-client`

> Categoria: `kmp` · Maturidade: `stable` · Requires: `[kotlin-multiplatform, serialization-json]`

`ktor-client` é o **HTTP client cross-platform canônico** para projetos KMP
do catálogo `feature-forge`. Provê a capability singular `http-client`
(ver `docs/schemas/capability-labels.md §Network`) e ancora as convenções
de configuração do `HttpClient` (ContentNegotiation/Json, Logging, Auth com
refresh-token, HttpTimeout, retry), do dispatcher injetado no construtor,
do mapping de status HTTP para domain errors (`NetworkError`), e da
proibição de clients HTTP alternativos (Retrofit, OkHttp direto) no
`commonMain`.

Este card é o provedor exclusivo de `http-client` em v1 — habilita
features que dependem de operações REST sem amarrar a UI a um SDK
específico de plataforma. Cards downstream consomem indiretamente
(`rest-api-contract` define o catálogo de endpoints; `firebase-auth` /
`auth-jwt-bearer` configuram o plugin de Auth bearer).

---

## O que este card declara

| Item | Valor |
|---|---|
| `provides` | `http-client` |
| `requires` | `kotlin-multiplatform`, `serialization-json` |
| `conflicts-with` | `http-client` (singular — só um provedor por projeto) |
| `config-defaults` | `conventions.network.http-client: "ktor-client"`, `conventions.network.engine-android: "okhttp"`, `conventions.network.engine-ios: "darwin"`, `conventions.network.json-config: "ContentNegotiation Json { ignoreUnknownKeys=true }"` |
| Detecção (threshold 0.5) | `build.gradle*` contém `io.ktor:ktor-client` (0.5) + `ktor-client-core` (0.3) + `*.kt` contém `HttpClient(` (0.3) + `io.ktor.client` (0.2) |

A capability `http-client` é singular (uma feature, um provedor), por isso
`conflicts-with` lista a própria capability — projetos não podem ativar
dois cards diferentes que ambos provejam `http-client` (ex.: hipotético
`okhttp-direct` ou `apollo-rest` futuro).

`requires: [serialization-json]` é estrutural: o plugin
`ContentNegotiation` do Ktor consome a instância única de `Json {}` exposta
pelo card `kotlinx-serialization-json`.

---

## Quando este card ativa

O `forge init` ativa automaticamente quando detecta:

1. `build.gradle*` referenciando explicitamente `io.ktor:ktor-client`
   (confidence 0.5) — sinal mais forte, captura módulo do core.
2. `build.gradle*` com `ktor-client-core` (0.3) — captura projetos
   declarando dependências via aliases.
3. Qualquer `.kt` instanciando `HttpClient(` (0.3) — confirma uso real.
4. Qualquer `.kt` com import `io.ktor.client` (0.2) — sinal fraco mas
   complementar.

Em projetos KMP que adotaram Ktor a soma cruza 0.5 facilmente — basta a
dependency Gradle (0.5) ou a dependency + import (0.7).

---

## O que este card contribui

### 1. `tech-spec-agent` → `section:Data layer`

Arquivo: `agent-contributions/tech-spec-additions.md`.

Injeta na seção do data layer do `tech-spec.md` as regras do HTTP client:

- Configuração canônica do `HttpClient` (ContentNegotiation + Json único,
  Logging, HttpTimeout, Auth bearer com refresh, HttpRequestRetry,
  defaultRequest, `expectSuccess=false`).
- Engine por plataforma via expect/actual: OkHttp (Android), Darwin (iOS),
  Js (Web), MockEngine (testes).
- Dispatcher injection no construtor — `withContext(ioDispatcher)` envolve
  cada chamada, nunca hardcode `Dispatchers.IO`.
- Tabela canônica de error mapping (status HTTP → `NetworkError`).
- Anti-patterns (Retrofit/OkHttp direto no commonMain, parsing manual,
  `runBlocking`, múltiplos `HttpClient {}`, hardcode de baseUrl/engine,
  tokens manuais em vez do Auth plugin).
- Quando registrar explicitamente no tech-spec.

### 2. `contract-planner-agent` → `section:data-contract`

Arquivo: `agent-contributions/contract-planner-additions.md`.

Orienta o planner a:

- NÃO documentar `firestore_collections:` quando só `ktor-client` é
  provedor REST (separar quando coexistir com cards Firestore).
- Documentar `rest_endpoints:` com schema canônico (method, path, auth,
  request_dto, response_dto, success_status, error_mapping, idempotent).
- Mapear cada user story que toca rede para 1+ endpoint.
- Marcar entidades com `source: rest`.
- Tratar `public_endpoints:` (login, signup, reset) — configuram o
  `sendWithoutRequest` do Auth plugin.
- Não declarar `indexes:` / `query_catalog:` para REST puro.

### 3. `task-contract-writer` → `after:Allowed Files`

Arquivo: `agent-contributions/task-writer-additions.md`.

Orienta o writer sobre:

- Globs canônicos de `allowed_files` para HttpClient factories
  (`**/network/HttpClientFactory*.kt`), engines expect/actual
  (`**/network/HttpEngine*.kt`), Services
  (`**/service/*Service.kt`), Auth/Token plugins, error mappers,
  integration tests com MockEngine.
- Exclusões obrigatórias (`**/build/**`, `**/generated/**`, Service em
  sourceSets específicos sem justificativa).
- Validações canônicas (`detekt`, `ktlintCheck`, `compileKotlinMetadata`,
  `integration-test-mock-engine`, `check-no-blocking-http`).
- Gates por tipo de mudança (criação de Service → lint + integration;
  alteração de plugins → integration + no-blocking; engine novo →
  compile-android + compile-ios paralelos).
- Anti-patterns para sinalizar (Retrofit/OkHttp direto, `runBlocking`,
  `HttpClient {}` ad-hoc, dispatcher hardcoded, Service em domain/UI).

### 4. Template — `tech-spec.md` section `Network — Ktor Client`

Arquivo: `templates/ktor-client-tech-spec.md`.

Inserido com merge mode `append-section` ao fim do `tech-spec.md` da
feature. Contém tabela de plugins instalados, tabela de engines por
plataforma, estrutura canônica de Service com dispatcher injection,
slots de endpoints da feature, tabela de error mapping, e resumo de test
plan obrigatório para code de rede.

### 5. Validator — `check-no-blocking-http`

Arquivo: `validators/check-no-blocking-http.py` (stub — Phase 5 pendente).

`runs-on: [pre-commit, verify-task]` · `severity: error`. Detecta
`runBlocking { ... }` envolvendo chamadas `HttpClient` em código de
produção (exclui testes). Bloqueia Main thread freeze.

### 6. Config defaults

```yaml
conventions.network.http-client:    "ktor-client"
conventions.network.engine-android: "okhttp"
conventions.network.engine-ios:     "darwin"
conventions.network.json-config:    "ContentNegotiation Json { ignoreUnknownKeys=true }"
```

Conflitos de default (outro card provendo `http-client`) viram erro de
install.

---

## O que este card NÃO contribui

Deliberadamente fora do escopo:

- **Catálogo de endpoints REST** — fica em `rest-api-contract` (a ser
  adicionado quando refactor 3.5 promover).
- **Templates de DTOs Request/Response** — Kotlin idiomático coberto por
  `kotlinx-serialization-json`.
- **Auth flow completo** — `firebase-auth` ou `auth-jwt-bearer` definem
  `loadTokens`/`refreshTokens`; este card só prescreve que o plugin Auth
  está instalado.
- **Cache de respostas** — `room-database` ou `datastore-prefs` quando
  cache persistente; HttpCache plugin opcional documentado em tech-spec.
- **WebSocket / SSE** — fora do escopo de `http-client`; reservado para
  `websocket-realtime` / `sse-realtime` v1.1+.
- **GraphQL** — reservado para `graphql-client` v1.1+.

---

## Exemplo canônico — `HttpClientFactory`

```kotlin
// shared/core/network/HttpClientFactory.kt (commonMain)

class HttpClientFactory(
    private val engineProvider: () -> HttpClientEngine,
    private val json: Json,
    private val tokenStore: TokenStore,
    private val tokenRefresher: TokenRefresher,
    private val baseUrl: String,
) {
    fun create(): HttpClient = HttpClient(engineProvider()) {
        install(ContentNegotiation) {
            json(json)
        }
        install(Logging) {
            level = LogLevel.HEADERS
            logger = KtorAppLogger
        }
        install(HttpTimeout) {
            requestTimeoutMillis = 30_000
            connectTimeoutMillis = 10_000
            socketTimeoutMillis  = 30_000
        }
        install(Auth) {
            bearer {
                loadTokens {
                    tokenStore.current()?.let { BearerTokens(it.access, it.refresh) }
                }
                refreshTokens {
                    tokenRefresher.refresh()?.let { BearerTokens(it.access, it.refresh) }
                }
                sendWithoutRequest { request -> request.url.host in publicHosts }
            }
        }
        install(HttpRequestRetry) {
            retryOnExceptionOrServerErrors(maxRetries = 3)
            exponentialDelay()
        }
        defaultRequest {
            url(baseUrl)
            header(HttpHeaders.Accept, ContentType.Application.Json.toString())
        }
        expectSuccess = false
    }

    companion object {
        private val publicHosts = setOf("auth.bonsai-meo.app")
    }
}
```

```kotlin
// shared/core/network/HttpEngine.kt (commonMain)
expect fun provideHttpClientEngine(): HttpClientEngine

// shared/core/network/HttpEngine.android.kt
actual fun provideHttpClientEngine(): HttpClientEngine = OkHttp.create()

// shared/core/network/HttpEngine.ios.kt
actual fun provideHttpClientEngine(): HttpClientEngine = Darwin.create()
```

```kotlin
// shared/feature/bonsai/data/service/BonsaiService.kt
class BonsaiService(
    private val httpClient: HttpClient,
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO,
) {
    suspend fun fetch(id: String): BonsaiResponse =
        withContext(ioDispatcher) {
            httpClient.get("v1/bonsais/$id").body()
        }
}
```

---

## Referência viva (MeoBonsai)

Este card foi destilado a partir do projeto-fixture `~/Documents/MeoBonsai/`
e dos cards REST canônicos do refactor Fase 3.5 (ver
`docs/schemas/capability-labels.md §Migração Fase 3 → Fase 3.5`). Em projetos
do mundo real, esperar:

- HttpClientFactory: `shared/core/.../network/HttpClientFactory.kt`
- Engines expect/actual: `shared/core/.../network/HttpEngine.{android,ios,js}.kt`
- Services REST: `shared/feature/*/data/service/*Service.kt`
- Error mapper: `shared/core/.../error/NetworkErrorMapper.kt`
- Regras compiladas: `.claude/rules/architecture_kmp.md §Camadas` (Service
  no `data/`) + `.claude/rules/kotlin-idioms.md §Dispatchers e Main Thread`
  (injeção de dispatcher, proibição de `runBlocking`).

---

## Lifecycle

- **Install** (via `forge init` ou menu "adicionar card" no
  `forge reconfigure`): copia este diretório para
  `.claude/cards/ktor-client/`, registra sha256 em `workflow-config.yaml`,
  instala validator no pipeline pre-commit/verify-task.
- **Update**: recopia do canonical, mostra diff (especial atenção a
  mudanças no `tech-spec-additions.md` e no validator stub → real), requer
  aceite.
- **Remove**: bloqueado se algum endpoint REST documentado em feature
  ativa depende de `http-client`. Forçar remoção exige migrar para outro
  provedor de `http-client` (não existe em v1).

---

## Versionamento

`1.0.0` — primeira versão estável, alinhada com `architecture_kmp.md`
(Service em `data/`, dispatcher injection, sem `runBlocking`) +
`kotlin-idioms.md` (Dispatchers / Main Thread) da fixture MeoBonsai
(mai/2026) e com o catálogo `capability-labels.md` v1 (label `http-client`
singular, provedor exclusivo `ktor-client`).
