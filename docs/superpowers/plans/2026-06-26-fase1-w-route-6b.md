# W-ROUTE 6b — `forge evolve` conhecimento→mem-inbox + `status` L2-size→mem-stats — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-rotear os 3 branches de conhecimento em `apply_proposal_to_l2` pro `mem inbox add` em vez de escrever no L2, adicionar o wrapper `mem_inbox_add` à camada de integração, e trocar a linha de L2-size em `_render_memory` / `_status_payload` por um resumo de `mem stats`.

**Architecture:** Estende a camada de wrappers de 6a (`engine/integrations/mem.py`) com `mem_inbox_add`. Re-roteia os branches `promote-to-l2`, `l1-to-l2-promotion`, `consolidate-l2` dentro de `apply_proposal_to_l2` (distiller) para chamarem `mem_inbox_add` e levantarem `MemoryError` se `ok=False` (raise-não-drena). Substitui `_render_memory` em `status.py` para exibir `mem stats` e atualiza o JSON payload com bloco `mem`. Reconcilia footprint de testes observáveis e faz doc-sync.

**Tech Stack:** Python 3, subprocess (via `mem_call`/`_run_or_degrade`), pytest.

## Global Constraints

- Branch: `feat/mem-integration` — acumula, NÃO cria branch nova, UM PR no fim da Fase 1.
- Test runner canônico: `.venv/bin/pytest` (tem json5 + deps; system pytest dá false-fail).
- `mem_inbox_add` monta argv: `["inbox", "add", "--type", mem_type, "-t", title]` + opcionais (`--importance`, `--tags`, `--source`, `--origin`) + **`"--", body`** OBRIGATORIAMENTE no fim — `--` antes do body posicional previne que body começando com `-` quebre o argparse do mem (lição W-RULES). Usa-se a forma longa `--importance` (mais legível que o alias `-i`).
- Re-rota só os 3 branches de L2-knowledge implementados (`promote-to-l2`, `l1-to-l2-promotion`, `consolidate-l2`). O loop interativo do `forge evolve` (single-by-single, checkpoint-resume) permanece intacto — 6b NÃO o torna stateless. Mas D5 É implementado: o overflow-guard (`detect_l2_overflow`) em `_apply_proposal` PULA para os 3 kinds de conhecimento (eles vão pro mem inbox, não escrevem L2 — bloqueá-los por "L2 cheia" seria incorreto). `forget-l1` e branches estruturais INALTERADOS (continuam sujeitos ao overflow-guard, pois `forget-l1` mexe em L1 e os estruturais não tocam L2 mas mantêm o comportamento legacy do guard).
- Raise-não-drena: se `mem_inbox_add` retornar `ok=False`, raise `MemoryError` — não chamar `remove_from_queue`. Só remove da queue após sucesso.
- `l2.add_entry` e `apply_proposal_to_l2` NÃO são deletados nem renomeados em 6b (órfão e misnomer anotados em 04-pending).
- Full-lane unit+integration. Teste real-mem obrigatório pro path de escrita inbox-add.
- Voz mentor-calmo em toda string user-facing. Sem emoji decorativo nos docstrings.

---

### Task 1: `mem_inbox_add` em `engine/integrations/mem.py`

**Files:**
- Modify: `engine/integrations/mem.py` (adiciona `mem_inbox_add` ao fim)
- Test: `tests/integrations/test_mem_wrappers.py` (adiciona testes de `mem_inbox_add` — mock + real-mem)

**Interfaces:**
- Consumes: `_run_or_degrade(project_root, args)`, `MemQuery`, `_resolve_binary`, `mem_call` (todos já existem em `engine/integrations/mem.py`).
- Produces:
  ```
  mem_inbox_add(
      project_root: Path,
      title: str,
      body: str,
      mem_type: str,
      *,
      importance: int | None = None,
      tags: str | None = None,
      source: str | None = None,
      origin: str = "manual",
  ) -> MemQuery
  ```
  `data` = stdout parseado (o id da nota candidata ou dict); `ok=False` em degrade/erro.

**Reuso (Mandamento #3):** `mem_inbox_add` COMPÕE sobre os helpers já existentes — chama `_run_or_degrade` (que por sua vez usa `mem_call` + `_parse_json` + `_degraded_message`). NÃO introduz subprocess novo nem lógica de degrade própria; estende a camada D3 criada em 6a no mesmo módulo (`engine/integrations/mem.py`), seguindo o padrão verbatim dos 5 wrappers de 6a (`mem_find`/`mem_get`/`mem_stats`/`mem_brief`/`mem_evolve`). Consultado o padrão dos wrappers de 6a antes de escrever — zero helper novo.

- [ ] **Step 1: Escrever os testes (falhando)**

Adicione ao final de `tests/integrations/test_mem_wrappers.py` os seguintes testes. Os helpers `_stub`, `_Fake`, `_patch_run` já existem no arquivo — não os redefina:

```python
# ── Task 1 (6b): mem_inbox_add ────────────────────────────────────────────


def test_inbox_add_builds_correct_argv(tmp_path, monkeypatch):
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout='"01ABC"')
    res = mem.mem_inbox_add(
        tmp_path,
        title="use-stateflow",
        body="Use MutableStateFlow para screen state",
        mem_type="reference",
        importance=4,
        tags="auth,kotlin",
        source="forge-evolve:P-001",
        origin="manual",
    )
    assert res.ok is True
    # argv esperado (sem o binário — index 1 em diante):
    # --json inbox add --type reference -t use-stateflow
    # --importance 4 --tags auth,kotlin --source forge-evolve:P-001 --origin manual
    # -- Use MutableStateFlow para screen state
    cmd = cap["cmd"]
    assert cmd[1] == "--json"
    assert cmd[2] == "inbox"
    assert cmd[3] == "add"
    assert "--type" in cmd and cmd[cmd.index("--type") + 1] == "reference"
    assert "-t" in cmd and cmd[cmd.index("-t") + 1] == "use-stateflow"
    assert "--importance" in cmd and cmd[cmd.index("--importance") + 1] == "4"
    assert "--tags" in cmd and cmd[cmd.index("--tags") + 1] == "auth,kotlin"
    assert "--source" in cmd and cmd[cmd.index("--source") + 1] == "forge-evolve:P-001"
    assert "--origin" in cmd and cmd[cmd.index("--origin") + 1] == "manual"
    # -- separador ANTES do body (obrigatório — lição W-RULES)
    assert "--" in cmd
    dash_dash_idx = cmd.index("--")
    assert cmd[dash_dash_idx + 1] == "Use MutableStateFlow para screen state"


def test_inbox_add_minimal_argv(tmp_path, monkeypatch):
    """Sem opcionais: só --type, -t, -- body."""
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout='"01XYZ"')
    res = mem.mem_inbox_add(
        tmp_path,
        title="t",
        body="desc",
        mem_type="reference",
    )
    assert res.ok is True
    cmd = cap["cmd"]
    # Opcionais ausentes
    assert "--importance" not in cmd
    assert "--tags" not in cmd
    assert "--source" not in cmd
    # --origin default é "manual" — deve estar presente
    assert "--origin" in cmd and cmd[cmd.index("--origin") + 1] == "manual"
    # -- separador presente
    assert "--" in cmd
    assert cmd[-1] == "desc"


def test_inbox_add_body_with_leading_dash_safe(tmp_path, monkeypatch):
    """Body começando com '-' não quebra o argparse do mem por causa do '--'."""
    from engine.integrations import mem
    _stub(tmp_path / ".claude" / "bin" / "mem")
    cap = _patch_run(monkeypatch, 0, stdout='"01DEF"')
    mem.mem_inbox_add(tmp_path, title="t", body="--option-like body", mem_type="reference")
    cmd = cap["cmd"]
    dash_dash_idx = cmd.index("--")
    assert cmd[dash_dash_idx + 1] == "--option-like body"


def test_inbox_add_degrades_soft_when_binary_missing(tmp_path, monkeypatch):
    from engine.integrations import mem
    monkeypatch.setattr(mem.shutil, "which", lambda _t: None)
    res = mem.mem_inbox_add(tmp_path, title="t", body="b", mem_type="reference")
    assert res.ok is False
    assert res.data is None
    assert res.message  # mensagem 3-caminhos presente


# ── Teste real-mem (MOCK-BLINDNESS): path de escrita contra binário real ──


import os as _os


@pytest.mark.skipif(
    not (_os.path.isfile("/tmp/.claude/bin/mem") or _os.path.isfile(
        str(Path(__file__).resolve().parents[2] / ".claude" / "bin" / "mem")
    )),
    reason="binário mem não disponível — pule em CI sem vendorização",
)
def test_inbox_add_real_mem_roundtrip(tmp_path):
    """Teste real-mem: add via mem_inbox_add + asserta que aparece no inbox list.

    Copia o binário vendorizado do repo pra tmp_path/.claude/bin/mem pra
    isolar o banco de dados do inbox de produção. Sem mock — o binário real
    processa o argv e escreve no banco.
    """
    import shutil as _shutil
    from engine.integrations import mem

    # Localiza o binário vendorizado do repo (não o de /tmp usado pelo dev)
    repo_root = Path(__file__).resolve().parents[2]
    src_bin = repo_root / ".claude" / "bin" / "mem"
    if not src_bin.is_file():
        pytest.skip("binário vendorizado não encontrado no repo")

    dest_bin = tmp_path / ".claude" / "bin" / "mem"
    dest_bin.parent.mkdir(parents=True, exist_ok=True)
    _shutil.copy2(str(src_bin), str(dest_bin))
    dest_bin.chmod(0o755)

    unique_title = f"test-6b-real-mem-{tmp_path.name}"
    res = mem.mem_inbox_add(
        tmp_path,
        title=unique_title,
        body="Descrição do padrão de teste real-mem da sub-onda 6b.",
        mem_type="reference",
        importance=3,
        source="forge-evolve:TEST-REAL",
        origin="manual",
    )
    assert res.ok is True, f"mem_inbox_add falhou: {res.message}"

    # Asserta que a nota aparece no inbox list
    from engine.integrations.mem import mem_call
    list_result = mem_call(tmp_path, ["inbox", "list"])
    assert list_result.found is True
    assert list_result.exit_code == 0
    import json as _json_rt
    items = _json_rt.loads(list_result.stdout or "[]")
    titles = [it.get("title") for it in items if isinstance(it, dict)]
    assert unique_title in titles, f"nota não aparece no inbox list: {titles}"
```

- [ ] **Step 2: Rodar pra confirmar que falham**

```bash
.venv/bin/pytest tests/integrations/test_mem_wrappers.py -v -k "inbox"
```
Expected: FAIL (`AttributeError: module 'engine.integrations.mem' has no attribute 'mem_inbox_add'`).

- [ ] **Step 3: Implementar `mem_inbox_add`**

Adicione ao FIM de `engine/integrations/mem.py` (após `mem_evolve`), preservando todo o conteúdo existente intacto:

```python
def mem_inbox_add(
    project_root: Path,
    title: str,
    body: str,
    mem_type: str,
    *,
    importance: int | None = None,
    tags: str | None = None,
    source: str | None = None,
    origin: str = "manual",
) -> MemQuery:
    """`mem inbox add` — enfileira candidato curado no inbox do mem.

    O conhecimento aprovado no ``forge evolve`` entra na fila de inbox
    (anti-envenenamento G11/R12) e só vira nota ativa após ``mem evolve`` /
    ``mem inbox promote``. Reusa ``_run_or_degrade`` — degrade soft 3-caminhos.

    O separador ``"--"`` antes do ``body`` posicional é OBRIGATÓRIO (lição
    W-RULES): body começando com ``-`` quebraria o argparse do mem sem ele.
    """
    args = ["inbox", "add", "--type", mem_type, "-t", title]
    if importance is not None:
        args += ["--importance", str(importance)]
    if tags is not None:
        args += ["--tags", tags]
    if source is not None:
        args += ["--source", source]
    args += ["--origin", origin]
    args += ["--", body]
    return _run_or_degrade(project_root, args)
```

- [ ] **Step 4: Rodar pra confirmar verde**

```bash
.venv/bin/pytest tests/integrations/test_mem_wrappers.py -v
```
Expected: PASS (todos os testes do arquivo — os 8 de 6a + os novos de 6b). O teste `test_inbox_add_real_mem_roundtrip` pode ser SKIPPED em ambientes sem o vendorizado acessível — isso é esperado; o CI com vendorização o roda.

- [ ] **Step 5: Commit**

```bash
git add engine/integrations/mem.py tests/integrations/test_mem_wrappers.py
git commit -m "feat(mem): mem_inbox_add wrapper sobre mem inbox add (6b Task 1)

W-ROUTE 6b Task 1. Argv: inbox add --type mem_type -t title [opcionais]
--origin origin -- body. O '--' antes do body posicional é obrigatório
(lição W-RULES). Degrade soft 3-caminhos via _run_or_degrade. Testes:
argv mockado (completo + minimal + body-com-dash) + real-mem roundtrip."
```

---

### Task 2: Re-rota dos branches de conhecimento em `distiller.apply_proposal_to_l2`

**Files:**
- Modify: `engine/memory/distiller.py` (3 branches de L2-knowledge → `mem_inbox_add`)
- Modify: `engine/evolve.py` (`_apply_proposal` — skip do overflow-guard pra kinds de conhecimento; D5)
- Test: `tests/unit/test_memory_distiller.py` (adiciona testes de conhecimento-apply + l2.add_entry ausência)
- Test: `tests/unit/test_engine_evolve_resume.py` (adiciona teste: knowledge-proposal NÃO bloqueado por L2-overflow)
- Test: `tests/unit/test_reuse_intelligence.py` (confirma que reuse-intelligence INALTERADO)

**Interfaces:**
- Consumes: `mem_inbox_add` (Task 1); `DistillationProposal` (já existe); `is_fingerprint_rejected`, `remove_from_queue`, `_apply_forget_l1`, `apply_reuse_intelligence_proposal`, `detect_l2_overflow` (todos já existem).
- Produces:
  - `apply_proposal_to_l2` com os 3 branches de conhecimento redirecionados pro `mem inbox add`. Contrato de raise: se `mem_inbox_add` retorna `ok=False` → `raise MemoryError(...)` sem chamar `remove_from_queue`. Contrato de sucesso: `remove_from_queue` após `mem_inbox_add` retornar `ok=True`.
  - `_apply_proposal` (evolve.py) com **skip do overflow-guard** (D5): se `proposal.kind` ∈ {`promote-to-l2`, `l1-to-l2-promotion`, `consolidate-l2`}, pula `detect_l2_overflow` — esses kinds vão pro mem inbox, não escrevem L2; bloqueá-los por "L2 cheia" seria incorreto.

**Conjunto de kinds de conhecimento (constante reusada):** os 3 kinds re-roteados são uma lista compartilhada entre `distiller.py` e `evolve.py`. Para evitar duplicação literal do set em dois módulos, declare-o como constante exportável em `distiller.py` (`_KNOWLEDGE_KINDS`) e importe em `evolve.py` — reuso antes de copiar (Mandamento #3).

**Mapeamento D3 (proposal → mem inbox add):**

| campo do proposal      | argv do mem inbox add              | nota                            |
|------------------------|------------------------------------|---------------------------------|
| `proposal.title`       | `-t`                               | direto                          |
| `proposal.description` | `body` (após `--`)                 | direto                          |
| `proposal.provenance`  | `--tags`                           | `",".join(proposal.provenance)` |
| `proposal.confidence`  | `--importance`                     | `max(1, min(5, round(confidence * 4) + 1))` |
| `proposal.id`          | `--source`                         | `f"forge-evolve:{proposal.id}"` |
| (ação "a" = humano)    | `--origin manual`                  | curadoria humana                |
| `"reference"`          | `--type`                           | padrões/convenções aprendidas   |

> **Fórmula de importance — `round(confidence * 4) + 1`, não `round(confidence * 5)`.**
> Python usa banker's rounding (round-half-to-even): `round(2.5) == 2`, então
> `round(0.5 * 5) == 2` — quebraria a expectativa de confidence 0.5 → importance 3.
> A fórmula `round(confidence * 4) + 1` é monotônica e bate o midpoint corretamente:
> `0.0 → round(0)+1 = 1`; `0.5 → round(2.0)+1 = 3`; `0.8 → round(3.2)+1 = 4`;
> `1.0 → round(4)+1 = 5`. O `max(1, min(5, ...))` é cinto-de-segurança para
> confidence fora de `[0.0, 1.0]`.

- [ ] **Step 1: Escrever os testes (falhando)**

Adicione ao FINAL de `tests/unit/test_memory_distiller.py` (preserve todo o conteúdo existente):

```python
# ── Task 2 (6b): re-rota dos branches de conhecimento ────────────────────


def test_apply_promote_to_l2_calls_mem_inbox_add(tmp_path, monkeypatch):
    """promote-to-l2 deve chamar mem_inbox_add com campos mapeados (D3)."""
    import engine.memory.distiller as _dist
    called: dict = {}

    def _fake_inbox_add(project_root, title, body, mem_type, **kw):
        called["title"] = title
        called["body"] = body
        called["mem_type"] = mem_type
        called["importance"] = kw.get("importance")
        called["tags"] = kw.get("tags")
        called["source"] = kw.get("source")
        called["origin"] = kw.get("origin")
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=True, data="01ABC")

    monkeypatch.setattr(_dist, "mem_inbox_add", _fake_inbox_add)

    p = DistillationProposal(
        id="P-001",
        kind="promote-to-l2",
        title="use-stateflow",
        description="Use MutableStateFlow para screen state",
        provenance=["auth", "profile"],
        confidence=0.8,
        fingerprint="",
    )
    _dist.apply_proposal_to_l2(tmp_path, p)

    assert called["title"] == "use-stateflow"
    assert called["body"] == "Use MutableStateFlow para screen state"
    assert called["mem_type"] == "reference"
    assert called["importance"] == 4  # round(0.8 * 4) + 1 = round(3.2) + 1 = 4, clamp 1-5
    assert called["tags"] == "auth,profile"
    assert called["source"] == "forge-evolve:P-001"
    assert called["origin"] == "manual"


def test_apply_l1_to_l2_promotion_calls_mem_inbox_add(tmp_path, monkeypatch):
    """l1-to-l2-promotion (alias) segue o mesmo caminho que promote-to-l2."""
    import engine.memory.distiller as _dist
    called: list = []

    def _fake_inbox_add(project_root, title, body, mem_type, **kw):
        called.append(True)
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=True, data="01XYZ")

    monkeypatch.setattr(_dist, "mem_inbox_add", _fake_inbox_add)

    p = DistillationProposal(
        id="P-002",
        kind="l1-to-l2-promotion",
        title="mvvm-pattern",
        description="Padrão MVVM consistente",
        provenance=["onboarding"],
        confidence=0.7,
    )
    _dist.apply_proposal_to_l2(tmp_path, p)
    assert len(called) == 1


def test_apply_consolidate_l2_calls_mem_inbox_add(tmp_path, monkeypatch):
    """consolidate-l2 colapsa no mesmo caminho (merge-semantic moot com L2 abandonado)."""
    import engine.memory.distiller as _dist
    called: list = []

    def _fake_inbox_add(project_root, title, body, mem_type, **kw):
        called.append(True)
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=True, data="01DEF")

    monkeypatch.setattr(_dist, "mem_inbox_add", _fake_inbox_add)

    p = DistillationProposal(
        id="P-003",
        kind="consolidate-l2",
        title="repo-pattern",
        description="Padrão de repositório unificado",
        provenance=["payment", "cart"],
        confidence=0.9,
    )
    _dist.apply_proposal_to_l2(tmp_path, p)
    assert len(called) == 1


def test_apply_knowledge_does_not_call_l2_add_entry(tmp_path, monkeypatch):
    """Nenhum dos 3 branches de conhecimento deve chamar l2.add_entry."""
    import engine.memory.distiller as _dist
    import engine.memory.l2 as _l2

    add_entry_calls: list = []
    original_add_entry = _l2.add_entry

    def _spy_add_entry(*args, **kwargs):
        add_entry_calls.append(args)
        return original_add_entry(*args, **kwargs)

    monkeypatch.setattr(_l2, "add_entry", _spy_add_entry)

    def _fake_inbox_add(project_root, title, body, mem_type, **kw):
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=True, data="01GHI")

    monkeypatch.setattr(_dist, "mem_inbox_add", _fake_inbox_add)

    for kind in ("promote-to-l2", "l1-to-l2-promotion", "consolidate-l2"):
        _dist.apply_proposal_to_l2(
            tmp_path,
            DistillationProposal(
                id=f"P-{kind[:3]}",
                kind=kind,
                title="t",
                description="d",
                provenance=["feat-a"],
                confidence=0.6,
            ),
        )

    assert add_entry_calls == [], f"l2.add_entry foi chamado: {add_entry_calls}"


def test_apply_knowledge_raises_on_mem_inbox_add_failure(tmp_path, monkeypatch):
    """Se mem_inbox_add retorna ok=False, raise MemoryError (não drena a queue)."""
    import engine.memory.distiller as _dist
    from engine.memory import MemoryError as _MemError

    def _fake_inbox_add(project_root, title, body, mem_type, **kw):
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=False, data=None, message="mem indisponível. Três caminhos: ...")

    monkeypatch.setattr(_dist, "mem_inbox_add", _fake_inbox_add)

    p = DistillationProposal(
        id="P-004",
        kind="promote-to-l2",
        title="t",
        description="d",
        provenance=["auth"],
        confidence=0.5,
    )
    # Enfileira primeiro pra testar que não é drenada
    _dist.queue_proposal(tmp_path, p)

    with pytest.raises(_MemError):
        _dist.apply_proposal_to_l2(tmp_path, p)

    # Queue não deve ter sido drenada (raise antes do remove_from_queue)
    queue = _dist.read_proposals_queue(tmp_path)
    assert any(q.id == "P-004" for q in queue), "queue foi drenada indevidamente"


def test_apply_knowledge_importance_clamp(tmp_path, monkeypatch):
    """importance via round(confidence*4)+1, clamp [1,5]. Midpoint 0.5 → 3
    (não 2 — a fórmula evita o banker's rounding de round(0.5*5)==round(2.5)==2)."""
    import engine.memory.distiller as _dist
    importances: list = []

    def _fake_inbox_add(project_root, title, body, mem_type, **kw):
        importances.append(kw.get("importance"))
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=True, data="01JKL")

    monkeypatch.setattr(_dist, "mem_inbox_add", _fake_inbox_add)

    for confidence, expected in ((0.0, 1), (1.0, 5), (0.5, 3)):
        _dist.apply_proposal_to_l2(
            tmp_path,
            DistillationProposal(
                id=f"P-conf{int(confidence*10)}",
                kind="promote-to-l2",
                title="t",
                description="d",
                confidence=confidence,
            ),
        )

    assert importances == [1, 5, 3]


def test_apply_forget_l1_unchanged_no_mem_call(tmp_path, monkeypatch):
    """forget-l1 NÃO toca mem_inbox_add — branch estrutural inalterado."""
    import engine.memory.distiller as _dist

    inbox_add_calls: list = []

    def _spy_inbox_add(*args, **kwargs):
        inbox_add_calls.append(args)
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=True, data="x")

    monkeypatch.setattr(_dist, "mem_inbox_add", _spy_inbox_add)

    # forget-l1 exige target — simula via payload
    p = DistillationProposal(
        id="P-forget",
        kind="forget-l1",
        title="archive auth",
        description="feature obsoleta",
        provenance=["auth"],
        payload={"target": "auth"},
    )
    # O _apply_forget_l1 pode falhar sem estrutura de L1 real; catching MemoryError
    # (target não existe) é ok — o importante é que inbox_add não foi chamado.
    try:
        _dist.apply_proposal_to_l2(tmp_path, p)
    except Exception:
        pass

    assert inbox_add_calls == [], "forget-l1 não deve chamar mem_inbox_add"
```

- [ ] **Step 2: Rodar pra confirmar que falham**

```bash
.venv/bin/pytest tests/unit/test_memory_distiller.py -v -k "mem_inbox or inbox or knowledge or raises_on or importance or forget_l1"
.venv/bin/pytest tests/unit/test_engine_evolve_resume.py -v -k "skips_overflow or keeps_overflow"
```
Expected: FAIL (os branches de conhecimento ainda chamam `l2.add_entry` / `_apply_consolidate_l2`; `mem_inbox_add` e `_KNOWLEDGE_KINDS` não estão importados; o overflow-skip ainda não existe).

- [ ] **Step 3: Implementar a re-rota em `engine/memory/distiller.py`**

**3a.** Adicione o import de `mem_inbox_add` nos imports do módulo. Localize o bloco de imports existente no topo do arquivo (após `from __future__ import annotations`) e adicione:

```python
from engine.integrations.mem import mem_inbox_add
```

**3b.** Declare a constante compartilhada `_KNOWLEDGE_KINDS` logo após o set `_VALID_KINDS` existente (≈ linha 98, após o `}` que fecha `_VALID_KINDS`). Esta constante é o conjunto único de kinds de conhecimento re-roteados, reusado tanto aqui quanto em `evolve.py` (Step 3d):

```python
# W-ROUTE 6b: os 3 kinds de L2-knowledge que agora vão pro mem inbox em vez
# de escrever L2. Compartilhado com engine/evolve.py (skip do overflow-guard).
_KNOWLEDGE_KINDS = frozenset({"promote-to-l2", "l1-to-l2-promotion", "consolidate-l2"})
```

**3c.** Substitua o corpo de `apply_proposal_to_l2` a partir da linha atual `if proposal.kind in {"promote-to-l2", "l1-to-l2-promotion"}:` até (exclusive) o bloco `if proposal.kind == "forget-l1":`. O código ANTES (fingerprint-veto) e DEPOIS (forget-l1, reuse-intelligence, NotImplementedError) PERMANECE INALTERADO. Somente o trecho de conhecimento muda:

O código atual (linhas ~483–501) é:
```python
    if proposal.kind in {"promote-to-l2", "l1-to-l2-promotion"}:
        entry = L2Entry(
            id=proposal.id.replace("P-", "L2-") if proposal.id.startswith("P-") else proposal.id,
            kind="pattern",
            title=proposal.title,
            body=proposal.description,
            provenance=list(proposal.provenance),
            promoted_at=utc_now_iso(),
            promoted_from=proposal.provenance[0] if proposal.provenance else "",
            confidence=proposal.confidence,
        )
        add_entry(project_root, entry)
        remove_from_queue(project_root, proposal.id)
        return

    if proposal.kind == "consolidate-l2":
        _apply_consolidate_l2(project_root, proposal)
        remove_from_queue(project_root, proposal.id)
        return
```

Substitua por:

```python
    if proposal.kind in _KNOWLEDGE_KINDS:
        # W-ROUTE 6b: knowledge proposals vão pro mem inbox (anti-envenenamento G11).
        # O merge-semantic do consolidate-l2 é moot com L2 abandonado para conhecimento
        # — vira candidato inbox como os outros dois.
        # round(confidence*4)+1 (não *5): evita banker's rounding de round(0.5*5)==2;
        # 0.0→1, 0.5→3, 0.8→4, 1.0→5. clamp [1,5] para confidence fora de [0,1].
        importance = max(1, min(5, round(proposal.confidence * 4) + 1))
        tags = ",".join(proposal.provenance) if proposal.provenance else None
        result = mem_inbox_add(
            project_root,
            title=proposal.title,
            body=proposal.description,
            mem_type="reference",
            importance=importance,
            tags=tags or None,
            source=f"forge-evolve:{proposal.id}",
            origin="manual",
        )
        if not result.ok:
            raise MemoryError(
                f"apply_proposal_to_l2: mem_inbox_add falhou para {proposal.id} — "
                f"{result.message} — queue não drenada (raise-não-drena)."
            )
        remove_from_queue(project_root, proposal.id)
        return
```

**3d.** Implemente o skip do overflow-guard (D5) em `engine/evolve.py`. Adicione o import da constante compartilhada ao bloco `from engine.memory.distiller import (...)` existente (≈ linhas 20–29):

```python
from engine.memory.distiller import (
    DistillationProposal,
    apply_proposal_to_l2,
    compute_proposal_fingerprint,
    detect_l2_overflow,
    is_fingerprint_rejected,
    read_proposals_queue,
    record_rejection,
    remove_from_queue,
    _KNOWLEDGE_KINDS,
)
```

O código atual de `_apply_proposal` (linhas 272–291) é:

```python
def _apply_proposal(
    project_root: Path,
    p: DistillationProposal,
    cfg: dict[str, Any],
) -> bool:
    """Apply with overflow guard. Returns True on success, False on overflow pause."""
    max_mb = _l2_max_mb(cfg)
    if detect_l2_overflow(project_root, cfg):
        renderer.write(
            renderer.colored(
                f"  🛑 L2 cheia — {_format_kb(l2_size_bytes(project_root))} "
                f"/ {max_mb * 1024:.0f} KB",
                "yellow",
            )
        )
        return False

    apply_proposal_to_l2(project_root, p)
    renderer.write(renderer.colored(f"  ✓ Aplicado {p.id}.", "green"))
    return True
```

Substitua por (o skip é uma guarda ANTES do `detect_l2_overflow` — knowledge kinds vão pro mem inbox, não escrevem L2, então o overflow-check não se aplica):

```python
def _apply_proposal(
    project_root: Path,
    p: DistillationProposal,
    cfg: dict[str, Any],
) -> bool:
    """Apply with overflow guard. Returns True on success, False on overflow pause.

    W-ROUTE 6b (D5): kinds de conhecimento (``_KNOWLEDGE_KINDS``) vão pro mem
    inbox em vez de escrever L2 — o overflow-guard (`detect_l2_overflow`) não
    se aplica a eles e seria incorreto bloqueá-los por "L2 cheia". Os demais
    kinds (forget-l1, reuse-intelligence, etc.) mantêm o guard legacy.
    """
    if p.kind not in _KNOWLEDGE_KINDS:
        max_mb = _l2_max_mb(cfg)
        if detect_l2_overflow(project_root, cfg):
            renderer.write(
                renderer.colored(
                    f"  🛑 L2 cheia — {_format_kb(l2_size_bytes(project_root))} "
                    f"/ {max_mb * 1024:.0f} KB",
                    "yellow",
                )
            )
            return False

    apply_proposal_to_l2(project_root, p)
    renderer.write(renderer.colored(f"  ✓ Aplicado {p.id}.", "green"))
    return True
```

**3e.** Adicione ao FINAL de `tests/unit/test_engine_evolve_resume.py` o teste que prova o skip (knowledge-proposal NÃO bloqueado por L2-overflow):

```python
# ── Task 2 (6b / D5): overflow-skip pra kinds de conhecimento ─────────────


def test_apply_proposal_skips_overflow_for_knowledge_kind(tmp_path, monkeypatch):
    """Knowledge proposal NÃO é bloqueado por L2-overflow (D5).

    detect_l2_overflow é forçado a True; mem_inbox_add (via apply_proposal_to_l2)
    é stubado pra sucesso. O proposal de conhecimento deve aplicar (retorna True),
    provando que o guard foi pulado.
    """
    import engine.evolve as _evolve
    from engine.memory.distiller import DistillationProposal

    # Força overflow True — se o guard NÃO fosse pulado, _apply_proposal retornaria False.
    monkeypatch.setattr(_evolve, "detect_l2_overflow", lambda root, cfg: True)
    # Stuba o apply pra não tocar mem real nem L2.
    applied: list = []
    monkeypatch.setattr(
        _evolve, "apply_proposal_to_l2",
        lambda root, p: applied.append(p.id),
    )

    p = DistillationProposal(
        id="P-know",
        kind="promote-to-l2",
        title="t",
        description="d",
        provenance=["auth"],
        confidence=0.7,
    )
    result = _evolve._apply_proposal(tmp_path, p, {})
    assert result is True, "knowledge proposal foi bloqueado pelo overflow-guard (D5 falhou)"
    assert applied == ["P-know"]


def test_apply_proposal_keeps_overflow_guard_for_non_knowledge_kind(tmp_path, monkeypatch):
    """forget-l1 (não-conhecimento) AINDA respeita o overflow-guard (regression)."""
    import engine.evolve as _evolve
    from engine.memory.distiller import DistillationProposal

    monkeypatch.setattr(_evolve, "detect_l2_overflow", lambda root, cfg: True)
    applied: list = []
    monkeypatch.setattr(
        _evolve, "apply_proposal_to_l2",
        lambda root, p: applied.append(p.id),
    )

    p = DistillationProposal(
        id="P-forget",
        kind="forget-l1",
        title="t",
        description="d",
        provenance=["auth"],
        payload={"target": "auth"},
    )
    result = _evolve._apply_proposal(tmp_path, p, {})
    assert result is False, "forget-l1 deveria ser pausado por overflow (guard preservado)"
    assert applied == [], "apply não deveria rodar sob overflow para kind não-conhecimento"
```

- [ ] **Step 4: Rodar pra confirmar verde**

```bash
.venv/bin/pytest tests/unit/test_memory_distiller.py tests/unit/test_engine_evolve_resume.py -v
```
Expected: PASS (todos). Em seguida confirme que `test_reuse_intelligence.py` continua verde (o branch reuse-intelligence é inalterado):

```bash
.venv/bin/pytest tests/unit/test_reuse_intelligence.py -v
```
Expected: PASS (o `apply_proposal_to_l2` com proposal de kind `consolidate-duplicate-helper` ainda delega para `apply_reuse_intelligence_proposal` sem tocar `mem_inbox_add`).

- [ ] **Step 5: Commit**

```bash
git add engine/memory/distiller.py engine/evolve.py tests/unit/test_memory_distiller.py tests/unit/test_engine_evolve_resume.py
git commit -m "feat(distiller): re-rota knowledge proposals → mem inbox add + D5 overflow-skip (6b Task 2)

W-ROUTE 6b Task 2. Os 3 branches de L2-knowledge (promote-to-l2,
l1-to-l2-promotion, consolidate-l2) colapsam num único caminho que
chama mem_inbox_add com mapeamento D3 (title/-t, description/body,
provenance/--tags, confidence→importance=round(c*4)+1, id/--source,
--type reference, --origin manual). Raise-não-drena: MemoryError se
ok=False, sem remove_from_queue. forget-l1 e branches estruturais
INALTERADOS. D5: _apply_proposal pula detect_l2_overflow para os kinds
de conhecimento (_KNOWLEDGE_KINDS compartilhada distiller↔evolve) —
eles vão pro mem inbox, não escrevem L2. l2.add_entry órfão-pra-
conhecimento (anotado em Task 4/04-pending)."
```

---

### Task 3: `status.py` — `_render_memory` + bloco `mem` no JSON payload

**Files:**
- Modify: `engine/status.py` (`_render_memory` + `_status_payload`)
- Test: `tests/unit/test_commands_status.py` (adiciona testes de mem-stats render + degrade)
- Test: `tests/unit/test_status_json.py` (adiciona teste de bloco `mem` no JSON payload)

**Interfaces:**
- Consumes: `mem_stats(project_root: Path) -> MemQuery` (já existe em 6a); `list_active_features`, `list_archived_features` (já existem — L1 counts ficam).
- Produces:
  - `_render_memory`: seção memory com `L1 active/archived` (preservados) + resumo de `mem stats` (total, live, stale, by_type). Degrade soft: se `mem_stats` retornar `ok=False`, exibe linha placeholder sem crash.
  - `_status_payload`: bloco `"mem": {"total": N, "by_type": {...}, "live": N, "stale": N}` no campo `"memory"` (ao lado dos `l1_active`/`l1_archived` existentes).

**Código atual de `_render_memory` (linhas 199–221) para referência:**
```python
def _render_memory(project_root: Path, config: dict) -> None:
    max_mb = _config_get_path(config, ["memory", "l2", "max-size-mb"], None)
    if max_mb is None:
        max_mb = _config_get_path(config, ["memory", "L2-project", "max-size-mb"], 0.5)
    try:
        max_bytes = float(max_mb) * 1024 * 1024
    except (TypeError, ValueError):
        max_bytes = 0.5 * 1024 * 1024
    l2_path = memory_l2_path(project_root)
    if l2_path.exists():
        size_bytes = l2_size_bytes(project_root)
        pct = (size_bytes / max_bytes * 100) if max_bytes else 0
        l2_summary = f"{size_bytes / 1024:.1f} KB / {max_mb} MB ({pct:.0f}%)"
    else:
        l2_summary = "(ainda não criado)"

    body = [
        f"L2 size:          {l2_summary}",
        f"L1 active:        {len(list_active_features(project_root))}",
        f"L1 archived:      {len(list_archived_features(project_root))}",
    ]
    renderer.write("")
    renderer.write(renderer.box("memory", body))
```

**Código atual de `_status_payload` (trecho `"memory"`, linhas 345–348):**
```python
        "memory": {
            "l1_active": len(list_active_features(project_root)),
            "l1_archived": len(list_archived_features(project_root)),
        },
```

- [ ] **Step 1: Escrever os testes (falhando)**

Adicione ao FINAL de `tests/unit/test_commands_status.py`:

```python
# ── Task 3 (6b): _render_memory com mem stats ─────────────────────────────


def test_render_memory_shows_mem_stats(monkeypatch, tmp_project_root, capsys):
    """_render_memory exibe total/live/stale/by_type de mem stats."""
    from engine import status
    from engine.integrations.mem import MemQuery

    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr(
        status, "mem_stats",
        lambda root: MemQuery(
            ok=True,
            data={"total": 5, "live": 4, "stale": 1, "by_type": {"feedback": 3, "reference": 2}},
        ),
    )
    status._render_memory(tmp_project_root, {})
    out = capsys.readouterr().out
    assert "total=5" in out or "total: 5" in out
    assert "live=4" in out or "live: 4" in out
    assert "stale=1" in out or "stale: 1" in out


def test_render_memory_degrades_soft_when_mem_unavailable(monkeypatch, tmp_project_root, capsys):
    """Se mem_stats retorna ok=False, exibe placeholder sem crash."""
    from engine import status
    from engine.integrations.mem import MemQuery

    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr(
        status, "mem_stats",
        lambda root: MemQuery(ok=False, data=None, message="mem indisponível. Três caminhos: ..."),
    )
    # Não deve levantar exceção
    status._render_memory(tmp_project_root, {})
    out = capsys.readouterr().out
    # Deve ainda renderizar L1 counts (não crashar)
    assert "L1 active" in out or "l1" in out.lower()
```

Adicione ao FINAL de `tests/unit/test_status_json.py`:

```python
def test_status_json_memory_has_mem_block(tmp_forge_project, capsys, monkeypatch):
    """O payload JSON deve ter memory.mem com total/by_type/live/stale."""
    import json
    from engine.integrations.mem import MemQuery

    import engine.status as _status
    monkeypatch.setattr(
        _status, "mem_stats",
        lambda root: MemQuery(
            ok=True,
            data={"total": 2, "live": 2, "stale": 0, "by_type": {"decision": 1, "feedback": 1},
                  "by_status": {}, "inbox_pending": 0, "inbox_promoted": 0, "inbox_rejected": 0,
                  "top_accessed": []},
        ),
    )
    code, payload = _run_json(capsys, tmp_forge_project, monkeypatch)
    assert code == 0
    mem_block = payload.get("memory", {}).get("mem")
    assert mem_block is not None, "campo 'mem' ausente no bloco 'memory'"
    assert "total" in mem_block
    assert "by_type" in mem_block
    assert "live" in mem_block
    assert "stale" in mem_block


def test_status_json_memory_mem_block_absent_when_degraded(tmp_forge_project, capsys, monkeypatch):
    """Se mem_stats degrada, o bloco 'mem' pode ser None ou ausente — sem crash."""
    import json
    from engine.integrations.mem import MemQuery

    import engine.status as _status
    monkeypatch.setattr(
        _status, "mem_stats",
        lambda root: MemQuery(ok=False, data=None, message="mem indisponível"),
    )
    code, payload = _run_json(capsys, tmp_forge_project, monkeypatch)
    assert code == 0
    # memory block ainda existe com L1 counts
    assert "memory" in payload
    # mem pode ser None ou estar ausente — não é erro
    mem_block = payload.get("memory", {}).get("mem")
    assert mem_block is None or isinstance(mem_block, dict)
```

- [ ] **Step 2: Rodar pra confirmar que falham**

```bash
.venv/bin/pytest tests/unit/test_commands_status.py tests/unit/test_status_json.py -v -k "mem_stats or mem_block or render_memory or degrades"
```
Expected: FAIL (`AttributeError: module 'engine.status' has no attribute 'mem_stats'`).

- [ ] **Step 3: Implementar as mudanças em `engine/status.py`**

**3a.** Adicione o import de `mem_stats` no topo de `engine/status.py` (junto dos imports existentes de `engine.memory` e `engine.ui`):

```python
from engine.integrations.mem import mem_stats
```

**3b.** Substitua `_render_memory` inteiro (linhas 199–221) por:

```python
def _render_memory(project_root: Path, config: dict) -> None:  # noqa: ARG001
    l1_active = len(list_active_features(project_root))
    l1_archived = len(list_archived_features(project_root))

    stats_res = mem_stats(project_root)
    if stats_res.ok and isinstance(stats_res.data, dict):
        s = stats_res.data
        mem_line = (
            f"mem total={s.get('total', 0)}  live={s.get('live', 0)}"
            f"  stale={s.get('stale', 0)}"
        )
        by_type = s.get("by_type") or {}
        by_type_parts = "  ".join(f"{t}={n}" for t, n in sorted(by_type.items()))
        mem_detail = f"  ({by_type_parts})" if by_type_parts else ""
    else:
        mem_line = "mem: indisponível (rode `forge init` pra vendorizar `.claude/bin/mem`)"
        mem_detail = ""

    body = [
        f"{mem_line}{mem_detail}",
        f"L1 active:        {l1_active}",
        f"L1 archived:      {l1_archived}",
    ]
    renderer.write("")
    renderer.write(renderer.box("memory", body))
```

**3c.** Substitua o trecho `"memory"` em `_status_payload` (linhas 345–348):

```python
        "memory": {
            "l1_active": len(list_active_features(project_root)),
            "l1_archived": len(list_archived_features(project_root)),
            "mem": _mem_stats_snapshot(project_root),
        },
```

E adicione a função auxiliar `_mem_stats_snapshot` logo acima de `_status_payload` (ou ao final das funções privadas do módulo):

```python
def _mem_stats_snapshot(project_root: Path) -> dict | None:
    """Snapshot de mem stats pro JSON payload. None se mem indisponível."""
    res = mem_stats(project_root)
    if not res.ok or not isinstance(res.data, dict):
        return None
    s = res.data
    return {
        "total": s.get("total", 0),
        "by_type": s.get("by_type") or {},
        "live": s.get("live", 0),
        "stale": s.get("stale", 0),
    }
```

**Atenção:** `l2_size_bytes` e `memory_l2_path` deixam de ser usados em `_render_memory`. Verifique se têm outros callers em `status.py` antes de remover os imports — se só eram usados aqui, remova-os do bloco de imports (evite imports órfãos). A função `_config_get_path` também pode tornar-se desnecessária para `_render_memory`; verifique se tem outros callers antes de remover.

- [ ] **Step 4: Rodar pra confirmar verde**

```bash
.venv/bin/pytest tests/unit/test_commands_status.py tests/unit/test_status_json.py -v
```
Expected: PASS (todos). Depois a lane rápida completa:

```bash
.venv/bin/pytest -m "not integration and not e2e" -q | tail -3
```
Expected: verde (sem regressão de count).

- [ ] **Step 5: Commit**

```bash
git add engine/status.py tests/unit/test_commands_status.py tests/unit/test_status_json.py
git commit -m "feat(status): _render_memory usa mem stats; JSON payload ganha bloco mem (6b Task 3)

W-ROUTE 6b Task 3. _render_memory troca L2-size por resumo de mem stats
(total/live/stale/by_type); L1 active/archived ficam. Degrade soft: mem
ausente → linha placeholder sem crash. _status_payload ganha mem block
(total/by_type/live/stale) via _mem_stats_snapshot; None se degrade."
```

---

### Task 4: Doc-sync + footprint observável + 04-pending

**Files:**
- Modify: `docs/design/06-command-surface.md` (se descreve evolve/status-memory com L2)
- Modify: `CHANGELOG.md` (Unreleased)
- Modify: `README.md` (se stats de testes ou descrição de status-memory mudou)
- Modify: `docs/guides/daily-workflow.md` (se menciona L2 no contexto de evolve/status)
- Modify: `docs/design/04-pending.md` (órfão `l2.add_entry` + misnomer `apply_proposal_to_l2`)

**Interfaces:**
- Consumes: superfície nova das Tasks 1–3.
- Produces: docs e strings consistentes com a re-rota de conhecimento pro mem.

**Footprint a reconciliar (implementer confirma quais quebram rodando a lane):**

Os testes abaixo devem ser varridos ANTES de escrever código (grep ou leitura direta) pra identificar quais asserts tocam o contrato observável que mudou:

- `tests/unit/test_memory_distiller.py` — já atualizado na Task 2; verificar que nenhum teste asserta `l2.add_entry` para kinds de conhecimento (os novos asserts fazem o inverso — ausência).
- `tests/unit/test_engine_evolve_resume.py` — DOIS pontos: (a) verificar se asserta que `apply_proposal_to_l2` chama `add_entry`/escreve L2 para conhecimento; se sim, atualizar pro novo contrato (`mem_inbox_add`). (b) verificar que os testes EXISTENTES de overflow-pause usam um kind NÃO-conhecimento — se algum teste de overflow-pause usar `promote-to-l2`/`l1-to-l2-promotion`/`consolidate-l2`, ele agora FALHARÁ corretamente (o skip D5 da Task 2 faz esses kinds não pausarem). Reconcilie trocando o kind do proposal para `forget-l1` no teste de overflow-pause, ou consolide com o novo `test_apply_proposal_keeps_overflow_guard_for_non_knowledge_kind` (Task 2 Step 3e).
- `tests/unit/test_commands_evolve.py` — verificar se tem asserts sobre L2 size ou `l2.add_entry` no contexto de apply de conhecimento.
- `tests/unit/test_memory_l2.py` — usa `l2.add_entry` diretamente nos testes de L2 (não via distiller); esses FICAM intactos (testam a função L2 em si, não o caller).
- `tests/unit/test_reuse_intelligence.py:355` — chama `apply_proposal_to_l2` com proposal de kind `consolidate-duplicate-helper` → delega a `apply_reuse_intelligence_proposal`. Verificar se o monkeypatch de `mem_inbox_add` introduzido na Task 2 interfere com este teste (não deve, pois o kind é reuse-intelligence, mas confirmar).
- `tests/unit/test_status_json.py` e `tests/unit/test_commands_status.py` — já atualizados na Task 3; verificar que os testes existentes (`test_status_json_emits_valid_json_with_required_keys`) ainda passam com o bloco `mem` novo no payload.
- `tests/integration/test_qa_evolve_integration.py` — verificar se tem asserts sobre L2 size ou escrita L2 no contexto de proposals de conhecimento.

- [ ] **Step 1: Varrer o footprint e reconciliar testes que quebram**

```bash
.venv/bin/pytest tests/unit/test_engine_evolve_resume.py tests/unit/test_commands_evolve.py tests/unit/test_memory_l2.py tests/unit/test_reuse_intelligence.py tests/integration/test_qa_evolve_integration.py -v 2>&1 | tail -30
```

Para cada FAIL encontrado: leia o assert quebrado, identifique se ele testa o contrato antigo (escrita L2 para conhecimento) ou um contrato não-relacionado. Se for o contrato antigo → atualize pro novo contrato (chama `mem_inbox_add`, não `add_entry`). Se for não-relacionado → investigue se é side-effect da Task 2/3 ou bug pré-existente.

- [ ] **Step 2: Atualizar `docs/design/06-command-surface.md`**

`06-command-surface.md` é doc load-bearing (whitelist do hook PreToolUse). A edição aqui é **necessária pra doc-sync da superfície (Mandamento #6) — não é revisita de decisão**: nenhuma decisão de `01-decisions.md` muda; apenas a documentação do comportamento observável de `forge evolve`/`forge status` é sincronizada com o código das Tasks 2–3 no mesmo ciclo. Sem cerimônia "Revisita decisão N".

Localize a descrição de `forge evolve` e `forge status` (seção memory). Se mencionar "L2" no contexto de proposals de conhecimento aprovadas, atualize para refletir que aprovação de conhecimento emite `mem inbox add` (candidato curado, não persiste direto no L2). Se mencionar a linha de L2-size no status, atualize para "resumo de mem stats". Exemplo de adição:

```markdown
- `forge evolve` (knowledge proposals): ao aprovar ("a") um proposal de
  conhecimento (`promote-to-l2` / `l1-to-l2-promotion` / `consolidate-l2`),
  emite `mem inbox add` (candidato curado). O conhecimento só vira nota ativa
  após `mem evolve` / `mem inbox promote`. Reuse-intelligence e `forget-l1`
  não são afetados (W-ROUTE 6b).
- `forge status` (seção memory): exibe resumo de `mem stats`
  (total/live/stale/by_type) + L1 active/archived. JSON payload tem bloco
  `memory.mem` com total/by_type/live/stale.
```

- [ ] **Step 3: Atualizar `docs/guides/daily-workflow.md`**

Se o guia menciona que `forge evolve` (ação "a") escreve direto no L2, reescreva para o novo fluxo: aprovação → `mem inbox add` → curadoria posterior via `mem inbox promote` ou `mem evolve`. Se não menciona L2, registre "sem mudança" no commit body.

- [ ] **Step 4: Atualizar `README.md`**

Se a seção de `forge status` no README menciona a linha de L2-size na seção memory, alinhe com `mem stats`. Se não muda stats/contagem de comandos, sem mais.

- [ ] **Step 5: Atualizar `CHANGELOG.md` (Unreleased)**

Adicione em `### Changed`:

```markdown
- `forge evolve` (knowledge proposals): aprovação de `promote-to-l2` /
  `l1-to-l2-promotion` / `consolidate-l2` agora emite `mem inbox add` em vez
  de escrever direto no L2 (anti-envenenamento G11). O conhecimento entra na
  fila de inbox do mem e fica disponível via `mem evolve` / `mem inbox promote`
  (W-ROUTE 6b).
- `forge status` (seção memory): linha de L2-size substituída por resumo de
  `mem stats` (total/live/stale/by_type). Payload JSON ganha bloco
  `memory.mem`. Degrade soft se mem indisponível (W-ROUTE 6b).
```

E em `### Added`:

```markdown
- `mem_inbox_add` — wrapper sobre `mem inbox add` na camada de integração
  (`engine/integrations/mem.py`). Argv: `inbox add --type mem_type -t title
  [opcionais] --origin origin -- body`. Separador `--` antes do body é
  obrigatório (lição W-RULES). Degrade soft via `_run_or_degrade` (W-ROUTE 6b).
```

- [ ] **Step 6: Anotar órfão e misnomer em `docs/design/04-pending.md`**

Adicione **exatamente duas** entradas a `docs/design/04-pending.md` (NÃO anote D5/overflow-skip como limitação — D5 É implementado na Task 2, não há divergência pendente):

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

- [ ] **Step 7: Rodar a lane completa**

```bash
.venv/bin/pytest -m "not integration and not e2e" -q | tail -3
.venv/bin/pytest -m "integration" -q | tail -3
```
Expected: verde nas duas lanes (sem regressão de count além de eventuais ajustes declarados no footprint desta task).

- [ ] **Step 8: Commit**

```bash
git add docs/design/06-command-surface.md CHANGELOG.md README.md docs/guides/daily-workflow.md docs/design/04-pending.md
git commit -m "docs(w-route): doc-sync + footprint observável + 04-pending (6b Task 4)

CHANGELOG + command-surface + guide + 04-pending alinhados ao re-roteamento
de knowledge proposals pro mem inbox. Órfão l2.add_entry e misnomer
apply_proposal_to_l2 anotados em 04-pending. Footprint de testes
reconciliado: asserts de escrita L2 para conhecimento atualizados pro novo
contrato (mem_inbox_add); test_memory_l2 e test_reuse_intelligence intactos."
```

---

## Self-Review

### Cobertura D1–D6

- **D1 (conjunto re-roteado — só 4 kinds L2-knowledge):** Task 2 colapsa `promote-to-l2`, `l1-to-l2-promotion`, `consolidate-l2` num único caminho `mem_inbox_add`. `distill-l2` permanece `NotImplementedError` (inalterado). Forget-l1 e reuse-intelligence inalterados (confirmado pelo teste `test_apply_forget_l1_unchanged_no_mem_call` e pela continuidade de `test_reuse_intelligence.py`).
- **D2 ("aplicar" enfileira, não persiste):** Task 2 chama `mem_inbox_add` (inbox = fila de candidatos); só vira nota ativa via `mem evolve`/`mem inbox promote`. Semântica documentada em CHANGELOG e command-surface na Task 4.
- **D3 (mapeamento de campos + `--type reference`):** Task 1 constrói o argv (com `--importance` forma longa) e os testes assertam cada campo: `-t`←title, body←description (após `--`), `--tags`←",".join(provenance), `--importance`←`max(1, min(5, round(conf*4)+1))`, `--source`←`forge-evolve:{id}`, `--origin manual`, `--type reference`. **Fórmula `round(conf*4)+1`, não `round(conf*5)`** — esta última sofre banker's rounding (`round(0.5*5)==round(2.5)==2`, errado; o esperado é 3). Task 2 confirma os valores via `test_apply_promote_to_l2_calls_mem_inbox_add` (0.8→4) e `test_apply_knowledge_importance_clamp` (`[1, 5, 3]` para confidence `[0.0, 1.0, 0.5]`).
- **D4 (status: L2-size → mem stats + bloco JSON):** Task 3 substitui `_render_memory` inteiro e adiciona `_mem_stats_snapshot` no `_status_payload`. Testes cobrem: render com stats, degrade sem crash, bloco JSON presente e bloco JSON com None em degrade.
- **D5 (overflow-skip pra kinds de conhecimento — IMPLEMENTADO):** Task 2 Step 3d altera `_apply_proposal` em `engine/evolve.py`: ANTES do `detect_l2_overflow`, pula o overflow-guard se `p.kind in _KNOWLEDGE_KINDS` (os 3 kinds vão pro mem inbox, não escrevem L2 — bloqueá-los por "L2 cheia" seria incorreto). O loop INTERATIVO do `forge evolve` (single-by-single, checkpoint-resume) permanece intacto — 6b NÃO o torna stateless; apenas o overflow-guard ganha o skip para conhecimento. `_KNOWLEDGE_KINDS` é constante compartilhada (declarada em `distiller.py`, importada em `evolve.py` — reuso, não cópia). Provado por `test_apply_proposal_skips_overflow_for_knowledge_kind` (knowledge não bloqueado mesmo com overflow True) + `test_apply_proposal_keeps_overflow_guard_for_non_knowledge_kind` (forget-l1 ainda pausa — regression).
- **D6 (`l2.add_entry` órfão, misnomer anotados):** Task 4 adiciona ambos em 04-pending explicitamente.

### Sem placeholder

Todo passo de código contém código Python completo, verbatim. Comandos têm expected output. Nenhum `# TODO`, `# placeholder`, `pass` de stub, ou `...` no código dos steps.

### Consistência de assinaturas `mem_inbox_add`

| Ponto de uso | Assinatura / chamada |
|---|---|
| Task 1 — implementação | `mem_inbox_add(project_root, title, body, mem_type, *, importance=None, tags=None, source=None, origin="manual") -> MemQuery` |
| Task 1 — teste mock | `mem.mem_inbox_add(tmp_path, title=..., body=..., mem_type="reference", importance=4, tags=..., source=..., origin="manual")` |
| Task 1 — teste real-mem | `mem.mem_inbox_add(tmp_path, title=unique_title, body=..., mem_type="reference", importance=3, source=..., origin="manual")` |
| Task 2 — distiller | `mem_inbox_add(project_root, title=proposal.title, body=proposal.description, mem_type="reference", importance=importance, tags=tags or None, source=f"forge-evolve:{proposal.id}", origin="manual")` |
| Task 2 — teste distiller | `monkeypatch.setattr(_dist, "mem_inbox_add", _fake_inbox_add)` — spy injetado antes de `apply_proposal_to_l2` |
| Task 3 — import | `from engine.integrations.mem import mem_stats` (não `mem_inbox_add` — status usa stats, não add) |

Assinaturas idênticas entre implementação (Task 1) e todos os call-sites (Task 2). O distiller importa `mem_inbox_add` de `engine.integrations.mem` — disciplina Decisão 22 (zero runtime dep em outra ferramenta via import direto; a fronteira é o subprocess no `mem_call`).

### Reuso (Mandamento #3)

- `mem_inbox_add` (Task 1) compõe sobre `_run_or_degrade`/`mem_call` existentes — zero subprocess novo, estende a camada D3 de 6a no mesmo módulo, padrão verbatim dos 5 wrappers de 6a.
- `_KNOWLEDGE_KINDS` (Task 2) é constante única declarada em `distiller.py` e importada em `evolve.py` — o set dos 3 kinds não é duplicado em dois módulos.

### Lição MOCK-BLINDNESS (teste real-mem)

Task 1 inclui `test_inbox_add_real_mem_roundtrip`: copia o binário vendorizado do repo para `tmp_path`, chama `mem_inbox_add` sem mock, asserta que a nota aparece em `mem inbox list`. O teste é marcado com `skipif` quando o vendorizado não está disponível (ambientes CI sem o asset). A disciplina é: paths que ESCREVEM no mem exigem ao menos um teste sem mock — um bug de quoting/arg que o monkeypatch silencia (ex.: `body` começando com `-` sem `--`) só é pego contra o binário real.

### Footprint por contrato (não por import)

Task 4 varre explicitamente: `test_engine_evolve_resume.py` (Task 2 já adicionou os 2 testes de overflow-skip; Task 4 confirma que testes legacy de overflow-pause não usam kind de conhecimento), `test_commands_evolve.py`, `test_memory_l2.py` (intacto — testa `l2.add_entry` direto, não via distiller), `test_reuse_intelligence.py:355` (kind reuse-intelligence — inalterado), `test_qa_evolve_integration.py`, e os testes de status (já atualizados na Task 3). O implementer confirma quais quebram rodando a lane antes de editar.
