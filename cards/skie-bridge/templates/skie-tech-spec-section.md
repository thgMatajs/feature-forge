<!--
Fragment contribuído pelo card `skie-bridge` para tech-spec.md.
Merge: append-section em "iOS UI layer".
-->

### Kotlin↔Swift Bridge (SKIE)

Este projeto usa SKIE (`co.touchlab.skie`) para reescrever a header
gerada pelo compilador Kotlin/Native em Swift idiomático. Toda decisão
de API exposta para o iOS deve respeitar as convenções abaixo.

**Plugin & versão**

- Plugin: `co.touchlab.skie` aplicado em `shared/build.gradle.kts` via
  `alias(libs.plugins.skie)`.
- Versão pinada em `gradle/libs.versions.toml` — não alterar sem PR
  dedicado.

**Convenções obrigatórias**

| Item | Padrão | Anti-padrão |
|---|---|---|
| `suspend fun` exposta ao iOS | declarar `suspend fun` normal — SKIE gera `async throws` | escrever wrapper manual com `withCheckedContinuation` no Swift |
| `Flow<T>` exposta ao iOS | `stateIn(scope, SharingStarted.WhileSubscribed(5_000), initial)` + consumir em Swift com `.task { for await … in flow }` | expor `Flow` raw e coletar em closure manual; usar `WhileSubscribed(0)` (race em recomposição) |
| `sealed interface/class` exposta ao iOS | declarar normalmente — SKIE gera `enum Swift` com `switch` exaustivo | criar tipo Swift paralelo manualmente |
| Default arguments em APIs públicas | habilitar `@DefaultArgumentInterop.Enabled` no módulo | obrigar Swift a passar todos os parâmetros |
| Tipos platform-specific | manter em `expect/actual` (Android `Context`, `Uri`) | tentar expor `Context` no commonMain (SKIE não re-mapeia) |

**Padrão de consumo em SwiftUI**

```swift
.task {
    for await state in viewModel.uiState {
        self.state = state
    }
}
```

`.task {}` cancela automaticamente ao sair do scope da View — não usar
`Task { … }` solto (vaza coroutine quando a View desaparece).

**Validação**

- Build do framework iOS: `iosApp/scripts/build-shared-framework.sh`
  (gera o xcframework consumido pelo Xcode).
- Smoke test: `./scripts/run-ios-simulator.sh` (compila + sobe app no
  simulador; falha se a bridge SKIE não gerar tipos corretos).
- Lint estático (card validator): `validators/check-no-manual-async-wrappers.py`
  flagga `withCheckedContinuation` envolvendo APIs do framework
  compartilhado (severity warn).
