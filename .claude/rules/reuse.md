# Reuso — antes de criar, consulte

Mandamento #3. feature-forge tem 17 graph queries canônicas pra detectar
duplicação ANTES dela existir.

## Antes de criar helper/função/template/card/validator

### 1. Consulta o graph

```bash
# Reusable helpers existentes
forge graph query Q11

# Reuse intelligence (6 categorias)
forge graph query Q12  # consolidate-within-module
forge graph query Q13  # promote-to-shared
forge graph query Q14  # redundant-platform
forge graph query Q15  # near-duplicate
forge graph query Q16  # kmp-migration-candidate
forge graph query Q17  # consolidate-ts-helpers
```

Se graph diz "já existe X em <path>" → usa o existente. Se diz
"near-duplicate" → 3-caminhos (consolidar / promover pra shared / criar
nova com justificativa explícita).

### 2. Grep como fallback

Graph pode estar stale (rebuild via `forge reconfigure → graph`):

```bash
grep -rn "def <conceito>\|fun <conceito>\|fn <conceito>" engine/ validators/
grep -rn "<conceito>" templates/ cards/ presets/
```

### 3. Inventory pra UI/strings

Antes de pedir UI component novo ou i18n string nova:

```bash
# DS components + i18n + conventions extraídos do projeto
ls engine/inventory/
cat engine/inventory/design-system.yaml 2>/dev/null | head
cat engine/inventory/i18n.yaml 2>/dev/null | head
```

## Quando graph diz "near-duplicate"

Não escreva ainda. Abre o candidato, avalia 3-caminhos:

1. **Usar o existente** — talvez já cobre 90% e diff de 10% é parametrização
2. **Promover pra shared** — se uso vai ser cross-module, mexe em
   `engine/inventory/conventions.yaml` ou KMP shared layer
3. **Criar nova com justificativa** — quando semântica é genuinamente
   diferente; documenta no commit body por que NÃO consolida

Caminho C exige justificativa no commit — graph vai re-detectar near-dup
na próxima execução, então o "por que" precisa estar no histórico.

## Templates e cards

```bash
ls templates/   # 18 canônicos em v1.1
ls cards/       # 20 canônicos em v1.1
ls presets/     # kmp-mobile + ...
```

Antes de criar template novo:
- Verifica se existe template similar em `templates/`
- Consulta `docs/design/02-phases.md` pra ver se nova phase aparece
- Se card novo: confere `docs/schemas/card.md` (schema)

## Validators

Antes de criar validator novo: `ls validators/` (14 em v1.1).
Sobreposição comum:
- `check_files_in_allowed_files.py` — escopo
- `check_no_invented_behavior.py` — analytics + behavior
- `check_no_behavior_change.py` — refactor

Se semantically novo: prosseguir, mas referenciar em
`docs/design/07-discipline.md §2` se policy mudou.

## Pointer canônico

Detalhe profundo: `docs/lifecycle/memory-and-graph.md`.
