# Preset: kmp-mobile-firebase

**Status:** stable v1.0.0 (definido em `preset.yaml`).

Preset canônico para projetos Android + iOS + KMP com Firebase como backend.
Espelha a stack do projeto-fixture **MeoBonsai** (`~/Documents/MeoBonsai/`), generalizada para qualquer projeto com o mesmo arquétipo.

## Target stack

- **Android:** Kotlin, Jetpack Compose, Navigation 3
- **iOS:** Swift, SwiftUI, NavigationStack
- **KMP:** shared business logic com expect/actual, SKIE bridge para iOS
- **Backend:** Firebase (Auth, Firestore, Storage, Crashlytics)
- **DI:** Koin Annotations (KMP/Android) + factory functions `create{ClassName}()` (iOS/Web)

## Cards incluídos (12)

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
| 9 | `firebase-auth` | backend-auth | `auth-server`, `firebase-auth` |
| 10 | `firebase-firestore` | backend-persistence | `persistence-server`, `realtime-data` |
| 11 | `firebase-storage` | backend-storage | `file-storage`, `firebase-storage` |
| 12 | `crashlytics` | observability-crash | `crash-reporting`, `crashlytics` |

Lista completa em `preset.yaml § cards`. Cada card vive em `~/Documents/feature-forge/cards/{name}/`.

## Capabilities latentes (esperadas do ambiente)

Cards do preset usam estas labels em `requires:`, mas elas vêm do ambiente, não de outro card:

- `android-platform` — Android SDK + Gradle Android plugin
- `ios-platform` — Xcode + iOS SDK
- `swift-language` — compilador Swift (vem com Xcode)

`forge init` verifica presença antes de ativar o preset.

## Grafo de dependências entre cards

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

firebase-auth            (independente — provê auth-server)
firebase-firestore       (independente — provê persistence-server)
firebase-storage         (independente — provê file-storage)
crashlytics              (independente — provê crash-reporting)
```

Resolver topo-ordena automaticamente. Ordem alfabética é o tiebreaker.

## Conflitos canônicos (declarados nos cards)

- `koin-annotations` → conflita com `dependency-injection` (qualquer outro DI)
- `firebase-auth` → conflita com `auth-server` (qualquer outro provedor de auth)
- `firebase-firestore` → conflita com `persistence-server` server (outro backend de persistência server-side)
- `firebase-storage` → conflita com `file-storage` (outro provedor de file storage)
- `crashlytics` → conflita com `crash-reporting` (Sentry, Bugsnag)

Labels que o ecossistema cita mas não existem no catálogo v1 — anotadas como FOLLOWUP para v1.1:

- `hilt-di`, `koin-dsl` (DI Android alternativos)
- `android-xml-views` (UI Android legado)
- `ios-ui-uikit` (UI iOS legado)
- `navigation2-android` (Navigation 2)
- `material3` (design system específico)

Adicionar essas labels v1.1 requer atualização sincrônica do catálogo + criação de cards correspondentes.

## Detecção (auto-suggest pelo `forge init`)

`preset.yaml § detection` define sinais cumulativos com threshold 0.6:

- Gradle com `kotlin("multiplatform")` (0.25)
- Compose nas deps Android (0.15)
- SwiftUI imports (0.15)
- `shared/` e `iosApp/` dirs (0.10 + 0.10)
- `google-services.json` + `GoogleService-Info.plist` (0.10 + 0.10)
- `firebase-firestore` Gradle dep (0.15)
- SKIE plugin (0.10)

Threshold 0.6 = um projeto KMP+Firebase típico atinge ≥ 0.7 facilmente.

## Defaults seeded no `workflow-config.yaml`

Quando o usuário escolhe este preset em `forge init`, o engine semeia `workflow-config.yaml` com defaults agregados:

- DI: Koin Annotations + factory functions iOS/Web
- Navegação: Nav3 (Android) + SwiftUI NavigationStack (iOS) — AppRoute sealed interface canônica em `shared:core`
- Camadas KMP: data + domain + presentation, dispatcher injection via construtor
- Backend: Firebase em tudo
- Folder layout Android: `{Screen}Screen.kt + {Screen}Content.kt + {Screen}Components.kt + {Screen}Mappers.kt`
- Folder layout iOS: `{Screen}ScreenView.swift + {Screen}ScreenContentView.swift + {Screen}Components.swift + {Screen}Strings.swift`
- Style: SwiftLint + SwiftFormat obrigatórios (sem `disable`)
- Testing: kotlin-test (shared), firestore-emulator (backend e2e)

Lista completa em `preset.yaml § defaults`.

## Referência viva — MeoBonsai

Este preset foi extraído iterando contra `~/Documents/MeoBonsai/`. Todas as convenções/regras nos cards apontam para artefatos reais do MeoBonsai como exemplo:

- Regras: `.claude/rules/*.md`
- Estrutura KMP: `shared/core/`, `shared/feature/{name}/`
- Estrutura Android: `composeApp/`, `androidApp/feature/{name}/`, `navigation/`
- Estrutura iOS: `iosApp/iosApp/Features/{Feature}/`
- Observability: `shared/core/observability/`, `shared/feature/{name}/.../analytics/`
- Firebase contratos: `docs/specs/data/{firestore-data-model,query-catalog,access-matrix,security-and-threat-model}.md`

Veja `INFLUENCES.md` na raiz do feature-forge para o detalhamento do que foi absorvido.

## Lifecycle do preset

- **Escolha:** `forge init` interativo — sugere via detection ou usuário escolhe manualmente.
- **Mudança de preset:** não suportado por `forge reconfigure`. Requer branch dedicada + apagar `.claude/` + novo `forge init`. (Ver `docs/design/06-command-surface.md` migration table.)
- **Adição/remoção de card individual:** via `forge reconfigure` menu cards. Card add/remove não muda o preset declarado em `workflow-config.yaml`, só `cards.active`.
- **Upgrade de preset versão:** v1 não suporta. Snapshot copy local — `forge reconfigure` atualiza cards individualmente.

## FOLLOWUPs conhecidos

Anotados nos cards individuais e consolidados aqui:

1. Catálogo de capability labels v1 não cobre alternativas legadas (Hilt, XML Views, UIKit, Nav2). v1.1 deve resolver.
2. `contract-planner-agent` não declara extension-points em frontmatter (só em tabela no corpo §5) — vários cards tiveram que confirmar via leitura do corpo. Padronizar declaração no frontmatter v1.1.
3. `screen-analysis-agent` ainda não declara extension-points formalmente — alguns cards mantiveram fragments como documentos preparatórios fora de `contributes.agent-prompts`.
4. snake_case (templates) vs kebab-case (alguns exemplos em agent prompts) — convenção canônica é **snake_case** nos artefatos YAML/JSON; normalização global pendente.
