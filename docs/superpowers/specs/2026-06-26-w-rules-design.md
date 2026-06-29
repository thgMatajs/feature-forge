# W-RULES (Fase 1, Onda 5) — Design refinement

> Refinamento de design do brainstorm (2026-06-26). O design de alto nível
> vive na spec `2026-06-25-mem-integration-design.md` §Fase 1 (init pós-mem,
> passo 1-5). Este doc fixa as DECISÕES de mecânica que a spec deixou abertas,
> pra alimentar o writing-plans. Voz: mentor calmo.

## O quê (recap da spec)

`forge init` lê os `.claude/rules/*` + `CLAUDE.md` do consumidor, classifica
cada fragmento em Tier-0 (invariante, fica injetado lean) vs Tier-1 (referência
→ vira nota mem), PROPÕE a divisão ao humano (G1/G2 — nunca trucida em silêncio),
e ao aprovar: `mem add` do Tier-1 + enxuga o núcleo + escreve/aponta o RULE_INDEX.
É o fix do gap de assimilação de convenção do piloto.

## Decisões do brainstorm (2026-06-26)

### D1 — Classificação: conductor/host (LLM) via intent
A classificação Tier-0/Tier-1 é **trabalho do host (Claude Code = LLM)**, não
heurística no engine (Decisão 22: engine não importa LLM em runtime). O engine
lê os fragmentos e emite um **intent de classificação**; o host fulfilla com
julgamento semântico e devolve o split estruturado; o engine aplica + propõe
3-caminhos ao humano.

### D2 — Transformação: move Tier-1 pro mem + enxuga rules (com .bak)
Ao aprovar: Tier-1 → `mem add` E removido dos `.claude/rules/*` (que viram
ponteiros enxutos), com `.bak` (Decisão 24). A fonte do conhecimento Tier-1
passa a ser o mem. Reversível via `.bak`. G1/G2 garantido pela ratificação
3-caminhos + backup. Espelha o que a Fase 0 fez no próprio forge.

### D3 — Infra: NOVO intent-kind `AskKind.CLASSIFY`
Os intent-kinds atuais (`ASK`/`ASK_MULTI`/`ASK_TEXT`/`ASK_THREE_PATHS`/`CONFIRM`)
são todos shapes de PERGUNTA ao usuário. Classificação é uma TAREFA que o
host-LLM fulfilla — semântica diferente. Decisão: adicionar `AskKind.CLASSIFY`
(infra limpa e reutilizável pro W-ROUTE/conductor depois), em vez de esticar
`ask_text` (tarefa disfarçada de pergunta) ou inventar handshake por arquivo.

Componentes da infra `classify`:
- `engine/host/adapter.py`: `AskKind.CLASSIFY` no enum + método/handling no
  protocolo do adapter (assinatura: recebe os fragmentos + schema de
  classificação; devolve a classificação estruturada).
- Adapters: Claude Code (emite o intent pending → host fulfilla → response
  JSON), TTY/stdin fallback (degradação graciosa — ex.: pede classificação
  manual ou pula com aviso), intent-file.
- `engine/ui/question.py`: entrypoint `classify(...)` que monta o intent
  pending, levanta `PausedForInputError` (exit 2), e na re-invocação parseia a
  resposta estruturada. Espelha o padrão de `ask_three_paths`.
- Driver (SKILL.md/AGENTS.md do forge — ou o doc equivalente que ensina o host
  a dirigir o forge): instrução de COMO fulfillar um intent `classify` (ler os
  fragmentos do pending, classificar Tier-0/1, escrever o response JSON).
- Contrato de resposta (JSON): lista de `{fragment_id, tier: 0|1, rationale,
  mem_note?: {type, title, body, tags}}` — `mem_note` presente só pra Tier-1.

## Mecânica (7 pontos)

1. **Trigger:** passo `_reduce_rules` no `forge init`, APÓS o vendoring (W-VENDOR).
   Só roda se o consumidor TEM `.claude/rules/*` ou `CLAUDE.md` reduzível.
   Greenfield (sem rules) → skip.
2. **Fragmento = seção** (bloco delimitado por heading `##`/`###`) em cada
   `.claude/rules/*.md` e no `CLAUDE.md`; arquivo pequeno = 1 fragmento.
3. **Classificação:** engine lê fragmentos → `question.classify(fragmentos,
   schema)` → host devolve o split (D3). Decisão 22 OK.
4. **Proposta 3-caminhos (G1/G2):** `ask_three_paths`: aceitar / ajustar
   (humano edita atribuições → re-propõe) / pular (deixa as rules como estão).
   Nunca auto-aplica.
5. **Aplicar (no aceitar):** `.bak` de CLAUDE.md + `.claude/rules/*` → Tier-1
   vira `mem add` (via `mem_call`) → remove Tier-1 dos arquivos-fonte (rules
   viram ponteiros "detalhe: `mem find '<tema>'`") → CLAUDE.md enxugado pra
   Tier-0 + referência ao RULE_INDEX.
6. **RULE_INDEX:** o scaffold do mem (W-VENDOR) já escreveu o RULE_INDEX
   genérico no `AGENTS.md`. W-RULES NÃO duplica — só garante que as
   rules/CLAUDE.md enxutos apontem pra ele.
7. **Idempotência:** sentinel `.claude/.rules-reduced`; re-init sem `--force`
   → no-op.

## Decomposição provável (pro writing-plans)

- **Task A — infra `classify`:** `AskKind.CLASSIFY` + adapter handling + os 3
  adapters + `question.classify` + contrato JSON + testes (incl. fallback
  não-TTY). TDD. É a fundação; vem primeiro.
- **Task B — `_reduce_rules`:** leitura de fragmentos (parse por seção) + emite
  classify + 3-caminhos + aplicar (.bak/mem add/trim/sentinel) + wire no init.
- **Task C — driver:** instrução de fulfillment do `classify` no driver do forge.
- **Task D — doc-sync + ADR (se houver toque load-bearing) + 04-pending.**

## Riscos / watches

- A infra `classify` toca o host adapter (load-bearing, AI-first layer) — o
  writing-plans DEVE scoutar `engine/host/adapter.py` + os 3 adapters +
  `intent_state` + o driver real antes de decompor (plan-scout).
- Fallback não-TTY do `classify`: sem host-LLM, a classificação não acontece —
  degradar gracioso (pular a redução com aviso, ou pedir classificação manual),
  nunca travar o init. Detection-shaped: o plano define o comportamento honesto.
- Testes: por fixture (consumer sintético com CLAUDE.md + .claude/rules), +
  scrub de env pra pinar host=intent-file em teste (determinismo).
