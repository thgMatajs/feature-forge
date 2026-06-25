# W-STATE (Fase 1, Onda 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** Mover a state-machine de lifecycle de `.claude/memory/L1/` → `.claude/forge/state/lifecycle/` (Decisão #1), consolidando os ~10 sites hardcoded numa fonte única `paths.lifecycle_root()`, sem perder comportamento. Inclui a fila `proposed-evolutions` e re-aponta os validators que leem lifecycle.

**Architecture:** Mesmo padrão do W-RENAME. Introduz `lifecycle_root(project_root)` em `engine/utils/paths.py` como fonte única; todos os sites que hoje constroem `memory_dir / "L1" / ...` passam a derivar dela. O move vira a troca de UMA expressão no helper. Task 1 consolida (valor inalterado, behavior-preserving); Task 2 vira o helper p/ forge/state + migra testes + gitignore + grep-gate; Task 3 doc-sync.

**Tech Stack:** Python 3.13, pytest (`.venv/bin/pytest` canônico), git.

## Global Constraints

- **W-STATE = só L1.** L2 (`memory_l2_path`) e L3 ficam INTOCADOS — a remoção de escrita em L2 é inseparável do W-ROUTE (evolve→mem inbox). NÃO tocar `engine/memory/l2.py`, `l3.py`, nem `memory_l2_path`.
- **Move TUDO de `memory/L1/`** (decisão do user): per-feature `<slug>/`, `archived/`, e `proposed-evolutions/` → todos sob `forge/state/lifecycle/`.
- **Manter o nome `memory_l1_path`** re-derivado (spec §Reconciliação manda; minimiza churn). Docstring atualizada.
- **Sem revisita formal de decisão.** A Decisão 20 (persistence) entra como **ADR-note no CHANGELOG `### Changed`** (sem ritual "Revisita decisão N") — espírito mantido: lifecycle continua arquivo+SQLite, só muda o sub-namespace de `memory/` pra `forge/state/`.
- **Sem migração de dados in-repo.** `.claude/memory/L1/` é WIP gitignored, transiente, pré-produção — clean break. `git ls-files .claude/memory/L1/` = vazio (nada committado). Não há shim de back-compat.
- `.venv/bin/pytest` é canônico.
- Exclusões do grep-gate: `docs/superpowers/**`, `.claude/worktrees/**` (worktree stale).
- Voz mentor calmo.
- NÃO tocar `init.py:2404` `"layers-enabled": ["L1","L2","L3"]` — é o conceito de camadas (retirado em ondas futuras), não um path.

---

### Task 1: Fonte única `lifecycle_root` (consolidação behavior-preserving)

**Files:**
- Modify: `engine/utils/paths.py` (add `lifecycle_root`; re-derive `memory_l1_path` dela; valor ainda `memory_dir/"L1"`)
- Modify: `engine/memory/l1.py` (`_archived_dir` linha 128; list-active linha 466 → consomem `lifecycle_root`)
- Modify: `engine/qa/emit.py` (`_PROPOSED_DIR_PARTS` linha 42 → deriva de `lifecycle_root`)
- Modify: `engine/ingest.py:283`, `engine/verify.py:616`, `engine/doctor.py:591`, `engine/init.py:2038-2039` (scaffold)
- Modify: `validators/validate_extension_feature.py:59,110,161`, `validators/validate_forge_config.py:326`, `validators/validate_memory.py:244,314`
- Modify: `engine/persona/mentor_calmo.py:135` (string user-facing — usar o helper p/ montar)
- Test: `tests/engine/utils/test_utils_paths.py` (ou `tests/unit/test_paths_helpers.py`) — add single-source test

**Interfaces:**
- Produces: `paths.lifecycle_root(project_root: Path) -> Path` (a raiz que contém os slugs per-feature + `archived/` + `proposed-evolutions/`; nesta task ainda retorna `memory_dir(project_root) / "L1"`). `paths.memory_l1_path` passa a ser `lifecycle_root(project_root) / feature_slug`.

- [ ] **Step 1: Write the failing single-source test**

```python
# tests/engine/utils/test_utils_paths.py (append)
import engine.utils.paths as paths

def test_lifecycle_root_is_single_source(monkeypatch, tmp_path):
    # Patchar lifecycle_root deve fluir pra todos os paths de lifecycle derivados.
    sentinel = tmp_path / "SENTINEL_STATE"
    monkeypatch.setattr(paths, "lifecycle_root", lambda root: sentinel)
    assert paths.memory_l1_path(tmp_path, "feat-x") == sentinel / "feat-x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/engine/utils/test_utils_paths.py::test_lifecycle_root_is_single_source -v`
Expected: FAIL — `AttributeError: module 'engine.utils.paths' has no attribute 'lifecycle_root'` (ou `memory_l1_path` não deriva do patch).

- [ ] **Step 3: Implement `lifecycle_root` + re-derive `memory_l1_path` (valor inalterado)**

```python
# engine/utils/paths.py — perto dos helpers de memory
def lifecycle_root(project_root: Path) -> Path:
    """Raiz da state-machine de lifecycle (per-feature WIP + archived +
    proposed-evolutions). Decisão #1: a lifecycle vive em forge/state, fora
    de .claude/memory/ (que é 100% do mem). [Task 1 mantém o valor legado;
    Task 2 vira pra forge_state_dir/lifecycle.]"""
    return memory_dir(project_root) / "L1"

def memory_l1_path(project_root: Path, feature_slug: str) -> Path:
    """Diretório de lifecycle (per-feature WIP) de uma feature."""
    return lifecycle_root(project_root) / feature_slug
```

- [ ] **Step 4: Route todos os sites hardcoded pra consumir `lifecycle_root`**

Substituir cada `memory_dir(project_root) / "L1"` (e variações de string `("...","memory","L1",...)`) por `lifecycle_root(project_root)`:
- `engine/memory/l1.py:128` `_archived_dir` → `return lifecycle_root(project_root) / "archived"`
- `engine/memory/l1.py:466` list-active → `root = lifecycle_root(project_root)`
- `engine/qa/emit.py:42` `_PROPOSED_DIR_PARTS` → derivar de `lifecycle_root(project_root) / "proposed-evolutions"` (ler como o helper é consumido na função que usa `_PROPOSED_DIR_PARTS`; trocar pra montar via `lifecycle_root`)
- `engine/ingest.py:283` → `lifecycle_root(project_root) / feature_slug / "history.jsonl"`
- `engine/verify.py:616` → `lifecycle_root(project_root) / feature_slug / "verify-log.jsonl"`
- `engine/doctor.py:591` → `lifecycle_root(project_root)`
- `engine/init.py:2038-2039` → `ensure_dir(lifecycle_root(project_root))` + `ensure_dir(lifecycle_root(project_root) / "archived")`
- `validators/validate_extension_feature.py:59,110,161` → via `memory_l1_path`/`lifecycle_root`
- `validators/validate_forge_config.py:326` → `lifecycle_root(project_root)`
- `validators/validate_memory.py:244,314` → `lifecycle_root(project_root)` (ajustar a semântica: valida o layout de lifecycle no novo root)
- `engine/persona/mentor_calmo.py:135` → montar a string via `lifecycle_root` (não hardcodar `.claude/memory/L1/`)

(Importar `lifecycle_root` onde necessário. NÃO mudar o valor — ainda `memory/L1`.)

- [ ] **Step 5: Single-source test + rapid lane green (valor inalterado)**

Run: `.venv/bin/pytest tests/engine/utils/test_utils_paths.py -v && .venv/bin/pytest -m "not integration and not e2e" -q | tail -1`
Expected: PASS; rapid lane sem regressão (path ainda `.claude/memory/L1/`).
Nota: 10 falhas pré-existentes em `tests/integration/test_claude_rules_system.py` (débito Fase 0, CLAUDE.md enxuto) NÃO contam — não estão na rapid lane.

- [ ] **Step 6: Commit**

```bash
git add engine/utils/paths.py engine/memory/l1.py engine/qa/emit.py engine/ingest.py \
  engine/verify.py engine/doctor.py engine/init.py engine/persona/mentor_calmo.py \
  validators/validate_extension_feature.py validators/validate_forge_config.py validators/validate_memory.py \
  tests/engine/utils/test_utils_paths.py
git commit -m "refactor(paths): single-source lifecycle_root (consolida sites de memory/L1)"
```

---

### Task 2: Virar o helper p/ forge/state + migrar testes + gitignore + grep-gate + ADR-note

**Files:**
- Modify: `engine/utils/paths.py` (`lifecycle_root` → `forge_state_dir(project_root) / "lifecycle"`; docstring)
- Modify: `.gitignore` (migrar a regra de L1 WIP)
- Modify: `CHANGELOG.md` (ADR-note Decisão 20, Unreleased)
- Modify (testes que criam/asseguram path L1 — fixtures + asserts): os arquivos de teste que constroem `.claude/memory/L1/` ou esperam esse path (ex.: `tests/unit/test_utils_paths.py`, `test_l1_blocked_state.py`, `test_implement_*.py`, `test_memory_l1_blocking_deps_resilient.py`, `tests/engine/qa/*` que tocam proposed-evolutions, `tests/integration/*` de lifecycle, `validators` tests). Enumerar via grep no Step 2.
- Create: `tests/unit/test_no_legacy_l1_path.py` (grep-gate)

**Interfaces:**
- Consumes: `paths.lifecycle_root` (Task 1).

**Anti-padrões (Task 2):**
- NÃO tocar testes/sites de L2/L3 (fora de escopo).
- Trocar fixtures de DEFAULT lifecycle path; preservar qualquer override custom de `feature-roots`/state se existir.
- NÃO reescrever `docs/superpowers/**` nem tocar `.claude/worktrees/**`.
- NÃO tocar prosa de docs (Task 3) exceto o CHANGELOG (ADR-note aqui).
- grep-gate com self-exclusão por PATH RESOLVIDO COMPLETO.

- [ ] **Step 1: Write the grep-gate (red)**

```python
# tests/unit/test_no_legacy_l1_path.py
import subprocess
from pathlib import Path

# DETECÇÃO SIMÉTRICA: o path L1 legado aparece em DUAS formas no código —
#   (1) string literal: ".claude/memory/L1/..." (docstrings, mensagens, qa parts)
#   (2) construção Path: memory_dir(project_root) / "L1"  (a maioria dos sites)
# O gate pega as duas. Padrões montados por partes pra o próprio gate não auto-casar.
STRING_LITERAL = "memory" + "/L1"
PATH_CONSTRUCT = "memory_dir"  # par com "L1" na mesma linha = construção legada
BEHAVIOR_DIRS = ["engine", "validators", "hooks", "tests"]

def _grep(pattern, dirs, root):
    out = subprocess.run(
        ["grep", "-rn", "--exclude-dir=__pycache__", pattern, *dirs],
        cwd=root, capture_output=True, text=True,
    )
    return out.stdout.splitlines()

def _not_self(line, root, self_path):
    # grep -rn → "relpath:lineno:conteúdo"; exclui só este próprio arquivo por path resolvido.
    rel = line.split(":", 1)[0]
    return (root / rel).resolve() != self_path

def test_no_legacy_l1_path_in_behavior_code():
    root = Path(__file__).resolve().parents[2]
    self_path = Path(__file__).resolve()
    dirs = [d for d in BEHAVIOR_DIRS if (root / d).is_dir()]
    # Forma 1: string literal memory/L1
    str_hits = [l for l in _grep(STRING_LITERAL, dirs, root) if _not_self(l, root, self_path)]
    # Forma 2: construção Path — linha com memory_dir(...) E o segmento "L1"
    # (não casa `"layers-enabled": ["L1","L2","L3"]` pois essa linha não tem memory_dir)
    construct_hits = [
        l for l in _grep(PATH_CONSTRUCT, dirs, root)
        if '"L1"' in l and _not_self(l, root, self_path)
    ]
    hits = sorted(set(str_hits + construct_hits))
    assert hits == [], f"Path L1 legado sobrou: {hits}"
```
Nota: o gate cobre código de comportamento + testes (as duas formas). Docstrings/comentários em `engine/*.py` (plan.py, verify.py, l1.py:1, __init__ etc.) que citam `.claude/memory/L1/` em STRING são pegos pela Forma 1 → devem virar `forge/state/lifecycle` na Task 2 (não só Task 3), porque vivem em behavior dirs. (Task 3 cobre só prosa markdown em `docs/`.) O `"layers-enabled": ["L1","L2","L3"]` (init.py:2404) NÃO é path e NÃO casa nenhuma das formas (sem `memory_dir` na linha, sem string `memory/L1`).

- [ ] **Step 2: Run gate to verify it fails + enumerar arquivos afetados**

Run: `.venv/bin/pytest tests/unit/test_no_legacy_l1_path.py -v` (FAIL, lista os sobreviventes)
Run auxiliar p/ enumerar testes a migrar: `grep -rln "memory/L1" tests/ --exclude-dir=__pycache__`

- [ ] **Step 3: Flip `lifecycle_root` + docstrings em código**

```python
# engine/utils/paths.py
def lifecycle_root(project_root: Path) -> Path:
    """Raiz da state-machine de lifecycle — forge/state/lifecycle/ (Decisão #1)."""
    return forge_state_dir(project_root) / "lifecycle"
```
Atualizar docstrings/comentários com `.claude/memory/L1/` em código (l1.py:1-8, plan.py:6/1174/1177/2120, verify.py:285/597, memory/__init__.py:4, qa/__init__.py:1526/1531, qa/emit.py docstrings, undo.py:627, implement.py:966, validate_extension_feature.py docstrings) → `.claude/forge/state/lifecycle/`.

- [ ] **Step 4: Migrar fixtures/asserts de teste**

Substituir nos arquivos de teste enumerados (Step 2) o path `.claude/memory/L1/` / `memory_dir/"L1"` por `forge/state/lifecycle` (fixtures que CRIAM dirs + asserts). Preservar overrides custom.

- [ ] **Step 5: Migrar a regra de gitignore**

Em `.gitignore`: REMOVER (clean break) as linhas 41-42:
```
.claude/memory/L1/*
!.claude/memory/L1/archived/
```
ADICIONAR (espelhando, na seção "Local-only project state"):
```
.claude/forge/state/lifecycle/*
!.claude/forge/state/lifecycle/archived/
```

- [ ] **Step 6: ADR-note Decisão 20 no CHANGELOG (Unreleased, voz mentor calmo)**

```markdown
### Changed
- State-machine de lifecycle migrada de `.claude/memory/L1/` →
  `.claude/forge/state/lifecycle/` (Decisão #1 da integração mem). Consolidada
  numa fonte única `paths.lifecycle_root`. `.claude/memory/` deixa de hospedar
  lifecycle (caminho pra ser 100% do mem). ADR-note Decisão 20 (persistence):
  o espírito se mantém — lifecycle continua arquivos + SQLite; só muda o
  sub-namespace de `memory/` pra `forge/state/`. Sem revisita formal (não
  contradiz a decisão locked).
```

- [ ] **Step 7: grep-gate + full suite green**

Run: `.venv/bin/pytest tests/unit/test_no_legacy_l1_path.py -v && .venv/bin/pytest -m "not integration and not e2e" -q | tail -1 && .venv/bin/pytest -m "integration or e2e" -q | tail -1`
Expected: grep-gate PASS; rapid verde; integração/e2e sem regressão NOVA (as 10 falhas de `test_claude_rules_system.py` são pré-existentes — confirmar que o count de falhas não SOBE além dessas 10).

- [ ] **Step 8: Commit**

```bash
git add engine/ validators/ tests/ .gitignore CHANGELOG.md
git commit -m "refactor(state): lifecycle .claude/memory/L1 -> .claude/forge/state/lifecycle (Decisão #1)"
```

---

### Task 3: Doc-sync (prosa markdown)

**Files:**
- Modify: `docs/schemas/memory.md` (path de L1), `docs/design/05-filesystem-layout.md` (layout)
- Modify: outros docs em `docs/` (exceto `docs/superpowers/**`) que citam `.claude/memory/L1/` — enumerar via grep
- Modify: `README.md` (se cita o path)
- **NÃO tocar:** `docs/superpowers/**`, código (feito em Tasks 1/2)

**Interfaces:** nenhuma (doc-sync).

- [ ] **Step 1: Enumerar prosa afetada**

Run: `grep -rln "memory/L1" docs/ README.md | grep -v "docs/superpowers/"`

- [ ] **Step 2: Substituir** `.claude/memory/L1/` → `.claude/forge/state/lifecycle/` nos arquivos enumerados (preservar o resto da prosa).

- [ ] **Step 3: Verify** — `grep -rln "memory/L1" docs/ README.md | grep -v "docs/superpowers/" || echo "CLEAN"` → esperado `CLEAN` (CHANGELOG pode citar o path velho na própria entrada de migração — histórico aceitável).

- [ ] **Step 4: Commit**

```bash
git add docs/ README.md
git commit -m "docs(state): doc-sync memory/L1 -> forge/state/lifecycle"
```
