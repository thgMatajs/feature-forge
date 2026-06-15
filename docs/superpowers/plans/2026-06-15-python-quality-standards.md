# Python Quality Standards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Worktree:** Este plano executa em worktree isolada. O orchestrator invoca `superpowers:using-git-worktrees` (branch `feat/python-quality-standards`) antes de despachar tasks.

**Goal:** Estabelecer gates de qualidade Python strict via ruff (lint + format) + mypy strict no pré-commit, e documentar convenções Python para subagentes em `.claude/rules/python.md`.

**Architecture:** Migração em 4 passos que protege o baseline de 1113 tests: (1) adicionar ruff config + auto-fix no código existente, (2) ativar mypy strict com amortização por módulo para violações pré-existentes, (3) conectar ruff + mypy no hook pré-commit, (4) criar o doc de rules para AI. Cada passo é um commit atômico. A amortização mypy usa `[[tool.mypy.overrides]]` por módulo com `ignore_errors = true` para que código novo/tocado seja sempre strict enquanto o legado diminui organicamente.

**Tech Stack:** Python 3.11+, ruff ≥ 0.4, mypy ≥ 1.8, pytest, bash (pre-commit hook)

---

### Task 1: pyproject.toml — add ruff config + update dev deps

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read current pyproject.toml**

```bash
cat pyproject.toml
```

Note o bloco `[tool.mypy]` atual e `[project.optional-dependencies]` — você vai inserir após eles.

- [ ] **Step 2: Add ruff to dev dependencies**

Em `[project.optional-dependencies]`, trocar:

```toml
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.1",
    "mypy>=1.8",
]
```

Por:

```toml
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.1",
    "mypy>=1.8",
    "ruff>=0.4",
]
```

- [ ] **Step 3: Add ruff config sections at end of pyproject.toml**

Append após o bloco `[tool.mypy]` existente:

```toml
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = [
    "E", "W",   # pycodestyle errors/warnings
    "F",        # pyflakes (undefined names, unused imports)
    "I",        # isort (import sorting)
    "UP",       # pyupgrade (moderniza sintaxe py311+)
    "B",        # flake8-bugbear (bugs comuns)
    "SIM",      # flake8-simplify
    "RUF",      # ruff-specific rules
    "N",        # pep8-naming
]
ignore = [
    "E501",     # line length (ruff format cuida disso)
    "B008",     # function calls in default args (legítimo em alguns casos)
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["N802", "N803"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

- [ ] **Step 4: Install ruff**

```bash
pip install "ruff>=0.4"
```

Expected: instala sem erros.

- [ ] **Step 5: Verify ruff runs (informational)**

```bash
ruff --version
ruff check . 2>&1 | tail -5
```

Expected: versão impressa, violations listadas (esperado — Task 2 corrige).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml
git commit -m "chore(python-quality): add ruff config + dev dep to pyproject.toml"
```

---

### Task 2: ruff auto-fix — clean up existing codebase

**Files:**
- Modify: múltiplos arquivos (auto-detectados pelo ruff)

- [ ] **Step 1: Run ruff auto-fix**

```bash
ruff check --fix .
```

Expected: ruff modifica arquivos e imprime o que corrigiu. Algumas violations podem restar (as que ruff não auto-corrige).

- [ ] **Step 2: Run ruff format**

```bash
ruff format .
```

Expected: formata todos os arquivos Python para 100 chars com double quotes.

- [ ] **Step 3: Check remaining violations**

```bash
ruff check .
```

Se violations restarem, corrija manualmente. Casos comuns não auto-fixáveis:

- `N803` (argument name should be lowercase): renomear argumento na assinatura
- `N806` (variable in function should be lowercase): renomear variável local
- `B006` (mutable default argument): mudar `def f(x=[])` para `def f(x: list | None = None): if x is None: x = []`

Se não restar nenhuma violation, skip o fix manual.

- [ ] **Step 4: Verify pytest baseline**

```bash
pytest -m "not integration and not e2e" --tb=short -q 2>&1 | tail -10
```

Expected: mesmo test count de antes, todos passando. Se algum test falhar, investigue antes de commitar — a mudança do ruff quebrou algo.

- [ ] **Step 5: Commit all ruff-changed files**

```bash
git add -u
git commit -m "chore(python-quality): apply ruff auto-fix to existing codebase"
```

---

### Task 3: mypy strict + amortization

**Files:**
- Modify: `pyproject.toml` (seção mypy)
- Modify: `docs/design/04-pending.md`

- [ ] **Step 1: Update mypy section in pyproject.toml**

Substituir o bloco `[tool.mypy]` atual:

```toml
[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
no_strict_optional = true
warn_unused_ignores = true
files = ["engine", "validators"]
# Advisory mode: errors are reported but do not gate CI. Rollout per-module
# plan tracked in docs/design/04-pending.md.
```

Por:

```toml
[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true
warn_unused_ignores = true
files = ["engine", "validators"]
# strict = true activa: disallow_untyped_defs, disallow_incomplete_defs,
# check_untyped_defs, disallow_untyped_decorators, warn_return_any,
# no_implicit_optional, strict_optional, warn_redundant_casts.
# Módulos com violações pré-existentes são deferidos via [[tool.mypy.overrides]]
# abaixo. Arquivos novos devem passar strict sem ignore.
```

- [ ] **Step 2: Run mypy and capture failing modules**

```bash
mypy 2>&1 | tee /tmp/mypy-out.txt; echo "mypy exit: $?"
```

Expected: muitos erros (esperado). Anotar o exit code.

- [ ] **Step 3: Extract unique failing module names**

```bash
grep "^engine\|^validators" /tmp/mypy-out.txt \
  | cut -d: -f1 \
  | sed 's|\.py$||; s|/|.|g' \
  | sort -u
```

Output exemplo:
```
engine.cards.loader
engine.plan
validators.check_cyclomatic_complexity
```

- [ ] **Step 4: Add overrides for each failing module**

No fim de `pyproject.toml`, adicionar um bloco usando a forma de lista:

```toml
# --- mypy strict amortization (generated 2026-06-15) ---
# Remova um módulo desta lista ao tocá-lo em qualquer task — resolva type errors antes de commitar.
[[tool.mypy.overrides]]
module = [
    "engine.plan",
    "engine.cards.loader",
    # ... preencher com a lista real do Step 3
]
ignore_errors = true
```

Substitua os exemplos acima pela lista real gerada no Step 3.

- [ ] **Step 5: Verify mypy now passes**

```bash
mypy
```

Expected: exit 0 (`Success: no issues found` ou similar).

- [ ] **Step 6: Add deferred modules gap to docs/design/04-pending.md**

Adicionar seção nova (ou ao fim do arquivo):

```markdown
## Python quality — mypy strict amortization

Adicionado 2026-06-15. Módulos abaixo têm `ignore_errors = true` em `pyproject.toml`
por violações pré-existentes no momento da adoção de strict.

**Regra:** ao tocar qualquer destes módulos numa task, remova-o do override e resolva
os type errors antes de commitar. A lista diminui organicamente.

Módulos deferidos (gerados 2026-06-15):
- `engine.plan`
- `engine.cards.loader`
- ... (preencher com lista real do Step 3)

Tracking: módulos resolvidos marcados com ✅.
```

Substituir os exemplos pela lista real do Step 3.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml docs/design/04-pending.md
git commit -m "chore(python-quality): mypy strict amortization — $(grep -c 'engine\|validators' /tmp/mypy-out.txt | head -1 || echo 'N') modules deferred"
```

(Use a contagem real de módulos únicos na mensagem.)

---

### Task 4: pre-commit hook — add ruff + mypy gates

**Files:**
- Modify: `.claude/hooks/pre-commit-feature-forge.sh`

- [ ] **Step 1: Read the current hook**

```bash
cat .claude/hooks/pre-commit-feature-forge.sh
```

Note onde o arquivo termina (antes de `exit 0` ou fim de arquivo).

- [ ] **Step 2: Add Python quality gates block**

Inserir o bloco abaixo antes do `exit 0` final (ou no fim do arquivo se não houver exit explícito):

```bash
# ─── Python quality gates ──────────────────────────────────────────────────
if command -v ruff &>/dev/null; then
    ruff check . || {
        echo "🛑 ruff lint falhou — rode: ruff check --fix ." >&2
        exit 1
    }
    ruff format --check . || {
        echo "🛑 ruff format diff detectado — rode: ruff format ." >&2
        exit 1
    }
else
    echo "⚠️  ruff não instalado — pip install 'ruff>=0.4'" >&2
fi

if command -v mypy &>/dev/null; then
    mypy || {
        echo "🛑 mypy strict falhou" >&2
        exit 1
    }
else
    echo "⚠️  mypy não instalado — pip install 'mypy>=1.8'" >&2
fi
```

- [ ] **Step 3: Verify bash syntax**

```bash
bash -n .claude/hooks/pre-commit-feature-forge.sh
```

Expected: sem output (sintaxe OK).

- [ ] **Step 4: Smoke test — create file with ruff violation**

```bash
cat > test_ruff_viol_DELETE_ME.py << 'EOF'
import os
x=1
EOF
git add test_ruff_viol_DELETE_ME.py
```

- [ ] **Step 5: Verify hook blocks commit**

```bash
git commit -m "test: should be blocked" 2>&1 | head -5
```

Expected: output contém "🛑 ruff lint falhou" e commit NÃO acontece.

- [ ] **Step 6: Clean up test file**

```bash
git restore --staged test_ruff_viol_DELETE_ME.py
rm test_ruff_viol_DELETE_ME.py
```

- [ ] **Step 7: Commit**

```bash
git add .claude/hooks/pre-commit-feature-forge.sh
git commit -m "feat(python-quality): add ruff+mypy strict gates to pre-commit hook"
```

---

### Task 5: .claude/rules/python.md + README update

**Files:**
- Create: `.claude/rules/python.md`
- Modify: `.claude/rules/README.md`

- [ ] **Step 1: Create .claude/rules/python.md with exact content below**

```markdown
# Python — guia de qualidade

Mandamento #2 (verde antes de "pronto") + tooling layer (ruff + mypy strict).
Leia este rule antes de qualquer task que toque `engine/` ou `validators/`.

## 1. Formatação e estilo

- `ruff format` é lei. Nunca formatar manualmente.
- `from __future__ import annotations` em todo arquivo (padrão do projeto).
- Line length: 100 caracteres.
- Double quotes para strings.
- Sintaxe py311+: `X | Y` em vez de `Optional[X]`, `list[str]` em vez de `List[str]`.

Comandos:

```bash
ruff format .          # formata tudo
ruff check --fix .     # corrige lint auto-fixável
ruff check .           # verifica sem fix (use antes de commit)
```

## 2. Tipagem

- Type hints obrigatórios em toda função pública e privada — sem exceção.
- Return type obrigatório, inclusive `-> None`.
- Sem `Any` nu — se necessário: `# type: ignore[<code>] — <razão concreta>`.
- `TypeAlias` explícito quando tipo complexo aparece em mais de um lugar.
- Union com `|`, não com `Union[]` nem `Optional[]`.

Correto:

```python
from __future__ import annotations
from typing import TypeAlias

PathOrStr: TypeAlias = str | Path

def process(items: list[str]) -> dict[str, int]:
    ...

def noop() -> None:
    ...
```

Errado:

```python
def process(items):          # sem type hint
def noop():                  # sem return type
x: Optional[str] = None     # use str | None
y: Union[int, str] = 0      # use int | str
```

## 3. Arquitetura e módulos

- `engine/` → handlers de comando. Handler = thin dispatcher; lógica em helpers internos.
- `validators/` → SEMPRE consulta `_gate_infra.py`, `_diff.py`, `_common.py` antes de criar helper novo (Mandamento #3 + `reuse.md`).
- Sem import circular: engine não importa de validators; validators não importa de engine.
- Decision 22: engine não importa de skills ou superpowers em runtime — portability load-bearing.
- `__init__.py` sem side-effects. Re-exports apenas quando necessário e explícito.

## 4. Error handling

- `except SomeSpecificError:` sempre. Nunca `except:` nu nem `except Exception:` sem re-raise imediato.
- Regra H-03 (remediada junho 2026, 18 sites): narrow except é mandamento.
- Não silenciar com `pass` — se ignorar é intencional, comentar o motivo.

Correto:

```python
try:
    result = parse_yaml(path)
except FileNotFoundError:
    raise ConfigError(f"config not found: {path}") from None
except yaml.YAMLError as exc:
    raise ConfigError(f"invalid yaml in {path}: {exc}") from exc
```

Errado:

```python
try:
    result = parse_yaml(path)
except Exception:    # too broad
    pass             # silencia sem motivo
except:              # bare except — proibido
    return None
```

## 5. Funções e complexidade

- CC gate threshold: 10 (Python via Radon). Função acima de 10 → refatorar antes de submitar.
- Funções privadas com prefixo `_`. Públicas apenas se forem API do módulo.
- Uma responsabilidade por função. Se o nome precisa de "e" (ex: `parse_and_validate`), separe.
- Sem side-effects em funções com nome de query (`get_*`, `find_*`, `list_*`).

```bash
radon cc engine/ -s -a -nb    # lista funções com CC > threshold
```

## 6. Antipadrões observados (histórico)

| Antipadrão | Contexto | Regra |
|---|---|---|
| Over-mock | M-01 pré-PR #9 | Mock só em boundaries externas; prefer comportamento real |
| Broad except | H-03, 18 sites, junho 2026 | `except SpecificError:` sempre |
| Constante hardcoded | `_SKIP_DIRS` phase | Usar config ou parâmetro, não constante inline |
| TODO/FIXME sem gap | vários | Referenciar gap em `docs/design/04-pending.md` |
| Módulo em `ignore_errors` | migração mypy | Remover override ao tocar módulo; resolver type errors na mesma task |

## Tooling pointer

Configuração: `pyproject.toml` (`[tool.ruff]`, `[tool.mypy]`).
Gate pré-commit: `.claude/hooks/pre-commit-feature-forge.sh`.
Módulos mypy deferidos: `docs/design/04-pending.md §Python quality`.
```

- [ ] **Step 2: Add python.md row to .claude/rules/README.md**

Na tabela `## Map`, adicionar linha nova após a linha de `superpowers.md`:

```markdown
| [python.md](python.md) | Estilo, tipagem, arquitetura, antipadrões Python | em toda task que toca `engine/` ou `validators/` |
```

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/python.md .claude/rules/README.md
git commit -m "docs(rules): add python.md — style, architecture, antipatterns guide"
```

---

### Task 6: doc-sync — CHANGELOG + handoff

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/design/08-session-handoff.md`

- [ ] **Step 1: Add entries to CHANGELOG.md under ## [Unreleased]**

```markdown
### Added
- `[tool.ruff]` config em `pyproject.toml` — lint (E,W,F,I,UP,B,SIM,RUF,N) + format (100-char, double-quotes) gates
- `.claude/rules/python.md` — guia Python de estilo, tipagem, arquitetura e antipadrões para subagentes
- ruff + mypy strict gates em `.claude/hooks/pre-commit-feature-forge.sh`

### Changed
- `[tool.mypy]` em `pyproject.toml` promovido de advisory para `strict = true`; violações pré-existentes amortizadas via overrides por módulo (ver `docs/design/04-pending.md §Python quality`)
- `ruff>=0.4` adicionado a `[project.optional-dependencies] dev`
```

- [ ] **Step 2: Update docs/design/08-session-handoff.md**

Atualizar a linha `**Última atualização:**`:

```markdown
**Última atualização:** 2026-06-15 (v1.2-dev — python-quality-standards)
```

Atualizar `**Estado:**` para refletir que os gates Python estão ativos.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md docs/design/08-session-handoff.md
git commit -m "docs(sync): python-quality-standards — CHANGELOG + handoff update"
```
