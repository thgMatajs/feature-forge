# W-ROUTE 6a — `forge memory` vira wrapper fino arg-driven (design)

> Sub-design da Onda 6 (W-ROUTE) da Fase 1 (integração mem↔forge). Refina,
> sem contradizer, a spec congelada
> `docs/superpowers/specs/2026-06-25-mem-integration-design.md` (§Superfície
> de comando, §Re-roteamento, §Estratégia de teste). Onde este doc e a spec
> divergirem em detalhe operacional, este doc vence para 6a; onde a spec
> decide arquitetura, a spec vence. Voz: mentor calmo. Data: 2026-06-26.

## O que 6a entrega

Converte o comando `forge memory` — hoje um menu interativo com 7 ações
sobre L1/L2/L3 e carga de checkpoint-resume (DRIFT-1) em
`engine/memory_cli.py` (637 LOC) — num **wrapper fino arg-driven** que
delega ao binário `mem` vendorizado. É o coração da cura estrutural de
BUG-M1: ao não haver mais menu interativo multi-passo, os callsites de
checkpoint-resume desaparecem com o handler antigo.

6a também cria a **camada típica de wrappers** sobre `mem_call()` em
`engine/integrations/mem.py` — o contrato que 6b (evolve/status), 6c
(plan/implement/verify/qa) e W-AGENTS vão estender.

## Decisões de 6a (refinam a spec)

### D1 — Superfície arg-driven, zero `question.ask`

`forge memory` deixa de ser menu interativo e passa a `forge memory <ação>
[args]`. Alinha com o modelo de execução canônico Claude-Code-fronted (o CC
dirige a seleção; o menu via stdin era fallback drift). Clean-break liberado
(pré-produção, sem usuários reais).

| Comando | Delega a |
|---|---|
| `forge memory search <query>` | `mem_find` |
| `forge memory inspect [id]` | `mem_get(id)` se id presente; senão `mem_stats` |
| `forge memory export [--budget N]` | `mem_brief` |
| `forge memory forget <id>` | `mem_supersede` / `mem_evolve --apply` |
| `forge memory distill` | `mem_evolve` + `mem_inbox` |

CLI wiring: subparser argparse com ação posicional em `engine/cli.py:69`
(substitui o registro do menu).

### D2 — Inspeção de lifecycle SAI do `forge memory`

A spec dizia "inspeção de lifecycle fica (lê `.claude/forge/state/`); pode
separar pra `forge status`". 6a resolve: **separa**. `forge memory` passa a
ser puramente o wrapper de memória-de-conhecimento (não mistura mecânica de
lifecycle, respeitando a Divisão de Responsabilidade da spec). A inspeção de
estado de lifecycle pertence ao `forge status` (L1 já migrou pra
`.claude/forge/state/` no W-STATE). `inspect L3` (auto-memory proxy) já sai
removido pela spec.

### D3 — Camada típica compartilhada, só o que 6a usa (YAGNI)

Adiciona a `engine/integrations/mem.py` apenas os wrappers que 6a consome de
fato, cada um parseando `MemResult` → tipo Python e degradando soft (binário
ausente → mensagem 3-caminhos, sem crash):

- `mem_find(query) -> list[hit]`
- `mem_get(id) -> note | None`
- `mem_stats() -> dict`
- `mem_brief(budget=None) -> str`
- `mem_supersede(old_id, new_id)`
- `mem_evolve(apply=False) -> dict`
- `mem_inbox(...)`

6b/6c/W-AGENTS estendem a MESMA camada quando chegarem. Não se criam
wrappers sem consumidor/teste real (evita inchar `mem.py` sem cobertura
comportamental).

### D4 — Prova de BUG-M1: investigar primeiro, decidir com dados

A spec exige TDD red→green sobre BUG-M1; o handoff da sessão anterior
revisou para "provar ausência de estado multi-passo + equivalência, não
caçar sintoma inexistente". 6a reconcilia as duas com **um passo-0 de
investigação time-boxed (~30min, systematic-debugging)**:

1. **Passo 0 — investigação.** Confirmar se há sintoma reproduzível de
   checkpoint-resume defeituoso no `memory_cli.py` ATUAL (resume pulando
   passo / re-prompt duplicado).
2. **Se há repro** → regression test VERMELHO que o captura → refatora →
   verde (caminho spec literal).
3. **Se não há repro** → teste de **ausência estrutural** (0 `question.ask`
   / 0 callsite de checkpoint no módulo reescrito) + **equivalência** (cada
   ação monta o argv `mem` correto), com a ausência de repro DOCUMENTADA
   neste doc (caminho handoff).

A eliminação dos callsites é a hipótese de cura; o teste (de qualquer um dos
dois caminhos) é a prova. Sem prova, não há "curado".

## Estratégia de teste

- **Camada wrapper:** fake-mem-stub (`.claude/bin/mem` que ecoa JSON
  canônico por subcomando) OU monkeypatch de `subprocess.run`. Testar:
  binário ausente → `MemResult(found=False)` + mensagem 3-caminhos (sem
  crash); exit 0 → parse JSON; exit 2 → not-found tratado; timeout →
  fail-soft.
- **Env scrub:** testes que subprocessam herdam `CLAUDECODE`/`OPENCODE_*`/
  `CODEX` — scrub no fixture pra determinismo (reusar padrão já estabelecido
  nos testes de subprocess do forge).
- **Dispatch arg-driven:** assert sobre o argv `mem` montado por ação
  (`search` → `["find", query]`, `export` → `["brief", ...]`, etc.).
- **Prova BUG-M1:** conforme D4.
- Canonical: `.venv/bin/pytest` (tem json5 + deps; system pytest dá false
  fail).

## Footprint de teste (clean-break — escopo expandido declarado)

A memória operacional registra que o cap de 25 test-updates é conservador
demais para clean-break; 6a declara escopo expandido explícito:

- **Remove:** `tests/unit/test_engine_memory_cli_resume.py` (184 LOC) —
  testa o checkpoint-resume que deixa de existir. Remover é correto (testa
  comportamento que some), não regressão.
- **Reescreve:** `tests/unit/test_commands_memory.py` — smoke do dispatcher
  arg-driven (substitui o smoke do menu).
- **Adiciona:** testes da camada wrapper (`mem_find`/`get`/`stats`/`brief`/
  `supersede`/`evolve`/`inbox`) + testes de dispatch (argv por ação) +
  teste-prova de BUG-M1 (D4).

### Footprint observável completo (descoberto via plan-audit r1-r3)

Além de `memory_cli` e seus testes diretos, a reescrita toca o contrato
OBSERVÁVEL em:
- **Removidos** (testam comportamento que some): `test_engine_memory_cli_resume.py`,
  `test_memory_json.py`, e `test_smoke_memory_emits_intent` (em
  `test_callsites_smoke.py`).
- **Atualizados** (asserções estáticas/metadata): `test_subnamespace_paths.py`
  (drop de `memory_cli` da assertion `active_config_path`),
  `test_help_json_manifest.py` + `_COMMAND_META["memory"]`
  (`prompts_by_default` → False, manifest honesto).
- **Contrato preservado** (passam sem mudança após o fix): `test_exit_codes.py`
  e `test_bug_regressions.py` (pre-init → exit 1, garantido por
  `find_project_root()` no topo do `run()`).
- **Fixture:** testes de dispatch monkeypatcham `find_project_root` (ele exige
  marker forge, não basta `.git/`).

Lição: num clean-break rewrite, o footprint de teste é todo teste que assere
o contrato observável (exit codes, intent emission, manifest metadata,
asserções estáticas sobre o source), não só quem importa o módulo. Varrer
por contrato, não por import.

## Doc-sync (mesmo commit da implementação)

- `docs/design/06-command-surface.md` — nova superfície arg-driven de
  `forge memory`.
- `CHANGELOG.md` (Unreleased) — entrada da mudança.
- `README.md` — se a linha de `forge memory` na command surface mudar.
- `docs/guides/daily-workflow.md` (e outros guides que descrevem o menu) —
  atualizar pro fluxo arg-driven.

## Fora de 6a (fica para 6b/6c)

- 6b: `engine/evolve.py` (proposals `kind=promote-to-l2` → `mem inbox add`;
  reuse-estrutural FICA no forge) + `engine/status.py` (L2-size → `mem
  stats`).
- 6c: reads `mem find` por gotchas/convenções em `plan`/`implement`/
  `verify`/`qa` + remoção da escrita em L2 (deferida do W-STATE). WATCH
  OBS-3: `validate_memory.validate()` early-return pass se `memory_dir` não
  existe — vigiar quando L2 sair de `memory/`.

A camada típica de wrappers criada em 6a (D3) é o contrato estável que essas
sub-ondas estendem.
