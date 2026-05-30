<!-- Injected into: screen-analysis-agent
     Extension point: after:Component Detection
     Source card: swiftui-screens v1.0.0
-->

## SwiftUI inference hints (card `swiftui-screens`)

Quando a feature ativa este card, o agente de screen-analysis assume que a
plataforma iOS será implementada com **SwiftUI puro** (sem UIKit em telas
novas). Use os sinais abaixo para inferir hierarquia, estados e side-effects
da tela diretamente do screenshot/PRD — **sem inventar**. Se faltar evidência,
marque `needs-elicitation` com `phase_lock: TASK-{slug}-ui`.

### Hierarquia SwiftUI a inferir

A tela aparece em três camadas mapeadas para arquivos físicos (ver card
`config-defaults`):

| Camada | Responsabilidade | Arquivo destino |
|---|---|---|
| `{Screen}ScreenView` | Host stateful: instancia `ViewModelAdapter`, observa `@StateObject`/`@ObservedObject`, dispara `.task { … }` para coletar Flows SKIE | `{Screen}ScreenView.swift` |
| `{Screen}ScreenContentView` | Stateless: recebe state + callbacks via parâmetros, monta layout SwiftUI | `{Screen}ScreenContentView.swift` |
| `{Screen}Components` | Subviews internas reutilizadas só nesta tela (cards, rows, headers) | `{Screen}Components.swift` |

Componentes do Design System (Meo*) **não** ficam aqui — são referenciados
e listados em `screen-analysis.md` na seção "Components used".

### Containers de navegação SwiftUI a detectar

Mapeie indícios visuais para containers SwiftUI explícitos:

| Indício visual | Container SwiftUI |
|---|---|
| Tela com push horizontal vindo de outra | `NavigationStack` (raiz) + `NavigationLink(value:)` |
| Modal subindo de baixo, com handle | `.sheet(isPresented:)` |
| Card semi-transparente bloqueando a tela | `.alert(_:isPresented:)` ou `.confirmationDialog(...)` |
| Toolbar com botão "Voltar" custom | `.toolbar { ToolbarItem(placement: .topBarLeading) { … } }` + `.navigationBarBackButtonHidden(true)` |
| Tab bar inferior | `TabView` (geralmente já existe — não recriar) |
| Drawer lateral | `NavigationSplitView` (apenas iPad/regular width) |

### State e bindings

Inferir e listar em `ui-state-spec.yaml`:

- `@State` privado → estado puramente local da View (toggle de password
  visível, foco de campo). Não persiste, não cruza tela.
- `@Binding` → quando subview de `Components` muta valor da tela pai.
- `@StateObject` → instância única do `ViewModelAdapter` no `ScreenView`.
- `@ObservedObject` → adapter já criado pelo pai, passado adiante.
- `@FocusState` → ordem de foco entre campos (`TextField` com `.focused`).
- `@Environment(\.dismiss)` → fechar sheet/modal a partir do conteúdo.

Side-effects e timing a registrar:

- `.task { for await item in flow { … } }` para consumir `Flow` SKIE.
- `.onAppear` apenas para tracking de analytics one-shot (não para I/O).
- `.onChange(of:)` para reagir a binding/state externo.
- `.refreshable { await … }` em listas (pull-to-refresh).

### Main Thread (jank/hitches)

A análise da tela deve sinalizar trabalho pesado que **não** pode rodar em
`body` / `init` da View nem em `LaunchedEffect` SwiftUI equivalente:

- Parse JSON grande, decode de imagem, OCR, hashing → fica no shared Kotlin
  com `withContext(io|default)`. iOS apenas consome resultado já pronto.
- `JSONDecoder` em Swift no fluxo de UI → `Task.detached(priority:.userInitiated)`.
- Loops sobre coleções grandes em `body` → mover para o ViewModel ou
  computar uma vez e cachear em `@State`.
- `DispatchQueue.main.sync` **nunca** — anti-pattern obrigatório de marcar
  no Component UX Matrix se aparecer no PRD.

### Accessibility identifiers

Cada elemento interativo da matriz deve ter um identificador estável vindo
do contrato canônico em `shared:core/observability/` (ex.: `AuthTestIds.shared`)
e ser consumido via `.accessibilityIdentifier(...)`. Strings hardcoded
nessa posição são bloqueio — marque `needs-elicitation`.

### Anti-patterns que viram `needs-elicitation`

Se o PRD/screenshot sugerir algo da lista abaixo, NÃO assuma — abra ponto
de elicitação:

- ViewModel Swift manual (`ObservableObject`) duplicando state do shared
  Kotlin (SKIE já torna `StateFlow` observável).
- Navegação por `UIHostingController` ou `UINavigationController` direto
  (deve ser `NavigationStack` puro, exceto interop legado documentado).
- `// swiftlint:disable` ou `// swiftformat:disable` em qualquer linha —
  proibido por card `swiftui-screens`.
- Preview em arquivo separado (`*Previews.swift`) — preview vive no
  mesmo arquivo do componente.
