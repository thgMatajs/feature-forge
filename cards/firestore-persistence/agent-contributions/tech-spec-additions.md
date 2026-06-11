<!--
  Injetado em: tech-spec-agent
  Extension-point: section:Data layer
  Card: firestore-persistence
-->

## firestore-persistence — Data Strategy

Ao escrever a seção "Data layer" do `tech-spec.md` quando a feature usa
Firestore em **CRUD/queries one-shot/batch writes**, cobrir explicitamente
cada item abaixo. Não deixar `TBD`. Se algum subitem não se aplica, marcar
"Não aplicável" e justificar.

> **Escopo deste card.** Snapshot listeners (realtime) NÃO entram aqui —
> são responsabilidade do card `firestore-realtime`, que injeta sua própria
> subseção `Data — Firestore (realtime)` neste mesmo `tech-spec.md`.
> Security rules são responsabilidade do card `firestore-security-rules`.
> Se a feature usa listener, confirmar com o usuário que aquele card está
> ativo antes de prosseguir.

### 1. Repository pattern

- Toda I/O Firestore atrás de `{Feature}Repository` (interface no domain +
  Impl em data).
- ViewModel/UseCase NÃO importam tipos do SDK Firebase
  (`DocumentSnapshot`, `QuerySnapshot`, `FirebaseFirestoreException`).
- `FirebaseFirestore` injetado via Koin (`@Single` em `commonMain`
  quando possível, ou em `androidMain`; iOS/Web via factory function).
- Mapper DTO → Domain explícito; nullability resolvida no mapper, não na UI.
- `CoroutineDispatcher` injetado no construtor — nunca `Dispatchers.IO`
  hardcoded no corpo.

### 2. Reads one-shot

- Read pontual: `suspend fun` com `getDocument().await()`.
- Lista one-shot: `suspend fun` com `getDocuments().await()`.
- Paginação manual: cursor com `startAfter` + `limit`.
- Paginação reativa: `Flow<PagingData<T>>` (com card de paging, se houver).

### 3. Writes

- Write único → `set` / `update` / `delete` + `await()`.
- Múltiplos writes interdependentes → `WriteBatch` (até 500 ops) ou
  `runTransaction` (quando há read-modify-write).
- Server timestamps → `FieldValue.serverTimestamp()`
  (nunca `System.currentTimeMillis`).
- Idempotência documentada: chamada 2x → mesmo estado final?
- Retry: `ABORTED` em transação → retry com backoff curto (até 3x).

### 4. Cache strategy

Documentar a política de cache por query:

| Estratégia | Quando usar |
|---|---|
| Sem cache | Dados sempre frescos, baixa frequência, baixo volume |
| Cache SDK Firestore | Default; offline temporário sem coordenação extra |
| Cache local separado (Room/SwiftData) | Offline-first → compor com card `persistence-local` |
| Cache em memória | Hot-data dentro da sessão; descartar no logout |

Se a feature usa offline-first com Room/SwiftData, declarar
explicitamente qual é o source-of-truth (local com sync push, ou remoto com
mirror local). Paridade Android↔iOS obrigatória.

### 5. Error handling — `FirebaseFirestoreException` → Domain

Repository converte códigos Firestore em tipos de erro de domínio:

| Code | Domain |
|---|---|
| `PERMISSION_DENIED` | `DomainError.Forbidden` |
| `UNAUTHENTICATED` | `DomainError.NotAuthenticated` |
| `UNAVAILABLE` / `DEADLINE_EXCEEDED` | `DomainError.Network` |
| `NOT_FOUND` | `DomainError.NotFound` ou retorno null |
| `FAILED_PRECONDITION` | `DomainError.Internal` + log crítico (índice ausente) |
| `ABORTED` (transação) | `DomainError.Retryable` + retry policy |
| Outros | `DomainError.Unknown` + `Crashlytics.recordException` |

Erros não previstos → log + Crashlytics (paridade Android/iOS via shared
class — ver card `firebase-crashlytics` quando ativo).

### 6. Threading

- Chamadas Firestore: `withContext(io)` no Repository.
- Parsing pesado / mapping de listas grandes: `withContext(default)`.
- Update de StateFlow: `Dispatchers.Main` (default do `viewModelScope`).
- NUNCA `runBlocking` em código de produção.

### 7. Índices

Toda query compound ou `orderBy + where` declara índice em
`firestore.indexes.json`. NUNCA aceitar criar índice via console do
Firebase — declarar no arquivo committado. Validator
`check-firestore-indexes` (severity: warn) sinaliza queries sem índice.

### 8. Atualização obrigatória — 4-source-of-truth

Esta seção precisa terminar com o checklist:

- [ ] `docs/specs/data/firestore-data-model.md` atualizado nesta PR
- [ ] `docs/specs/data/query-catalog.md` atualizado nesta PR
- [ ] `docs/specs/data/access-matrix.md` atualizado nesta PR
- [ ] `docs/specs/data/security-and-threat-model.md` atualizado nesta PR

Se algum item não foi atualizado, justificar (ex.: "feature apenas lê doc
existente sem mudar shape — atualização não necessária"). Sem justificativa,
o `tech-spec` retorna `status: partial`.
