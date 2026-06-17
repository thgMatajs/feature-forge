# Relatório de Auditoria LLM-First / Agentic-Compatibility — feature-forge 1.4.0 (PR #17)

> **Data:** 2026-06-17
> **Escopo:** compatibilidade ponta-a-ponta do `forge` como ferramenta dirigida 100% por hosts agênticos (Claude Code, opencode + LLMs). Foco: o que foi entregue no PR #17 (`feat/v1.3-pilot-ready`, 75 commits, host-aware execution + 4 adapters + sub-namespace `.claude/forge/` + install.sh + forge upgrade).
> **Método:** 6 auditorias paralelas (token-economy, command-surface, consumer-footprint, agents/templates, robustez/concorrência, completude-do-protocolo) + verificação manual trust-but-verify das alegações críticas no código.
> **Relação com `auditoria-pre-piloto.md`:** este relatório complementa e em pontos **corrige** a auditoria anterior (ver §1).
> **Voz:** mentor calmo. Severidade é determinística, não improvisada.

---

## 0. Veredito

**O `forge` NÃO está agentic-ready para piloto** — e o motivo não é nenhum dos quatro P0 que a auditoria anterior nomeou (MCP server, `--non-interactive`, opencode 2nd-class, implement-stub).

O bloqueador real é único e quase invisível: **nenhum artefato ensina o host a DIRIGIR o intent loop.** Toda a máquina de host-aware execution (4 adapters, marker `<FORGE_INTENT/>`, exit 2, protocolo de re-invocação) é a metade-engine de um protocolo de duas partes cuja outra metade — o driver no host — nunca é entregue ao consumidor. Resultado: num projeto consumidor recém-instalado, `forge plan` (e todo comando interativo) **morre no primeiro prompt**.

Além do bloqueador central, a auditoria confirmou **em código** três defeitos críticos adicionais e um conjunto largo de fricções de token/UX que sangram o orçamento do agente.

### Quadro-resumo de severidade

| # | Finding | Severidade | Estado |
|---|---|---|---|
| DRIVER-001 | Host não sabe dirigir o intent loop (sem skill/CLAUDE.md/plugin) | **CRÍTICO** | Confirmado (absence-of) |
| DEAD-VERIFY | Gate pre-commit `forge verify` é no-op silencioso no consumidor | **CRÍTICO** | Confirmado em código |
| EXIT-2-COLLISION | Exit 2 significa "pausado" E "erro fatal" simultaneamente | **CRÍTICO** | Confirmado em código |
| CONC-1 | Processos forge paralelos corrompem state files (sem flock) | **CRÍTICO** | Confirmado (teste do próprio projeto) |
| TOKEN-BLIND | Camada de output é host-blind; non-TTV não economiza token | **ALTO** | Confirmado |
| NO-MANIFEST | Sem manifesto de comandos/args machine-readable | **ALTO** | Confirmado |
| ENV-1 | CLAUDECODE/OPENCODE_ herdado → adapter errado → hang | **ALTO** | Confirmado |
| REPLAY-1/2 | init re-executa pipeline; reconfigure faz `.bak` antes do confirm | **ALTO** | Confirmado |
| NO-ONBOARDING | forge init não instala nada que ensine o LLM que forge existe | **ALTO** | Confirmado |
| (vários) | latência de hooks, exit-ladder, dedup de templates, etc. | MÉDIO/BAIXO | Confirmado |

---

## 1. Método e correções à auditoria anterior

A `auditoria-pre-piloto.md` (939 linhas) é exaustiva e útil, mas foi escrita contra um estado **mais antigo** da branch e contém imprecisões que este relatório corrige:

1. **`engine/host/adapters/opencode_fallback.py` (§4.6 da auditoria anterior) não existe mais.** O código atual tem apenas `claude_code.py`, `intent_file.py`, `tty.py`. opencode é roteado pra `IntentFileAdapter` via `HostName.OPENCODE` no registry.
2. **`IntentFileAdapter.wait_for_intent()` "loop infinito / blocks forever" (§3.4 e §3.8) é falso.** Não existe método de polling. O adapter escreve o pending e imediatamente `raise PausedForInputError` (`intent_file.py:301`) → exit 2. Ele NÃO espera. Isso torna o driver ausente *ainda mais* load-bearing: ninguém está bloqueado esperando — o engine simplesmente sai e depende do host re-invocar.
3. **Ratings "B+/B-" dos adapters (§4.3/§4.6) são enganosos.** Sugerem que os canais *funcionam* e só precisam de polish. Na prática os canais são inertes sem o driver do host (DRIVER-001). O problema não é qualidade do adapter — é a ausência da contraparte.
4. **A priorização P0 da auditoria anterior está invertida.** MCP server e `--non-interactive` são reais mas secundários. O P0 verdadeiro (driver do host) não aparece em nenhum dos 22 gaps nem nas duas listas de críticos da auditoria anterior.

Onde as duas auditorias concordam (race conditions, env detect, MCP stubs, Ctrl+C mid-intent), este relatório aprofunda com evidência de código e cenários compostos.

---

## 2. O bloqueador central (CRÍTICO) — o host não sabe dirigir o intent loop

### 2.1 O que o protocolo espera do host

Sob Claude Code, ao encontrar uma pergunta, o `ClaudeCodeAdapter`:
1. emite uma linha única em stdout: `<FORGE_INTENT kind="..." intent-id="..." question="..." options='...' .../>` (`claude_code.py:283-354`);
2. levanta `PausedForInputError` → o engine sai com **exit 2** (`cli.py:330-337`).

O contrato (literal em `cli.py:331-335`) diz: *"The caller (Claude Code host or the in-process TtyAdapter) is expected to read that file, write a response, and re-invoke us with the same argv."* Ou seja, o host **deve**: ler o marker, despachar sua UI nativa de pergunta (`AskUserQuestion`), escrever `.claude/forge/state/forge-response.json` no schema exato com o `intent-id` casado, e re-invocar `forge` com **argv idêntico** (o `intent-id` é hash de kind+question+options+command+argv; argv diferente → `IntentMismatchError` → exit 1).

### 2.2 Prova de ausência (DRIVER-001)

Nada no que `forge init` instala — nem em lugar algum que o contexto do host carregue — ensina esse loop:

- `find . -iname "SKILL.md"` (excl. worktrees/.git) → **vazio**. Nenhuma skill é versionada ou instalada.
- `find` por `output-style`, `plugin.json`, `.claude-plugin`, `marketplace*` → **todos vazios**. Sem plugin de CC, sem output-style.
- `AskUserQuestion` aparece SÓ em: `.claude/rules/*` (maintainer-only deste repo), `agents/*.md` (prompts de planejamento, **não** instalados no consumidor), specs/plans, o source do adapter, e testes. **Zero** ocorrências em qualquer coisa que `forge init` instale.
- `engine/init.py::_register_forge_cc_hooks` (`init.py:763-820`) registra no `.claude/settings.json` do consumidor apenas 4 hooks: `session-start-drift-check`, `post-edit-codebase-graph`, `post-write-feature-artifact`, `post-subagent-validate`. **Nenhum dirige o intent loop.**
- `engine/init.py:208-219` (`for sub in ("skills", "agents")`) é *detecção* brownfield ("`.claude/skills/` exists and is non-empty"), **não** instalação. forge não escreve skill nem agent no consumidor.
- O protocolo está descrito **apenas** em comentários de código: `claude_code.py:8-38` e `bin/forge:38-44`. O host do consumidor nunca lê o source do forge.

### 2.3 A simulação dia-1 do piloto ("E se...")

> **E se** um dev instala forge via `scripts/install.sh`, abre o repo dele no Claude Code e diz "rode forge plan auth"?
> O Claude Code despacha `Bash("forge plan auth")`. O engine chega no primeiro `question.ask()`, o `ClaudeCodeAdapter` imprime `<FORGE_INTENT .../>` em stdout e sai com exit 2. O Claude Code recebe: um resultado de tool com uma linha XML estranha em stdout e exit 2. **Nada disse a ele que isso é um protocolo.** No melhor caso o modelo trata exit 2 como falha de comando e mostra o marker cru ao usuário; no pior, alucina um re-run com args diferentes (→ intent-id mismatch → exit 1) ou escreve a resposta em `.claude/state/` (legado, conforme docstrings velhas) em vez de `.claude/forge/state/` → nunca consumida → loop. **`forge plan` está morto na chegada.**

**Impacto:** os ~108 callsites de `ask*()` viram becos sem saída. `init`, `plan`, `implement`, `verify`, `reconfigure`, `evolve`, `undo`, `memory`, `qa` — o produto inteiro — são não-funcionais num host consumidor não-preparado. É a diferença entre "o protocolo está implementado" e "o produto funciona".

### 2.4 opencode é igual ou pior (DRIVER-003)

`docs/research/opencode-tool-api.md` (Veredito B) decide que opencode usa `IntentFileAdapter`. Mas a pesquisa estabelece corretamente que **nada faz o opencode OLHAR pra `forge-pending.json`** — subprocessos não têm canal pra "pausar o engine e perguntar" na arquitetura de bash-tool do opencode, e o ACP não roteia `question.asked`. Pior que CC: o file adapter nem emite marker em stdout (`intent_file.py:166-174` retorna None no canal de progresso). opencode precisa do MESMO artefato-ensino que CC, entregue via `AGENTS.md` ou plugin opencode. O "aceitável" do Veredito B subestima isso.

### 2.5 Recomendação (em ordem de fit)

1. **Ship uma `feature-forge` SKILL.md instalada por `forge init` em `.claude/skills/feature-forge/SKILL.md`** (e versionada no repo pro próprio maintainer). Ela ensina, verbatim: como parsear o marker, chamar `AskUserQuestion`, escrever `forge-response.json` no schema com o mesmo `intent-id`, e re-invocar com argv idêntico — até exit 0/1/130. **Menor fricção, maior fit, respeita Decisão 22** (skills são comportamento, não runtime dep).
2. **`AGENTS.md` pro opencode** (+ avaliar plugin opencode / ACP-HTTP adapter via `POST /question/:id/reply`).
3. **Injeção brownfield-safe num bloco do `CLAUDE.md` do consumidor** (append-only, como o merge de settings.json já faz) — fallback se não quiser skill.
4. **Estratégico: reconsiderar o non-goal "MCP server".** MCP tem *elicitation* nativa: o server pede input estruturado mid-call e hosts MCP-aware (Claude Code, Cursor, Windsurf) renderizam nativamente — **sem artefato-ensino**. Isso dissolve o protocolo de marker/arquivo E o requisito de driver-skill de uma vez. O engine já tem o chokepoint limpo (`question.ask*()` + registry de adapters), então um `McpAdapter` que mapeia `ask*()`→elicitation é alinhado à arquitetura e respeita Decisão 22 (MCP é transporte, não import de skill). Sequência sugerida: **skill agora (dias) → MCP depois (estratégico).**

---

## 3. Bugs CRÍTICOS confirmados em código

### 3.1 DEAD-VERIFY — gate pre-commit `forge verify` é no-op silencioso em todo consumidor

**Evidência:**
- `_install_hooks` copia `pre-commit-feature-forge.sh` pra `.claude/forge/hooks/` (`forge_hooks_dir`, `paths.py:288`).
- O wrapper gerado em `.git/hooks/pre-commit` exec `.claude/forge/hooks/git-pre-commit`.
- Mas o `git-pre-commit` copiado tem **hardcoded** `HOOK="$PROJECT_ROOT/.claude/hooks/pre-commit-feature-forge.sh"` (`hooks/git-pre-commit:13`) — o caminho **legado** `.claude/hooks/`, que o init nunca popula (tudo foi pra `.claude/forge/hooks/` na Task 0.8). `[[ -x "$HOOK" ]]` é falso → `exit 0`.
- O teste que "cobre" isso (`tests/integration/test_git_hook_delegator.py`) stuba um `git-pre-commit` sintético, então nunca exercita o caminho hardcoded real — o bug é invisível à suíte.

> **E se** o LLM termina uma feature, commita, e assume que `forge verify` rodou no gate de pre-commit? Não rodou. O gate de qualidade mais importante do lado-consumidor silenciosamente não faz nada. fail-open virou fail-silent — pior que bloquear, porque ninguém percebe. Artefatos quebrados passam pro PR com falso "verificado".

**Recomendação:** corrigir `hooks/git-pre-commit:13` pra `$PROJECT_ROOT/.claude/forge/hooks/pre-commit-feature-forge.sh`. Adicionar teste de integração que roda o `git-pre-commit` **real** contra um `.claude/forge/hooks/` populado e assere que `forge ingest --event pre-commit` é de fato invocado.

### 3.2 EXIT-2-COLLISION — exit 2 significa "pausado" E "erro fatal" ao mesmo tempo

**Evidência (verificada à mão):**
- Contrato (`docs/design/06-command-surface.md:186`): `2 | paused for input (needs response)` — o sinal load-bearing que dirige o loop de pause/resume.
- Mas handlers retornam 2 pra erro **fatal**: `plan.py:1396` (`return 2` em `ProjectRootNotFoundError`), `implement.py:1138` (idem), além de `evolve.py`, `undo.py`, `init.py` (bad args / `InitError`).
- O **mesmo** `ProjectRootNotFoundError` retorna **1** em `verify.py:183`, `status.py`, `doctor.py:217`, `memory_cli.py`, `graph_cli.py`.

> **E se** o LLM roda `forge plan x` num diretório que não é projeto forge? Recebe exit 2. Pelo contrato (e pela futura skill), exit 2 = "o engine emitiu pending, vá ler e responda". O LLM vai caçar um pending que não existe, ou pior, entrar em loop esperando input que nunca resolve — quando o problema real era "diretório errado, rode forge init". Exit 2 é o sinal mais carregado do protocolo inteiro; sobrecarregá-lo com "erro de init" envenena exatamente o sinal que o host precisa confiar.

**Exit-ladder não-documentada + colisões (ALTO, mesmo cluster):** handlers emitem 3/4/5/6/8 que o contrato (só 0/1/2/130) nunca lista — `plan.py:1448` `return 3`; `implement.py:1168` `return 4` (feature missing), `:1177` `return 5`, `:1186` `return 6`; `upgrade.py:227/246` `return 4` (smoke failed — **colide** com "feature missing" do implement); `qa/__init__.py:380` `return 8` (BLOCK — parece crash pra host keyed na escada documentada); `raw.py` `return 2/3`.

**Recomendação:** reservar exit 2 **exclusivamente** pra `PausedForInputError`/`UserPausedError` (deixar borbulhar só de `cli.main`). Trocar todo path de `ProjectRootNotFoundError`/bad-args/`InitError` pra `return 1`. Colapsar 3/4/5/6/8 → `1` + uma linha machine-readable em stderr (`forge-error: feature-missing`), OU documentar e des-colidir a escada por comando. Adicionar teste: "nenhum handler retorna 2 exceto via as exceções de pause".

### 3.3 CONC-1 — processos forge paralelos corrompem state files (sem flock, tempfile de nome fixo)

**Evidência:**
- `json_io.write_json` usa tempfile de **nome fixo** `path + ".tmp"` (`json_io.py:106`), sem componente de PID/random — i.e. `forge-pending.json.tmp` compartilhado.
- `detect_race`→`write_pending` tem janela TOCTOU documentada (`intent_state.py:604` "Lock file via fcntl.flock is deferred").
- O **próprio teste do projeto** `test_concurrent_writers_document_torn_write_window` (`tests/.../test_intent_state_concurrency.py:156-178`) **assere explicitamente que JSON inválido no destino é um resultado possível e deliberadamente NÃO assere sua ausência.**
- log append (`_append_intent_log`) e o response file também são keyed só em `project_root`+`state_dir`, nunca PID.

> **E se** dois agentes paralelos (o projeto SHIPa `dispatching-parallel-agents` e o workflow de maintainer incentiva dispatch paralelo) rodam `forge plan featA` e `forge implement featB` no mesmo root? Ambos chegam num `ask*`, ambos abrem `forge-pending.json.tmp` (mesmo inode), ambos escrevem concorrente → bytes interleaved → `os.replace` promove arquivo malformado. O próximo `read_pending` dá `JsonIOError` → exit 1 pros dois; OU `detect_race` engole o pending malformado como "stale" e sobrescreve silenciosamente o pending legítimo do outro agente → o usuário responde a pergunta de A que é atribuída ao intent-id de B (**cross-answer / state bleed entre features**).

**Impacto:** corrupção de dado + resposta-errada + vazamento de estado cross-feature sob agentes paralelos. O padrão que o forge promove quebra o forge.

**Recomendação:** (1) tempfile único por processo: `path + f".{os.getpid()}.{uuid4().hex}.tmp"` em `write_json` (elimina a colisão de truncamento, zero mudança de behavior pra single-writer); (2) `fcntl.flock(LOCK_EX)` num `state_dir/.lock` em volta da seção crítica detect_race→write_pending; (3) namespacing de pending/response/log por invocação concorrente (keyed pelo root intent-id ou PID).

---

## 4. Economia de tokens — a camada de output é host-blind (ALTO)

**Causa-raiz:** `engine/host/` governa só os fluxos interativos `ask*`. O **resultado** dos comandos (verify cascades, doctor, status, trees, banners) passa direto por `renderer.write()` — que nunca checa `detect_host`/`CLAUDECODE`. A UI "cinematográfica" é cega pra saber se quem lê é um terminal humano ou uma janela de contexto de LLM. `renderer.write` é um chokepoint único — então a maior parte do conserto é mudança de um arquivo só.

- **TOKEN-BLIND / C1 — non-TTY troca Unicode→ASCII mas NÃO reduz volume de token.** `renderer.py` non-TTY faz `to_ascii_box(strip_ansi(text))` — tira cor e vira `┌─┐`→`+-+`, mas mantém o mesmo número de linhas. Medido: `forge status` num projeto quase-vazio = **33 linhas / 1812 chars**, ~20 linhas de borda/divisória paddada a 80 colunas. A "degradação" non-TTV economiza ~zero token.
- **C2 — só `forge graph` tem `--json`.** `status`/`doctor`/`verify`/`memory` têm prosa humana como única superfície. Medido (projeto vazio): `doctor` = **75 linhas / 3908 chars**; `verify` = 15 linhas / 800 chars; pra responder "passou?" o LLM tem que parsear caixas e glyphs `✓`/`⚠`/`🛑`. As dataclasses internas pra serializar **já existem** (`_CategoryReport`/`_Check` no doctor, `_ValidatorResult` no verify). `graph_cli.py:344-453` é o template canônico a copiar.
- **H1 — banners/greetings/menus impressos ANTES do marker sob CC.** `init` sob CC despeja ~18 linhas de decoração antes do primeiro `<FORGE_INTENT/>`; `doctor` 2 linhas de banner; `graph` 1 linha. Fluxos interativos pausam várias vezes, repetindo o padrão a cada pausa.
- **H2 — prosa do persona `mentor_calmo` viaja pro LLM como custo de narração.** Greetings/acks/progress-phrases + o `three_paths_block` (~20 linhas) são impressos mesmo quando o marker já carrega `paths_detail` (o host deveria renderizar os 3 caminhos a partir do marker — `question.py:799-807`).
- **H3 — progress/spinner emitem linhas pro non-TTY** em vez de ficar silenciosos (`progress.py:67-70,104-106,142-146`). `init`+`reconfigure` têm 6 sites.
- **M1 — `options` do marker carrega padding de alinhamento de terminal + `(QN)`.** O marker do `forge graph` é 913 chars, ~30-40% padding não-semântico (`graph_cli.py:714-734`).
- **M3 — `doctor` imprime linhas `✓ ok` que não carregam sinal acionável** (signal-to-noise invertido: projeto mais saudável = maior dump).

**Recomendação:** tornar `renderer.write` host-aware (suprimir bordas/dividers/banners em modo agêntico, emitir `key: value` puro); adicionar `--json` a status/doctor/verify/memory copiando o padrão do `graph_cli`; introduzir env global `FORGE_OUTPUT=json|plain|tty` setado uma vez pelo host; rotear progress/warn pelos canais `emit_progress`/`emit_warn` do adapter (que já são no-ops corretos no CC).

---

## 5. Superfície de comando para invocação por LLM (ALTO)

- **NO-MANIFEST — não existe inventário machine-readable de comandos/args/descrições.** `_print_help` (`cli.py:235-251`) emite lista crua de 14 verbos sem args, sem descrição, sem JSON, apontando pra um doc cujo path pode não resolver. Decisão 10 proíbe argparse, mas um manifesto é um dict estático que `COMMANDS` já meio-tem. **E se** um LLM cold-start pergunta "o que forge faz, e `forge plan` precisa de arg?" — `forge --help` dá 14 verbos sem dica de argumento; ele tem que ler source ou um doc de 200 linhas. **Recomendação:** `forge --help --json` (ou `forge commands --json`) emitindo por comando `{name, summary, args, exit_codes, mutates, idempotent}`.
- **NO-WORKFLOW-ROUTER — nada diz ao LLM a ordem do ciclo (init→plan→implement→verify).** `forge status` (`status.py:1-68`) renderiza 6 seções mas **não** sugere próximo passo. **Recomendação:** `forge status` termina com "Próximo passo sugerido: forge implement <slug>" derivado do estado L1, e/ou `forge status --json` com `{active_feature, state, suggested_next_command}` — vira o router que o LLM precisa.
- **FLAG-CONTRACT-VIOLATION — "14 verbos, zero flags, zero exceções" (`06-command-surface.md:172`) é contradito pelo código:** `graph --json`/`--no-auto-build`, `verify --feature-slug`, `upgrade --force`, `ingest --key value`. E `--help` por-subcomando só funciona em 3 de 14. O LLM não pode generalizar a convenção de input. **Recomendação:** documentar um carve-out ("flags não-interativas pra invocação programática") + listá-las no manifesto.
- **DOCTOR-MASKS-FAILURE — `doctor` retorna 0 mesmo com warnings** por default; strictness via `FORGE_DOCTOR_STRICT=1` só documentada em docstring. Um LLM keyed no exit code fica cego pros warnings.
- **HELP-DOC-PATH-FRAGILE — `cli.py:250` aponta pra `~/Documents/feature-forge/docs/...`**, path que não resolve em installs XDG (`~/.local/share/feature-forge`). O único fio de Ariadne do `--help` pro contrato real quebra pra não-maintainers.

---

## 6. Footprint instalado no consumidor (ALTO/MÉDIO)

**O que já está certo (não regredir):** todo hook é fail-open (`forge ingest` sempre `return 0`); guarda non-forge em cada git hook; o `pre-commit` verify é genuinamente non-interactive (`run_scope(interactive=False)`); o merge de settings.json é append-only com dedup deep-equal; git hooks de usuário são preservados (migrados pra `.user` + chained); o post-edit filtra dirs gerados.

- **NO-ONBOARDING — forge instala zero artefatos que ensinem o LLM que forge existe ou como dirigi-lo.** Sem `CLAUDE.md` de consumidor, sem `.claude/skills/`, sem guia, sem `AGENTS.md`. **E se** uma sessão CC abre num consumidor forge-inicializado? O agente vê `.claude/forge/`, alguns hooks disparam, warnings de drift aparecem — mas nada diz que `forge plan`/`implement`/`verify` são o workflow pretendido. forge vira scaffolding invisível que o agente contorna. É a diferença entre "instalado" e "adotado". (Mesma raiz do DRIVER-001; resolução compartilhada: a skill.)
- **SUBAGENT-LATENCY — `SubagentStop` dispara `post-subagent-validate.sh` após CADA subagente**, que roda validators como `subprocess.run(..., timeout=30)` síncronos (`ingest.py:347-381`). Pros subagent-types mapeados (os do ciclo forge), adiciona latência perceptível no loop; validator pendurado = stall de 30s. **Recomendação:** timeout 5-10s e/ou fire-and-forget.
- **EDIT-LOOP-COST — `PostToolUse` (Edit|Write|NotebookEdit) roda SQLite síncrono por edit** (`graph_update_file` abre DB + migrations + parse + resolve imports). Num refactor de 40 arquivos = 40 transações sequenciais no loop. **Recomendação:** debounce/batch (`update_batch` já existe) ou deferir pra pós-commit.
- **SESSION-START-DEPENDS-ON-PATH — todos os hooks chamam `forge` bare.** `forge` só está no PATH via symlink do install.sh + edição de PATH que o usuário aceitou. Se o env do hook não herda o PATH do shell de login, `forge` não é achado, o `|| true` engole o erro → toda a camada de hooks silenciosamente morre, sem diagnóstico. **Recomendação:** assar o path absoluto do `forge` (init conhece FORGE_HOME) nos shims/settings; `forge doctor` deve verificar "hooks acham forge no env do hook".
- **CI-TEMPLATE-PLACEHOLDER (BAIXO) — `hooks/ci-pr-ingest.yml:34` tem `<TBD-user>`** não-resolvido (não auto-instalado; footgun humano).

---

## 7. Robustez / failure modes (ALTO/MÉDIO)

**Robusto de fato (verificado):** o anchor de state está **unificado** em `.claude/forge/state/` no código vivo (só docstrings mentem — ver L-1); ordenação multi-confirm→mutação-terminal é replay-safe (ex.: `undo` só faz `git revert` após ambos confirmam; replay determinístico via consumed-log); escrita atômica single-writer correta (tempfile→fsync→replace→fsync-dir, 0o600); parsing do consumed-log é defensivamente tolerante.

- **REPLAY-1 — `forge init` re-executa o pipeline inteiro a cada re-invocação exit-2.** `init.py:937` "por enquanto resume = restart" — o `step` salvo nunca é usado pra pular passos. Mutações (snapshot de cards, writes de inventory) rodam ANTES de asks posteriores. Hoje não corrompe (writes idempotentes), mas é frágil: qualquer mutação não-idempotente colocada antes de um ask vira bug de dado silencioso. **Recomendação:** honrar o checkpoint `step` OU hoist todos os `ask*` pra frente (coletar respostas, mutar uma vez).
- **REPLAY-2 — `reconfigure` faz move irreversível de `.bak` ANTES do apply-confirm.** `reconfigure.py:550-553` move `cards/X/`→`cards/X.bak` enquanto só *staging* a config in-memory; o confirm final vem em `:366-378`; o branch de cancel **não** restaura os `.bak`. **E se** o usuário escolhe "remover card X", chega no apply-confirm e responde "não"? Config intacta no disco, mas `cards/X/` sumiu → drift entre `forge-config.yaml` (lista X ativo) e o snapshot dir → `forge verify` hard-fail. **Recomendação:** deferir moves destrutivos pra DEPOIS do confirm.
- **ENV-1 — `CLAUDECODE`/`OPENCODE_*` herdado roteia forge pro adapter errado; sem scrub em produção.** `detect_host` keys puramente em env herdado (`env.py:10-15`, `detect.py:47-50`); scrub só existe no harness e2e e no sandbox de QA. **E se** forge é spawnado como subprocess de dentro de uma sessão CC (teste, hook, wrapper de tool)? Herda `CLAUDECODE=1` → `ClaudeCodeAdapter` emite marker + exit 2 esperando um harness CC que não está dirigindo → **hang / loop sem progresso**. **Recomendação:** exigir `host:` explícito em `forge-config.yaml` pra contextos não-interativos (config já vence) + scrub no boundary do engine.
- **DETECT-1 (MÉDIO) — `detect_codex`/`detect_cursor` são dead code em `detect_host`.** Existem (`env.py:19-24`), só alcançáveis via `detect_any_agentic()` que nunca é chamado em produção. O docstring do teste e2e afirma uma precedência (`... > CODEX* > CURSOR_* > ...`) que o código não implementa. Fallback é seguro (intent-file), mas é drift doc/código. **Recomendação:** wirar (mapear pra IntentFileAdapter) ou deletar + corrigir o docstring.
- **STALE-1 (MÉDIO) — pending de processo crashado trava a raia 10 min; PID gravado mas nunca checado.** `detect_race` grava `pid` (`intent_state.py:661-664`) mas não faz `os.kill(pid,0)`. **E se** um `forge plan` emite pending e crasha (OOM/SIGKILL)? 30s depois o retry vê pending recente com PID morto → `RaceDetectedError` → exit 1, bloqueando até ~10 min. **Recomendação:** probe de liveness antes de raise.
- **SCHEMA-1 (MÉDIO) — guard de schema-version é assimétrico:** `_check_schema_version` só roda em `read_response` (`intent_state.py:449`); `read_pending` e `detect_race` pulam. Version skew vira "race"/IO error confuso em vez do friendly "atualize feature-forge". **Recomendação:** aplicar o guard nas duas direções.
- **STDOUT-1 (BAIXO) — UI cinematográfica compartilha `sys.stdout` com o marker.** Progress `\r` + boxes na mesma stdout antes do marker. Baixa probabilidade (progress finaliza com `\n`, marker é flushed), mas acopla higiene de UI a correção de protocolo. **Recomendação:** rotear toda UI conversacional/progress pra `sys.stderr` (o TtyAdapter já faz), reservando stdout pro marker.
- **L-1 (BAIXO) — docstrings/comentários espalhados ainda citam o anchor legado `.claude/state/`** (`question.py`, `json_io.py`, `cli.py:331,375`, `intent_file.py:37`), e os helpers nativos mortos (`_emit_pending_and_raise` etc.) defaultam pro novo anchor — convidando regressão write-aqui/read-ali. **Recomendação:** deletar os helpers nativos mortos + varrer os docstrings.

---

## 8. Agents & templates como artefatos LLM (MÉDIO/ALTO)

Arquitetura sólida: `agents/*.md` são subagentes CC reais (host-dispatched, não órfãos); `templates/*` são LLM-filled (engine só substitui `{{FEATURE_SLUG}}`); split limpo entre artefatos-máquina (JSON/YAML, parseados por validators/synthesis) e narrativos (MD).

- **DUP-FINGERPRINT (ALTO) — o algoritmo de fingerprint sha256 é especificado à mão em 3 lugares** (`retrospective-agent.md:213-232`, `qa-synthesizer.md:67-68`, `evals.template.json`). **LLMs não produzem sha256 confiável por raciocínio — alucinam hex.** E se a normalização derivar entre os dois (NFC vs casefold), dois agentes computam fingerprints diferentes pro mesmo proposal → dedup quebra, propostas rejeitadas re-aparecem. **Recomendação:** helper determinístico (`engine/...fingerprint.py`) que o host chama; agentes referenciam disciplina §4, não re-derivam.
- **DUP-DUAL-BDD (ALTO) — `bdd.md` e `bdd.json` são autorados DUAS vezes pelo LLM** como "dois encodings" do mesmo Gherkin (ambos required em `validate_feature_package.py`). Drift quase-certo. **Recomendação:** `bdd.json` canônico, gerar `bdd.md` deterministicamente (ou dropar o .md).
- **BLOAT-CONDUCTOR (MÉDIO) — `planning-conductor.md` = 1168 linhas / 50KB** ingeridas em todo `forge plan`, incl. sub-prompts de retrospective (que pertencem a outro agente) e 6 exemplos. **Recomendação:** mover sub-prompts/exemplos pra siblings; alvo ~600 linhas.
- **SKEL-DUP (MÉDIO) — 7 agentes de planejamento repetem o mesmo esqueleto** (Voice/What-you-receive/Output/What-you-are-NOT/Discipline). "Never invent" em 9 arquivos, voz mentor-calmo em 16. **Os qa-auditors já provam o conserto** (`qa-auditor-*.md:20-22` herdam o overlay, não reescrevem). **Recomendação:** extrair um `forge-subagent-base` (skill ou snippet `agents/_shared/`) — **maior win de token + manutenção.**
- **JSON-GUIDEKEY-INCONSISTENT (MÉDIO) — `qa-finding.template.json` e `qa-report.template.json` não têm as `_template_rules`** que os outros JSON templates usam pra guiar o fill. **ENUM-FREETEXT (MÉDIO) — campos de alta cardinalidade usam free-text** (`{{server_only_local_only_both_none}}`) onde comment-enums (estilo `task-contract.template.yaml`) seriam determinísticos e validáveis.
- **PORT-CC-TOOLS (BAIXO) — frontmatter de conductor nomeia tools CC-específicas** (`AskUserQuestion`, `mcp__claude_ai_*`) sem análogo opencode. Ok pro piloto CC-primário; abstrair antes da paridade opencode.

---

## 9. Simulações "E se..." compostas (cross-cutting)

Cenários que nenhum eixo isolado vê — emergem do cruzamento dos findings:

1. **Morte no dia-1 do piloto (DRIVER-001 × stale-anchor docs × intent-id):** instala → `forge plan` → marker + exit 2 → sem skill o modelo não sabe o protocolo → mesmo se inferir, re-invoca com argv normalizado (→ mismatch → exit 1) ou escreve resposta em `.claude/state/` (docs velhas) em vez de `.claude/forge/state/` → nunca consumida → loop. **Produto morto na chegada.**
2. **Agentes paralelos se corrompem (CONC-1 × `dispatching-parallel-agents`):** o próprio padrão que o forge promove (dispatch paralelo) dispara o tempfile compartilhado → torn write → cross-answer entre features.
3. **Erosão silenciosa de qualidade (DEAD-VERIFY × DOCTOR-MASKS-FAILURE):** modelo termina feature, commita; o gate verify está morto → nenhuma validação roda; `doctor` retorna 0 com warnings → o agente tem falso senso de qualidade o tempo todo, reporta "verificado" sobre artefato quebrado.
4. **Sangria de token em escala (TOKEN-BLIND × NO-MANIFEST):** cada `status`/`doctor`/`verify` pra se orientar = centenas de tokens de caixa ASCII sem valor de máquina; numa sessão multi-feature, milhares de tokens parseando decoração — e risco de ler `✓` vs `⚠` errado → decisão errada.
5. **Hang por env leak (ENV-1 × subprocess):** agente roda forge num subprocess (teste/hook/tool aninhado) → herda `CLAUDECODE=1` → CC adapter emite marker + exit 2 → ninguém dirige (é subprocess, não o loop top-level) → hang/loop. Sem scrub em produção.

---

## 10. O que já está bom (balanço autocrítico)

Pra calibrar severidade com honestidade — muita coisa está certa:

- **`forge graph --json`** (`graph_cli.py:344-453`) é o modelo de superfície LLM-first: stdout só pra JSON, build-noise + erros pra stderr, exceções internas sanitizadas, aliases tolerantes (`q3`/`3`/`orphan-files`). É o template a generalizar.
- **O protocolo intent em si** (schema, exit-2, re-invocação, multi-question, cancel/pause) é **completo e bem especificado** em `docs/schemas/intent-protocol.md`. O gap não é o protocolo — é a contraparte (driver) nunca entregue.
- **Hooks fail-open + non-blocking + brownfield-safe merge** — os fundamentos de segurança agêntica estão certos; o install não *atrapalha* o loop (falha seguro), só falha *silencioso e invisível*.
- **Mapeamento de sentinelas pra exit limpo em `cli.main`** (`cli.py:363-379`): `RaceDetectedError`/`IntentMismatchError`/`JsonIOError` viram exit 1 com mensagem, não traceback cru.
- **qa-auditors são DRY exemplares** (herdam overlay) e o padrão `_*` guide-key em JSON templates é design LLM-first esperto.
- **Anchor de state vivo unificado** em `.claude/forge/state/` (só docstrings mentem).
- **`renderer.write` é chokepoint único** — a maior parte do conserto de token é mudança de um arquivo.

---

## 11. Catálogo de oportunidades (skill / hook / agent / template / loop)

| Tipo | Oportunidade | Endereça | Prioridade |
|---|---|---|---|
| **Skill** | `feature-forge` driver SKILL.md (ensina o intent loop + re-invocação + exit codes), instalada por `forge init` | DRIVER-001, NO-ONBOARDING | **P0** |
| **Skill/Doc** | `AGENTS.md` pro opencode (mesmo loop, mecanismo opencode) | DRIVER-003 | P0 |
| **Skill** | `forge-subagent-base` (persona/disciplina/output compartilhados dos 7 agentes) | SKEL-DUP, BLOAT-CONDUCTOR | P1 |
| **Loop/Protocol** | `McpAdapter` com elicitation nativa (5º host adapter) — dissolve o teaching burden | DRIVER-006 | P1 (estratégico) |
| **Loop/CLI** | `forge --help --json` (manifesto) + `forge status --json` com `suggested_next_command` (router) | NO-MANIFEST, NO-WORKFLOW-ROUTER | P0 |
| **CLI** | Env global `FORGE_OUTPUT=json\|plain\|tty` + `--json` em status/doctor/verify/memory | TOKEN-BLIND, C2 | P0 |
| **CLI** | Modo não-interativo (`--json` answers) pra pular o round-trip pause/resume no caso comum | (eficiência) | P1 |
| **Hook** | Corrigir path do `git-pre-commit` + teste do hook REAL | DEAD-VERIFY | **P0** |
| **Hook** | Debounce/batch do PostToolUse graph; timeout menor / async no SubagentStop; assar path absoluto do `forge` | EDIT-LOOP-COST, SUBAGENT-LATENCY, PATH | P1 |
| **Hook** | SessionStart que injeta "este projeto usa forge — rode `forge status`" + aponta pra skill | NO-ONBOARDING | P1 |
| **Agent** | Abstrair tools CC-específicas (AskUserQuestion/mcp__claude_ai_*) dos prompts pra paridade opencode | PORT-CC-TOOLS | P2 |
| **Template** | `bdd.json` canônico (gerar/dropar `bdd.md`); `_template_rules` nos qa-*.json; comment-enums nos spec YAML | DUP-DUAL-BDD, JSON-GUIDEKEY, ENUM-FREETEXT | P1 |
| **Engine** | Helper determinístico de fingerprint (LLM não faz sha256) | DUP-FINGERPRINT | P1 |
| **Engine** | Des-colidir exit codes (reservar 2 pra pause; colapsar 3/4/5/6/8→1 + tag stderr) | EXIT-2-COLLISION | **P0** |
| **Engine** | Concorrência: tempfile por-PID + flock + namespacing por invocação | CONC-1 | **P0** |
| **Engine** | Replay-safety: hoist asks / deferir mutações pós-confirm; honrar checkpoint step | REPLAY-1/2/3 | P1 |
| **Engine** | Scrub de env agêntico no boundary + pin de host em config | ENV-1, DETECT-1 | P1 |
| **Engine** | renderer host-aware (suprimir decoração em modo agêntico) | TOKEN-BLIND | P0 |

---

## 12. Roadmap priorizado

### P0 — gate do piloto (nada de piloto sem isso)
1. **`feature-forge` SKILL.md driver** + instalação por `forge init` + `AGENTS.md` opencode. *(Sem isso o produto não funciona.)*
2. **DEAD-VERIFY** — corrigir o path do hook + teste real.
3. **EXIT-2-COLLISION** — reservar exit 2 pra pause; colapsar a escada.
4. **CONC-1** — tempfile por-PID + flock (mínimo viável: tempfile por-PID já mata o caso comum).
5. **TOKEN-BLIND + `--json`/`FORGE_OUTPUT`** — renderer host-aware + `--json` nos read commands + `forge --help --json` manifesto + `forge status` router.

### P1 — robustez e adoção
6. ENV-1 scrub + pin de host; REPLAY-1/2 (deferir mutações pós-confirm); NO-ONBOARDING (SessionStart pointer).
7. Hooks: debounce graph, timeout/async subagent-validate, path absoluto do forge.
8. Templates: bdd single-source, `_template_rules`, comment-enums; fingerprint helper.
9. `forge-subagent-base` (extrair esqueleto dos 7 agentes); BLOAT-CONDUCTOR.
10. **McpAdapter (estratégico)** — avaliar como caminho que dissolve o teaching burden de vez.

### P2 — polish
11. DETECT-1 (wirar/deletar codex/cursor), STALE-1 (liveness probe), SCHEMA-1 (guard simétrico), STDOUT-1 (UI→stderr), L-1 (limpar docstrings/dead-code), PORT-CC-TOOLS.

---

## Apêndice — índice de findings por severidade

**CRÍTICO (4):** DRIVER-001 (host não dirige o loop), DEAD-VERIFY (gate verify morto), EXIT-2-COLLISION (exit 2 ambíguo), CONC-1 (corrupção concorrente).
**ALTO (8):** TOKEN-BLIND, NO-MANIFEST, NO-WORKFLOW-ROUTER, ENV-1, REPLAY-1, REPLAY-2, NO-ONBOARDING, DUP-FINGERPRINT, DUP-DUAL-BDD, FLAG-CONTRACT-VIOLATION, EXIT-LADDER. *(cluster)*
**MÉDIO:** SUBAGENT-LATENCY, EDIT-LOOP-COST, SESSION-START-PATH, DETECT-1, STALE-1, SCHEMA-1, REPLAY-3, BLOAT-CONDUCTOR, SKEL-DUP, JSON-GUIDEKEY-INCONSISTENT, ENUM-FREETEXT, DOCTOR-MASKS-FAILURE, HELP-DOC-PATH-FRAGILE, HIDDEN-COMMANDS.
**BAIXO:** STDOUT-1, L-1, CI-TEMPLATE-PLACEHOLDER, DRIFT-NOISE, PORT-CC-TOOLS, ARG-PARSING-DIVERGENCE, HELP-COUNT-DRIFT, RAW-STUB-EXIT-3.
**OPORTUNIDADE:** MCP adapter (DRIVER-006), FORGE_OUTPUT env, forge skill/rule, non-interactive mode, route-progress-through-adapter.

> **Conclusão (mentor calmo):** a engenharia do PR #17 é boa — o adapter layer, o protocolo intent e a disciplina de fail-open estão certos. O que falta é a *outra metade*: o host nunca foi ensinado a dirigir o que o engine tão cuidadosamente passou a emitir. Resolva o driver (uma skill, dias de trabalho), conserte os dois bugs de path/exit-code e o de concorrência, e torne o output host-aware — e o forge passa de "arquitetura elegante e inerte" pra "ferramenta que um LLM dirige de olhos fechados, gastando pouco token e entregando com confiança".
