<!--
  Template fragment contribuído pelo card `firebase-storage`.
  Merge mode: append-section em tech-spec.md sob "Storage Strategy (Firebase)".

  O agente tech-spec-agent inclui este conteúdo quando o card está ativo.
  Edição manual deste arquivo é mudança de canonical — propague via
  `forge reconfigure` → "atualizar card do canonical".
-->

## Storage Strategy (Firebase)

A feature persiste binários (imagens, mídias) em **Firebase Cloud Storage**.
O acesso é mediado por um `{Feature}StorageRepository` em `commonMain` que
expõe upload/download como `Flow<UploadProgress>` / `suspend fun` — nunca
expõe a API nativa de Storage para a UI.

### Layered design (camadas)

| Camada | Tipo | Responsabilidade |
|---|---|---|
| `data/storage/` | `{Feature}StorageService` | Wrapper fino em torno do SDK Firebase Storage. Aceita `ByteArray` + path, retorna `Flow<UploadState>` ou `suspend ByteArray`. Sem regras de negócio. |
| `data/repository/` | `{Feature}StorageRepositoryImpl` | Aplica path convention (ver abaixo), compressão de imagem pré-upload, mapeamento `StorageException → domain error`. Cacheia metadata se necessário. |
| `domain/` | `{Feature}StorageRepository` (interface) | Contrato consumido por UseCases. Expõe `Flow<UploadProgress>` para progress reporting. |
| `domain/usecase/` | `Upload{Asset}UseCase`, `Get{Asset}UseCase` | Single-shot vs stream — ver `kotlin-idioms.md` §Flow vs Suspend. |

### Path convention (obrigatório)

Todo path de Storage segue o pattern:

```
{userId}/{collection}/{docId}/{filename}.{ext}
```

Exemplos:

| Asset | Path |
|---|---|
| Foto de bonsai (primária) | `{uid}/bonsais/{bonsaiId}/main.jpg` |
| Galeria de bonsai | `{uid}/bonsais/{bonsaiId}/gallery/{photoId}.jpg` |
| Avatar de usuário | `{uid}/profile/avatar.jpg` |

Regra: **`{userId}` é sempre o primeiro segmento** — security rules dependem
disso para autorização (`request.auth.uid == path[0]`). Paths que não sigam
o pattern são rejeitados pelo validator `check-storage-rules-coverage`.

### Security rules (`storage.rules`)

Toda escrita coberta pela feature precisa de match em `storage.rules`:

```
service firebase.storage {
  match /b/{bucket}/o {
    match /{userId}/bonsais/{bonsaiId}/{allPaths=**} {
      allow read:  if request.auth != null && request.auth.uid == userId;
      allow write: if request.auth != null
                   && request.auth.uid == userId
                   && request.resource.size < 5 * 1024 * 1024
                   && request.resource.contentType.matches('image/.*');
    }
  }
}
```

Constraints obrigatórias em toda rule de upload:
- `request.auth.uid == userId` (path-based authorization).
- `request.resource.size < {limit}` (default 5 MiB para imagens).
- `request.resource.contentType.matches('{mime}.*')` (default `image/*`).

### Upload com progress (`Flow<UploadProgress>`)

```kotlin
sealed class UploadProgress {
    data class InProgress(val bytesTransferred: Long, val totalBytes: Long) : UploadProgress() {
        val percent: Float = if (totalBytes > 0) bytesTransferred.toFloat() / totalBytes else 0f
    }
    data class Completed(val downloadUrl: String) : UploadProgress()
    data class Failed(val cause: StorageError) : UploadProgress()
}
```

O ViewModel consome esse `Flow` e atualiza `StateUI<T>` com campo
`uploadProgress: Float?` — não usa Channel/SharedFlow para progress (é
estado contínuo, não evento one-shot).

### Image compression (pré-upload)

Imagens grandes são comprimidas **antes** do upload, em `Dispatchers.Default`,
nunca na Main. Limite default: 1280px no maior lado, JPEG q=85. A compressão
é responsabilidade do `*StorageRepositoryImpl`, não do ViewModel.

### Cache local de uploads pendentes

Se a feature precisa retry de uploads (offline → online), persistir intent
de upload em `shared:core/cache/` ou DataStore — não em Storage. A
`StorageRepositoryImpl` re-tenta a partir do cache local quando
`NetworkMonitor` reporta online.

### Error mapping

| Firebase `StorageException` code | Domain error |
|---|---|
| `ERROR_OBJECT_NOT_FOUND` | `StorageError.NotFound` |
| `ERROR_BUCKET_NOT_FOUND` | `StorageError.Misconfigured` (crashlytics record) |
| `ERROR_QUOTA_EXCEEDED` | `StorageError.QuotaExceeded` |
| `ERROR_UNAUTHENTICATED` | `StorageError.AuthRequired` |
| `ERROR_UNAUTHORIZED` | `StorageError.PermissionDenied` |
| `ERROR_RETRY_LIMIT_EXCEEDED` | `StorageError.Network` |
| default | `StorageError.Unknown` (crashlytics record com `code` + `causeType`) |

### Threading

- Service `suspend fun upload(...)` envolve `withContext(io)` antes de chamar SDK.
- Compressão de imagem → `withContext(default)`.
- Atualização de `StateFlow<UploadProgress>` → Main (`viewModelScope`).
- NUNCA `runBlocking` para aguardar upload — `Flow` cancela com a coroutine.

### Emulator

O emulator local roda em `localhost:9199` (ver `scripts/firebase-emulator.sh`).
O service detecta build flavor `debug` e aponta para emulator via
`FirebaseStorage.useEmulator("10.0.2.2", 9199)` no Android e
`Storage.storage().useEmulator(...)` no iOS.

### Testes

- Service: fake `{Feature}StorageService` em `commonTest` com `Flow` emitindo
  estados em sequência (`InProgress(0,100) → InProgress(50,100) → Completed(...)`).
- Repository: testa mapeamento `StorageException → StorageError` para cada code.
- Rules: emulator + suite de unit tests em `storage.rules` (allow/deny matrix).
