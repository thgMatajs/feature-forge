# Card — `fcm`

> Firebase Cloud Messaging para push notifications cross-platform em
> Android/iOS. Card backend-axis `notifications` introduzido em DET-6
> (W4.3); identidade canônica vem do cell `backend.notifications.<platform>`
> em `workflow-config.yaml`.

- **Categoria (axis):** `notifications`
- **Platforms:** `android`, `ios`
- **Maturity:** `stable`
- **Provides:** _vazio_ (backend-axis — cell-anchored, ver
  [`docs/schemas/backend-axes.md`](../../docs/schemas/backend-axes.md))
- **Requires:** _nenhum_
- **Conflicts-with:** _nenhum_ (cardinalidade enforçada pelo schema do
  `backend.notifications.<platform>` cell)

## Quando este card é ativado

`forge init` ativa `fcm` quando a soma de confidence dos signals abaixo é
≥ `0.5`:

| Sinal | Confidence | Por quê |
|---|---|---|
| `gradle-dep com.google.firebase:firebase-messaging` | 0.5 | Coordenada Maven canônica (consumida pelo composer em W5). |
| `**/google-services.json` existe | 0.3 | Config Firebase Android — gerada pelo console. |
| `com.google.firebase.messaging` em `**/*.kt` | 0.3 | Import direto do SDK Messaging no código Kotlin. |

## O que este card contribui

- Fragmento de tech-spec em `templates/fcm-tech-spec.md` — documenta
  registro do device token, `FirebaseMessagingService` lifecycle, payload
  schema (data-only vs notification-only vs hybrid), e DI do handler.

## Integração com outros cards

| Combina com | Efeito |
|---|---|
| `firebase-auth` | Token FCM associado ao `user_id` pós-login (topic subscriptions). |
| `firebase-analytics` | Eventos `notification_received` / `notification_opened` capturados automaticamente quando ambos ativos. |
| `firebase-crashlytics` | Falhas no handler ganham `recordException` no exception class compartilhada da feature. |

## Limites declarados

- Este card cobre Firebase Cloud Messaging exclusivamente — `onesignal`
  e outros providers vivem em cards próprios e coabitam o catalog.
- iOS exige APNs configurado no Firebase Console — esse setup é
  responsabilidade do projeto (este card só descreve convenções).
- KMP shared não é suportado pelo SDK FCM nativo — cada plataforma
  instancia seu próprio handler.
