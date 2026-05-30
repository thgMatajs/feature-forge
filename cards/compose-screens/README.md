# Card: `compose-screens`

Card canônico do feature-forge que ativa contribuições específicas para
**Jetpack Compose** quando o projeto usa Compose como camada de UI Android.
Modela o layout `{Screen}Screen.kt` + `{Screen}Content.kt` + `{Screen}Components.kt`
(+ opcional `{Screen}Mappers.kt`), proíbe `@Suppress` em código Compose, e
mantém previews co-localizados com seus componentes.

Inspirado em referência viva: `~/Documents/MeoBonsai/` (regras em
`.claude/rules/architecture_android.md` e `.claude/rules/design-system.md`).

## Identidade

| Campo         | Valor                                                              |
|---------------|--------------------------------------------------------------------|
| name          | `compose-screens`                                                  |
| version       | `1.0.0`                                                            |
| category      | `ui`                                                               |
| maturity      | `stable`                                                           |
| maintainer    | `feature-forge-core`                                               |
| rules-link    | `architecture_android`                                             |

## Capabilities

| Provê             | Requer                          | Conflita com       |
|-------------------|---------------------------------|--------------------|
| `android-ui`      | `kotlin`                        | — (ver FOLLOWUP)   |
| `compose`         | `android-platform`              |                    |

`conflicts-with` está vazio porque o catálogo v1 ainda não tem label para
"Android XML views". Quando o label `android-xml-views` (ou equivalente) for
adicionado, este card deve declarar conflito. Ver FOLLOWUP-1.

## Detecção

Threshold: **0.6**. Score máximo: 1.2.

| Sinal                                                          | Confidence |
|----------------------------------------------------------------|------------|
| `file-content` em `**/*.kt` contendo `androidx.compose`        | 0.5        |
| `file-content` em `**/build.gradle*` contendo `androidx.compose` | 0.4      |
| `file-content` em `**/*.kt` contendo `@Composable`             | 0.3        |

Projetos com import Compose + dependência Gradle já passam (0.9). Projetos
com apenas menção em comentário não passam — evita falso positivo.

## Contribuições

### Templates (2)

| Target              | Section                       | Merge mode       | Arquivo                                       |
|---------------------|-------------------------------|------------------|-----------------------------------------------|
| `tech-spec.md`      | `UI — Android (Compose)`      | `append-section` | `templates/compose-tech-spec-section.md`      |
| `task-contract.yaml`| `compose-file-patterns`       | `merge-keys`     | `templates/compose-allowed-files.yaml`        |

### Validators (2 stubs — Phase 5)

| Nome                              | Arquivo                                 | Runs-on                     | Severity |
|-----------------------------------|-----------------------------------------|-----------------------------|----------|
| `validate-compose-no-suppress`    | `validators/check-no-suppress.py`       | `pre-commit, verify-task`   | `error`  |
| `validate-compose-screen-layout`  | `validators/check-screen-layout.py`     | `pre-commit, verify-task`   | `error`  |

Ambos são stubs marcados com `# TODO Phase 5` — retornam exit 0 hoje e
não bloqueiam o pipeline até serem implementados.

### Agent prompts (2 ativos + 1 documental)

| Agent                  | Extension point             | Arquivo                                                | Estado            |
|------------------------|-----------------------------|--------------------------------------------------------|-------------------|
| `tech-spec-agent`      | `section:Android UI layer`  | `agent-contributions/tech-spec-additions.md`           | ativo             |
| `task-contract-writer` | `after:Allowed Files`       | `agent-contributions/task-writer-additions.md`         | ativo             |
| `screen-analysis-agent`| _(nenhum declarado ainda)_  | `agent-contributions/screen-analysis-additions.md`     | docs preparatório |

Ver FOLLOWUP-2 sobre o caso `screen-analysis-agent`.

### Config defaults

```yaml
conventions.folder-layout.android: "{Screen}Screen.kt + {Screen}Content.kt + {Screen}Components.kt + {Screen}Mappers.kt"
conventions.ui.compose.preview-location: "same-file-as-component"
```

## Estrutura física

```
cards/compose-screens/
├── card.yaml
├── README.md                                       (este arquivo)
├── detection/
│   └── signals.yaml
├── templates/
│   ├── compose-tech-spec-section.md
│   └── compose-allowed-files.yaml
├── validators/
│   ├── check-no-suppress.py                        (stub Phase 5)
│   └── check-screen-layout.py                      (stub Phase 5)
└── agent-contributions/
    ├── screen-analysis-additions.md                (docs preparatório)
    ├── tech-spec-additions.md
    └── task-writer-additions.md
```

## O que este card garante quando ativo

1. **Layout de tela determinístico**. Todo `{Screen}Screen.kt` vem acompanhado
   de `{Screen}Content.kt`. `Components.kt` e `Mappers.kt` só nascem com a
   regra de 2+ ocorrências.
2. **Stateless content boundary**. `{Screen}Content.kt` nunca conhece
   `ViewModel`, `NavController` ou `Koin` — só state + callbacks.
3. **Preview co-localizado**. Previews ficam no mesmo arquivo do componente
   que cobrem, com nomes em `PascalCase`.
4. **Sem supressões**. `@Suppress(...)` e `@file:Suppress(...)` bloqueados
   em qualquer arquivo Compose UI — bug é corrigido na raiz (extração).
5. **Performance baseline**. Mappers em `Dispatchers.Default`, listas com
   `LazyColumn + key`, computações reativas via `derivedStateOf`,
   `LaunchedEffect` sem lógica de negócio.
6. **State contract**. `StateUI<T>` do shared (KMP) é a única sealed class
   permitida para estado de tela — nunca custom loading/error sealed class.
7. **Allowed files coerente**. Tasks Compose têm `allowed_files` que
   refletem o layout, com `forbidden_files` para `**/*.xml`, `shared/**` e
   `iosApp/**`.

## O que este card NÃO faz

- Não gera código. Cards são manifestos declarativos.
- Não escolhe biblioteca de DI (delegado a `koin-annotations` ou similar).
- Não escolhe biblioteca de navegação (delegado a `navigation-3-android`).
- Não decide promoção de componente para o design system (delegado a
  `design-system-components`).
- Não toca iOS / Web / shared — escopo é estritamente Android Compose UI.

## Como rodar localmente (sanity, sem engine de merge)

```bash
# Validar YAML
python3 -c "import yaml,sys; yaml.safe_load(open('card.yaml')); print('ok')"

# Rodar validators stubs (devem ser exit 0)
python3 validators/check-no-suppress.py
python3 validators/check-screen-layout.py
```

## FOLLOWUPs

- **FOLLOWUP-1** — Adicionar `android-xml-views` (ou label equivalente) ao
  catálogo v1 e declará-lo em `conflicts-with` deste card. Hoje cabe ao
  resolver/usuário garantir que nenhum card concorrente de UI Android
  esteja ativo simultaneamente.
- **FOLLOWUP-2** — `screen-analysis-agent` ainda não declara
  `extension-points` no frontmatter. O fragmento
  `agent-contributions/screen-analysis-additions.md` está versionado como
  documento preparatório (não é injetado pelo engine). Quando o agent
  formalizar pontos como `after:Phase 2 — Vision-component matching` ou
  `section:Component UX Matrix`, atualizar `card.yaml` para incluir a
  contribuição.
- **FOLLOWUP-3** — Implementar `check-no-suppress.py` e `check-screen-layout.py`
  em Phase 5: argumentos de CLI, suporte a `--paths`, integração com hooks
  pre-commit do projeto, e relatório legível (file:line:trecho).
- **FOLLOWUP-4** — Quando o catálogo v1 ganhar label para Material 3 vs
  Material 2, considerar se este card especifica `material3` como capability
  requerida ou opcional.
- **FOLLOWUP-5** — Exemplos em `examples/` (atualmente ausente) podem ser
  adicionados depois com snippets reais do MeoBonsai para servir como
  fixture do resolver.
