# firebase-crashlytics

Card canônico para **Firebase Crashlytics** como provedor de crash reporting
+ non-fatal exceptions em projetos KMP (Kotlin Multiplatform) com targets
Android e iOS.

## O que este card resolve

Crash reporting cru (capturar `Throwable` que escapa) é fácil. O que distingue
um projeto maduro é o tratamento de **non-fatal exceptions** — falhas que não
crasham o app mas representam degradação observável (erro de auth, falha de
upload, validação remota inesperada).

Sem disciplina, cada feature inventa:

- Seu próprio shape de payload (`"register_error" + e.message` vs
  `"register_error" + errorCode`).
- Sua própria classe de exceção (uma no Android, outra no Swift).
- Sua própria estratégia de quando reportar (só catch genérico vs catch
  granular por causa).

O resultado: dashboards de Crashlytics intraváveis, paridade Android↔iOS
quebrada, e impossibilidade de filtrar non-fatals por `errorCode` ou
`causeType` no console.

Este card impõe um **padrão único cross-feature**: uma exception class
compartilhada em `commonMain` por feature, com `errorCode` + `causeType`,
consumida igual nos dois lados.

## Padrão canônico — exception class compartilhada

Toda feature que dispara evento analytics terminando em `_error` precisa de
uma exception class no shared layer:

```
shared/feature/{feature}/.../analytics/Firebase{Feature}AnalyticsException.kt
```

Forma canônica:

```kotlin
class Firebase{Feature}AnalyticsException(
    val errorCode: String,
    val causeType: String,
    cause: Throwable? = null,
) : Throwable(message = "$errorCode/$causeType", cause = cause)
```

Referência viva no MeoBonsai:
`shared/feature/auth/.../analytics/FirebaseAuthAnalyticsException.kt`.

## Como o evento `*_error` consome o pattern

Cada vez que o tracker da feature loga um evento de falha:

```kotlin
analytics.logEvent(
    AuthAnalytics.Events.REGISTER_ERROR,
    mapOf(
        AuthAnalytics.Params.ERROR_CODE to "auth/email-already-in-use",
        AuthAnalytics.Params.CAUSE_TYPE to "firebase_auth",
    ),
)

Firebase.crashlytics.recordException(
    FirebaseAuthAnalyticsException(
        errorCode = "auth/email-already-in-use",
        causeType = "firebase_auth",
        cause = originalThrowable,
    ),
)
```

Regras:

1. Evento analytics e `recordException` carregam **o mesmo** par
   `(errorCode, causeType)` — não há "split-brain" entre dashboards.
2. A exception class vive no shared (`commonMain`) e é consumida igual no
   Android e via SKIE no iOS — não há duas classes paralelas.
3. `cause: Throwable?` opcional preserva o stack original quando disponível
   (Firebase, Ktor, etc.).
4. Crashes fatais (não vindos de evento `_error`) continuam sendo reportados
   automaticamente pelo SDK do Crashlytics — este card não toca nesse caminho.

## Conflitos

Este card declara `provides: crash-reporting`. Qualquer outro provedor da
mesma capability (Sentry, Bugsnag, Datadog Crash Reporting, custom) precisa
ser removido antes de ativar este — o resolver erra em conflito explícito.

## Contribuições para o pipeline

### Agente — contract-planner-agent

Injeção em `section:Analytics Contract` (artefato `analytics-spec.yaml`):

- Regra: todo evento listado terminando em `_error` precisa de bloco
  `crashlytics:` declarando o nome canônico da exception class compartilhada
  e o par `(errorCode, causeType)`.
- Validação derivada: o validator `check-crashlytics-shared-exception.py`
  falha o gate se o artefato lista evento `*_error` sem binding.

### Agente — tech-spec-agent

Injeção em `section:Observability hooks` (artefato `tech-spec.md`):

- Estrutura física da exception class:
  `shared/feature/{feature}/src/commonMain/kotlin/.../analytics/Firebase{Feature}AnalyticsException.kt`.
- Breadcrumbs: instruções para `FirebaseCrashlytics.setCustomKey` (feature,
  userType, screen) ANTES de `recordException`, para enriquecer o card no
  console sem PII.
- Opt-out: respeitar `CrashlyticsManager.setCollectionEnabled(false)` quando
  o usuário recusa consentimento.

### Agente — task-contract-writer

Injeção em `after:Allowed Files` (artefato `tasks/TASK-NNNN.yaml`):

- Padrão de `allowed_files` para tasks que tocam analytics:
  `shared/feature/{feature}/**/analytics/Firebase{Feature}AnalyticsException.kt`
  e o respectivo `*AnalyticsImpl.kt`.
- Validation step adicional: rodar
  `python scripts/observability/check-crashlytics-binding.py {feature}` no
  gate de verify, garantindo paridade Android↔iOS.

### Templates

- `templates/crashlytics-tech-spec.md` — fragmento append-section em
  `tech-spec.md` ("Observability — Crashlytics").
- `templates/crashlytics-analytics.yaml` — merge-keys em
  `analytics-spec.yaml`, expondo o shape do bloco `crashlytics:` por evento.

### Validators

- `validators/check-crashlytics-shared-exception.py` — stub Phase 5.
  Falha se evento `*_error` em `analytics-spec.yaml` não declara binding
  para `Firebase{Feature}AnalyticsException`. Severity: `error`. Roda em
  `pre-commit` e `verify-task`.

## Detection

Auto-ativa se a soma de signals ≥ 0.5:

| Signal | Confiança |
|---|---|
| `build.gradle*` contém `firebase-crashlytics` | 0.5 |
| `build.gradle*` contém `com.google.firebase.crashlytics` (plugin) | 0.3 |
| `Package.swift` contém `FirebaseCrashlytics` | 0.3 |
| `Podfile` contém `FirebaseCrashlytics` | 0.3 |

Threshold mínimo de 0.5 cobre o caso mais comum (Android-first com
dependência declarada). iOS-only ainda pede confirmação manual.

## Convenções aplicadas via `config-defaults`

| Key | Valor |
|---|---|
| `conventions.observability.crash-reporting` | `firebase-crashlytics` |
| `conventions.observability.crashlytics-exception-pattern` | `Firebase{Feature}AnalyticsException(errorCode, causeType)` |

## Anti-patterns que este card bloqueia

- Evento `*_error` que NÃO chama `recordException` — perde non-fatal no
  console, deixa só métricas do Analytics.
- Exception class duplicada (uma `*AnalyticsException` em `androidApp/` e
  outra em `iosApp/`) — paridade quebra.
- `recordException(Throwable(e.message))` sem `errorCode/causeType` — vira
  ruído não-filtrável.
- `FirebaseCrashlytics.setCrashlyticsCollectionEnabled(true)` hard-coded —
  ignora opt-out do usuário.

## Rule link

Alinhado com `.claude/rules/observability.md` §Crashlytics do projeto
MeoBonsai (regra canônica que originou este card).
