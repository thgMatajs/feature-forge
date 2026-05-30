<!--
  Injetado em: contract-planner-agent
  Extension-point: section:Data Contract
  Card: kmp-shared
-->

## kmp-shared — orientações para `data-contract-spec.yaml`

O shared module exige separação estrita entre **DTO (wire format)** e
**Domain Model (puro)**. O contrato precisa refletir ambas as camadas e o
mapper que liga as duas. Não colapsar em uma única estrutura.

### Estruture cada entidade em três blocos

Para cada entity em `data-contract-spec.yaml`, descreva:

1. `dto`: shape exato como vem do provider (Firestore doc, JSON response).
   Campos opcionais com `nullable: true`. Anote `@Serializable` quando
   aplicável. Use `snake_case` ou nome do provider — não normalizar aqui.
2. `domain-model`: shape limpo consumido pelos UseCases. Campos sempre
   não-nulos quando possível; defaults aplicados no mapper. Nome puro
   (`Bonsai`, não `BonsaiResponse`).
3. `mapper`: regras explícitas de DTO → Domain. Cada campo do domain tem
   origem rastreável (`from: dto.field` ou `default: <valor>` ou
   `computed: <expressão>`).

### Null handling no mapper (obrigatório no contrato)

Para cada campo onde `dto.x` é nullable mas `domain.x` é não-nulo,
documente no contrato a regra de default. O cenário "Null/empty input"
do BDD (§5 testing rules) precisa ser executável a partir desta tabela
— sem isso, o teste fica indefinido.

Exemplo de bloco YAML esperado:

```yaml
entities:
  Bonsai:
    dto:
      fields:
        id: { type: string, nullable: false }
        species: { type: string, nullable: true }
        acquired_at: { type: timestamp, nullable: true }
    domain-model:
      fields:
        id: { type: String }
        species: { type: String }        # default "" se null
        acquiredAt: { type: LocalDate? } # mantém nullable
    mapper:
      rules:
        - { field: id,         from: dto.id }
        - { field: species,    from: dto.species, default: "" }
        - { field: acquiredAt, from: dto.acquired_at, transform: "Instant → LocalDate (TZ user)" }
```

### Tipos canônicos a usar no domain-model

- Datas/horas → `kotlinx.datetime.LocalDate`, `Instant`, `LocalDateTime`.
  Nunca `java.time.*`.
- IDs e enums externos → `String` no DTO, enum/value class no Domain.
- Coleções → `List<T>` imutável (não `MutableList`).
- Money/quantidades → value class dedicada quando o domínio diferencia
  unidades; senão `Double`/`Int` com unidade documentada no contrato.

### Sinalize no `notes` quando aplicável

- Campo do DTO sem regra de default documentada → bloqueia o tech-spec.
- Entity sem mapper → bloqueia tech-spec e task-contract.
- Uso de `expect/actual` para tipo de domínio → red flag (business logic
  não deve depender de platform shim).
