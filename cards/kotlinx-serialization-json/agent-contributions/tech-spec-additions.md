<!-- Injected into: tech-spec-agent
     Extension point: section:Shared (KMP) layer
     Source card: kotlinx-serialization-json v1.0.0
-->

## JSON serialization conventions (card `kotlinx-serialization-json`)

Todo modelo de transporte (DTO, Request, Response) no shared layer
(commonMain) usa `kotlinx.serialization` com `@Serializable`. Decisões
registradas no tech-spec devem refletir as regras abaixo — se o spec
prescreve algo que viola uma destas regras, sinalize como
**3-caminhos failure** em `open-questions.yaml` em vez de inventar.

### Regras canônicas

- **Anotação obrigatória**: toda classe de transporte (DTO/Request/Response)
  declarada no shared layer recebe `@Serializable` na própria classe e em
  toda subestrutura aninhada. Classes sem `@Serializable` não atravessam
  fronteira de rede/persistência.
- **Localização**: DTOs vivem em `data/.../dto/` (ou `data/.../model/`
  conforme o `inventory.conventions.folder-layout`). Nunca em `domain/`.
- **Naming**: `{Entity}Response` (entrada), `{Entity}Request` (saída),
  `{Entity}Dto` (formato bruto neutro). Domain models não carregam
  `@Serializable` — são tipos puros do `domain/`.
- **Config canônica de `Json {}`** — instância única injetada via DI:
  ```kotlin
  Json {
      ignoreUnknownKeys = true   // tolera campos extras do backend
      encodeDefaults    = false  // omite defaults na saída (payload menor)
      explicitNulls     = false  // omite nulls na saída
      isLenient         = false  // exige JSON estrito de entrada
  }
  ```
  Qualquer divergência (`encodeDefaults = true`, `isLenient = true`) deve
  ser justificada no tech-spec na seção do contrato de rede.
- **Serializers custom** apenas quando o backend não acompanha o modelo
  natural (ex.: timestamp ISO-8601 → `Instant`, enum string-coded com
  fallback). Declarar em `data/.../serialization/` com nome
  `{Type}Serializer.kt`. Documentar com `/** */` o porquê do desvio.
- **Polymorphism**: usar `@SerialName` em sealed hierarchies + módulo
  `SerializersModule` registrado na `Json {}` única. Nunca polimorfismo
  baseado em reflection.

### Mapping domain ↔ DTO

- DTOs nunca vazam para `presentation/` ou `domain/` — `Mapper` em
  `data/.../mapper/` traduz `Response → DomainModel` e
  `DomainModel → Request`.
- Defaults defensivos no mapper, não no DTO: `response.field ?: ""` ou
  fallback explícito no domain model. DTO mantém nullability fiel ao
  contrato de rede.
- Listas: mapear via `.map { it.toDomain() }`, nunca `as List<DomainX>`.

### Anti-patterns críticos (bloquear no tech-spec)

- `gson`/`moshi`/`jackson` no `commonMain` — incompatível com KMP. Restrito
  a `androidMain` em casos legados (justificar).
- `Json { isLenient = true }` global — esconde divergência de schema.
- `kotlinx.serialization.json.JsonElement` vazando para `domain/` —
  domain deve receber tipos tipados, não árvore JSON crua.
- DTOs com `var` mutável — sempre `val` + `data class`.
- `@Serializable` em UI model (`{Concept}UI`) — UI não atravessa rede.
- Reflection-based parsing (`Json.decodeFromString<T>(json)` com `T` vindo
  de generic erased em runtime) — usar `serializer<T>()` ou reified.
- Múltiplas instâncias `Json {}` diferentes por feature — uma única
  instância canônica injetada via DI.

### Quando registrar no tech-spec

Cada decisão de serialização que afeta a arquitetura aparece explícita na
seção "Shared (KMP) layer" do tech-spec:

- Lista de DTOs novos (`{Entity}Response`/`{Entity}Request`) e seu campo
  → tipo Kotlin → mapeamento para domain.
- Serializers custom (com link para o motivo — ex.: backend manda data
  como string `dd/MM/yyyy`).
- Configuração da `Json {}` se desviar da canônica.
- Estratégia de polimorfismo (`@SerialName` discriminator, módulo).
