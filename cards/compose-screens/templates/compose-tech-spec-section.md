## UI — Android (Compose)

> Fragmento contribuído pelo card `compose-screens`. Inserido como
> append-section na seção "Android UI layer" do tech-spec.md.

### Organização de arquivos (obrigatória)

Toda tela Compose deve ser quebrada em arquivos com responsabilidades claras
e nomes determinísticos. O agente de planejamento deve descrever cada arquivo
explicitamente no tech-spec, mesmo quando opcional.

```
androidApp/feature/{feature}/ui/{screen}/
├── {Screen}Screen.kt        # stateful host: ViewModel, side-effects, navigation
├── {Screen}Content.kt       # stateless content: recebe state + callbacks
├── {Screen}Components.kt    # subcomponentes e helpers internos da tela
└── {Screen}Mappers.kt       # domínio→UI (opcional — criar quando 2+ mappers)
```

- `{Screen}Screen.kt` é o único arquivo que conhece o `ViewModel`, coleta
  `StateFlow`, dispara `LaunchedEffect`, faz navegação e injeção via Koin
  (`koinViewModel()`).
- `{Screen}Content.kt` é puramente stateless. Recebe `state: {Concept}UI` e
  callbacks (`onEvent`, `onClickX`). Não conhece `ViewModel`, `NavController`
  ou Koin.
- `{Screen}Components.kt` agrupa subcomposables privados da tela. Promoção
  para o design system só acontece via card `design-system-components`.
- `{Screen}Mappers.kt` só é criado quando o tech-spec lista 2+ funções
  de mapeamento (domain→UI ou error→UI). Caso contrário, mapper inline.

### Previews

- Toda `@Composable` exposta no `Content.kt` ou `Components.kt` deve ter pelo
  menos um `@Preview` (dark/light quando aplicável) no **mesmo arquivo**.
- Funções `@Preview` usam `PascalCase` (alinhado com detekt do projeto).
- Nunca criar arquivo dedicado só para previews — quebra co-localização.

### Estado e side-effects

- O `ViewModel` mantém `MutableStateFlow<StateUI<{Concept}UI>>` exposto como
  `StateFlow` via `stateIn(SharingStarted.WhileSubscribed(5_000))`.
- Efeitos one-shot (toast, navegar, abrir diálogo) ficam como campos no
  `{Concept}UI` consumidos por `LaunchedEffect(key)` que chama uma fun
  `consume*` do ViewModel após disparar o efeito.
- `Channel<T>(Channel.BUFFERED)` só é usado quando há race condition entre
  emissor e consumidor (raro). Tech-spec deve justificar.

### Performance Compose (regras anti-jank)

- Listas grandes → `LazyColumn` / `LazyVerticalGrid` com `key = { it.id }`
  estável. Sem `key`, recomposição perde identidade.
- Computações reativas caras durante recomposição → `derivedStateOf`.
- Mapper de domain → UI executa em `Dispatchers.Default` (no ViewModel/UseCase)
  antes de emitir no `StateFlow`. Composable nunca faz parse, sort ou regex.
- `LaunchedEffect` nunca contém lógica de negócio — só dispara funções do
  ViewModel. Sem `runBlocking`, sem chamadas Ktor/Firebase diretas.
- Coil 3 para imagens; decode roda fora da Main por padrão — não envolver em
  `withContext` extra. Sem `BitmapFactory` síncrono em Composable.

### Acessibilidade e test IDs

- `Modifier.testTag(...)` para todo elemento interativo. Os IDs vêm de
  `shared:core/observability/{Feature}TestIds.kt` — nunca string literal
  hardcoded no Composable (ver card `observability-contracts`, se ativo).
- `Modifier.semantics { contentDescription = ... }` em ícones puros.
- Textos vêm de `stringResource(...)` gerados pelo script i18n — nunca
  literal no Composable.

### Proibições absolutas

- `@Suppress(...)`, `@file:Suppress(...)` — bloqueado pelo validator
  `validate-compose-no-suppress`. Corrigir a violação na raiz (mover lógica
  para `Components.kt` ou `Mappers.kt` se for `LongMethod`/`LongParameterList`).
- `NavHost` / `composable(...)` da Navigation 2 — usar Navigation 3
  (`NavDisplay`) via card `navigation-3-android`.
- `Context` capturado em `remember` ou ViewModel — usar `LocalContext.current`
  apenas em Composable e injetar abstrações no ViewModel.
- UI Composable em `shared/` — fica em `androidApp/feature/{name}/ui/`.

### Dependências esperadas no `tech-spec.md §Dependencies`

- `androidx.compose.ui`, `androidx.compose.material3`, `androidx.compose.foundation`
- `androidx.activity:activity-compose`
- `androidx.lifecycle:lifecycle-viewmodel-compose`
- `io.coil-kt.coil3:coil-compose` (quando há imagem remota)
- `org.koin:koin-androidx-compose` (quando card `koin-annotations` está ativo)
