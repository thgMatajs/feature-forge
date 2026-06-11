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
