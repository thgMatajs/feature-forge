<!-- Contributed by card: ktor-client v1.0.0
     Target: tech-spec.md
     Section: "Network — Ktor Client"
     Merge mode: append-section
-->

## Network — Ktor Client

> Esta seção é contribuída pelo card `ktor-client` quando ativo. Substitui a
> seção 7.2 (REST/GraphQL) do template quando o provider de rede é Ktor.

### Cliente único por escopo

- Uma instância de `HttpClient` por escopo de DI (singleton ou activity-retained,
  conforme `conventions.di-pattern`).
- Factory canônica: `HttpClientFactory.create(engine, json, tokenStore)`.
- Não criar `HttpClient {}` dentro de Service/Repository/UseCase — sempre
  injetar.

### Plugins instalados (canônicos)

| Plugin | Configuração mínima | Por quê |
|---|---|---|
| `ContentNegotiation` | `json(canonicalJson)` | Serialização única via card `kotlinx-serialization-json` |
| `Logging` | `LogLevel.HEADERS`, delegado para `Logger` (expect/actual) | Debug sem vazar body em produção |
| `HttpTimeout` | request 30s, connect 10s, socket 30s | Timeout previsível por chamada |
| `Auth` (bearer) | `loadTokens` + `refreshTokens` + `sendWithoutRequest` | Refresh transparente, sem race-conditions |
| `HttpRequestRetry` | `retryOnExceptionOrServerErrors(maxRetries=3)`, `exponentialDelay()` | Resilience contra 5xx/IO transientes |
| `defaultRequest` | `baseUrl` + `Accept: application/json` | DRY de headers comuns |

`expectSuccess = false` — status non-2xx vira `HttpResponse` normal e cai no
error mapper, não em exceção do plugin.

### Engine por plataforma

| Target | Engine | Sourceset |
|---|---|---|
| Android | `OkHttp` | `androidMain` |
| iOS (arm64 + sim arm64 + sim x64) | `Darwin` | `iosMain` |
| Web | `Js` | `jsMain` |
| Unit test | `MockEngine` | `commonTest` |

Engine acessado via `expect fun provideHttpClientEngine(): HttpClientEngine`
em `shared:core/network/`.

### Dispatcher injection

```kotlin
class {{FeatureService}}(
    private val httpClient: HttpClient,
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO,
) {
    suspend fun {{operation}}({{params}}): {{ResponseDto}} =
        withContext(ioDispatcher) {
            httpClient.{{verb}}("{{path}}") {
                {{configure_request}}
            }.body()
        }
}
```

### Endpoints da feature

| Operação | Método | Path | Auth | Request DTO | Response DTO | Status esperado |
|---|---|---|---|---|---|---|
| {{op_1}} | {{verb_1}} | {{path_1}} | {{auth_1}} | {{req_1}} | {{res_1}} | {{ok_1}} |
| ... | | | | | | |

### Error mapping (status → `NetworkError`)

| Status / condição | Domain error | Notas |
|---|---|---|
| 2xx | success — body → DTO → domain | |
| 400 | `NetworkError.BadRequest` | |
| 401 | `NetworkError.Unauthorized` | Auth plugin já tentou refresh |
| 403 | `NetworkError.Forbidden` | |
| 404 | `NetworkError.NotFound` | |
| 409 | `NetworkError.Conflict` | |
| 422 | `NetworkError.ValidationFailed(fields)` | |
| 5xx | `NetworkError.ServerError` | Retry pelo plugin antes de chegar aqui |
| timeout/IO | `NetworkError.ConnectionLost` | |
| `SerializationException` | `NetworkError.Malformed` | |

### Test plan (resumo)

- Integration test contra `MockEngine` cobrindo happy path + 401 + 422 + 5xx.
- Test do `Auth` plugin (refresh transparente em 401).
- Test do `HttpRequestRetry` (5xx repete N vezes, sucesso na N+1).
- Test do error mapper (cada status mapeado).
