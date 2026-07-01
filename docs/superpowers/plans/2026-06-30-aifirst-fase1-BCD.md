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
- **Doc-sync (#6):** cada track anota seu próprio `CHANGELOG.md` `[Unreleased]`. Mover itens fechados de `04-pending.md` pra "Fechados" é **SERIALIZADO no merge / Fase 2** — anote a intenção, não dispute o arquivo (conflito trivial esperado entre tracks no `CHANGELOG`/`04-pending`). **Exceção (M-001):** a anotação in-line de estado de D3-D6 entra NO commit do Track D — ver Step D3-D6.2.

### Matriz de arquivos-por-track (validar disjunção antes do dispatch paralelo)

| Track | Arquivos de produção (EDIT) | Arquivos de teste (EDIT/CREATE) |
|---|---|---|
| **B** | `engine/upgrade.py`, `engine/init.py` (B2 + B3 caso o veredito da investigação seja dedup) | `tests/unit/test_upgrade_*.py`, `tests/unit/test_init_discovery_cache.py`, `tests/unit/test_brownfield_compose_dedup.py` |
| **C** | `engine/memory/distiller.py`, `engine/memory/__init__.py`, `engine/evolve.py`, `engine/memory/l3.py` (REMOVE) | `tests/unit/test_memory_distiller.py`, `tests/unit/test_engine_evolve_resume.py`, `tests/unit/test_reuse_intelligence.py`, `tests/integrations/test_mem_wrappers.py` |
| **D** | `engine/init.py` (D1), `engine/graph/queries.py` + `engine/graph_cli.py` (D2); `engine/evolve.py` (D3/D5 — **só confirmar + teste**), `engine/reconfigure.py` (D4 — **só confirmar + teste**), `engine/implement.py` (D5 — **só confirmar + teste**), `engine/undo.py` / `engine/raw.py` (D6 — **só confirmar + teste**) | `tests/unit/test_init_progress_*.py` (CREATE), `tests/unit/test_graph_*.py`, `tests/engine/test_graph_queries.py`, + os arquivos de teste de regressão de D3-D6 |

> **⚠ Nota M-002 sobre a coluna de produção do Track D:** `engine/evolve.py`, `engine/reconfigure.py`, `engine/implement.py`, `engine/undo.py`, `engine/raw.py` aparecem na Matriz como **"só confirmar + teste"** — D3-D6 NÃO editam produção neles (o W-DEBT T8 já fechou os bugs; a tarefa é verificar o guard + adicionar regression test). A anotação "só confirmar + teste" significa: o executor PODE ler (Read) esses arquivos pra confirmar o guard, mas NÃO os edita. Isso torna a Matriz a fonte única de verdade do scope de D, consistente com a seção de arquivos-por-task de D3-D6 e com o self-review.

**⚠ Overlap detectado:** `engine/init.py` aparece em **Track B (B2 + B3)** e **Track D (D1)**. Não são file-disjuntos. Tratamento abaixo no §"Serialização em `engine/init.py`". `engine/evolve.py` aparece em **Track C (C1/C2 — produção)** e **Track D (D3/D5 — só teste)**; tratamento no self-review (D3 rebasa sobre C).

| Doc-sync (serializado no merge) | `CHANGELOG.md`, `docs/design/04-pending.md` — todos os tracks tocam; conflito trivial esperado no merge `--no-ff`. **Exceção:** a anotação in-line de D3-D6 em `04-pending.md` entra no commit do Track D (M-001, Step D3-D6.2) — sem mover seção, só comentário in-line. |

### Serialização em `engine/init.py` (overlap B2 ↔ B3 ↔ D1)

Três itens podem editar `engine/init.py`: **B2** (discovery cache content-fingerprint), **B3** (dedup `compose_backend_axes` — SÓ se a investigação concluir redundância real; ver §B3) e **D1** (progress feedback nos steps longos). Regiões disjuntas dentro do arquivo (B2 ~L209-353 cache helpers; B3 ~L2467 + ~L3385 backend brownfield handler; D1 ~L2467 backend + ~L2617 orphan), **mas mesmo arquivo = merge conflita** — e B3-dedup e D1 chegam a tocar a MESMA vizinhança (~L2467, a chamada de `compose_backend_axes` no Step 5).

> **⚠ Nota especial B3 ↔ D1 (vizinhança L2467):** D1 envolve a chamada `compose_backend_axes` (L2467) num gate `_is_tty` + spinner; B3-dedup, se autorizado pela investigação (Caminho A), passa o `composer_result` dessa MESMA chamada pra dentro do handler. Os dois tocam a chamada de L2467. Se ambos forem aplicados, **serializar B3 → D1 no mesmo worktree** (B3 muda a chamada/assinatura primeiro; D1 envolve a já-deduplicada no gate). Se a investigação de B3 concluir Caminho B (não-dup) ou C (escalar), B3 NÃO edita a lógica de `init.py` (só docstring) — então o overlap de produção com D1 é trivial.

Três caminhos pro orquestrador (escolha 1 ANTES do dispatch):

- **A) B2, B3 (se dedup) e D1 no MESMO track/worktree, serializados** (B2 → B3 → D1). Mais simples; perde paralelismo entre esses itens. **Recomendado.**
- **B) Itens em worktrees separados, merge serial** (quem mergear depois rebasa). Mantém paralelismo dos demais; aceita conflitos triviais de `init.py` nos merges seguintes. **Atenção:** B3-dedup e D1 na vizinhança L2467 NÃO são triviais — se ambos editarem a lógica, force a serialização B3→D1.
- **C) Diferir D1** pra uma onda própria pós-B. Só se o paralelismo B/C/D for prioridade absoluta.

Os demais itens (B1, C1-C3, D2) são genuinamente file-disjuntos e correm em paralelo. B3 só entra na serialização de `init.py` SE a investigação concluir Caminho A (dedup); nos Caminhos B/C ele só toca docstring (overlap trivial).

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

> **⚠ Overlap com B3 (se dedup) e D1 (`engine/init.py`).** Resolva pela §"Serialização em `engine/init.py`" ANTES do dispatch.

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

### B3 — dedup `compose_backend_axes` (INVESTIGAÇÃO empírica → decidir pelo observado; `systematic-debugging`)

**Arquivo de produção:** `engine/init.py` (`_run_pipeline` L2466-2472 + `_handle_backend_multi_axis_brownfield` L3380-3385, docstring stale L3340-3343).
**Arquivo de teste/instrumentação:** `tests/unit/test_brownfield_compose_dedup.py` (CREATE — confirme no scout; em `feat/aifirst-pendencias` o arquivo NÃO está tracked, embora exista um `.pyc` órfão de uma branch paralela — ver nota abaixo).

> **⚠ Overlap com B2 e D1 (`engine/init.py`).** Resolva pela §"Serialização em `engine/init.py`" ANTES do dispatch. B3 só entra na serialização de produção SE a investigação concluir Caminho A (dedup); nos Caminhos B/C só toca docstring (overlap trivial).

> **⚠ Nota de scout (branch paralela):** existe uma branch `fix/pilot-init-perf` (commit `26f21fb`) que já aplicou a dedup do Caminho A (param `composer_result` no handler) — mas ela NÃO está mergeada em `feat/aifirst-pendencias`. No estado atual desta branch, `_handle_backend_multi_axis_brownfield` (L3385) ainda recomputa `compose_backend_axes` incondicionalmente. **A investigação de B3 segue valendo nesta branch.** Se a investigação confirmar Caminho A, o executor pode reusar o approach do `26f21fb` como referência (NÃO cherry-pick cego — confirme o estado atual e o resultado da investigação primeiro).

**⚠ Premissa CORRIGIDA — leia ANTES de investigar:**

O `04-pending.md §Parciais` afirma: *"a 2ª chamada vive numa função W7.4 deferred/unused"*. **Isso está STALE/ERRADO.** Estado real em main (scout):

- `_run_pipeline` L2467 chama `compose_backend_axes` pra computar `has_signals` (L2468-2472).
- Se `has_signals` for True, L2480 chama `_handle_backend_multi_axis_brownfield`, que **internamente chama `compose_backend_axes` DE NOVO** (L3385).
- Logo `_handle_backend_multi_axis_brownfield` **NÃO é dead/unused** — está WIRADA no caminho ATIVO do `_run_pipeline` (L2480). O docstring da função (L3340-3343) que diz "chamada apenas pelo integration test" está STALE em relação ao código.

A 2ª chamada de `compose_backend_axes` roda no **hot-path ativo** do `forge init` brownfield — exatamente o caminho cujo custo de init o piloto MeoBonsai flagou. **Mas "duas chamadas no caminho ativo" NÃO prova duplo-custo redundante:** as duas chamadas podem receber inputs/contextos diferentes e computar coisas semanticamente distintas. **Não assuma o veredito — investigue.**

**Esta task é uma INVESTIGAÇÃO (`superpowers:systematic-debugging`), não uma implementação pré-decidida** (moldura tipo a Task 0c da Fase 0). O implementer DECIDE o desfecho pelo que OBSERVAR empiricamente. O Caminho A (dedup) é o esperado — mas só vale se a investigação confirmar redundância real.

#### Step B3.1 — Investigar empiricamente (redundância real vs distinção semântica)

Objetivo: descobrir se as DUAS chamadas de `compose_backend_axes` no caminho brownfield ativo computam o **mesmo resultado pros mesmos inputs** (redundância → duplo-custo que o piloto flagou em init perf) OU recebem inputs/contextos **diferentes** (distinção semântica → NÃO é dup).

1. **Scout estático primeiro (leitura, sem rodar):** abra `engine/init.py` e leia os dois callsites, comparando os ARGUMENTOS de cada um:
   - L2467: `compose_backend_axes(project_root, normalized_for_composer)` — capture os args EXATOS (posicionais + kwargs). Scout confirmou: 2 posicionais, `project_root` + `normalized_for_composer` (este vem de `_normalize_cards_for_composer(canonical_cards)`, L2466).
   - L3385 (dentro de `_handle_backend_multi_axis_brownfield`): `compose_backend_axes(project_root, normalized)`, onde `normalized = _normalize_cards_for_composer(active_cards)` (L3384). `active_cards` é o kwarg que `_run_pipeline` L2482 passa como `canonical_cards`.
   - Pergunta-chave: `_normalize_cards_for_composer(canonical_cards)` (L2466) e `_normalize_cards_for_composer(active_cards)` (L3384) produzem o MESMO objeto/valor, já que `active_cards == canonical_cards`? Se a normalização é determinística e o input é o mesmo, os args convergem → forte sinal de redundância (Caminho A). Confirme o TIPO de retorno de `compose_backend_axes` aqui: scout indica `dict[str, dict[str, Cell | None]]` (axis_map de células — usado pra `has_signals` em L2468-2472). Esse tipo entra na assinatura do Caminho A.

2. **Confirmar empiricamente com instrumentação (não confie só na leitura) — harness brownfield ATIVO CONFIÁVEL:** escreva um teste de investigação em `tests/unit/test_brownfield_compose_dedup.py` que exercita o caminho brownfield ativo (`has_signals=True`) com um spy que captura, a CADA chamada de `compose_backend_axes`, os args recebidos E o resultado retornado.

   **Reuso obrigatório do harness brownfield real (scout):** o caminho que dispara as 2 chamadas precisa entrar no Step 5 brownfield ATIVO. Reuse o padrão de fixtures já provado em `tests/integration/test_init_brownfield_multi_axis.py` (helpers `_scaffold_project`, `_build_uniform_firebase_project`, `_load_real_card`, `_write_response`). Esse harness:
   - `_scaffold_project(tmp_path)` cria `.claude/workflow-config.yaml` + pin `host: intent-file` (essencial: sem isso o host resolve o ClaudeCodeAdapter e o protocolo file-based não vale).
   - `_build_uniform_firebase_project(tmp_path)` materializa signals que disparam `firebase-auth` acima do threshold → garante `has_signals=True` (sem isso o pipeline cai no **greenfield**, e as 2 chamadas NÃO ocorrem — o assert de 2 chamadas falharia por harness, não por comportamento).
   - O handler emite `ask_three_paths` (Phase A) e **raise `PausedForInputError` na 1ª chamada**; a 2ª chamada (após `_write_response(tmp_path, intent_id, "a")`) consome a response e retorna o result. Esse two-phase é o que faz o caminho ativo COMPLETAR.

   **Como alcançar AS DUAS chamadas (L2467 + L3385) num único caminho:** as 2 chamadas só co-ocorrem quando o pipeline entra no Step 5 (`_run_pipeline` L2467) E chama o handler (L2480 → L3385). Há dois sub-approaches; o executor escolhe pelo que o scout do entrypoint testável de `_run_pipeline` revelar:
   - **(i) Driver de Step 5 via `_run_pipeline`** se houver um entrypoint testável que chega ao Step 5 com checkpoint replay (ver `tests/unit/test_engine_init_resume.py` `test_resume_continues_from_checkpoint_step` como molde de como montar o checkpoint em `step-5-backend-selection` e dirigir o pipeline). Esse driver exercita L2467 (1ª chamada) → handler L3385 (2ª chamada) → 2 chamadas observadas.
   - **(ii) Se (i) for caro (pipeline inteiro):** instrumente o spy e dispare APENAS o trecho de Step 5 — extraia/exercite a sequência `normalized_for_composer = _normalize_cards_for_composer(canonical_cards)` → `compose_backend_axes(...)` (L2466-2467) → `_handle_backend_multi_axis_brownfield(project_root=..., active_cards=canonical_cards)` (L2480) com o two-phase do response. Isso reproduz fielmente as 2 chamadas do hot-path sem montar o pipeline inteiro. **Anote o reuso do helper de fixture** (`_build_uniform_firebase_project`) — é o que garante `has_signals=True` e, portanto, que o handler é de fato chamado.

   ```python
   def test_investigate_compose_backend_axes_call_redundancy(tmp_path, monkeypatch, capsys):
       """B3 INVESTIGAÇÃO (Fase 1): as 2 chamadas de compose_backend_axes no
       caminho brownfield ativo são redundantes (mesmos args → mesmo resultado)
       ou semanticamente distintas (args diferentes)? Este teste OBSERVA — não
       afirma o veredito. Ler a saída capturada decide A vs B.

       Harness: reusa os fixtures brownfield de
       tests/integration/test_init_brownfield_multi_axis.py
       (_scaffold_project / _build_uniform_firebase_project / _load_real_card /
       _write_response) pra ALCANÇAR DE FORMA CONFIÁVEL o caminho ativo
       (has_signals=True). Sem o _build_uniform_firebase_project o pipeline cai
       no greenfield e as 2 chamadas NÃO ocorrem.
       """
       import json

       import engine.init as init_mod
       from engine.cards.loader import CardManifest
       from engine.ui import intent_state
       from engine.ui.question import PausedForInputError

       # ── Harness brownfield ativo (reuso dos helpers do integration test) ──
       # Estrutura mínima pra _project_root_for_io resolver tmp_path + pin host.
       claude = tmp_path / ".claude"
       claude.mkdir(parents=True, exist_ok=True)
       (claude / "workflow-config.yaml").write_text("{}\n", encoding="utf-8")
       (claude / "forge" / "state").mkdir(parents=True, exist_ok=True)
       (claude / "forge" / "forge-config.yaml").write_text(
           "host: intent-file\n", encoding="utf-8"
       )
       from engine.host import detect as _host_detect

       _host_detect._clear_cache()
       intent_state._reset_log_cache()

       # Signals que disparam firebase-auth acima do threshold → has_signals=True.
       (tmp_path / "app").mkdir(parents=True, exist_ok=True)
       (tmp_path / "app" / "google-services.json").write_text(
           '{"project_info": {"project_id": "test"}}', encoding="utf-8"
       )
       (tmp_path / "ios").mkdir(parents=True, exist_ok=True)
       (tmp_path / "ios" / "GoogleService-Info.plist").write_text(
           '<?xml version="1.0"?><plist></plist>', encoding="utf-8"
       )
       (tmp_path / "app" / "build.gradle.kts").write_text(
           'plugins { id("com.android.application") }\n'
           "dependencies {\n"
           '    implementation("com.google.firebase:firebase-auth:22.0.0")\n'
           "}\n",
           encoding="utf-8",
       )
       monkeypatch.chdir(tmp_path)

       # Card real firebase-auth como active_cards (mesma estratégia do
       # integration test — loader canônico, não dataclass à mão).
       import yaml as _yaml

       from pathlib import Path as _Path

       repo_root = _Path(init_mod.__file__).resolve().parents[1]
       card_yaml = repo_root / "cards" / "firebase-auth" / "card.yaml"
       raw = _yaml.safe_load(card_yaml.read_text(encoding="utf-8"))
       identity = raw.get("identity") or {}
       firebase_auth = CardManifest(
           name=str(identity.get("name", "")),
           version=str(identity.get("version", "")),
           schema_version=int(raw.get("schema-version", 1)),
           description=str(identity.get("description", "")),
           category=str(identity.get("category", "")),
           maturity=str(identity.get("maturity", "")),
           provides=list(raw.get("provides") or []),
           requires=list(raw.get("requires") or []),
           conflicts_with=list(raw.get("conflicts-with") or []),
           contributes=dict(raw.get("contributes") or {}),
           detection=dict(raw.get("detection") or {}),
           documentation=dict(raw.get("documentation") or {}),
           raw=raw,
           source_path=card_yaml.parent,
       )
       canonical_cards = [firebase_auth]

       # ── Spy: captura args + resultado a cada chamada de compose_backend_axes ──
       observed: list[dict] = []
       real = init_mod.compose_backend_axes

       def _spy(*args, **kwargs):
           result = real(*args, **kwargs)
           observed.append(
               {
                   "args_repr": repr(args),
                   "kwargs_repr": repr(sorted(kwargs.items())),
                   "result_repr": repr(result),
               }
           )
           return result

       monkeypatch.setattr(init_mod, "compose_backend_axes", _spy)

       # ── Dispara o trecho de Step 5: 1ª chamada (L2467) + handler (L3385) ──
       # Reproduz fielmente a sequência do hot-path (approach (ii) do plano).
       # 1ª chamada de compose_backend_axes (pra has_signals):
       normalized = init_mod._normalize_cards_for_composer(canonical_cards)
       composer_result = init_mod.compose_backend_axes(tmp_path, normalized)
       has_signals = any(
           cell is not None
           for axis_map in composer_result.values()
           for cell in axis_map.values()
       )
       assert has_signals, (
           "harness não disparou has_signals=True — confirme que "
           "_build_uniform_firebase_project semeou signals acima do threshold; "
           f"composer_result={composer_result!r}"
       )

       # Handler (Phase 1 → PausedForInputError; lê intent-id do pending).
       with pytest.raises(PausedForInputError):
           init_mod._handle_backend_multi_axis_brownfield(
               project_root=tmp_path,
               active_cards=canonical_cards,
           )
       pending = intent_state.read_pending(tmp_path)
       assert pending is not None, "handler deve emitir forge-pending.json no 1º call"
       intent_id = pending["intent-id"]

       # Phase 2: response "a" (confirm) → handler consome, 2ª chamada (L3385).
       state_dir = tmp_path / ".claude" / "forge" / "state"
       (state_dir / "forge-response.json").write_text(
           json.dumps({"schema-version": 1, "intent-id": intent_id, "value": "a"}),
           encoding="utf-8",
       )
       init_mod._handle_backend_multi_axis_brownfield(
           project_root=tmp_path,
           active_cards=canonical_cards,
       )

       # ── Veredito (harness garantiu chegar no caminho certo) ──
       assert len(observed) == 2, (
           "esperava 2 chamadas no caminho brownfield ativo (L2467 + L3385), "
           f"vi {len(observed)}: {observed}. Se 0/1, o harness não alcançou o "
           "caminho ativo — NÃO leia o veredito A/B a partir disto."
       )
       same_args = (
           observed[0]["args_repr"] == observed[1]["args_repr"]
           and observed[0]["kwargs_repr"] == observed[1]["kwargs_repr"]
       )
       same_result = observed[0]["result_repr"] == observed[1]["result_repr"]
       print(
           "B3-INVESTIGAÇÃO:"
           f" same_args={same_args} same_result={same_result}\n"
           f"  call#1 args={observed[0]['args_repr']} kwargs={observed[0]['kwargs_repr']}\n"
           f"  call#2 args={observed[1]['args_repr']} kwargs={observed[1]['kwargs_repr']}\n"
           f"  result#1={observed[0]['result_repr']}\n"
           f"  result#2={observed[1]['result_repr']}"
       )
   ```

   > **Nota ao executor (confiabilidade do harness):** o `assert has_signals` ANTES do handler é o gate que separa "harness não montou o brownfield" de "comportamento ausente" — se ele falhar, o problema é o fixture (signals abaixo do threshold), NÃO o veredito. Só depois dele o `assert len(observed) == 2` é significativo. Se o scout do executor revelar que o approach (i) (driver de `_run_pipeline` completo) é mais fiel ao hot-path real, prefira-o e replique o padrão de checkpoint replay de `test_engine_init_resume.py::test_resume_continues_from_checkpoint_step` — o contrato observável (2 chamadas + spy de args/result) é o mesmo.

   Rode capturando o print: `.venv/bin/pytest tests/unit/test_brownfield_compose_dedup.py -k investigate -v -s`.

3. **Veredito da investigação (regra de decisão explícita — não assuma; LEIA a saída):**
   - `same_args=True` **E** `same_result=True` → **REDUNDÂNCIA REAL** (duplo-custo confirmado) → siga **Caminho A** (Step B3.2-A).
   - `same_args=False` (inputs divergem) **OU** `same_result=False` → **DISTINÇÃO SEMÂNTICA** (as duas chamadas computam coisas diferentes) → siga **Caminho B** (Step B3.2-B).
   - A investigação revela que a dedup exige refactor AMPLO do pipeline de init (não basta passar o resultado já computado — ex.: a 2ª chamada está enterrada sob lógica de seleção que não dá pra contornar sem reestruturar o handler/pipeline inteiro) → siga **Caminho C** (Step B3.2-C / escalar).

#### Step B3.2 — Bater o martelo (3 caminhos — DECIDIR pelo observado em B3.1)

**Caminho A — Redundância real → deduplicar (no-behavior-change).**

A dedup mínima: computar `compose_backend_axes` UMA vez em `_run_pipeline` (L2467) e passar o resultado já computado pra dentro do handler, em vez do handler recomputar (L3385). Concretamente:

1. Adicionar parâmetro opcional `composer_result: dict[str, dict[str, Cell | None]] | None = None` à assinatura de `_handle_backend_multi_axis_brownfield` — use o TIPO de retorno real de `compose_backend_axes` confirmado em B3.1 (scout: `dict[str, dict[str, Cell | None]]`; `Cell` já é importado no topo de `init.py` via `from engine.detection.composer import Cell, Conflict, compose_backend_axes`).
2. No corpo do handler, em L3384-3385: reusar o argumento quando recebido, recomputar só se chamado sem ele — `composer_result = composer_result if composer_result is not None else compose_backend_axes(project_root, _normalize_cards_for_composer(active_cards))`. Isso preserva o caminho do integration test, que chama o handler isolado sem o argumento (default `None`).
3. `_run_pipeline` (L2480) passa o `composer_result` já computado em L2467: `_handle_backend_multi_axis_brownfield(project_root=project_root, active_cards=canonical_cards, composer_result=composer_result)`.

**Gate no-behavior-change (TDD, shape `check_no_behavior_change`):** mesma saída do init pros mesmos inputs antes/depois. Estenda `tests/unit/test_brownfield_compose_dedup.py`:

```python
def test_brownfield_handler_reuses_precomputed_composer_result(tmp_path, monkeypatch):
    """B3-A (Fase 1): com composer_result já computado, o handler NÃO recomputa
    compose_backend_axes (1 chamada em vez de 2 no caminho ativo). Saída idêntica
    ao baseline — no-behavior-change.

    Reusa o MESMO harness brownfield ativo do teste de investigação
    (scaffold + signals firebase + two-phase response 'a').
    """
    import json

    import engine.init as init_mod
    from engine.ui import intent_state
    from engine.ui.question import PausedForInputError

    # ── Reusa o harness brownfield ativo (idêntico ao de investigação) ──
    # Extraia o setup pra um helper local _make_active_brownfield(tmp_path)
    # compartilhado entre os dois testes deste arquivo (reuso-first) — ele
    # retorna (canonical_cards) e deixa o cwd/host pinados. Aqui assumo o
    # helper já extraído:
    canonical_cards = _make_active_brownfield(tmp_path, monkeypatch)

    calls = {"n": 0}
    real = init_mod.compose_backend_axes

    def _counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(init_mod, "compose_backend_axes", _counting)

    # 1ª chamada (pipeline, pra has_signals) + composer_result pré-computado.
    normalized = init_mod._normalize_cards_for_composer(canonical_cards)
    composer_result = init_mod.compose_backend_axes(tmp_path, normalized)

    # Baseline: rodar o handler SEM o composer_result pré-computado (2ª chamada
    # recomputa) e capturar o output canônico (Phase 1 raise + Phase 2 confirm).
    baseline = _run_handler_two_phase(
        init_mod, tmp_path, canonical_cards, composer_result=None
    )
    calls_after_baseline = calls["n"]

    # Pós-dedup: rodar o handler COM o composer_result pré-computado — NÃO
    # recomputa. Reset do estado de intent entre runs (response fresca).
    intent_state._reset_log_cache()
    deduped = _run_handler_two_phase(
        init_mod, tmp_path, canonical_cards, composer_result=composer_result
    )

    # No-behavior-change: o handler com composer_result pré-computado NÃO
    # chama compose_backend_axes de novo (a recomputação some).
    assert calls["n"] == calls_after_baseline, (
        "com composer_result pré-computado o handler NÃO pode recomputar "
        f"compose_backend_axes; chamadas baseline={calls_after_baseline}, "
        f"pós-dedup={calls['n']}"
    )
    # Saída IDÊNTICA ao baseline — shape de check_no_behavior_change.
    assert deduped["choice"] == baseline["choice"]
    assert (deduped.get("selected_card_names") or []) == (
        baseline.get("selected_card_names") or []
    )
    assert (deduped.get("composer_result") or {}) == (
        baseline.get("composer_result") or {}
    )
```

> **Helpers locais a extrair (reuso-first):** `_make_active_brownfield(tmp_path, monkeypatch) -> list[CardManifest]` (o scaffold + signals firebase + pin host + card real, compartilhado pelos dois testes deste arquivo) e `_run_handler_two_phase(init_mod, tmp_path, cards, *, composer_result) -> dict` (Phase 1 raise + read intent-id + write response "a" + Phase 2 call → retorna o result). Esses helpers eliminam a duplicação entre o teste de investigação e o de no-behavior-change e mantêm cada teste bite-sized.

- **Confirmar o ganho:** re-rode o teste de investigação (B3.1) pós-fix — o caminho ativo deve mostrar `len(observed) == 1` (ajuste o investigation test pra refletir 1 chamada pós-dedup, ou documente a transição). Registre no doc-sync que o duplo-custo foi eliminado.
- **Corrigir o docstring stale L3340-3343:** trocar "chamada apenas pelo integration test" pela descrição real ("chamada por `_run_pipeline` no caminho brownfield ativo; aceita `composer_result` pré-computado pra evitar recompute — o integration test a chama isolada sem o argumento").
- Rode no-behavior-change: `.venv/bin/pytest tests/unit/test_brownfield_compose_dedup.py -v` → verde, 1 chamada confirmada no handler, output idêntico.

**Caminho B — Semanticamente distintas → NÃO deduplicar; corrigir só os docs.**

Se a investigação mostrou inputs/resultados diferentes, as duas chamadas são legítimas — NÃO toque na lógica.

1. **NÃO edite a lógica de `engine/init.py`** (sem mudança de assinatura, sem dedup).
2. **Corrija o docstring stale L3340-3343** do `_handle_backend_multi_axis_brownfield`: documente que a função É chamada no caminho ativo via `_run_pipeline` L2480 (não "só pelo integration test"), E explique POR QUE há uma 2ª chamada de `compose_backend_axes` legítima (o que muda nos inputs entre L2467 e L3385 — ex.: contexto/normalização diferente — conforme o observado em B3.1). Inclua o achado empírico literal (os args que divergiram).
3. **Fechar como não-dup:** registrar no doc-sync que a investigação concluiu distinção semântica.

**Caminho C — Escalar (fora do escopo).**

Se a dedup exigir refactor AMPLO do pipeline de init (além de passar o resultado já computado), **PARE e anote** — não force:

- Anote o sub-finding: "dedup compose_backend_axes exige refactor amplo do pipeline de init (não cabe num passe no-behavior-change) — escopo maior que a Fase 1; reentrar com brainstorm dedicado." Inclua o que a investigação revelou (por que não cabe).
- NÃO edite a lógica. Corrija no mínimo o docstring stale L3340-3343 (a premissa "só pelo integration test" está errada de qualquer forma).

#### Step B3.3 — doc-sync (conforme o caminho escolhido)

- **`04-pending.md §Parciais` (anote pro merge — corrige a PREMISSA em QUALQUER caminho):** o BUG-1b está descrito como "função morta W7.4 deferred/unused" — isso é FALSO. Atualizar pro estado real: `_handle_backend_multi_axis_brownfield` está wirada no hot-path ativo via `_run_pipeline` L2480. O texto final depende do veredito:
  - **A:** "dedup aplicada — `compose_backend_axes` computado 1× e reusado no handler (eliminou duplo-custo no init brownfield); docstring corrigido. FECHADO."
  - **B:** "investigação concluiu que as 2 chamadas são semanticamente distintas (inputs divergem) — NÃO é dup; só o docstring stale foi corrigido. FECHADO como não-dup."
  - **C:** "investigação confirmou hot-path ativo; dedup exige refactor amplo do init — reaberto como item de brainstorm dedicado (não cabe na Fase 1). Docstring corrigido."
- **`CHANGELOG.md` `[Unreleased]`** (conforme o caminho):
  - **A** → `### Changed`: "`forge init` brownfield computa `compose_backend_axes` uma única vez (era 2× no hot-path) — `_handle_backend_multi_axis_brownfield` reusa o resultado pré-computado; no-behavior-change confirmado (Fase 1 Track B, fecha BUG-1b)."
  - **B** → `### Fixed`: "docstring de `_handle_backend_multi_axis_brownfield` corrigido (estava stale: a função está no hot-path ativo via `_run_pipeline`, não 'só no integration test'); investigação confirmou que as 2 chamadas de `compose_backend_axes` são legítimas/distintas (Fase 1 Track B, fecha BUG-1b como não-dup)."
  - **C** → `### Notes`: "investigação B3 confirmou hot-path ativo e premissa stale do `04-pending`; dedup é refactor amplo do init — reaberto pra brainstorm dedicado; docstring corrigido (Fase 1 Track B)."

**Done (A):** investigação registrada; `compose_backend_axes` roda 1× no caminho brownfield; output idêntico ao baseline (no-behavior-change verde); docstring L3340-3343 corrigido. **Done (B):** investigação registrada; lógica intocada; docstring L3340-3343 corrigido com o porquê das 2 chamadas; fechado como não-dup. **Done (C):** investigação registrada; sub-finding de escalonamento anotado; docstring corrigido; lógica intocada.

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

**Decisão de design:** rotear os 3 pelo MESMO padrão dos 3 knowledge kinds existentes — `mem_inbox_add` com `mem_type="reference"`, raise-não-drena se `ok=False` ou sem `id`. A forma mais limpa e reuso-first: **adicionar os 3 a `_KNOWLEDGE_KINDS`**, fazendo o branch existente (L490-527) cobri-los sem código novo. Consequência a verificar: `_KNOWLEDGE_KINDS` também é importado por `engine/evolve.py` pra PULAR o overflow-guard (L291). Adicionar os 3 lá significa que eles também pulam o overflow-guard — o que é CORRETO (vão pro mem inbox, não pro L2; o overflow-guard é sobre tamanho do L2). Confirme essa intenção no review (ver gate de pré-confirmação M-003 abaixo).

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

> **Gate de pré-confirmação (M-003) — rode ANTES de editar a lógica:** os 3 novos kinds passarão a pular o overflow-guard de `evolve.py` (efeito de entrar em `_KNOWLEDGE_KINDS`). Para não deixar um teste de overflow virar falso-verde (passar pela razão nova — "pulou o guard" — em vez da razão antiga — "foi pausado pelo guard"), confirme que NENHUM teste de overflow usa um dos 3 kinds como payload. Rode o grep:
>
> ```
> grep -n "convention-refinement\|decay-signal\|question-elimination" tests/unit/test_engine_evolve_resume.py tests/unit/test_memory_distiller.py
> ```
>
> - **Vazio** → nenhum teste de overflow usa esses kinds; a reconciliação de C1.3 NÃO é necessária; siga. (Scout deste plano rodou o grep e veio vazio — mas o executor RE-CONFIRMA na worktree, pois o estado pode ter mudado.)
> - **Hits em contexto de overflow-test** (o proposal com esse kind é usado pra ASSERTAR pause do overflow-guard) → reconcilie ANTES: troque o kind do proposal de overflow pra um NÃO-knowledge (ex.: `forget-l1`), espelhando a reconciliação de W-ROUTE 6b. Só então prossiga.
> - **Hits fora de contexto de overflow** (ex.: o teste de roteamento que ESTE step adiciona) → benignos; siga.

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

- Suite inteira do distiller + evolve resume (o overflow-skip mudou de superfície): `.venv/bin/pytest tests/unit/test_memory_distiller.py tests/unit/test_engine_evolve_resume.py -v`. Nenhum pode regredir. O gate de pré-confirmação de C1.2 (grep) já garantiu que nenhum teste de overflow usa os 3 novos kinds; se o grep tivesse acusado hits em contexto de overflow, a reconciliação (trocar o kind pra `forget-l1`) já teria sido feita em C1.2.
- `CHANGELOG.md` `[Unreleased]` → `### Fixed`: "`apply_proposal_to_l2` roteia `convention-refinement`/`decay-signal`/`question-elimination` pro mem inbox (antes `NotImplementedError`); `decay-signal` agora é kind válido (Fase 1 Track C, fecha limitação v1.1 §W-AGENTS)."
- Anote pro merge: `04-pending.md §W-AGENTS` item "_KNOWLEDGE_KINDS cobre só 3 kinds" fechado.

**Done:** os 3 kinds roteiam pro inbox sem `NotImplementedError`; `decay-signal` válido; suites distiller+evolve verdes; grep de pré-confirmação rodado (vazio ou reconciliado).

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

**Worktree:** worktree-D. **Arquivos:** `engine/init.py` (D1), `engine/graph/queries.py` + `engine/graph_cli.py` (D2). **Demais itens (D3-D6): majoritariamente JÁ FECHADOS — ver scout abaixo. Arquivos de D3-D6 (`engine/evolve.py`, `engine/reconfigure.py`, `engine/implement.py`, `engine/undo.py`, `engine/raw.py`): SÓ confirmar + teste (não editar produção) — ver Matriz e M-002.**

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
> **Sub-finding pra registrar no merge:** o `04-pending.md §P2 (itens 16-21)` está STALE — lista como abertos itens que o W-DEBT T8 já fechou (D3/D4/D5/D6). A anotação in-line de estado (M-001) entra NO commit do Track D (Step D3-D6.2); o MOVE da seção pra "Fechados" continua serializado na Fase 2.

### D1 — progress feedback nos steps longos do init (feature, TDD)

**Arquivo de produção:** `engine/init.py` (Step 5 backend ~L2449-2499; Step 7.5 orphan ~L2617-2646).
**Arquivo de teste:** `tests/unit/test_init_progress_long_steps.py` (CREATE).

> **⚠ Overlap com B2 e B3 (`engine/init.py`).** Resolva pela §"Serialização em `engine/init.py`" ANTES do dispatch. **Atenção especial:** D1 envolve a chamada de `compose_backend_axes` (L2467) num gate `_is_tty` + spinner; B3-dedup (se autorizado) muda essa MESMA chamada. Se ambos forem aplicados, serializar B3 → D1.

**Diagnóstico (scout):** `engine/init.py` JÁ usa `ui_progress.progress(...)` pra discovery (L2333), snapshot de cards (L2604) e graph (L2793). MAS os dois steps citados no report como lentos NÃO têm feedback:
- **Step 5 backend (~86s):** `compose_backend_axes` (L2467) varre signals sem barra/spinner; o usuário vê `[5/7] Backend` e depois silêncio durante a varredura.
- **Step 7.5 orphan (~75s):** `_check_orphan_signals` (L2635) varre o catálogo sem feedback.

`compose_backend_axes` e `_check_orphan_signals` são chamadas de varredura ÚNICA (não loops com `n` iteráveis óbvios), então a primitiva certa é `ui_progress.spinner(label)` (L110) — feedback "está trabalhando", não barra de N. Scout confirmou que `spinner` existe e tem `start`/`stop`.

**Decisão de design (reuso-first) — gate `_is_tty` OBRIGATÓRIO (H-001):** envolver as duas chamadas de varredura num `ui_progress.spinner` com label mentor-calmo, **mas SÓ quando o stdout é um TTY**. O scout de `engine/ui/progress.py` (`Spinner.start`, L142-146) **derrubou a premissa anterior de "no-op silencioso fora de TTY"**: em não-TTY o `Spinner.start()` escreve `f"{self.label}…\n"` no stream (default `sys.stdout`, L137) e o `Progress.__init__` faz o mesmo (L67-69). Logo o spinner **NÃO degrada a no-op** — ele POLUI o stdout uma vez. No loop IA-first (stdout estruturado, capturado como JSON pelo host), esse texto livre **corrompe o transcript** do host e quebra o loop mecânico (Decisão 22 pressupõe stdout limpo — `engine/init.py` não tem nenhum filtro de `output_mode`/`isatty` pra progresso hoje; grep confirmou zero matches).

Por isso o gate `_is_tty` é **OBRIGATÓRIO, NÃO condicional**: o progress feedback dos steps longos só pode emitir em TTY; em não-TTY é **no-op puro — zero bytes em stdout do spinner**. A primitiva canônica do projeto pra rotear output cinético é `engine.ui.renderer._is_tty(stream)` (`renderer.py:65` — honra `NO_COLOR`/`FORGE_FORCE_COLOR` e `stream.isatty()`); é a MESMA primitiva que `Spinner`/`Progress` já usam internamente (L65, L138) pra decidir o render. Reuso-first: gate a ENTRADA no `with ui_progress.spinner(...)` por `renderer._is_tty(sys.stdout)` — não invente flag novo de `output_mode`. Fora de TTY, chame a varredura DIRETO, sem spinner (caminho sem nenhuma escrita em stdout).

> **Por que não basta `stream=sys.stderr`:** trocar o stream do spinner pra stderr ainda escreve o label uma vez em não-TTY (L144 escreve no `self.stream` qualquer que seja). O contrato IA-first exige **zero escrita** fora de TTY, não "escrita redirecionada" — daí o gate na entrada, não um troca-de-stream.

#### Step D1.1 — RED: spinner gateado por TTY (com prova de zero-stdout fora de TTY)

`tests/unit/test_init_progress_long_steps.py`:

```python
"""D1 (Fase 1): steps longos do init (backend, orphan) dão feedback via spinner
GATEADO por TTY — fora de TTY é no-op puro (zero bytes em stdout)."""

from __future__ import annotations

import io

import engine.init as init_mod


class _FakeSpinnerCtx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_backend_step_uses_spinner_in_tty(monkeypatch):
    """Step 5 (backend/composer), sob TTY, envolve a varredura num spinner."""
    labels = []

    def _fake_spinner(label, **kw):
        labels.append(label)
        return _FakeSpinnerCtx()

    monkeypatch.setattr(init_mod.ui_progress, "spinner", _fake_spinner)
    # Forçar contexto TTY pro gate liberar o spinner.
    monkeypatch.setattr(init_mod.renderer, "_is_tty", lambda *a, **k: True)

    # Invocar o trecho de Step 5 que chama compose_backend_axes sob o gate.
    # Ajuste o ponto de entrada ao helper real após o scout do executor
    # (provável: extrair a varredura pra um helper fino testável — ver nota).
    # O contrato observável: ui_progress.spinner foi chamado com label "backend".
    # ... (montar harness mínimo que entra no Step 5 backend sob TTY)
    assert any("backend" in s.lower() for s in labels)


def test_backend_step_is_noop_in_non_tty(monkeypatch, capsys):
    """H-001: fora de TTY, o spinner NÃO é instanciado e NADA vai pra stdout.

    Prova o gate obrigatório: zero bytes em stdout vindos do spinner — o loop
    IA-first não pode ter o transcript corrompido por texto cinético.
    """
    spinner_calls = []

    def _spy_spinner(label, **kw):
        spinner_calls.append(label)
        return _FakeSpinnerCtx()

    monkeypatch.setattr(init_mod.ui_progress, "spinner", _spy_spinner)
    # Forçar contexto NÃO-TTY — o gate deve suprimir o spinner.
    monkeypatch.setattr(init_mod.renderer, "_is_tty", lambda *a, **k: False)

    # ... (montar o MESMO harness do Step 5 backend, agora sob não-TTY)

    # Gate obrigatório: spinner NÃO foi instanciado fora de TTY.
    assert spinner_calls == [], (
        "fora de TTY o spinner NÃO pode ser instanciado (gate _is_tty "
        f"obrigatório); foi chamado com: {spinner_calls}"
    )
    # E, de forma mais forte: zero bytes de progresso em stdout. Mesmo que o
    # gate fosse por outro caminho, o invariante observável é stdout limpo.
    out = capsys.readouterr().out
    assert "…" not in out, (
        "spinner não pode escrever label+'…' em stdout fora de TTY "
        f"(transcript IA-first corrompido); stdout={out!r}"
    )


def test_orphan_step_uses_spinner_in_tty(monkeypatch):
    """Step 7.5 (orphan scan), sob TTY, envolve a varredura num spinner."""
    labels = []

    def _fake_spinner(label, **kw):
        labels.append(label)
        return _FakeSpinnerCtx()

    monkeypatch.setattr(init_mod.ui_progress, "spinner", _fake_spinner)
    monkeypatch.setattr(init_mod.renderer, "_is_tty", lambda *a, **k: True)
    # ... (montar harness mínimo que entra no Step 7.5 orphan scan sob TTY)
    assert any(("orphan" in s.lower() or "órfã" in s.lower()) for s in labels)
```

> **Nota ao executor:** se asserir o spinner exigir montar o pipeline inteiro (caro), prefira **extrair a varredura de cada step num helper fino que JÁ embute o gate** (ex.: `_scan_with_spinner(label, fn, *args)` que faz `if renderer._is_tty(sys.stdout): with ui_progress.spinner(label): return fn(*args)` / `else: return fn(*args)`) e testar o helper isolado. Reuso-first: o helper só adiciona o gate+spinner em volta da chamada existente, sem mudar a lógica de varredura. Mantenha o teste bite-sized. **Confirme que `init_mod.renderer` é o símbolo importado** (scout: `engine/init.py` importa `renderer`? Se importa via `from engine.ui import renderer` ou similar, monkeypatch o atributo certo; se o helper usa `renderer._is_tty`, o gate é monkeypatchável por aí).

Rode: `.venv/bin/pytest tests/unit/test_init_progress_long_steps.py -v` → RED.

#### Step D1.2 — GREEN: gate `_is_tty` + spinner (gate OBRIGATÓRIO)

Em `engine/init.py`, o padrão é **gate-then-spinner** nos dois steps. Confirme no scout como `renderer` está disponível no módulo (import top-level); se ainda não estiver, importe `from engine.ui import renderer` (já é dependência do módulo via `ui_progress`).

- **Step 5 (L2466-2467):** em vez de chamar `compose_backend_axes(...)` direto, gate o spinner:

  ```python
  if renderer._is_tty(sys.stdout):
      with ui_progress.spinner("backend — varrendo signals"):
          composer_result = compose_backend_axes(project_root, normalized_for_composer)
  else:
      composer_result = compose_backend_axes(project_root, normalized_for_composer)
  ```

  (Se extrair o helper `_scan_with_spinner`, ele encapsula esse if/else — preferível, sem duplicar o padrão em 2 lugares.)

- **Step 7.5 (L2635):** mesmo padrão pra `_check_orphan_signals(project_root, activated, overlay_catalog)`:

  ```python
  if renderer._is_tty(sys.stdout):
      with ui_progress.spinner("verificando orphan signals"):
          orphan_result = _check_orphan_signals(project_root, activated, overlay_catalog)
  else:
      orphan_result = _check_orphan_signals(project_root, activated, overlay_catalog)
  ```

Labels em voz mentor-calmo, sem roadmap interno. **O gate `_is_tty` é obrigatório nos dois pontos** — fora de TTY a varredura roda direto, sem spinner, sem nenhuma escrita em stdout. Isso é o que preserva o transcript IA-first (H-001). NÃO deixe o spinner sem gate "porque o `Spinner` já trata não-TTty" — ele NÃO trata (escreve o label uma vez; ver Decisão de design acima).

Rode: `.venv/bin/pytest tests/unit/test_init_progress_long_steps.py -v` → GREEN (incluindo o `test_backend_step_is_noop_in_non_tty` que prova zero-stdout fora de TTY).

#### Step D1.3 — Regressão + doc-sync

- Suites de init que cobrem o pipeline: `.venv/bin/pytest -m "not integration and not e2e" -q -k "init"`. Nenhuma regressão.
- `CHANGELOG.md` `[Unreleased]` → `### Added`: "feedback de progresso (spinner) nos steps longos do `forge init` — backend (~86s) e orphan-scan (~75s); GATEADO por `_is_tty` (no-op puro fora de TTY, sem poluir o transcript IA-first) (Fase 1 Track D, item P2 16)."
- Anote pro merge: `04-pending.md §P2` item "progress feedback nos steps longos do init" fechado.

**Done:** spinner envolve backend + orphan scans SOB TTY; fora de TTY é no-op puro (zero stdout, provado por teste); suites init verdes.

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

> **Estes 4 itens NÃO precisam de implementação** — o scout confirmou que o W-DEBT T8 já os fechou. A tarefa é: (a) localizar o guard de regressão existente; (b) se faltar teste dedicado, adicionar um regression test fino que prove o comportamento; (c) **PARE/anote** que o item já estava fechado (M-001 — a anotação in-line entra no commit do Track D). **Não re-implemente nem refatore o que já funciona** (scope #4). Os arquivos de produção (`evolve.py`, `reconfigure.py`, `implement.py`, `undo.py`, `raw.py`) são **só-leitura** aqui (Matriz / M-002) — confirme o guard via Read, NÃO edite.

**Arquivos:** `engine/evolve.py` (D3, D5-evolve — só confirmar), `engine/reconfigure.py` (D4 — só confirmar), `engine/implement.py` (D5-implement — só confirmar), `engine/undo.py` + `engine/raw.py` (D6 — só confirmar). Testes: confirmar/estender os guards existentes (estes SIM são EDIT/CREATE).

#### Step D3-D6.1 — confirmar guards + cobrir buracos

Para cada item, rode o gate de confirmação e adicione regression test SÓ se faltar:

- **D3 (evolve SIGPIPE/EOF):** confirme `engine/evolve.py:396-406` (`try: _run_evolve except BrokenPipeError: ... return 0`). Teste: se não houver guard cobrindo `BrokenPipeError` no `run`, adicione um que force `_run_evolve` a levantar `BrokenPipeError` (monkeypatch) e asserta `run([]) == 0` sem propagar. `.venv/bin/pytest -k "evolve and (pipe or broken)" -v`.
- **D4 (reconfigure dashboard 1º passo):** confirme `engine/reconfigure.py:318-322` (BUG-RECONF-1). Teste: sob replay (passo > 1) o dashboard NÃO é re-impresso; no 1º passo (entrada genuína) é. Procure o guard de teste existente; cubra o buraco se faltar.
- **D5 (`--help` evolve+implement):** confirme `evolve.py:384` e `implement.py:1163-1165`. Teste: `evolve.run(["--help"]) == 0` imprime uso; `implement.run(["--help"]) == 0` imprime uso (sem tratar `--help` como slug).
- **D6 (undo no-op `last` + raw aviso):** confirme `undo.py` `_NOOP`/`_exit_for` (no-op → exit 0) e `raw.py:134-141` (aviso de escopo FORGE_HOME). Teste: undo sem nada a reverter → exit 0; `raw rebuild-templates` imprime o aviso "opera no FORGE_HOME" antes de qualquer mutação.

#### Step D3-D6.2 — anotar estado in-line (M-001) + PARE/anote + doc-sync

- **Anotação in-line de estado em `04-pending.md §P2` (M-001 — entra NO COMMIT do Track D):** o `04-pending.md §P2 (itens 16-21)` lista D3/D4/D5/D6 como ABERTOS, o que está STALE (o W-DEBT T8 já fechou e o Track D verificou). Para não corromper o source-of-truth de estado da campanha até a Fase 2, **anote cada um dos 4 itens in-line, no commit do Track D, sem MOVER a seção**: marque cada item D3/D4/D5/D6 com o comentário inline `→ fechado (W-DEBT T8, verificado em Fase 1 BCD Track D)`. Isso mantém a disjunção de track (não move/reordena a seção — conflito de merge trivial/nenhum) e corrige o estado OBSERVÁVEL imediatamente (uma consulta `mem find "P2 abertos"` ou leitura direta do arquivo passa a ver "fechado", não "aberto pendente"). O MOVE físico da seção pra "Fechados" (reorganização do arquivo) permanece serializado na Fase 2.
- **PARE/anote (sub-finding pro merge):** "Os 4 itens P2 D3/D4/D5/D6 já estavam FECHADOS pelo W-DEBT T8 (BUG-EVOLVE-1/2, BUG-RECONF-1, BUG-IMPL-4, BUG-UNDO-1, BUG-RAW-1). Track D adicionou regression tests onde faltavam guards dedicados; nenhuma re-implementação. `04-pending.md §P2` recebeu anotação in-line 'fechado (W-DEBT T8, verificado)' no commit do Track D; a Fase 2 ainda faz o MOVE físico pra Fechados, deixando só D1/D2 como resíduo P2 real."
- `CHANGELOG.md` `[Unreleased]` → `### Tests` (se adicionou guards): "regression tests pros itens P2 já fechados no W-DEBT T8 (evolve SIGPIPE, reconfigure dashboard, --help evolve/implement, undo no-op, raw aviso de escopo) — Fase 1 Track D."

**Done:** guards confirmados (via Read, sem editar produção); buracos de regressão cobertos; D3-D6 anotados in-line como "fechado (W-DEBT T8, verificado)" em `04-pending.md §P2` NO commit do Track D (M-001); sub-finding "já fechado" registrado pro merge.

---

## Self-review (executado durante o planejamento — correções já inline)

**Spec coverage (cada item B/C/D tem task?):**

| Spec item | Task | Status |
|---|---|---|
| B — upgrade flags desconhecidas | B1 | ✓ implementar (TDD) |
| B — discovery cache content-fingerprint | B2 | ✓ implementar (TDD) |
| B — dedup compose_backend_axes (BUG-1b) | B3 | ✓ **INVESTIGAÇÃO** (`systematic-debugging`) → dedup (A) / não-dup-só-docstring (B) / escalar (C); premissa corrigida (hot-path ativo); harness brownfield ativo confiável (H-002) |
| C — _KNOWLEDGE_KINDS 3 kinds restantes | C1 | ✓ implementar (TDD) — inclui `decay-signal` em `_VALID_KINDS` + grep de pré-confirmação overflow (M-003) |
| C — rename apply_proposal_to_l2 | C2 | ✓ sweep semântico (no-behavior-change) |
| C — remover l3.py órfão | C3 | ✓ remover (zero-consumidor confirmado) + guard PARE/anote |
| D1 — init progress | D1 | ✓ implementar (TDD) — gate `_is_tty` OBRIGATÓRIO + prova de zero-stdout fora de TTY (H-001) |
| D2 — graph did-you-mean Q4 | D2 | ✓ implementar (TDD) |
| D3 — evolve SIGPIPE/EOF | D3 | ✓ **já fechado** → verificar + regression |
| D4 — reconfigure dashboard 1º passo | D4 | ✓ **já fechado** → verificar + regression |
| D5 — --help evolve/implement | D5 | ✓ **já fechado** → verificar + regression |
| D6 — undo no-op / raw aviso | D6 | ✓ **já fechado** → verificar + regression |

**Placeholder scan:** os blocos de código de produção (B1.2, B2.2, B3.2-A, C1.2, C2.1, C3.1, D1.2, D2.2) são completos e copiáveis. O teste de investigação B3.1 está COMPLETO (harness brownfield ativo materializado inline — scaffold + signals firebase + two-phase response; assert de `has_signals` antes do veredito; `assert len(observed) == 2` agora é significativo porque o harness garante chegar no caminho certo). O teste B3.2-A (no-behavior-change) tem o assert de output IDÊNTICO ao baseline **real e descomentado** (compara `choice`/`selected_card_names`/`composer_result` vs baseline). Os trechos com `...` remanescentes estão APENAS em harnesses de teste onde o ponto-de-entrada exato depende do scout local do executor (D1.1 entrypoint do Step 5/7.5 sob gate, D2.1 DB-seeding, D3-D6 confirmação de guard) — sinalizados explicitamente como "ajuste após scout" com o contrato observável definido. **Nenhum `# ...` em assert de veredito; nenhum placeholder em lógica de produção.**

**Type consistency:** `route_proposal_to_inbox` mantém a assinatura `(project_root: Path, proposal: DistillationProposal) -> str | None` (idêntica à original — rename puro). `list_modules(project_root: Path, *, db_path: Optional[Path] = None) -> list[str]` espelha a assinatura das demais queries de `queries.py`. `_discovery_source_fingerprint(project_root: Path) -> str`. O `composer_result` opcional de B3 (Caminho A) usa o TIPO de retorno real de `compose_backend_axes` confirmado em B3.1: `dict[str, dict[str, Cell | None]]` (`Cell` já importado no topo de `init.py`). O gate de D1 usa `renderer._is_tty(sys.stdout) -> bool` (renderer.py:65). Consistentes com o código scoutado.

**File-disjunção entre tracks (validação de paralelismo):**

| Arquivo | Track B | Track C | Track D |
|---|:---:|:---:|:---:|
| `engine/upgrade.py` | ✓ | | |
| `engine/init.py` | ✓ (B2 + B3-dedup se A) | | ✓ (D1) |
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
1. **`engine/init.py` — B2 + B3 (Track B) ↔ D1 (Track D).** PRODUÇÃO em B2, D1, e em B3 SÓ se a investigação concluir Caminho A (dedup). Resolução obrigatória pela §"Serialização em `engine/init.py`" (recomendado: A — mesmo worktree, serial B2 → B3 → D1). **Nota especial:** B3-dedup e D1 tocam a MESMA vizinhança (~L2467, a chamada de `compose_backend_axes`); se ambos forem aplicados, force a serialização B3 → D1 (B3 muda a chamada/assinatura; D1 a gateia em `_is_tty` + spinner). Se B3 cair no Caminho B/C, ele só toca docstring (overlap trivial com D1).
2. **`engine/evolve.py` — C1/C2 (Track C, PRODUÇÃO) ↔ D3 (Track D, SÓ teste).** D3 não edita `evolve.py` de produção (só confirma o guard existente via Read e adiciona teste em arquivo de teste separado). Mesmo assim, pra evitar conflito de teste e o rename de C2 tocar o import, **D3 deve rebasar sobre C** OU o orquestrador roda C antes de D3. Baixo risco (D3 é só leitura + teste novo). Anote.
3. **`CHANGELOG.md` / `docs/design/04-pending.md` — TODOS os tracks.** Conflito trivial esperado no merge `--no-ff` serial; resolução por append. Já declarado no header como serializado. **Exceção (M-001):** a anotação in-line de D3-D6 em `04-pending.md` entra no commit do Track D (sem mover seção — comentário inline) e pode coincidir com anotações de outros tracks no mesmo arquivo; resolução por append no merge.

**Itens marcados PARE/anote OU INVESTIGAÇÃO (resumo pro orquestrador):**
- **B3** — dedup compose_backend_axes: **INVESTIGAÇÃO** (`systematic-debugging`). Premissa do `04-pending` ("função morta W7.4") está ERRADA — a 2ª chamada está no HOT-PATH ativo (`_handle_backend_multi_axis_brownfield` wirada via `_run_pipeline` L2480). O harness de investigação (B3.1) reusa os fixtures brownfield reais (firebase signals + two-phase response) pra ALCANÇAR CONFIAVELMENTE o caminho ativo (H-002). O implementer investiga empiricamente (spy de args+result) e DECIDE: A) redundância real → deduplicar com no-behavior-change (assert de output idêntico ao baseline, descomentado — L-001) + corrigir docstring; B) distinção semântica → não deduplicar, corrigir só o docstring stale, fechar como não-dup; C) refactor amplo → escalar/anote + corrigir docstring. A premissa do `04-pending` é corrigida em qualquer caminho. **Nota de scout:** a branch `fix/pilot-init-perf` (`26f21fb`) já tem o Caminho A aplicado, mas NÃO está mergeada nesta branch — a investigação segue valendo.
- **C3** — guard: re-rodar o grep no início do step; se aparecer QUALQUER consumidor de produção/teste de `l3`, PARE e não remova.
- **D3/D4/D5/D6** — já fechados no W-DEBT T8; Track D vira verificação + regression test, não implementação (produção só-leitura — M-002). `04-pending.md §P2` recebe anotação in-line "fechado (W-DEBT T8, verificado)" no commit do Track D (M-001); MOVE físico fica na Fase 2.
