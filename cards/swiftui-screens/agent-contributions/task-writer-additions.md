<!-- Injected into: task-contract-writer
     Extension point: after:Allowed Files
     Source card: swiftui-screens v1.0.0
-->

## Allowed files e validações — iOS SwiftUI (card `swiftui-screens`)

Tarefas que tocam UI iOS desta feature devem respeitar os padrões abaixo no
`allowed_files` e `validations` do Task Contract. **Não invente caminhos**:
derive de `inventory.conventions.folder-layout.ios` e do template
`swiftui-allowed-files.yaml` que este card contribui ao `task-contract.yaml`.

### Padrões de `allowed_files` por tipo de tarefa iOS

Tarefa que cria/edita uma tela SwiftUI nova:

```yaml
allowed_files:
  - "iosApp/iosApp/Features/{Feature}/{Screen}/{Screen}ScreenView.swift"
  - "iosApp/iosApp/Features/{Feature}/{Screen}/{Screen}ScreenContentView.swift"
  - "iosApp/iosApp/Features/{Feature}/{Screen}/{Screen}Components.swift"
  - "iosApp/iosApp/Features/{Feature}/{Screen}/{Screen}Strings.swift"
```

Tarefa que cria/edita o adapter + factory de uma feature:

```yaml
allowed_files:
  - "iosApp/iosApp/Features/{Feature}/{Feature}ViewModelAdapter.swift"
  - "iosApp/iosApp/Features/{Feature}/{Feature}UIFactory.swift"
```

Tarefa que altera apenas callbacks já isolados:

```yaml
allowed_files:
  - "iosApp/iosApp/Features/{Feature}/{Screen}/{Screen}ScreenContentCallbacks.swift"
```

Caminhos **proibidos** em `allowed_files` de tarefas UI:

- `iosApp/iosApp/Features/**/*Previews.swift` — preview vive no mesmo arquivo.
- `shared/**` — UI iOS não edita shared no escopo da mesma tarefa
  (separar em tarefa shared).
- `iosApp/iosApp/**/*.storyboard`, `*.xib` — projeto é SwiftUI-only.

### Validações canônicas a anexar

Toda tarefa iOS UI inclui:

```yaml
validations:
  - name: swiftlint-format-check
    command: "./scripts/swift-style.sh --lint"
    severity: error
  - name: ios-build
    command: "./scripts/run-ios-simulator.sh --build-only"
    severity: error
  - name: card-validator-no-suppress
    command: "python3 .claude/cards/swiftui-screens/validators/check-no-swiftlint-disable.py"
    severity: error
  - name: card-validator-screen-layout
    command: "python3 .claude/cards/swiftui-screens/validators/check-screen-layout-ios.py"
    severity: warn
```

`./scripts/swift-style.sh --lint` é canônico do projeto (alinhado com
`.claude/rules/swift-style.md`). Não substituir por `swiftlint lint` direto —
o script garante paridade com configs locais.

### Gates a registrar

- Pre-commit: `swiftlint-format-check` + `card-validator-no-suppress`.
- Verify-task: todos os 4 acima.
- Pre-push: idêntico a verify-task.

### Categorias de tarefa típicas para este card

- `ios-ui-screen` — criar/editar ScreenView + ContentView + Components + Strings.
- `ios-ui-adapter` — criar/editar ViewModelAdapter + UIFactory.
- `ios-ui-component` — extrair componente reutilizável de tela para Components.
- `ios-i18n` — regenerar Strings a partir de `shared/resources/i18n/**`.

Cada categoria mapeia para um conjunto fixo de `allowed_files`; nunca
combinar shared + iOS UI na mesma tarefa.

### Quando bloquear (severity error → block)

- `// swiftlint:disable` ou `// swiftformat:disable` em diff → bloquear,
  pedir refactor (extrair para `Components.swift`, dividir struct).
- Arquivo `*Previews.swift` no diff → bloquear, mover preview para o
  arquivo do componente.
- `.storyboard` / `.xib` no diff → bloquear (projeto SwiftUI-only).
- Adapter sem factory function correspondente em `{Feature}UIFactory.swift` →
  warn no Task Contract; bloqueia em verify se factory não aparecer no
  diff final.
