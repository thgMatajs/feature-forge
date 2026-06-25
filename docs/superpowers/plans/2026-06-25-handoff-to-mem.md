# Fase 0.5 — handoff de sessão → mem (re-route) · Implementation Plan

> **For agentic workers:** este plano segue o terminal-state do
> `superpowers:writing-plans`. A execução é despachada via subagentes
> (Mandamento 0 — o orquestrador nunca edita direto). **REQUIRED SUB-SKILL:
> `subagent-driven-development`**. As mudanças aqui são de **hooks bash**,
> **docs** e **notas mem** — nenhuma muda código Python, então a verificação
> de cada task é **invocação sintética** (no espírito do `SMOKE-CHECKLIST.md`:
> `echo '<json>' | bash <hook>` + inspeção de stdout/stderr/side-effect),
> NUNCA pytest. A suíte é rodada uma vez no gate de aceite (T6) só pra provar
> que nada de Python regrediu.

> **Voz:** mentor calmo em todo artefato gerado (mensagens de hook, notas mem,
> nota de congelamento). Sem voz corporativa, sem emoji decorativo (✅⏭️🤔 do
> template 3-caminhos são OK).

---

## Goal

O `mem` assume o estado-de-sessão do próprio repo forge: o
`session-start-orientation.sh` passa a injetar o último `mem session`
(fallback gracioso pro grep do arquivo), os três hooks/docs que apontavam pro
`08-session-handoff.md` re-roteiam pra `mem session` no fim de sessão, o
arquivo congela como snapshot histórico + rede de bootstrap, e os hooks do mem
são instalados coexistindo aditivamente com os do forge.

---

## Architecture

O estado-de-sessão deixa de viver num arquivo único-sobrescrito e passa a
viver em notas `mem session` append-only committed (uma por sessão
significativa, decaem no `find`/`brief` padrão mas ficam no git e são
listáveis via `--type session`). O `session-start-orientation.sh` lê o handoff
curado mais recente do mem por um caminho de dois passos
(`find --type session -k 1` → `get <id>`) com fallback gracioso pro grep dos
dois campos do arquivo quando o mem está vazio/ausente/falhando, mantendo o
contrato de exit 0 e o bloco hardcoded de Mandamento 0. Os hooks do mem
(`Stop`/`UserPromptSubmit`/`SessionStart`/`PostToolUse`) são somados aos do
forge no `.claude/settings.json` via `mem install-hooks --apply`, cujo
`_merged_settings` preserva as entradas não-mem por evento (merge soma, não
sobrescreve).

---

## Tech Stack

- **mem** — `.claude/bin/mem` (script único Python3 stdlib, vendorizado v0.8.1,
  schema v4). **O flag global `--json` precede o subcomando**
  (`mem --json find ...`, NÃO `mem find --json ...`). Exit codes: `0` ok ·
  `1` uso · `2` não-encontrado · `3` interno. Invocações usadas neste plano,
  confirmadas no scout (rodadas contra o acervo real):
  - **Último handoff curado (dois passos):**
    `.claude/bin/mem --json find "" --type session -k 1` → retorna lista JSON;
    extrai `.[0].id`; depois
    `.claude/bin/mem --json get <id>` → retorna `{id,type,title,body,
    git_meta,...}`; o corpo do handoff é `.body` (e `git_meta` é um JSON-string
    aninhado com `branch`/`head`/`commits`). Confirmado: `find ""` com
    `--type session` entra no branch no-FTS e ordena por `score` (sessions
    decaem agressivamente → a mais recente tem o maior score, então `-k 1`
    surfa a última sessão; quando não há sessão, retorna `[]` com exit 0). O
    `get` registra um access em `access_log` (efeito esperado de uma leitura
    real; mesmo comportamento da skill `mem-resume`).
  - **Re-classificar nota do acervo:** `.claude/bin/mem add ...` (cria a versão
    corrigida) + `.claude/bin/mem supersede NEW_ID OLD_ID` (marca a antiga
    superseded, preservando-a no JSONL append-only — `supersede` recebe
    `NEW_ID OLD_ID` nessa ordem, confirmado no `--help`).
  - **Hooks do mem:** `.claude/bin/mem install-hooks --tool claude-code --apply`
    (dry-run sem `--apply`). `_HOOK_WIRING` = `{Stop, UserPromptSubmit,
    SessionStart, PostToolUse}`; `_HOOK_MATCHERS` = `{PostToolUse: "Edit|Write"}`
    (resto `""`). `_merged_settings` faz, por evento: `kept = [entradas que NÃO
    são hook-do-mem] + [a entrada do mem]` — ou seja, **soma** (preserva as
    entradas do forge), **não sobrescreve**. `PreToolUse` não está em
    `_HOOK_WIRING` → fica intocado.
- **bash** — os três hooks alvo. `session-start-orientation.sh` NÃO usa
  `set -euo pipefail` (contrato exit-0, R3.5); os outros dois usam.
- **python3** — usado dentro do hook só pra parsear o JSON do mem (stdlib
  `json`), mesmo padrão já presente em `post-edit-doc-drift.sh`.
- **git** — `/usr/bin/git` em todos os comandos (o proxy rtk pode vaziar
  output). Branch única `feat/mem-integration`.
- **pytest** — `.venv/bin/pytest` (canonical — tem json5 + deps; system pytest
  gera false-fail). Só roda no gate de aceite (T6).

---

## Global Constraints

Copiados verbatim das premissas do spec (§Decisões resolvidas, §SessionStart
re-route, §adoção dos hooks do mem). Inegociáveis pra toda task abaixo:

- **HYBRID — não-deleta.** O `08-session-handoff.md` vira arquivo-morto
  histórico + fallback de bootstrap; **não deletar** (Decisão #1). Migrar pro
  mem é aditivo: o estado passa do arquivo único-sobrescrito pra uma série de
  notas `mem session` append-only versionadas — mais histórico, não menos.
- **SessionStart sempre exit 0 + Mandamento 0 hardcoded permanece.** O hook
  nunca trava em nenhum caminho; se a invocação do mem falha (binário ausente,
  JSON inesperado, timeout, `[]` vazio) degrada pro fallback do arquivo, depois
  pro `(handoff missing)` de hoje — sempre `exit 0`. O bloco hardcoded de
  Mandamento 0 + fluxo (linhas 42–60 do hook hoje) **PERMANECE** no hook, NÃO
  vem do mem — o orquestrador não pode depender de o mem estar populado pra
  saber que é o orquestrador.
- **`/usr/bin/git`** em todo comando git (proxy rtk vaza output).
- **`.venv/bin/pytest`** é canonical (system pytest gera false-fail).
- **Branch única `feat/mem-integration`.** Todo o trabalho acumula nela; um PR
  ao final. Sem worktree por task. NÃO criar branch nova por task.
- **mem `--json` é flag GLOBAL antes do subcomando** (`mem --json find ...`,
  nunca `mem find --json ...` → `unrecognized arguments`).
- **Gate de coexistência (merge soma, não sobrescreve).** Após
  `mem install-hooks --apply`, os hooks do forge (`session-start-orientation`,
  `post-edit-doc-drift`, `pre-tool-use-load-bearing`, git `pre-commit`)
  continuam registrados e funcionais no `.claude/settings.json`. Se algum hook
  do forge for sobrescrito → **PARAR** (3-caminhos), não prosseguir.

---

## Task 1 — SessionStart re-route (P1)

Re-roteia o `session-start-orientation.sh`: tenta injetar o corpo do último
`mem session`; se mem vazio/ausente/erro → fallback pro grep dos dois campos
do arquivo (comportamento de hoje). Preserva o bloco hardcoded de Mandamento 0
e o contrato exit 0.

### Files

- **Modify:** `.claude/hooks/session-start-orientation.sh`

### Interfaces

- Entrada: evento SessionStart (sem payload relevante — o hook não lê stdin).
- Saída: stdout (injetado como contexto). Contrato: **sempre exit 0**.
- Dependência externa: `.claude/bin/mem` (opcional — degrada se ausente) +
  `python3` (já assumido pelo projeto, usado no parse do JSON do mem).

### Steps

- [ ] Substituir o bloco "Extract handoff metadata" (linhas 26–34 de hoje):

  **ANTES** (linhas 26–34):
  ```bash
  # Extract handoff metadata
  UPDATED="(handoff missing)"
  STATE_LINE="(handoff missing)"
  if [[ -f "$HANDOFF" ]]; then
      UPDATED=$(grep -m1 '^\*\*Última atualização:\*\*' "$HANDOFF" \
          | sed 's/^\*\*Última atualização:\*\* //' || echo "(unknown)")
      STATE_LINE=$(grep -m1 '^\*\*Estado:\*\*' "$HANDOFF" \
          | sed 's/^\*\*Estado:\*\* //' || echo "(unknown)")
  fi
  ```

  **DEPOIS** (mantém a mesma posição; `MEM_BIN` declarado logo após `HANDOFF`
  no topo do arquivo — ver step seguinte):
  ```bash
  # ── Session state: tenta o último `mem session`, fallback pro arquivo ──
  # Contrato exit-0 (R3.5): o hook NÃO usa `set -e`; toda etapa abaixo
  # degrada graciosamente (mem ausente → fallback grep → "(handoff missing)").
  MEM_BODY=""
  if [[ -x "$MEM_BIN" ]]; then
      # Passo 1: id da última `mem session` (score-ordered; a mais recente
      # decai menos → maior score → topo de `-k 1`). `[]` quando não há
      # sessão → SID vazio → cai no fallback. Stderr do mem é descartado.
      SID=$("$MEM_BIN" --json find "" --type session -k 1 2>/dev/null \
          | python3 -c "
  import json, sys
  try:
      data = json.load(sys.stdin)
      print(data[0]['id'] if data else '')
  except Exception:
      print('')
  " 2>/dev/null || echo "")
      # Passo 2: corpo do handoff curado (.body). `get` registra access — é
      # uma leitura real, comportamento esperado (igual à skill mem-resume).
      if [[ -n "$SID" ]]; then
          MEM_BODY=$("$MEM_BIN" --json get "$SID" 2>/dev/null \
              | python3 -c "
  import json, sys
  try:
      print(json.load(sys.stdin).get('body', '').strip())
  except Exception:
      print('')
  " 2>/dev/null || echo "")
      fi
  fi

  # Fallback pro arquivo (clone fresco antes do mem rebuild, ou repo sem
  # nenhum `mem session` ainda, ou qualquer falha do mem acima).
  UPDATED="(handoff missing)"
  STATE_LINE="(handoff missing)"
  if [[ -f "$HANDOFF" ]]; then
      UPDATED=$(grep -m1 '^\*\*Última atualização:\*\*' "$HANDOFF" \
          | sed 's/^\*\*Última atualização:\*\* //' || echo "(unknown)")
      STATE_LINE=$(grep -m1 '^\*\*Estado:\*\*' "$HANDOFF" \
          | sed 's/^\*\*Estado:\*\* //' || echo "(unknown)")
  fi
  ```

- [ ] Declarar `MEM_BIN` no bloco de variáveis do topo, logo após a linha
  `HANDOFF="$PROJECT_ROOT/docs/design/08-session-handoff.md"` (linha 21):

  ```bash
  MEM_BIN="$PROJECT_ROOT/.claude/bin/mem"
  ```

- [ ] Substituir o heredoc de orientação (linhas 42–60 de hoje) pra renderizar
  o `mem session` quando presente, caindo nos dois campos do arquivo quando
  não. O bloco de Mandamento 0 + fluxo (verbatim, hardcoded) **permanece**:

  **ANTES** (bloco "Estado do projeto", dentro do heredoc, linhas 49–52):
  ```bash
  Estado do projeto:
    · Última atualização handoff: $UPDATED
    · Estado: $STATE_LINE
    · Drift pendente da sessão anterior: $DRIFT_PENDING
  ```

  **DEPOIS** — montar a seção de estado ANTES do heredoc (pra escolher mem vs
  arquivo) e interpolar uma única variável `$STATE_BLOCK`:
  ```bash
  # Monta a seção de estado: corpo do mem (preferido) ou os 2 campos do arquivo.
  if [[ -n "$MEM_BODY" ]]; then
      STATE_BLOCK="Estado do projeto (último \`mem session\`):

  $MEM_BODY

    · Drift pendente da sessão anterior: $DRIFT_PENDING"
  else
      STATE_BLOCK="Estado do projeto (fallback: docs/design/08-session-handoff.md):
    · Última atualização handoff: $UPDATED
    · Estado: $STATE_LINE
    · Drift pendente da sessão anterior: $DRIFT_PENDING"
  fi
  ```

  E o heredoc passa a interpolar `$STATE_BLOCK` no lugar do bloco antigo:
  ```bash
  cat <<EOF
  🔨 feature-forge — orientação de sessão

  Você é o ORQUESTRADOR-MANTENEDOR. Nunca Write/Edit/NotebookEdit/Bash-mutação
  direto — toda mudança é despachada via Agent tool (gsd-executor / gsd-code-
  reviewer / gsd-code-fixer).

  $STATE_BLOCK

  Antes de qualquer trabalho:
    1. Brainstorm com usuário → writing-plans
    2. Dispatch gsd-executor (impl) → gsd-code-reviewer (review) → gsd-code-fixer (fixes)
    3. Verification → doc-sync → commit

  Regras: CLAUDE.md · Mandamento 0: .claude/rules/orchestrator-persona.md
  EOF

  exit 0
  ```

  > O bloco "Você é o ORQUESTRADOR-MANTENEDOR…" + "Antes de qualquer
  > trabalho…" + "Regras: …" permanece **hardcoded e verbatim** — é o
  > Mandamento 0 + fluxo, não vem do mem (invariante do Global Constraints).

### Verificação sintética (4 caminhos do gate de aceite do spec)

Rodar do root do repo. Não há stdin relevante (`</dev/null`).

- [ ] **(a) mem populado → injeta session.** Com o acervo atual (há 1 `mem
  session`):
  ```bash
  bash .claude/hooks/session-start-orientation.sh </dev/null
  ```
  **Esperado:** stdout contém `Estado do projeto (último \`mem session\`):` e o
  corpo da última sessão (ex.: `Estado feature-forge v1.6.1` ou o handoff mais
  recente que existir no momento da execução). Exit 0.

- [ ] **(b) mem vazio → grep do arquivo.** Simular acervo sem session
  apontando `MEM_BIN` pra um stub que retorna `[]`:
  ```bash
  TMP=$(mktemp); printf '#!/usr/bin/env bash\necho "[]"\nexit 0\n' > "$TMP"; chmod +x "$TMP"
  # Editar temporariamente NÃO é necessário: basta provar o fallback rodando o
  # bloco com um find que retorna []. Validação direta do branch:
  SID=$(echo "[]" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')")
  test -z "$SID" && echo "OK: [] → SID vazio → fallback"
  rm -f "$TMP"
  ```
  **Esperado:** `OK: [] → SID vazio → fallback`. (O fallback grep dos 2 campos
  é o mesmo bloco preservado de hoje — já coberto pelo caminho (c).)

- [ ] **(c) binário ausente → exit 0 + fallback.** Renomear/ocultar o mem não é
  necessário — provar via um `PROJECT_ROOT` sem `.claude/bin/mem`:
  ```bash
  TMPROOT=$(mktemp -d)
  mkdir -p "$TMPROOT/docs/design"
  printf '**Última atualização:** 2099-01-01 (probe)\n**Estado:** probe-state\n' \
      > "$TMPROOT/docs/design/08-session-handoff.md"
  ( cd "$TMPROOT" && git init -q . && bash "$OLDPWD/.claude/hooks/session-start-orientation.sh" </dev/null ); echo "exit=$?"
  rm -rf "$TMPROOT"
  ```
  **Esperado:** stdout contém `fallback: docs/design/08-session-handoff.md`,
  `Última atualização handoff: 2099-01-01 (probe)`, `Estado: probe-state`; e
  `exit=0` (mem ausente não trava o hook).

- [ ] **(d) Mandamento 0 sempre presente.** Em qualquer caminho:
  ```bash
  bash .claude/hooks/session-start-orientation.sh </dev/null | grep -q "ORQUESTRADOR-MANTENEDOR" && echo "OK: Mandamento 0 presente"
  ```
  **Esperado:** `OK: Mandamento 0 presente`.

### Deliverable verificável

`session-start-orientation.sh` injeta o corpo do último `mem session` quando o
acervo tem sessão; cai pro grep dos 2 campos do arquivo quando o mem retorna
`[]`/falha/está ausente; mantém o bloco hardcoded de Mandamento 0 e `exit 0`
em todos os 4 caminhos (a)–(d) acima.

---

## Task 2 — doc-drift hook re-route (P1)

O aviso de drift para de mandar editar `08-session-handoff.md`; passa a apontar
"rode `mem session` no fim da sessão". CHANGELOG/README seguem no aviso (são
per-commit).

### Files

- **Modify:** `.claude/hooks/post-edit-doc-drift.sh`

### Steps

- [ ] Substituir o heredoc de aviso (linhas 104–115 de hoje):

  **ANTES** (linhas 104–115):
  ```bash
  cat <<EOF >&2

  📝 doc-drift: $REL_PATH editado.

  Doc-sync pendente (mesmo commit):
    · CHANGELOG.md (Unreleased)
    · docs/design/08-session-handoff.md (Última atualização + Conhecidos limites se mudou)
    · README.md (se stats mudaram)

  Matriz completa: .claude/rules/doc-sync.md

  EOF
  ```

  **DEPOIS:**
  ```bash
  cat <<EOF >&2

  📝 doc-drift: $REL_PATH editado.

  Doc-sync per-commit (mesmo commit):
    · CHANGELOG.md (Unreleased)
    · README.md (se stats mudaram)

  Fim de sessão (não per-commit): rode \`.claude/bin/mem session\` pra
  registrar o handoff curado (estado + próximos passos; git_meta automático).
  O docs/design/08-session-handoff.md NÃO é mais editado a cada sessão —
  congelou como snapshot histórico + fallback de bootstrap.

  Matriz completa: .claude/rules/doc-sync.md

  EOF
  ```

  > O `\`` escapa o crase dentro do heredoc não-quotado (`<<EOF`, não
  > `<<'EOF'`) pra manter o literal `mem session` sem expansão.

### Verificação sintética

- [ ] Invocar o hook com um JSON sintético apontando pra um arquivo "vivo" e
  inspecionar o stderr (o hook escreve o aviso em `>&2`). Precisa rodar do root
  do repo (o hook resolve `PROJECT_ROOT` via git):
  ```bash
  echo '{"tool_input":{"file_path":"'"$PWD"'/engine/cli.py"}}' \
      | bash .claude/hooks/post-edit-doc-drift.sh 2>&1 1>/dev/null
  ```
  **Esperado (stderr):** contém `rode \`.claude/bin/mem session\``, contém
  `CHANGELOG.md (Unreleased)` e `README.md (se stats mudaram)`, e **NÃO**
  contém `docs/design/08-session-handoff.md (Última atualização` como destino
  de sync per-commit (a única menção ao arquivo é a frase de congelamento).
  Exit 0.

  > O hook só avisa 1×/arquivo/sessão (state em `drift-warned.json`). Pra
  > re-testar limpo: `rm -f .claude/state/drift-warned.json` antes da invocação.
  > Limpar depois também: `rm -f .claude/state/drift-warned.json
  > .claude/state/drift-pending.json` (resetam por SessionStart de qualquer forma).

### Deliverable verificável

O aviso do `post-edit-doc-drift.sh` lista `CHANGELOG.md` + `README.md` como
per-commit e aponta `mem session` como o trilho de fim-de-sessão; o arquivo
`08-session-handoff.md` deixa de figurar como destino de sync per-commit.

---

## Task 3 — pre-commit gate re-route (P1)

Tira o `08-session-handoff.md` do regex `TOUCHED_DOCS` do **SOFT WARNING** de
doc-sync (fica `CHANGELOG`/`README`) e atualiza o texto do aviso. O **HARD
BLOCK** do Mandamento #1 (`01-decisions.md`) NÃO é tocado.

### Files

- **Modify:** `.claude/hooks/pre-commit-feature-forge.sh`

### Steps

- [ ] No bloco `─── SOFT WARNING: doc-sync ausente ───` (linhas 42–60 de hoje),
  remover `08-session-handoff.md` do regex e ajustar o texto. **NÃO tocar** no
  bloco `─── HARD BLOCK: decisions sem ceremony ───` (linhas 19–40), nem na
  limpeza de `drift-pending.json` (linha 63), nem no `exit 0` final.

  **ANTES** (linhas 44–58):
  ```bash
  TOUCHED_CODE=$(echo "$CHANGED" | grep -E '^(engine|validators|hooks|templates|cards|presets|docs/schemas)/' || true)
  if [[ -n "$TOUCHED_CODE" ]]; then
      TOUCHED_DOCS=$(echo "$CHANGED" | grep -E '^(CHANGELOG\.md|docs/design/08-session-handoff\.md|README\.md)$' || true)
      if [[ -z "$TOUCHED_DOCS" ]]; then
          cat <<EOF >&2

  ⚠️  doc-sync: commit toca código vivo mas não CHANGELOG/handoff/README.

      Arquivos vivos alterados:
  $(echo "$TOUCHED_CODE" | sed 's/^/      · /')

      Lembre-se de atualizar doc-sync ou justifique no commit body.
      (Sem bloqueio — só aviso.)

  EOF
      fi
  fi
  ```

  **DEPOIS:**
  ```bash
  TOUCHED_CODE=$(echo "$CHANGED" | grep -E '^(engine|validators|hooks|templates|cards|presets|docs/schemas)/' || true)
  if [[ -n "$TOUCHED_CODE" ]]; then
      TOUCHED_DOCS=$(echo "$CHANGED" | grep -E '^(CHANGELOG\.md|README\.md)$' || true)
      if [[ -z "$TOUCHED_DOCS" ]]; then
          cat <<EOF >&2

  ⚠️  doc-sync: commit toca código vivo mas não CHANGELOG/README.

      Arquivos vivos alterados:
  $(echo "$TOUCHED_CODE" | sed 's/^/      · /')

      Lembre-se de atualizar doc-sync (CHANGELOG/README) ou justifique no
      commit body. O handoff de sessão não é per-commit: rode
      \`.claude/bin/mem session\` no fim da sessão. (Sem bloqueio — só aviso.)

  EOF
      fi
  fi
  ```

- [ ] Atualizar o comentário-cabeçalho do arquivo (linha 6) que descreve o SOFT
  WARNING, pra refletir que o handoff saiu do gate:

  **ANTES** (linha 6):
  ```bash
  #   (2) SOFT WARNING: code "vivo" staged sem CHANGELOG/handoff/README staged.
  ```
  **DEPOIS:**
  ```bash
  #   (2) SOFT WARNING: code "vivo" staged sem CHANGELOG/README staged.
  ```

### Verificação sintética

O hook lê o staging via `git diff --cached`. Testar num clone temporário pra
não sujar o staging do repo de trabalho:

- [ ] **Caso 1 — código vivo + CHANGELOG staged → sem warning:**
  ```bash
  T=$(mktemp -d); cp .claude/hooks/pre-commit-feature-forge.sh "$T/hook.sh"
  ( cd "$T" && git init -q . && mkdir -p engine && echo x > engine/probe.py \
      && echo y > CHANGELOG.md && git add engine/probe.py CHANGELOG.md \
      && bash hook.sh 2>&1; echo "exit=$?" )
  rm -rf "$T"
  ```
  **Esperado:** sem linha `⚠️  doc-sync`, `exit=0`.

- [ ] **Caso 2 — código vivo sem nenhum doc → warning sem mencionar handoff:**
  ```bash
  T=$(mktemp -d); cp .claude/hooks/pre-commit-feature-forge.sh "$T/hook.sh"
  ( cd "$T" && git init -q . && mkdir -p engine && echo x > engine/probe.py \
      && git add engine/probe.py && bash hook.sh 2>&1; echo "exit=$?" )
  rm -rf "$T"
  ```
  **Esperado:** stderr contém `⚠️  doc-sync: commit toca código vivo mas não
  CHANGELOG/README.`, contém `mem session`, **NÃO** contém `handoff` como
  destino de sync (só a frase "O handoff de sessão não é per-commit"); `exit=0`
  (soft warning não bloqueia).

- [ ] **Caso 3 — HARD BLOCK intacto (regressão-guard do Mandamento #1):**
  ```bash
  T=$(mktemp -d); cp .claude/hooks/pre-commit-feature-forge.sh "$T/hook.sh"
  ( cd "$T" && git init -q . && mkdir -p docs/design \
      && echo "# probe" > docs/design/01-decisions.md \
      && echo "## Unreleased" > CHANGELOG.md \
      && git add docs/design/01-decisions.md CHANGELOG.md \
      && bash hook.sh 2>&1; echo "exit=$?" )
  rm -rf "$T"
  ```
  **Esperado:** stderr contém `🛑 BLOCK: docs/design/01-decisions.md alterado
  sem cerimônia.`, `exit=1` (o hard-block continua bloqueando — esta task NÃO o
  tocou).

### Deliverable verificável

O SOFT WARNING do `pre-commit-feature-forge.sh` exige só `CHANGELOG`/`README`
(handoff fora do gate per-commit) e aponta `mem session` como fim-de-sessão; o
HARD BLOCK do Mandamento #1 segue bloqueando `01-decisions.md` sem cerimônia
(exit 1).

---

## Task 4 — docs re-route + congelar o arquivo (P1)

Refletir o novo modelo em `CLAUDE.md` (§Mandamento 6), `.claude/rules/doc-sync.md`
(ponteiro), nas duas notas mem de doc-sync (re-classificadas via add+supersede),
e congelar `08-session-handoff.md` com nota de arquivo-morto + última atualização
viva registrando o congelamento. NÃO tocar `01-decisions.md`.

### Files

- **Modify:** `CLAUDE.md` (§6 — load-bearing; só a edição estritamente necessária)
- **Modify:** `.claude/rules/doc-sync.md` (ponteiro — load-bearing; idem)
- **Modify:** `docs/design/08-session-handoff.md` (congelamento + última atualização viva)
- **Operação mem (não é Modify de arquivo):** `mem add` + `mem supersede` nas
  duas notas de doc-sync que referenciam o handoff (re-classificação aditiva no
  JSONL committed `.claude/memory/<autor>.jsonl`).

> **Nota de escopo (Mandamento #4):** `CLAUDE.md` e `.claude/rules/**` estão na
> whitelist load-bearing. As edições abaixo são só o re-route do handoff — não
> é janela pra re-enxugar o resto.

### Steps

- [ ] **`CLAUDE.md` §6 (linhas 98–106 de hoje)** — refletir per-commit =
  CHANGELOG/README; handoff = `mem session` no fim de sessão.

  **ANTES** (linhas 98–106):
  ```markdown
  ### 6. Doc-sync na mesma mudança

  Mexeu em `engine/`, `validators/`, `hooks/`, `templates/`, `cards/`,
  `presets/`, `docs/schemas/`, `docs/guides/`, `docs/diagrams/` → atualizou
  no MESMO commit: `CHANGELOG.md` (Unreleased) + `docs/design/08-session-
  handoff.md` (Última atualização + Conhecidos limites se aplicável) +
  `README.md` (se stats mudaram) + guides/diagrams (se comportamento mudou).

  Matriz código→docs: `.claude/bin/mem find "matriz código docs sincronizar ao tocar engine"`.
  ```

  **DEPOIS:**
  ```markdown
  ### 6. Doc-sync na mesma mudança

  Mexeu em `engine/`, `validators/`, `hooks/`, `templates/`, `cards/`,
  `presets/`, `docs/schemas/`, `docs/guides/`, `docs/diagrams/` → atualizou
  no MESMO commit: `CHANGELOG.md` (Unreleased) + `README.md` (se stats
  mudaram) + guides/diagrams (se comportamento mudou).

  O **estado de sessão** não é per-commit: no fim de trabalho significativo,
  rode `.claude/bin/mem session` (handoff curado, committed, com git_meta
  automático). O `docs/design/08-session-handoff.md` congelou — snapshot
  histórico + fallback de bootstrap do SessionStart, não mais editado a cada
  sessão.

  Matriz código→docs: `.claude/bin/mem find "matriz código docs sincronizar ao tocar engine"`.
  ```

- [ ] **`.claude/rules/doc-sync.md` §Invariante always-on (linhas 8–15 de
  hoje)** — tirar o handoff do invariante per-commit.

  **ANTES** (linhas 7–15):
  ```markdown
  ## Invariante always-on

  Mexeu em `engine/`, `validators/`, `hooks/`, `templates/`, `cards/`,
  `presets/`, `docs/schemas/`, `docs/guides/`, `docs/diagrams/` → atualize no
  MESMO commit: `CHANGELOG.md` (Unreleased) + `docs/design/08-session-
  handoff.md` (Última atualização + Conhecidos limites se aplicável) +
  `README.md` (se stats mudaram) + guides/diagrams (se comportamento
  documentado mudou). O pre-commit emite SOFT WARNING quando código vivo é
  staged sem CHANGELOG/handoff/README.
  ```

  **DEPOIS:**
  ```markdown
  ## Invariante always-on

  Mexeu em `engine/`, `validators/`, `hooks/`, `templates/`, `cards/`,
  `presets/`, `docs/schemas/`, `docs/guides/`, `docs/diagrams/` → atualize no
  MESMO commit: `CHANGELOG.md` (Unreleased) + `README.md` (se stats mudaram)
  + guides/diagrams (se comportamento documentado mudou). O pre-commit emite
  SOFT WARNING quando código vivo é staged sem CHANGELOG/README.

  O **estado de sessão** saiu do gate per-commit: rode `.claude/bin/mem
  session` no fim de sessão (handoff curado, committed). O
  `docs/design/08-session-handoff.md` congelou — snapshot histórico +
  fallback de bootstrap do SessionStart, não mais editado a cada sessão.
  ```

- [ ] **Re-classificar a nota mem da MATRIZ** (`01KVZVXC0D72Y0GHVHCWVD0MCB` —
  "Matriz código→docs — o que sincronizar ao tocar cada área"). A matriz hoje
  lista `08-session-handoff.md` como destino obrigatório em quase toda linha;
  com o re-route, o handoff sai do per-commit. Criar a versão corrigida e
  supersedir a antiga (preserva histórico no JSONL append-only):

  Interface confirmada no `mem add --help`: `--type` · `-i/--importance` ·
  `-t/--title` · `--tags` · **o corpo é POSICIONAL** (último argumento, NÃO um
  flag `--body`).

  ```bash
  NEW_ID=$(.claude/bin/mem --json add \
      --type reference \
      --title "Matriz código→docs — o que sincronizar ao tocar cada área" \
      --tags "doc-sync,mandamento-6,matrix" \
      -i 3 \
      "Mandamento #6: ao tocar código vivo, atualize docs no MESMO commit. Per-commit = CHANGELOG + README (se stats mudaram) + guides/diagrams (se comportamento documentado mudou). O estado de sessão NÃO é per-commit: rode \`.claude/bin/mem session\` no fim de sessão (handoff curado, committed, git_meta automático); o docs/design/08-session-handoff.md congelou (snapshot histórico + fallback de bootstrap do SessionStart). Matriz canônica (mudou → atualize obrigatoriamente | considere também):

  - engine/<command>.py (handler) → CHANGELOG | README §Stats, 06-command-surface.md
  - engine/foundation/* (cli, utils, ui, persona) → CHANGELOG
  - validators/<x>.py → CHANGELOG | 07-discipline.md §2 se policy mudou
  - hooks/*.sh ou .claude/hooks/*.sh → CHANGELOG | 05-filesystem-layout.md
  - Novo card em cards/ → CHANGELOG, README §Stats | 02-phases.md
  - Novo template em templates/ → CHANGELOG, README §Stats | 02-phases.md
  - Schema em docs/schemas/ → CHANGELOG, README §Schemas | templates que usam o schema
  - presets/*.yaml → CHANGELOG, README §Preset | 03-influences.md
  - 01-decisions.md → CHANGELOG '### Changed (load-bearing)' 'Revisita decisão N' | sempre append, nunca delete
  - 04-pending.md → risca gap fechado, adiciona novo | handoff §Conhecidos limites era o destino antigo; agora o gap aberto entra no corpo do próximo \`mem session\`
  - agents/*.md → CHANGELOG
  - docs/ux/*.md → CHANGELOG
  - Release tag → CHANGELOG seção [vX.Y.Z], README versão
  - Novo comando forge ou mudança de comportamento → CHANGELOG | docs/guides/daily-workflow.md, docs/diagrams/command-decision-tree.mermaid
  - Mudança em contagem de doctor/verify → CHANGELOG | docs/guides/ (toda menção a 'N categorias'/'N validators'), diagrams
  - Mudança na estrutura de memória (L1/L2) → CHANGELOG | getting-started, bootstrap-flow/files-versioned diagrams
  - Mudança em Apply Mode ou fases → CHANGELOG | feature-lifecycle guide+diagram
  - docs/guides/*.md ou docs/diagrams/*.mermaid editados → CHANGELOG" \
      2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
  .claude/bin/mem supersede "$NEW_ID" 01KVZVXC0D72Y0GHVHCWVD0MCB
  echo "matriz: NEW_ID=$NEW_ID supersedes 01KVZVXC0D72Y0GHVHCWVD0MCB"
  ```

  > Interface verificada no scout (`mem add --help`): flags `--type` ·
  > `-i/--importance` · `-t/--title` · `--tags` · `--source`; **o corpo é o
  > argumento POSICIONAL final** (NÃO existe flag `--body`). Por isso o corpo
  > acima é passado como string posicional logo antes do pipe.

- [ ] **Re-classificar a nota mem do CHECKLIST** (`01KVZVY422G127XXYE2NQT9V9S` —
  "Antes do commit, rode o checklist de doc-sync"). O item 2 do checklist
  (atualizar o handoff "Última atualização"/"Estado") sai; entra o trilho `mem
  session`:

  ```bash
  NEW_ID=$(.claude/bin/mem --json add \
      --type feedback \
      --title "Antes do commit, rode o checklist de doc-sync" \
      --tags "checklist,doc-sync,pre-commit" \
      -i 3 \
      "Checklist pré-commit (confirme antes de git commit):
  1. CHANGELOG.md tem entrada em [Unreleased] cobrindo a mudança?
  2. README.md Stats refletem (se stats mudaram — file count, test count, LOC, schemas)?
  3. Rule específico atualizado SE comportamento mudou (novo validator → testing.md; novo subagent_type → subagent-workflow.md)?
  4. Gap em 04-pending.md fechado/atualizado se aplicável?
  5. docs/guides/ e docs/diagrams/ atualizados se a mudança afeta comportamento documentado?
  Se algum falhar, dispatch gsd-doc-writer (ou gsd-executor focado em docs) ANTES do commit final.

  Estado de sessão NÃO é per-commit: no fim de trabalho significativo rode \`.claude/bin/mem session '<resumo: estado + próximos passos>'\` — handoff curado, committed, com git_meta automático (branch/head/commits/files). O docs/design/08-session-handoff.md congelou (snapshot histórico + fallback de bootstrap do SessionStart), não é mais editado a cada sessão.

  Como editar CHANGELOG (keep-a-changelog): sempre [Unreleased] no topo. Seções: Added, Changed, Changed (load-bearing) (revisita decisão locked), Fixed, Removed. Release move [Unreleased] → [vX.Y.Z] - YYYY-MM-DD e cria novo [Unreleased] vazio.

  Quando NÃO precisa doc-sync: typo puro em comentário; reformatação automatizada (black, ruff format); rename de variável local sem afetar API pública; edição de string literal já testada sem mudança de comportamento; update de version pin sem mudança de behavior. Tudo fora desta lista exige sync. Em dúvida: faça sync." \
      2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
  .claude/bin/mem supersede "$NEW_ID" 01KVZVY422G127XXYE2NQT9V9S
  echo "checklist: NEW_ID=$NEW_ID supersedes 01KVZVY422G127XXYE2NQT9V9S"
  ```

- [ ] **Congelar `docs/design/08-session-handoff.md`** — adicionar a nota de
  arquivo-morto no topo (logo após o blockquote da linha 4) e atualizar a
  `**Última atualização:**`/`**Estado:**` uma última vez registrando o
  congelamento. **Não** apagar o histórico abaixo (hybrid).

  **ANTES** (linhas 1–7):
  ```markdown
  # Session Handoff

  > Use este doc se você está **retomando feature-forge numa sessão nova** ou se
  > é um agente cold-start sem contexto da conversa de design original.

  **Última atualização:** 2026-06-25 (Fase 0 — dogfood do `mem`: CLAUDE.md + `.claude/rules/**` enxugados pro Tier-0 + índice mem)
  **Estado:** Fase 0 da integração mem↔forge em andamento na branch `feat/mem-integration` (não mergeada). [...]
  ```

  **DEPOIS** — inserir o bloco `> **ARQUIVO-MORTO**` entre o blockquote
  existente e a linha `**Última atualização:**`, e reescrever os dois campos:
  ```markdown
  # Session Handoff

  > Use este doc se você está **retomando feature-forge numa sessão nova** ou se
  > é um agente cold-start sem contexto da conversa de design original.

  > **ARQUIVO-MORTO (Fase 0.5 — handoff → mem).** Este arquivo deixou de ser a
  > fonte viva de estado-de-sessão. O estado vivo passou a viver em notas
  > `mem session` (committed, append-only, listáveis via
  > `.claude/bin/mem find "" --type session`); o SessionStart injeta a última.
  > Este arquivo PERMANECE como (1) snapshot histórico do projeto até a Fase 0
  > e (2) fallback de bootstrap do SessionStart pra clone fresco antes do `mem
  > rebuild`. Não é mais editado a cada sessão — para retomar o estado atual,
  > consulte o `mem` (o conteúdo abaixo é histórico congelado).

  **Última atualização:** 2026-06-25 (Fase 0.5 — handoff → mem: este arquivo CONGELOU como snapshot histórico + fallback de bootstrap; estado vivo agora em `mem session`)
  **Estado:** Arquivo congelado. O estado-de-sessão vivo migrou pro `mem` (notas `mem session` committed). Última atualização viva deste arquivo. Histórico abaixo preservado (snapshot até a Fase 0). Para o estado atual, rode `.claude/bin/mem find "" --type session -k 1` + `mem get <id>`.
  ```

  > Manter intactos o `**Última atualização anterior:**`/`**Estado:**` e todo o
  > corpo histórico abaixo da linha 8 — append-only, hybrid (não deletar).

### Verificação sintética

- [ ] **CLAUDE.md / doc-sync.md não citam mais o handoff como per-commit:**
  ```bash
  grep -n "08-session-handoff" CLAUDE.md .claude/rules/doc-sync.md
  ```
  **Esperado:** as únicas menções restantes descrevem o congelamento/fallback,
  nenhuma lista o arquivo como destino de sync per-commit.

- [ ] **Notas mem re-classificadas (antigas superseded, novas ativas):**
  ```bash
  .claude/bin/mem --json get 01KVZVXC0D72Y0GHVHCWVD0MCB | python3 -c "import json,sys; print('matriz antiga status:', json.load(sys.stdin)['status'])"
  .claude/bin/mem --json get 01KVZVY422G127XXYE2NQT9V9S | python3 -c "import json,sys; print('checklist antiga status:', json.load(sys.stdin)['status'])"
  .claude/bin/mem --json find "matriz código docs sincronizar" -k 1 | python3 -c "import json,sys; d=json.load(sys.stdin); print('matriz ativa topo:', d[0]['id'] if d else 'NENHUMA')"
  ```
  **Esperado:** ambas as antigas com `status: superseded`; o `find` da matriz
  retorna a nova nota no topo (a antiga some do `find` padrão por estar
  superseded). A nova matriz NÃO lista `08-session-handoff.md` como destino
  obrigatório.

- [ ] **Arquivo congelado (nota no topo + campos atualizados, histórico
  preservado):**
  ```bash
  head -15 docs/design/08-session-handoff.md | grep -q "ARQUIVO-MORTO" && echo "OK: nota de congelamento"
  grep -c "Última atualização anterior" docs/design/08-session-handoff.md
  ```
  **Esperado:** `OK: nota de congelamento`; a contagem de "Última atualização
  anterior" permanece a mesma de antes (histórico não deletado).

### Deliverable verificável

`CLAUDE.md` §6 e `.claude/rules/doc-sync.md` refletem per-commit =
CHANGELOG/README e handoff = `mem session` no fim de sessão; as duas notas mem
de doc-sync estão re-classificadas (antigas superseded, novas ativas sem o
handoff per-commit); `08-session-handoff.md` tem a nota de arquivo-morto no
topo + última atualização viva, com o histórico preservado. `01-decisions.md`
intacto.

---

## Task 5 — mem install-hooks + gate de coexistência (P2)

Instalar os hooks do mem e verificar que os hooks do forge continuam
registrados e funcionais (merge soma, não sobrescreve). Se sobrescrever algum
hook do forge → PARAR (3-caminhos).

### Files

- **Modify (via comando mem):** `.claude/settings.json` (escrito pelo `mem
  install-hooks --apply`, não por Edit direto)

### Steps

- [ ] **Dry-run primeiro** (inspecionar o merge antes de aplicar):
  ```bash
  .claude/bin/mem install-hooks --tool claude-code 2>&1
  ```
  **Esperado:** imprime o `settings.json` mergeado (sem escrever). Conferir que
  o JSON resultante contém AMBOS por evento compartilhado:
  - `SessionStart` → a entrada do forge (`session-start-orientation.sh`) **e** a
    do mem (`mem hook session-start`).
  - `PostToolUse` → a entrada do forge (`post-edit-doc-drift.sh`, matcher
    `Edit|Write|NotebookEdit`) **e** a do mem (`mem hook post-tool`, matcher
    `Edit|Write`).
  - `PreToolUse` → só a do forge (`pre-tool-use-load-bearing.sh`), **intocada**
    (mem não registra `PreToolUse`).
  - `Stop` e `UserPromptSubmit` → novos, só do mem.

  > Grounding (`_merged_settings` em `engine/assets/mem/mem`:1893): por evento,
  > `kept = [entradas que NÃO são hook-do-mem] + [a entrada do mem]`. As
  > entradas do forge não casam `_is_mem_hook_entry` (não terminam em
  > `mem <suffix>`), então são preservadas. `_HOOK_WIRING` cobre só
  > `Stop/UserPromptSubmit/SessionStart/PostToolUse` — `PreToolUse` fica fora.

- [ ] **Gate de coexistência (PARE se falhar).** Validar no output do dry-run
  que os 3 hooks do forge sobrevivem ANTES de aplicar:
  ```bash
  .claude/bin/mem install-hooks --tool claude-code 2>/dev/null | python3 -c "
  import json, sys
  s = json.load(sys.stdin)
  h = s.get('hooks', {})
  def has(event, needle):
      return any(needle in hk.get('command','')
                 for grp in h.get(event, []) for hk in grp.get('hooks', []))
  checks = {
      'forge SessionStart': has('SessionStart', 'session-start-orientation.sh'),
      'mem   SessionStart': has('SessionStart', 'mem hook session-start'),
      'forge PreToolUse':   has('PreToolUse', 'pre-tool-use-load-bearing.sh'),
      'forge PostToolUse':  has('PostToolUse', 'post-edit-doc-drift.sh'),
      'mem   PostToolUse':  has('PostToolUse', 'mem hook post-tool'),
      'mem   Stop':         has('Stop', 'mem hook stop'),
      'mem   UserPrompt':   has('UserPromptSubmit', 'mem hook prompt'),
  }
  for k, v in checks.items():
      print(('OK  ' if v else 'FALHA ') + k)
  forge_intact = checks['forge SessionStart'] and checks['forge PreToolUse'] and checks['forge PostToolUse']
  print('GATE:', 'PASS' if forge_intact else 'STOP — forge hook sobrescrito')
  sys.exit(0 if forge_intact else 1)
  "
  ```
  **Esperado:** todas as 7 linhas `OK`, `GATE: PASS`. **Se `GATE: STOP`** →
  PARAR e apresentar 3-caminhos ao orquestrador (A: ajustar merge manualmente
  preservando o forge / B: reverter e re-scope / C: escalar pro autor) — NÃO
  aplicar.

- [ ] **Aplicar** (só depois do gate PASS):
  ```bash
  .claude/bin/mem install-hooks --tool claude-code --apply 2>&1
  ```
  **Esperado:** `wired hooks into .../.claude/settings.json`.

### Verificação sintética (pós-apply)

- [ ] **Settings tem AMBOS nos eventos compartilhados** (mesmo predicado do
  gate, agora contra o arquivo escrito):
  ```bash
  python3 -c "
  import json
  s = json.load(open('.claude/settings.json'))
  h = s['hooks']
  def has(event, needle):
      return any(needle in hk.get('command','')
                 for grp in h.get(event, []) for hk in grp.get('hooks', []))
  assert has('SessionStart','session-start-orientation.sh'), 'forge SessionStart sumiu'
  assert has('SessionStart','mem hook session-start'), 'mem SessionStart ausente'
  assert has('PreToolUse','pre-tool-use-load-bearing.sh'), 'forge PreToolUse sumiu'
  assert has('PostToolUse','post-edit-doc-drift.sh'), 'forge PostToolUse sumiu'
  assert has('PostToolUse','mem hook post-tool'), 'mem PostToolUse ausente'
  assert has('Stop','mem hook stop'), 'mem Stop ausente'
  assert has('UserPromptSubmit','mem hook prompt'), 'mem UserPrompt ausente'
  print('OK: coexistência confirmada — forge + mem nos eventos compartilhados')
  "
  ```
  **Esperado:** `OK: coexistência confirmada — forge + mem nos eventos
  compartilhados`.

- [ ] **Hook do forge ainda dispara (invocação sintética):** o
  `session-start-orientation.sh` segue funcional após a co-instalação:
  ```bash
  bash .claude/hooks/session-start-orientation.sh </dev/null | grep -q "ORQUESTRADOR-MANTENEDOR" && echo "OK: forge SessionStart funcional pós-coexistência"
  ```
  **Esperado:** `OK: forge SessionStart funcional pós-coexistência`.

### Deliverable verificável

`.claude/settings.json` registra os hooks do forge
(`session-start-orientation`, `pre-tool-use-load-bearing`,
`post-edit-doc-drift`) E os do mem (`session-start`, `post-tool`, `stop`,
`prompt`) nos eventos compartilhados; o merge somou (não sobrescreveu); o
SessionStart do forge segue funcional. Se o gate STOP disparar, a task PARA com
3-caminhos.

---

## Task 6 — doc-sync + gate de aceite

CHANGELOG cobre o re-route; README só se stats mudaram (não mudaram — confirmar);
gate de aceite espelha a Fase 0 (não fecha por subagente); suíte verde.

### Files

- **Modify:** `CHANGELOG.md` (`## [Unreleased]` — `### Added`/`### Changed`)
- **Modify (condicional):** `README.md` (só se uma stat mudar — ver step de
  confirmação)

### Steps

- [ ] **CHANGELOG `## [Unreleased]`** — adicionar entradas cobrindo o re-route.
  Em `### Changed` (sob as entradas já presentes da Fase 0):
  ```markdown
  - Handoff de sessão re-roteado pro `mem` (Fase 0.5 — dogfood). O
    `session-start-orientation.sh` passa a injetar o corpo do último `mem
    session` (dois passos: `mem --json find "" --type session -k 1` → `mem
    --json get <id>` → `.body`), com fallback gracioso pro grep dos dois campos
    do `08-session-handoff.md` quando o mem está vazio/ausente/falhando — o
    bloco hardcoded de Mandamento 0 + fluxo e o contrato exit-0 permanecem
    intactos em todos os caminhos. O `post-edit-doc-drift.sh` e o SOFT WARNING
    do `pre-commit-feature-forge.sh` deixam de exigir o handoff-arquivo no gate
    per-commit (fica `CHANGELOG`/`README`) e passam a apontar `mem session`
    como o trilho de fim-de-sessão; o HARD BLOCK do Mandamento #1
    (`01-decisions.md`) não foi tocado. `CLAUDE.md` §6 e
    `.claude/rules/doc-sync.md` refletem o novo modelo (per-commit =
    CHANGELOG/README; handoff = `mem session`); as duas notas mem de doc-sync
    (matriz código→docs + checklist pré-commit) foram re-classificadas via
    `mem add` + `mem supersede` (antigas preservadas como superseded). O
    `docs/design/08-session-handoff.md` congelou — snapshot histórico +
    fallback de bootstrap do SessionStart, não mais editado a cada sessão
    (estado-final hybrid: não deletado). Nenhuma mudança de código Python.
  - Hooks do mem instalados no `.claude/settings.json` via `mem install-hooks
    --apply` (P2): `Stop`/`UserPromptSubmit` (eventos novos pro repo) +
    `SessionStart`/`PostToolUse` somados aos do forge. Merge aditivo verificado
    (gate de coexistência): os hooks do forge — `session-start-orientation`,
    `pre-tool-use-load-bearing`, `post-edit-doc-drift` — continuam registrados e
    funcionais; `PreToolUse` fica só do forge (mem não o registra). Continuidade
    via `checkpoint` (singleton mantido pelos hooks do mem) + consolidação via
    skill `mem-consolidate` passam a ser a prática canônica.
  ```

- [ ] **Confirmar se alguma stat do README mudou.** Este re-route NÃO adiciona
  hooks do forge (os hooks do mem são separados, instalados via settings, não
  contados como hooks do forge no `README §Stats`), NÃO muda validators/cards/
  templates/comandos, NÃO muda LOC Python (zero código Python), NÃO muda test
  count. Verificar:
  ```bash
  grep -n "4 hooks\|9 hooks\|PostToolUse lembra doc-sync\|hard-blocks" README.md
  ```
  - Se a linha de prosa (README:91) descreve "PostToolUse lembra doc-sync"
    apontando o handoff como destino → atualizar SÓ essa frase pra refletir que
    o aviso aponta `mem session` (sem mudar nenhum NÚMERO). Essa é a única
    edição candidata de README e é prosa, não stat.
  - Se nenhuma stat numérica mudou (esperado), NÃO tocar `README §Stats`. O
    SOFT WARNING não vai disparar por README ausente porque CHANGELOG estará
    staged.

- [ ] **Suíte verde (gate de não-regressão de Python):**
  ```bash
  .venv/bin/pytest -m "not integration and not e2e" -q | tail -1
  ```
  **Esperado:** `2020 passed` (mesmo count da Fase 0 — nenhuma mudança de
  Python neste plano; qualquer delta de count é regressão a investigar).

### Gate de aceite (espelha a Fase 0 — NÃO fecha por subagente)

Anotar no report pro orquestrador conduzir com o autor:

- [ ] **Sessão de manutenção fresca** (SessionStart limpo, sessão Claude Code
  nova no repo): confirma que a orientação vem do último `mem session` +
  fallback funcional + Mandamento 0 intacto.
- [ ] **Coexistência de settings:** após `mem install-hooks --apply`, os hooks
  do forge (orientação/drift/load-bearing/pre-commit) continuam registrados e
  funcionais (já provado sinteticamente na T5; o gate de aceite confirma em
  sessão real).

### Deliverable verificável

CHANGELOG `## [Unreleased]` cobre o re-route (Added/Changed); README sem
mudança de stat numérica (confirmado); `.venv/bin/pytest -m "not integration
and not e2e"` verde em `2020 passed`; gate de aceite anotado pro orquestrador
(não fechado por subagente).

---

## Self-review

- **Spec coverage:** cada seção do spec tem task.
  - §SessionStart re-route + §3 cadências (fim-de-sessão) → **T1**.
  - §mudanças de hook (`post-edit-doc-drift` l110) → **T2**.
  - §mudanças de hook (`pre-commit-feature-forge` l46, SOFT WARNING, hard-block
    intacto) → **T3**.
  - §mudanças de docs (`CLAUDE.md` §6 + `.claude/rules/doc-sync.md` + nota mem
    de doc-sync) + §papel novo do arquivo (congelamento hybrid) → **T4**.
  - §adoção dos hooks do mem (P2) + §coexistência (gate merge-soma) → **T5**.
  - §Validação/gate de aceite + doc-sync (CHANGELOG/README/suíte) → **T6**.
  - Anti-goals honrados: sem checkpoint-por-commit custom (T1 usa só
    `find`/`get` nativos); sem deletar o arquivo (T4 congela hybrid); não toca
    `01-decisions.md` (T3 preserva o hard-block; T4 não o lista); não é a Fase 1
    (escopo é só o repo forge); Mandamento 0 hardcoded permanece (T1). Sem gaps.
- **Placeholder scan:** zero TBD/TODO/FIXME/"similar à Task N". Cada step de
  hook traz o bloco bash ANTES→DEPOIS completo; cada operação mem traz o comando
  exato (interface do `mem add`/`supersede`/`install-hooks` confirmada no scout
  contra o binário real — corpo posicional, `supersede NEW_ID OLD_ID`,
  `_merged_settings` soma); cada verificação traz comando + output esperado.
  Nenhuma lacuna pendente.
- **Type/name consistency:** `session-start-orientation.sh` /
  `post-edit-doc-drift.sh` / `pre-commit-feature-forge.sh` /
  `pre-tool-use-load-bearing.sh` grafados consistentemente; variáveis novas do
  hook (`MEM_BIN`, `MEM_BODY`, `SID`, `STATE_BLOCK`) consistentes entre os
  steps de T1; `mem --json find/get/add/supersede/install-hooks` com o `--json`
  sempre global; IDs das notas (`01KVZVXC0D72Y0GHVHCWVD0MCB` matriz,
  `01KVZVY422G127XXYE2NQT9V9S` checklist) grafados igual em T4 e nas
  verificações; P1/P2 conforme o §Fasamento do spec.
- **Voz:** mentor calmo, PT neutro, sem emoji decorativo (os ⚠️/📝/🛑/🔨 nos
  blocos de hook são literais do código existente preservados, não decoração do
  plano).
