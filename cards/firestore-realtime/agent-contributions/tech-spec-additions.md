<!--
  Fragment injetado no `tech-spec-agent` no extension-point
  `section:Data layer`. Ativo quando o card `firestore-realtime` está
  presente em workflow-config.yaml > cards.active.

  Objetivo: forçar tech-spec.md a descrever lifecycle de listeners,
  estratégia de sharing, reconnection, backpressure, latência esperada
  e cache-and-network vs server-only — de forma uniforme entre features
  que consomem Firestore em tempo real.
-->

## Card contribution — `firestore-realtime` (Data layer)

A feature consome Firestore em tempo real. O tech-spec precisa
descrever explicitamente os **sete pilares** abaixo. Nada é opcional.

Este card depende de `firestore-persistence` — Repository pattern,
DTO↔domain mapping, path convention e taxonomia de erro (`FirestoreError`)
vêm de lá. Esta contribuição cobre apenas o eixo realtime.

### 1. `Flow<T>` cold para streams; `suspend fun` para one-shot

```kotlin
interface BonsaiRepository {
    fun observeBonsaiList(uid: String): Flow<List<Bonsai>>
    fun observeBonsai(id: String): Flow<Bonsai?>

    suspend fun getBonsai(id: String): Result<Bonsai>     // firestore-persistence
    suspend fun saveBonsai(bonsai: Bonsai): Result<Unit>  // firestore-persistence
}
```

Regras:

- Stream contínuo → `Flow`. One-shot → `suspend fun`.
- O `Flow` é **cold**: começa ao primeiro collect, cancela com a
  coroutine. Service nunca expõe `MutableSharedFlow` (hot).
- Observar para depois `take(1).first()` é anti-pattern — usar `get()`.

### 2. `callbackFlow` + `awaitClose` (obrigatório)

```kotlin
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
```

Pontos invioláveis:

- `awaitClose { registration.remove() }` — sem isso o listener vaza.
- Erro do listener → `close(throwable)`; **não** swallow com try/catch.
- Mapping DTO→domain em `.map { ... }.flowOn(dispatchers.default)` no
  Repository (não no Service).

### 3. Sharing strategy obrigatória

```kotlin
val state: StateFlow<StateUI<BonsaiListUI>> = observeBonsaiList()
    .map { StateUI.Processed(it.toUI()) }
    .catch { emit(StateUI.Error(it.toErrorUI())) }
    .stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = StateUI.Processing,
    )
```

Default: `WhileSubscribed(5_000)`. Tech-spec deve declarar a estratégia
e justificar se diferir:

| Estratégia | Quando usar |
|---|---|
| `WhileSubscribed(5000)` | **Default** — rotação não reabre, billing controlado |
| `WhileSubscribed(0)` | Apenas em testes ou tela one-screen sem rotação |
| `Eagerly` | Listener crítico (notifications) que precisa rodar com VM viva |
| `Lazily` | Raro — listener só liga após interação explícita |

Silenciar a escolha é ambiguidade — abrir `open-question`.

### 4. Reconnection automática (sem código nosso)

O SDK Firestore reconecta sozinho após queda de rede. O `Flow` pausa
durante a queda e re-emite ao voltar. Tech-spec deve declarar:

- **Não** implementar retry/backoff manual em cima — duplica trabalho.
- Para indicar "offline" na UI, consumir `NetworkMonitor` em paralelo
  via `combine(observe..., networkMonitor.online)`.
- Erros recuperáveis (`UNAVAILABLE`, `DEADLINE_EXCEEDED`) não terminam
  o `Flow`.
- Erros não-recuperáveis (`PERMISSION_DENIED`, `UNAUTHENTICATED`,
  `FAILED_PRECONDITION`) terminam o `Flow` → UI vai para `StateUI.Error`.

### 5. cache-and-network vs server-only

Default: **cache-and-network** (SDK aplica automaticamente). O `Flow`
emite snapshot cache imediato e depois o servidor.

Casos que exigem `Source.SERVER`:

- Tela pós-mutation onde a UX precisa de consistência forte.
- Paginação por cursor onde o cache pode confundir o offset.

Declarar na tech-spec: `firestore-source: cache-and-network | server`.
Para `server`, usar `.get(Source.SERVER)` (one-shot, fora deste card) —
listeners sempre são cache-and-network por design do SDK.

### 6. Latência esperada (declarar na tech-spec)

| Operação | Latência típica | Aceitável? |
|---|---|---|
| Primeira emissão (cache) | < 50ms | ✓ |
| Primeira emissão (server, online) | 150-400ms | ✓ |
| Update pós-write local | < 100ms | ✓ (latency compensation) |
| Update cross-device | 200-800ms | ✓ |

Se a feature exige < 100ms cross-device, Firestore não atende — abrir
`open-question` sugerindo Realtime Database ou WebSocket dedicado.

### 7. Threading checklist

- Service registra listener na thread chamadora; SDK invoca callback
  em thread interna (não-Main, mas não garantida).
- Mapping DTO→domain → `flowOn(dispatchers.default)`.
- `_uiState.update { ... }` → Main (default do `viewModelScope`).
- **NUNCA** `runBlocking` para aguardar primeira emissão (deadlock
  potencial no SDK).

### 8. Test plan summary (delta sobre firestore-persistence)

- `{Feature}ServiceFake` em `commonTest` expõe
  `MutableSharedFlow<List<{Entity}Response>>` — teste controla emissões.
- Repository test: cobre mapping DTO→domain + propagação de erro (Flow
  termina com `FirestoreError`).
- ViewModel test (Turbine): cobre transições Processing → Processed
  → re-Processed (segunda emissão real-time) → Error.
- Usar `WhileSubscribed(0)` ou coletor explícito no teste — não
  depender do delay de 5s do default.
- `cancelAndConsumeRemainingEvents()` ao final de cada `test {}`.
