<!--
  Injetado em: tech-spec-agent
  Extension-point: section:Data layer
  Card: auth-jwt-bearer

  Wave C do forge plan. O tech-spec-agent produz tech-spec.md. Quando este
  card está ativo, estas orientações se aplicam à §Data layer (e à
  subseção "Auth Strategy (JWT Bearer)" appendada via template).
-->

## auth-jwt-bearer — orientações para `tech-spec.md > Data layer`

### 1. Service como IO boundary

Toda interação com a API de auth passa por `data/service/AuthService.kt`
(interface) + `AuthRestService.kt` (implementação Ktor). Nenhuma outra
classe — UseCase, Repository, ViewModel, Compose, SwiftUI — pode importar
`io.ktor.client.*` direto.

```kotlin
interface AuthService {
    suspend fun login(email: String, password: String): TokenPair
    suspend fun refresh(refreshToken: String): TokenPair
    suspend fun logout(refreshToken: String)
}
```

Por quê: troca de provider (auth0, supabase, OAuth2) afeta apenas este
arquivo + storage. Domain e UI não precisam saber.

### 2. Ktor Auth plugin é a única forma de anexar Authorization header

Não escrever interceptor manual. O plugin oficial
(`io.ktor.client.plugins.auth`) faz:

- `loadTokens { ... }` na primeira request — popula cache.
- `refreshTokens { ... }` em qualquer 401 — refresh + retry automáticos.
- `sendWithoutRequest { ... }` exclui `/auth/login` e `/auth/refresh` do
  header (evita rejeição do servidor e loops infinitos de refresh).

Tech-spec deve referenciar o snippet do template como verdade canônica e
listar quais endpoints da feature são "públicos" (sem header).

### 3. TokenStorage é boundary obrigatório de storage seguro

| Plataforma | Implementação canônica |
|---|---|
| Android | `EncryptedDataStore` (Tink) OU `EncryptedSharedPreferences` (AndroidX Security) |
| iOS | Keychain Services (shim `expect/actual` ou wrapper KMP) |
| Web | Cookie `HttpOnly Secure` setado pelo backend (preferido); fallback `sessionStorage` apenas para access-token efêmero |

Anti-padrões absolutos:

- `SharedPreferences` plain
- `UserDefaults` plain
- `localStorage` no Web
- Arquivo texto em disco

O validator `check-no-plaintext-token-storage.py` bloqueia commit / verify
quando detecta esses anti-padrões. Tech-spec deve declarar **qual** das
opções canônicas a feature usa.

### 4. Refresh strategy — reactive (401) vs proactive (exp)

O default é **reactive**: o Ktor Auth plugin dispara `refreshTokens` em
resposta `401`. Esse é o caminho padrão.

**Proactive refresh** (refresh antes de `exp` para reduzir latência da
primeira request) é opcional e só vale a pena quando:

- O backend lista o `expires_in` no payload e o app tem uma janela longa
  entre login e primeira request autenticada.
- O custo de um round-trip extra é mensurável e o PRD pede.

Quando proativo, fazer no `AuthRepository` (Job em `viewModelScope` ou
`applicationScope`) — não no Service. Service só responde a chamadas.

### 5. Mapping HTTP → AuthDomainError

`AuthDomainError` é sealed class em `domain/model/`:

```kotlin
sealed class AuthDomainError {
    data object InvalidCredentials : AuthDomainError()
    data object InvalidPayload : AuthDomainError()
    data object SessionExpired : AuthDomainError()
    data object Forbidden : AuthDomainError()
    data object ServerUnavailable : AuthDomainError()
    data object NetworkUnavailable : AuthDomainError()
    data class Unknown(val status: Int, val code: String?) : AuthDomainError()
}
```

`AuthErrorMapper` mora em `data/mapper/`. Não é permitido `ResponseException`
cruzar a fronteira `data → domain`.

### 6. Logout limpa storage E cancela streams

Bug clássico: logout local não revoga refresh-token no servidor → token
ainda válido até `exp`. `LogoutUseCase` chama `/auth/logout` best-effort
(falha de rede não bloqueia logout local), depois `tokenStorage.clear()`
e emite `UserSession.SignedOut`. Coleta de `observeSession()` ativos deve
encerrar — usar `Flow` que reflete o estado do `TokenStorage`.

Cobertura de teste obrigatória:

- `LogoutUseCaseTest` com fake Service que retorna 200 — verifica clear.
- `LogoutUseCaseTest` com fake Service que retorna IOException — verifica
  clear mesmo assim.
- `LogoutUseCaseTest` verifica que o próximo `observeSession()` emite
  `SignedOut`.

### 7. DI por plataforma

| Plataforma | Padrão |
|---|---|
| Android | `@Single AuthRestService`, `@Single SecureTokenStorageAndroid`, `@Single AuthRepositoryImpl` via Koin Annotations (`@Module @ComponentScan` em `auth/data/`). |
| iOS | Factory functions em `auth/di/AuthFactory.kt`: `createAuthService()`, `createTokenStorage()`, `createAuthRepository()`. Koin runtime é JVM-only. |
| Web | Mesmo padrão iOS — `createAuthService()`, etc. |

`HttpClient` configurado com `Auth` plugin vem do card `ktor-client` —
**não** criar um `HttpClient` paralelo só para auth.

### 8. Dispatcher injection

`AuthRestService` e `SecureTokenStorage` recebem `CoroutineDispatcher` no
construtor (default `Dispatchers.IO`). Toda call Ktor + acesso a storage
criptografado roda em `withContext(io)`. Teste com `UnconfinedTestDispatcher`.

### 9. Observable session state

`AuthRepository.observeSession(): Flow<UserSession>` é o stream canônico.
Implementação reage a mudanças no `TokenStorage` (presença ou ausência de
refresh-token válido). Consumidores:

- Android: `viewModelScope.launch { observeSession().collect { ... } }`
- iOS (via SKIE): `.task { for await session in repo.observeSession() { ... } }`
- Web: `useStateFromFlow(observeSession())`

`StateFlow` derivado em ViewModels usa
`SharingStarted.WhileSubscribed(5_000)`.

### 10. Paridade Android ↔ iOS

Todo o flow de auth vive no shared (`commonMain`). Plataforma só fornece o
shim de storage seguro (`expect/actual`). Tech-spec deve declarar
explicitamente que **não há código de auth duplicado** em Android ou iOS —
qualquer divergência é bug.

### 11. Testes obrigatórios na camada `data/`

- `AuthRestServiceTest` com `MockEngine` do Ktor cobrindo:
  - 200 em `/auth/login` → `TokenPair` correto
  - 401 em `/auth/login` → exception traduzida pelo mapper
  - 200 em `/auth/refresh` → novo `TokenPair`
  - 401 em `/auth/refresh` → `SessionExpired`
- `AuthErrorMapperTest` cobrindo todos os status da tabela de mapping.
- `SecureTokenStorageTest` (fake/in-memory no commonTest, real na
  plataforma) verificando read/write/clear.
- `AuthRepositoryImplTest` happy path + cada `AuthDomainError`.
