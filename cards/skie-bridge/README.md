# Card `skie-bridge`

> Categoria: `kmp` · Maturidade: `stable` · Requer `kotlin-multiplatform` + `swift-language`

SKIE ([co.touchlab.skie](https://skie.touchlab.co)) é o plugin de
compilação Kotlin/Native que reescreve a Objective-C header gerada pelo
compilador para Swift idiomático. Sem SKIE, o iOS consome Kotlin via
ObjC headers verbosos (callbacks ao invés de `async`, `KotlinFlow` opaco,
`KotlinEnum` sem `switch` exaustivo). Com SKIE, o iOS consome Kotlin
como se fosse Swift nativo.

Este card declara as convenções de uso do SKIE neste projeto e contribui
fragments para `tech-spec.md` (seção iOS UI layer) e para o
`task-contract-writer` (allowed-files Swift + comandos de build do
framework compartilhado).

---

## O que este card declara

| Item | Valor |
|---|---|
| `provides` | `kotlin-swift-bridge`, `skie` |
| `requires` | `kotlin-multiplatform`, `swift-language` |
| `conflicts-with` | — (nenhum substituto canônico) |
| `config-defaults` | `conventions.kmp.swift-bridge: skie`, `conventions.kmp.ios-flow-pattern: SharingStarted.WhileSubscribed(5000)` |
| Detecção (threshold 0.6) | `build.gradle*` contém `skie` (0.5) + `co.touchlab:skie` (0.4) + `*.kts` contém `co.touchlab.skie` (0.3) |

---

## Quando este card ativa

`forge init` ativa automaticamente quando o `shared/build.gradle.kts`
referencia `co.touchlab.skie` (alias plugin) ou quando o version catalog
declara o plugin SKIE. Para projetos KMP que ainda usam apenas as
headers ObjC nativas do compilador Kotlin/Native, a detecção falha e o
card fica fora.

---

## Recursos cobertos pelo SKIE

| Recurso Kotlin | Swift sem SKIE | Swift com SKIE |
|---|---|---|
| `suspend fun foo()` | callback `(Result, Error) -> Void` | `func foo() async throws` |
| `Flow<T>` | `KotlinFlow` (opaco) | `AsyncSequence` consumível com `for await` |
| `sealed interface Foo { … }` | `KotlinBase` subclasses | `enum Foo` com `switch` exaustivo |
| Generics `Repository<T>` | apagados (`Any?`) | preservados como `Repository<T>` |
| Default arguments | obrigatórios em chamadas Swift | preservados via `@DefaultArgumentInterop.Enabled` |

---

## Convenções deste projeto (decididas pela fixture)

1. **Sem wrappers manuais de async no Swift.** Nunca envolver `suspend
   fun` exposta via SKIE em `withCheckedContinuation` ou em closures
   manuais. SKIE já gera `async throws`.
2. **Flow exposta para iOS sempre via `stateIn(WhileSubscribed(5_000))`.**
   Garante observação reativa sem leaks; SKIE converte em
   `AsyncSequence` consumido em `.task {}`.
3. **`@DefaultArgumentInterop.Enabled`** habilitado para módulos do
   shared cujos APIs públicos usam default arguments. Sem isso, Swift
   exige todos os parâmetros.
4. **Sem tipos platform-specific em `commonMain`.** SKIE não pode
   re-mapear tipos Android (`Context`, `Uri`); permaneçam em
   `expect/actual`.
5. **Coleta de `Flow` em SwiftUI usa `.task { for await … in flow }`** —
   `.task` cancela automaticamente quando a View sai do scope, evitando
   leaks de coroutine.

---

## O que este card contribui

### 1. `tech-spec-agent` → `section:iOS UI layer`

Arquivo: `agent-contributions/tech-spec-additions.md`.

Injeta as regras canônicas de bridge SKIE na seção iOS do `tech-spec.md`.
Cobre: padrão de exposição de `suspend`, padrão de exposição de `Flow`
com `SharingStarted.WhileSubscribed(5_000)`, default arguments via
anotação, proibição de wrappers manuais e padrão de consumo em SwiftUI
(`.task {}` + `for await`).

### 2. `task-contract-writer` → `after:Allowed Files`

Arquivo: `agent-contributions/task-writer-additions.md`.

Orienta o writer sobre allowed-files Swift no iOS (`iosApp/**/*.swift`),
comandos de validação canônicos (`./scripts/run-ios-simulator.sh` para
smoke test, `./gradlew :shared:linkPodReleaseFrameworkIosArm64` para
verificar geração do framework) e o script de bridge
(`iosApp/scripts/build-shared-framework.sh`).

### 3. Template fragment → `tech-spec.md` § iOS UI layer

Arquivo: `templates/skie-tech-spec-section.md`.

Bloco curto inserido por `append-section` que declara o uso do SKIE,
o version pin e as 5 convenções listadas acima. Documenta o trade-off
de cada decisão.

### 4. Validator → `validators/check-no-manual-async-wrappers.py`

Stub Phase 5. Quando implementado, varrerá arquivos `.swift` em busca
de `withCheckedContinuation` envolvendo chamadas a APIs do framework
compartilhado (heurística por import + nome do framework). Severity
`warn` — bridge automático é convenção, não bloqueio.

---

## O que este card NÃO contribui

Deliberadamente fora do escopo:

- **Templates Swift de UI** — ficam em `swiftui-screens` (não criado
  ainda).
- **Configuração do build do framework iOS** — fica no script
  `iosApp/scripts/build-shared-framework.sh` da fixture, não no card.
  Card só documenta o contrato.
- **Versionamento do SKIE** — gerenciado via `gradle/libs.versions.toml`
  do projeto, não pelo card.
- **Validators bloqueantes** — apenas `warn`. Bridge automático é
  preferência idiomática, não regra crítica.

---

## Referência viva (MeoBonsai)

Este card foi destilado a partir do projeto-fixture
`~/Documents/MeoBonsai/`. Para ver SKIE em uso real:

- Regra canônica iOS: `.claude/rules/architecture_ios.md` § SKIE
- Regra canônica KMP: `.claude/rules/architecture_kmp.md` § SKIE
- Plugin: `shared/build.gradle.kts` (`alias(libs.plugins.skie)`)
- Pin de versão: `gradle/libs.versions.toml` (`skie = "0.10.11"`)
- Build pipeline iOS: `iosApp/scripts/build-shared-framework.sh`

Exemplos curtos extraídos da fixture:

```kotlin
// ✅ shared/commonMain — suspend exposta sem wrapper
suspend fun fetchBonsai(id: String): Bonsai = withContext(io) {
    bonsaiService.get(id)
}

// ✅ shared/commonMain — Flow exposta com SharingStarted estável
val uiState: StateFlow<StateUI<BonsaiUI>> =
    _uiState.stateIn(
        scope,
        SharingStarted.WhileSubscribed(5_000),
        StateUI.Idle,
    )
```

```swift
// ✅ iOS — consome suspend como async throws (SKIE-gerado)
let bonsai = try await viewModel.fetchBonsai(id: id)

// ✅ iOS — consome Flow como AsyncSequence em .task
.task {
    for await state in viewModel.uiState {
        self.state = state
    }
}

// ❌ wrapper manual desnecessário (SKIE já fez o trabalho)
// withCheckedContinuation { cont in
//   viewModel.fetchBonsai(id: id) { result, err in ... }
// }
```

---

## Lifecycle

- **Install** (via `forge init` ou menu "adicionar card" no
  `forge reconfigure`): copia este diretório para
  `.claude/cards/skie-bridge/`, registra sha256 em `workflow-config.yaml`.
- **Update**: recopia do canonical, mostra diff, requer aceite.
- **Remove**: bloqueado se algum card downstream (ainda não criado)
  declarar `requires: skie` ou `requires: kotlin-swift-bridge`.

---

## Versionamento

`1.0.0` — primeira versão estável, alinhada com:

- `architecture_ios.md` § SKIE (mai/2026)
- `architecture_kmp.md` § SKIE (mai/2026)
- SKIE `0.10.11` na fixture MeoBonsai
