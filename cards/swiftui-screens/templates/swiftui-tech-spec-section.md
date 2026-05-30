<!-- Contributed to: tech-spec.md
     Section:        iOS UI layer
     Source card:    swiftui-screens v1.0.0
     Merge mode:     append-section
-->

## iOS UI layer — SwiftUI

> Esta seção é preenchida pelo `tech-spec-agent` com as decisões concretas
> da feature. O esqueleto abaixo é o contrato mínimo que cada tech-spec
> precisa cobrir quando `swiftui-screens` está ativo.

### Telas introduzidas / tocadas

| Tela | Pacote físico | Tipo |
|---|---|---|
| `{Screen}` | `iosApp/iosApp/Features/{Feature}/{Screen}/` | nova \| modificada |

Para cada tela: descrever os quatro arquivos canônicos
(`{Screen}ScreenView.swift`, `{Screen}ScreenContentView.swift`,
`{Screen}Components.swift`, `{Screen}Strings.swift`) e qual o ponto de
entrada na navegação iOS.

### Bridging shared Kotlin → SwiftUI

- ViewModel consumido: `{Feature}ViewModel` (no shared/presentation).
- Adapter iOS: `{Feature}ViewModelAdapter.swift` — descrever responsabilidades
  (espelhar `StateFlow<StateUI<{Feature}UI>>`, expor callbacks que chamam
  `viewModel.onEvent(...)` ou métodos individuais).
- Factory: `{Feature}UIFactory.swift` — listar as factory functions
  `create{Class}()` do shared que esta tela consome.
- Side-effects observados via `.task { for await … in vm.flow { … } }`
  (eventos one-shot) — listar quais eventos, qual o efeito visual (toast,
  navigate, dismiss).

### Hierarquia SwiftUI

Para cada tela, descrever em árvore a hierarquia esperada:

```
{Screen}ScreenView
└─ {Screen}ScreenContentView(state:, callbacks:)
   ├─ Meo{Component} (do design system)
   ├─ {Screen}Components.{Subview} (interno da tela)
   └─ ...
```

Sinalizar containers: `NavigationStack`, `.sheet`, `.alert`, `TabView`,
`NavigationSplitView` — com justificativa para cada.

### Estado e foco

- `@StateObject` no host (`{Screen}ScreenView`) — adapter único.
- `@FocusState` declarado quando há > 1 campo de texto — descrever a
  ordem de tab/return.
- `@Environment(\.dismiss)` quando a tela é apresentada como sheet/modal.
- `@State` privado apenas para UI puramente local (toggle de mostrar
  senha, animation flag) — listar cada uso e por que não cabe no
  StateUI compartilhado.

### Threading e Main Thread

- Confirmar que nenhuma operação I/O ou CPU-bound roda em `body`/`init`.
- Trabalho pesado mora no shared Kotlin (`withContext(io|default)`).
- Trabalho Swift CPU-bound (raro, ex.: parse local) usa
  `Task.detached(priority: .userInitiated)`.

### Accessibility / observability

- Listar IDs de `shared:core/observability/{Feature}TestIds.kt` aplicados
  via `.accessibilityIdentifier(...)`.
- Listar eventos de `shared:core/observability/{Feature}Analytics.kt`
  disparados a partir do shared (iOS não duplica nomes).

### Estilo (linters)

- SwiftFormat + SwiftLint via `./scripts/swift-style.sh --lint` no CI.
- Confirmar explicitamente: nenhuma diretiva
  `// swiftlint:disable` / `// swiftformat:disable` será introduzida.
- Confirmar: previews vivem no mesmo arquivo do componente.

### Riscos e perguntas abertas (iOS)

- (registrar aqui)
