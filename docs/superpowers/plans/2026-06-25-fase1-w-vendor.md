# W-VENDOR (Fase 1, Onda 3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** `forge init` vendoriza o mem no projeto consumidor — copia o asset embutido `engine/assets/mem/mem` → `.claude/bin/mem` (executável), roda o scaffold do mem, e o `forge doctor` ganha uma categoria que checa o mem + drift do pin.

**Architecture:** Espelha o padrão de `_install_hooks` (init copia de `forge_home()` pro consumidor). Reusa a fronteira `engine/integrations/mem.py:mem_call` pra rodar o scaffold (`mem init`) e o `mem doctor --json` — não replica lógica do mem em Python (Decisão #2). O pin é a VERSION que viaja com o asset; o doctor compara a versão vendorizada no consumidor vs a do asset deste forge.

**Tech Stack:** Python 3.13, pytest (`.venv/bin/pytest` canônico), subprocess (via mem_call).

## Global Constraints

- **Reuso (Mand. #3):** rodar o scaffold/doctor do mem via `mem_call`, NÃO replicar `_scaffold`/`cmd_doctor` em Python. Copiar o asset espelhando `_install_hooks`.
- **Vendor target exato:** `.claude/bin/mem` — é onde `mem._resolve_binary` (engine/integrations/mem.py) procura. Divergir quebra a fronteira.
- **ADR-note Decisão 22** (sem dep runtime de outras skills): o mem é vendorizado como **snapshot pinado fork-and-forget** (Decisão 15), NÃO import runtime — o espírito da 22 se mantém. Entra como ADR-note no CHANGELOG `### Changed`/`### Added`, sem ritual de revisita.
- **Idempotência:** re-rodar `forge init` re-vendoriza sem corromper (overwrite do binário + scaffold idempotente do mem).
- NÃO tocar L1/L2/lifecycle (ondas anteriores/posteriores). NÃO `git push`/PR.
- `.venv/bin/pytest` canônico. Baseline: 10 falhas pré-existentes em `test_claude_rules_system.py` (débito Fase 0) — count não pode subir.
- Voz mentor calmo.

---

### Task 1: `_vendor_mem` — copiar asset + scaffold via mem_call

**Files:**
- Modify: `engine/utils/paths.py` (helpers de path do asset + vendored)
- Modify: `engine/init.py` (`_vendor_mem` + wire em `_run_pipeline`)
- Test: `tests/integration/test_init_vendor_mem.py` (novo) ou estende um test de init existente

**Interfaces:**
- Produces: `paths.mem_asset_path() -> Path` (`forge_home() / "engine" / "assets" / "mem" / "mem"`); `paths.mem_asset_version_path() -> Path` (`.../VERSION`); `paths.vendored_mem_path(project_root) -> Path` (`claude_dir(project_root) / "bin" / "mem"`); `init._vendor_mem(project_root) -> bool` (True se vendorizou).

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_init_vendor_mem.py
import os, stat
from pathlib import Path
from engine import init
from engine.utils import paths

def test_vendor_mem_copies_binary_and_scaffolds(tmp_path, monkeypatch):
    # Projeto consumidor limpo com um .git pra find_project_root.
    (tmp_path / ".git").mkdir()
    monkeypatch.delenv("FORGE_HOME", raising=False)  # usa o fallback p/ o repo real
    init._vendor_mem(tmp_path)
    vendored = paths.vendored_mem_path(tmp_path)
    assert vendored.is_file(), "binário do mem não vendorizado"
    assert vendored.stat().st_mode & stat.S_IXUSR, "mem vendorizado não é executável"
    # scaffold do mem: gitignore do mem.db + índice no AGENTS.md
    gi = (tmp_path / ".gitignore").read_text() if (tmp_path / ".gitignore").exists() else ""
    assert "mem.db" in gi
    assert (tmp_path / "AGENTS.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/integration/test_init_vendor_mem.py -v`
Expected: FAIL — `AttributeError: module 'engine.init' has no attribute '_vendor_mem'`.

- [ ] **Step 3: Add path helpers**

```python
# engine/utils/paths.py
def mem_asset_path() -> Path:
    """Asset embutido do mem (binário) dentro do FORGE_HOME."""
    return forge_home() / "engine" / "assets" / "mem" / "mem"

def mem_asset_version_path() -> Path:
    """VERSION do asset embutido do mem."""
    return forge_home() / "engine" / "assets" / "mem" / "VERSION"

def vendored_mem_path(project_root: Path) -> Path:
    """Binário do mem vendorizado no consumidor — .claude/bin/mem."""
    return claude_dir(project_root) / "bin" / "mem"
```

- [ ] **Step 4: Implement `_vendor_mem` (espelha `_install_hooks`)**

```python
# engine/init.py
import shutil, stat
from engine.utils.paths import mem_asset_path, mem_asset_version_path, vendored_mem_path
from engine.integrations.mem import mem_call

def _vendor_mem(project_root: Path) -> bool:
    """Vendoriza o mem no consumidor: copia o asset → .claude/bin/mem (755) +
    a VERSION (pin), e roda o scaffold do mem (gitignore mem.db*, índice no
    AGENTS.md) via a fronteira mem_call. Reusa o scaffold do próprio mem
    (Decisão #2) em vez de replicá-lo. Idempotente."""
    asset = mem_asset_path()
    if not asset.is_file():
        return False
    dst = vendored_mem_path(project_root)
    ensure_dir(dst.parent)
    shutil.copy2(asset, dst)
    dst.chmod(0o755)
    version = mem_asset_version_path()
    if version.is_file():
        shutil.copy2(version, dst.parent / "mem.version")
    # Scaffold idempotente via a fronteira (mem init não aceita --json).
    mem_call(project_root, ["init"], json=False)
    return True
```
Wire em `_run_pipeline` (junto do bloco de hooks, ~linha 2228, ANTES de qualquer passo que use mem):
```python
        _vendor_mem(project_root)
```

- [ ] **Step 5: Run test + rapid lane**

Run: `.venv/bin/pytest tests/integration/test_init_vendor_mem.py -v && .venv/bin/pytest -m "not integration and not e2e" -q | tail -1`
Expected: PASS; rapid sem regressão.

- [ ] **Step 6: Commit**

```bash
git add engine/utils/paths.py engine/init.py tests/integration/test_init_vendor_mem.py
git commit -m "feat(init): vendoriza o mem no consumidor (.claude/bin/mem + scaffold)"
```

---

### Task 2: `forge doctor` — categoria mem + drift do pin

**Files:**
- Modify: `engine/doctor.py` (nova categoria/check mem)
- Test: `tests/unit/test_doctor_mem.py` (novo) ou estende test de doctor

**Interfaces:**
- Consumes: `paths.vendored_mem_path`, `paths.mem_asset_version_path`, `mem_call`.
- CONVENÇÃO REAL do doctor (scoutada): categorias retornam `_CategoryReport(title: str, checks: list[_Check])`; `_Check(name, status, message="", remediation="")`; status são as constantes `_STATUS_OK`/`_STATUS_WARN`/`_STATUS_FAIL` (já no módulo); `_CategoryReport.worst` deriva o pior status. Categorias entram em `_all_categories` (engine/doctor.py:224-248). Já existem `_check_memory_l1`/`_check_memory_l2` — a categoria nova é distinta ("mem", o binário vendorizado).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_doctor_mem.py
from engine import doctor

def test_check_mem_fails_when_not_vendored(tmp_path):
    (tmp_path / ".git").mkdir()
    report = doctor._check_mem(tmp_path)            # -> _CategoryReport
    assert report.title == "mem"
    assert report.worst == doctor._STATUS_FAIL      # sem vendor → fail (não silencioso)
    assert any("vendor" in c.name for c in report.checks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_doctor_mem.py -v`
Expected: FAIL — `AttributeError: module 'engine.doctor' has no attribute '_check_mem'`.

- [ ] **Step 3: Implement `_check_mem` (convenção `_CategoryReport`/`_Check`)**

```python
# engine/doctor.py  (imports no topo do módulo)
from engine.integrations.mem import mem_call
from engine.utils.paths import vendored_mem_path, mem_asset_version_path

def _check_mem(project_root: Path) -> _CategoryReport:
    """Categoria 'mem': vendorização + saúde (mem doctor) + drift do pin
    (VERSION vendorizada vs a do asset deste forge). Reusa a fronteira mem_call."""
    vendored = vendored_mem_path(project_root)
    if not vendored.is_file():
        return _CategoryReport("mem", [_Check(
            name="vendored", status=_STATUS_FAIL,
            message="mem não vendorizado em .claude/bin/mem",
            remediation="rode `forge init` ou `forge reconfigure`")])
    checks: list[_Check] = [_Check("vendored", _STATUS_OK, "mem vendorizado em .claude/bin/mem")]
    res = mem_call(project_root, ["doctor"])
    if res.found and res.exit_code == 0:
        checks.append(_Check("health", _STATUS_OK, "mem doctor ok"))
    else:
        checks.append(_Check("health", _STATUS_WARN,
                             f"mem doctor reportou problema: {(res.stderr or '')[:120]}"))
    pin = vendored.parent / "mem.version"
    asset_v = mem_asset_version_path()
    if pin.is_file() and asset_v.is_file():
        vp, va = pin.read_text().strip(), asset_v.read_text().strip()
        if vp != va:
            checks.append(_Check("pin", _STATUS_WARN,
                                 f"drift: vendorizado {vp} vs asset {va}",
                                 remediation="rode `forge reconfigure` pra atualizar o mem"))
        else:
            checks.append(_Check("pin", _STATUS_OK, f"pin alinhado ({vp})"))
    return _CategoryReport("mem", checks)
```
Adicionar `_check_mem(project_root)` ao bloco `scope == "full"` de `_all_categories` (engine/doctor.py:230-247), junto das outras categorias full.

- [ ] **Step 4: Run test + rapid lane**

Run: `.venv/bin/pytest tests/unit/test_doctor_mem.py -v && .venv/bin/pytest -m "not integration and not e2e" -q | tail -1`
Expected: PASS; rapid sem regressão.

- [ ] **Step 5: Commit**

```bash
git add engine/doctor.py tests/unit/test_doctor_mem.py
git commit -m "feat(doctor): categoria mem (saúde via mem doctor + drift do pin)"
```

---

### Task 3: Doc-sync + ADR-note Decisão 22

**Files:**
- Modify: `CHANGELOG.md` (Added: init vendoriza mem + doctor mem; ADR-note Decisão 22)
- Modify: `docs/design/05-filesystem-layout.md` (`.claude/bin/mem`), `docs/design/06-command-surface.md` (doctor mem)
- Modify: `docs/guides/getting-started.md` / `docs/guides/dot-claude-reference.md` (se citam o layout do init) — enumerar via grep, só se relevante
- **NÃO tocar:** históricos/congelados (08-session-handoff, docs/reports, docs/superpowers, docs/design/outputs)

**Interfaces:** nenhuma (doc-sync).

- [ ] **Step 1: CHANGELOG (Unreleased, voz mentor calmo)**

```markdown
### Added
- `forge init` vendoriza o mem no consumidor: copia o asset embutido pra
  `.claude/bin/mem` (executável), roda o scaffold do mem (gitignore `mem.db*`,
  índice no `AGENTS.md`) via a fronteira `mem_call`. `forge doctor` ganha a
  categoria `mem` (saúde via `mem doctor` + drift do pin vendorizado vs asset).

### Changed
- ADR-note Decisão 22 (sem dep runtime de outras skills): o mem é vendorizado
  como snapshot pinado fork-and-forget (Decisão 15), não import runtime — o
  espírito da 22 se mantém. Sem revisita formal (não contradiz a decisão locked).
```

- [ ] **Step 2: docs** — atualizar `05-filesystem-layout.md` (incluir `.claude/bin/mem` no layout) e `06-command-surface.md` (categoria mem do doctor). Grep `docs/` por menções ao init/doctor que precisem do novo passo; atualizar só prosa atual (não históricos).

- [ ] **Step 3: Commit** (git add com PATHS EXPLÍCITOS — nunca `git add docs/`)

```bash
git add CHANGELOG.md docs/design/05-filesystem-layout.md docs/design/06-command-surface.md
git commit -m "docs(vendor): doc-sync init vendoriza mem + doctor mem + ADR-note Dec.22"
```
