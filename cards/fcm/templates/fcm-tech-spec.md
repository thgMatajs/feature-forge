<!--
  Template fragment contribuído por: fcm
  Target: tech-spec.md
  Merge: append-section "Push notifications (FCM)"
-->

## Push notifications (FCM)

Esta seção é injetada pelo card `fcm` e padroniza o handler de push
notifications via Firebase Cloud Messaging.

### Camada `data/` (Android)

```
shared/feature/push/src/androidMain/kotlin/.../feature/push/
├── data/service/
│   └── PushMessagingService.kt        (extends FirebaseMessagingService)
├── data/handler/
│   └── PushPayloadHandler.kt          (mapa payload → ação)
└── domain/
    └── model/PushPayload.kt           (sealed class — types canônicos)
```

### Payload schema canônico

| Tipo | Quando | Estrutura |
|---|---|---|
| Data-only | Processado em foreground/background uniformemente | `{ "type": "<event>", "<feature>_id": "<id>", … }` |
| Notification-only | Sistema renderiza, app só recebe ao abrir | `notification: { title, body }` |
| Hybrid | Combinação — payload + visual default | ambos blocos preenchidos |

### Lifecycle handler

| Callback | Quando | O que faz |
|---|---|---|
| `onNewToken` | Token FCM atualiza | Encaminha pro backend (`/users/me/devices`). |
| `onMessageReceived` | Payload chega (foreground ou data-only background) | `PushPayloadHandler.handle(payload)`. |

### Analytics

Quando o card `firebase-analytics` está ativo, eventos `notification_received`
e `notification_opened` são capturados automaticamente — não duplicar logo.
