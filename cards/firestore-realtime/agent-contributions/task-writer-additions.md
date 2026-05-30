<!--
  Fragment injetado no `task-contract-writer` no extension-point
  `after:Allowed Files`. Ativo quando o card `firestore-realtime` está
  presente em workflow-config.yaml > cards.active.

  Objetivo: garantir que toda task que toque listeners Firestore liste
  patterns concretos de Repository realtime, force awaitClose, declare
  sharing strategy e proíba retry manual sobre o listener.
-->

## Card contribution — `firestore-realtime` (Task allowed_files + gates)

Quando uma task envolve `addSnapshotListener` / `.snapshots()` /
`Flow<T>` Firestore, o `task-contract.yaml` deve obedecer o template
abaixo. Este card complementa `firestore-persistence` — patterns base
de Service/Repository/UseCase vêm de lá; aqui adicionamos os patterns
realtime.

### Allowed files (patterns concretos)

Anexe os patterns abaixo ao `task.allowed_files`. Liste paths
**concretos**, não wildcards — a task só pode tocar o que está listado.

```yaml
task:
  allowed_files:
    # Repository expondo Flow (realtime) — pode ser o mesmo Repository
    # de firestore-persistence, agora com novos métodos observe*()
    - "shared/feature/{name}/src/commonMain/kotlin/.../data/repository/{Feature}RepositoryImpl.kt"
    - "shared/feature/{name}/src/commonMain/kotlin/.../domain/repository/{Feature}Repository.kt"

    # Service com callbackFlow envolvendo addSnapshotListener
    - "shared/feature/{name}/src/commonMain/kotlin/.../data/service/{Feature}Service.kt"
    - "shared/feature/{name}/src/commonMain/kotlin/.../data/service/{Feature}ServiceImpl.kt"

    # Use cases que retornam Flow
    - "shared/feature/{name}/src/commonMain/kotlin/.../domain/usecase/Observe{Entity}UseCase.kt"
    - "shared/feature/{name}/src/commonMain/kotlin/.../domain/usecase/Observe{Entity}ListUseCase.kt"

    # ViewModel consumindo Flow com stateIn(WhileSubscribed)
    - "androidApp/feature/{name}/src/main/kotlin/.../{Feature}{Screen}ViewModel.kt"

    # Testes
    - "shared/feature/{name}/src/commonTest/kotlin/.../data/service/{Feature}ServiceFake.kt"
    - "shared/feature/{name}/src/commonTest/kotlin/.../data/repository/{Feature}RepositoryImplObserveTest.kt"
    - "shared/feature/{name}/src/commonTest/kotlin/.../presentation/{Feature}{Screen}ViewModelObserveTest.kt"
```

### Forbidden patterns

```yaml
task:
  forbidden_patterns:
    - description: "callbackFlow sem awaitClose — listener vaza."
      match-glob: "**/src/commonMain/**/*.kt"
      regex-must-contain-if-present:
        if-regex:   "callbackFlow\\s*\\{"
        then-regex: "awaitClose\\s*\\{[^}]*\\.remove\\(\\)"
      severity: error

    - description: "Listener Firestore exposto como Flow hot (MutableSharedFlow) em Service."
      match-glob: "**/src/commonMain/**/data/service/**/*.kt"
      regex-must-not-contain: "MutableSharedFlow<"

    - description: "stateIn sem started ou com Eagerly por padrão (sem justificativa em comentário)."
      match-glob: "**/src/commonMain/**/presentation/**/*.kt"
      regex-must-not-contain: "stateIn\\([^)]*started\\s*=\\s*SharingStarted\\.Eagerly"
      exceptions:
        - "**/{Feature}NotificationViewModel.kt"  # documentar caso a caso

    - description: "Retry/backoff manual em cima do listener — SDK já reconecta."
      match-glob: "**/src/commonMain/**/data/**/*.kt"
      regex-must-not-contain: "(retry|retryWhen|exponentialBackoff).*addSnapshotListener"

    - description: "Import direto do SDK Firestore fora de data/service/ (igual a firestore-persistence)."
      match-glob: "**/src/{commonMain,androidMain,iosMain}/**/*.kt"
      regex-must-not-contain: "com\\.google\\.firebase\\.firestore"
      exceptions:
        - "**/data/service/**"

    - description: "Usar addSnapshotListener para leitura one-shot (vaza + custa extra)."
      match-glob: "**/src/commonMain/**/data/service/**/*.kt"
      regex-must-not-contain: "addSnapshotListener.*\\.take\\(1\\)"
```

### Validations (gates)

Este card **não** contribui validators próprios — cobertura indireta
via cards adjacentes:

```yaml
task:
  validations:
    # Herdadas de firestore-persistence
    - id:       firestore-paths-coverage
      command:  "python3 .claude/cards/firestore-persistence/validators/check-firestore-paths.py --feature {name}"
      runs-on:  [verify-task]
      severity: error

    # Herdadas de firestore-security-rules — read rule cobre listener também
    - id:       firestore-rules-coverage
      command:  "python3 .claude/cards/firestore-security-rules/validators/check-firestore-rules.py --feature {name}"
      runs-on:  [verify-task]
      severity: error
```

### Task categories (sugestão de breakdown)

| Categoria | Quando criar | Exemplo |
|---|---|---|
| `realtime-service`    | Adicionar método `observe*()` no Service via `callbackFlow` | `T-NNN — BonsaiService.observeCollection() + Fake` |
| `realtime-repository` | Repository expondo `Flow<T>` com mapping DTO→domain | `T-NNN — BonsaiRepositoryImpl.observeBonsaiList()` |
| `realtime-usecase`    | UseCase `Observe{Entity}UseCase` retornando `Flow` | `T-NNN — ObserveBonsaiListUseCase` |
| `realtime-vm-stateIn` | ViewModel consumindo Flow com `stateIn(WhileSubscribed(5000))` | `T-NNN — BonsaiListViewModel realtime wiring` |

Cada categoria vira uma task separada — Service e ViewModel são
contratos diferentes (fake vs Turbine test).

### Gates obrigatórios

```yaml
task:
  gates:
    - firestore-paths-coverage     # error — herdado de firestore-persistence
    - firestore-rules-coverage     # error — herdado de firestore-security-rules
    - validate-koin-modules        # se o card koin-annotations também ativo
    - detekt                       # shared/**/*.kt
    - swift-style                  # se a task tocar iosApp/**
```

### Checklist antes de marcar a task como done

- [ ] `callbackFlow` contém `awaitClose { registration.remove() }`.
- [ ] ViewModel usa `stateIn(viewModelScope, WhileSubscribed(5_000), Processing)`
      (ou justifica diferente em comentário top-of-file).
- [ ] Service mapeia erro Firestore → `close(throwable)`, nunca
      `try/catch` engolindo.
- [ ] Repository aplica `.flowOn(dispatchers.default)` para mapping
      DTO→domain.
- [ ] Test Service Fake expõe `MutableSharedFlow` controlado pelo teste.
- [ ] Test ViewModel cobre transição Processing → Processed →
      re-Processed (segunda emissão) → Error.
- [ ] Sem `Source.SERVER` em `addSnapshotListener` (listeners são sempre
      cache-and-network por design do SDK).
