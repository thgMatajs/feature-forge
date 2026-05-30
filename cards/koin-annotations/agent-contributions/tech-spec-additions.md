<!--
  Fragment injetado no tech-spec-agent em extension-point
  "section:Shared (KMP) layer" quando o card koin-annotations está ativo.

  O agente deve incorporar este conteúdo ao gerar a seção "Shared (KMP) layer"
  do tech-spec.md, na subseção "DI Strategy".
-->

### Card contribution — DI Strategy (koin-annotations)

Quando esta feature toca o shared layer e adiciona qualquer Service,
Repository, UseCase, Mapper ou ViewModel novo, o tech-spec.md DEVE conter
uma subseção explícita de DI Strategy seguindo as regras abaixo. Não infira;
declare.

**1. Anotações obrigatórias por tipo de componente**

- Service, Repository, Mapper, Analytics, RouteEntry stateless → `@Single`
- UseCase (uma operação de negócio) → `@Factory`
- ViewModel Android-only → `@KoinViewModel` em source set `androidMain` ou
  módulo `androidApp:feature:{name}`
- Container do módulo Gradle → `@Module` + `@ComponentScan("<pkg.raiz>")`

**2. Arquivos a criar/editar**

Para cada feature shared module, sempre dois arquivos no pacote `di/`:

- `{Feature}Module.kt` — uma classe `@Module @ComponentScan(...)` apenas.
  Nada mais nesse arquivo.
- `{Feature}Factory.kt` — `object` com factory functions `create{X}()`
  expostas para iOS/Web. **Mesmo grafo concreto** consumido pelo Android,
  apenas instanciado manualmente.

**3. Proibições que o tech-spec deve listar explicitamente**

- DSL `module { ... }` em código de produção (permitida apenas em
  `commonTest`/`androidUnitTest`).
- `org.koin.*` em código Swift ou TypeScript — iOS/Web não executam runtime
  Koin (JVM-only).
- `@KoinViewModel` em `commonMain`.
- `@Module` sem `@ComponentScan` pareado.

**4. Cross-feature singletons**

Se a feature precisa de um Service compartilhado (por exemplo,
`NetworkMonitor`, `Logger`), declarar como `@Single` em `shared:core/di/CoreModule.kt`
e listar no tech-spec qual módulo passa a depender — não duplicar a declaração
na feature.

**5. Output esperado no tech-spec.md**

Tabela enumerando, para esta feature:

| Componente | Anotação | Arquivo | Consumido por |
|---|---|---|---|
| `{X}Service` | `@Single` | `feature/{name}/data/remote/...` | `{X}Repository` |
| `{X}Repository` | `@Single` | `feature/{name}/data/repository/...` | UseCases |
| `{Verb}{Noun}UseCase` | `@Factory` | `feature/{name}/domain/usecase/...` | ViewModel |
| `{Feature}ViewModel` | `@KoinViewModel` | `androidApp/feature/{name}/.../presentation/` | Compose screen |

E uma diretiva de paridade iOS/Web:

> iOS/Web consomem via `{Feature}Factory.createXxx(...)`; toda dependência
> platform-specific (NetworkMonitor, Logger) é passada como parâmetro da
> factory function.
