# Disciplinas universais — quick reference

Síntese das 6 disciplinas universais de `docs/design/07-discipline.md`.
Enxugado pro ponteiro — o template canônico de 3-caminhos e o detalhe das
disciplinas (cascade fail-fast, pause/abort, `.bak` retention, vocabulário
project-native, fingerprint de proposta rejeitada) vivem no `mem`.

## Invariante always-on

- Em QUALQUER gate, apresente **exatamente 3 caminhos** — nunca 2, nunca 4.
  "Escalate/abort explícito" é caminho legítimo quando não há fix-forward.
- Validator cascade **para no primeiro erro hard**, segue passando warnings
  (fail-fast por default — Decisão 23).

## Detalhe (recupere por tema)

```bash
.claude/bin/mem find "exatamente 3 caminhos em todo gate template"
.claude/bin/mem find "6 disciplinas universais cascade fail-fast pause abort .bak fingerprint"
```

Fonte canônica: `docs/design/07-discipline.md`. Em conflito, esse doc vence.
