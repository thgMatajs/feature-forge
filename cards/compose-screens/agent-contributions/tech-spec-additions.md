<!--
  Contribuição do card `compose-screens` injetada em:
    agent: tech-spec-agent
    extension-point: section:Android UI layer
-->

## Card-specific: Compose UI strategy (Android)

Quando este card está ativo, a seção "Android UI layer" do tech-spec deve
cobrir explicitamente os pontos abaixo. Não improvisar nomes nem propor
estruturas paralelas: o agente herda diretamente as convenções deste
fragmento.

### 1. Layout de arquivos por tela (obrigatório no tech-spec)

Para cada `screen` listada no `screen-analysis.md`, o tech-spec deve gerar
uma sub-seção `#### Screen: {ScreenName}` contendo:

```
androidApp/feature/{feature}/ui/{screen}/
├── {Screen}Screen.kt        # stateful host (ViewModel + nav + side-effects)
├── {Screen}Content.kt       # stateless content (state + callbacks)
├── {Screen}Components.kt    # subcomponentes (criar quando 2+ subcompose)
└── {Screen}Mappers.kt       # domain→UI (criar quando 2+ funções de mapping)
```

Regra de criação:

- `Screen.kt` e `Content.kt` SEMPRE existem por tela. Não há exceção.
- `Components.kt` só nasce com 2+ subcomposables. Caso contrário, mantém-se
  no `Content.kt`.
- `Mappers.kt` só nasce com 2+ funções de mapeamento. Caso contrário, é
  função privada top-level no `Content.kt` ou `Screen.kt`.

### 2. Contrato de cada arquivo (descrever no tech-spec)

`{Screen}Screen.kt`:

- Injeta o ViewModel via `koinViewModel<{Screen}ViewModel>()` (quando card
  `koin-annotations` está ativo).
- `val state by viewModel.uiState.collectAsStateWithLifecycle()`.
- Trata navegação chamando lambdas recebidas do `NavGraph` (`onNavigateBack`,
  `onNavigateTo({route})`).
- `LaunchedEffect(state.navigationEvent)` para efeitos one-shot derivados de
  campos no `StateUI`. Sempre chama `viewModel.consumeNavigationEvent()`
  após disparar.
- Renderiza `{Screen}Content(state = state, onEvent = viewModel::onEvent, ...)`.

`{Screen}Content.kt`:

- Assinatura: `@Composable fun {Screen}Content(state: {Screen}UI, onEvent: ({Screen}UIEvents) -> Unit, modifier: Modifier = Modifier, ...)`.
- Estritamente stateless. Sem `viewModel`, sem `NavController`, sem `koinInject`.
- Pode ter `@Preview` no mesmo arquivo com state mockado.

`{Screen}Components.kt`:

- Composables internos da tela. Visibilidade `internal` ou `private`.
- Promoção para o design system NUNCA é decidida aqui — pertence ao card
  `design-system-components`.

`{Screen}Mappers.kt`:

- Funções puras `internal fun {Concept}.toUI(): {Concept}UI`.
- Rodam em `Dispatchers.Default` quando chamadas no ViewModel/UseCase — não
  em Composable.

### 3. State management (referência cruzada)

O state segue o contrato `StateUI<T>` (ver `architecture_kmp.md §StateUI`).
O Composable nunca declara sealed class própria de loading/error.

```kotlin
val state: StateFlow<StateUI<{Concept}UI>> =
    repository.observe()
        .map { StateUI.Processed(it.toUI()) as StateUI<{Concept}UI> }
        .onStart { emit(StateUI.Processing) }
        .catch { emit(StateUI.Error(...)) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), StateUI.Idle)
```

### 4. Side-effects

Hierarquia obrigatória (do mais barato ao mais caro):

1. Campo no `{Concept}UI` consumido por `LaunchedEffect` + `consume*`.
2. `Channel<{Concept}OneShot>(Channel.BUFFERED)` quando há race condition.
3. `Mutex.withLock` em ViewModel quando há concorrência sobre estado mutável.

Tech-spec deve indicar QUAL nível usar e justificar quando subir de nível.

### 5. Performance Compose

Documentar explicitamente no tech-spec quando alguma das condições abaixo
se aplica:

- Lista com mais de ~20 itens visíveis simultaneamente → `LazyColumn` com
  `key = { it.id }`. Anotar `contentType` quando há heterogeneidade.
- Computação cara durante recomposição (filtro, ordenação) → `derivedStateOf`.
- Mapper domain → UI executa em `Dispatchers.Default` antes de emitir no
  `StateFlow` (no UseCase ou ViewModel).
- Imagens remotas → `coil-compose` (`AsyncImage`). Não envolver em
  `withContext` extra.

### 6. Previews

Previews ficam no mesmo arquivo do componente que cobrem. Nomes em PascalCase:

```kotlin
@Preview(name = "Idle", showBackground = true)
@Composable
private fun PreviewBonsaiListContentIdle() { ... }

@Preview(name = "Loaded — light", uiMode = UI_MODE_NIGHT_NO)
@Preview(name = "Loaded — dark",  uiMode = UI_MODE_NIGHT_YES)
@Composable
private fun PreviewBonsaiListContentLoaded() { ... }
```

Tech-spec deve listar os previews mínimos por tela (idle, loading, success,
empty, error).

### 7. Observabilidade

Quando o card `observability-contracts` está ativo, todo `Modifier.testTag(...)`
e log de evento Analytics consome IDs/eventos do `shared:core/observability/`.
Tech-spec deve listar quais IDs cada Composable interativo aplica.

### 8. Dependências esperadas

```
androidx.compose.ui
androidx.compose.material3
androidx.compose.foundation
androidx.activity:activity-compose
androidx.lifecycle:lifecycle-viewmodel-compose
io.coil-kt.coil3:coil-compose          # quando há imagem remota
org.koin:koin-androidx-compose          # quando koin-annotations ativo
```

Tech-spec lista apenas as que a feature realmente usa.
