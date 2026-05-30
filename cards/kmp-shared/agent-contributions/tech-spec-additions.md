<!--
  Injetado em: tech-spec-agent
  Extension-point: section:Shared (KMP) layer
  Card: kmp-shared
-->

## kmp-shared — orientações para a seção "Shared (KMP) layer"

Use estas regras ao preencher §3 do `tech-spec.md`. Toda decisão precisa ser
rastreável a um artefato upstream (PRD, BDD, data-contract) ou a uma decisão
de memória L2 — nunca inventar abstração.

### Camadas obrigatórias em `commonMain`

A organização do código compartilhado segue três camadas, na ordem
**Presentation → Domain ← Data**. Domain não importa nada de Data nem de
Presentation.

```
shared/feature/{feature}/src/commonMain/kotlin/.../feature/{feature}/
├── data/
│   ├── service/         # {Feature}Service       — IO boundary (Firestore, Ktor, Room)
│   ├── dto/             # {Entity}Response       — wire format, @Serializable
│   ├── mapper/          # {Feature}Mapper        — DTO ↔ Domain
│   └── repository/      # {Feature}RepositoryImpl
├── domain/
│   ├── model/           # nomes puros: Bonsai, UserSession
│   ├── repository/      # {Feature}Repository (interface)
│   └── usecase/         # {Verb}{Noun}UseCase
└── presentation/
    ├── viewmodel/       # {Feature}{Concept}ViewModel
    └── model/           # {Concept}UI, {Concept}UIEvents
```

### State, eventos e efeitos (regra absoluta)

- Estado de tela: `MutableStateFlow<StateUI<T>>` onde `StateUI` é a sealed
  canônica `Idle | Processing | Processed<T> | Error`. **Nunca** crie sealed
  class customizada de loading/error.
- 1–2 ações no ViewModel → funções individuais (`fun load()`, `fun refresh()`).
- 3+ ações → `sealed interface {Concept}UIEvents` + `fun onEvent(event)`.
- Side-effects one-shot (toast, navigate, dialog): **primeiro** campo no
  StateUI (UI consome e limpa). `Channel(Channel.BUFFERED)` só quando há
  race condition ou consumer imprevisível. `Mutex` apenas para concorrência
  em estado mutável fora do StateFlow.

### Flow vs `suspend`

| UseCase entrega… | Assinatura |
|---|---|
| Stream contínuo (lista paginada, realtime) | `operator fun invoke(...): Flow<T>` |
| Operação single-shot que alimenta `StateUI` | `operator fun invoke(...): Flow<T>` (gerencia Loading → Success/Error) |
| Fire-and-forget (delete, toggle, mark-as-read) | `suspend operator fun invoke(...)` |

`suspend` em função que retorna `Flow` é proibido. Se há `Flow<T>` no retorno,
remova `suspend`.

### Dispatcher injection (jank guard)

Repositórios, serviços e use cases que tocam I/O ou CPU-bound recebem
`CoroutineDispatcher` no construtor — nunca hardcode `Dispatchers.IO`:

```kotlin
class BonsaiRepositoryImpl(
    private val service: BonsaiService,
    private val mapper: BonsaiMapper,
    private val ioDispatcher: CoroutineDispatcher,
) : BonsaiRepository
```

- I/O (Firebase, Ktor, Room, DataStore, filesystem) → `Dispatchers.IO`
- CPU-bound (parse JSON grande, sort, crypto, image decode) → `Dispatchers.Default`
- Update de `StateFlow` / UI → `Dispatchers.Main` (default do `viewModelScope`)
- `viewModelScope.launch { withContext(io) { ... } }` para I/O dentro do VM —
  **nunca** `launch(io)` no scope inteiro (perde atualização de state na Main).
- Testes substituem por `UnconfinedTestDispatcher`.

### expect/actual (apenas platform shims)

Use `expect/actual` somente para shims que não podem viver em `commonMain`:
`NetworkMonitor`, `Logger`, `Clock` quando precisa de fonte plataforma-
específica, secure storage. **Nunca** para business logic — se uma regra
de negócio precisa de `expect/actual`, está mal modelada.

### DI (anotações apenas)

- `module { }` DSL **proibida** em produção (permitida apenas em `commonTest`).
- `@Single` → Repository, Service, Mapper.
- `@Factory` → UseCase.
- `@KoinViewModel` → ViewModel (somente quando o consumidor é Android via
  Koin runtime).
- `@Module @ComponentScan("pkg")` por módulo Gradle.
- iOS/Web não consomem Koin runtime: exponha factory function
  `create{ClassName}()` em `di/{Feature}Factory.kt` retornando a árvore
  totalmente instanciada (DI manual).

### Pacotes canônicos em `shared:core`

Promoção de helper cross-feature SEMPRE usa pacote existente. Não criar
pacote vazio por antecipação. Pacotes já existentes:

`di/`, `cache/`, `util/`, `platform/`, `navigation/`, `observability/`,
`storage/`, `error/`.

### Anti-patterns a sinalizar como risk em §13

- DTO/Response vazando para a UI → mapear DTO → Domain → UI.
- `java.time` em `commonMain` → `kotlinx.datetime`.
- `Context`/tipos Android em `commonMain` → `expect/actual` ou interface.
- `!!` fora de testes → `?.`, `?:`, `requireNotNull(...)`.
- `GlobalScope` em qualquer lugar → `viewModelScope` ou escopo de lifecycle.
- `runBlocking` em produção → bloqueia thread (geralmente a Main).
- `@JsExport` em ViewModel → Web gerencia state próprio via hooks.
