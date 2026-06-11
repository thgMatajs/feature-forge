# Card `firebase-storage`

> Categoria: `backend` · Maturidade: `stable` · Provê `file-storage`, `firebase-storage`

Firebase Cloud Storage como provedor canônico de **file-storage** para
binários (imagens, mídias) do projeto. Cobre o stack inteiro:

- Repository pattern em `commonMain` com upload exposto como
  `Flow<UploadProgress>`.
- Security rules (`storage.rules`) por feature com authorization path-based.
- Compressão de imagem em `Dispatchers.Default` antes do upload.
- Cache local de uploads pendentes para retry offline-first.
- Error mapping `StorageException → StorageError` (domain).
- Emulator local em `localhost:9199` (Storage emulator do Firebase Tools).

O card é **conflict-with `file-storage`**: ativar outro provedor (S3,
Supabase Storage, GCS direto) ao mesmo tempo é install-time error.

---

## O que este card declara

| Item | Valor |
|---|---|
| `provides` | `file-storage`, `firebase-storage` |
| `requires` | — (sem deps obrigatórias no resolver) |
| `conflicts-with` | `file-storage` (outros provedores) |
| `config-defaults` | `conventions.backend.file-storage: firebase-storage`, `conventions.observability.storage-rules-source: storage.rules` |
| Detecção (threshold 0.5) | `build.gradle*` contém `firebase-storage` (0.5) **OU** `storage.rules` existe (0.3) + `Package.swift`/`Podfile` contém `FirebaseStorage` (0.3 cada) |

---

## Quando este card ativa

`forge init` ativa automaticamente quando o repositório declara
`firebase-storage` em qualquer `build.gradle(.kts)` ou quando `storage.rules`
já existe combinado com o SDK iOS (SPM `FirebaseStorage` ou pod
`FirebaseStorage`).

Para projetos que ainda não consomem Storage, a detecção falha e o card
fica fora — a feature que introduzir o primeiro upload deve rodar
`forge reconfigure` → "adicionar card" → `firebase-storage`.

---

## Convenções deste projeto

### 1. Path convention (obrigatória)

```
{userId}/{collection}/{docId}/{filename}.{ext}
```

O **primeiro segmento sempre é `{userId}`** — security rules autorizam com
`request.auth.uid == userId`. Paths sem prefixo de uid não passam pelo
validator `check-storage-rules-coverage`.

Exemplos canônicos:

| Asset | Path |
|---|---|
| Foto principal de bonsai | `{uid}/bonsais/{bonsaiId}/main.jpg` |
| Galeria de bonsai | `{uid}/bonsais/{bonsaiId}/gallery/{photoId}.jpg` |
| Avatar de usuário | `{uid}/profile/avatar.jpg` |

### 2. Upload sempre via `Flow<UploadProgress>`

```kotlin
sealed class UploadProgress {
    data class InProgress(val bytesTransferred: Long, val totalBytes: Long) : UploadProgress()
    data class Completed(val downloadUrl: String) : UploadProgress()
    data class Failed(val cause: StorageError) : UploadProgress()
}
```

- ViewModel coleta `Flow` em `viewModelScope.launch { ... }` e mapeia para
  campo `uploadProgress: Float?` em `StateUI<T>` (sem Channel/SharedFlow).
- `Flow` é cold, cancelado com a coroutine.
- Delete/getURL one-shot → `suspend fun`, não `Flow`.

### 3. Compressão obrigatória para `image/*`

Toda imagem é comprimida em `Dispatchers.Default` **antes** do upload via
`ImageCompressor` (`expect/actual` em `shared:core/platform/`). Defaults:
1280px no maior lado, JPEG q=85.

Mídia que não é imagem (vídeo, áudio, PDF) **não** é comprimida client-side
— se necessário, fica explícito em `open-questions.md`.

### 4. Cache local para retry offline

Uploads pendentes vivem em DataStore/Room dedicado. Quando
`NetworkMonitor.online` emite `true`, o repository re-tenta com backoff
exponencial (max 3 tentativas). Falha definitiva → `crashlytics.recordException(...)`.

Features que **não** precisam offline retry declaram explicitamente
`offline-retry: not-applicable` no tech-spec — silenciar é ambiguidade.

### 5. Error mapping fechado

```
StorageException.ERROR_OBJECT_NOT_FOUND      → StorageError.NotFound
StorageException.ERROR_QUOTA_EXCEEDED        → StorageError.QuotaExceeded
StorageException.ERROR_UNAUTHENTICATED       → StorageError.AuthRequired
StorageException.ERROR_UNAUTHORIZED          → StorageError.PermissionDenied
StorageException.ERROR_RETRY_LIMIT_EXCEEDED  → StorageError.Network
StorageException.ERROR_BUCKET_NOT_FOUND      → StorageError.Misconfigured  + crashlytics
default                                       → StorageError.Unknown        + crashlytics
```

---

## Contribuições deste card

### Templates

| Target artifact | Section | Merge |
|---|---|---|
| `tech-spec.md` | `Storage Strategy (Firebase)` | append-section |
| `data-contract-spec.yaml` | `storage-paths` (top-level) | merge-keys |

### Validators

| Validator | Lifecycle | Severity |
|---|---|---|
| `check-storage-rules-coverage.py` | `verify-task`, `forge-doctor` | error (stub Phase 5) |

### Agent prompts

| Agent | Extension-point |
|---|---|
| `contract-planner-agent` | `section:Data Contract` |
| `tech-spec-agent` | `section:Data layer` |
| `task-contract-writer` | `after:Allowed Files` |

### Config defaults

```yaml
conventions:
  backend:
    file-storage: firebase-storage
  observability:
    storage-rules-source: storage.rules
```

---

## Dev environment

| Ambiente | Bucket | Notas |
|---|---|---|
| Dev (emulator) | `localhost:9199` | Iniciado por `scripts/firebase-emulator.sh` |
| Dev (Firebase real) | projeto `bonsai-meo-dev` | Preferível para QA próximo de produção |
| Prod | projeto `bonsai-meo` | Sem acesso direto durante desenvolvimento |

O service detecta build flavor `debug` e aponta para emulator via
`useEmulator("10.0.2.2", 9199)` (Android) ou `Storage.storage().useEmulator(...)` (iOS).
**Proibido** detectar runtime via comparação de hostname.

---

## Como este card interage com outros

| Outro card | Interação |
|---|---|
| `firebase-firestore` | Storage paths espelham hierarquia de coleções Firestore (`bonsais/{bonsaiId}` em ambos). Cleanup em cascata fica no repository, não em Cloud Function (default deste projeto). |
| `firebase-crashlytics` | `StorageError.Misconfigured` e `StorageError.Unknown` chamam `crashlytics.recordException(FirebaseStorageAnalyticsException(...))` — paridade com pattern de `FirebaseAuthAnalyticsException`. |
| `koin-annotations` | `{Feature}StorageService`/`{Feature}StorageRepositoryImpl` são `@Single`; UseCases são `@Factory`. |
| `kmp-shared` | `ImageCompressor` é `expect/actual` shim em `shared/core/platform/`. |

---

## Anti-patterns deste card

| Anti-pattern | Por quê |
|---|---|
| Path sem `{userId}` como primeiro segmento | Impossível autorizar com `request.auth.uid` em `storage.rules`. |
| Import de `com.google.firebase.storage.*` fora de `data/storage/` | ViewModel/UI nunca conhece SDK; quebra paridade iOS/Android. |
| Compressão de imagem dentro de `_uiState.update { ... }` | CPU-bound na Main → jank/ANR. Mover para `Dispatchers.Default`. |
| Upload exposto como `suspend fun` retornando `String` (URL) | Perde progress reporting; UI fica sem feedback. Usar `Flow<UploadProgress>`. |
| `useEmulator()` chamado em código de release | Quebra produção. Init guard com `isDebug` apenas. |
| Path literal hardcoded `"bonsais/abc/main.jpg"` | Burla path convention e validator. Sempre interpolar `{uid}/...`. |

---

## Lifecycle

- **Install**: `forge init` (auto) ou `forge reconfigure` → "adicionar card".
- **Update**: `forge reconfigure` → "atualizar card do canonical".
- **Remove**: só possível se nenhum outro card ativo requer `file-storage` /
  `firebase-storage` (raro — nenhum card v1 declara essa dep).

Edição manual de qualquer arquivo deste card no snapshot
(`.claude/cards/firebase-storage/`) é local. Para propagar mudanças,
edite o canonical em `~/Documents/feature-forge/cards/firebase-storage/` e
re-instale via `forge reconfigure`.
