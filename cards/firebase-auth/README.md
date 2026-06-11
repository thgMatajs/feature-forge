# Card — `firebase-auth`

> Firebase Authentication (Email/Password + provedores OAuth) para
> Android/iOS/Web. Provê o capability singular `auth-provider` (e as
> auxiliares `auth-token-bearer` + `auth-firebase-managed`) no grafo do
> feature-forge e adiciona observability canônica (test IDs + analytics
> events) com binding opcional ao Crashlytics via
> `FirebaseAuthAnalyticsException`.

- **Categoria:** `backend`
- **Maturidade:** `stable`
- **Provides:** `auth-provider` (singular), `auth-token-bearer` (auxiliar), `auth-firebase-managed` (auxiliar)
- **Requires:** _nenhum_
- **Conflicts-with:** `auth-provider` (qualquer outro provedor de identidade)

## Quando este card é ativado

`forge init` ativa `firebase-auth` quando a soma de confidence dos signals
abaixo é maior ou igual a `0.5`:

| Sinal | Confidence | Por quê |
|---|---|---|
| `**/google-services.json` existe | 0.3 | Android config Firebase — arquivo gerado pelo console |
| `**/GoogleService-Info.plist` existe | 0.3 | iOS config Firebase |
| `firebase-auth` em `build.gradle*` | 0.5 | Dependência Gradle explícita do módulo Auth |
| `FirebaseAuth` em `Podfile*` | 0.4 | iOS via CocoaPods |
| `FirebaseAuth` em `Package.swift` | 0.4 | iOS via SwiftPM |
| `firebase-auth-ktx` em `build.gradle*` | 0.2 | Variante KTX (sinal adicional) |

Se a soma cair em `[0.3, 0.5)`, o forge pergunta confirmação ao usuário.
Abaixo de 0.3, o card não é ativado.

## Capability + conflitos

`firebase-auth` provê três labels do catálogo v1 (`docs/schemas/capability-labels.md`):

- `auth-provider` (**singular**) — provedor de identidade canônico; apenas 1 por projeto.
- `auth-token-bearer` (**auxiliar**) — Firebase Auth usa fluxo Bearer (JWT/OAuth).
- `auth-firebase-managed` (**auxiliar**) — sessão gerenciada pelo SDK Firebase.

O campo `conflicts-with: [auth-provider]` garante que apenas um provedor de
identidade pode estar ativo num projeto. Cards alternativos como `auth-jwt-bearer`
(v1, REST/JWT artesanal), `auth0`, `supabase-auth` ou `clerk-auth` (planejados)
provêem `auth-provider` e caem automaticamente neste conflito — `forge init`
exigirá remoção explícita do provedor incumbente.

> Histórico: durante a Fase 3 inicial este card declarava `auth-server`. O
> refactor Fase 3.5 splittou aquela label em `auth-provider` + `auth-token-bearer`
> + `auth-firebase-managed` para permitir coexistência com cards REST/JWT.

## O que este card contribui

### 1. Template — seção "Auth Strategy (Firebase)" em `tech-spec.md`

`templates/firebase-auth-tech-spec.md` é appendado ao `tech-spec.md` da
feature quando o card está ativo. Documenta:

- Camada `data/service/AuthService.kt` como IO boundary (chama
  `FirebaseAuth` via `expect/actual` ou GitLive shim multiplataforma).
- Mapeamento `FirebaseAuthException` → `AuthDomainError` (sealed class) com
  códigos canônicos (`invalid_credentials`, `email_already_in_use`, etc.).
- DI: `@Single` Service no shared via Koin Annotations no Android,
  `createAuthService()` factory function no iOS/Web.
- Configs por ambiente: `bonsai-meo-dev` (dev/CI) vs `bonsai-meo` (prod) —
  ver `composeApp/src/{debug,release}/google-services.json` para Android e
  `iosApp/iosApp/Config/{Dev,Prod}/GoogleService-Info.plist` para iOS.

### 2. Fragmento de analytics — `analytics-spec.yaml`

`templates/firebase-auth-analytics.yaml` é mergeado por chave no
`analytics-spec.yaml` da feature. Garante que toda feature que toca auth
declare explicitamente os eventos canônicos (`register_attempt`,
`register_error`, `login_attempt`, `login_error`, `login_validation_error`)
seguindo o naming `<feature>_<verb>_<outcome>` definido em
`shared:core/observability/AuthAnalytics.kt`.

### 3. Validator — `check-auth-test-ids-canonical.py`

Bloqueia pre-commit / `forge verify` quando código de auth contém test_id
hardcoded (ex.: `Modifier.testTag("register_field_email")`). Test IDs devem
sempre vir do contrato canônico em `shared:core/observability/AuthTestIds.kt`
para garantir paridade Android↔iOS — Android via import direto, iOS via SKIE
(`AuthTestIds.Register.shared.SUBMIT`).

### 4. Prompts injetados nos agentes

| Agente | Extension-point | Conteúdo |
|---|---|---|
| `contract-planner-agent` | `rule:error-event-binding` | Toda regra `*_error` em `analytics-spec.yaml` referente a auth deve ter bloco `crashlytics.exception_class: FirebaseAuthAnalyticsException` quando o card `firebase-crashlytics` está ativo. |
| `tech-spec-agent` | `section:Data layer` | Detalha `AuthService`/`AuthRepository`, mapping `FirebaseAuthException` → domain, DI por plataforma e ambiente dev/prod. |
| `task-contract-writer` | `after:Allowed Files` | Adiciona globs `**/feature/auth/**/data/service/*Service.kt`, `**/feature/auth/**/data/analytics/*Exception.kt` em tasks de auth. |

### 5. Config defaults

- `conventions.backend.auth: "firebase-auth"` — registrado em
  `workflow-config.yaml` para que downstream agentes saibam qual provedor
  de auth está ativo.
- `conventions.observability.auth-contracts-location: "shared:core/observability/"`
  — localização canônica dos contratos `AuthAnalytics.kt` e `AuthTestIds.kt`.

## Integração com outros cards

| Combina com | Efeito |
|---|---|
| `firebase-crashlytics` | Eventos `*_error` ganham bloco `crashlytics.exception_class` referenciando `FirebaseAuthAnalyticsException`. |
| `kmp-shared` | `AuthService` mora em `commonMain`, `expect/actual` para shim do Firebase Auth SDK (GitLive). |
| `koin-annotations` | `@Single AuthService`, `@Factory` para UseCases (`SignInWithEmailUseCase`, `RegisterUseCase`, etc.). |
| `skie-bridge` | `Flow<UserSession>` no shared vira `AsyncSequence` no Swift via SKIE — sem wrappers manuais. |

## Como usar localmente

1. **Detecção:** `forge init` ativa automaticamente quando os signals batem
   em ≥ 0.5.
2. **Manual:** `forge reconfigure` → menu "adicionar card" → `firebase-auth`.
3. **Inspeção:** `forge reconfigure` → menu "inspecionar card" mostra
   sha256, conflitos resolvidos e contribuições mergeadas.

## Exemplo de configuração por ambiente

Projetos KMP que usam este card normalmente têm dois Firebase projects —
um para desenvolvimento e CI, outro para produção. Exemplo de mapeamento:

| Ambiente | Project ID | Usado em |
|---|---|---|
| Dev | `bonsai-meo-dev` | Local dev, CI, emuladores |
| Prod | `bonsai-meo` | Release builds |

Arquivos de config são **gitignored** e gerados pelo console Firebase:

- Android: `composeApp/src/debug/google-services.json` e
  `composeApp/src/release/google-services.json`
- iOS: `iosApp/iosApp/Config/Dev/GoogleService-Info.plist` e
  `iosApp/iosApp/Config/Prod/GoogleService-Info.plist`
- Web: `webApp/.env.development` e `webApp/.env.production`

## Limites declarados

- Este card **não** prescreve UI de auth (login/registro screens) — UI fica
  no card de UI ativo (`compose-screens`, `swiftui-screens`).
- Este card **não** gera código — apenas contribui contratos, templates e
  validators. Implementação concreta é responsabilidade dos agentes
  downstream (`tech-spec-agent`, `task-contract-writer`,
  `sprint-executor`).
- Crashlytics binding é **opcional** — se o card `firebase-crashlytics` não está
  ativo, eventos `*_error` apenas logam analytics; `recordException` não é
  chamado.

## Como o card se conecta à regra de observability

O contrato canônico do card alinha-se 1:1 com `.claude/rules/observability.md`
do projeto MeoBonsai:

| Regra do projeto | Contribuição do card |
|---|---|
| "Nunca hardcode test IDs em código de feature" | Validator `check-auth-test-ids-canonical.py` bloqueia hardcode no pre-commit + verify-task. |
| "Contrato canônico em `shared:core/observability/`" | `config-defaults` registra `conventions.observability.auth-contracts-location`. |
| "Naming `<feature>_<verb>_<outcome>`" | Fragment `firebase-auth-analytics.yaml` valida o formato em todos os eventos auth. |
| "Erros `*_error` chamam `recordException(FirebaseAuthAnalyticsException)`" | Prompt do contract-planner aplica regra apenas quando o card `firebase-crashlytics` está ativo. |
| "Paridade Android↔iOS via classe compartilhada" | Allowed-files do task-writer inclui o path da exception no `shared/`, garantindo edição única. |

## Exemplo — fluxo Criar Conta (Register)

Quando uma feature de Register é planejada com este card ativo:

1. `forge plan` detecta o card via signals → ativa automaticamente.
2. `screen-analysis-agent` produz `ui-state-spec.yaml` da tela de Register.
3. `contract-planner-agent` produz `analytics-spec.yaml` referenciando
   `AuthAnalytics.Events.REGISTER_*` — string literal é proibida.
4. `tech-spec-agent` appenda a seção "Auth Strategy (Firebase)" com
   `FirebaseAuthService`, mapping de erros e DI por plataforma.
5. `task-contract-writer` decompõe em `TASK-AUTH-001..N`, cada uma com
   `allowed_files` restrito aos pacotes auth e validations específicos.
6. `forge implement` corre validators (`check-auth-test-ids-canonical.py`)
   em pre-commit e verify-task.

## Referência viva

Implementação de referência (MeoBonsai):

- Estrutura completa: `shared/feature/auth/src/commonMain/kotlin/.../feature/auth/`
- Contratos de observability: `shared/core/src/commonMain/kotlin/.../core/observability/AuthAnalytics.kt`
  e `AuthTestIds.kt`
- Crashlytics binding: `shared/feature/auth/.../data/analytics/FirebaseAuthAnalyticsException.kt`
- Regras de naming + scope: `.claude/rules/observability.md`
- Configs por ambiente (gitignored): ver tabela acima.

## Roadmap

- Phase 5: implementar `check-auth-test-ids-canonical.py` (atualmente stub
  retornando 0). Implementação completa cobrirá Android testTag, iOS
  accessibilityIdentifier, modos `--staged` e `--branch`.
- v1.1: adicionar signal extra para detectar provedores OAuth ativos
  (`google-services.json` contém `oauth_client` blocks).
- v1.2: contribuir fragmento de `test-strategy.yaml` com cobertura mínima
  obrigatória para `AuthMapper` e `FirebaseAuthService`.
