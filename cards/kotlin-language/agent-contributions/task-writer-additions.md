<!-- Injected into: task-contract-writer
     Extension point: after:Allowed Files
     Source card: kotlin-language v1.0.0
-->

## Kotlin file patterns (card `kotlin-language`)

Quando uma TASK toca código Kotlin, use estes padrões canônicos para
`allowed_files` e `validations`. Não invente caminhos: derive de
`inventory.conventions.folder-layout` + os padrões abaixo.

### `allowed_files` — globs canônicos

- Código de produção (commonMain): `shared/**/src/commonMain/kotlin/**/*.kt`
- Código Android: `**/src/{androidMain,main}/kotlin/**/*.kt`
- Código iOS shared: `shared/**/src/iosMain/kotlin/**/*.kt`
- Testes shared: `shared/**/src/commonTest/kotlin/**/*.kt`
- Testes Android: `**/src/{androidUnitTest,testDebug,test}/kotlin/**/*.kt`
- Gradle scripts: `**/build.gradle.kts`, `**/settings.gradle.kts`

**Sempre excluir** das `allowed_files`:

- `**/build/**` (artefatos gerados)
- `**/generated/**` (código gerado por Koin Annotations, Room, etc.)
- `**/*.kts` quando a task não toca configuração de build

### `validations` — comandos canônicos Kotlin

Cada TASK que mexe em `.kt` deve declarar pelo menos:

```yaml
validations:
  - name: detekt
    command: "./gradlew detekt"
    on-failure: block
  - name: ktlint
    command: "./gradlew ktlintCheck"
    on-failure: block
```

Para tasks que tocam **somente** shared:

```yaml
  - name: shared-test
    command: "./gradlew :shared:<module>:testAndroidHostTest"
    on-failure: block
```

> Use `testAndroidHostTest` (não `testDebugUnitTest`) para módulos KMP
> shared — o JVM target do KMP usa o source set `androidHostTest`. Confirme
> via `inventory.conventions.test-pattern.framework-shared: kotlin-test`
> (default deste card).

### `gates`

- Toda TASK Kotlin deve ter gate `lint-and-format` (detekt + ktlint).
- TASK que cria/modifica modelo de domínio → gate `shared-unit-test`.
- TASK em UseCase com `Flow<StateUI<T>>` → gate `state-transitions-test`
  (Idle → Processing → Processed/Error coberto via Turbine).

### Anti-patterns a sinalizar no `task-breakdown.yaml`

- TASK com `allowed_files` apontando para `**/build/**` → erro de spec.
- TASK que executa `kotlinc` direto em vez de gradle task → erro de spec.
- TASK que ignora `detekt`/`ktlint` → não atende a hard-gate do projeto.
