<!--
  Fragment contribuído ao tech-spec.md pelo card nav3.
  Merge mode: append-section (vira §4.x dentro de "Android UI layer").
  Substitua {{placeholders}} ao gerar a tech-spec do feature.
-->

## Navigation — Android (Nav3)

Esta seção é mandatória quando o card `nav3` está ativo. Cada subitem
casa diretamente com uma `route`, `transition` ou `deep_link` de
`navigation-spec.yaml` — nada é inferido aqui.

### Rotas criadas / editadas neste feature

| `route_key` | Shape (`data object` ou `data class`) | Parent | Conditional gate |
|---|---|---|---|
| `AppRoute.{{ConceptRoute1}}` | `{{data object | data class(...)}}` | `{{parent_route_key_or_null}}` | `{{auth-required | feature-flag | none}}` |

> Referência cruzada: `navigation-spec.yaml §routes[]`. Toda linha precisa
> ter o `id` correspondente em `routes[].id`.

### RouteEntry — uma classe por destino

```kotlin
@Factory
class {{ConceptRoute1}}RouteEntry(
    private val viewModelFactory: {{Concept}}ViewModelFactory,
) {
    @Composable
    fun Render(route: AppRoute.{{ConceptRoute1}}) {
        val vm = koinViewModel<{{Concept}}ViewModel> { parametersOf({{route.params}}) }
        {{Concept}}Screen(viewModel = vm)
    }
}
```

- `@Factory` mandatório — `@Single` aqui retém estado entre back-stack
  entries (anti-pattern).
- `Render()` é o único método público.

### EntryProviderInstaller — uma por feature

```kotlin
@Single(binds = [EntryProviderInstaller::class])
class {{Feature}}NavigationInstaller(
    {{constructor-injected-route-entries}}
) : EntryProviderInstaller {
    override fun EntryProviderScope<AppRoute>.invoke() {
        entry<AppRoute.{{ConceptRoute1}}> { route -> {{routeEntry1}}.Render(route) }
        entry<AppRoute.{{ConceptRoute2}}> { {{routeEntry2}}.Render() }
    }
}
```

### Transitions (back behavior canônico)

| `T-id` | Source → Target | Trigger | back_behavior | `Navigator` call |
|---|---|---|---|---|
| `T-{{NNN}}` | `{{src}} → {{dst}}` | `{{kind}}: {{i18n_key}}` | `{{pop | replace | clear-stack | dismiss-dialog | dismiss-sheet | noop}}` | `{{navigator.goTo / goBack / replaceTop / resetTo}}` |

### Deep links neste feature

| `pattern` | `target_screen` | Auth required | Fallback transition |
|---|---|---|---|
| `{{pattern_or_none}}` | `{{screen_id}}` | `{{true|false}}` | `{{T-id_or_none}}` |

> Vazio quando `navigation-spec.deep_links[]` é vazio.

### Restrições impostas pelo card

- `AppRoute` vive em `shared:core/navigation/AppRoute.kt`, **não** em
  `:androidApp:navigation`.
- `composeApp/**` não pode aparecer no diff desta task — adicionar rota é
  responsabilidade de `androidApp:feature:*`.
- `module { ... navigation<T> { } }` DSL é proibida — validator
  `check-no-nav-dsl.py` falha o build.
- Tipos não-`@Serializable` em params da `data class` da rota = runtime
  crash; validar com `./gradlew compileDebugKotlin` na task.
