<!--
Fragment injetado pelo card `skie-bridge` no `tech-spec-agent`.
Extension point: section:iOS UI layer
-->

### Card `skie-bridge` — bridge KMP↔iOS via SKIE

Ao redigir a seção **iOS UI layer** do `tech-spec.md`, considere o
plugin SKIE (`co.touchlab.skie`) como o mecanismo canônico de exposição
de APIs Kotlin para Swift. Documente explicitamente:

**1. APIs `suspend` expostas ao iOS**

Declare `suspend fun` normalmente em `commonMain`. SKIE gera Swift
`async throws` automaticamente. **NÃO** documente wrappers manuais
(`withCheckedContinuation`, callbacks, closures `(Result, Error) -> Void`)
no design — eles são proibidos.

Para cada API `suspend` exposta, registre na tabela de iOS:

| API Kotlin | Assinatura Swift (gerada por SKIE) |
|---|---|
| `suspend fun fetchX(id: String): X` | `func fetchX(id: String) async throws -> X` |

**2. `Flow<T>` expostos ao iOS**

Toda `Flow` consumida pelo SwiftUI deve ser publicada via
`stateIn(scope, SharingStarted.WhileSubscribed(5_000), initial)`.
Razão:

- `WhileSubscribed(5_000)`: 5s de delay evita restart no rotate / reentry.
- SKIE converte automaticamente em `AsyncSequence` consumível com
  `for await … in flow`.
- Consumo em SwiftUI **deve** ser dentro de `.task {}` para
  cancelamento automático ao sair de scope da View.

Anti-padrão: expor `Flow` sem `stateIn`, ou usar `Task { for await … }`
solto (vaza ao destruir a View).

**3. Default arguments**

Se o módulo expõe APIs públicas com default arguments, habilite
`@DefaultArgumentInterop.Enabled` no nível do módulo ou da função.
Sem essa anotação, o Swift exige todos os parâmetros, quebrando a
ergonomia do call site.

**4. Sealed classes/interfaces**

Declare `sealed interface` / `sealed class` normalmente. SKIE gera
`enum Swift` com `switch` exaustivo. **Não** documente tipo Swift
paralelo manual.

**5. Tipos platform-specific**

`commonMain` **nunca** expõe `Context`, `Uri`, ou qualquer tipo
Android-only. Esses ficam em `androidMain` via `expect/actual`. SKIE
não consegue re-mapear esses tipos para o iOS.

**Validação no design**

- Liste o script `iosApp/scripts/build-shared-framework.sh` como passo
  de build do framework iOS.
- Liste o validator `check-no-manual-async-wrappers.py` (warn) como
  guard contra regressão.
