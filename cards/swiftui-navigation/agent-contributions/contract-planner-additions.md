<!--
  Injetado em: contract-planner-agent
  Extension-point: section:Navigation
  Card: swiftui-navigation
-->

## swiftui-navigation — orientações para `navigation-spec.yaml` (iOS)

Use estas regras quando esta feature for consumida pelo target iOS. iOS roda
`NavigationStack` SwiftUI — **não há Navigation 3 no iOS**. O contrato
`navigation-spec.yaml` é único e cross-platform, mas precisa carregar metadados
suficientes para que o `tech-spec-agent` derive o enum Swift correto.

### Forma das chaves de rota no spec

- A fonte canônica continua sendo o `AppRoute` shared (sealed interface Kotlin
  serializável). O navigation-spec referencia o nome canônico do route key
  (ex.: `AppRoute.Register`, `AppRoute.BonsaiForm`).
- Para cada route documente:
  - `args:` (lista de parâmetros com tipo Swift mapeado — `String?`, `Int`,
    `Double`, ou `String` para enums codificados como string).
  - `ios-case:` (nome do case Swift correspondente — geralmente camelCase do
    último segmento, ex.: `bonsaiForm`).

### Edges de navegação

Cada edge (from → to) precisa indicar a **operação iOS** equivalente:

| Intenção | Operação iOS canônica |
|---|---|
| Empilhar destino | `path.append(.X)` |
| Substituir topo (sem voltar para anterior) | `replaceTop(with: .X)` |
| Reset stack para destino único | `replaceAll(with: .X)` |
| Voltar 1 nível | `pop()` |
| Voltar para a raiz | `popToRoot()` |

Use `nav-op` como chave dentro de cada edge. O `tech-spec-agent` lê isso para
gerar as closures `onNavigateToX` corretas.

### Argumentos opcionais

Argumentos opcionais em rotas iOS são `Optional` Swift puro (`String?`).
Nunca documentar como `KotlinString?` ou tipo da framework Shared — o enum
Swift não importa `Shared` para parâmetros.

### Deep links

Se a feature tem deep link entry-points, liste-os em
`deep-links:` no navigation-spec. Cada entry indica:

- `url-pattern:` (padrão do scheme/host/path).
- `target-route:` (qual route key da feature).
- `ios-handler:` deve ser `.onOpenURL` no root NavigationStack (não em
  screens internas).

### Cases-only-iOS

Quando o iOS precisa de um destino que não existe no Android (ex.:
preview modal iOS-only), documente em `ios-only-routes:` com justificativa.
O Android ignora esse bloco; o tech-spec iOS o consumirá.

### Anti-patterns a sinalizar em `open-questions.md`

- Spec que assume Navigation 3 no iOS → bloquear, abrir questão.
- Argumento de rota tipado como `Shared.*` no navigation-spec → exigir
  tipo Swift puro.
- Edge sem `nav-op` → abrir questão (não inventar a operação).
