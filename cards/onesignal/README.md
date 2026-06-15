# Card — `onesignal`

> OneSignal para push notifications cross-platform em Android/iOS. Card
> backend-axis `notifications` introduzido em DET-6 (W4.4); identidade
> canônica vem do cell `backend.notifications.<platform>` em
> `workflow-config.yaml`.

- **Categoria (axis):** `notifications`
- **Platforms:** `android`, `ios`
- **Maturity:** `stable`
- **Provides:** _vazio_ (backend-axis — cell-anchored)
- **Requires:** _nenhum_
- **Conflicts-with:** _nenhum_ (cardinalidade enforçada pelo schema do
  `backend.notifications.<platform>` cell)

## Quando este card é ativado

`forge init` ativa `onesignal` quando a soma de confidence dos signals
abaixo é ≥ `0.5`:

| Sinal | Confidence | Por quê |
|---|---|---|
| `gradle-dep com.onesignal:OneSignal-Android-SDK` | 0.5 | Coordenada Maven canônica (era pré-v5). Consumida pelo composer em W5. |
| `com.onesignal:OneSignal` em `**/build.gradle*` | 0.3 | Fallback prefix-match que casa OneSignal SDK 5.x+ (`com.onesignal:OneSignal:5.x`) e a forma legada. |
| `com.onesignal` em `**/*.kt` | 0.3 | Import direto no código Kotlin (`com.onesignal.OneSignal`, `com.onesignal.notifications.*`). |

> **Coordenadas Maven por era:** pré-v5 publicava como
> `com.onesignal:OneSignal-Android-SDK`. A partir da v5.0.0 a coord
> mudou para `com.onesignal:OneSignal`. O `gradle-dep` declara a forma
> legada (mais comum nos projetos atuais migrando); o sinal
> `file-content` com prefixo `com.onesignal:OneSignal` casa ambas.

## O que este card contribui

- Fragmento de tech-spec em `templates/onesignal-tech-spec.md` —
  documenta `OneSignal.initWithContext`, registro de player ID, e
  handler de notification opened.

## Integração com outros cards

| Combina com | Efeito |
|---|---|
| `firebase-auth` | `user_id` pós-login encaminhado para `OneSignal.login(uid)` (External ID). |
| `firebase-analytics` | Eventos `notification_received` / `notification_opened` ainda passam pelo SDK Analytics; OneSignal não substitui. |

## Limites declarados

- KMP shared não suportado nativamente — cada plataforma instancia seu
  próprio `OneSignal`.
- iOS exige APNs key configurada no OneSignal Dashboard — esse setup é
  responsabilidade do projeto.
- Este card cobre OneSignal exclusivamente — `fcm` vive em card próprio e
  coabita o catalog (cell `(notifications, platform)` escolhe um único
  provider).
