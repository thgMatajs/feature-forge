# Decisões — protocolo de manipulação

Como respeitar `docs/design/01-decisions.md`. Mandamento #1. Enxugado pro
ponteiro — o detalhe (as 8 load-bearing, as 7 direcionais, a distinção de
tipos) vive no `mem`. O **ritual de revisita** fica enunciado aqui porque é
invariante de enforcement (o pre-commit hard-block depende dele).

## Invariante always-on — o ritual "Revisita decisão N"

Quando há razão real pra revisitar uma decisão locked (raríssimo):

1. **Brainstorm explícito** com o user, lendo o rationale original primeiro.
2. **Dispatch edit** em `docs/design/01-decisions.md` + `CHANGELOG.md` com:
   - APPEND da nova linha; NÃO deleta a antiga (marca como
     "(superseded by row X — YYYY-MM-DD)").
   - Entrada em CHANGELOG `### Changed (load-bearing)` com o TEXTO LITERAL
     "Revisita decisão N: <novo choice> — <rationale>".
   - Commit message contém "Revisita decisão N".
3. **Review** com foco: histórico preservado (append-only) + texto literal
   presente no CHANGELOG e no commit.
4. O hook `.claude/hooks/pre-commit-feature-forge.sh` faz HARD BLOCK se
   `01-decisions.md` é staged sem "Revisita decisão" no CHANGELOG staged.
   No fluxo correto isso NUNCA dispara.

## Detalhe (recupere por tema)

```bash
.claude/bin/mem find "8 decisões load-bearing Config scope persistence SQLite cascade fail-fast"
.claude/bin/mem find "como revisitar decisão locked sem silent drift"
```

Fonte canônica: `docs/design/01-decisions.md`. Em conflito, esse doc vence.
