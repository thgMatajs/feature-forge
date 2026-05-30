# Card `swiftui-screens`

> Categoria: `ui` · Maturidade: `stable` · Requer `swift-language` + `ios-platform`

SwiftUI como camada de UI iOS para qualquer feature ativa. Ancora o layout
canônico de quatro arquivos por tela, a política absoluta contra
`// swiftlint:disable` / `// swiftformat:disable`, o ponto de bridge para
o shared Kotlin via SKIE e o pipeline `SwiftFormat + SwiftLint` bloqueante.

Este card é o irmão iOS de `compose-screens`. Os dois podem (e devem)
estar ativos ao mesmo tempo em projetos KMP — eles não conflitam porque
provem capabilities ortogonais (`ios-ui`/`swiftui` vs `android-ui`/`compose`).

---

## O que este card declara

| Item | Valor |
|---|---|
| `provides` | `ios-ui`, `swiftui` |
| `requires` | `swift-language`, `ios-platform` |
| `conflicts-with` | nenhum (FOLLOWUP: introduzir `ios-ui-uikit` quando criado) |
| `config-defaults` | layout 4-arquivos, preview-no-mesmo-arquivo, swiftlint, swiftformat |
| Detecção (threshold 0.6) | `import SwiftUI` (0.5) + `iosApp/` (0.3) + `struct ContentView` (0.2) |

---

## Quando este card ativa

`forge init` ativa automaticamente quando detecta:

1. Qualquer arquivo `.swift` contendo `import SwiftUI` (confidence 0.5).
2. Diretório `iosApp/` presente na raiz do repo (confidence 0.3).
3. Qualquer arquivo `.swift` contendo `struct ContentView` — sinal do
   template Xcode padrão (confidence 0.2).

Em projetos com app iOS SwiftUI nativo (template Xcode ou MeoBonsai-like),
a soma supera 0.6 com folga e o card auto-ativa. Em projetos puramente
UIKit (sem `import SwiftUI`), a detecção cai abaixo do threshold.

---

## O que este card contribui

### Templates

| Alvo | Seção | Arquivo | Merge |
|---|---|---|---|
| `tech-spec.md` | `iOS UI layer` | `templates/swiftui-tech-spec-section.md` | `append-section` |
| `task-contract.yaml` | `swiftui-file-patterns` | `templates/swiftui-allowed-files.yaml` | `merge-keys` |

O template de tech-spec injeta o esqueleto obrigatório para a seção iOS:
telas, bridging shared→SwiftUI, hierarquia, estado, threading,
accessibility/observability e linters.

O template de task-contract injeta padrões reutilizáveis de `allowed_files`
(quarteto de tela, callbacks, adapter, factory) e a lista de caminhos
proibidos (previews dedicados, storyboards, xibs, Localizable.strings
hardcoded).

### Agent prompts

| Agent | Extension point | Arquivo |
|---|---|---|
| `screen-analysis-agent` | `after:Component Detection` | `agent-contributions/screen-analysis-additions.md` |
| `tech-spec-agent` | `section:iOS UI layer` | `agent-contributions/tech-spec-additions.md` |
| `task-contract-writer` | `after:Allowed Files` | `agent-contributions/task-writer-additions.md` |

- `screen-analysis-agent` recebe hints para inferir hierarquia SwiftUI a
  partir de screenshots: containers de navegação (`NavigationStack`,
  `.sheet`, `.alert`, `TabView`), bindings (`@State`, `@Binding`,
  `@StateObject`, `@FocusState`, `@Environment(\.dismiss)`), side-effects
  (`.task`, `.onAppear`, `.onChange`, `.refreshable`) e Main Thread rules.
- `tech-spec-agent` recebe as decisões vinculantes da seção iOS: layout
  físico, bridging SKIE, navegação, threading, accessibility, linters,
  anti-patterns.
- `task-contract-writer` recebe padrões de `allowed_files` por categoria
  (`ios-ui-screen`, `ios-ui-adapter`, `ios-ui-component`, `ios-i18n`),
  validações canônicas (`./scripts/swift-style.sh --lint`,
  `./scripts/run-ios-simulator.sh --build-only`) e regras de bloqueio.

### Validators (stubs Phase 5)

| Nome | Arquivo | Runs-on | Severity |
|---|---|---|---|
| `validate-no-swiftlint-disable` | `validators/check-no-swiftlint-disable.py` | `pre-commit`, `verify-task` | `error` |
| `validate-screen-layout-ios` | `validators/check-screen-layout-ios.py` | `verify-task` | `warn` |

Ambos são stubs com `# TODO Phase 5` explicitando a implementação esperada.
Saída atual: `exit 0` + mensagem de identificação.

### Config defaults

| Chave | Valor |
|---|---|
| `conventions.folder-layout.ios` | `"{Screen}ScreenView.swift + {Screen}ScreenContentView.swift + {Screen}Components.swift + {Screen}Strings.swift"` |
| `conventions.ui.swiftui.preview-location` | `"same-file-as-component"` |
| `conventions.style.swift.lint-tool` | `"swiftlint"` |
| `conventions.style.swift.format-tool` | `"swiftformat"` |

---

## Layout canônico por tela

```
iosApp/iosApp/Features/{Feature}/{Screen}/
├── {Screen}ScreenView.swift            # host stateful (ViewModelAdapter, .task)
├── {Screen}ScreenContentView.swift     # stateless (state + callbacks)
├── {Screen}Components.swift            # subviews internas
└── {Screen}Strings.swift               # strings localizadas geradas
```

Arquivos auxiliares quando aplicável:

```
{Feature}ViewModelAdapter.swift             # bridge StateFlow Kotlin → ObservableObject
{Feature}UIFactory.swift                    # factory functions DI
{Screen}ScreenContentCallbacks.swift        # struct de callbacks (quando ≥ 4)
```

Preview **sempre** no mesmo arquivo do componente. Nunca arquivo dedicado.

---

## O que este card NÃO contribui

Deliberadamente fora do escopo:

- **Tokens de design system iOS** — fica em `meo-design-system-ios`
  (futuro). Este card foca em estrutura/scaffolding, não em cores/typo.
- **Navigation iOS além de `NavigationStack` básico** — fluxos
  multi-stack, deep links com restauração de estado etc. ficam em
  `navigation-ios` (FOLLOWUP — label `navigation-ios` já reservada).
- **Bridging shared Kotlin** — mecanismo de bridge é do card
  `swift-bridge-skie` (provide: `kotlin-swift-bridge`, `skie`). Este
  card consome a saída do SKIE, não a configura.
- **Testes UI iOS** — `XCUITest` / `ViewInspector` ficam em card de
  testes iOS dedicado.

---

## Referência viva (MeoBonsai)

Este card foi destilado da fixture `~/Documents/MeoBonsai/`. Para ver as
convenções aplicadas em código real:

- Regras canônicas: `.claude/rules/architecture_ios.md`
- Regras de estilo Swift: `.claude/rules/swift-style.md`
- Código real exemplar:
  - `iosApp/iosApp/Features/Auth/Register/RegisterScreenView.swift`
  - `iosApp/iosApp/Features/Auth/Register/RegisterScreenContentView.swift`
  - `iosApp/iosApp/Features/Auth/Register/RegisterComponents.swift`
  - `iosApp/iosApp/Features/Auth/Register/AuthRegisterStrings.swift`
  - `iosApp/iosApp/Features/Auth/Register/RegisterViewModelAdapter.swift`
  - `iosApp/iosApp/Features/Auth/Register/RegisterUIFactory.swift`

Exemplo curto extraído da fixture:

```swift
// ✅ Host stateful em {Screen}ScreenView.swift
struct RegisterScreenView: View {
    @StateObject private var adapter: RegisterViewModelAdapter

    init() {
        _adapter = StateObject(wrappedValue: createRegisterViewModelAdapter())
    }

    var body: some View {
        RegisterScreenContentView(
            state: adapter.state,
            callbacks: adapter.callbacks
        )
        .task { await adapter.observe() }
    }
}

// ❌ Lógica de I/O em body — proibido
// var body: some View {
//     Text(try! String(contentsOfFile: path))  // jank/ANR
// }
```

---

## Lifecycle

- **Install** (via `forge init` ou menu "adicionar card" em
  `forge reconfigure`): copia este diretório para
  `.claude/cards/swiftui-screens/`, registra sha256 em
  `workflow-config.yaml`.
- **Update**: recopia do canonical, mostra diff, requer aceite.
- **Remove**: bloqueado se algum card ativo ainda requer `ios-ui` ou
  `swiftui` (improvável v1 — nenhum card downstream criado ainda).

---

## Versionamento

`1.0.0` — primeira versão estável, alinhada com:

- `.claude/rules/architecture_ios.md` da fixture MeoBonsai (mai/2026)
- `.claude/rules/swift-style.md` da fixture MeoBonsai (mai/2026)
- Camadas físicas exemplificadas pelo fluxo Auth/Register iOS.
