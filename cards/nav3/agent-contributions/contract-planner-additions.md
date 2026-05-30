<!--
  Injetado em: contract-planner-agent
  Extension-point: constraint:route-key-shape
  Card: nav3
-->

## nav3 — constraint para `navigation-spec.yaml`

Quando o card `nav3` está ativo, toda entry em `nav_graph.routes[]` precisa
seguir o shape canônico Navigation 3 abaixo. Validator cross-check
(`check-no-nav-dsl.py` + lint do navigation-spec) bloqueia merge se a
constraint for violada.

### 1. `route_key` é sempre um tipo Kotlin `@Serializable` membro de
`AppRoute` em `shared:core`

```yaml
routes:
  - id: "bonsai_detail"
    route_key: "AppRoute.BonsaiDetail"        # @Serializable data class : AppRoute
```

- `AppRoute` é declarado como
  `@Serializable sealed interface AppRoute : NavKey` em
  `shared/core/src/commonMain/kotlin/.../core/navigation/AppRoute.kt`.
- Membros sem parâmetros → `@Serializable data object` (ex.: `BonsaiList`,
  `Login`).
- Membros com parâmetros → `@Serializable data class` com tipos
  serializáveis (`String`, `Int`, `String?`); **nunca** receber objetos de
  domínio inteiros — somente IDs.
- iOS espelha o mesmo tipo via SKIE como Swift `enum AppRoute`, então o
  shape do `route_key` impacta as duas plataformas.

### 2. Deep links viram `data class` parametrizada — **não** template string

Em `nav_graph.deep_links[]`:

```yaml
deep_links:
  - pattern: "bonsai/{id}"
    target_screen: "bonsai_detail"
    params:
      id: "bonsaiId"
```

⇒ no código vira `AppRoute.BonsaiDetail(bonsaiId: String)` com o `id` da URL
mapeado para o parâmetro. Não usar `"bonsai/{id}"` como `route_key`
literal — Nav3 não tem string routes.

### 3. `params` em `routes[]` viram fields da `data class` na mesma ordem

```yaml
params:
  - name: "bonsaiId"
    type: "String"
    nullable: true        # null ⇒ create-mode, non-null ⇒ edit-mode
```

⇒ `data class BonsaiForm(val bonsaiId: String?) : AppRoute`. `nullable: true`
casa com `String?` no Kotlin. Documente o significado semântico em
`open_question` quando ambíguo (ex.: null vs missing key).

### 4. `back_behavior` da transition mapeia para método do `Navigator`

| `back_behavior` | Chamada Kotlin no Nav3 |
|---|---|
| `pop` | `navigator.goBack()` (default — pop um item do back stack) |
| `replace` | `navigator.replaceTop(route)` |
| `clear-stack` | `navigator.resetTo(route)` |
| `dismiss-dialog` | `navigator.goBack()` quando o entry decorator é dialog |
| `dismiss-sheet` | idem para bottom-sheet |
| `noop` | sem ação — sinaliza que o trigger é apenas analítico |

Se a `transition.back_behavior` não cabe nessa taxonomy, abrir
`Q-CP-{NN}` em `needs_elicitation` — não inventar entrada nova.

### 5. Marque o card como aplicado

Ao final do walk, popular `card_contributions.applied`:

```yaml
card_contributions:
  applied:
    - "nav3:constraint:route-key-shape"
  pending: []
```
