<!--
  Template fragment contribuído por: firebase-analytics
  Target: tech-spec.md
  Merge: append-section "Analytics events (Firebase)"

  Esta seção é appendada ao tech-spec.md quando o card firebase-analytics
  está ativo. Preencha os blocos com base no PRD + analytics-spec da
  feature; não deixe campo em branco — use `n/a` com justificativa em §13
  (Risks + open questions).
-->

## Analytics events (Firebase)

Esta seção é injetada pelo card `firebase-analytics` e padroniza eventos +
user properties enviados ao Firebase Analytics.

### Naming canônico

Todos os eventos seguem `<feature>_<verb>_<outcome>`. Verbos canônicos:
`view`, `click`, `submit`, `attempt`, `error`, `success`. Outcomes
canônicos: `success`, `error`, `cancelled`, `n/a`.

### Eventos da feature

| Event name | Quando dispara | Parâmetros | Outcome |
|---|---|---|---|
| `<feature>_<verb>_<outcome>` | _quando_ | _params_ | _outcome_ |

### User properties

| Property | Quando set | Valores | Notas |
|---|---|---|---|
| `user_id` | Pós-login bem-sucedido | UID Firebase | Limpa em logout. |
| `auth_method` | Pós-login bem-sucedido | `email`, `google`, `apple` | n/a se anônimo. |

### DebugView setup

- **Android:** `adb shell setprop debug.firebase.analytics.app <package>`.
- **iOS:** scheme arg `-FIRDebugEnabled`.
