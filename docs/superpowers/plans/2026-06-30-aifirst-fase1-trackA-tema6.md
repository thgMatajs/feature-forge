# Plano — Track A (Tema 6), Fase 1 da campanha AI-first

> **Status:** plano de execução TDD. Contrato é a spec da campanha
> (`docs/superpowers/specs/2026-06-30-aifirst-pendencias-campaign-design.md`
> §Fase 1 Track A) + as specs irmãs (`native-quality-gates-design.md` Caminho A;
> `runtime-visual-verification-design.md` build-only). Este plano cobre **só o
> Track A** — duas tasks: **A1 (native gate ktlint)** e **A2 (build-only)**.
> Tracks B/C/D NÃO estão aqui.
>
> **Voz:** mentor calmo. Firme nos gates, didático no porquê. O Tema 6 nasceu de
> uma lição: *verde inerte mente*. Nada aqui pode criar **vermelho inerte** no
> lugar — violação de gate nativo é **informativa por default** (`warn`), e subir
> pra `fail` é opt-in explícito por projeto.

---

## 0. Constraints globais (leia antes de qualquer task)

- **pytest canônico:** `.venv/bin/pytest` (tem json5 + deps; o system pytest dá
  falsos negativos). Lane rápida: `.venv/bin/pytest -m "not integration and not e2e"`.
- **Serial, checkout principal:** Track A toca `engine/verify.py` (arquivo
  compartilhado entre A1 e A2) → roda **no checkout principal, em série**. **A1
  antes de A2** — A2 reusa o step `_run_native_gates` que A1 cria. Não há worktree
  pra Track A.
- **Reuso-first (Mandamento #3):** A2 **reusa** o `_run_native_gates` de A1 — não
  duplica a lógica de resolve/run/map. A diferença entre A1 e A2 é só *qual lista
  de gates* alimenta o step (um helper de descoberta por face, um runner comum).
- **Decisão 33 é o contrato LOCKED** (Fase 0): `engine/external_exec.py` já existe
  com `run_external_tool` e `resolve_invocation`. Garantias dadas: `check=False`
  (classifica, não estoura), env reduzido via `build_safe_env`, timeout → `degraded`,
  `OSError` → `degraded`, skip-se-ausente (`resolve_invocation → None`), sem auto-fix
  (`ktlintCheck`, **nunca** `ktlintFormat`/`--fix`), sem instalar toolchain. **Não
  reabrir a 33; consumir como está.**
- **Sem refactor de `_run_cascade` nem de `_discover_validators`** (scout: não há
  ponto de extensão limpo). O step novo é **separado** e seus resultados são
  **mesclados** na lista `results` de `run_scope()` antes do cálculo do `overall`.
- **Doc-sync no MESMO commit de cada task** (Mandamento #6): CHANGELOG +
  `docs/schemas/forge-config.md` (bloco `native-gates`) + `docs/design/04-pending.md`
  (mover faces fechadas) + `docs/design/06-command-surface.md` (novo comportamento
  do verify). README só se stats mudarem.
- **Scope (Mandamento #4):** edite só `engine/verify.py`, os arquivos de teste
  nomeados, e os docs de sync. NÃO toque `engine/external_exec.py` (já pronto),
  `_run_cascade`, `_discover_validators`, nem qualquer card/template/preset.

### Fatos do scout (verbatim — não re-descobrir)

- **Orquestrador:** `run_scope()` — `engine/verify.py:280-501`. `run()` (`:188-264`)
  delega **inteiramente** a `run_scope()` (interativo e `--json`); logo o step novo
  entra **uma vez** em `run_scope()` e cobre os dois entrypoints.
- **Cascade:** `_run_cascade(validators, *, fail_fast, project_root, interactive, scope_type, scope_target) -> list[_ValidatorResult]` — `:940-978`. **Não tocar.**
- **`overall`** (`:443-448`): `fail` se hard_fail, senão `warn` se `warnings_list`,
  senão `incomplete` se `degraded_list`, senão `pass`. **`degraded` NÃO entra no
  `overall`** (vira `incomplete`). `warn` **não** seta hard_fail → exit 0.
- **`_ValidatorResult`** (`:83-106`): `name`, `status ∈ {pass, warn, fail, skipped, degraded}`,
  `duration_ms`, `message`, `paths`, `what_failed`, `where`, `why`, `coverage`.
- **Config lido** em `:320`: `config = read_yaml_or_default(active_config_path(project_root), {}) or {}`.
- **Glyphs** `_STATUS_GLYPH` — `:1169-1178` (`pass:✓ warn:⚠ fail:🛑 skipped:— degraded:⛒`).
  `_render_line` (`:1181-1198`) já imprime `message` na linha pra `warn` e `degraded`.
- **`_render_summary`** — `:1207-1247` (conta por status; deriva título do veredito).
  **`_coverage_breakdown`** — `:1128-1148` (conta passes por classe + `degraded`).
- **`external_exec.ExternalToolResult`** (`engine/external_exec.py:35-46`): `tool`,
  `status ∈ {pass, fail, degraded, skipped}`, `exit_code`, `stdout`, `stderr`,
  `duration_ms`, `skipped_reason`.
- **Stack do projeto:** `config.get("platforms", {}).get("active", [])` — valores
  ⊂ `["android", "ios", "kmp", "web"]`, gravado pelo init (`engine/init.py:3086`).

---

## 1. Contrato compartilhado (assinaturas — A1 e A2 batem nisto)

Toda assinatura abaixo é o **contrato fixo** que os testes e as duas tasks
assumem. Definir aqui evita drift de tipo entre A1, A2 e os testes.

```python
# engine/verify.py — adicionar perto do topo, após os imports existentes.
from engine.external_exec import (
    ExternalToolResult,
    resolve_invocation,
    run_external_tool,
)

# Mapping ExternalToolResult.status → _ValidatorResult.status.
# Decisão de design LOCKED: violação reportada (exit≠0, tool rodou) é INFORMATIVA
# (warn), não fail. Subir warn→fail é opt-in por projeto (ver _gate_enabled_fail).
_EXTERNAL_STATUS_MAP: dict[str, str] = {
    "pass": "pass",       # exit 0
    "fail": "warn",       # tool rodou e acusou violação → informativo por default
    "degraded": "degraded",  # timeout / OSError (ver run_external_tool)
    "skipped": "skipped",    # nunca emitido por run_external_tool; aqui por completude
}
```

Assinatura do step (criada em A1, reusada em A2):

```python
def _run_native_gates(
    config: dict,
    project_root: Path,
    *,
    interactive: bool,
) -> list[_ValidatorResult]:
    """Roda os gates de execução externa (Decisão 33) e devolve _ValidatorResult.

    Gates cobertos (Tema 6, Nível 1):
      - ktlint  (A1) — `./gradlew ktlintCheck` em modo check, read-only.
      - build   (A2) — `./gradlew assembleDebug` / `xcodebuild` conforme stack.

    Guard greenfield: se `config` é vazio (mid-init, config ainda não escrito),
    devolve `[]` — não tenta rodar gate sem config. Os callers de run_scope
    mesclam o retorno na lista `results` ANTES do cálculo do `overall`.

    Cada gate é INFORMATIVO por default: violação → `warn` (exit do verify fica 0).
    Opt-in `fail-on-violation: true` por gate sobe `warn → fail`.
    """
```

Helpers internos (criados em A1, A2 só acrescenta `_build_candidates`):

```python
def _map_external_result(
    res: ExternalToolResult,
    *,
    gate_name: str,
    fail_on_violation: bool,
    absent_message: str,
) -> _ValidatorResult:
    """ExternalToolResult → _ValidatorResult (mapping LOCKED de status)."""

def _native_gate_block(config: dict) -> dict:
    """Lê o bloco `native-gates` do config; `{}` se ausente."""

def _ktlint_candidates(config: dict, project_root: Path) -> list[list[str] | str]:
    """Candidatos de invocação do ktlint, em ordem de preferência."""

def _build_candidates(platform: str) -> list[list[str] | str]:
    """Candidatos de invocação do build-only por plataforma (A2)."""
```

Ponto de integração único em `run_scope()` (entre `_run_cascade` e o cálculo do
`overall`, ou seja após a linha `:414` e antes de `:418`):

```python
    # Track A (Tema 6): gates de execução externa (Decisão 33). Mesclados na
    # lista `results` ANTES do overall → fluem natural pro overall/coverage/
    # infra_degraded/JSON/render sem refactor do cascade.
    results = results + _run_native_gates(config, project_root, interactive=interactive)
```

> **Por que aqui:** `results` é consumido por `_render_summary` (`:416`), pelo
> cálculo de `hard_fail`/`warnings_list`/`degraded_list`/`overall` (`:418-448`),
> pelo `_write_verify_log_entry` (`:450`) e pelo payload `--json` (`:466-480`).
> Mesclar antes do `:418` faz os gates aparecerem em **todos** sem tocar nenhum.
> Como `degraded` vira `incomplete` no overall e `warn` não seta hard_fail, o
> exit-code segue 0 mesmo com gate em `warn`/`degraded` — exatamente o contrato.

---

## A1 — Native gate ktlint (TDD)

**Arquivo de produção:** `engine/verify.py`
**Arquivo de teste:** `tests/engine/test_verify_native_gates.py`
**Doc-sync (mesmo commit):** `CHANGELOG.md`, `docs/schemas/forge-config.md`,
`docs/design/06-command-surface.md`.

**Config nova (bloco `native-gates.ktlint`):**

```yaml
native-gates:
  ktlint:
    enabled: true            # default true; mas ausência do tool → skipped (não fail)
    bin: /opt/ktlint         # opcional; path/argv do binário quando não há wrapper
    timeout: 120             # segundos; default 120; estouro → degraded
    fail-on-violation: false # opt-in: true sobe warn→fail (default não-reprovante)
```

**Candidatos de invocação do ktlint (ordem de preferência — `_ktlint_candidates`):**

1. `["./gradlew", "ktlintCheck"]` — wrapper do projeto (versão fixada; preferido).
2. `bin` do config (`native-gates.ktlint.bin`) — se string, vira `[bin]`; se já
   for argv-lista, passa inalterado. Pra projetos que rodam ktlint fora do build.
3. `"ktlint"` — `which ktlint` no PATH (last-resort).

Saída estruturada quando possível no Nível 1: **acrescentar `--reporter=json` só ao
candidato wrapper/bin do ktlint nativo** (não muda o mapping mínimo: exit code →
status; o `stdout`/`stderr` vai no `message`). O parse JSON fica como follow-on
anotado (YAGNI no Nível 1) — o mapping de Nível 1 é puramente exit-code.

---

### A1 — Step 1 (RED): test pass — exit 0 → `_ValidatorResult.status="pass"`

**Arquivo:** `tests/engine/test_verify_native_gates.py`

Escreva o arquivo de teste com fixtures e o primeiro teste FALHANDO (o
`_run_native_gates` ainda não existe → `AttributeError`/`ImportError`).

```python
"""Track A1 — native gate ktlint no forge verify.

Fixtures: fake gradle wrapper (script trivial em tmp que sai com exit code
controlado) + monkeypatch de run_external_tool. NÃO depende de gradle/ktlint
reais. Cobre: pass / violação→warn / ausente→skipped / timeout→degraded / a
mescla no run_scope / o opt-in warn→fail.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from engine import verify
from engine.external_exec import ExternalToolResult


def _write_fake_gradlew(project_root: Path, *, exit_code: int) -> Path:
    """Cria um ./gradlew trivial que sai com `exit_code`.

    Serve só pra `resolve_invocation` enxergar o wrapper como arquivo presente;
    a execução real é interceptada por monkeypatch de run_external_tool nos
    testes que precisam de um resultado controlado.
    """
    gradlew = project_root / "gradlew"
    gradlew.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    mode = gradlew.stat().st_mode
    gradlew.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return gradlew


@pytest.fixture
def project_with_wrapper(tmp_path: Path) -> Path:
    """Project root com ./gradlew presente (exit 0 por default)."""
    _write_fake_gradlew(tmp_path, exit_code=0)
    return tmp_path


def _fake_run(status: str, *, exit_code: int | None, skipped_reason: str = "") -> object:
    """Factory de stub pra monkeypatch de run_external_tool."""

    def _runner(argv, project_root, *, timeout=120):
        return ExternalToolResult(
            tool=argv[0],
            status=status,
            exit_code=exit_code,
            stdout="",
            stderr="",
            duration_ms=12,
            skipped_reason=skipped_reason,
        )

    return _runner


def test_ktlint_pass_maps_to_pass(project_with_wrapper, monkeypatch):
    """exit 0 → _ValidatorResult.status == 'pass'."""
    monkeypatch.setattr(
        verify, "run_external_tool", _fake_run("pass", exit_code=0)
    )
    config = {"native-gates": {"ktlint": {"enabled": True}}}

    results = verify._run_native_gates(
        config, project_with_wrapper, interactive=False
    )

    ktlint = [r for r in results if r.name == "ktlint"]
    assert len(ktlint) == 1
    assert ktlint[0].status == "pass"
    assert ktlint[0].coverage == "substantive"
```

**Verify (RED):** `.venv/bin/pytest tests/engine/test_verify_native_gates.py::test_ktlint_pass_maps_to_pass -x` → FALHA
(`AttributeError: module 'engine.verify' has no attribute '_run_native_gates'` ou
`run_external_tool`).

**Done:** teste existe e falha exatamente porque a função/símbolo não existe.

---

### A1 — Step 2 (GREEN): implementar `_run_native_gates` + helpers (só ktlint) + wire em `run_scope`

**Arquivo:** `engine/verify.py`

Implemente o mínimo pra o teste do Step 1 passar — e já com a forma final do
contrato §1 (o resto dos testes do A1 vêm nos steps seguintes, mas a
implementação cobre todos os branches de uma vez, sem stub no-op).

1. **Imports** (após os imports existentes, junto dos `from engine...`):

```python
from engine.external_exec import (
    ExternalToolResult,
    resolve_invocation,
    run_external_tool,
)
```

2. **Constante de mapping** (perto de `_COVERAGE_CLASSES`, `:106`):

```python
# Track A (Tema 6) — mapping ExternalToolResult.status → _ValidatorResult.status.
# LOCKED: violação reportada (exit≠0, tool rodou) é INFORMATIVA (warn), não fail.
# Subir warn→fail é opt-in por gate (`fail-on-violation: true`). Não cria
# vermelho inerte — espelha a lição do Tema 6 (verde inerte mente).
_EXTERNAL_STATUS_MAP: dict[str, str] = {
    "pass": "pass",
    "fail": "warn",
    "degraded": "degraded",
    "skipped": "skipped",
}
```

3. **Helpers** (numa seção nova `# ── Native gates (Tema 6, Decisão 33) ──`, antes
   da seção `# ── Rendering ──` em `:1166`):

```python
def _native_gate_block(config: dict) -> dict:
    """Bloco `native-gates` do config; `{}` se ausente/malformado."""
    block = config.get("native-gates")
    return block if isinstance(block, dict) else {}


def _ktlint_candidates(config: dict, project_root: Path) -> list[list[str] | str]:
    """Candidatos de invocação do ktlint, em ordem de preferência.

    1. ./gradlew ktlintCheck (wrapper — versão fixada, preferido). Saída
       estruturada (--reporter=json) acoplada ao wrapper/bin nativo.
    2. native-gates.ktlint.bin (str → [bin]; argv-lista → inalterado).
    3. ktlint (which no PATH).
    """
    candidates: list[list[str] | str] = [["./gradlew", "ktlintCheck", "--reporter=json"]]
    ktlint_cfg = _native_gate_block(config).get("ktlint")
    if isinstance(ktlint_cfg, dict):
        bin_value = ktlint_cfg.get("bin")
        if isinstance(bin_value, str) and bin_value.strip():
            candidates.append([bin_value.strip(), "--reporter=json"])
        elif isinstance(bin_value, list) and bin_value:
            candidates.append([str(x) for x in bin_value])
    candidates.append("ktlint")
    return candidates


def _gate_cfg(config: dict, gate: str) -> dict:
    """Sub-bloco `native-gates.<gate>`; `{}` se ausente."""
    sub = _native_gate_block(config).get(gate)
    return sub if isinstance(sub, dict) else {}


def _gate_enabled(config: dict, gate: str) -> bool:
    """Default True — ausência do tool ainda vira skipped no resolve."""
    return bool(_gate_cfg(config, gate).get("enabled", True))


def _gate_timeout(config: dict, gate: str) -> int:
    raw = _gate_cfg(config, gate).get("timeout", 120)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 120
    return value if value > 0 else 120


def _gate_fail_on_violation(config: dict, gate: str) -> bool:
    """Opt-in: True sobe warn→fail. Default False (informativo)."""
    return bool(_gate_cfg(config, gate).get("fail-on-violation", False))


def _map_external_result(
    res: ExternalToolResult,
    *,
    gate_name: str,
    fail_on_violation: bool,
) -> _ValidatorResult:
    """ExternalToolResult → _ValidatorResult (mapping LOCKED).

    - status pelo _EXTERNAL_STATUS_MAP; `warn` vira `fail` só com opt-in.
    - coverage: pass externo é 'substantive' (rodou tool real sobre artefatos
      reais — não é stub/staged-blind/opaque). Não-pass não tem coverage.
    """
    mapped = _EXTERNAL_STATUS_MAP.get(res.status, "degraded")
    if mapped == "warn" and fail_on_violation:
        mapped = "fail"

    message = ""
    if res.status == "degraded":
        message = res.skipped_reason or "gate não terminou — classificado como degraded"
    elif res.status == "fail":
        tail = (res.stdout or res.stderr or "").strip().splitlines()
        message = (
            f"{gate_name} acusou violações (informativo; não reprova por default)."
            + (f" {tail[-1][:80]}" if tail else "")
        )

    return _ValidatorResult(
        name=gate_name,
        status=mapped,
        duration_ms=res.duration_ms,
        message=message,
        coverage="substantive" if mapped == "pass" else "",
    )


def _skipped_gate_result(gate_name: str, message: str) -> _ValidatorResult:
    """Gate ausente → skipped com mensagem mentor-calmo nomeando como habilitar."""
    return _ValidatorResult(name=gate_name, status="skipped", message=message)


def _run_native_gates(
    config: dict,
    project_root: Path,
    *,
    interactive: bool,
) -> list[_ValidatorResult]:
    """Gates de execução externa (Decisão 33). Ver contrato no plano §1."""
    if not config:
        # Guard greenfield: config vazio (mid-init) → não roda gate algum.
        return []

    results: list[_ValidatorResult] = []
    results.extend(_run_ktlint_gate(config, project_root))
    # A2 acrescenta aqui: results.extend(_run_build_gates(config, project_root))
    return results


def _run_ktlint_gate(config: dict, project_root: Path) -> list[_ValidatorResult]:
    if not _gate_enabled(config, "ktlint"):
        return []
    argv = resolve_invocation(_ktlint_candidates(config, project_root), project_root)
    if argv is None:
        return [
            _skipped_gate_result(
                "ktlint",
                "Gate nativo `ktlint` não encontrado (nem `./gradlew ktlintCheck`, "
                "nem `native-gates.ktlint.bin`, nem no PATH). Pulei este gate — a "
                "feature não foi reprovada por isso. Pra habilitá-lo, instale o "
                "ktlint ou aponte o binário em `forge-config.yaml`.",
            )
        ]
    res = run_external_tool(
        argv, project_root, timeout=_gate_timeout(config, "ktlint")
    )
    return [
        _map_external_result(
            res,
            gate_name="ktlint",
            fail_on_violation=_gate_fail_on_violation(config, "ktlint"),
        )
    ]
```

4. **Wire em `run_scope()`** — após `_run_cascade` (linha `:414`) e antes de
   `if interactive: _render_summary(results)` (`:415-416`):

```python
    results = results + _run_native_gates(config, project_root, interactive=interactive)
```

> **Atenção ao caminho early-return:** o bloco `if not validators:` (`:359-392`)
> faz `return` ANTES do cascade. No Nível 1 os gates nativos rodam **junto do
> cascade** (caminho com validators). Se `validators` está vazio, o early-return
> dispara e os gates não rodam — isso é **aceitável e documentado** no Nível 1
> (gates nativos acompanham a cascade; um projeto sem validators registrados
> também não roda gate nativo). NÃO refatore o early-return pra forçar gates —
> fica anotado como follow-on (ver §Follow-on).

**Verify (GREEN):** `.venv/bin/pytest tests/engine/test_verify_native_gates.py::test_ktlint_pass_maps_to_pass -x` → PASSA.

**Done:** o teste do Step 1 passa; `_run_native_gates` existe com a forma final
do contrato §1 (sem stub no-op).

---

### A1 — Step 3 (RED→GREEN): violação → `warn` (overall warn, exit 0) + opt-in `warn→fail`

**Arquivo:** `tests/engine/test_verify_native_gates.py` (acrescentar testes);
implementação já coberta no Step 2 (rode pra confirmar GREEN sem novo código).

```python
def test_ktlint_violation_maps_to_warn_by_default(project_with_wrapper, monkeypatch):
    """exit≠0 (tool rodou e acusou) → warn (informativo, não fail)."""
    monkeypatch.setattr(
        verify, "run_external_tool", _fake_run("fail", exit_code=1)
    )
    config = {"native-gates": {"ktlint": {"enabled": True}}}

    results = verify._run_native_gates(config, project_with_wrapper, interactive=False)

    ktlint = next(r for r in results if r.name == "ktlint")
    assert ktlint.status == "warn"
    assert "informativo" in ktlint.message.lower()


def test_ktlint_violation_opt_in_fail(project_with_wrapper, monkeypatch):
    """fail-on-violation: true sobe warn→fail (gate com dentes, opt-in)."""
    monkeypatch.setattr(
        verify, "run_external_tool", _fake_run("fail", exit_code=1)
    )
    config = {
        "native-gates": {"ktlint": {"enabled": True, "fail-on-violation": True}}
    }

    results = verify._run_native_gates(config, project_with_wrapper, interactive=False)

    ktlint = next(r for r in results if r.name == "ktlint")
    assert ktlint.status == "fail"


def test_ktlint_disabled_skips_entirely(project_with_wrapper, monkeypatch):
    """enabled: false → gate não roda (lista vazia pro ktlint)."""
    called = {"hit": False}

    def _boom(*a, **k):
        called["hit"] = True
        raise AssertionError("run_external_tool não devia ser chamado")

    monkeypatch.setattr(verify, "run_external_tool", _boom)
    config = {"native-gates": {"ktlint": {"enabled": False}}}

    results = verify._run_native_gates(config, project_with_wrapper, interactive=False)

    assert [r for r in results if r.name == "ktlint"] == []
    assert called["hit"] is False
```

**Verify (GREEN):** `.venv/bin/pytest tests/engine/test_verify_native_gates.py -k "violation or disabled" -x` → PASSA (sem novo código de produção; só confirma os branches do Step 2).

**Done:** warn-default, opt-in fail e disabled provados.

---

### A1 — Step 4 (RED→GREEN): ausente → `skipped` + mensagem mentor-calmo; timeout/OSError → `degraded`

**Arquivo:** `tests/engine/test_verify_native_gates.py` (acrescentar);
implementação já coberta no Step 2.

```python
def test_ktlint_absent_skips_with_mentor_message(tmp_path, monkeypatch):
    """Sem ./gradlew, sem bin, sem ktlint no PATH → skipped + como habilitar."""
    monkeypatch.setattr(verify, "resolve_invocation", lambda c, p: None)
    config = {"native-gates": {"ktlint": {"enabled": True}}}

    results = verify._run_native_gates(config, tmp_path, interactive=False)

    ktlint = next(r for r in results if r.name == "ktlint")
    assert ktlint.status == "skipped"
    assert "não foi reprovada" in ktlint.message
    assert "forge-config.yaml" in ktlint.message


def test_ktlint_timeout_maps_to_degraded(project_with_wrapper, monkeypatch):
    """Timeout (run_external_tool devolve degraded) → degraded com motivo."""
    monkeypatch.setattr(
        verify,
        "run_external_tool",
        _fake_run("degraded", exit_code=None, skipped_reason="timeout (>120s)"),
    )
    config = {"native-gates": {"ktlint": {"enabled": True}}}

    results = verify._run_native_gates(config, project_with_wrapper, interactive=False)

    ktlint = next(r for r in results if r.name == "ktlint")
    assert ktlint.status == "degraded"
    assert "timeout" in ktlint.message.lower()
```

**Verify (GREEN):** `.venv/bin/pytest tests/engine/test_verify_native_gates.py -k "absent or timeout" -x` → PASSA.

**Done:** skip-se-ausente com texto-modelo da spec native-gates §2 e degraded por
timeout provados.

---

### A1 — Step 5 (RED→GREEN): mescla no `run_scope` (gate aparece em results/JSON/overall) + não-regressão

**Arquivo:** `tests/engine/test_verify_native_gates.py` (acrescentar);
implementação já coberta no Step 2 (wire em `run_scope`).

Este teste prova a integração ponta-a-ponta: um `run_scope` com cascade vazia mas
gates presentes, em `--json`, mostra o gate em `validators[]`, e o `overall`
reflete o status do gate. Use `output_mode` em JSON pra capturar o payload via
`capsys`.

```python
def test_native_gate_merges_into_run_scope_json(project_with_wrapper, monkeypatch, capsys):
    """O gate ktlint flui pro payload --json e pro overall do run_scope.

    Cascade com 1 validator pass (pra não cair no early-return de validators
    vazios) + ktlint em warn → overall 'warn', exit 0, ktlint em validators[].
    """
    import json as _json

    from engine.ui import output_mode

    # 1 validator pass no cascade (evita o early-return de validators vazios).
    monkeypatch.setattr(
        verify,
        "_discover_validators",
        lambda root, cfg, scope: [
            verify._ValidatorSpec(name="dummy", script_path=Path("/x"))
        ],
    )
    monkeypatch.setattr(
        verify,
        "_run_cascade",
        lambda validators, **k: [
            verify._ValidatorResult(name="dummy", status="pass", coverage="substantive")
        ],
    )
    # ktlint presente, acusa violação → warn.
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("fail", exit_code=1))
    monkeypatch.setattr(
        verify, "_write_verify_log_entry", lambda *a, **k: None
    )
    monkeypatch.setattr(verify, "_restore_l1_status", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_clear_verify_checkpoint", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_scope_to_feature_slug", lambda *a, **k: "")

    # forge-config com bloco native-gates → read_yaml_or_default devolve dict.
    (project_with_wrapper / ".claude" / "forge").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        verify,
        "read_yaml_or_default",
        lambda path, default: {"native-gates": {"ktlint": {"enabled": True}}},
    )

    monkeypatch.setattr(output_mode, "is_json_mode", lambda: True)
    exit_code = verify.run_scope("feature", "demo", project_with_wrapper, interactive=False)

    payload = _json.loads(capsys.readouterr().out)
    names = [v["name"] for v in payload["validators"]]
    assert "ktlint" in names
    assert payload["overall"] == "warn"   # warn não reprova
    assert exit_code == 0                  # warn → exit 0
```

**Verify (GREEN):** `.venv/bin/pytest tests/engine/test_verify_native_gates.py::test_native_gate_merges_into_run_scope_json -x` → PASSA.

**Não-regressão (GATE de "pronto" do A1):**
`.venv/bin/pytest tests/engine/ -k verify -m "not integration and not e2e"` → todos os
testes existentes de verify continuam verdes (o step novo só ESTENDE `results`;
não muda o caminho de validators vazios nem o cascade).

**Done:** o gate aparece em `validators[]` no JSON, no `overall`, e o pipeline
existente não regride.

---

### A1 — Step 6 (doc-sync, MESMO commit)

**`docs/schemas/forge-config.md`** — após o bloco `secrets-gate` (`:553-600`), antes
de `## Deliberately OUT of config` (`:677`), adicione a seção:

```markdown
## `native-gates` (opt-in, Tema 6 / Decisão 33)

Configura os gates de **execução externa** — o engine roda os binários de
qualidade/build do projeto consumidor (linters, build tools) via a fronteira da
Decisão 33 (distinta do sandbox de validators da Decisão 30). Bloco opcional —
sem ele, os gates usam defaults. **Filosofia:** violação é **informativa** por
default (`warn`, não reprova); subir pra `fail` é opt-in por gate. Tool ausente
→ `skipped` (não reprova); timeout → `degraded`. Nunca auto-fix.

\`\`\`yaml
native-gates:
  ktlint:
    enabled: true             # default true; ausência do tool ainda → skipped
    bin: /opt/ktlint          # opcional; path/argv quando não há ./gradlew
    timeout: 120              # segundos; default 120; estouro → degraded
    fail-on-violation: false  # opt-in: true sobe warn→fail (default informativo)
  build:
    enabled: true             # default true; toolchain ausente → skipped/degraded
    timeout: 600              # builds são lentos; default 600s; estouro → degraded
    fail-on-violation: false  # opt-in: true sobe warn→fail
\`\`\`

### Semântica de campos

| Campo | Tipo | Default | Notas |
|---|---|---|---|
| `<gate>.enabled` | bool | `true` | `false` desliga o gate inteiro (não invoca tool) |
| `ktlint.bin` | str \| argv | — | path/argv do ktlint quando não há `./gradlew`; ignorado se o wrapper existe |
| `<gate>.timeout` | int > 0 | ktlint 120 / build 600 | estouro → `degraded` (não `fail`) |
| `<gate>.fail-on-violation` | bool | `false` | `true` sobe `warn → fail` (gate com dentes, opt-in) |

### Descoberta do binário (skip-se-ausente)

Ordem de preferência (primeiro que resolver vence):

- **ktlint:** `./gradlew ktlintCheck` → `native-gates.ktlint.bin` → `which ktlint`.
- **build:** por plataforma de `platforms.active` — android/kmp → `./gradlew assembleDebug`;
  ios → `xcodebuild build` (forma mínima); web → sem build-only no Nível 1 (skip).

Nenhum resolve → o gate é `skipped` com aviso mentor-calmo nomeando como habilitar.
Skip-se-ausente é **requisito**, não conveniência: um gate que falha por ausência
tornaria o forge refém da toolchain de cada consumidor.

### Notas de runtime

- **Modo check, read-only (ktlint).** O ktlint roda só em `ktlintCheck` — nunca
  `ktlintFormat`/`--fix`. A garantia "não escreve" vem de escolher o subcomando.
- **O build ESCREVE artefatos** (binários, caches) no working tree do projeto.
  Isso é esperado e legítimo (é o build do próprio projeto); o forge **não
  versiona nem limpa** esses artefatos.
- **`degraded` é cidadão de primeira classe.** Ausente/estourado → `degraded`,
  distinto de `pass`/`fail`. Ataca o "verde inerte" do Tema 6: o usuário vê que o
  gate não rodou, em vez de um falso verde.
- Os gates acompanham a **cascade de validators**: num scope sem validators
  registrados, os gates nativos também não rodam (Nível 1).
```

> **Nota ao executor:** as cercas \`\`\` acima estão escapadas porque vivem dentro
> deste plano markdown. No `forge-config.md` real elas são cercas normais de
> três backticks.

**`docs/design/06-command-surface.md`** — na entrada do `forge verify`, acrescente
um parágrafo: o `verify` agora roda **gates de execução externa (Decisão 33)** —
no Nível 1, o **ktlint** via `./gradlew ktlintCheck` — junto da cascade de
validators. Violação é informativa (`warn`, exit 0) por default; opt-in
`fail-on-violation` sobe pra `fail`. Tool ausente → `skipped`; timeout →
`degraded`. (O step build-only entra na A2.)

**`CHANGELOG.md`** — em `## [Unreleased] § Added` (ou criar a subseção):
`- Native gate ktlint no `forge verify` (Tema 6, Decisão 33): `./gradlew ktlintCheck`
em modo check, informativo por default (`warn`), opt-in `fail-on-violation`,
skip-se-ausente, timeout → `degraded`. Config em `native-gates.ktlint`.`

**`README.md`:** só se os números de teste/contagem que ele cita mudarem (provável
sim — novos testes). Atualize o count se citado.

**Verify (doc-sync):** `forge verify` não deve hard-fail por causa dos docs;
confirme que `docs/schemas/forge-config.md` é YAML-válido nas cercas.

**Done do A1:** lane rápida verde + os 8 testes do A1 verdes + não-regressão de
verify + doc-sync no mesmo commit (CHANGELOG + schema + command-surface).

---

## A2 — Build-only (TDD, reusa o step de A1)

**Arquivo de produção:** `engine/verify.py` (reusa `_run_native_gates`,
`_map_external_result`, `_gate_*`, `resolve_invocation`, `run_external_tool` de A1).
**Arquivo de teste:** `tests/engine/test_verify_build_only.py`
**Doc-sync (mesmo commit):** `CHANGELOG.md`, `docs/schemas/forge-config.md`
(o bloco `native-gates.build` já foi documentado em A1 §Step 6 — confirme que está
lá e só acrescente as notas que faltarem), `docs/design/06-command-surface.md`,
`docs/design/04-pending.md`.

**Stack → comando de build (`_build_candidates`):**

- `android` / `kmp` → `["./gradlew", "assembleDebug"]`.
- `ios` → `["xcodebuild", "build"]` (forma mínima sensata; sem `-scheme`/`-project`
  no Nível 1 — se o consumidor precisar de flags, é follow-on de config).
- `web` → sem build-only no Nível 1 → **skip** (não gera `_ValidatorResult`).

Lê a stack de `config.get("platforms", {}).get("active", [])`. Para cada
plataforma com build, resolve via `resolve_invocation` e roda via
`run_external_tool` — **exatamente o mesmo caminho do ktlint**, só mudando os
candidatos. Mesmo mapping de status (build falha → `warn` informativo por default;
opt-in `fail`; toolchain ausente → `skipped`; timeout → `degraded`).

---

### A2 — Step 1 (RED): test android build pass + reuso do step

**Arquivo:** `tests/engine/test_verify_build_only.py`

```python
"""Track A2 — build-only no forge verify (reusa o step de A1).

Mesmas fixtures-padrão do A1 (fake gradlew + monkeypatch de run_external_tool).
Cobre por plataforma: android pass / build-falha→warn / opt-in fail / ausente→
skipped / timeout→degraded / web→sem build / mescla no run_scope / guard greenfield.
"""
from __future__ import annotations

import stat
from pathlib import Path

import pytest

from engine import verify
from engine.external_exec import ExternalToolResult


def _write_fake_gradlew(project_root: Path, *, exit_code: int = 0) -> Path:
    gradlew = project_root / "gradlew"
    gradlew.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    mode = gradlew.stat().st_mode
    gradlew.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return gradlew


def _fake_run(status: str, *, exit_code: int | None, skipped_reason: str = ""):
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


@pytest.fixture
def android_project(tmp_path: Path) -> Path:
    _write_fake_gradlew(tmp_path, exit_code=0)
    return tmp_path


def test_build_android_pass(android_project, monkeypatch):
    """android com gradlew presente + exit 0 → build gate pass."""
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("pass", exit_code=0))
    config = {
        "platforms": {"active": ["android"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }

    results = verify._run_native_gates(config, android_project, interactive=False)

    build = [r for r in results if r.name == "build"]
    assert len(build) == 1
    assert build[0].status == "pass"
```

**Verify (RED):** `.venv/bin/pytest tests/engine/test_verify_build_only.py::test_build_android_pass -x` → FALHA
(nenhum `_ValidatorResult` com `name == "build"` — `_run_native_gates` ainda só roda ktlint).

**Done:** teste existe e falha porque o step de build ainda não foi acoplado.

---

### A2 — Step 2 (GREEN): `_build_candidates` + `_run_build_gates` + acoplar em `_run_native_gates`

**Arquivo:** `engine/verify.py`

1. Adicione os helpers na seção `# ── Native gates ──` (após `_run_ktlint_gate`):

```python
# Plataforma → comando de build-only (modo build, sem rodar o app). web não tem
# build-only no Nível 1 (skip). android/kmp compartilham o gradle wrapper.
_BUILD_CMD_BY_PLATFORM: dict[str, list[str]] = {
    "android": ["./gradlew", "assembleDebug"],
    "kmp": ["./gradlew", "assembleDebug"],
    "ios": ["xcodebuild", "build"],
}


def _active_platforms(config: dict) -> list[str]:
    platforms = config.get("platforms")
    if not isinstance(platforms, dict):
        return []
    active = platforms.get("active")
    return [str(p) for p in active] if isinstance(active, list) else []


def _build_candidates(platform: str) -> list[list[str] | str]:
    """Candidatos de invocação do build-only pra uma plataforma.

    Um candidato por plataforma no Nível 1 (o wrapper/binário canônico). web e
    plataformas desconhecidas devolvem [] → o caller pula (sem _ValidatorResult).
    """
    cmd = _BUILD_CMD_BY_PLATFORM.get(platform)
    return [cmd] if cmd else []


def _run_build_gates(config: dict, project_root: Path) -> list[_ValidatorResult]:
    """Build-only por plataforma ativa. Reusa resolve/run/map do A1.

    Um único _ValidatorResult `build` (a primeira plataforma com build que
    resolver vence) — Nível 1 não roda múltiplos builds no mesmo verify. Se
    nenhuma plataforma com build resolve E ao menos uma plataforma de build
    estava ativa → skipped; se só web/desconhecidas → nada (lista vazia).
    """
    if not _gate_enabled(config, "build"):
        return []

    platforms = _active_platforms(config)
    buildable = [p for p in platforms if _build_candidates(p)]
    if not buildable:
        return []  # só web/desconhecidas → sem build-only no Nível 1

    for platform in buildable:
        argv = resolve_invocation(_build_candidates(platform), project_root)
        if argv is None:
            continue
        res = run_external_tool(
            argv, project_root, timeout=_gate_timeout(config, "build")
        )
        return [
            _map_external_result(
                res,
                gate_name="build",
                fail_on_violation=_gate_fail_on_violation(config, "build"),
            )
        ]

    # Plataforma com build ativa mas toolchain ausente → skipped (não fail).
    return [
        _skipped_gate_result(
            "build",
            "Build-only pulado: toolchain de build não encontrada (nem `./gradlew "
            "assembleDebug` pra android/kmp, nem `xcodebuild` pra ios). A feature não "
            "foi reprovada por isso. Instale o SDK/toolchain pra habilitar o build-only.",
        )
    ]
```

2. **Acople em `_run_native_gates`** — descomente/adicione a linha já antecipada
   no A1 (Step 2), logo após o ktlint:

```python
    results.extend(_run_build_gates(config, project_root))
```

> **Reuso confirmado:** `_run_build_gates` não duplica resolve/run/map — chama
> `resolve_invocation`, `run_external_tool` e `_map_external_result` (de A1). A
> única lógica nova é `_build_candidates` (plataforma → comando) + a varredura de
> `platforms.active`. O `_gate_timeout` default já cobre o build via o default do
> schema (600s no doc; o código usa 120 a menos que o config diga outra coisa —
> ver nota abaixo).

> **Coerência timeout default:** `_gate_timeout` retorna 120 quando o config não
> declara `timeout`. O schema documenta default 600 pra build. Pra honrar isso
> **sem ramificar `_gate_timeout` por gate**, o executor deve passar o default no
> call-site do build: troque `timeout=_gate_timeout(config, "build")` por
> `timeout=_gate_timeout(config, "build", default=600)` E estenda `_gate_timeout`
> com um parâmetro `default: int = 120`. Atualize a assinatura no §1 mentalmente —
> o teste de timeout do build não depende do valor exato (usa o stub), mas a
> coerência doc↔código é parte do done.

**Verify (GREEN):** `.venv/bin/pytest tests/engine/test_verify_build_only.py::test_build_android_pass -x` → PASSA.

**Done:** build gate android pass via reuso do step de A1.

---

### A2 — Step 3 (RED→GREEN): build-falha→warn + opt-in fail + ios + web-skip + ausente→skipped + timeout→degraded

**Arquivo:** `tests/engine/test_verify_build_only.py` (acrescentar); implementação
já coberta no Step 2.

```python
def test_build_failure_maps_to_warn(android_project, monkeypatch):
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("fail", exit_code=1))
    config = {
        "platforms": {"active": ["android"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }
    build = next(
        r for r in verify._run_native_gates(config, android_project, interactive=False)
        if r.name == "build"
    )
    assert build.status == "warn"


def test_build_failure_opt_in_fail(android_project, monkeypatch):
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("fail", exit_code=1))
    config = {
        "platforms": {"active": ["android"]},
        "native-gates": {
            "build": {"enabled": True, "fail-on-violation": True},
            "ktlint": {"enabled": False},
        },
    }
    build = next(
        r for r in verify._run_native_gates(config, android_project, interactive=False)
        if r.name == "build"
    )
    assert build.status == "fail"


def test_build_web_only_produces_no_build_gate(tmp_path, monkeypatch):
    """web não tem build-only no Nível 1 → nenhum _ValidatorResult 'build'."""
    monkeypatch.setattr(
        verify, "run_external_tool", _fake_run("pass", exit_code=0)
    )
    config = {
        "platforms": {"active": ["web"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }
    results = verify._run_native_gates(config, tmp_path, interactive=False)
    assert [r for r in results if r.name == "build"] == []


def test_build_toolchain_absent_skips(tmp_path, monkeypatch):
    """ios ativo mas sem xcodebuild → skipped (não fail). tmp_path sem gradlew."""
    monkeypatch.setattr(verify, "resolve_invocation", lambda c, p: None)
    config = {
        "platforms": {"active": ["ios"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }
    build = next(
        r for r in verify._run_native_gates(config, tmp_path, interactive=False)
        if r.name == "build"
    )
    assert build.status == "skipped"
    assert "não foi reprovada" in build.message


def test_build_timeout_maps_to_degraded(android_project, monkeypatch):
    monkeypatch.setattr(
        verify,
        "run_external_tool",
        _fake_run("degraded", exit_code=None, skipped_reason="timeout (>600s)"),
    )
    config = {
        "platforms": {"active": ["android"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }
    build = next(
        r for r in verify._run_native_gates(config, android_project, interactive=False)
        if r.name == "build"
    )
    assert build.status == "degraded"
    assert "timeout" in build.message.lower()
```

**Verify (GREEN):** `.venv/bin/pytest tests/engine/test_verify_build_only.py -k "failure or web or absent or timeout" -x` → PASSA.

**Done:** warn-default, opt-in fail, web-skip, toolchain-ausente skipped e timeout
degraded provados pro build-only.

---

### A2 — Step 4 (RED→GREEN): guard greenfield + mescla no `run_scope` com ktlint+build juntos

**Arquivo:** `tests/engine/test_verify_build_only.py` (acrescentar); implementação
já coberta (guard `if not config: return []` em A1 Step 2).

```python
def test_greenfield_empty_config_runs_no_gates(tmp_path):
    """Config vazio (mid-init) → nenhum gate roda (silent skip)."""
    assert verify._run_native_gates({}, tmp_path, interactive=False) == []


def test_ktlint_and_build_both_merge_into_run_scope(android_project, monkeypatch, capsys):
    """ktlint + build juntos fluem pro payload --json do run_scope."""
    import json as _json
    from engine.ui import output_mode

    monkeypatch.setattr(
        verify,
        "_discover_validators",
        lambda root, cfg, scope: [
            verify._ValidatorSpec(name="dummy", script_path=Path("/x"))
        ],
    )
    monkeypatch.setattr(
        verify,
        "_run_cascade",
        lambda validators, **k: [
            verify._ValidatorResult(name="dummy", status="pass", coverage="substantive")
        ],
    )
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("pass", exit_code=0))
    monkeypatch.setattr(verify, "_write_verify_log_entry", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_restore_l1_status", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_clear_verify_checkpoint", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_scope_to_feature_slug", lambda *a, **k: "")
    monkeypatch.setattr(
        verify,
        "read_yaml_or_default",
        lambda path, default: {
            "platforms": {"active": ["android"]},
            "native-gates": {"ktlint": {"enabled": True}, "build": {"enabled": True}},
        },
    )
    monkeypatch.setattr(output_mode, "is_json_mode", lambda: True)

    exit_code = verify.run_scope("feature", "demo", android_project, interactive=False)

    payload = _json.loads(capsys.readouterr().out)
    names = [v["name"] for v in payload["validators"]]
    assert "ktlint" in names
    assert "build" in names
    assert payload["overall"] == "pass"
    assert exit_code == 0
```

**Verify (GREEN):** `.venv/bin/pytest tests/engine/test_verify_build_only.py -k "greenfield or both_merge" -x` → PASSA.

**Não-regressão (GATE de "pronto" do A2):**
`.venv/bin/pytest tests/engine/ -k verify -m "not integration and not e2e"` verde +
lane rápida inteira verde.

**Done:** guard greenfield e mescla ktlint+build no run_scope provados; pipeline
existente sem regressão.

---

### A2 — Step 5 (doc-sync, MESMO commit)

**`docs/schemas/forge-config.md`:** confirme que o bloco `native-gates.build`
(documentado em A1 Step 6) está presente e completo; complemente as notas de
plataforma se faltarem (android/kmp → `assembleDebug`; ios → `xcodebuild build`;
web → sem build-only no Nível 1) e a nota de que **o build escreve artefatos no
working tree** (o forge não versiona/limpa).

**`docs/design/06-command-surface.md`:** complete o parágrafo do `verify` com o
step build-only: `./gradlew assembleDebug` (android/kmp) / `xcodebuild build`
(ios), conforme `platforms.active`; web sem build-only no Nível 1; mesmo
mapping de status (build-falha → `warn` informativo, opt-in `fail`; toolchain
ausente → `skipped`; timeout → `degraded`).

**`docs/design/04-pending.md`:** mover as duas faces de Follow-on pra Fechados:
- **impl de gates-nativos (Tema 6, face 2)** (`:148-153`) → marcar `✓` em Fechados,
  citando a impl (`engine/verify.py::_run_native_gates` / `_run_ktlint_gate`) e as
  guardas (`tests/engine/test_verify_native_gates.py`).
- **impl de runtime/visual (Tema 6, face 3)** (`:154-157`) → marcar `✓` em Fechados
  **só o Nível 1 build-only**; deixar explícito que smoke (Nível 2) e screenshot
  (Nível 3) seguem deferidos com seus critérios de reentrada. Guarda:
  `tests/engine/test_verify_build_only.py`.
Também atualize a entrada **P0 §Tema 6** (`:131-139`) registrando que as faces
gates-nativos e build-only foram fechadas na Fase 1 Track A.

**`CHANGELOG.md`** — em `## [Unreleased] § Added`:
`- Build-only no `forge verify` (Tema 6, Nível 1, Decisão 33): `./gradlew assembleDebug`
(android/kmp) / `xcodebuild build` (ios) conforme `platforms.active`, reusando o step
de gates externos. Informativo por default, opt-in `fail-on-violation`, skip-se-ausente,
timeout → `degraded`. Config em `native-gates.build`.`

**`README.md`:** atualize o count de testes se citado.

**Verify (doc-sync):** `docs/design/04-pending.md` — confirme que NENHUMA das duas
faces aparece mais em Follow-on (`grep -c` filtrado por linhas não-comentário).

**Done do A2:** lane rápida verde + os testes do A2 verdes + não-regressão de
verify + doc-sync no mesmo commit (CHANGELOG + schema + command-surface +
04-pending).

---

## 2. Follow-on (YAGNI no Nível 1 — anotar, não fazer)

Registrar em `04-pending.md` como follow-on, não implementar agora:

1. **Parse JSON estruturado do ktlint** (`--reporter=json`) → violações
   individuais no sumário, em vez do mapping exit-code. O `--reporter=json` já é
   passado no candidato wrapper/bin; falta só o parse.
2. **Agrupamento visual por tool** em `_render_summary`. No Nível 1 o `name` do
   entry (`ktlint`/`build`) já identifica o tool — agrupar por tool é cosmético.
3. **Gates nativos no caminho de validators-vazios** (`run_scope :359-392`
   early-return). Hoje os gates acompanham a cascade; rodar gate nativo mesmo sem
   validators registrados exigiria mexer no early-return.
4. **Múltiplos builds** (android + ios no mesmo verify). Nível 1 roda só o
   primeiro buildable que resolver.
5. **detekt/swiftlint** (Níveis 2/3 das specs irmãs) — só após o build+ktlint
   provarem valor no re-piloto MeoBonsai.

---

## 3. Cadência por task (loop da campanha)

Para A1 e depois A2, em série no checkout principal:

plano → **plan-auditor** (12 checks) → dispatch impl (`gsd-executor`, TDD,
`.venv/bin/pytest` canônico) → review (`gsd-code-reviewer`, zero-tolerância, 11
dimensões + Caminho A/B/C por finding) → fix (`gsd-code-fixer`) → re-review → fix
→ auditoria final (READY_TO_MERGE) → fix se preciso → checkpoint (commit na branch
de campanha `feat/aifirst-pendencias` + doc-sync no mesmo commit). Cap de 3
rodadas de review; rodada 4 → ESCALATE ao usuário.

**Gates de "pronto" por task:** `.venv/bin/pytest` verde (lane rápida no loop;
full-lane antes do PR final, pois `verify` foi tocado) + `forge verify` sem hard
fail + reviewer assinou (sem high/critical) + doc-sync no mesmo commit. Count de
testes não regride sem justificativa no commit body.

---

## 4. Self-review (feito antes de commitar este plano)

- **Spec coverage:** A1 (native gate ktlint via `./gradlew ktlintCheck`,
  informativo, skip-se-ausente, degraded) + A2 (build-only android/kmp/ios,
  reusa o step, escreve artefatos documentado) cobrem **exatamente** o Track A da
  spec da campanha §Fase 1 + o Caminho A da native-gates §1/6 + o Caminho A
  build-only da runtime-visual §5. B/C/D fora — confirmado.
- **Placeholder scan:** zero `TBD`/`stub`/`...`/`v1`/`placeholder` — todo step tem
  código completo, comando de verify exato e critério de done.
- **Type consistency:** `_run_native_gates(config, project_root, *, interactive) -> list[_ValidatorResult]`
  bate entre §1, A1 Step 2, A2 Step 2 e todos os testes (sempre `interactive=False`
  nos testes unitários do step; `run_scope` passa `interactive=interactive`).
  `_map_external_result(res, *, gate_name, fail_on_violation) -> _ValidatorResult`
  bate entre A1 e A2 (A2 só muda `gate_name="build"`). `_build_candidates(platform)
  -> list[list[str] | str]` e `_ktlint_candidates(config, project_root)` batem com
  o que `resolve_invocation` espera (`list[list[str] | str]`). Mapping
  `_EXTERNAL_STATUS_MAP` (pass→pass, fail→warn, degraded→degraded) consistente em
  todos os testes. Ajuste de coerência: `_gate_timeout(config, gate, *, default=120)`
  com o call-site do build passando `default=600` (anotado em A2 Step 2).
