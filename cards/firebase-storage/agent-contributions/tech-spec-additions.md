<!--
  Fragment injetado no `tech-spec-agent` no extension-point
  `section:Data layer`. Ativo quando o card `firebase-storage` está
  presente em workflow-config.yaml > cards.active.

  Objetivo: forçar tech-spec.md a descrever Repository pattern + Flow de
  progress + cache local + compression + error mapping de forma uniforme
  entre features que persistem binários.
-->

## Card contribution — `firebase-storage` (Data layer)

A feature usa Firebase Cloud Storage para binários. O tech-spec precisa
descrever explicitamente os **cinco pilares** abaixo. Nada é opcional.

### 1. Repository pattern

```
domain/      {Feature}StorageRepository (interface) — assinatura única para iOS/Android
data/repo/   {Feature}StorageRepositoryImpl         — orquestra Service + compression + cache
data/svc/    {Feature}StorageService                — SDK Firebase wrapper, sem regra de negócio
```

O ViewModel **nunca** importa `com.google.firebase.storage.*` (Android) nem
`FirebaseStorage` (Swift). Toda interação passa pela interface em `domain/`.

### 2. Upload com `Flow<UploadProgress>`

```kotlin
interface BonsaiStorageRepository {
    fun uploadMainPhoto(
        bonsaiId: String,
        bytes: ByteArray,
    ): Flow<UploadProgress>

    suspend fun deleteMainPhoto(bonsaiId: String): Result<Unit>
}

sealed class UploadProgress {
    data class InProgress(val bytesTransferred: Long, val totalBytes: Long) : UploadProgress()
    data class Completed(val downloadUrl: String) : UploadProgress()
    data class Failed(val cause: StorageError) : UploadProgress()
}
```

Regras:

- Upload (stream contínuo) → `Flow`. Delete/getURL (one-shot) → `suspend fun`.
- `Flow` é cold, cancelado com a coroutine — `viewModelScope.launch { upload(...).collect { ... } }`.
- ViewModel mapeia para `StateUI<T>` com campo `uploadProgress: Float?`.

### 3. Image compression antes do upload

Toda imagem é comprimida em `Dispatchers.Default` antes de subir:

```kotlin
class BonsaiStorageRepositoryImpl(
    private val service: BonsaiStorageService,
    private val imageCompressor: ImageCompressor,
    private val cache: PendingUploadCache,
    private val dispatchers: AppDispatchers,
) : BonsaiStorageRepository {

    override fun uploadMainPhoto(bonsaiId: String, bytes: ByteArray): Flow<UploadProgress> = flow {
        val compressed = withContext(dispatchers.default) {
            imageCompressor.compress(bytes, maxDimension = 1280, quality = 85)
        }
        service.upload(path = "$uid/bonsais/$bonsaiId/main.jpg", bytes = compressed)
            .map { state -> mapToUploadProgress(state) }
            .collect { emit(it) }
    }.flowOn(dispatchers.io)
}
```

`ImageCompressor` é `expect/actual` shim — Android usa `BitmapFactory`,
iOS usa `UIImage.jpegData(...)`. Nunca rodar compressão na Main.

### 4. Cache local de uploads pendentes (offline-first)

Se a UX exige retry automático quando volta ao online:

- Persistir intent de upload (`bonsaiId`, `bytes` ref, `path-template`,
  `attempts`) em DataStore ou tabela Room dedicada.
- `NetworkMonitor.online` → re-tenta uploads em fila.
- Limite de tentativas: 3, backoff exponencial.
- Falha definitiva → `crashlytics.recordException(StorageUploadFailedException(...))`.

Se a feature **não** precisa offline retry, declarar explicitamente no
tech-spec (`offline-retry: not-applicable` na seção storage) — não silenciar.

### 5. Error mapping (Firebase → domain)

`{Feature}StorageRepositoryImpl` traduz `StorageException` para sealed class
domain:

```kotlin
sealed class StorageError {
    data object NotFound          : StorageError()
    data object QuotaExceeded     : StorageError()
    data object AuthRequired      : StorageError()
    data object PermissionDenied  : StorageError()
    data object Network           : StorageError()
    data class  Misconfigured(val code: String) : StorageError()
    data class  Unknown(val code: String, val causeType: String) : StorageError()
}
```

`Misconfigured` e `Unknown` chamam
`Firebase.crashlytics.recordException(FirebaseStorageAnalyticsException(...))`
com `errorCode + causeType` (mesmo pattern do card `firebase-crashlytics`, se ativo).

### 6. Threading checklist

- Service chama SDK dentro de `withContext(dispatchers.io)` — sem confiar
  que o SDK troca de thread.
- Compressão de imagem → `Dispatchers.Default`.
- Atualização de `_uiState.update { ... }` → Main (default do `viewModelScope`).
- NUNCA `runBlocking` aguardando upload finalizar.

### 7. Emulator + dev environment

O service detecta build flavor e aponta para emulator em `localhost:9199`:

```kotlin
class BonsaiStorageServiceImpl(
    private val isDebug: Boolean,
) : BonsaiStorageService {
    init {
        if (isDebug) {
            FirebaseStorage.getInstance().useEmulator("10.0.2.2", 9199) // Android
            // iOS equivalente em iosMain
        }
    }
}
```

Tech-spec deve declarar o flag (`isDebug`, `BuildConfig.DEBUG`, etc.) e
**proibir** detecção em runtime via comparação de bundle id ou hostname.

### 8. Test plan summary (delta)

- `{Feature}StorageServiceFake` em `commonTest` — emite `Flow<UploadState>`
  pré-programado (`InProgress(0,100) → InProgress(50,100) → Completed(...)`).
- Teste de repository cobre **todos** os `StorageException.code → StorageError`
  mapeados acima.
- Compression: teste isolado garantindo `ByteArray` output respeita
  `maxDimension` e `quality`.
- Rules: suite de emulator-side tests em `storage.rules` com matriz
  allow/deny por uid e content-type.
