# Preset: kmp-mobile

**Status:** stable v1.0.0 (definido em `preset.yaml`).

Preset base para projetos Android + iOS + KMP. **Apenas stack** — backend, persistência, auth e observability são escolhas livres ativadas via cards individuais após `forge init`.

## Por que apenas stack?

Em projetos reais, o backend varia: Firebase, REST com Retrofit/Ktor, GraphQL, ou mix híbrido. Forçar um backend canônico no preset enviesa a UX e exige fresh init pra mudar. Solução: preset base inclui só a stack universal (linguagem, KMP, UI, navegação, DI, bridge) e o usuário escolhe backend via cards independentes.

A combinação Firebase ainda é suportada — basta ativar os cards `firebase-auth`, `firestore-persistence`, `firestore-realtime`, `firestore-security-rules`, `firebase-storage`, `crashlytics`. A diferença é que isso virou **escolha** em vez de **default**.

## Target stack

- **Android:** Kotlin, Jetpack Compose, Navigation 3
- **iOS:** Swift, SwiftUI, NavigationStack
- **KMP:** shared business logic com expect/actual, SKIE bridge para iOS
- **DI:** Koin Annotations (KMP/Android) + factory functions `create{ClassName}()` (iOS/Web)

## Cards incluídos (8 — apenas stack)

| # | Card | Role | Provides |
|---|---|---|---|
| 1 | `kotlin-language` | foundation | `kotlin`, `jvm-language` |
| 2 | `kmp-shared` | foundation | `kotlin-multiplatform`, `shared-code` |
| 3 | `compose-screens` | ui-android | `android-ui`, `compose` |
| 4 | `swiftui-screens` | ui-ios | `ios-ui`, `swiftui` |
| 5 | `koin-annotations` | di | `dependency-injection`, `kmp-di`, `android-di` |
| 6 | `skie-bridge` | kmp-bridge | `kotlin-swift-bridge`, `skie` |
| 7 | `nav3` | navigation-android | `navigation-android`, `nav3` |
| 8 | `swiftui-navigation` | navigation-ios | `navigation-ios` |

## Capabilities latentes (esperadas do ambiente)

Cards do preset usam estas labels em `requires:`, mas elas vêm do ambiente, não de outro card:

- `android-platform` — Android SDK + Gradle Android plugin
- `ios-platform` — Xcode + iOS SDK
- `swift-language` — compilador Swift (vem com Xcode)

`forge init` verifica presença antes de ativar o preset.

## Backend candidatos (cards individuais — ativados após init)

`forge init` detecta o stack real e oferece estes combos canônicos:

### Stack Firebase (`backend-candidates.firebase-stack`)
- `firebase-auth` + `firestore-persistence` + `firestore-realtime` + `firestore-security-rules` + `firebase-storage` + `crashlytics`
- **Detection hint:** `google-services.json` + `GoogleService-Info.plist` presentes
- Exemplo real: MeoBonsai

### Stack REST (`backend-candidates.rest-stack`)
- `ktor-client` + `rest-api-contract` + `kotlinx-serialization-json` + `room-database` + `datastore-prefs` + `auth-jwt-bearer`
- **Detection hint:** `io.ktor:ktor-client` + `@SerialName` em DTOs
- Inclui auth JWT Bearer com refresh-token + Ktor Auth plugin
- Persistência local: Room (entidades) + DataStore (prefs)

### Stack híbrida (`backend-candidates.hybrid-firebase-auth-rest-data`)
- `firebase-auth` (identity) + `ktor-client` + `rest-api-contract` + `kotlinx-serialization-json` + `room-database` + `crashlytics`
- **Detection hint:** `google-services.json` + `ktor-client` deps
- Cenário comum: Firebase Auth pelo SDK enterprise + dados via API REST própria

### Stack local-only (`backend-candidates.local-only`)
- `room-database` + `datastore-prefs`
- **Detection hint:** Room presente, sem `google-services.json` nem `ktor-client`
- Apps offline-first sem backend remoto

### Combinações não-listadas

Você pode ativar cards arbitrariamente — não precisa seguir um combo. `forge reconfigure` → menu cards → "adicionar card" deixa selecionar individualmente. Conflitos por capability singular (auth-provider, http-client, persistence-server, file-storage, crash-reporting) são enforced pelo resolver.

## Grafo de dependências do preset base

```
kotlin-language          (leaf — sem deps)
    ↓ provê kotlin
    ├─ kmp-shared        (requires: kotlin)
    │     ↓ provê kotlin-multiplatform
    │     └─ skie-bridge (requires: kotlin-multiplatform, swift-language)
    │
    └─ koin-annotations  (requires: kotlin)

compose-screens          (requires: kotlin, android-platform)
    ↓ provê compose
    └─ nav3              (requires: compose, android-platform)

swiftui-screens          (requires: swift-language, ios-platform)
    ↓ provê swiftui
    └─ swiftui-navigation (requires: swiftui, ios-platform)
```

Resolver topo-ordena automaticamente. Ordem alfabética é o tiebreaker.

## Detecção (auto-suggest pelo `forge init`)

`preset.yaml § detection` define sinais cumulativos com threshold 0.6:

- Gradle com `kotlin("multiplatform")` (0.30)
- Compose nas deps Android (0.20)
- SwiftUI imports (0.20)
- `shared/` e `iosApp/` dirs (0.10 + 0.10)
- SKIE plugin (0.10)

Threshold 0.6 = um projeto KMP-mobile típico atinge ≥ 0.7 facilmente.

Sinais de **backend** (`google-services.json`, `ktor-client`, etc) são tratados por cards individuais, não pelo preset.

## Defaults seeded no `workflow-config.yaml`

Quando o usuário escolhe este preset em `forge init`, o engine semeia `workflow-config.yaml` com defaults agregados da stack:

- DI: Koin Annotations + factory functions iOS/Web
- Navegação: Nav3 (Android) + SwiftUI NavigationStack (iOS) — AppRoute sealed interface canônica em `shared:core`
- Camadas KMP: data + domain + presentation, dispatcher injection via construtor
- Folder layout Android: `{Screen}Screen.kt + {Screen}Content.kt + {Screen}Components.kt + {Screen}Mappers.kt`
- Folder layout iOS: `{Screen}ScreenView.swift + {Screen}ScreenContentView.swift + {Screen}Components.swift + {Screen}Strings.swift`
- Style: SwiftLint + SwiftFormat obrigatórios (sem `disable`)
- Testing shared: kotlin-test

**Defaults de backend, persistência, auth e observability** vêm dos cards específicos que o usuário ativar (firebase-auth, ktor-client, room-database, etc).

Lista completa em `preset.yaml § defaults`.

## Histórico — preset kmp-mobile-firebase removido na Fase 3.5

Versões anteriores (Fase 3 inicial) tinham um preset `kmp-mobile-firebase` que vinha com 12 cards (8 stack + 4 Firebase). O preset Firebase foi arquivado em `presets/.archived/kmp-mobile-firebase-pre-3.5/` durante o refactor da Fase 3.5 por dois motivos:

1. **Viés implícito** — projetos REST (maioria fora do MeoBonsai-like) viam Firebase como assumption silenciosa.
2. **Granularidade insuficiente** — bundle de 4 cards Firebase impedia mix híbrido (ex.: Firebase Auth + REST data).

A migração resultou em:
- `firebase-firestore` (monolítico) → split em `firestore-persistence` + `firestore-realtime` + `firestore-security-rules`
- 6 cards REST novos
- Catálogo formal de capability labels em `docs/schemas/capability-labels.md`
- Templates `data-contract-spec.template.yaml`, `tech-spec.template.md`, `test-strategy.template.yaml` refatorados pra agnóstico
- Agents `contract-planner-agent.md` e `tech-spec-agent.md` patchados com exemplos agnósticos

Ver `docs/design/04-pending.md § Fase 3.5` pra detalhamento.

## Referência viva — MeoBonsai

Convenções de stack vieram iterando contra `~/Documents/MeoBonsai/`. Todas as regras nos cards apontam pra artefatos reais:

- Regras: `.claude/rules/*.md`
- Estrutura KMP: `shared/core/`, `shared/feature/{name}/`
- Estrutura Android: `composeApp/`, `androidApp/feature/{name}/`, `navigation/`
- Estrutura iOS: `iosApp/iosApp/Features/{Feature}/`

MeoBonsai usa stack `kmp-mobile` + combo backend `firebase-stack`.

## Lifecycle do preset

- **Escolha:** `forge init` interativo — sugere via detection ou usuário escolhe manualmente.
- **Mudança de preset:** não suportado por `forge reconfigure`. Requer branch dedicada + apagar `.claude/` + novo `forge init`. (Ver `docs/design/06-command-surface.md` migration table.)
- **Adição/remoção de cards individuais:** via `forge reconfigure` menu cards. Não muda o preset declarado em `workflow-config.yaml`, só `cards.active`.
- **Upgrade de preset versão:** v1 não suporta. Snapshot copy local — `forge reconfigure` atualiza cards individualmente.

## FOLLOWUPs herdados da Fase 3.5

Anotados em `docs/design/04-pending.md § Fase 3.5 — FOLLOWUPs`:

1. snake_case (templates) vs kebab-case (alguns fragments de cards) — normalização global pendente. Templates já estão em snake_case canônico; cards a alinhar.
2. Capability label catalog em `docs/schemas/capability-labels.md` — validator `validate_capability_labels.py` (Phase 5) vai forçar conformidade.
3. Labels reservadas v1.1+: `analytics-pipeline`, `graphql-client`, `websocket-realtime`, `sse-realtime`, `auth-oauth2-rest`. Sem provider v1.
4. Labels out-of-scope v1: `hilt-di`, `koin-dsl`, `android-xml-views`, `ios-ui-uikit`, `navigation2-android`, `material3`.
5. Validator scripts (Phase 5) precisam reconhecer novos top-level keys em `data-contract-spec.template.yaml` (`persistence_strategy`, `operations`, `rest_endpoints`, `local_tables`, `local_prefs`, `realtime_streams`).
