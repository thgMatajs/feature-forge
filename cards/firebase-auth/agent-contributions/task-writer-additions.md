<!--
  Injetado em: task-contract-writer
  Extension-point: after:Allowed Files
  Card: firebase-auth

  Wave D do forge plan. O task-contract-writer decompõe o tech-spec em
  TASK-NNNN.yaml. Quando este card está ativo, tasks relacionadas a auth
  ganham globs de allowed_files e validations específicos.
-->

## firebase-auth — adições para Task Contracts

### 1. Globs adicionais em `allowed_files`

Tasks cujo nome ou escopo case com `auth-*`, `login-*`, `register-*` ou
referencie `AuthService`/`AuthRepository` recebem estes globs:

```yaml
allowed_files:
  # camada data — service + mapping + analytics
  - "shared/feature/auth/**/data/service/*Service.kt"
  - "shared/feature/auth/**/data/service/Firebase*Service.kt"
  - "shared/feature/auth/**/data/mapper/Auth*Mapper.kt"
  - "shared/feature/auth/**/data/dto/Auth*Response.kt"
  - "shared/feature/auth/**/data/repository/Auth*RepositoryImpl.kt"
  - "shared/feature/auth/**/data/analytics/FirebaseAuthAnalyticsException.kt"

  # camada domain
  - "shared/feature/auth/**/domain/model/UserSession.kt"
  - "shared/feature/auth/**/domain/model/AuthDomainError.kt"
  - "shared/feature/auth/**/domain/repository/AuthRepository.kt"
  - "shared/feature/auth/**/domain/usecase/*UseCase.kt"

  # DI per platform
  - "shared/feature/auth/**/di/Auth*Module.kt"          # Android Koin
  - "shared/feature/auth/**/di/AuthFactory.kt"          # iOS/Web factory

  # observability — contratos canônicos (referenciados, raramente editados)
  - "shared/core/**/observability/AuthAnalytics.kt"
  - "shared/core/**/observability/AuthTestIds.kt"

  # configs de ambiente — gitignored, NÃO entram em allowed_files
  # (deny implícito — quem precisar configurar gera via Firebase Console)
```

### 2. Globs proibidos (deny lists)

Tasks de auth **nunca** podem editar diretamente:

```yaml
denied_files:
  - "**/google-services.json"           # gerado pelo Firebase Console
  - "**/GoogleService-Info.plist"       # gerado pelo Firebase Console
  - "**/.env.development"               # ambiente Web — config sensível
  - "**/.env.production"
```

### 3. Validations específicas

Adicione a tasks que tocam auth:

```yaml
validations:
  - name: auth-test-ids-canonical
    command: "python3 .claude/cards/firebase-auth/validators/check-auth-test-ids-canonical.py --paths {changed_files}"
    severity: error
    rationale: "Test IDs hardcoded em código de auth quebram paridade Android↔iOS."

  - name: auth-analytics-events-canonical
    command: "grep -rE 'logEvent\\(\\\"(register|login)_' shared/ androidApp/ iosApp/ || true"
    severity: warn
    rationale: "Detecta event names hardcoded — devem vir de AuthAnalytics.Events."

  - name: firebase-auth-exception-not-leaked
    command: "grep -rE 'FirebaseAuthException' shared/feature/auth/*/domain shared/feature/auth/*/presentation || true"
    severity: error
    rationale: "FirebaseAuthException não pode vazar para domain/ ou presentation/."
```

### 4. Gates por tipo de task

| Categoria de task | Gates obrigatórios |
|---|---|
| `data-service` (cria/edita `*Service.kt` de auth) | unit tests + `auth-test-ids-canonical` + `firebase-auth-exception-not-leaked` |
| `data-mapper` (cria/edita `Auth*Mapper.kt`) | unit tests cobrindo todos os `errorCode` da tabela de mapping |
| `analytics-tracker` (cria/edita trackers nativos) | `auth-analytics-events-canonical` + verificar paridade Android↔iOS |
| `ui-screen` (cria/edita Login/Register screens) | `auth-test-ids-canonical` + visual regression se configurado |

### 5. Ordem sugerida de tasks em features de auth

1. `TASK-AUTH-001-domain-model` — `UserSession`, `AuthDomainError` em `domain/model/`
2. `TASK-AUTH-002-service-interface` — `AuthService` interface em `data/service/`
3. `TASK-AUTH-003-firebase-service-impl` — `FirebaseAuthService` + DI Android (`@Single` no `@Module`)
4. `TASK-AUTH-004-mapper` — `AuthMapper` com cobertura de todos os codes
5. `TASK-AUTH-005-repository` — `AuthRepository` interface + `AuthRepositoryImpl`
6. `TASK-AUTH-006-usecases` — `SignInWithEmailUseCase`, `RegisterUseCase`, etc.
7. `TASK-AUTH-007-analytics-exception` — `FirebaseAuthAnalyticsException` para Crashlytics (quando o card `firebase-crashlytics` está ativo)
8. `TASK-AUTH-008-ios-factory` — `createAuthService()` em `di/AuthFactory.kt`
9. `TASK-AUTH-009-viewmodel` — `LoginViewModel` / `RegisterViewModel` consumindo UseCases
10. `TASK-AUTH-010-screens-android` + `TASK-AUTH-011-screens-ios` — UI nativa

Ordem específica pode mudar conforme PRD; ordem domínio → data → presentation é regra dura.
