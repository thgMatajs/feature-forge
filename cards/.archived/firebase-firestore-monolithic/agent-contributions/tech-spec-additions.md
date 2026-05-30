<!--
  Injetado em: tech-spec-agent
  Extension-point: section:Data layer
  Card: firebase-firestore
-->

## firebase-firestore — Data Strategy

Ao escrever a seção "Data layer" do `tech-spec.md`, cobrir explicitamente
cada item abaixo. Não deixar `TBD`. Se algum subitem não se aplica, marcar
"Não aplicável" e justificar.

### 1. Repository pattern

- Toda I/O Firestore atrás de `{Feature}Repository` (interface no domain +
  Impl em data).
- ViewModel/UseCase NÃO importam tipos do SDK Firebase.
- Mapper DTO → Domain explícito; nullability resolvida no mapper, não no UI.
- `CoroutineDispatcher` injetado no construtor — nunca `Dispatchers.IO`
  hardcoded no corpo.

### 2. Snapshot listeners (realtime)

- Quando usar: lista que precisa refletir mudanças server-side em tempo real
  (ex.: lista colaborativa, status de processing).
- Lifecycle: `Flow` com `callbackFlow { listener }`, exposto como
  `StateFlow<StateUI<T>>` com `SharingStarted.WhileSubscribed(5_000)` no shared.
- Backpressure: `distinctUntilChanged` + `flowOn(Dispatchers.Default)` antes
  de chegar na UI; mapear domain→UI fora da Main.
- iOS: `for await` em `.task {}` — cancela com a View automaticamente.

### 3. Cache strategy

Documentar a política de cache por query:

| Estratégia | Quando usar |
|---|---|
| Sem cache local | Dados sempre frescos, baixa frequência, baixo volume |
| Cache offline-first | UX precisa funcionar offline → compor com card `persistence-local` |
| Cache em memória | Hot-data dentro da sessão; descartar no logout |

Se a feature usa offline-first com Room/SwiftData, declarar explicitamente
qual é o source-of-truth (local com sync push, ou remoto com mirror local).

### 4. Error handling — `FirebaseFirestoreException` → Domain

Repository converte códigos Firestore em tipos de erro de domínio. Tabela
canônica:

| Code | Domain |
|---|---|
| `PERMISSION_DENIED` | `DomainError.Forbidden` |
| `UNAUTHENTICATED` | `DomainError.NotAuthenticated` |
| `UNAVAILABLE` / `DEADLINE_EXCEEDED` | `DomainError.Network` |
| `NOT_FOUND` | `DomainError.NotFound` ou retorno null |
| `FAILED_PRECONDITION` | `DomainError.Internal` + log crítico (índice ausente) |
| Outros | `DomainError.Unknown` + `Crashlytics.recordException` |

Erros não previstos → log + Crashlytics (paridade Android/iOS via shared
class — ver card `crashlytics` quando ativo).

### 5. Writes

- Write único → `set`/`update`/`delete` + `await()`
- Múltiplos writes interdependentes → `WriteBatch` ou `runTransaction`
- Server timestamps → `FieldValue.serverTimestamp()` (nunca `System.currentTimeMillis`)
- Idempotência documentada: chamada 2x → mesmo estado final?

### 6. Threading

- Chamadas Firestore: `withContext(io)` no Repository
- Parsing pesado / mapping de listas grandes: `withContext(default)`
- Update de StateFlow: `Dispatchers.Main` (default do `viewModelScope`)
- NUNCA `runBlocking` em código de produção

### 7. Security rules — referência

Toda operação listada em `data-contract-spec.yaml § firestore-collections[].operations`
amarra a um bloco em `firestore.rules`. Validator
`check-firestore-rules-coverage` (severity: error) bloqueia se faltar.

### 8. Índices

Toda query compound ou `orderBy + where` declara índice em
`firestore.indexes.json`. NUNCA aceitar criar índice via console do Firebase —
declarar no arquivo committado.

### 9. Atualização obrigatória — 4-source-of-truth

Esta seção precisa terminar com o checklist:

- [ ] `docs/specs/data/firestore-data-model.md` atualizado nesta PR
- [ ] `docs/specs/data/query-catalog.md` atualizado nesta PR
- [ ] `docs/specs/data/access-matrix.md` atualizado nesta PR
- [ ] `docs/specs/data/security-and-threat-model.md` atualizado nesta PR

Se algum item não foi atualizado, justificar (ex.: "feature apenas lê doc
existente sem mudar shape — atualização não necessária"). Sem justificativa,
o `tech-spec` retorna `status: partial`.
