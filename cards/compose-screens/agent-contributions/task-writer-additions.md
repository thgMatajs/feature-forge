<!--
  Contribuição do card `compose-screens` injetada em:
    agent: task-contract-writer
    extension-point: after:Allowed Files
-->

## Card-specific: padrões Compose para `allowed_files` e validations

Quando este card está ativo, tasks classificadas como `category: android-ui`
herdam os padrões abaixo. Não improvise nomes — derive sempre do
`screen-analysis.md` (`screen.slug`) e do `tech-spec.md §Android UI layer`.

### Composição obrigatória de `allowed_files` para uma task de tela

Para `TASK-{NNNN}` que implementa a tela `{ScreenName}` da feature `{feature}`,
o `allowed_files` deve seguir este shape:

```yaml
allowed_files:
  - "androidApp/feature/{feature}/ui/{screen}/{Screen}Screen.kt"
  - "androidApp/feature/{feature}/ui/{screen}/{Screen}Content.kt"
  - "androidApp/feature/{feature}/ui/{screen}/{Screen}Components.kt"   # opcional
  - "androidApp/feature/{feature}/ui/{screen}/{Screen}Mappers.kt"      # opcional
  - "androidApp/feature/{feature}/ui/{screen}/{Screen}*Preview.kt"     # raríssimo
```

Regras de inclusão:

- `{Screen}Screen.kt` e `{Screen}Content.kt` SEMPRE aparecem (criar ou
  modificar). Sem exceção.
- `{Screen}Components.kt` só entra se o tech-spec listou 2+ subcomposables
  internos. Caso contrário, omitir do `allowed_files` — task não tem
  permissão para criá-lo.
- `{Screen}Mappers.kt` só entra se o tech-spec listou 2+ funções de mapping.
- `{Screen}*Preview.kt` é proibido por padrão (previews ficam no mesmo
  arquivo do componente). Só liberar se houver justificativa explícita no
  tech-spec.

### Forbidden patterns (negative allowed_files)

Tasks Compose NÃO podem tocar:

```yaml
forbidden_files:
  - "**/*.xml"                          # sem View XML em Compose-only screen
  - "shared/**/*Screen.kt"              # UI no shared é violação contratual
  - "shared/**/*Content.kt"
  - "iosApp/**"                         # task Compose nunca toca iOS
  - "**/*Module.kt"                     # DI module é task separada
```

Se a task precisar mexer em `*Module.kt`, separar em duas tasks
(`TASK-{N}-ui` + `TASK-{N+1}-di`) — não estourar o fence.

### Validations injetadas

Para cada task de UI Compose, adicionar:

```yaml
validations:
  - name: "compose-no-suppress"
    command: "python3 .claude/cards/compose-screens/validators/check-no-suppress.py {{file}}"
    severity: error
    applies-to: "androidApp/feature/{feature}/ui/{screen}/**/*.kt"

  - name: "compose-screen-layout"
    command: "python3 .claude/cards/compose-screens/validators/check-screen-layout.py androidApp/feature/{feature}/ui/{screen}"
    severity: error
    runs-after: edit

  - name: "compose-detekt"
    command: "./gradlew :composeApp:detekt"
    severity: error
    runs-after: edit-batch

  - name: "compose-assemble"
    command: "./gradlew :composeApp:assembleDebug"
    severity: error
    runs-after: edit-batch
```

Os dois primeiros validators são do próprio card (stubs em Phase 5). Os
dois últimos vêm de `inventory.commands.android-build` — task-contract-writer
deve confirmar que existem antes de injetar.

### Gates

```yaml
gates:
  task-complete:
    - all-validations-pass
    - assemble-debug-green
    - previews-render-at-least-once    # quando o repo tem snapshot test
```

### Estrutura de Task Categories

Quando o card está ativo, o task-contract-writer reconhece a categoria:

```yaml
category: android-ui
sub-categories:
  - compose-screen          # cria/edita Screen.kt + Content.kt de uma tela
  - compose-component       # cria/edita item de Components.kt
  - compose-mapper          # cria/edita Mappers.kt isolado
  - compose-preview-fix     # ajusta previews existentes
```

Cada sub-categoria filtra `allowed_files` apropriadamente.

### Sequência típica de tasks Compose dentro de uma feature

1. `TASK-{N}-compose-mapper` — opcional, prepara `{Screen}Mappers.kt` se
   tech-spec exigir.
2. `TASK-{N+1}-compose-component` — opcional, prepara
   `{Screen}Components.kt` quando há subcomposables compartilhados na tela.
3. `TASK-{N+2}-compose-screen` — cria `{Screen}Screen.kt` + `{Screen}Content.kt`
   ligando ViewModel, state e callbacks.

Ordem inversa (tela primeiro, componentes depois) é permitida quando a tela
é simples e cabe inteira em `Content.kt`.
