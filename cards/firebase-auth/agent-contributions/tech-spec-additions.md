<!--
  Injetado em: tech-spec-agent
  Extension-point: section:Data layer
  Card: firebase-auth

  Wave C do forge plan. O tech-spec-agent produz tech-spec.md. Quando este
  card está ativo, estas orientações são aplicadas à §Data layer (e à
  subseção "Auth Strategy (Firebase)" appendada via template).
-->

## firebase-auth — orientações para `tech-spec.md > Data layer`

### 1. Service como IO boundary

Toda interação com Firebase Authentication passa por
`data/service/AuthService.kt` (interface) + `FirebaseAuthService.kt`
(implementação). Nenhuma outra classe — UseCase, Repository, ViewModel —
pode importar `dev.gitlive.firebase.auth.*` ou
`com.google.firebase.auth.*` direto.

```kotlin
interface AuthService {
    suspend fun signInWithEmail(email: String, password: String): UserSession
    suspend fun register(email: String, password: String): UserSession
    suspend fun signOut()
    fun observeSession(): Flow<UserSession?>
}
```

Por quê: troca de provedor (Auth0, Supabase) afeta apenas este arquivo.

### 2. DI por plataforma

| Plataforma | Padrão |
|---|---|
| Android (Koin Annotations) | `@Single FirebaseAuthService` no pacote `auth/data/` coberto por `@Module @ComponentScan`. |
| iOS | Factory function `createAuthService(): AuthService` em `auth/di/AuthFactory.kt`. iOS chama no app entry. |
| Web | Mesmo padrão iOS: `createAuthService()` com possível `@JsExport` no entry point conforme `architecture_web.md`. |

Koin runtime é JVM-only — **nunca** rodar Koin no iOS/Web.

### 3. Mapping FirebaseAuthException → AuthDomainError

`AuthDomainError` é sealed class em `domain/model/`:

```kotlin
sealed class AuthDomainError {
    data object InvalidEmail : AuthDomainError()
    data object InvalidCredentials : AuthDomainError()
    data object EmailAlreadyInUse : AuthDomainError()
    data object WeakPassword : AuthDomainError()
    data object NetworkUnavailable : AuthDomainError()
    data class Unknown(val code: String) : AuthDomainError()
}
```

Mapper canônico em `data/mapper/AuthMapper.kt`. `FirebaseAuthException`
não cruza a fronteira `data → domain`.

### 4. Crashlytics binding via FirebaseAuthAnalyticsException

Quando o card `firebase-crashlytics` está ativo:

- Toda emissão de evento `*_error` (definida em `analytics-spec.yaml`)
  deve, no mesmo bloco, chamar
  `Firebase.crashlytics.recordException(FirebaseAuthAnalyticsException(errorCode, causeType))`.
- A classe vive em
  `shared/feature/auth/.../data/analytics/FirebaseAuthAnalyticsException.kt`
  e é compartilhada entre Android e iOS (paridade obrigatória — o teste de
  contrato em shared garante).
- Quando o card `firebase-crashlytics` está inativo, omita a chamada
  `recordException` — apenas log de analytics.

### 5. Dispatcher injection

`FirebaseAuthService` recebe `CoroutineDispatcher` no construtor (default
`Dispatchers.IO`). Toda call Firebase roda em `withContext(io)` — nunca
hardcoded. Teste com `UnconfinedTestDispatcher`.

### 6. Observable session state

`observeSession(): Flow<UserSession?>` é o stream canônico de sessão
ativa. Camadas acima consomem como:

- Android: `viewModelScope.launch { observeSession().collect { ... } }`
- iOS (via SKIE): `.task { for await session in service.observeSession() { ... } }`
- Web: `useStateFromFlow(observeSession())`

`StateFlow` derivado em ViewModels usa
`SharingStarted.WhileSubscribed(5_000)`.

### 7. Configs por ambiente — declare na seção 4 do tech-spec

Tech-spec deve listar explicitamente quais arquivos de config estão em
uso (gitignored sempre):

| Ambiente | Project ID | Android | iOS | Web |
|---|---|---|---|---|
| Dev | `<dev-project-id>` | `composeApp/src/debug/google-services.json` | `Config/Dev/GoogleService-Info.plist` | `webApp/.env.development` |
| Prod | `<prod-project-id>` | `composeApp/src/release/google-services.json` | `Config/Prod/GoogleService-Info.plist` | `webApp/.env.production` |

### 8. Observability — referencie contratos canônicos

Tech-spec deve referenciar (não duplicar):

- Test IDs: `shared:core/observability/AuthTestIds.kt`
- Analytics: `shared:core/observability/AuthAnalytics.kt`
- Crashlytics: `shared/feature/auth/.../data/analytics/FirebaseAuthAnalyticsException.kt`

### 9. Testes obrigatórios na camada `data/`

- `FirebaseAuthServiceTest` com fake do GitLive Firebase shim
  (`FakeFirebaseAuth`).
- `AuthMapperTest` cobrindo todos os códigos de
  `FirebaseAuthException.errorCode` listados na tabela de mapping.
- `AuthRepositoryImplTest` cobrindo happy path + cada `AuthDomainError`.
