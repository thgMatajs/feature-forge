<!--
  Injetado em: tech-spec-agent
  Extension-point: section:iOS UI layer
  Card: swiftui-navigation
-->

## swiftui-navigation — orientações para a seção "Navigation — iOS"

Use estas regras ao preencher a parte de navegação iOS dentro de §"iOS UI layer"
do `tech-spec.md`. O iOS usa **SwiftUI NavigationStack** exclusivamente —
nunca Navigation 3, nunca UIKit `UINavigationController` direto.

### Decisões obrigatórias no tech-spec

1. **Route enum Swift**: declare o nome do arquivo
   (`iosApp/iosApp/App/Navigation/{Shell}Route.swift`) e os cases derivados
   do `AppRoute` shared. Cada case usa tipos Swift puros (`String?`, `Int`),
   nunca tipos `Shared.*` como parâmetro.

2. **NavigationStack host**: declare qual view detém o `@State [Route]`.
   Tipicamente `ContentView` ou `{Shell}HostView`. Apenas o host manipula
   o `path`; screens recebem closures `onNavigateToX`.

3. **`.navigationDestination(for:destination:)`**: mapeia cada case do enum
   para uma `*ScreenView`. Em features grandes, extrair `@ViewBuilder`
   privado `destinationView(for:)` mantém o `body` legível.

4. **Operações de navegação**: helpers privados `pop()`, `popToRoot()`,
   `replaceTop(with:)`, `replaceAll(with:)` no host. Cada edge do
   navigation-spec mapeia diretamente para uma destas operações.

5. **Deep links**: se aplicável, `.onOpenURL { url in ... }` no root.
   Conversão URL→sequência de routes acontece no host, atribuindo
   `path = [...]` em uma única operação.

### Espelhamento do AppRoute shared

O `AppRoute` Kotlin é a fonte da verdade lógica. Em Swift:

- Existe um case para cada subtipo `AppRoute` consumido pela feature.
- Cases podem aparecer em ordem diferente (Swift idiomático: alfabético).
- Parâmetros viram tipos Swift puros (`String?` em vez de `KotlinString?`).
- `Equatable` + `Hashable` são gerados automaticamente pelo compilador Swift.
- Não importar `Shared.AppRoute` no arquivo do enum iOS.

### Integração com ViewModel adapter

Screens com ViewModel shared (via SKIE) recebem o adapter como `@StateObject`
**dentro de um Host view privado**, não no `.navigationDestination`
diretamente — o destination roda em cada recomposição e recriaria o adapter.
Padrão canônico:

```swift
case .home:
    HomeShellHostView(onNavigateToX: { path.append(.x) })
```

Onde `HomeShellHostView` é `private struct` que faz
`@StateObject private var adapter: HomeViewModelAdapter`.

### Quando criar shell separado vs reusar ContentView

- **1 shell**: app pequeno (auth + home + algumas modais) → ContentView host.
- **N shells**: features grandes com tabs/abas → um `{Shell}HostView`
  por aba com seu próprio `NavigationStack` (multi-stack pattern).

### Validação no tech-spec

Ao gerar §11.3 (test scenarios), garanta que para cada edge do
navigation-spec exista um scenario iOS — mesmo que o teste seja manual via
UI tests, ele precisa estar listado.

### Anti-patterns a explicitar

- `NavHost` ou `composable {}` em qualquer arquivo Swift → erro.
- `import Shared` no arquivo do enum de rota → mover para host view.
- Screen empilhando direto em `path` → refatorar para closure.
- `NavigationLink` com destination inline grande → migrar para
  `.navigationDestination(for:)`.
- `// swiftlint:disable` em qualquer arquivo de navegação → proibido pelo
  rule `swift-style.md`.
