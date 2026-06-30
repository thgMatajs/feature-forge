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

## Fulfillment do intent `kind:"classify"`

Quando o engine pausa pra uma classificação de rules (`kind:"classify"`), o
fluxo difere do loop padrão: não há `AskUserQuestion` — você, como host-LLM,
FAZ a classificação e escreve a response diretamente.

### Como reconhecer

O pending tem `"kind": "classify"` e carrega `"fragments"` (lista de
fragmentos de texto das rules do consumidor) mais `"classification-schema"`.

**ClaudeCodeAdapter** (CLAUDECODE=1): o marker stdout `<FORGE_INTENT kind="classify" .../>` sinaliza o pending; os fragments grandes vivem em
`forge-pending.json` — leia-o pra obter o payload completo.

**IntentFileAdapter** (FORGE_FORCE_INTENT_MODE=1): apenas `forge-pending.json`;
sem marker stdout. Leia o arquivo pra obter fragments + schema.

**TtyAdapter** (host sem LLM): o engine retorna `None` diretamente; sem
pending, sem pausa. `_reduce_rules` pula com aviso — nenhuma ação do host.

### Como classificar

Para cada fragment em `fragments`:

- **`tier: 0`** — invariante sempre-on: gates, enforcement, regras com
  "NUNCA/sempre", bloqueadores hard, cerimônias obrigatórias. Permanece no
  arquivo de rule inline.
- **`tier: 1`** — referência, exemplo, detalhe recuperável, contexto de
  consulta. Vai pro mem (você gerará o `mem_note`).

Gere `mem_note` **somente para tier 1**:
```json
{
  "type": "reference",
  "title": "<título conciso do conteúdo>",
  "body": "<texto do fragmento — corpo acionável>",
  "tags": ["<tema-a>", "<tema-b>"]
}
```

`tier` é sempre **int** (`0` ou `1`), nunca string.

### Revisão (revise — M-202)

Se `classification-schema` traz `"revise": true` + campo `"prior"` (a
classificação anterior que o humano pediu pra ajustar), re-classifique
considerando o `prior` como feedback: o humano discordou do split anterior —
devolva um split revisado no MESMO formato. Um fragment pode mudar de tier;
gere `mem_note` pra qualquer tier 1 resultante. O `intent-id` será novo
(schema mudou) — a resposta vai pro novo pending, não ao anterior.

### Response a escrever

Escreva `.claude/forge/state/forge-response.json` com:
```json
{
  "schema-version": 1,
  "intent-id": "<mesmo intent-id do pending>",
  "classification": [
    {
      "fragment_id": "<id do fragmento — campo 'id' do pending>",
      "tier": 0,
      "rationale": "<por que tier 0: é invariante always-on>"
    },
    {
      "fragment_id": "<id do outro fragmento>",
      "tier": 1,
      "rationale": "<por que tier 1: detalhe recuperável>",
      "mem_note": {
        "type": "reference",
        "title": "<título>",
        "body": "<texto do fragmento>",
        "tags": ["<tag>"]
      }
    }
  ],
  "answered-at": "<ISO-8601 UTC>"
}
```

Todo fragment recebido em `fragments` deve aparecer em `classification`
(um-pra-um). Não omita fragments; não invente fragment_ids.

Re-invoque o `forge` com argv idêntico ao que pausou. O engine consume a
response, move tier-1 pro mem, e exibe a proposta de 3-caminhos (G1/G2).

## Workflow — mapa de verbos

| Verbo | O que dirige |
|---|---|
| `forge init` | install no projeto (interativo via intent loop) |
| `forge plan "<ticket\|frase\|slug>"` | planejamento — ver abaixo |
| `forge implement` | dirige a execução das waves |
| `forge verify` | cascade de validators (gate "verde antes de pronto") |
| `forge status` | board read-only do projeto (features, memória, git, qa verdict) |
| `forge qa "<slug\|paranoid>"` | red-team adversarial da feature; emite verdict (PASS/BLOCK) |
| `forge doctor` | diagnóstico do setup (paths, version-lock, secrets-tools, .bak) |
| `forge reconfigure` | re-ajusta config/cards/external-deps do projeto |
| `forge graph` | consultas Q1–Q17 ao grafo (reuso, dependências, impacto) |
| `forge memory` | drena/consulta a memória (mem) — tier-1 e proposals |
| `forge evolve` | revisa e aplica proposed-evolutions (3-caminhos) |
| `forge undo` | reverte a última operação destrutiva (last/reconfigure) |
| `forge raw` | utilitários de manutenção do FORGE_HOME (ex.: rebuild-templates) |
| `forge upgrade` | atualiza o forge no FORGE_HOME (use `--dry-run` pra preview) |

**Ao rodar `forge plan`:** o comando é interativo wave-a-wave. Duas coisas
acontecem interleaved — não confunda:

1. **O engine dirige o stepping das waves** e emite os PRÓPRIOS prompts
   `<FORGE_INTENT>` ao longo do loop (exit 2 a cada um). Responda cada um pelo
   intent loop acima: confirm de slug, subtype, sub-questão de bugfix (se for),
   source-inquiry de screenshot, task-count na Wave D, e o gate
   continuar/pausar ao fim de cada wave (A→B→C→D→E). Esses prompts são
   mecânicos — o engine renderiza o ESQUELETO de cada wave e pausa.
2. **O conductor preenche o CONTEÚDO** de cada esqueleto. Entre os gates de
   continuar, **consulte `agents/planning-conductor.md` (lido do FORGE_HOME)**
   pra saber COMO fazer a elicitação profunda e preencher os artefatos que o
   engine renderizou — Phase 4 do conductor é onde mora a elicitação real.

Ou seja: "dispatch o conductor" **não** é um passo único no início que assume o
volante — o engine continua dirigindo o stepping. O conductor é o trabalho que
preenche os esqueletos conforme o wave-loop avança. O screenshot entra
conversacionalmente (path na source-inquiry que o engine emite), sem flag.
