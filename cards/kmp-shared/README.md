# Card · `kmp-shared`

Kotlin Multiplatform shared module com `kotlinx.coroutines`,
`kotlinx.serialization`, `kotlinx.datetime`, `expect/actual` para platform
shims e camadas **Domain / Data / Presentation** em `commonMain`.

| Campo | Valor |
|---|---|
| Nome | `kmp-shared` |
| Versão | `1.0.0` |
| Categoria | `kmp` |
| Maturidade | `stable` |
| Provides | `kotlin-multiplatform`, `shared-code` |
| Requires | `kotlin` |
| Conflicts-with | — |
| Rules link | `architecture_kmp` |

---

## O que é

O card `kmp-shared` declara as convenções canônicas para o módulo
compartilhado (`shared/`) de um projeto Kotlin Multiplatform. Ele assume
que `kotlin` está ativo (via card `kotlin-language`) e adiciona em cima:

- Estrutura de camadas **Domain / Data / Presentation** dentro de
  `commonMain`.
- Tipos canônicos: `kotlinx.datetime.LocalDate`/`Instant` (nunca
  `java.time`), `kotlinx.serialization` para DTOs, `kotlinx.coroutines.Flow`
  e `StateFlow` para streams.
- `expect/actual` **somente** para platform shims (`NetworkMonitor`,
  `Logger`, secure storage, `Clock`) — nunca para regra de negócio.
- Dispatcher injection no construtor (`IO` para repositórios, `Default`
  para parsing/CPU-bound, `Main` para UI updates).
- DI por anotação Koin (`@Single`, `@Factory`, `@KoinViewModel`,
  `@Module @ComponentScan`) — DSL `module { }` proibida em produção.
  iOS/Web consomem via factory functions `create{ClassName}()`.
- Split rígido entre **DTO** (`{Entity}Response`, wire format) e
  **Domain Model** (nome puro, sem sufixo), conectados por um mapper
  explícito.

O card é deliberadamente fino: convenções de DI específicas (Koin
Annotations) vivem no card `koin-annotations`; observabilidade no card
`observability`; navegação no card `nav3`. O `kmp-shared` cuida apenas
da camada compartilhada e das suas regras de organização.

---

## Quando ativa

Auto-ativa quando o `forge init` detecta sinais cumulativos ≥ 0.6:

| Sinal | Confiança |
|---|---|
| `build.gradle*` contém `kotlin-multiplatform` | 0.5 |
| `build.gradle*` contém `kotlin("multiplatform")` | 0.4 |
| Diretório `shared/` existe | 0.2 |
| Algum `**/*.kt` contém `expect ` (cobrindo `expect fun`/`expect class`) | 0.3 |

Threshold `0.6` significa que basta o plugin gradle estar declarado, ou
o uso explícito de `expect/actual`, para ativar. O sinal `directory-exists`
sozinho não dispara — evita falso-positivo em projetos JVM que tenham
um diretório `shared/` por outra razão.

Cards alternativos quando este não ativa: nenhum por ora (Android-only
puro continua usando o card `kotlin-language` sem `kmp-shared`).

---

## O que contribui

### Templates (`tech-spec.md`)

| Target | Section | Arquivo | Merge |
|---|---|---|---|
| `tech-spec.md` | `Shared (KMP) layer` | `templates/kmp-tech-spec-section.md` | `append-section` (entra como §3.5) |

O fragment adiciona à §3 do tech-spec: tabela de pacotes permitidos por
camada, tabela de UseCases, tabela de dispatchers injetados, listagem
explícita de `expect/actual` e DI wiring (common + iOS/Web).

### Agent prompts

| Agent | Extension-point | Arquivo |
|---|---|---|
| `tech-spec-agent` | `section:Shared (KMP) layer` | `agent-contributions/tech-spec-additions.md` |
| `contract-planner-agent` | `section:Data Contract` | `agent-contributions/contract-planner-additions.md` |
| `task-contract-writer` | `after:Allowed Files` | `agent-contributions/task-writer-additions.md` |

- **tech-spec**: regras de Domain/Data/Presentation, Flow vs `suspend`,
  dispatcher injection, anti-patterns a sinalizar como risk.
- **contract-planner**: força split DTO ↔ Domain Model + mapper explícito
  no `data-contract-spec.yaml`, com tabela de null-handling por campo.
- **task-writer**: ordem canônica de tasks (Data → Domain → Presentation
  → DI), patterns de `allowed_files` por camada, bloqueios automáticos
  (ex: TASK de Presentation sem TASK de UseCase prévio).

### Config defaults

```yaml
conventions:
  kmp:
    layer-structure: "data + domain + presentation"
    dispatcher-injection: "constructor"
```

---

## MeoBonsai como referência viva

A estrutura canônica aplicada por este card vive em
`~/Documents/MeoBonsai/`:

- `.claude/rules/architecture_kmp.md` — fonte das regras de camada,
  pacotes em `shared:core`, nomenclatura, anti-patterns.
- `.claude/rules/kotlin-idioms.md` — Flow vs `suspend`, dispatchers,
  reactive streams, thread safety.
- `shared/core/src/commonMain/kotlin/.../core/` — pacotes canônicos
  já existentes (`di/`, `cache/`, `util/`, `platform/`, `navigation/`,
  `observability/`, `storage/`, `error/`).
- `shared/feature/{feature}/src/commonMain/kotlin/.../feature/{feature}/`
  — split por feature seguindo `data/`, `domain/`, `presentation/`, `di/`.

Antes de editar este card, leia esses dois arquivos de regras — eles
são a fonte de verdade para qualquer ajuste de convenção.

---

## Exemplos curtos

### Service + Repository com dispatcher injetado

```kotlin
class BonsaiRepositoryImpl(
    private val service: BonsaiService,
    private val mapper: BonsaiMapper,
    private val ioDispatcher: CoroutineDispatcher,
) : BonsaiRepository {
    override fun observe(id: String): Flow<Bonsai> =
        service.observe(id)
            .map(mapper::toDomain)
            .flowOn(ioDispatcher)
}
```

### UseCase: Flow vs suspend

```kotlin
class ObserveBonsaiUseCase(private val repo: BonsaiRepository) {
    operator fun invoke(id: String): Flow<Bonsai> = repo.observe(id)
}

class DeleteBonsaiUseCase(private val repo: BonsaiRepository) {
    suspend operator fun invoke(id: String) = repo.delete(id)
}
```

### ViewModel com StateUI

```kotlin
class BonsaiDetailViewModel(
    private val observeBonsai: ObserveBonsaiUseCase,
) : ViewModel() {
    private val _state = MutableStateFlow<StateUI<BonsaiDetailUI>>(StateUI.Idle)
    val state: StateFlow<StateUI<BonsaiDetailUI>> = _state.asStateFlow()

    fun load(id: String) {
        viewModelScope.launch {
            _state.value = StateUI.Processing
            observeBonsai(id)
                .map { it.toUI() }
                .catch { _state.value = StateUI.Error(it) }
                .collect { _state.value = StateUI.Processed(it) }
        }
    }
}
```

---

## Anti-patterns que este card flagra

- DTO/`Response` vazando para UI.
- Sealed class customizada para loading/error (use `StateUI<T>`).
- `java.time.*` em `commonMain`.
- `Context` (Android) em `commonMain`.
- `module { }` Koin DSL em produção.
- `runBlocking` em código de produção.
- `expect/actual` para business logic.
- `@JsExport` em ViewModel.
