# Card `swiftui-navigation`

> Categoria: `navigation` · Maturidade: `stable` · Requer: `swiftui`, `ios-platform`

Navegação iOS via `NavigationStack` do SwiftUI. O modelo de rotas é um enum
Swift `Hashable` que **espelha** o `AppRoute` do shared (Kotlin sealed
interface em `commonMain`), mas é tipo Swift nativo — nunca o tipo
Kotlin diretamente, nunca Navigation 3 no iOS.

Este card encapsula uma decisão arquitetural forte: enquanto Android usa
Navigation 3 sobre a mesma fonte canônica `AppRoute`, o iOS materializa
essa fonte como enum Swift puro e dirige a navegação por
`.navigationDestination(for:destination:)`.

---

## O que este card declara

| Item | Valor |
|---|---|
| `provides` | `navigation-ios` |
| `requires` | `swiftui`, `ios-platform` |
| `conflicts-with` | nada |
| `config-defaults` | `conventions.navigation.ios: swiftui-navigation-stack` · `conventions.navigation.ios-route-source: Swift enum mirroring shared AppRoute` |
| Detecção (threshold 0.6) | `NavigationStack` (0.5) + `NavigationLink` (0.3) + `navigationDestination` (0.3) em `**/*.swift` |

---

## Quando este card ativa

`forge init` auto-ativa quando detecta, em qualquer arquivo `.swift`:

1. `NavigationStack` (confidence 0.5).
2. `NavigationLink` (confidence 0.3).
3. `navigationDestination` (confidence 0.3).

Em projetos iOS modernos com SwiftUI a soma facilmente excede 0.6 — o
card auto-ativa. Para projetos só-Android, só-Web, ou iOS legado
puro-UIKit a detecção falha e o card fica fora.

---

## O que este card contribui

### 1. Template — `tech-spec.md` § "Navigation — iOS (SwiftUI NavigationStack)"

Arquivo: `templates/swiftui-nav-tech-spec-section.md`.

Append-section ao `tech-spec.md` com o desenho canônico de navegação iOS:
enum Swift de rotas, host com `NavigationStack`, helpers `pop()` /
`popToRoot()` / `replaceTop` / `replaceAll`, integração com deep links via
`.onOpenURL`, regras de paridade com `AppRoute` shared.

### 2. Agent prompt — `contract-planner-agent` § `section:Navigation`

Arquivo: `agent-contributions/contract-planner-additions.md`.

Orienta o planner sobre o que o `navigation-spec.yaml` precisa carregar
para que iOS gere o enum Swift correto: campo `ios-case`, mapeamento
de cada edge para a operação iOS canônica (`path.append`, `replaceTop`,
`replaceAll`, `pop`, `popToRoot`), argumentos opcionais como `String?`
puro, tratamento de cases-only-iOS, deep links via `.onOpenURL`.

### 3. Agent prompt — `tech-spec-agent` § `section:iOS UI layer`

Arquivo: `agent-contributions/tech-spec-additions.md`.

Detalha as decisões obrigatórias no tech-spec iOS: nome do arquivo do
enum, view-host que detém o `path`, `.navigationDestination` no root,
integração com adapters `@StateObject` em host views privadas (não
dentro do destination), padrão multi-stack para apps com tabs, anti-patterns
proibidos (`NavHost`, `composable`, `import Shared` no enum de rota,
screens manipulando `path` direto).

### 4. Agent prompt — `task-contract-writer` § `after:Allowed Files`

Arquivo: `agent-contributions/task-writer-additions.md`.

Padrões de `allowed_files` para tasks que tocam navegação iOS:
`iosApp/iosApp/App/Navigation/*Route.swift`, `App/ContentView.swift`,
`App/*HostView.swift`, e screens só quando a task tambem altera a callback
de navegação. Inclui validações canônicas (`./scripts/swift-style.sh --lint`,
`./scripts/run-ios-simulator.sh`) e gates (`build-ios`, `lint-swift`,
`navigation-parity`).

---

## O que este card NÃO contribui

Deliberadamente fora do escopo (delegado a outros cards):

- **Validators executáveis** — checagem de paridade enum Swift ↔ AppRoute
  shared seria um validator próprio, mas fica para um card futuro
  (`swiftui-navigation-parity-check`).
- **Hooks** — sem automação pós-edit nesta camada.
- **Estrutura de screens** — fica em `swiftui-screens` (host/content/components).
- **Navegação Android** — fica em `nav3`.
- **AppRoute shared** — fica em `kmp-shared` (a sealed interface
  serializável Kotlin é fonte canônica das rotas).
- **Deep link entitlements / URL schemes Info.plist** — fica em
  `ios-platform`.

---

## Referência viva (MeoBonsai)

Este card foi destilado do projeto-fixture `~/Documents/MeoBonsai/`:

- Regras canônicas: `.claude/rules/architecture_ios.md` § "Navegação".
- Implementação real do host com `NavigationStack`:
  `iosApp/iosApp/ContentView.swift` (linhas 8-138).
- Enum Swift de rotas: `AuthRoute` em `ContentView.swift` linhas 130-138
  (no MeoBonsai o enum ainda vive co-localizado com o host; um arquivo
  dedicado `App/Navigation/{Shell}Route.swift` é o destino canônico).

Exemplo curto extraído da fixture:

```swift
@State private var path: [AuthRoute] = []

NavigationStack(path: $path) {
    WelcomeScreenView(
        onNavigateToRegister: { path.append(.register) },
        onNavigateToLogin: { path.append(.login) }
    )
    .navigationDestination(for: AuthRoute.self) { route in
        switch route {
        case .register: RegisterScreenView(...)
        case .login:    LoginScreenView(...)
        case let .bonsaiForm(id): BonsaiFormScreenView(bonsaiId: id, ...)
        // ...
        }
    }
}

private enum AuthRoute: Hashable {
    case register
    case login
    case bonsaiForm(bonsaiId: String?)
    // ...
}
```

E a regra absoluta da fixture (`architecture_ios.md`):

> Usar `NavigationStack` do SwiftUI — **NUNCA** Navigation 3. Rotas Swift
> espelham `AppRoute` do shared mas são tipos nativos Swift.

---

## Lifecycle

- **Install** (`forge init` ou menu "adicionar card"): copia este diretório
  para `.claude/cards/swiftui-navigation/`, registra sha256 em
  `workflow-config.yaml`.
- **Update**: recopia do canonical, mostra diff, requer aceite.
- **Remove**: bloqueado se alguma feature ativa depende explicitamente
  de `navigation-ios` ou se o app ainda tem `NavigationStack` em uso.

---

## Versionamento

`1.0.0` — primeira versão estável, alinhada com `architecture_ios.md`
§ "Navegação" da fixture MeoBonsai (mai/2026).
