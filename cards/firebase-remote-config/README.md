# Card — `firebase-remote-config`

> Firebase Remote Config para feature flags, remote config e A/B test
> rollouts em Android/iOS. Card backend-axis `flags` introduzido em
> DET-6 (W4.5); identidade canônica vem do cell
> `backend.flags.<platform>` em `workflow-config.yaml`.

- **Categoria (axis):** `flags`
- **Platforms:** `android`, `ios`
- **Maturity:** `stable`
- **Provides:** _vazio_ (backend-axis — cell-anchored)
- **Requires:** _nenhum_
- **Conflicts-with:** _nenhum_

## Quando este card é ativado

`forge init` ativa `firebase-remote-config` quando a soma de confidence
dos signals abaixo é ≥ `0.5`:

| Sinal | Confidence | Por quê |
|---|---|---|
| `gradle-dep com.google.firebase:firebase-config` | 0.5 | Coordenada Maven canônica do Remote Config (consumida pelo composer em W5). |
| `**/google-services.json` existe | 0.3 | Config Firebase Android — gerada pelo console. |
| `com.google.firebase.remoteconfig` em `**/*.kt` | 0.3 | Import direto do SDK Remote Config no código Kotlin. |

## O que este card contribui

- Fragmento de tech-spec em `templates/firebase-remote-config-tech-spec.md`
  — documenta naming canônico de flags, `defaultsXml`, `setMinimumFetchInterval`
  para dev/prod e fetch lifecycle.

## Integração com outros cards

| Combina com | Efeito |
|---|---|
| `firebase-analytics` | Audiences definidas em Analytics são alvos válidos pra targeting de Remote Config rollouts. |
| `firebase-auth` | Condições baseadas em `user_id` / claims funcionam após login. |

## Limites declarados

- Fetch lifecycle (chamada `fetchAndActivate`) é responsabilidade do
  projeto — este card só descreve convenções.
- KMP shared não suportado nativamente — cada plataforma instancia seu
  próprio `FirebaseRemoteConfig`.
- Este card cobre Remote Config exclusivamente — `posthog-flags` e
  outros providers vivem em cards próprios.
