# Reuso — antes de criar, consulte

Mandamento #3. Enxugado pro ponteiro — o detalhe (as graph queries Q11-Q17,
o grep fallback, o inventory pra UI/strings, os 3-caminhos pra near-duplicate,
a infra compartilhada de validators e como compor) vive no `mem`.

## Invariante always-on

Antes de criar helper/função/template/card/validator, consulte: `forge
graph` (Q11 reusable-helpers; Q12-Q17 reuse-intelligence), `engine/inventory/`,
e `cards/`/`templates/`/`validators/`. Se o graph diz "near-duplicate" →
3-caminhos (consolidar / promover pra shared / criar nova com justificativa
no commit body). Compor a infra compartilhada de validators
(`_gate_infra`/`_diff`/`_common`) é preferível a copiar.

## Detalhe (recupere por tema)

```bash
.claude/bin/mem find "reuso forge graph antes de criar helper"
.claude/bin/mem find "near-duplicate três caminhos consolidar promover shared"
.claude/bin/mem find "infra compartilhada validators _gate_infra _diff _common compor"
```

Pointer canônico: `docs/lifecycle/memory-and-graph.md`.
