# Spec — Camada de Interação AI-First: Driver + Grill (Wave 1)

> **Data:** 2026-06-17
> **Status:** aprovado em brainstorming (este doc é o contrato de design; alimenta writing-plans).
> **Origem:** brainstorming pós-auditoria LLM-first. Insumos: `docs/reports/auditoria-consolidada-2026-06-17.md` + `docs/reports/analise-comportamental-2026-06-17.md`.
> **Branch:** `feat/ai-first-interaction-layer` (empilhada sobre PR #17 — depende da host-adapter layer).
> **Voz:** mentor calmo.

## 1. Goal / Por quê

feature-forge é dirigido 100% por hosts agênticos (Claude Code / opencode), mas hoje:
- **Nada ensina o host a dirigir o intent loop** (DRIVER-001): o engine emite `<FORGE_INTENT/>` + exit 2 e espera que o host leia o marker, chame `AskUserQuestion`, escreva `forge-response.json` com o `intent-id` casado e re-invoque com argv idêntico — mas nenhum artefato instalado no consumidor ensina isso. Resultado: `forge plan` morre no 1º prompt num consumidor fresco.
- **O forge não interroga ambiguidade** (AMBIGUITY-DEAD): no engine, `forge plan` rejeita ticket/texto-livre com `SystemExit`; o `ambiguity-map.yaml` é scaffolding morto; o grill existe só no prompt do `planning-conductor` (uni-direcional — consulta docs pra suprimir perguntas, nunca pra confrontar o pedido) e é inerte sem o driver.

Esta Wave 1 entrega a **camada de interação AI-first**: o host passa a dirigir o forge de ponta a ponta, e o forge passa a confrontar o pedido contra o que já existe (grill-with-docs), incluindo entrada visual (screenshots) como cidadão de primeira classe.

## 2. Decisões travadas no brainstorming

| # | Decisão | Escolha |
|---|---|---|
| D1 | Mecanismo do driver | **Faseado**: artefatos de ensino agora (`SKILL.md` CC + `AGENTS.md` opencode), mantendo engine subprocess+marker; MCP server com elicitation nativa = norte estratégico (wave futura, não agora) |
| D2 | Escopo da Wave 1 | **Visão completa**: driver + front-door + grounded-challenge + readiness enforce |
| D3 | Tom do grill em conflito | **Confronta + pergunta, humano decide** (não-bloqueante); registra no `rationale-trace` |
| D4 | Onde mora o grounded-challenge | **Inline no `planning-conductor` (Phase 2.5)**; agentes lidos do FORGE_HOME; front-door no engine |
| D5 | UI sem input visual | **Proativo**: grill pergunta na hora — 3-caminhos (anexar mockup / descrever em texto / reusar screen-analysis de feature similar da L2) |

## 3. Restrições e invariantes

- **Decisão 22 (load-bearing):** skills/agents são comportamento, não runtime import. A `SKILL.md`/`AGENTS.md` são instruções pro host — o engine NÃO importa nada delas. Preservada.
- **Decisão 18:** skill location XDG (`~/.local/share/feature-forge/`). FORGE_HOME canônico.
- **Decisão 10 (zero flags):** o front-door aceita ticket/frase como **argv posicional** (não é flag) e o screenshot entra **conversacionalmente** (path na source-inquiry, sem flag CLI) — Decisão 10 preservada, sem carve-out novo.
- **Exec model canônico:** engine emite intent, LLM raciocina. O grounded-challenge é raciocínio → vive no conductor (prompt), não no engine. O engine só orquestra + sanitiza (ex.: valida screenshot), nunca interpreta pixel/domínio.
- **Pré-produção:** clean break OK; sem usuários reais ainda.

## 4. Arquitetura — 5 componentes

```
forge plan "<ticket|frase|slug>" [screenshot conversacional]
  → [C3 front-door/engine] deriva slug + confirma + semeia intake (+ sanitiza/fingerprint screenshot via C3a)
  → [C1 driver] host responde o intent loop (marker → AskUserQuestion → response → re-invoca)
  → [C1 driver] host dispatcha agents/planning-conductor.md (do FORGE_HOME)
  → [conductor] Phase 1-2 → [C4 Phase 2.5 grounded-challenge] → Phase 3 elicit (confronta + humano decide)
  → preenche artefatos (needs-elicitation no que faltar)
  → [C5 readiness enforce] bloqueia se needs-elicitation/blocking-OQ não resolvidos
```

### C1 — Driver `SKILL.md` (+ `AGENTS.md`)
- **Conteúdo da SKILL.md** (`.claude/skills/feature-forge/SKILL.md`):
  - **Protocolo (intent loop):** ao rodar um comando `forge` que sai com **exit 2** + linha `<FORGE_INTENT kind=... intent-id=... question=... options=... .../>` no stdout: parsear os atributos; chamar `AskUserQuestion` nativo com `question`+`options`; escrever `.claude/forge/state/forge-response.json` no schema de `docs/schemas/intent-protocol.md` com o **mesmo `intent-id`**; re-invocar o forge com **argv idêntico**; repetir até exit 0/1/130. Legenda de exit: 0=ok, 1=erro, 2=pausado(responder), 130=cancelado.
  - **Workflow mínimo:** mapa dos verbos (init/plan/implement/verify/status/...) + a regra "ao rodar `forge plan`, dispatch `agents/planning-conductor.md` (do FORGE_HOME) e dirija a elicitação dele (que usa `AskUserQuestion` direto)".
  - Voz mentor calmo; conciso (token-aware).
- **`AGENTS.md`** (raiz do consumidor — convenção opencode): mesmo conteúdo, adaptado ao mecanismo opencode (responder o pending file `.claude/forge/state/forge-pending.json` + re-invocar).
- **Instalação:** `forge init` cria/aponta os dois, **brownfield-safe** (merge/append, nunca clobber — mesmo padrão de `merge_settings_json`). Idempotente.

### C3 — Front-door no engine (`forge plan`)
- **Aceita** argv posicional: slug válido (como hoje) · ticket-id (ex.: `IN-37234`) · frase livre (ex.: `adicionar detalhe do bonsai`).
- **Frase/ticket → deriva slug** kebab-case (slugify determinístico: lowercase, espaços→hífen, strip de acentos/inválidos, colapsa hífens, trunca 2..50, garante início com letra). Colisão de slug existente → sufixo/3-caminhos.
- **Confirma o slug derivado** via `<FORGE_INTENT>` ("derivei `adicionar-detalhe-do-bonsai` — confirma ou ajusta?") — o usuário pode corrigir.
- **Semeia o intake**: grava o texto/ticket cru no campo source/intent do `feature-intake.md` (o conductor refina via grill).
- **Troca `raise SystemExit`** por mensagem mentor-calmo + exit-code correto (slug-derivável NÃO é erro; só vira exit 1 se realmente impossível derivar).
- **CASING-BUG fix (mesmo ponto):** `_render_template` (`engine/plan.py:401`) passa a substituir `{{feature_slug}}` (lowercase, como os templates usam — 74×) + os tokens triviais que o engine conhece (slug, `generated_at_iso8601`, `source_type`, `source_ref`, paths relativos). É o mesmo `_render_template` que a semeadura toca.

### C3a — Wire do `engine/vision/screenshot.py` (dormente → ativo)
- Hoje `engine/vision/screenshot.py` é código real (valida formato/tamanho, fingerprint sha256, normaliza path com proteção a traversal, infere plataforma por aspect-ratio) mas **nunca é chamado**.
- **Wire (reuso — Mandamento 3):** quando o usuário fornece path(s) de screenshot na source-inquiry, o engine chama `normalize_screenshot_path` (traversal-safe) → `validate_screenshot` (rejeita inválido com mensagem clara, não crasha) → copia pro `{feature}/screenshots/` → `compute_screenshot_fingerprint` no manifest. `infer_platform_inference` só como hint de baixa confiança que o conductor pode sobrepor.
- O engine **não interpreta pixel** — só sanitiza + registra o ponteiro. A vision-analysis é do host conductor (multimodal).

### C4 — Grounded-challenge (`planning-conductor.md` Phase 2.5)
- **Posição:** fase nova entre Ambiguity Map (Phase 2) e Elicit (Phase 3).
- **Inputs (reuso do que o conductor já carrega):** grafo Q1 (similar-features) + Q11-Q17 (reuse-intelligence) · `engine/inventory/` (design-system/i18n/conventions) · L2 `decisions-frozen` + memory L2/L3.
- **Confronta o pedido** (não só semeia default): duplicação ("Q1 mostra `bonsai-list` já persiste `starred` — reusar/estender/novo?"), terminologia ("o termo X conflita com a entidade Y da L2"), decisão-frozen ("isso contraria a decisão D-N"), componente fora do design-system.
- **Output:** cada conflito vira pergunta na Phase 3 (`AskUserQuestion` agrupado existente), formato "confronta + humano decide" (D3); a resolução + rationale entram no `rationale-trace.yaml`.
- **No-visual branch (D5):** se a feature é UI/product e não há input visual, o grill confronta no front da elicitação com 3-caminhos: (a) anexar mockup/screenshot, (b) descrever a tela em texto (vira estados `confirmed` com `source: prd/intake`), (c) reusar a screen-analysis de feature similar da L2. Abortar continua como caminho honesto só se nenhum rolar.
- **Degradação graciosa:** grafo/inventory ausente (projeto sem bootstrap) → pula o que não tem, anota; nunca crasha o grill.

### C5 — Readiness enforce (`readiness-reviewer.md` Phase 5)
- Adiciona scan de `needs-elicitation: true` não-promovido nos artefatos (junto do forbidden-phrases scan existente) → **block-severity** em contract specs; warning em narrativa.
- Fecha o ponto-cego "thin-but-structurally-complete": hoje um campo `needs-elicitation` que o conductor não promove a `blocking: true` open-question pode escapar como `ready` se a cadeia story→task ainda fecha nominalmente.

## 5. Fluxo de dados (com e sem screenshot)

**Com screenshot:** usuário fornece path(s) na source-inquiry → engine sanitiza/fingerprint/copia (C3a) → conductor (host, multimodal) analisa os pixels, casa contra design-system, mostra matches + pede confirmação → screen-analysis-agent consome a extração (não os pixels) na Wave B.

**Sem screenshot (UI):** front-door + grill → no-visual branch (C4/D5) confronta com os 3-caminhos antes de planejar a tela → conforme a escolha: (a) usuário anexa → vira "com screenshot"; (b) descreve → estados `confirmed` de texto; (c) reuso L2 → herda screen-analysis similar.

## 6. Error handling

- Host não dispatcha o conductor → a `SKILL.md` é explícita sobre isso; defense-in-depth: o engine, ao sinalizar "dispatch conductor", inclui a instrução no payload do intent.
- argv não-derivável a slug → mensagem mentor-calmo + exit 1 (não `SystemExit` cru).
- screenshot inválida → `validate_screenshot` rejeita limpo (mensagem + segue sem a imagem, marca `needs-elicitation`), não crasha.
- grafo/inventory/L2 ausente → grounded-challenge degrada gracioso.
- intent-id mismatch / re-invocação com argv diferente → já tratado pelo protocolo (exit 1 mentor-calmo); a `SKILL.md` enfatiza "argv idêntico".

## 7. Testing

- **Front-door (C3):** unit — slugify determinístico (frase/ticket/edge: acentos, espaços, colisão, uppercase ticket), semeadura do intake, troca do SystemExit, **CASING-BUG** (asserir `{{feature_slug}}` substituído).
- **Vision wire (C3a):** unit — `normalize/validate/fingerprint` no front-door (path traversal rejeitado, formato inválido rejeitado, fingerprint estável, cópia pro screenshots/).
- **SKILL.md / AGENTS.md (C1):** smoke — existência + instalação por `forge init` (brownfield-safe, idempotente) + conteúdo mínimo (legenda de exit, regra de dispatch). O loop em si é validado via `SMOKE-CHECKLIST.md` (mesma lógica de hooks: não pytest-testável).
- **Grounded-challenge (C4):** prompt-level — não unit-testável; cobertura via smoke + exemplo no `docs/ux/forge-plan-roteiro.md` (cena de confronto + no-visual branch).
- **Readiness enforce (C5):** validator test — `needs-elicitation` scan (block em contract spec, warning em narrativa).
- Gate de "pronto": `.venv/bin/pytest` verde (rapid+integration), `forge verify` sem hard fail, counts ≥ baseline 1.4.0 (rapid 1569 / integration 162 / e2e 30).

## 8. Escopo

**IN (Wave 1):** C1 driver `SKILL.md`+`AGENTS.md` · C3 front-door (+CASING-BUG +C3a vision wire) · C4 grounded-challenge Phase 2.5 (+no-visual branch) · C5 readiness enforce.

**OUT (waves separadas / anti-goals desta wave):**
- **MCP server** com elicitation nativa — norte estratégico (D1), wave futura.
- **EXIT-2-COLLISION amplo** (des-colidir 3/4/5/6/8 + reservar exit 2 só pra pause) — wave de robustez. (Esta wave só conserta o `SystemExit` local do front-door.)
- **DEAD-VERIFY** (path do git-pre-commit) — wave de hooks.
- **CONC-1** (tempfile por-PID + flock) — wave de concorrência.
- **TOKEN-BLIND / `--json` / manifesto / `forge status` router** — wave de token economy.
- Esses ficam registrados em `docs/design/04-pending.md` pela tarefa de doc-sync do plano.

## 9. Doc-sync requerido (pra o plano cobrir)

- `CHANGELOG.md` (Unreleased): Added (driver SKILL.md + AGENTS.md, front-door, grounded-challenge, readiness enforce), Fixed (CASING-BUG), Changed (vision wire).
- `docs/design/08-session-handoff.md`: estado + Última atualização.
- `docs/design/06-command-surface.md`: `forge plan` aceita ticket/frase (comportamento novo).
- `docs/design/04-pending.md`: risca AMBIGUITY-DEAD/CASING-BUG; registra os OUT (MCP, exit-2, dead-verify, conc-1, token) como follow-ups.
- `docs/ux/forge-plan-roteiro.md`: front-door + grounded-challenge + no-visual branch.
- `agents/planning-conductor.md` + `agents/readiness-reviewer.md`: as mudanças C4/C5 (são os próprios arquivos editados).
- `docs/guides/getting-started.md`: seção "como o forge fala com seu host AI" (o driver).
- `README.md`: se stats mudarem (novo artefato/skill).
- `.claude/rules/`: mention do driver skill se virar parte do workflow canônico.

## 10. Impacto em decisões locked

Nenhuma decisão locked revisitada. Decisão 22 e 18 preservadas (ver §3). Decisão 10 preservada (front-door usa argv posicional + screenshot conversacional, sem flag novo).

## 11. Reuso (Mandamento 3)

- `engine/vision/screenshot.py` — código pronto, dormente; wire em vez de reescrever (C3a).
- `planning-conductor.md` Phase 1-4 + `AskUserQuestion` agrupado existente — Phase 2.5 reusa o contexto que ele já carrega; não duplica.
- Grafo Q1/Q11-Q17 + `engine/inventory/` + L2 — já existem; o grounded-challenge consome, não recria.
- `merge_settings_json` (brownfield-safe) — padrão reusado pra instalar SKILL.md/AGENTS.md.
- `readiness-reviewer` forbidden-phrases scan — estende, não reescreve (C5).
