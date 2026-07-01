# Smoke Gate (Tema 6 Nível 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps usam checkbox (`- [ ]`). TDD estrito: teste falha ANTES da impl.

**Goal:** Adicionar o smoke gate (Nível 2, Caminho A) ao `forge verify` — o consumidor declara `native-gates.smoke.cmd`, o forge roda como step do verify reusando a fronteira `external_exec`. Fecha o I-02 de brinde (helper de teste compartilhado).

**Architecture:** `_run_smoke_gate` espelha `_run_build_gates` (mesma fronteira: resolve_invocation → run_external_tool → _map_external_result). Opt-in default off. Device/toolchain ausente → skipped/degraded, nunca fail.

**Tech Stack:** Python (engine/verify.py), pytest (TDD, `.venv/bin/pytest`).

## Global Constraints

- `.venv/bin/pytest` é o canonical. Em worktree, garantir venv próprio + `engine.__file__` apontando pra worktree (senão testa o source errado).
- TDD: cada teste falha antes (RED), passa depois (GREEN). Refactor (Task 1) NÃO adiciona teste — roda os existentes pra provar no-behavior-change.
- Voz mentor calmo nas mensagens de skip.
- Reuso: NÃO reimplementar resolve/run/map — usar os de `engine/verify.py` + `engine/external_exec.py`.
- Branch `feat/tema6-n2-smoke`. Sem push até `gh auth`=`thgMatajs`.
- Semântica LOCKED do smoke: cmd ausente→skipped; toolchain ausente→skipped; exit0→pass(substantive); exit≠0→warn (fail só com fail-on-violation); timeout/OSError→degraded.

---

### Task 1: Extrair helper de teste compartilhado (fecha I-02) — REFACTOR

**Files:**
- Create: `tests/engine/helpers/__init__.py` (vazio)
- Create: `tests/engine/helpers/external_exec.py`
- Modify: `tests/engine/test_verify_build_only.py` (remover defs locais, importar do helper)
- Modify: `tests/engine/test_verify_native_gates.py` (idem)

**Interfaces produzidas:** `_write_fake_gradlew(project_root, *, exit_code=0)`, `_fake_run(status, *, exit_code, skipped_reason="")`.

- [ ] **Step 1: criar o helper compartilhado** `tests/engine/helpers/external_exec.py`:

```python
"""Helpers compartilhados pros testes de gates de execução externa.

Extraídos de test_verify_build_only.py + test_verify_native_gates.py (I-02):
o fake gradle wrapper + o factory de stub de run_external_tool eram idênticos
nos dois módulos. Ao chegar o 3º gate (smoke), consolidados aqui.
"""
from __future__ import annotations

import stat
from pathlib import Path

from engine.external_exec import ExternalToolResult


def _write_fake_gradlew(project_root: Path, *, exit_code: int = 0) -> Path:
    """Cria um ./gradlew trivial que sai com `exit_code` (visível a resolve_invocation)."""
    gradlew = project_root / "gradlew"
    gradlew.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    mode = gradlew.stat().st_mode
    gradlew.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return gradlew


def _fake_run(status: str, *, exit_code: int | None, skipped_reason: str = ""):
    """Factory de stub pra monkeypatch de run_external_tool (ignora timeout)."""

    def _runner(argv, project_root, *, timeout=120):
        return ExternalToolResult(
            tool=argv[0],
            status=status,
            exit_code=exit_code,
            stdout="",
            stderr="",
            duration_ms=20,
            skipped_reason=skipped_reason,
        )

    return _runner
```

- [ ] **Step 2: criar** `tests/engine/helpers/__init__.py` vazio.

- [ ] **Step 3: migrar `test_verify_build_only.py`** — remover as defs locais de `_write_fake_gradlew`/`_fake_run` e importar: `from tests.engine.helpers.external_exec import _write_fake_gradlew, _fake_run`. (Se o import por `tests.` não resolver no layout, usar o import relativo/estilo já usado no repo — confira um teste vizinho.)

- [ ] **Step 4: migrar `test_verify_native_gates.py`** — idem.

- [ ] **Step 5: provar no-behavior-change**

Run: `.venv/bin/pytest tests/engine/test_verify_build_only.py tests/engine/test_verify_native_gates.py -q`
Expected: PASS (mesmo count de antes; refactor não muda comportamento).

- [ ] **Step 6: commit**

```bash
git add tests/engine/helpers/ tests/engine/test_verify_build_only.py tests/engine/test_verify_native_gates.py
git commit -m "refactor(test): extrai helper external_exec compartilhado (fecha I-02)"
```

---

### Task 2: `_run_smoke_gate` (TDD)

**Files:**
- Modify: `engine/verify.py` (`_OPT_IN_GATES`; `_smoke_candidates`; `_run_smoke_gate`; wire em `_run_native_gates`)
- Test: `tests/engine/test_verify_smoke_gate.py` (novo)

**Interfaces consumidas:** `resolve_invocation`, `run_external_tool`, `_map_external_result`, `_skipped_gate_result`, `_gate_enabled`, `_gate_timeout`, `_gate_fail_on_violation`, `_gate_cfg`, `_ValidatorResult`.

- [ ] **Step 1 (RED): escrever `tests/engine/test_verify_smoke_gate.py`**

```python
"""Tema 6 Nível 2 — smoke gate no forge verify (Caminho A: consumidor declara cmd)."""
from __future__ import annotations

from pathlib import Path

import pytest

from engine import verify
from tests.engine.helpers.external_exec import _write_fake_gradlew, _fake_run


def _cfg(**smoke):
    return {"native-gates": {"smoke": smoke, "ktlint": {"enabled": False}, "build": {"enabled": False}}}


def test_smoke_disabled_by_default(tmp_path, monkeypatch):
    """smoke sem enabled → gate não roda (opt-in default off)."""
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("pass", exit_code=0))
    results = verify._run_native_gates(_cfg(cmd=["./gradlew", "test"]), tmp_path, interactive=False)
    assert [r for r in results if r.name == "smoke"] == []


def test_smoke_enabled_no_cmd_skipped(tmp_path):
    """enabled mas sem cmd declarado → skipped ensinando a declarar."""
    results = verify._run_native_gates(_cfg(enabled=True), tmp_path, interactive=False)
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "skipped"
    assert "native-gates.smoke.cmd" in smoke[0].message


def test_smoke_pass(tmp_path, monkeypatch):
    """cmd declarado + exit 0 → pass (substantive)."""
    _write_fake_gradlew(tmp_path, exit_code=0)
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("pass", exit_code=0))
    results = verify._run_native_gates(_cfg(enabled=True, cmd=["./gradlew", "test"]), tmp_path, interactive=False)
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "pass" and smoke[0].coverage == "substantive"


def test_smoke_fail_is_warn(tmp_path, monkeypatch):
    """exit ≠ 0 sem fail-on-violation → warn (informativo)."""
    _write_fake_gradlew(tmp_path, exit_code=0)
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("fail", exit_code=1))
    results = verify._run_native_gates(_cfg(enabled=True, cmd=["./gradlew", "test"]), tmp_path, interactive=False)
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "warn"


def test_smoke_fail_on_violation(tmp_path, monkeypatch):
    """exit ≠ 0 + fail-on-violation → fail."""
    _write_fake_gradlew(tmp_path, exit_code=0)
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("fail", exit_code=1))
    cfg = _cfg(enabled=True, cmd=["./gradlew", "test"], **{"fail-on-violation": True})
    results = verify._run_native_gates(cfg, tmp_path, interactive=False)
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "fail"


def test_smoke_toolchain_absent_skipped(tmp_path):
    """cmd declara ./gradlew inexistente → resolve None → skipped."""
    results = verify._run_native_gates(_cfg(enabled=True, cmd=["./gradlew", "test"]), tmp_path, interactive=False)
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "skipped"


def test_smoke_timeout_degraded(tmp_path, monkeypatch):
    """timeout → degraded, nunca fail."""
    _write_fake_gradlew(tmp_path, exit_code=0)
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("degraded", exit_code=None, skipped_reason="timeout"))
    results = verify._run_native_gates(_cfg(enabled=True, cmd=["./gradlew", "test"]), tmp_path, interactive=False)
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "degraded"


def test_smoke_greenfield_empty_config(tmp_path):
    """config vazio (mid-init) → _run_native_gates devolve [] (não roda smoke)."""
    assert verify._run_native_gates({}, tmp_path, interactive=False) == []
```

- [ ] **Step 2: rodar → RED**

Run: `.venv/bin/pytest tests/engine/test_verify_smoke_gate.py -q`
Expected: FAIL (smoke ainda não existe em `_run_native_gates` / `_run_smoke_gate` ausente).

- [ ] **Step 3 (GREEN): implementar em `engine/verify.py`**

3a. Em `_gate_enabled`, incluir smoke nos opt-in:
```python
    _OPT_IN_GATES = {"build", "smoke"}
```

3b. Adicionar (perto de `_build_candidates`/`_run_build_gates`):
```python
def _smoke_candidates(config: dict) -> list[list[str] | str]:
    """Candidato de invocação do smoke: o cmd DECLARADO pelo consumidor.

    Nível 2 Caminho A: o forge NÃO adivinha o smoke. Sem cmd → [] (caller emite
    skipped ensinando a declarar).
    """
    cmd = _gate_cfg(config, "smoke").get("cmd")
    if isinstance(cmd, list) and cmd:
        return [[str(x) for x in cmd]]
    if isinstance(cmd, str) and cmd.strip():
        return [cmd.strip()]
    return []


def _run_smoke_gate(config: dict, project_root: Path) -> list[_ValidatorResult]:
    """Smoke test (Tema 6 Nível 2, Caminho A). Reusa resolve/run/map do A1/A2.

    O consumidor declara `native-gates.smoke.cmd`; o forge só roda. Opt-in
    (default off). Device/toolchain ausente → skipped/degraded, nunca fail.
    """
    if not _gate_enabled(config, "smoke"):
        return []
    candidates = _smoke_candidates(config)
    if not candidates:
        return [
            _skipped_gate_result(
                "smoke",
                "Gate `smoke` habilitado mas sem comando declarado. Declare "
                "`native-gates.smoke.cmd` em `forge-config.yaml` (ex.: "
                '`["./gradlew", "testDebugUnitTest"]`) — o forge roda o smoke que '
                "você escolher, não adivinha o teste. A feature não foi reprovada por isso.",
            )
        ]
    argv = resolve_invocation(candidates, project_root)
    if argv is None:
        return [
            _skipped_gate_result(
                "smoke",
                "Gate `smoke` declarado mas a toolchain não resolveu (o comando de "
                "`native-gates.smoke.cmd` não foi encontrado no projeto nem no PATH). "
                "Pulei — a feature não foi reprovada. Instale a toolchain do smoke.",
            )
        ]
    res = run_external_tool(
        argv, project_root, timeout=_gate_timeout(config, "smoke", default=600)
    )
    return [
        _map_external_result(
            res,
            gate_name="smoke",
            fail_on_violation=_gate_fail_on_violation(config, "smoke"),
        )
    ]
```

3c. Em `_run_native_gates`, após o build:
```python
    results.extend(_run_smoke_gate(config, project_root))
```

- [ ] **Step 4: rodar → GREEN**

Run: `.venv/bin/pytest tests/engine/test_verify_smoke_gate.py -q`
Expected: PASS (8 testes).

- [ ] **Step 5: commit**

```bash
git add engine/verify.py tests/engine/test_verify_smoke_gate.py
git commit -m "feat(verify): smoke gate (Tema 6 Nível 2, Caminho A) — consumidor declara cmd"
```

---

### Task 3: doc-sync (CHANGELOG + 04-pending fecha I-02 + guia)

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/design/04-pending.md` (fechar I-02; anotar smoke = Nível 2 shipado)
- Modify: guia de `native-gates` em `docs/guides/` SE existir (senão pular — confira com `ls docs/guides/`)

- [ ] **Step 1: CHANGELOG** sob `## [Unreleased]` → `### Added`:
```markdown
- **Smoke gate (Tema 6 Nível 2, Caminho A)** — `forge verify` ganha o step
  `smoke` (opt-in, default off): o consumidor declara `native-gates.smoke.cmd`
  e o forge roda como gate nativo (reusa `external_exec`). Device/toolchain
  ausente → `skipped`/`degraded`, nunca `fail`. Fecha o follow-on I-02 (helper
  de teste `external_exec` compartilhado). Spec:
  `docs/superpowers/specs/2026-07-01-smoke-gate-n2-design.md`.
```

- [ ] **Step 2: 04-pending — fechar I-02.** Localize o bullet do I-02 (§Follow-on) e prefixe com `✓` + marque FECHADO:
```markdown
- ✓ **I-02 — dedup do helper de teste `_write_fake_gradlew`/`_fake_run`** —
  FECHADO com o smoke gate (Nível 2): helpers extraídos pra
  `tests/engine/helpers/external_exec.py`; `test_verify_build_only.py` e
  `test_verify_native_gates.py` migrados. O 3º gate nativo chegou (smoke).
```
E na entrada de runtime/visual (§Follow-on "impl de runtime/visual"), anote que o Nível 2 (smoke) foi shipado, Nível 3 (screenshot) segue deferido pós-piloto.

- [ ] **Step 3: sincronia mem (Mandamento #7):** o item I-02 fechou → a nota `reference` do mem correspondente deve ser superseded. Rode:
```bash
.claude/bin/mem find "I-02 dedup helper external_exec"
```
Capture o id da nota "Aberto: I-02…", crie a nota de closure e supersede:
```bash
.claude/bin/mem add --type reference -t "Fechado: I-02 — helper external_exec compartilhado" --tags "i-02,testes,fechado" "FECHADO com o smoke gate (Nível 2): _write_fake_gradlew/_fake_run extraídos pra tests/engine/helpers/external_exec.py; build_only + native_gates migrados. Canônico: 04-pending §Follow-on I-02."
.claude/bin/mem supersede <NEW_ID> <OLD_ID_DA_NOTA_ABERTA>
```

- [ ] **Step 4: rodar full lane + commit**

Run: `.venv/bin/pytest -q | tail -3`
Expected: verde, sem regressão.

```bash
git add CHANGELOG.md docs/design/04-pending.md .claude/memory/*.jsonl
git commit -m "docs(smoke): doc-sync — CHANGELOG + fecha I-02 (04-pending + mem sync)"
```

---

### Task 4: Verification

- [ ] **Step 1: lane completa** — `.venv/bin/pytest -q | tail -5` → rapid+integration+e2e verdes, smoke tests incluídos.
- [ ] **Step 2:** confirmar que o smoke é opt-in de fato: um verify com config sem `native-gates.smoke` NÃO emite gate smoke (nenhuma linha `smoke`).
- [ ] **Step 3:** reportar counts das lanes.

---

## Self-Review (autor)

- **Cobertura da spec:** §3 config→Task2; §4 semântica→Task2 (8 testes); §6 I-02→Task1+Task3; §7 testes→Task2; §8 escopo→Tasks 1-3.
- **Placeholders:** nenhum — código real em todos os steps.
- **Consistência:** `_run_smoke_gate` usa exatamente as funções existentes (resolve_invocation/run_external_tool/_map_external_result/_skipped_gate_result/_gate_*); helper importado do módulo novo.

## Cross-refs

- Spec impl: `docs/superpowers/specs/2026-07-01-smoke-gate-n2-design.md`.
- Spec produto: `docs/superpowers/specs/2026-06-30-runtime-visual-verification-design.md`.
- Fronteira: `engine/external_exec.py`, `engine/verify.py::_run_native_gates`.
