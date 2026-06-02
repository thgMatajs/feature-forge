# Scope discipline

Mandamento #4: edite só o que a tarefa pede. Em dúvida, **pergunte ao
usuário** (não decida).

## Regra cardinal

Subagent recebe lista explícita de "ARQUIVOS PERMITIDOS PARA EDIT" no
context-pack. Sair desta lista = violação de scope, dispatch revert.

## Arquivos load-bearing (sempre confirmar antes de Write/Edit)

Estes têm hook PreToolUse que avisa (audit em
`.claude/state/load-bearing-edits.jsonl`):

```
docs/design/00-vision.md
docs/design/01-decisions.md
docs/design/05-filesystem-layout.md
docs/design/06-command-surface.md
docs/design/07-discipline.md
docs/schemas/**
presets/**
cards/**
CLAUDE.md
.claude/rules/**
```

Se task autêntica precisa tocar esses, OK — context-pack já incluiu na
whitelist. Hook só avisa, não bloqueia.

## Anti-padrões observados

### "Vou aproveitar pra atualizar isso também"

Aparece como "while I'm here, let me fix this typo nearby" ou "isso aqui
está mal nomeado, vou renomear de passagem". NÃO. Anota em
`docs/design/04-pending.md` como gap separado. Tarefa nova, dispatch novo.

### Refactor não solicitado

Aparece como "limpar um pouco o código que estou tocando". NÃO. Se o
código está ruim, abre task de refactor separada com brainstorming +
writing-plans. Rendimento misturado = scope creep + review impossível.

### Rename "while I'm here"

Aparece como "var é mal nomeada, rename de aproveitando". NÃO. Rename
afeta consumers — task separada. Especialmente: rename em código exportado
(public API) é Decision territory.

### Tocar arquivos não relacionados pra "consistency"

Aparece como "outros lugares usam pattern X, vou alinhar". Se o pattern
está alinhado a `docs/design/*`, propose como gap. Se está alinhado a uma
preferência pessoal sem base no projeto, NÃO faça.

## Exceção legítima

**Doc-sync na mesma mudança (Mandamento #6).** Quando você toca
`engine/`, `validators/`, `hooks/`, etc., DEVE atualizar:
- `CHANGELOG.md` (Unreleased)
- `docs/design/08-session-handoff.md` (Última atualização)
- `README.md` (se stats mudaram)

Isso NÃO é scope creep — é mandamento explícito. Matriz completa em
[doc-sync.md](doc-sync.md).

## Em dúvida

Se subagent não sabe se mudança X está in-scope:

1. **Pare a edição**
2. Reporta ao orchestrator
3. Orchestrator pergunta ao usuário via `AskUserQuestion`
4. Usuário decide (in-scope ou separar)

Custo de perguntar < custo de scope creep silencioso. Subagent **nunca**
expande escopo por iniciativa própria.

## Detection mecânico

Hook `pre-tool-use-load-bearing.sh` (PreToolUse Edit/Write) emite:

```
🛑 LOAD-BEARING edit: <arquivo>
Confirme intenção. Se revisita decisão locked, commit deve dizer
"Revisita decisão N".
```

Aparece no contexto da sessão. Se você vê esse aviso e o arquivo NÃO está
na whitelist do context-pack atual → scope creep iminente, aborta.

Audit log: `cat .claude/state/load-bearing-edits.jsonl | jq .` revisa
histórico de tentativas.
