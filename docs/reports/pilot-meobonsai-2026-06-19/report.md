# Relatório — Piloto MeoBonsai IA-first · forge v1.5.0

> Data: 2026-06-19 · forge v1.5.0 (dev-clone em `~/Documents/feature-forge`, tip de `main`)
> Alvo: MeoBonsai (KMP real — composeApp/androidApp/iosApp/shared/functions)
> Sandbox: worktree `MeoBonsai-pilot` na branch `pilot/forge-v1.5.0` (de `origin/main` @ `5d1d435`)
> Driver: Claude Code top-level fechando o intent loop conforme `skills/feature-forge/SKILL.md`
> Protocolo: `docs/reports/pilot-meobonsai-2026-06-19/protocol.md`

## Sumário executivo

O piloto exercitou **install → init**. O init **não completou** num projeto
brownfield real: bate em dois bloqueadores críticos independentes
(**P-01** loop de intent e **P-09** resolução de cards). Por decisão do
mantenedor, o piloto parou no init — `plan`/`graph`/`implement`/`QA` não
foram exercitados (dependem de um `forge-config` válido que o init produziria).

**Veredito AI-first end-to-end:** o modelo AI-first canônico (host claude_code)
**não fecha o ciclo** hoje. O loop documentado no `SKILL.md` (responder o
`<FORGE_INTENT>` + re-invocar com argv idêntico) trava no PRIMEIRO prompt de
qualquer comando com checkpoint, porque a re-invocação injeta um prompt de
"Resume?" não-documentado cujo intent-id não bate com a resposta pendente.
Há workaround (apagar o checkpoint antes de re-invocar), mas é externo ao
contrato documentado.

**Positivos confirmados:** B1 (versão) corrigido · F1 (PATH no install)
resolvido com `install.sh` robusto · detecção rest-stack (B2/B7) melhorou —
agora detecta ktor/rest/serialization (era cega no v1.2).

## Ambiente & método

- forge v1.5.0; `forge --version` lê `engine.__version__` (fonte única).
- Adapters testados: **claude_code** (via `CLAUDECODE=1`, default do ambiente)
  e **intent-file** (via `FORGE_FORCE_INTENT_MODE=1`).
- Drive: ler `<FORGE_INTENT>` (stdout, claude_code) ou `forge-pending.json`
  (intent-file) → escrever `.claude/forge/state/forge-response.json` com o
  mesmo intent-id → re-invocar argv idêntico.
- Não se rodou o instalador global (`scripts/install.sh | bash`) — outward-facing
  + mutaria PATH global; avaliado por leitura. Binário em uso = dev-clone na main
  (= o que a última release tag v1.5.0 entregaria).

---

## Findings

Severidade: **Crítica** (bloqueia / setup errado silencioso) · **Alta** · **Média** · **Baixa**.
Categoria: 🐛 bug · 🧱 fricção UX · 📄 doc · 💡 melhoria.

### [P-01] 🐛 Crítica — Loop de intent dá deadlock em comandos com checkpoint · etapa: init

**Descrição.** Quando um comando `forge` pausa (escreve checkpoint + emite
`<FORGE_INTENT>` X) e o host segue o `SKILL.md` (escreve response pra X +
re-invoca argv idêntico), a re-invocação **detecta o checkpoint e emite um
intent DIFERENTE primeiro** — "Resume de init pendente?" (id Y). A response
pra X não bate com Y → `IntentMismatchError` → exit 1. O `SKILL.md` não
documenta esse prompt de resume. Qualquer host seguindo a doc trava no
primeiro prompt de qualquer comando com checkpoint (init, reconfigure…).

**Repro.**
```
cd <projeto>; forge init            # exit 2, emite preset prompt id=8332…, escreve checkpoint
# host escreve forge-response.json {intent-id: 8332…, value: sim}
forge init                          # exit 1: "expected 'cec9…', got '8332…'"
```

**Esperado vs observado.** Esperado: re-invocar consome a response e avança.
Observado: re-invocar emite "Resume?" (cec9…) e rejeita a response (8332…).

**Diff empírico (causa-raiz).** Os dois ids são prompts distintos:
- fresh (`8332d3fe-…`): `question="Confirmar preset kmp-mobile?"`
- resume (`cec993ea-…`): `question="Resume de init pendente?"`, options `{resume, discard, abort}`

**Agravantes.**
- O adapter **claude_code não persiste `forge-pending.json`** (comentário
  deliberado em `engine/host/adapters/claude_code.py` ~L28-33): "no pending.json
  is written on this channel". Sem pending em disco, não há id persistido pra
  reconciliar — o host depende só do marker stdout.
- O intent-id é **determinístico** (SHA-256 de kind+question+options+extra+
  command+command_args — `engine/ui/question.py` `stable_intent_id` ~L183-243),
  então é estável no MESMO caminho; o problema é o resume ser um prompt OUTRO.

**Workaround (verificado nos 2 adapters).** Apagar o checkpoint
(`.claude/.init-checkpoint.yaml`) antes de re-invocar → força o caminho fresh
(id estável) → o `consumed-intent-log` (`.claude/forge/state/forge-intent-log.jsonl`)
carrega as respostas já dadas (idempotência §4 do schema). Avança normalmente.

**Pointer de fix.** Reconciliar o prompt de resume com o intent loop: ou (a) o
resume vira o primeiro intent que o host DEVE responder (e documentar no
SKILL.md), ou (b) suprimir o resume quando há response pendente correspondente
ao checkpoint, ou (c) claude_code persistir o pending pra reconciliação. Ver
também P-11.

**Regressão?** Novo (o intent loop nunca foi exercitado em piloto — v1.2 parou antes).

### [P-09] 🐛 Crítica — `init` brownfield aborta no resolver (DEP-MISSING) · etapa: init

**Descrição.** Confirmar a detecção brownfield "como-is" num projeto híbrido
real (firebase + rest + local) produz um conjunto de cards insatisfazível e o
resolver aborta:
```
🛑 RESOLVER-ERRORS … exit 1 … [FORGE-ERR:ABORTED]
DEP-MISSING: card 'firestore-security-rules' requires 'persistence-server'
but no active card provides it.
```
A detecção pegou `firestore-security-rules` (MeoBonsai tem `firestore.rules`)
mas **não** pegou o provider de persistência server-side (`firestore-persistence`).
Como a única opção funcional da detecção é "a) confirmar como-is" (ver P-02) e
ela leva ao abort, o init **não completa** neste projeto pelos caminhos oferecidos.

**Repro.**
```
forge init  → confirma preset kmp-mobile (a) → no prompt de backend, escolhe (a) "confirmar como-is"
→ resolver: DEP-MISSING firestore-security-rules → exit 1
```

**Esperado vs observado.** Esperado: detecção coerente (incluir o provider
faltante OU não detectar a security-rule isolada) e init completar. Observado:
conjunto inconsistente → abort, sem caminho funcional de correção.

**Pointer de fix.** (1) Detecção: ao detectar `firestore-security-rules`,
incluir/exigir o provider `firestore-persistence`, ou tratar security-rules
como add-on dependente. (2) Implementar os caminhos de correção (P-02) pro
usuário remover/ajustar cards. (3) Resolver deveria pausar (exit 2) pra escolha,
não abortar (ver P-10).

**Regressão?** Relacionado a B2/B7 (v1.2): a DETECÇÃO melhorou (rest agora é
visto), mas a RESOLUÇÃO brownfield agora quebra num híbrido real.

### [P-02] 🐛 Alta — 3-caminhos com 2 paths fantasma (não implementados) · etapa: init

**Descrição.** No prompt de detecção brownfield (`ask_three_paths`), as opções
**b** ("Ajustar células divergentes") e **c** ("Começar do zero / custom-from-scratch")
trazem no `motive` o texto de dev **"[W7.2 implementa o multi-select.]"** /
**"[W7.2 implementa o fluxo greenfield.]"** e não estão implementadas. Só a
opção **a** funciona. Viola a disciplina dos 3-caminhos (2 dos 3 são phantom)
e vaza texto de roadmap interno no artefato do usuário (Mandamento 5).

**Esperado vs observado.** Esperado: 3 caminhos funcionais OU não oferecer os
não-implementados. Observado: 2 paths dead + leak de "[W7.2 …]".

**Pointer de fix.** Implementar b/c (W7.2) OU ocultá-los até existirem; remover
o texto "[W7.2 …]" do `motive` user-facing.

**Regressão?** Classe F3 do v1.2 (opção morta + texto de dev no menu) — persiste em forma nova.

### [P-03] 🐛 Alta — Detecção marca CONFLITO falso pra pareamento KMP legítimo · etapa: init

**Descrição.** A detecção composta reporta:
```
ui:         CONFLITO — compose-screens, swiftui-screens
navigation: CONFLITO — nav3, swiftui-navigation
```
Mas isso é o pareamento **correto** de KMP (Compose=Android, SwiftUI=iOS;
Nav3=Android, NavigationStack=iOS) — não conflito. Pior: a mesma lista de
conflito se repete **idêntica** nas linhas `android`, `ios` e `kmp` (a partição
por plataforma está quebrada — atribui cards iOS à linha android e vice-versa).
Num projeto KMP real, todo eixo de UI/nav vira "conflito".

**Pointer de fix.** A detecção deve tratar cards por-plataforma como
complementares (não conflitantes) quando cada um pertence à sua plataforma; e
corrigir a partição android/ios/kmp pra não repetir o mesmo set nas 3 linhas.

**Regressão?** Novo (relacionado à classe B4 de naming/detecção do v1.2).

### [P-10] 🐛 Alta — Gate RESOLVER-ERRORS imprime 3-caminhos mas aborta (exit 1) em vez de pausar · etapa: init

**Descrição.** O gate de erro do resolver renderiza o bloco "Três caminhos pra
resolver" (voltar/personalizar/abortar) mas termina com `[FORGE-ERR:ABORTED]`
e **exit 1** — não emite intent (exit 2) pra o usuário escolher. Não há
`forge-pending.json`/marker pro gate; o 3-caminhos é cosmético. Viola a
disciplina de gate-resolution (apresenta escolhas que não aceita) e, combinado
com P-02/P-09, deixa o usuário sem saída.

**Pointer de fix.** O gate deve pausar (exit 2) com `ask_three_paths` real, ou
deixar claro que é guidance read-only e oferecer o caminho de correção em outro
ponto interativo.

**Regressão?** Novo. (Severidade Alta por calibração de detection/gate findings —
`.claude/rules/plan-auditor.md §Severity calibration`.)

### [P-11] 🐛 Alta — "Resume" não resume; checkpoint é vestigial · etapa: init

**Descrição.** No prompt "Resume de init pendente?", as labels são contraditórias:
- `resume` = "começar do zero mantendo o checkpoint como audit"
- `discard` = "apagar o checkpoint e começar limpo"

**Nenhuma** continua do step salvo — ambas recomeçam do zero; a única diferença
é manter o checkpoint como artefato. Ou seja: o checkpoint não resume progresso
(só serve de auditoria) e a label "resume" é semanticamente errada.

**Pointer de fix.** Ou implementar resume real (continuar do step) ou renomear
as opções pra refletir que ambas recomeçam (ex.: "recomeçar (manter audit)" /
"recomeçar (limpar)"). Reavaliar se o checkpoint de init tem valor sem resume real.

**Regressão?** Novo.

### [P-04] 🧱 Média — Tabela de detecção inteira embutida no campo `question` · etapa: init

**Descrição.** O `ask_three_paths` de backend coloca toda a tabela de detecção
(20+ linhas, com `&#10;` escapados) dentro do campo `question` do intent. Um
host renderizando isso num `AskUserQuestion` recebe um blob gigante como
"pergunta". O conteúdo de contexto deveria ser separado da pergunta.

**Pointer de fix.** Mover a tabela pra um campo de contexto/`paths-detail` ou
imprimir como contexto antes do intent; manter `question` curto.

### [P-05] 🐛 Média — `forge <subcmd> --help --json` ignora `--json` · etapa: install/contrato

**Descrição.** `forge --help --json` (top-level) emite manifesto JSON correto.
Mas `forge init --help --json` (per-subcomando) imprime prosa, ignorando `--json`.
Uma automação/IA inspecionando o contrato de um subcomando específico recebe
prosa, não JSON.

**Pointer de fix.** Suportar `--json` no help per-subcomando OU erro explícito;
não ignorar a flag silenciosamente.

### [P-06] 📄 Média — Schema intent-protocol não documenta o marker stdout `<FORGE_INTENT>` · etapa: doc

**Descrição.** `docs/schemas/intent-protocol.md` documenta só o protocolo
file-based (`forge-pending.json`) e nunca menciona o marker stdout
`<FORGE_INTENT>` que o adapter claude_code usa (e que NÃO escreve pending). O
`SKILL.md` cobre o marker; os dois divergem. Um implementador de host lendo só
o schema fica perdido sobre o canal real do host primário.

**Pointer de fix.** Documentar o marker stdout + a diferença claude_code
(stdout, sem pending) vs intent-file (pending em disco) no schema.

### [P-07] 🧱 Baixa — Frase de abertura varia entre runs · etapa: init

**Descrição.** Observado em 4 runs: "Cheguei. Pode me contar o contexto." /
"Pronto. Vamos olhar isso juntos." / "Aqui. Vou ler o que já existe…". Variação
de banner entre execuções.

**Pointer de fix.** Documentar se é intencional; se não, fixar.

**Regressão?** F6/S10 do v1.2 — persiste.

### [P-08] 🧱 Média — Opção `outro` no preset com texto de dev · etapa: init

**Descrição.** No prompt "Confirmar preset kmp-mobile?", a opção `outro` diz
"escolher outro preset (não disponível no v1 — só kmp-mobile)" — texto de dev/
roadmap vazando no menu user-facing.

**Pointer de fix.** Remover a opção morta ou marcar como disabled sem o "(não disponível no v1)".

**Regressão?** F3 do v1.2 — persiste literalmente.

### [P-12] 🧱 Média — Sem ETA; timestamps internos enganam · etapa: init

**Descrição.** Os prefixos `[0:01]`, `[1:00]` são relógio interno da ferramenta,
não tempo decorrido nem ETA. Sem aviso de duração esperada (discovery + futuro
graph build). Reaparece a fricção F2/D6 do v1.2.

**Pointer de fix.** Mostrar ETA antes de etapas longas; rotular os timestamps.

**Regressão?** F2/D6 do v1.2 — persiste.

---

## Status das regressões herdadas (checklist v1.2 · 2026-06-09)

| Item v1.2 | Status v1.5.0 |
|---|---|
| B1 — versão hardcoded em bin/forge | ✅ Corrigido (lê `engine.__version__`) |
| B2/B7 — detector rest-stack cego | ⚠️ Melhorou (rest detectado), mas resolução brownfield quebra (P-09) |
| B3 — i18n keys 0 | ⏳ Não verificado (init não chegou no inventory) |
| B4 — design-system naming errado | ⏳ Não verificado |
| F1 — binário fora do PATH | ✅ Resolvido (install.sh: PATH 3-caminhos + conflito + smoke) |
| F2/D6 — sem ETA, timestamps enganam | 🔴 Persiste (P-12) |
| F3 — opção morta `[outro]` + texto dev | 🔴 Persiste (P-08, e classe nova P-02) |
| F6/S10 — frase de abertura varia | 🔴 Persiste (P-07) |
| D4/D5 — plan/implement "stub/não-AI" no README | ⏳ Não verificado (não chegou no plan); README "Limites conhecidos" ainda diz "implement é stub" e "Anthropic API é Phase 6" — possivelmente stale vs camada AI-first; A VERIFICAR |
| reconfigure (B-reconfigure*, F-reconfigure*) | ⏳ Não exercitado |

**Drift de stats no README (novo, 📄 Média):** contagens internas inconsistentes
— validators "20" (L14) vs "22" (L5/196) vs "25+3" (L122); cards "22" (L105)
vs "29" (L5/120); tests "1797/190" (L125) vs "1863/204" (L5/196).

---

## Não exercitado (piloto parou no init por decisão do mantenedor)

`forge plan`, `forge graph` (Q1-Q17), `forge implement`, `forge verify`,
`forge doctor`, `forge qa`, cards locais, memory L1/L2. Dependem de um
`forge-config` válido que o init produziria.

---

## Prioridades de fix sugeridas

**P0 (bloqueadores do AI-first / init num projeto real):**
- P-01 — reconciliar prompt de resume com o intent loop (+ documentar no SKILL.md)
- P-09 — detecção brownfield coerente (provider de persistência) + caminho de correção
- P-10 — gate de resolver deve pausar pra escolha, não abortar

**P1:**
- P-02 — implementar/ocultar paths b/c; remover leak "[W7.2 …]"
- P-03 — não marcar pareamento KMP por-plataforma como conflito; corrigir partição
- P-11 — resume real OU renomear opções; reavaliar valor do checkpoint
- P-08 — opção morta `outro`

**P2:**
- P-04 — separar tabela de detecção do campo `question`
- P-05 — `--json` per-subcomando
- P-06 — documentar marker stdout no schema
- P-07 / P-12 — frase de abertura + ETA/timestamps
- README — reconciliar drift de stats + revisar "Limites conhecidos" (D4/D5)

---

## Pointers de código (root-cause)

- Seleção de adapter: `engine/host/detect.py` ~L38-67 (precedência: config `host:` > `FORGE_FORCE_INTENT_MODE` > `CLAUDECODE` > TTY > intent-file).
- claude_code sem pending: `engine/host/adapters/claude_code.py` ~L28-33.
- intent-id determinístico: `engine/ui/question.py` `stable_intent_id` ~L183-243.
- read_response / mismatch: `engine/ui/intent_state.py` (consumed-log §4).
- Prompt de resume + resolver brownfield: handler do `init` (localizar a emissão de "Resume de init pendente?" e o resolver DEP-MISSING — provável `engine/init.py` + camada de cards).

---

## Findings round 3

### [P-13] 🐛 Média — Resolução de conflito do eixo `data` elege card de security-rules como vencedor
No init brownfield do MeoBonsai (firebase+rest híbrido), o eixo `data` em CONFLITO resolveu pra `firestore-security-rules` (um card de *security rules*) como vencedor, em vez de um card primário de acesso a dados (ex.: firestore-persistence). Init completa e config é válido, mas semanticamente questionável — a heurística de "vencedor" do eixo data deveria preferir o card de acesso a dados, não a security-rule. Pointer: resolver de cards / heurística de winner em eixo conflitado.

### [P-14] 🧱 Baixa — Vocabulário do `forge plan` assume "tela" mesmo pra componentes
`forge plan meo-badge` (um componente de DS, não uma tela) abriu com "Tem material visual pra essa **tela**?". O fluxo de plan assume feature=tela; pra features tipo componente/serviço o vocabulário soa errado. Pointer: prompts do plan flow (source-inquiry).

### [P-15] 🐛 Crítico — Loop AI-first do `forge plan` quebrado (guard de re-entrada intercepta) — fix do R1 foi estreito
`forge plan <slug>` cria a feature (status=planning) na 1ª invocação; toda re-invocação do loop do host bate no guard "feature já existe" (id próprio) ANTES de re-alcançar o prompt em-voo → a response pendente não casa → IntentMismatchError → exit 1. Mesma classe do P-01 (init), mas o fix do R1 gateou só o resume do init (per-comando). Atinge o comando CENTRAL — o modelo AI-first não fecha end-to-end mesmo pós-R1. Guards afetados: plan `_handle_active_slug_collision` (plan.py:1257), plan `_handle_done_feature_branch` (plan.py:1313), reconfigure draft-confirm (reconfigure.py:246). CORRIGIDO no round 4 via helper compartilhado `host_is_replaying` (generaliza o gate do P-01).

---

## Findings round 5 + validação de lifecycle (2026-06-19)

Após R4 (fix generalizado de re-entry guards), o piloto continuou pelo lifecycle no engine corrigido, com um subagente-conductor preenchendo os artefatos do feature de teste `meo-divider`.

### Validações positivas (o que passou a funcionar)

- ✅ **`forge plan` dirige end-to-end via loop canônico** (P-15 corrigido). Waves A→E avançam sem IntentMismatchError, sem workaround. Retomada/resume limpa ("Detectei plano em andamento — retomando na Wave X").
- ✅ **Readiness (Wave E) enforça antes do dispatch.** Plano vazio (placeholders) é pego pela readiness (`readiness-not-ready`, ask_three_paths, pausa exit-2 corretamente). Plano preenchido → `readiness_verdict.status: ready` → "Próximo: forge implement". O caminho "re-revisar" RE-REVISA de forma NÃO-destrutiva (não sobrescreve os artefatos preenchidos — verificado via diff vs backup).
- ✅ **D5 RESOLVIDO — `forge implement` é REAL, não stub.** Mostra **Plan Mode** por task (contrato: allowed_files, BDD coberto, gates ativos: readiness-must-be-ready / no-files-outside-allowed-files / validations-must-pass / completion-evidence-required / no-invented-behavior) → confirm → Apply Mode. O modelo AI-first task-driven está vivo.
- ✅ **D4/D5 — README "Limites conhecidos" está STALE.** A seção ainda afirma "`forge implement` é stub manual — Apply Mode é Phase 6" e "plan.py/implement.py narram fluxo... integração Anthropic API é Phase 6". Na prática (modelo CC-fronted), plan e implement são fluxos reais dirigidos pelo host AI. Recomendado reescrever a seção "Limites conhecidos".

### [P-16] 🧱 Média — Gates de avanço de wave (A→D) não validam preenchimento de artefato

Os gates "Status da Wave X? continuar/pausar" avançam mesmo com os artefatos 100% `{{placeholder}}`. O validator `check_unfilled_placeholders` NÃO está plugado no gate de avanço. **Mitigado:** a readiness (Wave E) pega antes do dispatch. Mas o feedback é tardio — o host descobre só no fim que nada foi preenchido. Recomendado: validar (ou ao menos avisar) o preenchimento por-wave, não só no gate final. Pointer: handler do `plan` (gates de wave) + `validators/check_unfilled_placeholders.py`.

### [P-17] 🐛 Alta — `forge implement` bloqueado por phase-lock stale ("by 'None'")

`forge implement meo-divider` (logo após plan completar com readiness=ready) falha:
```
forge implement: 'meo-divider' phase-locked by 'None'. Run `forge undo` to release, or wait.
[FORGE-ERR:LOCKED]
```
Causa-raiz (duas facetas):
1. **Lock não liberado no plan-complete.** O arquivo `.claude/memory/L1/meo-divider/.phase-lock` persiste com conteúdo `"planning"` após o plan completar. Já o `status.json` diz `"phase-lock": null` — **as duas fontes de verdade divergem** (arquivo `.phase-lock` vs `status.json:phase-lock`). O plan adquire o phase-lock da fase "planning" e não o libera ao finalizar.
2. **Mensagem de erro errada.** Diz "phase-locked by **'None'**" quando o conteúdo do lock é `"planning"` — o código formata o holder como None em vez do valor real. Diagnóstico enganoso.

**Workaround usado no piloto:** `rm .claude/memory/L1/<slug>/.phase-lock` → implement destrava e roda. **Fix recomendado:** (a) plan-complete deve liberar o phase-lock; (b) reconciliar `.phase-lock` (arquivo) ↔ `status.json:phase-lock` (fonte única); (c) corrigir a mensagem pra mostrar o holder real. Pointers: lógica de phase-lock em `engine/` (memory L1) + handler de plan-complete + o check no `engine/implement.py`.

### Estado do AI-first end-to-end (pós-R1+R4)

| Etapa | Status |
|---|---|
| init | ✅ completa (R1) |
| plan | ✅ end-to-end com conductor (R4) |
| graph/status/inventory | ✅ funcionam (reuse-intelligence achou P-0001) |
| implement | ✅ REAL (Plan Mode); destrava após workaround do P-17 |
| QA (verify/doctor/qa) | ⏳ não exercitado nesta campanha |

Bloqueadores remanescentes pra um lifecycle 100% limpo: **P-17** (phase-lock stale — Alta). Demais (P-16/P-14/P-13) são qualidade, não bloqueiam.

---

## Findings — stage reconfigure + QA (2026-06-19)

Continuação do lifecycle: `forge reconfigure` (pra habilitar qa) + `forge qa meo-divider` (red-team via qa-conductor).

### Validações positivas
- ✅ `forge reconfigure` dirige o menu multi-axis canônico (category → submenu → confirm) sem mismatch — o gate G4/R4 (`host_is_replaying`) segura a NAVEGAÇÃO.
- ✅ `forge qa` funciona end-to-end: scaffold (sandbox boot + **env-scrub** de vars sensitive não-declaradas + run tree) → dispatch do `agents/qa-conductor.md` → verdict canônico (BLOCK/FLAG/PASS) com findings (que iriam pra `forge evolve`).
- ✅ **Env-scrub é defesa de segurança real funcionando:** detectou 2 vars sensitive no env do pai não-declaradas por card ativo e as dropou no sandbox isolado (nomes mascarados pra não vazar em log de CI). 3-caminhos informativo (ignorar / declarar no card / grant no projeto).

### [P-18] 🐛 Alta — `forge reconfigure` não aplica mutações via loop canônico AI-first
Sequência observada: menu "O que mudar?" → `qa` → `enable` → confirm "ativar?" (ok) → "Aplicar essas mudanças?" (apply-confirm) → re-invoke → o engine emite o guard **"Detectei um draft de reconfigure não aplicado. Retomar?"** (id ≠ apply-confirm) → IntentMismatchError → exit 1, **mudança NÃO aplicada**. Responder o guard "Retomar? sim" volta pro menu INICIAL (não retoma o apply — P-11-like). Deadlock circular. O R4 (`host_is_replaying`) gateou guards de NAVEGAÇÃO do reconfigure mas NÃO cobriu o caminho **apply-confirm × draft-resume**. Net: o "single mutation entrypoint" do forge não aplica mutações via AI-first. **Workaround no piloto:** editar `.claude/forge/forge-config.yaml` direto. Pointer: `engine/reconfigure.py` (apply-confirm + draft-resume guard; estender cobertura de `host_is_replaying` pro apply path).

### [P-19] 🐛 Alta — `forge qa` Phase 0 não popula `snapshot/`
A run tree tem `snapshot/` vazio (só dirs aninhados vazios). O `qa-conductor.md` + contratos dos auditores mandam ler read-only de `snapshot/` pra reprodutibilidade (§5.0). Vazio, os auditores são forçados a ler o working tree VIVO — quebra a garantia de reprodutibilidade do red-team. (Maior bug de `forge qa` no piloto.) Pointer: `engine/qa` Phase 0 (ingest/snapshot).

### [P-20] 🐛 Média — `conductor-handoff.json` sem campos do contrato
O `qa-conductor.md` promete que o handoff contém `snapshot/ paths`, `config_snapshot`, e a lista de auditores ativos (4 core + N extension). O arquivo real tem só `scope`, `run_id`, `root`, `config`. Um auditor seguindo o contrato literal procura campos ausentes. Pointer: writer do handoff em `engine/qa` vs `agents/qa-conductor.md`.

### [P-21 / P-22 / P-23] 🧱 Média/Baixa — ambiguidades no contrato do qa-conductor
- **P-21:** o auditor validator-claim manda "escolher fixture-extension pela linguagem do validator" — mapeia mal quando os gates reais são scripts Python de card (não `.kt`/`.swift` que o contrato antecipa).
- **P-22:** `must_pass` usa nomes de validator sem path (`validate_task_contract.py`); o resolver implícito (cwd/PATH) não é documentado no handoff, e há split `.claude/scripts/` vs `.agents/skills/.../scripts/`.
- **P-23:** degraded-mode (Phase 3 sandbox não roda) não é especificado no contrato — sem isso o synthesizer emitiria `qa-sandbox-results-missing` (high) espúrio.

### [P-24] 🐛 Alta — card canônico `compose-screens` com validators stub declarados como hard gate
`compose-screens/check-no-suppress.py` e `check-screen-layout.py` são declarados `severity: error` (gates duros) no `card.yaml` + citados nos task gates, mas os corpos são stubs "TODO Phase 5" que `return 0` sempre. Um `@Suppress` ou layout Screen/Content quebrado **passa silenciosamente** — "validator mente sobre cobertura". Pointer: `cards/compose-screens/` (check-*.py + severity no card.yaml).

### Verdict do red-team no meo-divider: BLOCK (informativo)
2 critical (P-24 + drift de schema do task-contract: `validate_task_contract.py` exige ~20 campos que os `TASK-000N.yaml` do meo-divider não têm, mas a readiness alegou "4 contratos válidos" — uma das duas fontes está em drift) + 1 high + 4 medium + 4 low. A MAIORIA é infra de validação (stubs Phase-5 cabeados como gates) e drift de schema, não defeito do divider — que ficou coerente e minimal-honesto (seções N/A justificadas). Confirma que o red-team produz findings reais e acionáveis.

### Estado do lifecycle AI-first (final desta campanha)
| Etapa | Status |
|---|---|
| init | ✅ completa (R1) |
| plan | ✅ end-to-end (R4 + conductor) |
| implement | ✅ REAL (Plan Mode; P-17 workaround) |
| reconfigure | ⚠️ navega ok, mas **não aplica** (P-18) |
| qa | ✅ end-to-end (scaffold + conductor + verdict); bugs P-19..P-23 |

Bloqueadores AI-first abertos: **P-17** (implement phase-lock stale), **P-18** (reconfigure apply), **P-19** (qa snapshot). **P-24** (validators stub como gate) é finding de card canônico.
