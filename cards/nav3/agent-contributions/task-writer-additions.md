<!--
  Injetado em: task-contract-writer
  Extension-point: after:Allowed Files
  Card: nav3
-->

## nav3 — allowed-files + validations para tasks de Navegação

Quando o card `nav3` está ativo, qualquer task que toque grafo de navegação
precisa restringir o `allowed_files` aos paths canônicos abaixo e
declarar os validators dedicados. Toda fence diferente deve ser
justificada via decision L2 — fora isso é hard-fail de
`task-contract-writer`.

### Allowed files canônicos por categoria de task

#### Task que adiciona/edita uma `route` (`AppRoute.X`)

```yaml
allowed_files:
  - "shared/core/src/commonMain/kotlin/**/core/navigation/AppRoute.kt"
  - "androidApp/feature/{feature}/src/main/kotlin/**/{Feature}NavigationInstaller.kt"
  - "androidApp/feature/{feature}/src/main/kotlin/**/route/*RouteEntry.kt"
forbidden_files:
  - "composeApp/**"
  - "androidApp/navigation/src/main/kotlin/**/AppNavDisplay.kt"
  - "androidApp/navigation/src/main/kotlin/**/Nav3Navigator.kt"
```

`composeApp` nunca muda quando se adiciona rota — se mudou, regra de
modularização foi quebrada.

#### Task que adiciona uma feature nova (módulo `androidApp:feature:{new}`)

```yaml
allowed_files:
  - "androidApp/feature/{new}/build.gradle.kts"
  - "androidApp/feature/{new}/src/main/AndroidManifest.xml"
  - "androidApp/feature/{new}/src/main/kotlin/**/{New}NavigationInstaller.kt"
  - "androidApp/feature/{new}/src/main/kotlin/**/route/*RouteEntry.kt"
  - "androidApp/feature/{new}/src/main/kotlin/**/ui/**/*.kt"
  - "settings.gradle.kts"                      # include(":androidApp:feature:{new}")
  - "composeApp/build.gradle.kts"              # apenas se compose precisar implementation(project(":androidApp:feature:{new}"))
  - "shared/core/src/commonMain/kotlin/**/core/navigation/AppRoute.kt"
```

#### Task que adiciona deep link

```yaml
allowed_files:
  - "androidApp/navigation/src/main/kotlin/**/DeepLinkResolver.kt"
  - "shared/core/src/commonMain/kotlin/**/core/navigation/AppRoute.kt"
  - "androidApp/feature/{feature}/src/main/AndroidManifest.xml"   # intent-filter
```

### Forbidden patterns (validar grep nos diffs antes de fechar a task)

Padrões abaixo são sinais de regressão para Navigation 2 ou DSL
proibida — listar como `forbidden_grep` no contrato da task:

| Pattern | Razão |
|---|---|
| `NavHost(` | Navigation 2 — substituir por `NavDisplay` |
| `composable(` (em uso de Navigation) | Navigation 2 — substituir por `entry<AppRoute.X>` |
| `rememberNavController` | Navigation 2 — Nav3 usa `Navigator` injetado |
| `navigation<` (Koin DSL scoped) | DSL proibida — usar `EntryProviderInstaller` |
| `module {` em arquivo de produção | Koin DSL — usar anotações |
| Hardcoded route string `"feature/{id}"` | Nav3 usa tipos — `AppRoute.X(...)` |

### Validations obrigatórias na task

Adicionar ao bloco `validations:` da task:

```yaml
validations:
  - command: "python3 .claude/cards/nav3/validators/check-no-nav-dsl.py"
    expects: "exit-0"
    severity: error
    description: "Garante que navigation<T> { } e Navigation 2 APIs não foram introduzidas."

  - command: "./gradlew :androidApp:navigation:compileDebugKotlin :androidApp:feature:{feature}:compileDebugKotlin"
    expects: "exit-0"
    severity: error
    description: "Compila o módulo de navegação e o módulo da feature — pega quebra de contrato EntryProviderInstaller."
```

### Definition-of-done específica do card

- `AppRoute.X` declarado em `shared:core` com `@Serializable`.
- RouteEntry da nova rota anotado com `@Factory` e expondo
  `@Composable fun Render()`.
- `{Feature}NavigationInstaller` registrado com
  `@Single(binds = [EntryProviderInstaller::class])`.
- Nenhum diff em `AppNavDisplay.kt` nem em `Nav3Navigator.kt`.
- `navigation-spec.yaml` contém entry em `routes[]` com `route_key`
  apontando para `AppRoute.X` (cross-check com `card_contributions.applied`
  do `contract-planner-agent`).
