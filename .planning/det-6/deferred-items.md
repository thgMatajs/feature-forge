# DET-6 Phase B — Deferred items (out of scope)

Items discovered during W2 execution that are pre-existing and unrelated
to the category cleanup. Logged here per executor `SCOPE BOUNDARY` rule.

## Flaky test (time-dependent)

**File:** `tests/engine/qa/test_common.py::test_utc_iso_z_never_uses_plus_offset`
**Discovered:** W2 rapid-lane run on 2026-06-11T00:00 UTC
**Failure mode:**
```
AssertionError: assert '00:00' not in '2026-06-11T00:00:48Z'
```

**Root cause:** o test usa `assert "00:00" not in utc_iso_z()` como
belt-and-suspenders contra `+00:00`, mas falha sempre que o wall-clock
está dentro de `00:00:SS` UTC (uma janela de 60 segundos por dia). É
bug pre-existente — não tocado por W2 (W2 só mexe em `cards/*/card.yaml`,
`engine/cards/loader.py`, `tests/unit/test_cards_loader.py`,
`.planning/det-6/category-migration-audit.json`).

**Fix sugerido (não aplicado em W2):** trocar o assert por verificação
de regex/sufixo (`assert not re.search(r"[+-]\d{2}:\d{2}", out)`) — o
re_ISO_Z_RE no test acima já cobre o formato exato.

**Status:** deferido — não bloqueia W2. Endereçar em follow-up dedicado
ou na W8 (doc-sync + cleanup) de DET-6 se o user concordar.

**Origem:** SCOPE BOUNDARY rule — auto-fix só pra issues directly
causados pelas mudanças do task atual.

---

## Integration fixtures usando `category: network` (W2 spillover)

**Files (descobertos em W3 full-suite run):**
- `tests/integration/test_e2e_local_card_pilot.py::test_pilot_local_card_added_appears_in_cascade`
- `tests/integration/test_e2e_local_card_pilot.py::test_pilot_local_cards_manifest_written`
- `tests/integration/test_claude_rules_system.py::test_bootstrap_is_idempotent` (failure cascade do mesmo issue)

**Failure mode:**
```
engine.cards.CardError: ... CARD-004: identity.category must be one of
['analytics', 'auth', 'build', 'data', ...], got 'network'
```

**Root cause:** fixtures montam card stub com `"category": "network"`
(`tests/integration/test_e2e_local_card_pilot.py:80`). W2 removeu
`network` do set `_KNOWN_CATEGORIES` no loader (`backend`/`network` foram
split nos 8 axes via category-migration-audit). Loader corretamente
rejeita; fixture quem precisa atualizar pra `category: data` (ou
similar).

**Por que NÃO foi fixado em W3:** SCOPE BOUNDARY rule — failures não são
causadas pelas mudanças de W3 (label refactor), são W2 spillover.
W3 só toca cards específicos (5 cards listados) + loader CARD-006 +
catalog markdown + 1 test file (`test_cards_resolver.py`). Fixture
update em `tests/integration/*` é tarefa W2 follow-up ou W8 cleanup.

**Fix sugerido:** mudar `"category": "network"` → `"category": "data"`
no fixture (`test_e2e_local_card_pilot.py:80`). Pequeno; trivial. Pode
entrar em W8 (doc-sync) ou follow-up dedicado.

**Status:** deferido — não bloqueia W3. Endereçar em follow-up.

**Verificação rapid-lane preservada:** `pytest -m "not integration and
not e2e"` continua 100% verde em W3 (1029 passed). Failures vivem só
no integration lane (3 falhas, todas pré-existentes desde W2).
