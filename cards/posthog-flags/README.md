# Card — `posthog-flags`

> PostHog Feature Flags para feature flags e multivariate experiments em
> Android/iOS. Compartilha SDK com `posthog-analytics`. Card backend-axis
> `flags` introduzido em DET-6 (W4.6); identidade canônica vem do cell
> `backend.flags.<platform>` em `workflow-config.yaml`.

- **Categoria (axis):** `flags`
- **Platforms:** `android`, `ios`
- **Maturity:** `stable`
- **Provides:** _vazio_ (backend-axis — cell-anchored)
- **Requires:** _nenhum_
- **Conflicts-with:** _nenhum_

## Quando este card é ativado

`forge init` ativa `posthog-flags` quando a soma de confidence dos
signals abaixo é ≥ `0.5`:

| Sinal | Confidence | Por quê |
|---|---|---|
| `gradle-dep com.posthog:posthog-android` | 0.4 | Coord Maven compartilhada com `posthog-analytics`; confidence reduzida pra evitar dupla contagem quando os dois cards estão ativos. |
| `isFeatureEnabled` em `**/*.kt` | 0.3 | API canônica de flags do SDK — evidência específica de uso de feature flags (não só analytics). |
| `getFeatureFlag` em `**/*.kt` | 0.3 | Variante para multivariate (retorna variant key). |

> Quando ambos `posthog-flags` e `posthog-analytics` estão presentes
> num projeto, o composer (W5) trata como cards coabitando o mesmo SDK
> — não há conflito, mas a chamada `initWithContext` deve aparecer
> uma única vez. O template orienta para o boot único.

## O que este card contribui

- Fragmento de tech-spec em `templates/posthog-flags-tech-spec.md` —
  naming canônico de flags, bootstrap pattern compartilhado com Analytics,
  e fetch lifecycle (`reloadFeatureFlags`).

## Integração com outros cards

| Combina com | Efeito |
|---|---|
| `posthog-analytics` | SDK único — bootstrap shared (`PostHog.with(context)`). |
| `firebase-auth` | `identify(uid)` pós-login encaminha persona pra avaliação de flags com condições baseadas em user properties. |

## Limites declarados

- Avaliação local + remoto: PostHog faz fetch periódico das flags; chamadas
  de `isFeatureEnabled` usam a snapshot local — `reloadFeatureFlags()` força
  refresh sob demanda.
- KMP shared não suportado nativamente — cada plataforma instancia seu
  próprio `PostHog`.
- Este card cobre PostHog flags exclusivamente — `firebase-remote-config`
  vive em card próprio e coabita o catalog.
