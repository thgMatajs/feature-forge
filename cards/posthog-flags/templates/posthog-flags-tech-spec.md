<!--
  Template fragment contribuído por: posthog-flags
  Target: tech-spec.md
  Merge: append-section "Feature flags (PostHog)"
-->

## Feature flags (PostHog)

Esta seção é injetada pelo card `posthog-flags` e padroniza naming +
fetch lifecycle de flags via PostHog SDK.

### Naming canônico

| Padrão | Exemplo | Quando |
|---|---|---|
| `feature-<name>-enabled` | `feature-payments-enabled` | Toggle binário. |
| `experiment-<name>` | `experiment-onboarding-v2` | Multivariate. |

> PostHog usa hífen como separator (`feature-foo-bar`), distinto do
> snake_case do Firebase Remote Config — alinhar à convenção do vendor.

### Bootstrap compartilhado com Analytics

Quando o card `posthog-analytics` também está ativo, o SDK é instanciado
uma única vez (no `Application.onCreate` Android ou `AppDelegate` iOS):

```kotlin
PostHog.with(this, PostHogConfig(POSTHOG_API_KEY).apply {
    captureScreenViews = true
})
```

Ambos os cards consomem o mesmo singleton.

### Avaliação

| API | Retorna | Quando |
|---|---|---|
| `PostHog.isFeatureEnabled("flag-key")` | `Boolean` | Toggle binário. |
| `PostHog.getFeatureFlag("experiment-key")` | `String?` (variant key) | Multivariate. |

Snapshot local é atualizada periodicamente pelo SDK; `PostHog.reloadFeatureFlags()`
força refresh sob demanda (raro — usar apenas em fluxos sensíveis a flags
recém-criadas).
