# Card — `posthog-analytics`

> PostHog Analytics para product analytics, funnels e session replay em
> Android/iOS. Card backend-axis `analytics` introduzido em DET-6 (W4.2);
> identidade canônica vem do cell `backend.analytics.<platform>` em
> `workflow-config.yaml`, não de label singular do catálogo.

- **Categoria (axis):** `analytics`
- **Platforms:** `android`, `ios`
- **Maturity:** `stable`
- **Provides:** _vazio_ (backend-axis — cell-anchored, ver
  [`docs/schemas/backend-axes.md`](../../docs/schemas/backend-axes.md))
- **Requires:** _nenhum_
- **Conflicts-with:** _nenhum_ (cardinalidade enforçada pelo schema do
  `backend.analytics.<platform>` cell)

## Quando este card é ativado

`forge init` ativa `posthog-analytics` quando a soma de confidence dos
signals abaixo é ≥ `0.5`:

| Sinal | Confidence | Por quê |
|---|---|---|
| `gradle-dep com.posthog:posthog-android` | 0.5 | Coordenada Maven canônica (consumida pelo composer em W5). |
| `com.posthog:posthog-android` em `**/build.gradle*` | 0.3 | Declaração de dependency no Gradle clássico (fallback). |
| `com.posthog.android` em `**/*.kt` | 0.3 | Import direto do SDK no código Kotlin. |

> Como em `firebase-analytics`, o sinal `gradle-dep` chega ao evaluator
> em W5 (composer). Hoje os sinais `file-content` somam 0.6 ≥ 0.5 em
> projetos canonicamente configurados.

## O que este card contribui

- Fragmento de tech-spec em `templates/posthog-analytics-tech-spec.md` —
  documenta naming de eventos, capture API e feature-flag bridge para a
  feature `posthog-flags`.

## Integração com outros cards

| Combina com | Efeito |
|---|---|
| `posthog-flags` | Mesmo SDK; flags consumidas via `PostHog.isFeatureEnabled`. |
| `firebase-auth` | `user_id` pós-login encaminhado para `posthog.identify(uid)`. |

## Limites declarados

- KMP shared não suportado nativamente — cada plataforma instancia seu
  próprio `PostHog`.
- Captura automática de session replay tem custo de bandwidth; defaults
  do template ficam OFF até decisão explícita do projeto.
