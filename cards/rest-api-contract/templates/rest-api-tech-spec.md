<!--
  Template contribuído por: rest-api-contract
  Target: tech-spec.md
  Section: "REST API Contract"
  Merge: append-section

  Inserido pelo tech-spec-agent quando o card está ativo. Documenta a
  estratégia REST canônica da feature: endpoints, DTOs, error mapping,
  paginação, idempotência.
-->

## REST API Contract

Esta seção formaliza o contrato REST da feature. É obrigatória quando o
card `rest-api-contract` está ativo. Convenções alinhadas com:

- `conventions.api.contract-style: "rest"`
- `conventions.api.endpoints-source: "ApiEndpoints.kt"`
- `conventions.api.error-envelope: { error: { code, message, details? } }`
- `conventions.api.pagination: "cursor-based"`

### 1. Endpoints — fonte única `ApiEndpoints.kt`

Todos os paths REST são `const` em
`data/network/ApiEndpoints.kt` (object). Service classes referenciam pelo
nome, nunca por string literal:

```kotlin
internal object ApiEndpoints {
    const val BONSAIS_LIST   = "/api/v1/bonsais"
    const val BONSAI_DETAIL  = "/api/v1/bonsais/{id}"
    const val BONSAI_CREATE  = "/api/v1/bonsais"
}
```

Por quê: bump de versão (`v1` → `v2`), prefix swap, ou mock em testes
muda 1 arquivo. Trocar provedor de API não vaza pra Service classes.

### 2. DTOs — `{Entity}Request.kt` / `{Entity}Response.kt`

Em `data/network/dto/`. Nomes terminam em `Request` (body de POST/PUT/PATCH)
ou `Response` (corpo de 200/201). `@Serializable` + `@SerialName` quando
JSON usa snake_case:

```kotlin
@Serializable
internal data class BonsaiResponse(
    @SerialName("id")          val id: String,
    @SerialName("owner_uid")   val ownerUid: String,
    @SerialName("created_at")  val createdAt: String,
    @SerialName("species")     val species: String,
)
```

DTOs **não** cruzam fronteira `data → domain`. Mappers em
`data/network/mapper/{Entity}Mapper.kt` convertem DTO → domain model.

### 3. Error envelope canônico

Toda resposta de erro do backend segue o envelope:

```json
{
  "error": {
    "code": "email_already_in_use",
    "message": "Email já está cadastrado",
    "details": { "field": "email" }
  }
}
```

DTO canônico em `data/network/dto/ErrorResponse.kt`:

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

### 4. Mapping HTTP status → Domain Error

Mapper canônico em `data/network/mapper/{Feature}HttpMapper.kt`. Domain
layer **nunca** importa `io.ktor.client.statement.*` ou
`HttpStatusCode`. Exemplo:

```kotlin
internal fun mapHttpException(t: Throwable, body: ErrorResponse?): DomainError {
    val status = (t as? ResponseException)?.response?.status?.value
    return when (status) {
        400  -> DomainError.ValidationError(body?.error?.code.orEmpty())
        401  -> DomainError.Unauthorized
        403  -> DomainError.Forbidden
        404  -> DomainError.NotFound
        409  -> DomainError.Conflict(body?.error?.code.orEmpty())
        429  -> DomainError.RateLimited
        in 500..599 -> DomainError.ServerError
        else -> DomainError.NetworkUnavailable
    }
}
```

Tabela obrigatória de status → domain code (`data-contract-spec.yaml`
declara em `status-mapping:` por endpoint). Códigos não mapeados caem em
`DomainError.Unknown` com `code` original — nunca silenciar.

### 5. Paginação cursor-based (default)

Endpoints que retornam coleções usam cursor:

```
GET /api/v1/bonsais?cursor=<opaque>&limit=50
→ { items: [...], next_cursor: "<opaque-ou-null>" }
```

Repository expõe `Flow<PagingData<T>>` (Paging 3 / Paging-multiplatform)
ou `suspend fun loadPage(cursor: String?): Page<T>` quando paging library
indisponível. Offset-based **só** quando backend não suporta cursor —
justificar em §1 do tech-spec.

### 6. Idempotência

| Método | Idempotência | Header obrigatório? |
|---|---|---|
| GET | Sim (sempre) | não |
| PUT | Sim (sempre) | não |
| DELETE | Sim (sempre) | não |
| POST | Não por default | `Idempotency-Key` quando `create` precisa retry-safe |
| PATCH | Depende — declarar explícito | `Idempotency-Key` quando aplicável |

Service classes que retentam POST (auto-retry em network failure)
**obrigatoriamente** enviam `Idempotency-Key: <UUIDv4>` gerado no client
e persistido enquanto o retry estiver vivo.

### 7. Service layer — IO boundary

`data/network/service/{Feature}Service.kt` é a única classe que importa
`HttpClient`. UseCase / Repository consomem Service via interface:

```kotlin
internal interface BonsaiService {
    suspend fun list(cursor: String?, limit: Int): Page<BonsaiResponse>
    suspend fun create(req: CreateBonsaiRequest): BonsaiResponse
}
```

`@Single` no Koin Annotations (Android); `createBonsaiService()` factory
function em `di/{Feature}Factory.kt` (iOS/Web).

### 8. Dispatcher injection

Toda chamada HTTP em `withContext(io)`. Injetar `CoroutineDispatcher` no
construtor (default `Dispatchers.IO`) — nunca hardcode no corpo. Permite
substituição por `UnconfinedTestDispatcher` em testes.

### 9. Timeouts

| Tipo | Default | Override |
|---|---|---|
| Connect timeout | 10s | configurável no `HttpClient` install |
| Request timeout | 15s | per-endpoint via `timeout-ms` no data-contract-spec |
| Socket timeout | 30s | apenas para uploads/downloads grandes |

### 10. Observabilidade

- Logs de request/response **nunca** incluem `Authorization` header nem
  campos `sensitivity: user-private` do body. Filter no `HttpClient`
  logging plugin.
- Métricas: `duration_ms`, `status_code`, `endpoint_id` — alinhar com
  contrato de analytics quando feature tem eventos `*_attempt`/`*_error`.

### 11. Testes obrigatórios

- `{Entity}MapperTest` cobrindo DTO → domain happy + null/empty fields.
- `{Feature}HttpMapperTest` cobrindo cada status code declarado em
  `status-mapping:` do data-contract-spec.
- `{Feature}ServiceTest` com `MockEngine` do Ktor cobrindo: 200, 4xx
  com error envelope, 5xx, timeout, IOException.
- `{Feature}RepositoryImplTest` cobrindo happy path + cada `DomainError`.
