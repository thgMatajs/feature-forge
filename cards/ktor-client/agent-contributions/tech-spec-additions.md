<!-- Injected into: tech-spec-agent
     Extension point: section:Data layer
     Source card: ktor-client v1.0.0
-->

## HTTP client conventions (card `ktor-client`)

Toda chamada HTTP cross-platform passa pelo `HttpClient` do Ktor, instanciado
**uma única vez** por feature (ou por escopo de DI). Quando o tech-spec
prescreve um endpoint REST/GraphQL/WebSocket-HTTP, derive a configuração e o
mapping de erros das regras abaixo — se a feature pede algo que viola, marque
**3-caminhos failure** em `open-questions.yaml` em vez de improvisar.

### Configuração canônica do `HttpClient`

Instância única, injetada via DI, configurada com os plugins mínimos:

```kotlin
HttpClient(engine) {
    install(ContentNegotiation) {
        json(canonicalJson)     // instância única do Json {} (card kotlinx-serialization-json)
    }
    install(Logging) {
        level = LogLevel.HEADERS
        logger = KtorAppLogger    // delegado para Logger expect/actual
    }
    install(HttpTimeout) {
        requestTimeoutMillis = 30_000
        connectTimeoutMillis = 10_000
        socketTimeoutMillis  = 30_000
    }
    install(Auth) {
        bearer {
            loadTokens { tokenStore.current()?.toBearerTokens() }
            refreshTokens { tokenRefresher.refresh()?.toBearerTokens() }
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
    expectSuccess = false        // tratamos status manualmente no mapper
}
```

Divergências (timeouts diferentes, retry desligado, `expectSuccess=true`)
devem ser justificadas explicitamente no tech-spec.

### Engine por plataforma (expect/actual factory)

- **Android**: `OkHttp` — interop com Interceptors existentes do projeto.
- **iOS**: `Darwin` — usa `NSURLSession`, integra com background tasks.
- **Web**: `Js` — usa `fetch` no browser.
- **JVM (testes)**: `MockEngine` — nunca rodar engine real em unit test.

Factory `HttpClientFactory` em `data/.../network/` retorna o `HttpClient`
configurado; o `engine` vem de `expect/actual fun provideHttpClientEngine()`
em `shared:core/network/`.

### Dispatcher injection (não hardcode `Dispatchers.IO`)

`Service`/`Repository` que consome o `HttpClient` recebe `CoroutineDispatcher`
no construtor (default `Dispatchers.IO`). Chamadas HTTP rodam dentro de
`withContext(ioDispatcher) { httpClient.get(...) }` — necessário para
testabilidade com `UnconfinedTestDispatcher` e para evitar surpresa de
thread (Ktor não muda dispatcher por conta própria).

```kotlin
class BonsaiService(
    private val httpClient: HttpClient,
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO,
) {
    suspend fun fetch(id: String): BonsaiResponse =
        withContext(ioDispatcher) {
            httpClient.get("bonsais/$id").body()
        }
}
```

### Error mapping (status HTTP → domain error)

`HttpResponse.status` é mapeado para sealed `NetworkError` em
`shared:core/error/`. Repositories nunca propagam `ResponseException` cru
para `domain/`:

| Status | Domain error |
|---|---|
| 2xx | success — body → DTO → domain |
| 400 | `NetworkError.BadRequest(code, message)` |
| 401 | `NetworkError.Unauthorized` (Auth plugin tenta refresh antes) |
| 403 | `NetworkError.Forbidden` |
| 404 | `NetworkError.NotFound` |
| 409 | `NetworkError.Conflict(code)` |
| 422 | `NetworkError.ValidationFailed(fieldErrors)` |
| 5xx | `NetworkError.ServerError(code)` — elegível a retry |
| timeout/IO | `NetworkError.ConnectionLost` |
| `SerializationException` | `NetworkError.Malformed` |

### Anti-patterns críticos (bloquear no tech-spec)

- `Retrofit` / `OkHttp` direto no `commonMain` — não compila KMP; usar Ktor.
- Parsing manual de JSON (`response.bodyAsText()` + `Json.decodeFromString`)
  quando `ContentNegotiation` já está instalado — duplica responsabilidade.
- `runBlocking { httpClient.get(...) }` em qualquer lugar — bloqueia Main
  thread (capturado pelo validator `check-no-blocking-http`).
- Múltiplos `HttpClient {}` por feature — uma instância por escopo de DI.
- Hardcode de `baseUrl` em Service — vem de `workflow-config` ou env.
- Auth tokens em header manual em vez do `Auth` plugin — perde refresh
  automático e race-conditions resolvidas pelo plugin.
- `expectSuccess = true` sem tratamento explícito de `ResponseException` —
  mapper de erro pula casos não-2xx.
- Engine hardcoded (`HttpClient(OkHttp)`) no `commonMain` — usa expect/actual.

### Quando registrar no tech-spec (section 7.2 REST/GraphQL)

Cada feature que toca rede declara explicitamente:

- Endpoints consumidos (`{verb} {path}`) → DTO entrada/saída.
- Plugins extras além dos canônicos (ex.: `HttpCache`).
- Estratégia de retry desviando do default (ex.: idempotency-only).
- Mapping específico de status para domain error quando a tabela canônica
  não cobre (ex.: 423 Locked tem semântica de feature).
- Auth scope (público vs autenticado) — `sendWithoutRequest` lista hosts.
