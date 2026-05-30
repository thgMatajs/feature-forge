<!--
  Injetado em: task-contract-writer
  Extension-point: after:Allowed Files
  Card: rest-api-contract

  Wave D do forge plan. Task-contract-writer decompõe o tech-spec em
  TASK-NNNN.yaml. Quando este card está ativo, tasks que tocam camada
  REST ganham globs de allowed_files e validations específicos.
-->

## rest-api-contract — adições para Task Contracts

### 1. Globs adicionais em `allowed_files`

Tasks cujo escopo case com `api-*`, `service-*`, `network-*`, `dto-*`,
`endpoint-*`, ou que toquem `data/network/` recebem estes globs:

```yaml
allowed_files:
  # camada network — fonte única de endpoints
  - "shared/feature/{feature}/**/data/network/ApiEndpoints.kt"

  # DTOs Request/Response + envelope canônico
  - "shared/feature/{feature}/**/data/network/dto/*Request.kt"
  - "shared/feature/{feature}/**/data/network/dto/*Response.kt"
  - "shared/feature/{feature}/**/data/network/dto/ErrorResponse.kt"

  # Service interface + impl
  - "shared/feature/{feature}/**/data/network/service/*Service.kt"
  - "shared/feature/{feature}/**/data/network/service/*ServiceImpl.kt"

  # Mappers — DTO→domain + HTTP status→DomainError
  - "shared/feature/{feature}/**/data/network/mapper/*Mapper.kt"
  - "shared/feature/{feature}/**/data/network/mapper/*HttpMapper.kt"

  # Domain — sealed DomainError + Repository interface
  - "shared/feature/{feature}/**/domain/model/*DomainError.kt"
  - "shared/feature/{feature}/**/domain/repository/*Repository.kt"
  - "shared/feature/{feature}/**/data/repository/*RepositoryImpl.kt"

  # DI por plataforma
  - "shared/feature/{feature}/**/di/*Module.kt"          # Android (Koin)
  - "shared/feature/{feature}/**/di/*Factory.kt"          # iOS/Web factory

  # Testes — MockEngine + cobertura de mappers
  - "shared/feature/{feature}/**/data/network/**/*Test.kt"
  - "shared/feature/{feature}/**/domain/**/*Test.kt"
```

### 2. Globs proibidos (deny lists)

Tasks REST **nunca** editam:

```yaml
denied_files:
  - "**/openapi.yaml"                   # spec do backend — fora do escopo client
  - "**/swagger.json"
  - "**/api-keys.properties"            # credenciais nunca em PR
  - "**/.env*"                          # config sensível
```

### 3. Validações específicas (compile + contract test)

Adicione a tasks que tocam camada REST:

```yaml
validations:
  - name: rest-endpoints-from-const
    command: "grep -rE '\"/api/v[0-9]+/' shared/feature/{feature}/ | grep -v ApiEndpoints.kt | grep -v Test.kt || true"
    severity: error
    rationale: "Path REST hardcoded fora de ApiEndpoints.kt. Centralizar para permitir bump de versão e mock em testes."

  - name: rest-dto-not-leaked-to-domain
    command: "grep -rE '(Request|Response)\\b' shared/feature/{feature}/*/domain shared/feature/{feature}/*/presentation || true"
    severity: error
    rationale: "DTOs Request/Response não podem cruzar a fronteira data→domain. Sempre mapear."

  - name: rest-http-types-not-leaked
    command: "grep -rE 'io\\.ktor\\.|HttpStatusCode|HttpResponse' shared/feature/{feature}/*/domain shared/feature/{feature}/*/presentation || true"
    severity: error
    rationale: "Tipos HTTP (Ktor) só em data/network/. Domain e presentation usam apenas DomainError."

  - name: rest-shared-compile
    command: "./gradlew :shared:feature:{feature}:compileKotlinMetadata"
    severity: error
    rationale: "Camada network precisa compilar antes de qualquer task de UI consumir Service."

  - name: rest-contract-tests
    command: "./gradlew :shared:feature:{feature}:testAndroidHostTest --tests '*HttpMapperTest' --tests '*ServiceTest' --tests '*MapperTest'"
    severity: error
    rationale: "Mappers e Service (MockEngine) cobertos antes de promover task para review."
```

### 4. Gates por tipo de task

| Categoria de task | Gates obrigatórios |
|---|---|
| `network-endpoints` (cria/edita `ApiEndpoints.kt`) | `rest-endpoints-from-const` + compile shared |
| `network-dto` (cria/edita `*Request.kt` / `*Response.kt`) | compile shared + `rest-dto-not-leaked-to-domain` |
| `network-service` (cria/edita `*Service.kt`) | `rest-http-types-not-leaked` + unit tests com MockEngine |
| `network-mapper` (cria/edita `*Mapper.kt`, `*HttpMapper.kt`) | `*MapperTest` cobrindo todos os status declarados no data-contract-spec |
| `domain-error` (cria/edita `*DomainError.kt`) | sealed class compila + matching exhaustivo em mapper |
| `repository-rest` (cria/edita `*RepositoryImpl.kt` REST) | unit tests com fake Service cobrindo happy + cada DomainError |
| `di-platform` (cria/edita Module Android / Factory iOS-Web) | compile shared + KSP roda sem erro (Koin Annotations) |

### 5. Ordem sugerida de tasks em features REST

1. `TASK-{FEAT}-001-domain-error` — sealed `DomainError` em `domain/model/`
2. `TASK-{FEAT}-002-endpoints` — `ApiEndpoints.kt` com paths como const
3. `TASK-{FEAT}-003-dto` — `*Request`, `*Response`, `ErrorResponse` em `data/network/dto/`
4. `TASK-{FEAT}-004-dto-mapper` — `*Mapper.kt` (DTO → domain) + test cobrindo nullable fields
5. `TASK-{FEAT}-005-http-mapper` — `*HttpMapper.kt` (status → DomainError) + test por status
6. `TASK-{FEAT}-006-service-interface` — `{Feature}Service.kt` interface em `data/network/service/`
7. `TASK-{FEAT}-007-service-impl` — `{Feature}ServiceImpl.kt` consumindo `HttpClient` + DI Android (`@Single`)
8. `TASK-{FEAT}-008-service-test` — `ServiceTest` com `MockEngine` cobrindo 200/4xx/5xx/timeout
9. `TASK-{FEAT}-009-repository` — `Repository` interface + `RepositoryImpl`
10. `TASK-{FEAT}-010-ios-factory` — `create{Feature}Service()` em `di/{Feature}Factory.kt`
11. `TASK-{FEAT}-011-usecases` — `{Verb}{Noun}UseCase` consumindo Repository
12. `TASK-{FEAT}-012-viewmodel` (delegado para card de UI) — consumir UseCases

Ordem dura: `domain → data/network → data/repository → domain/usecase → presentation`.
Pular qualquer etapa quebra dependência de compilação.

### 6. Allowed-files compartilhado com auth-jwt-bearer (quando ativo)

Se o card `auth-jwt-bearer` está ativo, tasks REST que tocam endpoints
autenticados podem editar **adicionalmente**:

```yaml
allowed_files:
  - "shared/core/**/auth/AuthInterceptor.kt"     # injeta Bearer token
  - "shared/core/**/auth/TokenStore.kt"           # persistência de token
```

Card `firebase-auth` ativo: Bearer token é o Firebase ID token,
recuperado via `AuthService.getCurrentIdToken()` — Service classes
recebem o token por parâmetro, não persistem.
