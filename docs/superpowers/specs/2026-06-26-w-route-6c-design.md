# W-ROUTE 6c — `mem find` reads (4 handlers) + orphan-cleanup (design)

> Sub-design da Onda 6 (W-ROUTE) da Fase 1 (integração mem↔forge). Refina,
> sem contradizer, a spec congelada
> `docs/superpowers/specs/2026-06-25-mem-integration-design.md` (§Re-roteamento
> dos consumidores). Voz: mentor calmo. Data: 2026-06-26.

## O que 6c entrega

Duas frentes:

1. **Reads:** `plan`/`implement`/`verify`/`qa` consultam o acervo de
   memória-de-conhecimento (`mem find`, via `engine/integrations/mem.py`) por
   gotchas/convenções relevantes ANTES de agir. É o valor de W-ROUTE — o forge
   passa a USAR o mem, não só escrever nele.
2. **Orphan-cleanup:** remove o código de escrita-em-L2 que 6a/6b deixaram
   órfão (`_apply_consolidate_l2`, `l2.add_entry`, imports mortos).

A re-rota do `forge undo` pra knowledge kinds (gap IM-01) fica para **6d** —
tem blocker real (proposal-id→inbox-id não mapeável: `mem inbox reject` exige a
ULID do inbox, e `mem inbox list` não expõe `source`; precisa de `mem inbox
add` retornar o id ou mudança mem-side).

Acumula em `feat/mem-integration`. Nada pushado.

## Decisões de 6c

### D1 — Reads nos 4 handlers, best-effort, handler-only

Cada handler ganha um `mem find` degrade-soft que alimenta um CONSUMIDOR REAL
(não um log morto), NUNCA dentro de um validator (determinismo):

| Handler | Onde lê | Consumidor do resultado |
|---|---|---|
| `plan` (conductor) | antes de redigir artefatos | context-pack do subagente de planejamento |
| `qa` (conductor) | antes da Phase 1 audit | handoff JSON pré-conductor |
| `implement` (conductor) | antes do dispatch de implementação | context-pack do subagente |
| `verify` | antes do `_run_cascade` | hint educacional renderizado pro usuário (NÃO passa pra validator) |

Invariantes:
- **Degrade soft:** mem ausente → sem read, sem crash, sem nag de "forge init"
  (lição de 6b: o degrade NÃO deve surfar a mensagem genérica do mem que
  sugere `forge init`).
- **Bounded:** top-N resultados; query derivada do tema da feature/task.
- **Determinismo (test-enforced):** nenhum validator importa ou chama mem. Os
  reads vivem nos handlers (`engine/plan.py`/`implement.py`/`verify.py`/`qa/`),
  jamais em `validators/`.

### D2 — Orphan-cleanup (confirmado por grep)

Após 6b, estes ficaram órfãos (grep confirmou zero caller vivo):
- `_apply_consolidate_l2` (`engine/memory/distiller.py:543+`) — o branch
  `consolidate-l2` que o chamava foi colapsado pro `mem_inbox_add` em 6b.
  **Deletar.**
- Import órfão de `add_entry` em `distiller.py:25` (sem call-site após 6b) +
  a linha reservada `_ = remove_entry` (`distiller.py:639`) se ficar sem uso
  após deletar `_apply_consolidate_l2`. **Remover.**
- `l2.add_entry` (`engine/memory/l2.py`) + sua entrada em `__all__` —
  **deletar SE o footprint sweep confirmar zero caller/teste** (era a nota de
  04-pending). Decisão do user (2026-06-26): pode deletar se o sweep confirmar.

FICAM (não tocar — território de 6d/W-MIGRATE):
- `remove_entry`/`l2_remove_entry` + `write_l2`: `engine/undo.py:372` ainda usa
  `remove_entry` no undo de evolve (a re-rota é 6d).
- `read_l2` e os readers de L2: o migrador (W-MIGRATE deferido) lê L2.
- `apply_proposal_to_l2`: continua (é o gateway re-rotado em 6b); o misnomer
  fica anotado.

### D3 — 04-pending: resolve os órfãos fixados

As entradas de 04-pending §W-ROUTE 6b sobre `l2.add_entry` órfão e (se aplicável)
`_apply_consolidate_l2` são RESOLVIDAS (removidas, pois agora deletados).
Permanecem: `apply_proposal_to_l2` misnomer + `forge undo` no-op pra knowledge
(6d).

## Estratégia de teste

- **Reads (por handler):** teste que `mem find` é chamado com a query certa e o
  resultado injetado no consumidor (context-pack/handoff/hint) — mockando
  `mem_find`. Teste de degrade-soft: mem ausente → handler funciona, sem crash,
  sem "forge init".
- **Real-mem read (lição MOCK-BLINDNESS):** ≥1 teste de um read contra o `mem`
  vendorizado REAL (sem mock) — confirma que o find roda e o resultado é
  consumível.
- **Determinismo (test-enforced):** um teste que asserta que nenhum módulo em
  `validators/` importa `engine.integrations.mem` nem chama `mem_*` (varredura
  estática sobre o source dos validators).
- **Cleanup:** asserta que `_apply_consolidate_l2` não existe mais
  (`not hasattr`); footprint sweep por testes que referenciam `add_entry`
  (`test_memory_l2`, `test_memory_distiller`) → reconciliar/remover os que
  testavam a escrita órfã.
- **Full-lane incl. `RUN_E2E=1`** (lição de 6b — lanes env-gated escondem
  regressão; o review final roda os 3 com o gate ligado).

## Footprint observável (varrer por contrato, não por import — lição 6a/6b)

Varrer `tests/` por: asserts de `add_entry`/`_apply_consolidate_l2` (cleanup);
context-pack/handoff de plan/implement/qa (reads — o que o subagente recebe);
output de `verify` pré-cascade (hint); e e2e gated por `RUN_E2E` que toquem
esses fluxos. Reconciliar todos no mesmo ciclo.

## Doc-sync

`docs/design/06-command-surface.md` (comportamento de read documentado, se
muda a descrição de plan/qa/verify/implement — justificativa: doc-sync
Mandamento #6), `CHANGELOG.md` (Unreleased), `docs/design/04-pending.md`
(resolve as entradas de órfão), guides se descrevem esses fluxos.

## Fora de 6c (→ 6d / depois)

- **6d:** re-rota do `forge undo` pra knowledge kinds (blocker proposal→inbox-id).
- **W-AGENTS (Onda 7):** re-rota dos 5 conductor prompts → `mem find`/`mem inbox`.

A camada de wrappers (`mem_find` de 6a) é reusada aqui — 6c não adiciona wrapper
novo (só consome `mem_find`).
