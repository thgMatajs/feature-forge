<!--
  Injetado em: task-contract-writer
  Extension-point: after:Allowed Files
  Card: swiftui-navigation
-->

## swiftui-navigation — `allowed_files` para tasks de navegação iOS

Quando uma task toca rotas iOS (criar feature nova, adicionar destino,
mover deep link), o `allowed_files` precisa cobrir os arquivos certos —
sem alargar para o app inteiro nem deixar de fora o host.

### Padrões canônicos

Adicione estes globs ao `allowed_files` da task **apenas quando a tarefa
mexer em rotas iOS**:

```yaml
allowed_files:
  # enum Swift de rotas (espelha AppRoute shared)
  - "iosApp/iosApp/App/Navigation/*Route.swift"

  # host com NavigationStack + .navigationDestination
  - "iosApp/iosApp/App/ContentView.swift"
  - "iosApp/iosApp/App/*HostView.swift"

  # screens consumidoras (apenas se a task editar as closures de navegação)
  - "iosApp/iosApp/Features/{Feature}/**/*ScreenView.swift"
```

### Regras para o writer

1. **Não incluir `**/*.swift`** — sempre estreitar para `App/Navigation/`,
   `App/ContentView.swift` e os arquivos da feature em `Features/{Feature}/`.

2. **AppRoute shared também muda?** Se a task altera o `AppRoute` em
   `shared/core/.../navigation/`, abrir uma task separada (Kotlin)
   antes da task iOS — não misturar idiomas no mesmo `allowed_files`.

3. **Deep links**: se a task mexe em `Info.plist` (URL schemes) ou
   `*.entitlements` (associated domains), adicionar explicitamente:
   ```yaml
   allowed_files:
     - "iosApp/iosApp/Info.plist"
     - "iosApp/iosApp/iosApp.entitlements"
   ```

4. **Screens NÃO devem aparecer em tasks de navegação puras** — se a
   única mudança é "empilhar nova rota", apenas o host e o enum mudam.
   Screens só entram se a task tambem altera o que a screen faz com a
   callback de navegação.

### Validações canônicas a anexar

Para qualquer task que toque navegação iOS:

```yaml
validations:
  - cmd: "./scripts/swift-style.sh --lint"
    purpose: "swiftlint + swiftformat (regra repo: nenhum disable comment)"

  - cmd: "./scripts/run-ios-simulator.sh"
    purpose: "build + run no simulador (verifica que NavigationStack compila)"
```

Se o repo não tiver esses scripts, derivar do `inventory.conventions.yaml`
ao invés de inventar comandos.

### Gates obrigatórios

- `build-ios`: app compila com o novo enum/destination.
- `lint-swift`: zero violações swiftlint/swiftformat.
- `navigation-parity`: cada case do enum Swift tem `AppRoute` correspondente
  no shared (validar manualmente listando ambos no `notes:` da task).

### Anti-patterns a recusar

- `allowed_files` contendo `iosApp/**/*.swift` em task de navegação → estreitar.
- Task que altera enum Swift sem listar o host (`ContentView.swift` ou
  `{Shell}HostView.swift`) → host precisa estar presente porque o
  `.navigationDestination` aciona compile-error em case faltante.
- Task de "nova rota" que inclui screens não relacionadas → separar.
