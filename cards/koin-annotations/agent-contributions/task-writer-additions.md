<!--
  Fragment injetado no task-contract-writer em extension-point
  "after:Allowed Files" quando o card koin-annotations está ativo.

  O writer usa este conteúdo para enriquecer as seções `allowed_files` e
  `validations` de tasks que tocam DI.
-->

### Card contribution — Allowed Files + Validations (koin-annotations)

Quando uma task adiciona/modifica um componente DI (Service, Repository,
UseCase, ViewModel, Mapper) ou cria um Gradle module novo, o task-contract
DEVE listar explicitamente os arquivos Koin e os validators correspondentes.

**Allowed-files patterns**

Para tasks de DI, autorize **apenas o path concreto** envolvido. Não use
glob amplo como `**/di/**` no campo `allowed_files`. Exemplo correto:

```yaml
allowed_files:
  - shared/feature/auth/src/commonMain/kotlin/io/gentalha/code/meobonsai/feature/auth/di/AuthModule.kt
  - shared/feature/auth/src/commonMain/kotlin/io/gentalha/code/meobonsai/feature/auth/di/AuthFactory.kt
```

Patterns canônicos esperados para tasks de DI:

- `shared/feature/<name>/src/commonMain/kotlin/**/di/<Feature>Module.kt`
- `shared/feature/<name>/src/commonMain/kotlin/**/di/<Feature>Factory.kt`
- `shared/core/src/commonMain/kotlin/**/di/CoreModule.kt` (apenas para singletons cross-feature)
- `composeApp/src/main/kotlin/**/di/AppModule.kt` (apenas para registro de novos módulos no host Android)

**Validations a adicionar**

Toda task que toca arquivos Module/Factory deve incluir:

```yaml
validations:
  - id: koin-module-componentscan-pair
    command: "python3 .claude/cards/koin-annotations/validators/check-koin-modules.py"
    severity: error

  - id: koin-dsl-banned-in-production
    command: "python3 .claude/cards/koin-annotations/validators/check-koin-modules.py --dsl-check"
    severity: error
```

**Regras determinísticas para o writer**

1. Se a task cria um novo Gradle module shared (`shared:feature:{name}`),
   exigir os dois arquivos `{Feature}Module.kt` e `{Feature}Factory.kt`
   como `allowed_files` — nunca apenas um.

2. Se a task adiciona um ViewModel Android, o `allowed_files` deve incluir
   `androidApp/feature/{name}/.../presentation/{X}ViewModel.kt` e **não**
   permitir `@KoinViewModel` em `commonMain`.

3. Se a task adiciona um `@Single` cross-feature (ex.: `NetworkMonitor`,
   `Logger`), exigir edição de `shared/core/.../di/CoreModule.kt` e
   atualização de `composeApp/src/main/kotlin/**/di/AppModule.kt` para
   incluir o módulo Core no `startKoin`.

4. Se a task adiciona um factory novo em `{Feature}Factory.kt`, exigir
   teste de paridade (mesmo grafo Android↔iOS) listado em
   `task.acceptance_criteria`.
