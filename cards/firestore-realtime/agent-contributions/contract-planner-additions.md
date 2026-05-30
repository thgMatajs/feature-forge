<!--
  Fragment injetado no `contract-planner-agent` no extension-point
  `section:Data Contract`. Ativo quando o card `firestore-realtime` está
  presente em workflow-config.yaml > cards.active.

  Objetivo: forçar declarações explícitas de `realtime: true` no
  data-contract-spec.yaml com campos observados, frequência esperada
  e error handling em stream.
-->

## Card contribution — `firestore-realtime`

Quando a feature consome Firestore em tempo real (listeners /
`Flow<T>`), o `data-contract-spec.yaml` precisa marcar **explicitamente**
cada operação observável e declarar três blocos auxiliares: campos
observados, frequência esperada e error handling.

Este card complementa `firestore-persistence` — paths, DTOs e
authorization vêm de lá. Aqui descrevemos só o eixo realtime.

### 1. Marcar operações como `realtime: true`

```yaml
firestore-collections:
  - id:          bonsai-list
    path:        "{uid}/bonsais"
    document:    BonsaiResponse
    operations:
      - id:           observe-list
        kind:         observe
        realtime:     true
        cardinality:  collection
        source:       cache-and-network   # ou: server
        sharing:      WhileSubscribed(5000)

      - id:           get-one
        kind:         get
        realtime:     false               # one-shot — pertence a firestore-persistence
        cardinality:  document
```

Regras invioláveis:

- `kind: observe` SEMPRE acompanha `realtime: true`. Combinação
  `observe` + `realtime: false` é erro de design (deve virar `get`).
- `kind: get/create/update/delete` SEMPRE `realtime: false` — listeners
  para one-shot é vazamento.
- `cardinality` ∈ `{document, collection}` — afeta forma do `Flow`
  (`Flow<T?>` vs `Flow<List<T>>`).

### 2. Campos observados (`observed-fields`)

Para cada operação realtime, declarar quais campos a UI realmente
consome — isso ajuda a justificar billing e a desenhar `select()` /
query optimization futura.

```yaml
operations:
  - id:           observe-list
    kind:         observe
    realtime:     true
    observed-fields:
      - bonsaiId
      - species
      - mainPhotoUrl
      - lastWateredAt
    excluded-fields:
      - createdAt          # não exibido na lista
      - notes              # carregado apenas no detail
```

Campos não observados podem ser carregados via `get()` no detail
(reduz payload do listener). Se a lista exibe **todos** os campos,
omitir `excluded-fields` é OK.

### 3. Frequência esperada (`expected-update-frequency`)

```yaml
operations:
  - id:           observe-list
    expected-update-frequency: low      # low | medium | high | spike
    rationale: "Usuário típico edita um bonsai a cada poucos dias; lista atualiza < 5x/sessão."
```

| Frequência | Definição | Implicação |
|---|---|---|
| `low` | < 10 updates/sessão | OK com `WhileSubscribed(5000)` |
| `medium` | 10-100 updates/sessão | Avaliar throttling no ViewModel (`debounce`/`sample`) |
| `high` | > 100 updates/sessão ou múltiplas/segundo | Considerar paginação ou backend agregador |
| `spike` | Burst ocasional (ex.: live event) | Listener apenas durante a janela; fechar manualmente |

Frequência `high` ou `spike` exige `open-question` confirmando que
Firestore é adequado — alternativas: Realtime Database, agregação no
servidor, WebSocket dedicado (v1.1).

### 4. Error handling em stream

```yaml
operations:
  - id:           observe-list
    error-handling:
      on-permission-denied:   "terminate-flow + navigate-login"
      on-unauthenticated:     "terminate-flow + navigate-login"
      on-not-found:           "emit-null"            # apenas para cardinality: document
      on-failed-precondition: "terminate-flow + crashlytics"
      on-unavailable:         "no-op (SDK reconnects)"
      on-deadline-exceeded:   "no-op (SDK reconnects)"
      on-unknown:             "terminate-flow + crashlytics"
```

Regras:

- Erros recuperáveis (`UNAVAILABLE`, `DEADLINE_EXCEEDED`) **nunca**
  terminam o Flow nem chamam crashlytics — o SDK reconecta sozinho.
- Erros não-recuperáveis terminam o Flow → ViewModel mapeia para
  `StateUI.Error`.
- `FAILED_PRECONDITION` geralmente significa índice composto faltando
  — crashlytics obrigatório para evitar silêncio em produção.

### 5. Offline behavior (`offline-mode`)

```yaml
operations:
  - id:           observe-list
    offline-mode:
      cache-emit-on-open:  true     # padrão do SDK; declarar explicitamente
      pause-on-offline:    true     # Flow pausa, não termina
      indicate-to-ui:      "via NetworkMonitor combine"
```

Se a feature exige indicação visual de "offline", o tech-spec descreve
como combinar `NetworkMonitor.online` com o `Flow` realtime via
`combine(...)`. **Não** inferir offline de ausência de emissão.

### Pegadinhas a flagar em `open-questions.md`

- `kind: observe` com `realtime: false` → erro de design; perguntar
  intenção real.
- `expected-update-frequency: high` ou `spike` → confirmar adequação
  do Firestore.
- Operação `observe` sem `observed-fields` declarados → sugerir
  enumerar campos para reduzir payload.
- Tela com 3+ listeners simultâneos no mesmo screen → propor
  consolidar em query composta ou agregação backend.
- Listener em coleção sem filtro por uid → revisar; quase sempre
  quebra rules e é desperdício de billing.
