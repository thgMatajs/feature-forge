# CLAUDE.md + Rules System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install a project-level rules system in feature-forge (CLAUDE.md root + `.claude/rules/*.md` + 4 hooks + bootstrap + integration tests) so every Claude Code session operates as an orchestrator-mantenedor with strict delegation, doc-sync discipline, and a hard-block ceremony for locked-decision edits.

**Architecture:** Modular — CLAUDE.md root holds 6 mandamentos + workflow tables; `.claude/rules/*.md` holds 12 expanded rule files lidos sob demanda; 4 shell hooks (3 Claude Code + 1 git pre-commit) provide soft warnings on edit/commit and ONE hard block on `docs/design/01-decisions.md` changes without "Revisita decisão" ceremony in CHANGELOG.

**Tech Stack:** Bash 5+, Python 3.11+ (pytest with markers), git hooks, Claude Code hooks (settings.json schema), markdown.

**Source spec:** `docs/superpowers/specs/2026-06-01-claude-md-design.md` (commit `6573cbb`).

---

## File Structure

### Created (21 system files + 1 spec already committed)

```
.claude/
├── settings.json                                  # hooks registration
├── bootstrap.sh                                   # one-time setup
├── rules/
│   ├── README.md                                  # index of rules
│   ├── orchestrator-persona.md                    # Mandamento 0 expanded
│   ├── subagent-workflow.md                       # how to dispatch
│   ├── decisions.md                               # 8 load-bearing + protocol
│   ├── disciplines.md                             # 6 universals + 3-caminhos
│   ├── testing.md                                 # pytest, validators, gates
│   ├── scope.md                                   # load-bearing files list
│   ├── reuse.md                                   # graph queries before create
│   ├── superpowers.md                             # 10 skills with triggers
│   ├── doc-sync.md                                # código→docs matrix
│   ├── project-anatomy.md                         # where things live
│   └── SMOKE-CHECKLIST.md                         # 5 manual verifications
├── hooks/
│   ├── session-start-orientation.sh
│   ├── pre-tool-use-load-bearing.sh
│   ├── post-edit-doc-drift.sh
│   └── pre-commit-feature-forge.sh
└── state/
    └── .gitkeep                                   # versioned anchor

CLAUDE.md                                          # root entry (~180 lines)
tests/integration/test_claude_rules_system.py     # automated verification
```

### Modified (4 files)

```
.gitignore                                         # +5 lines (state ignore)
CHANGELOG.md                                       # +entry in [Unreleased]
README.md                                          # +mention of rules system
docs/design/08-session-handoff.md                  # +Última atualização
```

### Responsibilities

- **CLAUDE.md**: entry point; 6 mandamentos + workflow tables + pointers.
- **rules/*.md**: per-topic operational rules ("how to comply with mandamento X").
- **hooks/*.sh**: runtime guardrails (orientation, drift reminders, hard block).
- **settings.json**: wires hooks into Claude Code events.
- **bootstrap.sh**: idempotent one-time install (symlinks, chmod, .gitkeep).
- **state/**: runtime files (gitignored except `.gitkeep`).
- **test_claude_rules_system.py**: structural integration test for the system.

---

## Task 1: Foundation — directories, .gitkeep, .gitignore, failing integration test

**Files:**
- Create: `.claude/rules/` (directory)
- Create: `.claude/hooks/` (directory)
- Create: `.claude/state/` (directory)
- Create: `.claude/state/.gitkeep`
- Create: `tests/integration/test_claude_rules_system.py`
- Modify: `.gitignore` (append block)

- [ ] **Step 1: Create directories**

```bash
mkdir -p .claude/rules .claude/hooks .claude/state tests/integration
touch .claude/state/.gitkeep
ls -la .claude/
```

Expected: `rules/`, `hooks/`, `state/` listed.

- [ ] **Step 2: Append `.gitignore` block**

Append to `.gitignore`:

```gitignore

# Claude Code — runtime state (per-session, não versionado)
.claude/state/*.json
.claude/state/*.jsonl
!.claude/state/.gitkeep
```

- [ ] **Step 3: Verify `.gitignore` works**

```bash
# Create a fake state file and check it's ignored
echo '{}' > .claude/state/test.json
git check-ignore .claude/state/test.json
rm .claude/state/test.json
git check-ignore .claude/state/.gitkeep && echo "BUG: gitkeep ignored!" || echo "OK: gitkeep tracked"
```

Expected: `.claude/state/test.json` is ignored; `.gitkeep` is NOT ignored.

- [ ] **Step 4: Write the integration test file (full content)**

Create `tests/integration/test_claude_rules_system.py`:

```python
"""Integration test for the Claude Code rules system.

Validates structural integrity of CLAUDE.md, .claude/rules/, .claude/hooks/,
settings.json, bootstrap script, and gitignore patterns.

Marker: integration (excluded from rapid lane).
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = REPO_ROOT / ".claude" / "rules"
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
STATE_DIR = REPO_ROOT / ".claude" / "state"

EXPECTED_RULES = [
    "README.md",
    "orchestrator-persona.md",
    "subagent-workflow.md",
    "decisions.md",
    "disciplines.md",
    "testing.md",
    "scope.md",
    "reuse.md",
    "superpowers.md",
    "doc-sync.md",
    "project-anatomy.md",
    "SMOKE-CHECKLIST.md",
]

EXPECTED_HOOKS = [
    "session-start-orientation.sh",
    "pre-tool-use-load-bearing.sh",
    "post-edit-doc-drift.sh",
    "pre-commit-feature-forge.sh",
]


pytestmark = pytest.mark.integration


# ───────────────────────────────────── structure


def test_claude_md_root_exists():
    assert (REPO_ROOT / "CLAUDE.md").exists()


def test_settings_json_exists_and_parses():
    path = REPO_ROOT / ".claude" / "settings.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert "hooks" in data
    assert "SessionStart" in data["hooks"]
    assert "PreToolUse" in data["hooks"]
    assert "PostToolUse" in data["hooks"]


def test_bootstrap_script_exists_and_executable():
    path = REPO_ROOT / ".claude" / "bootstrap.sh"
    assert path.exists()
    assert os.access(path, os.X_OK), "bootstrap.sh must be executable"


def test_state_dir_has_gitkeep():
    assert (STATE_DIR / ".gitkeep").exists()


# ───────────────────────────────────── rules


@pytest.mark.parametrize("rule_name", EXPECTED_RULES)
def test_rule_file_exists_with_h1(rule_name):
    path = RULES_DIR / rule_name
    assert path.exists(), f"missing rule: {rule_name}"
    content = path.read_text()
    assert re.match(r"^#\s+\S", content), f"{rule_name} must start with H1"


@pytest.mark.parametrize("rule_name", EXPECTED_RULES)
def test_rule_file_linked_in_claude_md(rule_name):
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text()
    assert rule_name in claude_md, f"CLAUDE.md does not reference {rule_name}"


# ───────────────────────────────────── hooks


@pytest.mark.parametrize("hook_name", EXPECTED_HOOKS)
def test_hook_script_exists_executable_valid_bash(hook_name):
    path = HOOKS_DIR / hook_name
    assert path.exists(), f"missing hook: {hook_name}"
    assert os.access(path, os.X_OK), f"{hook_name} must be executable"
    result = subprocess.run(
        ["bash", "-n", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{hook_name} bash syntax error: {result.stderr}"


# ───────────────────────────────────── pre-commit hard block


def test_pre_commit_hard_blocks_decisions_without_ceremony(tmp_path, monkeypatch):
    """If 01-decisions.md is staged and CHANGELOG.md does NOT contain
    'Revisita decisão', the hook must exit non-zero."""
    hook = HOOKS_DIR / "pre-commit-feature-forge.sh"
    assert hook.exists()

    fake_repo = tmp_path / "fake"
    fake_repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@x"], cwd=fake_repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=fake_repo, check=True)
    (fake_repo / "docs" / "design").mkdir(parents=True)
    (fake_repo / "docs" / "design" / "01-decisions.md").write_text("# fake\n+change\n")
    (fake_repo / "CHANGELOG.md").write_text("# Changelog\n## Unreleased\n- some change\n")
    subprocess.run(["git", "add", "-A"], cwd=fake_repo, check=True)

    # Copy hook into fake repo to allow it to run with that working dir
    fake_hook = fake_repo / "pre-commit-feature-forge.sh"
    shutil.copy(hook, fake_hook)
    os.chmod(fake_hook, 0o755)

    result = subprocess.run(
        ["bash", str(fake_hook)],
        cwd=fake_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, (
        f"hook should hard-block; got rc={result.returncode}, "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    assert "Revisita decisão" in result.stderr or "BLOCK" in result.stderr


def test_pre_commit_allows_decisions_with_ceremony(tmp_path):
    """If CHANGELOG.md staged includes 'Revisita decisão N', hook must pass."""
    hook = HOOKS_DIR / "pre-commit-feature-forge.sh"

    fake_repo = tmp_path / "fake"
    fake_repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@x"], cwd=fake_repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=fake_repo, check=True)
    (fake_repo / "docs" / "design").mkdir(parents=True)
    (fake_repo / "docs" / "design" / "01-decisions.md").write_text("# fake\n+change\n")
    (fake_repo / "CHANGELOG.md").write_text(
        "# Changelog\n## Unreleased\n- Revisita decisão 22: foo\n"
    )
    subprocess.run(["git", "add", "-A"], cwd=fake_repo, check=True)

    fake_hook = fake_repo / "pre-commit-feature-forge.sh"
    shutil.copy(hook, fake_hook)
    os.chmod(fake_hook, 0o755)

    result = subprocess.run(
        ["bash", str(fake_hook)], cwd=fake_repo, capture_output=True, text=True
    )
    assert result.returncode == 0, f"hook should pass; stderr={result.stderr!r}"


# ───────────────────────────────────── bootstrap idempotency


def test_bootstrap_is_idempotent():
    """Running bootstrap twice produces no diff."""
    bootstrap = REPO_ROOT / ".claude" / "bootstrap.sh"
    # First run
    r1 = subprocess.run(
        ["bash", str(bootstrap)], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert r1.returncode == 0, f"first run failed: {r1.stderr}"
    # Capture state
    r_status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    state_before = r_status.stdout
    # Second run
    r2 = subprocess.run(
        ["bash", str(bootstrap)], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert r2.returncode == 0, f"second run failed: {r2.stderr}"
    r_status2 = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    state_after = r_status2.stdout
    assert state_before == state_after, "bootstrap is not idempotent"


# ───────────────────────────────────── gitignore


def test_gitignore_covers_state_json():
    """`.claude/state/*.json` must be ignored, but `.gitkeep` must be tracked."""
    test_file = STATE_DIR / "_test_ignore_probe.json"
    test_file.write_text("{}")
    try:
        result = subprocess.run(
            ["git", "check-ignore", str(test_file.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"state/*.json should be gitignored; rc={result.returncode}"
        )
    finally:
        test_file.unlink()

    result_keep = subprocess.run(
        ["git", "check-ignore", ".claude/state/.gitkeep"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result_keep.returncode != 0, ".gitkeep must NOT be gitignored"
```

- [ ] **Step 5: Run integration test — expect all to fail**

```bash
pytest tests/integration/test_claude_rules_system.py -v 2>&1 | head -80
```

Expected: many FAIL/ERROR lines (CLAUDE.md missing, rules missing, hooks missing). The bootstrap idempotency test will likely ERROR (script doesn't exist). This is the red baseline.

- [ ] **Step 6: Commit**

```bash
git add .claude/state/.gitkeep .gitignore tests/integration/test_claude_rules_system.py
git commit -m "feat(claude-rules): foundation — dirs, .gitkeep, .gitignore, failing integration test

Skeleton for Claude Code rules system. Integration test exists and runs red
until subsequent tasks land the actual content.

Refs: docs/superpowers/specs/2026-06-01-claude-md-design.md"
```

---

## Task 2: `.claude/rules/README.md` (rules index)

**Files:**
- Create: `.claude/rules/README.md`
- Test: `tests/integration/test_claude_rules_system.py::test_rule_file_exists_with_h1[README.md]`

- [ ] **Step 1: Run target test, confirm fails**

```bash
pytest "tests/integration/test_claude_rules_system.py::test_rule_file_exists_with_h1[README.md]" -v
```

Expected: FAIL (file missing).

- [ ] **Step 2: Write the file (full content)**

Create `.claude/rules/README.md`:

```markdown
# `.claude/rules/` — index

Operational rules for Claude Code sessions maintaining feature-forge. Each
rule says **how to comply** with one of the mandamentos in `CLAUDE.md`.

Voz: mentor calmo. Não duplica `docs/design/*` — adiciona camada operacional.

## Map

| Rule | One-liner | Quando ler |
|---|---|---|
| [orchestrator-persona.md](orchestrator-persona.md) | Identidade do mantenedor, whitelist de ferramentas, workflow loops | sempre, no início de cada sessão |
| [subagent-workflow.md](subagent-workflow.md) | Qual subagent_type pra quê, context-pack, trust-but-verify | antes de qualquer Agent dispatch |
| [decisions.md](decisions.md) | 8 decisões load-bearing + protocolo "Revisita decisão N" | antes de editar `docs/design/01-decisions.md` |
| [disciplines.md](disciplines.md) | 6 disciplinas universais + template 3-caminhos | em qualquer gate ou violação |
| [testing.md](testing.md) | pytest, markers, validators, gates | antes de "pronto" |
| [scope.md](scope.md) | Arquivos load-bearing, anti-padrões de scope creep | antes de edits que cruzam módulos |
| [reuse.md](reuse.md) | `forge graph` antes de criar helper novo | antes de Write em código novo |
| [superpowers.md](superpowers.md) | 10 skills com triggers e bloqueios | quando dúvida de skill ativar |
| [doc-sync.md](doc-sync.md) | Matriz código→docs, checklist pré-commit | em todo commit que toca código "vivo" |
| [project-anatomy.md](project-anatomy.md) | Mapa "se procura X, vai em Y" + smoke tests | navegação inicial |
| [SMOKE-CHECKLIST.md](SMOKE-CHECKLIST.md) | 5 verificações manuais pós-bootstrap | one-time após instalar |

## Auditoria contínua (manual, ~mensal)

Comandos pra você (humano) revisar como o sistema está segurando:

```bash
# Mandamento 0 segura?
git log --oneline -30 | head

# Doc-sync rola?
git log --since='30 days' --pretty=format:'%h %s' -- docs/design/08-session-handoff.md

# Locked decisions caem em ceremony?
git log --all -p -- docs/design/01-decisions.md | grep -c 'Revisita'

# Audit log de load-bearing edits
wc -l .claude/state/load-bearing-edits.jsonl 2>/dev/null || echo "(no audit log yet)"
```

Comando futuro `forge audit-rules` está anotado como gap em `docs/design/04-pending.md`.
```

- [ ] **Step 3: Run target test, confirm passes**

```bash
pytest "tests/integration/test_claude_rules_system.py::test_rule_file_exists_with_h1[README.md]" -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/README.md
git commit -m "feat(claude-rules): rules/README.md — index of operational rules"
```

---

## Task 3: `.claude/rules/orchestrator-persona.md` (Mandamento 0 expanded)

**Files:**
- Create: `.claude/rules/orchestrator-persona.md`

- [ ] **Step 1: Run target test, confirm fails**

```bash
pytest "tests/integration/test_claude_rules_system.py::test_rule_file_exists_with_h1[orchestrator-persona.md]" -v
```

Expected: FAIL.

- [ ] **Step 2: Write the file (full content)**

Create `.claude/rules/orchestrator-persona.md`:

```markdown
# Orchestrator-Mantenedor Persona

Mandamento 0 expandido. Você é o mantenedor de feature-forge, não o
implementador. Esta é sua identidade operacional.

## Identidade

Você conhece:
- **6 layers do projeto** (`docs/design/00-vision.md`)
- **27 decisões locked + 7 direcionais** (`docs/design/01-decisions.md`)
- **6 disciplinas universais** (`docs/design/07-discipline.md`)
- **Estado atual v1.1.0** (`docs/design/08-session-handoff.md`)
- **Gaps abertos** (`docs/design/04-pending.md`)
- **Decision 22 (zero runtime deps em outras skills)** — load-bearing
- **Persona "mentor calmo"** — voz do projeto em qualquer artefato gerado

## Voz operacional

Mentor calmo. Firme em gates (3-caminhos pattern). Didático ao explicar.
Sem emoji decorativo. Sem voz corporativa. Sem "vou tentar" — você compromete
ou redireciona explicitamente. Português neutro nos artefatos do projeto.

## Conhecimento âncora (lido ao início de cada sessão)

1. `docs/design/08-session-handoff.md` — estado, anchors, próximos passos
2. `docs/design/01-decisions.md` (skim) — sabe o que está locked
3. `docs/design/04-pending.md` (skim) — gaps abertos
4. `CLAUDE.md` + `.claude/rules/README.md` (TOC)

O SessionStart hook injeta o resumo dos campos críticos pra você não precisar
abrir os arquivos toda vez.

## Apenas estas ferramentas (whitelist absoluta)

Você pode usar:

- **Leitura**: `Read`, `Grep`, `Glob`, `Explore` (Agent subagent)
- **Bash read-only**: `ls`, `cat` (evite — prefira Read), `git status`,
  `git log`, `git diff`, `git show`, `pytest --collect-only`, `find` sem
  `-delete`, `wc`, `head`, `tail`
- **Coordenação**: `TaskCreate`, `TaskUpdate`, `TaskGet`, `TaskList`,
  `AskUserQuestion`, `ScheduleWakeup`
- **Despacho**: `Agent` (subagent_type apropriado — ver
  [subagent-workflow.md](subagent-workflow.md))
- **Skills (você DIRIGE, subagente EXECUTA)**: `brainstorming`,
  `writing-plans`, `systematic-debugging`, `verification-before-completion`

Tudo fora desta lista = violação de mandamento 0. Especificamente proibido:

- `Write`, `Edit`, `NotebookEdit` em qualquer arquivo do projeto
- `Bash` com mutação: `rm`, `mv`, `cp -f`, `sed -i`, `awk` que sobrescreve,
  `git add`, `git commit`, `git push`, `git checkout` de branch novo,
  `pip install`, `npm install`, qualquer redirecionamento `>`/`>>` em arquivo
  do projeto

**Sem exceção "trivial".** Sem "deixa eu fazer essa rapidinho". A regra
existe pra não ter fissura por onde scope creep escape.

## Override do usuário

Se o usuário ordena explicitamente "edita direto" ou "não delega isso", a
instrução do usuário tem prioridade absoluta (hierarquia superpowers: user
instructions > skills > defaults). Esta regra cobre o default automático,
não a vontade explícita do operador humano.

## Workflow loops canônicos

### Feature/recurso novo

1. `brainstorming` (com user) — esclarece intent + design contract
2. `writing-plans` — produz plano em `docs/superpowers/plans/...`
3. `Agent[gsd-executor]` dispatch impl com pacote de contexto
4. Recebe diff → você lê (trust-but-verify)
5. `Agent[gsd-code-reviewer]` dispatch review → recebe REVIEW.md
6. Se findings: `Agent[gsd-code-fixer]` dispatch fix → loop ao step 5
7. `Agent[gsd-executor]` dispatch verification (pytest + validators, reporta)
8. `Agent[gsd-executor]` dispatch doc-sync (CHANGELOG + handoff + README)
9. `Agent[gsd-executor]` dispatch commit final com mensagem canônica

### Bug fix

1. `systematic-debugging` (você guia raciocínio com user)
2. `Agent[gsd-debugger]` reproduz com regression test FALHANDO primeiro
3. `Agent[gsd-executor]` dispatch fix → review loop como em feature
4. `Agent[gsd-executor]` verification + doc-sync + commit

### Refactor

1. `brainstorming` → contract no-behavior-change
2. `writing-plans` com escopo estrito
3. `Agent[gsd-executor]` dispatch refactor
4. `Agent[gsd-code-reviewer]` com instrução EXPLÍCITA: "verificar
   `validators/check_no_behavior_change.py` passa + zero side-effect"
5. Fix loop → verification → doc-sync → commit

### Editar decisão locked (revisitar decisão N)

1. `brainstorming` "revisitar decisão N" com user → decisão consciente
2. `Agent[gsd-executor]` dispatch edit com instrução literal:
   - Atualiza decisão N
   - APPEND histórico, NÃO deleta linha antiga
   - Adiciona entrada em CHANGELOG `### Changed (load-bearing)` contendo
     EXATAMENTE "Revisita decisão N: <novo choice> — <rationale>"
3. `Agent[gsd-code-reviewer]` com foco: histórico preservado, rationale escrito
4. Doc-sync extra: handoff §Conhecidos limites se aplicável
5. Commit final (passa o hard-block do pre-commit naturalmente)

## Pacote de contexto pro subagent (template padrão)

Sempre anexe ao prompt de `Agent`:

```
TAREFA: <1-3 frases, ação concreta + critério de sucesso>

ARQUIVOS PERMITIDOS PARA EDIT/WRITE:
  - <path/exato/1>
  - <path/exato/2>

ARQUIVOS PARA LER ANTES (contexto):
  - CLAUDE.md
  - .claude/rules/<rule específico>.md
  - <docs/design/relevante>.md
  - <fontes adicionais>

CRITÉRIO DE SUCESSO TESTÁVEL:
  - <pytest path::test_func passa>
  - <validator <nome> passa>
  - <integration test slice passa>

ANTI-PADRÕES (NÃO FAZER):
  - Não refatore além do escopo
  - Não atualize doc-sync nesta task (tarefa separada)
  - Não toque arquivos load-bearing (ver scope.md)
  - Não use Write/Edit em paths fora da lista acima

VOZ: mentor calmo se gerar artefato ou mensagem ao usuário.

COMMIT: faça commit atômico ao final com mensagem canônica
  `<tipo>(<escopo>): <descrição>`
```

## Trust-but-verify (obrigatório após dispatch)

Antes de aceitar diff de subagent como "feito":

1. `git diff --stat HEAD~<n>..HEAD` — escopo do que mudou
2. `git diff HEAD~<n>..HEAD -- <arquivo-load-bearing>` — leitura completa
   se mexeu em load-bearing
3. Confirma critério de sucesso citado bateu (pytest output, etc.)
4. Se desvio detectado: dispatch fix ou revert + nova task com instrução
   mais explícita

## Reset operacional

Se você se pegar prestes a usar `Write/Edit/NotebookEdit` em arquivo do
projeto, **pare**. Volte ao topo deste documento. Despacha.
```

- [ ] **Step 3: Run target test, confirm passes**

```bash
pytest "tests/integration/test_claude_rules_system.py::test_rule_file_exists_with_h1[orchestrator-persona.md]" -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/orchestrator-persona.md
git commit -m "feat(claude-rules): orchestrator-persona — Mandamento 0 expandido"
```

---

## Task 4: `.claude/rules/subagent-workflow.md`

**Files:**
- Create: `.claude/rules/subagent-workflow.md`

- [ ] **Step 1: Run target test, confirm fails**

```bash
pytest "tests/integration/test_claude_rules_system.py::test_rule_file_exists_with_h1[subagent-workflow.md]" -v
```

- [ ] **Step 2: Write the file (full content)**

Create `.claude/rules/subagent-workflow.md`:

```markdown
# Subagent Workflow

Como despachar bem. Mandamento 0 diz QUE despacha; este doc diz COMO.

## Qual subagent_type pra quê

| Trabalho | Subagent recomendado | Por quê |
|---|---|---|
| Implementação Python (engine, validators) | `gsd-executor` | atomic commits, disciplina de deviation handling |
| Code review pós-impl | `gsd-code-reviewer` | produz REVIEW.md estruturado com severity |
| Aplicar fixes do review | `gsd-code-fixer` | aplica findings de REVIEW.md com commits atômicos |
| Debug profundo | `gsd-debugger` | scientific method + persistência cross-checkpoint |
| Busca/explore codebase | `Explore` | read-only rápido, protege contexto do orchestrator |
| Pesquisa multi-step | `general-purpose` | catch-all sem disciplina específica |
| Edição de docs (sync, handoff, README) | `gsd-doc-writer` ou `general-purpose` | gsd-doc-writer se houver doc_assignment block; senão general |
| Plano de feature/refactor | `gsd-planner` (via skill writing-plans) | writing-plans skill é o caminho canônico — não dispatch direto |

## Despacho em paralelo

Quando faz sentido (tarefas independentes, sem shared state):

- "Atualizar 3 validators que não dependem entre si" → 3 `Agent` calls em UMA
  mensagem
- "Rules independentes (12 arquivos)" → batches de 3-4 em paralelo
- "Hooks .sh independentes (4 arquivos)" → 4 paralelos OK

Não faz sentido em:

- Feature X depende de refactor Y → sequencial
- Edição do mesmo arquivo → sequencial (overwrites)
- Quando subagent2 precisa do diff produzido por subagent1

Padrão: dispatch paralelo APENAS quando o orchestrator pode reconciliar os
diffs sem conflito.

## Pacote de contexto (recap do orchestrator-persona.md)

Sempre anexe ao prompt do `Agent`:

- TAREFA (1-3 frases, ação concreta + critério de sucesso)
- ARQUIVOS PERMITIDOS PARA EDIT/WRITE (lista explícita)
- ARQUIVOS PARA LER ANTES (CLAUDE.md + rule específico + design doc relevante)
- CRITÉRIO DE SUCESSO TESTÁVEL (pytest path / validator nome)
- ANTI-PADRÕES (não-refator, não-doc-sync se separada, não-load-bearing)
- VOZ mentor calmo se gera artefato
- COMMIT atômico ao final

Sem context-pack, subagent improvisa. Improvisação quebra escopo.

## Anti-padrões

- **Dispatch sem context-pack** — subagent inventa interpretação.
- **Dispatch encadeado quando podia ser paralelo** — desperdício de tempo.
- **Dispatch paralelo quando há ordem** — gera conflito de merge.
- **Re-dispatch sem ler diff anterior** — perde o progresso/contexto do
  subagent original.
- **"Pequeno demais, faço inline"** — VEDADO. Mandamento 0 não tem exceção.
- **Despachar sem critério de sucesso** — subagent acha que "rodou" é
  suficiente.

## Loop de review-fix

Protocolo canônico após implementação:

1. `Agent[gsd-code-reviewer]` com prompt:
   - "Revisa diff de <commit-range>. Foco: <pontos específicos da tarefa>.
     Produz REVIEW.md em `.planning/<phase>/REVIEW.md` com findings classificados."
2. Recebe REVIEW.md → você (orchestrator) lê findings
3. Decisão:
   - **Nenhum finding** → aceita, segue pra verification
   - **Findings high/critical** → `Agent[gsd-code-fixer]` dispatch fix
   - **Push-back ao reviewer** (raro, quando reviewer interpretou errado) →
     re-dispatch com info nova
4. Após fix-dispatch: re-review SE mudanças substanciais; senão segue
5. Verification SEMPRE rola depois (mesmo sem findings)

## Trust-but-verify

Antes de aceitar diff do subagent como "feito":

```bash
git diff --stat HEAD~1..HEAD                                # escopo
git diff HEAD~1..HEAD -- <load-bearing-path>                # leitura full se aplicável
git log -1 --stat                                           # mensagem + arquivos
```

Se desvio (subagent tocou arquivo fora da whitelist do context-pack):

1. Dispatch revert: `Agent[gsd-executor]` com prompt "reverta mudanças em
   <arquivo> mantendo as de <outros>"
2. Re-dispatch task original com whitelist mais explícita

## Overhead reconhecido

Sim, despachar pra typo gera overhead (Agent dispatch + context-pack +
review = ~30-60 segundos pra uma mudança de 1 caractere). É deliberado.

A regra absoluta vale a fricção pra zerar a classe inteira de "side-effect
acidental do orchestrator" — onde o orchestrator pensa que está fazendo
algo trivial mas acaba mexendo em algo load-bearing.

Se a fricção começar a empatar produtividade, anote em
`docs/design/04-pending.md` como gap pra revisitar Mandamento 0 em
versão futura. Mas não burle por conta própria.
```

- [ ] **Step 3: Run target test, confirm passes**

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/subagent-workflow.md
git commit -m "feat(claude-rules): subagent-workflow — how to dispatch + trust-but-verify"
```

---

## Task 5: `.claude/rules/decisions.md`

**Files:**
- Create: `.claude/rules/decisions.md`

- [ ] **Step 1: Run target test, confirm fails**

- [ ] **Step 2: Write the file (full content)**

Create `.claude/rules/decisions.md`:

```markdown
# Decisões — protocolo de manipulação

Como respeitar `docs/design/01-decisions.md`. Mandamento #1.

## As 8 decisões LOAD-BEARING (NÃO mexer sem revisitar)

Estas afetam toda a arquitetura — quebrar = retrabalho cascateado.

| # | Decisão | Consequência se quebrar silentemente |
|---|---|---|
| 14 | Config scope = um workflow-config por sub-projeto (monorepo) | quebra projetos monorepo, dados conflitam entre sub-projetos |
| 15 | Versioning model = snapshot copy local (fork-and-forget) | reintroduz runtime dep que Decision 22 rejeita |
| 18 | Skill location = standalone repo em `~/Documents/feature-forge/` | quebra `forge init` + per-project install |
| 19 | Language = Python core + Bash dispatcher + YAML/MD specs | requer reescrever 21K LOC se mudar |
| 20 | Persistence = SQLite (graph) + arquivos (config, memory, docs) | quebra hooks + 17 graph queries canônicas |
| 22 | No runtime deps em outras skills (absorb patterns only) | quebra portability + viola Decision 18 |
| 23 | Validator cascade = fail-fast por default | quebra UX dos 14 validators + cascade behavior |
| 27 | Pause = `deferred` auto-resumable; abort = 2-step via `forge undo` | quebra resume + perda de progresso silenciosa |

## As 7 direcionais (Fase 3.5) — podem evoluir com ADR note

Listadas em `docs/design/01-decisions.md` §Decisions deferred + §Decisions
that could be revisited. Mudança aceita SE acompanhada de:

- Commit body explicando rationale
- Entrada em CHANGELOG `### Changed`
- Sem promoção pra "locked" sem brainstorm explícito com user

## Protocolo "Revisita decisão N"

Quando há razão real pra revisitar uma locked (deve ser raríssimo):

### Passo 1 — brainstorming explícito

Use `superpowers:brainstorming` com user. Pergunta-âncora: "Por que esta
decisão foi tomada originalmente?" Leia o rationale em `01-decisions.md`
antes da conversa.

### Passo 2 — dispatch edit com instrução literal

```
Agent[gsd-executor] prompt:
  TAREFA: Revisita decisão N — atualiza tabela em
  docs/design/01-decisions.md.

  ARQUIVOS PERMITIDOS PARA EDIT: docs/design/01-decisions.md, CHANGELOG.md

  REGRAS:
    - APPEND nova linha à tabela; NÃO deleta a linha antiga
    - Marca a linha antiga como "(superseded by row X — YYYY-MM-DD)"
    - Adiciona entrada em CHANGELOG sob ### Changed (load-bearing)
      contendo TEXTO LITERAL "Revisita decisão N: <novo choice> — <rationale>"

  CRITÉRIO DE SUCESSO:
    - Linha histórica preservada em 01-decisions.md
    - CHANGELOG contém "Revisita decisão N"
    - Commit message contém "Revisita decisão N"

  ANTI-PADRÕES:
    - Não deletar linha antiga
    - Não mudar numeração das outras decisões
    - Não simplificar rationale antigo
```

### Passo 3 — review com foco específico

`Agent[gsd-code-reviewer]` prompt explícito: "verifica que linha antiga da
decisão N foi preservada em 01-decisions.md (append-only) + CHANGELOG
contém 'Revisita decisão N' textual + commit message idem".

### Passo 4 — commit naturalmente passa pelo hard-block

O hook `.claude/hooks/pre-commit-feature-forge.sh` faz hard-block se
`01-decisions.md` está staged sem "Revisita decisão" em CHANGELOG staged.
No fluxo correto, isso NUNCA dispara — só dispara se algo escapou.

## Distinção quick reference

| Tipo | Característica | Pode mudar via |
|---|---|---|
| **Locked** (27 items) | Imutável sem revisitar formal | Protocolo acima |
| **Locked load-bearing** (8 subset) | Quebra arquitetura inteira se mudar | Protocolo + revisita Phase plan |
| **Direcional** (7 Fase 3.5) | Pode evoluir | ADR-style commit note |
| **Revisitável** (3 mencionadas em 01-decisions.md "could be revisited") | Refator local | Commit com rationale |

Fonte canônica: `docs/design/01-decisions.md`. Em conflito, esse doc vence.
```

- [ ] **Step 3: Run target test, confirm passes**

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/decisions.md
git commit -m "feat(claude-rules): decisions — 8 load-bearing + Revisita protocol"
```

---

## Task 6: `.claude/rules/disciplines.md`

**Files:**
- Create: `.claude/rules/disciplines.md`

- [ ] **Step 1: Run target test, confirm fails**

- [ ] **Step 2: Write the file (full content)**

Create `.claude/rules/disciplines.md`:

```markdown
# Disciplinas universais — quick reference

Síntese das 6 disciplinas em `docs/design/07-discipline.md`. Em conflito,
o doc original vence.

## 1. 3-caminhos pattern (gate-resolution universal)

Em QUALQUER gate (falha de validator, violação de escopo, artefato
faltando, ambiguidade, contradição entre contracts), o agente apresenta
**exatamente 3 caminhos**. Nunca 2, nunca 4, nunca "consulte a documentação".

**Onde LLM erra:** tende a apresentar 2 caminhos óbvios e parar; ou inventa
um 4º caminho fake quando o 3º genuíno seria "abort". Lembrar: 3 é canônico,
e "escalate/abort explícito" é caminho legítimo quando não há fix-forward.

### Template canônico (cole quando bloqueia)

```
🛑 {nome-do-gate}

O que falhou:
  {explicação em 1-2 linhas}

Onde:
  {arquivo:linha ou artefato:campo}

Por que importa:
  · {regra violada}
  · {contract referenciado}
  · {consequência se passar}

Três caminhos pra resolver:

  1) {Caminho A — fix forward}
     {motivo provável}

  2) {Caminho B — revert}
     {motivo provável}

  3) {Caminho C — split / escalate}
     {motivo provável}

Sem auto-fix aqui — escolha humana.
```

## 2. Validator cascade — fail-fast por default

Cascade **para no primeiro erro hard**, continua passando por warnings.
Vale pra `forge verify`, `forge doctor`, hook `post-subagent-validate`, e
qualquer ponto que rode N validators em sequência.

**Onde LLM erra:** tende a "rodar todos e mostrar resumo" mesmo em modo
fail-fast. Ler `docs/design/07-discipline.md §2` pra Override
(`validators.fail-fast: false` em workflow-config).

## 3. Pause vs abort

Ctrl+C / "para" = pause (state `deferred`, auto-resumable). Abort terminal
só via `forge undo` interativo escolhendo "abort feature entirely".

**Onde LLM erra:** descarta state ao receber sinal de interrupt; ou ao
contrário, persiste demais e não deixa abort claro.

## 4. `.bak` retention

7 dias default (configurável em `cleanup.bak-retention-days`). `forge
doctor` reporta overdue. NUNCA auto-deleta — limpeza via menu interativo
em `forge reconfigure`.

**Onde LLM erra:** sugerir `rm *.bak` na primeira vista. Não. Mostrar
`forge reconfigure` path.

## 5. Project-native vocabulary

Engine lê `CLAUDE.md` e `.claude/rules/*` + `docs/design/*`. Vocabulário do
projeto > vocabulário genérico. "Forge" só como verbo (Decision 4). Persona
"mentor calmo" em todos os artefatos gerados.

**Onde LLM erra:** voz corporativa, emoji decorativo, jargão genérico
("seja cuidadoso", "considere", "pode ser uma boa ideia").

## 6. Rejected proposal fingerprint

`sha256` sobre canonical-form `{type, name, normalized-description,
sorted-provenance-set}`. Estável contra timestamps e edits cosméticos;
muda quando conteúdo ou evidência mudam.

**Onde LLM erra:** sugerir mudar fingerprint quando proposta similar
re-aparece. Não — fingerprint deve mudar APENAS via mudança em
conteúdo/evidence; re-apresentação com mesmo fingerprint deve ser
silenciada (proposal já foi vista).

## Fonte canônica

`docs/design/07-discipline.md` é detalhado, com exemplos vivos do projeto
(forge-implement-roteiro Cena 6, forge-verify-roteiro Cena 4, etc.).
Quando este rule e o doc divergirem, **doc original vence**.
```

- [ ] **Step 3: Run target test, confirm passes**

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/disciplines.md
git commit -m "feat(claude-rules): disciplines — 6 universals quick reference"
```

---

## Task 7: `.claude/rules/testing.md`

**Files:**
- Create: `.claude/rules/testing.md`

- [ ] **Step 1: Run target test, confirm fails**

- [ ] **Step 2: Write the file (full content)**

Create `.claude/rules/testing.md`:

```markdown
# Testing — disciplina

Mandamento #2: verde antes de "pronto". 367 tests passing é estado-base.

## Comandos canônicos

```bash
# Lane completa (default)
pytest

# Lane rápida (skip integration + e2e)
pytest -m "not integration and not e2e"

# Apenas validators
pytest tests/validators/

# Apenas engine
pytest tests/engine/

# Test único (debug rápido)
pytest tests/path/test_x.py::test_func -xvs

# Apenas tests marcados integration
pytest -m integration

# Cascade de validators do projeto
forge verify

# Health check 12 categorias
forge doctor

# Smoke do CLI
./bin/forge --version
```

## Markers do projeto (em `pyproject.toml`)

- `integration` — testes que cruzam múltiplos módulos end-to-end. Podem
  precisar fixture MeoBonsai. Excluídos de rapid CI lane.
- `e2e` — subprocessam o CLI (slow). Excluídos de rapid CI lane.
- (sem marker) — unit puro. Lane default.

Quando marcar test novo:

- Cruza ≥2 módulos OU usa fixture MeoBonsai → `@pytest.mark.integration`
- Subprocess CLI → `@pytest.mark.e2e`
- Pure unit → sem marker

## Regra TDD (mandamento, não sugestão)

### Para bug fix

1. Reproduz com **regression test FALHANDO primeiro**
2. Roda: confirma FAIL
3. Implementa fix
4. Roda: confirma PASS
5. Garante que outros tests não quebraram: `pytest`
6. Commit (test + fix juntos OU test commit 1, fix commit 2 — escolha
   consistente por sessão)

### Para feature

1. Escreve happy-path test
2. Roda: confirma FAIL (function não existe)
3. Implementa minimal — só pra passar
4. Roda: PASS
5. Adiciona edge-case tests + impl iterativamente
6. Roda full suite: confirma green
7. Commit

### Para refactor

1. **NÃO adiciona test novo** (regra: refactor = sem mudança de comportamento)
2. Roda suite full ANTES do refactor: registra count + duration baseline
3. Refactor
4. Roda suite full DEPOIS: confirma mesmo count + verde
5. Roda `validators/check_no_behavior_change.py` se aplicável
6. Commit

## Fixtures conhecidos

Localização: `tests/conftest.py` + `tests/<module>/conftest.py`.

Principais (verifique `tests/conftest.py` pra lista atualizada):

- `tmp_project` — diretório temporário com estrutura mínima de projeto forge
- `mock_workflow_config` — workflow-config.yaml válido em memória
- `meobonsai_fixture` (marker `integration`) — repo fixture pra E2E
- `graph_session` — SQLite in-memory pra graph tests
- `frozen_now` — congela datetime pra testes determinísticos

Antes de criar fixture novo: `grep -rn "def fixture\|@pytest.fixture"
tests/` — talvez já exista.

## Validators são código

Novo validator em `validators/` exige:

1. Test em `tests/validators/test_<name>.py` (happy + edge cases)
2. Entrada na cascade de `forge verify` (`engine/verify.py` — verificar
   onde os validators são listados)
3. Mention em `docs/design/07-discipline.md §2` SE policy mudar (ex.: novo
   severity level)
4. Update `pyproject.toml` se introduzir marker novo

## Gates de "pronto"

Você só pode reportar trabalho "concluído" se TODOS:

- [ ] `pytest` (full suite) sai com 0 falhas
- [ ] Count de tests >= baseline (367 em v1.1.0; consulte
      `docs/design/08-session-handoff.md` pra current count)
- [ ] `forge verify` passa cascade sem hard fail
- [ ] Doc-sync executado (rule [doc-sync.md](doc-sync.md))
- [ ] Subagent reviewer assinou off (REVIEW.md sem high/critical)

Subagent que reporta "implementado" sem rodar pytest = falha de verification-
before-completion. Dispatch verification explícita SEMPRE.

## Test count regression

Se PR reduz test count, exige justificativa no commit body:

```
Removed N tests because <razão concreta>.
```

Sem isso, push-back via review. Test count protege regression detection.
```

- [ ] **Step 3: Run target test, confirm passes**

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/testing.md
git commit -m "feat(claude-rules): testing — pytest, markers, TDD, gates"
```

---

## Task 8: `.claude/rules/scope.md`

**Files:**
- Create: `.claude/rules/scope.md`

- [ ] **Step 1: Run target test, confirm fails**

- [ ] **Step 2: Write the file (full content)**

Create `.claude/rules/scope.md`:

```markdown
# Scope discipline

Mandamento #4: edite só o que a tarefa pede. Em dúvida, **pergunte ao
usuário** (não decida).

## Regra cardinal

Subagent recebe lista explícita de "ARQUIVOS PERMITIDOS PARA EDIT" no
context-pack. Sair desta lista = violação de scope, dispatch revert.

## Arquivos load-bearing (sempre confirmar antes de Write/Edit)

Estes têm hook PreToolUse que avisa (audit em
`.claude/state/load-bearing-edits.jsonl`):

```
docs/design/00-vision.md
docs/design/01-decisions.md
docs/design/05-filesystem-layout.md
docs/design/06-command-surface.md
docs/design/07-discipline.md
docs/schemas/**
presets/**
cards/**
CLAUDE.md
.claude/rules/**
```

Se task autêntica precisa tocar esses, OK — context-pack já incluiu na
whitelist. Hook só avisa, não bloqueia.

## Anti-padrões observados

### "Vou aproveitar pra atualizar isso também"

Aparece como "while I'm here, let me fix this typo nearby" ou "isso aqui
está mal nomeado, vou renomear de passagem". NÃO. Anota em
`docs/design/04-pending.md` como gap separado. Tarefa nova, dispatch novo.

### Refactor não solicitado

Aparece como "limpar um pouco o código que estou tocando". NÃO. Se o
código está ruim, abre task de refactor separada com brainstorming +
writing-plans. Rendimento misturado = scope creep + review impossível.

### Rename "while I'm here"

Aparece como "var é mal nomeada, rename de aproveitando". NÃO. Rename
afeta consumers — task separada. Especialmente: rename em código exportado
(public API) é Decision territory.

### Tocar arquivos não relacionados pra "consistency"

Aparece como "outros lugares usam pattern X, vou alinhar". Se o pattern
está alinhado a `docs/design/*`, propose como gap. Se está alinhado a uma
preferência pessoal sem base no projeto, NÃO faça.

## Exceção legítima

**Doc-sync na mesma mudança (Mandamento #6).** Quando você toca
`engine/`, `validators/`, `hooks/`, etc., DEVE atualizar:
- `CHANGELOG.md` (Unreleased)
- `docs/design/08-session-handoff.md` (Última atualização)
- `README.md` (se stats mudaram)

Isso NÃO é scope creep — é mandamento explícito. Matriz completa em
[doc-sync.md](doc-sync.md).

## Em dúvida

Se subagent não sabe se mudança X está in-scope:

1. **Pare a edição**
2. Reporta ao orchestrator
3. Orchestrator pergunta ao usuário via `AskUserQuestion`
4. Usuário decide (in-scope ou separar)

Custo de perguntar < custo de scope creep silencioso. Subagent **nunca**
expande escopo por iniciativa própria.

## Detection mecânico

Hook `pre-tool-use-load-bearing.sh` (PreToolUse Edit/Write) emite:

```
🛑 LOAD-BEARING edit: <arquivo>
Confirme intenção. Se revisita decisão locked, commit deve dizer
"Revisita decisão N".
```

Aparece no contexto da sessão. Se você vê esse aviso e o arquivo NÃO está
na whitelist do context-pack atual → scope creep iminente, aborta.

Audit log: `cat .claude/state/load-bearing-edits.jsonl | jq .` revisa
histórico de tentativas.
```

- [ ] **Step 3: Run target test, confirm passes**

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/scope.md
git commit -m "feat(claude-rules): scope — load-bearing list + anti-padrões"
```

---

## Task 9: `.claude/rules/reuse.md`

**Files:**
- Create: `.claude/rules/reuse.md`

- [ ] **Step 1: Run target test, confirm fails**

- [ ] **Step 2: Write the file (full content)**

Create `.claude/rules/reuse.md`:

```markdown
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
```

- [ ] **Step 3: Run target test, confirm passes**

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/reuse.md
git commit -m "feat(claude-rules): reuse — graph queries antes de criar"
```

---

## Task 10: `.claude/rules/superpowers.md`

**Files:**
- Create: `.claude/rules/superpowers.md`

- [ ] **Step 1: Run target test, confirm fails**

- [ ] **Step 2: Write the file (full content)**

Create `.claude/rules/superpowers.md`:

```markdown
# Superpowers — 10 skills ativadas

Skills do superpowers que o orchestrator usa neste projeto. **Não há
runtime import** — skills são recurso humano + Claude Code (Decision 22).

## Tabela completa

| Skill | Trigger preciso | Bloqueia? |
|---|---|---|
| `superpowers:brainstorming` | qualquer creative work — "vamos planejar/adicionar/criar/refatorar X" | sim — hard gate antes de tocar código |
| `superpowers:writing-plans` | task ≥3 passos OU cruza ≥3 arquivos OU envolve subagent dispatch | sim para implementação não-trivial |
| `superpowers:subagent-driven-development` | toda implementação não-trivial | **sim — mandamento 0** |
| `superpowers:dispatching-parallel-agents` | 2+ tarefas independentes sem shared state | sim quando aplicável |
| `superpowers:test-driven-development` | implementar feature ou bugfix (instrução vai no pacote do subagent) | sim — context-pack pro subagent inclui obrigatoriamente |
| `superpowers:systematic-debugging` | bug, test failure, comportamento inesperado | sim — orchestrator guia raciocínio |
| `superpowers:requesting-code-review` | pós toda implementação não-trivial | **sim — mandamento 0** |
| `superpowers:receiving-code-review` | quando reviewer subagent retorna REVIEW.md | sim |
| `superpowers:executing-plans` | quando há plan escrito a seguir (modo inline alternativo ao subagent-driven) | recomendado |
| `superpowers:verification-before-completion` | antes de claim "pronto/implementado/feito" | sim — hard gate antes de commit final |

## Skills NÃO ativadas (deliberadamente)

- `superpowers:using-git-worktrees` — projeto não usa worktrees em v1.1.
  Influences.md já documenta como "absorvido patterns only" sem dep. Se
  pattern emergir (multi-feature paralelo), entra via `forge evolve`.
- `superpowers:finishing-a-development-branch` — single-maintainer, branch
  cleanup é simples.
- `superpowers:writing-skills` — projeto inteiro É uma skill; criar
  sub-skills não está no radar.
- `superpowers:using-superpowers` — meta-skill, auto-invocada por session-
  start.

Quando padrão emergir e justificar, entrar via:
1. `forge evolve` propõe addition
2. Brainstorm de revisita
3. Update neste rule + CLAUDE.md superpowers map

## Hierarquia de prioridade (per superpowers contract)

```
1. User explicit instructions (CLAUDE.md, AGENTS.md, direct requests) ← TOPO
2. Superpowers skills
3. Default system prompt                                                ← BASE
```

Se CLAUDE.md (este projeto) entra em conflito com superpowers, **o
projeto vence**. Se user manda "edita direto" mesmo violando Mandamento 0,
**o user vence**.

## Decision 22 reforço

Skills são padrão de comportamento + ferramenta humana + ferramenta do
Claude Code. NUNCA são import runtime. `engine/` não importa nada de
`superpowers/`, `gsd-*/`, ou qualquer outra skill. Esta é decisão
load-bearing — quebra portability.

Se algum subagent sugerir "vamos usar superpowers como lib" → push-back
imediato, viola Decision 22.
```

- [ ] **Step 3: Run target test, confirm passes**

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/superpowers.md
git commit -m "feat(claude-rules): superpowers — 10 skills with triggers"
```

---

## Task 11: `.claude/rules/doc-sync.md`

**Files:**
- Create: `.claude/rules/doc-sync.md`

- [ ] **Step 1: Run target test, confirm fails**

- [ ] **Step 2: Write the file (full content)**

Create `.claude/rules/doc-sync.md`:

```markdown
# Doc-sync — matriz código→docs

Mandamento #6. Ao tocar código vivo, atualize docs no MESMO commit.

## Matriz canônica

| Mudou… | Atualize obrigatoriamente | Considere também |
|---|---|---|
| `engine/<command>.py` (handler) | CHANGELOG, `08-session-handoff.md` | `README.md §Stats`, `06-command-surface.md` |
| `engine/foundation/*` (cli, utils, ui, persona) | CHANGELOG, handoff | — |
| `validators/<x>.py` | CHANGELOG, handoff stats | `07-discipline.md §2` se policy mudou |
| `hooks/*.sh` ou `.claude/hooks/*.sh` | CHANGELOG, handoff | `05-filesystem-layout.md` |
| Novo card em `cards/` | `README §Stats`, handoff | `02-phases.md` |
| Novo template em `templates/` | `README §Stats`, handoff | `02-phases.md` |
| Schema em `docs/schemas/` | CHANGELOG, `README §Schemas` | qualquer template que use o schema |
| `presets/*.yaml` | CHANGELOG, `README §Preset` | `03-influences.md` se rationale muda |
| `docs/design/01-decisions.md` | CHANGELOG `### Changed (load-bearing)` "Revisita decisão N: ..." | sempre append, nunca delete |
| `docs/design/04-pending.md` | risca gap fechado, adiciona novo | handoff `§Conhecidos limites` |
| `agents/*.md` (prompts) | CHANGELOG, handoff | — |
| `docs/ux/*.md` (roteiros) | CHANGELOG | `08-session-handoff.md` se UX muda |
| Release tag | CHANGELOG seção `## [vX.Y.Z]`, `README versão` | handoff `§Estado` |

## Checklist pré-commit

Antes de `git commit`, confirme:

1. [ ] `CHANGELOG.md` tem entrada em `## [Unreleased]` cobrindo a mudança?
2. [ ] `docs/design/08-session-handoff.md` `**Última atualização:**` é hoje
       (ou no commit também) E `**Estado:**` reflete o que mudou?
3. [ ] `README.md` Stats refletem (se stats mudaram — file count, test
       count, LOC, schemas count)?
4. [ ] Rule específico atualizado SE comportamento mudou (ex.: novo
       validator → mention em `testing.md`; novo subagent_type → mention
       em `subagent-workflow.md`)?
5. [ ] Gap em `04-pending.md` fechado/atualizado se aplicável?

Se algum check falhar, dispatch `gsd-doc-writer` (ou `gsd-executor` com
prompt focado em docs) ANTES do commit final.

## Como editar `08-session-handoff.md`

Campos canônicos a tocar:

```markdown
**Última atualização:** YYYY-MM-DD (v1.X.Y — <slug curto>)
**Estado:** v1.X feito; <próximo>
```

A tabela `| Categoria | Status |` ganha linha quando há nova phase/wave.
Não inventar formato — replicar pattern existente.

`§Conhecidos limites` ganha entrada SE shipping com limitação deliberada
(não bug).

## Como editar `CHANGELOG.md`

Segue keep-a-changelog. Sempre tem `## [Unreleased]` no topo. Seções:

- `### Added` — funcionalidade nova
- `### Changed` — comportamento alterado (não-breaking)
- `### Changed (load-bearing)` — quando revisita decisão locked
- `### Fixed` — bug fix
- `### Removed` — funcionalidade removida (anuncia + razão)

Release move `[Unreleased]` → `[vX.Y.Z] - YYYY-MM-DD` e cria novo
`[Unreleased]` vazio acima.

## Quando NÃO precisa doc-sync (exceções enumeradas)

- Typo puro em comentário (sem mudança de semântica do código)
- Reformatação que ferramenta automatizada gera (`black`, `ruff format`)
- Renomear variável local sem afetar API pública
- Edição de string literal já testada que não muda comportamento
  verificável
- Update de version pin em `pyproject.toml` sem mudança de behavior
  (aplica `### Changed` opcionalmente)

Tudo fora desta lista exige doc-sync. Em dúvida: faça sync.

## Bloqueios opt-in disponíveis (futuro)

Documentados aqui mas NÃO ativos. Pra ativar, descomentar bloco específico
em `.claude/hooks/pre-commit-feature-forge.sh`:

### Test-count regression block

```bash
# Bloco opt-in: descomentar quando quiser ativar
# CURRENT_COUNT=$(pytest --collect-only -q 2>/dev/null | tail -1 | awk '{print $1}')
# BASELINE=$(cat .claude/state/test-count-baseline 2>/dev/null || echo 0)
# if [[ "$CURRENT_COUNT" -lt "$BASELINE" ]]; then
#     git log -1 --pretty=%B | grep -q "Removed.*tests because" || {
#         echo "🛑 test count dropped from $BASELINE to $CURRENT_COUNT without justification" >&2
#         exit 1
#     }
# fi
```

Custo: +1-3s por commit. Quando ligar: se perdas silenciosas começarem.

### Validator cascade fail block

```bash
# Bloco opt-in
# CHANGED=$(git diff --cached --name-only | grep -E '^(engine|validators)/' || true)
# if [[ -n "$CHANGED" ]]; then
#     forge verify --quiet || {
#         echo "🛑 validators failed pré-commit" >&2
#         exit 1
#     }
# fi
```

Custo: +5-15s. Quando ligar: se PRs começarem a quebrar verify pós-merge.

### Per-tool-use Mandamento 0 block

Não-implementável de forma estável hoje — depende de Claude Code expor
distinção main-vs-subagent no hook protocol. Anotado em `04-pending.md`
como gap pra detection futura.
```

- [ ] **Step 3: Run target test, confirm passes**

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/doc-sync.md
git commit -m "feat(claude-rules): doc-sync — matriz código→docs + bloqueios opt-in"
```

---

## Task 12: `.claude/rules/project-anatomy.md`

**Files:**
- Create: `.claude/rules/project-anatomy.md`

- [ ] **Step 1: Run target test, confirm fails**

- [ ] **Step 2: Write the file (full content)**

Create `.claude/rules/project-anatomy.md`:

```markdown
# Project Anatomy — "se procura X, vai em Y"

Mapa orientativo. Em dúvida sobre onde algo vive, comece aqui.

## Engine (~21.9K LOC Python)

| Procura | Vai em |
|---|---|
| Handler de comando (`forge <cmd>`) | `engine/<cmd>.py` (13 handlers em v1.1) |
| Foundation: dispatcher, CLI parser, UI helpers, persona | `engine/{cli,utils,ui,persona}.py` |
| State: cards, memory, graph, inventory | `engine/{cards,memory,graph,inventory}/` |
| Integrations: MCP, vision | `engine/{mcp,vision}/` |
| Schema migrations (graph SQLite) | `engine/graph/migrations/` |
| Reuse intelligence pipeline | `engine/graph/reuse/` (parsers + detection + apply) |

## Layer 1 — Capability cards

| Procura | Vai em |
|---|---|
| Card canônico (20 em v1.1) | `cards/<name>.yaml` |
| Card schema | `docs/schemas/card.md` |
| Preset | `presets/kmp-mobile.yaml` (+ outros) |

## Layer 2 — Templates (18 em v1.1)

| Procura | Vai em |
|---|---|
| Feature artifacts | `templates/feature-*.template.md` |
| Spec artifacts (YAML) | `templates/*-spec.template.yaml` |
| Subtype-specific intake | `templates/feature-intake-{bugfix,refactor}.template.md` |

## Validators (14 + 2 helpers em v1.1)

| Procura | Vai em |
|---|---|
| Validator canônico | `validators/<name>.py` |
| Helpers compartilhados | `validators/_common.py` |
| Validator tests | `tests/validators/test_<name>.py` |

## Docs

| Procura | Vai em |
|---|---|
| Visão geral | `docs/design/00-vision.md` |
| Decisões | `docs/design/01-decisions.md` |
| Phases roadmap | `docs/design/02-phases.md` + `docs/design/ROADMAP.md` |
| Influences (skills absorbidas) | `INFLUENCES.md` + `docs/design/03-influences.md` |
| Pending gaps | `docs/design/04-pending.md` |
| Filesystem layout | `docs/design/05-filesystem-layout.md` |
| Command surface | `docs/design/06-command-surface.md` |
| Disciplinas universais | `docs/design/07-discipline.md` |
| Estado/handoff | `docs/design/08-session-handoff.md` |
| Schemas YAML/JSON | `docs/schemas/*.md` |
| UX roteiros (forge plan/implement/verify/etc.) | `docs/ux/*.md` |
| Lifecycle (memory + graph) | `docs/lifecycle/memory-and-graph.md` |

## Agents (prompts pra sub-agents)

| Procura | Vai em |
|---|---|
| Planning conductor + 9 sub-agents | `agents/*.md` |

## Hooks — dois diretórios distintos

| Procura | Vai em |
|---|---|
| Git hooks + Claude Code hooks instalados em PROJETOS CONSUMIDORES via `forge init` | `hooks/` (raiz) |
| Claude Code hooks deste repo (manutenção interna) | `.claude/hooks/` |

## Tests

| Procura | Vai em |
|---|---|
| Unit tests | `tests/<module>/test_*.py` |
| Integration (marker `integration`) | `tests/integration/test_*.py` |
| E2E (marker `e2e`) | `tests/e2e/test_*.py` |
| Fixtures comuns | `tests/conftest.py` |
| Test data | `tests/fixtures/` |

## Bin

| Procura | Vai em |
|---|---|
| Dispatcher Bash canônico | `bin/forge` |

## Smoke tests rápidos

```bash
./bin/forge --version              # CLI vivo
pytest -k smoke                    # smoke suite
pytest tests/validators/ -x        # validators OK
python -m engine.cli --help        # CLI entry alternativa (pyproject scripts)
```

## Onde NÃO mexer sem revisitar

Lista em [scope.md](scope.md). Decisões load-bearing em
[decisions.md](decisions.md).
```

- [ ] **Step 3: Run target test, confirm passes**

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/project-anatomy.md
git commit -m "feat(claude-rules): project-anatomy — mapa 'se procura X, vai em Y'"
```

---

## Task 13: `.claude/rules/SMOKE-CHECKLIST.md`

**Files:**
- Create: `.claude/rules/SMOKE-CHECKLIST.md`

- [ ] **Step 1: Run target test, confirm fails**

- [ ] **Step 2: Write the file (full content)**

Create `.claude/rules/SMOKE-CHECKLIST.md`:

```markdown
# Smoke Checklist (one-time, post-bootstrap)

5 verificações manuais pra confirmar que o rules system está vivo.

Execute **uma vez** após rodar `bash .claude/bootstrap.sh` pela primeira vez.

## 1. SessionStart hook injeta orientação?

- Abre sessão Claude Code nova no repo.
- Confirma que o início da conversa tem (no contexto inicial, antes do
  primeiro prompt seu):
  - `🔨 feature-forge — orientação de sessão`
  - Linha "Última atualização handoff"
  - Mandamento 0 lembrete

✅ se aparece. ❌ se não:
- `cat .claude/settings.json` — `SessionStart` está registrado?
- `ls -la .claude/hooks/session-start-orientation.sh` — exec?
- `bash -n .claude/hooks/session-start-orientation.sh` — sintaxe OK?

## 2. PostToolUse drift hook dispara em edit de arquivo "vivo"?

- Pede ao Claude (na sessão): "Despacha um subagent pra adicionar um
  comentário inócuo em `engine/cli.py` na primeira linha (algo tipo
  `# smoke test {{date}}`)".
- Após o dispatch concluir, confirma stderr contém:
  - `📝 doc-drift`
  - Listagem de docs a sync

✅ se aparece. ❌ se não:
- `cat .claude/settings.json` — `PostToolUse` registrado com matcher correto?
- `cat .claude/state/drift-warned.json` — apareceu entrada?

(Depois reverte: `git checkout engine/cli.py`.)

## 3. PreToolUse load-bearing hook dispara em edit de doc load-bearing?

- Pede: "Despacha subagent pra adicionar nota dummy no fim de
  `docs/design/00-vision.md`".
- Confirma stderr contém:
  - `🛑 LOAD-BEARING edit`
- Confirma audit log:
  - `cat .claude/state/load-bearing-edits.jsonl | tail -1`
  - Deve ter linha JSON com timestamp + file + tool.

✅ se ambos. ❌ se não — debug similar ao #2.

(Reverte: `git checkout docs/design/00-vision.md`.)

## 4. Pre-commit hard block dispara em `01-decisions.md` sem ceremony?

```bash
# Simula edit sem ceremony
echo "# probe" >> docs/design/01-decisions.md
git add docs/design/01-decisions.md
echo "## probe Unreleased" >> CHANGELOG.md
git add CHANGELOG.md
git commit -m "probe" 2>&1 | head -20
```

Expected: exit 1 com mensagem contendo "BLOCK" e "Revisita decisão".

Agora com ceremony:

```bash
# Cleanup probe
git restore --staged docs/design/01-decisions.md CHANGELOG.md
git checkout docs/design/01-decisions.md CHANGELOG.md

# Re-stage com ceremony
echo "# probe" >> docs/design/01-decisions.md
git add docs/design/01-decisions.md
echo "## Unreleased" >> CHANGELOG.md
echo "- Revisita decisão 99: probe — testing hard block" >> CHANGELOG.md
git add CHANGELOG.md
git commit -m "probe"
```

Expected: commit passes.

Cleanup: `git reset --soft HEAD~1` + revert dos arquivos.

✅ se ambos comportamentos. ❌ se inverso:
- `bash -n .claude/hooks/pre-commit-feature-forge.sh` — sintaxe?
- `.git/hooks/pre-commit` é symlink pra `hooks/git-pre-commit`?

## 5. Mandamento 0 — modelo dispatcha pra mudança trivial?

- Pede: "Quero adicionar um espaço em branco no final do README.md.
  Faça."
- Observa: o orchestrator (sessão principal) PROPÕE dispatch subagent?
  Ou tenta `Edit` direto?

✅ se dispatch. ❌ se Edit direto:
- Confirma CLAUDE.md foi carregado (ler topo do contexto da sessão)
- Confirma `.claude/rules/orchestrator-persona.md` é referenciado em
  CLAUDE.md
- Reset da sessão, tenta de novo

Se persistente: é sinal que CLAUDE.md root precisa de Mandamento 0 mais
forte. Ajuste no `CLAUDE.md` e re-teste.

## Resultado esperado

5/5 passam = sistema vivo. Marque a data abaixo:

> **Última execução do checklist:** YYYY-MM-DD — N/5 passou.
> Observações:

(Update após cada execução manual.)
```

- [ ] **Step 3: Run target test, confirm passes**

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/SMOKE-CHECKLIST.md
git commit -m "feat(claude-rules): SMOKE-CHECKLIST — 5 verificações manuais post-bootstrap"
```

---

## Task 14: Hook `.claude/hooks/session-start-orientation.sh`

**Files:**
- Create: `.claude/hooks/session-start-orientation.sh`

- [ ] **Step 1: Run target test, confirm fails**

```bash
pytest "tests/integration/test_claude_rules_system.py::test_hook_script_exists_executable_valid_bash[session-start-orientation.sh]" -v
```

- [ ] **Step 2: Write the script (full content)**

Create `.claude/hooks/session-start-orientation.sh`:

```bash
#!/usr/bin/env bash
# feature-forge — SessionStart hook (Claude Code)
# Injects orientation at session start so orchestrator has Mandamento 0
# fresh and current state without having to re-read all docs.
#
# Contract:
#   - Always exits 0
#   - Stdout is injected as additional context
#   - Stderr is logged but not blocking
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE_DIR="$PROJECT_ROOT/.claude/state"
HANDOFF="$PROJECT_ROOT/docs/design/08-session-handoff.md"

# Reset per-session state
rm -f "$STATE_DIR/drift-warned.json" 2>/dev/null || true

# Extract handoff metadata
UPDATED="(handoff missing)"
STATE_LINE="(handoff missing)"
if [[ -f "$HANDOFF" ]]; then
    UPDATED=$(grep -m1 '^\*\*Última atualização:\*\*' "$HANDOFF" \
        | sed 's/^\*\*Última atualização:\*\* //' || echo "(unknown)")
    STATE_LINE=$(grep -m1 '^\*\*Estado:\*\*' "$HANDOFF" \
        | sed 's/^\*\*Estado:\*\* //' || echo "(unknown)")
fi

# Check drift from previous session
DRIFT_PENDING="não"
if [[ -f "$STATE_DIR/drift-pending.json" && -s "$STATE_DIR/drift-pending.json" ]]; then
    DRIFT_PENDING="sim"
fi

cat <<EOF
🔨 feature-forge — orientação de sessão

Você é o ORQUESTRADOR-MANTENEDOR. Nunca Write/Edit/NotebookEdit/Bash-mutação
direto — toda mudança é despachada via Agent tool (gsd-executor / gsd-code-
reviewer / gsd-code-fixer).

Estado do projeto:
  · Última atualização handoff: $UPDATED
  · Estado: $STATE_LINE
  · Drift pendente da sessão anterior: $DRIFT_PENDING

Antes de qualquer trabalho:
  1. Brainstorm com usuário → writing-plans
  2. Dispatch gsd-executor (impl) → gsd-code-reviewer (review) → gsd-code-fixer (fixes)
  3. Verification → doc-sync → commit

Regras: CLAUDE.md · Mandamento 0: .claude/rules/orchestrator-persona.md
EOF

exit 0
```

- [ ] **Step 3: Make executable**

```bash
chmod +x .claude/hooks/session-start-orientation.sh
```

- [ ] **Step 4: Test manually**

```bash
bash -n .claude/hooks/session-start-orientation.sh && echo "syntax OK"
bash .claude/hooks/session-start-orientation.sh
```

Expected: orientation text printed; exit 0.

- [ ] **Step 5: Run target test, confirm passes**

- [ ] **Step 6: Commit**

```bash
git add .claude/hooks/session-start-orientation.sh
git commit -m "feat(claude-hooks): session-start-orientation — Mandamento 0 + state injection"
```

---

## Task 15: Hook `.claude/hooks/pre-tool-use-load-bearing.sh`

**Files:**
- Create: `.claude/hooks/pre-tool-use-load-bearing.sh`

- [ ] **Step 1: Run target test, confirm fails**

- [ ] **Step 2: Write the script (full content)**

Create `.claude/hooks/pre-tool-use-load-bearing.sh`:

```bash
#!/usr/bin/env bash
# feature-forge — PreToolUse hook (Edit|Write|NotebookEdit)
# Warns + audit logs when load-bearing files are about to be edited.
# Never blocks (per design: hooks leves + 1 hard-block apenas no
# pre-commit das decisions).
#
# Input: JSON via stdin com `tool_input.file_path` (Claude Code hook protocol).
# Contract: exit 0 sempre; stderr é mostrado mas não bloqueia.
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE_DIR="$PROJECT_ROOT/.claude/state"
AUDIT_LOG="$STATE_DIR/load-bearing-edits.jsonl"

mkdir -p "$STATE_DIR"

# Parse file_path do JSON stdin (defensivo — se input não é JSON válido, sai 0)
INPUT="$(cat 2>/dev/null || true)"
if [[ -z "$INPUT" ]]; then
    exit 0
fi

# Extract file_path com python (mais robusto que jq pra ambientes variados)
FILE_PATH=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    print(data.get('tool_input', {}).get('file_path', ''))
except Exception:
    print('')
" <<< "$INPUT")

if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

# Path relativo ao repo (se foi passado absoluto)
REL_PATH="${FILE_PATH#$PROJECT_ROOT/}"

# Lista de patterns load-bearing
is_load_bearing() {
    case "$1" in
        docs/design/00-vision.md) return 0 ;;
        docs/design/01-decisions.md) return 0 ;;
        docs/design/05-filesystem-layout.md) return 0 ;;
        docs/design/06-command-surface.md) return 0 ;;
        docs/design/07-discipline.md) return 0 ;;
        docs/schemas/*) return 0 ;;
        presets/*) return 0 ;;
        cards/*) return 0 ;;
        CLAUDE.md) return 0 ;;
        .claude/rules/*) return 0 ;;
        *) return 1 ;;
    esac
}

if is_load_bearing "$REL_PATH"; then
    cat <<EOF >&2

🛑 LOAD-BEARING edit: $REL_PATH

Confirme intenção explícita. Se revisita decisão locked, commit deve
dizer "Revisita decisão N" no CHANGELOG (hard-block do pre-commit).

Detalhe: .claude/rules/scope.md + .claude/rules/decisions.md

EOF

    # Audit log
    TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    TOOL=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    print(data.get('tool_name', 'unknown'))
except Exception:
    print('unknown')
" <<< "$INPUT")

    printf '{"ts":"%s","file":"%s","tool":"%s"}\n' \
        "$TS" "$REL_PATH" "$TOOL" >> "$AUDIT_LOG"
fi

exit 0
```

- [ ] **Step 3: Make executable + test**

```bash
chmod +x .claude/hooks/pre-tool-use-load-bearing.sh
bash -n .claude/hooks/pre-tool-use-load-bearing.sh && echo "syntax OK"

# Smoke: dispara com fake input
echo '{"tool_name":"Edit","tool_input":{"file_path":"docs/design/01-decisions.md"}}' \
  | bash .claude/hooks/pre-tool-use-load-bearing.sh

# Confirma audit log
cat .claude/state/load-bearing-edits.jsonl
# Cleanup
rm -f .claude/state/load-bearing-edits.jsonl
```

Expected: stderr 🛑 LOAD-BEARING edit; audit log JSON line.

- [ ] **Step 4: Run target test, confirm passes**

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/pre-tool-use-load-bearing.sh
git commit -m "feat(claude-hooks): pre-tool-use-load-bearing — warn + audit on sensitive paths"
```

---

## Task 16: Hook `.claude/hooks/post-edit-doc-drift.sh`

**Files:**
- Create: `.claude/hooks/post-edit-doc-drift.sh`

- [ ] **Step 1: Run target test, confirm fails**

- [ ] **Step 2: Write the script (full content)**

Create `.claude/hooks/post-edit-doc-drift.sh`:

```bash
#!/usr/bin/env bash
# feature-forge — PostToolUse hook (Edit|Write|NotebookEdit)
# Reminds about doc-sync when paths "vivos" são editados. Once per file
# per session — evita spam.
#
# Input: JSON via stdin (tool_input.file_path).
# Contract: exit 0 sempre.
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE_DIR="$PROJECT_ROOT/.claude/state"
WARNED="$STATE_DIR/drift-warned.json"
PENDING="$STATE_DIR/drift-pending.json"

mkdir -p "$STATE_DIR"

INPUT="$(cat 2>/dev/null || true)"
[[ -z "$INPUT" ]] && exit 0

FILE_PATH=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    print(data.get('tool_input', {}).get('file_path', ''))
except Exception:
    print('')
" <<< "$INPUT")

[[ -z "$FILE_PATH" ]] && exit 0

REL_PATH="${FILE_PATH#$PROJECT_ROOT/}"

# Match paths "vivos"
is_live_code() {
    case "$1" in
        engine/*|validators/*|hooks/*|templates/*|cards/*|presets/*|docs/schemas/*)
            return 0 ;;
        *) return 1 ;;
    esac
}

if ! is_live_code "$REL_PATH"; then
    exit 0
fi

# Check se já avisou nesta sessão
ALREADY_WARNED=$(WARNED="$WARNED" TARGET="$REL_PATH" python3 -c "
import json, sys, os
path = os.environ.get('WARNED', '')
target = os.environ.get('TARGET', '')
if not os.path.exists(path):
    print('no')
    sys.exit(0)
try:
    with open(path) as f:
        data = json.load(f)
    if target in data.get('files', []):
        print('yes')
    else:
        print('no')
except Exception:
    print('no')
")

if [[ "$ALREADY_WARNED" == "yes" ]]; then
    exit 0
fi

# Append to warned + pending
WARNED="$WARNED" PENDING="$PENDING" TARGET="$REL_PATH" python3 -c "
import json, os, sys
warned_path = os.environ['WARNED']
pending_path = os.environ['PENDING']
target = os.environ['TARGET']

for p in (warned_path, pending_path):
    data = {'files': []}
    if os.path.exists(p):
        try:
            with open(p) as f:
                data = json.load(f)
        except Exception:
            data = {'files': []}
    if target not in data.get('files', []):
        data.setdefault('files', []).append(target)
    with open(p, 'w') as f:
        json.dump(data, f, indent=2)
"

cat <<EOF >&2

📝 doc-drift: $REL_PATH editado.

Doc-sync pendente (mesmo commit):
  · CHANGELOG.md (Unreleased)
  · docs/design/08-session-handoff.md (Última atualização + Conhecidos limites se mudou)
  · README.md (se stats mudaram)

Matriz completa: .claude/rules/doc-sync.md

EOF

exit 0
```

- [ ] **Step 3: Make executable + smoke test**

```bash
chmod +x .claude/hooks/post-edit-doc-drift.sh
bash -n .claude/hooks/post-edit-doc-drift.sh && echo "syntax OK"

# Smoke
echo '{"tool_name":"Edit","tool_input":{"file_path":"engine/cli.py"}}' \
  | bash .claude/hooks/post-edit-doc-drift.sh

cat .claude/state/drift-warned.json
cat .claude/state/drift-pending.json

# Second call — should NOT print warning (already warned)
echo '{"tool_name":"Edit","tool_input":{"file_path":"engine/cli.py"}}' \
  | bash .claude/hooks/post-edit-doc-drift.sh

# Cleanup
rm -f .claude/state/drift-warned.json .claude/state/drift-pending.json
```

Expected: first call shows warning + writes state; second call silent.

- [ ] **Step 4: Run target test, confirm passes**

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/post-edit-doc-drift.sh
git commit -m "feat(claude-hooks): post-edit-doc-drift — doc-sync reminder (once per file per session)"
```

---

## Task 17: Hook `.claude/hooks/pre-commit-feature-forge.sh` (hard block + soft warning)

**Files:**
- Create: `.claude/hooks/pre-commit-feature-forge.sh`

- [ ] **Step 1: Run target test, confirm fails**

```bash
pytest "tests/integration/test_claude_rules_system.py::test_hook_script_exists_executable_valid_bash[pre-commit-feature-forge.sh]" -v
pytest "tests/integration/test_claude_rules_system.py::test_pre_commit_hard_blocks_decisions_without_ceremony" -v
pytest "tests/integration/test_claude_rules_system.py::test_pre_commit_allows_decisions_with_ceremony" -v
```

Expected: all FAIL.

- [ ] **Step 2: Write the script (full content)**

Create `.claude/hooks/pre-commit-feature-forge.sh`:

```bash
#!/usr/bin/env bash
# feature-forge — git pre-commit (canonical, called by hooks/git-pre-commit).
# Two checks:
#   (1) HARD BLOCK: docs/design/01-decisions.md staged without "Revisita
#       decisão" in staged CHANGELOG.md → exit 1.
#   (2) SOFT WARNING: code "vivo" staged sem CHANGELOG/handoff/README staged.
#
# Override consciente: git commit --no-verify (registra bypass deliberado).
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE_DIR="$PROJECT_ROOT/.claude/state"

CHANGED=$(git diff --cached --name-only 2>/dev/null || true)
if [[ -z "$CHANGED" ]]; then
    exit 0
fi

# ─── HARD BLOCK: decisions sem ceremony ───────────────────────────────

TOUCHES_DECISIONS=$(echo "$CHANGED" | grep -E '^docs/design/01-decisions\.md$' || true)
if [[ -n "$TOUCHES_DECISIONS" ]]; then
    CHANGELOG_DIFF=$(git diff --cached CHANGELOG.md 2>/dev/null || true)
    if ! echo "$CHANGELOG_DIFF" | grep -qiE 'revisita decisão|revisit decision'; then
        cat <<'EOF' >&2

🛑 BLOCK: docs/design/01-decisions.md alterado sem cerimônia.

    Adicione entrada em CHANGELOG.md (staged) contendo:
      'Revisita decisão N: <novo choice> — <rationale>'

    Por quê: decisões locked são imutáveis sem revisitar (mandamento #1).
    Override consciente: git commit --no-verify (registra que foi deliberado).

    Detalhe: .claude/rules/decisions.md

EOF
        exit 1
    fi
fi

# ─── SOFT WARNING: doc-sync ausente ───────────────────────────────────

TOUCHED_CODE=$(echo "$CHANGED" | grep -E '^(engine|validators|hooks|templates|cards|presets|docs/schemas)/' || true)
if [[ -n "$TOUCHED_CODE" ]]; then
    TOUCHED_DOCS=$(echo "$CHANGED" | grep -E '^(CHANGELOG\.md|docs/design/08-session-handoff\.md|README\.md)$' || true)
    if [[ -z "$TOUCHED_DOCS" ]]; then
        cat <<EOF >&2

⚠️  doc-sync: commit toca código vivo mas não CHANGELOG/handoff/README.

    Arquivos vivos alterados:
$(echo "$TOUCHED_CODE" | sed 's/^/      · /')

    Lembre-se de atualizar doc-sync ou justifique no commit body.
    (Sem bloqueio — só aviso.)

EOF
    fi
fi

# Limpa drift-pending consumido pelo commit
rm -f "$STATE_DIR/drift-pending.json" 2>/dev/null || true

exit 0
```

- [ ] **Step 3: Make executable**

```bash
chmod +x .claude/hooks/pre-commit-feature-forge.sh
bash -n .claude/hooks/pre-commit-feature-forge.sh && echo "syntax OK"
```

- [ ] **Step 4: Run integration tests for the hook**

```bash
pytest "tests/integration/test_claude_rules_system.py::test_hook_script_exists_executable_valid_bash[pre-commit-feature-forge.sh]" -v
pytest "tests/integration/test_claude_rules_system.py::test_pre_commit_hard_blocks_decisions_without_ceremony" -v
pytest "tests/integration/test_claude_rules_system.py::test_pre_commit_allows_decisions_with_ceremony" -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/pre-commit-feature-forge.sh
git commit -m "feat(claude-hooks): pre-commit — hard block decisions + soft doc-sync warning"
```

---

## Task 18: `.claude/settings.json` (hooks registration)

**Files:**
- Create: `.claude/settings.json`

- [ ] **Step 1: Run target test, confirm fails**

```bash
pytest "tests/integration/test_claude_rules_system.py::test_settings_json_exists_and_parses" -v
```

- [ ] **Step 2: Write the file (full content)**

Create `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "command": ".claude/hooks/session-start-orientation.sh"
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit",
        "command": ".claude/hooks/pre-tool-use-load-bearing.sh"
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit",
        "command": ".claude/hooks/post-edit-doc-drift.sh"
      }
    ]
  }
}
```

- [ ] **Step 3: Verify JSON parses**

```bash
python3 -m json.tool .claude/settings.json
```

Expected: pretty-printed JSON, no error.

- [ ] **Step 4: Run target test, confirm passes**

- [ ] **Step 5: Commit**

```bash
git add .claude/settings.json
git commit -m "feat(claude-hooks): settings.json — register 3 Claude Code hooks (committed)"
```

---

## Task 19: `.claude/bootstrap.sh` (idempotent one-time setup)

**Files:**
- Create: `.claude/bootstrap.sh`

- [ ] **Step 1: Run target tests, confirm fails**

```bash
pytest "tests/integration/test_claude_rules_system.py::test_bootstrap_script_exists_and_executable" -v
pytest "tests/integration/test_claude_rules_system.py::test_bootstrap_is_idempotent" -v
```

- [ ] **Step 2: Write the script (full content)**

Create `.claude/bootstrap.sh`:

```bash
#!/usr/bin/env bash
# feature-forge — one-time bootstrap pra rodar Claude Code com hooks/rules.
# Idempotente: pode rodar várias vezes sem efeito colateral.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

echo "🔨 feature-forge bootstrap"

# 1. Garante .claude/state/ existe com .gitkeep
mkdir -p .claude/state
[[ -f .claude/state/.gitkeep ]] || touch .claude/state/.gitkeep
echo "  ✓ .claude/state/ pronto"

# 2. Linka git hooks aos delegators canônicos em hooks/
for h in pre-commit pre-push; do
    target=".git/hooks/$h"
    source_file="hooks/git-$h"
    if [[ -f "$source_file" ]]; then
        if [[ -L "$target" || -f "$target" ]]; then
            current=$(readlink "$target" 2>/dev/null || echo "")
            expected="../../$source_file"
            if [[ "$current" == "$expected" ]]; then
                echo "  ✓ $target → $source_file (já linkado)"
                continue
            elif [[ -n "$current" && "$current" != "$expected" ]]; then
                echo "  ⚠️  $target já existe e aponta pra outro lugar — pulando (revisão manual)"
                continue
            else
                # Arquivo regular existente, não symlink — pula com aviso
                echo "  ⚠️  $target é arquivo regular — pulando (mova manualmente se quiser usar nosso delegator)"
                continue
            fi
        fi
        ln -s "../../$source_file" "$target"
        chmod +x "$source_file" 2>/dev/null || true
        echo "  ✓ $target → $source_file (novo symlink)"
    else
        echo "  ⊘ $source_file não existe — pulando (sem delegator pra linkar)"
    fi
done

# 3. Marca .claude/hooks/*.sh executáveis
if [[ -d .claude/hooks ]]; then
    chmod +x .claude/hooks/*.sh 2>/dev/null || true
    echo "  ✓ .claude/hooks/*.sh executáveis"
fi

# 4. Aviso sobre settings.local.json tracked
if git ls-files --error-unmatch .claude/settings.local.json >/dev/null 2>&1; then
    echo ""
    echo "  ⚠️  .claude/settings.local.json está tracked. Recomendado untrack:"
    echo "       git rm --cached .claude/settings.local.json"
    echo "       (mantém o arquivo localmente, remove do git)"
    echo ""
fi

echo "✅ Bootstrap completo. Próxima sessão Claude Code carrega hooks + rules automaticamente."
```

- [ ] **Step 3: Make executable + manual smoke**

```bash
chmod +x .claude/bootstrap.sh
bash -n .claude/bootstrap.sh && echo "syntax OK"
bash .claude/bootstrap.sh
# Run a second time to verify idempotency
bash .claude/bootstrap.sh
```

Expected: both runs succeed; second run reports "já linkado" / "pronto" not "novo".

- [ ] **Step 4: Run target tests, confirm pass**

```bash
pytest "tests/integration/test_claude_rules_system.py::test_bootstrap_script_exists_and_executable" -v
pytest "tests/integration/test_claude_rules_system.py::test_bootstrap_is_idempotent" -v
```

- [ ] **Step 5: Commit**

```bash
git add .claude/bootstrap.sh
git commit -m "feat(claude-hooks): bootstrap.sh — idempotent one-time setup"
```

---

## Task 20: `CLAUDE.md` root (entry document)

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Run target tests, confirm fail**

```bash
pytest "tests/integration/test_claude_rules_system.py::test_claude_md_root_exists" -v
pytest "tests/integration/test_claude_rules_system.py::test_rule_file_linked_in_claude_md" -v
```

Expected: FAIL.

- [ ] **Step 2: Write the file (full content)**

Create `CLAUDE.md`:

```markdown
# CLAUDE.md — feature-forge

> Guia operacional pra Claude Code mantendo este repo.
> Voz: mentor calmo — firme nos gates, didático nos exemplos.
> Última atualização: 2026-06-01 · Versão do projeto: v1.1.0

## Identidade rápida

- **O que é:** CLI skill orquestrando feature lifecycle mobile (Android/iOS/KMP/Web)
- **Persona dos artefatos gerados:** mentor calmo · Vocabulário: "forge" só como verbo
- **Scope OUT:** arch macro · decisão de produto · code review final · time tracking
- **Mais:** `README.md` · `docs/design/00-vision.md`

---

## Mandamento 0 — Você é o orquestrador-mantenedor

Nesta sessão você É o mantenedor de feature-forge. Não o implementador.

**Regra absoluta — sem exceção:** você NUNCA usa `Write`, `Edit`,
`NotebookEdit`, nem Bash com mutação (`rm`, `mv`, `sed -i`, `git commit`/
`push`, `pip install`, etc.) em qualquer arquivo deste projeto. Toda
mudança — incluindo typo de 1 caractere, comentário, espaço em branco,
renomear variável — é executada por subagente despachado via `Agent` tool.

Sem "rapidinho". Sem "é só um espaço". Sem "deixa eu fazer essa que é
trivial". A consistência vale o overhead.

**Suas ferramentas legítimas:**
- **Leitura**: `Read`, `Grep`, `Glob`, `Explore` agent
- **Bash read-only**: `ls`, `git status/log/diff/show`, `pytest --collect-only`
- **Coordenação**: `TaskCreate`/`Update`, `AskUserQuestion`, `ScheduleWakeup`
- **Despacho**: `Agent` (subagent_type apropriado)
- **Skills (você DIRIGE, subagente EXECUTA)**: `superpowers:brainstorming`,
  `superpowers:writing-plans`, `superpowers:systematic-debugging`,
  `superpowers:verification-before-completion`

**Override do usuário:** se o usuário ordena explicitamente "edita direto"
ou "não delega isso", a instrução do usuário tem prioridade absoluta.
Esta regra cobre o default automático.

**Seu fluxo único:**

1. Brainstorm com usuário → traduz em plano (`superpowers:writing-plans`)
2. Despacha implementação (`gsd-executor`)
3. Recebe diff → lê → julga (trust-but-verify)
4. Despacha review (`gsd-code-reviewer`)
5. Se findings → despacha fix (`gsd-code-fixer`) → loop
6. Despacha verification (subagente roda pytest + validators, reporta)
7. Despacha doc-sync (CHANGELOG + handoff + README)
8. Despacha commit final

Detalhe + edge cases: `.claude/rules/orchestrator-persona.md`.
Como despachar: `.claude/rules/subagent-workflow.md`.

---

## Os 6 mandamentos (não-negociáveis)

### 1. Decisões locked são imutáveis sem revisitar

`docs/design/01-decisions.md` lista 27 locked + 7 direcionais. Mexer em
alguma = passo explícito de "Revisita decisão N" no commit body + entrada
em CHANGELOG. Nunca silent drift. O hook `.claude/hooks/pre-commit-feature-
forge.sh` faz HARD BLOCK se este ritual não acontecer.

Detalhe: `.claude/rules/decisions.md`.

### 2. Verde antes de "pronto"

`pytest` (367 tests baseline) verde + `forge verify` verde + validators
sem hard fail. Sem isso, não dizemos "implementado". Subagente que
implementa SEMPRE recebe `superpowers:verification-before-completion`
como hard gate no context-pack.

Detalhe: `.claude/rules/testing.md`.

### 3. Reuso antes de criar

Antes de escrever helper/função/template/card novo, consulte:
- `forge graph` Q11 (reusable-helpers)
- `forge graph` Q12–Q17 (reuse-intelligence)
- `engine/inventory/` (DS components + i18n + conventions)
- `cards/`, `templates/`, `validators/`

Inventar paralelo é falha. Detalhe: `.claude/rules/reuse.md`.

### 4. Escopo contido na tarefa pedida

Não refator não solicitado, não editar arquivos não relacionados, não
expandir feature além do pedido. Em dúvida, **pergunte ao usuário** via
`AskUserQuestion` — não decida.

Detalhe: `.claude/rules/scope.md`.

### 5. Voz mentor calmo em tudo que gera artefato

Templates, mensagens de gate, prompts de agent — todos seguem o tom
estabelecido em `docs/design/07-discipline.md`. Sem voz corporativa, sem
emoji decorativo.

### 6. Doc-sync na mesma mudança

Mexeu em `engine/`, `validators/`, `hooks/`, `templates/`, `cards/`,
`presets/`, `docs/schemas/` → atualizou no MESMO commit:
- `CHANGELOG.md` (Unreleased)
- `docs/design/08-session-handoff.md` (Última atualização + Conhecidos
  limites se aplicável)
- `README.md` (se stats mudaram)

Matriz código→docs: `.claude/rules/doc-sync.md`.

---

## Workflow por verbo

| Vou… | Skills (orchestrator invoca) | Quem executa |
|---|---|---|
| Adicionar feature/recurso | `brainstorming` → `writing-plans` → `subagent-driven-development` | `gsd-executor` + review subagent |
| Resolver bug | `systematic-debugging` → `subagent-driven-development` | `gsd-executor` + review subagent |
| Refatorar | `brainstorming` → `writing-plans` (no-behavior) → `subagent-driven-development` | `gsd-executor` + review (check_no_behavior_change) |
| Editar locked decision | `brainstorming` (revisitar N) | `gsd-executor` edita com histórico preservado |
| Editar schema/template | `writing-plans` → `subagent-driven-development` | `gsd-executor` + review |
| Finalizar qualquer mudança | `verification-before-completion` + doc-sync | subagent verifica + subagent atualiza docs |
| Typo / 1-char fix / espaço | — | `gsd-code-fixer` com prompt minimal (zero exceção inline) |

---

## Superpowers map (10 skills ativas)

| Skill | Trigger | Bloqueia? |
|---|---|---|
| `superpowers:brainstorming` | qualquer creative work | sim — hard gate |
| `superpowers:writing-plans` | task ≥3 passos OU cruza arquivos | sim para implementação não-trivial |
| `superpowers:subagent-driven-development` | toda implementação não-trivial | sim — mandamento 0 |
| `superpowers:dispatching-parallel-agents` | 2+ tarefas independentes | sim quando aplicável |
| `superpowers:test-driven-development` | feature ou fix (subagent recebe via context-pack) | sim |
| `superpowers:systematic-debugging` | bug, test failure (orchestrator guia) | sim |
| `superpowers:requesting-code-review` | pós toda implementação | sim — mandamento 0 |
| `superpowers:receiving-code-review` | reviewer retorna REVIEW.md | sim |
| `superpowers:executing-plans` | quando há plan escrito | recomendado |
| `superpowers:verification-before-completion` | antes de claim "pronto" | sim — hard gate |

Skills são RECURSO humano + Claude Code, sem runtime import (Decision 22).
Detalhe: `.claude/rules/superpowers.md`.

---

## Anatomia rápida

- `engine/` — Python core, 13 commands handlers + foundation + state + integrations
- `validators/` — 14 validators + helpers (tests obrigatórios em `tests/validators/`)
- `templates/`, `cards/`, `presets/` — composição declarativa, YAML/MD
- `docs/design/` — fonte de verdade pra "por que" (quase tudo load-bearing)
- `hooks/` — git + Claude Code hooks que `forge init` instala em **projetos consumidores** (diferente de `.claude/hooks/` que é deste repo)

Mapa completo: `.claude/rules/project-anatomy.md`.

---

## Comandos úteis

```bash
pytest                              # 367 tests, default lane
pytest -m "not integration"         # rápido
forge verify                        # validators cascade
forge doctor                        # health check 12 categorias
./bin/forge --version               # smoke
```

---

## Pointers

- Decisões: `docs/design/01-decisions.md` · `.claude/rules/decisions.md`
- Disciplinas: `docs/design/07-discipline.md` · `.claude/rules/disciplines.md`
- Estado/Handoff: `docs/design/08-session-handoff.md`
- Pendências/Gaps: `docs/design/04-pending.md`
- Filesystem: `docs/design/05-filesystem-layout.md`
- Influences: `INFLUENCES.md` · `docs/design/03-influences.md`

## Bootstrap

Após clonar, rode **uma vez**:

```bash
bash .claude/bootstrap.sh
```

Idempotente. Liga git hooks ao delegator canônico, marca scripts executáveis.
Detalhe + checklist pós-bootstrap: `.claude/rules/SMOKE-CHECKLIST.md`.
```

- [ ] **Step 3: Run target tests, confirm pass**

```bash
pytest "tests/integration/test_claude_rules_system.py::test_claude_md_root_exists" -v
pytest "tests/integration/test_claude_rules_system.py::test_rule_file_linked_in_claude_md" -v
```

Expected: all 12 parameterized PASS.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "feat(claude-rules): CLAUDE.md root — Mandamento 0 + 6 mandamentos + workflow tables"
```

---

## Task 21: Run full integration test suite

**Files:**
- Test: `tests/integration/test_claude_rules_system.py`

- [ ] **Step 1: Run full integration test suite**

```bash
pytest tests/integration/test_claude_rules_system.py -v
```

Expected: **all PASS** (~16 tests including 12 parameterized rule existence + structural + hook bash syntax + 2 pre-commit + 2 bootstrap + gitignore).

- [ ] **Step 2: Run full project test suite, ensure baseline (367) preserved**

```bash
pytest -m "not integration and not e2e" 2>&1 | tail -3
pytest 2>&1 | tail -3
```

Expected:
- rapid lane: green
- full lane: count ≥ 367 + integration tests we added (+~16 → 383+)

- [ ] **Step 3: If anything failed, fix iteratively**

For each failure:
1. Read the assertion message
2. Identify which task left the gap
3. Apply correction (the fix is in the file that owns the assertion, per task ownership above)
4. Re-run

- [ ] **Step 4: Commit if any fixes happened**

```bash
# Only if fixes were needed
git add -p   # review each hunk
git commit -m "fix(claude-rules): post-integration corrections (see commit body)"
```

---

## Task 22: Doc-sync (CHANGELOG + handoff + README) — eat our own dog food

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/design/08-session-handoff.md`
- Modify: `README.md`

- [ ] **Step 1: Update `CHANGELOG.md`**

Append under `## [Unreleased]` (if section doesn't exist, create it at top
under the title):

```markdown
### Added (Claude Code rules system)

- `CLAUDE.md` root + `.claude/rules/*.md` (12 operational rules)
- `.claude/hooks/*.sh` (4 hooks: SessionStart orientation, PreToolUse
  load-bearing audit, PostToolUse doc-sync drift, git pre-commit with
  hard block on `01-decisions.md` without "Revisita decisão" ceremony)
- `.claude/settings.json` registering hooks
- `.claude/bootstrap.sh` (idempotent one-time setup)
- `tests/integration/test_claude_rules_system.py` (~16 tests, marker
  `integration`)

Implements Mandamento 0 (orchestrator-mantenedor, zero direct edits) +
doc-sync discipline + 6 mandamentos + 10 superpowers skills wiring.
Spec: `docs/superpowers/specs/2026-06-01-claude-md-design.md`.
Plan: `docs/superpowers/plans/2026-06-01-claude-md-rules-system.md`.
```

- [ ] **Step 2: Update `docs/design/08-session-handoff.md`**

Edit the header:

```markdown
**Última atualização:** 2026-06-01 (Claude Code rules system instalado)
**Estado:** v1.1.0 estável; rules system ativo (CLAUDE.md + 12 rules + 4 hooks + integration tests). Próximo: dogfooding via primeira feature pós-rules em MeoBonsai.
```

Adicione ao final da seção `## Estado atual (anchors)` ou crie nova seção
**Conhecidos limites (rules system)**:

```markdown
**Rules system v1 (2026-06-01) — limites reconhecidos:**

- Per-tool-use Mandamento 0 detection é manual (depende de orchestrator
  obedecer regra textual). Hook bloqueante depende de Claude Code expor
  distinção main-vs-subagent — gap em `04-pending.md`.
- `forge audit-rules` (comando futuro pra verificar conformidade em git
  log) ainda não existe — gap em `04-pending.md` pra v1.2+.
- Bloqueios opt-in (test-count regression, validator-cascade fail) estão
  documentados em `.claude/rules/doc-sync.md` mas comentados no script;
  ativar quando emergir necessidade.
```

- [ ] **Step 3: Update `README.md`**

Após a seção "Stack alvo" ou onde fizer sentido pelo flow, adicione
sub-seção:

```markdown
## Manutenção via Claude Code

Este repo tem rules system ativo (`CLAUDE.md` + `.claude/rules/` + 4
hooks) que disciplina toda sessão Claude Code mantendo o projeto.
Orchestrator-mantenedor delega 100% das mudanças via Agent tool
(`gsd-executor` / `gsd-code-reviewer` / `gsd-code-fixer`).

Após clonar:

```bash
bash .claude/bootstrap.sh
```

Detalhe: `CLAUDE.md` + `.claude/rules/README.md`.
```

Atualize as stats no `## Stats` se aplicável (LOC total, files total —
+~21 arquivos novos + ~1500 LOC entre rules + hooks + tests).

- [ ] **Step 4: Verify pre-commit accepts the doc-sync commit**

```bash
git add CHANGELOG.md docs/design/08-session-handoff.md README.md
git status
# Should NOT trigger hard block (no 01-decisions.md staged)
# Should NOT trigger soft warning (CHANGELOG + handoff + README staged)
git commit -m "docs: sync CHANGELOG + handoff + README for Claude Code rules system"
```

Expected: commit succeeds; no hook warnings.

---

## Task 23: Bootstrap + Smoke Checklist (manual, user-driven)

This task is **manual** — the user runs it personally to validate the
system end-to-end.

- [ ] **Step 1: Run bootstrap**

```bash
bash .claude/bootstrap.sh
```

Expected: success messages, idempotent on re-run.

- [ ] **Step 2: Execute 5-item SMOKE-CHECKLIST**

Open `.claude/rules/SMOKE-CHECKLIST.md` and execute each of the 5
checks in a fresh Claude Code session. Mark results in the file's
"Última execução do checklist" footer.

- [ ] **Step 3: Update SMOKE-CHECKLIST.md with results**

Dispatch `gsd-executor` to update the footer:

```
TAREFA: Atualiza .claude/rules/SMOKE-CHECKLIST.md, seção
"Última execução do checklist", com: data de hoje, N/5 passou,
e observações por item.

ARQUIVOS PERMITIDOS PARA EDIT: .claude/rules/SMOKE-CHECKLIST.md

CRITÉRIO DE SUCESSO: footer atualizado, commit feito.
```

- [ ] **Step 4: Final state confirmation**

```bash
git log --oneline | head -25                       # commits do rules system
pytest tests/integration/test_claude_rules_system.py -v 2>&1 | tail -5
forge doctor                                       # health check
```

Expected: all green.

---

## Self-Review

### Spec coverage check

| Spec section | Implementing task(s) |
|---|---|
| §3.1 inventário (21 files + 4 mods) | Tasks 1–22 (mapped 1:1 except foundation/bundling) |
| §4 CLAUDE.md root content | Task 20 |
| §5.1 rules/README | Task 2 |
| §5.2 orchestrator-persona | Task 3 |
| §5.3 subagent-workflow | Task 4 |
| §5.4 decisions | Task 5 |
| §5.5 disciplines | Task 6 |
| §5.6 testing | Task 7 |
| §5.7 scope | Task 8 |
| §5.8 reuse | Task 9 |
| §5.9 superpowers | Task 10 |
| §5.10 doc-sync | Task 11 |
| §5.11 project-anatomy | Task 12 |
| §5.12 SMOKE-CHECKLIST | Task 13 |
| §6.1 hook session-start | Task 14 |
| §6.2 hook pre-tool-use load-bearing | Task 15 |
| §6.3 hook post-edit-doc-drift | Task 16 |
| §6.4 hook pre-commit (hard block + soft warning) | Task 17 |
| §6.5 settings.json wiring | Task 18 |
| §6.6 state runtime + .gitignore | Task 1 |
| §7.1 bootstrap.sh | Task 19 |
| §7.2 smoke checklist (manual) | Task 23 |
| §7.3 integration tests | Task 1 (skeleton) + Task 21 (verify full) |
| §7.4 auditoria contínua (manual) | documented in `.claude/rules/README.md` §Auditoria (Task 2) |
| §10 ordem canônica | matches Tasks 1 → 23 |
| §11 critérios de sucesso (verificáveis) | Task 21 + Task 23 |

### Placeholder scan

- No "TBD", "TODO", "implement later"
- No "add appropriate error handling" — all error handling is explicit (or
  deliberately absent in scripts that always exit 0 by design)
- No "similar to Task N" — content reproduced in each task
- No undefined references — all subagent_type names (`gsd-executor`,
  `gsd-code-reviewer`, `gsd-code-fixer`, `gsd-debugger`, `Explore`,
  `general-purpose`) exist per spec
- All file paths exact

### Type / signature consistency

- `EXPECTED_RULES` (12 items) in test matches the 12 rule files created
  in Tasks 2–13 ✓
- `EXPECTED_HOOKS` (4 items) matches the 4 hooks created in Tasks 14–17 ✓
- `.claude/settings.json` keys (`SessionStart`, `PreToolUse`,
  `PostToolUse`) match what hooks expect ✓
- Hook input parsing uses `tool_input.file_path` consistently ✓
- State file paths consistent: `drift-warned.json`, `drift-pending.json`,
  `load-bearing-edits.jsonl` ✓
- Gitignore pattern `.claude/state/*.json` covers `drift-warned.json` and
  `drift-pending.json`; `.jsonl` pattern covers audit log ✓

### Scope check

23 tasks, decomposable into 3 parallel waves if executed via subagent-
driven:
- **Wave 1 (foundation):** Task 1 alone (must precede all)
- **Wave 2 (parallel):** Tasks 2–13 (rules) + Tasks 14–17 (hooks) + Task
  18 (settings) + Task 19 (bootstrap) — all independent
- **Wave 3 (sequential, depends on Wave 2):** Task 20 (CLAUDE.md, must
  come after rules to link them) → Task 21 (full test) → Task 22 (doc-
  sync) → Task 23 (manual smoke)

This decomposes cleanly. Single plan stands.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-01-claude-md-rules-system.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task,
review between tasks, fast iteration. Wave 2 (Tasks 2–19) can run in
parallel batches of 3-4 for speed. Total: ~23 subagent dispatches +
review cycles.

**2. Inline Execution** — Execute tasks in this session using
`superpowers:executing-plans`, batch execution with checkpoints. Single
session, sequential, slower but lighter context.

**Which approach?**
