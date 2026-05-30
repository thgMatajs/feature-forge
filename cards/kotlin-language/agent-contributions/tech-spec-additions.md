<!-- Injected into: tech-spec-agent
     Extension point: section:Shared (KMP) layer
     Source card: kotlin-language v1.0.0
-->

## Kotlin language conventions (card `kotlin-language`)

Todo código novo no shared layer (commonMain) e no Android segue as regras
abaixo. Decisões registradas no tech-spec devem ser coerentes — se o spec
prescreve algo que viola uma destas regras, sinalize como
**3-caminhos failure** no `open-questions.yaml` em vez de inventar.

### Flow vs suspend

- Operação single-shot (fetch, delete, toggle, mark) → `suspend fun`.
  **Nunca** `Flow<T>` para single-shot.
- Stream de valores (paginação, real-time) → `Flow<T>`.
- UseCase que alimenta `StateUI` (loading → success/error) → `Flow<T>`.
- Função que retorna `Flow` **não pode** ter modificador `suspend`.

### Reactive streams

| Cenário | Ferramenta |
|---|---|
| Estado de tela | `MutableStateFlow<StateUI<T>>` |
| Evento one-shot (toast, navigate, dialog) | `Channel<T>(Channel.BUFFERED)` |
| Stream de dados | `Flow<T>` |
| Broadcast multi-collector | `SharedFlow` (raro — justificar) |

`Channel()` sem capacidade é RENDEZVOUS (0) — perde eventos. Sempre
`Channel.BUFFERED` ou `Channel(1)`.

### Thread safety

| Cenário | Ferramenta |
|---|---|
| Estado reativo UI | `MutableStateFlow` |
| Seção crítica em coroutines | `Mutex.withLock {}` |
| Flag/contador atômico | `AtomicBoolean` / `AtomicInteger` |
| Coroutine code | **Nunca** `synchronized` (bloqueia a thread) |

### Dispatchers e Main thread

- `CoroutineDispatcher` **injetado** no construtor de Repository/UseCase/
  Service. Nunca hardcode `Dispatchers.IO` no corpo (impede teste com
  `UnconfinedTestDispatcher`).
- I/O (rede, persistência, arquivos) → `withContext(io) { … }`.
- CPU-bound (parse JSON grande, decode imagem, crypto, regex pesado) →
  `withContext(default) { … }`.
- Update de `StateFlow`/UI fica na Main (default do `viewModelScope`).
- `runBlocking` **proibido** em produção (bloqueia a thread chamadora —
  tipicamente a Main).
- Loops longos em coroutine → `yield()` ou `ensureActive()` periódico.

### KDoc e comentários

- `/** */` obrigatório em:
  - Interfaces públicas com contratos não-óbvios.
  - `suspend` que lança exceções de plataforma (Firebase, Ktor).
- `/** */` **proibido** em:
  - Funções triviais, data classes, implementações `*Impl`.
- Comentário inline `//` **nunca** (código deve ser auto-explicativo).

### Thresholds de qualidade

| Métrica | Limite |
|---|---|
| Complexidade ciclomática | 15 / método |
| Profundidade de blocos | 4 níveis |
| Linhas por classe | 600 |
| Funções por classe | 15 |

### Anti-patterns críticos (bloquear no tech-spec)

- `!!` fora de testes → `?.`, `?:`, `requireNotNull()`.
- `catch (e: Exception) {}` vazio → logar/relançar.
- `var` onde `val` serve.
- `GlobalScope` → `viewModelScope` ou escopo de lifecycle.
- `Thread.sleep()` → `delay()`.
- `java.time` no commonMain → `kotlinx.datetime` (LocalDate, Clock, Instant).
- `@Suppress(...)` para contornar detekt/ktlint → corrigir na raiz.
- Wildcard imports (`import foo.*`).
- `lateinit var` em modelo/UI state (usar `val` + default).

### Quando registrar no tech-spec

Cada decisão de Kotlin idiomático que afeta a arquitetura deve aparecer
explícita na seção "Shared (KMP) layer" do tech-spec:

- Quais dispatchers são injetados em quais classes.
- Onde mora cada `Mutex` (se houver concorrência real).
- Qual canal (`Channel.BUFFERED`) carrega cada evento one-shot.
- Justificativa quando `SharedFlow` é escolhido sobre `StateFlow`.
