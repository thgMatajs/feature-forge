<!-- Injected into: task-contract-writer
     Extension point: after:Allowed Files
     Source card: kotlinx-serialization-json v1.0.0
-->

## JSON serialization file patterns (card `kotlinx-serialization-json`)

Quando uma TASK toca DTOs/Request/Response ou configura `Json {}`, use os
padrões canônicos abaixo para `allowed_files` e `validations`. Não invente
caminhos: derive de `inventory.conventions.folder-layout` + os padrões
abaixo.

### `allowed_files` — globs canônicos

DTOs e código de serialização vivem em `data/` do shared layer:

- DTOs (entrada): `shared/**/src/commonMain/kotlin/**/*Response.kt`
- DTOs (saída):   `shared/**/src/commonMain/kotlin/**/*Request.kt`
- DTOs neutros:   `shared/**/src/commonMain/kotlin/**/*Dto.kt`
- Serializers custom: `shared/**/src/commonMain/kotlin/**/serialization/*.kt`
- Mappers DTO ↔ Domain: `shared/**/src/commonMain/kotlin/**/mapper/*Mapper*.kt`
- Config `Json {}`: `shared/**/src/commonMain/kotlin/**/di/*Module.kt` (ou
  factory equivalente no card de DI ativo)

**Sempre excluir** das `allowed_files`:

- `**/build/**` (artefatos gerados pelo compiler plugin de serialization)
- `**/generated/**` (Koin Annotations, Room, etc.)
- DTOs em `androidMain/` ou `iosMain/` — DTOs canônicos moram em
  `commonMain/`; aparição em sourceSet específico exige justificativa
  no tech-spec.

### `validations` — comandos canônicos

Cada TASK que cria/modifica DTO declara:

```yaml
validations:
  - name: detekt
    command: "./gradlew detekt"
    on-failure: block
  - name: ktlint
    command: "./gradlew ktlintCheck"
    on-failure: block
  - name: compile-shared
    command: "./gradlew :shared:<module>:compileKotlinMetadata"
    on-failure: block
```

TASK que muda contrato de DTO (campo novo, rename, tipo) ou serializer
custom adiciona:

```yaml
  - name: serialization-roundtrip-test
    command: "./gradlew :shared:<module>:testAndroidHostTest --tests '*SerializationTest'"
    on-failure: block
```

> Roundtrip mínimo: `Json.encodeToString(dto) → Json.decodeFromString<T>()`
> retorna instância equivalente. Cobrir também tolerância a campo
> desconhecido (`ignoreUnknownKeys=true`) quando aplicável.

### `gates`

- TASK criando/alterando DTO → gate `lint-and-format` (detekt + ktlint).
- TASK alterando contrato de rede (campo novo/removido em
  `*Response.kt`/`*Request.kt`) → gate `serialization-roundtrip-test`.
- TASK criando serializer custom (`serialization/{Type}Serializer.kt`) →
  gate `serialization-roundtrip-test` + KDoc obrigatório explicando o
  desvio do default.

### Anti-patterns a sinalizar no `task-breakdown.yaml`

- TASK adicionando dependency `gson`/`moshi`/`jackson` ao `commonMain` →
  erro de spec (viola contrato KMP do card).
- TASK criando `Json {}` ad-hoc dentro de Repository/UseCase em vez de
  consumir a instância injetada → erro de spec.
- TASK com DTO em `domain/` ou `presentation/` → erro de spec
  (DTO vive em `data/`).
- TASK que muda `Json { ignoreUnknownKeys }` para `false` sem
  justificativa no tech-spec → bloquear.
- TASK que adiciona `@Serializable` em UI model (`*UI.kt`) → erro de
  spec (UI não atravessa rede).
