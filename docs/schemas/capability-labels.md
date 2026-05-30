# Capability labels — canonical catalog v1

Este é o **source of truth** de capability labels para feature-forge v1. Cards declaram `provides:` / `requires:` / `conflicts-with:` em `card.yaml` usando apenas labels listadas aqui. O resolver de cards (engine) usa este catálogo como referência para validar dependências e detectar conflitos.

A validação automática (Phase 5) vai criar `validators/validate_capability_labels.py` para garantir conformidade — cada label usada em qualquer `card.yaml` deve constar deste arquivo.

**Regras canônicas relevantes do schema:**

- **CARD-006** — `provides` deve ser não-vazio para todos os cards
- **CARD-007** — labels em `requires` devem ser referenciáveis (existir como `provides` de algum card)
- **CARD-008** — `conflicts-with` aceita labels OU nomes específicos de cards

---

## Legenda — os 4 tipos

| Tipo | Significado |
|---|---|
| **Singular** | Apenas 1 card pode prover esta label em um mesmo projeto. Cards que provêem labels singulares declaram `conflicts-with: [<label>]` para forçar exclusividade. Aplica-se a labels onde tecnicamente faz sentido só uma escolha por projeto (auth-provider, http-client, persistence-server principal, file-storage, crash-reporting). |
| **Latente** | Capacidade fornecida pelo **ambiente** (Android SDK, Xcode, JDK), não por um card. `forge init` verifica presença antes de ativar cards que requerem labels latentes. |
| **Auxiliar** | Label secundária — múltiplos cards podem prover. Tipicamente labels específicas de tecnologia (ex.: `compose` é auxiliar de `android-ui` singular) ou labels de capability secundária (ex.: `auth-token-bearer` provido por múltiplos auth cards). |
| **Reservada** | Planejada para v1.1+; sem provider v1. Existe documentada para que cards/agents/roteiros não usem nome conflitante antes do tempo. |

---

## Tabela canônica — 9 famílias

### Foundation / Stack

| Label | Família | Provedor(es) v1 | Descrição | Tipo |
|---|---|---|---|---|
| `kotlin` | Foundation | `kotlin-language` | Kotlin como linguagem primária | Singular |
| `jvm-language` | Foundation | `kotlin-language` | Linguagem-alvo JVM | Auxiliar |
| `kotlin-multiplatform` | Foundation | `kmp-shared` | Shared module KMP ativo | Singular |
| `shared-code` | Foundation | `kmp-shared` | Camada de código compartilhado cross-platform | Auxiliar |
| `swift-language` | Foundation | (ambiente Xcode) | Compilador Swift, fornecido com Xcode | Latente |
| `android-platform` | Foundation | (ambiente) | Android SDK + Gradle Android plugin | Latente |
| `ios-platform` | Foundation | (ambiente) | Xcode + iOS SDK | Latente |
| `kotlin-swift-bridge` | Foundation | `skie-bridge` | Bridge idiomática Kotlin↔Swift | Singular |
| `skie` | Foundation | `skie-bridge` | SKIE especificamente como provedor de bridge | Auxiliar |

### Dependency Injection

| Label | Família | Provedor(es) v1 | Descrição | Tipo |
|---|---|---|---|---|
| `dependency-injection` | DI | `koin-annotations` | Framework de DI canônico do projeto | Singular |
| `kmp-di` | DI | `koin-annotations` | DI funcionando no shared KMP | Auxiliar |
| `android-di` | DI | `koin-annotations` | DI no Android (composeApp/feature modules) | Auxiliar |

### UI

| Label | Família | Provedor(es) v1 | Descrição | Tipo |
|---|---|---|---|---|
| `android-ui` | UI | `compose-screens` | Framework de UI Android | Singular |
| `compose` | UI | `compose-screens` | Jetpack Compose especificamente | Auxiliar |
| `ios-ui` | UI | `swiftui-screens` | Framework de UI iOS | Singular |
| `swiftui` | UI | `swiftui-screens` | SwiftUI especificamente | Auxiliar |

### Navigation

| Label | Família | Provedor(es) v1 | Descrição | Tipo |
|---|---|---|---|---|
| `navigation-android` | Navigation | `nav3` | Navegação Android | Singular |
| `nav3` | Navigation | `nav3` | Navigation 3 especificamente | Auxiliar |
| `navigation-ios` | Navigation | `swiftui-navigation` | Navegação iOS | Singular |

### Network / API contracts

| Label | Família | Provedor(es) v1 | Descrição | Tipo |
|---|---|---|---|---|
| `http-client` | Network | `ktor-client` | Cliente HTTP cross-platform (KMP) | Singular |
| `api-contract-rest` | Network | `rest-api-contract` | Convenções REST (endpoints, DTOs, error mapping) | Auxiliar |
| `api-contract-firebase-sdk` | Network | `firestore-persistence` | Calls via SDK Firebase (não-REST) | Auxiliar |
| `realtime-stream` | Network | `firestore-realtime` | Stream realtime (listeners, WebSocket, SSE) | Singular |
| `serialization-json` | Network | `kotlinx-serialization-json` | Serialização JSON canônica KMP | Singular |

### Persistence

| Label | Família | Provedor(es) v1 | Descrição | Tipo |
|---|---|---|---|---|
| `persistence-server` | Persistence | `firestore-persistence` | Persistência server-side (backend DB) | Singular |
| `persistence-local` | Persistence | `room-database` | Banco local (Room — KMP-stable) | Singular |
| `local-prefs-storage` | Persistence | `datastore-prefs` | Preferences small KV (Android DataStore) | Auxiliar |
| `firestore-rules-guarded` | Persistence | `firestore-security-rules` | Cobertura de Firestore security rules | Auxiliar |

### Auth

| Label | Família | Provedor(es) v1 | Descrição | Tipo |
|---|---|---|---|---|
| `auth-provider` | Auth | `firebase-auth` **OU** `auth-jwt-bearer` | Provedor de identidade canônico (um por projeto) | Singular |
| `auth-token-bearer` | Auth | `firebase-auth` **E** `auth-jwt-bearer` | Auth flow baseado em token Bearer (JWT/OAuth) | Auxiliar |
| `auth-firebase-managed` | Auth | `firebase-auth` | Sessão gerenciada pelo SDK Firebase | Auxiliar |

### Storage

| Label | Família | Provedor(es) v1 | Descrição | Tipo |
|---|---|---|---|---|
| `file-storage` | Storage | `firebase-storage` | Storage de arquivos/mídias | Singular |
| `firebase-storage` | Storage | `firebase-storage` | Firebase Storage especificamente | Auxiliar |

### Observability

| Label | Família | Provedor(es) v1 | Descrição | Tipo |
|---|---|---|---|---|
| `crash-reporting` | Observability | `crashlytics` | Reporte de crashes + non-fatal exceptions | Singular |
| `crashlytics` | Observability | `crashlytics` | Firebase Crashlytics especificamente | Auxiliar |

---

## Labels reservadas v1.1+

Estas labels têm nome canônico reservado, mas **não têm provider em v1**. Existem aqui pra evitar collision quando v1.1 adicionar cards correspondentes.

| Label | Família | Planejado para | Notas |
|---|---|---|---|
| `analytics-pipeline` | Observability | v1.1 | Firebase Analytics, Amplitude, Mixpanel |
| `graphql-client` | Network | v1.1 | Apollo KMP, GraphQL Kotlin |
| `websocket-realtime` | Network | v1.1 | Alternativa REST a `realtime-stream` |
| `sse-realtime` | Network | v1.1 | Server-Sent Events |
| `auth-oauth2-rest` | Auth | v1.1 | OAuth2 flow completo (não só bearer token) |

Cards v1 **NÃO** podem usar labels reservadas em `provides:`. Usuários de v1 que precisam destas capabilities devem aguardar v1.1 ou criar card local com label v1.

---

## Labels rejeitadas / out-of-scope v1

Cards do MeoBonsai ou anotações iniciais usaram estas labels durante drafting da Fase 3, mas elas **não entram no catálogo v1**:

| Label | Motivo da rejeição | Status |
|---|---|---|
| `hilt-di` | DI Android-only; v1 escolheu Koin Annotations cross-platform | v1.1 candidate quando houver projeto Android-only que precise |
| `koin-dsl` | DSL runtime de Koin; proibida pela regra do projeto MeoBonsai (Koin Annotations only) | Out-of-scope permanente |
| `android-xml-views` | UI legado; v1 é Compose-first | v1.1 candidate (legacy Android) |
| `ios-ui-uikit` | UI legado iOS; v1 é SwiftUI-first | v1.1 candidate (legacy iOS) |
| `navigation2-android` | Navigation 2; v1 é Nav3 | v1.1 candidate (apps que ainda usam Nav2) |
| `material3` | Design system específico — DS sai do escopo de cards (vira config-default ou inventory) | Out-of-scope v1 |

---

## Migração — Fase 3 → Fase 3.5

Durante a Fase 3 inicial, algumas labels foram usadas com nomes/escopo que mudaram após o refactor Fase 3.5 (cobertura REST + cards Firebase splittados):

| Label v1 inicial | Status final v1 | Justificativa |
|---|---|---|
| `realtime-data` | **Renomeada → `realtime-stream`** | Descreve o mecanismo (stream contínuo), não um tipo de dado. Cards que provêem realtime declaram isto. |
| `auth-server` | **Split → `auth-provider` + `auth-token-bearer` + `auth-firebase-managed`** | Granularidade necessária pra REST/JWT/OAuth coexistirem com Firebase Auth. |
| `persistence-server` | Mantida (já singular) | OK; agora provida por `firestore-persistence` (split do antigo `firebase-firestore`) |
| `file-storage` | Mantida | OK |
| `crash-reporting` | Mantida | OK |

**Cards afetados pelo rename/split (Step 2 do refactor 3.5):**

- `firebase-firestore` → **deletado**, split em `firestore-persistence` (provê `persistence-server`, `api-contract-firebase-sdk`), `firestore-realtime` (provê `realtime-stream`), `firestore-security-rules` (provê `firestore-rules-guarded`)
- `firebase-auth` → patch `provides`: `auth-provider`, `auth-token-bearer`, `auth-firebase-managed`
- `firebase-storage` → spot-check (sem mudança esperada)
- `crashlytics` → spot-check (sem mudança esperada)

**Cards novos REST (Step 2 do refactor 3.5):**

- `ktor-client` → provê `http-client`
- `rest-api-contract` → provê `api-contract-rest`
- `kotlinx-serialization-json` → provê `serialization-json`
- `room-database` → provê `persistence-local`
- `datastore-prefs` → provê `local-prefs-storage`
- `auth-jwt-bearer` → provê `auth-provider`, `auth-token-bearer`

---

## Política de adição de label nova (v1.x)

Adicionar uma label nova ao catálogo requer **4 passos**, executados na **mesma PR**:

1. **PR dedicada** — adição de capability label não slip dentro de outra mudança (princípio de auditabilidade).
2. **Atualizar este catálogo** — tabela canônica + classificação de tipo (Singular / Latente / Auxiliar / Reservada) + família.
3. **Pelo menos 1 card provedor** — a label não pode ser adicionada sem ter card que a provê (exceto labels Reservadas, com justificativa explícita).
4. **Atualizar agent prompts** — se a label aparece em extension-points usados por agents (tech-spec-agent, contract-planner-agent, etc), os prompts devem refletir o catálogo atualizado.

Adicionar label que rompe semântica (renomear / split / merge) requer também migração documentada na seção "Migração Fase X → Y" deste arquivo + spot-check de cards existentes.

---

## Relação com o schema do card

Toda label usada em qualquer `card.yaml` deve constar deste catálogo. O schema em `docs/schemas/card.md` define:

- **CARD-006** — `provides` lista de capability labels, não-vazia
- **CARD-007** — `requires` lista de capability labels (devem ser provided por algum card)
- **CARD-008** — `conflicts-with` lista de labels OU nomes específicos de cards

A Phase 5 vai criar `validators/validate_capability_labels.py` que:

1. Lê este arquivo e extrai labels canônicas
2. Para cada `card.yaml` em `cards/` + snapshot em `.claude/cards/`, valida que toda label em `provides`/`requires`/`conflicts-with` está no catálogo
3. Falha hard se label fora do catálogo for usada
4. Warn se label Reservada for usada (esperando v1.1)

---

## Footer

```yaml
schema-version: 1
last-updated: 2026-05-29
catalog-version: 1.0.0
covers: feature-forge v1.0 + Fase 3.5 refactor (backend-agnostic + REST coverage)
total-labels:
  singular: 13
  latent: 3
  auxiliary: 14
  reserved: 5
  total: 35
```
