# opencode Tool API — Research para Adapter de Host

**Data:** 2026-06-16  
**Objetivo:** avaliar se opencode suporta adapter dedicado in-process (análogo ao `ClaudeCodeAdapter`) ou se o fallback `IntentFileAdapter` é o caminho correto.  
**Fontes primárias:** source code `anomalyco/opencode` (fork pós-rebrand de `sst/opencode`), ACP SDK `agentclientprotocol/typescript-sdk`, documentação oficial `opencode.ai/docs`.

---

## 1. Como opencode invoca tools/subprocessos — formato de mensagem

opencode é construído em TypeScript/Bun e expõe **dois planos de integração** distintos:

### 1a. HTTP API interna (porta 4096 por default)

Quando opencode está rodando em modo `serve` ou como TUI/desktop, ele sobe um servidor HTTP local na `127.0.0.1:4096`. A API segue a interface Effect `HttpApi` e expõe endpoints REST/SSE:

- `GET /event` — SSE stream de eventos do sistema (inclui `question.asked`, `permission.asked`, etc.)
- `GET /question` — lista perguntas pendentes
- `POST /question/:requestID/reply` — responde a uma pergunta
- `POST /question/:requestID/reject` — rejeita uma pergunta
- `POST /permission/:requestID` — responde permissão de tool call

O servidor também responde requisições sem auth por default (auth opcional via `OPENCODE_SERVER_PASSWORD`).

### 1b. ACP (Agent Client Protocol) via NDJSON/stdio

O comando `opencode acp` sobe um servidor JSON-RPC 2.0 sobre stdin/stdout usando Newline-Delimited JSON. Este é o canal de integração com editores (Zed, JetBrains, Neovim/Avante, VS Code via extensão).

**Formato de mensagem ACP (NDJSON):**

```
→ editor envia:  {"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}
← opencode responde: {"jsonrpc":"2.0","id":1,"result":{...}}\n
```

Cada mensagem é um objeto JSON-RPC 2.0 completo, separado por `\n`. O editor é o cliente (inicia requests); opencode (agent-side) responde.

**Métodos ACP principais:**

| Método | Direção | Descrição |
|---|---|---|
| `initialize` | editor → opencode | handshake, troca capabilities |
| `newSession` | editor → opencode | cria sessão de trabalho |
| `prompt` | editor → opencode | envia mensagem do usuário |
| `cancel` | editor → opencode | cancela operação em andamento |
| `sessionUpdate` | opencode → editor | eventos de progresso (chunks de texto, tool calls) |
| `requestPermission` | opencode → editor | pede aprovação de tool call ao usuário |
| `writeTextFile` | opencode → editor | solicita escrita de arquivo (opcional) |

A direção de `requestPermission` e `writeTextFile` é invertida: opencode envia ao editor, não o contrário. Isso é chamado de "AgentSideConnection" no source (`packages/opencode/src/acp/service.ts`).

### 1c. Como subprocessos (bash tool) se comunicam de volta

Quando opencode executa um comando via bash tool (`packages/opencode/src/tool/shell.ts`), o subprocesso é spawned com `stdin: "ignore"`. **Não há canal de volta do subprocesso para o engine** além de stdout/stderr capturados ao final da execução. O output capturado vira o resultado da tool call, que o LLM lê na próxima iteração.

Subprocessos não têm um canal para "pausar o engine e fazer uma pergunta" — esse padrão não existe na arquitetura de bash tool do opencode.

---

## 2. Existe equivalente a `AskUserQuestion`?

**Sim, existe — mas o mecanismo é diferente do ClaudeCodeAdapter.**

opencode tem um sistema de `Question` completo (`packages/opencode/src/question/index.ts`):

### Como funciona:

1. O LLM pode chamar a **`question` tool** (`packages/opencode/src/tool/question.ts`) passando um array de `Question.Prompt` (cada um com `question`, `header`, `options`, `multiple`).

2. A tool invoca `Question.Service.ask(...)`, que:
   - Cria um `Deferred` interno
   - Publica um evento `question.asked` (com schema `Question.Request`)
   - **Suspende** a execução da tool call até receber resposta

3. Qualquer consumidor que escuta o SSE stream (`GET /event`) recebe o evento `question.asked` com o payload:
   ```json
   {
     "id": "...",
     "sessionID": "...",
     "questions": [
       {"question": "...", "header": "...", "options": [...]}
     ],
     "tool": {"messageID": "...", "callID": "..."}
   }
   ```

4. O consumidor responde via `POST /question/:requestID/reply`:
   ```json
   {"answers": [["opção_escolhida"]]}
   ```

5. O `Deferred` resolve, a tool retorna o resultado para o LLM.

### Diferença crítica vs. `AskUserQuestion` do Claude Code:

- **ClaudeCodeAdapter**: a pergunta vai in-process para o host (Claude Code intercepta o marker e chama `AskUserQuestion` nativamente). Latência zero de round-trip.
- **opencode**: a pergunta vai via HTTP (SSE event → POST reply). Requer que haja um consumidor escutando o stream da HTTP API. A TUI e o desktop app fazem isso nativamente. Um adapter externo precisaria implementar esse polling/SSE loop.

### ACP + Elicitation (experimental):

O ACP SDK (`agentclientprotocol/typescript-sdk`) define `CreateElicitationRequest` como tipo experimental:

```typescript
// @experimental — not yet part of the stable spec
type CreateElicitationRequest = {
  mode: "form" | "url";
  message: string;
  requestedSchema: ElicitationSchema; // JSON Schema para form fields
  sessionId: SessionId;
  // ...
}
```

**Porém**: o source do opencode ACP (`packages/opencode/src/acp/event.ts`, `service.ts`) **não implementa** o relay de `question.asked` via ACP. O ACP só roteia `permission.asked` para o editor via `requestPermission`. Perguntas ao usuário via `question` tool não chegam ao cliente ACP pelo protocolo atual — apenas ao consumidor da HTTP API.

---

## 3. Env vars setados pelo opencode para subprocessos

### Env vars que opencode seta para subprocessos bash:

A função `shellEnv` em `packages/opencode/src/tool/shell.ts`:

```typescript
const shellEnv = Effect.fn("ShellTool.shellEnv")(function* (ctx, cwd) {
  const extra = yield* plugin.trigger("shell.env", {...}, { env: {} })
  return {
    ...process.env,   // herda todo o env do processo opencode
    ...extra.env,     // adiciona variáveis do plugin "shell.env"
  }
})
```

**O que isso significa:**
- Subprocesso herda **todo** `process.env` do processo opencode (incluindo `PATH`, credenciais, etc.)
- Não há injeção automática de variável identificadora como `OPENCODE=1` ou `OPENCODE_VERSION=X`
- Plugins podem injetar vars arbitrárias via hook `shell.env`

### Variáveis OPENCODE_* disponíveis no ambiente:

As seguintes vars existem como configuração do próprio opencode (não injetadas em subprocessos por default):

| Variável | Propósito |
|---|---|
| `OPENCODE_CONFIG` | Caminho do config file |
| `OPENCODE_CONFIG_CONTENT` | Override de config em JSON |
| `OPENCODE_SERVER_PASSWORD` | Auth básica para HTTP API |
| `OPENCODE_SERVER_USERNAME` | Auth básica para HTTP API |
| `OPENCODE_DISABLE_AUTOUPDATE` | Desabilita auto-update |
| `OPENCODE_DISABLE_MOUSE` | Desabilita captura de mouse no TUI |
| `OPENCODE_EXPERIMENTAL_*` | Feature flags experimentais |

`OPENCODE_VERSION` existe como **constante compilada** (`declare global { const OPENCODE_VERSION: string }`), não como env var de runtime injetada em subprocessos.

### Estado do issue #1775 ("environment variable to detect OPENCODE"):

Issue aberto em agosto/2025, fechado como "completed" em agosto/2025 (1 dia depois). O único comentário diz "this seems to have regressed in the latest dev branch". Source atual de `shell.ts` e `flag.ts` **não mostra nenhuma injeção de `OPENCODE=1` ou `OPENCODE_VERSION` em subprocessos bash**. O source do plugin `shell.env` também não injeta nada por default.

**Conclusão sobre detecção:** não há variável de ambiente confiável para detectar "estou rodando dentro do opencode" em junho/2026. A detecção via env var **não é possível** de forma oficial e estável. A alternativa viável é:
1. Plugin `shell.env` customizado que injeta `OPENCODE=1` — requer configuração no projeto consumidor
2. Detecção indireta via presença de arquivo `.opencode/` no `cwd` (heurística fraca)
3. `OPENCODE_CONFIG_CONTENT` ou `OPENCODE_CONFIG` presentes no env (indiretto)

---

## 4. Veredito: A ou B

**Veredito: (B) — não compatível com ClaudeCodeAdapter shape. Recomenda fallback `IntentFileAdapter`.**

### Justificativa detalhada:

#### Por que não é (A) — ClaudeCodeAdapter-equivalent:

O `ClaudeCodeAdapter` funciona porque o Claude Code host intercepta um marker em stdout (`<FORGE_INTENT/>`) e responde in-process via `AskUserQuestion`. Isso é possível porque Claude Code tem um protocolo de hooks explícito onde o subprocesso (forge) e o host (Claude Code) compartilham um contrato de stdout-marker → in-process reply.

opencode **não tem** esse mecanismo:

1. **Stdout de subprocesso bash é capturado, não interceptado.** O engine captura stdout/stderr do subprocess ao final da execução para passar ao LLM. Não há parsing de markers em tempo real. Emitir `<FORGE_INTENT/>` em stdout simplesmente viraria output capturado, não um trigger de interação.

2. **Não há env var confiável para detectar opencode.** Sem detecção confiável, o adapter não pode saber que deve usar a path opencode vs. o fallback.

3. **A `question` tool existe, mas é do LLM, não do subprocess.** O mecanismo de ask-user do opencode é a `question` tool que o LLM chama diretamente — não um canal que subprocessos podem acionar. Forge seria chamado como bash tool; dentro do bash tool, não há como forge acionar a `question` tool do opencode.

4. **ACP não roteia perguntas de usuário.** O canal ACP (stdin/stdout) roteia `permission.asked` mas não `question.asked`. Um adapter ACP teria que ser o editor-side (rodar como cliente ACP), o que é uma integração de nível completamente diferente — forge se tornaria um editor ACP client, não um subprocess.

#### O que existe e é utilizável:

O **OpenCodeHTTPAdapter** seria factível em teoria: forge detecta opencode pela presença de `OPENCODE_CONFIG` ou similar, conecta na HTTP API local (`http://127.0.0.1:4096`), faz polling no SSE stream e posta respostas. Mas:
- Requer que opencode já esteja rodando com `serve` mode (não é garantido quando forge é invocado via bash tool no TUI)
- Adiciona latência e complexidade de rede local
- Não há env var oficial para descobrir a porta dinamicamente
- A HTTP API não tem auth-free guarantee estável

Esse adapter seria **mais complexo que o IntentFileAdapter** e com garantia menor de funcionar.

#### Recomendação concreta:

Para a wave de opencode adapter em v1.3:

- **Usar `IntentFileAdapter` como adapter para opencode.** Ele funciona por definição em qualquer ambiente (é arquivo). O opencode bash tool captura o exit code 2 (paused-for-input), o que inicia o protocolo intent-file normalmente.
- **Adicionar detecção heurística** no `host_detector.py` para identificar opencode: presença de `OPENCODE_CONFIG` ou `.opencode/` no projeto. Resultado: `host=intent-file` (não `host=opencode-specific`).
- **Documentar** que opencode não recebe perguntas inline — o usuário verá o arquivo de pending e precisará responder via response file (ou via wrapper de automação). Isso é aceitável dado que opencode já é um ambiente de automação.
- **Não criar `OpenCodeAdapter`** até que o opencode exponha um mecanismo de subprocess-to-host communication (issue #1775 ou equivalente futuro).

---

## 5. Sources

- [ACP protocol docs — opencode.ai/docs/acp](https://opencode.ai/docs/acp/)
- [opencode CLI docs — opencode.ai/docs/cli](https://opencode.ai/docs/cli/)
- [opencode config docs — opencode.ai/docs/config](https://opencode.ai/docs/config/)
- [GitHub anomalyco/opencode source — packages/opencode/src/acp/](https://github.com/anomalyco/opencode/tree/main/packages/opencode/src/acp)
- [GitHub anomalyco/opencode — packages/opencode/src/question/index.ts](https://github.com/anomalyco/opencode/blob/main/packages/opencode/src/question/index.ts)
- [GitHub anomalyco/opencode — packages/opencode/src/tool/question.ts](https://github.com/anomalyco/opencode/blob/main/packages/opencode/src/tool/question.ts)
- [GitHub anomalyco/opencode — packages/opencode/src/tool/shell.ts](https://github.com/anomalyco/opencode/blob/main/packages/opencode/src/tool/shell.ts)
- [GitHub anomalyco/opencode — packages/opencode/src/server/routes/instance/httpapi/groups/question.ts](https://github.com/anomalyco/opencode/blob/main/packages/opencode/src/server/routes/instance/httpapi/groups/question.ts)
- [GitHub anomalyco/opencode — packages/core/src/flag/flag.ts](https://github.com/anomalyco/opencode/blob/main/packages/core/src/flag/flag.ts)
- [GitHub sst/opencode — Issue #1775: environment variable to detect OPENCODE](https://github.com/sst/opencode/issues/1775)
- [GitHub agentclientprotocol/typescript-sdk — src/schema/types.gen.ts](https://github.com/agentclientprotocol/typescript-sdk/blob/main/src/schema/types.gen.ts)
- [DeepWiki sst/opencode — Agent Client Protocol (ACP)](https://deepwiki.com/sst/opencode/7.4-agent-client-protocol-(acp))
- [Agent Client Protocol overview — agentclientprotocol.com](https://agentclientprotocol.com)
- [byteiota.com — Agent Client Protocol: The LSP for AI Coding Agents](https://byteiota.com/agent-client-protocol-lsp-ai-coding-agents/)
