<!-- Injected into: contract-planner-agent
     Extension point: section:data-contract
     Source card: ktor-client v1.0.0
-->

## REST data contract orientation (card `ktor-client`)

Quando `ktor-client` está ativo, a data layer é **REST sobre HTTP** — não
Firestore SDK. Ao produzir `data-contract-spec.yaml`, espelhe a realidade
do backend REST, não invente coleções estilo Firestore.

### Regras de produção

- **NÃO documentar `firestore_collections:`** quando `ktor-client` é o
  provedor ativo de `http-client` E nenhum card Firestore (`firestore-persistence`,
  `firestore-realtime`) está ativo. Se ambos coexistirem, separe os blocos
  por entidade — REST para entidades servidas via endpoint, Firestore para
  entidades em coleção. Não duplique a mesma entidade nos dois.
- **Documentar `rest_endpoints:`** — uma entrada por endpoint consumido pela
  feature. Schema mínimo:
  ```yaml
  rest_endpoints:
    - id: get_bonsai
      method: GET
      path: /v1/bonsais/{id}
      auth: bearer       # ou: public | bearer | bearer-refresh
      request_dto: null   # ou nome do *Request quando POST/PUT/PATCH
      response_dto: BonsaiResponse
      success_status: [200]
      error_mapping:
        404: NetworkError.NotFound
        422: NetworkError.ValidationFailed
      idempotent: true    # decide se entra em retry
  ```
- **Entidades** continuam descritas em `entities:` — campo `source: rest`
  (ou `firestore` quando coexistir) deve apontar para o endpoint canônico.
- **DTOs** (Request/Response) declarados em `dtos:` — naming `{Entity}Request`,
  `{Entity}Response` per regras do card `kotlinx-serialization-json`.

### Mapeamento de operações

Cada user story do PRD que toca rede → 1+ entrada em `rest_endpoints:`.
Use a tabela de error mapping canônica do tech-spec-agent (`section:Data
layer` injection) como base. Endpoints com semântica fora do mapping
(ex.: 423 Locked = recurso em uso) requerem entrada explícita em
`error_mapping:` por endpoint.

### Indexes / queries

Não aplicável a REST puro — descartar campos `indexes:` e
`query_catalog:` do template quando não há card de persistência server
ativo (Firestore/Room). Se existir cache local via `room-database` ou
`datastore-prefs`, esses cards documentam seus próprios blocos.

### Auth e refresh

Endpoints com `auth: bearer-refresh` confiam no `Auth` plugin do
`HttpClient` (refresh transparente). Endpoints `auth: bearer` falham com
401 sem retry de refresh. Endpoints `auth: public` (login, signup, reset)
NÃO enviam token — declarar host/path em `public_endpoints:` para
configuração do plugin.

### Anti-patterns a sinalizar

- `data-contract-spec.yaml` listando coleções Firestore quando só
  `ktor-client` está ativo → erro de spec.
- Endpoint REST sem `response_dto` quando retorna body (≠ 204) → erro.
- `error_mapping:` ausente em endpoint que pode retornar 4xx → erro
  (mínimo: cobrir 401/404/422/5xx).
- `idempotent: true` para POST sem chave de idempotência declarada →
  inconsistente com o `HttpRequestRetry` do client.
