# PRD docs/product/ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Materializar os 4 docs do PRD do feature-forge em `docs/product/` (~2370 LOC total) conforme spec aprovado, em 4 waves de conteúdo + 1 wave doc-sync final. Voz mentor calmo PT-BR, coexistência paralela com `docs/design/` e `docs/ux/` sem mexer em load-bearing.

**Architecture:** 5 fases sequenciais (Wave 1 → 2 → 3 → 4 → doc-sync). Wave 1 escreve sub-doc independente (personas) que ancora cross-refs nos próximos. Wave 4 escreve porta-de-entrada por último porque depende de cross-refs estáveis pros 3 sub-docs. Fase E faz doc-sync canônico (CHANGELOG + handoff + README) em commit separado.

**Tech Stack:** Markdown puro (sem código fonte novo). Validação via `wc -l`, `grep`, e leitura manual. Voz mentor calmo PT-BR conforme `docs/design/07-discipline.md §5` e nomes personas canônicos (Marina/Bruno/Sub-agente Claude/Carlos/Lucas/Carolina/Patricia/Diego).

**Source spec:** `docs/superpowers/specs/2026-06-04-prd-design.md` (commit `2e1a266`).

---

## File Structure

### Created (4 docs em diretório novo)

```
docs/product/                              ← NOVO diretório
├── 00-prd.md                              ~600 LOC — porta de entrada, 13 seções
├── 01-personas.md                         ~600 LOC — 8 personas em 3 camadas
├── 02-scenarios.md                        ~770 LOC — 6 user journeys end-to-end
└── 03-roadmap.md                          ~400 LOC — 3 ondas + Eisenhower + anti-roadmap
```

### Modified (3 docs no doc-sync final)

```
CHANGELOG.md                               # ### Added — 4 docs em docs/product/
docs/design/08-session-handoff.md          # Última atualização + Estado refletindo entrega
README.md                                  # pointer pra docs/product/ em §Documentação
```

### Out-of-scope explícito

Não mexer em `docs/design/00-vision.md` nem `docs/design/ROADMAP.md` (load-bearing — coexistência paralela é decisão tomada no spec). Cross-refs no PRD apontam pra eles, sem reciprocidade nesta entrega.

### Responsibilities por doc

- **01-personas.md (Wave 1, ~600 LOC):** Fonte de verdade dos nomes (Marina/Bruno/Sub-agente Claude/Carlos/Lucas/Carolina/Patricia/Diego). 3 camadas: A (dedicadas com day-in-life, 3×~90), B (variantes Marina com caveats, 3×~55), C (downstream read-only, 2×~30).
- **02-scenarios.md (Wave 2, ~770 LOC):** 6 user journeys (C1-C6) seguindo schema: Persona/Estado inicial→final/Passos numerados/Outcome/Cross-ref. Depende de personas escritas pra cross-ref nomes.
- **03-roadmap.md (Wave 3, ~400 LOC):** §1 Princípios + §2-§4 Ondas + §5 Eisenhower + §6 Anti-roadmap + §7 Cross-ref bidirecional pro ROADMAP.md técnico. Depende de personas pra "persona afetada por onda".
- **00-prd.md (Wave 4, ~600 LOC):** 13 seções (Por-quê / Vision / Princípios / Escopo IN-OUT / Personas resumo + link / Scenarios resumo + link / Roadmap resumo + link / Success criteria / Anti-personas / Cross-refs docs técnicos / Glossary / FAQ / Risks). Escrito por último com cross-refs estáveis pros sub-docs.
- **Doc-sync (Fase E):** CHANGELOG `### Added` + handoff Última atualização + Estado + README §Documentação ganha pointer.

---

## Fase A — Wave 1: 01-personas.md (~600 LOC)

### Task 1: Criar diretório + skeleton + Camada A persona Marina (~90 LOC)

**Files:**
- Create: `docs/product/01-personas.md`
- Read context: `docs/superpowers/specs/2026-06-04-prd-design.md` §Seção 2 (Camada A Marina)

- [ ] **Step 1: Verificar que diretório docs/product/ não existe**

```bash
test ! -d docs/product/ && echo "OK: dir não existe" || echo "FAIL: dir já existe"
```

Expected: `OK: dir não existe`. Se já existe, abort com 3-caminhos pro orchestrator (criado por outra sessão? remover e refazer? continuar?).

- [ ] **Step 2: Criar diretório**

```bash
mkdir -p docs/product/
```

- [ ] **Step 3: Render skeleton do 01-personas.md**

Write `docs/product/01-personas.md` com cabeçalho + estrutura completa (3 camadas + 8 sub-headers) mas SEM conteúdo das personas ainda:

```markdown
# Personas do feature-forge

> **Cross-ref:** Este doc é referenciado por [`00-prd.md`](00-prd.md) §5, [`02-scenarios.md`](02-scenarios.md) (persona principal de cada cenário) e [`03-roadmap.md`](03-roadmap.md) (persona afetada por onda).

8 personas em 3 camadas. Camada A é dedicada (day-in-life completo); Camada B agrupa variantes da Marina com caveats; Camada C cobre consumidores downstream / read-only.

---

## Camada A — Personas dedicadas

### Marina — Mobile dev solo KMP/Android (PRIMÁRIA)

[a preencher na Task 1]

### Bruno — Tech lead / staff engineer (SECUNDÁRIA)

[a preencher na Task 2]

### Sub-agente Claude — Persona técnica não-humana

[a preencher na Task 2]

---

## Camada B — Variantes da Marina

### Carlos — Android-only sem KMP

[a preencher na Task 3]

### Lucas — iOS-only sem KMP

[a preencher na Task 3]

### Carolina — Dev iniciante / onboarding

[a preencher na Task 3]

---

## Camada C — Downstream / read-only

### Patricia — PM / Product Owner

[a preencher na Task 4]

### Diego — Code reviewer humano

[a preencher na Task 4]
```

- [ ] **Step 4: Preencher seção da Marina (~90 LOC) seguindo spec §Seção 2**

Substitua o `[a preencher na Task 1]` da seção Marina pelo conteúdo: Perfil + Stack típica + JTBD principal (lista 4 itens) + Frustrações sem forge (lista 4) + Critérios sucesso com forge (lista 3) + Day-in-life típico (terça-feira em 8 bullets com horários).

Render fiel ao spec §Seção 2 Camada A Marina. Voz mentor calmo PT-BR. Use formato bullet markdown coerente com o resto do projeto.

- [ ] **Step 5: Validar Marina render**

```bash
wc -l docs/product/01-personas.md
grep -c "^- \*\*" docs/product/01-personas.md  # contagem de bullets bold
grep -n "Marina" docs/product/01-personas.md | head -5
```

Expected: LOC ~120 (skeleton + Marina). "Marina" aparece ≥ 8 vezes. Bullets bold ≥ 15.

### Task 2: Preencher Bruno + Sub-agente Claude (~180 LOC adicionais)

**Files:**
- Modify: `docs/product/01-personas.md`

- [ ] **Step 1: Preencher Bruno (~90 LOC) seguindo spec §Seção 2 Camada A Bruno**

Substitua `[a preencher na Task 2]` da Bruno por: Perfil + Stack típica + Momentos de uso forge (lista 4) + JTBD principal (lista 4) + Frustrações sem forge (lista 3) + Critérios sucesso com forge (lista 3) + Day-in-life típico (quarta tarde em 5 bullets com horários).

- [ ] **Step 2: Preencher Sub-agente Claude (~90 LOC) seguindo spec §Seção 2 Camada A Sub-agente Claude**

Substitua `[a preencher na Task 2]` da Sub-agente Claude por: Perfil + Inputs canônicos esperados (lista 4) + Outputs canônicos esperados (lista 3) + 5 critérios sucesso não-negociáveis (numerados 1-5: Determinismo, Escopo, Voz, Never-invent, 3-caminhos) + Frustrações sem forge (lista 3) + Day-in-life típico (Wave A dispatch pra subtype=bugfix em 5 bullets).

- [ ] **Step 3: Validar Bruno + Sub-agente render**

```bash
wc -l docs/product/01-personas.md
grep -n "Bruno" docs/product/01-personas.md | head -3
grep -n "Sub-agente Claude" docs/product/01-personas.md | head -3
grep -c "5 critérios sucesso" docs/product/01-personas.md
```

Expected: LOC ~300 (skeleton + Marina + Bruno + Sub-agente Claude). "Bruno" e "Sub-agente Claude" aparecem ≥ 3 cada. Header "5 critérios sucesso" presente.

### Task 3: Preencher Camada B (Carlos + Lucas + Carolina, ~165 LOC adicionais)

**Files:**
- Modify: `docs/product/01-personas.md`

- [ ] **Step 1: Preencher Carlos (~55 LOC) seguindo spec §Seção 2 Camada B Carlos**

Substitua `[a preencher na Task 3]` do Carlos por: Diferencial + Posicionamento v1 + Caveats leves (lista 5) + JTBD herdado da Marina + nuance.

- [ ] **Step 2: Preencher Lucas (~55 LOC) com TABELA OBRIGATÓRIA**

Substitua `[a preencher na Task 3]` do Lucas por: Diferencial + Posicionamento v1 + Tabela "Caveats v1" com EXATAMENTE 6 linhas:

| Aspecto | Estado v1.2 | Comportamento | Workaround |
|---|---|---|---|
| Preset dedicado `ios-only` | ❌ não existe | `forge init` não detecta auto | Manual via `forge reconfigure` |
| Auto-detection em `forge init` | ❌ retorna 0 signals positivos | Sem preset aplicado | Manual via menu |
| Cards canon utilizáveis | ✅ `swiftui-screens`, `swiftui-navigation`, `auth-jwt-bearer`, `crashlytics`, `firebase-storage` | Aplicam-se normalmente | — |
| Cards canon NÃO utilizáveis | ❌ `kmp-shared`, `koin-annotations`, `kotlin-language`, `skie-bridge`, `ktor-client`, `retrofit-client`, `room-database`, `datastore-prefs`, `shared-preferences-prefs` | Não ativam (sem signal) | — |
| Customização pra stack | ✅ Gap 5 cobre — `.claude/cards/local/` | Cards iOS locais (Alamofire, KeychainAccess, etc.) | Caminho oficial |
| Roadmap pra UX nativa | Onda 2 cobre preset `ios-only` | Quando demanda concreta justificar | — |

- [ ] **Step 3: Preencher Carolina (~55 LOC) seguindo spec §Seção 2 Camada B Carolina**

Substitua `[a preencher na Task 3]` da Carolina por: Diferencial + JTBD diferenciado em relação à Marina + Forge usa também como material didático (lista 5) + Frustração sem forge (lista 2) + Critério sucesso.

- [ ] **Step 4: Validar Camada B**

```bash
wc -l docs/product/01-personas.md
grep -nE "Carlos|Lucas|Carolina" docs/product/01-personas.md | head -10
grep -c "❌\|✅" docs/product/01-personas.md  # tabela do Lucas
```

Expected: LOC ~470. Nomes Carlos/Lucas/Carolina presentes ≥ 2 cada. Tabela do Lucas tem ≥ 8 marcadores ❌/✅.

### Task 4: Preencher Camada C (Patricia + Diego, ~60 LOC adicionais)

**Files:**
- Modify: `docs/product/01-personas.md`

- [ ] **Step 1: Preencher Patricia (~30 LOC) seguindo spec §Seção 2 Camada C Patricia**

Substitua `[a preencher na Task 4]` da Patricia por: NÃO toca código + Única interação com forge + JTBD principal + Frustração sem forge + Boundary explícito (forge NÃO faz estimativa/schedule/priorização, cita 00-vision §What feature-forge is NOT).

- [ ] **Step 2: Preencher Diego (~30 LOC) seguindo spec §Seção 2 Camada C Diego**

Substitua `[a preencher na Task 4]` do Diego por: Dev senior + Interação com forge (indireta — recebe PR) + Expectativas em PR forge-gerado (lista 4) + JTBD principal + Frustração sem forge + Critério sucesso.

- [ ] **Step 3: Validar Camada C**

```bash
wc -l docs/product/01-personas.md
grep -nE "Patricia|Diego" docs/product/01-personas.md | head -6
```

Expected: LOC ~580-620 (range OK pra ~600). Patricia/Diego presentes ≥ 2 cada.

### Task 5: Wave 1 validate + commit

- [ ] **Step 1: Run validation suite no 01-personas.md**

```bash
echo "=== LOC ===" && wc -l docs/product/01-personas.md
echo "=== TBD/TODO scan ===" && grep -nE "TBD|TODO|XXX|FIXME|a preencher|placeholder" docs/product/01-personas.md
echo "=== naming consistency ===" && grep -nE "Mar[ií]a[^.]|Bru[nm][^o]|Carlitos|Lucca|Carolinea|Patrícia|Patricia[^.]" docs/product/01-personas.md
echo "=== headers count ===" && grep -c "^### " docs/product/01-personas.md
echo "=== cross-refs ===" && grep -c "\[\`.*\.md\`\]\|00-prd.md\|02-scenarios.md\|03-roadmap.md" docs/product/01-personas.md
```

Expected:
- LOC: 550-650 (range OK pra ~600)
- TBD/TODO scan: 0 hits (todos os `[a preencher]` foram substituídos)
- Naming consistency: 0 hits suspeitos
- Headers `###`: exatamente 8 (8 personas)
- Cross-refs: ≥ 3 (ao menos 00-prd, 02-scenarios, 03-roadmap mencionados)

Se algum check falhar, faça fix inline antes do commit.

- [ ] **Step 2: Commit atômico Wave 1**

```bash
git add docs/product/01-personas.md
git commit -m "$(cat <<'EOF'
docs(product): 01-personas wave 1 (8 personas em 3 camadas)

Cria docs/product/ com 01-personas.md (~600 LOC) — fonte de verdade dos
nomes canônicos do PRD. 8 personas em 3 camadas:

- Camada A (dedicadas): Marina (mobile dev solo KMP/Android, PRIMÁRIA) +
  Bruno (tech lead, SECUNDÁRIA) + Sub-agente Claude (técnica não-humana)
- Camada B (variantes Marina): Carlos (Android-only) + Lucas (iOS-only,
  com tabela de caveats v1) + Carolina (iniciante/onboarding)
- Camada C (downstream read-only): Patricia (PM) + Diego (code reviewer)

Wave 1 de 4 do plano docs/superpowers/plans/2026-06-04-product-docs.md.
Cross-refs futuros: 00-prd §5 (resumo), 02-scenarios (persona principal),
03-roadmap (persona afetada por onda).

Spec fonte: docs/superpowers/specs/2026-06-04-prd-design.md (commit 2e1a266).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

git log -1 --stat
```

Expected: 1 file changed, ~600 insertions.

---

## Fase B — Wave 2: 02-scenarios.md (~770 LOC)

### Task 6: Skeleton + C1 Brownfield init (~120 LOC)

**Files:**
- Create: `docs/product/02-scenarios.md`
- Read context: `docs/superpowers/specs/2026-06-04-prd-design.md` §Seção 3 C1

- [ ] **Step 1: Render skeleton com schema dos cenários**

Cabeçalho + cross-refs + explicação do schema:

```markdown
# Cenários de uso do feature-forge

> **Cross-ref:** Este doc é referenciado por [`00-prd.md`](00-prd.md) §6. Personas citadas vivem em [`01-personas.md`](01-personas.md).

6 user journeys end-to-end, cada um seguindo o schema:

- **Persona principal:** ...
- **Estado inicial:** ...
- **Estado final:** ...
- **Passos:** numerados
- **Outcome:** uma frase
- **Cross-ref:** docs/ux/*.md + docs/design/*.md relevantes

---

## C1 — Brownfield init com reuse-intelligence (~120 LOC)
[a preencher na Task 6]

## C2 — Feature product nova end-to-end (~150 LOC)
[a preencher na Task 7]

## C3 — Bugfix com ticket IN-37234 (~120 LOC)
[a preencher na Task 7]

## C4 — Retomar trabalho pausado (~100 LOC)
[a preencher na Task 8]

## C5 — Extension feature Gap 9 (~130 LOC)
[a preencher na Task 8]

## C6 — Reuse intelligence em ação (~120 LOC)
[a preencher na Task 9]
```

- [ ] **Step 2: Preencher C1 (~120 LOC) seguindo spec §Seção 3 C1**

Substitua `[a preencher na Task 6]` de C1 por: Persona principal (Bruno + Marina dia seguinte) + Estado inicial + Estado final + Passos numerados (1-6) + Outcome + Cross-ref pra `docs/ux/forge-init-roteiro.md` Cenas 5.5+5.6 e `docs/lifecycle/memory-and-graph.md`.

- [ ] **Step 3: Validar C1**

```bash
wc -l docs/product/02-scenarios.md
grep -n "C1 " docs/product/02-scenarios.md
grep -c "Bruno\|Marina" docs/product/02-scenarios.md
```

Expected: LOC ~155 (skeleton + C1). Bruno/Marina presentes em C1.

### Task 7: C2 Feature product + C3 Bugfix (~270 LOC adicionais)

**Files:**
- Modify: `docs/product/02-scenarios.md`

- [ ] **Step 1: Preencher C2 (~150 LOC) seguindo spec §Seção 3 C2**

Substitua `[a preencher na Task 7]` de C2 por: Persona (Marina) + Estado inicial (ticket IN-42100 lembrete de rega) + Estado final + Passos 1-10 (Wave A intake → Wave B PRD+screen → Wave C contracts → Wave D tech-spec+8 tasks → Wave E readiness → implement → verify → auto-retro → forge evolve) + Outcome (~15min Wave A-E + ~4h implement) + Cross-ref pra forge-plan-roteiro + forge-implement-roteiro + 07-discipline.

- [ ] **Step 2: Preencher C3 (~120 LOC) seguindo spec §Seção 3 C3**

Substitua `[a preencher na Task 7]` de C3 por: Persona (Marina P0 stress) + Estado inicial (Crashlytics 12% sessions Android 14 crashando, IN-37234) + Estado final + Passos 1-8 (forge plan IN-37234 detecta ticket-pattern → Cena 2.5 confirma subtype=bugfix → Wave B sub-question UI? → não → wave_b_required=false → Wave A intake-bugfix → preencher → Wave C-D tech-spec stripped + 2 tasks → implement + regression test obrigatório → auto-retro 5-whys) + Outcome (~25min vs ~60min) + Cross-ref pra 04-pending §Gap 1 + planning-conductor.

- [ ] **Step 3: Validar C2 + C3**

```bash
wc -l docs/product/02-scenarios.md
grep -nE "C2 |C3 " docs/product/02-scenarios.md
grep -c "IN-42100\|IN-37234" docs/product/02-scenarios.md
```

Expected: LOC ~430. Cenários C2/C3 identificáveis. Tickets IN-42100 e IN-37234 aparecem.

### Task 8: C4 Retomar pausado + C5 Extension feature (~230 LOC adicionais)

**Files:**
- Modify: `docs/product/02-scenarios.md`

- [ ] **Step 1: Preencher C4 (~100 LOC) seguindo spec §Seção 3 C4**

Substitua `[a preencher na Task 8]` de C4 por: Persona (Marina cold-start) + Estado inicial (Wave D agenda-poda terminou ontem, Ctrl+C, state=deferred) + Estado final + Passos 1-6 (sessão Claude Code nova → forge status → forge plan agenda-poda → engine detecta state=deferred + last-wave=D → auto-resume → conductor "Retomando..." → Wave E readiness=ready → implement) + Outcome (zero retrabalho) + Cross-ref pra 07-discipline §7 + 01-decisions D27.

- [ ] **Step 2: Preencher C5 (~130 LOC) seguindo spec §Seção 3 C5**

Substitua `[a preencher na Task 8]` de C5 por: Persona (Marina) + Estado inicial (lembrete-rega shipped semana passada, PM pede follow-up "lembrete por hora") + Estado final + Passos 1-8 (forge plan lembrete-rega-hora → Cena 1 mostra 4 caminhos incluindo Estender → Marina escolhe Estender + parent=lembrete-rega → validate_extension_feature EXT-001..004 confere → Wave A skipa elicit redundante → Wave B só pergunta delta → Wave C-D-E normais com tech-spec contextualiza parent → implement → status.json grava extends-feature + shipped-at) + Outcome (pattern leve product-derived) + Cross-ref pra 07-discipline §10 + 04-pending §Gap 9 + planning-conductor.

- [ ] **Step 3: Validar C4 + C5**

```bash
wc -l docs/product/02-scenarios.md
grep -nE "C4 |C5 " docs/product/02-scenarios.md
grep -c "agenda-poda\|lembrete-rega" docs/product/02-scenarios.md
```

Expected: LOC ~660. C4/C5 identificáveis. Slugs agenda-poda/lembrete-rega aparecem.

### Task 9: C6 Reuse intelligence (~120 LOC adicional)

**Files:**
- Modify: `docs/product/02-scenarios.md`

- [ ] **Step 1: Preencher C6 (~120 LOC) seguindo spec §Seção 3 C6**

Substitua `[a preencher na Task 9]` de C6 por: Persona (Bruno + Marina) + Estado inicial (squad 18 features, validateName em 15 lugares) + Estado final + Passos 1-7 (Marina planejando feature 19 → Wave B conductor consulta forge graph Q12+Q15 → graph retorna "validateName 15 lugares promove-shared" → conductor sugere PR separado → Marina sim em PR separado → Bruno quinta abre forge evolve → vê 47 proposals filtra promote-to-shared → aceita validateName promotion → Marina mergeia + atualiza .claude/cards/local/) + Outcome (engine detecta + propõe + humano decide) + Cross-ref pra memory-and-graph + graph.md §Q12-Q17.

- [ ] **Step 2: Validar C6**

```bash
grep -n "C6 " docs/product/02-scenarios.md
grep -c "validateName\|Q12\|Q15" docs/product/02-scenarios.md
```

Expected: C6 presente. validateName/Q12/Q15 referenciados.

### Task 10: Wave 2 validate + commit

- [ ] **Step 1: Run validation suite**

```bash
echo "=== LOC ===" && wc -l docs/product/02-scenarios.md
echo "=== TBD/TODO ===" && grep -nE "TBD|TODO|XXX|FIXME|a preencher" docs/product/02-scenarios.md
echo "=== scenarios count ===" && grep -c "^## C[1-6] " docs/product/02-scenarios.md
echo "=== personas referenciadas ===" && grep -cE "Marina|Bruno|Sub-agente Claude" docs/product/02-scenarios.md
```

Expected:
- LOC: 720-820 (range OK pra ~770)
- TBD/TODO: 0
- Scenarios `## C[1-6] `: exatamente 6
- Personas referenciadas: ≥ 15 (Marina aparece em C2/C3/C4/C5/C6; Bruno em C1/C6)

- [ ] **Step 2: Commit atômico Wave 2**

```bash
git add docs/product/02-scenarios.md
git commit -m "$(cat <<'EOF'
docs(product): 02-scenarios wave 2 (6 user journeys end-to-end)

docs/product/02-scenarios.md (~770 LOC) com 6 cenários:

- C1. Brownfield init com reuse-intelligence (Bruno + Marina)
- C2. Feature product nova end-to-end (Marina, IN-42100 lembrete-rega)
- C3. Bugfix com ticket IN-37234 (Marina, P0 Android crash)
- C4. Retomar trabalho pausado (Marina, cold-start)
- C5. Extension feature Gap 9 (Marina, lembrete-rega-hora)
- C6. Reuse intelligence em ação (Bruno + Marina, validateName promotion)

Schema consistente: Persona / Estado in→out / Passos numerados / Outcome
/ Cross-ref pra docs/ux + docs/design relevantes.

Wave 2 de 4 do plano docs/superpowers/plans/2026-06-04-product-docs.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

git log -1 --stat
```

---

## Fase C — Wave 3: 03-roadmap.md (~400 LOC)

### Task 11: Skeleton + §1 Princípios + §2 Onda 1 (~110 LOC)

**Files:**
- Create: `docs/product/03-roadmap.md`
- Read context: `docs/superpowers/specs/2026-06-04-prd-design.md` §Seção 4

- [ ] **Step 1: Render skeleton com 7 seções**

```markdown
# Roadmap-produto do feature-forge

> **Cross-ref:** Este doc é referenciado por [`00-prd.md`](00-prd.md) §7. Complementa [`docs/design/ROADMAP.md`](../design/ROADMAP.md) (lente técnica) com lente produto (ondas agrupadas por outcome de persona). Personas citadas vivem em [`01-personas.md`](01-personas.md).

3 ondas agrupadas por outcome de persona + anti-roadmap explícito + cross-ref bidirecional pro roadmap técnico.

---

## §1 — Princípios do roadmap-produto
[a preencher na Task 11]

## §2 — Onda 1: "Autopilot completo" (v1.3 → v1.4)
[a preencher na Task 11]

## §3 — Onda 2: "Catálogo evolutivo + colaboração" (v1.5 → v2.0)
[a preencher na Task 12]

## §4 — Onda 3: "Inteligência adaptativa" (v2.x — aspiracional)
[a preencher na Task 12]

## §5 — Matriz Eisenhower (persona-impact × esforço)
[a preencher na Task 13]

## §6 — Anti-roadmap (NÃO entrará — explícito com rationale)
[a preencher na Task 13]

## §7 — Cross-ref bidirecional com docs/design/ROADMAP.md técnico
[a preencher na Task 13]
```

- [ ] **Step 2: Preencher §1 Princípios (~30 LOC)**

Lista 5 princípios: Demand-driven / Persona-impact / Backwards-compat (schema migrators via forge raw) / Auditável (CHANGELOG + handoff entries) / Anti-roadmap explícito. Cada um com 1-2 linhas explicando.

- [ ] **Step 3: Preencher §2 Onda 1 (~80 LOC) seguindo spec §Seção 4 Onda 1**

Persona primária impactada (Marina) + Personas secundárias (Carlos/Lucas/Carolina/Sub-agente Claude) + Phase técnico correspondente (Phase 6 Apply Mode) + Outcome esperado + OKRs aspiracionais (time-to-merge ≤4h, manual edits 0, regression rate ≤2%) + Anti-feature explícito (NÃO automatiza decisão produto / NÃO pre-commit review / NÃO IDE plugin).

- [ ] **Step 4: Validar §1+§2**

```bash
wc -l docs/product/03-roadmap.md
grep -nE "^## §[1-2] " docs/product/03-roadmap.md
```

Expected: LOC ~135. §1 e §2 presentes.

### Task 12: §3 Onda 2 + §4 Onda 3 (~170 LOC adicionais)

**Files:**
- Modify: `docs/product/03-roadmap.md`

- [ ] **Step 1: Preencher §3 Onda 2 (~90 LOC) seguindo spec §Seção 4 Onda 2**

Persona primária (Lucas + Bruno) + Personas secundárias (Patricia, Carolina) + Phase técnico (Phase 7 + Gap 5 maturity + multi-dev opcional) + Outcome esperado (preset ios-only, cards iOS standalone, marketplace local maduro, multi-dev opcional, forge status filtros) + OKRs (preset count 1→≥3, cards locais ≥5, multi-dev features ≥10) + Anti-feature explícito (NÃO marketplace pública / NÃO hosted service / NÃO multi-target watchOS).

- [ ] **Step 2: Preencher §4 Onda 3 (~80 LOC) seguindo spec §Seção 4 Onda 3**

Persona afetada (TODAS) + Phase técnico (Phase 7+ + LLM real-time signals) + Outcome esperado (reuse-intel semantic, conductor lembra cross-feature, engine sugere com L2+L3, Carolina forge ensina, Sub-agente confiança histórica) + OKRs aspiracionais (drill-down rounds 2→0.5, questions per Wave A -30%, L2 auto-inject ≥60%) + Anti-feature explícito (NÃO toma decisões sem confirmação / NÃO substitui mentor humano).

- [ ] **Step 3: Validar §3+§4**

```bash
wc -l docs/product/03-roadmap.md
grep -nE "^## §[3-4] " docs/product/03-roadmap.md
grep -c "Onda " docs/product/03-roadmap.md
```

Expected: LOC ~305. §3 e §4 presentes. "Onda" mencionada ≥ 10 vezes.

### Task 13: §5 Eisenhower + §6 Anti-roadmap + §7 Cross-ref (~95 LOC adicionais)

**Files:**
- Modify: `docs/product/03-roadmap.md`

- [ ] **Step 1: Preencher §5 Matriz Eisenhower (~25 LOC) seguindo spec §Seção 4 §5**

Tabela 2x2 (High/Low impact × Low/High effort) + parágrafo explicando porque Onda 1 é "low-effort high-impact relativo".

- [ ] **Step 2: Preencher §6 Anti-roadmap (~40 LOC) seguindo spec §Seção 4 §6**

Tabela com EXATAMENTE 8 linhas: Multi-target watchOS/Wear/TV (out-of-scope permanente Gap 9) / PM scheduling (00-vision §What is NOT) / Code review final automático (humano decide) / Hosted service/SaaS (CLI-first Decision 18+22) / Marketplace pública (viola D22) / Auto-decidir produto/arch (usuário decide) / IDE plugin (CLI-first) / Skill auto-installer cross-project (snapshot via forge init Dec 22). Cada linha: Item | Por quê NÃO | Cross-ref.

- [ ] **Step 3: Preencher §7 Cross-ref bidirecional (~30 LOC) seguindo spec §Seção 4 §7**

Tabela "Onda produto | Phase técnico | Conexão" + lista "Phases técnicos sem onda direta" (Phase 8 MCP, Phase 9 cards reservados, Phase 10 cards legacy, Phase 11 Windows, Phase 12 validators expandidos, Phase 13 marketplace ANTI-ROADMAP).

- [ ] **Step 4: Validar §5+§6+§7**

```bash
wc -l docs/product/03-roadmap.md
grep -nE "^## §[5-7] " docs/product/03-roadmap.md
grep -c "ANTI-ROADMAP\|anti-roadmap" docs/product/03-roadmap.md
```

Expected: LOC ~400. §5/§6/§7 presentes. anti-roadmap referenciado ≥ 3 vezes.

### Task 14: Wave 3 validate + commit

- [ ] **Step 1: Run validation suite**

```bash
echo "=== LOC ===" && wc -l docs/product/03-roadmap.md
echo "=== TBD/TODO ===" && grep -nE "TBD|TODO|XXX|FIXME|a preencher" docs/product/03-roadmap.md
echo "=== sections count ===" && grep -c "^## §" docs/product/03-roadmap.md
echo "=== cross-refs canônicos ===" && grep -cE "ROADMAP\.md|07-discipline|04-pending|01-decisions|00-vision" docs/product/03-roadmap.md
```

Expected:
- LOC: 380-420 (range OK pra ~400)
- TBD/TODO: 0
- Sections `## §`: exatamente 7
- Cross-refs canônicos: ≥ 5

- [ ] **Step 2: Commit atômico Wave 3**

```bash
git add docs/product/03-roadmap.md
git commit -m "$(cat <<'EOF'
docs(product): 03-roadmap wave 3 (3 ondas + Eisenhower + anti-roadmap)

docs/product/03-roadmap.md (~400 LOC) com lente produto do roadmap,
complementar a docs/design/ROADMAP.md técnico:

- §1. Princípios (demand-driven, persona-impact, backwards-compat,
  auditável, anti-roadmap explícito)
- §2. Onda 1 "Autopilot completo" (v1.3→v1.4) — Marina + Phase 6
- §3. Onda 2 "Catálogo evolutivo + colaboração" (v1.5→v2.0) — Lucas +
  Bruno + Phase 7 + Gap 5 maturity
- §4. Onda 3 "Inteligência adaptativa" (v2.x aspiracional) — todas +
  Phase 7+ + LLM real-time
- §5. Matriz Eisenhower (persona-impact × esforço)
- §6. Anti-roadmap (8 items NÃO entrarão com rationale + cross-ref)
- §7. Cross-ref bidirecional com ROADMAP.md técnico

Wave 3 de 4 do plano docs/superpowers/plans/2026-06-04-product-docs.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

git log -1 --stat
```

---

## Fase D — Wave 4: 00-prd.md (~600 LOC)

### Task 15: Skeleton + §1+§2+§3 (~150 LOC)

**Files:**
- Create: `docs/product/00-prd.md`
- Read context: `docs/superpowers/specs/2026-06-04-prd-design.md` §Seção 5

- [ ] **Step 1: Render skeleton com 13 seções**

```markdown
# PRD — feature-forge

> **Audiência:** mantenedor + Claude futuro (interno). Voz mentor calmo PT-BR.
> **Status:** v1.2.0 + Gap 9 cumulativo (637 tests passing, 22 cards canon, 15 validators, 17 graph queries).
> **Cross-ref:** Este é a porta de entrada. Sub-docs: [`01-personas.md`](01-personas.md), [`02-scenarios.md`](02-scenarios.md), [`03-roadmap.md`](03-roadmap.md). Docs técnicos: ver §10.

PRD complementa [`docs/design/00-vision.md`](../design/00-vision.md) (lente arquitetura) com lente produto. Não substitui — coexiste.

---

## §1 — Por que feature-forge existe
[a preencher na Task 15]

## §2 — Vision (lente produto)
[a preencher na Task 15]

## §3 — Princípios não-negociáveis
[a preencher na Task 15]

## §4 — Escopo IN / OUT
[a preencher na Task 16]

## §5 — Personas (resumo)
[a preencher na Task 16]

## §6 — Cenários de uso (resumo)
[a preencher na Task 16]

## §7 — Roadmap produto (resumo)
[a preencher na Task 16]

## §8 — Success criteria & métricas
[a preencher na Task 17]

## §9 — Anti-personas
[a preencher na Task 17]

## §10 — Cross-refs docs técnicos
[a preencher na Task 17]

## §11 — Glossary de termos canon
[a preencher na Task 18]

## §12 — FAQ
[a preencher na Task 18]

## §13 — Risks & Open questions
[a preencher na Task 18]
```

- [ ] **Step 2: Preencher §1 (~50 LOC) seguindo spec §Seção 5 §1**

Problema observado (lista 5 itens) + WHY parágrafo síntese ("Operating system for mobile feature development").

- [ ] **Step 3: Preencher §2 Vision (~40 LOC) seguindo spec §Seção 5 §2**

2-3 parágrafos. Posicionamento CLI-first/file-driven/conversacional. Diferencial técnico: cards atômicos + memory L1/L2/L3 + reuse-intelligence. Promessa: feature N+30 mais rápida que N. Boundary NÃO PM/arquiteto/code reviewer.

- [ ] **Step 4: Preencher §3 Princípios (~60 LOC) seguindo spec §Seção 5 §3**

Lista numerada 1-7: Never invent / Files > Memory / Usuário decide WHAT / Mentor calmo voz / 3-caminhos em qualquer gate violation / Reversibilidade / Persona-native vocabulary. Cada um com 2-3 linhas explicando.

- [ ] **Step 5: Validar §1+§2+§3**

```bash
wc -l docs/product/00-prd.md
grep -nE "^## §[1-3] " docs/product/00-prd.md
grep -c "Never invent\|Files > Memory\|Mentor calmo" docs/product/00-prd.md
```

Expected: LOC ~190. §1/§2/§3 presentes. Princípios identificáveis.

### Task 16: §4 Escopo + §5 Personas + §6 Scenarios + §7 Roadmap (~200 LOC adicionais)

**Files:**
- Modify: `docs/product/00-prd.md`

- [ ] **Step 1: Preencher §4 Escopo IN/OUT (~60 LOC) seguindo spec §Seção 5 §4**

Tabela com EXATAMENTE 13 linhas (categoria | IN | OUT) cobrindo: Lifecycle / Disciplina / Knowledge / Plataformas / Backend / Voz / Subtypes / Reversibilidade / Decisões / Code review / PM / Marketplace / Distribuição / IDE. Onde OUT vazio, usar "—".

- [ ] **Step 2: Preencher §5 Personas (~50 LOC) seguindo spec §Seção 5 §5**

Cada Camada com personas listadas em 1 linha de identidade + link `[Detalhe em 01-personas.md §...]`. 8 personas total (Marina/Bruno/Sub-agente Claude/Carlos/Lucas/Carolina/Patricia/Diego).

- [ ] **Step 3: Preencher §6 Cenários (~50 LOC) seguindo spec §Seção 5 §6**

Lista 6 cenários (C1-C6) com 1-linha outcome + link `[Detalhe em 02-scenarios.md §C{N}]`.

- [ ] **Step 4: Preencher §7 Roadmap (~40 LOC) seguindo spec §Seção 5 §7**

3 ondas (Autopilot/Catálogo/Inteligência) em 1-linha cada + Matriz Eisenhower mini-versão + link `[Detalhe em 03-roadmap.md §...]`.

- [ ] **Step 5: Validar §4+§5+§6+§7**

```bash
wc -l docs/product/00-prd.md
grep -nE "^## §[4-7] " docs/product/00-prd.md
grep -c "01-personas.md\|02-scenarios.md\|03-roadmap.md" docs/product/00-prd.md
```

Expected: LOC ~390. §4-§7 presentes. Cross-refs internos ≥ 6.

### Task 17: §8 Success + §9 Anti-personas + §10 Cross-refs (~170 LOC adicionais)

**Files:**
- Modify: `docs/product/00-prd.md`

- [ ] **Step 1: Preencher §8 Success criteria (~70 LOC) seguindo spec §Seção 5 §8**

Qualitativos por persona (8 frases, uma por persona, do Marina à Sub-agente Claude) + Quantitativos aspiracionais (6 métricas com targets ≤4h/0/≥60%/≤1/≤2 sem/≤2%) + Baseline atual (637 tests, 22 cards, 15 validators, 17 graph queries).

- [ ] **Step 2: Preencher §9 Anti-personas (~50 LOC) seguindo spec §Seção 5 §9**

Tabela com EXATAMENTE 5 linhas (Anti-persona | Por quê não | O que faria sentido pra ela): Flutter/RN / Backend-only não-KMP / PM/designer direto / Squad que rejeita disciplina / Java-only sem Kotlin moderno.

- [ ] **Step 3: Preencher §10 Cross-refs docs técnicos (~50 LOC) seguindo spec §Seção 5 §10**

Tabela canônica com EXATAMENTE 10 linhas (Doc | Lente | Quando consultar): docs/design/00-vision, 01-decisions, 02-phases, 04-pending, 07-discipline, 08-session-handoff, ROADMAP, docs/lifecycle/memory-and-graph, docs/schemas/*, docs/ux/*.

- [ ] **Step 4: Validar §8+§9+§10**

```bash
wc -l docs/product/00-prd.md
grep -nE "^## §[8-9]|^## §10" docs/product/00-prd.md
grep -c "docs/design\|docs/ux\|docs/lifecycle\|docs/schemas" docs/product/00-prd.md
```

Expected: LOC ~560. §8/§9/§10 presentes. Cross-refs canônicos ≥ 10.

### Task 18: §11 Glossary + §12 FAQ + §13 Risks (~230 LOC adicionais)

**Files:**
- Modify: `docs/product/00-prd.md`

- [ ] **Step 1: Preencher §11 Glossary (~80 LOC) seguindo spec §Seção 5 §11**

Tabela com EXATAMENTE 15 termos: Subtype / Wave / Card / Preset / L1 / L2 / L3 / Capability label / Extension feature / Blocked-on-external / Backend-candidate / Reuse-intelligence / Card local overlay / 3-caminhos / Phase lock / Subagent (Claude Code). Cada um: Termo | Definição (1-2 linhas) | Cross-ref pro schema/decision relevante.

- [ ] **Step 2: Preencher §12 FAQ (~70 LOC) seguindo spec §Seção 5 §12**

Tabela com EXATAMENTE 9 perguntas: Por que zero flags / Por que Koin não Hilt / Como migrar de feature-implementation-workflow / Multi-dev mesma feature / watchOS-Wear-TV / Por que não automatiza decisão produto / Java puro funciona / Monorepo / forge implement aplica diff auto. Cada uma: Q | A resumida (2-3 linhas).

- [ ] **Step 3: Preencher §13 Risks & Open questions (~80 LOC) seguindo spec §Seção 5 §13**

Sub-tabela 1: Risks (6 linhas R1-R6) com Risk | Mitigação. Sub-tabela 2: Open questions (4 linhas Q1-Q4) com Q | Status.

- [ ] **Step 4: Validar §11+§12+§13**

```bash
wc -l docs/product/00-prd.md
grep -nE "^## §1[1-3] " docs/product/00-prd.md
grep -c "^| \*\*R[1-6]\.\|^| \*\*Q[1-4]\." docs/product/00-prd.md
```

Expected: LOC ~610-650 (range OK pra ~600 — pode estourar levemente). §11/§12/§13 presentes. R1-R6 + Q1-Q4 todos presentes.

### Task 19: Wave 4 validate + commit

- [ ] **Step 1: Run validation suite completa no 00-prd.md**

```bash
echo "=== LOC ===" && wc -l docs/product/00-prd.md
echo "=== TBD/TODO ===" && grep -nE "TBD|TODO|XXX|FIXME|a preencher" docs/product/00-prd.md
echo "=== sections count ===" && grep -c "^## §" docs/product/00-prd.md
echo "=== cross-refs internos ===" && grep -c "01-personas\.md\|02-scenarios\.md\|03-roadmap\.md" docs/product/00-prd.md
echo "=== cross-refs docs/design ===" && grep -c "docs/design/" docs/product/00-prd.md
echo "=== cross-refs docs/ux ===" && grep -c "docs/ux/" docs/product/00-prd.md
```

Expected:
- LOC: 580-680 (range OK pra ~600, com tolerância)
- TBD/TODO: 0
- Sections `## §`: exatamente 13
- Cross-refs internos: ≥ 6
- Cross-refs docs/design: ≥ 5
- Cross-refs docs/ux: ≥ 1

- [ ] **Step 2: Commit atômico Wave 4**

```bash
git add docs/product/00-prd.md
git commit -m "$(cat <<'EOF'
docs(product): 00-prd wave 4 (porta de entrada, 13 seções)

docs/product/00-prd.md (~600 LOC) — porta de entrada do PRD,
consolidação com cross-refs estáveis pros 3 sub-docs (01-personas,
02-scenarios, 03-roadmap) e pros docs técnicos (00-vision, ROADMAP,
01-decisions, 04-pending, 07-discipline, 08-session-handoff).

13 seções:
- §1. Por que feature-forge existe (problema + WHY)
- §2. Vision (lente produto, complementa 00-vision arquitetural)
- §3. Princípios não-negociáveis (7)
- §4. Escopo IN/OUT (tabela 13 linhas)
- §5. Personas resumo (link 01-personas.md)
- §6. Cenários de uso resumo (link 02-scenarios.md)
- §7. Roadmap produto resumo (link 03-roadmap.md)
- §8. Success criteria & métricas (qualitativos + quantitativos + baseline)
- §9. Anti-personas (5 perfis que NÃO usam o forge)
- §10. Cross-refs docs técnicos (tabela canônica 10 linhas)
- §11. Glossary de termos canon (15 termos)
- §12. FAQ (9 perguntas)
- §13. Risks & Open questions (6 risks + 4 open questions)

Wave 4 de 4 do plano docs/superpowers/plans/2026-06-04-product-docs.md.
Próximo: Fase E doc-sync (CHANGELOG + handoff + README).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

git log -1 --stat
```

---

## Fase E — Doc-sync final

### Task 20: CHANGELOG ### Added 4 docs

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Adicionar entrada em ## [Unreleased] ### Added**

Localize `## [Unreleased]` no CHANGELOG.md. Se existe `### Added` dentro, anexe. Se não, crie `### Added` antes de outras subsessões. Conteúdo:

```markdown
### Added

- **docs/product/** — PRD consolidado do feature-forge com 4 docs (~2370 LOC totais):
  - `00-prd.md` (~600 LOC) — porta de entrada, 13 seções (Por-quê / Vision / Princípios / Escopo IN-OUT / Personas-resumo / Scenarios-resumo / Roadmap-resumo / Success criteria / Anti-personas / Cross-refs docs técnicos / Glossary 15 termos / FAQ 9 perguntas / Risks 6+Open questions 4)
  - `01-personas.md` (~600 LOC) — 8 personas em 3 camadas: Marina (primária) + Bruno + Sub-agente Claude (dedicadas) / Carlos + Lucas + Carolina (variantes Marina) / Patricia + Diego (downstream read-only)
  - `02-scenarios.md` (~770 LOC) — 6 user journeys end-to-end (C1 Brownfield init / C2 Feature product / C3 Bugfix IN-37234 / C4 Retomar pausado / C5 Extension Gap 9 / C6 Reuse intelligence)
  - `03-roadmap.md` (~400 LOC) — 3 ondas (Autopilot v1.3-1.4 / Catálogo evolutivo v1.5-2.0 / Inteligência adaptativa v2.x) + Matriz Eisenhower + Anti-roadmap (8 items NÃO entrarão) + cross-ref bidirecional pro ROADMAP.md técnico
- Spec fonte: `docs/superpowers/specs/2026-06-04-prd-design.md` (commit `2e1a266`).
- Plan executado: `docs/superpowers/plans/2026-06-04-product-docs.md`.
- Coexistência paralela com `docs/design/` (arquitetura) e `docs/ux/` (roteiros) — sem mexer em load-bearing (00-vision.md, ROADMAP.md intactos).
```

### Task 21: 08-session-handoff Última atualização + Estado

**Files:**
- Modify: `docs/design/08-session-handoff.md`

- [ ] **Step 1: Atualizar header**

Localize as 2 primeiras linhas após o disclaimer (atualmente "**Última atualização:** 2026-06-03 (v1.2.0 + Gap 9...)" e "**Estado:** Gap 9 fechado..."). Substitua por:

```markdown
**Última atualização:** 2026-06-04 (v1.2.0 + Gap 9 + PRD docs/product/)
**Estado:** PRD do feature-forge entregue em `docs/product/` — 4 docs (~2370 LOC):
00-prd consolidado (13 seções) + 01-personas (8 personas em 3 camadas: Marina/Bruno/
Sub-agente Claude dedicadas; Carlos/Lucas/Carolina variantes; Patricia/Diego downstream)
+ 02-scenarios (6 user journeys end-to-end) + 03-roadmap (3 ondas Autopilot/Catálogo/
Inteligência + Matriz Eisenhower + anti-roadmap 8 items). Coexiste paralelo com
`docs/design/` (arquitetura) e `docs/ux/` (roteiros) — sem mexer em 00-vision.md
nem ROADMAP.md (load-bearing). Spec: `docs/superpowers/specs/2026-06-04-prd-design.md`
(commit `2e1a266`). Plan: `docs/superpowers/plans/2026-06-04-product-docs.md`.
Anterior (Gap 9): extends-feature mechanic shipado em `feat/gap9-extends-feature`,
pattern leve product-derived. Suite total: **637 tests passing + 12 skipped**.
Próximo: considerar Gap 14 (preset coverage), Onda 1 (Apply Mode = Phase 6 técnico).
```

### Task 22: README pointer pra docs/product/

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Localizar seção §Documentação no README**

Procurar a seção que começa com `## Documentação` (ou equivalente — "Documentation", "Start here"). Adicionar entrada pointing pra `docs/product/00-prd.md` como "porta de entrada do PRD" no TOP da lista.

- [ ] **Step 2: Editar §Documentação**

Adicione ANTES de `- **docs/design/08-session-handoff.md**` a nova entrada:

```markdown
- **`docs/product/00-prd.md`** — PRD consolidado (porta de entrada lente produto; complementa `docs/design/00-vision.md` arquitetural)
```

E adicione no fim da seção (após a última linha existente) um bloco:

```markdown
**PRD sub-docs** (lente produto detalhada):
- `docs/product/01-personas.md` — 8 personas em 3 camadas
- `docs/product/02-scenarios.md` — 6 user journeys end-to-end
- `docs/product/03-roadmap.md` — 3 ondas + Eisenhower + anti-roadmap
```

NÃO mexer no resto do README (stats canônicos, etc.) — docs/product/ é novo eixo, não muda contagem de cards/tests/validators.

### Task 23: Doc-sync atomic commit

- [ ] **Step 1: Validate doc-sync changes**

```bash
git diff --stat -- CHANGELOG.md docs/design/08-session-handoff.md README.md
```

Expected: 3 arquivos modificados, sem outros arquivos.

- [ ] **Step 2: Commit atômico Fase E**

```bash
git add CHANGELOG.md docs/design/08-session-handoff.md README.md
git commit -m "$(cat <<'EOF'
docs(sync): PRD docs/product/ — CHANGELOG + handoff + README baseline

Doc-sync final do PRD docs/product/ entregue em 4 waves:

- CHANGELOG.md ### Added 4 docs em docs/product/ (~2370 LOC totais)
- docs/design/08-session-handoff.md Última atualização + Estado atualizados
- README.md §Documentação ganha pointer pra docs/product/00-prd.md e bloco
  PRD sub-docs (01-personas, 02-scenarios, 03-roadmap)

NÃO mexido (decisão consciente do spec — load-bearing):
- docs/design/00-vision.md (lente arquitetura permanece intacta)
- docs/design/ROADMAP.md (roadmap técnico permanece intacto)
- Stats canônicos do README (cards/tests/validators count) — docs/product/
  é novo eixo, não muda contagem

Closing entrega: 4 commits prévios (wave 1 personas / wave 2 scenarios /
wave 3 roadmap / wave 4 prd) + este doc-sync. Total ~2370 LOC adicionados
em docs/ sem mexer engine/validators/tests/hooks.

Spec: docs/superpowers/specs/2026-06-04-prd-design.md (commit 2e1a266).
Plan: docs/superpowers/plans/2026-06-04-product-docs.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

git log --oneline -6
```

Expected: 6 commits acima do baseline (4 waves + spec + doc-sync). Histórico limpo.

---

## Self-Review (post-write check)

Antes do orchestrator aceitar este plan, run:

1. **Spec coverage:** todas as 9 seções do spec (`docs/superpowers/specs/2026-06-04-prd-design.md`) têm task que implementa? Lista qualquer gap.
2. **Placeholder scan:** grep `TBD|TODO|placeholder|FIXME|a preencher` em todo o plan — só pode aparecer dentro de blocos de instrução pra placeholder remover.
3. **Type/naming consistency:** Marina/Bruno/Sub-agente Claude/Carlos/Lucas/Carolina/Patricia/Diego escritos consistente em tudo? Cenários C1-C6 numerados corretamente? Onda 1/2/3 mantidas?
4. **Task structure:** cada Task tem **Files:** + Steps numerados com checkbox + comandos exatos + expected output quando aplicável?

Se algum check falhar, fix inline antes de declarar plan completo.

---

## Próximos passos pós-plan

1. **Orchestrator review do plan** — leitura crítica + aprovação.
2. **Execution choice** — Subagent-Driven (recommended, fresh subagent per task) OU Inline Execution (executing-plans skill, batch com checkpoints).
3. **Dispatch Fase A** — gsd-executor recebe context-pack com Wave 1 tasks + arquivos permitidos + critério sucesso.
4. **Loop Fase A→B→C→D→E** — cada wave dispatch separado, trust-but-verify entre waves.
