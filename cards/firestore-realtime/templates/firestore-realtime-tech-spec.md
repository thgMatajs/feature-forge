<!--
  Template fragment contribuído pelo card `firestore-realtime`.
  Merge mode: append-section em tech-spec.md sob
  "Realtime Strategy — Firestore Listeners".

  Ativo quando o card está em workflow-config.yaml > cards.active.
  Edição manual deste arquivo é mudança de canonical — propague via
  `forge reconfigure` → "atualizar card do canonical".
-->

## Realtime Strategy — Firestore Listeners

A feature consome dados Firestore em tempo real via `addSnapshotListener`
(SDK Android/iOS) ou extensão `.snapshots()` (Kotlin KMP). O acesso é
mediado pelo `{Feature}Repository` em `commonMain` que expõe
`Flow<T>` cold — nunca expõe a API nativa de listener para a UI.

> Depende de `firestore-persistence`. Repository pattern, DTO↔domain
> mapping, path convention e taxonomia de erro são herdados desse card.
> Esta seção descreve apenas o **eixo realtime**.

### Quando usar `Flow` vs `suspend fun`

| Operação | Forma |
|---|---|
| Observar lista (`/bonsais` por uid) | `fun observeBonsaiList(): Flow<List<Bonsai>>` |
| Observar documento (`/bonsais/{id}`) | `fun observeBonsai(id: String): Flow<Bonsai?>` |
| Ler one-shot pós-mutation | `suspend fun getBonsai(id: String): Result<Bonsai>` — não é deste card |
| Criar / editar / deletar | `suspend fun` — não é deste card |

Regra: stream contínuo → `Flow`. One-shot → `suspend fun`
(`firestore-persistence`). Não misturar — observar para depois fazer
`take(1).first()` é anti-pattern (`get()` direto custa menos).

### Repository expondo `Flow` cold

```kotlin
class BonsaiRepositoryImpl(
    private val service: BonsaiService,
    private val mapper: BonsaiMapper,
    private val dispatchers: AppDispatchers,
) : BonsaiRepository {

    override fun observeBonsaiList(uid: String): Flow<List<Bonsai>> =
        service.observeCollection("$uid/bonsais")
            .map { snapshots -> snapshots.map(mapper::toDomain) }
            .flowOn(dispatchers.default)
}
```

O `Service` encapsula o `callbackFlow`:

```kotlin
class BonsaiServiceImpl(
    private val firestore: FirebaseFirestore,
) : BonsaiService {

    override fun observeCollection(path: String): Flow<List<BonsaiResponse>> = callbackFlow {
        val registration = firestore.collection(path)
            .addSnapshotListener { snapshot, error ->
                when {
                    error != null -> close(error)
                    snapshot != null -> trySend(snapshot.toObjects(BonsaiResponse::class.java))
                }
            }
        awaitClose { registration.remove() }
    }
}
```

Pontos invioláveis:

- `awaitClose { registration.remove() }` — sem isso o listener vaza.
- Mapping DTO→domain em `Dispatchers.Default` via `flowOn` no Repository
  (não no Service).
- Service **não** importa nada de `domain/`.

### ViewModel — `stateIn(WhileSubscribed(5_000))`

```kotlin
class BonsaiListViewModel(
    observeBonsaiList: ObserveBonsaiListUseCase,
) : ViewModel() {

    val state: StateFlow<StateUI<BonsaiListUI>> =
        observeBonsaiList()
            .map<List<Bonsai>, StateUI<BonsaiListUI>> { StateUI.Processed(it.toUI()) }
            .catch { emit(StateUI.Error(it.toErrorUI())) }
            .stateIn(
                scope = viewModelScope,
                started = SharingStarted.WhileSubscribed(5_000),
                initialValue = StateUI.Processing,
            )
}
```

Por quê `WhileSubscribed(5_000)`:

- Rotação de tela / navegação back-forward não reabre conexão Firestore.
- Tela inativa > 5s desconecta — billing/quota param.
- `Eagerly` mantém listener vivo enquanto a VM existir (vazamento em
  telas raramente visíveis).
- `WhileSubscribed(0)` reabre conexão a cada novo subscriber.

Tech-spec deve declarar **explicitamente** a flow-strategy escolhida e
justificar se diferir de `WhileSubscribed(5000)` (default deste projeto).

### Cache-and-network vs server-only

Default: **cache-and-network** (SDK aplica automaticamente). O `Flow`
emite snapshot cache imediato e depois o servidor — UI mostra dado
stale por ms.

Casos que exigem `Source.SERVER`:

- Tela pós-mutation onde a UX precisa de consistência forte.
- Paginação por cursor onde o cache pode confundir o offset.

Declarar na tech-spec: `firestore-source: cache-and-network | server`.
Silenciar é ambiguidade.

### Error mapping em stream

| Erro Firestore (`FirebaseFirestoreException.Code`) | Domain | Comportamento |
|---|---|---|
| `PERMISSION_DENIED` | `FirestoreError.PermissionDenied` | termina o Flow, UI vai para Error |
| `UNAUTHENTICATED` | `FirestoreError.AuthRequired` | termina o Flow, navega para login |
| `NOT_FOUND` | `FirestoreError.NotFound` | (para observe de documento) emite `null` ou termina |
| `UNAVAILABLE` / `DEADLINE_EXCEEDED` | (sem ação — SDK reconecta) | listener segue vivo |
| `FAILED_PRECONDITION` (índice) | `FirestoreError.Misconfigured` | crashlytics + Error |
| default | `FirestoreError.Unknown` | crashlytics + Error |

Taxonomia compartilhada com `firestore-persistence` — não duplicar
sealed class.

### Reconnection automática

O SDK Firestore reconecta sozinho ao voltar online: o `Flow` pausa
durante a queda e re-emite a partir do snapshot atualizado. **Não**
implementar retry manual em cima do listener — duplica trabalho.

Para indicar "offline" para a UI, consumir `NetworkMonitor` em paralelo:

```kotlin
combine(
    observeBonsaiList(),
    networkMonitor.online,
) { bonsais, online ->
    BonsaiListUI(items = bonsais.toUI(), offline = !online)
}
```

### Lifecycle e cancelamento

- ViewModel coleta via `stateIn(viewModelScope, ...)` ou
  `viewModelScope.launch { flow.collect { ... } }`.
- iOS: SKIE expõe como `AsyncSequence`; consumir com `for await` em
  `.task {}` cancela junto com a View.
- Listener registration removido em `awaitClose` — garantido pelo
  cancelamento do `callbackFlow` quando o último collector sai.

### Threading

- Service `callbackFlow` registra listener na thread chamadora; SDK
  Firestore invoca callback em sua própria thread interna.
- Mapping DTO→domain → `flowOn(dispatchers.default)`.
- Atualização de `StateFlow` → Main (default do `viewModelScope`).
- **NUNCA** `runBlocking` para aguardar primeira emissão.

### Testes

- Service: fake `{Feature}Service` em `commonTest` expõe
  `MutableSharedFlow<List<{Entity}Response>>` — teste controla emissões
  e cobre transições (`emit(listA) → emit(listB) → close(error)`).
- Repository: testa mapeamento DTO→domain e propagação de erro (Flow
  termina com `FirestoreError`).
- ViewModel: usar Turbine com `WhileSubscribed(0)` no teste para evitar
  delay artificial; cobrir Processing → Processed → re-Processed
  (segunda emissão) → Error.
- Emulator + suite de rules confirma que `read` autoriza listener (cobertura
  do card `firestore-security-rules`).
