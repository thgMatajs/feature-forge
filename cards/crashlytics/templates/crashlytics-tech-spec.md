<!-- Card: crashlytics — fragment append-section em tech-spec.md -->
<!-- Target section: "Observability — Crashlytics" -->

## Observability — Crashlytics

Esta feature usa **Firebase Crashlytics** como provedor único de
crash-reporting e non-fatal exceptions. Padrão obrigatório:

### Exception class compartilhada

Definir em `commonMain`:

```
shared/feature/{feature}/src/commonMain/kotlin/.../analytics/Firebase{Feature}AnalyticsException.kt
```

Forma canônica:

```kotlin
class Firebase{Feature}AnalyticsException(
    val errorCode: String,
    val causeType: String,
    cause: Throwable? = null,
) : Throwable(message = "$errorCode/$causeType", cause = cause)
```

Regras:

1. **Uma classe por feature** — nunca acoplar features distintas no mesmo
   tipo. Auth tem `FirebaseAuthAnalyticsException`; Bonsai tem
   `FirebaseBonsaiAnalyticsException`.
2. **`errorCode` é o mesmo string usado no parâmetro `error_code` do evento
   analytics correspondente** — para que o cruzamento Analytics↔Crashlytics
   seja trivial no console.
3. **`causeType` agrupa famílias de causa** (`firebase_auth`, `ktor_io`,
   `validation_local`, `unknown`) — vira facet filtrável no dashboard.
4. **`cause: Throwable?`** preserva o stack original quando há um. Quando
   o erro é puramente de validação local, `cause` é `null`.

### Vinculação com eventos analytics

Todo evento listado em `analytics-spec.yaml` cujo nome termina em `_error`
DEVE chamar `Firebase.crashlytics.recordException(...)` com a exception class
compartilhada **imediatamente após** o `logEvent`. Mesmo `errorCode`, mesmo
`causeType`.

Implementação típica no tracker da feature:

```kotlin
override fun trackRegisterError(errorCode: String, causeType: String, cause: Throwable?) {
    analytics.logEvent(
        AuthAnalytics.Events.REGISTER_ERROR,
        mapOf(
            AuthAnalytics.Params.ERROR_CODE to errorCode,
            AuthAnalytics.Params.CAUSE_TYPE to causeType,
        ),
    )
    crashReporter.recordException(
        FirebaseAuthAnalyticsException(errorCode, causeType, cause),
    )
}
```

### Breadcrumbs e custom keys

Antes de `recordException`, enriquecer o card com `setCustomKey` para
contexto sem PII:

- `feature` — slug da feature (ex.: `auth`, `bonsai`).
- `screen` — id da tela atual (ex.: `register`, `login`).
- `user_type` — `anonymous`, `authenticated`, `pro` (nunca o `uid`).

PII proibida em qualquer key: e-mail, nome, telefone, conteúdo do form.

### Opt-out

Respeitar `CrashlyticsManager.setCollectionEnabled(false)` quando o consent
de telemetria do usuário está negado. O default do SDK (coleta ligada) é
violação de privacidade em projetos com consent screen — o setup do
`Application` / `AppDelegate` deve ler o flag de consent antes do primeiro
evento.

### Paridade Android↔iOS

A exception class no shared garante o tipo. O tracker no shared (ou
adapters por plataforma com mesma assinatura) garante o callsite. Validator
`check-crashlytics-shared-exception.py` (severity `error`) bloqueia commit
se o artefato `analytics-spec.yaml` listar evento `*_error` sem o bloco
`crashlytics:` correspondente.
