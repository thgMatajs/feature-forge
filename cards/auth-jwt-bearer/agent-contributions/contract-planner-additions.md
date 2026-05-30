<!--
  Injetado em: contract-planner-agent
  Extension-point: section:data-contract
  Card: auth-jwt-bearer

  Wave B do forge plan. O contract-planner produz data-contract-spec.yaml.
  Quando este card está ativo, regras abaixo são obrigatórias ao desenhar
  os endpoints `/auth/*` e o shape do JWT.
-->

## auth-jwt-bearer — regras para `data-contract-spec.yaml`

Estas regras se aplicam à seção de auth (endpoints `/auth/*`, shape do
JWT, contratos de erro). Demais endpoints da feature seguem o padrão REST
do card `rest-api-contract`.

### 1. Endpoints canônicos — declarar mesmo se "óbvios"

Toda feature que precisa de session ativa deve declarar no contrato:

```yaml
endpoints:
  - id: auth-login
    path: "/auth/login"
    method: POST
    auth: public                   # sem header Authorization
    request:
      body:
        email:    { type: string, format: email, required: true }
        password: { type: string, min-length: 8, required: true }
    response:
      200:
        body:
          access_token:  { type: string, format: jwt, required: true }
          refresh_token: { type: string, required: true }
          expires_in:    { type: integer, unit: seconds, required: true }
      400: { error-code: invalid_payload }
      401: { error-code: invalid_credentials }

  - id: auth-refresh
    path: "/auth/refresh"
    method: POST
    auth: public                   # excluído do sendWithoutRequest
    request:
      body:
        refresh_token: { type: string, required: true }
    response:
      200:
        body:
          access_token:  { type: string, format: jwt, required: true }
          refresh_token: { type: string, required: true }
          expires_in:    { type: integer, unit: seconds, required: true }
      401: { error-code: refresh_invalid }   # → SessionExpired no domain

  - id: auth-logout
    path: "/auth/logout"
    method: POST
    auth: bearer                   # header obrigatório
    request:
      body:
        refresh_token: { type: string, required: false }
    response:
      204: {}
      401: { error-code: invalid_session }
```

Endpoints adicionais (`/auth/register`, `/auth/forgot-password`, etc.) seguem
o mesmo template — sempre declarar `auth: public | bearer`.

### 2. Shape do JWT — claims obrigatórias

```yaml
jwt-payload:
  required-claims:
    - { name: sub, type: string,  purpose: "user id" }
    - { name: exp, type: integer, purpose: "expiration epoch seconds" }
    - { name: iat, type: integer, purpose: "issued at epoch seconds" }
  optional-claims:
    - { name: role,  type: string }
    - { name: scope, type: "string | array<string>" }
    - { name: iss,   type: string }
  validation:
    decode-only-on-client: true     # NUNCA validar assinatura no client
    expiration-driver:    "exp"     # usado para refresh proativo opcional
```

### 3. Auth requirement por endpoint — explícito sempre

Todo endpoint da feature declara `auth: public | bearer | optional` —
nunca implícito. `public` significa "Ktor Auth plugin não anexa header"
(deve constar em `sendWithoutRequest`).

### 4. Error contract — códigos canônicos

Mapping HTTP → `AuthDomainError` é obrigatório no contrato:

```yaml
error-mapping:
  - { status: 400, endpoint: auth-login,   code: invalid_payload,     domain-error: InvalidPayload }
  - { status: 401, endpoint: auth-login,   code: invalid_credentials, domain-error: InvalidCredentials }
  - { status: 401, endpoint: auth-refresh, code: refresh_invalid,     domain-error: SessionExpired }
  - { status: 403, endpoint: "*",          code: forbidden,           domain-error: Forbidden }
  - { status: "5xx", endpoint: "*",        code: server_unavailable,  domain-error: ServerUnavailable }
  - { status: "network", endpoint: "*",    code: network_unavailable, domain-error: NetworkUnavailable }
```

Códigos novos vão ao contrato antes do código — não inventar `domain-error`
sem declarar no `data-contract-spec.yaml`.

### 5. Refresh-token rotation policy

Backend que rotaciona refresh-token a cada `/auth/refresh` é o esperado.
Declarar explicitamente:

```yaml
refresh-policy:
  rotation: true                    # cada refresh devolve novo refresh-token
  one-time-use: true                # refresh-token antigo inválido após uso
  absolute-lifetime: 30d            # após este prazo, login obrigatório
  reuse-detection: true             # backend invalida cadeia se detectar reuso
```

Se o backend **não** faz rotation, anotar em `notes:` e justificar — afeta o
risco de session hijacking.

### 6. Storage não entra no data-contract

`TokenStorage` é decisão do **tech-spec** (Data layer), não do contrato de
API. O contrato descreve apenas o que o servidor expõe.

### 7. Paridade Android ↔ iOS implícita

Como o flow vive no shared, o contrato vale igual para as duas plataformas.
Não declarar variações por plataforma — qualquer divergência sugere bug no
desenho do contrato ou no servidor.
