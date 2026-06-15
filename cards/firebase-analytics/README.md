# Card — `firebase-analytics`

> Firebase Analytics para event tracking, screen views e user properties em
> Android/iOS. Card backend-axis `analytics` introduzido em DET-6 (W4.1);
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

`forge init` ativa `firebase-analytics` quando a soma de confidence dos
signals abaixo é ≥ `0.5`:

| Sinal | Confidence | Por quê |
|---|---|---|
| `gradle-dep com.google.firebase:firebase-analytics` | 0.5 | Coordenada Maven canônica (consumida pelo composer em W5). |
| `**/google-services.json` existe | 0.3 | Config Firebase Android — gerado pelo console. |
| `com.google.firebase.analytics` em `**/*.kt` | 0.3 | Import direto no código de feature. |

Se a soma cair em `[0.3, 0.5)`, `forge init` pergunta confirmação ao
usuário. Abaixo de 0.3, o card não é ativado.

> O evaluator runtime atual (`engine.init._eval_detection_signals`) ainda
> não consome `gradle-dep` — esse sinal vira ativo quando o composer W5
> landa. Enquanto isso, os sinais `file-content` e `file-exists` cobrem
> o threshold em projetos canonicamente configurados.

## O que este card contribui

- Fragmento de tech-spec em `templates/firebase-analytics-tech-spec.md` —
  appendado ao `tech-spec.md` da feature quando o card está ativo,
  documentando convenções de naming de eventos (`<feature>_<verb>_<outcome>`),
  user properties, e DebugView setup.

## Integração com outros cards

| Combina com | Efeito |
|---|---|
| `firebase-crashlytics` | Eventos `*_error` podem chamar `Firebase.crashlytics.recordException` lado a lado com `Analytics.logEvent`. |
| `firebase-auth` | User properties (`user_id`, `auth_method`) populadas após login bem-sucedido. |
| `firebase-remote-config` | Audiences definidas em Analytics são exportáveis pro Remote Config. |

## Como o card se conecta ao workflow-config

Após ativação, `forge init` materializa o cell:

```yaml
backend:
  analytics:
    android: { card: firebase-analytics, status: active }
    ios:     { card: firebase-analytics, status: active }
    kmp:     null    # opt-out — analytics não tem SDK KMP nativo
```

Cells `null` significam opt-out explícito (ex.: KMP shared layer não tem
Firebase Analytics SDK direto — Android e iOS instanciam separadamente).

## Limites declarados

- Este card **não** gera código — apenas contribui templates e config
  defaults. Implementação concreta é responsabilidade dos agentes
  downstream.
- KMP shared não é suportado nativamente pelo SDK Firebase Analytics —
  cada plataforma instancia seu próprio `FirebaseAnalytics`.
- Naming canônico de eventos (`<feature>_<verb>_<outcome>`) é
  responsabilidade do contrato de analytics no projeto consumidor; este
  card não enforça via validator em v1.2.
