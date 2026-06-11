<!--
  Template fragment contribuído por: posthog-analytics
  Target: tech-spec.md
  Merge: append-section "Analytics events (PostHog)"
-->

## Analytics events (PostHog)

Esta seção é injetada pelo card `posthog-analytics` e padroniza eventos +
user properties enviados ao PostHog.

### Naming canônico

Mesmo padrão dos demais analytics: `<feature>_<verb>_<outcome>`. PostHog
trata `event` como string livre — disciplina de naming vive no contrato
da feature.

### Eventos da feature

| Event name | Quando dispara | Propriedades | Outcome |
|---|---|---|---|
| `<feature>_<verb>_<outcome>` | _quando_ | _props_ | _outcome_ |

### Identify

| Quando | Chamada |
|---|---|
| Pós-login bem-sucedido | `PostHog.identify(distinctId = uid, userProperties = { auth_method, … })` |
| Logout | `PostHog.reset()` |

### Feature flags

Quando o card `posthog-flags` também está ativo, consumir flags via
`PostHog.isFeatureEnabled("flag-key")` no mesmo SDK — não criar handler
separado.
