<!--
  Injetado em: tech-spec-agent
  Extension-point: section:Android UI layer
  Card: nav3
-->

## nav3 — orientações para "Navigation — Android (Nav3)"

Use esta seção ao preencher §4 (Android UI layer) do `tech-spec.md` quando o
card `nav3` estiver ativo. Toda decisão precisa ser rastreável a uma
`route` ou `transition` de `navigation-spec.yaml` — não inventar destinos.

### Estrutura física do grafo

Navigation 3 distribui responsabilidades entre três tipos de módulo:

```
:composeApp                            # host único — não conhece feature alguma
  └── depends on :androidApp:navigation
:androidApp:navigation                 # contrato Nav3 + Navigator
  ├── AppRoute (re-export do shared:core)
  ├── Navigator (fun interface) + Nav3Navigator (impl Koin @Single)
  ├── EntryProviderInstaller (fun interface — multibinding)
  └── AppNavDisplay (NavDisplay composable host)
:androidApp:feature:{feature}          # uma installer + N RouteEntry
  └── {Feature}EntryProviderInstaller : EntryProviderInstaller
       ↳ register entry<AppRoute.X> { routeEntry.Render() }
shared:core                            # AppRoute sealed interface
  └── @Serializable sealed interface AppRoute : NavKey
```

Features **não dependem entre si**; `:composeApp` depende só de
`:androidApp:navigation`. Adicionar feature nova = um novo módulo
`androidApp:feature:*` + uma installer — sem tocar em `composeApp` nem em
`:navigation`.

### RouteEntry — uma classe por destino

Cada destino é uma classe injetada por Koin com `@Factory` que expõe um
único `@Composable fun Render()`:

```kotlin
@Factory
class BonsaiDetailRouteEntry(
    private val viewModelFactory: BonsaiDetailViewModelFactory,
) {
    @Composable
    fun Render(route: AppRoute.BonsaiDetail) {
        val vm = koinViewModel<BonsaiDetailViewModel> { parametersOf(route.bonsaiId) }
        BonsaiDetailScreen(viewModel = vm)
    }
}
```

- `@Factory` (não `@Single`) — nova instância por consumidor evita estado
  vazado entre back-stack entries.
- O parâmetro `route: AppRoute.X` é o ponto onde os params da `data class`
  chegam ao ViewModel (via `parametersOf` ou inject manual).
- O composable host (`{Screen}Screen`) é responsável por ViewModel,
  side-effects e navegação — mesma regra do `.claude/rules/architecture_android.md`.

### EntryProviderInstaller — uma por feature

```kotlin
@Single(binds = [EntryProviderInstaller::class])
class BonsaiNavigationInstaller(
    private val list: BonsaiListRouteEntry,
    private val detail: BonsaiDetailRouteEntry,
    private val form: BonsaiFormRouteEntry,
) : EntryProviderInstaller {
    override fun EntryProviderScope<AppRoute>.invoke() {
        entry<AppRoute.BonsaiList> { list.Render() }
        entry<AppRoute.BonsaiDetail> { route -> detail.Render(route) }
        entry<AppRoute.BonsaiForm>   { route -> form.Render(route)   }
    }
}
```

`AppNavDisplay` coleta `getAll<EntryProviderInstaller>()` do Koin e
executa todos os `invoke()` dentro de um único `entryProvider { }`. Nada
no host precisa enumerar destinos.

### `AppRoute` — fonte única em `shared:core`

```kotlin
@Serializable
sealed interface AppRoute : NavKey {
    @Serializable data object Welcome : AppRoute
    @Serializable data class BonsaiDetail(val bonsaiId: String) : AppRoute
    @Serializable data class BonsaiForm(val bonsaiId: String?) : AppRoute
}
```

- `: NavKey` é o supertipo do Nav3 que habilita uso como item de back stack.
- `@Serializable` em cada membro habilita state restoration + deep links.
- iOS espelha o mesmo arquivo via SKIE — toda mudança é cross-platform.

### `Navigator` (fun interface) + `Nav3Navigator` (impl)

```kotlin
fun interface Navigator {
    fun goTo(route: AppRoute)
    fun goBack(): Boolean
    fun replaceTop(route: AppRoute)
    fun resetTo(route: AppRoute)
    val backStack: SnapshotStateList<AppRoute>
}

@Single(binds = [Navigator::class])
class Nav3Navigator : Navigator { /* SnapshotStateList<AppRoute>() backing */ }
```

ViewModels recebem `Navigator` no construtor — nunca importam tipos Nav3
do AndroidX direto. Trocar de Navigation 3 para outro framework no futuro
mexe só em `:androidApp:navigation`.

### DSL proibida

```kotlin
// ❌ NUNCA — DSL `navigation<T> { }` do Koin scoped graph
module {
    activityRetainedScope {
        navigation<AppRoute.BonsaiList> { /* ... */ }
    }
}
```

Razões:

1. Embute conhecimento de rotas no DI graph — quebra o contrato "uma
   installer por feature".
2. Estabelece scope retido por activity que conflita com a vida útil dos
   `entryDecorators` (saveable state + ViewModelStore) do `NavDisplay`.
3. Não tem paridade no SKIE bridge (iOS) — fluxo dupla de verdade.

Substituir por `@Single(binds = [EntryProviderInstaller::class])` no
módulo de feature.

### Riscos a sinalizar em §13

- **Migração de Navigation 2 incompleta** — `NavHost`/`composable("...")`
  remanescente em algum módulo cria duplo grafo. Listar todos os módulos
  cobertos pelo PR.
- **Param não-serializável em `data class` de rota** — Nav3 falha em
  runtime ao serializar back stack. Tipos permitidos: primitivos + `String`
  + `String?` + outros `@Serializable`.
- **RouteEntry com state estático** — `@Factory` é mandatório; um
  `@Single` no RouteEntry retém ViewModel entre back-stack entries
  diferentes e vaza estado.
- **Deep link sem cobertura de auth gate** — toda `deep_links[]` cuja
  `target_screen` é gated precisa de fallback `redirect-to-login` listado
  em `navigation-spec.transitions[]`.

### Test plan referencer

Cada destino deve aparecer em pelo menos um cenário de
`navigation-spec.yaml` e em ao menos um BDD `@flow:navigation`. Sem
cobertura cruzada, marcar como `needs_elicitation` em vez de inventar.
