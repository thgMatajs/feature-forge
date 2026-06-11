<!--
  Template fragment contribuído por: firebase-auth
  Target: tech-spec.md
  Merge: append-section "Auth Strategy (Firebase)"

  Esta seção é appendada ao tech-spec.md quando o card firebase-auth está
  ativo. Preencha os blocos com base no PRD + data-contract-spec + ambiente
  do projeto. Não deixe campo em branco — use `n/a` com justificativa em §13
  (Risks + open questions).
-->

## Auth Strategy (Firebase)

Esta seção é injetada pelo card `firebase-auth` e padroniza a camada de
autenticação da feature.

### Provedor + ambientes

| Item | Decisão | Onde vive |
|---|---|---|
| Provedor de auth | Firebase Authentication | `data/service/AuthService.kt` |
| Métodos suportados | Email/Password (default) + provedores OAuth quando o PRD pedir | declarar em §11 (BDD) |
| Project ID — dev | `<dev-project-id>` (ex.: `bonsai-meo-dev`) | configs gitignored |
| Project ID — prod | `<prod-project-id>` (ex.: `bonsai-meo`) | configs gitignored |
| Android config dev | `composeApp/src/debug/google-services.json` | gitignored |
| Android config prod | `composeApp/src/release/google-services.json` | gitignored |
| iOS config dev | `iosApp/iosApp/Config/Dev/GoogleService-Info.plist` | gitignored |
| iOS config prod | `iosApp/iosApp/Config/Prod/GoogleService-Info.plist` | gitignored |

### Camada `data/` (shared, commonMain)

```
shared/feature/auth/src/commonMain/kotlin/.../feature/auth/
├── data/
│   ├── service/
│   │   ├── AuthService.kt            (interface — IO boundary)
│   │   └── FirebaseAuthService.kt    (@Single impl — chama Firebase Auth)
│   ├── dto/
│   │   └── AuthUserResponse.kt       (@Serializable — wire para token claims)
│   ├── mapper/
│   │   └── AuthMapper.kt             (FirebaseAuthException → AuthDomainError)
│   ├── repository/
│   │   └── AuthRepositoryImpl.kt     (@Single — usa AuthService)
│   └── analytics/
│       └── FirebaseAuthAnalyticsException.kt   (paridade Crashlytics)
└── domain/
    ├── model/
    │   ├── UserSession.kt
    │   └── AuthDomainError.kt        (sealed class — códigos canônicos)
    ├── repository/
    │   └── AuthRepository.kt          (interface)
    └── usecase/
        ├── SignInWithEmailUseCase.kt
        ├── RegisterUseCase.kt
        ├── SignOutUseCase.kt
        └── ObserveAuthStateUseCase.kt
```

### Mapeamento de erros

`FirebaseAuthException` (provider-specific) **nunca** vaza para `domain/`
ou `presentation/`. Mapper canônico em `data/mapper/AuthMapper.kt`:

| `FirebaseAuthException.errorCode` | `AuthDomainError` |
|---|---|
| `ERROR_INVALID_EMAIL` | `InvalidEmail` |
| `ERROR_WRONG_PASSWORD` | `InvalidCredentials` |
| `ERROR_USER_NOT_FOUND` | `InvalidCredentials` |
| `ERROR_EMAIL_ALREADY_IN_USE` | `EmailAlreadyInUse` |
| `ERROR_WEAK_PASSWORD` | `WeakPassword` |
| `ERROR_NETWORK_REQUEST_FAILED` | `NetworkUnavailable` |
| _qualquer outro_ | `Unknown(errorCode)` |

### DI por plataforma

| Plataforma | Padrão |
|---|---|
| Android | `@Single FirebaseAuthService` + `@Single AuthRepositoryImpl` via Koin Annotations (`@Module @ComponentScan` no pacote `auth/data/`). |
| iOS | Factory function `createAuthService(): AuthService` em `auth/di/AuthFactory.kt`. iOS instancia diretamente — sem Koin runtime. |
| Web | Mesmo padrão iOS: `createAuthService()` (`@JsExport`-friendly se necessário). |

### Threading / dispatchers

Toda chamada Firebase Auth roda em `Dispatchers.IO` via `withContext(io)`
no `FirebaseAuthService`. `Dispatchers.IO` é **injetado** no construtor —
nunca hardcoded — para permitir teste com `UnconfinedTestDispatcher`.

### Observability — paridade obrigatória

- **Test IDs:** consumir de `shared:core/observability/AuthTestIds.kt`
  (`AuthTestIds.Login.SUBMIT`, `AuthTestIds.Register.FIELD_PASSWORD`).
  Hardcoded test_id em código de auth é bloqueado pelo validator
  `check-auth-test-ids-canonical.py`.
- **Analytics events:** consumir de
  `shared:core/observability/AuthAnalytics.kt` (`AuthAnalytics.Events.LOGIN_ATTEMPT`,
  `AuthAnalytics.Params.ERROR_CODE`). Naming: `<feature>_<verb>_<outcome>`.
- **Crashlytics:** quando o card `firebase-crashlytics` está ativo, eventos
  `*_error` chamam `Firebase.crashlytics.recordException(
  FirebaseAuthAnalyticsException(errorCode, causeType))`. A classe vive em
  `shared/feature/auth/.../data/analytics/FirebaseAuthAnalyticsException.kt`
  para garantir paridade Android↔iOS.

### State management

Estado da tela de auth segue o contrato canônico do shared:
`MutableStateFlow<StateUI<AuthUI>>` onde `StateUI` é
`Idle | Processing | Processed<T> | Error`. Eventos one-shot (navegação,
toast) vão como **campos no UI state** consumidos e limpos pela UI.

### Anti-patterns (bloqueados por validator ou code review)

- `FirebaseAuthException` exposta para `domain/` ou `presentation/`
- Test ID hardcoded em código de auth (validator bloqueia)
- Wrapper manual `suspend → async` no iOS (SKIE faz automaticamente)
- `@KoinViewModel` no iOS (Koin é JVM-only — factory function)
- Configs Firebase versionados no Git (gitignored sempre)
