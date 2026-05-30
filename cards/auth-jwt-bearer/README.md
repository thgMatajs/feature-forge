# Card — `auth-jwt-bearer`

> Autenticação via **JWT Bearer Token em REST APIs**. Provê o capability
> singular `auth-provider` (e o auxiliar `auth-token-bearer`) no grafo do
> feature-forge. Padroniza o flow `login → access-token + refresh-token`,
> usa o **Ktor Auth plugin** (`loadTokens` / `refreshTokens`) para anexar
> o header Authorization e fazer refresh automático em 401, e exige
> **storage seguro** do refresh-token (encrypted DataStore, Android
> Keystore, iOS Keychain ou cookie HttpOnly Secure).

- **Categoria:** `backend`
- **Maturidade:** `stable`
- **Provides:** `auth-provider` (singular), `auth-token-bearer` (auxiliar)
- **Requires:** `http-client`
- **Conflicts-with:** `auth-provider` (qualquer outro provedor de identidade — `firebase-auth`, `auth0`, `supabase-auth`, `clerk-auth`)

## Quando este card é ativado

`forge init` ativa `auth-jwt-bearer` quando a soma de confidence dos
signals abaixo é maior ou igual a `0.5`:

| Sinal | Confidence | Por quê |
|---|---|---|
| `Bearer ` em `**/*.kt` | 0.3 | String literal usada em headers HTTP Authorization |
| `Authorization` em `**/auth/**/*.kt` | 0.3 | Header referenciado dentro de pacote auth/ — evidência de flow manual ou Ktor Auth plugin |
| `RefreshToken` em `**/*.kt` | 0.3 | Símbolo (classe/função) — vocabulário específico de JWT, ausente em Firebase Auth no shared |
| `JWT` em `**/*.kt` | 0.2 | Menção a JSON Web Token — confidence baixo isolado |
| `io.ktor.client.plugins.auth` em `**/*.kt` | 0.2 | Import do plugin oficial Ktor Auth |

Se a soma cair em `[0.3, 0.5)`, o forge pergunta confirmação ao usuário.
Abaixo de 0.3, o card não é ativado.

## Capability + conflitos

`auth-jwt-bearer` provê duas labels do catálogo v1
(`docs/schemas/capability-labels.md`):

- `auth-provider` (**singular**) — provedor de identidade canônico; apenas
  1 por projeto. O campo `conflicts-with: [auth-provider]` garante que
  ativar este card requer remover qualquer provedor incumbente
  (`firebase-auth`, futuramente `auth0`, `supabase-auth`, `clerk-auth`).
- `auth-token-bearer` (**auxiliar**) — flow Bearer JWT/OAuth. Mesma label
  também é provida por `firebase-auth`; cards que dependem apenas do flow
  (analytics, retry policy genérica) podem `requires: auth-token-bearer`
  sem amarrar provedor.

Este card requer `http-client` — auth via REST não funciona sem o
`HttpClient` cross-platform onde o **Ktor Auth plugin** é instalado.

## O que este card contribui

### 1. Template — seção "Auth Strategy (JWT Bearer)" em `tech-spec.md`

`templates/jwt-bearer-tech-spec.md` é appendado ao `tech-spec.md` da
feature quando o card está ativo. Documenta:

- Endpoints REST canônicos `/auth/login`, `/auth/refresh`, `/auth/logout`
  com shapes de request/response e códigos de erro.
- Claims esperadas do JWT (`sub`, `exp`, `iat`, opcionais `role`, `scope`,
  `iss`) e regra explícita "decode-only no client — assinatura é validada
  no servidor".
- Estrutura de pastas `data/service/`, `data/storage/`, `data/mapper/`,
  `domain/model/`, `domain/usecase/` em `shared/feature/auth/commonMain`.
- Snippet canônico do Ktor `Auth { bearer { loadTokens / refreshTokens /
  sendWithoutRequest } }`.
- Tabela de mapping HTTP → `AuthDomainError`.
- Storage seguro por plataforma (Android: EncryptedDataStore /
  EncryptedSharedPreferences; iOS: Keychain; Web: cookie HttpOnly Secure).
- Regras de logout (revogar no servidor + clear local + cancelar streams).

### 2. Validator — `check-no-plaintext-token-storage.py`

Bloqueia pre-commit / `forge verify` quando código de auth tenta salvar
refresh-token ou access-token em storage **não seguro**:

- `SharedPreferences` plain (Android)
- `UserDefaults` plain (iOS)
- `localStorage` (Web)
- Arquivo texto em disco

Stub Phase 5 (no-op retornando sucesso) — implementação completa cobrirá
regex Kotlin/Swift/TS, allowlist de classes `Encrypted*` / `Secure*` /
`Keychain*` / `Keystore*`, modos `--staged` e `--branch`.

### 3. Prompts injetados nos agentes

| Agente | Extension-point | Conteúdo |
|---|---|---|
| `tech-spec-agent` | `section:Data layer` | Service como IO boundary, Ktor Auth plugin como única forma de anexar header, TokenStorage como boundary de storage seguro, refresh strategy reativo vs proativo, mapping HTTP → AuthDomainError, regras de logout, DI por plataforma, dispatcher injection, observable session, paridade Android↔iOS, testes obrigatórios. |
| `contract-planner-agent` | `section:data-contract` | Endpoints `/auth/*` declarados com `auth: public \| bearer`, shape do JWT com claims obrigatórias, error mapping HTTP → domain, refresh-token rotation policy (rotation / one-time-use / absolute-lifetime / reuse-detection). |
| `task-contract-writer` | `after:Allowed Files` | Globs auth (`**/data/service/AuthService.kt`, `**/data/storage/SecureTokenStorage*.kt`, `**/domain/usecase/LoginUseCase.kt`, etc.), denied_files (`**/.env*`, `SharedPreferencesTokenStorage*.kt`), validations (no-plaintext-token-storage, no-manual-authorization-interceptor, ktor-exception-not-leaked, jwt-signature-not-validated-on-client), ordem sugerida domain → data → presentation. |

### 4. Config defaults

- `conventions.auth.provider: "auth-jwt-bearer"` — provedor de auth ativo.
- `conventions.auth.token-storage: "encrypted-datastore OR android-keystore"`
  — storage seguro padrão; agentes downstream podem ajustar via
  `forge reconfigure`.
- `conventions.auth.refresh-strategy: "ktor-auth-plugin-refresh-tokens"`
  — refresh reativo em 401 via plugin oficial é o default.

## Exemplo — Ktor Auth plugin (config canônica)

O snippet abaixo vive em `shared/core/.../network/HttpClientFactory.kt`
e é a **única** forma autorizada de anexar Authorization header. Validators
falham em interceptor manual:

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

Pontos críticos:

- **`refreshTokens`** roda automaticamente em qualquer resposta 401 — Ktor
  retenta a request original com o novo access-token, sem código
  adicional no UseCase / Repository.
- **`sendWithoutRequest`** exclui `/auth/login` e `/auth/refresh` do header.
  Sem essa exclusão, o plugin tentaria refresh em loop quando o próprio
  endpoint de refresh responde 401.
- **Persistência** acontece dentro de `refreshTokens` — `tokenStorage.write(...)`
  garante que o novo refresh-token sobrescreve o antigo (rotation).

## Integração com outros cards

| Combina com | Efeito |
|---|---|
| `ktor-client` | Dependência hard — `HttpClientFactory` instala o Auth plugin no `HttpClient` canônico. Card não funciona sem ele. |
| `rest-api-contract` | Endpoints `/auth/*` seguem o padrão REST do contract; auth requirement (`public` / `bearer`) declarado por endpoint. |
| `kotlinx-serialization-json` | DTOs `LoginRequest`, `RefreshRequest`, `TokenPairResponse` são `@Serializable`. |
| `kmp-shared` | Todo o flow vive em `commonMain`; plataforma só fornece shim de storage seguro via `expect/actual`. |
| `koin-annotations` | `@Single AuthRestService`, `@Single SecureTokenStorageAndroid`, `@Single AuthRepositoryImpl` no Android. |
| `skie-bridge` | `Flow<UserSession>` no shared vira `AsyncSequence` no Swift via SKIE — sem wrappers manuais. |
| `datastore-prefs` | Pode prover `EncryptedDataStore` para `SecureTokenStorageAndroid` quando ambos os cards estão ativos. |

## Como usar localmente

1. **Detecção:** `forge init` ativa automaticamente quando os signals batem
   em ≥ 0.5.
2. **Manual:** `forge reconfigure` → menu "adicionar card" → `auth-jwt-bearer`.
   Se `firebase-auth` estiver ativo, o forge exige remoção primeiro
   (conflito em `auth-provider`).
3. **Inspeção:** `forge reconfigure` → menu "inspecionar card" mostra
   sha256, conflitos resolvidos e contribuições mergeadas.

## Limites declarados

- Este card **não** prescreve UI de auth (login/logout screens) — UI fica
  no card de UI ativo (`compose-screens`, `swiftui-screens`).
- Este card **não** gera código — apenas contribui contratos, templates e
  validators. Implementação concreta é responsabilidade dos agentes
  downstream (`tech-spec-agent`, `task-contract-writer`, `sprint-executor`).
- Este card **não** valida assinatura do JWT no client. A regra é
  decode-only no client; o servidor é a autoridade. Tentativa de
  validar assinatura no client é antipadrão bloqueado pelo validator
  `jwt-signature-not-validated-on-client`.
- Este card **não** lida com OAuth2 completo (authorization code, PKCE,
  consent screens) — `auth-oauth2-rest` é a label reservada para v1.1.
  Este card cobre apenas o flow Bearer JWT direto (login + refresh +
  logout) contra backend próprio.

## Como o card se conecta ao catálogo de capability labels

Provê:

- `auth-provider` — singular (catalog: linha 90 de `capability-labels.md`).
- `auth-token-bearer` — auxiliar (catalog: linha 91); convive com
  `firebase-auth` que também provê (em projetos diferentes — `auth-provider`
  garante exclusão mútua).

Requer:

- `http-client` — singular (catalog: linha 71). Em v1 é provido apenas por
  `ktor-client`.

Conflita com: qualquer card que provê `auth-provider`.

## Roadmap

- **Phase 5:** implementar `check-no-plaintext-token-storage.py`
  (atualmente stub retornando 0). Implementação completa cobrirá regex
  Kotlin/Swift/TS, allowlist de classes `Encrypted*` / `Secure*` /
  `Keychain*`, modos `--staged` e `--branch`, JSON summary para o forge.
- **v1.1:** adicionar fragmento de `test-strategy.yaml` com cobertura
  mínima obrigatória para `AuthRestService` (MockEngine), `AuthErrorMapper`
  (todos os status) e `LogoutUseCase` (clear em happy + failure path).
- **v1.1:** signal extra para detectar refresh-token rotation no servidor
  (mock de response em testes) e warning quando o contrato declara
  `rotation: false`.
- **v1.2:** card complementar `auth-oauth2-rest` (label reservada) cobrindo
  authorization code + PKCE + consent screens, com este card como peer.
