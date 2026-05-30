<!--
  Injetado em: task-contract-writer
  Extension-point: after:Allowed Files
  Card: auth-jwt-bearer

  Wave D do forge plan. O task-contract-writer decompõe o tech-spec em
  TASK-NNNN.yaml. Quando este card está ativo, tasks de auth ganham globs
  de allowed_files, denied_files e validations específicos.
-->

## auth-jwt-bearer — adições para Task Contracts

### 1. Globs adicionais em `allowed_files`

Tasks cujo nome ou escopo case com `auth-*`, `login-*`, `logout-*`,
`refresh-*` ou referencie `AuthService` / `AuthRepository` / `TokenStorage`
recebem estes globs:

```yaml
allowed_files:
  # camada data — service + storage + mapping + dto
  - "shared/feature/auth/**/data/service/AuthService.kt"
  - "shared/feature/auth/**/data/service/AuthRestService.kt"
  - "shared/feature/auth/**/data/storage/TokenStorage.kt"
  - "shared/feature/auth/**/data/storage/SecureTokenStorage*.kt"
  - "shared/feature/auth/**/data/mapper/AuthErrorMapper.kt"
  - "shared/feature/auth/**/data/dto/LoginRequest.kt"
  - "shared/feature/auth/**/data/dto/RefreshRequest.kt"
  - "shared/feature/auth/**/data/dto/TokenPairResponse.kt"
  - "shared/feature/auth/**/data/repository/AuthRepositoryImpl.kt"

  # camada domain
  - "shared/feature/auth/**/domain/model/UserSession.kt"
  - "shared/feature/auth/**/domain/model/TokenPair.kt"
  - "shared/feature/auth/**/domain/model/AuthDomainError.kt"
  - "shared/feature/auth/**/domain/repository/AuthRepository.kt"
  - "shared/feature/auth/**/domain/usecase/LoginUseCase.kt"
  - "shared/feature/auth/**/domain/usecase/LogoutUseCase.kt"
  - "shared/feature/auth/**/domain/usecase/RefreshTokenUseCase.kt"
  - "shared/feature/auth/**/domain/usecase/ObserveAuthStateUseCase.kt"

  # DI per platform
  - "shared/feature/auth/**/di/Auth*Module.kt"          # Android Koin
  - "shared/feature/auth/**/di/AuthFactory.kt"          # iOS/Web factory

  # platform shims do storage seguro (expect/actual)
  - "shared/feature/auth/**/data/storage/SecureTokenStorageAndroid.kt"
  - "shared/feature/auth/**/data/storage/SecureTokenStorageIOS.kt"
  - "shared/feature/auth/**/data/storage/SecureTokenStorageWeb.kt"

  # HttpClient — config do Ktor Auth plugin (compartilhado com ktor-client)
  - "shared/core/**/network/HttpClientFactory.kt"
```

### 2. Globs proibidos (deny lists)

Tasks de auth **nunca** podem editar diretamente:

```yaml
denied_files:
  # secrets / keys de assinatura
  - "**/keystore.properties"
  - "**/*.jks"
  - "**/*.keystore"
  - "**/.env*"

  # storage não seguro (qualquer salvamento de token aqui é violação)
  - "**/SharedPreferencesTokenStorage*.kt"
  - "**/UserDefaultsTokenStorage*.kt"
  - "**/LocalStorageTokenStorage*.ts"
```

### 3. Validations específicas

Adicione a tasks que tocam auth:

```yaml
validations:
  - name: no-plaintext-token-storage
    command: "python3 .claude/cards/auth-jwt-bearer/validators/check-no-plaintext-token-storage.py --paths {changed_files}"
    severity: error
    rationale: "Refresh-token / access-token em SharedPreferences/UserDefaults/localStorage plain é vetor crítico de session hijacking."

  - name: no-manual-authorization-interceptor
    command: "grep -rE 'header\\(\\\"Authorization\\\",|setHeader\\(\\\"Authorization\\\",' shared/feature/auth/ || true"
    severity: warn
    rationale: "Authorization header deve ser anexado pelo Ktor Auth plugin (loadTokens/refreshTokens), não manualmente."

  - name: ktor-exception-not-leaked
    command: "grep -rE 'ResponseException|ClientRequestException|ServerResponseException' shared/feature/auth/*/domain shared/feature/auth/*/presentation || true"
    severity: error
    rationale: "Exceptions do Ktor não podem vazar para domain/ ou presentation/ — AuthErrorMapper traduz na fronteira."

  - name: jwt-signature-not-validated-on-client
    command: "grep -rE 'Jwts\\.parser|JWT\\.require|verify\\(.*Algorithm' shared/feature/auth/ || true"
    severity: error
    rationale: "Validação de assinatura do JWT no client é falso senso de segurança — confiar no servidor."
```

### 4. Gates por tipo de task

| Categoria de task | Gates obrigatórios |
|---|---|
| `data-service` (cria/edita `AuthRestService.kt`) | unit tests com `MockEngine` + `ktor-exception-not-leaked` + `no-manual-authorization-interceptor` |
| `data-storage` (cria/edita `SecureTokenStorage*.kt`) | unit tests read/write/clear + `no-plaintext-token-storage` |
| `data-mapper` (cria/edita `AuthErrorMapper.kt`) | unit tests cobrindo todos os status da tabela de mapping |
| `usecase-logout` (cria/edita `LogoutUseCase.kt`) | testes: clear no happy path + clear no failure de rede + emissão de `SignedOut` |
| `http-client-config` (edita `HttpClientFactory.kt` para instalar Auth plugin) | inspeção de `sendWithoutRequest` excluindo `/auth/login` e `/auth/refresh` |

### 5. Ordem sugerida de tasks em features de auth

1. `TASK-AUTH-001-domain-model` — `UserSession`, `TokenPair`, `AuthDomainError` em `domain/model/`
2. `TASK-AUTH-002-service-interface` — `AuthService` interface em `data/service/`
3. `TASK-AUTH-003-dto` — `LoginRequest`, `RefreshRequest`, `TokenPairResponse` (`@Serializable`)
4. `TASK-AUTH-004-rest-service-impl` — `AuthRestService` consumindo Ktor + DI Android (`@Single`)
5. `TASK-AUTH-005-error-mapper` — `AuthErrorMapper` com cobertura de todos os status
6. `TASK-AUTH-006-token-storage-interface` — `TokenStorage` interface no commonMain
7. `TASK-AUTH-007-token-storage-android` — `SecureTokenStorageAndroid` (EncryptedDataStore)
8. `TASK-AUTH-008-token-storage-ios` — `SecureTokenStorageIOS` (Keychain)
9. `TASK-AUTH-009-http-client-auth-plugin` — instalar `Auth { bearer { ... } }` no `HttpClientFactory`
10. `TASK-AUTH-010-repository` — `AuthRepository` interface + `AuthRepositoryImpl`
11. `TASK-AUTH-011-usecases` — `LoginUseCase`, `LogoutUseCase`, `RefreshTokenUseCase`, `ObserveAuthStateUseCase`
12. `TASK-AUTH-012-ios-factory` — `createAuthService()`, `createTokenStorage()`, `createAuthRepository()`
13. `TASK-AUTH-013-viewmodel` — `LoginViewModel` / `LogoutViewModel` consumindo UseCases
14. `TASK-AUTH-014-screens-android` + `TASK-AUTH-015-screens-ios` — UI nativa

Ordem específica pode mudar conforme PRD; regra dura é domain → data → presentation.
