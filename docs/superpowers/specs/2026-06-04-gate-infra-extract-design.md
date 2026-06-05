# Gate Infrastructure Extraction — Design Spec (Phase 0)

> Data: 2026-06-04 · Status: aprovado (brainstorm via AskUserQuestion)
> Branch: `worktree-feat+gate-infra-extract` (de `origin/main` pós PR #4)
> Voz: mentor calmo · Escopo: refactor sem mudança de comportamento

## Sumário executivo

PR #4 fechou o CC gate (`check_cyclomatic_complexity.py`, ~1127 LOC)
codificando um padrão que o resto do roadmap de quality gates (R1/R2/R3
no plan aprovado em `/Users/thg.inchurch/.claude/plans/wobbly-greeting-barto.md`)
vai reusar: 1 validator Python dispatcha tools nativas via subprocess,
respeita a cascade fail-fast (Decision 23), não importa nada de outras
skills (Decision 22), emite 3-caminhos canônico on-fail, aceita
override-justify auditável no commit body. O padrão é bom; o copy-paste
para os próximos 7 gates não. Mandamento #3 e `.claude/rules/reuse.md`
mandam consolidar a infra ANTES de criar gates novos — senão débito
explode em todas as ondas seguintes.

Esta Phase 0 extrai os helpers gate-agnostic do CC validator para dois
módulos compartilhados (`validators/_gate_infra.py` e `validators/_diff.py`)
e renomeia dois helpers já em `validators/_common.py` para nome genérico.
O CC gate passa a compor a nova infra em vez de carregar os helpers
embutidos. Contrato de no-behavior-change é absoluto: nenhum bit de
output observável do CC gate muda — mesmas mensagens, mesmos warnings,
mesmo 3-caminhos render, mesmo result_pass/warn/fail, mesmo
posicionamento na cascade. `validators/check_no_behavior_change.py` +
suite pytest verde antes/depois validam isso.

## Decisões do brainstorm

| Eixo | Decisão (locked) | Alternativas rejeitadas |
|---|---|---|
| Naming | Públicos sem underscore: `dispatch_native_tool`, `check_tool_available`, `parse_overrides`, `apply_overrides`, `render_config_with_placeholders`, `extract_diff_hunks`, `git_staged_files`, `read_commit_body`, `classify_range_against_hunks`. Tipos: `DispatchResult`, `DiffHunk`. | Manter underscore (`_dispatch_tool`) sinalizaria "privado ao módulo" — exatamente o contrário do objetivo (público pros próximos 7 gates). |
| Backwards-compat | Hard rename, sem aliases temporários em `_common.py` nem stubs em `check_cyclomatic_complexity.py`. | Alias por 1 ciclo de release era a sugestão do plan §Helpers de _common.py merecem rename — descartada porque ninguém fora do repo importa esses helpers (são internos do validator), e o custo de alias é manter dois nomes válidos no graph confundindo Q11 (reusable-helpers). |
| Granularidade de commits | Atômicos por helper extraído (~7-8 commits totais), cada um mantém suite verde antes do próximo. | Big-bang single commit dificultaria bisect se algo der errado; commits muito finos (1 por linha movida) sobrecarregariam o histórico sem ganho de auditabilidade. |

Estas três decisões saíram de AskUserQuestion (2026-06-04) durante o
brainstorm anterior à dispatch desta spec. Não revisitam decisões
load-bearing (1-27 em `docs/design/01-decisions.md`).

## Seção 1 — Extraction map (helpers a mover)

Cada linha das tabelas abaixo é literal: arquivo + linha de origem no
`check_cyclomatic_complexity.py` da branch atual, destino com nome novo,
assinatura pública pós-extração e nota de generalização. O subagente que
executar a Phase 0 usa esta tabela como contrato.

### `validators/_gate_infra.py` (NEW)

| Origem (check_cyclomatic_complexity.py:linha) | Destino | Assinatura nova | Notas |
|---|---|---|---|
| `class _DispatchResult` (linha 330-348) | `_gate_infra.DispatchResult` | `@dataclass(frozen=True) class DispatchResult: language: str; tool_found: bool; crashed: bool; raw_stdout: str; error_message: str` | Rename só remove o underscore. Campos idênticos. |
| `_check_tool_available` (linha 351) | `_gate_infra.check_tool_available` | `def check_tool_available(tool: str) -> bool` | Rename só remove o underscore. Implementação idêntica (shutil.which). |
| `_render_config_for_threshold` (linha 363) | `_gate_infra.render_config_with_placeholders` | `def render_config_with_placeholders(template_path: Path, placeholders: dict[str, str]) -> str` | Generaliza: dict de placeholders em vez de threshold único. CC gate passa `{"__CC_THRESHOLD__": str(threshold)}`. Outros gates passam suas próprias chaves (`__COG_THRESHOLD__`, `__LEN_THRESHOLD__`, etc.). Helper aplica `raw.replace(k, v)` para cada par. |
| `_dispatch_tool` (linha 380-549) | `_gate_infra.dispatch_native_tool` | `def dispatch_native_tool(*, language: str, files: list[str], cmd_builder: Callable[[str, list[str], Path \| None], list[str]], project_root: Path, config_template: Path \| None = None, placeholders: dict[str, str] \| None = None, tool_bin: str, timeout: int = 60, benign_nonzero_codes: tuple[int, ...] = ()) -> DispatchResult` | Parametriza o que era hard-coded por linguagem: `cmd_builder` recebe `(tool_bin, files, rendered_config_path)` e devolve `cmd`. `config_template` + `placeholders` opcionais (tools que aceitam threshold via CLI passam `None`). `benign_nonzero_codes=(1,)` cobre o caso eslint exit=1 sem precisar hard-code "ts" no helper. CC gate vai expor `cmd_builder` por linguagem (lambdas locais) e injetar pelo dispatch. |
| `_parse_overrides` (linha 576-639) | `_gate_infra.parse_overrides` | `def parse_overrides(commit_body: str, *, prefix: str, key_fields: list[str], return_warnings: bool = False) -> list[dict] \| tuple[list[dict], list[str]]` | Generalizado: `prefix` substitui o literal `CC-OVERRIDE` (vira `SECRETS-OVERRIDE`, `DEPS-OVERRIDE`, `DUP-OVERRIDE`, `COG-OVERRIDE`, `LEN-OVERRIDE`, `DEAD-OVERRIDE`, `ARCH-OVERRIDE` conforme gate). `key_fields` define quais grupos do regex extrair (CC usa `["file", "func", "cc"]`; secrets usa `["file", "line", "kind"]`; etc.). O helper compila os dois regex (strict + loose) parametrizados em runtime e devolve o mesmo formato de antes — dict por override + lista de warnings de malformados. |
| `_apply_overrides` (linha 642-670) | `_gate_infra.apply_overrides` | `def apply_overrides(fails: list, commit_body: str, *, prefix: str, key_fields: list[str], key_extractor: Callable[[Any], tuple]) -> tuple[list, list, list[str]]` | Generalizado: `key_extractor` é função `fail → tuple` que casa contra a chave do override. CC gate passa `lambda f: (f.file, f.function)`; secrets passa `lambda f: (f.file, f.line)`; cada gate define o que casa. `prefix` + `key_fields` repassados pro `parse_overrides` interno. |

### `validators/_diff.py` (NEW)

| Origem (linha) | Destino | Assinatura nova |
|---|---|---|
| `class CCResult.classify_function` lógica (linha 78-109) | `_diff.classify_range_against_hunks` | `def classify_range_against_hunks(func_range: tuple[int, int], diff_hunks: list[DiffHunk]) -> str` — retorna `"new" \| "modified" \| "unchanged"`. Lógica idêntica (entire-range-in-add → new; qualquer intersecção → modified; senão unchanged). |
| Dict shape `{"start", "end", "kind"}` usado em hunks (linhas 776-778) | `_diff.DiffHunk` | `@dataclass(frozen=True) class DiffHunk: start: int; end: int; kind: str` — formaliza o que hoje é dict ad-hoc. `extract_diff_hunks` passa a emitir `DiffHunk`; `classify_range_against_hunks` consome `DiffHunk`. CC gate adapta consumidores (mudança interna, observável zero). |
| `_extract_diff_hunks` (linha 739-780) | `_diff.extract_diff_hunks` | `def extract_diff_hunks(project_root: Path, files: list[Path]) -> dict[str, list[DiffHunk]]` — mesmo dict-by-rel-path; valores agora `list[DiffHunk]` em vez de `list[dict]`. |
| `_git_staged_files` (linha 705-736) | `_diff.git_staged_files` | `def git_staged_files(project_root: Path, *, extensions: set[str] \| None = None) -> list[Path]` — novo parâmetro `extensions` filtra na origem por suffix (CC passa `set(SUPPORTED_EXTENSIONS)`; secrets passa `None` pra capturar tudo; deps passa `{".gradle", ".swift", ".json", ".toml"}` etc.). Sem `extensions`, devolve tudo. Mantém o `-M80%` rename detection. |
| `_read_commit_body` (linha 783-812) | `_diff.read_commit_body` | `def read_commit_body(project_root: Path) -> str` — idêntico. Fallback ordem (`.git/COMMIT_EDITMSG` → `git log -1 --format=%B`) preservado. |

### `validators/_common.py` (RENAME de helpers existentes)

| Atual (linha) | Novo nome | Notas |
|---|---|---|
| `cc_threshold_lookup` (linha 316) | `gate_threshold_lookup` | Generaliza o nome. Assinatura mantida; semântica idêntica. O `card.get("cc-gate-override")` lookup vira parametrizável via novo argumento `card_override_key: str` (CC passa `"cc-gate-override"`; secrets vai passar `"secrets-gate-override"` etc.); similar pra `workflow_config.get("cc-gate")` que vira `workflow_block_key: str`. Defaults table também vira parâmetro (CC passa `DEFAULTS_CC`; outros gates passarão `DEFAULTS_SECRETS` etc.). |
| `cc_format_three_paths` (linha 364) | `format_three_paths_message` | Generaliza. O literal `"🛑 Cyclomatic Complexity gate"` vira parâmetro `gate_title: str`; a linha `"Funções com CC alto..."` vira parâmetro `why_lines: list[str]`; o annotation suffix por status (`[new]`, `↑ de cc=...`) fica como callback `format_annotation: Callable[[dict], str]` opcional (default = render genérico que mostra status raw). CC gate passa título + razões + callback específicos como hoje, comportamento observável zero diff. |
| `DEFAULTS_CC` (linha 308) | **mantém** como `DEFAULTS_CC` | CC-específico. Outras gates terão suas próprias tables (`DEFAULTS_COG`, `DEFAULTS_LEN`, etc.) no momento em que forem criados. Nenhuma promoção a "DEFAULTS genérico" — cada gate tem range próprio. |

## Seção 2 — Refactor de `check_cyclomatic_complexity.py`

Após extração, o validator passa a compor a nova infra. Imports do topo
ficam assim:

```python
# Imports do _common.py (renomeados)
from _common import (
    DEFAULTS_CC,
    format_three_paths_message,
    gate_threshold_lookup,
    make_paths,
    result_fail,
    result_pass,
    result_warn,
    run_cli,
)

# Imports da nova infra
from _gate_infra import (
    DispatchResult,
    apply_overrides,
    check_tool_available,
    dispatch_native_tool,
    parse_overrides,
    render_config_with_placeholders,
)
from _diff import (
    DiffHunk,
    classify_range_against_hunks,
    extract_diff_hunks,
    git_staged_files,
    read_commit_body,
)
```

### O que **PERMANECE** em `check_cyclomatic_complexity.py`

Tudo que é CC-específico:

- `class CCResult` — gate-specific data shape (cc, cc_before, language, status).
- `_parse_detekt`, `_parse_swiftlint`, `_parse_eslint`, `_parse_radon` —
  parsers de output das 4 tools. Heterogêneos por tool, não-genéricos;
  ficam aqui.
- `_TOOL_BIN`, `_CONFIG_DIR`, `_TEST_IGNORE_DEFAULTS`,
  `SUPPORTED_EXTENSIONS`, `_CC_THRESHOLD_PLACEHOLDER` — constantes do
  gate.
- `_CC_OVERRIDE_RE`, `_CC_OVERRIDE_LOOSE_RE` — regex CC-específicos.
  **Removidos**: substituídos pelos regex internos parametrizados que
  `parse_overrides` compila a partir de `prefix` + `key_fields`. Os dois
  attributes deixam de existir no módulo.
- `_run_tools_for_staged` — orquestrador per-language que monta o
  `cmd_builder` por linguagem (lambdas locais) e chama
  `dispatch_native_tool`. Passa a ser quem conhece o `_TOOL_BIN[lang]` e
  qual config template usar.
- `_load_active_cards`, `_load_workflow_config`, `_compile_ignore_patterns`,
  `_path_matches_ignore` — inicialmente ficam aqui (YAGNI: só CC usa
  agora). Promovem pra módulo compartilhado em Wave R1+ se outro gate
  precisar. Os outros gates podem reusar diretamente importando do CC
  enquanto for o único consumidor — promoção formal só quando aparecer o
  segundo cliente.
- `validate(project_root, **kwargs)` — entry point. Pipeline interno
  agora chama `git_staged_files`, `extract_diff_hunks`, `read_commit_body`,
  `gate_threshold_lookup`, `apply_overrides`, `format_three_paths_message`
  importados.

### Substituições representativas

Antes:

```python
# Em check_cyclomatic_complexity.py
result = _dispatch_tool(language="kotlin", files=files, threshold=10, project_root=project_root)
```

Depois:

```python
# Em check_cyclomatic_complexity.py
def _build_detekt_cmd(tool_bin: str, files: list[str], config_path: Path | None) -> list[str]:
    return [tool_bin, "--input", ",".join(files), "--config", str(config_path), "--report", "json:-"]

result = dispatch_native_tool(
    language="kotlin",
    files=files,
    cmd_builder=_build_detekt_cmd,
    project_root=project_root,
    tool_bin=_TOOL_BIN["kotlin"],
    config_template=_CONFIG_DIR / "detekt.yml",
    placeholders={"__CC_THRESHOLD__": str(threshold)},
)
```

Antes:

```python
silenced, surviving, warnings = _apply_overrides(fails, commit_body)
```

Depois:

```python
def _cc_key_extractor(fail: CCResult) -> tuple[str, str]:
    return (fail.file, fail.function)

silenced, surviving, warnings = apply_overrides(
    fails, commit_body,
    prefix="CC-OVERRIDE",
    key_fields=["file", "func", "cc"],
    key_extractor=_cc_key_extractor,
)
```

Antes:

```python
hunks_dict = _extract_diff_hunks(project_root, staged_paths)
# hunks_dict[file] = list[dict[start/end/kind]]
status = classify_function((line_start, line_end), hunks_dict[rel])
```

Depois:

```python
hunks_by_file: dict[str, list[DiffHunk]] = extract_diff_hunks(project_root, staged_paths)
status = classify_range_against_hunks((line_start, line_end), hunks_by_file.get(rel, []))
```

### Resultado em LOC

`check_cyclomatic_complexity.py` cai de ~1127 LOC pra ~600-700 LOC:

- `_DispatchResult`, `_check_tool_available`, `_render_config_for_threshold`,
  `_dispatch_tool` movidos: ~220 LOC removidas (linhas 330-549).
- `_parse_overrides`, `_apply_overrides` movidos: ~95 LOC removidas
  (linhas 576-670).
- `classify_function`, `_extract_diff_hunks`, `_git_staged_files`,
  `_read_commit_body` movidos: ~140 LOC removidas (linhas 78-109 +
  705-812).
- Adições: `_build_detekt_cmd`, `_build_swiftlint_cmd`,
  `_build_eslint_cmd`, `_build_radon_cmd` (lambdas locais, ~40 LOC) +
  ajustes de import + adaptação dos call-sites (~20 LOC).

Saldo: ~430 LOC a menos no validator principal, ~280 LOC adicionados em
`_gate_infra.py` + `_diff.py` (módulos novos sem duplicação). Net
infraestrutura reusável criada: ~430 LOC promovidos a infra; ~150 LOC
generalizados na promoção.

## Seção 3 — Critério de no-behavior-change

Mandamento crítico: refactor NÃO PODE mudar comportamento observável.

Verificação obrigatória, na ordem:

1. **`validators/check_no_behavior_change.py`** roda antes e depois do
   refactor. Mantém o veredito do PR #4 sem regredir.
2. **Suite pytest verde** antes e depois do refactor. Test count
   idêntico — count atual em `docs/design/08-session-handoff.md`,
   confirmar pré-refactor com `pytest --collect-only -q | tail -1`.
3. **Tests específicos do CC gate** (`tests/validators/test_check_cyclomatic_complexity.py`,
   `tests/validators/test_cc_dispatch.py`, `tests/validators/test_cc_override.py`,
   `tests/validators/test_cc_parsers_*.py`, `tests/integration/test_implement_cc_gate.py`,
   `tests/engine/test_verify_cc_position.py`) — assertions inalteradas;
   só `import` paths mudam quando o teste importa diretamente um helper
   que mudou de módulo (ex: `from validators.check_cyclomatic_complexity import classify_function` vira `from validators._diff import classify_range_against_hunks` e a função
   é chamada com o mesmo input). Assertions sobre output do validator
   (status/message/paths/warnings) **não mudam** — qualquer diff em
   assertions é red flag.
4. **Snapshot test do 3-caminhos render** continua batendo
   byte-a-byte. `format_three_paths_message` produz string idêntica
   quando chamada com os mesmos parâmetros que `cc_format_three_paths`
   recebia antes (mesmo título, mesmas razões, mesmo annotation
   callback).
5. **`forge verify` cascade** roda CC gate idênticamente: mesma posição
   (após `check_no_invented_behavior`, conforme `test_verify_cc_position`),
   mesmo `status=pass/warn/fail` para os mesmos inputs.
6. **`forge implement` per-task hook** continua bloqueando os mesmos
   commits com a mesma mensagem (integração `test_implement_cc_gate`).
7. **CHANGELOG entry** explicita "no-behavior-change" — sinaliza ao
   reviewer que qualquer diff observável no CC gate é bug do refactor,
   não feature nova.

Critério de aceite final: subagente reviewer (`gsd-code-reviewer`)
confirma os 7 itens acima no REVIEW.md antes de qualquer merge.

## Seção 4 — Sequência de commits atômicos (granularidade locked)

7 commits de refactor + 1 commit de doc-sync. Cada commit individual
mantém pytest verde e `forge verify` verde. Bisect-safe.

1. **`refactor(validators): _gate_infra.py skeleton + DispatchResult`**
   - Cria `validators/_gate_infra.py` com módulo docstring + import
     `from dataclasses import dataclass`.
   - Move `_DispatchResult` → `DispatchResult` (sem underscore).
   - `check_cyclomatic_complexity.py` importa
     `from _gate_infra import DispatchResult` e usa o nome novo nos
     consumidores internos (3 ocorrências em `_dispatch_tool`).

2. **`refactor(validators): extract check_tool_available to _gate_infra`**
   - Move função `_check_tool_available` → `check_tool_available` em
     `_gate_infra.py`.
   - CC gate importa e usa o nome novo (1 call-site em `_dispatch_tool`).

3. **`refactor(validators): extract render_config_with_placeholders to _gate_infra`**
   - Move `_render_config_for_threshold` →
     `render_config_with_placeholders` em `_gate_infra.py`.
   - Generaliza para `placeholders: dict[str, str]` (iteração).
   - CC gate substitui 2 chamadas (kotlin + swift branches em
     `_dispatch_tool`) passando `{"__CC_THRESHOLD__": str(threshold)}`.
   - Remove constante `_CC_THRESHOLD_PLACEHOLDER` do CC validator (vira
     apenas string literal em 2 call-sites).

4. **`refactor(validators): extract dispatch_native_tool to _gate_infra`**
   - Move `_dispatch_tool` → `dispatch_native_tool` em `_gate_infra.py`,
     parametrizando `cmd_builder` + `tool_bin` + `benign_nonzero_codes`.
   - CC gate adiciona 4 lambdas locais (`_build_detekt_cmd`,
     `_build_swiftlint_cmd`, `_build_eslint_cmd`, `_build_radon_cmd`) +
     atualiza `_run_tools_for_staged` para chamar `dispatch_native_tool`.

5. **`refactor(validators): extract parse_overrides + apply_overrides to _gate_infra`**
   - Move `_parse_overrides` → `parse_overrides` + `_apply_overrides` →
     `apply_overrides` em `_gate_infra.py`, parametrizando `prefix` +
     `key_fields` + `key_extractor`.
   - Remove `_CC_OVERRIDE_RE` e `_CC_OVERRIDE_LOOSE_RE` do CC validator
     (regex passam a ser compilados internamente em `parse_overrides`).
   - CC gate atualiza `validate()` para chamar com
     `prefix="CC-OVERRIDE"`, `key_fields=["file", "func", "cc"]`,
     `key_extractor=lambda f: (f.file, f.function)`.

6. **`refactor(validators): create _diff.py with DiffHunk + helpers`**
   - Cria `validators/_diff.py` com `DiffHunk` dataclass +
     `classify_range_against_hunks` + `extract_diff_hunks` +
     `git_staged_files` + `read_commit_body`.
   - Move as 4 funções e o renomeio de `classify_function` →
     `classify_range_against_hunks`.
   - `extract_diff_hunks` passa a emitir `list[DiffHunk]` em vez de
     `list[dict]`; `classify_range_against_hunks` consome `DiffHunk`.
   - CC gate atualiza call-sites em `_run_tools_for_staged` e `validate()`
     (3 ocorrências).

7. **`refactor(validators): rename cc_threshold_lookup + cc_format_three_paths in _common.py`**
   - Renomeia `cc_threshold_lookup` → `gate_threshold_lookup` com novos
     parâmetros (`card_override_key`, `workflow_block_key`, `defaults`).
   - Renomeia `cc_format_three_paths` → `format_three_paths_message`
     com novos parâmetros (`gate_title`, `why_lines`, `format_annotation`).
   - `DEFAULTS_CC` mantém o nome.
   - CC gate atualiza 2 call-sites (`gate_threshold_lookup` com
     `card_override_key="cc-gate-override"`, `workflow_block_key="cc-gate"`,
     `defaults=DEFAULTS_CC`; `format_three_paths_message` com título e
     razões CC).
   - Hard rename — sem aliases temporários (decisão locked).

8. **`docs(sync): Phase 0 refactor — gate-infra-extract`**
   - `CHANGELOG.md` em `### Changed`: "Extraída infra reusável do CC
     gate (`validators/_gate_infra.py` + `validators/_diff.py`); rename
     `cc_*` helpers em `_common.py` pra nomes genéricos. No behavior
     change."
   - `docs/design/08-session-handoff.md` `**Última atualização:**`
     2026-06-04, `**Estado:**` reflete Phase 0 concluída.
   - `README.md` Stats atualizadas (validator count mantido, mas
     contagem de helpers compartilhados sobe).
   - `.claude/rules/reuse.md` ganha menção dos novos módulos em
     "Antes de criar helper/função/template/card/validator" — passa a
     citar `_gate_infra.py` e `_diff.py` como consulta obrigatória
     para próximos gates.
   - `docs/design/04-pending.md` risca a pendência implícita de
     extração (se foi anotada no plan de gaps).

Cada commit deve passar:

- `pytest -m "not integration and not e2e"` (lane rápida) verde.
- `forge verify` verde sem mudança de result_pass/warn/fail no CC gate.
- `git diff --stat HEAD~1..HEAD` confinado aos arquivos esperados.

## Seção 5 — Decisões load-bearing preservadas

Nenhuma das 8 decisões load-bearing (`docs/design/01-decisions.md`)
é tocada por este refactor. Tabela de confirmação:

| # | Decisão | Status nesta Phase | Razão |
|---|---|---|---|
| 14 | Config scope = um workflow-config por sub-projeto | Preservado | Refactor é só helpers em `validators/`; não toca config scope nem leitura. |
| 15 | Versioning model = snapshot copy local (fork-and-forget) | Preservado | Sem reintrodução de runtime dep; novos módulos vivem no próprio repo `feature-forge`, snapshotados em `forge init`. |
| 18 | Skill location = standalone repo em `~/Documents/feature-forge/` | Preservado | Sem mudança de location nem install path. |
| 19 | Language = Python core + Bash dispatcher + YAML/MD specs | Preservado | Refactor é Python puro; mesma stack. |
| 20 | Persistence = SQLite (graph) + arquivos | Preservado | Refactor não toca persistence layer. |
| 22 | No runtime deps em outras skills | Preservado | Novos módulos só usam stdlib + `engine.utils.*` (já parte do projeto). Zero import de superpowers/gsd-* etc. |
| 23 | Validator cascade = fail-fast por default | Preservado | CC gate continua emitindo `result_fail` na mesma posição da cascade; comportamento fail-fast inalterado. |
| 27 | Pause = `deferred` auto-resumable; abort = 2-step via `forge undo` | Preservado | Refactor não toca state machine de pause/abort. |

Nenhuma entrada "Revisita decisão N" no CHANGELOG. Pre-commit hook
`.claude/hooks/pre-commit-feature-forge.sh` não vai disparar hard-block
porque `docs/design/01-decisions.md` não está staged em nenhum dos 8
commits.

## Seção 6 — Próximo passo após Phase 0

Phase 0 mergeada em main desbloqueia o paralelismo de Wave R1+:

- **Wave R1.1 (`feat/check-secrets`)** pode iniciar imediatamente.
  Estimativa do plan original era 1-2d; com `_gate_infra` pronta cai
  para **~1d** (parsers `gitleaks` / `trufflehog` específicos + 4
  imports da infra para dispatch/override/diff/3-caminhos).
- **Wave R1.2 (`feat/check-deps-cve`)** segue mesmo padrão — ~1.5d.
- **Wave R2.x** (`check_duplication`, `check_cognitive_complexity`,
  `check_function_length_and_nesting`) reusa ainda mais agressivamente
  porque compartilham as 4 tools do CC gate (Detekt/SwiftLint/eslint/
  Radon) — só novos config templates + nomes de rule. Estimativas do
  plan (~1d cada para cog e ~0.5d para length-nesting) ficam realistas.
- **Wave R3.x** (`check_dead_code`, `check_arch_rules`) reusam
  parcialmente (Periphery/Konsist têm dispatch ortogonal); ainda assim
  `parse_overrides` + `format_three_paths_message` + `check_tool_available`
  + `git_staged_files` + `read_commit_body` são ganho garantido.

Cada Wave seguinte deve consultar `forge graph query Q11` antes de
escrever helper novo — se aparecer near-duplicate dos novos módulos, o
caminho correto é compor, não reinventar (Mandamento #3). O próprio
subagente que executar Wave R1.1 vai validar que a Phase 0 cumpriu o
contrato: se `check_secrets` precisar reescrever lógica de dispatch ou
override-parsing, é sinal de que a generalização da Phase 0 ficou curta
— retorna para revisita aqui.

Phase 0 é o investimento que torna o resto do roadmap composição limpa
em vez de cópia. Sem ela, o débito multiplica em cada gate.
