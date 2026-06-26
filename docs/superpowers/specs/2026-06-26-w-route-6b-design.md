# W-ROUTE 6b — `forge evolve` conhecimento→mem-inbox + `status` L2-size→mem-stats (design)

> Sub-design da Onda 6 (W-ROUTE) da Fase 1 (integração mem↔forge). Refina,
> sem contradizer, a spec congelada
> `docs/superpowers/specs/2026-06-25-mem-integration-design.md` (§Re-roteamento
> dos consumidores, §forge evolve vs mem evolve). Voz: mentor calmo. Data: 2026-06-26.

## O que 6b entrega

Re-rota DUAS leituras/escritas de memória-de-conhecimento pro `mem`:

1. **`engine/evolve.py` / `engine/memory/distiller.py`** — quando o usuário
   aprova ("a") um proposal de CONHECIMENTO no `forge evolve`, em vez de
   escrever no L2 (`l2.add_entry`), emite `mem inbox add` (candidato curado,
   anti-envenenamento G11). O conhecimento só vira nota ativa depois de
   `mem evolve` / `mem inbox promote`.
2. **`engine/status.py`** — a linha de L2-size na seção memory vira um resumo
   de `mem stats` (o L2 deixa de crescer; o conhecimento agora vive no mem).

Acumula em `feat/mem-integration`. Reuse-estrutural e artefatos do forge
FICAM no forge — 6b toca só o caminho de conhecimento.

## Decisões de 6b

### D1 — Conjunto re-roteado: só os 4 kinds de L2-knowledge

`DistillationProposal.kind` tem 16 valores. Re-rotam pro `mem inbox`:

- `promote-to-l2`, `l1-to-l2-promotion` (alias), `consolidate-l2` — implementados
  hoje (escrevem L2 via `apply_proposal_to_l2`); 6b troca a escrita por `mem inbox add`.
- `distill-l2` — está como `NotImplementedError` hoje; permanece assim (6b NÃO o implementa).

FICAM no forge (6b não toca):
- 6 reuse-estruturais (`consolidate-duplicate-helper`, `promote-to-shared-helper`,
  `remove-redundant-platform-helper`, `review-near-duplicate-helper`,
  `kmp-migration-candidate`, `consolidate-ts-helper`) → `apply_reuse_intelligence_proposal`
  (são sobre código, não conhecimento; Decisão 25 fingerprint governa).
- 5 forge-artifact (`template-patch`, `agent-prompt-addition`, `new-card-suggestion`,
  `convention-refinement`, `question-elimination`) → curadoria de artefatos do
  forge, não memória (§forge evolve da spec).
- `forget-l1` → lifecycle (arquiva feature; já em `.claude/forge/state/` pós-W-STATE).

### D2 — "Aplicar" enfileira candidato, não persiste

O gate "aplicar" (ação "a") de um proposal de conhecimento emite `mem inbox add`
— o conhecimento entra na FILA de inbox do mem (anti-envenenamento, G11/R12), e
só vira nota ativa após `mem evolve` / `mem inbox promote` (promoção por-item).
Muda a semântica: aplicar não persiste direto, enfileira como candidato curado.
Alinha com a ponte spec (§forge evolve vs mem evolve): proposals de conhecimento
do forge alimentam o ciclo de curadoria do mem.

### D3 — `--type reference`

Os proposals de conhecimento (promote/consolidate-l2) promovem PADRÕES/CONVENÇÕES
aprendidas do L1 — "como as coisas são neste projeto". Mapeiam pra `--type
reference` no schema do mem (ponteiros/convenções curadas). Mapeamento de campos:

| campo do proposal | → mem inbox add | nota |
|---|---|---|
| `title` | `-t` | direto |
| `description` | body (posicional) | direto |
| `provenance` (slugs) | `--tags` | comma-join |
| `confidence` (0.0–1.0) | `--importance` | `max(1, min(5, round(confidence × 4) + 1))` |
| `id` | `--source` | `forge-evolve:<proposal-id>` (rastreabilidade) |
| (gate "a" = humano aprovou) | `--origin manual` | captura curada por humano |
| `payload` | — | meta de reuse; irrelevante pro mem |

### D4 — `status.py`: L2-size → `mem stats`

`_render_memory` substitui a linha L2-size/max/pct por um resumo de `mem stats`:
total de notas + by_type (decision/feedback/reference/episode) + live/stale. Os
L1 counts (active/archived) FICAM (são lifecycle). O JSON payload de `status`
ganha um bloco `mem: {total, by_type, live, stale}` (hoje só tem L1 counts).
Degrada soft se o mem estiver ausente (omite o bloco / placeholder, sem crash).

### D5 — Loop do `forge evolve` inalterado; overflow-guard pulado pra conhecimento

O `forge evolve` segue interativo, single-by-single, com checkpoint-resume
(DRIFT-1) — é curadoria multi-passo genuína, NÃO o padrão BUG-M1 (não vira
stateless). 6b muda só o destino do "aplicar" pra kinds de conhecimento.
Consequência: o guard de L2-overflow (`detect_l2_overflow`) deixa de fazer
sentido pra esses kinds (não crescem mais L2) → 6b pula o overflow-check pra
kinds de conhecimento (vão pro inbox do mem, não pro L2).

### D6 — Fronteira de escopo 6b vs 6c; `l2.add_entry` órfão

6b NÃO deleta `l2.add_entry`. Após 6b ele perde o caller do evolve, ficando
órfão-pra-conhecimento — mas a leitura de L2 ainda serve ao migrador (W-MIGRATE
deferido) e a remoção da escrita L2 restante (deferida do W-STATE) é 6c. 6b
anota o órfão em `04-pending.md` (padrão do `l3.py` em 6a). Idem: o nome
`apply_proposal_to_l2` vira misnomer (não escreve L2 pra conhecimento) — mantido
em 6b pra conter footprint (rename ripplaria em callers/tests); anotado em
04-pending como candidato a rename num sweep posterior.

## Estratégia de teste

- **Wrapper `mem_inbox_add`** (`engine/integrations/mem.py`): assinatura
  `mem_inbox_add(project_root, title, body, mem_type, *, importance=None,
  tags=None, source=None, origin="manual") -> MemQuery`. Testes: argv montado
  correto (`inbox add --type reference -t … --tags … --source … --origin manual
  <body>`), mockando `subprocess.run`; degrade soft.
- **Teste real-mem obrigatório (lição MOCK-BLINDNESS do W-RULES):** ≥1 teste do
  path de inbox-add contra o `mem` vendorizado REAL (sem mock) — paths que
  ESCREVEM no mem precisam de cobertura sem mock, senão um bug de quoting/arg
  escapa. Asserta que a nota candidata aparece em `mem inbox list` após o add.
- **evolve knowledge-apply:** monkeypatch `mem_inbox_add`; asserta que é chamado
  com os campos mapeados (D3); asserta que `l2.add_entry` NÃO é chamado pra
  kinds de conhecimento; asserta que branches estruturais e `forget-l1` NÃO
  tocam o mem (zero chamada).
- **status:** `mem stats` renderizado na seção memory; degrade soft (mem
  ausente); bloco `mem` no JSON payload.
- **Footprint observável (lição 6a — varrer por contrato, não por import):**
  varrer `tests/` por asserts de `apply_proposal_to_l2`/`l2.add_entry`, da seção
  memory do `status` (texto + JSON), e do contrato observável do `forge evolve`
  (checkpoint, exit codes, intent emission) — reconciliar todos.
- Canonical: `.venv/bin/pytest` (unit + integration; mudança toca consumidor).

## Fora de 6b (fica pra 6c / depois)

- 6c: `mem find` reads por gotchas/convenções em `plan`/`implement`/`verify`/`qa`
  + remoção da escrita em L2 restante (deferida do W-STATE) + delete do
  write-path órfão de l2. WATCH OBS-3: `validate_memory.validate()` early-return
  pass se `memory_dir` não existe — vigiar quando L2 sair.
- W-AGENTS: re-rota dos 5 conductor prompts.

A camada wrapper estendida em 6b (`mem_inbox_add`) soma-se ao contrato de 6a
(`mem_find/get/stats/brief/evolve`) — base estável pra 6c e W-AGENTS.
