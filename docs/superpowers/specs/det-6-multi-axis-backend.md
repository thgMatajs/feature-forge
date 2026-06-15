# SPEC — DET-6: Multi-axis backend model

**Phase:** B (DET-6) — segue Phase A (DRIFT-1).
**Origem:** `docs/design/04-pending.md` §"v1.2-dev pilot 2026-06-10 — findings + phase sequencing".
**Status:** locked após brainstorm user↔orchestrator (2026-06-10).
**Voz:** mentor calmo.

---

## Goal

Substituir o modelo bundle-first do backend (`presets/kmp-mobile/preset.yaml § backend-candidates` + `identity.backend-choice`) por um modelo multi-axis composable, platform-keyed, capaz de exprimir combinações reais (Firebase só pra Crashlytics + REST pra dados + JWT pra auth) sem inventar especs em campo que não existe.

## Why

DET-6 capturado no piloto v1.2-dev (2026-06-10) como **Crítico de design**: bundles fechados (`firebase-stack`, `rest-stack`, `hybrid-firebase-auth-rest-data`, `local-only`) não cobrem combinações reais observadas no campo. Projetos KMP mistos misturam Firebase Auth + REST data + Sentry observability + JWT bearer; ou GraphQL + Firebase Crashlytics + Posthog analytics + Room local. Bundle-first força usuário a escolher "o mais próximo" e desativa cards manualmente.

DET-6 absorve naturalmente:

- **B1** (`identity.backend-choice` ↔ `backend.provider` desync) — campos legacy são removidos no design novo, desync vira moot.
- **B2** (seção `backend.firebase:` órfã após swap) — schema novo não tem blocos provider-específicos no `backend:`; cleanup logic some.
- **DET-5** (`retrofit-client` fora do preset kmp-mobile) — sem bundles fechados, retrofit vira card detectável por (axis=data, platform=android) sem precisar de slot em bundle.

Cross-references locked:

- Não toca DET-3 (Phase 0b — shipped 2026-06-10).
- Não toca DRIFT-1 (Phase A — separate).
- Não introduz MCP-style integration.

## Non-goals (explícito)

- **NÃO** refactor de stack/tooling cards (`kotlin-language`, `kmp-shared`, `compose-screens`, `swiftui-screens`, `koin-annotations`, `skie-bridge`, `nav3`, `swiftui-navigation`). Esses são "stack", não "backend axis".
- **NÃO** migration logic — feature-forge está pre-production (ver `MEMORY.md project_pre_production_status`). Clean break sem preservar workflow-configs históricos.
- **NÃO** touch em DET-3 (`gradle-dep` signal type) — fundação já shipou e funciona.
- **NÃO** touch em DRIFT-1 — Phase A delivera AskUserQuestion intent protocol; Phase B consome.
- **NÃO** MCP-style integration — auditores ainda são scripts/Python locais.
- **NÃO** adicionar capability labels novos pras 3 categorias novas (`analytics`, `notifications`, `flags`) — o schema enforça cardinalidade per-cell. Labels singulares legacy serão removidas (ver §Capability labels refactor).

---

## Design contract (locked — translation verbatim)

### Taxonomia — 8 backend axes

Eixos canônicos:

```
data            — HTTP/REST/GraphQL/RPC + persistence-server transport
auth            — identity + token bearer + session
observability   — crash reporting, perf monitoring, distributed tracing
analytics       — event tracking, funnels, attribution
storage         — blob storage (imagens, arquivos, anexos)
persistence     — local DB + KV prefs
notifications   — push notifications (FCM / OneSignal / APNs)
flags           — feature flags + remote config + A/B
```

**Naming nota:** axis "auth" é explicitamente chamado `auth` e **NÃO** `identity` para evitar colisão com bloco top-level `identity:` em `workflow-config.yaml` (que carrega project metadata). Auth como axis é semanticamente provider de "authentication backend", não "project identity".

### Schema shape — cell platform-keyed

`workflow-config.yaml § backend` torna-se mapa de 8 eixos, cada um mapa de `<platform>` → cell-object ou `null`:

```yaml
backend:
  data:
    android:
      card: retrofit-client
      status: migrating-to        # one of: active | migrating-to | deprecated
      migrating-to: ktor-client   # REQUIRED quando status=migrating-to
    kmp:
      card: ktor-client
      status: active
    ios: null                      # opt-out (essa plataforma consome via KMP shared)
  auth:
    android: { card: firebase-auth, status: active }
    ios:     { card: firebase-auth, status: active }
    kmp:     { card: firebase-auth, status: active }
  observability:
    android: { card: firebase-crashlytics, status: active }
    ios:     { card: firebase-crashlytics, status: active }
    kmp: null
  analytics:    { android: { card: firebase-analytics, status: active }, ios: { card: firebase-analytics, status: active }, kmp: null }
  storage:      { android: { card: firebase-storage,   status: active }, ios: { card: firebase-storage,   status: active }, kmp: null }
  persistence:  { android: { card: room-database,      status: active }, ios: null, kmp: { card: sqldelight, status: active } }
  notifications:{ android: { card: fcm, status: active }, ios: { card: fcm, status: active }, kmp: null }
  flags:        { android: { card: firebase-remote-config, status: active }, ios: { card: firebase-remote-config, status: active }, kmp: null }
```

**Cell object schema:**

| Campo | Tipo | Obrigatório | Semântica |
|---|---|---|---|
| `card` | string (card identity name) | sim (quando cell != null) | nome do card ativo nessa célula. Match contra `cards/<name>/card.yaml § identity.name`. |
| `status` | enum `active | migrating-to | deprecated` | sim (quando cell != null) | estado do card no projeto. Ver semântica abaixo. |
| `migrating-to` | string (card identity name) | **sim** quando `status=migrating-to`; **MUST be absent** em outros casos | card-alvo da migração; valida que existe em `cards/`. |

**Status enum semantics:**

- `active` — card é o provedor canônico para (axis, platform). Único estado em projetos sem migração.
- `migrating-to` — coexistência temporária. Sinaliza ao planner que features novas devem usar `migrating-to` mas legacy continua suportado. Validator no `forge verify` pode warn quando código novo importa o "card antigo".
- `deprecated` — card já saiu de uso mas permanece declarado por motivo histórico (referência em retrospectives, etc.). `forge plan` rejeita usar card `deprecated` em features novas.

**Cell `null`:** opt-out explícito. Significa "essa plataforma não tem provedor para esse eixo neste projeto" (ex.: iOS consome via KMP shared, ou app local-only sem analytics).

**Platforms enumerados por `platforms.active`** (campo já existente no workflow-config — não muda).

### Starter bundles (4 canônicos)

Bundles agora são **templates de partida**, não escolha fechada. Após bundle picker, usuário pode override per-(axis, platform) cell antes de finalizar. YAML defs vivem em `presets/kmp-mobile/bundles/<bundle-name>.yaml` (path canônico — agente confirma em §Open implementation details).

#### `firebase-full`

Stack Firebase máxima onde aplicável:

```yaml
# presets/kmp-mobile/bundles/firebase-full.yaml
name:         firebase-full
description:  "Firebase across all backend axes; ready for serverless apps."

defaults:
  data:          { all-platforms: firestore-persistence }
  auth:          { all-platforms: firebase-auth }
  observability: { all-platforms: firebase-crashlytics }
  analytics:     { all-platforms: firebase-analytics }
  storage:       { all-platforms: firebase-storage }
  persistence:   { android: room-database, ios: null, kmp: sqldelight }
  notifications: { all-platforms: fcm }
  flags:         { all-platforms: firebase-remote-config }
```

Note `persistence` é platform-divergente: Room no Android, SQLDelight no KMP, null no iOS (iOS consome via KMP shared).

#### `rest-with-firebase-telemetry`

REST data + Firebase identity/telemetry/push:

```yaml
# presets/kmp-mobile/bundles/rest-with-firebase-telemetry.yaml
name:         rest-with-firebase-telemetry
description:  "REST API for data + Firebase for identity, telemetry, push."

defaults:
  data:          { android: retrofit-client, kmp: ktor-client, ios: null }
  auth:          { all-platforms: firebase-auth }
  observability: { all-platforms: firebase-crashlytics }
  analytics:     { all-platforms: firebase-analytics }
  storage:       { all-platforms: null }
  persistence:   { android: room-database, ios: null, kmp: sqldelight }
  notifications: { all-platforms: fcm }
  flags:         { all-platforms: firebase-remote-config }
```

Note `data` é divergente — retrofit no Android (legacy/dominante), ktor no KMP shared (KMP-native). Captura a realidade de migração KMP em curso.

#### `local-only`

Sem backend remoto:

```yaml
# presets/kmp-mobile/bundles/local-only.yaml
name:         local-only
description:  "Offline-first app; no remote backend dependencies."

defaults:
  data:          { all-platforms: null }
  auth:          { all-platforms: null }
  observability: { all-platforms: null }
  analytics:     { all-platforms: null }
  storage:       { all-platforms: null }
  persistence:   { android: room-database, ios: null, kmp: sqldelight }
  notifications: { all-platforms: null }
  flags:         { all-platforms: null }
```

#### `custom-from-scratch`

Escape hatch. **Não é arquivo** — é valor sentinela no bundle picker. Quando user seleciona, init flow pula resolução de bundle e vai direto pros prompts per-axis (ou per-(axis, platform) no modo adaptive). Documentado como opção válida no SPEC dos bundles + tratado em `engine/init.py`.

### 6 cards novos (W4)

| Card name | Axis (identity.category) | Categoria nova? | Detection strategy |
|---|---|---|---|
| `firebase-analytics` | analytics | sim | file-content `google-services.json` + file-content `import com.google.firebase.analytics` |
| `posthog-analytics` | analytics | sim | gradle-dep `com.posthog:posthog-android` + file-content `import com.posthog.android` |
| `fcm` | notifications | sim | gradle-dep `com.google.firebase:firebase-messaging` + file-content manifest receiver pattern |
| `onesignal` | notifications | sim | gradle-dep `com.onesignal:OneSignal-Android-SDK` |
| `firebase-remote-config` | flags | sim | gradle-dep `com.google.firebase:firebase-config` |
| `posthog-flags` | flags | sim | gradle-dep `com.posthog:posthog-android` + file-content `posthog.isFeatureEnabled` |

Cada card cria:

- `cards/<name>/card.yaml` (manifest completo)
- `cards/<name>/detection/signals.yaml` (mirror documental — ver FU-2 em 04-pending; mantém disciplina atual)
- `cards/<name>/README.md`
- `cards/<name>/templates/*.md` (stubs mínimos, expandíveis em features que ativarem)

Relacionamentos cross-card:

- `firebase-analytics` requires `google-services.json` setup — mencionado no README, não enforçado em schema (já é signal).
- `posthog-analytics` + `posthog-flags` compartilham base posthog dep — um card pode detectar ambos via signals, mas são cards independentes (axis diferente).
- `fcm` requires `google-services.json`.

### identity.category cleanup (W2)

Categorias atuais (`grep ^category cards/*/card.yaml`):

| Categoria atual | Cards | Ação Phase B |
|---|---|---|
| `backend` (7) | `firebase-auth`, `firebase-storage`, `firestore-persistence`, `firestore-realtime`, `firestore-security-rules`, `rest-api-contract`, `auth-jwt-bearer` | **split por eixo real** (ver mapeamento abaixo) |
| `kmp` (4) | `kmp-shared`, `kotlinx-serialization-json`, `ktor-client`, `skie-bridge` | `ktor-client` → `data`; demais ficam `kmp` (stack/tooling) |
| `persistence` (3) | `datastore-prefs`, `room-database`, `shared-preferences-prefs` | mantém `persistence` (já alinhado) |
| `ui` (2) | `compose-screens`, `swiftui-screens` | preservado |
| `navigation` (2) | `nav3`, `swiftui-navigation` | preservado |
| `network` (1) | `retrofit-client` | → `data` |
| `observability` (1) | `crashlytics` | preservado (e nota: card pode ser renomeado pra `firebase-crashlytics` em W4 se conflito de naming — agente decide) |
| `dependency-injection` (1) | `koin-annotations` | preservado |
| `language` (1) | `kotlin-language` | preservado |

Migration explícita (cards `backend` → 8 axes):

| Card | identity.category novo |
|---|---|
| `firebase-auth` | `auth` |
| `auth-jwt-bearer` | `auth` |
| `firebase-storage` | `storage` |
| `firestore-persistence` | `data` |
| `firestore-realtime` | `data` (mantém atrelado a data; sub-axis "realtime" fica como Open implementation detail) |
| `firestore-security-rules` | `data` (mantém atrelado; sub-axis "rules" fica como Open implementation detail) |
| `rest-api-contract` | `data` (data-contract sub-axis fica como Open implementation detail) |
| `retrofit-client` | `data` (já é `network`, vai pra `data`) |
| `ktor-client` | `data` (já é `kmp`, vai pra `data`) |

Audit determinístico vive em `.planning/det-6/category-migration-audit.json` (gerado por task de W2) — mesma disciplina do DET-3 migration-audit.

Categorias enumeradas em `docs/schemas/card.md § identity.category` ganham 3 novas (`analytics`, `notifications`, `flags`); demais (stack/tooling) preservadas.

### Capability labels refactor (W3) — big bang

Labels singulares cobertas pelo novo schema (cardinalidade já enforçada por `Map[axis][platform] = card`) são removidas:

| Label | Onde vivia | Ação |
|---|---|---|
| `auth-provider` (singular) | `firebase-auth.provides`, `auth-jwt-bearer.provides` | remover — schema enforça 1 card per (auth, platform) cell |
| `http-client` (singular) | `ktor-client.provides`, `retrofit-client.provides` | remover — schema enforça 1 card per (data, platform) cell |
| `crash-reporting` (singular) | `crashlytics.provides` | remover — schema enforça 1 card per (observability, platform) cell |
| `analytics-provider` (planejada singular) | (não existe ainda) | **NÃO adiciona** — schema enforça |
| `notifications-provider` (planejada singular) | (não existe ainda) | **NÃO adiciona** — schema enforça |
| `feature-flags-provider` (planejada singular) | (não existe ainda) | **NÃO adiciona** — schema enforça |

Labels singulares preservadas (cardinalidade não é cobertura do schema novo):

| Label | Razão |
|---|---|
| `di-framework` (Koin / Hilt) | stack/tooling concern, não backend axis |
| `navigation-router` (Nav3 / Compose-Navigation) | stack/tooling |
| `serialization-format` (kotlinx-serialization / Moshi) | stack/tooling, transversal |

Audit completo (lista de labels removidas + cards afetados + onde no engine eram enforçadas) vive em `.planning/det-6/label-refactor-audit.json` (W3).

### Detection composer (W5)

Composer per-(axis, platform):

```
For each card in cards/*/card.yaml:
  - Read identity.category (eixos novos: data/auth/observability/analytics/storage/persistence/notifications/flags)
  - Run detection/signals.yaml against project
  - For each match:
    - Determine card's platform-applicability (read from card YAML; new field or derived from existing platforms field)
    - For each applicable platform:
      - Record (card, axis=category, platform, confidence)

For each (axis, platform) cell:
  - Rank detected cards by cumulative confidence
  - If 1 card above threshold:    cell = { card: <name>, status: active }
  - If 2+ above threshold:        cell = Conflict[card1, card2]  # surfaces 3-caminhos prompt
  - If 0 above threshold:         cell = null  # opt-out by default

Final emit: Map[axis][platform] → cell | Conflict
```

**Reuse:** parsers de detection signals já existem em `engine/init.py:_eval_detection_signals` (e helpers como `_eval_gradle_dep` do DET-3). Composer reusa, agrega por (axis, platform).

**Conflict resolution UX:** quando composer detecta conflito (2 cards com confidence similar pra mesma cell), init UX prompta:

```
🛑 axis `data`, platform `android`:
   detectei `retrofit-client` (conf 0.7) E `ktor-client` (conf 0.6)
   
   Como o projeto trata?
     1) só retrofit-client (status: active, ktor-client desativado)
     2) só ktor-client (status: active, retrofit-client desativado)
     3) migração em curso (status: migrating-to ktor-client; retrofit-client ainda ativo)
```

Cell resultante:
- (1) → `{ card: retrofit-client, status: active }`
- (2) → `{ card: ktor-client, status: active }`
- (3) → `{ card: retrofit-client, status: migrating-to, migrating-to: ktor-client }`

### UX init flow (W7) — hybrid detection-first + bundles fallback

**Brownfield path** (codebase tem signals detectáveis):

1. Composer scans all backend cards per-(axis, platform).
2. Composer compila tabela `(axis, platform) → detected-card | null | conflict`.
3. AskUserQuestion (modo Claude-fronted via Phase A) apresenta tabela detectada:
   ```
   Detectei o seguinte setup de backend:
   
   axis            | android        | ios           | kmp
   ----------------|----------------|---------------|---------------
   data            | retrofit-client| -             | ktor-client
   auth            | firebase-auth  | firebase-auth | firebase-auth
   observability   | crashlytics    | crashlytics   | -
   ...
   
   Como prosseguir?
     [confirmar tudo]  [ajustar eixos específicos]  [começar do zero]
   ```
4. "Confirmar tudo" → escreve workflow-config conforme detecção.
5. "Ajustar eixos específicos" → multiSelect quais eixos → per-axis AskUserQuestion (com detected como default + alternativas).
6. "Começar do zero" → cai no greenfield path.

**Greenfield path** (sem detecção OU usuário escolheu "começar do zero"):

1. AskUserQuestion: bundle picker — 4 opções:
   - `firebase-full`
   - `rest-with-firebase-telemetry`
   - `local-only`
   - `custom-from-scratch` (sentinela — pula bundle resolution)
2. Se ≠ `custom-from-scratch`: AskUserQuestion "override algum eixo?" yes/no.
3. Se yes → multiSelect quais eixos → per-axis prompts (com bundle default + alternativas).
4. Se `custom-from-scratch` → vai direto pros prompts per-axis.

**Adaptive UX (platform compaction):**

- Quando card detectado é **uniforme** entre platforms ativas pra um eixo, init apresenta 1 prompt: `axis <X>: <card> (todas plataformas) — confirmar?`
- Quando **divergente**, expande: 1 prompt per (axis, platform) cell.
- Goal mensurável: brownfield com setup mostly-uniform gera ~5-8 prompts; divergente gera mais (proporcional à divergência real).

### Reconfigure flow (W7)

Simétrico ao init. `engine/reconfigure.py` ganha submenu novo "ajustar backend axes":

1. Mostra schema atual (tabela 8 axes × N platforms).
2. AskUserQuestion: quais cells editar (multiSelect).
3. Per cell selecionada:
   - Opções: `null` | escolher card | trocar status | (se status=migrating-to) editar `migrating-to`.
4. Aplica edits atomically (backup `.bak`, history entry, sha256 update).
5. Re-valida: cell.card existe em `cards/`, status enum válido, migrating-to target existe.

Substitui o `_handle_backend` atual (linha ~1108 do `engine/reconfigure.py`) — fluxo legacy (escolha de provider monolítico) é removido inteiro junto com `identity.backend-choice`.

---

## Acceptance criteria

Cada critério é testável; mapeamento pra waves vive no PLAN.

- **AC-1** — `docs/schemas/card.md` documenta cell-object shape (campos `card`, `status`, `migrating-to`) + status enum (active/migrating-to/deprecated) + 8 axes enum (data/auth/observability/analytics/storage/persistence/notifications/flags). Doc novo `docs/schemas/backend-axes.md` formaliza taxonomia + naming rationale ("auth" não "identity").
- **AC-2** — `docs/schemas/workflow-config.md` documenta o bloco `backend:` no shape multi-axis platform-keyed; remove referências a `identity.backend-choice` e `backend.provider`.
- **AC-3** — 4 bundle YAMLs existem em `presets/kmp-mobile/bundles/` (`firebase-full.yaml`, `rest-with-firebase-telemetry.yaml`, `local-only.yaml`); `custom-from-scratch` é sentinela documentada (sem arquivo). Schema dos bundles validado por validator de presets.
- **AC-4** — 6 cards novos existem (`firebase-analytics`, `posthog-analytics`, `fcm`, `onesignal`, `firebase-remote-config`, `posthog-flags`) com `card.yaml` + `signals.yaml` + `README.md` válidos (passam `validate_card_yaml.py` cascade CARD-001..020).
- **AC-5** — Detection composer correctly identifies card per (axis, platform) em fixture de teste com setup misto (retrofit-client em android + ktor-client em kmp simulando migração KMP em curso). Composer emit `Conflict[retrofit, ktor]` na cell `(data, android)` se ambos detectados acima do threshold.
- **AC-6** — Init brownfield flow: detection result apresentado via AskUserQuestion (Phase A intent), adaptive UX compacta quando uniform, expande quando divergent. Smoke test verifica que projeto MeoBonsai-like (uniform Firebase) gera ≤ 8 prompts.
- **AC-7** — Init greenfield flow: bundle picker → opt override → per-axis prompts funcionam. `custom-from-scratch` pula bundle resolution.
- **AC-8** — Reconfigure flow: usuário pode editar cell de null↔card, trocar `status`, atualizar `migrating-to`. Validações enforçam shape (migrating-to required quando status=migrating-to, MUST be absent caso contrário).
- **AC-9** — `identity.category` de todos os cards realinhados conforme migration mapping; zero referência a `category: backend` ou `category: network` em `cards/*/card.yaml`; categorias enumeradas em `docs/schemas/card.md § CARD-004` cobrem (`data, auth, observability, analytics, storage, persistence, notifications, flags`) + preservadas (`language, kmp, ui, navigation, dependency-injection, testing, build, design-system, ticketing`).
- **AC-10** — Labels singulares removidas (`auth-provider`, `http-client`, `crash-reporting`) não aparecem em `cards/*/card.yaml § provides`. `validate_card_yaml.py` não enforça presença delas. `forge verify` passa cascade; baseline pytest verde + novos tests verdes.

---

## Open implementation details

Itens NÃO decididos no brainstorm — agente flagga sensible defaults inline pra reviewer confirmar (visíveis em PR review, nunca silencioso):

1. **Bundle YAML path:** default proposto `presets/kmp-mobile/bundles/<bundle-name>.yaml`. Alternativa: inline em `presets/kmp-mobile/preset.yaml § bundles:`. Default prefere arquivo separado (paridade com `card.yaml` per card).
2. **Detection composer module location:** default proposto `engine/detection/composer.py` (módulo novo, parallel a `engine/init.py`). Alternativa: helper privado em `engine/init.py`. Default prefere módulo separado (testability + reuse).
3. **Status enum `deprecated` semantics — cell-or-card?** Card.yaml já tem `identity.maturity: deprecated` (CARD-005). Cell `status: deprecated` significa: "este card está deprecated NESTE projeto" (mesmo que canonical card.yaml diga `maturity: stable`). São conceitos independentes — agente documenta no SPEC's schema doc (W1).
4. **`firestore-realtime` fate:** mantido em `category: data` por enquanto. Sub-axis "realtime" (separado de "data") fica como follow-up v1.1+ — anotar em `04-pending.md` (W8).
5. **`rest-api-contract` + `firestore-security-rules` sub-cards:** mantidos em `category: data`. Sub-axis "data-contract" ou "rules" são follow-ups v1.1+ — anotar em 04-pending (W8).
6. **Phase A dependency API:** W7 consome AskUserQuestion intent protocol que Phase A delivera. Forma exata do API (single call vs builder pattern, payload shape) ainda não definida — agente lê Phase A SPEC quando ela for shipada, ajusta W7 implementação. Até lá, W7 fica blocked.
7. **`crashlytics` card rename:** considerar rename `crashlytics` → `firebase-crashlytics` (paridade com `firebase-auth`, `firebase-storage`, `firebase-analytics`). Decisão delegada à task de W4 — se rename, registra como deviation tracked no PLAN.
8. **Platform-applicability source:** `card.yaml` hoje não tem campo explícito `platforms: [android, ios, kmp]` — agente verifica `cards/*/card.yaml` schemas atuais. Se ausente, W1 adiciona campo opcional `identity.platforms: [...]` ao schema; composer usa esse campo. Se já existe (sob outro nome), reusa.

---

## Anti-goals + considerações futuras

- **Spike multi-tenant** (multi-projeto compartilhando workflow-config) — out-of-scope v1.x. Anotar em `04-pending.md` se padrão surgir.
- **Backend de "messaging direta"** (chat, push interactivo) — não é eixo canônico v1.0. Anotar como possível 9º axis em `04-pending.md`.
- **Sub-axes formal:** `data` poderia ter sub-axes `transport / contract / realtime / rules`. v1.0 mantém flat (1 card per (data, platform)). Anotar follow-up em 04-pending pós-DET-6 ship.
- **Card composability dentro da mesma cell:** v1.0 não suporta "2 cards ativos na mesma (axis, platform) cell além de migrating-to". Use case: side-by-side multi-tenant Firebase. Anotar follow-up.

---

## Spec coverage table (preview — detalhado no PLAN)

| AC | Wave(s) | Validation |
|---|---|---|
| AC-1 | W1 | schema doc updated + cross-checked |
| AC-2 | W1 | workflow-config schema doc updated |
| AC-3 | W6 | 4 YAML files validated + presets validator |
| AC-4 | W4 | 6 card.yaml files passam CARD-001..020 |
| AC-5 | W5 | unit test composer com fixture mixed setup |
| AC-6 | W7 | smoke test brownfield (depende Phase A) |
| AC-7 | W7 | smoke test greenfield + custom-from-scratch |
| AC-8 | W7 | reconfigure unit/integration test |
| AC-9 | W2 | audit JSON + grep verifica zero `category: backend` |
| AC-10 | W3 | audit JSON + grep verifica labels removidas + forge verify green |
