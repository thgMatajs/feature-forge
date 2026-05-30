<!--
  Fragmento contribuído por: firebase-firestore
  Target: tech-spec.md
  Section: Data layer
  Merge: append-section
  Extension-point anchor: <!-- extension-point: section:Data layer -->
-->

### Data — Firestore

Esta seção é obrigatória sempre que a feature toca em Cloud Firestore. Cada
subitem deve estar respondido — não deixar `TBD`. Se a feature não toca
Firestore, marque "Não aplicável" e justifique.

#### 1. Repository pattern

- Toda I/O Firestore mora atrás de um `{Feature}Repository` (interface no
  domain + `{Feature}RepositoryImpl` em data).
- ViewModels/UseCases **não** importam tipos do SDK Firebase
  (`DocumentSnapshot`, `QuerySnapshot`, `FirebaseFirestoreException`).
- Mapper DTO → Domain é explícito (ver `data-contract-spec.yaml § entities[].mapper`).
- Dispatcher injetado no construtor (`Dispatchers.IO` em produção,
  `UnconfinedTestDispatcher` em testes). NUNCA hardcode `Dispatchers.IO` no
  corpo da função.

#### 2. Reads — one-shot vs realtime

| Cenário | Estratégia |
|---|---|
| Read pontual (detalhe, validação) | `suspend fun` com `await()`/`getDocuments()` |
| Lista que precisa atualizar em tempo real | `Flow<T>` com `snapshotListener`, lifecycle `WhileSubscribed(5_000)` no shared |
| Paginação | `Flow<PagingData<T>>` ou cursor manual com `startAfter` |
| Cache offline-first | Card de persistência local (Room/SwiftData) como source-of-truth, Firestore como sync |

Listar nas tabelas abaixo CADA query da feature com sua estratégia.

#### 3. Writes — atomicidade

- Write único → `set` / `update` / `delete` com `await()`.
- Múltiplos writes interdependentes → `WriteBatch` ou `runTransaction`.
- Server timestamp para `created_at` / `updated_at` (`FieldValue.serverTimestamp()`).
- Documentar idempotência: pode ser chamado 2x? Risco de dup-key? (loading-guard
  no ViewModel já bloqueia chamada concorrente — mas backend não deve assumir).

#### 4. Mapeamento de erro: `FirebaseFirestoreException` → Domain

Todo `try/catch` na camada de data converte para o tipo de domínio:

| Code Firestore | Domain mapping (exemplo) |
|---|---|
| `PERMISSION_DENIED` | `DomainError.Forbidden` |
| `UNAUTHENTICATED` | `DomainError.NotAuthenticated` |
| `UNAVAILABLE` / `DEADLINE_EXCEEDED` | `DomainError.Network` |
| `NOT_FOUND` | `DomainError.NotFound` (ou retorno null, dependendo do UseCase) |
| `FAILED_PRECONDITION` (índice ausente) | `DomainError.Internal` + log crítico |
| Outros | `DomainError.Unknown` + `Crashlytics.recordException` |

ViewModel/UseCase consomem APENAS o tipo domain. Crashlytics integration: ver
`crashlytics` card.

#### 5. Security rules — cobertura

Toda operação listada em `data-contract-spec.yaml § firestore-collections[].operations`
referencia um bloco em `firestore.rules`. Validator
`check-firestore-rules-coverage` (severity: error) bloqueia se faltar.

Padrão de teste: rules-unit-tests rodando contra emulator Firestore — toda PR
que mexe em `firestore.rules` precisa de teste verde no emulator.

#### 6. Índices

Toda query compound ou `orderBy + where` precisa de índice em
`firestore.indexes.json`. Em dev, o SDK loga "create index" link no erro
`FAILED_PRECONDITION` — NUNCA aceitar esse link como solução em PR, declarar
o índice no arquivo committado.

#### 7. Threading / Main thread

- Toda chamada Firestore via `withContext(io)` no Repository.
- Mapping pesado (parsing de listas grandes, agregação) → `Dispatchers.Default`.
- Update do `StateFlow` volta para `Dispatchers.Main` (default do `viewModelScope`).

#### 8. Cross-feature reusability candidates

Listar nesta seção helpers de Firestore promovidos para `shared/core/`:
mappers de timestamp, conversor de `FirebaseFirestoreException`, builders de
batch. Promoção segue rule-of-three (ver `mobile-engineering.md`) — só promove
na 3ª ocorrência (exceto SP-022 eager-extract).

#### 9. Atualização obrigatória da 4-source-of-truth

Toda PR que toca em coleção, query, índice ou regra de segurança atualiza
**na mesma PR**:

- [ ] `docs/specs/data/firestore-data-model.md` — shape do doc/campos
- [ ] `docs/specs/data/query-catalog.md` — queries + índices
- [ ] `docs/specs/data/access-matrix.md` — quem pode `create/read/update/delete`
- [ ] `docs/specs/data/security-and-threat-model.md` — STRIDE para nova exposição

Não fazer essa atualização é red flag explícito no review da tech-spec.

<!-- /firebase-firestore — Data layer -->
