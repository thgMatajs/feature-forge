<!--
  Fragment injetado no `contract-planner-agent` no extension-point
  `section:Data Contract`. Ativo quando o card `firebase-storage` está
  presente em workflow-config.yaml > cards.active.

  Objetivo: garantir que toda feature que toca binários produza um
  `storage-paths` block bem-formado em data-contract-spec.yaml.
-->

## Card contribution — `firebase-storage`

Quando a feature persiste imagens, vídeos ou qualquer binário em **Firebase
Cloud Storage**, o `data-contract-spec.yaml` precisa declarar um bloco
top-level `storage-paths` com **três** sub-seções obrigatórias.

### 1. Path convention (sempre `{userId}` first)

Path template fixo deste projeto:

```
{userId}/{collection}/{docId}/{filename}.{ext}
```

Para cada asset que a feature manipula, emita uma entrada em
`storage-paths.assets`:

```yaml
storage-paths:
  assets:
    - id:             bonsai-main-photo
      path-template:  "{uid}/bonsais/{bonsaiId}/main.jpg"
      content-type:   "image/jpeg"
      max-size-bytes: 5242880
      compression:
        max-dimension: 1280
        quality:       85
      rule-ref:       "storage.rules#bonsai-photos"
      operations:     [read, write, delete]
      crashlytics-on-failure: true
```

Regras invioláveis:

- **Primeiro segmento sempre é o uid do dono.** Paths como
  `bonsais/{bonsaiId}/main.jpg` (sem prefixo de uid) são rejeitados — não há
  como autorizar com `request.auth.uid` em `storage.rules`.
- **Nunca paths em namespace público compartilhado** (`public/`, `shared/`,
  `global/`). Conteúdo cross-user fica em coleção Firestore com URL pública
  assinada, não em path aberto.
- **`max-size-bytes` é obrigatório e cobrado por rule.** Default razoável
  para imagens: 5 MiB.

### 2. Security rules coverage

Toda operação declarada em `assets[].operations` precisa ter rule equivalente
em `storage.rules`. O bloco `storage-paths.rules-coverage` lista as
**required-constraints** que a rule de upload precisa exibir:

```yaml
storage-paths:
  rules-coverage:
    rules-file: "storage.rules"
    required-constraints:
      - "request.auth != null"
      - "request.auth.uid == userId"
      - "request.resource.size < {max-size-bytes}"
      - "request.resource.contentType.matches('{mime-prefix}/.*')"
```

Se alguma operation (`read`, `write`, `delete`) não estiver coberta no
rules file, deixe uma entrada em `open-questions.md` apontando o gap —
**não invente** a rule. O validator `check-storage-rules-coverage` bloqueia
o commit de qualquer forma.

### 3. Progress reporting design

Uploads expostos para a UI **sempre** via `Flow<UploadProgress>` com estados
`InProgress` / `Completed` / `Failed`. Documente na seção `domain-events` (ou
`storage-paths.assets[].progress-reporting`) que:

- O Flow é **cold** — começa ao primeiro collect e cancela com a coroutine.
- O ViewModel mapeia `InProgress` para um campo `uploadProgress: Float?` em
  `StateUI<UI>` (sem Channel, sem SharedFlow — é estado contínuo).
- `Failed` enriquece `StateUI.Error` com `StorageError` (sealed class
  domain — ver tech-spec contribution deste card).

### Pegadinhas a flagar em `open-questions.md`

- Asset sem `max-size-bytes`? → pergunte o limite.
- Asset acessível por múltiplos uids (ex.: foto compartilhada de bonsai)? →
  pergunte se vai por Storage path ou por Firestore + signed URL.
- Compressão pré-upload obrigatória ou opt-in? → default é obrigatória
  para `image/*`; confirmar se mídia é foto, gif animado, ou vídeo (vídeo
  não é comprimido client-side).
- Retention / cleanup quando o doc Firestore correspondente é deletado? →
  rule de Cloud Function ou cleanup manual? Geralmente cleanup manual no
  repository (`delete` em cascata).
