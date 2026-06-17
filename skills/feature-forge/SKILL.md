---
name: feature-forge
description: Dirige o feature-forge — orquestra o ciclo de planejamento e implementação de features mobile. Use ao rodar qualquer comando `forge`.
---
<!-- FORGE_AI_DRIVER -->

# feature-forge — driver

Você dirige o `forge`. O engine emite intenções e pausa; você responde e re-invoca.

## Protocolo do intent loop

Ao rodar um comando `forge` que sai com **exit 2** + uma linha
`<FORGE_INTENT kind=... intent-id=... question=... options=... default=... allow-pause=... .../>`
no stdout:

1. **Parseie os atributos do marker.** Sempre presentes: `kind`, `intent-id`,
   `question`, `options`, `default`, `allow-pause`. Opcionais: `validator-hint`,
   `min-selected`, `paths-detail`. Todos os valores vêm XML-attribute-escaped
   (`&amp; &lt; &gt; &quot; &apos;`) — **unescape as entidades XML** ao ler.
2. **`options` vem JSON-encoded** — faça `JSON.parse` pra obter o dict
   `{key: label}` (não trate como texto plano; um blob JSON cru passado como
   label quebra o `AskUserQuestion`).
3. **Chame `AskUserQuestion`** nativo com `question` + as opções decodificadas
   (cada `label` vira uma opção; o `key` é o que você devolve na response).
   Respeite `default` (key pré-selecionada quando ≠ `"null"`) e `allow-pause`
   (`false` → não ofereça pausa). Pra `kind=ask_multi`, `min-selected` é o piso
   de seleções.
4. **Se `kind=ask_three_paths`**, parseie também `paths-detail` — uma lista JSON
   `[{"key","label","motive"}, ...]`. Renderize o bloco 3-caminhos canônico
   (disciplina §1) usando `label` + `motive` por caminho: no `AskUserQuestion`,
   `label` → label da opção, `motive` → description (o "motivo provável" de cada
   caminho). Sem `motive`, o prompt fica anêmico — viola o template de gate.
5. **Escreva `.claude/forge/state/forge-response.json`** com o **mesmo
   `intent-id`** (schema completo em `docs/schemas/intent-protocol.md`).
6. **Re-invoque o `forge` com argv idêntico** ao da chamada que pausou.
7. Repita até exit 0, 1 ou 130.

Legenda de exit: **0**=ok · **1**=erro · **2**=pausado (responda) · **130**=cancelado.

> Re-invoque com argv idêntico. Mudar o argv troca o `intent-id` e o engine
> rejeita (exit 1).

Atributos, kinds e shape da response em detalhe: `docs/schemas/intent-protocol.md`.

## Workflow — mapa de verbos

| Verbo | O que dirige |
|---|---|
| `forge init` | install no projeto (interativo via intent loop) |
| `forge plan "<ticket\|frase\|slug>"` | planejamento — ver abaixo |
| `forge implement` | dirige a execução das waves |
| `forge verify` | cascade de validators |
| `forge status` | estado da feature |

**Ao rodar `forge plan`:** depois que o engine derivar/confirmar o slug e
semear o intake, **dispatch `agents/planning-conductor.md` (lido do FORGE_HOME)**
e dirija a elicitação dele — o conductor usa `AskUserQuestion` direto. O
screenshot entra conversacionalmente (path na source-inquiry), sem flag.
