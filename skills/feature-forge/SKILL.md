---
name: feature-forge
description: Dirige o feature-forge — orquestra o ciclo de planejamento e implementação de features mobile. Use ao rodar qualquer comando `forge`.
---

# feature-forge — driver

Você dirige o `forge`. O engine emite intenções e pausa; você responde e re-invoca.

## Protocolo do intent loop

Ao rodar um comando `forge` que sai com **exit 2** + uma linha
`<FORGE_INTENT kind=... intent-id=... question=... options=... .../>` no stdout:

1. Parseie os atributos do marker (`kind`, `intent-id`, `question`, `options`).
2. Chame `AskUserQuestion` nativo com o `question` + `options`.
3. Escreva `.claude/forge/state/forge-response.json` no schema de
   `docs/schemas/intent-protocol.md`, com o **mesmo `intent-id`**.
4. Re-invoque o `forge` com **argv idêntico** ao da chamada que pausou.
5. Repita até exit 0, 1 ou 130.

Legenda de exit: **0**=ok · **1**=erro · **2**=pausado (responda) · **130**=cancelado.

> Re-invoque com argv idêntico. Mudar o argv troca o `intent-id` e o engine
> rejeita (exit 1).

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
