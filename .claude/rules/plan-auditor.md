# Plan Auditor — prompt template

Prompt determinístico que `gsd-code-reviewer` recebe ao auditar planos
pós-`superpowers:writing-plans`. Voz: mentor calmo. Output:
`PLAN-REVIEW.md` em `.planning/plan-reviews/<plan-slug>-review-r<N>.md`.

## Invocação canônica

Orquestrador dispatcha após writing-plans terminal-state (antes do
"Execution Handoff" do SKILL.md) com:

```
Agent[gsd-code-reviewer] prompt:
  CONTEXTO: auditoria pós-plano de feature-forge. Leia o arquivo inteiro
  `.claude/rules/plan-auditor.md` e aplique os 12 checks ao plano.

  INPUTS:
    - Plan: docs/superpowers/plans/<plan-slug>.md
    - Spec: docs/superpowers/specs/<spec-slug>.md
    - Rodada: <N> de 3

  OUTPUT: .planning/plan-reviews/<plan-slug>-review-r<N>.md
```

## Voz

Mentor calmo. Firme em findings, didático no rationale. PT neutro. Sem
emoji decorativo (exceto ✅⏭️🤔 do template 3-caminhos canônico do
projeto). Sem voz corporativa, sem hedging ("vou tentar", "considere",
"talvez"). Compromete-se ou redireciona — não suaviza.

**Severity é determinística:** veja §"Severity calibration" abaixo pra
defaults canônicos de detection finding. Reviewer não improvisa "esse
caso é cosmético" pra detection issues — segue a calibração explícita.

## Severity calibration — detection findings

**Default automático:** findings que envolvem **detection failures**
(friendly errors, validation checks, gate bypasses, mandamento
enforcement, state assertions) recebem severity **mínimo HIGH** — nunca
Low ou Medium — INDEPENDENTE de quão cosmético o sintoma pareça.

**Critérios pra trigger desta calibração:**

1. **Friendly error mente.** Função que deveria emitir mensagem ao
   usuário falha silenciosamente em condição esperada (ex.: `_check_*`
   retorna `None` em vez de erro quando state é inválido).
2. **Mandamento bypass.** Comportamento que permite contornar gate
   estabelecido (especialmente pre-commit hard-block do Mandamento #1,
   `forge verify` cascade, hooks de doc-sync).
3. **State assertion frouxa.** Check aceita partially-broken state como
   válido (ex.: symlink existe mas aponta target ausente; DB existe mas
   schema desatualizado; config presente mas required field NULL).
4. **Detection assimétrica.** Função detecta caso A (claramente errado)
   mas não detecta caso B (igualmente errado, mas que requer 1+ check
   adicional). Cobertura parcial = severity full.

**Severity upgrade quando trigger bate:**

- Severity natural Low → **High**
- Severity natural Medium → **High**
- Se afeta Mandamento numerado (1-6) DIRETAMENTE → **Critical**
- Se afeta security boundary OR data integrity → **Critical**

**Override permitido:** mantenedor pode rebaixar via override inline
no plano (`<!-- audit-override: H-XXX -- justificativa concreta -->`)
documentando POR QUE o caso real é menos severo do que a regra sugere.
Override frívolo (sem rationale acionável) é re-promovido em re-audit.

**Origem operacional:** sessão 2026-06-15, v1.3.0 graph-ia-evolution.
`_check_bootstrap_state` aceitar broken symlinks foi classificado **Low**
em extension-audit (L-EXT-001) por parecer "edge case minor". Code-review
pós-impl re-classificou **Critical** (C-004) porque o bypass do friendly
error abre brecha pro hard-block do Mandamento #1 ser pulado silenciosamente.
Esta regra evita recorrência: detection bugs sobem de severity por padrão.

## Os 12 checks

### Critical (bloqueia execution-handoff)

#### C1. Locked decision ceremony (Mandamento #1)

**Trigger:** plano edita `docs/design/01-decisions.md` em qualquer task.

**Detecção:**
1. Procure tasks com `01-decisions.md` em "**Files:**" ou "Modify:".
2. Se encontrado, busque em todas as tasks: existe task que adiciona
   entrada em `CHANGELOG.md` contendo o texto literal "Revisita decisão N"
   (substituindo N pelo número)?
3. Se encontrado, busque: o commit message especificado em alguma task
   contém "Revisita decisão N"?
4. Confirme que N no texto encontrado é um número inteiro real, não o
   literal "N" do template. Texto "Revisita decisão N" sem substituição
   numérica = falha da condição 2 (efetivamente template não
   instanciado).

**Falha:** alguma das 3 condições não satisfeita.

**Por que importa:** o pre-commit hard-block
(`.claude/hooks/pre-commit-feature-forge.sh`) vai bloquear depois.
Retrabalho cascateado.

#### C2. Spec coverage

**Trigger:** sempre.

**Detecção:**
1. Localize spec referenciado no header do plano (campo **Spec:** ou
   prosa equivalente).
2. Se spec path não existe no filesystem → falha.
3. Pra cada seção/requisito do spec, identifique pelo menos uma task no
   plano que implementa.

**Falha:** spec ausente OU requisito sem task correspondente.

**Por que importa:** sem cobertura completa do spec, o plano não entrega
o contrato aprovado.

### High (warn, orquestrador decide)

#### H1. Load-bearing files sem justificativa (Mandamento #4)

**Trigger:** task toca arquivo em load-bearing whitelist.

**Whitelist (de `.claude/rules/scope.md`):**
- `docs/design/00-vision.md`
- `docs/design/01-decisions.md` (já tratado em C1)
- `docs/design/05-filesystem-layout.md`
- `docs/design/06-command-surface.md`
- `docs/design/07-discipline.md`
- `docs/schemas/**`
- `presets/**`
- `cards/**`
- `CLAUDE.md`
- `.claude/rules/**`

**Detecção:** pra cada task tocando arquivo load-bearing, busque na
prose da task palavras-chave de justificativa: "porque", "necessário",
"alinha com", "revisita", "consequência de", "mandamento", "decisão N",
"escopo da tarefa". Se nenhuma justificativa textual → finding.

**Exceção chicken-and-egg:** quando a task **cria** o próprio arquivo
que figura no Goal do plano (ex.: plano cuja meta É entregar
`.claude/rules/X.md`), a justificativa textual pode estar no §Goal ou
§Architecture do plano em vez de na prose da task. Nesse caso, aceitar
sem finding — a intenção é canônica pelo Goal.

#### H2. Doc-sync coverage (Mandamento #6)

**Trigger:** plano toca diretórios de código vivo: `engine/`,
`validators/`, `hooks/`, `templates/`, `cards/`, `presets/`,
`docs/schemas/`, `.claude/rules/**`.

**Detecção:**
1. Liste tasks que tocam esses diretórios.
2. Verifique se existe task explícita atualizando `CHANGELOG.md`.
3. Verifique se existe task atualizando
   `docs/design/08-session-handoff.md`.
4. Se mudança envolve nova stat (test count, validator count, card count,
   template count, LOC), verifique task atualizando `README.md`.

**Falha:** qualquer dos 3 ausente quando aplicável.

#### H3. Reuse-first ignorado (Mandamento #3)

**Trigger:** plano cria helper/função/validator/template/card novo.

**Detecção:**
1. Procure tasks com "Create:" em `engine/`, `validators/`, `templates/`,
   `cards/`.
2. Pra cada criação, busque no plano (qualquer task, qualquer step):
   menção a `forge graph` (queries Q11-Q17) OU `engine/inventory/` OU
   grep de precedente OU justificativa "near-duplicate analisado" OU
   "não existe equivalente em".

**Falha:** criação sem evidência de consulta a reuse intelligence.

#### H4. Testing gates (Mandamento #2)

**Trigger:** plano implementa feature ou fix em `engine/` ou
`validators/`.

**Detecção:**
1. Determine tipo: feature (Create em engine/validators), bugfix (Modify
   com test de regressão), refactor (no-behavior contract explícito).
2. Pra feature/bugfix:
   - Existe step "Write the failing test" ANTES de step "implement"?
   - Existe step "Run: pytest <path>" com path concreto?
3. Pra refactor: existe step rodando
   `validators/check_no_behavior_change.py` ou equivalente?

**Falha:** TDD shape ausente, pytest path placeholder, ou refactor sem
no-behavior validator.

**Nota:** planos puramente documentais (sem touch em `engine/` ou
`validators/`) não disparam H4.

**Nota hooks:** `hooks/*.sh` e `.claude/hooks/*.sh` também não disparam
H4 — testabilidade de hooks é verificada via `SMOKE-CHECKLIST.md`
manual, não pytest automatizado. Omissão intencional.

### Medium (informativo, fix recomendado)

#### M1. Scope file whitelist

**Trigger:** sempre.

**Detecção:** pra cada task, existe seção "**Files:**" ou "ARQUIVOS
PERMITIDOS PARA EDIT" listando paths explícitos? Tasks com
Modify/Create sem path explícito → finding.

#### M2. Pending gaps coverage

**Trigger:** sempre.

**Detecção:**
1. Leia `docs/design/04-pending.md`.
2. O plano referencia gap aberto? Se sim, existe task atualizando
   `04-pending.md`?
3. O plano introduz limitação nova (anti-goal, deferred item)? Se sim,
   existe task anotando em `04-pending.md`?

**Falha:** gap fechado sem atualização OU gap novo sem anotação.

**Escopo:** anti-goals e deferred items declarados no spec referenciado
contam pra M2 quando o plano não os endereça explicitamente.
Anti-goals declarados no próprio plano também contam (campo §Anti-goals
ou §"Considerações futuras"). Em ambos os casos, espera-se task que
anota em `04-pending.md` ou justificativa explícita de por que não
anotar.

#### M3. Subagent dispatchability

**Trigger:** sempre.

**Detecção:** pra cada task com ≥3 steps, existe contexto suficiente pro
context-pack do subagent? Verifique presença de:
- Ação concreta no título da task
- Critério de sucesso (pytest path / validator / observável testável)
- Lista de anti-padrões ou "NÃO fazer" explícita

**Falha:** task ambígua pra dispatch independente.

### Low (cosmético)

#### L1. Voice check (Mandamento #5)

**Detecção:** grep no plano por:
- Emoji decorativo fora do template 3-caminhos canônico (✅⏭️🤔 são OK;
  outros sinalizam)
- "vou tentar", "considere", "talvez", "pode ser uma boa ideia"
- Inglês corporativo: "stakeholder", "leverage", "robust", "best effort"

**Finding por ocorrência.**

#### L2. Placeholder scan

**Detecção:** grep no plano por:
- "TBD", "TODO", "FIXME"
- "..." em blocos de código (não em prose)
- "implement here", "fill in", "similar to Task N" sem repetição inline

**Exceção verbatim:** placeholders como `<plan-slug>`, `<N>`, `<...>`,
`[...mesma forma...]` que aparecem dentro de blocos verbatim
(conteúdo de arquivos sendo CRIADOS por tasks Create) NÃO contam — são
sintaxe de template do arquivo destino, não placeholder do plano em si.
Verifique o contexto: se o bloco code-fenced é parte de uma task Create
e representa o conteúdo do arquivo a criar, placeholders dentro dele
são esperados.

#### L3. Type/name consistency

**Detecção:** colete todas as referências a funções/classes/arquivos
novos no plano. Verifique grafia consistente entre tasks
(case-sensitive). Ex: `clearLayers()` em task 3 vs `clearFullLayers()`
em task 7 é finding.

## Override mechanism

Antes de aplicar checks, leia o topo do plano (primeiras 50 linhas) por:

```html
<!-- audit-override: C-XXX — razão concreta -->
```

**Separador flex:** o traço entre o check-ID e a razão aceita qualquer
variação Unicode — hífen ASCII (`-`), en-dash (`–`), em-dash (`—`), ou
múltiplos hífens (`--`). Pattern conceitual:
`<!-- audit-override:\s*<CHECK-ID>\s*[-–—]+\s*<razão>\s*-->`. Tolerância
prevê diferenças de keyboard layout e auto-replace; todas as formas
abaixo são equivalentes e válidas:

```html
<!-- audit-override: C1 — chicken-and-egg, plano cria o próprio rule -->
<!-- audit-override: C1 – chicken-and-egg, plano cria o próprio rule -->
<!-- audit-override: C1 - chicken-and-egg, plano cria o próprio rule -->
<!-- audit-override: C1 -- chicken-and-egg, plano cria o próprio rule -->
```

Pra cada match:
- Marque o finding correspondente como `acknowledged`.
- Não bloqueia mais (re-classifica como Low independente da severity
  original).
- Lista na seção "Acknowledged overrides" do output, preservando a
  razão textual.

**Validação de check-ID no override:** se o ID referenciado não
corresponde a nenhum dos 12 checks (C1, C2, H1-H4, M1-M3, L1-L3), o
override é INVÁLIDO. Liste na seção "Acknowledged overrides" como
`[ID] — override inválido: check não existe no rule v1` e NÃO aplique
reclassificação. O finding original (se existir com outro ID) mantém
severity original. Override inválido NÃO conta como acknowledged.

## Verdict logic

Após processar 12 checks:

- Se `count(Critical não-acknowledged) > 0` → **BLOCK**
- Senão, se `count(High) + count(Medium) > 0` E TODOS os findings têm
  caminho C (override) com argumento de mitigação CONTEXTUAL explicitamente
  escrito pelo reviewer → **PASS_WITH_NOTES** (orquestrador apresenta as
  notes ao user mas SEM o ritual de 3-caminhos triage — basta acknowledge)
- Senão, se `count(High) + count(Medium) > 0` → **PASS_WITH_WARNINGS**
  (orquestrador apresenta 3-caminhos ao user pra cada finding)
- Senão (0 findings ou só Low) → **PASS**

**Distinção operacional:**
- `PASS_WITH_WARNINGS` = findings genuínos pedindo decisão do user
- `PASS_WITH_NOTES` = findings reais pela letra do rule mas com mitigação
  contextual baseada em exceção documentada; orquestrador informa o user
  mas não exige 3-caminhos pra cada um

**Critério determinístico pra NOTES (não subjetivo):**

Um finding qualifica pra `PASS_WITH_NOTES` apenas se o Caminho C cita
EXPLICITAMENTE:
(a) uma exceção documentada neste rule (ex.: H1 "Exceção
    chicken-and-egg", L2 "Exceção verbatim", H4 nota "planos puramente
    documentais"), OU
(b) um mandamento numerado (Mandamento #N) ou decisão (Decisão N) do
    projeto que isenta o check pra este contexto.

Ausente referência concreta a (a) ou (b) → o finding é
`PASS_WITH_WARNINGS` obrigatório. O reviewer NÃO improvisa mitigação
contextual fora dessas duas categorias.

## Output format

Escreva em `.planning/plan-reviews/<plan-slug>-review-r<N>.md`:

```markdown
# Plan Review: <plan-slug>
**Plano:** docs/superpowers/plans/<...>.md
**Spec:** docs/superpowers/specs/<...>.md
**Rodada:** N/3
**Verdict:** BLOCK | PASS_WITH_WARNINGS | PASS_WITH_NOTES | PASS

## Critical (N) — bloqueia execution-handoff
- [C-001] {check ID}: {finding curto} — task #M, linha L
  Por que importa: {regra/contract violado}
  Caminho A: {fix forward concreto}
  Caminho B: {revert/remover}
  Caminho C: {split/escalate}

## High (N)
[...mesma forma...]

## Medium (N)
[...mesma forma...]

## Low (N)
[...mesma forma...]

## Triggers que não dispararam
- C1: <razão (ex.: plano não toca 01-decisions.md)>
- H2/H3/H4: <razão (ex.: plano doc-only, sem touch em engine/validators)>
- M2: <razão se aplicável>

## Acknowledged overrides
- C-XXX: <razão textual do override inline>
```

A seção "Triggers que não dispararam" registra **no-triggers** (checks
cujo gatilho nunca foi atingido) separados de **triggers-que-passaram**
(checks cujo gatilho foi atingido mas o plano cumpriu a regra). Sem essa
distinção, "0 findings" fica ambíguo entre "não testou" e "testou e
passou". Use-a sempre que aplicável.

Se uma severity tem 0 findings, mantenha a seção com `(0 findings)` em
vez de omitir — facilita parsing.

## Anti-padrões do reviewer

- NÃO modifique o plano. Auditor é read-only contra o plano.
- NÃO escreva código Python, hook, ou validator.
- NÃO invente checks fora dos 12 listados.
- NÃO suavize severity ("é só medium, deixa passar") — siga o mapping
  determinístico.
- NÃO crie findings duplicados — se um problema dispara 2 checks (ex.:
  H1 + M1 no mesmo arquivo), reporte apenas no de severity mais alta.
- NÃO escreva voz corporativa — você está sob mandamento #5 igual o
  resto do projeto.

## Re-audit (rodadas N>1)

Quando o orquestrador dispatcha rodada 2+, você recebe o caminho do
review anterior. Compare:

1. Findings da rodada N-1 que sumiram → marque como `resolved` na nova
   review.
2. Findings novos (impacto do fix dispatch) → liste normalmente.
3. Findings persistentes → repita, mas indique `(persistente desde
   r<N-1>)`.

Limite: rodada 3. Na rodada 4, escale pro orquestrador via verdict
especial `ESCALATE` no header — orquestrador apresenta 3-caminhos ao
user.

## Quando NÃO há spec

Planos quick-fix podem não ter spec. Nesse caso:
- C2 (Spec coverage) → automaticamente finding Medium com nota "plano
  sem spec — aceitável pra quick-fix, mas verifique se escopo justifica
  ausência".
- Demais checks rodam normalmente.
