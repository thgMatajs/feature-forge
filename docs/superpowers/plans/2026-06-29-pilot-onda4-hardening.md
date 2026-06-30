# Onda 4 — Hardening P1 (remediação do piloto MeoBonsai)

> **Plano de execução** (`superpowers:writing-plans`). Aterra a Onda 4 da spec
> `docs/superpowers/specs/2026-06-29-pilot-remediation-design.md` §"Onda 4 —
> Hardening P1". Fecha a fricção IA-first séria e os papercuts de protocolo /
> segurança / visibilidade que sobraram do piloto.
> **Voz:** mentor calmo. **Branch:** `docs/pilot-remediation`.
> **Roda em paralelo** com O1 (correctness) e O2 (gates) — file-disjuntas.
> **Colisão coordenada:** `engine/init.py` é compartilhado com a Onda 3
> (discovery cache). Ver §Footprint & coordenação.

---

## Contexto

O piloto provou que a plumbing IA-first é sólida; a Onda 4 tira os papercuts
que penalizam um host genérico e fecha duas armadilhas de adoção (status cego
ao git, upgrade destrutivo sem preview) e um check morto (version-lock path
mismatch). Cada bug vira uma task isolada com TDD vermelho-antes; os P2 de
polish entram numa única task oportunista.

**Princípio de execução (mesmo da campanha mem):** cada task começa com um
teste de regressão FALHANDO que reproduz o bug, depois o fix mínimo que o faz
passar. Verde antes de pronto: `.venv/bin/pytest` full verde + `forge verify`
sem hard fail + reviewer assinou off. Doc-sync no MESMO commit
(`docs/design/04-pending.md` move o item ABERTO→fechado + CHANGELOG Unreleased).

**Reuso-first (Mandamento #3):** antes de criar helper novo, consulte
`forge graph` + `engine/inventory/` + `.claude/bin/mem find "..."`. Vários
fixes desta onda reusam infra que já existe (ver cada task).

**`.venv/bin/pytest` é canonical** — o system pytest gera falsos negativos
(falta json5 + deps). Toda task roda a lane assim.

---

## Footprint & coordenação (REPORTE pro orquestrador)

Arquivos que esta onda edita (whitelist agregada — fora disto = violação de
scope):

| Arquivo | Task | Região | Colide com |
|---|---|---|---|
| `engine/status.py` | T1 | git reconcile + qa verdict (novos renderers + payload) | — |
| `engine/memory/l1.py` *(se preciso ler qa verdict)* | T1 | helper de leitura do verdict | — (ver nota T1) |
| `engine/host/adapters/claude_code.py` | T2 | `_emit_marker` attrs (~L422) | — |
| `engine/host/adapters/intent_file.py` *(se espelhar)* | T2 | paridade do marker/pending | — (ver nota T2) |
| `engine/upgrade.py` | T3 | `--dry-run` + guard de branch + `run()` argv | — |
| `engine/init.py` | T4 + T6 | **gitignore gen ~L2666-2682** (T4) · **version-lock write ~L2654** (T6, leitura) | **Onda 3** (discovery cache ~L150-204 + step-2) |
| `engine/doctor.py` | T6 | `_check_forge_version_lock` ~L881 (read path) | — |
| `cards/swiftui-screens/templates/swiftui-allowed-files.yaml` | T5 | `ios-build` command ~L59 | — |
| `cards/compose-screens/templates/compose-allowed-files.yaml` | T5 | `validations_suggested` ~L29-47 | — |
| `cards/kotlin-language/agent-contributions/task-writer-additions.md` | T5 | prose de derivação | — |
| `engine/<task-writer / contract>` *(consumo dos cmds)* | T5 | ponto de derivação `gradlew tasks` | — (ver nota T5) |
| `skills/feature-forge/SKILL.md` | T7 | mapa de verbos ~L132-141 | — |
| `engine/undo.py` | T8 | no-op exit code ~L275-289 / caller ~L846 | — |
| `engine/raw.py` | T8 | aviso de escopo rebuild-templates | — |
| `engine/reconfigure.py` | T8 | dashboard só no 1º passo | — |
| `engine/evolve.py` | T8 | SIGPIPE/EOF + `--help` | — |
| `docs/design/04-pending.md` | todas | mover itens ABERTO→fechado | O1/O2/O3 (doc-sync — append/edit por seção; coordenar merge) |
| `CHANGELOG.md` | todas | Unreleased | O1/O2/O3 (doc-sync) |
| `tests/...` | todas | testes de regressão novos | — |

**COORDENAÇÃO CRÍTICA com a Onda 3 (`engine/init.py`):**

- A Onda 3 cacheia discovery no **checkpoint** — região ~L150-204
  (`_serialize_checkpoint`/`_load_checkpoint`) + o step de discovery (~step-2,
  perto de L190 referenciado na spec/catálogo como BUG-2).
- A Onda 4 toca **dois pontos distintos e tardios** do init: a geração do
  `.gitignore` (step-12.6, ~L2666-2682) e o write do version-lock
  (step-12.5, ~L2654, só leitura para confirmar o path — o fix do BUG-B mora
  no doctor).
- **As regiões não se sobrepõem** (steps 2 vs 12.5/12.6, ~2400 linhas de
  distância). Risco real = conflito de merge textual em `init.py` se as duas
  ondas commitarem na mesma branch sem rebase. **Recomendação:** O3 e O4
  sequenciam os commits em `init.py` (quem fechar primeiro empurra; o outro
  rebase antes do seu commit de init.py). Sem trabalho compartilhado — só
  higiene de merge.

**Doc-sync compartilhado:** `04-pending.md` e `CHANGELOG.md` são tocados por
todas as ondas. Editar por seção (cada item tem seu bloco) minimiza conflito;
em colisão, é merge trivial (append/move de linha).

---

## Tasks

Uma task por bug; P2 polish agrupado na T8 oportunista. Ordem sugerida:
T6 (path mismatch, mais barato + alto valor de regressão) → T4 → T1 → T2 →
T3 → T5 → T7 → T8. Sem dependências entre tasks (file-disjuntas internamente,
exceto init.py em T4+T6 — mesmo arquivo, regiões distintas, mesma onda → sem
conflito interno).

---

### TASK 1 — BUG-STATUS-1/2: status cego ao git/qa

**Objetivo (bug):** `forge status` é fiel-ao-forge mas cego-à-realidade: numa
feature commitada reporta `implementing` com os commits do git invisíveis
(BUG-STATUS-1) e não expõe o qa verdict (BLOCK invisível — sem rastro;
BUG-STATUS-2). Gate de aceite da spec: "`forge status` numa feature commitada
reflete os commits do git e o qa verdict (observável no `--json`)".

**ARQUIVOS PERMITIDOS:**
- `engine/status.py` (novos renderers + campos no `_status_payload`)
- `engine/memory/l1.py` — SOMENTE se a leitura do qa verdict exigir um helper
  novo de L1 (ver reuso); preferir reusar `read_l1_status`/`read_history`.
- `tests/unit/test_commands_status.py` + `tests/unit/test_status_json.py`
  (regressão)
- `docs/design/04-pending.md`, `CHANGELOG.md` (doc-sync)

**Reuso-first:** `engine/status.py` já importa `read_history`,
`read_l1_status`, `list_active_features` de `engine.memory.l1`. O qa verdict,
se persistido, vem do history/L1 — **NÃO** crie um leitor de qa do zero;
descubra onde o verdict é gravado: `.claude/bin/mem find "qa verdict
persistência L1 status"` + `grep -rn "verdict\|BLOCK" engine/qa*.py
engine/memory/l1.py`. Para o git: reuse um helper de subprocess git já
existente se houver (`grep -rn "rev-parse\|git log\|subprocess.*git"
engine/`); se não houver, o leitor git é read-only e mínimo (rev-list count
HEAD vs base, ou `git log --oneline` no dir da feature) — **read-only, nunca
muta git**.

**TDD (vermelho concreto — escreva ANTES do fix):**
- `test_status_json_reflects_git_commits`: monta um repo git temp com uma
  feature em estado `implementing` + N commits que tocam o dir da feature;
  `forge status --json` hoje NÃO mostra os commits → asserção `payload[...]
  ["git"]["feature-commits"] >= N` FALHA antes do fix.
- `test_status_json_exposes_qa_verdict`: persiste um qa verdict `BLOCK` no
  L1/history; `forge status --json` hoje omite → asserção
  `payload[...]["qa-verdict"] == "BLOCK"` FALHA antes do fix.
- (opcional) `test_status_flags_git_drift`: feature `implementing` com commits
  → status sinaliza descompasso (campo `git-drift: true` ou nota no render).

**Critério de sucesso:** os dois testes verdes; `forge status --json` numa
feature commitada expõe `feature-commits` + `qa-verdict`; render humano ganha
uma linha de reconciliação git + o verdict; sem mutar git/estado (status
permanece pure-read — confirme que nenhum write entrou). Lane full verde.

**Anti-padrões / escopo:** NÃO transformar status em comando que escreve
(quebra o contrato pure-read da L12 do módulo). NÃO reconciliar/avançar a DAG
(isso é Tema 7, FECHADO — regressão a evitar). NÃO inventar persistência de qa
nova se o verdict ainda não é gravado em lugar nenhum — se for o caso, status
lê "qa: sem registro" honesto e o BLOCKED de persistência vira nota pro
orquestrador (3-caminhos), não trabalho silencioso aqui.

---

### TASK 2 — BUG-G2/MEM-4: marker sem `response-schema-version`

**Objetivo (bug):** o `<FORGE_INTENT>` em
`engine/host/adapters/claude_code.py:422` (`_emit_marker`) não anuncia o
`response-schema-version` que a resposta exige (`"schema-version":1`); um host
ingênuo omite e toma exit 1 silencioso (BUG-G2 em graph, BUG-MEM-4 em memory).
Gate de aceite: "um host que omite `response-schema-version` é orientado pelo
marker (ou aceito como default) — não toma exit 1 silencioso".

**ARQUIVOS PERMITIDOS:**
- `engine/host/adapters/claude_code.py` (atributo no `attrs` dict, ~L422-430)
- `engine/host/adapters/intent_file.py` — SOMENTE se o pending file precisar
  espelhar o requisito para paridade de adapters (ver nota).
- `engine/<leitor de response>` — SOMENTE se a abordagem escolhida for "aceitar
  ausência como default 1" no parser (ver decisão abaixo).
- `tests/unit/test_host_claude_code.py` (regressão)
- `docs/design/04-pending.md`, `CHANGELOG.md`; `docs/schemas/intent-protocol.md`
  + `skills/feature-forge/SKILL.md` se o atributo virar contrato documentado
  (doc-sync) — **coordene a edição do SKILL.md com a T7** (mesmo arquivo).

**Decisão de design (a spec oferece dois caminhos — escolher 1, registrar no
commit body):**
- **(A) anunciar no marker** — adicionar `"response-schema-version": "1"` ao
  `attrs` dict do `_emit_marker` (auto-descritivo; o host lê e sabe o que
  devolver). Preferível: alinha com o veredito "o intent deveria ser
  auto-descritivo" (Tema 4).
- **(B) aceitar ausência como default 1** no leitor de response (tolerante).
  Pode combinar com (A) — anunciar E tolerar.

Recomendação: **(A) + (B) leve** — anunciar o atributo no marker E o parser de
response tratar ausência de `schema-version` como `1` com aviso mentor-calmo,
não exit 1 hard.

**Reuso-first:** o `attrs` dict já é a fonte canônica dos atributos do marker;
adicionar uma chave segue o padrão exato dos opcionais (`validator-hint` etc.).
NÃO crie um caminho de emissão paralelo. `.claude/bin/mem find "intent
protocol schema-version marker contrato"`.

**TDD (vermelho concreto):**
- `test_marker_announces_response_schema_version`: parseia o marker emitido
  via `ElementTree.fromstring` e asserta
  `attrib["response-schema-version"] == "1"` → FALHA antes (atributo ausente).
- `test_response_missing_schema_version_defaults_to_1` (se escolher B):
  response sem `schema-version` é aceita com default 1 (não exit 1) → FALHA
  antes se hoje rejeita.

**Critério de sucesso:** o marker round-trip-a por `ElementTree` com o novo
atributo; o teste de paridade dos adapters (se houver `test_host_adapter_abc`)
continua verde; o host que omitia schema-version não toma mais exit 1
silencioso. Lane full verde.

**Anti-padrões / escopo:** NÃO mudar o shape dos atributos existentes (hosts
que parseiam por presença quebram). NÃO renomear `intent-id`/`options`/etc.
Manter o atributo opcional-tolerante (presença não pode virar hard-require que
quebre hosts antigos).

---

### TASK 3 — BUG-UPGRADE-1: upgrade destrutivo sem preview

**Objetivo (bug):** `engine/upgrade.py` faz `git checkout --detach <tag>` +
`pip install` no FORGE_HOME sem `--dry-run` nem guard de branch. Perigoso numa
branch de dev (tiraria o HEAD silenciosamente). Gate de aceite: "`forge
upgrade --dry-run` faz preview sem mutar git; sem `--dry-run` numa branch
não-release, o guard pausa antes do checkout".

**ARQUIVOS PERMITIDOS:**
- `engine/upgrade.py` (`run_upgrade` + `run` adapter + helpers de dry-run/guard)
- `tests/e2e/test_forge_upgrade.py` (regressão — já existe)
- `docs/design/04-pending.md`, `CHANGELOG.md`

**Reuso-first:** os helpers testáveis já existem
(`_git_current_sha`, `_git_fetch`, `_latest_local_tag`, `_tag_sha`,
`_git_checkout`). O `--dry-run` reusa os 5 primeiros (read-only) e PULA o
checkout/pip. O guard de branch reusa `_git_current_sha` + um novo
`_current_branch(home)` (read-only, `git rev-parse --abbrev-ref HEAD` ou
`symbolic-ref`). NÃO duplique a sequência de descoberta de tag.

**Detached HEAD nuance:** pós-install o repo fica em detached HEAD numa release
tag (estado canônico — L9 do módulo). O guard deve pausar quando o HEAD está
numa **branch nomeada não-release** (ex.: `fix/...`, `feat/...`,
`docs/...`), NÃO quando já está em detached numa tag v*. Critério: branch
nomeada ≠ `(HEAD detached)` E não numa tag v* → guard.

**TDD (vermelho concreto):**
- `test_upgrade_dry_run_does_not_mutate_git`: monta um repo git temp com tags;
  `run_upgrade(dry_run=True)` mostra o que faria mas o SHA do HEAD permanece
  idêntico antes/depois → hoje não existe `dry_run`, asserção FALHA (a flag
  nem é aceita).
- `test_upgrade_guards_named_dev_branch`: repo temp com HEAD numa branch
  `fix/algo` + tag nova; `run_upgrade()` sem dry-run NÃO faz checkout (pausa
  pelo guard — exit dedicado ou intent) → hoje prossegue pro checkout,
  asserção FALHA.

**Critério de sucesso:** `forge upgrade --dry-run` preview sem mutação (SHA
intacto); numa branch nomeada não-release o guard pausa antes do
`_git_checkout`; numa tag/detached o fluxo normal segue; rollback existente
intacto. Lane full verde (incluindo a e2e existente, que NÃO pode regredir).

**Anti-padrões / escopo:** NÃO mexer no rollback automático (já existe e
funciona — regressão a evitar). NÃO mutar o git do projeto consumidor (upgrade
opera só no FORGE_HOME). O guard é **pausa**, não bloqueio mudo: mensagem
mentor-calmo com 3-caminhos (continuar mesmo assim / abortar / como sair da
branch primeiro) — alinhe com a disciplina §1.

---

### TASK 4 — BUG-4/MEM-5: `.gitignore` gerado pelo init incompleto

**Objetivo (bug):** o `.gitignore` gerado no step-12.6
(`engine/init.py:2666-2682`) cobre só `state/` + checkpoints; faltam os
artefatos derivados `graph.db`, `cards/`, `memory/`, `locks/`,
`.memory-cli-checkpoint.yaml`. Um `git add .` commita 2.3 MB de graph.db +
snapshots. Gate de aceite: "cobrir todos os artefatos derivados do init".

**SCOUT confirmado:** o `.gitignore` vive em `forge_dir(project_root)` =
`.claude/forge/.gitignore` (sub-namespace, Task 0.10). Os artefatos a cobrir
vivem em paths diferentes: `graph.db` em `.claude/` (`claude_dir`), `cards/`
em `.claude/cards/`, `memory/` em `.claude/memory/`, `.memory-cli-checkpoint
.yaml` no top-level de `.claude/`. **Decisão de escopo:** um `.gitignore` em
`.claude/forge/` NÃO cobre irmãos fora de `forge/` por padrões relativos.
Confirme onde cada artefato derivado realmente cai
(`grep -rn "graph_db_path\|cards_dir\|memory_dir\|memory-cli-checkpoint"
engine/utils/paths.py engine/init.py`) e escolha:
- **(A)** escrever/anexar também um `.gitignore` em `.claude/` cobrindo os
  irmãos derivados (graph.db, cards/, memory/, locks/,
  `.memory-cli-checkpoint.yaml`), append-only e não-destrutivo se já existir;
- **(B)** consolidar os artefatos derivados sob `.claude/forge/` (escopo maior,
  toca outros sites — provável BLOCKED 3-caminhos, NÃO fazer aqui).

Recomendação: **(A)** — aditivo, contido, fecha o bug exatamente. Registrar a
decisão no commit body.

**ARQUIVOS PERMITIDOS:**
- `engine/init.py` (step-12.6 — estender o `gitignore_content` do `forge/` +,
  se (A), gerar/anexar o `.gitignore` de `.claude/` append-only)
- `tests/integration/test_init_*.py` (regressão — escolher o mais próximo do
  step de gitignore; ou novo `tests/unit/test_init_gitignore.py`)
- `docs/design/04-pending.md`, `CHANGELOG.md`; `docs/design/05-filesystem-
  layout.md` se o layout documentado mudar (doc-sync)

**Reuso-first:** os paths canônicos já têm helpers em `engine/utils/paths.py`
(`graph_db_path`, `cards_dir`, `memory_dir`, `claude_dir`) — derive os nomes a
ignorar DELES, não hardcode strings que driftam do layout real. Para append
não-destrutivo, `.claude/bin/mem find "merge não-destrutivo append-only
settings init"` (mesmo padrão de `merge_settings_json`).

**TDD (vermelho concreto):**
- `test_init_gitignore_covers_derived_artifacts`: roda o step de gitignore (ou
  o init em fixture brownfield), depois asserta que `git check-ignore` (ou
  parse do conteúdo) cobre `graph.db`, `cards/`, `memory/`, `locks/`,
  `.memory-cli-checkpoint.yaml` → hoje FALHA (só cobre `state/` + checkpoints).
- (se (A)) `test_init_gitignore_append_non_destructive`: `.claude/.gitignore`
  pré-existente com linhas do usuário é preservado (append, 0 remoções).

**Critério de sucesso:** pós-init, `git status` num projeto limpo NÃO lista
graph.db nem os snapshots derivados; o `.gitignore` versiona só
`forge-config.yaml` (e o que deve ser versionado); append-only confirmado.
Lane full verde.

**Anti-padrões / escopo:** NÃO mover artefatos de lugar (isso é (B), escopo
maior). NÃO sobrescrever um `.gitignore` do usuário (append-only — Mandamento
de não-destrutividade do init). NÃO tocar a região de checkpoint/discovery do
init (zona da Onda 3).

---

### TASK 5 — BUG-IMPL-2: build commands hardcoded nos cards

**Objetivo (bug):** comandos de build hardcoded nos templates de card:
`swiftui-allowed-files.yaml:59` (`run-ios-simulator.sh --build-only`) e a
suíte android/kotlin que assume `testDebugUnitTest` (KMP usa
`testAndroidHostTest`). Gate de aceite (Tema 7): derivar do projeto (ler
`gradlew tasks`) em vez de assumir.

**SCOUT confirmado:**
- `swiftui-allowed-files.yaml:58-59` tem `ios-build` →
  `./scripts/run-ios-simulator.sh --build-only` hardcoded.
- `compose-allowed-files.yaml:28-47` tem `validations_suggested` /
  `gates_suggested` com `:composeApp:assembleDebug` etc. hardcoded.
- `kotlin-language/agent-contributions/task-writer-additions.md` JÁ documenta
  corretamente `testAndroidHostTest` (não `testDebugUnitTest`) na prose
  (L49-52) — o problema é que os COMANDOS efetivos nos YAMLs/contrato não
  derivam do projeto.

**ARQUIVOS PERMITIDOS:**
- `cards/swiftui-screens/templates/swiftui-allowed-files.yaml` (build command)
- `cards/compose-screens/templates/compose-allowed-files.yaml`
  (`validations_suggested` / `gates_suggested`)
- `cards/kotlin-language/agent-contributions/task-writer-additions.md` (prose
  de derivação — reforçar "derive de `gradlew tasks`/inventory, não assuma")
- `engine/<task-writer / contract builder>` — o ponto que CONSOME esses
  templates e monta o contrato de task. **SCOUT obrigatório antes do fix:**
  `grep -rn "validations_suggested\|swiftui_validations\|gradlew tasks\|
  task-contract" engine/` pra achar onde os comandos viram contrato e onde
  derivar do projeto. Whitelist exata desse arquivo a confirmar no scout.
- `tests/...` (regressão — ver TDD)
- `docs/design/04-pending.md`, `CHANGELOG.md`

**Reuso-first:** o inventory já detecta o stack (gradle catalogs — há
`_check_gradle_catalogs` no doctor). Veja se `engine/inventory/` já lê
`gradlew tasks` ou os módulos gradle; derive os build commands DAÍ.
`.claude/bin/mem find "inventory gradle tasks derivação build command projeto"`.
Se a derivação ainda não existe, o caminho mínimo é: o task-writer lê o módulo
real do inventory e substitui o placeholder do template em vez de emitir o
literal hardcoded.

**TDD (vermelho concreto):**
- `test_kmp_shared_task_uses_android_host_test`: dado um inventory KMP, o
  contrato de task de módulo shared usa `testAndroidHostTest` (não
  `testDebugUnitTest`) → hoje FALHA se o literal hardcoded vaza.
- `test_ios_build_command_derived_or_parameterized`: o build command iOS não é
  o literal `run-ios-simulator.sh --build-only` cego — vem do projeto ou é
  parametrizável → FALHA antes.

**Critério de sucesso:** os comandos de build no contrato de task gerado
refletem o projeto real (módulo/task names derivados do inventory), não os
literais hardcoded; testes verdes. Lane full verde.

**Anti-padrões / escopo:** Esta task tem maior incerteza de footprint (o ponto
de derivação no engine é a confirmar no scout). **Se o scout revelar que
derivar de `gradlew tasks` exige rodar gradle em tempo de plan/implement (custo
+ rede + dependência externa) ou tocar >5 arquivos** → BLOCKED com 3-caminhos
(A: parametrizar o template + deixar o host preencher do inventory existente,
barato; B: derivação completa via `gradlew tasks`, escopo de onda própria;
C: defer pro mem Fase 2). Recomendação default = **A** (parametrizar +
inventory-derived, sem invocar gradle), que fecha o gate sem custo de runtime.

---

### TASK 6 — BUG-B: version-lock path mismatch (check morto)

**Objetivo (bug):** init grava o version-lock em `.claude/forge/`
(`engine/init.py:2654`, `forge_dir(project_root)`) mas o doctor LÊ em
`.claude/` (`engine/doctor.py:881`, `claude_dir(project_root)`) → o check cai
sempre no SKIP "não criado ainda (gerenciado por forge init)" e a detecção
lock-vs-binário está morta. Gate de aceite: "round-trip init→doctor lê o
version-lock no mesmo path (check vivo)".

**SCOUT CONFIRMADO (os dois paths divergem):**
- `engine/init.py:2654` → `forge_dir(project_root) / "forge-version-lock.yaml"`
  = `.claude/forge/forge-version-lock.yaml`
- `engine/doctor.py:881` → `claude_dir(project_root) / "forge-version-lock
  .yaml"` = `.claude/forge-version-lock.yaml`
- `paths.py`: `forge_dir` = `.claude/forge` (L254-256); `claude_dir` =
  `.claude` (L106-108). Divergência confirmada de ponta a ponta.

**Direção de fix:** alinhar o doctor ao path canônico do init —
`forge_dir(project_root)` (o sub-namespace `.claude/forge/` é o canônico per
spec §2; init é a fonte). Trocar `claude_dir` → `forge_dir` em
`_check_forge_version_lock` (L881) + garantir o import de `forge_dir` em
`doctor.py`.

**ARQUIVOS PERMITIDOS:**
- `engine/doctor.py` (`_check_forge_version_lock` L881 — read path + import)
- `engine/init.py` — SOMENTE leitura/confirmação do write path (NÃO mexer no
  write; o init já está canônico). Listado por precaução; o fix mora no doctor.
- `tests/unit/test_doctor_*.py` — preferir um round-trip
  (`test_init_doctor_version_lock_roundtrip.py` novo ou estender o existente)
- `docs/design/04-pending.md`, `CHANGELOG.md`

**Reuso-first:** `forge_dir` já existe em `engine/utils/paths.py` (L254) e já é
usado por init. NÃO crie path helper novo — importe o canônico.

**TDD (vermelho concreto — round-trip):**
- `test_init_doctor_version_lock_roundtrip`: roda o write do version-lock do
  init (ou o step) num project_root temp, depois roda
  `_check_forge_version_lock(project_root)` e asserta que o check é `OK`
  (forge-version == binary), NÃO `SKIP "não criado ainda"` → hoje FALHA porque
  o doctor lê no path errado e nunca acha o arquivo que o init criou.

**Critério de sucesso:** após `forge init`, `forge doctor` reporta o
version-lock como check VIVO (OK quando casam, FAIL quando driftam) — nunca
mais o SKIP falso "não criado ainda" com o arquivo existindo. Round-trip verde.
Lane full verde.

**Anti-padrões / escopo:** NÃO mover o write do init (já canônico — mexer nele
arrisca regredir Task 0.10 do sub-namespace). NÃO "consertar" também o BUG-A
(doctor schema-version) — está FECHADO em main, regressão a evitar. Fix
cirúrgico: uma linha de path + import no doctor.

---

### TASK 7 — BUG-QA-4: SKILL.md não cobre todos os verbos

**Objetivo (bug):** o mapa de verbos do `skills/feature-forge/SKILL.md`
(L132-141) cobre só `init/plan/implement/verify/status`; não cobre
`qa/verify*/memory/reconfigure/upgrade/undo` (`verify` está listado mas qa/
evolve/memory/reconfigure/upgrade/undo não). Um host genérico não dirige
IA-first esses verbos pelos artefatos instalados. Gate de aceite (Tema 4):
expandir o mapa de verbos do SKILL.md instalado.

**SCOUT confirmado:** a tabela "Workflow — mapa de verbos" (L134-141) tem 5
linhas: init/plan/implement/verify/status. Faltam qa, evolve, memory,
reconfigure, upgrade, undo, graph, doctor, raw.

**ARQUIVOS PERMITIDOS:**
- `skills/feature-forge/SKILL.md` (estender a tabela de verbos + breve nota
  por verbo) — **coordene com a T2** (mesmo arquivo, se T2 documentar o
  `response-schema-version` aqui; sequenciar: T2 primeiro OU mesclar as duas
  edições do SKILL.md numa só — ver §Footprint).
- `tests/...` — se houver teste que valida cobertura do SKILL.md instalado
  (`grep -rn "SKILL\|verbos\|verb" tests/`); senão, um teste leve de presença.
- `docs/design/04-pending.md`, `CHANGELOG.md`

**Reuso-first:** a lista canônica de verbos vem do registry de comandos
(`engine/cli.py` COMMANDS). Derive o mapa DELE pra não driftar
(`grep -n "COMMANDS\|register" engine/cli.py`). NÃO invente verbos que não
existem; NÃO documente o conductor inline (ele é lido do FORGE_HOME — manter o
ponteiro, como a tabela já faz pro planning-conductor).

**TDD (vermelho concreto):**
- `test_skill_md_covers_all_user_verbs`: parseia a tabela de verbos do
  `skills/feature-forge/SKILL.md` e asserta que cada verbo IA-first dirigível
  (qa, evolve, memory, reconfigure, upgrade, undo, graph, doctor) aparece →
  hoje FALHA (só 5 verbos). Cross-check contra o COMMANDS registry pra a lista
  não driftar.

**Critério de sucesso:** a tabela de verbos cobre todos os comandos
dirigíveis; cada linha diz o que o verbo dirige (mentor-calmo, conciso); o
teste de cobertura verde. Lane full verde.

**Anti-padrões / escopo:** NÃO reescrever o protocolo do intent loop (está
correto). NÃO instalar prompts do conductor no projeto (é escopo maior, BUG-QA-4
tinha duas partes — a parte "instalar conductor" é defer/onda-própria se grande;
aqui foca o mapa de verbos, que é o gate de aceite enunciado). Se o reviewer
achar que "instalar conductor" é inseparável → 3-caminhos pro orquestrador.

---

### TASK 8 — P2 polish (oportunista, agrupada)

**Objetivo:** dobrar nos pontos baratos enquanto já se está perto dos arquivos.
Itens 18-21 do report. Cada um é cirúrgico; agrupados numa task porque isolados
desperdiçam contexto.

**Itens:**
1. **BUG-UNDO-1** — `engine/undo.py`: no-op de `last`/`reconfigure` retorna
   exit 1 ("nada a reverter") quando exit 0 seria a semântica correta de no-op
   legítimo. SCOUT: `_undo_reconfigure` (L275-282) retorna `False` quando não
   há `.bak`; o caller (~L846) faz `return 0 if ok else 1`. Fix: distinguir
   "no-op legítimo" (sem `.bak` = nada a fazer → exit 0) de "erro real"
   (exit 1). Avaliar o caller pra não regredir os caminhos de erro genuíno.
2. **BUG-RAW-1** — `engine/raw.py`: `rebuild-templates` muta FORGE_HOME sem
   aviso de escopo. Fix: aviso mentor-calmo de que opera no FORGE_HOME
   (não no projeto) antes de mutar — alinhar com o guard de escopo do upgrade
   (T3, mesma filosofia de "comando que muta fora do projeto-alvo avisa").
3. **BUG-EVOLVE-1 + BUG-EVOLVE-2** — `engine/evolve.py`: tratar SIGPIPE/EOF no
   loop de render (hoje trava/exit 143 se stdout fecha cedo — `< /dev/null |
   head`); e `--help` cai no fluxo normal em vez de imprimir uso. Fix:
   `except BrokenPipeError` no loop de render + reconhecer `--help`/`-h` no
   `run()` (~L380).
4. **BUG-RECONF-1** — `engine/reconfigure.py`: dashboard re-impresso a cada
   passo do loop multi-passo (ruído no transcript IA-first). Fix: imprimir só
   no 1º passo do loop (~`run` L207).
5. **BUG-IMPL-4** (se barato e no caminho) — `forge implement --help`
   interpreta `--help` como slug inválido. Fix: reconhecer `--help` antes de
   tratar argv[0] como slug. Incluir SOMENTE se não expandir o footprint além
   de `engine/implement.py` no parsing de argv.

**ARQUIVOS PERMITIDOS:**
- `engine/undo.py`, `engine/raw.py`, `engine/evolve.py`,
  `engine/reconfigure.py`, `engine/implement.py` (só o argv `--help`)
- `tests/unit/test_commands_undo.py`, `tests/...` por item
- `docs/design/04-pending.md`, `CHANGELOG.md`

**Reuso-first:** o padrão `--help`/`-h` no `run()` já existe em
`engine/upgrade.py` (L268-278) — copie a FORMA (não o texto). O aviso de
escopo do raw espelha o do upgrade guard (T3). Para SIGPIPE,
`.claude/bin/mem find "SIGPIPE BrokenPipe loop de render stdout fecha"`.

**TDD (vermelho concreto — um por item):**
- `test_undo_noop_exits_zero`: `undo last`/`reconfigure` sem `.bak` retorna
  exit 0 (no-op legítimo) → hoje FALHA (exit 1).
- `test_evolve_help_recognized`: `forge evolve --help` exit 0 + texto de uso →
  hoje FALHA (cai no fluxo normal).
- `test_evolve_handles_broken_pipe`: render com stdout fechado cedo não trava
  nem sai 143 → FALHA antes (se reproduzível em teste; senão, asserção sobre o
  `except BrokenPipeError` presente + um smoke).
- `test_raw_rebuild_templates_warns_scope`: o output avisa que opera no
  FORGE_HOME → FALHA antes.
- (reconfigure) asserção de que o dashboard sai 1× no loop multi-passo.

**Critério de sucesso:** cada item com seu teste verde; nenhum regride o
caminho de erro genuíno (esp. undo exit 1 em erro REAL permanece). Lane full
verde.

**Anti-padrões / escopo:** NÃO transformar "polish" em refactor. Cada fix é
cirúrgico (1 condição, 1 except, 1 guard de print). Se QUALQUER item revelar
escopo > poucas linhas → tira do bundle e vira nota pro orquestrador (NÃO
forçar no commit oportunista). NÃO incluir BUG-IMPL-4 se ele tocar o parsing
de slug de forma arriscada.

---

## Gate de aceite consolidado (Onda 4 — verde antes de pronto)

- `.venv/bin/pytest` lane completa verde (count não regride sem justificativa
  no commit body).
- `forge verify` sem hard fail.
- `gsd-code-reviewer` (zero-tolerância, 11 dimensões + verdict + 3-caminhos por
  finding) assinou off — sem high/critical não-acknowledged.
- **BUG-STATUS:** `forge status --json` numa feature commitada reflete os
  commits do git + o qa verdict.
- **BUG-G2:** host que omite `response-schema-version` é orientado (ou aceito
  como default) — sem exit 1 silencioso.
- **BUG-UPGRADE-1:** `forge upgrade --dry-run` preview sem mutar git; sem
  dry-run numa branch não-release o guard pausa antes do checkout.
- **BUG-4/MEM-5:** pós-init `git status` não lista graph.db nem snapshots
  derivados; `.gitignore` cobre todos os artefatos derivados.
- **BUG-IMPL-2:** build commands no contrato derivam do projeto (não literais
  hardcoded); KMP shared usa `testAndroidHostTest`.
- **BUG-B:** round-trip init→doctor lê o version-lock no MESMO path (check
  vivo, nunca SKIP falso).
- **BUG-QA-4:** SKILL.md cobre todos os verbos dirigíveis.
- **Doc-sync:** `docs/design/04-pending.md` move os 8 itens da onda
  ABERTO→fechado + CHANGELOG Unreleased, no MESMO commit do fix de cada item.

---

## Disciplinas (valem em toda task)

- **TDD (Mandamento #2):** vermelho-antes obrigatório (cada task enuncia o
  teste que FALHA antes do fix).
- **Reuso (Mandamento #3):** consultar graph/inventory/mem antes de criar
  helper; vários fixes reusam infra existente (helpers de upgrade, paths
  canônicos, `--help` do upgrade, attrs do marker).
- **Escopo (Mandamento #4):** cada task edita só sua whitelist; os FECHADOS
  (Tema 7, BUG-A, BUG-MEM, BUG-1) são regressão a evitar, não trabalho a
  refazer. Sair da whitelist = violação → revert + re-dispatch.
- **Voz (Mandamento #5):** mensagens de gate/guard/aviso em mentor-calmo, com
  3-caminhos onde há gate (upgrade guard, BLOCKED de scope).
- **Doc-sync (Mandamento #6):** `04-pending.md` + CHANGELOG no MESMO commit.

## BLOCKED candidates (3-caminhos pro orquestrador, se aparecerem)

- **T1:** se o qa verdict ainda NÃO é persistido em lugar nenhum → A: status
  lê "qa: sem registro" honesto / B: adicionar a persistência (escopo Tema 7,
  fechado — cuidado) / C: defer.
- **T5:** se derivar build commands exigir rodar `gradlew tasks` (custo/rede)
  ou >5 arquivos → A: parametrizar + inventory-derived (default) / B: derivação
  completa em onda própria / C: defer mem Fase 2.
- **T7:** se "instalar prompts do conductor" for julgado inseparável do mapa de
  verbos → A: só o mapa (gate de aceite) / B: incluir instalação do conductor
  (escopo maior) / C: split.
