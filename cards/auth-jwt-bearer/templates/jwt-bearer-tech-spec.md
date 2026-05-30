<!--
  Template fragment contribuído por: auth-jwt-bearer
  Target: tech-spec.md
  Merge: append-section "Auth Strategy (JWT Bearer)"

  Esta seção é appendada ao tech-spec.md quando o card auth-jwt-bearer está
  ativo. Preencha cada bloco a partir do PRD + data-contract-spec + escolha
  de storage seguro. Não deixe campo em branco — use `n/a` com justificativa
  em §13 (Risks + open questions).
-->

## Auth Strategy (JWT Bearer)

Esta seção é injetada pelo card `auth-jwt-bearer` e padroniza a camada de
autenticação via JWT Bearer Token em REST APIs.

### Endpoints REST canônicos

| Endpoint | Método | Request | Response | Notas |
|---|---|---|---|---|
| `/auth/login` | `POST` | `{ email, password }` | `{ access_token, refresh_token, expires_in }` | 200 ok, 401 invalid credentials |
| `/auth/refresh` | `POST` | `{ refresh_token }` | `{ access_token, refresh_token, expires_in }` | 200 ok, 401 refresh inválido/expirado → logout forçado |
| `/auth/logout` | `POST` | `{ refresh_token }` _(opcional)_ | `204 No Content` | Revoga refresh-token no servidor |

Endpoints e shapes exatos vêm do `data-contract-spec.yaml` da feature; este
fragmento descreve o **padrão** — o contrato manda.

### Shape do JWT (claims esperadas)

| Claim | Tipo | Obrigatório | Uso |
|---|---|---|---|
| `sub` | string | sim | User id |
| `exp` | int (epoch s) | sim | Expiration — driver do refresh proativo |
| `iat` | int (epoch s) | sim | Issued at |
| `role` / `scope` | string / array | depende | Autorização downstream |
| `iss` | string | recomendado | Validação de issuer |

Validação local do JWT é decode-only (split por `.`, base64 do payload).
**Não** verificar assinatura no client — verificação é responsabilidade do
servidor; tentativa client-side gera falso senso de segurança.

### Camada `data/` (shared, commonMain)

```
shared/feature/auth/src/commonMain/kotlin/.../feature/auth/
├── data/
│   ├── service/
│   │   ├── AuthService.kt              (interface — IO boundary)
│   │   └── AuthRestService.kt          (@Single impl — Ktor HttpClient + /auth/* endpoints)
│   ├── dto/
│   │   ├── LoginRequest.kt
│   │   ├── RefreshRequest.kt
│   │   └── TokenPairResponse.kt        (@Serializable)
│   ├── storage/
│   │   ├── TokenStorage.kt             (interface — secure storage boundary)
│   │   └── SecureTokenStorage.kt       (@Single impl — encrypted DataStore / Keystore / Keychain)
│   ├── mapper/
│   │   └── AuthErrorMapper.kt          (HTTP status + body → AuthDomainError)
│   └── repository/
│       └── AuthRepositoryImpl.kt
└── domain/
    ├── model/
    │   ├── UserSession.kt
    │   ├── TokenPair.kt
    │   └── AuthDomainError.kt          (sealed class — códigos canônicos)
    ├── repository/
    │   └── AuthRepository.kt
    └── usecase/
        ├── LoginUseCase.kt
        ├── LogoutUseCase.kt
        ├── RefreshTokenUseCase.kt
        └── ObserveAuthStateUseCase.kt
```

### Ktor Auth plugin — config canônica

O interceptor de Authorization header + refresh automático é instalado no
`HttpClient` do card `ktor-client`. **Não** escreva interceptor manual.

```kotlin
HttpClient(engine) {
    install(Auth) {
        bearer {
            loadTokens {
                val pair = tokenStorage.read() ?: return@loadTokens null
                BearerTokens(pair.accessToken, pair.refreshToken)
            }

            refreshTokens {
                val current = tokenStorage.read() ?: return@refreshTokens null
                val refreshed = authRestService.refresh(current.refreshToken)
                tokenStorage.write(refreshed)
                BearerTokens(refreshed.accessToken, refreshed.refreshToken)
            }

            sendWithoutRequest { request ->
                request.url.encodedPath.startsWith("/auth/login").not()
                    && request.url.encodedPath.startsWith("/auth/refresh").not()
            }
        }
    }
}
```

- `loadTokens` é chamado uma vez para popular o cache do plugin.
- `refreshTokens` é chamado automaticamente em resposta `401` — Ktor faz o
  retry da request original com o novo access-token.
- `sendWithoutRequest` evita anexar o header nos endpoints públicos
  (`/auth/login`, `/auth/refresh`) — caso contrário o servidor pode rejeitar.

### Storage seguro do refresh-token

| Plataforma | Storage canônico |
|---|---|
| Android | `EncryptedDataStore` (Tink-backed) OU `EncryptedSharedPreferences` (AndroidX Security) — **nunca** SharedPreferences plain |
| iOS | Keychain Services (via shim em `expect/actual` ou KMP wrapper) — **nunca** UserDefaults |
| Web | `HttpOnly Secure` cookie set pelo backend (preferido) OU `sessionStorage` apenas para access-token de curta duração — **nunca** localStorage |

`TokenStorage` é interface no shared; impl é platform-specific via
`expect/actual` ou DI por factory (`SecureTokenStorageAndroid`,
`SecureTokenStorageIOS`, `SecureTokenStorageWeb`).

Validator `check-no-plaintext-token-storage.py` bloqueia pre-commit /
`forge verify` quando detecta token salvo em storage não seguro.

### Mapeamento de erros REST → AuthDomainError

`AuthErrorMapper` traduz status HTTP + payload em `AuthDomainError`:

| HTTP | Endpoint | `AuthDomainError` |
|---|---|---|
| 200 | `/auth/login` | n/a (`UserSession`) |
| 400 | `/auth/login` | `InvalidPayload` (form inválido) |
| 401 | `/auth/login` | `InvalidCredentials` |
| 401 | qualquer (após refresh falhar) | `SessionExpired` → logout forçado |
| 403 | qualquer | `Forbidden` |
| 5xx | qualquer | `ServerUnavailable` |
| network failure | qualquer | `NetworkUnavailable` |

`HttpClient` exceptions (`ResponseException`, `IOException`) **nunca** vazam
para `domain/` ou `presentation/` — o mapper traduz na fronteira.

### DI por plataforma

| Plataforma | Padrão |
|---|---|
| Android | `@Single AuthRestService`, `@Single SecureTokenStorageAndroid`, `@Single AuthRepositoryImpl` via Koin Annotations (`@Module @ComponentScan` em `auth/data/`). |
| iOS | Factory functions em `auth/di/AuthFactory.kt`: `createAuthService()`, `createTokenStorage()`, `createAuthRepository()`. Koin runtime é JVM-only. |
| Web | Mesmo padrão iOS. Token storage Web usa cookie HttpOnly quando possível. |

### Threading / dispatchers

Toda chamada Ktor + acesso a storage criptografado roda em `Dispatchers.IO`
via `withContext(io)`. `Dispatchers.IO` é **injetado** no construtor —
nunca hardcoded — para permitir teste com `UnconfinedTestDispatcher`.

### Logout — limpeza obrigatória

`LogoutUseCase` deve:

1. Chamar `POST /auth/logout` com o refresh-token (best-effort — falha de
   rede não bloqueia o logout local).
2. Limpar `TokenStorage` (`tokenStorage.clear()`).
3. Cancelar streams de `observeSession()` ativos.
4. Emitir `UserSession.SignedOut` no `StateFlow` do auth.

Resíduo de token após logout é bug grave — cobertura de teste obrigatória.

### State management

Estado da tela segue o contrato canônico do shared:
`MutableStateFlow<StateUI<AuthUI>>` com `Idle | Processing | Processed<T> | Error`.
Eventos one-shot (navegação após login, toast de erro) vão como **campos no
UI state** consumidos e limpos pela UI.

### Anti-patterns (bloqueados por validator ou code review)

- Refresh-token salvo em `SharedPreferences` plain / `UserDefaults` plain /
  `localStorage` (validator bloqueia)
- Interceptor manual de Authorization header em vez do Ktor Auth plugin
- Decode + validação de assinatura do JWT no client
- `HttpClient` `ResponseException` vazando para `domain/` ou
  `presentation/`
- Endpoint `/auth/refresh` chamado sem `sendWithoutRequest` → loop infinito
  de refresh em caso de 401
- `runBlocking` envolvendo `authService.login(...)` (Main thread freeze)
