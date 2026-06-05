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

## Infra reusável de validators (Phase 0 — v1.2-dev+)

Quando criar novo validator (gate), consulte PRIMEIRO esses módulos antes
de criar helper novo:

- `validators/_gate_infra.py`
  - `DispatchResult` dataclass — outcome de subprocess dispatch
  - `check_tool_available(tool)` — shutil.which wrapper
  - `dispatch_native_tool(*, language, files, cmd_builder, config_template, placeholders, ...)` — generic CLI tool dispatcher
  - `render_config_with_placeholders(template, placeholders)` — tempfile-render pattern
  - `parse_overrides(body, *, prefix, key_pattern, return_warnings)` — `<PREFIX>-OVERRIDE` regex parser generalizado
  - `apply_overrides(fails, body, *, prefix, key_pattern, fail_key_extractor, override_key_fields)` — split fails/silenced/warnings
- `validators/_diff.py`
  - `DiffHunk` dataclass
  - `classify_range_against_hunks(range, hunks)` — "new" | "modified" | "unchanged"
  - `extract_diff_hunks(project_root, files)` — parse git diff hunks
  - `git_staged_files(project_root, extensions)` — staged files filtrado por suffix
  - `read_commit_body(project_root)` — git log -1 --format=%B
- `validators/_common.py`
  - `gate_threshold_lookup(language, active_cards, workflow_config)` — precedência card > workflow > defaults
  - `format_three_paths_message(violations, thresholds_by_lang)` — render canônico 3-caminhos
  - `result_pass / result_fail / result_warn` — return shapes padronizadas

**Compor é preferível a copiar.** Se houver near-duplicate detectado em outro
validator (via `forge graph` Q11/Q12/Q15), promova ao módulo compartilhado
em vez de criar versão paralela.

Exemplo de composição (CC gate pós-Phase 0):

```python
from pathlib import Path
from typing import Optional

from validators._gate_infra import dispatch_native_tool, apply_overrides
from validators._diff import git_staged_files, extract_diff_hunks
from validators._common import gate_threshold_lookup, format_three_paths_message

# cmd_builder é invocado posicionalmente por dispatch_native_tool:
#   cmd_builder(tool_bin, files, rendered_config)
# Declarar kw-only (*, ...) estoura TypeError em runtime.
def _build_my_tool_cmd(
    tool_bin: str, files: list[str], rendered_config: Optional[str]
) -> list[str]:
    return [tool_bin, "--config", str(rendered_config), *files]

def validate(project_root: Path, **kwargs):
    files = [str(p) for p in git_staged_files(project_root, extensions={".kt", ".swift"})]
    hunks = extract_diff_hunks(project_root, files)
    threshold = gate_threshold_lookup("kotlin", cards, wf_config)
    result = dispatch_native_tool(
        language="kotlin",
        files=files,
        cmd_builder=_build_my_tool_cmd,
        project_root=project_root,
        tool_bin="my-tool",
        config_template=MY_TOOL_CONFIG,
        placeholders={"__THRESHOLD__": str(threshold)},
    )
    # ... process result, apply overrides, etc.
```

## Pointer canônico

Detalhe profundo: `docs/lifecycle/memory-and-graph.md`.
