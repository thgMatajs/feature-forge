<!--
  Template fragment — tech-spec.md
  Card: swiftui-navigation
  Section: Navigation — iOS (SwiftUI NavigationStack)
  Merge: append-section
-->

## Navigation — iOS (SwiftUI NavigationStack)

Esta seção descreve como a feature integra com a navegação iOS. iOS usa
`NavigationStack` do SwiftUI exclusivamente — **nunca** Navigation 3. As
rotas Swift espelham `AppRoute` do shared (`commonMain`), mas são um
**enum nativo Swift** com `Hashable`, não o tipo Kotlin diretamente.

### Modelo de rotas

Defina um enum Swift por shell de navegação (ex.: `AuthRoute`, `HomeRoute`).
Cada case espelha um destino do `AppRoute` shared, mas com tipos Swift
puros para parâmetros (`String?`, `Int`, etc.). Não usar `KotlinString` nem
expor tipos `Shared.*` como NavKey.

```swift
private enum AuthRoute: Hashable {
    case register
    case login
    case bonsaiForm(bonsaiId: String?)
}
```

### NavigationStack root

O shell do feature (host view) detém o `path` como `@State [Route]` e
declara `.navigationDestination(for:destination:)` no root da
`NavigationStack`. Cada case do enum mapeia para uma `*ScreenView`.

```swift
@State private var path: [AuthRoute] = []

NavigationStack(path: $path) {
    RootScreenView(onNavigate: { path.append($0) })
        .navigationDestination(for: AuthRoute.self) { route in
            switch route {
            case .register: RegisterScreenView(...)
            case .login:    LoginScreenView(...)
            case let .bonsaiForm(id): BonsaiFormScreenView(bonsaiId: id, ...)
            }
        }
}
```

### Operações de navegação canônicas

Helpers privados na view raiz centralizam manipulação de `path`:

- `pop()` → `path.removeLast()`
- `popToRoot()` → `path.removeAll()`
- `replaceTop(with:)` → `path[path.count - 1] = newRoute`
- `replaceAll(with:)` → `path = [newRoute]`

Screens recebem closures (`onNavigateToX`) — nunca manipulam `path`
diretamente, nunca importam `NavigationPath` no escopo da screen.

### Deep links

Deep links chegam via `.onOpenURL { url in ... }` no root da
`NavigationStack`. O handler converte a URL em uma sequência de
`AuthRoute` e atribui `path = [...]` de uma vez (evita animação intermediária).

### Paridade com shared `AppRoute`

A fonte canônica de rotas é o `AppRoute` em `shared/core/.../navigation/`.
O enum Swift precisa ter um case para cada subtipo `AppRoute` que a
feature consome. Diferenças permitidas:

- Tipos primitivos Swift (`String?`) em vez de `KotlinString?`.
- Ordem dos cases pode variar (alfabético em Swift).
- Cases-only-iOS são aceitos se documentados no `navigation-spec.yaml`.

### Anti-patterns proibidos

- `NavHost` / `composable {}` / Navigation 3 APIs no código iOS.
- Expor `AppRoute` Kotlin como NavKey direto via SKIE.
- Manipular `path` dentro de `*ScreenView` (apenas no host).
- `// swiftlint:disable` / `// swiftformat:disable` em arquivos de navegação.
- Strings hardcoded de rota — usar enum cases.

### Arquivos esperados

```
iosApp/iosApp/App/
├── ContentView.swift          # ou {Shell}HostView.swift — NavigationStack raiz
└── Navigation/
    └── {Shell}Route.swift     # enum Swift Hashable
```
