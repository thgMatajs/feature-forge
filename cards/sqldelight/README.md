# Card — `sqldelight`

> SQLDelight para persistência SQL KMP-native (Android + iOS via shared).
> Card backend-axis `persistence` introduzido em DET-6 W6 (fecha o gap
> `(persistence, kmp)` registrado em W6.1 das starter bundles); identidade
> canônica vem do cell `backend.persistence.<platform>` em
> `workflow-config.yaml`.

- **Categoria (axis):** `persistence`
- **Platforms:** `android`, `ios`, `kmp`
- **Maturity:** `stable`
- **Provides:** _vazio_ (backend-axis — cell-anchored, ver
  [`docs/schemas/backend-axes.md`](../../docs/schemas/backend-axes.md))
- **Requires:** _nenhum_
- **Conflicts-with:** _nenhum_ (cardinalidade enforçada pelo schema do
  `backend.persistence.<platform>` cell)

## Quando este card é ativado

`forge init` ativa `sqldelight` quando a soma de confidence dos signals
abaixo é ≥ `0.5`:

| Sinal | Confidence | Por quê |
|---|---|---|
| `gradle-dep app.cash.sqldelight:runtime` | 0.5 | Coordenada Maven do runtime (consumida em todos os targets KMP). |
| `gradle-dep app.cash.sqldelight:android-driver` | 0.3 | Driver Android-specific — sinaliza uso, mas isolado não confirma KMP ativo. |
| `gradle-dep app.cash.sqldelight:native-driver` | 0.3 | Driver iOS/native — pareado com Android em projetos KMP cross-platform. |
| `app.cash.sqldelight` em `**/*.gradle.kts` | 0.3 | Plugin Gradle aplicado — confirma configuração ativa (block `sqldelight { }` esperado). |

Threshold 0.5 — runtime dispara sozinho, OU dois sinais secundários
compõem (drivers + plugin).

## O que este card contribui

- Fragmento de tech-spec em `templates/sqldelight-tech-spec.md` —
  documenta `*.sq` schema files, drivers per-platform, query DSL,
  migrations, e integração com coroutines.

## Integração com outros cards

| Combina com | Efeito |
|---|---|
| `room-database` | Estratégia híbrida: Room em Android (já consolidado), SQLDelight em commonMain. Cells separadas — sem conflito direto. |
| `datastore-prefs` | Preferences cobrem KV simples; SQLDelight cobre dados relacionais. Concerns ortogonais. |
| `kmp-shared` | SQLDelight vive em commonMain do módulo shared — declaração `.sq` files acessível a Android e iOS via expect/actual driver. |

## Limites declarados

- Este card cobre SQLDelight (cash.app/sqldelight) exclusivamente —
  outras opções KMP-SQL (ex.: Multiplatform Settings com backing SQL)
  vivem em cards próprios se entrarem no catalog.
- Schema definitions ficam em `*.sq` files (não YAML/JSON) — o template
  de tech-spec referencia a convenção, mas o composer não gera os
  `*.sq` automaticamente.
- iOS driver (`native-driver`) exige linkagem com `sqlite3` do sistema —
  responsabilidade do projeto consumidor configurar `linker.flags`
  quando aplicável.
