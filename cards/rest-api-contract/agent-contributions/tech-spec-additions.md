<!--
  Injetado em: tech-spec-agent
  Extension-point: section:Data layer
  Card: rest-api-contract

  Wave C do forge plan. Tech-spec-agent produz tech-spec.md. Quando este
  card está ativo, estas orientações são aplicadas à §Data layer (e à
  seção "REST API Contract" appendada via template).
-->

## rest-api-contract — orientações para `tech-spec.md > Data layer`

### 1. Centralização de endpoints em `ApiEndpoints.kt`

Todo path REST vive como `const` em `data/network/ApiEndpoints.kt`. UseCase,
Repository, ViewModel **nunca** referenciam path por string. Service
classes consomem `ApiEndpoints.<NAME>` direto.

Por quê:
- Bump de versão (`/api/v1` → `/api/v2`) muda 1 arquivo.
- Mock em testes vira override do `object` ou parâmetro de Service.
- Code review encontra todos os endpoints com `grep ApiEndpoints`.

### 2. Camada `data/network/` — estrutura canônica

```
data/network/
├── ApiEndpoints.kt                          # paths como const
├── dto/
│   ├── {Entity}Request.kt                   # body de POST/PUT/PATCH
│   ├── {Entity}Response.kt                  # corpo de 200/201
│   └── ErrorResponse.kt                     # envelope canônico
├── service/
│   ├── {Feature}Service.kt                  # interface
│   └── {Feature}ServiceImpl.kt              # consome HttpClient
└── mapper/
    ├── {Entity}Mapper.kt                    # DTO → domain
    └── {Feature}HttpMapper.kt               # HTTP status → DomainError
```

`{Feature}ServiceImpl` é a ÚNICA classe que importa `HttpClient` /
`io.ktor.client.*`. UseCases e Repositories consomem `{Feature}Service`
interface.

### 3. DTOs `@Serializable` — naming e fronteira

- Naming: `{Entity}Request`, `{Entity}Response` — terminam no sufixo HTTP.
- `internal data class` por padrão — DTOs não vazam para outros módulos.
- `@SerialName` quando JSON usa snake_case ou nome diferente do Kotlin.
- Tipos primitivos quando possível; `JsonElement` apenas em `details`
  do error envelope (genérico).
- **Proibido**: DTO em `domain/` ou `presentation/` — sempre mapeie.

### 4. Error envelope — uma classe, um mapper

`ErrorResponse` é canônica:

```kotlin
@Serializable
internal data class ErrorResponse(
    @SerialName("error") val error: ErrorBody,
) {
    @Serializable
    internal data class ErrorBody(
        @SerialName("code")    val code: String,
        @SerialName("message") val message: String,
        @SerialName("details") val details: JsonElement? = null,
    )
}
```

`{Feature}HttpMapper.kt` recebe `Throwable + ErrorResponse?` e retorna
`DomainError`. Domain layer **nunca** importa:
- `io.ktor.client.statement.*`
- `io.ktor.http.HttpStatusCode`
- `kotlinx.serialization.json.*`

### 5. Status → DomainError — tabela canônica

| HTTP | DomainError | Quando |
|---|---|---|
| 200/201/204 | (sucesso) | mapeie response para domain |
| 400 | `ValidationError(code)` | body/params inválidos |
| 401 | `Unauthorized` | token ausente/expirado → triggers refresh |
| 403 | `Forbidden` | token válido sem permissão |
| 404 | `NotFound` | recurso não existe |
| 409 | `Conflict(code)` | ex: `email_already_in_use` |
| 422 | `Unprocessable(code)` | semântica inválida |
| 429 | `RateLimited` | UI mostra retry timer |
| 500..599 | `ServerError` | log + retry com backoff |
| timeout / IOException | `NetworkUnavailable` | offline state |
| outro | `Unknown(code)` | log warning, não silenciar |

Cada `DomainError` é subclass de sealed class em
`domain/model/{Feature}DomainError.kt`.

### 6. Paginação cursor-based

Default canônico:

```kotlin
@Serializable
internal data class PageResponse<T>(
    @SerialName("items")       val items: List<T>,
    @SerialName("next_cursor") val nextCursor: String?,
)
```

Repository expõe:

```kotlin
suspend fun loadPage(cursor: String?, limit: Int = 50): Page<DomainEntity>
```

Ou `Flow<PagingData<DomainEntity>>` quando Paging 3 (ou
`androidx.paging:paging-common`) está ativo. Offset-based **só** quando
backend não suporta cursor — justificar em §1 da tech-spec.

### 7. Idempotência

- GET / PUT / DELETE: idempotentes por contrato HTTP — auto-retry seguro.
- POST: NÃO idempotente por default. Auto-retry de POST exige
  `Idempotency-Key: <UUIDv4>` gerado no client e persistido no escopo
  do retry.
- PATCH: depende do endpoint; declare explícito no data-contract-spec.

`HttpClient` config:

```kotlin
HttpClient {
    install(HttpRequestRetry) {
        retryOnExceptionIf(maxRetries = 3) { _, cause ->
            cause is IOException
        }
        retryIf(maxRetries = 3) { _, response ->
            response.status.value in 500..599
        }
        // POST com retry SÓ se header Idempotency-Key presente
    }
}
```

### 8. Timeouts e cancelamento

- Default request timeout: 15s (config global no `HttpClient`).
- Endpoints longos (upload, batch) sobrescrevem via `timeout-ms` no
  data-contract-spec — Service classes lêem o valor declarado.
- Cancelamento: Service sempre roda em `withContext(io)` dentro do
  `viewModelScope` ou escopo do UseCase — cancelamento da coroutine
  cancela o request Ktor automaticamente.

### 9. DI por plataforma

| Plataforma | Padrão |
|---|---|
| Android (Koin Annotations) | `@Single {Feature}ServiceImpl` em pacote coberto por `@Module @ComponentScan` |
| iOS | `create{Feature}Service(): {Feature}Service` em `di/{Feature}Factory.kt` |
| Web | Mesmo padrão iOS — `create{Feature}Service()` consumido por hook `useViewModel(UseCase)` |

`HttpClient` é singleton compartilhado (provido pelo card `ktor-client`)
— Service classes recebem por injeção, nunca instanciam.

### 10. Observabilidade — request/response logging

- Logging plugin do Ktor com level `INFO` por default.
- **Filtrar sempre**: `Authorization` header, campos
  `sensitivity: user-private` declarados no data-contract-spec.
- Eventos analytics `*_attempt` / `*_success` / `*_error` com params
  `duration_ms`, `status_code`, `endpoint_id` (alinhar com card de
  analytics quando ativo).

### 11. Testes mínimos obrigatórios

| Classe | Cobertura mínima |
|---|---|
| `{Entity}MapperTest` | DTO completo + DTO com nullable fields default + DTO com lista vazia |
| `{Feature}HttpMapperTest` | Um caso por status declarado em `status-mapping:` (incluindo `Unknown(code)`) |
| `{Feature}ServiceTest` | 200 happy + 4xx com envelope canônico + 5xx + timeout (IOException) + cancelamento de coroutine |
| `{Feature}RepositoryImplTest` | Happy path + cada `DomainError` |

Use `MockEngine` do Ktor para `ServiceTest` — nunca rede real em unit
tests.

### 12. Coexistência com Firestore (projetos híbridos)

Quando feature usa REST + Firestore (cards `rest-api-contract` +
`firestore-persistence` ambos ativos):

- Cada Service vive na sua camada (`data/network/` vs `data/firestore/`).
- Repository pode combinar fontes (`{Feature}RepositoryImpl` chama dois
  Services) — desde que mapeie ambos para o mesmo domain model.
- `DomainError` é unificado: `NetworkUnavailable` cobre tanto IOException
  REST quanto offline Firestore.
