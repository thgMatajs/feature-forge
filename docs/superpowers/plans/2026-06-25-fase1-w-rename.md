# W-RENAME (Fase 1, Onda 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** Renomear o path de artefatos de feature `docs/feature-implementation-workflow` → `docs/forge-specs` (clean break, sem back-compat) consolidando os ~11 literais hardcoded numa fonte única em `paths.py`.

**Architecture:** Introduz `FEATURE_WORKFLOW_DIRNAME` em `engine/utils/paths.py` como fonte única. Path-helpers e sites string-only passam a derivar dela. O rename vira a troca de UM valor. Refactor de consolidação (Mandamento #3) anda junto com o rename no mesmo plano.

**Tech Stack:** Python 3.13, pytest (`.venv/bin/pytest` canônico), YAML configs.

## Global Constraints

- `docs/superpowers/specs/` **NÃO renomeia** (specs do próprio forge) — alertado 2x na spec.
- `.claude/worktrees/**` está **fora de escopo** (worktree stale; não é a working tree).
- `docs/superpowers/**` contém o literal como conteúdo histórico/design → **não reescrever** (registro histórico).
- Clean break: sem alias, sem back-compat (pré-produção, sem usuários reais).
- Sem revisita de decisão (rename não toca decisão locked). ADR-note das Decisões 20/22 NÃO é desta onda (é W-STATE/W-VENDOR).
- Voz mentor calmo em toda prosa/CHANGELOG.
- `.venv/bin/pytest` é o pytest canônico.

---

### Task 1: Fonte única `FEATURE_WORKFLOW_DIRNAME` (consolidação behavior-preserving)

**Files:**
- Modify: `engine/utils/paths.py` (add constant; linhas 153, 203, 228 derivam dela)
- Modify: `engine/memory/l1.py:721`
- Modify: `engine/qa/scope.py:166`
- Modify: `validators/validate_task_contract.py:88`
- Modify: `validators/check_files_in_allowed_files.py:48`
- Modify: `engine/graph/reuse_apply.py:28`
- Modify: `engine/graph/duplicates.py:935`
- Modify: `engine/init.py:3250`
- Test: `tests/engine/utils/test_feature_path_consolidated.py`

**Interfaces:**
- Produces: `paths.FEATURE_WORKFLOW_DIRNAME: str` (relative dirname, default `"feature-implementation-workflow"`); `paths.feature_workflow_root(project_root) -> Path` (já existe, passa a usar a constante).

- [ ] **Step 1: Write the failing test** — single-source assertion via monkeypatch

```python
# tests/engine/utils/test_feature_path_consolidated.py (append)
import engine.utils.paths as paths

def test_workflow_dirname_is_single_source(monkeypatch, tmp_path):
    # Patching the canonical constant must flow to every derived path.
    monkeypatch.setattr(paths, "FEATURE_WORKFLOW_DIRNAME", "SENTINEL_DIR")
    root = tmp_path
    assert paths.feature_workflow_root(root) == root / "docs" / "SENTINEL_DIR"
    assert paths.feature_dir(root, "x") == root / "docs" / "SENTINEL_DIR" / "features" / "x"
    assert paths._resolve_features_root(root) == (root / "docs" / "SENTINEL_DIR" / "features").resolve()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/engine/utils/test_feature_path_consolidated.py::test_workflow_dirname_is_single_source -v`
Expected: FAIL — `AttributeError: module 'engine.utils.paths' has no attribute 'FEATURE_WORKFLOW_DIRNAME'`

- [ ] **Step 3: Implement the constant + derive all paths.py sites**

```python
# engine/utils/paths.py — add near top of the path helpers block
FEATURE_WORKFLOW_DIRNAME = "feature-implementation-workflow"

def feature_workflow_root(project_root: Path) -> Path:
    """Default feature-workflow artifacts root in the project."""
    return project_root / "docs" / FEATURE_WORKFLOW_DIRNAME
```

Em `_resolve_features_root` (linha ~203) trocar o literal por:

```python
    base = feature_workflow_root(project_root)
```

Em `feature_path` (linha ~228) trocar o default-comparison por:

```python
        default = (feature_workflow_root(project_root) / "features").resolve()
```

- [ ] **Step 4: Consolidate external call-sites onto the helper/constant**

`engine/memory/l1.py` (import + linha 721):

```python
from engine.utils.paths import ensure_dir, feature_workflow_root, memory_dir, memory_l1_path
...
    base = feature_workflow_root(project_root)
```

`engine/qa/scope.py` (import `feature_workflow_root` + linha 166):

```python
def _features_root(root: Path) -> Path:
    return feature_workflow_root(root) / "features"
```

`validators/validate_task_contract.py` (add `feature_workflow_root` ao import da linha 34 + linha 88):

```python
    base = feature_workflow_root(project_root) / "features"
```

`validators/check_files_in_allowed_files.py` (add `feature_workflow_root` ao import da linha 27 + linha 48):

```python
    base = feature_workflow_root(project_root) / "features"
```

String-only sites (consomem a constante, não o Path) — importar `FEATURE_WORKFLOW_DIRNAME` de `engine.utils.paths`:

```python
# engine/graph/reuse_apply.py linha 28:
_NON_PRODUCT_DIR = f"docs/{FEATURE_WORKFLOW_DIRNAME}/non-product"
# engine/graph/duplicates.py linha 935:
"target-file": f"docs/{FEATURE_WORKFLOW_DIRNAME}/non-product/(generated)",
# engine/init.py linha 3250 (dentro de _build_paths):
"features-package-root": f"docs/{FEATURE_WORKFLOW_DIRNAME}/features",
```

- [ ] **Step 5: Run consolidation test + rapid lane to confirm green (valor inalterado)**

Run: `.venv/bin/pytest tests/engine/utils/test_feature_path_consolidated.py -v && .venv/bin/pytest -m "not integration and not e2e" -q | tail -1`
Expected: PASS; rapid lane sem regressão (valor ainda `feature-implementation-workflow`).

- [ ] **Step 6: Commit**

```bash
git add engine/utils/paths.py engine/memory/l1.py engine/qa/scope.py \
  validators/validate_task_contract.py validators/check_files_in_allowed_files.py \
  engine/graph/reuse_apply.py engine/graph/duplicates.py engine/init.py \
  tests/engine/utils/test_feature_path_consolidated.py
git commit -m "refactor(paths): single-source FEATURE_WORKFLOW_DIRNAME (consolida 11 literais)"
```

---

### Task 2: Executar o rename (virar a constante) + migrar testes + grep-gate

**Files:**
- Modify: `engine/utils/paths.py` (valor da constante; docstrings 152/157/217)
- Modify: `engine/plan.py:5`, `engine/qa/scope.py:5,62`, `engine/graph/reuse_apply.py:5`, validators docstrings (docstrings que citam o path)
- Modify: `hooks/ci-pr-ingest.yml`
- Modify: `agents/feature-intake-agent.md`, `feature-prd-agent.md`, `planning-conductor.md`, `retrospective-agent.md`, `screen-analysis-agent.md`, `task-contract-writer.md`, `tech-spec-agent.md`
- Modify (test migration, ~25 arquivos): `tests/conftest.py`, `tests/unit/test_validators_task_contract.py`, `test_implement_lock_release.py`, `test_lock_error_message_shows_real_holder.py`, `test_validators_readiness.py`, `test_validators_screen_analysis.py`, `test_l1_blocked_state.py`, `test_plan_extension.py`, `test_validators_data_contract.py`, `test_reuse_intelligence.py`, `test_memory_l1_blocking_deps_resilient.py`, `test_utils_paths.py`, `test_implement_done.py`, `tests/integration/test_qa_cross_feature_paranoid.py`, `test_qa_lifecycle_feature.py`, `test_qa_lifecycle_task.py`, `test_qa_pause_resume.py`, `tests/validators/test_validate_readiness_elicitation.py`, `tests/e2e/test_qa_cli_smoke.py`, `tests/engine/qa/test_run_qa_synthesis.py`, `test_sandbox_findings.py`, `test_scope.py`, `test_run_qa_resume.py`, `test_snapshot.py`, `test_qa_report.py`
- Create: `tests/unit/test_no_legacy_workflow_path.py` (grep-gate)

**Interfaces:**
- Consumes: `paths.FEATURE_WORKFLOW_DIRNAME` (Task 1).

- [ ] **Step 1: Write the grep-gate regression test (red)**

```python
# tests/unit/test_no_legacy_workflow_path.py
import subprocess
from pathlib import Path

# Construído por partes pra o próprio arquivo de teste não casar no grep.
LEGACY = "feature-implementation" + "-workflow"
BEHAVIOR_DIRS = ["engine", "validators", "hooks", "agents", "presets", "cards", "templates", "tests"]

def test_no_legacy_workflow_path_in_behavior_dirs():
    root = Path(__file__).resolve().parents[2]
    existing = [d for d in BEHAVIOR_DIRS if (root / d).is_dir()]
    out = subprocess.run(
        ["grep", "-rln", "--exclude-dir=__pycache__", LEGACY, *existing],
        cwd=root, capture_output=True, text=True,
    )
    hits = [l for l in out.stdout.splitlines() if l and Path(l).name != Path(__file__).name]
    assert hits == [], f"Literal legado sobrou em: {hits}"
```

- [ ] **Step 2: Run gate to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_no_legacy_workflow_path.py -v`
Expected: FAIL — lista os arquivos de teste/agents/hooks que ainda têm o literal.

- [ ] **Step 3: Flip the constant + update docstrings/comments**

```python
# engine/utils/paths.py
FEATURE_WORKFLOW_DIRNAME = "forge-specs"
```

Atualizar docstrings/comentários que citam o path velho (paths.py 152/157/217; plan.py:5; qa/scope.py 5,62; reuse_apply.py:5; validators docstrings) para `docs/forge-specs/...`.

- [ ] **Step 4: Migrate behavior files (agents, hooks) + test fixtures/assertions**

Substituição literal `feature-implementation-workflow` → `forge-specs` em:
- os 7 `agents/*.md` listados (onde instruem onde os artefatos moram),
- `hooks/ci-pr-ingest.yml`,
- os ~25 arquivos de teste listados (fixtures que CRIAM dirs + asserts que esperam o path).

Regra de migração (clean-break): testes que asseguram o **DEFAULT** migram pra `forge-specs`. Se algum teste assegura um **OVERRIDE** custom (config `paths.feature-roots` com valor próprio), **preserve o valor custom** — não é o default. (Verificar antes de trocar cegamente. Nota: `test_validators_forge_config.py` e `test_subnamespace_paths.py` usam override custom e NÃO estão na lista — não os toque.)

- [ ] **Step 5: Run grep-gate + full suite green**

Run: `.venv/bin/pytest tests/unit/test_no_legacy_workflow_path.py -v && .venv/bin/pytest -m "not integration and not e2e" -q | tail -1 && .venv/bin/pytest -m "integration or e2e" -q | tail -1`
Expected: grep-gate PASS; rapid + integration/e2e sem regressão.

- [ ] **Step 6: Commit**

```bash
git add engine/utils/paths.py engine/plan.py engine/qa/scope.py engine/graph/reuse_apply.py \
  validators/ hooks/ci-pr-ingest.yml agents/ tests/
git commit -m "refactor(rename): docs/feature-implementation-workflow -> docs/forge-specs (clean break)"
```

---

### Task 3: Doc-sync (prosa) + CHANGELOG + README

**Files:**
- Modify: `docs/design/04-pending.md`, `05-filesystem-layout.md`, `07-discipline.md`
- Modify: `docs/guides/feature-lifecycle.md`, `dot-claude-reference.md`
- Modify: `docs/product/00-prd.md`
- Modify: `docs/schemas/forge-config.md` (default `features-package-root`), `memory.md`, `proposed-evolutions.md`
- Modify: `docs/ux/forge-evolve-roteiro.md`, `forge-implement-roteiro.md`, `forge-plan-roteiro.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md` (Unreleased)
- **NÃO tocar:** `docs/superpowers/**` (histórico/design)

**Interfaces:** nenhuma (doc-sync).

- [ ] **Step 1: Update prose docs** — substituir `feature-implementation-workflow` → `forge-specs` nos arquivos `docs/` listados (exceto `docs/superpowers/**`) e em `README.md`.

- [ ] **Step 2: Add CHANGELOG Unreleased entry** (voz mentor calmo)

```markdown
### Changed
- Renomeado o path de artefatos de feature `docs/feature-implementation-workflow`
  → `docs/forge-specs` (clean break, sem alias). Consolidados os 11 literais
  hardcoded numa fonte única `paths.FEATURE_WORKFLOW_DIRNAME`. `docs/superpowers/specs/`
  (specs do forge) NÃO muda.
```

- [ ] **Step 3: Verify docs grep (excluindo superpowers) zera**

Run: `grep -rln "feature-implementation-workflow" docs/ README.md | grep -v "docs/superpowers/" || echo "CLEAN"`
Expected: `CLEAN` (CHANGELOG pode citar o nome velho na própria entrada de rename — aceitável, é histórico).

- [ ] **Step 4: Commit**

```bash
git add docs/ README.md CHANGELOG.md
git commit -m "docs(rename): doc-sync feature-implementation-workflow -> forge-specs"
```
