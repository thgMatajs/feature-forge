# W-ROUTE 6d — re-rota do `forge undo` pra knowledge kinds — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer `forge undo` de um evolve-apply de conhecimento de fato reverter — `mem inbox reject <id>` em vez do no-op silencioso atual (que só mexe em L2).

**Architecture:** Captura o inbox-id no momento do apply (`mem --json inbox add` já o retorna), persiste-o no evento de history `evolve-apply`, e o `_undo_evolve` lê esse id de volta pra chamar um novo wrapper `mem_inbox_reject`. O path L2 legado fica intacto pros kinds não-conhecimento e pros eventos pré-6d. É um bugfix → TDD com regression test VERMELHO primeiro.

**Tech Stack:** Python core; subprocess wrapper sobre o binário vendorizado `mem` via `engine/integrations/mem.py::_run_or_degrade` (força `--json`, degrade-soft 3-caminhos); pytest (`.venv/bin/pytest`, canonical).

## Global Constraints

- `.venv/bin/pytest` é o interpretador canonical — NUNCA o system pytest (falsos negativos por falta de json5/deps).
- Voz mentor-calmo em toda microcopy de gate/aviso. Sem voz corporativa, sem emoji decorativo.
- Nenhum VALIDATOR pode importar/chamar mem (Decisão de determinismo, guard em `tests/unit/test_validators_determinism.py`). `undo.py` é HANDLER, não validator — pode chamar mem. NÃO mover nada de undo pra um validator.
- Degrade-soft: se o `mem` está ausente/timeout/erro, NUNCA surfar "forge init"; reportar honesto e não fingir sucesso.
- Scope tight (decisão do usuário 2026-06-29): 6d é SÓ a re-rota do undo. NÃO renomear `apply_proposal_to_l2` (misnomer fica pra sweep próprio). NÃO tocar arquivos fora dos listados.
- Report honesto: se o reject falha (mem degrade OU candidato já promovido a nota ativa), o undo retorna falha e NÃO grava undo-log de sucesso.

---

### Task 1: helper `mem_inbox_reject` em `engine/integrations/mem.py`

**Files:**
- Modify: `engine/integrations/mem.py` (adicionar função após `mem_inbox_add`, ~linha 284; incluir em `__all__` se houver)
- Test: `tests/integrations/test_mem_wrappers.py`

**Interfaces:**
- Consumes: `_run_or_degrade(project_root: Path, args: list[str]) -> MemQuery` (já existe; força `--json` ANTES do subcomando e parseia stdout).
- Produces: `mem_inbox_reject(project_root: Path, inbox_id: str) -> MemQuery` — wrapper sobre `mem inbox reject <inbox_id>`.

- [ ] **Step 1: VERIFICAÇÃO EMPÍRICA do shape de saída** (NÃO assumir). Rode contra o mem vendorizado real um reject de um id inexistente e um válido, observando se `mem --json inbox reject <id>` emite JSON ou texto, e o exit code:
  - `./.claude/bin/mem --json inbox reject NAO_EXISTE_XYZ ; echo "exit=$?"`
  - Confirme se `_run_or_degrade` (que faz `json.loads(stdout or "null")`) tolera a saída. Se o reject emitir texto não-JSON em sucesso, o `_run_or_degrade` pode marcar ok=False indevidamente — nesse caso, e SÓ nesse caso, adicione um caminho que não force `--json` pro reject (documente a razão num comentário). Caso contrário, mantenha o uso padrão de `_run_or_degrade`.

- [ ] **Step 2: Write the failing test**

```python
def test_mem_inbox_reject_invokes_reject_subcommand(tmp_path, monkeypatch):
    captured = {}

    def fake_run_or_degrade(project_root, args):
        captured["args"] = args
        from engine.integrations.mem import MemQuery
        return MemQuery(ok=True, data={"status": "rejected"})

    monkeypatch.setattr(
        "engine.integrations.mem._run_or_degrade", fake_run_or_degrade
    )
    from engine.integrations.mem import mem_inbox_reject
    res = mem_inbox_reject(tmp_path, "01ABCDEF")
    assert res.ok is True
    assert captured["args"] == ["inbox", "reject", "01ABCDEF"]
```

(Se a verificação do Step 1 exigir non-json, ajuste a asserção de `captured["args"]`/chamada conforme o caminho escolhido, documentando.)

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/integrations/test_mem_wrappers.py::test_mem_inbox_reject_invokes_reject_subcommand -v`
Expected: FAIL com `ImportError`/`AttributeError` (mem_inbox_reject não existe).

- [ ] **Step 4: Write minimal implementation**

```python
def mem_inbox_reject(project_root: Path, inbox_id: str) -> MemQuery:
    """`mem inbox reject <id>` — descarta um candidato do inbox do mem.

    Usado pelo `forge undo` pra reverter um evolve-apply de conhecimento
    (W-ROUTE 6d): o id do candidato foi capturado no apply e gravado no
    evento `evolve-apply`. Reusa ``_run_or_degrade`` — degrade soft 3-caminhos,
    sem surfar "forge init". Se o candidato já foi promovido a nota ativa ou
    já não está no inbox, o mem retorna erro e ``MemQuery.ok`` vem False —
    o caller (undo) reporta honesto, sem fingir sucesso.
    """
    return _run_or_degrade(project_root, ["inbox", "reject", inbox_id])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/integrations/test_mem_wrappers.py::test_mem_inbox_reject_invokes_reject_subcommand -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add engine/integrations/mem.py tests/integrations/test_mem_wrappers.py
git commit -m "feat(mem): mem_inbox_reject wrapper (W-ROUTE 6d Task 1)"
```

---

### Task 2: capturar inbox-id no apply e persistir no evento `evolve-apply`

**Files:**
- Modify: `engine/memory/distiller.py:485-509` (`apply_proposal_to_l2` — retornar o inbox-id pro knowledge branch)
- Modify: `engine/evolve.py:273-299` (`_apply_proposal` — propagar o id) e `engine/evolve.py:511-536` (call-site `action == "a"` + `_record_history_event`)
- Test: `tests/unit/test_memory_distiller.py`, `tests/unit/test_engine_evolve_resume.py`

**Interfaces:**
- Consumes: `mem_inbox_add(...) -> MemQuery` (já retorna `data={"id": ..., "status": "pending"}` no sucesso, confirmado empiricamente 2026-06-29).
- Produces:
  - `apply_proposal_to_l2(project_root, proposal) -> str | None` — retorna o `mem-inbox-id` (de `result.data["id"]`) no branch de knowledge kinds; `None` em TODOS os outros branches (forget-l1, reuse-intelligence, etc.). Hoje retorna `None` implícito em todos.
  - `_apply_proposal(project_root, p, cfg) -> tuple[bool, str | None]` — `(True, inbox_id)` no sucesso de knowledge; `(True, None)` no sucesso L2/reuse; `(False, None)` na pausa por overflow. (Hoje retorna `bool`.)

- [ ] **Step 1: Write the failing test (distiller retorna o id)**

```python
def test_apply_proposal_to_l2_returns_inbox_id_for_knowledge(tmp_path, monkeypatch):
    # knowledge proposal → mem inbox add → retorna o id capturado
    from engine.integrations import mem as mem_mod
    from engine.memory import distiller as dist

    def fake_inbox_add(project_root, **kwargs):
        return mem_mod.MemQuery(ok=True, data={"id": "01INBOXID", "status": "pending"})

    monkeypatch.setattr(dist, "mem_inbox_add", fake_inbox_add)
    monkeypatch.setattr(dist, "remove_from_queue", lambda *a, **k: None)
    monkeypatch.setattr(dist, "is_fingerprint_rejected", lambda *a, **k: False)

    p = _make_knowledge_proposal()  # helper local: kind em _KNOWLEDGE_KINDS, fingerprint set
    inbox_id = dist.apply_proposal_to_l2(tmp_path, p)
    assert inbox_id == "01INBOXID"
```

(Use/estenda os helpers de construção de proposal já existentes em `test_memory_distiller.py`. Se não houver, crie um `_make_knowledge_proposal()` mínimo consistente com `DistillationProposal`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_memory_distiller.py::test_apply_proposal_to_l2_returns_inbox_id_for_knowledge -v`
Expected: FAIL (retorna `None`, não `"01INBOXID"`).

- [ ] **Step 3: Implement — distiller retorna o id**

Em `engine/memory/distiller.py`, no branch `if proposal.kind in _KNOWLEDGE_KINDS:` (linha ~485), após o guard `if not result.ok: raise ...` e `remove_from_queue(...)`, troque o `return` nu por retornar o id capturado:

```python
        remove_from_queue(project_root, proposal.id)
        inbox_id = None
        if isinstance(result.data, dict):
            inbox_id = result.data.get("id")
        return inbox_id
```

Garanta que TODOS os outros caminhos da função retornem `None` explicitamente (forget-l1, reuse-intelligence, e o `raise NotImplementedError` permanece). A assinatura passa a `-> str | None`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_memory_distiller.py::test_apply_proposal_to_l2_returns_inbox_id_for_knowledge -v`
Expected: PASS

- [ ] **Step 5: Write the failing test (evento evolve-apply carrega o id)**

```python
def test_evolve_apply_records_mem_inbox_id(tmp_path, monkeypatch):
    # aplicar um knowledge proposal grava routed-to=mem-inbox + mem-inbox-id no history _evolve
    from engine import evolve as ev

    monkeypatch.setattr(ev, "apply_proposal_to_l2", lambda root, p: "01INBOXID")
    # evitar overflow guard pro branch knowledge (não se aplica), mas garantir caminho:
    recorded = {}
    def fake_record(project_root, kind, proposal_id, extras=None):
        recorded[kind] = {"proposal-id": proposal_id, **(extras or {})}
    monkeypatch.setattr(ev, "_record_history_event", fake_record)

    p = _make_knowledge_proposal()
    ok, inbox_id = ev._apply_proposal(tmp_path, p, cfg={})
    assert ok is True
    assert inbox_id == "01INBOXID"
```

E um teste de integração leve do call-site (que o `run`-loop grava o extra). Se testar o loop inteiro for custoso, cubra via o teste de `_apply_proposal` acima + um assert direto no `_record_history_event` call no loop (ver Step 7).

- [ ] **Step 6: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_engine_evolve_resume.py::test_evolve_apply_records_mem_inbox_id -v`
Expected: FAIL (`_apply_proposal` retorna `bool`, não tupla).

- [ ] **Step 7: Implement — propagar o id em evolve.py**

Em `_apply_proposal` (273-299): capture o retorno de `apply_proposal_to_l2` e retorne a tupla.

```python
    inbox_id = apply_proposal_to_l2(project_root, p)
    renderer.write(renderer.colored(f"  ✓ Aplicado {p.id}.", "green"))
    return True, inbox_id
```

E no early-return de overflow (linha ~295): `return False, None`.

No call-site `action == "a"` (linha 511-536): desempacote e thread no history event:

```python
        if action == "a":
            success, inbox_id = _apply_proposal(project_root, p, cfg)
            if not success:
                # ... bloco de overflow inalterado ...
                return 0
            # M-001 (plan-audit r1): um apply de conhecimento NÃO toca L2 —
            # não carregar l2-size-after-bytes nesse branch (evita um evento
            # evolve-apply que mistura semântica de dois substratos).
            if inbox_id:
                extras = {"routed-to": "mem-inbox", "mem-inbox-id": inbox_id}
            else:
                extras = {"l2-size-after-bytes": l2_size_bytes(project_root)}
            _record_history_event(
                project_root,
                "evolve-apply",
                p.id,
                extras=extras,
            )
            cursor += 1
            continue
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_engine_evolve_resume.py tests/unit/test_memory_distiller.py -v`
Expected: PASS (e nenhuma regressão nos testes existentes desses arquivos).

- [ ] **Step 9: Commit**

```bash
git add engine/memory/distiller.py engine/evolve.py tests/unit/test_memory_distiller.py tests/unit/test_engine_evolve_resume.py
git commit -m "feat(evolve,distiller): captura mem-inbox-id no apply e grava no evento evolve-apply (W-ROUTE 6d Task 2)"
```

---

### Task 3: `_undo_evolve` re-rota pro `mem inbox reject` (regression RED first)

**Files:**
- Modify: `engine/undo.py:353-402` (`_undo_evolve`) + adicionar helper `_evolve_apply_event_for` perto de `_last_evolve_apply` (245-250); adicionar import `mem_inbox_reject`
- Test: `tests/unit/test_engine_undo_resume.py` (ou o arquivo de teste de undo existente; se não houver caso pra `_undo_evolve`, crie um módulo `tests/unit/test_engine_undo_knowledge.py`)

**Interfaces:**
- Consumes: `mem_inbox_reject(project_root, inbox_id) -> MemQuery` (Task 1); `read_history(slug, project_root, tail=0)` (já importado em undo via l1).
- Produces: helper `_evolve_apply_event_for(project_root: Path, proposal_id: str) -> dict | None` — o evento `evolve-apply` mais recente cujo `proposal-id == proposal_id`.

- [ ] **Step 1: Write the failing REGRESSION test (o bug: knowledge undo é no-op)**

```python
def test_undo_evolve_knowledge_rejects_mem_inbox(tmp_path, monkeypatch):
    # Dado um evento evolve-apply roteado pro mem-inbox, o undo deve chamar
    # mem_inbox_reject com o id capturado — NÃO l2_remove_entry (no-op atual).
    from engine import undo as und

    monkeypatch.setattr(
        und, "_evolve_apply_event_for",
        lambda root, pid: {"proposal-id": pid, "routed-to": "mem-inbox", "mem-inbox-id": "01INBOXID"},
    )
    reject_calls = []
    monkeypatch.setattr(
        und, "mem_inbox_reject",
        lambda root, iid: (reject_calls.append(iid) or _ok_memquery()),
    )
    l2_calls = []
    monkeypatch.setattr(und, "l2_remove_entry", lambda *a, **k: l2_calls.append(a))
    monkeypatch.setattr(und.question, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(und, "_append_undo_log", lambda *a, **k: None)

    ok = und._undo_evolve(tmp_path, "P-001")
    assert ok is True
    assert reject_calls == ["01INBOXID"]
    assert l2_calls == []  # caminho L2 NÃO é tocado pra knowledge
```

(Defina `_ok_memquery()` retornando `MemQuery(ok=True, data={"status":"rejected"})`.)

- [ ] **Step 2: Write the honest-failure test (degrade OU já-promovido → não finge sucesso)**

```python
def test_undo_evolve_knowledge_reject_failure_reports_honest(tmp_path, monkeypatch):
    from engine import undo as und
    monkeypatch.setattr(
        und, "_evolve_apply_event_for",
        lambda root, pid: {"proposal-id": pid, "routed-to": "mem-inbox", "mem-inbox-id": "01INBOXID"},
    )
    monkeypatch.setattr(
        und, "mem_inbox_reject",
        lambda root, iid: _fail_memquery(),  # ok=False (degrade ou já promovido)
    )
    undo_logs = []
    monkeypatch.setattr(und, "_append_undo_log", lambda *a, **k: undo_logs.append(k.get("target")))
    monkeypatch.setattr(und.question, "confirm", lambda *a, **k: True)

    ok = und._undo_evolve(tmp_path, "P-001")
    assert ok is False
    assert undo_logs == []  # NÃO grava undo-log de sucesso
```

- [ ] **Step 3: Write the regression-preservation test (evento legado/L2 → caminho L2 intacto)**

```python
def test_undo_evolve_legacy_event_uses_l2_path(tmp_path, monkeypatch):
    from engine import undo as und
    # evento sem mem-inbox-id (pré-6d) → fallback L2
    monkeypatch.setattr(und, "_evolve_apply_event_for", lambda root, pid: None)
    monkeypatch.setattr(und.question, "confirm", lambda *a, **k: True)
    removed = []
    monkeypatch.setattr(und, "l2_remove_entry", lambda root, tid: removed.append(tid))
    monkeypatch.setattr(und, "_append_undo_log", lambda *a, **k: None)
    # L2 path exige l2_path existente — mocke memory_l2_path pra um arquivo tmp existente
    l2 = tmp_path / "L2.yaml"; l2.write_text("entries: []\n")
    monkeypatch.setattr(und, "memory_l2_path", lambda root: l2)

    ok = und._undo_evolve(tmp_path, "P-001")
    assert ok is True
    assert removed == ["L2-001"]  # mangling P- → L2- preservado no path legado
```

- [ ] **Step 4: Run the three tests to verify they FAIL**

Run: `.venv/bin/pytest tests/unit/test_engine_undo_knowledge.py -v`
Expected: FAIL — `_evolve_apply_event_for`/`mem_inbox_reject` não existem/não são chamados; o `_undo_evolve` atual ignora o roteamento e sempre vai pro L2.

- [ ] **Step 5: Implement — helper de lookup + import**

No topo de `engine/undo.py`, adicione o import:

```python
from engine.integrations.mem import mem_inbox_reject
```

Perto de `_last_evolve_apply` (245-250), adicione:

```python
def _evolve_apply_event_for(
    project_root: Path, proposal_id: str
) -> Optional[dict[str, Any]]:
    """O evento `evolve-apply` mais recente com `proposal-id` == proposal_id.

    Usado por `_undo_evolve` pra descobrir se o apply foi roteado pro mem inbox
    (W-ROUTE 6d) e recuperar o `mem-inbox-id` capturado no momento do apply.
    """
    history = read_history("_evolve", project_root, tail=0)
    for entry in reversed(history):
        if (
            entry.get("kind") == "evolve-apply"
            and entry.get("proposal-id") == proposal_id
        ):
            return entry
    return None
```

- [ ] **Step 6: Implement — re-rota em `_undo_evolve`**

Reescreva `_undo_evolve` (353-402) pra ramificar por roteamento. O bloco do mem vem ANTES do path L2; o L2 fica como fallback (evento legado/sem id):

```python
def _undo_evolve(project_root: Path, proposal_id: str) -> bool:
    event = _evolve_apply_event_for(project_root, proposal_id)
    inbox_id = (event or {}).get("mem-inbox-id")
    routed_to = (event or {}).get("routed-to")

    # W-ROUTE 6d: apply roteado pro mem inbox → reverter via `mem inbox reject`.
    if routed_to == "mem-inbox" and inbox_id:
        renderer.write(f"  proposal: {proposal_id}")
        renderer.write(f"  mem inbox-id: {inbox_id}")
        if not question.confirm(
            f"Reverter aplicação de {proposal_id} (rejeitar candidato no mem inbox)?",
            default=False,
        ):
            return False
        result = mem_inbox_reject(project_root, inbox_id)
        if not result.ok:
            renderer.write(renderer.colored(
                "  Não consegui rejeitar o candidato no mem — pode já ter sido "
                "promovido a nota ativa, ou o mem está indisponível. Nada foi "
                "revertido. Confira com `mem inbox list` / reverta a nota via mem.",
                "yellow",
            ))
            return False
        renderer.write(renderer.colored(
            f"  ✓ candidato {inbox_id} rejeitado no mem inbox.", "green"
        ))
        _append_undo_log(
            project_root,
            kind="undo",
            target=f"evolve-apply:{proposal_id}",
            reverted_at=_utc_now_iso(),
            slug="_evolve",
        )
        return True

    # Fallback legado: apply em L2 (kinds não-conhecimento ou eventos pré-6d).
    l2_path = memory_l2_path(project_root)
    bak = l2_path.with_suffix(l2_path.suffix + ".bak")
    if not l2_path.exists():
        renderer.write(renderer.colored("  L2 não existe.", "yellow"))
        return False

    renderer.write(f"  proposal: {proposal_id}")
    renderer.write(f"  L2:       {l2_path}")
    if bak.exists():
        renderer.write(f"  backup:   {bak} (será usado pra restaurar)")

    if not question.confirm(
        f"Reverter aplicação de {proposal_id}?", default=False
    ):
        return False

    target_id = proposal_id.replace("P-", "L2-") if proposal_id.startswith("P-") else proposal_id
    try:
        l2_remove_entry(project_root, target_id)
    except (KeyError, OSError, YamlIOError, MemoryError) as exc:
        renderer.write(renderer.colored(
            f"  remoção da entrada falhou — {exc}", "yellow"
        ))

    if bak.exists() and question.confirm(
        "Restaurar L2 inteiro a partir do .bak (sobrescreve mudanças "
        "posteriores)?",
        default=False,
    ):
        shutil.copy2(bak, l2_path)
        renderer.write(renderer.colored("  ✓ L2 restaurado do .bak.", "green"))
    else:
        renderer.write(renderer.colored(
            f"  ✓ entrada {target_id} removida.", "green"
        ))

    _append_undo_log(
        project_root,
        kind="undo",
        target=f"evolve-apply:{proposal_id}",
        reverted_at=_utc_now_iso(),
        slug="_evolve",
    )
    return True
```

NOTA: `l2_remove_entry` é o nome importado (`from engine.memory.l2 import remove_entry as l2_remove_entry` em undo.py:40). Os testes monkeypatcham `und.l2_remove_entry` e `und.mem_inbox_reject` — os nomes precisam existir no namespace do módulo `undo`.

ALÉM do `_undo_evolve`, no MESMO arquivo `engine/undo.py`, corrija a microcopy stale (H-001, plan-audit r1) — pós-6d o caminho de conhecimento não mexe em L2, e `undo` é recovery: a UI não pode mentir sobre o substrato:
- Opção de menu (linha ~693): troque `"4": "evolve apply — reverter aplicação L2",` por `"4": "evolve apply — reverter aplicação de proposta (L2 ou mem inbox)",`.
- Docstring de cabeçalho do módulo (linha ~9): troque `  4. evolve apply (per id)   — restore L2 backup and drop the entry` por `  4. evolve apply (per id)   — revert L2 entry OR reject the mem-inbox candidate`.

- [ ] **Step 7: Run the three tests to verify they PASS**

Run: `.venv/bin/pytest tests/unit/test_engine_undo_knowledge.py -v`
Expected: PASS

- [ ] **Step 8: Run undo + evolve full lane (sem regressão)**

Run: `.venv/bin/pytest tests/unit/test_engine_undo_resume.py tests/unit/test_engine_evolve_resume.py tests/unit/test_memory_distiller.py tests/integrations/test_mem_wrappers.py -q`
Expected: tudo PASS.

- [ ] **Step 9: Commit**

```bash
git add engine/undo.py tests/unit/test_engine_undo_knowledge.py
git commit -m "fix(undo): re-rota evolve-apply de conhecimento pra mem inbox reject (W-ROUTE 6d Task 3)"
```

---

### Task 4: doc-sync + limpeza dos probes

**Files:**
- Modify: `docs/design/04-pending.md` (§W-ROUTE 6b/6c)
- Modify: `CHANGELOG.md` (Unreleased)
- Modify: `README.md` (somente se o count de testes mudou — re-confirme)
- Cleanup: rejeitar os 2 candidatos-probe do inbox do mem deste repo

**Interfaces:** nenhuma (doc + cleanup).

- [ ] **Step 1: 04-pending — marcar o bug como RESOLVIDO em 6d**

Na entrada "**`forge undo` de evolve-apply é no-op pra knowledge kinds (W-ROUTE 6b)**" (linhas ~79-86), prefixe a resolução, preservando o histórico (append, não apague o texto original do gap). Adicione ao fim do parágrafo:

```
  RESOLVIDO em 6d: o apply captura o `mem-inbox-id` (de `mem --json inbox add`)
  e grava em `routed-to: mem-inbox` + `mem-inbox-id` no evento `evolve-apply`;
  `_undo_evolve` lê de volta e chama `mem inbox reject <id>`. Report honesto se
  o candidato já foi promovido ou o mem está indisponível (não finge sucesso).
  O path L2 legado fica intacto pros kinds não-conhecimento e eventos pré-6d.
```

A entrada "**`apply_proposal_to_l2` misnomer (W-ROUTE 6b)**" PERMANECE como PENDENTE — NÃO a edite (decisão do usuário: rename fica pra sweep próprio).

- [ ] **Step 2: CHANGELOG — entrada Unreleased**

Sob `## [Unreleased]` → `### Fixed`:

```
- `forge undo` de evolve-apply de conhecimento agora reverte de fato via
  `mem inbox reject` (W-ROUTE 6d) — antes era no-op silencioso pós-6b (o
  candidato persistia no inbox do mem). O id é capturado no apply e gravado
  no evento `evolve-apply`; report honesto quando o candidato já virou nota
  ativa ou o mem está indisponível.
```

E sob `### Added` (se a seção existir; senão crie-a sob Unreleased):

```
- `engine/integrations/mem.py::mem_inbox_reject` — wrapper degrade-soft sobre
  `mem inbox reject <id>`.
```

- [ ] **Step 3: README — recontagem OBRIGATÓRIA do stat rapid**

Run (obrigatório, não condicional): `.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1`
O plano adiciona ~6 testes rapid novos e o `README.md` expõe o stat literal (ex.: `rapid 2068 passed`). Compare o output com o stat do README — se diferirem (o esperado é +~6), atualize o README pro número EXATO do output. Só pule o edit se o output bater exatamente com o README atual.

- [ ] **Step 4: limpar os probes do inbox**

Os ids podem ter mudado; liste e rejeite os 2 candidatos cujos títulos começam com `probe-` (`probe-6d-unblock-check`, `probe-json-add-returns-id`). NÃO rejeite o candidato `user correction signal` (origin correction-signal — é real).

```bash
./.claude/bin/mem --json inbox list
# para cada id cujo title começa com "probe-":
./.claude/bin/mem inbox reject <ID>
```

- [ ] **Step 5: Commit**

```bash
git add docs/design/04-pending.md CHANGELOG.md README.md
git commit -m "docs(w-route): doc-sync 6d — undo knowledge re-route resolvido (W-ROUTE 6d Task 4)"
```

---

## Notas de verificação final (pós-execução, antes do checkpoint)

- Lane rapid + integration verdes; e2e com `RUN_E2E=1` se tocou caminho coberto por e2e.
- `test_validators_determinism.py` ainda verde (undo.py não é validator — o guard não deve regredir).
- `forge verify` sem hard fail.
- Diff cumulativo `8ad1b46..HEAD` revisado por gsd-code-reviewer (costuras Task 2↔Task 3: o nome do extra `mem-inbox-id`/`routed-to` gravado em evolve.py é EXATAMENTE o lido em undo.py).
