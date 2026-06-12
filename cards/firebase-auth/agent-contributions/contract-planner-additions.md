<!--
  Injetado em: contract-planner-agent
  Extension-point: rule:error-event-binding
  Card: firebase-auth

  Wave B do forge plan. O contract-planner produz analytics-spec.yaml entre
  outros artefatos. Quando este card está ativo, todas as regras abaixo
  são obrigatórias ao escrever a seção de auth do analytics-spec.
-->

## firebase-auth — regras para `analytics-spec.yaml`

Estas regras se aplicam APENAS a eventos da feature `auth` (prefixo
`register_*`, `login_*`, `forgot_password_*`, `create_account_*`,
`screen_view_login`). Outras features seguem suas próprias contribuições.

### 1. Toda const de evento vem do contrato canônico

Não escreva strings literais para event names ou param keys. Use sempre a
constante de `shared:core/observability/AuthAnalytics.kt`:

```yaml
# CORRETO
events:
  - id: login_attempt
    const-ref: "AuthAnalytics.Events.LOGIN_ATTEMPT"
    params:
      - name: duration_ms
        const-ref: "AuthAnalytics.Params.DURATION_MS"

# ERRADO — string hardcoded
events:
  - id: login_attempt
    name: "login_attempt"
    params:
      - name: "duration_ms"
```

Se o evento que você precisa não existe em `AuthAnalytics.kt`, **adicione
ao contrato primeiro** e cite a adição em `notes:` do analytics-spec. Não
referencie um evento que ainda não exista no shared.

### 2. Naming format imutável

`<feature>_<verb>_<outcome>` — para auth, `<feature>` é sempre `register`,
`login`, `forgot_password`, `create_account` ou `screen_view`. Outcomes
canônicos: `attempt`, `success`, `error`, `offline`, `validation_error`,
`clicked`. Outros outcomes precisam de justificativa em `notes:`.

### 3. Crashlytics binding em `*_error` (condicional)

Quando o card `firebase-crashlytics` está ativo, todo evento com sufixo `_error`
deve declarar bloco `crashlytics:`:

```yaml
- id: login_error
  const-ref: "AuthAnalytics.Events.LOGIN_ERROR"
  params:
    - { name: error_code, const-ref: "AuthAnalytics.Params.ERROR_CODE", required: true }
  crashlytics:
    when-card-active: "firebase-crashlytics"
    exception-class:  "FirebaseAuthAnalyticsException"
    bind-params:      ["error_code"]
    cause-type:       "LOGIN"      # ou REGISTER, FORGOT_PASSWORD
```

A classe `FirebaseAuthAnalyticsException` vive em
`shared/feature/auth/.../data/analytics/` e garante paridade Android↔iOS na
cadeia de erro do Crashlytics — a mesma exception é chamada por ambos os
trackers nativos.

Quando o card `firebase-crashlytics` está **inativo**, omita o bloco
`crashlytics:` (não escreva `crashlytics: false` — apenas omita) e
adicione `# firebase-crashlytics card inativo — recordException não disparado` em
`notes:`.

### 4. Validation errors são eventos separados

Não confunda erros de validação client-side (campos vazios, formato
inválido) com erros do Firebase. Validação client-side dispara
`login_validation_error` / `register_validation_error` com `field_id` e
`error_type`. Não recordExceptiona.

### 5. Paridade Android ↔ iOS obrigatória

Toda regra que aparecer na seção de auth do `analytics-spec.yaml` deve ser
implementada nos dois trackers nativos. Se o PRD só especifica Android,
liste o iOS counterpart em `notes:` como follow-up explícito; nunca deixe
implícito.

### 6. Eventos canônicos disponíveis (referência rápida)

| Evento | Quando dispara | Crashlytics |
|---|---|---|
| `register_attempt` | submit do form de criar conta | não |
| `register_success` | conta criada | não |
| `register_error` | FirebaseAuthException no registro | sim (cause `REGISTER`) |
| `register_offline` | sem conexão antes do call | não |
| `login_attempt` | submit do form de login | não |
| `login_success` | login completou | não |
| `login_error` | FirebaseAuthException no login | sim (cause `LOGIN`) |
| `login_validation_error` | validação client-side bloqueou | não |
| `login_offline` | sem conexão antes do call | não |
| `forgot_password_clicked` | tap em "esqueci senha" | não |
| `create_account_clicked` | tap em "criar conta" | não |
| `screen_view_login` | login screen em foreground | não |

Eventos fora desta lista precisam ser adicionados ao
`shared:core/observability/AuthAnalytics.kt` no mesmo PR e citados em
`notes:` do analytics-spec.
