# Disciplinas universais — quick reference

Síntese das 6 disciplinas em `docs/design/07-discipline.md`. Em conflito,
o doc original vence.

## 1. 3-caminhos pattern (gate-resolution universal)

Em QUALQUER gate (falha de validator, violação de escopo, artefato
faltando, ambiguidade, contradição entre contracts), o agente apresenta
**exatamente 3 caminhos**. Nunca 2, nunca 4, nunca "consulte a documentação".

**Onde LLM erra:** tende a apresentar 2 caminhos óbvios e parar; ou inventa
um 4º caminho fake quando o 3º genuíno seria "abort". Lembrar: 3 é canônico,
e "escalate/abort explícito" é caminho legítimo quando não há fix-forward.

### Template canônico (cole quando bloqueia)

```
🛑 {nome-do-gate}

O que falhou:
  {explicação em 1-2 linhas}

Onde:
  {arquivo:linha ou artefato:campo}

Por que importa:
  · {regra violada}
  · {contract referenciado}
  · {consequência se passar}

Três caminhos pra resolver:

  1) {Caminho A — fix forward}
     {motivo provável}

  2) {Caminho B — revert}
     {motivo provável}

  3) {Caminho C — split / escalate}
     {motivo provável}

Sem auto-fix aqui — escolha humana.
```

## 2. Validator cascade — fail-fast por default

Cascade **para no primeiro erro hard**, continua passando por warnings.
Vale pra `forge verify`, `forge doctor`, hook `post-subagent-validate`, e
qualquer ponto que rode N validators em sequência.

**Onde LLM erra:** tende a "rodar todos e mostrar resumo" mesmo em modo
fail-fast. Ler `docs/design/07-discipline.md §2` pra Override
(`validators.fail-fast: false` em workflow-config).

## 3. Pause vs abort

Ctrl+C / "para" = pause (state `deferred`, auto-resumable). Abort terminal
só via `forge undo` interativo escolhendo "abort feature entirely".

**Onde LLM erra:** descarta state ao receber sinal de interrupt; ou ao
contrário, persiste demais e não deixa abort claro.

## 4. `.bak` retention

7 dias default (configurável em `cleanup.bak-retention-days`). `forge
doctor` reporta overdue. NUNCA auto-deleta — limpeza via menu interativo
em `forge reconfigure`.

**Onde LLM erra:** sugerir `rm *.bak` na primeira vista. Não. Mostrar
`forge reconfigure` path.

## 5. Project-native vocabulary

Engine lê `CLAUDE.md` e `.claude/rules/*` + `docs/design/*`. Vocabulário do
projeto > vocabulário genérico. "Forge" só como verbo (Decision 4). Persona
"mentor calmo" em todos os artefatos gerados.

**Onde LLM erra:** voz corporativa, emoji decorativo, jargão genérico
("seja cuidadoso", "considere", "pode ser uma boa ideia").

## 6. Rejected proposal fingerprint

`sha256` sobre canonical-form `{type, name, normalized-description,
sorted-provenance-set}`. Estável contra timestamps e edits cosméticos;
muda quando conteúdo ou evidência mudam.

**Onde LLM erra:** sugerir mudar fingerprint quando proposta similar
re-aparece. Não — fingerprint deve mudar APENAS via mudança em
conteúdo/evidence; re-apresentação com mesmo fingerprint deve ser
silenciada (proposal já foi vista).

## Fonte canônica

`docs/design/07-discipline.md` é detalhado, com exemplos vivos do projeto
(forge-implement-roteiro Cena 6, forge-verify-roteiro Cena 4, etc.).
Quando este rule e o doc divergirem, **doc original vence**.
