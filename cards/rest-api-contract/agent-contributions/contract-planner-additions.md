<!--
  Injetado em: contract-planner-agent
  Extension-point: section:Data Contract
  Card: rest-api-contract

  Wave B do forge plan. Contract-planner produz data-contract-spec.yaml.
  Quando este card está ativo, toda operação REST citada no PRD/scope
  vira UM bloco em `rest-endpoints:` seguindo as regras abaixo.
-->

## rest-api-contract — regras para `data-contract-spec.yaml > rest-endpoints`

Aplicar quando a feature consome backend REST (HTTP JSON). Cards que
provêem `api-contract-firebase-sdk` (Firestore) coexistem — endpoints
REST vão para `rest-endpoints:`, coleções Firestore para
`firestore-collections:`.

### 1. Um bloco por endpoint — nunca agrupar

Cada endpoint distinto (combinação `method + path`) é uma entrada em
`rest-endpoints:`. Não agrupar variantes em "endpoint genérico".

```yaml
# CORRETO — endpoints separados
rest-endpoints:
  - id: list-bonsais
    method: GET
    path: "/api/v1/bonsais"
  - id: get-bonsai-detail
    method: GET
    path: "/api/v1/bonsais/{id}"

# ERRADO — agrupar oculta diferenças de auth/pagination/idempotency
rest-endpoints:
  - id: bonsais-api
    methods: [GET, POST, PUT, DELETE]
```

### 2. `endpoint-const` é obrigatório

Toda entrada referencia a const em `ApiEndpoints.kt`. Se ela não existe
ainda, declare como pendente em `notes:` da feature:

```yaml
- id: create-bonsai
  endpoint-const: "ApiEndpoints.BONSAI_CREATE"   # adicionar em data/network/ApiEndpoints.kt
```

String hardcoded de path no data-contract-spec é proibida fora do
campo `path:` (que é metadado para documentação humana).

### 3. Status mapping obrigatório

Toda entrada declara `status-mapping:` cobrindo no MÍNIMO:

- O status de sucesso (200 ou 201 ou 204)
- 401 / 403 quando `auth.required: true`
- 400 quando o endpoint aceita body
- 404 quando o path tem `{id}` ou outro recurso identificável
- 500 / 503 (sempre)

Códigos não-declarados caem em `DomainError.Unknown` por convenção do
mapper canônico — listar apenas códigos que a UI ou business logic
diferencia.

### 4. Error envelope é canônico — nunca redefinir

O envelope `{ error: { code, message, details? } }` é fixo no projeto.
Se o backend retorna outro formato, declarar `error-envelope.shape:` com
o formato real **e** adicionar follow-up em `notes:` para alinhar com
backend ou adicionar adapter no `{Feature}HttpMapper.kt`.

### 5. Paginação default: cursor-based

`pagination.style: cursor` é default. Mudanças para `offset` ou `none`
precisam de justificativa em `notes:` do data-contract-spec. Cards
downstream (UI, tech-spec) consultam este campo para escolher Paging 3
vs `LazyColumn` manual vs single-shot list.

### 6. Idempotência declarada explícita

`POST/PUT/PATCH/DELETE` **obrigatoriamente** declaram `idempotency:`. GET
pode omitir (`is-idempotent: true` implícito). Quando POST é idempotente
via `Idempotency-Key`, declarar header:

```yaml
idempotency:
  is-idempotent: true
  idempotency-key-header: "Idempotency-Key"
```

Use cases que disparam retry automático **devem** ser sobre endpoint
idempotente — se não, declare retry no client como erro de design.

### 7. BDD refs amarram endpoint a cenário

Cada `bdd-refs:` aponta para `scenario-id` em `behavior-spec.yaml` da
feature. Endpoint sem cenário coberto = endpoint sem teste — bloqueio
implícito ao implementar.

### 8. Auth scheme alinha com card de auth-provider ativo

| Card auth-provider ativo | `auth.scheme` esperado |
|---|---|
| `auth-jwt-bearer` | `Bearer` |
| `firebase-auth` | `Bearer` (Firebase ID token) ou `none` (endpoint público) |
| nenhum | `none` apenas |

Mismatch dispara warning no contract-planner: "Card `firebase-auth` ativo
mas endpoint declara `auth.scheme: custom` — confirmar."

### 9. Cross-references obrigatórios em endpoints custom

Toda entrada `rest-endpoints:` aponta para o spec do backend
(`docs/api/openapi.yaml`, Swagger UI, ou link interno). Sem cross-ref,
contract-planner emite warning — feature em isolamento é proibida.

### 10. Coexistência com Firestore (projetos híbridos)

Feature que usa REST + Firestore declara DOIS blocos no mesmo
data-contract-spec:

```yaml
rest-endpoints:
  - id: ...
firestore-collections:
  - name: ...
```

Cards complementares (`rest-api-contract` + `firestore-persistence`)
mergeiam ambos sem conflito. Validators rodam independente em cada bloco.
