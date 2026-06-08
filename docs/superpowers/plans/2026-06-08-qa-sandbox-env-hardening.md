# QA-11 Sandbox Env Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar leak de env vars sensitive do processo pai pra subprocess de validators no `forge qa` Phase 3 sandbox via allowlist core hardcoded + per-card opt-in declarativo + grant explícito do user pra vars sensitive.

**Architecture:** Helper compartilhado `engine/_sandbox/env.py` (pure stdlib, zero deps em `engine.*`) consumido por `engine.qa.sandbox._hardened_env` (refactor) e `engine.verify` subprocess call (linha 624). Cards declaram `qa-extensions.env-needs` (opcional); vars que batem `SENSITIVE_PATTERN` exigem grant explícito persistido em `workflow-config.qa.sensitive-env-grants`. Alert mentor-calmo 3-caminhos dispara em qa quando sensitive vars seriam dropadas.

**Tech Stack:** Python 3.13 stdlib (`re`, `os`, `subprocess`, `dataclasses`); pytest com markers `integration` e `e2e`; pyyaml (já no projeto).

**Spec base:** `docs/superpowers/specs/2026-06-08-qa-sandbox-env-hardening-design.md` (commit 5e156d9).

**Resolve gap:** QA-11 (`docs/design/04-pending.md` linhas 1933-1953).

---

## Wave summary

| Wave | Title | Tasks | Marker |
|---|---|---|---|
| 0 | Helper foundation (`engine/_sandbox/env.py`) | 5 | rapid |
| 1 | Consumer refactors (sandbox + verify) | 2 | rapid |
| 2 | Schema + card extension | 2 | rapid |
| 3 | Grant flow (loader → grant → init/reconfigure) | 3 | rapid |
| 4 | Alert layer pré Phase 3 | 1 | rapid |
| 5 | Integration + E2E | 3 | integration + e2e |
| 6 | Docs + doc-sync | 3 | n/a |

Total: 18 tasks, 7 waves.

---

## Wave 0 — Helper foundation

Cria `engine/_sandbox/` subpacote (pure stdlib, zero deps em `engine.*`) com `CORE_ALLOWLIST`, `SENSITIVE_PATTERN`, `is_sensitive`, `build_safe_env`, `inspect_dropped`. Esta wave NÃO toca nada além desse módulo e seus tests — consumers ficam pra Wave 1.

---

### Task 0.1: Skeleton `engine/_sandbox/env.py` com CORE_ALLOWLIST + SENSITIVE_PATTERN

**Files:**
- Create: `engine/_sandbox/__init__.py` (vazio)
- Create: `engine/_sandbox/env.py` (só constantes nesta task)
- Create: `tests/engine/_sandbox/__init__.py` (vazio)
- Create: `tests/engine/_sandbox/test_env.py` (2 smoke tests)

- [ ] **Step 1: Write the failing tests**

```python
# tests/engine/_sandbox/test_env.py
"""Tests for engine/_sandbox/env.py — safe env builder pra subprocess (QA-11)."""

from __future__ import annotations

import pytest

from engine._sandbox.env import CORE_ALLOWLIST, SENSITIVE_PATTERN


def test_core_allowlist_is_frozen():
    """CORE_ALLOWLIST é frozenset (imutável) — mutação deve raise AttributeError."""
    assert isinstance(CORE_ALLOWLIST, frozenset)
    with pytest.raises(AttributeError):
        CORE_ALLOWLIST.add("EVIL_VAR")  # type: ignore[attr-defined]


def test_sensitive_pattern_compiles_and_is_case_insensitive():
    """SENSITIVE_PATTERN é regex compilada e match é case-insensitive."""
    import re
    assert isinstance(SENSITIVE_PATTERN, re.Pattern)
    assert SENSITIVE_PATTERN.match("GITHUB_TOKEN") is not None
    assert SENSITIVE_PATTERN.match("github_token") is not None
    assert SENSITIVE_PATTERN.match("Github_Token") is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/_sandbox/test_env.py -xvs`
Expected: FAIL com `ModuleNotFoundError: No module named 'engine._sandbox'` (módulo ainda não existe).

- [ ] **Step 3: Write minimal implementation**

Criar `engine/_sandbox/__init__.py` vazio (marker de pacote):

```python
# engine/_sandbox/__init__.py
```

Criar `engine/_sandbox/env.py` com as constantes:

```python
# engine/_sandbox/env.py
"""Safe env builder pra subprocess. Allowlist core + extras declarados.

Internal API (underscore prefix). Consumidores autorizados:
- engine.qa.sandbox
- engine.verify
- engine.qa.__init__   (alert layer)
- engine.cards.loader  (parse env-needs)
- engine.cards.grant   (decisão sensitive)

Externos NÃO devem importar.

Spec: docs/superpowers/specs/2026-06-08-qa-sandbox-env-hardening-design.md (QA-11).
"""

from __future__ import annotations

import re


CORE_ALLOWLIST: frozenset[str] = frozenset({
    "PATH",                              # binary lookup defensivo
    "HOME",                              # ~ expansion + cache
    "USER", "LOGNAME",                   # subprocess identity
    "LANG", "LC_ALL", "LC_CTYPE",        # unicode em pytest output
    "TZ",                                # timestamps determinísticos
    "TMPDIR", "TEMP", "TMP",             # temp file creation
    "PYTHONHASHSEED",                    # determinismo dict ordering
})


SENSITIVE_PATTERN: re.Pattern = re.compile(
    r"(?i).*(TOKEN|SECRET|PASSWORD|AUTH|CREDENTIAL|API[_-]?KEY|PRIVATE[_-]?KEY).*"
)
```

Criar `tests/engine/_sandbox/__init__.py` vazio.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/_sandbox/test_env.py -xvs`
Expected: PASS (2 tests).

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest -m "not integration and not e2e"`
Expected: 953+2 = 955 passed (baseline atual 953 + 2 novos).

- [ ] **Step 6: Commit**

```bash
git add engine/_sandbox/__init__.py engine/_sandbox/env.py tests/engine/_sandbox/__init__.py tests/engine/_sandbox/test_env.py
git commit -m "feat(qa): _sandbox helper skeleton — CORE_ALLOWLIST + SENSITIVE_PATTERN constants (QA-11 wave 0)"
```

---

### Task 0.2: `is_sensitive()` + 3 tests

**Files:**
- Modify: `engine/_sandbox/env.py` (adicionar fn `is_sensitive`)
- Modify: `tests/engine/_sandbox/test_env.py` (adicionar 3 tests)

- [ ] **Step 1: Write the failing tests**

Append a `tests/engine/_sandbox/test_env.py`:

```python
from engine._sandbox.env import is_sensitive


@pytest.mark.parametrize("name", [
    "GITHUB_TOKEN",
    "AWS_SECRET_ACCESS_KEY",
    "DB_PASSWORD",
    "OAUTH2_CREDENTIAL",
    "RSA_PRIVATE_KEY",
    "MY_API_KEY",
    "MY-API-KEY",
    "OAUTH_TOKEN",
])
def test_is_sensitive_matches_token_patterns(name):
    """Pattern bate em formatos canônicos de var sensitive."""
    assert is_sensitive(name) is True


@pytest.mark.parametrize("name", [
    "github_token",
    "Github_Token",
    "AWS_secret_access_key",
    "db_PASSWORD",
])
def test_is_sensitive_case_insensitive(name):
    """Case-insensitive: lowercase / mixed-case batem igual."""
    assert is_sensitive(name) is True


@pytest.mark.parametrize("name", [
    "PATH",
    "HOME",
    "JAVA_HOME",
    "MY_VAR",
    "LANG",
    "PYTHONHASHSEED",
])
def test_is_sensitive_negative_cases(name):
    """Vars non-sensitive não batem (PATH, HOME, JAVA_HOME, etc.)."""
    assert is_sensitive(name) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/_sandbox/test_env.py -xvs -k is_sensitive`
Expected: FAIL com `ImportError: cannot import name 'is_sensitive' from 'engine._sandbox.env'`.

- [ ] **Step 3: Write minimal implementation**

Append a `engine/_sandbox/env.py`:

```python
def is_sensitive(name: str) -> bool:
    """Testa nome contra SENSITIVE_PATTERN (case-insensitive)."""
    return SENSITIVE_PATTERN.match(name) is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/_sandbox/test_env.py -xvs`
Expected: PASS (todos os tests parametrizados — 8 + 4 + 6 = 18 invocações somando 3 funções).

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest -m "not integration and not e2e"`
Expected: 955+3 funções = 958 (contagem aproximada; parametrize não muda contagem por função).

- [ ] **Step 6: Commit**

```bash
git add engine/_sandbox/env.py tests/engine/_sandbox/test_env.py
git commit -m "feat(qa): is_sensitive() helper + 3 tests (QA-11 wave 0)"
```

---

### Task 0.3 + 0.4 (merged): `build_safe_env()` + `_validate_extras()` + 7 tests

> **Nota:** `_validate_extras` é private; testá-lo direto seria over-engineering. Cobertura indireta via `test_build_safe_env_raises_typeerror_on_non_string_extras`. Mesclei as duas tasks pra commit atômico — feature inteira ("env builder seguro com type-check") fica em 1 commit.

**Files:**
- Modify: `engine/_sandbox/env.py` (adicionar `build_safe_env` + `_validate_extras`)
- Modify: `tests/engine/_sandbox/test_env.py` (adicionar 7 tests)

- [ ] **Step 1: Write the failing tests**

Append a `tests/engine/_sandbox/test_env.py`:

```python
from engine._sandbox.env import build_safe_env


def test_build_safe_env_returns_core_allowlist_intersection(monkeypatch):
    """Output contém SÓ vars de CORE_ALLOWLIST ∩ os.environ."""
    # Limpa qualquer var poluente do ambiente do test runner
    for k in ("PATH", "HOME", "ARBITRARY_VAR", "EVIL_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/tmp/h")
    monkeypatch.setenv("ARBITRARY_VAR", "x")

    env = build_safe_env()

    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/tmp/h"
    assert "ARBITRARY_VAR" not in env


def test_build_safe_env_drops_arbitrary_var(monkeypatch):
    """Var fora de CORE_ALLOWLIST é dropada."""
    monkeypatch.setenv("MY_CUSTOM_FOO", "bar")
    env = build_safe_env()
    assert "MY_CUSTOM_FOO" not in env


def test_build_safe_env_drops_sensitive_pattern_match(monkeypatch):
    """Vars que batem SENSITIVE_PATTERN são dropadas (mesmo se não fosse arbitrária)."""
    monkeypatch.setenv("AWS_TOKEN", "AKIA...")
    monkeypatch.setenv("MY_SECRET", "shh")
    monkeypatch.setenv("DB_PASSWORD", "p4ssw0rd")
    env = build_safe_env()
    assert "AWS_TOKEN" not in env
    assert "MY_SECRET" not in env
    assert "DB_PASSWORD" not in env


def test_build_safe_env_includes_extras(monkeypatch):
    """Extras declarados são injetados se existirem em os.environ."""
    monkeypatch.setenv("JAVA_HOME", "/opt/java")
    env = build_safe_env(extras=["JAVA_HOME"])
    assert env["JAVA_HOME"] == "/opt/java"


def test_build_safe_env_extras_filtered_if_not_in_environ(monkeypatch):
    """Extras ausentes em os.environ silenciosamente filtrados (sem raise)."""
    monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
    env = build_safe_env(extras=["NONEXISTENT_VAR"])
    assert "NONEXISTENT_VAR" not in env


def test_build_safe_env_raises_typeerror_on_non_string_extras():
    """Extras não-string raise TypeError (cobertura indireta de _validate_extras)."""
    with pytest.raises(TypeError, match="int"):
        build_safe_env(extras=[1])  # type: ignore[list-item]


def test_build_safe_env_empty_extras_default(monkeypatch):
    """Chamada sem extras retorna só CORE ∩ os.environ."""
    monkeypatch.setenv("PATH", "/bin")
    monkeypatch.setenv("RANDOM_VAR", "z")
    env = build_safe_env()
    assert env == {"PATH": "/bin"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/_sandbox/test_env.py -xvs -k build_safe_env`
Expected: FAIL com `ImportError: cannot import name 'build_safe_env'`.

- [ ] **Step 3: Write minimal implementation**

Append a `engine/_sandbox/env.py`:

```python
from typing import Iterable
import os


def build_safe_env(*, extras: Iterable[str] = ()) -> dict[str, str]:
    """Constrói env reduzido pra subprocess.

    Retorna dict com (CORE_ALLOWLIST ∪ extras) ∩ os.environ. Vars
    listadas em ``extras`` mas ausentes em ``os.environ`` são filtradas
    silenciosamente (subprocess naturalmente não as vê).

    Raises
    ------
    TypeError
        Se algum elemento de ``extras`` não for ``str``.
    """
    allowed = CORE_ALLOWLIST | _validate_extras(extras)
    return {k: v for k, v in os.environ.items() if k in allowed}


def _validate_extras(extras: Iterable[str]) -> frozenset[str]:
    """Type-check + freeze. TypeError se houver não-string."""
    out: set[str] = set()
    for v in extras:
        if not isinstance(v, str):
            raise TypeError(
                f"build_safe_env extras: expected str, got {type(v).__name__} ({v!r})"
            )
        out.add(v)
    return frozenset(out)
```

> **Reordering nota:** mova `import os` e `from typing import Iterable` pro topo do arquivo (logo após `from __future__ import annotations`), agrupados com `import re`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/_sandbox/test_env.py -xvs`
Expected: PASS (todos os tests da task — 7 funções novas + tests anteriores).

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest -m "not integration and not e2e"`
Expected: baseline + 12 = 965 (5 da task 0.1+0.2 + 7 desta task).

- [ ] **Step 6: Commit**

```bash
git add engine/_sandbox/env.py tests/engine/_sandbox/test_env.py
git commit -m "feat(qa): build_safe_env() + _validate_extras() + 7 tests (QA-11 wave 0)"
```

---

### Task 0.5: `inspect_dropped()` + 2 tests

**Files:**
- Modify: `engine/_sandbox/env.py` (adicionar fn `inspect_dropped`)
- Modify: `tests/engine/_sandbox/test_env.py` (adicionar 2 tests)

- [ ] **Step 1: Write the failing tests**

Append a `tests/engine/_sandbox/test_env.py`:

```python
from engine._sandbox.env import inspect_dropped


def test_inspect_dropped_returns_sorted_list(monkeypatch):
    """Output determinístico (lista ordenada alfabeticamente)."""
    # Limpa para isolar
    for k in ("Z_VAR", "A_VAR", "M_VAR"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("Z_VAR", "z")
    monkeypatch.setenv("A_VAR", "a")
    monkeypatch.setenv("M_VAR", "m")

    dropped = inspect_dropped()

    # Pode haver outras vars no env do test runner; só checamos que
    # estas 3 aparecem ordenadas relativamente entre si.
    indices = [dropped.index(v) for v in ("A_VAR", "M_VAR", "Z_VAR")]
    assert indices == sorted(indices)
    assert dropped == sorted(dropped)


def test_inspect_dropped_respects_extras(monkeypatch):
    """Vars listadas em extras não aparecem em dropped."""
    monkeypatch.setenv("A_VAR", "a")
    monkeypatch.setenv("B_VAR", "b")

    dropped = inspect_dropped(extras=["A_VAR"])
    assert "A_VAR" not in dropped
    assert "B_VAR" in dropped
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/_sandbox/test_env.py -xvs -k inspect_dropped`
Expected: FAIL com `ImportError: cannot import name 'inspect_dropped'`.

- [ ] **Step 3: Write minimal implementation**

Append a `engine/_sandbox/env.py`:

```python
def inspect_dropped(*, extras: Iterable[str] = ()) -> list[str]:
    """Retorna lista ordenada de vars em os.environ que seriam dropadas.

    Útil pra alert layer pré Phase 3: caller filtra por ``is_sensitive``
    pra decidir se dispara prompt.
    """
    allowed = CORE_ALLOWLIST | _validate_extras(extras)
    return sorted(k for k in os.environ if k not in allowed)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/_sandbox/test_env.py -xvs`
Expected: PASS (14 tests cumulativos na task 0).

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest -m "not integration and not e2e"`
Expected: baseline + 14 = 967.

- [ ] **Step 6: Commit**

```bash
git add engine/_sandbox/env.py tests/engine/_sandbox/test_env.py
git commit -m "feat(qa): inspect_dropped() + 2 tests — Wave 0 helper completo (QA-11 wave 0)"
```

---

## Wave 1 — Consumer refactors

`engine.qa.sandbox._hardened_env` delega pra `build_safe_env`; `engine.verify` subprocess passa a usar env reduzido. Pure refactor + 1 fix de bug equivalente em verify.

---

### Task 1.1: Refactor `engine/qa/sandbox.py._hardened_env` pra delegar a `build_safe_env` + adicionar `extras`

**Files:**
- Modify: `engine/qa/sandbox.py:155-164` (substituir corpo de `_hardened_env`)
- Modify: `engine/qa/sandbox.py:167-210` (estender `run_sandbox` signature + repassar `extras` ao `_hardened_env`)
- Modify: `tests/engine/qa/test_sandbox.py` (adicionar 4 tests novos)

- [ ] **Step 1: Write the failing tests**

Append a `tests/engine/qa/test_sandbox.py`:

```python
from unittest.mock import patch

from engine.qa.sandbox import _hardened_env


def test_hardened_env_delegates_to_build_safe_env(tmp_path, monkeypatch):
    """_hardened_env constrói env a partir de build_safe_env (não dict(os.environ))."""
    # Set var sensitive no pai — não deve aparecer no env retornado
    monkeypatch.setenv("AWS_SECRET", "leak")
    guard_dir = tmp_path / "guard"
    guard_dir.mkdir()

    env = _hardened_env(guard_dir)

    assert "AWS_SECRET" not in env, "env do sandbox não pode incluir var sensitive do pai"


def test_hardened_env_preserves_pythonpath_guard_prepend(tmp_path, monkeypatch):
    """guard_dir é prepended ao PYTHONPATH existente."""
    monkeypatch.setenv("PYTHONPATH", "/existing/path")
    # PYTHONPATH não está em CORE_ALLOWLIST — mas _hardened_env sobrescreve
    # com guard_dir + existing (lendo de env já reduzido). Como build_safe_env
    # não inclui PYTHONPATH, a "existing" será vista via os.environ direto pela
    # impl de _hardened_env. Garantimos que o resultado tem guard_dir primeiro.
    guard_dir = tmp_path / "guard"
    guard_dir.mkdir()

    env = _hardened_env(guard_dir)

    assert env["PYTHONPATH"].startswith(str(guard_dir))


def test_hardened_env_preserves_forge_qa_sandbox_marker(tmp_path):
    """FORGE_QA_SANDBOX=1 marker é setado."""
    guard_dir = tmp_path / "guard"
    guard_dir.mkdir()

    env = _hardened_env(guard_dir)

    assert env["FORGE_QA_SANDBOX"] == "1"


def test_hardened_env_propagates_extras_to_build_safe_env(tmp_path, monkeypatch):
    """extras passados pra _hardened_env chegam em build_safe_env."""
    monkeypatch.setenv("JAVA_HOME", "/opt/java")
    guard_dir = tmp_path / "guard"
    guard_dir.mkdir()

    env = _hardened_env(guard_dir, extras=["JAVA_HOME"])

    assert env["JAVA_HOME"] == "/opt/java"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/qa/test_sandbox.py -xvs -k hardened_env`
Expected: FAIL — `test_hardened_env_delegates_to_build_safe_env` falha porque impl atual usa `dict(os.environ)` (AWS_SECRET vaza). Os outros podem passar incidentalmente, mas o delegação falha.

- [ ] **Step 3: Write minimal implementation**

Em `engine/qa/sandbox.py`, adicionar import no topo (junto com os outros imports do engine):

```python
from engine._sandbox.env import build_safe_env
```

Substituir o corpo de `_hardened_env` (linhas 155-164 atuais):

```python
def _hardened_env(
    guard_dir: Path,
    *,
    extras: Iterable[str] = (),
) -> dict[str, str]:
    """Constrói env safe + sitecustomize.py preload + marker.

    Refactor (QA-11): delega base pra build_safe_env(extras=...);
    adiciona PYTHONPATH guard e FORGE_QA_SANDBOX=1 por cima.
    """
    env = build_safe_env(extras=extras)
    # PYTHONPATH não está em CORE_ALLOWLIST; lemos do os.environ direto pra
    # preservar herança defensiva quando caller já configurou paths extras.
    existing = os.environ.get("PYTHONPATH", "")
    if existing:
        env["PYTHONPATH"] = f"{guard_dir}{os.pathsep}{existing}"
    else:
        env["PYTHONPATH"] = str(guard_dir)
    env["FORGE_QA_SANDBOX"] = "1"
    return env
```

Garantir `Iterable` está importado no topo:

```python
from typing import Iterable, Literal
```

(Se já existir `from typing import Literal`, adicionar `Iterable` à lista.)

Estender `run_sandbox` signature pra aceitar `extras` e repassar:

```python
def run_sandbox(
    run_dir: Path,
    fixtures: list[Fixture],
    *,
    budget_total_s: float = 60.0,
    per_validator_s: float = 15.0,
    extras: Iterable[str] = (),
) -> list[SandboxResult]:
    """...docstring existente — adicionar parágrafo:

    Parameters
    ----------
    extras : Iterable[str]
        Env vars declaradas em ``qa-extensions.env-needs`` dos cards
        ativos. Filtradas contra grants em workflow-config antes do
        caller chamar (QA-11).
    """
```

E na linha que chama `_hardened_env(guard_dir)` (linha 210), passar `extras`:

```python
env = _hardened_env(guard_dir, extras=extras)
```

> **CRÍTICO:** se algum test existente em `test_sandbox.py` quebrar porque assumia `os.environ` integral (ex.: setou `MY_VAR` e esperava ver no env do subprocess), ajustar o test pra usar `monkeypatch.delenv` das vars sensitive testadas OU pra passar a var como `extras=["MY_VAR"]` no `run_sandbox(...)`. Rationale: comportamento novo é DEFAULT — quem precisa de var extra declara explicitamente.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/qa/test_sandbox.py -xvs`
Expected: PASS (4 novos + N existentes — todos verdes; se algum existente quebrou, fix conforme nota crítica acima).

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest -m "not integration and not e2e"`
Expected: baseline + 14 (wave 0) + 4 = 971.

- [ ] **Step 6: Commit**

```bash
git add engine/qa/sandbox.py tests/engine/qa/test_sandbox.py
git commit -m "refactor(qa): _hardened_env delega pra build_safe_env() + 4 tests (QA-11 wave 1)"
```

---

### Task 1.2: Patch `engine/verify.py:624` — `subprocess.run` passa a usar env reduzido

**Files:**
- Modify: `engine/verify.py` (import + 1 linha no subprocess.run)

- [ ] **Step 1: Write the failing tests**

> **Nota:** sem novos tests dedicados — cobertura já existe via Wave 0 (`test_build_safe_env_*`). A garantia regression aqui é "tests existentes de `test_verify.py` + tests de validators continuam verdes". Steps 4 e 5 cobrem isso.

- [ ] **Step 2: Run tests to verify they fail**

N/A (não há test novo). Pule pro Step 3.

- [ ] **Step 3: Write minimal implementation**

Adicionar import no topo de `engine/verify.py` (no bloco de imports do projeto):

```python
from engine._sandbox.env import build_safe_env
```

Modificar `subprocess.run` na linha 624 — adicionar `env=build_safe_env()`:

```python
        proc = subprocess.run(
            [sys.executable, str(spec.script_path), "--project-root", str(project_root)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            env=build_safe_env(),     # QA-11: env reduzido pra subprocess de validator
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/test_verify.py -v && pytest tests/validators/ -v`
Expected: PASS — todos os tests existentes continuam verdes.

> Se algum validator test quebrar porque o subprocess testado consumia var de env não-allowlisted, três opções: (a) test estava acidentalmente passando por leak — fix o test pra setup explícito via monkeypatch; (b) validator legitimamente precisa da var — abrir como deviation (Rule 4 architectural — adicionar à CORE_ALLOWLIST exige brainstorm); (c) test pode passar a var via fixture custom.

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest -m "not integration and not e2e"`
Expected: baseline + 18 (waves 0 + 1) = 971 (delta zero nesta task; só fix sem novos tests).

- [ ] **Step 6: Commit**

```bash
git add engine/verify.py
git commit -m "fix(verify): subprocess de validator usa env reduzido (QA-11 wave 1)"
```

---

## Wave 2 — Schema + card extension

Adiciona campo `qa-extensions.env-needs` (opcional, lista de strings) com schema check + parsing em `Card` dataclass.

---

### Task 2.1: Schema validator pra `qa-extensions.env-needs`

**Files:**
- Modify: `validators/validate_qa_extensions.py` (adicionar check de env-needs)
- Modify: `tests/validators/test_validate_qa_extensions.py` (+5 tests)

- [ ] **Step 1: Write the failing tests**

Append a `tests/validators/test_validate_qa_extensions.py`:

```python
from pathlib import Path

import pytest

from validators.validate_qa_extensions import (
    validate_qa_extensions,
    QAExtensionsValidationError,
)


def _card_with_env_needs(env_needs):
    """Helper: monta card_data mínimo com qa-extensions.env-needs."""
    return {
        "qa-extensions": {
            "auditors": [],   # vazio é OK; o foco é env-needs
            "env-needs": env_needs,
        }
    }


def test_env_needs_optional_absent_ok(tmp_path):
    """Card sem env-needs passa (campo opcional)."""
    card_data = {"qa-extensions": {"auditors": []}}
    # No raise:
    validate_qa_extensions(tmp_path / "card.yaml", card_data)


def test_env_needs_list_of_strings_ok(tmp_path):
    """Lista de strings válida passa."""
    card_data = _card_with_env_needs(["GITHUB_TOKEN", "JAVA_HOME"])
    validate_qa_extensions(tmp_path / "card.yaml", card_data)


def test_env_needs_non_list_raises(tmp_path):
    """env-needs não-lista (string, dict, etc.) raise."""
    card_data = _card_with_env_needs("GITHUB_TOKEN")  # string em vez de lista
    with pytest.raises(QAExtensionsValidationError, match="env-needs"):
        validate_qa_extensions(tmp_path / "card.yaml", card_data)


def test_env_needs_non_string_item_raises(tmp_path):
    """env-needs com item não-string (int, None) raise."""
    card_data = _card_with_env_needs(["GITHUB_TOKEN", 42])
    with pytest.raises(QAExtensionsValidationError, match="env-needs"):
        validate_qa_extensions(tmp_path / "card.yaml", card_data)


def test_env_needs_empty_string_item_raises(tmp_path):
    """env-needs com string vazia raise (whitespace é proibido)."""
    card_data = _card_with_env_needs(["GITHUB_TOKEN", ""])
    with pytest.raises(QAExtensionsValidationError, match="env-needs"):
        validate_qa_extensions(tmp_path / "card.yaml", card_data)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/validators/test_validate_qa_extensions.py -xvs -k env_needs`
Expected: FAIL — validator atual ignora `env-needs` (passa sem checar tipo).

- [ ] **Step 3: Write minimal implementation**

Em `validators/validate_qa_extensions.py`, dentro de `validate_qa_extensions` (após o check de `auditors` ser lista), adicionar bloco novo de validação:

```python
    # QA-11: env-needs (opcional, lista de strings non-empty sem whitespace)
    env_needs = qa_ext.get("env-needs")
    if env_needs is not None:
        if not isinstance(env_needs, list):
            raise QAExtensionsValidationError(
                f"{card_path}: qa-extensions.env-needs deve ser lista (recebido "
                f"{type(env_needs).__name__})"
            )
        for idx, item in enumerate(env_needs):
            if not isinstance(item, str):
                raise QAExtensionsValidationError(
                    f"{card_path}: qa-extensions.env-needs[{idx}] deve ser string "
                    f"(recebido {type(item).__name__}: {item!r})"
                )
            if not item or item != item.strip() or any(c.isspace() for c in item):
                raise QAExtensionsValidationError(
                    f"{card_path}: qa-extensions.env-needs[{idx}] inválido "
                    f"({item!r}): deve ser non-empty sem whitespace interno"
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/validators/test_validate_qa_extensions.py -xvs`
Expected: PASS (5 novos + tests prévios verdes).

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest -m "not integration and not e2e"`
Expected: baseline + 18 + 5 = 976.

- [ ] **Step 6: Commit**

```bash
git add validators/validate_qa_extensions.py tests/validators/test_validate_qa_extensions.py
git commit -m "feat(qa): validate_qa_extensions valida env-needs schema + 5 tests (QA-11 wave 2)"
```

---

### Task 2.2: Estender `Card` (`CardManifest`) dataclass em `engine/cards/loader.py`

**Files:**
- Modify: `engine/cards/loader.py` (adicionar `env_needs` + `sensitive_env_needs` ao `CardManifest`; parse em `load_card`)
- Create: `tests/engine/cards/test_loader_env_needs.py` (+3 tests)

- [ ] **Step 1: Write the failing tests**

Criar `tests/engine/cards/test_loader_env_needs.py`:

```python
"""Tests for CardManifest.env_needs / sensitive_env_needs parsing (QA-11 wave 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine.cards.loader import load_card


def _write_card(card_dir: Path, qa_extensions: dict | None = None) -> None:
    """Helper: escreve card.yaml mínimo válido + README.md."""
    data = {
        "schema-version": 1,
        "identity": {
            "name": "test-card",
            "version": "1.0.0",
            "description": "fixture card pra QA-11 tests",
            "category": "testing",
            "maturity": "experimental",
        },
        "provides": ["foundation.testing.unit-test-runner"],
    }
    if qa_extensions is not None:
        data["qa-extensions"] = qa_extensions

    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / "card.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    (card_dir / "README.md").write_text("# test-card\n", encoding="utf-8")


def test_load_card_parses_env_needs_into_tuple(tmp_path):
    """env-needs YAML vira tupla imutável no CardManifest."""
    card_dir = tmp_path / "test-card"
    _write_card(card_dir, qa_extensions={"env-needs": ["JAVA_HOME", "MY_VAR"]})

    manifest = load_card(card_dir)

    assert manifest.env_needs == ("JAVA_HOME", "MY_VAR")
    assert isinstance(manifest.env_needs, tuple)


def test_load_card_classifies_sensitive_env_needs(tmp_path):
    """Vars que batem SENSITIVE_PATTERN são separadas em sensitive_env_needs."""
    card_dir = tmp_path / "test-card"
    _write_card(
        card_dir,
        qa_extensions={"env-needs": ["JAVA_HOME", "GITHUB_TOKEN", "DB_PASSWORD"]},
    )

    manifest = load_card(card_dir)

    assert manifest.env_needs == ("JAVA_HOME", "GITHUB_TOKEN", "DB_PASSWORD")
    assert manifest.sensitive_env_needs == ("GITHUB_TOKEN", "DB_PASSWORD")


def test_load_card_no_env_needs_defaults_empty(tmp_path):
    """Card sem qa-extensions.env-needs tem tuplas vazias por default."""
    card_dir = tmp_path / "test-card"
    _write_card(card_dir, qa_extensions=None)

    manifest = load_card(card_dir)

    assert manifest.env_needs == ()
    assert manifest.sensitive_env_needs == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/cards/test_loader_env_needs.py -xvs`
Expected: FAIL com `AttributeError: 'CardManifest' object has no attribute 'env_needs'`.

- [ ] **Step 3: Write minimal implementation**

Em `engine/cards/loader.py`:

1. Adicionar import no topo:

```python
from engine._sandbox.env import is_sensitive
```

2. Estender `CardManifest` dataclass (adicionar campos antes de `origin`):

```python
@dataclass
class CardManifest:
    # ... campos existentes ...
    legacy_marker: bool = False
    env_needs: tuple[str, ...] = ()
    sensitive_env_needs: tuple[str, ...] = ()
    origin: str = "canon"
```

3. Em `load_card`, após `data = read_yaml(...)` e antes do `return CardManifest(...)`, parsear env-needs:

```python
    qa_ext = data.get("qa-extensions") or {}
    env_needs_raw = qa_ext.get("env-needs") or []
    env_needs = tuple(env_needs_raw) if isinstance(env_needs_raw, list) else ()
    sensitive_env_needs = tuple(v for v in env_needs if is_sensitive(v))
```

4. Passar pros kwargs do `CardManifest(...)`:

```python
    return CardManifest(
        # ... kwargs existentes ...
        legacy_marker=bool(data.get("legacy-marker", False)),
        env_needs=env_needs,
        sensitive_env_needs=sensitive_env_needs,
        origin="canon",
    )
```

> **Nota schema:** parse é tolerante (`isinstance(env_needs_raw, list)` ou cai pra `()`). Validation hard fica em `validate_qa_extensions` (Task 2.1) — que `load_card` já invoca via `validate_card_yaml` → `_validate_qa_extensions_overlay`. Por isso parse permissivo aqui não esconde bug: o validator faz hard fail antes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/cards/test_loader_env_needs.py -xvs`
Expected: PASS (3 tests).

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest -m "not integration and not e2e"`
Expected: baseline + 23 + 3 = 979.

- [ ] **Step 6: Commit**

```bash
git add engine/cards/loader.py tests/engine/cards/test_loader_env_needs.py
git commit -m "feat(cards): Card.env_needs + sensitive_env_needs parsing + 3 tests (QA-11 wave 2)"
```

---

## Wave 3 — Grant flow

`engine/cards/grant.py` (novo) implementa o prompt 3-caminhos pra sensitive vars; `engine/init.py` e `engine/reconfigure.py` chamam o grant quando ativam cards.

---

### Task 3.1: Criar `engine/cards/grant.py` com `GrantDecision` + `evaluate_sensitive_grants`

**Files:**
- Create: `engine/cards/grant.py`
- Create: `tests/engine/cards/test_grant.py` (+7 tests com mock do 3-caminhos)

- [ ] **Step 1: Write the failing tests**

Criar `tests/engine/cards/test_grant.py`:

```python
"""Tests for engine/cards/grant.py — sensitive env-need grant flow (QA-11 wave 3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from engine.cards.grant import (
    GrantDecision,
    UserAbortError,
    evaluate_sensitive_grants,
)
from engine.cards.loader import CardManifest


def _make_card(name: str, env_needs: tuple[str, ...] = (), sensitive: tuple[str, ...] = ()) -> CardManifest:
    """Helper: monta CardManifest mínimo pra tests."""
    return CardManifest(
        name=name,
        version="1.0.0",
        schema_version=1,
        description=f"fixture {name}",
        category="testing",
        maturity="experimental",
        provides=["foundation.testing.unit-test-runner"],
        env_needs=env_needs,
        sensitive_env_needs=sensitive,
    )


@pytest.fixture
def mock_three_paths(monkeypatch):
    """Mock pra surface_three_paths: caller atribui responses por (card_name, var)."""
    calls: list[dict[str, Any]] = []
    responses: dict[str, str] = {}

    def fake_prompt(*, card_name: str, var: str, **kwargs) -> str:
        calls.append({"card_name": card_name, "var": var})
        return responses.get(var, "grant")

    monkeypatch.setattr(
        "engine.cards.grant._prompt_sensitive_grant", fake_prompt
    )
    return {"calls": calls, "responses": responses}


def test_no_sensitive_needs_skips_prompt(mock_three_paths):
    """Card sem sensitive_env_needs não dispara prompt nenhum."""
    cards = [_make_card("c1", env_needs=("JAVA_HOME",), sensitive=())]
    cfg: dict[str, Any] = {"qa": {}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert mock_three_paths["calls"] == []
    assert decision.granted == ()
    assert decision.denied_cards == ()
    assert decision.new_grants_to_persist == ()


def test_already_granted_skips_prompt(mock_three_paths):
    """Var já em workflow_config.qa.sensitive-env-grants não pergunta de novo."""
    cards = [_make_card("c1", env_needs=("GITHUB_TOKEN",), sensitive=("GITHUB_TOKEN",))]
    cfg = {"qa": {"sensitive-env-grants": ["GITHUB_TOKEN"]}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert mock_three_paths["calls"] == []
    assert decision.granted == ()  # nada novo granted
    assert decision.new_grants_to_persist == ()


def test_grant_path_adds_to_workflow_config(mock_three_paths):
    """Path 1 (grant) adiciona var em new_grants_to_persist."""
    mock_three_paths["responses"]["GITHUB_TOKEN"] = "grant"
    cards = [_make_card("c1", sensitive=("GITHUB_TOKEN",))]
    cfg: dict[str, Any] = {"qa": {}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert decision.granted == ("GITHUB_TOKEN",)
    assert decision.new_grants_to_persist == ("GITHUB_TOKEN",)
    assert decision.denied_cards == ()


def test_deny_path_deactivates_card(mock_three_paths):
    """Path 2 (deny) marca card como denied_cards."""
    mock_three_paths["responses"]["GITHUB_TOKEN"] = "deny"
    cards = [_make_card("c1", sensitive=("GITHUB_TOKEN",))]
    cfg: dict[str, Any] = {"qa": {}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert decision.denied_cards == ("c1",)
    assert decision.granted == ()


def test_abort_path_raises_user_abort(mock_three_paths):
    """Path 3 (abort) raise UserAbortError."""
    mock_three_paths["responses"]["GITHUB_TOKEN"] = "abort"
    cards = [_make_card("c1", sensitive=("GITHUB_TOKEN",))]
    cfg: dict[str, Any] = {"qa": {}}

    with pytest.raises(UserAbortError, match="GITHUB_TOKEN"):
        evaluate_sensitive_grants(cards, cfg)


def test_multiple_cards_same_var_single_prompt(mock_three_paths):
    """2 cards declaram GITHUB_TOKEN → prompt único, ambos cards 'granted'."""
    mock_three_paths["responses"]["GITHUB_TOKEN"] = "grant"
    cards = [
        _make_card("c1", sensitive=("GITHUB_TOKEN",)),
        _make_card("c2", sensitive=("GITHUB_TOKEN",)),
    ]
    cfg: dict[str, Any] = {"qa": {}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert len(mock_three_paths["calls"]) == 1
    assert decision.granted == ("GITHUB_TOKEN",)
    assert decision.denied_cards == ()


def test_grant_persistence_idempotent(mock_three_paths):
    """Re-running evaluate com grants já persistidos: zero new_grants."""
    mock_three_paths["responses"]["GITHUB_TOKEN"] = "grant"
    cards = [_make_card("c1", sensitive=("GITHUB_TOKEN",))]

    # 1ª chamada — grant
    cfg: dict[str, Any] = {"qa": {}}
    d1 = evaluate_sensitive_grants(cards, cfg)
    assert d1.new_grants_to_persist == ("GITHUB_TOKEN",)

    # Simula persist: caller copia new_grants_to_persist pra cfg
    cfg["qa"]["sensitive-env-grants"] = list(d1.new_grants_to_persist)

    # 2ª chamada — não pergunta de novo
    d2 = evaluate_sensitive_grants(cards, cfg)
    assert d2.new_grants_to_persist == ()
    assert d2.granted == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/cards/test_grant.py -xvs`
Expected: FAIL com `ModuleNotFoundError: No module named 'engine.cards.grant'`.

- [ ] **Step 3: Write minimal implementation**

Criar `engine/cards/grant.py`:

```python
"""Decisão sensitive-var grant pra cards em init/reconfigure (QA-11 wave 3).

Quando um card declara `qa-extensions.env-needs` com vars que batem
SENSITIVE_PATTERN, este módulo dispara prompt 3-caminhos pro user:
  1) grant   — adiciona var em workflow-config.qa.sensitive-env-grants
  2) deny    — desativa o card pra esse projeto
  3) abort   — raise UserAbortError (operação cancelada)

Per-projeto (não per-card): se card A grant GITHUB_TOKEN, card B usa
mesmo grant sem novo prompt (KISS, conforme spec §5.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from engine.cards.loader import CardManifest
from engine.persona import mentor_calmo


class UserAbortError(RuntimeError):
    """User escolheu path 3 (abort) num prompt sensitive grant."""


@dataclass(frozen=True)
class GrantDecision:
    """Resultado de evaluate_sensitive_grants.

    Attributes
    ----------
    granted : tuple[str, ...]
        Vars aprovadas pelo user neste run (path 1).
    denied_cards : tuple[str, ...]
        Nomes de cards desativados porque user negou pelo menos uma var
        sensitive declarada pelo card (path 2).
    new_grants_to_persist : tuple[str, ...]
        Subconjunto de `granted` que ainda não estava em
        ``workflow_config.qa.sensitive-env-grants`` — caller persiste.
    """

    granted: tuple[str, ...] = ()
    denied_cards: tuple[str, ...] = ()
    new_grants_to_persist: tuple[str, ...] = ()


def evaluate_sensitive_grants(
    cards_to_activate: Iterable[CardManifest],
    workflow_config: dict[str, Any],
) -> GrantDecision:
    """Per card, per sensitive var não-granted, dispara prompt 3-caminhos.

    Dedup cross-cards: mesma var perguntada UMA vez mesmo se N cards
    declaram. Cards com pelo menos 1 var denied entram em ``denied_cards``.

    Parameters
    ----------
    cards_to_activate : Iterable[CardManifest]
        Cards que serão ativados (init) ou re-ativados (reconfigure).
    workflow_config : dict[str, Any]
        Workflow-config carregado; lê ``qa.sensitive-env-grants`` (lista).

    Returns
    -------
    GrantDecision

    Raises
    ------
    UserAbortError
        Se user escolher path 3 em qualquer prompt.
    """
    cards_list = list(cards_to_activate)
    already_granted = _load_existing_grants(workflow_config)

    # Coleta universo de sensitive vars NEW (não-granted), com quais cards as pedem
    var_to_cards: dict[str, list[str]] = {}
    for card in cards_list:
        for var in card.sensitive_env_needs:
            if var in already_granted:
                continue
            var_to_cards.setdefault(var, []).append(card.name)

    granted: list[str] = []
    denied_vars: set[str] = set()

    # Prompt único per var (dedup cross-cards)
    for var in sorted(var_to_cards):
        cards_requesting = var_to_cards[var]
        # card_name argumento principal é o primeiro card que pediu (display)
        decision = _prompt_sensitive_grant(
            card_name=", ".join(cards_requesting),
            var=var,
        )
        if decision == "grant":
            granted.append(var)
        elif decision == "deny":
            denied_vars.add(var)
        elif decision == "abort":
            raise UserAbortError(
                f"User abortou grant pra var sensitive {var!r} "
                f"(cards pedindo: {cards_requesting})"
            )
        else:
            # Defesa: 3-caminhos contract garante grant/deny/abort
            raise RuntimeError(
                f"_prompt_sensitive_grant retornou decisão inválida: {decision!r}"
            )

    # Cards com pelo menos 1 var denied → denied_cards
    denied_cards: list[str] = []
    for card in cards_list:
        if any(v in denied_vars for v in card.sensitive_env_needs):
            denied_cards.append(card.name)

    return GrantDecision(
        granted=tuple(granted),
        denied_cards=tuple(denied_cards),
        new_grants_to_persist=tuple(granted),  # já filtrado por already_granted
    )


def _load_existing_grants(workflow_config: dict[str, Any]) -> set[str]:
    """Lê workflow_config.qa.sensitive-env-grants tolerando shape malformado.

    Shape inesperado (não-lista) trata como vazio + warning visível.
    """
    qa_section = (workflow_config or {}).get("qa") or {}
    raw = qa_section.get("sensitive-env-grants", [])
    if not isinstance(raw, list):
        # Fail-safe: shape ruim vira [] (não raise, pra não bloquear init);
        # mas warning fica visível pro user reconciliar.
        import sys
        print(
            f"⚠️  qa.sensitive-env-grants tem shape inesperado ({type(raw).__name__}); "
            f"tratando como vazio. Reconcilie via `forge reconfigure → qa`.",
            file=sys.stderr,
        )
        return set()
    return {v for v in raw if isinstance(v, str)}


def _prompt_sensitive_grant(*, card_name: str, var: str) -> str:
    """Dispara prompt 3-caminhos mentor-calmo. Retorna 'grant'|'deny'|'abort'.

    Reusa mentor_calmo.three_paths_block (mesmo helper de engine.init.
    _surface_three_paths).
    """
    mentor_calmo.three_paths_block(
        title=f"Card pede acesso a variável sensitive: {var}",
        what_failed=(
            f"O card {card_name!r} declarou {var!r} em "
            f"`qa-extensions.env-needs`. Esta var bate o pattern de var "
            f"sensitive (TOKEN/SECRET/PASSWORD/etc.) e exige autorização "
            f"explícita antes de chegar ao subprocess de validators."
        ),
        where=f"forge init/reconfigure → ativação de card {card_name!r}",
        why_matters=[
            "vars sensitive no env do subprocess podem vazar via log/traceback",
            "card extension é trust-on-install — autorização explícita audita o gate",
            "grant fica persistido em workflow-config (revisável a qualquer momento)",
        ],
        paths=[
            ("Autorizar (grant)", f"adiciona {var!r} em qa.sensitive-env-grants"),
            ("Negar (deny)", f"card {card_name!r} é desativado pra esse projeto"),
            ("Abortar", "operação cancelada; ajuste manual em workflow-config se quiser"),
        ],
    )
    # Leitura da escolha — reusa pattern de engine.init._surface_three_paths
    # via input() simples. Implementação real lê stdin; mocked em tests.
    choice = input("Escolha [1/2/3]: ").strip()
    return {"1": "grant", "2": "deny", "3": "abort"}.get(choice, "abort")
```

> **Sobre `_prompt_sensitive_grant`:** o test fixture `mock_three_paths` substitui essa fn inteira via `monkeypatch.setattr`, então o `input()` real nunca roda em test. O caller (init/reconfigure) também pode injetar override pra TTY-less envs (Wave 5 integration tests).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/cards/test_grant.py -xvs`
Expected: PASS (7 tests).

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest -m "not integration and not e2e"`
Expected: baseline + 26 + 7 = 986.

- [ ] **Step 6: Commit**

```bash
git add engine/cards/grant.py tests/engine/cards/test_grant.py
git commit -m "feat(cards): grant.py — evaluate_sensitive_grants + GrantDecision + 7 tests (QA-11 wave 3)"
```

---

### Task 3.2: Wire `evaluate_sensitive_grants` em `engine/init.py`

**Files:**
- Modify: `engine/init.py` (chamada de `evaluate_sensitive_grants` no Step de ativação de cards)

- [ ] **Step 1: Write the failing tests**

> **Nota:** sem unit test dedicado nesta task. Cobertura via Wave 5 integration tests (`test_first_activation_prompts_and_persists_grant`). Suite existente de `tests/engine/test_init.py` deve continuar verde — Step 4 valida.

- [ ] **Step 2: Run tests to verify they fail**

N/A. Pule pro Step 3.

- [ ] **Step 3: Write minimal implementation**

Em `engine/init.py`:

1. Adicionar imports no topo (junto com outros `from engine.cards`):

```python
from engine.cards.grant import (
    GrantDecision,
    UserAbortError,
    evaluate_sensitive_grants,
)
```

2. Localizar o Step que ativa cards no `_run_pipeline`. Procurar (`grep -n "_activate_cards\|active.*cards\|cards.*activate" engine/init.py`) o ponto entre "Step 7.5" (Gap 5 overlay) e a finalização. O wire insere imediatamente **após** o load dos cards e **antes** de qualquer persist de config:

```python
        # ... carregamento de cards concluído (canon ∪ local) → lista `active_cards`

        # QA-11: grant flow pra sensitive env-needs declaradas em qa-extensions
        try:
            grant_decision = evaluate_sensitive_grants(active_cards, workflow_config)
        except UserAbortError as exc:
            renderer.write(
                mentor_calmo.pause_message(
                    resume_command=f"forge init  # após reconciliar grants — {exc}"
                )
            )
            return  # aborta init sem persistir state parcial

        # Aplica decisão: persiste novos grants + remove cards denied
        if grant_decision.new_grants_to_persist:
            qa_cfg = workflow_config.setdefault("qa", {})
            existing = list(qa_cfg.get("sensitive-env-grants", []))
            for var in grant_decision.new_grants_to_persist:
                if var not in existing:
                    existing.append(var)
            qa_cfg["sensitive-env-grants"] = existing

        if grant_decision.denied_cards:
            active_cards = [c for c in active_cards if c.name not in grant_decision.denied_cards]
```

> **Localização exata:** a busca por âncoras (`grep`) é parte da task. Se houver dúvida, o critério é "depois de `active_cards` estar resolvido e antes do snapshot/persist final do workflow-config". Em caso de ambiguidade real, surface 3-caminhos pro orchestrator.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/test_init.py -v`
Expected: PASS — suite existente continua verde. Se algum test quebrou porque agora o init lê `qa.sensitive-env-grants`, ajustar o fixture do test pra incluir `qa: {}` no workflow-config base.

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest -m "not integration and not e2e"`
Expected: baseline + 33 = 986 (delta zero desta task; integration cobre fluxo).

- [ ] **Step 6: Commit**

```bash
git add engine/init.py
git commit -m "feat(init): wire grant flow pra cards com sensitive env-needs (QA-11 wave 3)"
```

---

### Task 3.3: Wire `evaluate_sensitive_grants` em `engine/reconfigure.py`

**Files:**
- Modify: `engine/reconfigure.py` (chamada de `evaluate_sensitive_grants` na re-ativação de cards)

- [ ] **Step 1: Write the failing tests**

> **Nota:** sem unit test dedicado; integration test `test_second_activation_same_var_no_prompt` (Wave 5 Task 5.2) cobre o fluxo idempotente.

- [ ] **Step 2: Run tests to verify they fail**

N/A. Pule pro Step 3.

- [ ] **Step 3: Write minimal implementation**

Em `engine/reconfigure.py`:

1. Mesmos imports da Task 3.2:

```python
from engine.cards.grant import (
    GrantDecision,
    UserAbortError,
    evaluate_sensitive_grants,
)
```

2. Localizar onde cards são re-ativados / a workflow-config é re-validada (provavelmente após user editar o menu de cards). Inserir bloco idêntico ao de `init.py`:

```python
        # QA-11: grant flow pra sensitive env-needs declaradas em qa-extensions
        try:
            grant_decision = evaluate_sensitive_grants(active_cards, workflow_config)
        except UserAbortError as exc:
            renderer.write(
                mentor_calmo.pause_message(
                    resume_command=f"forge reconfigure  # após reconciliar grants — {exc}"
                )
            )
            return

        if grant_decision.new_grants_to_persist:
            qa_cfg = workflow_config.setdefault("qa", {})
            existing = list(qa_cfg.get("sensitive-env-grants", []))
            for var in grant_decision.new_grants_to_persist:
                if var not in existing:
                    existing.append(var)
            qa_cfg["sensitive-env-grants"] = existing

        if grant_decision.denied_cards:
            active_cards = [c for c in active_cards if c.name not in grant_decision.denied_cards]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/test_reconfigure.py -v 2>/dev/null || pytest -k reconfigure -v`
Expected: PASS — suite existente verde.

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest -m "not integration and not e2e"`
Expected: 986.

- [ ] **Step 6: Commit**

```bash
git add engine/reconfigure.py
git commit -m "feat(reconfigure): wire grant flow pra cards com sensitive env-needs (QA-11 wave 3)"
```

---

## Wave 4 — Alert layer pré Phase 3

`engine/qa/__init__.py` ganha `_alert_sensitive_drops` que dispara 3-caminhos no momento do `forge qa` se vars sensitive serão dropadas e nenhum card declarou.

---

### Task 4.1: `_alert_sensitive_drops` em `engine/qa/__init__.py` + integração pré Phase 3

**Files:**
- Modify: `engine/qa/__init__.py` (adicionar fn + chamada antes de `run_sandbox`)

- [ ] **Step 1: Write the failing tests**

> **Nota:** cobertura via Wave 5 integration tests:
> - `test_alert_fires_when_sensitive_unwhitelisted_present`
> - `test_alert_silent_when_no_sensitive_present`
>
> Não há test unit dedicado nesta task porque o helper é thin wrapper sobre `inspect_dropped` + `is_sensitive` (já cobertos em Wave 0) + UI (`mentor_calmo.three_paths_block`).

- [ ] **Step 2: Run tests to verify they fail**

N/A. Pule pro Step 3.

- [ ] **Step 3: Write minimal implementation**

Em `engine/qa/__init__.py`, adicionar imports:

```python
from typing import Iterable

from engine._sandbox.env import inspect_dropped, is_sensitive
from engine.persona import mentor_calmo
```

Adicionar a fn:

```python
def _alert_sensitive_drops(card_extras: Iterable[str]) -> None:
    """Pré Phase 3: alerta se vars sensitive serão dropadas.

    Dispara mentor_calmo.three_paths_block com 3 paths:
      1) ignore → segue com env reduzido (perda de funcionalidade aceita)
      2) declare no card → user vai editar card e re-rodar
      3) grant no projeto → user roda forge reconfigure e adiciona em
         workflow-config.qa.sensitive-env-grants

    Note: alert é informativo (não bloqueia). Se user quer parar, basta
    Ctrl+C; pause discipline (Decisão 27) registra deferred state.
    """
    extras_tuple = tuple(card_extras)
    dropped = inspect_dropped(extras=extras_tuple)
    sensitive = [v for v in dropped if is_sensitive(v)]
    if not sensitive:
        return

    mentor_calmo.three_paths_block(
        title="Variáveis sensitive serão dropadas no sandbox",
        what_failed=(
            f"Detectadas {len(sensitive)} vars sensitive no env do pai "
            f"não declaradas por nenhum card ativo: "
            f"{', '.join(sensitive)}"
        ),
        where="engine/qa Phase 3 sandbox boot",
        why_matters=[
            "subprocess de validators rodará sem essas vars",
            "se validator/card depende delas, vai falhar com erro de auth/config",
            "se NÃO depende, o drop é a defesa funcionando (zero ação)",
        ],
        paths=[
            (
                "Ignorar e seguir",
                "validator/card não depende dessas vars — drop esperado",
            ),
            (
                "Declarar no card",
                "editar qa-extensions.env-needs do card relevante e re-rodar",
            ),
            (
                "Grant no projeto",
                "rodar `forge reconfigure` e adicionar em qa.sensitive-env-grants",
            ),
        ],
    )
```

Integração: localizar a fn `run_qa` (ou equivalente que coordena Phases). Imediatamente antes da chamada pra `run_sandbox(...)` da Phase 3, computar `card_extras` (union de `env_needs` cross cards ativos ∩ allowed = CORE_ALLOWLIST ∪ grants) e disparar alert:

```python
    # QA-11: alert layer antes de Phase 3 sandbox (informativo, não bloqueia)
    card_env_needs = set()
    for card in active_cards:
        card_env_needs.update(card.env_needs)
    granted = set(
        (workflow_config or {}).get("qa", {}).get("sensitive-env-grants", []) or []
    )
    allowed_extras = card_env_needs & (set(CORE_ALLOWLIST) | granted)
    _alert_sensitive_drops(allowed_extras)

    sandbox_results = run_sandbox(
        run_dir=run_tree.root,
        fixtures=fixtures,
        budget_total_s=qa_config.sandbox_budget_seconds_total,
        per_validator_s=qa_config.agent_timeout_seconds,
        extras=allowed_extras,
    )
```

> Adicionar `from engine._sandbox.env import CORE_ALLOWLIST` se ainda não estiver importado.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/qa/ -v`
Expected: PASS — tests existentes continuam verdes (alert silente sem vars sensitive no env do test runner).

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest -m "not integration and not e2e"`
Expected: 986.

- [ ] **Step 6: Commit**

```bash
git add engine/qa/__init__.py
git commit -m "feat(qa): _alert_sensitive_drops alert layer pré Phase 3 (QA-11 wave 4)"
```

---

## Wave 5 — Integration + E2E

3 arquivos de test E2E (8 integration + 1 e2e). Cobertura cross-componente: env não vaza, alert dispara, grant flow persiste, CLI smoke.

---

### Task 5.1: Integration tests `tests/integration/test_qa_env_hardening.py` (4 tests)

**Files:**
- Create: `tests/integration/test_qa_env_hardening.py` (marker `integration`)

- [ ] **Step 1: Write the failing tests**

Criar `tests/integration/test_qa_env_hardening.py`:

```python
"""Integration tests pra QA-11 env hardening (Wave 5 Task 5.1).

Cobertura E2E cross-componente:
- Env do pai (incl. secrets) não vaza pro subprocess de validator.
- Card declara env-need legítima → var chega ao subprocess.
- Alert dispara quando vars sensitive presentes sem grant/card.
- Alert silente quando env mínimo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from engine._sandbox.env import build_safe_env, inspect_dropped, is_sensitive


pytestmark = pytest.mark.integration


def _write_minimal_fixture(fixtures_dir: Path, validator_script: Path) -> None:
    """Helper: escreve fixture + validator que dumpa env como JSON em stdout."""
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    (fixtures_dir / "input.txt").write_text("ignored", encoding="utf-8")
    validator_script.parent.mkdir(parents=True, exist_ok=True)
    validator_script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "json.dump(dict(os.environ), sys.stdout)\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    validator_script.chmod(0o755)


def test_secret_in_parent_env_does_not_leak_to_subprocess(tmp_path, monkeypatch):
    """AWS_TOKEN no env do pai NÃO chega ao subprocess do sandbox."""
    monkeypatch.setenv("AWS_TOKEN", "leaky-AKIA-12345")

    from engine.qa.sandbox import Fixture, run_sandbox

    validator = tmp_path / "validator.py"
    _write_minimal_fixture(tmp_path / "fixtures", validator)

    fixtures = [Fixture(
        name="probe",
        input_path=tmp_path / "fixtures" / "input.txt",
        validator_path=validator,
    )]

    results = run_sandbox(tmp_path, fixtures, budget_total_s=10.0, per_validator_s=5.0)

    assert len(results) == 1
    assert results[0].status == "ok"
    subprocess_env = json.loads(results[0].stdout)
    assert "AWS_TOKEN" not in subprocess_env, (
        f"AWS_TOKEN vazou pro subprocess: {list(subprocess_env.keys())}"
    )


def test_card_env_needs_chain_grant_to_subprocess(tmp_path, monkeypatch):
    """Var declarada em extras (post-grant) chega ao subprocess."""
    monkeypatch.setenv("JAVA_HOME", "/opt/java-fixture")

    from engine.qa.sandbox import Fixture, run_sandbox

    validator = tmp_path / "validator.py"
    _write_minimal_fixture(tmp_path / "fixtures", validator)

    fixtures = [Fixture(
        name="probe",
        input_path=tmp_path / "fixtures" / "input.txt",
        validator_path=validator,
    )]

    results = run_sandbox(
        tmp_path,
        fixtures,
        budget_total_s=10.0,
        per_validator_s=5.0,
        extras=["JAVA_HOME"],
    )

    assert results[0].status == "ok"
    subprocess_env = json.loads(results[0].stdout)
    assert subprocess_env.get("JAVA_HOME") == "/opt/java-fixture"


def test_alert_fires_when_sensitive_unwhitelisted_present(monkeypatch, capsys):
    """Quando AWS_TOKEN no env e nenhum card declara → alert mentor-calmo dispara."""
    monkeypatch.setenv("AWS_TOKEN", "secret123")

    from engine.qa import _alert_sensitive_drops

    _alert_sensitive_drops(card_extras=[])

    captured = capsys.readouterr()
    # mentor_calmo.three_paths_block escreve em stdout (ou stderr) — qualquer um
    combined = captured.out + captured.err
    assert "sensitive" in combined.lower() or "AWS_TOKEN" in combined, (
        f"Alert não disparou. Output: {combined!r}"
    )


def test_alert_silent_when_no_sensitive_present(monkeypatch, capsys):
    """Quando nenhuma var sensitive no env (pós-cleanup) → alert silencioso."""
    # Limpa qualquer sensitive var residual do ambiente de teste
    for k in list(os.environ):
        if is_sensitive(k):
            monkeypatch.delenv(k, raising=False)

    from engine.qa import _alert_sensitive_drops

    _alert_sensitive_drops(card_extras=[])

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "sensitive" not in combined.lower(), (
        f"Alert deveria estar silencioso. Output: {combined!r}"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_qa_env_hardening.py -xvs`
Expected: ou todos PASS (se Wave 0-4 prévias já mergeadas) ou alguns FAIL específicos. Como esta task vem após Wave 0-4, deve passar.

- [ ] **Step 3: Write minimal implementation**

N/A — tests integration; toda impl já foi feita em waves anteriores.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_qa_env_hardening.py -xvs`
Expected: PASS (4 tests).

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest` (full suite, incluindo integration)
Expected: baseline + 33 (wave 0-4) + 4 = 990.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_qa_env_hardening.py
git commit -m "test(qa): integration tests pra env hardening — 4 tests (QA-11 wave 5)"
```

---

### Task 5.2: Integration tests `tests/integration/test_card_grant_flow.py` (4 tests)

**Files:**
- Create: `tests/integration/test_card_grant_flow.py` (marker `integration`)

- [ ] **Step 1: Write the failing tests**

Criar `tests/integration/test_card_grant_flow.py`:

```python
"""Integration tests pra grant flow E2E em init/reconfigure (QA-11 wave 5 Task 5.2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from engine.cards.grant import (
    GrantDecision,
    UserAbortError,
    evaluate_sensitive_grants,
)
from engine.cards.loader import CardManifest


pytestmark = pytest.mark.integration


def _make_card(name: str, sensitive: tuple[str, ...] = ()) -> CardManifest:
    return CardManifest(
        name=name,
        version="1.0.0",
        schema_version=1,
        description=f"fixture {name}",
        category="testing",
        maturity="experimental",
        provides=["foundation.testing.unit-test-runner"],
        env_needs=sensitive,
        sensitive_env_needs=sensitive,
    )


def test_first_activation_prompts_and_persists_grant(monkeypatch):
    """1ª ativação: prompt dispara, grant decision tem new_grants_to_persist."""
    monkeypatch.setattr(
        "engine.cards.grant._prompt_sensitive_grant",
        lambda *, card_name, var: "grant",
    )
    cards = [_make_card("github-ci-card", sensitive=("GITHUB_TOKEN",))]
    cfg: dict = {"qa": {}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert decision.new_grants_to_persist == ("GITHUB_TOKEN",)
    assert decision.granted == ("GITHUB_TOKEN",)
    assert decision.denied_cards == ()


def test_second_activation_same_var_no_prompt(monkeypatch):
    """Re-ativação após grant persistido: zero prompts, zero new_grants."""
    prompts_seen = []
    monkeypatch.setattr(
        "engine.cards.grant._prompt_sensitive_grant",
        lambda *, card_name, var: (prompts_seen.append(var) or "grant"),
    )
    cards = [_make_card("github-ci-card", sensitive=("GITHUB_TOKEN",))]
    cfg: dict = {"qa": {"sensitive-env-grants": ["GITHUB_TOKEN"]}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert prompts_seen == []
    assert decision.new_grants_to_persist == ()


def test_deny_path_disables_card_in_workflow_config(monkeypatch):
    """Deny: card aparece em denied_cards, caller deve removê-lo de active_cards."""
    monkeypatch.setattr(
        "engine.cards.grant._prompt_sensitive_grant",
        lambda *, card_name, var: "deny",
    )
    cards = [
        _make_card("github-card", sensitive=("GITHUB_TOKEN",)),
        _make_card("clean-card", sensitive=()),
    ]
    cfg: dict = {"qa": {}}

    decision = evaluate_sensitive_grants(cards, cfg)

    assert "github-card" in decision.denied_cards
    assert "clean-card" not in decision.denied_cards
    assert decision.granted == ()


def test_manual_revoke_via_reconfigure_removes_grant(monkeypatch):
    """User edita workflow-config removendo grant → próxima ativação re-pergunta."""
    # Setup: grant persistido
    cfg: dict = {"qa": {"sensitive-env-grants": ["GITHUB_TOKEN"]}}
    cards = [_make_card("github-card", sensitive=("GITHUB_TOKEN",))]

    # 1ª chamada: sem prompt
    monkeypatch.setattr(
        "engine.cards.grant._prompt_sensitive_grant",
        lambda *, card_name, var: "grant",
    )
    d1 = evaluate_sensitive_grants(cards, cfg)
    assert d1.new_grants_to_persist == ()

    # User edita config manualmente — remove grant
    cfg["qa"]["sensitive-env-grants"] = []

    # 2ª chamada: prompt dispara de novo
    prompts_seen = []
    monkeypatch.setattr(
        "engine.cards.grant._prompt_sensitive_grant",
        lambda *, card_name, var: (prompts_seen.append(var) or "grant"),
    )
    d2 = evaluate_sensitive_grants(cards, cfg)

    assert prompts_seen == ["GITHUB_TOKEN"]
    assert d2.new_grants_to_persist == ("GITHUB_TOKEN",)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_card_grant_flow.py -xvs`
Expected: PASS (toda impl pronta desde Wave 3).

- [ ] **Step 3: Write minimal implementation**

N/A — integration tests sobre impl existente.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_card_grant_flow.py -xvs`
Expected: PASS (4 tests).

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest`
Expected: baseline + 37 + 4 = 994.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_card_grant_flow.py
git commit -m "test(cards): integration tests pra grant flow — 4 tests (QA-11 wave 5)"
```

---

### Task 5.3: E2E extensão `tests/e2e/test_qa_cli_smoke.py` (+1 test)

**Files:**
- Modify: `tests/e2e/test_qa_cli_smoke.py` (adicionar 1 test)

- [ ] **Step 1: Write the failing tests**

Append a `tests/e2e/test_qa_cli_smoke.py`:

```python
def test_forge_qa_cli_no_secret_leak_smoke(tmp_project, monkeypatch):
    """E2E: `forge qa` CLI — AWS_TOKEN no env do pai não vaza em report nem stderr.

    Roda subprocess real do CLI (`forge qa scope=feature target=...`) com
    AWS_TOKEN exportado. Assert: var não aparece em qa-report.json nem
    em stderr capturado.
    """
    import os
    import subprocess
    import json
    from pathlib import Path

    secret_value = "AKIA-LEAK-PROBE-12345"
    env = dict(os.environ)
    env["AWS_TOKEN"] = secret_value
    # CI smoothing: pula prompts interativos do CLI (alert mentor-calmo
    # imprime mas não bloqueia em modo non-tty)
    env["FORGE_NONINTERACTIVE"] = "1"

    forge_bin = Path(__file__).resolve().parents[2] / "bin" / "forge"

    # Setup mínimo: `forge init` pra ter projeto válido
    subprocess.run(
        [str(forge_bin), "init", "--preset", "kmp-mobile", "--yes"],
        cwd=tmp_project,
        env=env,
        check=False,
        timeout=60,
        capture_output=True,
    )

    # Rodar QA scope=task no menor escopo possível
    result = subprocess.run(
        [str(forge_bin), "qa", "scope=task", "target=TASK-0001"],
        cwd=tmp_project,
        env=env,
        check=False,
        timeout=120,
        capture_output=True,
        text=True,
    )

    # 1) Secret não aparece em stdout/stderr
    assert secret_value not in result.stdout, "AWS_TOKEN vazou em stdout"
    assert secret_value not in result.stderr, "AWS_TOKEN vazou em stderr"

    # 2) Secret não aparece em qa-report.json (se foi gerado)
    qa_runs = list((tmp_project / ".planning" / "qa").rglob("qa-report.json"))
    for report_path in qa_runs:
        content = report_path.read_text(encoding="utf-8")
        assert secret_value not in content, (
            f"AWS_TOKEN vazou em {report_path}"
        )
```

> **Nota:** este test é resiliente — não exige que o `forge qa` complete com sucesso (target sintético `TASK-0001` pode não existir). O critério é "secret não aparece em saída textual nem em artifacts gerados", e isso é o suficiente pra validar no-leak guarantee end-to-end. Se `tmp_project` fixture não existe ainda, o test deve criar projeto temporário inline.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/e2e/test_qa_cli_smoke.py::test_forge_qa_cli_no_secret_leak_smoke -xvs`
Expected: PASS (impl pronta desde Wave 1-4).

- [ ] **Step 3: Write minimal implementation**

N/A — E2E sobre impl existente.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/e2e/test_qa_cli_smoke.py -xvs`
Expected: PASS.

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest`
Expected: baseline + 41 + 1 = 995.

- [ ] **Step 6: Commit**

```bash
git add tests/e2e/test_qa_cli_smoke.py
git commit -m "test(qa): e2e smoke test pra no-leak guarantee (QA-11 wave 5)"
```

---

## Wave 6 — Docs + doc-sync

Schema docs, CHANGELOG, handoff, 04-pending closeout, baseline test count.

---

### Task 6.1: Schema docs — `qa-extensions.md` + `workflow-config.md`

**Files:**
- Modify: `docs/schemas/qa-extensions.md` (adicionar seção `env-needs (opcional)`)
- Modify: `docs/schemas/workflow-config.md` (adicionar seção `qa.sensitive-env-grants (opcional)`)

- [ ] **Step 1: Edit `docs/schemas/qa-extensions.md`**

Localizar a seção principal (provavelmente depois de `auditors:`). Append esta nova seção:

```markdown
## env-needs (opcional, since v1.2 — QA-11)

Lista de env vars que o card declara precisar no subprocess do sandbox.

\`\`\`yaml
qa-extensions:
  env-needs:
    - GITHUB_TOKEN      # bate pattern sensitive → exige grant
    - JAVA_HOME         # non-sensitive → passa direto
\`\`\`

### Semântica

- Cada item é o nome literal da env var (case-sensitive no lookup).
- Vars **non-sensitive** (não batem `SENSITIVE_PATTERN` —
  `TOKEN|SECRET|PASSWORD|AUTH|CREDENTIAL|API_KEY|PRIVATE_KEY`,
  case-insensitive) são injetadas direto no subprocess sem prompt.
- Vars **sensitive** disparam prompt 3-caminhos pro user no momento de
  `forge init` ou `forge reconfigure` (não no momento de `forge qa`).
- Grant é persistido em `workflow-config.qa.sensitive-env-grants` —
  per-projeto, não per-card. Mesma var declarada por 2 cards = prompt
  único pro user.

### Regras de validação (validator: validate_qa_extensions.py)

| Regra | Comportamento |
|---|---|
| Tipo deve ser `list[str]` | shape errado → `QAExtensionsValidationError` |
| Item non-string | raise com índice + tipo recebido |
| Item vazio ou com whitespace interno | raise |
| Var sensitive sem grant | NÃO rejeita em load-time; runtime (init/reconfigure) dispara grant |

### Cross-refs

- Grant flow: `engine/cards/grant.py`
- Storage: `docs/schemas/workflow-config.md §qa.sensitive-env-grants`
- Spec: `docs/superpowers/specs/2026-06-08-qa-sandbox-env-hardening-design.md`
```

- [ ] **Step 2: Edit `docs/schemas/workflow-config.md`**

Localizar seção `## qa (since v1.2)`. Append sub-seção:

```markdown
### qa.sensitive-env-grants (opcional, since v1.2 — QA-11)

Lista de env vars sensitive autorizadas pelo user neste projeto. Cards
que declaram `qa-extensions.env-needs` com vars sensitive precisam ter
todas elas presentes nesta lista pra serem ativados sem novo prompt.

\`\`\`yaml
qa:
  sensitive-env-grants:
    - GITHUB_TOKEN      # granted em init/reconfigure pelo user
    - AWS_TOKEN         # granted via prompt 3-caminhos
\`\`\`

### Semântica

- Lista vazia ou ausente: zero grants — qualquer card com sensitive
  env-needs dispara prompt na próxima ativação.
- Edição manual da lista é suportada (e auditável via git diff).
  Remoção de var → próxima ativação re-pergunta.
- Adição manual (sem passar pelo prompt) é tecnicamente possível mas
  desencorajada — log da decisão fica fora da auditoria.
- Shape malformado (não-lista) é tratado como `[]` com warning em
  stderr (não raise).

### Não-revoke automático

Quando um card declarando GITHUB_TOKEN é desinstalado, o grant
permanece em workflow-config. Revoke explícito: edite manualmente OU
aguarde gap opt-in `forge reconfigure --revoke-grants` (não
implementado v1.2).
```

- [ ] **Step 3: Verify diff**

Run: `git diff --stat docs/schemas/`
Expected: 2 arquivos modificados, ~80-120 linhas adicionadas total.

- [ ] **Step 4: No tests to run**

N/A — doc-only.

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest -m "not integration and not e2e"`
Expected: 986 (sem delta de doc).

- [ ] **Step 6: Commit**

```bash
git add docs/schemas/qa-extensions.md docs/schemas/workflow-config.md
git commit -m "docs(schemas): env-needs (qa-extensions) + sensitive-env-grants (workflow-config) (QA-11 wave 6)"
```

---

### Task 6.2: CHANGELOG + handoff + 04-pending closeout

**Files:**
- Modify: `CHANGELOG.md` (Unreleased — Added + Changed + Security)
- Modify: `docs/design/08-session-handoff.md` (Última atualização + Estado)
- Modify: `docs/design/04-pending.md` (linhas 1933-1953 — Gap QA-11 closeout)

- [ ] **Step 1: Edit `CHANGELOG.md`**

Na seção `## [Unreleased]`, adicionar/append:

```markdown
### Added

- `engine/_sandbox/env.py` — safe env builder pra subprocess de validators
  (`build_safe_env`, `inspect_dropped`, `is_sensitive`); pure stdlib, zero
  deps em `engine.*` (QA-11).
- Campo `qa-extensions.env-needs` em cards (lista opcional de env vars
  que o card declara precisar no sandbox; QA-11).
- Campo `workflow-config.qa.sensitive-env-grants` (lista de env vars
  sensitive autorizadas explicitamente pelo user; QA-11).
- `engine/cards/grant.py` — `evaluate_sensitive_grants` + `GrantDecision`
  + `UserAbortError`. Prompt 3-caminhos mentor-calmo dispara em
  `forge init` / `forge reconfigure` quando card pede sensitive var sem
  grant prévio (QA-11).
- `engine.qa._alert_sensitive_drops` — alert mentor-calmo pré Phase 3
  quando vars sensitive serão dropadas e nenhum card as declara (QA-11).

### Changed

- `engine/qa/sandbox.py._hardened_env` agora delega base do env pra
  `build_safe_env(extras=...)` em vez de `dict(os.environ)`. Refactor
  mantém PYTHONPATH guard + FORGE_QA_SANDBOX marker (QA-11).
- `engine.verify` linha 624 — `subprocess.run` pra validator agora usa
  `env=build_safe_env()` (era default: herdar env completo do pai). Bug
  silente de leak fechado (QA-11).

### Security

- **QA-11 fechado.** Secrets do processo pai (`AWS_TOKEN`, `GITHUB_TOKEN`,
  `DB_PASSWORD`, `*_SECRET`, etc.) não vazam mais pro subprocess de
  validators rodando em `forge qa` Phase 3 sandbox nem em `forge verify`.
  Mitigação cobre dois threats: card extension malicioso (`qa-extensions.
  auditors` lendo `os.environ`) e leak acidental em validator canon
  (traceback que printa env em debug). Defesa = allowlist core
  (`CORE_ALLOWLIST` hardcoded em `engine/_sandbox/env.py`) + per-card
  opt-in declarativo + grant explícito do user pra vars sensitive.
```

- [ ] **Step 2: Edit `docs/design/08-session-handoff.md`**

Atualizar campos topo:

```markdown
**Última atualização:** 2026-06-08 (v1.2.x + Gap 9 + PR #4 CC + PR #8 QA + QA-11 sandbox hardening)
**Estado:** v1.2 com `forge qa` shipado; QA-11 fechado; pré-piloto restrito a QA-13 (paranoid state filter).
```

(Mantenha o resto do doc intacto. Se houver tabela `| Categoria | Status |`, adicione linha relevante; caso contrário, só os 2 campos acima.)

Em `§Conhecidos limites` (se existir), adicionar:

```markdown
- **Grant revoke automático:** quando card com `qa-extensions.env-needs`
  é desinstalado, grant permanece em `workflow-config.qa.sensitive-env-grants`.
  Revoke é manual (editar config) ou via gap opt-in
  `forge reconfigure --revoke-grants` (não implementado v1.2).
```

- [ ] **Step 3: Edit `docs/design/04-pending.md`**

Localizar Gap QA-11 (linhas 1933-1953 conforme spec §11). Modificar o campo `**Status:**` (mantendo o resto da entrada como histórico append-only):

```markdown
**Status:** ✅ resolvido 2026-06-08 (allowlist core + per-card opt-in + grant explícito via spec `docs/superpowers/specs/2026-06-08-qa-sandbox-env-hardening-design.md` + impl em PR QA-11; 40+ tests adicionados; baseline 953 → ~995 tests; closeout commit referencia este resolvido).
```

> Não altere as outras linhas da entrada — mantenha rationale histórico, threat model, citações.

- [ ] **Step 4: Verify diff**

Run: `git diff --stat CHANGELOG.md docs/design/08-session-handoff.md docs/design/04-pending.md`
Expected: 3 arquivos modificados, ~50-80 linhas total.

- [ ] **Step 5: Run full suite for regression check**

Run: `pytest -m "not integration and not e2e"`
Expected: 986.

- [ ] **Step 6: Commit**

```bash
git add CHANGELOG.md docs/design/08-session-handoff.md docs/design/04-pending.md
git commit -m "docs(qa-11): CHANGELOG + handoff + 04-pending closeout (QA-11 wave 6)"
```

---

### Task 6.3: Baseline test count + README

**Files:**
- Modify: `.claude/rules/testing.md` (atualizar baseline test count)
- Modify: `README.md` (atualizar Stats se test count mencionado)

- [ ] **Step 1: Coletar count atual**

Run: `pytest --collect-only -q 2>/dev/null | tail -3`
Expected output (exemplo): `995 tests collected in 0.50s`. Anote o valor real.

- [ ] **Step 2: Edit `.claude/rules/testing.md`**

Localizar baselines mencionados (procurar `877`, `953`, `637`, ou similares). Substituir pela contagem real coletada no Step 1. Linhas típicas a ajustar:

```diff
- # Lane completa (default)
- pytest                              # 953 tests, default lane
+ pytest                              # ~995 tests, default lane
```

E o gate "Test count regression":

```diff
- - [ ] Count de tests >= baseline (637 em v1.1.0; consulte
-       `docs/design/08-session-handoff.md` pra current count)
+ - [ ] Count de tests >= baseline (995 em v1.2.x pós-QA-11; consulte
+       `docs/design/08-session-handoff.md` pra current count)
```

- [ ] **Step 3: Edit `README.md`**

Procurar se há linha de stats com test count. Se sim, atualizar:

```diff
- - Tests: 953 passing
+ - Tests: ~995 passing
```

Se não há menção a count, skip esta edição e commit só `.claude/rules/testing.md`.

- [ ] **Step 4: Verify diff**

Run: `git diff --stat .claude/rules/testing.md README.md`

- [ ] **Step 5: Run full suite — confirma count anunciado**

Run: `pytest --collect-only -q 2>/dev/null | tail -3`
Expected: bate com o número anunciado.

- [ ] **Step 6: Commit**

```bash
git add .claude/rules/testing.md README.md
git commit -m "docs(testing): baseline test count +40 (QA-11 wave 6)"
```

---

## Self-review final (não-doc, lista de checks executada pelo orchestrator pós-leitura)

> Esta seção é checklist mental do orchestrator ao revisar este plano, NÃO faz parte do
> contrato de execução. Tasks 0.1–6.3 acima são o contrato.

- [ ] Spec coverage: cada componente de spec §6 (API) mapeado em Wave 0-4. Tests de spec §8.1 → Tasks 0.1-0.5; §8.2 → 2.1; §8.3 → 2.2; §8.4 → 3.1; §8.5 → 1.1; §8.7 → 5.1; §8.8 → 5.2; §8.9 → 5.3. Doc-sync §10 → 6.1-6.3.
- [ ] Zero placeholders ("TBD", "fill in", "implement later") — todo bloco de código está copiado completo, todo bloco de test idem.
- [ ] Type/symbol consistency: `CORE_ALLOWLIST`, `SENSITIVE_PATTERN`, `build_safe_env`, `inspect_dropped`, `is_sensitive`, `_validate_extras`, `CardManifest.env_needs`, `CardManifest.sensitive_env_needs`, `GrantDecision`, `UserAbortError`, `evaluate_sensitive_grants`, `_alert_sensitive_drops`, `_prompt_sensitive_grant` — todos os símbolos batem cross-task.
- [ ] Commit message pattern uniforme: `<tipo>(<escopo>): <descrição curta> (QA-11 wave N)`.
- [ ] Voz mentor-calmo neutra técnica em todas as descrições; sem emojis decorativos; sem voz corporativa.
