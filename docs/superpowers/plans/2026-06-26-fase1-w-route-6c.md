# W-ROUTE 6c — `mem find` reads (4 handlers) + orphan-cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dois entregáveis: (1) inserir `mem find` reads em `plan`/`implement`/`verify`/`qa`
(handler-only, degrade-soft, consumidor real por handler) e (2) remover o código de escrita L2
que 6b deixou órfão (`_apply_consolidate_l2`, import de `add_entry` em distiller, e
`l2.add_entry` + `__all__`-entry em l2.py, após sweep confirmar zero caller).

**Architecture:** Um helper compartilhado `mem_context_hint(project_root, query, *, limit)
-> str | None` é extraído em `engine/integrations/mem.py` (reusa `mem_find` de 6a, degrade
soft retornando None, formata resultado pra text block). Os 4 handlers COMPÕEM sobre esse
helper em vez de duplicar read+degrade+format 4×. O helper só formata — não decide o
consumidor: `plan`/`implement`/`qa` injetam a string no context-pack/handoff; `verify` a
renderiza como hint antes de `_run_cascade`. Determinismo garantido por teste estático: zero
validator importa `engine.integrations.mem` ou chama `mem_*`.

**Tech Stack:** Python 3, `engine/integrations/mem.py` (`mem_find` de 6a), pytest.

---

## Global Constraints

- Branch: `feat/mem-integration` — acumula, NÃO cria branch nova, UM PR no fim da Fase 1.
- Test runner canônico: `.venv/bin/pytest` (tem json5 + deps; system pytest dá false-fail).
- Reads são handler-only: `engine/plan.py`, `engine/implement.py`, `engine/verify.py`,
  `engine/qa/__init__.py`. Validators (`validators/`) NUNCA importam nem chamam mem — o
  determinismo é enforçado por teste estático (Task 3).
- Degrade soft: `mem_context_hint` retorna `None` quando mem ausente. Handler omite o
  hint/bloco silenciosamente — sem crash, sem "forge init" nag (o `_degraded_message`
  do mem NÃO é surfado ao usuário por estes reads).
- Reuso (Mandamento #3): helper compartilhado `mem_context_hint` (em
  `engine/integrations/mem.py`) compõe sobre `mem_find` existente de 6a — zero wrapper
  novo avulso, zero duplicação de lógica de read+degrade+format em 4 módulos distintos.
- Full-lane incl. `RUN_E2E=1` no gate de "pronto" (lição 6b: lanes env-gated escondem
  regressão).
- Real-mem read test (lição MOCK-BLINDNESS): Task 1 inclui ≥1 teste de `mem_context_hint`
  contra o binário vendorizado REAL (sem mock) — confirma que o find roda e o resultado é
  consumível.
- Voz mentor-calmo em toda string user-facing. Sem emoji decorativo em docstrings.
- `git add` com paths explícitos (nunca `git add .` nem `git add -A`).

---

## Decisão: helper compartilhado vs. duplicação inline

Cada handler precisa de: chamar `mem_find`, degradar soft (retornar sem crash se ausente),
formatar a lista de hits em texto compacto. Os 4 consumidores usam o mesmo formato de saída
(texto plano truncado pra context-pack/handoff/hint). Extrair `mem_context_hint` em
`engine/integrations/mem.py` é o melhor reuso (Mandamento #3): zero duplicação, um ponto de
mudança de formato, teste único do helper. Justificativa pra NÃO duplicar: os 3 alternativas
(inline em cada handler, util separado, helper em mem.py) diferem só no local — o formato e
a lógica de degrade são idênticos nos 4. O helper em mem.py é preferível porque a camada de
integração já contém a lógica de degrade (`_run_or_degrade`) e é o local natural pra
wrappers de alto nível sobre o binário.

---

### Task 1: helper `mem_context_hint` + read em `plan` (prova do padrão + real-mem test)

**Files:**
- Modify: `engine/integrations/mem.py` (adiciona `mem_context_hint` ao fim)
- Modify: `engine/plan.py` (adiciona import + read antes de `_run_static_wave("A", ...)`)
- Test: `tests/integrations/test_mem_wrappers.py` (adiciona testes de `mem_context_hint`)
- Test: `tests/unit/test_commands_plan.py` (adiciona testes do read em plan)

**Interfaces:**
- Consumes: `mem_find(project_root, query, *, limit=10, mem_type=None) -> MemQuery` (6a,
  já em `engine/integrations/mem.py`).
- Produces:
  ```python
  mem_context_hint(
      project_root: Path,
      query: str,
      *,
      limit: int = 5,
  ) -> str | None
  ```
  Retorna `None` em degrade (mem ausente/timeout/erro) ou quando lista vazia. Quando há
  hits, retorna um bloco de texto compacto com os N primeiros resultados formatados pra
  context-pack. Nunca propaga exceção.

**Reuso (Mandamento #3):** `mem_context_hint` compõe sobre `mem_find` de 6a, seguindo o
padrão verbatim dos wrappers existentes (usa `_run_or_degrade` via `mem_find`, não chama
subprocess diretamente). O helper vive em `engine/integrations/mem.py` junto dos outros
wrappers. O read em `engine/plan.py` COMPÕE sobre esse helper — nenhum import adicional de
subprocess nem de `_run_or_degrade` diretamente em plan.py.

- [ ] **Step 1: Escrever os testes (falhando)**

Adicione ao FINAL de `tests/integrations/test_mem_wrappers.py` (preserve todo o
conteúdo existente — não redefina os helpers `_stub`, `_Fake`, `_patch_run`):

```python
# ── Task 1 (6c): mem_context_hint ────────────────────────────────────────────


def test_mem_context_hint_formats_hits(tmp_path, monkeypatch):
    """Quando mem_find retorna hits, formata texto compacto não-None."""
    from engine.integrations import mem

    _stub(tmp_path / ".claude" / "bin" / "mem")
    _patch_run(
        monkeypatch,
        0,
        stdout='[{"id":"X1","score":0.9,"type":"feedback","title":"use-stateflow","author":"a"},'
               '{"id":"X2","score":0.7,"type":"reference","title":"mvvm-pattern","author":"b"}]',
    )
    result = mem.mem_context_hint(tmp_path, "pattern de arquitetura", limit=5)
    assert result is not None
    assert "use-stateflow" in result
    assert "mvvm-pattern" in result


def test_mem_context_hint_returns_none_on_empty_hits(tmp_path, monkeypatch):
    """Lista vazia → None (sem bloco em branco no context-pack)."""
    from engine.integrations import mem

    _stub(tmp_path / ".claude" / "bin" / "mem")
    _patch_run(monkeypatch, 0, stdout="[]")
    result = mem.mem_context_hint(tmp_path, "qualquer coisa", limit=5)
    assert result is None


def test_mem_context_hint_degrades_soft_when_binary_missing(tmp_path, monkeypatch):
    """Binário ausente → None sem crash, sem propagação de exceção."""
    from engine.integrations import mem

    monkeypatch.setattr(mem.shutil, "which", lambda _t: None)
    result = mem.mem_context_hint(tmp_path, "query", limit=5)
    assert result is None


def test_mem_context_hint_degrades_soft_on_error_exit(tmp_path, monkeypatch):
    """Exit não-zero → None sem crash."""
    from engine.integrations import mem

    _stub(tmp_path / ".claude" / "bin" / "mem")
    _patch_run(monkeypatch, 1, stdout="", stderr="erro interno")
    result = mem.mem_context_hint(tmp_path, "query", limit=5)
    assert result is None


def test_mem_context_hint_respects_limit(tmp_path, monkeypatch):
    """O argv enviado ao mem inclui -k <limit> correto."""
    from engine.integrations import mem

    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(
        monkeypatch,
        0,
        stdout='[{"id":"Y","score":0.8,"type":"reference","title":"t","author":"a"}]',
    )
    mem.mem_context_hint(tmp_path, "minha query", limit=3)
    cmd = cap["cmd"]
    # Deve delegar pra mem_find que monta: --json find <query> -k <limit>
    assert "find" in cmd
    assert "-k" in cmd and cmd[cmd.index("-k") + 1] == "3"


# ── Teste real-mem (MOCK-BLINDNESS): mem_context_hint contra binário real ─────


import os as _os


@pytest.mark.skipif(
    not (
        _os.path.isfile(
            str(Path(__file__).resolve().parents[2] / ".claude" / "bin" / "mem")
        )
    ),
    reason="binário mem vendorizado não encontrado — pule em CI sem vendorização",
)
def test_mem_context_hint_real_mem_returns_str_or_none(tmp_path):
    """Teste real-mem: mem_context_hint contra o binário vendorizado do repo.

    Copia o binário pra tmp_path/.claude/bin/mem (banco isolado).
    A query pode não ter hits no banco vazio — o invariante é:
    retorna str ou None sem crash, sem exceção.
    """
    import shutil as _shutil
    from engine.integrations import mem

    repo_root = Path(__file__).resolve().parents[2]
    src_bin = repo_root / ".claude" / "bin" / "mem"
    dest_bin = tmp_path / ".claude" / "bin" / "mem"
    dest_bin.parent.mkdir(parents=True, exist_ok=True)
    _shutil.copy2(str(src_bin), str(dest_bin))
    dest_bin.chmod(0o755)

    result = mem.mem_context_hint(tmp_path, "padrão de arquitetura kotlin", limit=3)
    # Banco vazio → None; banco com hits → str com títulos.
    assert result is None or isinstance(result, str)
    if isinstance(result, str):
        # Se retornou algo, deve ser não-vazio e não um dump de erro.
        assert len(result.strip()) > 0
```

Adicione ao FINAL de `tests/unit/test_commands_plan.py`:

```python
# ── Task 1 (6c): read em plan + degrade-soft ──────────────────────────────────


def test_plan_imports_mem_context_hint() -> None:
    """engine.plan importa mem_context_hint sem erro de import."""
    from engine import plan
    from engine.integrations.mem import mem_context_hint
    # Basta importar sem exceção — confirma que a dependência existe.
    assert callable(mem_context_hint)


def test_plan_run_degrades_soft_when_mem_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_project_root, capsys
) -> None:
    """plan.run com mem indisponível (binary missing) não crasha — degrade soft.

    Stubamos mem_context_hint pra retornar None (degrade), depois rodamos
    plan.run em projeto sem .claude/ pra confirmar que o comportamento de
    'project not found' ainda é o que vence (não um crash de mem).
    """
    import engine.plan as _plan
    from engine.integrations import mem as _mem

    monkeypatch.setattr(_mem, "mem_context_hint", lambda *a, **kw: None)
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("engine.ui.question.ask", lambda *a, **kw: "abort", raising=False)
    monkeypatch.setattr("engine.ui.question.ask_text", lambda *a, **kw: "", raising=False)
    monkeypatch.setattr("engine.ui.question.confirm", lambda *a, **kw: False, raising=False)
    try:
        rc = _plan.run([])
        assert rc in (1, 2)
    except SystemExit as exc:
        assert exc.code in (1, 2)
    # Nenhuma mensagem de erro de mem deve ter aparecido.
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "forge init" not in combined or ".claude" in combined  # OK se menciona .claude pra project-not-found
```

- [ ] **Step 2: Rodar pra confirmar que falham**

```bash
.venv/bin/pytest tests/integrations/test_mem_wrappers.py -v -k "context_hint"
.venv/bin/pytest tests/unit/test_commands_plan.py -v -k "mem_context_hint or degrades_soft"
```
Expected: FAIL (`AttributeError: module 'engine.integrations.mem' has no attribute 'mem_context_hint'`
para os testes do wrapper; o teste de plan pode PASS por não chamar plan.run até o import falhar).

- [ ] **Step 3: Implementar `mem_context_hint` em `engine/integrations/mem.py`**

Adicione ao FIM de `engine/integrations/mem.py` (após `mem_inbox_add`), preservando todo
o conteúdo existente intacto:

```python
def mem_context_hint(
    project_root: Path,
    query: str,
    *,
    limit: int = 5,
) -> str | None:
    """Consulta o acervo mem e formata resultado compacto pra context-pack/hint.

    Compõe sobre ``mem_find`` (de 6a) — sem subprocess novo, sem degrade própria.
    Retorna ``None`` em degrade (mem ausente, timeout, erro, lista vazia) pra que
    os callers omitam o bloco silenciosamente — sem crash, sem "forge init" nag.

    O formato de saída é texto plano multi-linha, adequado pra injeção direta em
    context-pack ou renderização como hint educacional:

        Memória relevante (mem find):
        · [feedback] use-stateflow — Use MutableStateFlow para screen state
        · [reference] mvvm-pattern — Padrão MVVM consistente nos ViewModels

    Args:
        project_root: raiz do projeto consumidor (resolve o binário vendorizado).
        query: termo de busca derivado do tema da feature/task.
        limit: máx. de hits a incluir no bloco (default 5 — bounded por design D1).

    Returns:
        Bloco de texto (str) quando há hits; ``None`` em degrade ou lista vazia.
    """
    res = mem_find(project_root, query, limit=limit)
    if not res.ok or not res.data:
        return None
    hits = res.data if isinstance(res.data, list) else []
    if not hits:
        return None
    lines: list[str] = ["Memória relevante (mem find):"]
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        kind = hit.get("type") or hit.get("kind") or "note"
        title = hit.get("title") or hit.get("id") or "?"
        lines.append(f"  · [{kind}] {title}")
    if len(lines) == 1:
        # Nenhum hit válido após parse.
        return None
    return "\n".join(lines)
```

- [ ] **Step 4: Adicionar import e read em `engine/plan.py`**

**4a.** Adicione o import de `mem_context_hint` ao bloco de imports existente no topo de
`engine/plan.py` (após `from engine.memory.l1 import (...)` e antes de
`from engine.persona import mentor_calmo`):

```python
from engine.integrations.mem import mem_context_hint
```

**4b.** Localize a função `run` em `engine/plan.py` (~L2051). O ponto de inserção é
ANTES de `_run_waves_for_subtype(...)` (~L2052) — após `starting_wave` ser determinada
e `intake_tokens` ser montado, mas antes das waves serem disparadas. Adicione o read de
`mem_context_hint` logo após a linha `intake_tokens.update({...})` (~L2043):

O trecho existente relevante (linhas ~L2043–2053 em `engine/plan.py`):
```python
    intake_tokens.update(
        {
            "{{screenshots_count}}": _ss_count,
            "{{screenshots_relative_paths_csv}}": _ss_paths,
            "{{screenshots_relative_paths_csv_or_none}}": _ss_paths,
        }
    )

    # Wave dispatch loop (subtype-aware; bugfix branches on wave_b_required).
    try:
        rc = _run_waves_for_subtype(
```

Insira entre o `intake_tokens.update(...)` e o `# Wave dispatch loop`:

```python
    # W-ROUTE 6c: consulta o acervo de memória por gotchas/convenções relevantes
    # ANTES de redigir os artefatos. O resultado alimenta o context-pack que o
    # subagente de planejamento recebe (token {{mem_context_hint}}). Degrade soft:
    # mem ausente → hint é None → token fica em branco (sem nag "forge init").
    _mem_hint = mem_context_hint(project_root, slug, limit=5)
    if _mem_hint is not None:
        intake_tokens["{{mem_context_hint}}"] = _mem_hint
    else:
        intake_tokens.setdefault("{{mem_context_hint}}", "")
```

- [ ] **Step 5: Rodar pra confirmar verde**

```bash
.venv/bin/pytest tests/integrations/test_mem_wrappers.py -v
```
Expected: PASS (todos os testes do arquivo — os da 6a + os de inbox_add de 6b + os novos
de context_hint). O `test_mem_context_hint_real_mem_returns_str_or_none` pode ser SKIPPED
em ambientes sem o vendorizado.

```bash
.venv/bin/pytest tests/unit/test_commands_plan.py -v
```
Expected: PASS (todos).

Lane rápida completa:
```bash
.venv/bin/pytest -m "not integration and not e2e" -q | tail -3
```
Expected: verde sem regressão.

- [ ] **Step 6: Commit**

```bash
git add engine/integrations/mem.py engine/plan.py tests/integrations/test_mem_wrappers.py tests/unit/test_commands_plan.py
git commit -m "feat(mem): mem_context_hint helper + read em plan (6c Task 1)

W-ROUTE 6c Task 1. Helper mem_context_hint em engine/integrations/mem.py:
compõe sobre mem_find de 6a, retorna str|None (degrade soft silencioso).
engine/plan.py: import + read antes de _run_waves_for_subtype; resultado
injetado em intake_tokens['{{mem_context_hint}}'] pra context-pack do
subagente de planejamento. Degrade: mem ausente → token vazio, sem crash,
sem nag forge-init. Real-mem test: test_mem_context_hint_real_mem_returns_str_or_none
(SKIPPED sem vendorizado). Testes de mock: argv correto, None em vazio/degrade."
```

---

### Task 2: reads em `implement` e `qa` (context-pack / handoff JSON)

**Files:**
- Modify: `engine/implement.py` (import + read antes de `_print_plan_mode`)
- Modify: `engine/qa/__init__.py` (import + read antes de `_write_conductor_handoff`)
- Test: `tests/unit/test_commands_implement.py` (adiciona testes do read + degrade)
- Test: `tests/engine/qa/test_run_qa_synthesis.py` OU novo arquivo
  `tests/engine/qa/test_run_qa_mem_hint.py` (testes do read em qa + degrade)

**Interfaces:**
- Consumes: `mem_context_hint(project_root, query, *, limit) -> str | None` (Task 1).
- Produces:
  - `implement._print_plan_mode`: antes de renderizar Plan Mode, lê
    `mem_context_hint(project_root, slug_como_query)` e renderiza o bloco como
    seção "Memória relevante" no context-pack exibido ao host (parte do
    `_print_plan_mode` output antes do `forge implement {slug}` confirm).
  - `qa.run_qa`: antes de `_write_conductor_handoff`, lê
    `mem_context_hint(project_root, scope.target)` e injeta o resultado em
    `handoff["mem_context"]` (novo campo no handoff JSON). Degrade → campo ausente
    ou `None` no JSON (sem crash).

**Ponto de inserção em `engine/implement.py` (`_print_plan_mode`, ~L458):**

O código atual de `_print_plan_mode` (linhas ~L458–L499):
```python
def _print_plan_mode(task: TaskContract, project_root: Path) -> None:
    renderer.write("")
    renderer.write(renderer.bold(f"📋 Plan Mode · {task.task_id}"))
    renderer.write("")
    if task.description:
        renderer.write(f"  {task.description}")
        renderer.write("")
    # ... (allowed_files, bdd_scenarios, validations, gates)
```

O consumidor do resultado em `implement` é o context-pack que o host (Claude Code) vê na
tela de Plan Mode — o hint é renderizado como bloco informativo antes do prompt de
confirmação. A query é o `task.description` (tema da task atual, mais específico que o slug).

**Ponto de inserção em `engine/qa/__init__.py` (`run_qa`, ~L337):**

O trecho atual de `run_qa` onde o handoff é montado (linhas ~L337–L344):
```python
        _write_conductor_handoff(
            scope,
            run_tree,
            cfg,
            allowed_extras=allowed_extras,
            snapshot_paths=snapshot_copied,
            workflow_config=workflow_config,
        )
```

O `mem_context_hint` é chamado ANTES desse bloco, com `scope.target` como query, e o
resultado é injetado em `_write_conductor_handoff` via um parâmetro opcional `mem_context`.
A função `_write_conductor_handoff` adiciona `"mem_context": mem_context` ao handoff JSON.

- [ ] **Step 1: Escrever os testes (falhando)**

Adicione ao FINAL de `tests/unit/test_commands_implement.py`:

```python
# ── Task 2 (6c): read em implement + degrade-soft ─────────────────────────────


def test_implement_imports_mem_context_hint() -> None:
    """engine.implement importa mem_context_hint sem erro de import."""
    from engine import implement
    from engine.integrations.mem import mem_context_hint
    assert callable(mem_context_hint)


def test_implement_run_degrades_soft_when_mem_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_project_root, capsys
) -> None:
    """implement.run com mem indisponível não crasha — degrade soft."""
    import engine.implement as _impl
    from engine.integrations import mem as _mem

    monkeypatch.setattr(_mem, "mem_context_hint", lambda *a, **kw: None)
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("engine.ui.question.ask", lambda *a, **kw: "abort", raising=False)
    monkeypatch.setattr("engine.ui.question.ask_text", lambda *a, **kw: "", raising=False)
    monkeypatch.setattr("engine.ui.question.confirm", lambda *a, **kw: False, raising=False)
    try:
        rc = _impl.run([])
        assert rc in (1, 2)
    except SystemExit as exc:
        assert exc.code in (1, 2)
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    # Nenhum traceback de mem deve aparecer.
    assert "mem_context_hint" not in combined or "forge init" not in combined
```

Crie `tests/engine/qa/test_run_qa_mem_hint.py`:

```python
"""Testes do read de mem_context_hint em engine.qa.run_qa (W-ROUTE 6c Task 2)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def _make_minimal_workflow_config() -> dict[str, Any]:
    return {"qa": {"enabled": True}}


def test_run_qa_injects_mem_context_in_handoff(tmp_path, monkeypatch):
    """run_qa injeta mem_context_hint no handoff JSON quando mem disponível."""
    import engine.qa as _qa
    from engine.integrations import mem as _mem

    # Stuba mem_context_hint pra retornar um bloco known.
    monkeypatch.setattr(
        _mem, "mem_context_hint",
        lambda root, query, **kw: "Memória relevante (mem find):\n  · [feedback] padrão-mvvm",
    )

    # Stuba as partes de I/O de run_qa que precisariam de infra real.
    # Resolve scope → fake scope com target.
    class _FakeScope:
        type = "feature"
        target = "minha-feature"
        paths: list = []

    class _FakeRunTree:
        run_id = "run-test-01"
        root = tmp_path / "run-01"
        snapshot_dir = tmp_path / "run-01" / "snapshot"

    fake_scope = _FakeScope()
    fake_tree = _FakeRunTree()
    fake_tree.root.mkdir(parents=True, exist_ok=True)
    fake_tree.snapshot_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(_qa, "resolve_scope", lambda *a, **kw: fake_scope)
    monkeypatch.setattr(_qa, "find_resumable_run", lambda *a, **kw: None)
    monkeypatch.setattr(_qa, "create_run_tree", lambda *a, **kw: fake_tree)
    monkeypatch.setattr(_qa, "snapshot_artefacts", lambda *a, **kw: [])
    monkeypatch.setattr(_qa, "_write_qa_report_skeleton", lambda *a, **kw: None)
    monkeypatch.setattr(_qa, "_maybe_alert_sensitive_drops", lambda *a, **kw: None)
    monkeypatch.setattr(_qa, "_compute_allowed_extras", lambda *a, **kw: ())
    # Roda run_qa; captura o handoff escrito.
    import json

    _qa.run_qa(
        "minha-feature",
        project_root=tmp_path,
        workflow_config=_make_minimal_workflow_config(),
    )

    handoff_path = fake_tree.root / "conductor-handoff.json"
    assert handoff_path.exists(), "conductor-handoff.json não foi escrito"
    handoff = json.loads(handoff_path.read_text())
    assert "mem_context" in handoff, "campo mem_context ausente no handoff"
    assert "padrão-mvvm" in (handoff["mem_context"] or "")


def test_run_qa_handoff_sem_mem_context_quando_degrade(tmp_path, monkeypatch):
    """run_qa com mem indisponível: campo mem_context ausente ou None, sem crash."""
    import engine.qa as _qa
    from engine.integrations import mem as _mem

    monkeypatch.setattr(_mem, "mem_context_hint", lambda *a, **kw: None)

    class _FakeScope:
        type = "feature"
        target = "feature-sem-mem"
        paths: list = []

    class _FakeRunTree:
        run_id = "run-test-02"
        root = tmp_path / "run-02"
        snapshot_dir = tmp_path / "run-02" / "snapshot"

    fake_scope = _FakeScope()
    fake_tree = _FakeRunTree()
    fake_tree.root.mkdir(parents=True, exist_ok=True)
    fake_tree.snapshot_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(_qa, "resolve_scope", lambda *a, **kw: fake_scope)
    monkeypatch.setattr(_qa, "find_resumable_run", lambda *a, **kw: None)
    monkeypatch.setattr(_qa, "create_run_tree", lambda *a, **kw: fake_tree)
    monkeypatch.setattr(_qa, "snapshot_artefacts", lambda *a, **kw: [])
    monkeypatch.setattr(_qa, "_write_qa_report_skeleton", lambda *a, **kw: None)
    monkeypatch.setattr(_qa, "_maybe_alert_sensitive_drops", lambda *a, **kw: None)
    monkeypatch.setattr(_qa, "_compute_allowed_extras", lambda *a, **kw: ())

    import json

    _qa.run_qa(
        "feature-sem-mem",
        project_root=tmp_path,
        workflow_config=_make_minimal_workflow_config(),
    )

    handoff_path = fake_tree.root / "conductor-handoff.json"
    assert handoff_path.exists()
    handoff = json.loads(handoff_path.read_text())
    # Degrade: campo pode ser None ou ausente — nunca causa crash.
    mem_ctx = handoff.get("mem_context")
    assert mem_ctx is None or isinstance(mem_ctx, str)
```

- [ ] **Step 2: Rodar pra confirmar que falham**

```bash
.venv/bin/pytest tests/unit/test_commands_implement.py -v -k "mem_context_hint or degrades_soft"
.venv/bin/pytest tests/engine/qa/test_run_qa_mem_hint.py -v
```
Expected: FAIL (`AttributeError` ou `ImportError` para os que testam o read; o de qa pode
falhar porque `mem_context` não está no handoff ainda).

- [ ] **Step 3: Implementar o read em `engine/implement.py`**

**3a.** Adicione o import ao bloco de imports no topo de `engine/implement.py` (após
`from engine.utils.iso import utc_now_iso`):

```python
from engine.integrations.mem import mem_context_hint
```

**3b.** Localize `_print_plan_mode(task: TaskContract, project_root: Path)` (~L458).
Insira o bloco de read ANTES do primeiro `renderer.write("")` da função:

O código atual de `_print_plan_mode` começa com:
```python
def _print_plan_mode(task: TaskContract, project_root: Path) -> None:
    renderer.write("")
    renderer.write(renderer.bold(f"📋 Plan Mode · {task.task_id}"))
```

Substitua as 3 linhas iniciais por:
```python
def _print_plan_mode(task: TaskContract, project_root: Path) -> None:
    # W-ROUTE 6c: lê memória relevante antes de renderizar o Plan Mode.
    # O resultado alimenta o context-pack que o host vê na tela de confirmação.
    # Degrade soft: mem ausente → hint é None → bloco omitido silenciosamente.
    _hint = mem_context_hint(
        project_root, task.description or task.task_id, limit=5
    )
    renderer.write("")
    renderer.write(renderer.bold(f"📋 Plan Mode · {task.task_id}"))
```

Após `renderer.write("")` (a linha após o bold), insira o bloco de renderização do hint
(logo após `renderer.write(renderer.bold(...))`):

```python
    if _hint is not None:
        renderer.write("")
        renderer.write(renderer.dim(_hint))
```

A sequência completa das primeiras linhas de `_print_plan_mode` fica:
```python
def _print_plan_mode(task: TaskContract, project_root: Path) -> None:
    # W-ROUTE 6c: lê memória relevante antes de renderizar o Plan Mode.
    # O resultado alimenta o context-pack que o host vê na tela de confirmação.
    # Degrade soft: mem ausente → hint é None → bloco omitido silenciosamente.
    _hint = mem_context_hint(
        project_root, task.description or task.task_id, limit=5
    )
    renderer.write("")
    renderer.write(renderer.bold(f"📋 Plan Mode · {task.task_id}"))
    if _hint is not None:
        renderer.write("")
        renderer.write(renderer.dim(_hint))
    renderer.write("")
    if task.description:
        renderer.write(f"  {task.description}")
        renderer.write("")
    # ... (resto da função inalterado)
```

- [ ] **Step 4: Implementar o read em `engine/qa/__init__.py`**

**4a.** Adicione o import ao topo de `engine/qa/__init__.py` (junto dos imports de módulos
de engine — após `from engine.qa.scope import ...`):

```python
from engine.integrations.mem import mem_context_hint
```

**4b.** Localize `_write_conductor_handoff` (~L1409). Adicione `mem_context` como
parâmetro opcional ao final da assinatura:

```python
def _write_conductor_handoff(
    scope: Scope,
    run_tree: RunTree,
    cfg: QAConfig,
    *,
    allowed_extras: tuple[str, ...] = (),
    snapshot_paths: Iterable[Path] = (),
    workflow_config: dict[str, Any] | None = None,
    mem_context: str | None = None,
) -> None:
```

E adicione `"mem_context": mem_context` ao dict `handoff` (após `"config": {...}`):

```python
    handoff: dict[str, Any] = {
        "scope": {
            "type": scope.type,
            "target": scope.target,
            "paths": [str(p) for p in scope.paths],
        },
        "run_id": run_tree.run_id,
        "root": str(run_tree.root),
        "snapshot": snapshot_rel,
        "config_snapshot": config_snapshot,
        "auditors": auditors,
        "config": {
            "sandbox_budget_seconds_total": cfg.sandbox_budget_seconds_total,
            "agent_timeout_seconds": cfg.agent_timeout_seconds,
            "extensions_disabled": list(cfg.extensions_disabled),
            "allowed_env_extras": list(allowed_extras),
        },
        # W-ROUTE 6c: memória relevante pro conductor (mem find pré-audit).
        # None quando mem indisponível (degrade soft) — conductor ignora.
        "mem_context": mem_context,
    }
```

**4c.** No fluxo principal de `run_qa`, antes de CADA chamada a `_write_conductor_handoff`
(há 3 call-sites: ~L294/stale-cleanup, ~L337/fresh-run, e o branch de resume não cria
handoff novo — só os 2 fresh), leia o hint:

```python
        # W-ROUTE 6c: lê memória relevante antes de escrever o handoff.
        # Query = scope.target (slug/screen/task-id); degrade soft retorna None.
        _mem_ctx = mem_context_hint(project_root, scope.target, limit=5)
        _write_conductor_handoff(
            scope,
            run_tree,
            cfg,
            allowed_extras=allowed_extras,
            snapshot_paths=snapshot_copied,
            workflow_config=workflow_config,
            mem_context=_mem_ctx,
        )
```

Atenção: há dois pontos onde `_write_conductor_handoff` é chamado na branch de fresh-run
(~L294 stale-checkpoint cleanup e ~L337 fresh normal). Ambos recebem `mem_context=_mem_ctx`
(calculado com a mesma `scope.target` query — reusar o valor ou recalcular por call-site
é indiferente, mas calcular uma vez antes do if/else é mais legível).

- [ ] **Step 5: Rodar pra confirmar verde**

```bash
.venv/bin/pytest tests/unit/test_commands_implement.py tests/engine/qa/test_run_qa_mem_hint.py -v
```
Expected: PASS (todos). Em seguida lane rápida:

```bash
.venv/bin/pytest -m "not integration and not e2e" -q | tail -3
```
Expected: verde sem regressão.

- [ ] **Step 6: Commit**

```bash
git add engine/implement.py engine/qa/__init__.py tests/unit/test_commands_implement.py tests/engine/qa/test_run_qa_mem_hint.py
git commit -m "feat(implement,qa): mem_context_hint reads em implement/_print_plan_mode + qa/handoff (6c Task 2)

W-ROUTE 6c Task 2. engine/implement.py: import + read em _print_plan_mode
(antes do bold Plan Mode); resultado renderizado como renderer.dim(_hint)
se não-None. engine/qa/__init__.py: import + campo mem_context em
_write_conductor_handoff (parâmetro opcional); run_qa calcula
mem_context_hint(project_root, scope.target) e injeta em ambos call-sites
do handoff. Degrade soft: hint=None → bloco omitido / campo None no JSON,
sem crash, sem nag forge-init."
```

---

### Task 3: read em `verify` (hint pré-cascade) + teste de DETERMINISMO

**Files:**
- Modify: `engine/verify.py` (import + read + renderização antes de `_run_cascade`)
- Test: `tests/unit/test_commands_verify.py` (adiciona testes do read + degrade)
- Test: `tests/unit/test_validators_determinism.py` (NOVO — teste estático de determinismo)

**Interfaces:**
- Consumes: `mem_context_hint(project_root, query, *, limit) -> str | None` (Task 1).
- Produces:
  - `engine/verify.py`: antes de `results = _run_cascade(...)` (~L377), lê
    `mem_context_hint(project_root, feature_slug or scope_target, limit=5)` e renderiza
    como hint educacional se não-None (`renderer.write(renderer.dim(hint))`). O hint
    NÃO é passado como argumento pra `_run_cascade` — os validators não recebem
    contexto de mem (invariante de determinismo).
  - `tests/unit/test_validators_determinism.py`: teste estático que varre todos os
    arquivos Python em `validators/` e asserta que nenhum contém `engine.integrations.mem`
    nem chamadas a `mem_find`/`mem_context_hint`/`mem_call`/`mem_get`/`mem_stats`/
    `mem_brief`/`mem_evolve`/`mem_inbox_add`.

**Ponto de inserção em `engine/verify.py`:**

O trecho relevante (linhas ~L376–L384):
```python
    fail_fast = _resolve_fail_fast(config)
    results = _run_cascade(
        validators,
        fail_fast=fail_fast,
        project_root=project_root,
        interactive=interactive,
        scope_type=scope_type,
        scope_target=scope_target,
    )
```

Insira o read e render ANTES de `fail_fast = _resolve_fail_fast(config)`:

```python
    # W-ROUTE 6c: hint educacional pré-cascade — renderizado pro usuário ANTES
    # dos validators rodarem. NÃO passado pra _run_cascade (determinismo: validators
    # nunca recebem contexto de mem — invariante enforçado por test_validators_determinism).
    # Degrade soft: mem ausente → hint None → omitido silenciosamente, sem nag.
    if interactive:
        _hint_query = feature_slug or scope_target or scope_type
        _verify_hint = mem_context_hint(project_root, _hint_query, limit=5)
        if _verify_hint is not None:
            renderer.write("")
            renderer.write(renderer.dim(_verify_hint))
            renderer.write("")

    fail_fast = _resolve_fail_fast(config)
    results = _run_cascade(
```

O hint só é exibido em modo interativo (`if interactive:`) — em modo JSON (`--json`) não
faz sentido poluir o stdout com texto livre.

- [ ] **Step 1: Escrever os testes (falhando)**

Adicione ao FINAL de `tests/unit/test_commands_verify.py`:

```python
# ── Task 3 (6c): read em verify + degrade-soft ────────────────────────────────


def test_verify_imports_mem_context_hint() -> None:
    """engine.verify importa mem_context_hint sem erro de import."""
    from engine import verify
    from engine.integrations.mem import mem_context_hint
    assert callable(mem_context_hint)


def test_verify_run_degrades_soft_when_mem_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_project_root, capsys
) -> None:
    """verify.run com mem indisponível não crasha — degrade soft."""
    import engine.verify as _verify
    from engine.integrations import mem as _mem

    monkeypatch.setattr(_mem, "mem_context_hint", lambda *a, **kw: None)
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("engine.ui.question.ask", lambda *a, **kw: "abort", raising=False)
    monkeypatch.setattr("engine.ui.question.ask_text", lambda *a, **kw: "", raising=False)
    monkeypatch.setattr("engine.ui.question.confirm", lambda *a, **kw: False, raising=False)
    try:
        rc = _verify.run([])
        assert rc in (1, 2)
    except SystemExit as exc:
        assert exc.code in (1, 2)
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "mem_context_hint" not in combined
```

Crie `tests/unit/test_validators_determinism.py`:

```python
"""Teste estático de determinismo: validators nunca importam engine.integrations.mem.

W-ROUTE 6c — invariante de determinismo (D1): validators/ são unidades read-only
determinísticas. Memória contextual (mem find) alimenta APENAS os handlers
(plan/implement/verify/qa) como hint educacional, jamais como input de decisão
num validator — isso contaminaria a natureza determinística do cascade.

Este teste é estático: varre o source text dos validators em validators/ e asserta
que nenhum módulo importa ou chama funções do substrato mem.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

# Raiz do repo: dois níveis acima de tests/unit/.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATORS_DIR = _REPO_ROOT / "validators"

# Padrões proibidos: nomes de módulos e funções do substrato mem.
_FORBIDDEN_IMPORTS = {"engine.integrations.mem", "engine.integrations"}
_FORBIDDEN_NAMES = {
    "mem_find",
    "mem_context_hint",
    "mem_call",
    "mem_get",
    "mem_stats",
    "mem_brief",
    "mem_evolve",
    "mem_inbox_add",
    "MemQuery",
    "MemResult",
    "mem_context_hint",
}


def _collect_validator_sources() -> list[Path]:
    """Retorna todos os .py de validators/ exceto __init__ e _common/_diff/_gate_infra."""
    return sorted(
        p for p in _VALIDATORS_DIR.glob("*.py")
        if p.name not in {"__init__.py"}
    )


def _check_source(path: Path) -> list[str]:
    """Retorna lista de violações encontradas no arquivo (vazia se ok)."""
    violations: list[str] = []
    source = path.read_text(encoding="utf-8")

    # Parse AST pra detecção estrutural (import statements).
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        violations.append(f"SyntaxError ao parsear: {exc}")
        return violations

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                # from engine.integrations.mem import ...
                # from engine.integrations import mem
                if any(
                    node.module == forbidden or node.module.startswith(f"{forbidden}.")
                    for forbidden in _FORBIDDEN_IMPORTS
                ):
                    violations.append(
                        f"L{node.lineno}: import proibido 'from {node.module} import ...'"
                    )
                # Verifica se os nomes importados são funções do mem.
                for alias in node.names:
                    if alias.name in _FORBIDDEN_NAMES:
                        violations.append(
                            f"L{node.lineno}: import de função mem proibida: '{alias.name}'"
                        )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(
                        alias.name == forbidden or alias.name.startswith(f"{forbidden}.")
                        for forbidden in _FORBIDDEN_IMPORTS
                    ):
                        violations.append(
                            f"L{node.lineno}: import proibido 'import {alias.name}'"
                        )

        # Detecção de chamadas diretas por nome (ex: mem_find(...) com import * hipotético).
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_NAMES:
                violations.append(
                    f"L{node.lineno}: chamada direta a função mem proibida: '{func.id}()'"
                )
            if isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_NAMES:
                violations.append(
                    f"L{node.lineno}: chamada a atributo mem proibido: '.{func.attr}()'"
                )

    return violations


@pytest.mark.parametrize(
    "validator_path",
    _collect_validator_sources(),
    ids=lambda p: p.name,
)
def test_validator_does_not_import_mem(validator_path: Path) -> None:
    """Nenhum validator deve importar ou chamar funções de engine.integrations.mem.

    Falha com a lista de violações encontradas pra facilitar o diagnóstico.
    """
    violations = _check_source(validator_path)
    assert not violations, (
        f"Validator '{validator_path.name}' viola o invariante de determinismo (W-ROUTE 6c):\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nValidators são determinísticos e não recebem contexto de mem. "
        "Moves de lógica de mem pra validators quebram a arquitetura — "
        "use os handlers (plan/implement/verify/qa) como ponto de injeção."
    )
```

- [ ] **Step 2: Rodar pra confirmar que falham**

```bash
.venv/bin/pytest tests/unit/test_validators_determinism.py -v
.venv/bin/pytest tests/unit/test_commands_verify.py -v -k "mem_context_hint or degrades_soft"
```
Expected para determinism: PASS (nenhum validator importa mem hoje — o teste confirma o
estado atual e vira regression guard). Expected para verify: FAIL (`AttributeError` no
import de `mem_context_hint` em `engine.verify`).

- [ ] **Step 3: Implementar o read em `engine/verify.py`**

**3a.** Adicione o import ao topo de `engine/verify.py` (após `from engine.persona import
mentor_calmo`):

```python
from engine.integrations.mem import mem_context_hint
```

**3b.** Localize o bloco antes de `fail_fast = _resolve_fail_fast(config)` (~L376) e
insira:

```python
    # W-ROUTE 6c: hint educacional pré-cascade — renderizado pro usuário ANTES
    # dos validators rodarem. NÃO passado pra _run_cascade (determinismo: validators
    # nunca recebem contexto de mem — invariante enforçado por test_validators_determinism).
    # Degrade soft: mem ausente → hint None → omitido silenciosamente, sem nag.
    if interactive:
        _hint_query = feature_slug or scope_target or scope_type
        _verify_hint = mem_context_hint(project_root, _hint_query, limit=5)
        if _verify_hint is not None:
            renderer.write("")
            renderer.write(renderer.dim(_verify_hint))
            renderer.write("")

    fail_fast = _resolve_fail_fast(config)
```

- [ ] **Step 4: Rodar pra confirmar verde**

```bash
.venv/bin/pytest tests/unit/test_commands_verify.py tests/unit/test_validators_determinism.py -v
```
Expected: PASS (todos). Lane rápida:

```bash
.venv/bin/pytest -m "not integration and not e2e" -q | tail -3
```
Expected: verde.

- [ ] **Step 5: Commit**

```bash
git add engine/verify.py tests/unit/test_commands_verify.py tests/unit/test_validators_determinism.py
git commit -m "feat(verify): mem_context_hint hint pré-cascade + teste de determinismo validators (6c Task 3)

W-ROUTE 6c Task 3. engine/verify.py: import + read de mem_context_hint
antes de _run_cascade; renderizado como renderer.dim(_hint) em modo
interativo (omitido em --json). NÃO entra em _run_cascade — determinismo
preservado. tests/unit/test_validators_determinism.py: novo teste estático
parametrizado que varre todos os .py em validators/ e asserta ausência de
import/chamada a funções de engine.integrations.mem. Regression guard pra
o invariante handler-only (D1)."
```

---

### Task 4: orphan-cleanup (grep-confirm → deletar `_apply_consolidate_l2` + `add_entry` + imports)

**Files:**
- Modify: `engine/memory/distiller.py` (deleta `_apply_consolidate_l2` + import de
  `add_entry` + linha `_ = remove_entry` se ficar sem uso)
- Modify: `engine/memory/l2.py` (deleta `add_entry` + remove entrada em `__all__`)
- Modify: `tests/unit/test_memory_distiller.py` (reconcilia testes que testavam
  `_apply_consolidate_l2` diretamente, se existirem)
- Modify: `tests/unit/test_memory_l2.py` (reconcilia testes de `add_entry` se precisar)
- Modify: `docs/design/04-pending.md` (resolve as entradas de órfão de 6b)

**Interfaces:**
- Consumes: grep de zero caller confirmado em Step 1 (pré-condição obrigatória antes de
  deletar).
- Produces: `distiller.py` sem `_apply_consolidate_l2` e sem import de `add_entry`;
  `l2.py` sem `add_entry` e sem a entrada em `__all__`; `04-pending.md` com as entradas
  de 6b sobre `l2.add_entry` e `_apply_consolidate_l2` marcadas como resolvidas (removidas).

**FICAM (não tocar — território de 6d/W-MIGRATE):**
- `remove_entry` em `l2.py` — `engine/undo.py:372` ainda usa.
- `write_l2`, `read_l2`, `export_for_context_pack` em `l2.py` — migrador W-MIGRATE lê L2.
- `apply_proposal_to_l2` — misnomer anotado em 04-pending; rename é 6d/posterior.

- [ ] **Step 1: Grep-confirm zero caller (pré-condição obrigatória)**

Execute os greps abaixo e registre os resultados antes de deletar qualquer código. Se
algum grep retornar caller fora dos arquivos listados, PARE e reporte (não delete):

```bash
# Zero caller de _apply_consolidate_l2 fora de distiller.py (exceto a própria definição)?
grep -rn "_apply_consolidate_l2" \
  /Users/thg.inchurch/Documents/feature-forge/ \
  --include="*.py" \
  | grep -v "\.venv" \
  | grep -v "__pycache__"
# Expected: apenas distiller.py linha de definição (def _apply_consolidate_l2).
# Se aparecer call-site em outro arquivo → PARE, reporte, não delete.

# Zero caller de add_entry via distiller (o import em distiller.py já é o único uso)?
grep -rn "add_entry" \
  /Users/thg.inchurch/Documents/feature-forge/ \
  --include="*.py" \
  | grep -v "\.venv" \
  | grep -v "__pycache__"
# Expected: distiller.py (import sem call-site de produção), l2.py (definição + __all__),
# tests/unit/test_memory_l2.py (testes diretos de l2.add_entry — FICAM).
# Se aparecer call-site em engine/ fora de distiller.py → PARE, reporte, não delete.
```

- [ ] **Step 2: Escrever os testes de cleanup (falhando)**

Adicione ao FINAL de `tests/unit/test_memory_distiller.py`:

```python
# ── Task 4 (6c): cleanup de órfãos ────────────────────────────────────────────


def test_apply_consolidate_l2_does_not_exist() -> None:
    """_apply_consolidate_l2 foi deletada em 6c — não deve existir mais."""
    import engine.memory.distiller as _dist
    assert not hasattr(_dist, "_apply_consolidate_l2"), (
        "_apply_consolidate_l2 ainda existe em distiller.py; "
        "deveria ter sido removida na Task 4 de 6c (W-ROUTE orphan-cleanup)."
    )


def test_distiller_does_not_import_add_entry() -> None:
    """distiller.py não deve importar add_entry de l2 (import órfão removido em 6c)."""
    import ast
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    distiller_src = (repo_root / "engine" / "memory" / "distiller.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(distiller_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "l2" in node.module:
                imported_names = [alias.name for alias in node.names]
                assert "add_entry" not in imported_names, (
                    f"distiller.py ainda importa 'add_entry' de l2 "
                    f"(linha {node.lineno}); deveria ter sido removido em 6c."
                )
```

Adicione ao FINAL de `tests/unit/test_memory_l2.py` (ou em arquivo separado se a
estrutura do conftest dificultar — confirme a fixture disponível antes):

```python
# ── Task 4 (6c): add_entry removido de l2.py ──────────────────────────────────


def test_l2_add_entry_removed_from_module() -> None:
    """add_entry foi deletada de engine.memory.l2 em 6c (write-path órfão).

    O write-path de conhecimento agora vai pro mem inbox (6b). l2.add_entry
    era o único caller de produção; após 6b nenhum engine code a chamava.
    """
    import engine.memory.l2 as _l2
    assert not hasattr(_l2, "add_entry"), (
        "add_entry ainda existe em engine.memory.l2; "
        "deveria ter sido removida na Task 4 de 6c (W-ROUTE orphan-cleanup)."
    )


def test_l2_add_entry_not_in_all() -> None:
    """add_entry não deve estar em __all__ de engine.memory.l2."""
    import engine.memory.l2 as _l2
    assert "add_entry" not in _l2.__all__, (
        "add_entry ainda está em l2.__all__; "
        "deveria ter sido removida junto com a função em 6c."
    )
```

- [ ] **Step 3: Rodar pra confirmar que falham**

```bash
.venv/bin/pytest tests/unit/test_memory_distiller.py -v -k "consolidate_l2_does_not_exist or does_not_import_add_entry"
.venv/bin/pytest tests/unit/test_memory_l2.py -v -k "add_entry_removed or not_in_all"
```
Expected: FAIL (`hasattr` retorna True pra `_apply_consolidate_l2`; `add_entry` existe).

- [ ] **Step 4: Deletar `_apply_consolidate_l2` e import de `add_entry` em `engine/memory/distiller.py`**

**4a.** Remova o import de `add_entry` do bloco `from engine.memory.l2 import (...)` (~L23):

O bloco atual de imports de l2 em `distiller.py`:
```python
from engine.memory.l2 import (
    L2Entry,
    add_entry,
    l2_overflow_check,
    read_l2,
    remove_entry,
    write_l2,
)
```

Substitua por (sem `add_entry` e sem `L2Entry` se ela só era usada em `_apply_consolidate_l2`
— verifique antes; `L2Entry` pode ter outros usos como type annotation):

```python
from engine.memory.l2 import (
    l2_overflow_check,
    read_l2,
    remove_entry,
    write_l2,
)
```

Atenção: `L2Entry` é usado em `_apply_consolidate_l2` (que será deletada) e possivelmente
em type annotations. Verifique com `grep -n "L2Entry" engine/memory/distiller.py` antes de
remover — se só aparecia na função deletada, remove; se há type annotation em outra função,
mantém.

**4b.** Delete a função `_apply_consolidate_l2` completa (~L543–L607 em distiller.py):

O início da função (verbatim):
```python
def _apply_consolidate_l2(
    project_root: Path,
    proposal: DistillationProposal,
) -> None:
    """Mescla entries L2 com mesmo `kind` cujo title sofre substring-match.
```

Delete da linha `def _apply_consolidate_l2(` até o fim do seu corpo (inclusive), antes de
`def _apply_forget_l1(`.

**4c.** Revise a linha `_ = remove_entry  # silenciar lint sobre import reservado` (~L639
em `_apply_forget_l1`). Essa linha existe pra silenciar lint sobre o import de `remove_entry`
que era reservado pra uso futuro. Como `remove_entry` agora é usada diretamente em
`apply_proposal_to_l2` (chamada via `remove_from_queue` que por sua vez usa `remove_entry`
internamente — verifique), a linha pode ser removida. Se `remove_entry` ainda precisar do
sentinela, deixe — mas confirme com grep:

```bash
grep -n "remove_entry\|remove_from_queue" /Users/thg.inchurch/Documents/feature-forge/engine/memory/distiller.py
```

Se `remove_entry` é importada mas nunca chamada diretamente (só via `remove_from_queue`),
o `_ = remove_entry` pode ser mantido ou removido (é lint-only). Se removido, remova também
`remove_entry` do bloco `from engine.memory.l2 import (...)`.

- [ ] **Step 5: Deletar `add_entry` e entrada em `__all__` em `engine/memory/l2.py`**

**5a.** Delete a função `add_entry` completa (~L435–L441):
```python
def add_entry(project_root: Path, entry: L2Entry) -> None:
    """Add a new entry. Fails (MemoryError) on duplicate id."""
    current = read_l2(project_root)
    if any(e.id == entry.id for e in current):
        raise MemoryError(f"L2 entry id already exists: {entry.id}")
    current.append(entry)
    write_l2(project_root, current, backup=True)
```

**5b.** Remova `"add_entry"` da lista `__all__` (~L504):
```python
__all__ = [
    "L2Entry",
    "read_l2",
    "write_l2",
    "add_entry",   # <- remover esta linha
    "remove_entry",
    ...
]
```

- [ ] **Step 6: Reconciliar o footprint de testes de `_apply_consolidate_l2` e `add_entry`**

Rode a lane pra identificar quais testes quebram:
```bash
.venv/bin/pytest tests/unit/test_memory_distiller.py tests/unit/test_memory_l2.py -v 2>&1 | tail -30
```

Para cada FAIL:
- Se o teste asserta a EXISTÊNCIA de `_apply_consolidate_l2` ou `add_entry` no sentido
  positivo (ex.: `assert hasattr(_dist, "_apply_consolidate_l2")` ou testa a função
  diretamente pelo caminho antigo) → DELETE o teste (era teste da função deletada).
- Se o teste asserta que `l2.add_entry` funciona pra escrever L2 diretamente (em
  `test_memory_l2.py`, `test_add_entry_succeeds_then_duplicate_fails`) → DELETE o teste
  (a função não existe mais; o novo caminho de escrita é via mem inbox).
- Se o teste testa outra coisa que incidentalmente usava `add_entry` como setup → ADAPTE
  o setup pra usar `write_l2` diretamente (que FICA).

**Importante:** `tests/unit/test_memory_l2.py` contém `test_add_entry_succeeds_then_duplicate_fails`
(~L57). Esse teste testa `l2.add_entry` diretamente — DELETE. Não substitua por um teste de
`mem_inbox_add` aqui (isso é coberto em `test_mem_wrappers.py` pela Task 1 de 6b).

- [ ] **Step 7: Atualizar `docs/design/04-pending.md`**

Localize as entradas de 6b sobre órfãos (~L67–L76) e marque como resolvidas em 6c:

As entradas atuais:
```markdown
- **`l2.add_entry` órfão-pra-conhecimento (W-ROUTE 6b)** — após 6b, os 3
  branches de L2-knowledge (`promote-to-l2`, `l1-to-l2-promotion`,
  `consolidate-l2`) param de chamar `l2.add_entry`. A função permanece no
  código (a leitura de L2 ainda serve ao migrador W-MIGRATE deferido e ao
  `forget-l1`); remoção do write-path órfão de conhecimento é candidata a 6c.

- **`apply_proposal_to_l2` misnomer (W-ROUTE 6b)** — o nome deixou de ser
  preciso: a função não escreve L2 para proposals de conhecimento. Mantido em
  6b pra conter footprint (rename ripplaria em callers/tests); candidato a
  rename num sweep posterior de limpeza semântica.
```

Substitua pelo bloco atualizado:

```markdown
- **`l2.add_entry` órfão-pra-conhecimento (W-ROUTE 6b)** — RESOLVIDO em 6c:
  `add_entry` deletada de `engine/memory/l2.py` (e de `__all__`) e import
  removido de `distiller.py`. Write-path órfão de conhecimento eliminado.

- **`apply_proposal_to_l2` misnomer (W-ROUTE 6b)** — PENDENTE: misnomer mantido.
  O rename ripplaria em callers/tests — candidato a sweep semântico posterior (6d+).
```

E a entrada de `_apply_consolidate_l2` (se houver entrada separada em 04-pending) ou
adicione como nota ao bloco §W-ROUTE 6b:

```markdown
- **`_apply_consolidate_l2` órfã (W-ROUTE 6c)** — RESOLVIDO em 6c: função
  deletada de `engine/memory/distiller.py`. O branch `consolidate-l2` já
  era roteado via `_KNOWLEDGE_KINDS → mem_inbox_add` desde 6b; a função era
  dead code confirmado por grep.
```

- [ ] **Step 8: Rodar pra confirmar verde**

```bash
.venv/bin/pytest tests/unit/test_memory_distiller.py tests/unit/test_memory_l2.py -v
```
Expected: PASS (todos — os de cleanup passam; os deletados não existem mais).

Lane rápida completa:
```bash
.venv/bin/pytest -m "not integration and not e2e" -q | tail -3
```
Expected: verde (count pode cair pelos testes deletados — isso é esperado e justificado no
commit body).

- [ ] **Step 9: Commit**

```bash
git add engine/memory/distiller.py engine/memory/l2.py tests/unit/test_memory_distiller.py tests/unit/test_memory_l2.py docs/design/04-pending.md
git commit -m "refactor(distiller,l2): orphan-cleanup _apply_consolidate_l2 + add_entry (6c Task 4)

W-ROUTE 6c Task 4. Grep confirmou zero caller de produção:

- engine/memory/distiller.py: remove import de add_entry (órfão desde 6b),
  deleta _apply_consolidate_l2 (dead-code: branch consolidate-l2 roteado
  via _KNOWLEDGE_KINDS → mem_inbox_add desde 6b).
- engine/memory/l2.py: deleta add_entry (write-path órfão de conhecimento)
  e remove entrada em __all__.
- Testes deletados: test_add_entry_succeeds_then_duplicate_fails (testa
  função inexistente); testes de _apply_consolidate_l2 via caminho direto
  (função inexistente). Os testes de 6b (mem_inbox_add como substituto)
  cobrem o novo contrato.
- 04-pending: entradas de l2.add_entry e _apply_consolidate_l2 marcadas
  como RESOLVIDO; misnomer apply_proposal_to_l2 permanece pendente (6d+).

FICAM: remove_entry, write_l2, read_l2 (undo.py + migrador W-MIGRATE)."
```

---

### Task 5: doc-sync (06-command-surface, CHANGELOG, guides)

**Files:**
- Modify: `docs/design/06-command-surface.md` (lê documentação de plan/implement/verify/qa
  e atualiza com comportamento de read)
- Modify: `CHANGELOG.md` (Unreleased)
- Modify: `docs/guides/daily-workflow.md` (se menciona plan/implement/verify sem o hint)

**Interfaces:**
- Consumes: superfície nova das Tasks 1–4.
- Produces: docs consistentes com os reads de 6c e o cleanup de órfãos.

- [ ] **Step 1: Varrer footprint de testes restante (pré-doc-sync)**

Antes de escrever docs, confirme que a lane integration também está verde:
```bash
.venv/bin/pytest -m "integration" -q | tail -3
```
Expected: verde (sem regressão de count nos testes de integração).

Se houver quebra, investigue e corrija antes de prosseguir.

- [ ] **Step 2: Atualizar `docs/design/06-command-surface.md`**

`06-command-surface.md` é doc load-bearing. A edição aqui é doc-sync do comportamento
observável (Mandamento #6) — sem cerimônia "Revisita decisão N" (nenhuma decisão de
`01-decisions.md` muda).

Localize as seções que descrevem `forge plan`, `forge implement`, `forge verify`, `forge qa`.
Para cada uma, adicione uma nota sobre o read de mem (se a seção descreve o comportamento do
handler):

```markdown
- `forge plan` (W-ROUTE 6c): antes de redigir os artefatos da Wave A, consulta
  `mem find` por gotchas/convenções relevantes ao slug da feature. O resultado é
  injetado no context-pack do subagente de planejamento via token
  `{{mem_context_hint}}`. Degrade soft: mem ausente → token vazio, sem crash.
- `forge implement` (W-ROUTE 6c): em Plan Mode, exibe memória relevante ao tema
  da task antes do prompt de confirmação. O host vê o hint educacional antes de
  aprovar o plano. Degrade soft: mem ausente → hint omitido.
- `forge verify` (W-ROUTE 6c): antes do cascade de validators, exibe hint educacional
  com memória relevante ao scope. Só em modo interativo (omitido em --json).
  O hint NÃO é passado pra validators — determinismo preservado.
- `forge qa` (W-ROUTE 6c): antes de escrever o conductor-handoff.json, consulta
  `mem find` com o scope target. O resultado é injetado em `handoff["mem_context"]`
  pro conductor auditor. Degrade soft: campo `None` no handoff, sem crash.
```

- [ ] **Step 3: Atualizar `CHANGELOG.md` (Unreleased)**

Adicione em `### Added`:

```markdown
- `mem_context_hint(project_root, query, *, limit) -> str | None` — helper
  compartilhado em `engine/integrations/mem.py`. Compõe sobre `mem_find` de 6a;
  retorna bloco de texto compacto com hits ou `None` em degrade (W-ROUTE 6c).
- `forge plan` / `implement` / `verify` / `qa`: leem `mem_context_hint` antes
  de agir; resultado alimenta context-pack/handoff/hint educacional por handler
  (D1 do design 6c). Handler-only: validators nunca recebem contexto de mem.
  Degrade soft em todos os handlers: mem ausente → sem crash, sem "forge init" nag.
- `tests/unit/test_validators_determinism.py`: teste estático parametrizado que
  garante que nenhum módulo em `validators/` importa ou chama funções de
  `engine.integrations.mem` (W-ROUTE 6c — invariante de determinismo).
```

Adicione em `### Removed`:

```markdown
- `engine/memory/distiller._apply_consolidate_l2` — dead code após 6b (branch
  `consolidate-l2` roteado via `_KNOWLEDGE_KINDS → mem_inbox_add`). Removido
  em 6c após grep-confirm de zero caller (W-ROUTE 6c orphan-cleanup).
- `engine/memory/l2.add_entry` — write-path órfão de conhecimento após 6b.
  Nenhum engine code chamava a função após o re-roteamento dos 3 branches de
  L2-knowledge pro mem inbox. Removida de `l2.py` e de `__all__` (W-ROUTE 6c).
- Import de `add_entry` em `engine/memory/distiller.py` — órfão correspondente.
```

- [ ] **Step 4: Atualizar `docs/guides/daily-workflow.md` (se aplicável)**

Leia a seção que descreve o uso de `forge plan` / `forge verify`. Se menciona que o forge
não usa contexto de memória ao planejar (ou se é omisso), adicione:

```markdown
Desde W-ROUTE 6c, os handlers consultam automaticamente o acervo de memória
(`mem find`) antes de agir: o `forge plan` injeta gotchas/convenções no
context-pack da Wave A; o `forge verify` exibe um hint educacional antes do
cascade. Sem intervenção do usuário — degrade soft quando mem ausente.
```

Se o guia não menciona isso, sem mudança (documente "sem alteração" no commit body).

- [ ] **Step 5: Full-lane final (incl. `RUN_E2E=1`)**

Rode as 3 lanes na ordem:
```bash
.venv/bin/pytest -m "not integration and not e2e" -q | tail -3
.venv/bin/pytest -m "integration" -q | tail -3
RUN_E2E=1 .venv/bin/pytest -m "e2e" -q | tail -3
```
Expected: verde nas 3. O `RUN_E2E=1` é obrigatório (lição 6b: a gate de e2e env-gated
esconde regressão que as outras lanes não veem).

- [ ] **Step 6: Commit**

```bash
git add docs/design/06-command-surface.md CHANGELOG.md docs/guides/daily-workflow.md
git commit -m "docs(w-route): doc-sync 6c — reads mem find em 4 handlers + orphan-cleanup (6c Task 5)

CHANGELOG + command-surface + guide alinhados com W-ROUTE 6c:
- mem_context_hint helper + reads em plan/implement/verify/qa
  (handler-only, degrade-soft, consumidor real por handler).
- Cleanup de órfãos: _apply_consolidate_l2 + l2.add_entry removidos.
- 04-pending: entradas de l2.add_entry e _apply_consolidate_l2 RESOLVIDAS.
- daily-workflow: nota sobre consulta automática de mem nos handlers (se
  a seção existia; 'sem alteração' caso contrário — ver commit body).
Full-lane RUN_E2E=1: verde nas 3 lanes pré-commit."
```

---

## Self-Review

### Cobertura D1–D3

- **D1 (reads nos 4 handlers, degrade-soft, handler-only):**
  - `plan`: Task 1 insere read em `run()` antes de `_run_waves_for_subtype`; resultado
    em `intake_tokens["{{mem_context_hint}}"]` → context-pack do subagente de Wave A.
  - `implement`: Task 2 insere read em `_print_plan_mode`; resultado renderizado como
    `renderer.dim(_hint)` antes do prompt de confirmação.
  - `qa`: Task 2 insere read em `run_qa` antes de `_write_conductor_handoff`; resultado
    em `handoff["mem_context"]` → conductor auditor.
  - `verify`: Task 3 insere read antes de `_run_cascade`; resultado renderizado em modo
    interativo, NÃO passado a `_run_cascade` (determinismo).
  - Degrade soft em todos: `mem_context_hint` retorna `None` → handler omite bloco
    silenciosamente. A `_degraded_message` do mem NÃO é surfada ao usuário.
  - Determinismo enforçado por teste estático (Task 3): `test_validators_determinism.py`
    varre todos os .py de `validators/` e garante zero import/call a
    `engine.integrations.mem`.

- **D2 (reuso — helper compartilhado):**
  - `mem_context_hint` é extraído em `engine/integrations/mem.py` (Task 1).
  - Compõe sobre `mem_find` de 6a via `_run_or_degrade` — zero subprocess novo.
  - Os 4 handlers COMPÕEM sobre `mem_context_hint` — zero duplicação de
    read+degrade+format. Decisão documentada no início do plano com justificativa.

- **D3 (orphan-cleanup confirmado por grep):**
  - Task 4 Step 1 exige grep-confirm ANTES de deletar. Expected outputs documentados.
  - `_apply_consolidate_l2`: definida mas irrastreável (dead-code desde 6b).
  - Import de `add_entry` em distiller: zero call-site de produção após 6b.
  - `l2.add_entry`: zero caller em engine/ (confirmado por grep externo ao arquivo).
  - `04-pending`: entradas de l2.add_entry e _apply_consolidate_l2 marcadas RESOLVIDO;
    misnomer `apply_proposal_to_l2` permanece pendente (6d+).
  - FICAM: `remove_entry`, `write_l2`, `read_l2`, `export_for_context_pack` (undo.py +
    migrador W-MIGRATE deferido).

### Sem placeholder

Todo step de código contém código Python completo, verbatim. Comandos têm expected output.
Nenhum `# TODO`, `# placeholder`, `pass` de stub, ou `...` no código dos steps.

### Consistência de assinatura `mem_context_hint` entre tasks

| Ponto de uso | Forma |
|---|---|
| Task 1 — implementação em mem.py | `mem_context_hint(project_root, query, *, limit=5) -> str \| None` |
| Task 1 — teste mock: `test_mem_context_hint_formats_hits` | `mem.mem_context_hint(tmp_path, "...", limit=5)` |
| Task 1 — import em plan.py | `from engine.integrations.mem import mem_context_hint` |
| Task 1 — call em plan.run | `mem_context_hint(project_root, slug, limit=5)` |
| Task 2 — import em implement.py | `from engine.integrations.mem import mem_context_hint` |
| Task 2 — call em _print_plan_mode | `mem_context_hint(project_root, task.description or task.task_id, limit=5)` |
| Task 2 — import em qa/__init__.py | `from engine.integrations.mem import mem_context_hint` |
| Task 2 — call em run_qa | `mem_context_hint(project_root, scope.target, limit=5)` |
| Task 3 — import em verify.py | `from engine.integrations.mem import mem_context_hint` |
| Task 3 — call em verify (pré-cascade) | `mem_context_hint(project_root, _hint_query, limit=5)` |
| Task 1 — monkeypatch nos testes de plan/implement/verify/qa | `lambda *a, **kw: None` ou string-literal |

Assinatura idêntica entre implementação e todos os call-sites. `mem_context_hint` importa
`mem_find` internamente (de 6a) — nenhum handler importa `mem_find` diretamente, só
`mem_context_hint`.

### Lição MOCK-BLINDNESS (real-mem test)

Task 1 inclui `test_mem_context_hint_real_mem_returns_str_or_none`: copia o binário
vendorizado pra `tmp_path`, chama `mem_context_hint` sem mock, asserta `str | None` sem
exceção. SKIPPED quando vendorizado ausente. Disciplina: paths de read (como o helper de
6c) exigem ao menos um teste contra o binário real — bugs de parsing/arg que o mock silencia
(ex.: formato de stdout inesperado do mem real) só são pegos sem mock.

### Footprint por contrato (não por import)

Task 4 Step 6 varre explicitamente: `test_memory_distiller.py` (reconcilia testes de
`_apply_consolidate_l2` diretamente), `test_memory_l2.py` (`test_add_entry_succeeds_then_duplicate_fails`
deletado — testa função inexistente). O implementer confirma quais quebram rodando a lane
antes de editar. `test_memory_l2.py` testes de `remove_entry`, `write_l2`, `read_l2` ficam
intactos.

### Full-lane RUN_E2E=1

Task 5 Step 5 roda explicitamente `RUN_E2E=1 .venv/bin/pytest -m "e2e"` como gate final
pré-commit. Nenhuma task anterior commita sem ter rodado a lane rápida (`not integration and
not e2e`). Task 5 é a única que roda a full-lane completa com e2e — adequado porque é o
commit de doc-sync final da sub-onda.
