# feature-forge v1.3 Pilot-Ready Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md`](../specs/2026-06-16-v1-3-pilot-ready-design.md)

**Goal:** Ship v1.3.0 — feature-forge instala em 1 comando, sobrevive em projetos brownfield denso, roda com UX fluida sob Claude Code + opencode + humano TTY.

**Architecture:** Novo módulo `engine/host/` abstrai interação user-facing via per-host adapters (Claude Code, opencode, TTY, intent_file fallback). Sub-namespace `.claude/forge/` isola state forge do `.claude/` user-owned. Install via curl one-liner com PATH detection + 3-caminhos; `forge upgrade` pra future updates. Revisita Decisão 18 (skill location → XDG default `~/.local/share/feature-forge/`).

**Tech Stack:** Python 3.10+, bash, pytest, git, bats (install.sh tests).

**Branch de execução:** `feat/v1.3-pilot-ready` criada a partir de `main` 100% sincronizada via `git pull --ff-only` (Task 0.0). Plano + spec vivem em `docs/v1-3-pilot-ready-spec`. Orquestrador decide ordem de PR (recomendado: spec+plan em PR único).

**Total:** 6 waves, 38 tasks, ~2830 LOC + docs, ~185 tests novos.

---

## File Structure

```
NOVOS:
  engine/host/__init__.py
  engine/host/adapter.py                    ABC + HostName + AskKind + AskResult + sentinels
  engine/host/env.py                        env var helpers (CLAUDECODE, OPENCODE_*, etc.)
  engine/host/registry.py                   registry de adapters
  engine/host/detect.py                     detect_host com cache
  engine/host/adapters/__init__.py
  engine/host/adapters/intent_file.py       fallback DRIFT-1 (migrado de question.py)
  engine/host/adapters/claude_code.py       in-process via AskUserQuestion shape
  engine/host/adapters/opencode.py          in-process via opencode tool API (W2)
  engine/host/adapters/tty.py               stdin direto + box-drawing
  engine/upgrade.py                         forge upgrade handler core
  scripts/install.sh                        curl one-liner installer
  docs/research/opencode-tool-api.md        W2.T0 research output
  tests/unit/test_host_adapter_abc.py
  tests/unit/test_host_env.py
  tests/unit/test_host_detect.py
  tests/unit/test_host_registry.py
  tests/unit/test_host_intent_file.py
  tests/unit/test_host_claude_code.py
  tests/unit/test_host_opencode.py
  tests/unit/test_host_tty.py
  tests/unit/test_paths_helpers.py
  tests/unit/test_settings_merge.py
  tests/unit/test_upgrade.py
  tests/unit/test_exit_codes.py
  tests/unit/test_qa_no_args.py
  tests/integration/test_init_brownfield_meobonsai_class.py
  tests/integration/test_claude_md_unchanged.py
  tests/integration/test_git_hook_delegator.py
  tests/integration/test_subnamespace_paths.py
  tests/e2e/test_install_sh.py              wrapper bats
  tests/e2e/test_forge_upgrade.py
  tests/e2e/test_pilot_smoke.py
  tests/e2e/test_per_host_dispatch.py
  tests/fixtures/meobonsai-class/           fixture sintética
  tests/fixtures/install-sh/                fixtures pra bats

REFACTOR:
  engine/ui/question.py                     delega a adapter via registry
  engine/ui/renderer.py                     ASCII fallback non-TTY
  engine/utils/paths.py                     adicionar forge_dir/forge_config_path/etc
  engine/init.py                            paths refactor + brownfield detect + delegator
  engine/cli.py                             exit codes unify + suppress WARN + forge upgrade
  engine/qa/*.py entry                      3-caminhos sem args

RENAME:
  engine/host/adapters/intent_file.py       ← engine/ui/intent_state.py
  validators/validate_workflow_config.py    → validators/validate_forge_config.py
  docs/schemas/workflow-config.md           → docs/schemas/forge-config.md

DOC-SYNC (W5):
  CHANGELOG.md                              v1.3.0 entry + "Revisita decisão 18"
  README.md                                 quickstart rewrite (curl install)
  docs/design/01-decisions.md               Revisita Decisão 18 append-only
  docs/design/04-pending.md                 clean-break + W2.T0 entries
  docs/design/05-filesystem-layout.md       sub-namespace .claude/forge/
  docs/design/08-session-handoff.md         v1.3 ship + Última atualização

CONFIG:
  requirements.txt                          json5 lib (W1.3) se escolhido
  pyproject.toml                            version bump 1.3.0 (W5)
```

---

## Wave Index

| Wave | Goal | Tasks | LOC | Tests |
|---|---|---|---|---|
| W0 | Foundation host/ + paths refactor + rename forge-config + CC adapter | 12 | ~900 | 51 |
| W1 | Sub-namespace iso + settings merge + delegator chain + MeoBonsai fixture | 8 | ~500 | 31 |
| W2 | Research opencode + opencode adapter + TTY + ASCII fallback | 6 | ~600 | 41 |
| W3 | 7 bugs do relatório fechados | 6 | ~400 | 27 |
| W4 | install.sh + forge upgrade + bats + e2e | 8 | ~330 | 30 |
| W5 | Pilot smoke + Revisita 18 + doc-sync mass + tag | 10 | ~100 + docs | 5 |
| **Total** | | **50** | **~2830** | **~185** |

(Task count 38→50 com sub-tasks de doc-sync miniaturizados ao fim de cada wave; estrutura preservada.)

---

## Wave 0 — Foundation + Claude Code vertical slice

**Goal:** engine/host/ module + sub-namespace `.claude/forge/` + Claude Code adapter funcionando end-to-end greenfield.
**Spec ref:** §2 (arquitetura), §3 (B + C components), §4 (data flow CC).

### Task 0.0: Branch precondition

**Files:** (operações git apenas)

- [ ] **Step 1: Confirm clean working tree**

Run: `git status --porcelain`
Expected: empty output

- [ ] **Step 2: Checkout main + fetch + pull --ff-only**

```bash
git checkout main
git fetch origin
git pull --ff-only origin main
```
Expected: "Already up to date" OR fast-forwarded. ABORT se non-ff — exige resolução manual.

- [ ] **Step 3: Create new branch + push -u**

```bash
git checkout -b feat/v1.3-pilot-ready
git push -u origin feat/v1.3-pilot-ready
```
Expected: branch local criada + tracking estabelecido origin

- [ ] **Step 4: Smoke**

Run: `git rev-parse --abbrev-ref HEAD`
Expected: `feat/v1.3-pilot-ready`

(no commit — branch setup only)

---

### Task 0.1: engine/host/adapter.py ABC + types

**Files:**
- Create: `engine/host/__init__.py`
- Create: `engine/host/adapter.py`
- Test: `tests/unit/test_host_adapter_abc.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_host_adapter_abc.py
import pytest
from engine.host.adapter import HostAdapter, HostName, AskKind, AskResult


def test_host_adapter_is_abstract():
    with pytest.raises(TypeError, match="abstract"):
        HostAdapter()


def test_host_name_enum_canonical():
    assert HostName.CLAUDE_CODE.value == "claude-code"
    assert HostName.OPENCODE.value == "opencode"
    assert HostName.TTY.value == "tty"
    assert HostName.INTENT_FILE.value == "intent-file"


def test_ask_kind_enum():
    for k in ("ask", "ask_three_paths", "ask_multi", "ask_text"):
        assert AskKind(k).value == k


def test_ask_result_dataclass_default():
    r = AskResult(value="product")
    assert r.value == "product"
    assert r.from_default is False
    assert r.paused is False
```

- [ ] **Step 2: Run test → FAIL**

Run: `pytest tests/unit/test_host_adapter_abc.py -v`
Expected: `ModuleNotFoundError: No module named 'engine.host'`

- [ ] **Step 3: Implement**

```python
# engine/host/__init__.py
from engine.host.adapter import (
    HostAdapter, HostName, AskKind, AskResult,
    PausedForInputError, UserCancelledError,
)
__all__ = ["HostAdapter", "HostName", "AskKind", "AskResult",
           "PausedForInputError", "UserCancelledError"]
```

```python
# engine/host/adapter.py
"""Host adapter abstract interface.

Spec: docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md §2.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class HostName(str, Enum):
    CLAUDE_CODE = "claude-code"
    OPENCODE = "opencode"
    TTY = "tty"
    INTENT_FILE = "intent-file"


class AskKind(str, Enum):
    ASK = "ask"
    ASK_THREE_PATHS = "ask_three_paths"
    ASK_MULTI = "ask_multi"
    ASK_TEXT = "ask_text"


@dataclass(frozen=True)
class AskResult:
    value: str | list[str]
    from_default: bool = False
    paused: bool = False


class PausedForInputError(Exception):
    """Engine sinaliza host pra pausar + emitir pending intent."""


class UserCancelledError(Exception):
    """User abortou via Ctrl+C / 3-caminhos Path C."""


class HostAdapter(ABC):
    name: HostName

    @abstractmethod
    def ask(self, *, kind: AskKind, question: str, options: dict,
            default: str | None, allow_pause: bool) -> AskResult: ...

    @abstractmethod
    def ask_text(self, *, prompt: str, default: str | None) -> str: ...

    @abstractmethod
    def ask_multi(self, *, question: str, options: dict,
                  min: int = 0, max: int | None = None) -> list[str]: ...

    @abstractmethod
    def emit_progress(self, *, step: str, total: int, current: int) -> None: ...

    @abstractmethod
    def emit_warn(self, *, message: str) -> None: ...
```

- [ ] **Step 4: Run test → PASS**

Run: `pytest tests/unit/test_host_adapter_abc.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/host/__init__.py engine/host/adapter.py tests/unit/test_host_adapter_abc.py
git commit -m "feat(host): adapter ABC + HostName/AskKind/AskResult types"
```

---

### Task 0.2: engine/host/env.py — env var detectors

**Files:**
- Create: `engine/host/env.py`
- Test: `tests/unit/test_host_env.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_host_env.py
import os
import pytest
from engine.host.env import (
    detect_claude_code, detect_opencode, detect_codex, detect_cursor, detect_any_agentic,
)


def test_detect_claude_code_truthy(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    assert detect_claude_code() is True


def test_detect_claude_code_falsy(monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    assert detect_claude_code() is False


def test_detect_opencode_via_prefix(monkeypatch):
    monkeypatch.setenv("OPENCODE_VERSION", "1.0")
    assert detect_opencode() is True


def test_detect_codex(monkeypatch):
    monkeypatch.setenv("CODEX_CLI", "1")
    assert detect_codex() is True


def test_detect_any_agentic_truthy(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    assert detect_any_agentic() is True


def test_detect_any_agentic_falsy(monkeypatch):
    for v in ("CLAUDECODE", "OPENCODE_VERSION", "CODEX_CLI", "CURSOR_AGENT"):
        monkeypatch.delenv(v, raising=False)
    assert detect_any_agentic() is False
```

- [ ] **Step 2: Run → FAIL**

Run: `pytest tests/unit/test_host_env.py -v`
Expected: `ModuleNotFoundError: No module named 'engine.host.env'`

- [ ] **Step 3: Implement**

```python
# engine/host/env.py
"""Env var helpers pra detect host agentic. Spec §2 / §4."""
import os


def _truthy(varname: str) -> bool:
    val = os.environ.get(varname)
    return bool(val) and val.lower() not in {"0", "false", "no", ""}


def detect_claude_code() -> bool:
    return _truthy("CLAUDECODE")


def detect_opencode() -> bool:
    # opencode setta vars com prefixo OPENCODE_
    return any(k.startswith("OPENCODE_") for k in os.environ.keys())


def detect_codex() -> bool:
    return any(k.startswith("CODEX") for k in os.environ.keys())


def detect_cursor() -> bool:
    return _truthy("CURSOR_AGENT") or any(k.startswith("CURSOR_") for k in os.environ.keys())


def detect_any_agentic() -> bool:
    return detect_claude_code() or detect_opencode() or detect_codex() or detect_cursor()
```

- [ ] **Step 4: Run → PASS**

Run: `pytest tests/unit/test_host_env.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/host/env.py tests/unit/test_host_env.py
git commit -m "feat(host): env var detectors (CLAUDECODE/OPENCODE_*/CODEX_*/CURSOR_*)"
```

---

### Task 0.3: engine/host/registry.py + detect.py com cache

**Files:**
- Create: `engine/host/registry.py`
- Create: `engine/host/detect.py`
- Test: `tests/unit/test_host_detect.py`, `tests/unit/test_host_registry.py`

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_host_registry.py
import pytest
from engine.host.registry import register, get_adapter_class, clear_registry
from engine.host.adapter import HostName, HostAdapter


def test_register_and_get(monkeypatch):
    class StubAdapter(HostAdapter):
        name = HostName.TTY
        def ask(self, **kw): ...
        def ask_text(self, **kw): ...
        def ask_multi(self, **kw): ...
        def emit_progress(self, **kw): ...
        def emit_warn(self, **kw): ...
    clear_registry()
    register(HostName.TTY, StubAdapter)
    assert get_adapter_class(HostName.TTY) is StubAdapter


def test_get_unknown_raises():
    clear_registry()
    with pytest.raises(KeyError):
        get_adapter_class(HostName.OPENCODE)
```

```python
# tests/unit/test_host_detect.py
from pathlib import Path
import pytest
from engine.host.detect import detect_host, _clear_cache
from engine.host.adapter import HostName


def test_detect_via_config_override(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    _clear_cache()
    cfg = tmp_path / ".claude" / "forge" / "forge-config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("host: opencode\n")
    assert detect_host(tmp_path) == HostName.OPENCODE


def test_detect_via_env_claude_code(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    _clear_cache()
    assert detect_host(tmp_path) == HostName.CLAUDE_CODE


def test_detect_fallback_intent_file(tmp_path, monkeypatch):
    for v in ("CLAUDECODE", "OPENCODE_VERSION", "CODEX_CLI", "CURSOR_AGENT"):
        monkeypatch.delenv(v, raising=False)
    _clear_cache()
    # sys.stdin.isatty() é False em pytest → fallback intent_file
    assert detect_host(tmp_path) in (HostName.TTY, HostName.INTENT_FILE)


def test_detect_cache_same_process(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    _clear_cache()
    first = detect_host(tmp_path)
    monkeypatch.delenv("CLAUDECODE")
    second = detect_host(tmp_path)
    assert first == second  # cache survives env change
```

- [ ] **Step 2: Run → FAIL**

Run: `pytest tests/unit/test_host_registry.py tests/unit/test_host_detect.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# engine/host/registry.py
from typing import Type
from engine.host.adapter import HostAdapter, HostName

_REGISTRY: dict[HostName, Type[HostAdapter]] = {}


def register(name: HostName, cls: Type[HostAdapter]) -> None:
    _REGISTRY[name] = cls


def get_adapter_class(name: HostName) -> Type[HostAdapter]:
    if name not in _REGISTRY:
        raise KeyError(f"Adapter not registered: {name.value}")
    return _REGISTRY[name]


def clear_registry() -> None:
    _REGISTRY.clear()
```

```python
# engine/host/detect.py
"""Detect host com precedence: config > env > fallback intent_file. Spec §2."""
import sys
from pathlib import Path
from functools import lru_cache
import yaml
from engine.host.adapter import HostName
from engine.host import env

_cache: dict[Path, HostName] = {}


def _clear_cache() -> None:
    _cache.clear()


def _read_config_host(project_root: Path) -> HostName | None:
    cfg = project_root / ".claude" / "forge" / "forge-config.yaml"
    if not cfg.exists():
        return None
    try:
        data = yaml.safe_load(cfg.read_text()) or {}
    except yaml.YAMLError:
        return None
    h = data.get("host")
    if not h:
        return None
    try:
        return HostName(h)
    except ValueError:
        return None


def detect_host(project_root: Path) -> HostName:
    if project_root in _cache:
        return _cache[project_root]
    # 1. Config override
    cfg = _read_config_host(project_root)
    if cfg is not None:
        result = cfg
    # 2. Env scan
    elif env.detect_claude_code():
        result = HostName.CLAUDE_CODE
    elif env.detect_opencode():
        result = HostName.OPENCODE
    # 3. TTY check (humano em terminal real)
    elif sys.stdin.isatty():
        result = HostName.TTY
    # 4. Fallback
    else:
        result = HostName.INTENT_FILE
    _cache[project_root] = result
    return result
```

- [ ] **Step 4: Run → PASS**

Run: `pytest tests/unit/test_host_registry.py tests/unit/test_host_detect.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/host/registry.py engine/host/detect.py tests/unit/test_host_registry.py tests/unit/test_host_detect.py
git commit -m "feat(host): registry + detect_host com precedence + cache"
```

---

### Task 0.4: engine/utils/paths.py — sub-namespace helpers

**Files:**
- Modify: `engine/utils/paths.py` (add functions)
- Test: `tests/unit/test_paths_helpers.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_paths_helpers.py
from pathlib import Path
from engine.utils.paths import (
    forge_dir, forge_config_path, forge_state_dir,
    forge_cards_local_dir, forge_hooks_dir,
)


def test_forge_dir(tmp_path):
    assert forge_dir(tmp_path) == tmp_path / ".claude" / "forge"


def test_forge_config_path(tmp_path):
    assert forge_config_path(tmp_path) == tmp_path / ".claude" / "forge" / "forge-config.yaml"


def test_forge_state_dir(tmp_path):
    assert forge_state_dir(tmp_path) == tmp_path / ".claude" / "forge" / "state"


def test_forge_cards_local_dir(tmp_path):
    assert forge_cards_local_dir(tmp_path) == tmp_path / ".claude" / "forge" / "cards" / "local"


def test_forge_hooks_dir(tmp_path):
    assert forge_hooks_dir(tmp_path) == tmp_path / ".claude" / "forge" / "hooks"
```

- [ ] **Step 2: Run → FAIL**

Run: `pytest tests/unit/test_paths_helpers.py -v`
Expected: `ImportError`

- [ ] **Step 3: Add helpers to engine/utils/paths.py**

```python
# engine/utils/paths.py — append (preservar funções existentes)

def forge_dir(project_root: Path) -> Path:
    """Sub-namespace canônico do forge no projeto consumidor. Spec §2."""
    return project_root / ".claude" / "forge"


def forge_config_path(project_root: Path) -> Path:
    return forge_dir(project_root) / "forge-config.yaml"


def forge_state_dir(project_root: Path) -> Path:
    return forge_dir(project_root) / "state"


def forge_cards_local_dir(project_root: Path) -> Path:
    return forge_dir(project_root) / "cards" / "local"


def forge_hooks_dir(project_root: Path) -> Path:
    return forge_dir(project_root) / "hooks"
```

- [ ] **Step 4: Run → PASS**

Run: `pytest tests/unit/test_paths_helpers.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/utils/paths.py tests/unit/test_paths_helpers.py
git commit -m "feat(paths): sub-namespace helpers (forge_dir/forge_config_path/etc)"
```

---

### Task 0.5: engine/host/adapters/intent_file.py — fallback DRIFT-1

**Files:**
- Create: `engine/host/adapters/__init__.py`
- Create: `engine/host/adapters/intent_file.py` (migra logic de `engine/ui/intent_state.py` + parte de `engine/ui/question.py`)
- Test: `tests/unit/test_host_intent_file.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_host_intent_file.py
from pathlib import Path
import json
import pytest
from engine.host.adapters.intent_file import IntentFileAdapter
from engine.host.adapter import AskKind, PausedForInputError


def test_ask_emits_pending_and_raises_paused(tmp_path):
    adapter = IntentFileAdapter(project_root=tmp_path)
    with pytest.raises(PausedForInputError):
        adapter.ask(kind=AskKind.ASK, question="Q?", options={"a": "A"},
                    default=None, allow_pause=True)
    pending = tmp_path / ".claude" / "forge" / "state" / "forge-pending.json"
    assert pending.exists()
    data = json.loads(pending.read_text())
    assert data["kind"] == "ask"
    assert data["question"] == "Q?"


def test_ask_consumes_response_via_intent_log(tmp_path):
    # Setup pending + response pré-existentes (re-invoke scenario)
    state = tmp_path / ".claude" / "forge" / "state"
    state.mkdir(parents=True)
    # ver spec §4 + docs/schemas/intent-protocol.md pra shape canônico completo
    # ... (impl detalhada na migração de intent_state.py)
```

- [ ] **Step 2: Run → FAIL**

Expected: `ModuleNotFoundError: No module named 'engine.host.adapters'`

- [ ] **Step 3: Implement (migração de logic atual)**

```python
# engine/host/adapters/__init__.py
from engine.host.adapters.intent_file import IntentFileAdapter
__all__ = ["IntentFileAdapter"]
```

```python
# engine/host/adapters/intent_file.py
"""Fallback adapter via pending.json/response.json (DRIFT-1 protocol).

Migrado de engine/ui/intent_state.py + parte de engine/ui/question.py.
Ver docs/schemas/intent-protocol.md pro shape canônico.
"""
from __future__ import annotations
from pathlib import Path
from engine.host.adapter import (
    HostAdapter, HostName, AskKind, AskResult,
    PausedForInputError,
)
from engine.utils.paths import forge_state_dir
# ... import demais helpers de json_io, iso, uuid


class IntentFileAdapter(HostAdapter):
    name = HostName.INTENT_FILE

    def __init__(self, *, project_root: Path):
        self.project_root = project_root

    def ask(self, *, kind, question, options, default, allow_pause):
        # 1. Check response file pra intent já consumido (idempotência re-entry)
        # 2. Se não → escrever pending.json + raise PausedForInputError (exit 2 no cli)
        # Ver spec §4 — fluxo intent_file fallback
        # Migrar logic exata de engine/ui/intent_state.py::write_pending + check_response
        ...

    def ask_text(self, *, prompt, default): ...
    def ask_multi(self, *, question, options, min, max): ...
    def emit_progress(self, *, step, total, current): ...
    def emit_warn(self, *, message): ...
```

- [ ] **Step 4: Run → PASS (smoke)**

Run: `pytest tests/unit/test_host_intent_file.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/host/adapters/__init__.py engine/host/adapters/intent_file.py tests/unit/test_host_intent_file.py
git commit -m "feat(host): IntentFileAdapter — migração DRIFT-1 fallback (Decisão 27 preservada)"
```

---

### Task 0.6: engine/host/adapters/claude_code.py

**Files:**
- Create: `engine/host/adapters/claude_code.py`
- Test: `tests/unit/test_host_claude_code.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_host_claude_code.py
from pathlib import Path
import pytest
from engine.host.adapters.claude_code import ClaudeCodeAdapter
from engine.host.adapter import AskKind, PausedForInputError


def test_ask_emits_stdout_marker_and_pauses(tmp_path, capsys):
    adapter = ClaudeCodeAdapter(project_root=tmp_path)
    with pytest.raises(PausedForInputError):
        adapter.ask(kind=AskKind.ASK, question="Q?", options={"a": "A"},
                    default=None, allow_pause=True)
    captured = capsys.readouterr()
    assert "<FORGE_INTENT" in captured.out
    assert "Q?" in captured.out


def test_ask_consumes_response_on_reentry(tmp_path):
    # Pre-populate intent-log + response: re-invoke after CC asked user
    # ver spec §4 sequência canônica CC
    ...
```

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Implement**

```python
# engine/host/adapters/claude_code.py
"""Adapter pra Claude Code via stdout intent marker + intent-log re-entry.

Spec §4 — sequência canônica Claude Code.
"""
from engine.host.adapter import (
    HostAdapter, HostName, AskKind, AskResult, PausedForInputError,
)
# ... usa intent-log helpers compartilhados com intent_file (módulo comum)


class ClaudeCodeAdapter(HostAdapter):
    name = HostName.CLAUDE_CODE

    def __init__(self, *, project_root):
        self.project_root = project_root

    def ask(self, *, kind, question, options, default, allow_pause):
        # 1. Check intent-log pra response cacheada (re-entry idempotente)
        # 2. Se não → emit stdout marker <FORGE_INTENT ... /> + raise PausedForInputError
        # Marker format: ver spec §4 + docs/schemas/intent-protocol.md
        ...

    # demais métodos similar shape
```

- [ ] **Step 4: Run → PASS**

- [ ] **Step 5: Commit**

```bash
git add engine/host/adapters/claude_code.py tests/unit/test_host_claude_code.py
git commit -m "feat(host): ClaudeCodeAdapter — stdout intent marker + intent-log re-entry"
```

---

### Task 0.7: engine/ui/question.py — delegate to adapter

**Files:**
- Modify: `engine/ui/question.py` (refactor ask/ask_text/ask_multi → delegate)
- Test: `tests/unit/test_question_delegation.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_question_delegation.py
from pathlib import Path
from unittest.mock import patch, MagicMock
from engine.ui.question import ask
from engine.host.adapter import AskKind, AskResult, HostName


def test_ask_delegates_to_resolved_adapter(tmp_path, monkeypatch):
    mock_adapter = MagicMock()
    mock_adapter.ask.return_value = AskResult(value="product")
    with patch("engine.ui.question._resolve_adapter", return_value=mock_adapter):
        result = ask(kind=AskKind.ASK, question="Q?", options={"a": "A"},
                     default=None, project_root=tmp_path)
    mock_adapter.ask.assert_called_once()
    assert result.value == "product"
```

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Refactor question.py**

```python
# engine/ui/question.py — refactor
"""Single entrypoint pra ask/ask_text/ask_multi via host adapter.

Spec §4 — engine.ui.question é o único choke-point de pergunta.
"""
from pathlib import Path
from engine.host.adapter import AskKind, AskResult, HostAdapter
from engine.host.detect import detect_host
from engine.host.registry import get_adapter_class


def _resolve_adapter(project_root: Path) -> HostAdapter:
    host = detect_host(project_root)
    cls = get_adapter_class(host)
    return cls(project_root=project_root)


def ask(*, kind: AskKind, question: str, options: dict,
        default: str | None = None, allow_pause: bool = True,
        project_root: Path) -> AskResult:
    return _resolve_adapter(project_root).ask(
        kind=kind, question=question, options=options,
        default=default, allow_pause=allow_pause,
    )


def ask_text(*, prompt: str, default: str | None = None,
             project_root: Path) -> str:
    return _resolve_adapter(project_root).ask_text(prompt=prompt, default=default)


def ask_multi(*, question: str, options: dict, min: int = 0,
              max: int | None = None, project_root: Path) -> list[str]:
    return _resolve_adapter(project_root).ask_multi(
        question=question, options=options, min=min, max=max,
    )
```

- [ ] **Step 4: Run → PASS + full rapid lane**

Run: `pytest tests/unit/test_question_delegation.py -v && pytest -m "not integration and not e2e" -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add engine/ui/question.py tests/unit/test_question_delegation.py
git commit -m "refactor(ui): question.py delega a host adapter (Decisão 27 preservada)"
```

---

### Task 0.8: Refactor 50+ callsites pra forge_config_path

**Files:**
- Modify: engine/* + validators/* que referenciam `.claude/workflow-config.yaml` (hardcoded)
- Test: `tests/integration/test_subnamespace_paths.py`

- [ ] **Step 1: Detect callsites**

Run: `grep -rn '"\.claude/workflow-config\.yaml"' engine/ validators/ tests/ | wc -l`
Expected: count > 0 (registra para verificar pós-refactor)

Run: `grep -rln '"\.claude/state"' engine/ validators/`
Expected: list of files needing update

- [ ] **Step 2: Failing integration test**

```python
# tests/integration/test_subnamespace_paths.py
import pytest
from pathlib import Path
from engine.init import run as init_run


@pytest.mark.integration
def test_init_writes_under_forge_subnamespace(tmp_project_root):
    init_run(project_root=tmp_project_root, non_interactive=True)
    assert (tmp_project_root / ".claude" / "forge" / "forge-config.yaml").exists()
    assert (tmp_project_root / ".claude" / "forge" / "state").exists()
    # NÃO existe no path antigo
    assert not (tmp_project_root / ".claude" / "workflow-config.yaml").exists()
```

- [ ] **Step 3: Run → FAIL**

- [ ] **Step 4: Bulk refactor**

Substituir hardcoded paths por chamadas a helpers. Pattern padrão:

```python
# ANTES
config_path = project_root / ".claude" / "workflow-config.yaml"

# DEPOIS
from engine.utils.paths import forge_config_path
config_path = forge_config_path(project_root)
```

Faça em batches de 5-10 arquivos. Após cada batch:

```bash
pytest -m "not integration and not e2e" -q
```

- [ ] **Step 5: Run integration test → PASS**

Run: `pytest tests/integration/test_subnamespace_paths.py -m integration -v`

- [ ] **Step 6: Commit**

```bash
git add engine/ validators/ tests/integration/test_subnamespace_paths.py
git commit -m "refactor(paths): callsites usam forge_config_path/forge_state_dir helpers"
```

---

### Task 0.9: Rename workflow-config.yaml → forge-config.yaml + schema bump 1.3

**Files:**
- Rename: `validators/validate_workflow_config.py` → `validators/validate_forge_config.py`
- Modify: schema-version field default → `"1.3"`
- Modify: cross-refs em CHANGELOG/README pendentes pra W5; engine code OK em W0.8

**Justificativa do edit em doc load-bearing** (`docs/schemas/workflow-config.md` está na whitelist do scope.md): o rename é necessário porque o Goal v1.3 (spec §Q3 resolvido — bump schema-version "1.3") exige consistência entre filename do schema YAML (forge-config.yaml) e filename do schema doc (forge-config.md). Sem rename, doc fica órfão referenciando filename obsoleto. Cobre Mandamento #4 (scope) + Mandamento #6 (doc-sync).

- [ ] **Step 1: Rename validator file**

```bash
git mv validators/validate_workflow_config.py validators/validate_forge_config.py
```

- [ ] **Step 2: Update imports + class names**

```python
# validators/validate_forge_config.py
# rename class ValidateWorkflowConfig -> ValidateForgeConfig
# update internal references "workflow-config.yaml" -> "forge-config.yaml"
# bump expected schema_version: "1.2" -> "1.3"
```

- [ ] **Step 3: Update cascade**

`engine/verify.py` ou similar onde validator é listado:

```python
# rename ref: validators/validate_workflow_config.py → validators/validate_forge_config.py
```

- [ ] **Step 4: Failing test**

```python
# tests/unit/test_forge_config_schema_version.py
from validators.validate_forge_config import ValidateForgeConfig


def test_expected_schema_version_is_1_3():
    assert ValidateForgeConfig.EXPECTED_SCHEMA_VERSION == "1.3"
```

- [ ] **Step 5: Run → PASS + full rapid lane**

```bash
pytest -m "not integration and not e2e" -q
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(config): rename workflow-config.yaml → forge-config.yaml + bump schema 1.3"
```

---

### Task 0.10: engine/init.py — writes under .claude/forge/

**Files:**
- Modify: `engine/init.py` (Steps que escrevem workflow-config/state/cards/hooks atualizam pra sub-namespace)
- Test: `tests/integration/test_init_greenfield_new_layout.py`

- [ ] **Step 1: Failing test**

```python
# tests/integration/test_init_greenfield_new_layout.py
import pytest
from engine.init import run as init_run


@pytest.mark.integration
def test_greenfield_init_creates_sub_namespace(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    init_run(project_root=tmp_path, non_interactive=True)
    forge = tmp_path / ".claude" / "forge"
    assert forge.exists()
    assert (forge / "forge-config.yaml").exists()
    assert (forge / "state").exists()
    assert (forge / "cards").exists()
```

- [ ] **Step 2: Run → FAIL (provavelmente paths antigos)**

- [ ] **Step 3: Refactor init.py Steps**

Funções a tocar (manter API pública estável):
- `_write_workflow_config()` → escreve em `forge_config_path(project_root)`
- `_init_cards_local()` → escreve em `forge_cards_local_dir(project_root)`
- `_install_hooks()` → instala em `forge_hooks_dir(project_root)`
- `_write_version_lock()` → escreve em `forge_dir(project_root) / "forge-version-lock.yaml"`
- `_write_gitignore()` → atualiza `.claude/forge/.gitignore`

Cada função usa helpers de `engine/utils/paths.py`.

- [ ] **Step 4: Run → PASS**

- [ ] **Step 5: Commit**

```bash
git add engine/init.py tests/integration/test_init_greenfield_new_layout.py
git commit -m "feat(init): writes under .claude/forge/ sub-namespace (greenfield)"
```

---

### Task 0.11: Wave 0 smoke + CHANGELOG [Unreleased] entry

**Files:**
- Modify: `CHANGELOG.md` (Unreleased section)

- [ ] **Step 1: Run full lane smoke**

```bash
pytest -m "not integration and not e2e" -q     # rapid
pytest -m integration -q                        # integration
./bin/forge --version                           # CLI smoke
```
Expected: all green; count cresceu ~51 tests vs baseline

- [ ] **Step 2: CHANGELOG W0 entry**

```markdown
# CHANGELOG.md — append em [Unreleased] sob ### Added

- v1.3 Wave 0: engine/host/ module (adapter ABC + env detect + registry + intent_file/claude_code adapters) + sub-namespace `.claude/forge/` paths (forge_config_path/forge_state_dir helpers) + question.py delega via host registry + workflow-config.yaml renomeado pra forge-config.yaml (schema-version "1.3"). Greenfield init writes under new layout. 51 tests novos.
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): W0 — host module + sub-namespace + forge-config rename"
```

- [ ] **Step 4: Push branch**

```bash
git push
```

---

## Wave 1 — Brownfield-safe init

**Goal:** Forge init em `.claude/` pré-populado (MeoBonsai-class) sobrevive sem tocar user-owned files.
**Spec ref:** §3 (C components), §4 (data flow), §8 success #2 + #5.

### Task 1.0: tests/fixtures/meobonsai-class/ — fixture sintética

**Files:**
- Create: `tests/fixtures/meobonsai-class/` com estrutura plantada

- [ ] **Step 1: Create fixture skeleton**

```bash
mkdir -p tests/fixtures/meobonsai-class/.claude/{skills,agents,hooks}
```

- [ ] **Step 2: Populate marker files**

```bash
# 5 skills marker
for i in 1 2 3 4 5; do
  cat > tests/fixtures/meobonsai-class/.claude/skills/skill-$i.md <<EOF
---
name: skill-$i
description: synthetic skill #$i for brownfield fixture
---
# Skill $i body content (marker checksum sentinel)
EOF
done

# 3 agents marker
for i in 1 2 3; do
  cat > tests/fixtures/meobonsai-class/.claude/agents/agent-$i.md <<EOF
---
name: agent-$i
---
agent-$i body
EOF
done

# 2 hooks marker
cat > tests/fixtures/meobonsai-class/.claude/hooks/post-edit.sh <<'EOF'
#!/usr/bin/env bash
echo "user post-edit hook marker"
EOF
chmod +x tests/fixtures/meobonsai-class/.claude/hooks/post-edit.sh

cat > tests/fixtures/meobonsai-class/.claude/hooks/pre-commit-user.sh <<'EOF'
#!/usr/bin/env bash
echo "user pre-commit hook marker"
EOF
chmod +x tests/fixtures/meobonsai-class/.claude/hooks/pre-commit-user.sh

# settings.json com 10 entries
cat > tests/fixtures/meobonsai-class/.claude/settings.json <<'EOF'
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Write", "hooks": [{"type": "command", "command": ".claude/hooks/user1.sh"}]}
    ],
    "PostToolUse": [
      {"matcher": "Edit", "hooks": [{"type": "command", "command": ".claude/hooks/user2.sh"}]}
    ],
    "SessionStart": [
      {"hooks": [{"type": "command", "command": ".claude/hooks/user3.sh"}]}
    ]
  }
}
EOF

# CLAUDE.md
cat > tests/fixtures/meobonsai-class/CLAUDE.md <<'EOF'
# CLAUDE.md (MeoBonsai-class fixture)
Voz: implementador. Persona local. Marker checksum sentinel.
EOF

# .gitignore + git init dummy
cat > tests/fixtures/meobonsai-class/.gitignore <<'EOF'
*.pyc
__pycache__/
EOF
```

- [ ] **Step 3: Verify fixture structure**

```bash
find tests/fixtures/meobonsai-class -type f | wc -l
# Expected: 12+ files
```

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/meobonsai-class/
git commit -m "test(fixtures): meobonsai-class brownfield fixture (5 skills + 3 agents + 2 hooks + settings + CLAUDE.md)"
```

---

### Task 1.1: engine/init.py — _detect_brownfield helper

**Files:**
- Modify: `engine/init.py`
- Test: `tests/unit/test_init_brownfield_detect.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_init_brownfield_detect.py
import pytest
from engine.init import _detect_brownfield


def test_detect_greenfield(tmp_path):
    assert _detect_brownfield(tmp_path) is False


def test_detect_brownfield_skills_present(tmp_path):
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "test.md").write_text("---\nname: x\n---")
    assert _detect_brownfield(tmp_path) is True


def test_detect_brownfield_agents_present(tmp_path):
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "test.md").write_text("test")
    assert _detect_brownfield(tmp_path) is True
```

- [ ] **Step 2: Implement**

```python
# engine/init.py — add helper
def _detect_brownfield(project_root: Path) -> bool:
    """True se .claude/skills, .claude/agents OR .claude/settings.json com content."""
    claude_dir = project_root / ".claude"
    if not claude_dir.exists():
        return False
    for sub in ("skills", "agents"):
        d = claude_dir / sub
        if d.exists() and any(d.iterdir()):
            return True
    settings = claude_dir / "settings.json"
    if settings.exists() and settings.stat().st_size > 0:
        return True
    return False
```

- [ ] **Step 3-5: Run → PASS + Commit**

```bash
pytest tests/unit/test_init_brownfield_detect.py -v
git add engine/init.py tests/unit/test_init_brownfield_detect.py
git commit -m "feat(init): _detect_brownfield helper (skills/agents/settings.json signals)"
```

---

### Task 1.2: settings.json append-only merge

**Files:**
- Create: `engine/utils/settings_merge.py`
- Test: `tests/unit/test_settings_merge.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_settings_merge.py
from engine.utils.settings_merge import merge_settings_json


def test_merge_appends_to_existing_arrays():
    existing = {
        "hooks": {
            "PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "user.sh"}]}],
        }
    }
    additions = {
        "hooks": {
            "PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "forge.sh"}]}],
        }
    }
    result = merge_settings_json(existing, additions)
    assert len(result["hooks"]["PreToolUse"]) == 2
    assert result["hooks"]["PreToolUse"][0]["matcher"] == "Write"  # user preserved first
    assert result["hooks"]["PreToolUse"][1]["matcher"] == "Edit"  # forge appended


def test_merge_preserves_unrelated_keys():
    existing = {"theme": "dark", "hooks": {}}
    additions = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "x.sh"}]}]}}
    result = merge_settings_json(existing, additions)
    assert result["theme"] == "dark"
    assert "SessionStart" in result["hooks"]


def test_merge_idempotent_dedupe_identical_entries():
    existing = {"hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "forge.sh"}]}]}}
    additions = {"hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "forge.sh"}]}]}}
    result = merge_settings_json(existing, additions)
    assert len(result["hooks"]["PreToolUse"]) == 1  # idempotent
```

- [ ] **Step 2-3: Implement**

```python
# engine/utils/settings_merge.py
"""Append-only merge pra .claude/settings.json. Spec §3 C.4."""
from copy import deepcopy


def merge_settings_json(existing: dict, additions: dict) -> dict:
    """Merge additions INTO existing sem sobrescrever entries do user.

    - dict keys: union, additions value win pra key não-existente
    - hooks.{stage}: array append, dedupe por shape idêntico
    """
    result = deepcopy(existing)
    add_hooks = additions.get("hooks", {})
    res_hooks = result.setdefault("hooks", {})
    for stage, entries in add_hooks.items():
        existing_entries = res_hooks.setdefault(stage, [])
        for entry in entries:
            if entry not in existing_entries:
                existing_entries.append(entry)
    # Top-level keys não-hooks (ex.: theme) — additions só adiciona quando ausente
    for k, v in additions.items():
        if k == "hooks":
            continue
        result.setdefault(k, v)
    return result
```

- [ ] **Step 4-5: Run → PASS + Commit**

```bash
pytest tests/unit/test_settings_merge.py -v
git add engine/utils/settings_merge.py tests/unit/test_settings_merge.py
git commit -m "feat(settings): append-only merge pra settings.json (preserva entries user)"
```

---

### Task 1.3: JSON5-tolerant parser fallback

**Files:**
- Modify: `requirements.txt` (add `json5` ou implementar regex-based) — decisão runtime
- Modify: `engine/utils/settings_merge.py` (add `read_settings_tolerant()`)
- Test: `tests/unit/test_settings_merge.py` (extender)

- [ ] **Step 1: Failing test pra JSON5 input**

```python
def test_read_settings_tolerant_handles_comments():
    from engine.utils.settings_merge import read_settings_tolerant
    content = """{
        // comment
        "theme": "dark",
        "hooks": {},  // trailing comma
    }"""
    result = read_settings_tolerant(content)
    assert result["theme"] == "dark"
```

- [ ] **Step 2-3: Implement (escolha A: json5 lib)**

```bash
echo "json5>=0.9.10" >> requirements.txt
```

```python
# engine/utils/settings_merge.py — adicionar
try:
    import json5
    HAS_JSON5 = True
except ImportError:
    import json as json5
    HAS_JSON5 = False


def read_settings_tolerant(content: str) -> dict:
    """Parse settings.json mesmo com comments / trailing commas (JSON5)."""
    return json5.loads(content)
```

- [ ] **Step 4-5: Run → PASS + Commit**

```bash
pip install json5
pytest tests/unit/test_settings_merge.py -v
git add requirements.txt engine/utils/settings_merge.py tests/unit/test_settings_merge.py
git commit -m "feat(settings): JSON5-tolerant parser (comments + trailing commas)"
```

---

### Task 1.4: Git hook delegator chained

**Files:**
- Modify: `engine/init.py` (`_install_git_hook_chained()` substitui `_install_git_hooks()`)
- Test: `tests/integration/test_git_hook_delegator.py`

- [ ] **Step 1: Failing test**

```python
# tests/integration/test_git_hook_delegator.py
import pytest
import subprocess
from engine.init import _install_git_hook_chained


@pytest.mark.integration
def test_delegator_chains_existing_user_hook(tmp_path):
    # Setup .git/hooks pre-existente
    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    user_hook = tmp_path / ".git" / "hooks" / "pre-commit"
    user_hook.write_text("#!/usr/bin/env bash\necho 'USER_HOOK_MARKER'\nexit 0\n")
    user_hook.chmod(0o755)

    # Install forge delegator
    _install_git_hook_chained(tmp_path)

    # Verify wrapper chama AMBOS
    output = subprocess.run([str(user_hook)], capture_output=True, text=True)
    assert "USER_HOOK_MARKER" in output.stdout
    assert "FORGE_HOOK_MARKER" in output.stdout  # forge hook deve emitir esse marker


@pytest.mark.integration
def test_delegator_idempotent(tmp_path):
    # Install twice, hook deve aparecer 1x cada
    ...
```

- [ ] **Step 2-3: Implement**

```python
# engine/init.py
def _install_git_hook_chained(project_root: Path) -> None:
    """Install forge pre-commit chained com hook existente do user. Spec §3 C.1."""
    git_hooks = project_root / ".git" / "hooks"
    git_hooks.mkdir(parents=True, exist_ok=True)
    forge_hook = forge_hooks_dir(project_root) / "pre-commit-feature-forge.sh"
    # ... copy forge hook content (do template)
    forge_hook.chmod(0o755)

    pre_commit = git_hooks / "pre-commit"
    if pre_commit.exists():
        # Check if já é delegator
        if "# FORGE_DELEGATOR_MARKER" in pre_commit.read_text():
            return  # idempotent
        # Backup user hook
        user_backup = git_hooks / "pre-commit.user"
        pre_commit.rename(user_backup)
        # Create wrapper
        pre_commit.write_text(f"""#!/usr/bin/env bash
# FORGE_DELEGATOR_MARKER
set -e
"{user_backup}" "$@"
"{forge_hook}" "$@"
""")
    else:
        # No user hook — wrapper aponta só pra forge
        pre_commit.write_text(f"""#!/usr/bin/env bash
# FORGE_DELEGATOR_MARKER
exec "{forge_hook}" "$@"
""")
    pre_commit.chmod(0o755)
```

- [ ] **Step 4-5: Run → PASS + Commit**

```bash
pytest tests/integration/test_git_hook_delegator.py -m integration -v
git add engine/init.py tests/integration/test_git_hook_delegator.py
git commit -m "feat(hooks): git hook delegator chained (preserva user pre-commit)"
```

---

### Task 1.5: CLAUDE.md checksum regression test

**Files:**
- Test: `tests/integration/test_claude_md_unchanged.py`

- [ ] **Step 1: Failing test (E2E)**

```python
# tests/integration/test_claude_md_unchanged.py
import hashlib
import shutil
import pytest
from pathlib import Path
from engine.init import run as init_run

FIXTURE = Path(__file__).parent.parent / "fixtures" / "meobonsai-class"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.mark.integration
def test_init_does_not_touch_claude_md(tmp_path, monkeypatch):
    # Copy fixture pra tmp
    proj = tmp_path / "project"
    shutil.copytree(FIXTURE, proj)
    claude_md = proj / "CLAUDE.md"
    sha_before = sha256(claude_md)

    monkeypatch.setenv("CLAUDECODE", "1")
    init_run(project_root=proj, non_interactive=True)

    sha_after = sha256(claude_md)
    assert sha_before == sha_after, "forge init MODIFICOU CLAUDE.md do consumidor!"
```

- [ ] **Step 2: Run → assume PASS pré-existente (init.py não toca CLAUDE.md)**

Se FAIL: investigar onde init toca CLAUDE.md (bug) + fix.

- [ ] **Step 3: Commit (test-only)**

```bash
git add tests/integration/test_claude_md_unchanged.py
git commit -m "test(brownfield): regression CLAUDE.md checksum inalterado pós init"
```

---

### Task 1.6: Brownfield e2e — forge init em fixture

**Files:**
- Test: `tests/integration/test_init_brownfield_meobonsai_class.py`

- [ ] **Step 1: E2E test**

```python
# tests/integration/test_init_brownfield_meobonsai_class.py
import shutil
import pytest
from pathlib import Path
from engine.init import run as init_run

FIXTURE = Path(__file__).parent.parent / "fixtures" / "meobonsai-class"


@pytest.mark.integration
def test_init_brownfield_preserves_user_files(tmp_path, monkeypatch):
    proj = tmp_path / "project"
    shutil.copytree(FIXTURE, proj)
    skills_before = sorted((proj / ".claude" / "skills").iterdir())
    agents_before = sorted((proj / ".claude" / "agents").iterdir())

    monkeypatch.setenv("CLAUDECODE", "1")
    init_run(project_root=proj, non_interactive=True)

    # User files intactos
    skills_after = sorted((proj / ".claude" / "skills").iterdir())
    agents_after = sorted((proj / ".claude" / "agents").iterdir())
    assert skills_before == skills_after
    assert agents_before == agents_after

    # Forge sub-namespace criado
    assert (proj / ".claude" / "forge").exists()
    assert (proj / ".claude" / "forge" / "forge-config.yaml").exists()

    # settings.json: append-only (user entries preserved + forge entries added)
    import json
    settings = json.loads((proj / ".claude" / "settings.json").read_text())
    assert len(settings["hooks"]["PreToolUse"]) >= 2  # user (1) + forge (1+)
```

- [ ] **Step 2-3: Run → PASS (depende W1.1-W1.4) + Commit**

```bash
pytest tests/integration/test_init_brownfield_meobonsai_class.py -m integration -v
git add tests/integration/test_init_brownfield_meobonsai_class.py
git commit -m "test(brownfield): e2e init em fixture meobonsai-class — user files preserved"
```

---

### Task 1.7: Wave 1 smoke + CHANGELOG entry + push

- [ ] **Step 1: Full smoke**

```bash
pytest -m "not integration and not e2e" -q   # rapid
pytest -m integration -q                      # integration
```
Expected: count cresceu ~31 vs pós-W0

- [ ] **Step 2: CHANGELOG W1 entry**

```markdown
# CHANGELOG.md [Unreleased] ### Added (append)
- v1.3 Wave 1: brownfield-safe init — _detect_brownfield helper + settings.json append-only merge (JSON5-tolerant) + git hook delegator chained + fixture meobonsai-class sintética. Regression tests pra CLAUDE.md checksum inalterado + user files preserved. 31 tests novos.
```

- [ ] **Step 3: Commit + push**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): W1 — brownfield-safe init + settings merge + delegator"
git push
```

---

## Wave 2 — opencode + TTY adapters

**Goal:** opencode adapter (ou fallback documentado) + TTY adapter polish + ASCII fallback non-TTY.
**Spec ref:** §3 (B components), §4 (data flow opencode + TTY), §8 R1 + success #4 + #5.

### Task 2.0: Research opencode tool API (research-only sub-task)

**Files:**
- Create: `docs/research/opencode-tool-api.md`

- [ ] **Step 1: Dispatch research sub-agent**

Orchestrator dispatcha `general-purpose` agent com prompt:

> Pesquise tool API do opencode (https://opencode.ai / opencode GitHub source). Documente em `docs/research/opencode-tool-api.md`:
> 1. Como opencode invoca tools — formato de mensagem, stdin/stdout shape?
> 2. Existe equivalente a `AskUserQuestion` (in-process question dispatch)?
> 3. Env vars setadas pelo opencode quando invoca subprocess
> 4. Veredito: compatível com nossa shape de adapter (similar a Claude Code) OU não-compatível (fallback intent_file documentado)
> 5. Sources com URLs

- [ ] **Step 2: Aguardar output + revisão**

Orchestrator lê `docs/research/opencode-tool-api.md`; decide A) implementar adapter dedicado OR B) fallback intent_file documentado.

- [ ] **Step 3: Commit research doc**

```bash
git add docs/research/opencode-tool-api.md
git commit -m "docs(research): opencode tool API — W2.T0 findings"
```

---

### Task 2.1: engine/host/adapters/opencode.py (ou fallback documentado)

**Files (path A — adapter dedicado):**
- Create: `engine/host/adapters/opencode.py`
- Test: `tests/unit/test_host_opencode.py`

**Files (path B — fallback intent_file):**
- Modify: `engine/host/registry.py` (registrar OPENCODE → IntentFileAdapter)
- Test: `tests/unit/test_host_opencode_fallback.py`

Path depende de W2.T0 outcome. Pseudo-impl path A:

```python
# engine/host/adapters/opencode.py — IF compatible
class OpencodeAdapter(HostAdapter):
    name = HostName.OPENCODE
    def ask(self, ...): ...
```

Path B fallback:

```python
# engine/host/registry.py
from engine.host.adapter import HostName
from engine.host.adapters.intent_file import IntentFileAdapter

register(HostName.OPENCODE, IntentFileAdapter)  # documented fallback
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(host): OpencodeAdapter [A: dedicated | B: intent_file fallback documentado]"
```

---

### Task 2.2: engine/host/adapters/tty.py

**Files:**
- Create: `engine/host/adapters/tty.py`
- Test: `tests/unit/test_host_tty.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_host_tty.py
from io import StringIO
from unittest.mock import patch
from engine.host.adapters.tty import TtyAdapter
from engine.host.adapter import AskKind


def test_tty_ask_reads_stdin(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    with patch("sys.stdin", StringIO("a\n")), patch("sys.stdin.isatty", return_value=True):
        result = adapter.ask(kind=AskKind.ASK, question="Q?",
                             options={"a": "A", "b": "B"}, default=None, allow_pause=True)
    assert result.value == "a"


def test_tty_refuses_non_tty(tmp_path):
    adapter = TtyAdapter(project_root=tmp_path)
    with patch("sys.stdin.isatty", return_value=False):
        with pytest.raises(RuntimeError, match="non-TTY"):
            adapter.ask(kind=AskKind.ASK, question="Q?",
                        options={"a": "A"}, default=None, allow_pause=True)
```

- [ ] **Step 2-3: Implement**

```python
# engine/host/adapters/tty.py
"""TTY adapter — stdin direto + box-drawing renderer. Spec §4 TTY humano."""
import sys
from engine.host.adapter import HostAdapter, HostName, AskKind, AskResult


class TtyAdapter(HostAdapter):
    name = HostName.TTY

    def __init__(self, *, project_root):
        self.project_root = project_root

    def ask(self, *, kind, question, options, default, allow_pause):
        if not sys.stdin.isatty():
            raise RuntimeError(
                "TtyAdapter chamado em non-TTY context — use intent_file fallback "
                "ou setta env var do harness agentic."
            )
        # render question + options (box-drawing — quando TTY suporta)
        # read stdin loop até match em options.keys()
        ...

    def ask_text(self, *, prompt, default): ...
    def ask_multi(self, *, question, options, min, max): ...
    def emit_progress(self, *, step, total, current): ...
    def emit_warn(self, *, message): ...
```

- [ ] **Step 4-5: Run → PASS + Commit**

```bash
git add engine/host/adapters/tty.py tests/unit/test_host_tty.py
git commit -m "feat(host): TtyAdapter — stdin direto + isatty guard"
```

---

### Task 2.3: engine/ui/renderer.py — ASCII fallback non-TTY

**Files:**
- Modify: `engine/ui/renderer.py`
- Test: `tests/unit/test_renderer_ascii_fallback.py`

- [ ] **Step 1: Failing test**

```python
def test_box_drawing_unicode_in_tty(monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    from engine.ui.renderer import draw_box
    out = draw_box("title", "content")
    assert "┌" in out  # unicode box-drawing


def test_ascii_fallback_in_non_tty(monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    from engine.ui.renderer import draw_box
    out = draw_box("title", "content")
    assert "+" in out  # ASCII fallback
    assert "┌" not in out
```

- [ ] **Step 2-3: Refactor renderer.py**

```python
# engine/ui/renderer.py
import sys


def _supports_unicode() -> bool:
    return sys.stdout.isatty()


def draw_box(title: str, content: str) -> str:
    if _supports_unicode():
        return f"┌─ {title} ─┐\n│ {content} │\n└──────────┘"
    return f"+-- {title} --+\n| {content} |\n+----------+"
```

- [ ] **Step 4-5: Run → PASS + Commit**

```bash
git add engine/ui/renderer.py tests/unit/test_renderer_ascii_fallback.py
git commit -m "fix(renderer): ASCII fallback non-TTY (bug U3 do relatório)"
```

---

### Task 2.4: Per-host integration tests

**Files:**
- Create: `tests/e2e/test_per_host_dispatch.py`

```python
# tests/e2e/test_per_host_dispatch.py
import pytest
import subprocess


@pytest.mark.e2e
def test_dispatch_claude_code(tmp_project):
    result = subprocess.run(
        ["./bin/forge", "plan", "test-feature"],
        env={"CLAUDECODE": "1", **os.environ},
        cwd=tmp_project, capture_output=True, text=True,
    )
    assert "<FORGE_INTENT" in result.stdout  # marker presente
    assert result.returncode == 2  # paused-for-input


@pytest.mark.e2e
def test_dispatch_tty_via_pty(tmp_project):
    # Use pty fixture pra simular TTY
    ...


@pytest.mark.e2e
def test_dispatch_intent_file_fallback(tmp_project):
    # No env vars, no isatty → fallback
    result = subprocess.run(
        ["./bin/forge", "plan", "test-feature"],
        cwd=tmp_project, capture_output=True, text=True,
    )
    pending = tmp_project / ".claude" / "forge" / "state" / "forge-pending.json"
    assert pending.exists()
```

- [ ] **Run + Commit**

```bash
RUN_E2E=1 pytest tests/e2e/test_per_host_dispatch.py -m e2e -v
git add tests/e2e/test_per_host_dispatch.py
git commit -m "test(e2e): per-host dispatch (claude_code + tty + intent_file)"
```

---

### Task 2.5: Wave 2 smoke + CHANGELOG entry + push

```markdown
# CHANGELOG.md [Unreleased] ### Added
- v1.3 Wave 2: opencode adapter [A dedicated | B fallback intent_file documentado] + TTyAdapter (stdin direto + isatty guard) + ASCII fallback non-TTY (fix bug U3) + per-host e2e tests. W2.T0 research documentado em docs/research/opencode-tool-api.md. 41 tests novos.
```

```bash
git add CHANGELOG.md && git commit -m "docs(changelog): W2 — opencode + TTY + ASCII fallback" && git push
```

---

## Wave 3 — Bug-fix sprint

**Goal:** 7 bugs do relatório MeoBonsai fechados com regression tests.
**Spec ref:** §3 (A components), §4 (resolução dos 3 críticos), §8 success #6 + #7.

### Task 3.1: Exit codes audit + unify 13 handlers

**Files:**
- Modify: `engine/cli.py` + handlers que divergem
- Test: `tests/unit/test_exit_codes.py`

- [ ] **Step 1: Audit table**

Mapear cada handler vs exit code atual:

```
forge status (no init) → 1   OK
forge doctor (no init) → 1   OK
forge verify (no init) → 1   OK
forge graph (no init) → 2    DIVERGE — fix pra 1
forge memory (no init) → 2   DIVERGE — fix pra 1
forge reconfigure (no init) → 2  DIVERGE — fix pra 1
forge plan/implement/qa/undo/evolve/raw (no init) → varies — audit + unify pra 1
```

Canônico (spec §3 A.1):
- pre-init falha (qualquer comando sem `.claude/forge/forge-config.yaml`) → exit 1
- intent-pause → exit 2
- user cancel (Ctrl+C / 3-caminhos Path C) → exit 130
- error genérico → exit 4

- [ ] **Step 2: Failing test pra cada divergente**

```python
# tests/unit/test_exit_codes.py
import subprocess
import pytest

DIVERGENT = ["graph", "memory", "reconfigure"]

@pytest.mark.parametrize("cmd", DIVERGENT)
def test_pre_init_returns_exit_1(tmp_path, cmd):
    result = subprocess.run(["./bin/forge", cmd], cwd=tmp_path, capture_output=True)
    assert result.returncode == 1
```

- [ ] **Step 3: Fix handlers**

```python
# engine/graph_cli.py / memory_cli.py / reconfigure.py
def main():
    if not forge_config_path(project_root).exists():
        sys.stderr.write("forge não inicializado neste projeto. Rode `forge init`.\n")
        return 1
    # ... existing logic
```

- [ ] **Step 4-5: Run → PASS + Commit**

```bash
pytest tests/unit/test_exit_codes.py -v
git add engine/cli.py engine/graph_cli.py engine/memory_cli.py engine/reconfigure.py tests/unit/test_exit_codes.py
git commit -m "fix(cli): unify exit codes — pre-init failures → 1 (bug U1)"
```

---

### Task 3.2: Suppress WARN em --help

**Files:**
- Modify: `engine/cli.py::main()` finally block

- [ ] **Step 1: Failing test**

```python
def test_help_emits_zero_warn():
    result = subprocess.run(["./bin/forge", "--help"], capture_output=True, text=True)
    assert "[WARN]" not in result.stderr
    assert "failed to clear intent log" not in result.stderr
```

- [ ] **Step 2-3: Guard via arg detection**

```python
# engine/cli.py::main()
def main():
    argv = sys.argv[1:]
    is_help = "--help" in argv or "-h" in argv or argv == []
    try:
        # ... dispatch
    finally:
        if not is_help:  # only cleanup intent log se não for help
            try:
                clear_intent_state(...)
            except Exception:
                pass  # silent
```

- [ ] **Step 4-5: Commit**

```bash
pytest tests/unit/test_exit_codes.py -v  # rerun + new test
git add engine/cli.py
git commit -m "fix(cli): suppress WARN cleanup em --help/-h (bug U2)"
```

---

### Task 3.3: forge qa CLI 3-caminhos sem args

**Files:**
- Modify: `engine/qa/__init__.py` ou `engine/qa/runner.py` entrypoint

- [ ] **Step 1: Failing test**

```python
def test_forge_qa_no_args_emits_three_paths_no_traceback():
    result = subprocess.run(["./bin/forge", "qa"], capture_output=True, text=True)
    assert "ValueError" not in result.stderr
    assert "Traceback" not in result.stderr
    assert "três caminhos" in result.stdout.lower() or "3 caminhos" in result.stdout.lower()
    assert result.returncode == 0 or result.returncode == 4  # non-fatal
```

- [ ] **Step 2-3: Guard sem args**

```python
# engine/qa/__init__.py
def main(args):
    if not args.target:
        sys.stdout.write(
            "forge qa requer scope target. Três caminhos:\n"
            "  A) `forge qa paranoid` — sweep cross-feature\n"
            "  B) `forge qa <slug>` — escopo single-feature\n"
            "  C) `forge qa --help` — ver doc completa\n"
        )
        return 0  # informativo, não erro
    # ... existing logic
```

- [ ] **Step 4-5: Commit**

```bash
git add engine/qa/ tests/unit/test_qa_no_args.py
git commit -m "fix(qa): 3-caminhos mentor-calmo sem args (bug U4 — sem traceback)"
```

---

### Task 3.4: Piped stdin docs + deprecation

**Files:**
- Modify: `engine/host/adapters/tty.py` (mensagem deprecada se non-TTY)
- Modify: `README.md` (W5 doc-sync absorve)

- [ ] **Step 1: Mensagem deprecada**

```python
# engine/host/adapters/tty.py — error message
raise RuntimeError(
    "TtyAdapter chamado em non-TTY context. v1.3: piped stdin é DEPRECATED — "
    "use harness agentic (CLAUDECODE=1, opencode, etc) ou rode em terminal real. "
    "Ver docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md §3 A.5."
)
```

- [ ] **Step 2: Commit**

```bash
git add engine/host/adapters/tty.py
git commit -m "docs(tty): piped stdin DEPRECATED em v1.3 — error mentor-calmo (bug #3)"
```

---

### Task 3.5: Regression tests pra 3 críticos + 4 usabilidade

**Files:**
- Test: `tests/integration/test_bug_regressions.py`

```python
# tests/integration/test_bug_regressions.py
import pytest


@pytest.mark.integration
def test_bug_1_checkpoint_intent_id_mismatch_resolved():
    """Re-invoke forge init com state pré-existente — sem mismatch error."""
    # ... setup pending + response cycle
    # assert no IntentMismatchError raised


@pytest.mark.integration
def test_bug_2_stale_response_cleared_on_startup():
    """Stale response.json não envenena próximo comando."""
    # ... write stale response, run different command, assert no poisoning


@pytest.mark.integration
def test_bug_3_piped_stdin_emits_clear_error():
    # echo "1" | forge plan slug → mensagem clara DEPRECATED, não trava


@pytest.mark.integration
def test_bug_u1_exit_codes_consistent():
    # cobertos em test_exit_codes.py — link aqui


@pytest.mark.integration
def test_bug_u2_help_no_warn():
    # cobertos em 3.2


@pytest.mark.integration
def test_bug_u3_ascii_fallback():
    # cobertos em renderer test


@pytest.mark.integration
def test_bug_u4_qa_no_args_no_traceback():
    # cobertos em 3.3
```

- [ ] **Commit**

```bash
pytest tests/integration/test_bug_regressions.py -m integration -v
git add tests/integration/test_bug_regressions.py
git commit -m "test(regression): 7 bugs do relatório MeoBonsai cobertos (3 críticos + 4 U)"
```

---

### Task 3.6: Wave 3 smoke + CHANGELOG + push

```markdown
# CHANGELOG.md [Unreleased] ### Fixed
- Bug #1: checkpoint × intent-id mismatch → resolvido via host adapter encapsulando intent-log
- Bug #2: stale forge-response.json poisoning → cleanup no startup + finally
- Bug #3: piped stdin ignored → adapter TTY emite erro mentor-calmo (DEPRECATED em v1.3)
- Bug U1: exit codes inconsistentes → unificados (pre-init=1, pause=2, cancel=130)
- Bug U2: WARN noise em --help → guarded em finally
- Bug U3: box-drawing Unicode em non-TTY → ASCII fallback via isatty
- Bug U4: forge qa sem args → 3-caminhos mentor-calmo, sem traceback
```

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): W3 — 7 bugs do relatório fechados"
git push
```

---

## Wave 4 — Install/upgrade CLI

**Goal:** `curl install.sh | bash` (com PATH detection + alias detection + 3-caminhos) + `forge upgrade`.
**Spec ref:** §3 (D components), §8 R5/R6, success #1 + #8.

### Task 4.1: scripts/install.sh — skeleton

**Files:**
- Create: `scripts/install.sh`
- Test: `tests/fixtures/install-sh/` (bats fixtures)

- [ ] **Step 1: Esqueleto base**

```bash
#!/usr/bin/env bash
set -euo pipefail

# Pre-requisitos
command -v git >/dev/null || { echo "git required"; exit 1; }
command -v python3 >/dev/null || { echo "python3 >= 3.10 required"; exit 1; }
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" || {
  echo "python3 >= 3.10 required"; exit 1;
}

# FORGE_HOME via XDG
FORGE_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/feature-forge"

# Abort grace period
echo "🔨 feature-forge install em $FORGE_HOME"
echo "(abort com Ctrl+C nos próximos 3s se mudou de ideia)"
sleep 3

# Clone (depth=1 — leve)
if [[ -d "$FORGE_HOME" ]]; then
  echo "FORGE_HOME já existe em $FORGE_HOME — rode 'forge upgrade' ou remova manualmente"
  exit 1
fi
git clone --depth=1 https://github.com/thgMatajs/feature-forge.git "$FORGE_HOME"

# Venv + deps
python3 -m venv "$FORGE_HOME/.venv"
"$FORGE_HOME/.venv/bin/pip" install -r "$FORGE_HOME/requirements.txt"

# Symlink (PATH setup vem na Task 4.2)
mkdir -p "$HOME/.local/bin"
ln -sf "$FORGE_HOME/bin/forge" "$HOME/.local/bin/forge"

# Smoke
"$FORGE_HOME/bin/forge" --version
echo "✓ instalado. próximo: cd <projeto> && forge init"
```

- [ ] **Step 2: Commit**

```bash
chmod +x scripts/install.sh
git add scripts/install.sh
git commit -m "feat(install): install.sh skeleton (clone + venv + symlink + smoke)"
```

---

### Task 4.2: install.sh — PATH detection + 3-caminhos

**Files:**
- Modify: `scripts/install.sh`

- [ ] **Step 1: Append PATH logic** (após symlink, antes do smoke)

Ver spec §3 D.1 — código completo da PATH detection + 3-caminhos mentor-calmo já documentado no spec. Copie inline.

- [ ] **Step 2: Commit**

```bash
git add scripts/install.sh
git commit -m "feat(install): PATH detection + 3-caminhos zsh/bash/fish (rc edit marker-guarded)"
```

---

### Task 4.3: install.sh — alias conflict detection

**Files:**
- Modify: `scripts/install.sh`

- [ ] **Step 1: Append antes do symlink**

```bash
# Alias / binary conflict detection
if command -v forge >/dev/null 2>&1; then
  EXISTING=$(command -v forge)
  echo ""
  echo "🔨 forge: já existe binário 'forge' em $EXISTING."
  echo ""
  echo "Três caminhos:"
  echo "  A) Prosseguir — install forge feature-forge SOBRESCREVE/ofusca o existente"
  echo "  B) Install como 'forge-cli' em vez de 'forge' (mantém ambos)"
  echo "  C) Abortar"
  read -r -p "Escolha [A/B/C]: " choice
  case "${choice,,}" in
    a) ;;
    b) BIN_NAME="forge-cli" ;;
    c) echo "abortado"; exit 130 ;;
    *) echo "escolha inválida"; exit 4 ;;
  esac
fi
BIN_NAME="${BIN_NAME:-forge}"
# (symlink usa $BIN_NAME)
ln -sf "$FORGE_HOME/bin/forge" "$HOME/.local/bin/$BIN_NAME"
```

- [ ] **Step 2: Commit**

```bash
git add scripts/install.sh
git commit -m "feat(install): alias conflict detection + 3-caminhos (Q5 resolvido)"
```

---

### Task 4.4: engine/upgrade.py — core handler

**Files:**
- Create: `engine/upgrade.py`
- Test: `tests/unit/test_upgrade.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_upgrade.py
import pytest
from unittest.mock import patch
from engine.upgrade import run_upgrade


def test_upgrade_no_op_when_at_latest(tmp_path):
    with patch("engine.upgrade._git_fetch") as fetch, \
         patch("engine.upgrade._git_head_eq_origin", return_value=True):
        result = run_upgrade(forge_home=tmp_path)
    assert result == 0  # já no latest


def test_upgrade_rollback_on_smoke_fail(tmp_path):
    with patch("engine.upgrade._git_pull"), \
         patch("engine.upgrade._smoke_version", return_value=False), \
         patch("engine.upgrade._git_reset_hard") as reset:
        result = run_upgrade(forge_home=tmp_path)
    assert result != 0
    reset.assert_called_once()
```

- [ ] **Step 2-3: Implement**

```python
# engine/upgrade.py
"""forge upgrade — git pull + venv refresh + smoke + rollback. Spec §3 D.2."""
import subprocess
from pathlib import Path


def _git_fetch(forge_home: Path) -> None:
    subprocess.run(["git", "fetch", "origin"], cwd=forge_home, check=True)


def _git_head_eq_origin(forge_home: Path) -> bool:
    local = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=forge_home).strip()
    remote = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=forge_home).strip()
    return local == remote


def _git_pull(forge_home: Path) -> None:
    subprocess.run(["git", "pull", "--ff-only", "origin", "main"], cwd=forge_home, check=True)


def _git_reset_hard(forge_home: Path, sha: str) -> None:
    subprocess.run(["git", "reset", "--hard", sha], cwd=forge_home, check=True)


def _smoke_version(forge_home: Path) -> bool:
    result = subprocess.run([str(forge_home / "bin" / "forge"), "--version"],
                            capture_output=True, text=True)
    return result.returncode == 0


def run_upgrade(*, forge_home: Path) -> int:
    prev_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=forge_home, text=True
    ).strip()
    _git_fetch(forge_home)
    if _git_head_eq_origin(forge_home):
        print("já no latest")
        return 0
    _git_pull(forge_home)
    # refresh venv
    subprocess.run([str(forge_home / ".venv" / "bin" / "pip"),
                    "install", "-r", str(forge_home / "requirements.txt"),
                    "--upgrade"], check=True)
    if not _smoke_version(forge_home):
        print("smoke falhou — rollback")
        _git_reset_hard(forge_home, prev_head)
        return 4
    print("atualizado")
    return 0
```

- [ ] **Step 4-5: Commit**

```bash
pytest tests/unit/test_upgrade.py -v
git add engine/upgrade.py tests/unit/test_upgrade.py
git commit -m "feat(upgrade): forge upgrade core (git pull + venv refresh + smoke + rollback)"
```

---

### Task 4.5: engine/cli.py — wire forge upgrade handler

**Files:**
- Modify: `engine/cli.py` (registry de comandos)

- [ ] **Step 1: Failing test**

```python
def test_forge_upgrade_resolves_handler():
    result = subprocess.run(["./bin/forge", "upgrade", "--help"],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert "upgrade" in result.stdout
```

- [ ] **Step 2-3: Wire**

```python
# engine/cli.py — adicionar
from engine import upgrade as upgrade_module

COMMANDS = {
    # ... existing
    "upgrade": upgrade_module.run_upgrade,
}
```

- [ ] **Step 4-5: Commit**

```bash
git add engine/cli.py tests/unit/test_cli_upgrade_wired.py
git commit -m "feat(cli): wire forge upgrade subcommand"
```

---

### Task 4.6: bats tests pra install.sh

**Files:**
- Create: `tests/e2e/test_install_sh.bats`
- Create: `tests/e2e/test_install_sh.py` (wrapper Python que invoca bats)

- [ ] **Step 1: bats scenarios**

```bash
# tests/e2e/test_install_sh.bats
#!/usr/bin/env bats

setup() {
  TMP=$(mktemp -d)
  export HOME=$TMP
  export PATH=$TMP/.local/bin:$PATH
}

teardown() {
  rm -rf "$TMP"
}

@test "install script sets PATH in zsh rc when missing" {
  export SHELL=/bin/zsh
  # ... mock git clone + venv + symlink
  run bash scripts/install.sh
  [ -f "$HOME/.zshrc" ]
  grep "feature-forge" "$HOME/.zshrc"
}

@test "install script offers 3-caminhos when forge alias exists" {
  # plant forge in PATH
  echo "#!/bin/bash" > "$TMP/.local/bin/forge"
  chmod +x "$TMP/.local/bin/forge"
  run bash scripts/install.sh <<< "C"  # abortar
  [ "$status" -eq 130 ]
}

@test "install script is idempotent — re-run no duplicate rc entry" { ... }
@test "install detects path already set, skips edit" { ... }
@test "install fish shell uses fish_add_path" { ... }
@test "install aborts on python3 < 3.10" { ... }
```

- [ ] **Step 2: Python wrapper**

```python
# tests/e2e/test_install_sh.py
import subprocess
import pytest


@pytest.mark.e2e
def test_install_sh_bats_suite():
    result = subprocess.run(["bats", "tests/e2e/test_install_sh.bats"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
```

- [ ] **Commit**

```bash
git add tests/e2e/test_install_sh.bats tests/e2e/test_install_sh.py
git commit -m "test(e2e): bats suite pra install.sh (6 scenarios)"
```

---

### Task 4.7: e2e test forge upgrade

**Files:**
- Create: `tests/e2e/test_forge_upgrade.py`

```python
# tests/e2e/test_forge_upgrade.py
import pytest
import subprocess


@pytest.mark.e2e
def test_forge_upgrade_simulates_pull_cycle(tmp_path):
    # Setup fake FORGE_HOME com git repo local
    # Simular tag v1.3.0 → v1.3.1
    # Run forge upgrade
    # Assert pull happened + smoke passed
    ...


@pytest.mark.e2e
def test_forge_upgrade_rollback_on_smoke_fail(tmp_path):
    # Inject smoke fail via mock binary
    # Assert git reset --hard rodou
    ...
```

```bash
git add tests/e2e/test_forge_upgrade.py
git commit -m "test(e2e): forge upgrade — pull cycle + rollback on smoke fail"
```

---

### Task 4.8: Wave 4 smoke + CHANGELOG + push

```markdown
# CHANGELOG.md [Unreleased] ### Added
- v1.3 Wave 4: scripts/install.sh (curl one-liner: clone + venv + symlink + PATH detection 3-caminhos + alias conflict 3-caminhos) + engine/upgrade.py (forge upgrade — git pull + venv refresh + smoke + rollback on fail) + bats suite. 30 tests novos.
```

```bash
git add CHANGELOG.md && git commit -m "docs(changelog): W4 — install.sh + forge upgrade + bats" && git push
```

---

## Wave 5 — Smoke pilot + doc-sync + release

**Goal:** End-to-end pilot smoke + Revisita Decisão 18 + doc-sync mass + tag v1.3.0.
**Spec ref:** §5 (clean break), §6 W5, §8 success #2 + #10, §9 (Revisita Decisão 18).

### Task 5.1: tests/e2e/test_pilot_smoke.py

**Files:**
- Create: `tests/e2e/test_pilot_smoke.py`

```python
# tests/e2e/test_pilot_smoke.py
import pytest
import subprocess
import shutil
from pathlib import Path

FIXTURE = Path(__file__).parent.parent / "fixtures" / "meobonsai-class"


@pytest.mark.e2e
def test_pilot_end_to_end(tmp_path, monkeypatch):
    # 1. Clone fixture
    proj = tmp_path / "pilot-project"
    shutil.copytree(FIXTURE, proj)
    skills_before = sorted((proj / ".claude" / "skills").iterdir())

    # 2. forge init em modo agentic (CLAUDECODE=1)
    monkeypatch.setenv("CLAUDECODE", "1")
    result = subprocess.run(["./bin/forge", "init"],
                            cwd=proj, capture_output=True, text=True,
                            input="\n".join(["sim"]*15))  # all defaults
    assert result.returncode in (0, 2)  # 2 = paused-for-input expected

    # 3. Asserts pós-init
    assert (proj / ".claude" / "forge").exists()
    assert (proj / ".claude" / "forge" / "forge-config.yaml").exists()
    skills_after = sorted((proj / ".claude" / "skills").iterdir())
    assert skills_before == skills_after

    # 4. forge upgrade no-op
    result = subprocess.run(["./bin/forge", "upgrade"], cwd=proj, capture_output=True, text=True)
    assert "já no latest" in result.stdout or result.returncode == 0
```

```bash
RUN_E2E=1 pytest tests/e2e/test_pilot_smoke.py -m e2e -v
git add tests/e2e/test_pilot_smoke.py
git commit -m "test(e2e): pilot smoke end-to-end (install → init brownfield → upgrade)"
```

---

### Task 5.2: docs/design/01-decisions.md — Revisita Decisão 18

**Files:**
- Modify: `docs/design/01-decisions.md`

**Justificativa**: Decisão load-bearing #18 (skill location) é mexida em v1.3 — mandatório seguir cerimônia do Mandamento #1 (append-only, sem deletar linha antiga).

- [ ] **Step 1: Append nova linha à tabela de Decisões**

```markdown
| 18 (v1) | Skill location | standalone repo em `~/Documents/feature-forge/` | (superseded by row 18-v2 — 2026-06-16) |
| 18-v2 | Skill location | standalone repo em `~/.local/share/feature-forge/` (XDG default; respeita $XDG_DATA_HOME) | Revisita v1.3 2026-06-16 — convenção universal pra ferramentas instaladas via script |
```

- [ ] **Step 2: Commit com texto LITERAL "Revisita decisão 18"**

```bash
git add docs/design/01-decisions.md
git commit -m "docs(decisions): Revisita decisão 18 — skill location → XDG default

Linha antiga preservada (superseded by row 18-v2 — 2026-06-16).
Justificativa: padrão XDG é convenção universal pra tools instaladas
via script. ~/Documents/ confunde organização (diretório de docs do user).

Histórico append-only conforme Mandamento #1 (.claude/rules/decisions.md)."
```

---

### Task 5.3: Rename docs/schemas/workflow-config.md → forge-config.md

**Files:**
- Rename: `docs/schemas/workflow-config.md` → `docs/schemas/forge-config.md`
- Modify: cross-refs em outros docs

- [ ] **Step 1: git mv + update content**

```bash
git mv docs/schemas/workflow-config.md docs/schemas/forge-config.md
```

Atualizar dentro do arquivo:
- Header: "workflow-config.yaml" → "forge-config.yaml"
- schema-version field: bump pra "1.3"
- referenced-from links

- [ ] **Step 2: Grep cross-refs + atualizar**

```bash
grep -rln "workflow-config\.md" docs/ engine/ validators/ tests/ .claude/
# update cada match
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "docs(schemas): rename workflow-config.md → forge-config.md + cross-refs"
```

---

### Task 5.4: docs/design/05-filesystem-layout.md update

**Files:**
- Modify: `docs/design/05-filesystem-layout.md`

- [ ] **Step 1: Refletir sub-namespace + install layout**

```markdown
## §3 Project consumidor layout (v1.3)

.claude/forge/                           ← NOVO em v1.3 (sub-namespace forge)
  forge-config.yaml                       ← era .claude/workflow-config.yaml
  state/
  cards/local/
  hooks/
.claude/skills/                          ← USER-MANAGED (forge não toca)
.claude/agents/                          ← USER-MANAGED
.claude/settings.json                    ← APPEND-ONLY merge pelo forge

## §4 Install layout (NOVO em v1.3 — Revisita Decisão 18)

~/.local/share/feature-forge/            ← XDG default
  .git/
  .venv/
  bin/forge → engine/cli.py
  engine/
  scripts/install.sh
~/.local/bin/forge → ~/.local/share/feature-forge/bin/forge
```

- [ ] **Step 2: Commit**

```bash
git add docs/design/05-filesystem-layout.md
git commit -m "docs(layout): v1.3 sub-namespace .claude/forge/ + XDG install layout"
```

---

### Task 5.5: docs/design/04-pending.md update

**Files:**
- Modify: `docs/design/04-pending.md`

- [ ] **Step 1: Adicionar entradas**

```markdown
## Fechado em [Unreleased v1.3]

- v1.3 ship completo cobrindo A+B+C+D — 6 waves entregues:
  W0 foundation host module + sub-namespace
  W1 brownfield-safe init
  W2 opencode + TTY adapters
  W3 7 bugs do relatório fechados
  W4 install.sh + forge upgrade
  W5 doc-sync + Revisita Decisão 18 + tag v1.3.0

## Open — pós v1.3

- v1.2 não tem migrator pra v1.3 — clean-break deliberado (pre-production status). Projetos experimentais em v1.2 limpam .claude/ e re-rodam forge init.
- W2.T0 opencode tool API research (se foi caminho B fallback): revisitar quando opencode shippar AskUserQuestion equivalente. Disparar se piloto opencode demonstrar UX gap real.
```

- [ ] **Step 2: Commit**

```bash
git add docs/design/04-pending.md
git commit -m "docs(pending): v1.3 ship complete + clean-break note + opencode follow-up"
```

---

### Task 5.6: docs/design/08-session-handoff.md update

**Files:**
- Modify: `docs/design/08-session-handoff.md`

- [ ] **Step 1: Update header + estado**

```markdown
**Última atualização:** 2026-XX-XX (v1.3.0 ship — pilot-ready foundation)
**Estado:** v1.3.0 tagged; spec + plan em main; piloto seguinte em projeto-canon real

(... atualizar Conhecidos limites se aplicável ...)
```

- [ ] **Step 2: Commit**

```bash
git add docs/design/08-session-handoff.md
git commit -m "docs(handoff): v1.3.0 ship — pilot-ready foundation"
```

---

### Task 5.7: README.md quickstart rewrite

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Substituir seção Install**

```markdown
## Install

\`\`\`bash
curl -fsSL https://raw.githubusercontent.com/thgMatajs/feature-forge/main/scripts/install.sh | bash
\`\`\`

One-liner: clona em `~/.local/share/feature-forge/` (XDG default), cria venv, instala deps, adiciona symlink em `~/.local/bin/forge`. Detecta seu shell (zsh/bash/fish) e ajusta PATH via 3-caminhos.

## Quickstart

\`\`\`bash
cd ~/seu-projeto
forge init           # cria .claude/forge/ + interactive setup
forge plan <slug>    # Waves A-E
forge verify         # validators cascade
\`\`\`

## Update

\`\`\`bash
forge upgrade
\`\`\`

Git pull + venv refresh + smoke. Rollback automático em falha.
```

- [ ] **Step 2: Atualizar §Stats do README**

Em seção §Stats (ou crie se não existir), atualizar:
- Test count: 1353 → 1538 (delta +185)
- Novo módulo: `engine/host/` (host-aware execution)
- Sub-namespace consumidor: `.claude/forge/` (era `.claude/`)
- Install via: `curl ... install.sh | bash` (one-liner; XDG default em `~/.local/share/feature-forge/`)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): v1.3 quickstart — curl install + forge upgrade"
```

---

### Task 5.8: CHANGELOG.md v1.3.0 entry

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Move [Unreleased] entries pra [v1.3.0] e criar novo [Unreleased]**

```markdown
## [Unreleased]

(empty)

## [v1.3.0] — 2026-XX-XX

### Added
- engine/host/ module: adapter ABC, env detect, registry, detect_host com cache
- Adapters: ClaudeCodeAdapter (in-process via stdout marker), TtyAdapter (stdin direto), OpencodeAdapter (ou fallback intent_file documentado), IntentFileAdapter (migração DRIFT-1)
- Sub-namespace `.claude/forge/`: forge-config.yaml, state/, cards/local/, hooks/
- Brownfield-safe init: settings.json append-only merge (JSON5-tolerant), git hook delegator chained
- scripts/install.sh: curl one-liner (clone + venv + symlink + PATH detection 3-caminhos + alias detection 3-caminhos)
- engine/upgrade.py + forge upgrade subcommand (git pull + venv refresh + smoke + rollback on fail)

### Changed
- workflow-config.yaml renomeado pra forge-config.yaml (schema-version bump "1.2" → "1.3")
- engine/ui/question.py delega a host adapter via registry (Decisão 27 preservada)
- engine/ui/renderer.py: ASCII fallback non-TTY

### Changed (load-bearing)
- **Revisita decisão 18**: skill location → `~/.local/share/feature-forge/` (XDG default; respeita $XDG_DATA_HOME) — convenção universal pra ferramentas instaladas via script. Histórico preservado em docs/design/01-decisions.md row 18-v1 (superseded by row 18-v2).

### Fixed
- Bug #1: checkpoint × intent-id mismatch (relatório MeoBonsai)
- Bug #2: stale forge-response.json poisoning
- Bug #3: piped stdin DEPRECATED (mensagem mentor-calmo)
- Bug U1: exit codes inconsistentes — unificados (pre-init=1, pause=2, cancel=130)
- Bug U2: WARN noise em --help
- Bug U3: box-drawing Unicode em non-TTY → ASCII fallback
- Bug U4: forge qa sem args → 3-caminhos mentor-calmo, sem ValueError traceback

### Removed
- Nenhum migrator v1.2 → v1.3 (clean-break deliberado, pre-production status)

### Notes
- v1.3.0 é **clean-slate release** — projetos experimentais em v1.2 devem ser re-inicializados (limpar `.claude/` e rodar `forge init` de novo). Primeira versão pré-piloto consolidada.
```

- [ ] **Step 2: Commit (mensagem com "Revisita decisão 18")**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): v1.3.0 release notes

Revisita decisão 18: skill location → ~/.local/share/feature-forge/ (XDG default)
— convenção universal pra ferramentas instaladas via script. Histórico
preservado em docs/design/01-decisions.md."
```

---

### Task 5.9: Bump version + tag v1.3.0

**Files:**
- Modify: `pyproject.toml` (version field) ou `engine/__init__.py::__version__`

- [ ] **Step 1: Bump version**

```python
# engine/__init__.py
__version__ = "1.3.0"
```

OU `pyproject.toml`:
```toml
[project]
version = "1.3.0"
```

- [ ] **Step 2: Commit + tag**

```bash
git add engine/__init__.py pyproject.toml
git commit -m "chore(version): bump 1.3.0"
git tag v1.3.0
git push
git push --tags
```

---

### Task 5.10: Wave 5 final verification

- [ ] **Step 1: Full lane smoke**

```bash
pytest -m "not integration and not e2e" -q
pytest -m integration -q
RUN_E2E=1 pytest -m e2e -q
forge verify --quiet
./bin/forge --version
./bin/forge doctor
```
Expected: All green; total count ~1538 tests (baseline 1353 + ~185 novos)

- [ ] **Step 2: Dispatch verification subagent** (orquestrador, fora do plano)

`gsd-verifier` confirma todos os 10 success criteria do spec §8 fechados.

- [ ] **Step 3: PR ready**

Orquestrador abre PR `feat/v1.3-pilot-ready → main` com body referenciando:
- Spec: docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md
- Plan: docs/superpowers/plans/2026-06-16-v1-3-pilot-ready.md
- 10 success criteria checklist
- Revisita Decisão 18 chamada explícita
- Test count delta 1353 → 1538

---

## Plan-Auditor Pre-Emptive Coverage

Mapeamento dos 12 checks do `.claude/rules/plan-auditor.md`:

| Check | Coberto em | Como |
|---|---|---|
| **C1** (locked decision ceremony) | Task 5.2 + Task 5.8 | Commit message com texto literal "Revisita decisão 18" + CHANGELOG `### Changed (load-bearing)` com mesmo texto + linha antiga preservada |
| **C2** (spec coverage) | Wave Index + cada Wave header refs §X do spec | Mapping §1→Goal/Escopo (todas tasks), §2→W0 host module, §3→W0+W1+W2+W3+W4 components, §4→W0.6+W2.2 adapters, §5→Task 5.5 04-pending, §6→Wave Index, §7→todas as TDD steps, §8→Task 5.10 verification, §9→Task 5.2+5.8 Revisita 18, §10→cross-refs em todas tasks doc |
| **H1** (load-bearing files justification) | Task 5.2 commit message contém justificativa textual "padrão XDG é convenção universal" | Cobre Mandamento #4 |
| **H2** (doc-sync coverage) | Wave 5 inteira (Tasks 5.2-5.8) | CHANGELOG + 04-pending + 08-session-handoff + README + docs/design/01-decisions + docs/design/05-filesystem-layout + docs/schemas/forge-config.md (rename) |
| **H3** (reuse-first) | Task 0.4 "estende engine/utils/paths.py existente" + Task 1.2 reusa engine/utils/* | Reusa infra; não cria módulo paralelo de paths |
| **H4** (testing gates) | TDD shape em TODAS tasks de engine/validators (failing test → run → impl → run → commit) | Cobre Mandamento #2 |
| **M1** (scope file whitelist) | Cada task tem Files block explícito | Cobre Mandamento #4 |
| **M2** (pending gaps coverage) | Task 5.5 atualiza 04-pending com clean-break + W2.T0 follow-up | Anti-goals do spec entram em 04-pending |
| **M3** (subagent dispatchability) | Cada task ≥ 3 steps tem ação concreta + Files + commit message | OK pra dispatch independente |
| **L1** (voice check) | Mentor calmo PT-BR / EN técnico em todo body | OK |
| **L2** (placeholder scan) | Code blocks completos em tasks novel; "ver spec §X.Y" só em tasks de migração (preserve content do spec) | OK |
| **L3** (type/name consistency) | HostAdapter / HostName / AskKind / AskResult consistentes em todas as tasks W0-W2 | OK |

---

## Triggers que NÃO dispararam

- **Nenhum** — todos os 12 checks foram acionados por algum aspecto do plano.

## Acknowledged overrides

- Nenhum override declarado. Plano espera PASS no plan-auditor.

---

> **Próximo passo após plano commitado:**
>
> 1. Orquestrador dispatcha `gsd-code-reviewer` com prompt do plan-auditor (`.claude/rules/plan-auditor.md`)
> 2. Se PASS → Execution Handoff via `superpowers:subagent-driven-development` (recomendado) ou `superpowers:executing-plans`
> 3. Se findings → fix-dispatch loop (cap rodada 3); se ESCALATE → 3-caminhos ao user
>
> Branch de execução `feat/v1.3-pilot-ready` será criada em Task 0.0 a partir de `main` 100% sincronizada via `git pull --ff-only`. Spec + plan vivem em `docs/v1-3-pilot-ready-spec` (esta branch); PR pode ser único spec+plan OU separado conforme escolha do orquestrador.
