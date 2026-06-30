# Plano — Fase 1 Tracks B/C/D (papercuts, limpeza mem, P2 polish)

> **Origem:** `docs/superpowers/specs/2026-06-30-aifirst-pendencias-campaign-design.md §Fase 1 Tracks B/C/D`.
> **Backlog fonte:** `docs/design/04-pending.md §Piloto MeoBonsai Follow-on`, `§W-AGENTS`, `§W-ROUTE 6a`, `§P2 (itens 16-21)`.
> **Branch de campanha:** `feat/aifirst-pendencias` (Track A já mergeado — commits `77292fe`/`99d63c1`).
> **Escopo deste plano:** SÓ Tracks B, C, D. Track A está feito; Fase 2 (docs holistic) é serial pós-merge e fica fora daqui.
> **Voz:** mentor calmo. Firme nos gates, didático nos exemplos.

---

## 0. Constraints globais (header — valem pra TODA task)

- **Pytest canônico:** `.venv/bin/pytest` (tem `json5` + deps). O system pytest gera falso-negativo. Lane rápida: `.venv/bin/pytest -m "not integration and not e2e"`.
- **Worktree isolado por track:** cada track (B, C, D) roda em worktree próprio com venv próprio. **Gate anti-trap (editable-install):** antes de rodar QUALQUER teste na worktree, confirme que o engine resolvido é o da worktree, não o repo principal:
  ```
  .venv/bin/python -c "import engine, pathlib; print(pathlib.Path(engine.__file__).resolve())"
  ```
  O path impresso DEVE estar sob a raiz da worktree. Se apontar pro repo principal, `pip install -e .` dentro da worktree antes de seguir.
- **TDD é mandamento (#2):**
  - **bugfix** → começa com regression test FALHANDO (RED), depois GREEN.
  - **refactor / rename** → NÃO adiciona teste novo de comportamento; roda os testes existentes verdes com o novo nome (no-behavior-change).
  - Gate de "pronto": pytest verde + `forge verify` sem hard fail + reviewer assinou (sem high/critical) + doc-sync no mesmo commit.
- **Reuso-first (#3):** antes de criar helper, consulte os helpers já presentes no módulo tocado (ex.: `engine/ui/progress.py`, `engine/integrations/mem.py`, `engine/graph/queries.py`). Não inventar paralelo.
- **Scope contido (#4):** edite SÓ os arquivos listados na task. Doc-sync na mesma mudança é exceção legítima (#6).
- **Doc-sync (#6):** cada track anota seu próprio `CHANGELOG.md` `[Unreleased]`. Mover itens fechados de `04-pending.md` pra "Fechados" é **SERIALIZADO no merge / Fase 2** — anote a intenção, não dispute o arquivo (conflito trivial esperado entre tracks no `CHANGELOG`/`04-pending`).

### Matriz de arquivos-por-track (validar disjunção antes do dispatch paralelo)

| Track | Arquivos de produção (EDIT) | Arquivos de teste (EDIT/CREATE) |
|---|---|---|
| **B** | `engine/upgrade.py`, `engine/init.py` | `tests/unit/test_upgrade_*.py`, `tests/unit/test_init_discovery_cache.py`, `tests/unit/test_brownfield_compose_dedup.py` |
| **C** | `engine/memory/distiller.py`, `engine/memory/__init__.py`, `engine/evolve.py`, `engine/memory/l3.py` (REMOVE) | `tests/unit/test_memory_distiller.py`, `tests/unit/test_engine_evolve_resume.py`, `tests/unit/test_reuse_intelligence.py`, `tests/integrations/test_mem_wrappers.py` |
| **D** | `engine/init.py`, `engine/graph/queries.py`, `engine/graph_cli.py` | `tests/unit/test_init_progress_*.py` (CREATE), `tests/unit/test_graph_*.py`, `tests/engine/test_graph_queries.py` |

**⚠ Overlap detectado:** `engine/init.py` aparece em **Track B (B2)** e **Track D (D1)**. Não são file-disjuntos. Tratamento abaixo no §"Serialização B2↔D1".

| Doc-sync (serializado no merge) | `CHANGELOG.md`, `docs/design/04-pending.md` — todos os tracks tocam; conflito trivial esperado no merge `--no-ff`. |

### Serialização B2 ↔ D1 (overlap em `engine/init.py`)

B2 (discovery cache content-fingerprint) e D1 (progress feedback nos steps longos do init) ambos editam `engine/init.py`. Regiões disjuntas dentro do arquivo (B2 ~L209-353 cache helpers; D1 ~L2467 backend + ~L2617 orphan), mas **mesmo arquivo = merge conflita**. Três caminhos pro orquestrador (escolha 1 ANTES do dispatch):

- **A) B2 e D1 no MESMO track/worktree, serializados** (B2 → merge → D1). Mais simples; perde paralelismo entre esses dois itens. **Recomendado.**
- **B) B2 num worktree, D1 noutro, merge serial** (quem mergear segundo rebasa). Mantém paralelismo dos demais; aceita 1 conflito trivial de `init.py` no 2º merge.
- **C) Diferir D1** pra uma onda própria pós-B. Só se o paralelismo B/C/D for prioridade absoluta.

Os demais itens (B1, B3, C1-C3, D2) são genuinamente file-disjuntos e correm em paralelo.

---

## TRACK B — Papercuts

**Worktree:** `feat/aifirst-pendencias` (worktree-B). **Arquivos:** `engine/upgrade.py`, `engine/init.py`.

### B1 — `forge upgrade` avisa em flag desconhecida (bugfix, TDD)

**Arquivo de produção:** `engine/upgrade.py` (função `run`, L308-335).
**Arquivo de teste:** `tests/unit/test_upgrade_unknown_flag_warns.py` (CREATE).

**Diagnóstico (scout):** `run(argv)` reconhece `--help`/`-h` (L317), `--force` (L333), `--dry-run` (L334). Qualquer outra flag (ex.: `--dryrun` typo, `--forse`) passa em silêncio — `force`/`dry_run` ficam `False` e o upgrade roda como se nenhuma flag tivesse sido passada. Sem feedback ao usuário. Cosmético (sem impacto de segurança), mas um typo de flag não dá pista.

**Fix:** emitir AVISO mentor-calmo (não-fatal, stderr) ao encontrar token não-reconhecido em `argv`, ANTES de chamar `run_upgrade`. Não aborta — segue com as flags reconhecidas (a flag típica errada é um typo; abortar seria fricção maior que o aviso). Os tokens conhecidos são `{"--force", "--dry-run", "--help", "-h"}`.

#### Step B1.1 — RED: teste do aviso

`tests/unit/test_upgrade_unknown_flag_warns.py`:

```python
"""B1 (Fase 1): forge upgrade avisa em flag desconhecida (não-fatal)."""

from __future__ import annotations

import engine.upgrade as up


def test_unknown_flag_emits_warning_to_stderr(monkeypatch, capsys):
    """Flag não-reconhecida → aviso em stderr; o upgrade ainda roda."""
    called = {}

    def _fake_run_upgrade(*, force: bool, dry_run: bool) -> int:
        called["force"] = force
        called["dry_run"] = dry_run
        return 0

    monkeypatch.setattr(up, "run_upgrade", _fake_run_upgrade)

    rc = up.run(["--dryrun"])  # typo proposital de --dry-run

    assert rc == 0
    err = capsys.readouterr().err
    assert "--dryrun" in err
    assert "não reconhecida" in err or "desconhecida" in err
    # Não-fatal: o upgrade rodou com as flags reconhecidas (nenhuma → defaults).
    assert called == {"force": False, "dry_run": False}


def test_known_flags_emit_no_warning(monkeypatch, capsys):
    """Flags válidas não disparam aviso."""

    def _fake_run_upgrade(*, force: bool, dry_run: bool) -> int:
        return 0

    monkeypatch.setattr(up, "run_upgrade", _fake_run_upgrade)

    up.run(["--dry-run", "--force"])

    err = capsys.readouterr().err
    assert "desconhecida" not in err
    assert "não reconhecida" not in err


def test_help_short_circuits_without_unknown_warning(capsys):
    """--help sai 0 e imprime uso; não dispara o aviso de flag desconhecida."""
    rc = up.run(["--help"])
    assert rc == 0
    out = capsys.readouterr()
    assert "forge upgrade" in out.out
    assert "desconhecida" not in out.err
```

Rode: `.venv/bin/pytest tests/unit/test_upgrade_unknown_flag_warns.py -v` → RED (aviso não existe ainda).

#### Step B1.2 — GREEN: aviso em `run`

Em `engine/upgrade.py`, substitua o corpo de `run` a partir de `force = "--force" in argv` (L333) — mantenha o bloco `--help`/`-h` (L317-331) INTACTO acima:

```python
    force = "--force" in argv
    dry_run = "--dry-run" in argv

    # B1 (Fase 1): flag não-reconhecida não passa mais em silêncio. Aviso
    # mentor-calmo (não-fatal) — segue com as flags válidas; um token errado é
    # quase sempre typo, abortar seria fricção maior que a pista.
    _known = {"--force", "--dry-run", "--help", "-h"}
    unknown = [tok for tok in argv if tok.startswith("-") and tok not in _known]
    for tok in unknown:
        sys.stderr.write(
            f"forge upgrade: flag '{tok}' não reconhecida — ignorando. "
            "Flags válidas: --dry-run, --force (veja `forge upgrade --help`).\n"
        )

    return run_upgrade(force=force, dry_run=dry_run)
```

`sys` já está importado no módulo (usado em L301/L318). Confirme antes de assumir.

Rode: `.venv/bin/pytest tests/unit/test_upgrade_unknown_flag_warns.py -v` → GREEN.

#### Step B1.3 — Regressão + doc-sync

- Rode os testes existentes do upgrade: `.venv/bin/pytest tests/unit/test_upgrade_dry_run_guard.py -v` (não pode regredir).
- `CHANGELOG.md` `[Unreleased]` → `### Fixed`: "forge upgrade avisa (não-fatal) em flag desconhecida em vez de ignorá-la em silêncio (Fase 1 Track B)."
- Anote (NÃO mova ainda): item "forge upgrade ignora flags desconhecidas em silêncio" de `04-pending.md §Follow-on` está fechado — mover pra Fechados no merge/Fase 2.

**Done:** `.venv/bin/pytest tests/unit/test_upgrade_unknown_flag_warns.py tests/unit/test_upgrade_dry_run_guard.py -v` verde.

---

### B2 — discovery cache com content-fingerprint (hardening, TDD)

**Arquivo de produção:** `engine/init.py` (helpers `_save_discovery_cache` L228-253, `_load_discovery_cache` L256-344, e o ponto de carga em `_run_pipeline` L2325-2346).
**Arquivo de teste:** `tests/unit/test_init_discovery_cache.py` (EXISTENTE — estender).

> **⚠ Overlap com D1 (`engine/init.py`).** Resolva pela §"Serialização B2↔D1" ANTES do dispatch.

**Diagnóstico (scout):** o cache (`.init-discovery-cache.yaml`) é invalidado pelo LIFECYCLE do checkpoint (`_clear_discovery_cache` em discard/abort/novo-init), nunca por um fingerprint do conteúdo da árvore (docstring L269-284 documenta isso como decisão consciente; só é seguro porque carregado apenas sob `host_is_replaying`). O hardening pedido (cinto + suspensório): gravar um fingerprint do conjunto de arquivos relevantes e invalidar o cache se o conteúdo mudou — robustez fora do caminho mecânico de replay.

**Decisão de design do fingerprint (mentor calmo — barato e determinístico):** hash dos `(path-relativo, mtime_ns, size)` dos arquivos que os 3 extractors leem é caro de recomputar (re-varre a árvore — o custo que o cache evita). Em vez disso, derive o fingerprint do que JÁ é barato e já está em mão: o `payload["schema-version"]` + os `.raw` dos inventories (que o cache já serializa) NÃO servem (são o RESULTADO, circular). O fingerprint correto é dos **inputs**: um hash estável dos mtimes+sizes dos diretórios-raiz de scan. Como recomputá-lo é a varredura que queremos evitar, a **escolha mínima e honesta** é: persistir um fingerprint do `project_root` mais barato disponível — o `mtime_ns` do próprio `project_root` e dos diretórios de 1º nível relevantes (não recursivo). Isso captura adições/remoções de top-level sem re-varrer a árvore inteira. Documente a limitação (não detecta edição profunda sem mudar mtime de dir-pai) como o trade-off do hardening barato.

#### Step B2.1 — RED: teste de invalidação por fingerprint

Estenda `tests/unit/test_init_discovery_cache.py` (NÃO reescreva os testes existentes; ADICIONE):

```python
def test_discovery_cache_invalidated_by_content_fingerprint(tmp_path, monkeypatch):
    """B2 (Fase 1): se o fingerprint do source mudou, o cache é cache-miss
    mesmo com o arquivo presente — hardening fora do replay mecânico."""
    import engine.init as init_mod
    from engine.inventory.conventions import ConventionsInventory

    # Semeia um cache válido com fingerprint do estado atual.
    init_mod._save_discovery_cache(
        tmp_path,
        None,
        None,
        ConventionsInventory(raw={"k": "v"}),
    )
    # Carrega com o MESMO fingerprint → cache-hit.
    assert init_mod._load_discovery_cache(tmp_path) is not None

    # Muda o conteúdo da árvore (novo dir top-level) → fingerprint diverge.
    (tmp_path / "novo-modulo").mkdir()

    # Agora o load deve ser cache-miss (fingerprint não casa).
    assert init_mod._load_discovery_cache(tmp_path) is None


def test_discovery_cache_hit_when_fingerprint_matches(tmp_path):
    """Sem mudança de conteúdo entre save e load → cache-hit (preserva o ganho
    de não re-varrer no replay mecânico)."""
    import engine.init as init_mod
    from engine.inventory.conventions import ConventionsInventory

    init_mod._save_discovery_cache(
        tmp_path, None, None, ConventionsInventory(raw={"k": "v"})
    )
    loaded = init_mod._load_discovery_cache(tmp_path)
    assert loaded is not None
    _, _, conv = loaded
    assert conv is not None and conv.raw == {"k": "v"}
```

Rode: `.venv/bin/pytest tests/unit/test_init_discovery_cache.py -v` → o teste novo de invalidação RED.

#### Step B2.2 — GREEN: fingerprint no save/load

Em `engine/init.py`, adicione um helper de fingerprint barato perto dos helpers de cache (após `_discovery_cache_path`, ~L226):

```python
def _discovery_source_fingerprint(project_root: Path) -> str:
    """Fingerprint barato do estado top-level do projeto (B2 — hardening).

    Hash do (nome, mtime_ns) do project_root e de seus filhos de 1º nível.
    Captura adições/remoções top-level SEM re-varrer a árvore (o custo que o
    cache evita). Trade-off consciente: não detecta edição PROFUNDA que não
    muda o mtime de um dir-pai top-level — cinto-e-suspensório sobre o
    lifecycle (não substituto). O lifecycle de checkpoint segue sendo a
    garantia primária; o fingerprint é o hardening fora do replay mecânico.
    """
    import hashlib

    h = hashlib.sha256()
    try:
        h.update(str(project_root.stat().st_mtime_ns).encode())
        for child in sorted(project_root.iterdir(), key=lambda p: p.name):
            try:
                h.update(child.name.encode())
                h.update(b"\x00")
                h.update(str(child.stat().st_mtime_ns).encode())
                h.update(b"\x00")
            except OSError:
                continue
    except OSError:
        return ""
    return h.hexdigest()
```

No `_save_discovery_cache`, adicione o fingerprint ao payload (após `payload: dict[str, Any] = {"schema-version": 1}`, L243):

```python
    payload: dict[str, Any] = {
        "schema-version": 1,
        "source-fingerprint": _discovery_source_fingerprint(project_root),
    }
```

No `_load_discovery_cache`, após `if not isinstance(data, dict): return None` (L290-291), adicione a checagem de fingerprint ANTES de reconstruir os inventories:

```python
    # B2 (Fase 1): cache-miss se o fingerprint do source divergiu do gravado.
    # Hardening cinto-e-suspensório sobre o lifecycle de checkpoint.
    cached_fp = data.get("source-fingerprint")
    if cached_fp != _discovery_source_fingerprint(project_root):
        return None
```

> **Compat:** caches pré-B2 não têm `source-fingerprint` (`data.get` → `None`); o fingerprint atual nunca é `None` (string vazia no pior caso). Logo cache legado → cache-miss seguro (re-roda discovery uma vez, re-popula com fingerprint). Comportamento correto: invalida o cache antigo sem fingerprint. Documente no docstring do `_load`.

Atualize o docstring de `_load_discovery_cache` (L269-284): o parágrafo "sem fingerprint de conteúdo, por design" muda — agora HÁ fingerprint barato top-level; mantenha a explicação do lifecycle como garantia primária e descreva o fingerprint como o hardening que foi adicionado.

Rode: `.venv/bin/pytest tests/unit/test_init_discovery_cache.py -v` → GREEN.

#### Step B2.3 — Regressão + doc-sync

- `.venv/bin/pytest tests/unit/test_init_discovery_cache.py -v` inteiro verde (os testes pré-existentes não podem regredir — em especial os que validam o ganho de cache-hit no replay).
- `CHANGELOG.md` `[Unreleased]` → `### Changed`: "discovery cache do init ganha content-fingerprint top-level (invalida fora do replay mecânico) — hardening cinto-e-suspensório sobre o lifecycle (Fase 1 Track B, fecha BUG-2 follow-on)."
- Anote: item "discovery cache sem content-fingerprint" de `04-pending.md §Follow-on` fechado — mover no merge/Fase 2.

**Done:** `.venv/bin/pytest tests/unit/test_init_discovery_cache.py -v` verde; fingerprint persiste e invalida.

---

### B3 — dedup `compose_backend_axes` (refactor / no-behavior-change OU PARE/anote)

**Arquivo de produção:** `engine/init.py` (`_run_pipeline` L2466-2472 + `_handle_backend_multi_axis_brownfield` L3380-3385).
**Arquivo de teste:** `tests/unit/test_brownfield_compose_dedup.py` (EXISTENTE — confirmar/estender).

**⚠ PARE/anote — leia ANTES de implementar:**

O `04-pending.md §Parciais` afirma: *"a 2ª chamada vive numa função W7.4 deferred/unused"*. **O scout CONTRADIZ isso parcialmente.** Estado real em main:

- `_run_pipeline` L2467 chama `compose_backend_axes` pra computar `has_signals` (L2468-2472).
- Se `has_signals` for True, L2480 chama `_handle_backend_multi_axis_brownfield`, que **internamente chama `compose_backend_axes` DE NOVO** (L3385).
- Logo `_handle_backend_multi_axis_brownfield` **NÃO é dead/unused** — está WIRADA no caminho ativo do `_run_pipeline` (L2480). O docstring da função (L3340-3343) que diz "chamada apenas pelo integration test" está STALE em relação ao código.

**Conclusão do scout:** há duplicação REAL no caminho ATIVO (compose roda 2×: uma pra `has_signals`, outra dentro do handler). Como **toca caminho ativo**, a instrução do usuário é: **se a remoção tocar caminho ativo, PARE e anote (não force)**.

**Decisão (3-caminhos pro orquestrador — escolha ANTES do dispatch):**

- **A) PARE/anote (default seguro, recomendado).** A 2ª chamada NÃO está numa função morta — está no hot-path. Dedup exige passar o `composer_result` já computado em L2467 pra dentro do handler (mudar a assinatura de `_handle_backend_multi_axis_brownfield` pra aceitar `composer_result` opcional e pular o recompute). Isso é refactor de assinatura num caminho que o init exercita — risco no-behavior-change real, mas precisa de cobertura cuidadosa. **Anote como sub-finding: "dedup compose_backend_axes é refactor de hot-path, não remoção de dead code — escopo maior que o `04-pending` sugeria; reentrar com brainstorm dedicado."** Não implemente neste dispatch.

- **B) Dedup conservador (só se o orquestrador autorizar explicitamente).** Adicionar parâmetro opcional `composer_result: dict | None = None` a `_handle_backend_multi_axis_brownfield`; quando o caller passa o resultado já computado, o handler reusa em vez de recomputar (L3385 vira condicional). `_run_pipeline` passa o `composer_result` de L2467. **Gate:** TDD no-behavior-change — `tests/unit/test_brownfield_compose_dedup.py` + um spy que conta as invocações de `compose_backend_axes` (deve cair de 2 pra 1 no caminho brownfield, com saída idêntica). Atualizar o docstring stale do handler.

- **C) Diferir** pra a wave de execução do Tema 6 face 3 (que vai tocar `verify`, não `init`) — sem ganho, descartar.

**Recomendação:** **A (PARE/anote).** O item é Parcial no backlog justamente por isso; o ganho (1 chamada de composer a menos) não justifica refactor de hot-path sem brainstorm. Registre o sub-finding e siga.

#### Step B3.1 (só se A) — registrar o PARE/anote

- NÃO edite `engine/init.py`.
- `CHANGELOG.md` `[Unreleased]` → `### Notes` (ou comentário no doc-sync de merge): "dedup compose_backend_axes mantido aberto — scout Fase 1 confirmou que a 2ª chamada está no hot-path ativo (`_handle_backend_multi_axis_brownfield` wirada via `_run_pipeline` L2480), não numa função morta; dedup é refactor de assinatura de hot-path, reentrar com brainstorm. Corrigir o docstring stale L3340-3343 do handler quando reentrar."
- `04-pending.md §Parciais` (anote pro merge): atualizar o texto do BUG-1b — a função NÃO é unused; corrigir a afirmação "deferred/unused".

#### Step B3.2 (só se B foi autorizado) — RED→GREEN no-behavior-change

`tests/unit/test_brownfield_compose_dedup.py` (estender):

```python
def test_brownfield_handler_reuses_precomputed_composer_result(tmp_path, monkeypatch):
    """B3: quando o caller passa composer_result, o handler não recomputa
    compose_backend_axes (1 chamada em vez de 2). Saída idêntica."""
    import engine.init as init_mod

    calls = {"n": 0}
    real = init_mod.compose_backend_axes

    def _counting(project_root, normalized, **kw):
        calls["n"] += 1
        return real(project_root, normalized, **kw)

    monkeypatch.setattr(init_mod, "compose_backend_axes", _counting)
    # ... construir active_cards mínimos com signals; chamar o handler
    #     passando composer_result já computado e asserir calls["n"] == 0
    #     (handler não recomputa) e selected_card_names idêntico ao baseline.
```

> O step B3.2 só roda sob autorização explícita do orquestrador (caminho B). Caso contrário, o Track B termina em B3.1.

**Done (A):** sub-finding registrado, `init.py` intocado. **Done (B):** spy confirma 1 chamada de composer, saída idêntica, testes verdes, docstring corrigido.

---

## TRACK C — Limpeza mem

**Worktree:** worktree-C. **Arquivos:** `engine/memory/distiller.py`, `engine/memory/__init__.py`, `engine/evolve.py`, `engine/memory/l3.py` (REMOVE).

### C1 — `_KNOWLEDGE_KINDS` roteia os 3 kinds restantes (feature/bugfix, TDD)

**Arquivo de produção:** `engine/memory/distiller.py` (`_VALID_KINDS` L78-96, `_KNOWLEDGE_KINDS` L100, `apply_proposal_to_l2` L460-555).
**Arquivo de teste:** `tests/unit/test_memory_distiller.py` (EXISTENTE — estender).

**Diagnóstico (scout):**
- `apply_proposal_to_l2` roteia pro mem inbox apenas `_KNOWLEDGE_KINDS = {promote-to-l2, l1-to-l2-promotion, consolidate-l2}` (L490-527).
- Os kinds que o `retrospective-agent.md` emite — `convention-refinement` / `decay-signal` / `question-elimination` — caem no `NotImplementedError` final (L553). Limitação herdada da v1.1, confirmada em `04-pending.md §W-AGENTS`.
- **Nuance load-bearing (scout):** em `_VALID_KINDS`, `question-elimination` (L87) e `convention-refinement` (L88) JÁ são válidos, mas **`decay-signal` NÃO está em `_VALID_KINDS`** — hoje `_validate_kind` REJEITARIA `decay-signal` com `MemoryError` antes mesmo de chegar no `NotImplementedError`. Logo C1 tem DUAS partes: (1) adicionar `decay-signal` a `_VALID_KINDS`; (2) rotear os 3 pro mem inbox.

**Decisão de design:** rotear os 3 pelo MESMO padrão dos 3 knowledge kinds existentes — `mem_inbox_add` com `mem_type="reference"`, raise-não-drena se `ok=False` ou sem `id`. A forma mais limpa e reuso-first: **adicionar os 3 a `_KNOWLEDGE_KINDS`**, fazendo o branch existente (L490-527) cobri-los sem código novo. Consequência a verificar: `_KNOWLEDGE_KINDS` também é importado por `engine/evolve.py` pra PULAR o overflow-guard (L291). Adicionar os 3 lá significa que eles também pulam o overflow-guard — o que é CORRETO (vão pro mem inbox, não pro L2; o overflow-guard é sobre tamanho do L2). Confirme essa intenção no review.

#### Step C1.1 — RED: cada kind roteia sem NotImplementedError

Estenda `tests/unit/test_memory_distiller.py` (ADICIONE; reuse o helper `_make_knowledge_proposal` L292 como molde):

```python
import pytest


@pytest.mark.parametrize(
    "kind",
    ["convention-refinement", "decay-signal", "question-elimination"],
)
def test_retrospective_kinds_route_to_inbox(tmp_path, monkeypatch, kind):
    """C1 (Fase 1): os 3 kinds do retrospective roteiam pro mem inbox como os
    demais knowledge kinds — sem NotImplementedError."""
    import engine.memory.distiller as _dist
    from engine.integrations import mem as mem_mod

    captured = {}

    def _fake_inbox_add(project_root, **kwargs):
        captured.update(kwargs)
        return mem_mod.MemQuery(ok=True, data={"id": "01INBOX", "status": "pending"})

    monkeypatch.setattr(_dist, "mem_inbox_add", _fake_inbox_add)
    monkeypatch.setattr(_dist, "remove_from_queue", lambda *a, **k: None)
    monkeypatch.setattr(_dist, "is_fingerprint_rejected", lambda *a, **k: False)

    p = _dist.DistillationProposal(
        id=f"P-{kind}",
        kind=kind,
        title=f"titulo {kind}",
        description="corpo",
        provenance=["feat-x"],
        confidence=0.8,
    )
    inbox_id = _dist.apply_proposal_to_l2(tmp_path, p)

    assert inbox_id == "01INBOX"
    assert captured["mem_type"] == "reference"
    assert captured["title"] == f"titulo {kind}"


def test_decay_signal_is_a_valid_kind(tmp_path):
    """decay-signal precisa estar em _VALID_KINDS, senão _validate_kind rejeita
    antes do roteamento."""
    import engine.memory.distiller as _dist

    # Não deve levantar MemoryError de 'invalid proposal kind'.
    _dist._validate_kind("decay-signal")
```

Rode: `.venv/bin/pytest tests/unit/test_memory_distiller.py -k "retrospective_kinds or decay_signal_is_a_valid" -v` → RED (`decay-signal` rejeitado em `_validate_kind`; os outros caem em `NotImplementedError`).

#### Step C1.2 — GREEN: adicionar os 3 kinds

Em `engine/memory/distiller.py`:

1. Adicione `decay-signal` a `_VALID_KINDS` (L78-96), junto aos kinds de conhecimento:

```python
    "question-elimination",
    "convention-refinement",
    "decay-signal",
```

2. Estenda `_KNOWLEDGE_KINDS` (L100) pra incluir os 3 do retrospective:

```python
# W-ROUTE 6b + C1 (Fase 1): kinds de L2-knowledge que vão pro mem inbox em vez
# de escrever L2. Compartilhado com engine/evolve.py (skip do overflow-guard —
# correto: o inbox não é o L2, o overflow-guard é sobre tamanho do L2).
_KNOWLEDGE_KINDS = frozenset({
    "promote-to-l2",
    "l1-to-l2-promotion",
    "consolidate-l2",
    "convention-refinement",
    "decay-signal",
    "question-elimination",
})
```

3. Atualize o docstring de `apply_proposal_to_l2` (L466-476): mover `question-elimination`/`convention-refinement` da lista de "não implementados" pra a lista de knowledge-kinds roteados; adicionar `decay-signal`. O `NotImplementedError` final (L553) passa a cobrir só os kinds genuinamente sem handler (`distill-l2`, `template-patch`, `agent-prompt-addition`, `new-card-suggestion`).

Rode: `.venv/bin/pytest tests/unit/test_memory_distiller.py -k "retrospective_kinds or decay_signal_is_a_valid" -v` → GREEN.

#### Step C1.3 — Regressão + doc-sync

- Suite inteira do distiller + evolve resume (o overflow-skip mudou de superfície): `.venv/bin/pytest tests/unit/test_memory_distiller.py tests/unit/test_engine_evolve_resume.py -v`. Nenhum pode regredir. Se um teste de overflow-pause usar um dos 3 novos kinds, ele agora pulará o guard corretamente — reconcilie trocando o kind do proposal pra um NÃO-knowledge (ex.: `forget-l1`), espelhando a reconciliação feita em W-ROUTE 6b.
- `CHANGELOG.md` `[Unreleased]` → `### Fixed`: "`apply_proposal_to_l2` roteia `convention-refinement`/`decay-signal`/`question-elimination` pro mem inbox (antes `NotImplementedError`); `decay-signal` agora é kind válido (Fase 1 Track C, fecha limitação v1.1 §W-AGENTS)."
- Anote pro merge: `04-pending.md §W-AGENTS` item "_KNOWLEDGE_KINDS cobre só 3 kinds" fechado.

**Done:** os 3 kinds roteiam pro inbox sem `NotImplementedError`; `decay-signal` válido; suites distiller+evolve verdes.

---

### C2 — rename `apply_proposal_to_l2` (refactor / no-behavior-change, sweep semântico)

**Arquivos de produção:** `engine/memory/distiller.py` (def L460 + `__all__` L639), `engine/evolve.py` (import L23, callsite L303, docstring L286).
**Arquivos de teste:** `tests/unit/test_memory_distiller.py`, `tests/unit/test_engine_evolve_resume.py`, `tests/unit/test_reuse_intelligence.py`, `tests/integrations/test_mem_wrappers.py`.

**Diagnóstico (scout):** o nome `apply_proposal_to_l2` é misnomer desde W-ROUTE 6b — o destino dos knowledge kinds é o **mem inbox**, não o L2 (`04-pending.md §W-ROUTE 6b`). Callers de PRODUÇÃO: `engine/evolve.py` (L23 import, L303 callsite). Callers de TESTE: os 4 arquivos acima (≈14 callsites — `grep` confirmou). Os muitos hits em `docs/superpowers/plans/*` e `docs/superpowers/specs/*` são **histórico congelado** (planos/specs já executados) — NÃO devem ser editados (são snapshots do que aconteceu, não contrato vivo). Hits em docs VIVOS a tratar: `docs/schemas/proposed-evolutions.md:238`, `docs/lifecycle/memory-and-graph.md:432-433`.

**Nome proposto (coerente com o código real observado):** `route_proposal_to_inbox`. Racional: o que a função faz hoje é rotear o proposal pro destino correto — knowledge kinds → mem inbox; `forget-l1` → arquiva L1; reuse-kinds → intake stub. "to_inbox" reflete o caminho dominante (knowledge) e o retorno (`mem-inbox-id`). Alternativa rejeitada: `apply_proposal` (genérico demais, perde o "pra onde").

> **Sweep semântico — escopo EXATO (whitelist):**
> - **Renomear** (produção): `engine/memory/distiller.py` (def + `__all__` + mensagens de erro internas L510/L523/L554 que prefixam `apply_proposal_to_l2:`), `engine/evolve.py` (import + callsite + docstring).
> - **Renomear** (testes): os 4 arquivos de teste — todos os callsites + nomes de função de teste que embutem o nome antigo (ex.: `test_apply_proposal_to_l2_returns_inbox_id_for_knowledge` → `test_route_proposal_to_inbox_returns_inbox_id_for_knowledge`) + `monkeypatch.setattr(..., "apply_proposal_to_l2", ...)`.
> - **Atualizar** (docs vivos): `docs/schemas/proposed-evolutions.md:238`, `docs/lifecycle/memory-and-graph.md:432-433`.
> - **NÃO TOCAR:** `docs/superpowers/plans/*`, `docs/superpowers/specs/*` (histórico congelado), `docs/design/ROADMAP.md`/`02-phases.md`/`08-session-handoff.md` (snapshots/roadmap — mover/atualizar é doc-sync de Fase 2, anote). `04-pending.md` — anote pro merge.

#### Step C2.1 — sweep (no-behavior-change)

1. Em `engine/memory/distiller.py`: renomeie `def apply_proposal_to_l2` → `def route_proposal_to_inbox`; atualize `__all__` (L639); atualize os 3 prefixos de mensagem de erro (`apply_proposal_to_l2:` → `route_proposal_to_inbox:`). Adicione um alias de compat OPCIONAL? **Não** — clean-break (pré-produção, sem consumidores externos; `mem find "Pre-production status"`). Sem alias.
2. Em `engine/evolve.py`: `from engine.memory.distiller import route_proposal_to_inbox` (L23 area); callsite L303 `inbox_id = route_proposal_to_inbox(project_root, p)`; docstring L286 atualizado.
3. Sweep dos 4 arquivos de teste: substitua TODOS os callsites e `monkeypatch.setattr` targets; renomeie funções de teste que embutem o nome antigo.
4. Docs vivos: `proposed-evolutions.md:238`, `memory-and-graph.md:432-433`.

**Verificação de completude do sweep (gate):** após o rename, NÃO pode sobrar referência ao nome antigo em código de produção ou teste:

```
grep -rn "apply_proposal_to_l2" engine/ tests/ docs/schemas/ docs/lifecycle/ --include="*.py" --include="*.md" | grep -v __pycache__
```

Resultado esperado: **vazio** (os hits remanescentes só em `docs/superpowers/*` e `docs/design/ROADMAP|02-phases|08-session` — histórico congelado, intocados por design).

#### Step C2.2 — Regressão (no-behavior-change)

Rode as 4 suites com o novo nome — devem ficar VERDES sem mudança de comportamento:

```
.venv/bin/pytest tests/unit/test_memory_distiller.py tests/unit/test_engine_evolve_resume.py tests/unit/test_reuse_intelligence.py tests/integrations/test_mem_wrappers.py -v
```

> `test_mem_wrappers.py` está em `tests/integrations/` (lane integration) — rode-o explicitamente por path; ele NÃO entra na lane rápida `-m "not integration and not e2e"`.

#### Step C2.3 — doc-sync

- `CHANGELOG.md` `[Unreleased]` → `### Changed`: "rename `apply_proposal_to_l2` → `route_proposal_to_inbox` (misnomer desde W-ROUTE 6b — knowledge kinds vão pro mem inbox, não L2); sweep semântico em callers + testes + docs vivos (Fase 1 Track C, clean-break sem alias — pré-produção)."
- Anote pro merge: `04-pending.md §W-ROUTE 6b` item "`apply_proposal_to_l2` misnomer" fechado.

**Done:** grep do nome antigo vazio (fora do histórico congelado); 4 suites verdes; nenhum comportamento mudou.

---

### C3 — remover `engine/memory/l3.py` órfão (clean-break / refactor OU PARE/anote)

**Arquivos de produção:** `engine/memory/l3.py` (REMOVE), `engine/memory/__init__.py` (docstring L6).
**Arquivos de teste:** confirmar zero imports de `l3` em `tests/`.

**Diagnóstico (scout — confirmação de zero-consumidor):** `04-pending.md §W-ROUTE 6a` diz que `l3.py` perdeu seu único consumidor de produção (`memory_cli` parou de inspecionar L3). Scout confirmou:

```
grep -rn "read_l3_index|read_l3_entry|search_l3|memory.l3|memory import l3|from engine.memory.l3" engine/ tests/ agents/ skills/ --include="*.py" --include="*.md"
```

→ **único hit:** `engine/memory/__init__.py:6` — e é uma **linha de docstring** (`- engine.memory.l3 — read-only proxy...`), NÃO um import. O match `tests/unit/test_parser_objc.py` de "l3" é falso-positivo (token `label3` numa string de teste de parser, L96 — confirmado lendo a linha). **ZERO consumidores de produção; ZERO imports de teste.**

**Decisão:** clean-break — remover o arquivo + a linha de docstring órfã. Pré-produção, sem consumidores externos (`mem find "Pre-production status"`).

> **PARE/anote — guard de segurança:** se durante a execução o subagente encontrar QUALQUER import de `engine.memory.l3` (ou de suas funções `read_l3_index`/`read_l3_entry`/`search_l3`) em código de produção OU teste que o scout não pegou, **PARE e anote** — não remova. O grep acima é o gate; rode-o de novo no início do step e confirme vazio (exceto a docstring L6 e o falso-positivo de parser).

#### Step C3.1 — confirmar + remover

1. **Gate (re-confirme):** rode o grep acima. Esperado: só `__init__.py:6` (docstring) + `test_parser_objc.py:96` (falso-positivo `label3`). Se aparecer outra coisa → PARE/anote, encerre o step.
2. Remova o arquivo: `git rm engine/memory/l3.py`.
3. Em `engine/memory/__init__.py`: atualize o docstring (L1 e L6) removendo a menção a L3. O docstring de módulo passa a descrever L1 + L2 + distiller (sem o "L3 read-only proxy"). Ex.: L1 vira `"""Memory subsystem — L1 (per-feature WIP) + L2 (project) + distiller."""` e remove a linha L6.

#### Step C3.2 — Regressão (no-behavior-change)

- Suite do subsistema mem (nada importa l3, então nada quebra — confirme):
  ```
  .venv/bin/pytest tests/unit/test_memory_distiller.py tests/unit/test_parser_objc.py -v
  ```
- Lane rápida inteira do mem-adjacente pra pegar import morto não-óbvio:
  ```
  .venv/bin/pytest -m "not integration and not e2e" -q -k "memory or distiller or l2 or l1"
  ```
- Sanidade de import do pacote: `.venv/bin/python -c "import engine.memory"` (sem erro).

#### Step C3.3 — doc-sync

- `CHANGELOG.md` `[Unreleased]` → `### Removed`: "`engine/memory/l3.py` (órfão desde W-ROUTE 6a — perdeu o único consumidor de produção; zero imports confirmado por grep) — clean-break (Fase 1 Track C)."
- Anote pro merge: `04-pending.md §W-ROUTE 6a` item "`engine/memory/l3.py` órfão" fechado.

**Done:** `l3.py` removido, docstring de `__init__` ajustado, `import engine.memory` OK, suites verdes — OU PARE/anote registrado com o grep que disparou.

---

## TRACK D — P2 polish (itens 16-21 do report)

**Worktree:** worktree-D. **Arquivos:** `engine/init.py` (D1), `engine/graph/queries.py` + `engine/graph_cli.py` (D2). **Demais itens (D3-D6): majoritariamente JÁ FECHADOS — ver scout abaixo.**

> **⚠ Descoberta do scout (load-bearing — leia antes de planejar Track D):** ao scoutar cada item, **4 dos 6 itens P2 já foram implementados** numa wave anterior (W-DEBT T8, ver `04-pending.md §P2 / dívida residual`). Track D vira majoritariamente **verificação + regression test**, não implementação. Detalhe item-a-item:
>
> | Item | Estado real (scout) | Ação |
> |---|---|---|
> | D1 init progress (backend ~86s / orphan ~75s) | **ABERTO** — `ui_progress.progress` existe pra discovery/snapshot/graph, mas NÃO pro Step 5 backend (composer scan) nem Step 7.5 orphan scan | Implementar (TDD) |
> | D2 graph did-you-mean Q4 | **ABERTO** — `find_symbols_in_module` retorna `[]` em módulo inexistente sem sugestão; não há helper de listagem de módulos | Implementar (TDD) |
> | D3 evolve SIGPIPE/EOF | **FECHADO** — `engine/evolve.py:398` `except BrokenPipeError` (BUG-EVOLVE-1 T8) envolve o loop inteiro de render | Verificar + regression test; PARE/anote |
> | D4 reconfigure dashboard 1º passo | **FECHADO** — `engine/reconfigure.py:318` (BUG-RECONF-1 T8) omite dashboard nos passos seguintes do loop | Verificar + regression test; PARE/anote |
> | D5 `--help` em evolve/implement | **FECHADO** — `evolve.py:384` (BUG-EVOLVE-2 T8), `implement.py:1163` (BUG-IMPL-4 T8) | Verificar + regression test; PARE/anote |
> | D6 undo no-op `last` exit 0 + raw rebuild-templates aviso | **FECHADO** — `undo.py` `_NOOP` sentinel (BUG-UNDO-1 T8, exit 0); `raw.py:134-141` (BUG-RAW-1 T8, aviso de escopo FORGE_HOME) | Verificar + regression test; PARE/anote |
>
> **Sub-finding pra registrar no merge:** o `04-pending.md §P2 (itens 16-21)` está STALE — lista como abertos itens que o W-DEBT T8 já fechou (D3/D4/D5/D6). A Fase 2 (doc-sync) deve mover esses 4 pra Fechados e deixar só D1/D2 como o resíduo P2 real. Não force a edição de `04-pending.md` aqui (serializado).

### D1 — progress feedback nos steps longos do init (feature, TDD)

**Arquivo de produção:** `engine/init.py` (Step 5 backend ~L2449-2499; Step 7.5 orphan ~L2617-2646).
**Arquivo de teste:** `tests/unit/test_init_progress_long_steps.py` (CREATE).

> **⚠ Overlap com B2 (`engine/init.py`).** Resolva pela §"Serialização B2↔D1" ANTES do dispatch.

**Diagnóstico (scout):** `engine/init.py` JÁ usa `ui_progress.progress(...)` pra discovery (L2333), snapshot de cards (L2604) e graph (L2793). MAS os dois steps citados no report como lentos NÃO têm feedback:
- **Step 5 backend (~86s):** `compose_backend_axes` (L2467) varre signals sem barra/spinner; o usuário vê `[5/7] Backend` e depois silêncio durante a varredura.
- **Step 7.5 orphan (~75s):** `_check_orphan_signals` (L2635) varre o catálogo sem feedback.

`compose_backend_axes` e `_check_orphan_signals` são chamadas de varredura ÚNICA (não loops com `n` iteráveis óbvios), então a primitiva certa é `ui_progress.spinner(label)` (L110) — feedback "está trabalhando", não barra de N. Scout confirmou que `spinner` existe e tem `start`/`stop`.

**Decisão de design (reuso-first):** envolver as duas chamadas de varredura num `ui_progress.spinner` com label mentor-calmo. Sob loop mecânico do host (replay), o spinner deve degradar pra no-op silencioso (não poluir o transcript IA-first) — verifique como `ui_progress.spinner` se comporta em modo não-TTY / output JSON (provavelmente já no-op se stream não é TTY; confirme lendo `engine/ui/progress.py` Spinner antes de assumir).

#### Step D1.1 — RED: spinner envolve os steps longos

`tests/unit/test_init_progress_long_steps.py`:

```python
"""D1 (Fase 1): steps longos do init (backend, orphan) dão feedback via spinner."""

from __future__ import annotations

import engine.init as init_mod


def test_backend_step_uses_spinner(monkeypatch):
    """Step 5 (backend/composer) envolve a varredura num spinner com label."""
    labels = []

    class _FakeSpinnerCtx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_spinner(label, **kw):
        labels.append(label)
        return _FakeSpinnerCtx()

    monkeypatch.setattr(init_mod.ui_progress, "spinner", _fake_spinner)

    # Invocar o trecho de Step 5 que chama compose_backend_axes dentro do
    # spinner. Ajuste o ponto de entrada ao helper real após o scout do
    # executor (provável: extrair a varredura pra um helper testável OU
    # asserir via um harness que roda o trecho). O contrato observável:
    #   - ui_progress.spinner foi chamado com um label contendo "backend".
    # ... (montar harness mínimo)
    assert any("backend" in s.lower() for s in labels)


def test_orphan_step_uses_spinner(monkeypatch):
    """Step 7.5 (orphan scan) envolve a varredura num spinner com label."""
    # Mesmo padrão; label contendo "orphan" ou "órfã".
    ...
```

> **Nota ao executor:** se asserir o spinner exigir montar o pipeline inteiro (caro), prefira **extrair a varredura de cada step num helper fino** (ex.: `_compose_backend_with_feedback(...)` que envolve `compose_backend_axes` no spinner) e testar o helper isolado. Reuso-first: o helper só adiciona o spinner em volta da chamada existente, sem mudar a lógica. Mantenha o teste bite-sized.

Rode: `.venv/bin/pytest tests/unit/test_init_progress_long_steps.py -v` → RED.

#### Step D1.2 — GREEN: envolver no spinner

Em `engine/init.py`:
- **Step 5 (L2467):** envolva `compose_backend_axes(project_root, normalized_for_composer)` num `with ui_progress.spinner("backend — varrendo signals"):`. (Se extrair helper, o helper faz isso.)
- **Step 7.5 (L2635):** envolva `_check_orphan_signals(project_root, activated, overlay_catalog)` num `with ui_progress.spinner("verificando orphan signals"):`.

Labels em voz mentor-calmo, sem roadmap interno. Confirme que `spinner` degrada a no-op fora de TTY (não polui replay) — se NÃO degradar sozinho, gate o spinner por `not output_mode` JSON / `sys.stderr.isatty()`, seguindo o padrão de BUG-RECONF-1 (dashboard só no 1º passo).

Rode: `.venv/bin/pytest tests/unit/test_init_progress_long_steps.py -v` → GREEN.

#### Step D1.3 — Regressão + doc-sync

- Suites de init que cobrem o pipeline: `.venv/bin/pytest -m "not integration and not e2e" -q -k "init"`. Nenhuma regressão.
- `CHANGELOG.md` `[Unreleased]` → `### Added`: "feedback de progresso (spinner) nos steps longos do `forge init` — backend (~86s) e orphan-scan (~75s); degrada a no-op no loop mecânico do host (Fase 1 Track D, itens P2 16)."
- Anote pro merge: `04-pending.md §P2` item "progress feedback nos steps longos do init" fechado.

**Done:** spinner envolve backend + orphan scans; degrada fora de TTY; suites init verdes.

---

### D2 — graph "did-you-mean" no Q4 quando o módulo não casa (feature, TDD)

**Arquivos de produção:** `engine/graph/queries.py` (novo helper `list_modules`), `engine/graph_cli.py` (Q4 interativo `_q_symbols` L177-180 + non-interactive key `"4"` L386-389).
**Arquivos de teste:** `tests/engine/test_graph_queries.py` (estender — confirmar nome/path real no scout), `tests/unit/test_graph_*.py` (CLI).

**Diagnóstico (scout):** `find_symbols_in_module(project_root, module_name)` (`queries.py:166`) faz `SELECT ... WHERE f.module = ?`. Módulo inexistente → `[]` rows, sem nenhuma sugestão. Não existe helper que liste os módulos conhecidos no grafo. O usuário digita `:feature:auth` errado (ex.: `:features:auth`) e recebe lista vazia silenciosa.

**Decisão de design:**
1. Novo helper `list_modules(project_root, *, db_path=None) -> list[str]` em `queries.py`: `SELECT DISTINCT module FROM files WHERE module IS NOT NULL ORDER BY module`. Reuso da infra `_connect` já presente no módulo.
2. Em `graph_cli.py`, quando a Q4 retorna vazio, computar sugestões por proximidade (`difflib.get_close_matches(module, list_modules(...), n=3)`) e emiti-las como "did-you-mean" via `_render_result`/`renderer`. Vale pro caminho interativo (`_q_symbols`) e pro non-interactive (key `"4"`).

#### Step D2.1 — RED: list_modules + did-you-mean

Em `tests/engine/test_graph_queries.py` (ou o arquivo de teste real de queries — confirme path no scout; semear DB com `files.module`):

```python
def test_list_modules_returns_distinct_sorted(tmp_path):
    """D2: list_modules lista os módulos distintos conhecidos no grafo."""
    from engine.graph import queries as gq
    # ... semear um graph.db com files.module em {":feature:auth", ":core"}
    mods = gq.list_modules(tmp_path, db_path=...)
    assert mods == [":core", ":feature:auth"]
```

Teste de CLI (no arquivo de teste do `graph_cli`):

```python
def test_q4_unknown_module_suggests_close_match(tmp_path, capsys, monkeypatch):
    """D2: Q4 com módulo inexistente sugere o mais próximo (did-you-mean)."""
    # ... grafo com módulo ":feature:auth"; pedir symbols de ":features:auth"
    # asserir que a saída contém "você quis dizer" / ":feature:auth"
    ...
```

Rode: `.venv/bin/pytest tests/engine/test_graph_queries.py -k list_modules -v` + o teste de CLI → RED.

#### Step D2.2 — GREEN: helper + sugestão

1. `engine/graph/queries.py` — adicione (perto de `find_symbols_in_module`, reusando `_connect`):

```python
def list_modules(
    project_root: Path,
    *,
    db_path: Optional[Path] = None,
) -> list[str]:
    """Módulos Gradle distintos conhecidos no grafo (pra did-you-mean da Q4)."""
    conn = _connect(project_root, db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT module FROM files "
            "WHERE module IS NOT NULL AND module != '' ORDER BY module"
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()
```

2. `engine/graph_cli.py`:
   - **Interativo** `_q_symbols` (L177-180): após `rows = gq.find_symbols_in_module(...)`, se `not rows`, compute `import difflib; sugg = difflib.get_close_matches(module, gq.list_modules(project_root), n=3)` e, se houver, escreva via `renderer` algo como `"Nenhum símbolo em '{module}'. Você quis dizer: {', '.join(sugg)}?"` antes do `_render_result`.
   - **Non-interactive** key `"4"` (L386-389): mesmo tratamento — se `result` vazio, anexe a sugestão ao output (no modo JSON, inclua um campo `suggestions`; no modo prosa, linha de did-you-mean em stderr). Confirme o shape de `_render_result`/`_emit_json_result` no scout antes de escolher onde injetar.

Rode os testes RED → GREEN.

#### Step D2.3 — Regressão + doc-sync

- Suites de graph: `.venv/bin/pytest tests/engine/test_graph_queries.py -v` + `.venv/bin/pytest -m "not integration and not e2e" -q -k "graph"`.
- `CHANGELOG.md` `[Unreleased]` → `### Added`: "`forge graph` Q4 (symbols por módulo) sugere o módulo mais próximo (did-you-mean) quando o nome não casa; novo helper `queries.list_modules` (Fase 1 Track D, item P2 17)."
- Anote pro merge: `04-pending.md §P2` item "graph did-you-mean no Q4" fechado.

**Done:** `list_modules` lista módulos; Q4 vazio sugere o mais próximo (interativo + non-interactive); suites graph verdes.

---

### D3-D6 — verificação dos itens JÁ FECHADOS (regression tests + PARE/anote)

> **Estes 4 itens NÃO precisam de implementação** — o scout confirmou que o W-DEBT T8 já os fechou. A tarefa é: (a) localizar o guard de regressão existente; (b) se faltar teste dedicado, adicionar um regression test fino que prove o comportamento; (c) **PARE/anote** que o item já estava fechado (para o merge mover de `04-pending.md`). **Não re-implemente nem refatore o que já funciona** (scope #4).

**Arquivos:** `engine/evolve.py` (D3, D5-evolve), `engine/reconfigure.py` (D4), `engine/implement.py` (D5-implement), `engine/undo.py` + `engine/raw.py` (D6). Testes: confirmar/estender os guards existentes.

#### Step D3-D6.1 — confirmar guards + cobrir buracos

Para cada item, rode o gate de confirmação e adicione regression test SÓ se faltar:

- **D3 (evolve SIGPIPE/EOF):** confirme `engine/evolve.py:396-406` (`try: _run_evolve except BrokenPipeError: ... return 0`). Teste: se não houver guard cobrindo `BrokenPipeError` no `run`, adicione um que force `_run_evolve` a levantar `BrokenPipeError` (monkeypatch) e asserta `run([]) == 0` sem propagar. `.venv/bin/pytest -k "evolve and (pipe or broken)" -v`.
- **D4 (reconfigure dashboard 1º passo):** confirme `engine/reconfigure.py:318-322` (BUG-RECONF-1). Teste: sob replay (passo > 1) o dashboard NÃO é re-impresso; no 1º passo (entrada genuína) é. Procure o guard de teste existente; cubra o buraco se faltar.
- **D5 (`--help` evolve+implement):** confirme `evolve.py:384` e `implement.py:1163-1165`. Teste: `evolve.run(["--help"]) == 0` imprime uso; `implement.run(["--help"]) == 0` imprime uso (sem tratar `--help` como slug).
- **D6 (undo no-op `last` + raw aviso):** confirme `undo.py` `_NOOP`/`_exit_for` (no-op → exit 0) e `raw.py:134-141` (aviso de escopo FORGE_HOME). Teste: undo sem nada a reverter → exit 0; `raw rebuild-templates` imprime o aviso "opera no FORGE_HOME" antes de qualquer mutação.

#### Step D3-D6.2 — PARE/anote + doc-sync

- **PARE/anote (sub-finding pro merge):** "Os 4 itens P2 D3/D4/D5/D6 já estavam FECHADOS pelo W-DEBT T8 (BUG-EVOLVE-1/2, BUG-RECONF-1, BUG-IMPL-4, BUG-UNDO-1, BUG-RAW-1). Track D adicionou regression tests onde faltavam guards dedicados; nenhuma re-implementação. `04-pending.md §P2` está stale ao listá-los como abertos — Fase 2 deve movê-los pra Fechados, deixando só D1/D2 como resíduo P2 real."
- `CHANGELOG.md` `[Unreleased]` → `### Tests` (se adicionou guards): "regression tests pros itens P2 já fechados no W-DEBT T8 (evolve SIGPIPE, reconfigure dashboard, --help evolve/implement, undo no-op, raw aviso de escopo) — Fase 1 Track D."

**Done:** guards confirmados; buracos de regressão cobertos; sub-finding "já fechado" registrado pro merge.

---

## Self-review (executado durante o planejamento — correções já inline)

**Spec coverage (cada item B/C/D tem task?):**

| Spec item | Task | Status |
|---|---|---|
| B — upgrade flags desconhecidas | B1 | ✓ implementar (TDD) |
| B — discovery cache content-fingerprint | B2 | ✓ implementar (TDD) |
| B — dedup compose_backend_axes (BUG-1b) | B3 | ✓ **PARE/anote** (hot-path, não dead code) |
| C — _KNOWLEDGE_KINDS 3 kinds restantes | C1 | ✓ implementar (TDD) — inclui `decay-signal` em `_VALID_KINDS` |
| C — rename apply_proposal_to_l2 | C2 | ✓ sweep semântico (no-behavior-change) |
| C — remover l3.py órfão | C3 | ✓ remover (zero-consumidor confirmado) + guard PARE/anote |
| D1 — init progress | D1 | ✓ implementar (TDD) |
| D2 — graph did-you-mean Q4 | D2 | ✓ implementar (TDD) |
| D3 — evolve SIGPIPE/EOF | D3 | ✓ **já fechado** → verificar + regression |
| D4 — reconfigure dashboard 1º passo | D4 | ✓ **já fechado** → verificar + regression |
| D5 — --help evolve/implement | D5 | ✓ **já fechado** → verificar + regression |
| D6 — undo no-op / raw aviso | D6 | ✓ **já fechado** → verificar + regression |

**Placeholder scan:** os blocos de código de produção (B1.2, B2.2, C1.2, C2.1, C3.1, D2.2) são completos e copiáveis. Os trechos com `...` estão APENAS em harnesses de teste onde o ponto-de-entrada exato depende do scout local do executor (D1.1 spinner harness, D2.1 DB-seeding, D3-D6 confirmação de guard) — sinalizados explicitamente como "ajuste após scout" com o contrato observável definido. Nenhum placeholder em lógica de produção.

**Type consistency:** `route_proposal_to_inbox` mantém a assinatura `(project_root: Path, proposal: DistillationProposal) -> str | None` (idêntica à original — rename puro). `list_modules(project_root: Path, *, db_path: Optional[Path] = None) -> list[str]` espelha a assinatura das demais queries de `queries.py`. `_discovery_source_fingerprint(project_root: Path) -> str`. Consistentes com o código scoutado.

**File-disjunção entre tracks (validação de paralelismo):**

| Arquivo | Track B | Track C | Track D |
|---|:---:|:---:|:---:|
| `engine/upgrade.py` | ✓ | | |
| `engine/init.py` | ✓ (B2) | | ✓ (D1) |
| `engine/memory/distiller.py` | | ✓ | |
| `engine/memory/__init__.py` | | ✓ | |
| `engine/evolve.py` | | ✓ (C1/C2) | ✓ (D3 — só teste) |
| `engine/memory/l3.py` | | ✓ (REMOVE) | |
| `engine/graph/queries.py` | | | ✓ |
| `engine/graph_cli.py` | | | ✓ |
| `engine/reconfigure.py` | | | ✓ (D4 — só teste) |
| `engine/implement.py` | | | ✓ (D5 — só teste) |
| `engine/undo.py` / `engine/raw.py` | | | ✓ (D6 — só teste) |

**Overlaps que impedem paralelismo puro (sinalizados):**
1. **`engine/init.py` — B2 (Track B) ↔ D1 (Track D).** PRODUÇÃO em ambos. Resolução obrigatória pela §"Serialização B2↔D1" (recomendado: A — mesmo worktree, serial). **Este é o único overlap de produção entre tracks.**
2. **`engine/evolve.py` — C1/C2 (Track C, PRODUÇÃO) ↔ D3 (Track D, SÓ teste).** D3 não edita `evolve.py` de produção (só confirma o guard existente e adiciona teste em arquivo de teste separado). Mesmo assim, pra evitar conflito de teste e o rename de C2 tocar o import, **D3 deve rebasar sobre C** OU o orquestrador roda C antes de D3. Baixo risco (D3 é só leitura + teste novo). Anote.
3. **`CHANGELOG.md` / `docs/design/04-pending.md` — TODOS os tracks.** Conflito trivial esperado no merge `--no-ff` serial; resolução por append. Já declarado no header como serializado.

**Itens marcados PARE/anote (resumo pro orquestrador):**
- **B3** — dedup compose_backend_axes: a 2ª chamada está no HOT-PATH ativo (`_handle_backend_multi_axis_brownfield` wirada via `_run_pipeline` L2480), NÃO numa função morta como o `04-pending` afirmava. PARE/anote recomendado; dedup só sob autorização explícita (caminho B).
- **C3** — guard: re-rodar o grep no início do step; se aparecer QUALQUER consumidor de produção/teste de `l3`, PARE e não remova.
- **D3/D4/D5/D6** — já fechados no W-DEBT T8; Track D vira verificação + regression test, não implementação. `04-pending.md §P2` está stale.
