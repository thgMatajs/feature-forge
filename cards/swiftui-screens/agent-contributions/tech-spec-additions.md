<!-- Injected into: tech-spec-agent
     Extension point: section:iOS UI layer
     Source card: swiftui-screens v1.0.0
-->

## iOS UI — SwiftUI (card `swiftui-screens`)

Todo trabalho de UI iOS desta feature é em **SwiftUI puro**. Decisões abaixo
são vinculantes — se o tech-spec precisar violar uma delas, registre como
3-caminhos failure em `open-questions.yaml` em vez de inventar.

### Layout físico obrigatório por tela

Cada `{Screen}` da feature gera quatro arquivos, sob
`iosApp/iosApp/Features/{Feature}/{Screen}/`:

```
{Screen}ScreenView.swift            # host stateful: ViewModelAdapter, @StateObject, .task { }
{Screen}ScreenContentView.swift     # stateless: state + callbacks via parâmetro, layout
{Screen}Components.swift            # subviews + helpers internos da tela
{Screen}Strings.swift               # strings localizadas geradas (i18n)
```

Arquivos auxiliares quando aplicável:

```
{Feature}ViewModelAdapter.swift     # ObservableObject que faz bridge do StateFlow Kotlin → SwiftUI
{Feature}UIFactory.swift            # factory functions de DI (cria adapter + dependências)
{Screen}ScreenContentCallbacks.swift # struct com todos os callbacks da tela (quando > 4)
```

Preview SEMPRE no mesmo arquivo do componente correspondente — **proibido**
criar arquivo dedicado a previews (`{Screen}Previews.swift`).

### Bridging shared Kotlin → SwiftUI

- SKIE transforma `StateFlow<T>` em propriedade publicada automaticamente —
  consumir via `for await … in vm.state` dentro de `.task { }` da View, ou
  via `ViewModelAdapter` quando a tela exige `@StateObject`.
- `suspend fun` Kotlin vira `async throws` Swift via SKIE — chamar com
  `await` em `.task { }`, **nunca** envolver em wrapper manual de
  `withCheckedContinuation`.
- DI via factory function `create{Screen}ViewModel()` exportada do shared
  (KMP). iOS não roda Koin runtime — espelha o resultado de `KoinConfig`
  expondo factories.

### Estado, bindings e foco

- `@StateObject` apenas no `{Screen}ScreenView` (host) — uma instância por
  ciclo de vida da tela.
- `@ObservedObject` no `{Screen}ScreenContentView` quando o adapter é
  passado adiante.
- `@FocusState` declarado no `ContentView` para coordenar ordem de foco
  entre campos. Nunca `firstResponder` UIKit-style.
- `@Environment(\.dismiss)` para fechar sheets/modais — não chamar APIs
  UIKit (`UIViewController.dismiss`) para fluxos novos.

### Navegação SwiftUI canônica

- Container raiz por tab/raiz da app: `NavigationStack(path:)`.
- Tipos de destino: enum/struct conformando a `Hashable`, registrados em
  `.navigationDestination(for:)`.
- Apresentações modais: `.sheet`, `.confirmationDialog`, `.alert` — nunca
  empilhar `NavigationStack` dentro de `.sheet` sem justificativa explícita.
- `NavigationSplitView` apenas para iPad/regular width quando a feature
  exige master-detail.
- Strings hardcoded em destinos → tipos serializáveis Swift que espelham
  `AppRoute` do shared.

### Main Thread e jank

`body` e `init` de `View` rodam na Main. Proibições:

- I/O síncrono (rede, disco, decode pesado) dentro de `body`/`init`.
- `DispatchQueue.main.sync` em qualquer ponto (deadlock se já estiver na Main).
- `Task { … }` sem cancelamento dentro de `body` — usar `.task { }` que é
  cancelada com a View.

Padrões corretos:

- I/O e CPU-bound vivem no shared Kotlin com `withContext(io|default)` —
  SwiftUI só consome o resultado.
- Trabalho Swift CPU-bound (parse JSON local, hashing) → `Task.detached(priority: .userInitiated)`.
- `@MainActor` apenas em código que atualiza UI; trabalho pesado fica em
  função não-isolada e usa `await MainActor.run { }` para devolver à UI.

### Accessibility identifiers e analytics

- Identificadores estáveis vêm de `shared:core/observability/` via SKIE
  (ex.: `AuthTestIds.Register.shared.SUBMIT`). Consumir com
  `.accessibilityIdentifier(...)`.
- Eventos de analytics são logados a partir do shared (`*Analytics.Events`).
  iOS não duplica nomes em enums Swift locais.

### Estilo e linters

- Ferramentas obrigatórias: `SwiftFormat` (config em `/.swiftformat`) e
  `SwiftLint` (config em `/.swiftlint.yml`).
- Comando canônico: `./scripts/swift-style.sh --lint` no CI,
  `./scripts/swift-style.sh --fix` localmente antes do commit.
- `// swiftlint:disable`, `// swiftformat:disable` (qualquer regra,
  qualquer escopo) → **proibido**. Corrigir na raiz: extrair `View` para
  `{Screen}Components.swift`, dividir struct grande, mover lógica para
  ViewModel.

### Anti-patterns que devem aparecer como bloqueio no tech-spec

- ViewModel Swift manual (`ObservableObject`) duplicando state já exposto
  do shared via SKIE.
- `UIHostingController` envolvendo SwiftUI dentro de `UINavigationController`
  para telas novas (apenas interop documentado).
- Lógica de negócio em `View.body` (filtrar/ordenar lista grande, calcular
  totais) — mover para ViewModel.
- `Color(red:green:blue:)` ou hex literal em `View` — usar tokens do design
  system Meo iOS.
- Strings hardcoded em UI — sempre `{Screen}Strings.swift` (gerado de
  `shared/resources/i18n/**`).
