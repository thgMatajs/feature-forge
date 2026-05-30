# Card — `rest-api-contract`

> Convenções REST canônicas para projetos KMP: endpoints como `const` em
> `ApiEndpoints.kt`, DTOs `{Entity}Request/Response` com
> `@Serializable`, error envelope padronizado
> `{ error: { code, message, details? } }`, mapping HTTP status → domain
> errors via `{Feature}HttpMapper.kt`, e paginação cursor-based como
> default. Provê a capability auxiliar `api-contract-rest`, podendo
> coexistir com `api-contract-firebase-sdk` em projetos híbridos
> (REST para feature X + Firestore para feature Y).

- **Categoria:** `backend`
- **Maturidade:** `stable`
- **Provides:** `api-contract-rest` (auxiliar)
- **Requires:** `http-client` (`ktor-client`), `serialization-json` (`kotlinx-serialization-json`)
- **Conflicts-with:** _nenhum_ (capability auxiliar; coexiste com Firestore)

## Quando este card é ativado

`forge init` ativa `rest-api-contract` quando a soma de confidence dos
signals abaixo é maior ou igual a `0.4`:

| Sinal | Confidence | Por quê |
|---|---|---|
| `@SerialName` em qualquer `*.kt` | 0.3 | Tipico de DTOs REST com naming JSON divergente |
| `@Serializable` em qualquer `*.kt` | 0.3 | Classes serializáveis (DTO candidato) |
| Diretório `**/network` existe | 0.2 | Convenção canônica `data/network/` |
| Diretório `**/api` existe | 0.2 | Variante comum de `network/` |
| `HttpClient` referenciado em `*.kt` | 0.2 | Cliente HTTP ativo (Ktor) |

Threshold 0.4 — sinais REST são individualmente fracos
(`@Serializable` aparece em persistência, IPC, config). Combinação
`@Serializable` + `network/` + `HttpClient` é o gatilho confiável.

Se a soma cair em `[0.3, 0.4)`, o forge pergunta confirmação ao usuário.
Abaixo de 0.3, o card não é ativado.

## Capability + relação com outros cards

`rest-api-contract` provê **uma label auxiliar** do catálogo v1
(`docs/schemas/capability-labels.md`):

- `api-contract-rest` (**auxiliar**) — convenções REST. Múltiplos cards
  podem provê-la em tese (variantes de convenção), mas v1 padroniza
  neste card.

Capability auxiliar significa que `conflicts-with:` é vazio. Em projetos
híbridos, o card coexiste com `firestore-persistence` (que provê
`api-contract-firebase-sdk`) — REST para feature A + Firestore para
feature B é arranjo legítimo.

`requires:` puxa dois cards obrigatórios:

- `http-client` → provido por `ktor-client` (KMP cross-platform).
- `serialization-json` → provido por `kotlinx-serialization-json`.

Se algum dos dois não estiver ativo, `forge init` falha com erro de
dependência e sugere ativação.

## O que este card contribui

### 1. Template — seção "REST API Contract" em `tech-spec.md`

`templates/rest-api-tech-spec.md` é appendado ao `tech-spec.md` da
feature quando o card está ativo. Documenta:

- Estrutura canônica `data/network/` (`ApiEndpoints.kt`, `dto/`,
  `service/`, `mapper/`).
- DTOs `@Serializable` com `@SerialName` para JSON snake_case.
- Error envelope `ErrorResponse` em DTO único compartilhado.
- Mapping `HTTP status → DomainError` em `{Feature}HttpMapper.kt`.
- Paginação cursor-based com `PageResponse<T>` canônico.
- Idempotência: tabela por método HTTP, header `Idempotency-Key` para
  POST retry-safe.
- DI por plataforma: `@Single` (Android Koin) + `create{Feature}Service()`
  (iOS/Web factory).
- Dispatcher injection (`withContext(io)`), timeouts, cancelamento.
- Testes mínimos: `MapperTest`, `HttpMapperTest`, `ServiceTest` com
  `MockEngine`, `RepositoryImplTest`.

### 2. Fragmento — `rest-endpoints:` em `data-contract-spec.yaml`

`templates/rest-endpoints-data-contract.yaml` é mergeado por chave no
`data-contract-spec.yaml` da feature. Garante que toda feature que
consome backend REST declare explicitamente:

- `method` + `path` + `endpoint-const` (referência à `ApiEndpoints.kt`).
- `auth` (scheme, scope, required).
- `request` (path-params, query-params, headers, body DTO).
- `response` (status de sucesso, DTO, envelope canônico de erro).
- `pagination` (cursor / offset / none).
- `status-mapping` (HTTP code → domain error code).
- `idempotency` (declaração explícita por método).
- `bdd-refs` (cenários cobertos).
- `cross-references` (link para OpenAPI / Swagger).

Bloco coexiste com `firestore-collections:` (card
`firestore-persistence`) no mesmo data-contract-spec para projetos
híbridos.

### 3. Prompts injetados nos agentes

| Agente | Extension-point | Conteúdo |
|---|---|---|
| `contract-planner-agent` | `section:Data Contract` | Regras para escrita do bloco `rest-endpoints:` — um endpoint por bloco, status-mapping mínimo (200 + 4xx críticos + 5xx), envelope fixo, paginação cursor default, idempotência explícita, BDD refs obrigatórios. |
| `tech-spec-agent` | `section:Data layer` | Estratégia REST canônica: estrutura `data/network/`, DTO @Serializable, error envelope, status→DomainError, paginação cursor, idempotência, DI por plataforma, dispatcher injection, observability filter, testes mínimos. |
| `task-contract-writer` | `after:Allowed Files` | Allowed-files patterns (`ApiEndpoints.kt`, `*Request/Response.kt`, `*Service.kt`, `*HttpMapper.kt`), denied-files (OpenAPI, .env, api-keys), validations (`rest-endpoints-from-const`, `rest-dto-not-leaked`, `rest-http-types-not-leaked`, compile + contract tests), ordem dura de tasks. |

### 4. Config defaults

- `conventions.api.contract-style: "rest"` — convenção raiz REST.
- `conventions.api.endpoints-source: "ApiEndpoints.kt"` — arquivo
  canônico de paths.
- `conventions.api.error-envelope: "{ error: { code, message, details? } }"`
  — formato fixo do envelope de erro.
- `conventions.api.pagination: "cursor-based"` — paginação default.

Cards / usuários podem sobrescrever em `workflow-config.yaml`. Por
exemplo, projeto que insiste em offset-based define
`conventions.api.pagination: "offset-based"` e justifica em ADR.

## Integração com outros cards

| Combina com | Efeito |
|---|---|
| `ktor-client` | Provê `HttpClient` consumido por Service classes. Service é a única classe que importa Ktor. |
| `kotlinx-serialization-json` | Provê serialização JSON dos DTOs `@Serializable`. |
| `kmp-shared` | Toda camada `data/network/` mora em `commonMain`. Sem `expect/actual` na camada REST. |
| `koin-annotations` | `@Single {Feature}ServiceImpl` em pacote coberto por `@Module @ComponentScan` no Android. |
| `firestore-persistence` | Coexiste (projetos híbridos). REST + Firestore numa mesma feature: dois blocos no data-contract-spec, um Repository unifica DomainError. |
| `firebase-auth` | Bearer token = Firebase ID token. Service recebe por parâmetro, não persiste. |
| `auth-jwt-bearer` | Allowed-files do task-writer abre `AuthInterceptor.kt` + `TokenStore.kt` em `shared/core/auth/`. |
| `crashlytics` | Eventos `*_error` REST disparam `recordException` com `status_code`, `endpoint_id`. |

## Como usar localmente

1. **Detecção:** `forge init` ativa automaticamente quando os signals
   batem em ≥ 0.4.
2. **Manual:** `forge reconfigure` → menu "adicionar card" →
   `rest-api-contract`.
3. **Inspeção:** `forge reconfigure` → menu "inspecionar card" mostra
   sha256, conflitos resolvidos e contribuições mergeadas.

## Convenções aplicadas pelo card (resumo)

### Endpoints

- Fonte única: `data/network/ApiEndpoints.kt`.
- `const val NAME = "/api/v1/resource"` — string literal de path fora
  desse arquivo é bloqueada por validator do task-writer.
- Bump de versão (`/v1` → `/v2`) muda 1 arquivo.

### DTOs

- Naming: `{Entity}Request` (body POST/PUT/PATCH), `{Entity}Response`
  (corpo 200/201).
- `@Serializable` + `@SerialName` quando JSON usa snake_case.
- `internal` por padrão — não vazam para outros módulos.
- DTO em `domain/` ou `presentation/` é bloqueado por validator.

### Error envelope

```json
{
  "error": {
    "code": "email_already_in_use",
    "message": "Email já está cadastrado",
    "details": { "field": "email" }
  }
}
```

DTO único `ErrorResponse` em `data/network/dto/`. Backends com formato
divergente exigem adapter em `{Feature}HttpMapper.kt` + follow-up
documentado.

### Status → Domain Error

Mapping centralizado em `data/network/mapper/{Feature}HttpMapper.kt`.
Tabela canônica:

| HTTP | DomainError |
|---|---|
| 400 | `ValidationError(code)` |
| 401 | `Unauthorized` |
| 403 | `Forbidden` |
| 404 | `NotFound` |
| 409 | `Conflict(code)` |
| 422 | `Unprocessable(code)` |
| 429 | `RateLimited` |
| 500-599 | `ServerError` |
| timeout / IOException | `NetworkUnavailable` |
| outro | `Unknown(code)` |

Domain layer **nunca** importa `io.ktor.client.statement.*` nem
`HttpStatusCode` — validator do task-writer bloqueia.

### Paginação

Cursor-based default:

```
GET /api/v1/items?cursor=<opaque>&limit=50
→ { items: [...], next_cursor: "<opaque-ou-null>" }
```

Repository expõe `suspend fun loadPage(cursor, limit)` ou
`Flow<PagingData<T>>` quando Paging 3 está ativo.

### Idempotência

| Método | Default | Auto-retry? |
|---|---|---|
| GET / PUT / DELETE | idempotente | sim |
| POST | NÃO idempotente | só com `Idempotency-Key: <UUIDv4>` |
| PATCH | declarar explícito | depende |

## Limites declarados

- Este card **não** prescreve schema do backend — ele descreve as
  convenções do cliente que CONSOME REST. Mudanças no backend
  (OpenAPI / Swagger) vivem fora do escopo do card.
- Este card **não** gera código — apenas contribui contratos, templates
  e prompts. Implementação concreta é responsabilidade dos agentes
  downstream.
- Este card **não** provê o `HttpClient` — isso é do card `ktor-client`.
  Idem para serialização (`kotlinx-serialization-json`).
- Este card **não** trata realtime (WebSocket, SSE) — capabilities
  `websocket-realtime` / `sse-realtime` são reservadas para v1.1.

## Como o card se conecta às regras de arquitetura

O contrato canônico alinha-se 1:1 com `.claude/rules/architecture_kmp.md`
(Quick Reference KMP) e `.claude/rules/kotlin-idioms.md`:

| Regra do projeto | Contribuição do card |
|---|---|
| "DTO/Response na UI → mapear para domain/UI model" | Validator `rest-dto-not-leaked-to-domain` bloqueia uso de DTO fora de `data/`. |
| "Service como IO boundary" | Tech-spec exige `{Feature}Service.kt` interface; única classe que importa `HttpClient`. |
| "Injetar dispatchers" | Service recebe `CoroutineDispatcher` no construtor (default `Dispatchers.IO`). |
| "Custom loading/error sealed class → usar `StateUI<T>`" | Mapping HTTP→`DomainError` mantém ViewModel/UseCase plugando em `StateUI<T>`. |
| "DI via Koin Annotations" | `@Single ServiceImpl` no Android; factory function `create{Feature}Service()` iOS/Web. |

## Exemplo — feature "List Bonsais" (REST)

Quando feature `bonsai-list` é planejada com este card ativo:

1. `forge plan` detecta sinais → ativa automaticamente.
2. `contract-planner-agent` produz `data-contract-spec.yaml` com bloco
   `rest-endpoints:` cobrindo `GET /api/v1/bonsais` + `GET /api/v1/bonsais/{id}`.
3. `tech-spec-agent` appenda seção "REST API Contract" descrevendo
   `BonsaiService`, `BonsaiResponse`, `BonsaiMapper`, `BonsaiHttpMapper`,
   paginação cursor com `PageResponse<BonsaiResponse>`.
4. `task-contract-writer` decompõe em `TASK-BONSAI-001..012` na ordem
   `domain-error → endpoints → dto → dto-mapper → http-mapper →
   service-interface → service-impl → service-test → repository →
   ios-factory → usecases → viewmodel`.
5. `forge implement` corre validators (`rest-endpoints-from-const`,
   `rest-dto-not-leaked-to-domain`, `rest-http-types-not-leaked`,
   compile shared, contract tests) em pre-commit e verify-task.

## Referência viva

- Estrutura canônica de feature REST KMP: `shared/feature/{name}/src/commonMain/kotlin/.../feature/{name}/data/network/`
- Convenções de Kotlin: `.claude/rules/kotlin-idioms.md`
- Convenções KMP / camadas: `.claude/rules/architecture_kmp.md`
- Catálogo de capabilities: `docs/schemas/capability-labels.md` (família Network)

## Roadmap

- Phase 5: implementar validators dedicados (`check-rest-endpoints-from-const.py`,
  `check-rest-dto-not-leaked.py`, `check-rest-http-types-not-leaked.py`)
  — hoje materializados como `grep` inline em validations das tasks.
- v1.1: contribuir fragmento de `test-strategy.yaml` com cobertura
  mínima obrigatória para `HttpMapper` (matriz status × código).
- v1.1: card complementar `graphql-client` (reservado no catálogo) para
  features que misturam REST + GraphQL.
- v1.2: signal extra de detecção: presença de `openapi.yaml` ou
  `swagger.json` na raiz do repo (confidence 0.3).
