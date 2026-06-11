# DET-3 — Deviations log

## D-1 — CARD-019 já está em uso (legacy-marker), bumped para CARD-020

**Descoberto durante:** pré-Task 4 (review de `engine/cards/loader.py`)

**Issue:** PLAN refere-se a "CARD-019 nova" pra validação de shape de
`gradle-dep`. Inspeção do código vivo mostra que CARD-019 já está
ocupado por `legacy-marker, if present, must be bool` (gap 5, aditivo
de versão anterior).

**Evidence:** `engine/cards/loader.py:524-614` mostra CARD-001..CARD-019
incluindo `CARD-019: legacy-marker` validation. `docs/schemas/card.md:514`
lista o mesmo.

**Decisão (autorizada pelo SPEC):** SPEC §AC-8 diz literal "Validation rule
nova: CARD-019 (**ou next free**)". Próximo livre é **CARD-020**.

**Impact:** PLAN Tasks 4 e 5 substituem todas referências a `CARD-019` por
`CARD-020`. Tests, mensagens de violation, e linha do schema doc usam
CARD-020. Comportamento idêntico ao planejado.

**Rule:** Rule 1 (auto-fix bug — incorrect ID), endereçado inline sem mudar
acceptance criteria.

