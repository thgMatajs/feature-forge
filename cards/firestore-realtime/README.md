# Card `firestore-realtime`

> Categoria: `backend` · Maturidade: `stable` · Provê `realtime-stream`

Camada de **streaming reativo** sobre `firestore-persistence`. Expõe
documentos e queries do Cloud Firestore como `Flow<T>` (via
`addSnapshotListener` / extensões `.snapshots()` do SDK), com lifecycle
gerenciado pelo `viewModelScope` e backpressure controlado por
`SharingStarted.WhileSubscribed(5000)`.

Este card **não** substitui `firestore-persistence` — depende dele. O
`-persistence` cuida de leituras one-shot, escritas, transações e mapping
DTO↔domain; este card adiciona o eixo **realtime** sobre o mesmo
backend.

É **singular**: `realtime-stream` admite um provedor por projeto.
WebSocket/SSE chegam apenas em v1.1.

---

## O que este card declara

| Item | Valor |
|---|---|
| `provides` | `realtime-stream` |
| `requires` | `persistence-server` (provido por `firestore-persistence`) |
| `conflicts-with` | `realtime-stream` (outros provedores singulares) |
| `config-defaults` | `conventions.realtime.stream: firestore-listeners`, `conventions.realtime.flow-strategy: SharingStarted.WhileSubscribed(5000)` |
| Detecção (threshold 0.5) | `*.kt` contém `addSnapshotListener` (0.4) **+** `.snapshots()` (0.3) **+** `*.swift` `addSnapshotListener` (0.3) **+** `build.gradle*` `firebase-firestore` (0.2) |

---

## Quando este card ativa

`forge init` ativa automaticamente quando o repositório usa listeners
Firestore — tipicamente em paralelo com `firestore-persistence`. Se o
projeto consome Firestore apenas via `get()` one-shot, este card fica
fora; a feature que introduzir o primeiro stream realtime deve rodar
`forge reconfigure` → "adicionar card" → `firestore-realtime`.

A detecção é intencionalmente fraca isolada (0.4 do primeiro signal) —
o card precisa de pelo menos duas evidências para atingir threshold 0.5,
evitando ativação falso-positiva em projetos que só citam o termo em
docs/tests.

---

## Convenções deste projeto

### 1. Realtime sempre via `Flow<T>` (cold)

```kotlin
interface BonsaiRepository {
    fun observeBonsaiList(): Flow<List<Bonsai>>
    fun observeBonsai(id: String): Flow<Bonsai?>
}
```

Regras:

- Stream contínuo (lista, documento observável, contadores em tempo real)
  → `Flow<T>`.
- Leitura one-shot, criação/edição, delete, transação → `suspend fun`
  (responsabilidade de `firestore-persistence`).
- O `Flow` é **cold**: começa ao primeiro `collect`, cancela com a
  coroutine. Nada de `Flow` hot retornado de Service.

### 2. Sharing strategy obrigatória no ViewModel

```kotlin
val state: StateFlow<StateUI<BonsaiListUI>> =
    observeBonsaiList()
        .map { it.toUI() }
        .map<BonsaiListUI, StateUI<BonsaiListUI>> { StateUI.Processed(it) }
        .catch { emit(StateUI.Error(it.toErrorUI())) }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = StateUI.Processing,
        )
```

Por quê `WhileSubscribed(5_000)`:

- Re-subscribe rápido (rotação de tela, navegação back/forward) **não**
  reabre a conexão Firestore — o listener segue vivo por 5s.
- Tela sem coletores por mais de 5s desconecta, parando billing/quota.
- `WhileSubscribed(0)` reabre conexão a cada navegação (custo).
- `SharingStarted.Eagerly` mantém listener aberto até a VM morrer
  (vazamento de read em telas raramente visitadas).

### 3. Lifecycle: cancelar com `viewModelScope`

- ViewModel coleta com `viewModelScope.launch { flow.collect { ... } }`
  **ou** mais comum: `stateIn(viewModelScope, ...)`.
- Listener Firestore registrado em `callbackFlow { ... awaitClose { reg.remove() } }`
  — `awaitClose` é obrigatório, sem ele o listener vaza ao cancelar.
- iOS: `for await` em SKIE-bridge cancela junto com a `Task`/`.task {}`.

### 4. Reconnection automática (sem código nosso)

O SDK Firestore reconecta sozinho após queda de rede: o `Flow` não
re-emite "loading", apenas pausa até voltar online. Não tentar implementar
retry/backoff manual em cima — duplica trabalho e gera double-emit.

Se a feature precisa indicar "offline" para a UI, consumir
`NetworkMonitor` (shim já fornecido por `firestore-persistence` /
`shared:core/platform/`) em paralelo, **não** inferir de ausência de
emissão do listener.

### 5. cache-and-network vs server-only

Default deste projeto: **cache-and-network** (Firestore SDK aplica
automaticamente). O Flow emite o snapshot cache imediato, depois o
servidor — UI mostra dado stale enquanto carrega.

Casos que exigem `Source.SERVER` (consistência forte, evitar stale):

- Telas pós-mutation onde a UX precisa do estado servidor confirmado.
- Listas com paginação por timestamp/cursor.

Declarar explicitamente no tech-spec quando server-only — silenciar é
ambiguidade.

### 6. Error handling em stream

```kotlin
fun observeBonsaiList(): Flow<List<Bonsai>> = callbackFlow {
    val reg = collection.addSnapshotListener { snapshot, error ->
        when {
            error != null -> close(error.toDomain())
            snapshot != null -> trySend(snapshot.toDomainList())
        }
    }
    awaitClose { reg.remove() }
}
```

Regras:

- Erro do listener → `close(throwable)` propaga via `Flow.catch` no
  consumer (ViewModel mapeia para `StateUI.Error`).
- **Não** swallow exceptions com `try/catch` dentro do `callbackFlow` —
  `Flow` precisa terminar para a UI saber que houve falha.
- Erros recuperáveis (queda de rede) → SDK reconecta, listener segue
  vivo. Erros não-recuperáveis (`PERMISSION_DENIED`, `NOT_FOUND`,
  `UNAUTHENTICATED`) terminam o `Flow`.

### 7. Latência esperada

| Operação | Latência típica |
|---|---|
| Primeira emissão (cache) | < 50ms |
| Primeira emissão (server, online) | 150-400ms |
| Update após write local | < 100ms (latency compensation do SDK) |
| Update vindo de outro device | 200-800ms (depende do region) |

Se a feature exige latência < 100ms ponta-a-ponta entre devices,
Firestore não é a ferramenta — abrir `open-question` no tech-spec.

---

## Contribuições deste card

### Templates

| Target artifact | Section | Merge |
|---|---|---|
| `tech-spec.md` | `Realtime Strategy — Firestore Listeners` | append-section |

### Agent prompts

| Agent | Extension-point |
|---|---|
| `contract-planner-agent` | `section:Data Contract` |
| `tech-spec-agent` | `section:Data layer` |
| `task-contract-writer` | `after:Allowed Files` |

### Config defaults

```yaml
conventions:
  realtime:
    stream:         firestore-listeners
    flow-strategy:  SharingStarted.WhileSubscribed(5000)
```

### Validators

Nenhum dedicado. Cobertura indireta via:

- `firestore-persistence` — valida path convention, DTO mapping, error
  taxonomy compartilhada.
- `firestore-security-rules` — valida cobertura de `read` (que serve
  tanto `get` quanto `addSnapshotListener`).

---

## Como este card interage com outros

| Outro card | Interação |
|---|---|
| `firestore-persistence` | **Hard dep** via `requires: persistence-server`. Reusa Service/Repository pattern, DTO↔domain mapping, sealed class de erro. Este card adiciona apenas o eixo realtime sobre os mesmos paths/coleções. |
| `firestore-security-rules` | Paralelo: rules de `allow read` valem para listeners também (não há rule separada de "subscribe"). Cobertura é responsabilidade do card de rules. |
| `koin-annotations` | `{Feature}Repository` permanece `@Single` (mesma instância expondo `get()` + `observe()`). |
| `kmp-shared` | `callbackFlow` + `awaitClose` em `commonMain`; iOS consome via SKIE como `AsyncSequence`. |
| `crashlytics` | Erros de listener mapeados para `FirestoreError` propagam para o handler comum de `firestore-persistence` — sem caminho dedicado. |

---

## Anti-patterns deste card

| Anti-pattern | Por quê |
|---|---|
| `callbackFlow` sem `awaitClose { registration.remove() }` | Listener vaza ao cancelar a coroutine — quota/billing crescem silenciosamente. |
| `SharingStarted.Eagerly` em ViewModel | Listener aberto enquanto a VM viver, mesmo sem UI observando. |
| `SharingStarted.WhileSubscribed(0)` | Re-subscribe instantâneo em rotação/navegação reabre conexão — desperdício. |
| Implementar retry/backoff manual em cima do listener | SDK já reconecta; manual gera double-emit e looping. |
| `try/catch` dentro do `callbackFlow` engolindo error | UI fica presa em Processing — sempre `close(error)` e deixar `Flow.catch` mapear. |
| Listener em Service expondo `Flow` hot (`MutableSharedFlow`) | Quebra o contrato cold; Service emite sob demanda do collector. |
| Inferir "offline" de ausência de emissão | Listener pausa mas não emite "offline" — consumir `NetworkMonitor` explicitamente. |
| Usar `addSnapshotListener` para leitura one-shot | Sempre `get()` (one-shot) — listener para isso vaza e custa extra. |

---

## Lifecycle

- **Install**: `forge init` (auto) ou `forge reconfigure` → "adicionar card".
  Requer `firestore-persistence` ativo (ou outro futuro provedor de
  `persistence-server`).
- **Update**: `forge reconfigure` → "atualizar card do canonical".
- **Remove**: possível se nenhum repositório ativo coleta `Flow` Firestore.
  Em v1.1, remover este card sem substituir por outro `realtime-stream`
  deixa a capability vazia.

Edição manual de qualquer arquivo deste card no snapshot
(`.claude/cards/firestore-realtime/`) é local. Para propagar mudanças,
edite o canonical em `~/Documents/feature-forge/cards/firestore-realtime/`
e re-instale via `forge reconfigure`.
