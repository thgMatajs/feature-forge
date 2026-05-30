# Card — `nav3`

> Jetpack Navigation 3 (NavDisplay) para Android com RouteEntry `@Factory` +
> `Render()` composables, `AppRoute` sealed interface em `shared:core` como
> `:NavKey`, `EntryProviderInstaller` multibinding por feature. DSL
> `navigation<T> { }` proibida.

| Campo | Valor |
|---|---|
| Categoria | `navigation` |
| Maturity | `beta` (Navigation 3 segue beta no ecossistema AndroidX) |
| Provides | `navigation-android`, `nav3` |
| Requires | `compose`, `android-platform` |
| Conflicts with | _(nenhum v1 — ver FOLLOWUP)_ |

## Por que este card existe

Navigation 3 substitui Navigation 2 com um modelo declarativo onde o back
stack é uma lista mutável de `NavKey` e o composable `NavDisplay` renderiza
o entry atual via `entryProvider { entry<AppRoute.X> { ... } }`. O ganho
arquitetural só se concretiza quando:

1. As rotas vivem em **um único lugar** (`shared:core/navigation/AppRoute.kt`)
   como sealed interface `@Serializable` — sem strings, sem duplicação por
   plataforma.
2. Cada feature **registra seus destinos via multibinding**
   (`EntryProviderInstaller`), permitindo adicionar uma feature nova sem
   tocar em `composeApp` nem em `:androidApp:navigation`.
3. ViewModels recebem um `Navigator` injetado em vez de importar APIs
   AndroidX direto — desacopla o feature de qualquer versão específica do
   Navigation.

Este card empacota essas três decisões como contribuições determinísticas
para os agents `tech-spec-agent`, `contract-planner-agent` e
`task-contract-writer`. O resultado é que toda feature gerada com o card
ativo nasce alinhada ao padrão Nav3 do projeto — sem improviso por turno.

## Estrutura física do card

```
cards/nav3/
├── card.yaml                                # manifest (schema-version: 1)
├── README.md                                # este arquivo
├── detection/
│   └── signals.yaml                         # espelho do bloco detection: de card.yaml
├── templates/
│   ├── nav3-tech-spec-section.md            # append em tech-spec.md
│   └── nav3-navigation-spec.yaml            # merge-keys em navigation-spec.yaml
├── validators/
│   └── check-no-nav-dsl.py                  # stub Phase 5 — exit 0 por enquanto
└── agent-contributions/
    ├── contract-planner-additions.md        # extension-point constraint:route-key-shape
    ├── tech-spec-additions.md               # extension-point section:Android UI layer
    └── task-writer-additions.md             # extension-point after:Allowed Files
```

## Detecção

Quatro sinais somam para um threshold cumulativo de `0.6`:

| Signal | Confidence |
|---|---|
| `**/*.kt` contains `NavDisplay` | 0.5 |
| `**/build.gradle*` contains `navigation3` | 0.4 |
| `**/*.kt` contains `NavKey` | 0.3 |
| `**/*.kt` contains `EntryProviderInstaller` | 0.2 |

Um único arquivo com `NavDisplay` + dependency `navigation3` no Gradle já
ultrapassa o threshold (0.9). Detalhes em `detection/signals.yaml`.

## Contribuições

### `tech-spec.md` (`append-section`)

Acrescenta a seção **"Navigation — Android (Nav3)"** dentro de §4 Android
UI layer. A seção pede tabela de rotas casando 1:1 com
`navigation-spec.yaml`, snippets canônicos de `RouteEntry` (`@Factory`),
`EntryProviderInstaller` (`@Single(binds = [EntryProviderInstaller::class])`)
e a tabela de mapeamento `back_behavior → Navigator method`.

### `navigation-spec.yaml` (`merge-keys`)

Injeta:

- `card_contributions.applied += "nav3:constraint:route-key-shape"`;
- bloco `nav3_route_key_shape` com 5 regras (`NAV3-RK-001..005`)
  consumidas pelo lint do navigation-spec — `route_key` precisa começar
  com `AppRoute.`, params devem ser `@Serializable`, `back_behavior` está
  limitado à taxonomy canônica.

### Agent prompts

| Agent | Extension-point | Conteúdo principal |
|---|---|---|
| `contract-planner-agent` | `constraint:route-key-shape` | Como mapear `routes`/`transitions`/`deep_links` em tipos `AppRoute` + tabela `back_behavior → Navigator`. |
| `tech-spec-agent` | `section:Android UI layer` | Estrutura :navigation, RouteEntry + EntryProviderInstaller, Navigator, DSL proibida, riscos para §13. |
| `task-contract-writer` | `after:Allowed Files` | `allowed_files` por categoria de task (route nova, feature nova, deep link), `forbidden_grep` para regressão Navigation 2, validations obrigatórias. |

### Validators

- `check-no-nav-dsl.py` — runs em `pre-commit` + `verify-task`, severity
  `error`. **Stub Phase 5**: contrato (exit codes, regex proibidas, escapes
  permitidos) está documentado no docstring; o executor real fica para a
  release Phase 5.

### Config defaults

```yaml
conventions.navigation.android: nav3
conventions.navigation.route-source-of-truth: "shared:core AppRoute sealed interface"
```

## Convenções endossadas

- `AppRoute` é `@Serializable sealed interface AppRoute : NavKey` em
  `shared:core` — fonte única consumida por Android (Nav3) e por iOS (SKIE
  espelha como `enum AppRoute`).
- Cada feature ship-a uma `{Feature}NavigationInstaller` com
  `@Single(binds = [EntryProviderInstaller::class])`; `AppNavDisplay`
  coleta `getAll<EntryProviderInstaller>()` e nada mais precisa mudar no
  host.
- `RouteEntry` é `@Factory` (não `@Single`) — `@Single` retém estado
  entre back-stack entries.
- `ViewModel` recebe `Navigator` (fun interface) no construtor; nunca
  importa APIs `androidx.navigation3.*` direto.
- DSL `module { ... navigation<T> { } }` é proibida em produção (válida só
  em `commonTest`).

## Anti-patterns que o card sinaliza como risco

- `NavHost` ou `composable("rota")` remanescente — Navigation 2 não foi
  totalmente removido.
- `route_key: "feature/{id}"` em `navigation-spec.yaml` — Nav3 não tem
  string routes; precisa virar `AppRoute.X(...)`.
- `data class BonsaiDetail(val bonsai: Bonsai)` como rota — domínio inteiro
  não é serializável e estoura o back stack; passar só o `id`.
- `@Single` em `RouteEntry` — vaza estado entre back-stack entries.
- `RouteEntry` que constrói `ViewModel` direto sem `koinViewModel { }` —
  perde o `ViewModelStoreOwner` por entry.

## FOLLOWUPs

- **Conflict label Navigation 2**: o catalog v1 não tem
  `navigation2-android` como capability. Quando o catalog for ampliado, o
  card declara `conflicts-with: [navigation2-android]`.
- **Validator real**: `check-no-nav-dsl.py` está como stub Phase 5. O
  executor real precisa implementar os regex listados no docstring +
  honrar `FORGE_CHANGED_FILES`.

## Referências vivas

- `.claude/rules/architecture_android.md` §Navegação (Navigation 3) — fonte
  canônica de DSL proibida, RouteEntry, AppRoute em `shared:core`.
- `shared/core/src/commonMain/kotlin/.../core/navigation/AppRoute.kt` —
  sealed interface real do projeto MeoBonsai.
- `androidApp/navigation/src/main/kotlin/.../EntryProviderInstaller.kt` —
  contrato multibinding consumido por `AppNavDisplay`.
- `androidApp/navigation/src/main/kotlin/.../AppNavDisplay.kt` — host único
  com `NavDisplay` e os dois `entryDecorators` canônicos.

## Categoria & maturity

`navigation` / `beta`. Promover para `stable` somente quando:

1. Navigation 3 sair de beta no AndroidX;
2. O validator `check-no-nav-dsl.py` for upgrade Phase 5;
3. O conflict label `navigation2-android` estiver no catalog.
