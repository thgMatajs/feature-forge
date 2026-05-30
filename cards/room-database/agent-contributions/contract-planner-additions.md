<!-- Injected into: contract-planner-agent
     Extension point: section:Data Contract
     Source card:     room-database v1.0.0
-->

## Data Contract — Local persistence with Room (card `room-database`)

Quando a feature usa cache/persistência local, o `data-contract-spec.yaml`
**deve** declarar a chave `room-tables` (fragmento contribuído por este
card) com cobertura exaustiva das tabelas tocadas. O contract-planner é
responsável por:

1. **Identificar quais entidades pertencem ao local** — domain models
   que precisam sobreviver a `process death`, alimentar UI offline, ou
   ser cache de payload remoto.
2. **Declarar cada tabela com schema completo** — sem campos
   "deduzidos depois". Cada coluna tem `type` (TEXT/INTEGER/REAL/BLOB),
   `nullable`, `primary-key`, `indexed`.
3. **Listar TODAS as queries do DAO** — cada query com `signature`,
   `returns` (flow|suspend), `sql` (exato) e `bdd-ref` apontando para
   scenario do BDD da feature. Query não documentada = bug de contract.
4. **Declarar índices compostos explícitos** — qualquer query com
   `WHERE x = ? ORDER BY y` ou `WHERE x = ? AND y = ?` exige `@Index`
   composto declarado em `room-tables[*].schema.indices`.
5. **Declarar migrations** — `current-version` da `@Database` +
   `history` listando cada transição. Bump de version sem entrada em
   `history` falha o `check-room-migrations` (Phase 5).
6. **Pareamento com persistência server-side** — quando a feature tem
   `persistence-server` ativo (ex.: `firestore-persistence`), preencher
   `sync-strategy` com `paired-with-server: true`, `mode`
   (write-through/stale-while-revalidate/offline-first/local-only) e
   `invalidation`. Sem isso, o tech-spec não consegue decidir fonte da
   verdade.

### Foreign keys e integridade referencial

- Room suporta `@ForeignKey` apenas **dentro do mesmo `@Database`**.
  Cross-database referencial não existe — declarar em
  `room-tables[*].schema.foreign-keys` apenas quando a tabela referenciada
  pertence ao mesmo DB da feature.
- Se a feature precisa referenciar dados de outra feature (DB separado),
  use ID solto (`TEXT`) sem foreign-key e justifique no tech-spec na
  seção "Local Persistence — Room".

### Sensitivity / privacy

- Diferente de `firestore-collections` (que tem coluna `sensitivity`
  porque o backend é multiusuário), `room-tables` é local — banco
  privado do usuário. Mesmo assim:
  - Dados privilegiados (token, PII regulada) **não** ficam em Room
    a menos que cifrados (TypeConverter de field-level encryption ou
    SQLCipher).
  - Sinalize no contract qualquer coluna com dados sensíveis →
    tech-spec decide estratégia (não persistir vs cifrar).

### Cross-checks com outros cards ativos

- Se `serialization-json` está ativo e a Entity é hidratada a partir de
  DTO server-side, o Mapper compõe: `Response → Domain → Entity` (ou
  rota direta `Response → Entity` quando estrutura idêntica — registrar
  no tech-spec).
- Se `firestore-realtime` está ativo, queries `Flow` do DAO podem ser
  combinadas com `Flow` do snapshot listener via `combine` no
  Repository. Declarar a estratégia em `sync-strategy.invalidation`.
- Se `crashlytics` está ativo, falhas de DAO (`SQLiteException`, schema
  corrompido) viram non-fatal exception com `errorCode` + `causeType`
  conforme `observability.md`.

### Anti-patterns (bloquear no contract review)

- Tabela declarada sem `dao.queries` — implica DAO improvisado em fase
  posterior, viola contract.
- Query `Flow` sem `bdd-ref` — UI reativa precisa de scenario BDD
  cobrindo o ciclo emit/observe.
- `migrations.current-version > 1` sem entrada correspondente em
  `migrations.history` — falha no `check-room-migrations`.
- `sync-strategy.paired-with-server: true` sem `mode` e `invalidation`
  preenchidos — contract incompleto.
- Foreign-key declarando referência cross-database (Room não suporta) —
  erro de contract.
