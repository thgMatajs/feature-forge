# Schema — `backend-axes`

Modelo canônico do bloco `backend:` em `workflow-config.yaml`. Substitui o
modelo bundle-first (`backend.provider` + sub-bloco provider-específico) por
um modelo **multi-axis composable, platform-keyed**, capaz de exprimir
combinações reais (Firebase só pra Crashlytics + REST pra dados + JWT pra
auth) sem inventar especs em campo que não existe.

Origem: Phase B (DET-6), brainstorm 2026-06-10. SPEC: `docs/superpowers/specs/det-6-multi-axis-backend.md`.

<!-- open-detail #1: bundle YAML path — default `presets/<preset>/bundles/<name>.yaml` (arquivo separado, paridade com card.yaml per card). Alternativa inline em `preset.yaml § bundles:` foi rejeitada por reduzir testabilidade isolada. -->

## Por que multi-axis

Bundles fechados (`firebase-stack`, `rest-stack`, `hybrid-firebase-auth-rest-data`,
`local-only`) não cobrem combinações reais observadas em projetos KMP mistos:
Firebase Auth + REST data + Sentry observability + JWT bearer; ou GraphQL +
Firebase Crashlytics + Posthog analytics + Room local. Bundle-first força o
usuário a escolher "o mais próximo" e desativar cards manualmente — drift
silencioso garantido.

Multi-axis trata cada **dimensão de backend** como independente. O projeto
declara, célula por célula `(eixo, plataforma)`, qual card está ativo. Sem
acoplamento artificial entre eixos.

## Os 8 axes canônicos

Cada axis tem boundary semântico explícito. Cards declaram seu eixo via
`identity.category` (ver [card.md](card.md) § CARD-004).

| Axis | Significado | Exemplos de cards |
|---|---|---|
| `data` | HTTP/REST/GraphQL/RPC + persistence-server transport. Inclui contratos de API e persistence servidor (Firestore, Supabase tables). | `retrofit-client`, `ktor-client`, `firestore-persistence`, `firestore-realtime`, `firestore-security-rules`, `rest-api-contract` |
| `auth` | Identity provider + token bearer + session. **Não confundir com bloco top-level `identity:` em workflow-config**, que carrega project metadata. | `firebase-auth`, `auth-jwt-bearer` |
| `observability` | Crash reporting, perf monitoring, distributed tracing. | `crashlytics` (ou `firebase-crashlytics` pós-rename, ver W4) |
| `analytics` | Event tracking, funnels, attribution. | `firebase-analytics`, `posthog-analytics` |
| `storage` | Blob storage (imagens, arquivos, anexos). | `firebase-storage` |
| `persistence` | Local DB + KV prefs. Persistence **client-side**. | `room-database`, `sqldelight`, `datastore-prefs`, `shared-preferences-prefs` |
| `notifications` | Push notifications (FCM / OneSignal / APNs). | `fcm`, `onesignal` |
| `flags` | Feature flags + remote config + A/B. | `firebase-remote-config`, `posthog-flags` |

### Naming rationale — `auth` vs `identity`

O axis é nomeado `auth` (não `identity`) explicitamente pra evitar colisão
com o bloco top-level `identity:` em `workflow-config.yaml`, que carrega
project metadata (`project-name`, `project-slug`, `preset`, `created-at`,
etc.). Auth como axis é semanticamente provedor de **authentication
backend** — token, sessão, OAuth flow — não "project identity".

A confusão custaria diariamente: schemas auto-completion, grep, queries de
graph. `auth` é mais curto, idiomático em mobile (Firebase Auth, JWT auth)
e ortogonal ao metadata top-level.

<!-- open-detail #3: status enum `deprecated` semantics — cell.status=deprecated significa "este card está deprecated NESTE projeto", independente do `identity.maturity` canônico do card (CARD-005). São conceitos ortogonais: card.yaml maturity=stable + cell.status=deprecated é válido (card é estável upstream, mas o projeto já saiu dele). -->

## Schema shape — cell platform-keyed

`workflow-config.yaml § backend` torna-se mapa de 8 eixos, cada um mapa de
`<platform>` → cell-object ou `null`.

```yaml
backend:
  data:
    android:
      card: retrofit-client
      status: migrating-to
      migrating-to: ktor-client
    kmp:
      card: ktor-client
      status: active
    ios: null                       # opt-out (iOS consome via KMP shared)
  auth:
    android: { card: firebase-auth, status: active }
    ios:     { card: firebase-auth, status: active }
    kmp:     { card: firebase-auth, status: active }
  observability:
    android: { card: firebase-crashlytics, status: active }
    ios:     { card: firebase-crashlytics, status: active }
    kmp: null
  analytics:
    android: { card: firebase-analytics, status: active }
    ios:     { card: firebase-analytics, status: active }
    kmp: null
  storage:
    android: { card: firebase-storage, status: active }
    ios:     { card: firebase-storage, status: active }
    kmp: null
  persistence:
    android: { card: room-database, status: active }
    ios: null
    kmp:     { card: sqldelight, status: active }
  notifications:
    android: { card: fcm, status: active }
    ios:     { card: fcm, status: active }
    kmp: null
  flags:
    android: { card: firebase-remote-config, status: active }
    ios:     { card: firebase-remote-config, status: active }
    kmp: null
```

### Cell object schema

| Campo | Tipo | Obrigatório | Semântica |
|---|---|---|---|
| `card` | string (card identity name) | sim (quando cell != null) | Nome do card ativo nessa célula. Match contra `cards/<name>/card.yaml § identity.name`. |
| `status` | enum (ver abaixo) | sim (quando cell != null) | Estado do card no projeto. |
| `migrating-to` | string (card identity name) | **sim** quando `status=migrating-to`; **MUST be absent** caso contrário | Card-alvo da migração; resolver valida que existe em `cards/`. |

Cells com `null` significam **opt-out explícito**: "essa plataforma não tem
provedor para esse eixo neste projeto" (ex.: iOS consome via KMP shared, ou
app local-only sem analytics).

Plataformas enumeradas vêm de `platforms.active` (já existente em
workflow-config — não muda).

### Status enum semantics

| Valor | Quando usar | Consequência |
|---|---|---|
| `active` | Card é o provedor canônico para `(axis, platform)`. Único estado em projetos sem migração. | Features novas usam este card sem fricção. |
| `migrating-to` | Coexistência temporária. Legacy ainda suportado, mas features novas devem usar `migrating-to`. | Validators podem warn quando código novo importa o card antigo. Campo `migrating-to` REQUIRED. |
| `deprecated` | Card já saiu de uso mas permanece declarado por motivo histórico (referência em retrospectives, audit). | `forge plan` rejeita usar card `deprecated` em features novas. |

Distinção load-bearing: `cell.status=deprecated` é **decisão do projeto**;
`card.yaml § identity.maturity=deprecated` é **decisão upstream do card**.
São independentes — ver open-detail #3 acima.

## Platform-applicability dos cards

Cards declaram em qual plataforma podem ser ativados via campo opcional
`identity.platforms: [android, ios, kmp]`. Default ausente = card aplicável
a todas as plataformas ativas do projeto.

O detection composer (Phase B W5) consome esse campo pra rankear candidatos
per-cell `(axis, platform)`. Ver `card.md § identity.platforms`.

<!-- open-detail #8: platform-applicability source — `identity.platforms` é campo opcional no card.yaml. Default ausente = aplicável a todas as plataformas. Composer consome em W5. Se ausente para todos os cards detectados, composer assume aplicabilidade universal. -->

## Detection composer — visão (W5)

O composer scaneia todos os cards backend per-(axis, platform):

```
For each card in cards/*/card.yaml:
  - Read identity.category (axis)
  - Run detection/signals.yaml against project
  - For each match:
    - For each applicable platform (identity.platforms ou default):
      - Record (card, axis, platform, confidence)

For each (axis, platform) cell:
  - Rank candidatos por confidence cumulativa
  - 1 card above threshold:    cell = { card, status: active }
  - 2+ above threshold:        Conflict → prompt 3-caminhos
  - 0 above threshold:         cell = null (opt-out by default)
```

Quando conflito é detectado (ex.: `retrofit-client` + `ktor-client` ambos
acima do threshold em `(data, android)`), o init UX apresenta prompt
canônico 3-caminhos pra usuário decidir: só A, só B, ou migration em curso
(`status: migrating-to`).

Detalhe da resolução em `det-6-multi-axis-backend.md § Detection composer`.

<!-- open-detail #2: composer module location — default `engine/detection/composer.py` (módulo novo, paralelo a `engine/init.py`). Alternativa helper privado em `engine/init.py` foi rejeitada por testability + reuse cross-command (init/reconfigure ambos consomem). -->

## Starter bundles (W6)

Bundles deixam de ser escolha fechada e viram **templates de partida**.
Quatro canônicos para o preset `kmp-mobile`:

- `firebase-full` — Firebase across all axes (serverless apps)
- `rest-with-firebase-telemetry` — REST data + Firebase identity/telemetry/push
- `local-only` — sem backend remoto
- `custom-from-scratch` — sentinela (não é arquivo); pula bundle resolution

Após bundle picker, o usuário pode override per-cell antes de finalizar.
YAML defs canônicos em `presets/<preset>/bundles/<bundle-name>.yaml`.

## Migrations — quando os campos legacy somem

Phase B remove (clean break, pre-production — ver SPEC §Non-goals):

- `identity.backend-choice` (campo monolítico em workflow-config)
- `backend.provider` + sub-blocos provider-específicos (`backend.firebase:`,
  `backend.rest:`)

Não há migration tool — workflow-configs históricos não são preservados
nesta phase. Pós-ship DET-6, o único shape válido é o multi-axis acima.

## Validação enforçada

RULE-019..024 abaixo são os **IDs canônicos** referenciados por
`validate_workflow_config.py` (W7 - update) quando aplicados ao bloco
`backend:` em `workflow-config.yaml`. `docs/schemas/workflow-config.md`
§"Validation rules" cita essa mesma faixa (RULE-019..024) e mantém os
slots RULE-010/011 reservados como audit-trail dos campos legacy
(`backend.provider`) removidos em Phase B / DET-6.

```text
RULE-019  backend.<axis> ∈ {data, auth, observability, analytics, storage,
          persistence, notifications, flags}
RULE-020  backend.<axis>.<platform> ∈ platforms.active OR é `null`
RULE-021  cell.card (quando cell != null) deve referenciar card em cards/
RULE-022  cell.status ∈ {active, migrating-to, deprecated}
RULE-023  cell.migrating-to REQUIRED quando status=migrating-to;
          MUST be absent caso contrário
RULE-024  cell.migrating-to (quando presente) deve referenciar card em cards/
```

## Related schemas

- [`card.md`](card.md) — `identity.category` enum + `identity.platforms`
- [`workflow-config.md`](workflow-config.md) — bloco `backend:` no shape
  multi-axis platform-keyed
- [`capability-labels.md`](capability-labels.md) — labels singulares
  removidas em W3 (`auth-provider`, `http-client`, `crash-reporting`)
  porque cardinalidade já é enforçada pelo schema multi-axis
