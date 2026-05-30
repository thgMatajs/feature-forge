<!--
  Contribuição do card `compose-screens` para o `screen-analysis-agent`.

  NOTA IMPORTANTE (Phase 1 do feature-forge):
  O `screen-analysis-agent` AINDA NÃO declara extension-points no frontmatter.
  Esta contribuição está versionada aqui como documentação preparatória — não
  é injetada automaticamente pelo engine. Quando o agent declarar pontos
  (provável `after:Phase 2 — Vision-component matching` ou
  `section:Component UX Matrix`), este arquivo deve ser ligado via
  `card.yaml` em `contributes.agent-prompts`. Ver FOLLOWUP no README.
-->

## Card-specific: detecção de componentes Compose

Quando o card `compose-screens` está ativo, complementar a inferência visual
com pistas idiomáticas de Compose.

### Mapeamento visual → Composable canônico

| Padrão visual              | Composable Compose esperado                                  |
|----------------------------|--------------------------------------------------------------|
| Botão preenchido (CTA)     | `Button` / `MeoButton` (variante primary) — atom DS          |
| Botão outline / texto      | `OutlinedButton` / `TextButton` — ou `MeoLinkButton`         |
| Floating action            | `FloatingActionButton` — ou `MeoFab`                         |
| Campo de texto             | `TextField` / `OutlinedTextField` — ou `MeoTextField`        |
| Campo de senha             | `MeoPasswordField`                                           |
| Lista vertical com scroll  | `LazyColumn` (NUNCA `Column` + `verticalScroll` em listas)   |
| Lista horizontal           | `LazyRow`                                                    |
| Grid                       | `LazyVerticalGrid` com `GridCells.Fixed` ou `Adaptive`       |
| Card / superfície elevada  | `Card` / `Surface` — ou `MeoCard`                            |
| Sheet inferior             | `ModalBottomSheet` (Material 3)                              |
| Diálogo                    | `Dialog` / `AlertDialog`                                     |
| Top bar                    | `TopAppBar` — ou `MeoTopBar`                                 |
| Bottom navigation          | `NavigationBar` — ou `MeoBottomBar`                          |
| Snackbar                   | `SnackbarHost` — ou `MeoSnackbar`                            |
| Imagem remota              | `AsyncImage` (Coil 3) — nunca `Image(painter = rememberX)`   |

### Inferência de hierarquia para Component UX Matrix

Ao listar componentes de uma tela Compose:

1. **Slot do host**: identificar se a tela é hospedada por `Scaffold` (com
   `topBar`, `bottomBar`, `floatingActionButton`, `snackbarHost`). Cada slot
   ocupado vira uma linha na Component UX Matrix.
2. **Conteúdo central**: classificar como `LazyColumn` / `LazyRow` / `Column`
   estático / `Box` (overlay). Para listas lazy, anotar se há `stickyHeader`,
   `item`, `items(key = ...)`.
3. **Estado de cada item da lista**: enumerar estados visuais (idle, hover
   desktop não se aplica, pressed, selected, disabled, loading-shimmer,
   empty-row, error-row). Sem hover. Ripple é default — só anote ausência.
4. **Componentes interativos profundos**: para cada `Button`, `Card`
   clicável, `IconButton`, listar evento mapeado para `UiEvents.*` no
   ViewModel.

### Estados obrigatórios para detectar (Phase 3 — State enumeration)

Mesmo quando o screenshot mostra apenas o happy path, perguntar ao usuário:

- `idle` / inicial — antes de qualquer ação.
- `loading` — qual indicador? (`CircularProgressIndicator`, skeleton, shimmer)
  Spinner de tela cheia vs inline vs por-item.
- `empty` — quando lista vier vazia. Há ilustração? CTA?
- `error` — banner topo? `MeoFeedbackState` com tone error? Snackbar?
- `processing-in-line` — quando ação dispara mas tela não troca (ex.: salvar
  inline). Botão fica disabled? Mostra spinner dentro do botão?
- `success-toast` — confirma e some? Naviga pra outra tela?

Tudo que não puder ser inferido vai como `needs-elicitation` com
`phase_lock: TASK-{slug}-ui`.

### Sinais de anti-pattern para sinalizar no relatório

- Composable com mais de 30 linhas no body → sugerir extração para
  `{Screen}Components.kt`.
- Composable que recebe `ViewModel` ou `NavController` como parâmetro →
  violação de stateless content; mover para `Screen.kt`.
- `@Composable` em pacote `shared/` → marcar como contract violation
  (UI Compose não pode viver no commonMain).
