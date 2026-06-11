<!--
  Template fragment contribuído por: onesignal
  Target: tech-spec.md
  Merge: append-section "Push notifications (OneSignal)"
-->

## Push notifications (OneSignal)

Esta seção é injetada pelo card `onesignal` e padroniza o handler de push
notifications via OneSignal SDK.

### Init canônico

| Plataforma | Onde |
|---|---|
| Android | `Application.onCreate` — `OneSignal.initWithContext(this, ONESIGNAL_APP_ID)` |
| iOS | `AppDelegate.didFinishLaunching` — `OneSignal.initialize(ONESIGNAL_APP_ID, withLaunchOptions: …)` |

### External ID + identify

Quando o card `firebase-auth` está ativo, encaminhar o UID pós-login:

```kotlin
OneSignal.login(firebaseUser.uid)
// On logout:
OneSignal.logout()
```

### Notification opened handler

| Callback | Quando | O que faz |
|---|---|---|
| `INotificationClickListener.onClick` | User abre notification | Roteia pra deep link via `data["deep_link"]`. |

### Tags vs External ID

| Conceito | Uso recomendado |
|---|---|
| `External ID` | Identifier persistente (UID, email hash). |
| `Tags` | Atributos de segmentação (`plan=premium`, `country=BR`). |

OneSignal Dashboard usa tags pra targeting de campanhas; reservar External
ID pra dedupe cross-device do mesmo usuário.
