# Card `kotlin-language`

> Categoria: `language` · Maturidade: `stable` · Card folha (sem `requires`)

Kotlin como linguagem primária para o módulo `shared/` (KMP — commonMain) e
para o app Android. Este card é a base de qualquer projeto que use Kotlin
e ancora todas as convenções canônicas de idiomas (`!!` proibido,
`kotlinx.datetime` no commonMain, KDoc só para contratos não-óbvios,
injeção de `CoroutineDispatcher`).

Outros cards (compose-screens, koin-annotations, kmp-shared,
swift-bridge-skie) declaram `requires: [kotlin]` e dependem deste card
estar ativo.

---

## O que este card declara

| Item | Valor |
|---|---|
| `provides` | `kotlin`, `jvm-language` |
| `requires` | nada (leaf) |
| `conflicts-with` | nada |
| `config-defaults` | `conventions.test-pattern.framework-shared: kotlin-test` |
| Detecção (threshold 0.6) | `**/*.kt` (0.5) + `settings.gradle*` contém `kotlin` (0.4) + `build.gradle*` contém `kotlin(` (0.3) |

---

## Quando este card ativa

O `forge init` ativa automaticamente quando detecta:

1. Qualquer arquivo `.kt` no repositório (confidence 0.5).
2. `settings.gradle*` referenciando `kotlin` (confidence 0.4).
3. `build.gradle*` com chamada `kotlin(` — DSL do plugin Kotlin (0.3).

Em projetos Kotlin reais a soma facilmente excede o threshold de 0.6 — o
card auto-ativa. Para projetos só-Swift ou só-TypeScript a detecção falha
e o card fica fora.

---

## O que este card contribui (agent-prompts)

### 1. `tech-spec-agent` → `section:Shared (KMP) layer`

Arquivo: `agent-contributions/tech-spec-additions.md`.

Injeta as regras canônicas de Kotlin idiomático na seção do shared layer
do `tech-spec.md`. Cobre:

- Flow vs suspend (quando usar cada um).
- Reactive streams (`MutableStateFlow`, `Channel.BUFFERED`, `Flow`).
- Thread safety (`Mutex.withLock`, atomics, proibição de `synchronized`).
- Dispatchers e Main thread (injeção, proibição de `runBlocking`).
- KDoc e comentários (`/** */` só para contratos não-óbvios, `//` proibido).
- Thresholds de qualidade (complexidade, profundidade, LOC).
- Anti-patterns críticos (`!!`, `java.time`, `GlobalScope`, `Thread.sleep`).

### 2. `task-contract-writer` → `after:Allowed Files`

Arquivo: `agent-contributions/task-writer-additions.md`.

Orienta o writer sobre:

- Padrões de `allowed_files` para arquivos Kotlin (`**/*.kt`,
  exclusão de `**/build/`).
- Comandos canônicos de validação Kotlin
  (`./gradlew detekt`, `./gradlew ktlintCheck`).
- Estrutura `src/{sourceSet}Main/kotlin/...` (commonMain, androidMain,
  iosMain, commonTest).

---

## O que este card NÃO contribui

Deliberadamente fora do escopo deste card (delegado para cards downstream):

- **Validators executáveis** — `detekt`/`ktlint` ficam em cards
  específicos (ex.: `kotlin-quality-gates`) que rodam scripts.
- **Templates** — formatos de tech-spec ou task-contract são neutros
  na linguagem; cards de framework (compose, koin) é que contribuem
  templates.
- **Hooks** — não há automação pós-edit nesta camada de linguagem.
- **DI específico** — fica em `koin-annotations`.
- **Compose / Android UI** — fica em `compose-screens`.
- **Shared KMP estrutura** — fica em `kmp-shared`.

---

## Referência viva (MeoBonsai)

Este card foi destilado a partir do projeto-fixture
`~/Documents/MeoBonsai/`. Para ver convenções aplicadas em código real:

- Regras canônicas: `.claude/rules/kotlin-idioms.md`
- Estrutura KMP: `.claude/rules/architecture_kmp.md`
- Código real: `shared/core/src/commonMain/kotlin/`

Exemplos curtos extraídos da fixture:

```kotlin
// ✅ kotlinx.datetime no commonMain
import kotlinx.datetime.Clock
import kotlinx.datetime.LocalDate

// ❌ java.time não funciona em commonMain
// import java.time.LocalDate

// ✅ dispatcher injetado
class BonsaiRepository(
    private val service: BonsaiService,
    private val io: CoroutineDispatcher,
) {
    suspend fun fetch(id: String) = withContext(io) { service.get(id) }
}

// ❌ dispatcher hardcoded
// suspend fun fetch(id: String) = withContext(Dispatchers.IO) { ... }

// ✅ StateUI<T> canônico — nunca sealed class custom
private val _state = MutableStateFlow<StateUI<BonsaiUI>>(StateUI.Idle)

// ❌ !! fora de testes
// val name = bonsai.name!!  // proibido
val name = bonsai.name ?: error("name required")
```

---

## Lifecycle

- **Install** (via `forge init` ou menu "adicionar card" no
  `forge reconfigure`): copia este diretório para
  `.claude/cards/kotlin-language/`, registra sha256 em
  `workflow-config.yaml`.
- **Update**: recopia do canonical, mostra diff, requer aceite.
- **Remove**: bloqueado se algum card ativo ainda requer `kotlin`
  (compose-screens, koin-annotations, etc.).

---

## Versionamento

`1.0.0` — primeira versão estável, alinhada com `kotlin-idioms.md` v1
da fixture MeoBonsai (mai/2026).
