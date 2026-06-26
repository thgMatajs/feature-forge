# W-ROUTE 6a — `forge memory` wrapper arg-driven — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Converter `forge memory` de menu interativo com checkpoint-resume num wrapper fino arg-driven que delega ao `mem` vendorizado, eliminando estruturalmente o burden multi-passo do DRIFT-1 (BUG-M1).

**Architecture:** Uma camada típica de wrappers sobre `mem_call()` em `engine/integrations/mem.py` (parse de `MemResult` → dado Python, degrade soft 3-caminhos). `engine/memory_cli.py` vira dispatcher stateless `forge memory <ação> [args]` (search/inspect/export/distill), zero `question.ask`, zero checkpoint. Inspeção de lifecycle sai (→ `forge status`); L3 removido.

**Tech Stack:** Python 3, argparse-style dispatch manual, subprocess (via `mem_call`), pytest.

## Global Constraints

- Branch: `feat/mem-integration` — acumula, NÃO cria branch nova, UM PR no fim da Fase 1.
- Test runner canônico: `.venv/bin/pytest` (tem json5 + deps; system pytest dá false-fail).
- `mem_call` já existe e já põe `--json` ANTES do subcomando + já faz env-scrub (`scrubbed_subprocess_env`). Os wrappers compõem sobre ele — não duplicam subprocess.
- Voz mentor-calmo em toda string user-facing. Sem emoji decorativo.
- Invariante de prova: o módulo `memory_cli` reescrito tem ZERO `question.ask*` e ZERO checkpoint helper.
- Doc-sync no MESMO commit da mudança de comportamento (Mandamento #6).
- `--json` é meta-flag global (resolvida em `cli.main` via contextvar antes do dispatch); o handler arg-driven DEVE filtrá-la do argv pra não poluir os args posicionais. `cli.main` passa `argv[1:]` sem strip.
- 6a roda unit + integration lanes (mudança de signature de comando exige full-lane, não só rapid).
- Design de referência: `docs/superpowers/specs/2026-06-26-w-route-6a-design.md` (refina a spec congelada `2026-06-25-mem-integration-design.md`).

---

### Task 1: Investigação BUG-M1 (time-boxed — define a forma da prova)

**Files:**
- Modify: `docs/superpowers/specs/2026-06-26-w-route-6a-design.md` (append de uma seção de resultado)

**Interfaces:**
- Consumes: nada.
- Produces: um veredito documentado (`REPRO-FOUND` ou `NO-REPRO`) que a Task 3 lê pra decidir se adiciona um teste de regressão histórico além da prova estrutural.

- [ ] **Step 1: Investigar (systematic-debugging, ~30min)**

Use a skill `superpowers:systematic-debugging`. Pergunta a responder: existe um sintoma REPRODUZÍVEL de checkpoint-resume defeituoso no `engine/memory_cli.py` ATUAL (resume pulando passo / re-prompt duplicado), ou a complexidade é fragilidade arquitetural sem defeito ativo? Evidência-chave: rode `.venv/bin/pytest tests/unit/test_engine_memory_cli_resume.py -v` — se passam, o resume FUNCIONA hoje (não há bug ativo; a cura é estrutural-por-eliminação). Procure também cenários não cobertos por esses testes (ex.: dois submenus encadeados com exit-2 no segundo).

- [ ] **Step 2: Documentar o veredito**

Append ao fim de `docs/superpowers/specs/2026-06-26-w-route-6a-design.md`:

```markdown
## BUG-M1 — resultado da investigação (Task 1)

**Veredito:** <REPRO-FOUND | NO-REPRO>

<Se REPRO-FOUND: descreva o sintoma exato, o cenário que o dispara, e o
teste de regressão a escrever na Task 3.>
<Se NO-REPRO: os testes de resume atuais passam → o resume funciona; a
"cura" do BUG-M1 é a ELIMINAÇÃO estrutural dos callsites (o wrapper
stateless não tem checkpoint nem prompt pausável). A prova é a asserção
de ausência estrutural + equivalência da Task 3, não um vermelho histórico.>
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-06-26-w-route-6a-design.md
git commit -m "docs(w-route): veredito da investigação BUG-M1 (6a Task 1)"
```

---

### Task 2: Camada típica de wrappers em `engine/integrations/mem.py`

**Files:**
- Modify: `engine/integrations/mem.py` (adiciona `MemQuery` + 5 wrappers ao fim do módulo)
- Test: `tests/integrations/test_mem_wrappers.py` (novo)

**Interfaces:**
- Consumes: `mem_call(project_root, subcmd_args, *, json=True, timeout=10) -> MemResult` e `MemResult(found, exit_code, stdout, stderr, timed_out)` (já existem).
- Produces:
  - `@dataclass(frozen=True) MemQuery(ok: bool, data: Any, message: str = "")`
  - `mem_find(project_root: Path, query: str, *, limit: int = 10, mem_type: str | None = None) -> MemQuery` (data = list[dict] de hits `{id,score,type,title,author}`)
  - `mem_get(project_root: Path, note_id: str) -> MemQuery` (data = dict da nota, ou `None` em exit 2 = not-found)
  - `mem_stats(project_root: Path) -> MemQuery` (data = dict de counts)
  - `mem_brief(project_root: Path, *, budget: int | None = None) -> MemQuery` (data = list[dict] `{id,type,line}`)
  - `mem_evolve(project_root: Path, *, apply: bool = False) -> MemQuery` (data = dict `{archive,dup_clusters,inbox,applied,skipped,proposals}`)

- [ ] **Step 1: Escrever os testes (falhando)**

Crie `tests/integrations/test_mem_wrappers.py`. Espelha o padrão de `tests/integrations/test_mem_call.py` (monkeypatch de `subprocess.run` com um fake; binário stub vendorizado):

```python
"""W-ROUTE 6a Task 2 — testes da camada típica de wrappers sobre mem_call.

TDD: escritos PRIMEIRO. Monkeypatcham `subprocess.run` (via o mesmo caminho
de mem_call) pra capturar o argv montado sem rodar o binário real.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _stub(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


class _Fake:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_run(monkeypatch, returncode: int, stdout: str = "", stderr: str = "") -> dict:
    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Fake(returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    return captured


def test_mem_find_builds_find_argv(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout='[{"id":"X","score":0.5,"type":"feedback","title":"t","author":"a"}]')
    res = mem.mem_find(tmp_path, "reuse", limit=3)
    assert res.ok is True
    assert res.data == [{"id": "X", "score": 0.5, "type": "feedback", "title": "t", "author": "a"}]
    # argv: <bin> --json find reuse -k 3
    assert cap["cmd"][1:] == ["--json", "find", "reuse", "-k", "3"]


def test_mem_find_type_filter(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout="[]")
    mem.mem_find(tmp_path, "q", mem_type="decision")
    assert "--type" in cap["cmd"] and "decision" in cap["cmd"]


def test_mem_get_returns_note(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout='{"id":"X","title":"t","body":"b","type":"feedback"}')
    res = mem.mem_get(tmp_path, "X")
    assert res.ok is True
    assert res.data["body"] == "b"
    assert cap["cmd"][1:] == ["--json", "get", "X"]


def test_mem_get_exit2_is_not_found_contract(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    _patch_run(monkeypatch, 2, stdout="", stderr="not found")
    res = mem.mem_get(tmp_path, "missing")
    # exit 2 é contrato (not-found), não erro: ok=True, data=None.
    assert res.ok is True
    assert res.data is None


def test_mem_stats_parses(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    _patch_run(monkeypatch, 0, stdout='{"total":3,"live":3,"by_type":{"feedback":3}}')
    res = mem.mem_stats(tmp_path)
    assert res.ok is True
    assert res.data["total"] == 3


def test_mem_brief_budget(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout='[{"id":"X","type":"decision","line":"l"}]')
    res = mem.mem_brief(tmp_path, budget=200)
    assert res.ok is True
    assert cap["cmd"][1:] == ["--json", "brief", "--budget", "200"]


def test_mem_evolve_apply_flag(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout='{"archive":[],"dup_clusters":[],"applied":0}')
    mem.mem_evolve(tmp_path, apply=True)
    assert cap["cmd"][1:] == ["--json", "evolve", "--apply"]


def test_wrapper_degrades_soft_when_binary_missing(tmp_path, monkeypatch):
    from engine.integrations import mem
    monkeypatch.setattr(mem.shutil, "which", lambda _t: None)
    res = mem.mem_find(tmp_path, "q")
    assert res.ok is False
    assert res.data is None
    assert res.message  # mensagem 3-caminhos presente
```

- [ ] **Step 2: Rodar pra confirmar que falham**

Run: `.venv/bin/pytest tests/integrations/test_mem_wrappers.py -v`
Expected: FAIL (`AttributeError: module 'engine.integrations.mem' has no attribute 'mem_find'`).

- [ ] **Step 3: Implementar os wrappers**

Adicione ao FIM de `engine/integrations/mem.py` (mantenha o `mem_call`/`MemResult`/`_resolve_binary` intactos). Adicione `import json as _json` e `from typing import Any` no topo do módulo (junto dos imports existentes):

```python
@dataclass(frozen=True)
class MemQuery:
    """Resultado de um wrapper de alto nível sobre ``mem_call``.

    ok:      True se o mem rodou e devolveu dado parseável (ou not-found
             contratual em ``get``). False em binário ausente / timeout /
             exit não-zero / JSON inválido.
    data:    JSON parseado (list|dict) quando ok; ``None`` em not-found ou
             em qualquer caminho degradado.
    message: mensagem 3-caminhos (mentor-calmo) quando ``ok`` é False.
    """

    ok: bool
    data: Any
    message: str = ""


def _degraded_message(result: MemResult) -> str:
    if not result.found:
        return (
            "mem indisponível. Três caminhos: "
            "(1) rode `forge init` pra vendorizar `.claude/bin/mem`; "
            "(2) instale o `mem` no PATH (dev/dogfood); "
            "(3) confira que `.claude/bin/mem` existe e é executável."
        )
    if result.timed_out:
        return (
            f"mem não respondeu a tempo ({result.stderr}). Tente de novo "
            "ou rode o subcomando direto em `.claude/bin/mem`."
        )
    return (
        f"mem falhou (exit {result.exit_code}): "
        f"{result.stderr.strip() or 'sem detalhe'}."
    )


def _parse_json(result: MemResult) -> MemQuery:
    try:
        return MemQuery(ok=True, data=_json.loads(result.stdout or "null"))
    except _json.JSONDecodeError as exc:
        return MemQuery(
            ok=False, data=None, message=f"mem devolveu JSON inválido: {exc}"
        )


def _run_or_degrade(project_root: Path, args: list[str]) -> MemQuery:
    result = mem_call(project_root, args)
    if not result.found or result.timed_out or result.exit_code != 0:
        return MemQuery(ok=False, data=None, message=_degraded_message(result))
    return _parse_json(result)


def mem_find(
    project_root: Path,
    query: str,
    *,
    limit: int = 10,
    mem_type: str | None = None,
) -> MemQuery:
    """`mem find` — busca ranqueada (títulos only). data = list de hits."""
    args = ["find", query, "-k", str(limit)]
    if mem_type:
        args += ["--type", mem_type]
    return _run_or_degrade(project_root, args)


def mem_get(project_root: Path, note_id: str) -> MemQuery:
    """`mem get` — corpo da nota. exit 2 (not-found) → ok=True, data=None."""
    result = mem_call(project_root, ["get", note_id])
    if not result.found or result.timed_out:
        return MemQuery(ok=False, data=None, message=_degraded_message(result))
    if result.exit_code == 2:
        return MemQuery(ok=True, data=None)
    if result.exit_code != 0:
        return MemQuery(ok=False, data=None, message=_degraded_message(result))
    return _parse_json(result)


def mem_stats(project_root: Path) -> MemQuery:
    """`mem stats` — counts + vitality + inbox. data = dict."""
    return _run_or_degrade(project_root, ["stats"])


def mem_brief(project_root: Path, *, budget: int | None = None) -> MemQuery:
    """`mem brief` — índice de alto valor. data = list de `{id,type,line}`."""
    args = ["brief"]
    if budget is not None:
        args += ["--budget", str(budget)]
    return _run_or_degrade(project_root, args)


def mem_evolve(project_root: Path, *, apply: bool = False) -> MemQuery:
    """`mem evolve` — curadoria do acervo. data = dict de proposals."""
    args = ["evolve"]
    if apply:
        args.append("--apply")
    return _run_or_degrade(project_root, args)
```

- [ ] **Step 4: Rodar pra confirmar verde**

Run: `.venv/bin/pytest tests/integrations/test_mem_wrappers.py -v`
Expected: PASS (8 testes).

- [ ] **Step 5: Commit**

```bash
git add engine/integrations/mem.py tests/integrations/test_mem_wrappers.py
git commit -m "feat(mem): camada típica de wrappers (find/get/stats/brief/evolve) sobre mem_call

W-ROUTE 6a Task 2. MemQuery uniforme (ok/data/message), degrade soft
3-caminhos. YAGNI: só os 5 wrappers que 6a consome; 6b/W-AGENTS estendem."
```

---

### Task 3: Reescrever `engine/memory_cli.py` como dispatcher arg-driven

**Files:**
- Modify (rewrite completo): `engine/memory_cli.py`
- Test: `tests/unit/test_commands_memory.py` (rewrite)
- Delete: `tests/unit/test_engine_memory_cli_resume.py`

**Interfaces:**
- Consumes: `mem_find/mem_get/mem_stats/mem_brief/mem_evolve` + `MemQuery` (Task 2); `output_mode.is_json_mode()`; `renderer`; `find_project_root`/`ProjectRootNotFoundError`.
- Produces: `run(argv: list[str]) -> int` — dispatcher de `search|inspect|export|distill`; filtra `--json` do argv antes de extrair ação/rest.

- [ ] **Step 1: Escrever os testes (falhando)**

Reescreva `tests/unit/test_commands_memory.py` inteiro:

```python
"""W-ROUTE 6a — testes do `forge memory` arg-driven (substitui o smoke de menu).

Cobre: dispatch por ação (equivalência — cada ação chama o wrapper certo),
usage em ação ausente/desconhecida, e a PROVA estrutural de BUG-M1 (zero
prompt pausável / zero checkpoint no módulo reescrito).
"""
from __future__ import annotations

import inspect

import pytest

from engine import memory_cli
from engine.integrations.mem import MemQuery


def test_module_imports() -> None:
    assert callable(memory_cli.run)


def test_empty_argv_is_usage(monkeypatch, tmp_project_root) -> None:
    monkeypatch.chdir(tmp_project_root)
    assert memory_cli.run([]) == 2


def test_unknown_action_is_usage(monkeypatch, tmp_project_root) -> None:
    monkeypatch.chdir(tmp_project_root)
    assert memory_cli.run(["bogus"]) == 2


def test_pre_init_returns_exit_1(monkeypatch, tmp_path) -> None:
    # dir bare (sem .git/.claude) → find_project_root levanta → exit 1
    # (contrato Bug U1), ANTES de qualquer parse de ação.
    monkeypatch.chdir(tmp_path)
    assert memory_cli.run([]) == 1


# ── Equivalência: cada ação delega ao wrapper correto ────────────────────

def test_search_calls_mem_find(monkeypatch, tmp_project_root) -> None:
    monkeypatch.chdir(tmp_project_root)
    seen: dict = {}

    def _fake_find(root, query, **kw):
        seen["query"] = query
        return MemQuery(ok=True, data=[])

    monkeypatch.setattr(memory_cli, "mem_find", _fake_find)
    assert memory_cli.run(["search", "reuse", "first"]) == 0
    assert seen["query"] == "reuse first"


def test_search_without_query_is_usage(monkeypatch, tmp_project_root) -> None:
    monkeypatch.chdir(tmp_project_root)
    assert memory_cli.run(["search"]) == 2


def test_inspect_with_id_calls_mem_get(monkeypatch, tmp_project_root) -> None:
    monkeypatch.chdir(tmp_project_root)
    seen: dict = {}

    def _fake_get(root, note_id):
        seen["id"] = note_id
        return MemQuery(ok=True, data={"id": note_id, "title": "t", "body": "b", "type": "feedback"})

    monkeypatch.setattr(memory_cli, "mem_get", _fake_get)
    assert memory_cli.run(["inspect", "01ABC"]) == 0
    assert seen["id"] == "01ABC"


def test_inspect_without_id_calls_mem_stats(monkeypatch, tmp_project_root) -> None:
    monkeypatch.chdir(tmp_project_root)
    called: dict = {}

    def _fake_stats(root):
        called["hit"] = True
        return MemQuery(ok=True, data={"total": 0, "live": 0})

    monkeypatch.setattr(memory_cli, "mem_stats", _fake_stats)
    assert memory_cli.run(["inspect"]) == 0
    assert called.get("hit") is True


def test_export_calls_mem_brief(monkeypatch, tmp_project_root) -> None:
    monkeypatch.chdir(tmp_project_root)
    seen: dict = {}

    def _fake_brief(root, *, budget=None):
        seen["budget"] = budget
        return MemQuery(ok=True, data=[])

    monkeypatch.setattr(memory_cli, "mem_brief", _fake_brief)
    assert memory_cli.run(["export", "--budget", "200"]) == 0
    assert seen["budget"] == 200


def test_distill_calls_mem_evolve(monkeypatch, tmp_project_root) -> None:
    monkeypatch.chdir(tmp_project_root)
    seen: dict = {}

    def _fake_evolve(root, *, apply=False):
        seen["apply"] = apply
        return MemQuery(ok=True, data={"archive": [], "dup_clusters": [], "applied": 0})

    monkeypatch.setattr(memory_cli, "mem_evolve", _fake_evolve)
    assert memory_cli.run(["distill", "--apply"]) == 0
    assert seen["apply"] is True


def test_degraded_mem_returns_1(monkeypatch, tmp_project_root) -> None:
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr(
        memory_cli, "mem_find",
        lambda root, q, **kw: MemQuery(ok=False, data=None, message="mem indisponível. Três caminhos: ..."),
    )
    assert memory_cli.run(["search", "x"]) == 1


# ── Prova estrutural de BUG-M1: ausência de estado multi-passo ───────────

def test_no_interactive_prompts_in_module() -> None:
    src = inspect.getsource(memory_cli)
    assert "question.ask" not in src
    assert "allow_pause" not in src


def test_checkpoint_machinery_removed() -> None:
    for name in (
        "_save_memory_cli_checkpoint",
        "_load_memory_cli_checkpoint",
        "_clear_memory_cli_checkpoint",
        "_MemoryCliCheckpoint",
        "_memory_snapshot",
    ):
        assert not hasattr(memory_cli, name), f"{name} deveria ter sumido"


# ── C-002: --json não polui os args posicionais do dispatch ──────────────

def test_json_flag_stripped_from_query(monkeypatch, tmp_project_root) -> None:
    monkeypatch.chdir(tmp_project_root)
    seen: dict = {}

    def _fake_find(root, query, **kw):
        seen["query"] = query
        return MemQuery(ok=True, data=[])

    monkeypatch.setattr(memory_cli, "mem_find", _fake_find)
    assert memory_cli.run(["search", "reuse", "--json"]) == 0
    assert seen["query"] == "reuse"  # --json removido, não poluiu a query


# ── C-001: JSON-mode emite o JSON do mem (substitui test_memory_json) ────

def test_inspect_json_mode_emits_stats_json(monkeypatch, tmp_project_root, capsys) -> None:
    import json as _json
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr(memory_cli.output_mode, "is_json_mode", lambda: True)
    monkeypatch.setattr(
        memory_cli, "mem_stats",
        lambda root: MemQuery(ok=True, data={"total": 2, "live": 2}),
    )
    assert memory_cli.run(["inspect", "--json"]) == 0
    out = capsys.readouterr().out
    assert _json.loads(out) == {"total": 2, "live": 2}


def test_search_json_mode_emits_hits_json(monkeypatch, tmp_project_root, capsys) -> None:
    import json as _json
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr(memory_cli.output_mode, "is_json_mode", lambda: True)
    monkeypatch.setattr(
        memory_cli, "mem_find",
        lambda root, q, **kw: MemQuery(ok=True, data=[{"id": "X", "title": "t"}]),
    )
    assert memory_cli.run(["search", "reuse", "--json"]) == 0
    out = capsys.readouterr().out
    assert _json.loads(out) == [{"id": "X", "title": "t"}]
```

> Se a Task 1 deu `REPRO-FOUND`, adicione AQUI também o teste de regressão histórico descrito no veredito (red→green), além da prova estrutural acima.

- [ ] **Step 2: Rodar pra confirmar que falham**

Run: `.venv/bin/pytest tests/unit/test_commands_memory.py -v`
Expected: FAIL (o módulo antigo ainda tem `question.ask`/checkpoint; e `mem_find` não está importado em `memory_cli`).

- [ ] **Step 3: Reescrever `engine/memory_cli.py` (conteúdo completo)**

Substitua TODO o conteúdo de `engine/memory_cli.py` por:

```python
"""`forge memory` — wrapper fino arg-driven sobre o `mem` vendorizado.

W-ROUTE 6a: o handler deixou de ser menu interativo (com checkpoint-resume
do DRIFT-1) e virou um dispatcher stateless de subcomandos que delega ao
substrato `mem` via a fronteira shell (`engine.integrations.mem`). Cada
invocação é stateless — sem prompt pausável, sem checkpoint — então o burden
multi-passo desaparece estruturalmente.

Superfície:
    forge memory search <query>      → mem find
    forge memory inspect [id]        → mem get <id> | mem stats
    forge memory export [--budget N] → mem brief
    forge memory distill [--apply]   → mem evolve

Inspeção de lifecycle (status/phase/history) NÃO vive aqui — é `forge status`
(estado operacional, não memória-de-conhecimento). L3 (proxy de MEMORY.md)
foi removido. Voz: mentor calmo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from engine.integrations.mem import (
    mem_brief,
    mem_evolve,
    mem_find,
    mem_get,
    mem_stats,
)
from engine.ui import output_mode, renderer
from engine.utils.paths import ProjectRootNotFoundError, find_project_root

_USAGE = (
    "uso: forge memory <ação> [args]\n"
    "  search <query>       busca ranqueada no acervo (mem find)\n"
    "  inspect [id]         corpo de uma nota (mem get) ou stats do acervo\n"
    "  export [--budget N]  índice de alto valor pro context-pack (mem brief)\n"
    "  distill [--apply]    curadoria do acervo (mem evolve)\n"
)


def _emit_degraded(message: str) -> int:
    sys.stderr.write(f"forge memory: {message}\n")
    return 1


def _action_search(project_root: Path, rest: list[str], json_mode: bool) -> int:
    query = " ".join(rest).strip()
    if not query:
        sys.stderr.write("forge memory search: falta <query>.\n")
        return 2
    res = mem_find(project_root, query)
    if not res.ok:
        return _emit_degraded(res.message)
    hits = res.data or []
    if json_mode:
        print(json.dumps(hits, indent=2, default=str))
        return 0
    if not hits:
        renderer.write(renderer.dim("  sem matches."))
        return 0
    renderer.write(renderer.bold(f"matches ({len(hits)})"))
    for h in hits:
        renderer.write(
            f"  {h.get('id', '?'):<28} score={h.get('score', 0):.3f}  "
            f"{h.get('type', ''):<10} {(h.get('title') or '')[:48]}"
        )
    return 0


def _action_inspect(project_root: Path, rest: list[str], json_mode: bool) -> int:
    if rest:
        note_id = rest[0]
        res = mem_get(project_root, note_id)
        if not res.ok:
            return _emit_degraded(res.message)
        if res.data is None:
            if json_mode:
                print(json.dumps(None))
            else:
                renderer.write(
                    renderer.colored(f"  nota {note_id} não encontrada.", "yellow")
                )
            return 0
        if json_mode:
            print(json.dumps(res.data, indent=2, default=str))
            return 0
        note = res.data
        renderer.write("")
        renderer.write(renderer.section_header(note.get("title") or note_id, width=78))
        renderer.write(
            renderer.dim(
                f"  {note.get('id', '')} · {note.get('type', '')} · "
                f"imp={note.get('importance', '?')}"
            )
        )
        renderer.write("")
        for line in (note.get("body") or "").splitlines():
            renderer.write(f"  {line}")
        return 0

    res = mem_stats(project_root)
    if not res.ok:
        return _emit_degraded(res.message)
    stats = res.data or {}
    if json_mode:
        print(json.dumps(stats, indent=2, default=str))
        return 0
    renderer.write("")
    renderer.write(renderer.bold("acervo (mem stats)"))
    renderer.write(
        f"  total={stats.get('total', 0)}  live={stats.get('live', 0)}  "
        f"stale={stats.get('stale', 0)}"
    )
    for t, n in sorted((stats.get("by_type") or {}).items()):
        renderer.write(f"    {t:<12} {n}")
    renderer.write(
        f"  inbox: pending={stats.get('inbox_pending', 0)} "
        f"promoted={stats.get('inbox_promoted', 0)} "
        f"rejected={stats.get('inbox_rejected', 0)}"
    )
    return 0


def _action_export(project_root: Path, rest: list[str], json_mode: bool) -> int:
    budget: int | None = None
    if "--budget" in rest:
        idx = rest.index("--budget")
        if idx + 1 >= len(rest):
            sys.stderr.write("forge memory export: --budget exige um inteiro.\n")
            return 2
        try:
            budget = int(rest[idx + 1])
        except ValueError:
            sys.stderr.write("forge memory export: --budget exige um inteiro.\n")
            return 2
    res = mem_brief(project_root, budget=budget)
    if not res.ok:
        return _emit_degraded(res.message)
    items = res.data or []
    if json_mode:
        print(json.dumps(items, indent=2, default=str))
        return 0
    # Texto pro context-pack — stdout direto, pipeable.
    for it in items:
        sys.stdout.write(f"- [{it.get('type', '')}] {it.get('line', '')}\n")
    sys.stdout.flush()
    return 0


def _action_distill(project_root: Path, rest: list[str], json_mode: bool) -> int:
    apply = "--apply" in rest
    res = mem_evolve(project_root, apply=apply)
    if not res.ok:
        return _emit_degraded(res.message)
    data = res.data or {}
    if json_mode:
        print(json.dumps(data, indent=2, default=str))
        return 0
    archive = data.get("archive") or []
    dups = data.get("dup_clusters") or []
    renderer.write("")
    renderer.write(renderer.bold("curadoria do acervo (mem evolve)"))
    renderer.write(
        f"  archive-candidatos={len(archive)}  dup-clusters={len(dups)}  "
        f"aplicados={data.get('applied', 0)}"
    )
    if not apply and (archive or dups):
        renderer.write(
            renderer.dim(
                "  rode `forge memory distill --apply` pra arquivar candidatos "
                "own-author."
            )
        )
    return 0


_ACTIONS = {
    "search": _action_search,
    "inspect": _action_inspect,
    "export": _action_export,
    "distill": _action_distill,
}


def run(argv: list[str]) -> int:
    """Dispatcher arg-driven do `forge memory` (stateless, sem prompt).

    `find_project_root()` vem PRIMEIRO: pré-init (dir sem projeto) → exit 1
    (contrato Bug U1/SPEC §3 A.1), antes de qualquer parse de ação. `--json`
    é meta-flag global já resolvida em `cli.main` (contextvar via
    `output_mode.is_json_mode()`); filtramos do argv aqui pra não poluir os
    args posicionais — `cli.main` repassa `argv[1:]` sem strip.
    """
    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        sys.stderr.write(f"forge memory: {exc}\n")
        return 1
    argv = [a for a in argv if a != "--json"]
    if not argv:
        sys.stderr.write(_USAGE)
        return 2
    action, rest = argv[0], argv[1:]
    handler = _ACTIONS.get(action)
    if handler is None:
        sys.stderr.write(f"forge memory: ação desconhecida '{action}'.\n")
        sys.stderr.write(_USAGE)
        return 2
    return handler(project_root, rest, output_mode.is_json_mode())


__all__ = ["run"]
```

- [ ] **Step 4: Remover os testes obsoletos**

```bash
git rm tests/unit/test_engine_memory_cli_resume.py tests/unit/test_memory_json.py
```

(Ambos testam comportamento que deixa de existir — `test_engine_memory_cli_resume.py` (checkpoint-resume) e `test_memory_json.py` (snapshot `_memory_snapshot` de 3 camadas + `read_l3_index`). Remoção correta, não regressão. Clean-break declarado no design 6a.)

- [ ] **Step 5: Rodar a lane afetada**

Run: `.venv/bin/pytest tests/unit/test_commands_memory.py tests/integrations/test_mem_wrappers.py -v`
Expected: PASS (todos). Dois arquivos de teste obsoletos removidos (resume + memory_json) — a queda de count é declarada, não regressão. Confirme que nenhum import órfão quebrou: `.venv/bin/pytest -m "not integration and not e2e" -q | tail -3`.

- [ ] **Step 6: Commit**

```bash
git add engine/memory_cli.py tests/unit/test_commands_memory.py
git rm tests/unit/test_engine_memory_cli_resume.py tests/unit/test_memory_json.py
git commit -m "feat(memory): forge memory vira wrapper arg-driven stateless (BUG-M1)

W-ROUTE 6a Task 3. Menu interativo + checkpoint-resume (DRIFT-1) → dispatcher
search/inspect/export/distill que delega ao mem. Zero question.ask, zero
checkpoint: o burden multi-passo some estruturalmente. Inspeção de lifecycle
sai (→ forge status); L3 removido; forget dropado (sem primitivo de archive
por-id no mem — curadoria via distill→mem evolve). Remove os testes de resume
e de snapshot-JSON (ambos cobrem comportamento removido); adiciona testes de
JSON-mode da superfície nova."
```

---

### Task 4: Reconciliar o footprint de testes do contrato observável

**Files:**
- Delete: (já feito na Task 3 — `test_engine_memory_cli_resume.py`, `test_memory_json.py`)
- Modify: `tests/integration/test_callsites_smoke.py`
- Modify: `tests/integration/test_subnamespace_paths.py`
- Modify: `tests/unit/test_help_json_manifest.py`
- Modify: `engine/cli.py` (`_COMMAND_META["memory"]`)

**Interfaces:**
- Consumes: a superfície stateless da Task 3.
- Produces: suíte verde nas lanes unit+integration; manifest honesto.

- [ ] **Step 1: Remover `test_smoke_memory_emits_intent`**

Remova de `tests/integration/test_callsites_smoke.py` a função `test_smoke_memory_emits_intent` inteira (≈ linhas 294-309). Ela assere que `forge memory` pausa no menu e emite pending JSON — comportamento que a cura do BUG-M1 elimina (handler stateless não emite intent). Remoção correta, não regressão.

- [ ] **Step 2: Tirar `memory_cli` da assertion de active_config_path**

Em `tests/integration/test_subnamespace_paths.py` (`test_all_active_config_consumers_resolve_via_resolver`, ≈ linhas 106-136), remova `memory_cli` da tupla de módulos que devem conter `"active_config_path"` no source. O módulo reescrito é stateless e não carrega config ativa. Os demais consumidores (cli/raw/evolve/ingest/undo/implement/doctor) permanecem na assertion.

- [ ] **Step 3: Flip `prompts_by_default` de memory pra False**

Em `engine/cli.py`, na entrada `_COMMAND_META["memory"]` (≈ linha 296), mude `"prompts_by_default": True` → `"prompts_by_default": False` e atualize o summary pra refletir a superfície nova:
```python
    "memory":      {"summary": "Wrapper sobre o mem: search/inspect/export/distill.", "prompts_by_default": False, "machine_readable": True,  "flags": ["--json"], "args": ["search|inspect|export|distill"]},
```
O handler stateless nunca prompta — `prompts_by_default: True` seria o manifest mentindo sobre a superfície (detection finding).

- [ ] **Step 4: Atualizar `test_help_json_manifest.py`**

Em `tests/unit/test_help_json_manifest.py` (≈ linhas 50-57), remova `memory` da tupla de read-cmds que promptam por default e adicione a asserção de non-prompting. Substitua o bloco:
```python
    # Os 4 read-cmds que promptam no default: prompts_by_default=True E --json.
    for name in ("verify", "doctor", "graph", "memory"):
        assert by_name[name]["prompts_by_default"] is True, name
        assert by_name[name]["machine_readable"] is True, name

    # status: único genuinamente non-prompting, mas machine_readable.
    assert by_name["status"]["prompts_by_default"] is False
    assert by_name["status"]["machine_readable"] is True
```
por:
```python
    # Read-cmds que promptam no default: prompts_by_default=True E --json.
    for name in ("verify", "doctor", "graph"):
        assert by_name[name]["prompts_by_default"] is True, name
        assert by_name[name]["machine_readable"] is True, name

    # status e memory: non-prompting, mas machine_readable (--json).
    for name in ("status", "memory"):
        assert by_name[name]["prompts_by_default"] is False, name
        assert by_name[name]["machine_readable"] is True, name
```

- [ ] **Step 5: Rodar unit + integration das áreas tocadas**

Run: `.venv/bin/pytest tests/unit/test_exit_codes.py tests/unit/test_help_json_manifest.py tests/unit/test_output_mode.py tests/integration/test_callsites_smoke.py tests/integration/test_subnamespace_paths.py -v`
Expected: PASS (todos). Depois a lane integration inteira: `.venv/bin/pytest -m "integration" -q | tail -3` — verde.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_callsites_smoke.py tests/integration/test_subnamespace_paths.py tests/unit/test_help_json_manifest.py engine/cli.py
git commit -m "test(w-route): reconcilia footprint observável do forge memory (6a)

Remove test_smoke_memory_emits_intent (handler stateless não emite intent),
tira memory_cli da assertion de active_config_path, flip prompts_by_default
de memory pra False (manifest honesto) + atualiza test_help_json_manifest."
```

---

### Task 5: Doc-sync (mesmo ciclo da mudança de superfície)

**Files:**
- Modify: `docs/design/06-command-surface.md`
- Modify: `CHANGELOG.md`
- Modify: `README.md` (só se a linha de `forge memory` mudar)
- Modify: `docs/guides/daily-workflow.md` (se descreve o menu)
- Modify: `engine/evolve.py` (3 strings que apontam pro comando antigo)
- Modify: `docs/design/04-pending.md` (anota `forget` dropado + `l3.py` órfão)

**Interfaces:**
- Consumes: a superfície nova da Task 3.
- Produces: docs e strings consistentes com `forge memory <ação>`.

- [ ] **Step 1: Atualizar `engine/evolve.py`**

Localize as 3 ocorrências (≈ linhas 305, 425, 516) de `forge memory → distill L2` / `Rode \`forge memory\` → distill L2` e troque pela forma arg-driven `forge memory distill` (mantendo a voz mentor-calmo da frase ao redor). Exemplo de substituição:
- `"a": "forge memory → distill L2 (depois retomo)"` → `"a": "forge memory distill (depois retomo)"`
- `"  Rode \`forge memory\` → distill L2, depois \`forge evolve\` "` → `"  Rode \`forge memory distill\`, depois \`forge evolve\` "`
- idem na 3ª ocorrência.

- [ ] **Step 2: Atualizar `docs/design/06-command-surface.md`**

Substitua a descrição de `forge memory` (que hoje diz "inspect L1/L2/L3" / menu) pela superfície arg-driven:

```markdown
- `forge memory <ação>` — wrapper fino sobre o `mem` vendorizado (stateless):
  - `search <query>` — busca ranqueada no acervo (`mem find`)
  - `inspect [id]` — corpo de uma nota (`mem get`) ou stats do acervo (`mem stats`)
  - `export [--budget N]` — índice de alto valor pro context-pack (`mem brief`)
  - `distill [--apply]` — curadoria do acervo (`mem evolve`)
  Inspeção de lifecycle vive em `forge status`; L3/forget removidos (W-ROUTE 6a).
```

- [ ] **Step 3: Atualizar `docs/guides/daily-workflow.md`**

Se o guia descreve o menu interativo (`inspect L2` / `search` por menu), reescreva os trechos pra invocação arg-driven (`forge memory search "<termo>"`, `forge memory export`). Se não menciona, pule este step (registre "sem mudança" no commit body).

- [ ] **Step 4: Atualizar `README.md`**

Se a command-surface do README lista `forge memory` com a forma antiga, alinhe com a nova superfície (1 linha). Se não muda stats/contagem, sem mais.

- [ ] **Step 5: Atualizar `CHANGELOG.md` (Unreleased)**

Adicione em `### Changed`:

```markdown
- `forge memory` reescrito como wrapper fino arg-driven sobre o `mem`
  vendorizado (`search`/`inspect`/`export`/`distill`), stateless — elimina
  o checkpoint-resume do DRIFT-1 (BUG-M1). Inspeção de lifecycle move pra
  `forge status`; L3 e `forget` por-id removidos (W-ROUTE 6a).
```

- [ ] **Step 6: Anotar gaps + atualizar linha stale em `docs/design/04-pending.md`**

Primeiro, atualize a linha stale (≈ linha 1145) que ainda lista a superfície antiga (`forge memory ... forget`) pra refletir a superfície nova (`search`/`inspect`/`export`/`distill`).

Depois, adicione duas entradas a `docs/design/04-pending.md`:

```markdown
- **`forge memory forget` removido (W-ROUTE 6a)** — o mem não tem primitivo
  de archive-por-id (`supersede` exige NEW+OLD; `evolve --apply` arquiva por
  standing, não por alvo). Curadoria de archive passa a ser `forge memory
  distill` → `mem evolve`. Candidato a `mem-report` upstream: um `mem archive
  <id>`.
- **`engine/memory/l3.py` órfão (W-ROUTE 6a)** — perdeu o único consumidor de
  produção (`memory_cli` parou de inspecionar L3). Slated pra remoção num
  passo clean-break posterior; mantido agora pra não expandir o escopo de 6a.
```

- [ ] **Step 7: Rodar a lane rápida + verify**

Run: `.venv/bin/pytest -m "not integration and not e2e" -q | tail -3`
Expected: verde (sem regressão de count além da remoção declarada do teste de resume).

- [ ] **Step 8: Commit**

```bash
git add docs/design/06-command-surface.md CHANGELOG.md README.md docs/guides/daily-workflow.md engine/evolve.py docs/design/04-pending.md
git commit -m "docs(w-route): doc-sync da superfície arg-driven do forge memory (6a)

CHANGELOG + command-surface + guide + strings de evolve.py alinhados ao
novo forge memory <ação>."
```

---

## Self-Review

- **Cobertura da spec/design 6a:** D1 (arg-driven, zero question.ask) → Task 3 + prova estrutural. D2 (lifecycle sai) → Task 3 (sem L1 inspect) + doc-sync. D3 (camada típica só do que 6a usa) → Task 2 (5 wrappers). D4 (prova BUG-M1 via investigação) → Task 1 + Task 3 (prova estrutural + regressão condicional). Footprint de teste (remove resume, reescreve smoke, adiciona wrapper+equivalência) → Task 2/3. Reconciliação do footprint observável → Task 4. Doc-sync → Task 5.
- **Sem placeholder:** todo step de código tem o código real; comandos têm output esperado.
- **Consistência de tipos:** `MemQuery(ok, data, message)` definido na Task 2 e consumido com os mesmos campos na Task 3 e nos testes. Assinaturas dos 5 wrappers idênticas entre Task 2 (Produces), Task 3 (chamadas) e os testes.
- **Decisão aberta resolvida:** `forget` dropado (sem primitivo de archive por-id no mem) — curadoria via `distill`→`mem evolve`. Documentado no commit da Task 3 e no doc-sync.
- **C-001/C-002 do plan-audit r1 endereçados:** `--json` filtrado no `run()` + testes de strip e JSON-mode; `test_memory_json.py` removido junto do resume; `forget` dropado e `l3.py` órfão anotados em 04-pending.
- **Round 2 fechou o footprint observável inteiro (varredura completa de tests/):** test_exit_codes (run reorder, find_project_root no topo→exit 1 pré-init), test_callsites_smoke (remove smoke_memory_emits_intent), test_subnamespace_paths (drop memory_cli da assertion active_config_path), test_help_json_manifest + _COMMAND_META (prompts_by_default→False, manifest honesto), 04-pending linha stale. Lanes: 6a roda unit+integration (não só rapid), por ser mudança de signature de comando.
