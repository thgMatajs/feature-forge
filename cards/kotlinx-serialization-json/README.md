# Card `kotlinx-serialization-json`

> Categoria: `kmp` · Maturidade: `stable` · Requires: `[kotlin]`

`kotlinx.serialization-json` é o serializador JSON canônico para qualquer
projeto KMP do catálogo `feature-forge`. Provê a capability singular
`serialization-json` (ver `docs/schemas/capability-labels.md §Network`) e
ancora as convenções de DTOs/Request/Response com `@Serializable`, da
configuração única de `Json {}` e da proibição de bibliotecas baseadas
em reflection no `commonMain`.

Este card é um leaf de framework — depende apenas de `kotlin` e habilita
cards downstream (ex.: `ktor-client`, `firestore-persistence`) que
consomem DTOs serializáveis.

---

## O que este card declara

| Item | Valor |
|---|---|
| `provides` | `serialization-json` |
| `requires` | `kotlin` |
| `conflicts-with` | `serialization-json` (singular — só um provedor por projeto) |
| `config-defaults` | `conventions.serialization.json: "kotlinx-serialization-json"`, `conventions.serialization.json-config: "ignoreUnknownKeys=true, encodeDefaults=false"` |
| Detecção (threshold 0.6) | `build.gradle*` contém `kotlinx-serialization-json` (0.5) + `kotlinx-serialization` (0.3) + `*.kt` contém `@Serializable` (0.3) + `kotlinx.serialization` (0.2) |

A capability `serialization-json` é singular (uma feature, um provedor),
por isso `conflicts-with` lista a própria capability — projetos não
podem ativar dois cards diferentes que ambos provejam `serialization-json`
(ex.: hipotético `moshi-kotlin` no futuro).

---

## Quando este card ativa

O `forge init` ativa automaticamente quando detecta:

1. `build.gradle*` referenciando explicitamente `kotlinx-serialization-json`
   (confidence 0.5) — sinal mais forte.
2. `build.gradle*` referenciando o plugin/lib `kotlinx-serialization` (0.3)
   — captura projetos que usam outros formatos do mesmo guarda-chuva
   (cbor, protobuf) com forte chance de também usar JSON.
3. Qualquer arquivo `.kt` com `@Serializable` (0.3) ou com import
   `kotlinx.serialization` (0.2).

Em projetos KMP reais a soma cruza o threshold de 0.6 facilmente — basta
a dependência declarada no Gradle e qualquer DTO com `@Serializable`.

---

## O que este card contribui (agent-prompts)

### 1. `tech-spec-agent` → `section:Shared (KMP) layer`

Arquivo: `agent-contributions/tech-spec-additions.md`.

Injeta na seção do shared layer do `tech-spec.md` as regras de
serialização JSON canônica:

- Anotação obrigatória `@Serializable` em DTOs/Request/Response.
- Localização (DTOs em `data/.../dto/`, nunca em `domain/`).
- Naming (`{Entity}Response`, `{Entity}Request`, `{Entity}Dto`).
- Configuração canônica do `Json {}` (`ignoreUnknownKeys=true`,
  `encodeDefaults=false`, `explicitNulls=false`, `isLenient=false`).
- Serializers custom em `data/.../serialization/` quando o backend
  desvia do modelo natural (timestamp, enum string-coded).
- Polimorfismo via `@SerialName` + `SerializersModule`.
- Mapping DTO ↔ Domain (`{Entity}Mapper` em `data/.../mapper/`).
- Anti-patterns (`gson`/`moshi`/`jackson` no commonMain, `JsonElement`
  vazando para domain, múltiplas instâncias `Json {}` por feature).

### 2. `task-contract-writer` → `after:Allowed Files`

Arquivo: `agent-contributions/task-writer-additions.md`.

Orienta o writer sobre:

- Globs canônicos de `allowed_files` para DTOs
  (`**/*Response.kt`, `**/*Request.kt`, `**/*Dto.kt`,
  `**/serialization/*.kt`, `**/mapper/*Mapper*.kt`).
- Exclusões obrigatórias (`**/build/**`, `**/generated/**`,
  DTO fora de `commonMain`).
- Validações canônicas (`detekt`, `ktlintCheck`,
  `compileKotlinMetadata`, roundtrip test quando contrato muda).
- Gates por tipo de mudança (criação de DTO → lint-and-format;
  mudança de contrato → serialization-roundtrip-test).
- Anti-patterns para sinalizar no `task-breakdown.yaml`
  (`gson`/`moshi`/`jackson` no commonMain, `Json {}` ad-hoc fora
  do módulo de DI, `@Serializable` em UI model).

---

## O que este card NÃO contribui

Deliberadamente fora do escopo:

- **Validators executáveis** — script que grep por `@Serializable` em
  modelo errado fica em card de quality-gate dedicado (futuro).
- **Templates** — formato de DTO é Kotlin idiomático coberto por
  `kotlin-language`; este card só prescreve naming e anotação.
- **Hooks** — sem automação pós-edit.
- **Cliente HTTP** — fica em `ktor-client` (declara
  `requires: [serialization-json]`).
- **Persistência local** — fica em `room-database` ou
  `datastore-prefs`.
- **Config de Json {} no DI** — fica em `koin-annotations` (consome
  a config-default deste card).

---

## Referência viva (MeoBonsai)

Este card foi destilado a partir do projeto-fixture
`~/Documents/MeoBonsai/`. Exemplos canônicos em código real:

- DTOs: `shared/feature/*/data/**/*Response.kt`
- Gradle: `shared/build.gradle*` aplicando o plugin
  `org.jetbrains.kotlin.plugin.serialization`.
- Regras compiladas: `.claude/rules/architecture_kmp.md §Nomenclatura`
  (`{Entity}Response`, `{Entity}Request`) e
  `.claude/rules/architecture_kmp.md §Anti-patterns críticos`
  (proibição de DTO/Response na UI).

Exemplos curtos:

```kotlin
@Serializable
data class BonsaiResponse(
    val id: String,
    val name: String,
    val plantedAt: String? = null,
)

@Serializable
data class BonsaiRequest(
    val name: String,
    val speciesId: String,
)

class BonsaiMapper {
    fun toDomain(response: BonsaiResponse): Bonsai = Bonsai(
        id = response.id,
        name = response.name,
        plantedAt = response.plantedAt?.toLocalDateOrNull(),
    )
}

val canonicalJson = Json {
    ignoreUnknownKeys = true
    encodeDefaults    = false
    explicitNulls     = false
}
```

---

## Lifecycle

- **Install** (via `forge init` ou menu "adicionar card" no
  `forge reconfigure`): copia este diretório para
  `.claude/cards/kotlinx-serialization-json/`, registra sha256 em
  `workflow-config.yaml`.
- **Update**: recopia do canonical, mostra diff, requer aceite.
- **Remove**: bloqueado se algum card ativo ainda requer
  `serialization-json` (ex.: `ktor-client`, `firestore-persistence`).

---

## Versionamento

`1.0.0` — primeira versão estável, alinhada com
`architecture_kmp.md` §Nomenclatura/Anti-patterns da fixture MeoBonsai
(mai/2026) e com o catálogo `capability-labels.md` v1.
