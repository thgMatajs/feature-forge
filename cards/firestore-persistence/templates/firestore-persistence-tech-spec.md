<!--
  Fragmento contribuído por: firestore-persistence
  Target: tech-spec.md
  Section: Data layer
  Merge: append-section
  Extension-point anchor: <!-- extension-point: section:Data layer -->
-->

### Data — Firestore (persistence)

Esta seção é obrigatória sempre que a feature toca em Cloud Firestore para
**operações CRUD one-shot**, **queries custom** ou **batch writes**.
Snapshot listeners (realtime) são responsabilidade do card
`firestore-realtime` — se a feature usa listener, há outra subseção
contribuída por aquele card. Security rules ficam em
`firestore-security-rules`.

Cada subitem abaixo deve estar respondido — não deixar `TBD`. Se a feature
não toca Firestore em CRUD, marque "Não aplicável" e justifique.

#### 1. Repository pattern

- Toda I/O Firestore mora atrás de um `{Feature}Repository` (interface no
  domain + `{Feature}RepositoryImpl` em data).
- ViewModels/UseCases **não** importam tipos do SDK Firebase
  (`DocumentSnapshot`, `QuerySnapshot`, `FirebaseFirestoreException`).
- `FirebaseFirestore` injetado via Koin (`@Single` provider em
  `commonMain`/`androidMain` ou factory function em iOS/Web).
- Mapper DTO → Domain explícito (ver
  `data-contract-spec.yaml § entities[].mapper`).
- `CoroutineDispatcher` injetado no construtor (`Dispatchers.IO` em
  produção, `UnconfinedTestDispatcher` em testes). NUNCA hardcode
  `Dispatchers.IO` no corpo da função.

#### 2. Reads — one-shot

| Cenário | Estratégia |
|---|---|
| Read pontual (detalhe, validação) | `suspend fun` com `getDocument().await()` |
| Lista paginada | `suspend fun` + cursor manual com `startAfter` ou `Flow<PagingData<T>>` |
| Lista one-shot | `suspend fun` com `getDocuments().await()` |
| Realtime (snapshot listener) | **fora deste card** — ver subseção contribuída por `firestore-realtime` |

Listar nas tabelas em `data-contract-spec.yaml § queries[]` CADA query
one-shot da feature com sua estratégia.

#### 3. Writes — atomicidade

- Write único → `set` / `update` / `delete` com `await()`.
- Múltiplos writes interdependentes → `WriteBatch` (até 500 ops) ou
  `runTransaction` (quando há read-modify-write).
- Server timestamp para `created_at` / `updated_at`
  (`FieldValue.serverTimestamp()` — nunca `System.currentTimeMillis`).
- Documentar idempotência: chamada 2x → mesmo estado final? Loading-guard no
  ViewModel já bloqueia chamada concorrente, mas o backend não deve assumir.

#### 4. Cache strategy

| Estratégia | Quando usar |
|---|---|
| Sem cache | Dados sempre frescos; baixa frequência; baixo volume |
| Cache local Firestore SDK | Default do SDK (`PersistentCacheSettings`) — bom para offline temporário |
| Cache local separado (Room/SwiftData) | UX offline-first → compor com card `persistence-local` |
| Cache em memória | Hot-data dentro da sessão; descartar no logout |

Se a feature usa offline-first com Room/SwiftData, declarar
explicitamente qual é o source-of-truth (local com sync push, ou remoto com
mirror local) — paridade entre Android/iOS é obrigatória.

#### 5. Mapeamento de erro: `FirebaseFirestoreException` → Domain

Todo `try/catch` na camada de data converte para o tipo de domínio:

| Code Firestore | Domain mapping (exemplo) |
|---|---|
| `PERMISSION_DENIED` | `DomainError.Forbidden` |
| `UNAUTHENTICATED` | `DomainError.NotAuthenticated` |
| `UNAVAILABLE` / `DEADLINE_EXCEEDED` | `DomainError.Network` |
| `NOT_FOUND` | `DomainError.NotFound` (ou retorno null) |
| `FAILED_PRECONDITION` (índice ausente) | `DomainError.Internal` + log crítico |
| `ABORTED` (transação) | `DomainError.Retryable` + retry policy |
| Outros | `DomainError.Unknown` + `Crashlytics.recordException` |

ViewModel/UseCase consomem APENAS o tipo domain. Integration com
Crashlytics: ver card `crashlytics` quando ativo (paridade Android/iOS
via shared class).

#### 6. Índices

Toda query compound ou `orderBy + where` precisa de índice em
`firestore.indexes.json`. Em dev, o SDK loga "create index" link no erro
`FAILED_PRECONDITION` — **NUNCA aceitar esse link como solução em PR**;
declarar o índice no arquivo committado. Validator `check-firestore-indexes`
(severity: warn) sinaliza queries sem índice declarado.

#### 7. Threading / Main thread

- Toda chamada Firestore via `withContext(io)` no Repository.
- Mapping pesado (parsing de listas grandes, agregação) →
  `Dispatchers.Default`.
- Update do `StateFlow` volta para `Dispatchers.Main` (default do
  `viewModelScope`).
- NUNCA `runBlocking` em código de produção.

#### 8. Cross-feature reusability candidates

Listar helpers de Firestore promovidos para `shared/core/`: mappers de
timestamp, conversor de `FirebaseFirestoreException` → domain, builders de
batch. Promoção segue rule-of-three (ver `mobile-engineering.md`) — só
promove na 3ª ocorrência (exceto SP-022 eager-extract).

#### 9. Atualização obrigatória da 4-source-of-truth

Toda PR que toca em coleção, query, índice ou regra atualiza
**na mesma PR**:

- [ ] `docs/specs/data/firestore-data-model.md` — shape do doc/campos
- [ ] `docs/specs/data/query-catalog.md` — queries + índices
- [ ] `docs/specs/data/access-matrix.md` — quem pode `create/read/update/delete`
- [ ] `docs/specs/data/security-and-threat-model.md` — STRIDE para nova exposição

Não fazer essa atualização é red flag explícito no review da tech-spec.

<!-- /firestore-persistence — Data layer -->
