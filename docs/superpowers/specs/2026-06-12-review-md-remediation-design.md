# REVIEW.md Remediation Plan — Design

**Date:** 2026-06-12
**Author:** orchestrator (mentor calmo)
**Branch:** `fix/review-md-remediation` (baseada em main HEAD `9e8ff4e`)
**Status:** spec — pronto pra writing-plans

---

## Context

`REVIEW.md` na raiz do repo (gerado pelo code-reviewer em 2026-06-11) listou
30 findings classificados em HIGH (10), MEDIUM (12) e LOW (8). Auditoria
contra o estado pós-PR #13 (HEAD `9e8ff4e`) confirmou 22 findings genuínos
e descartou 8 que não são acionáveis:

- **H-05** — já endereçado em PR #9 ultra-review (`engine/_sandbox/env.py`
  contém `SENSITIVE_PATTERN` + flag `allow_sensitive`; o reviewer não viu
  o estado atual).
- **H-08** — `_qa_run` é wrapper thin; a lógica não-trivial vive em
  `run_qa`, já coberta em `tests/engine/test_qa.py`.
- **L-02** — comentários PR-reference são history trace documental do
  projeto (Decision 7 do `01-decisions.md`), não metanarrativa removível.
- **L-05** — log "seguindo pro retrospective sem findings" se refere ao
  ciclo atual do QA, comportamento intencional.
- **L-08** — PEP 649 é debt distante; pyproject pinned em Python 3.11,
  revisitar quando 3.14 ship (sem ação útil agora).
- **M-03** — `_infer_active_feature` já preenche target quando slug vem
  vazio; reviewer leu fluxo parcial.
- **M-06** — `safe_dump` validation YAGNI: dados gravados são todos
  internally-generated (engine produz, engine grava).
- **M-11** — lógica defensiva em `_resolve_slug` já trata o cenário; o
  finding interpretou ambiguamente a interação com `_infer_active_feature`.

Plano é endereçar os 22 findings restantes em **uma branch única**
(`fix/review-md-remediation`) com **um PR**, organizado em **5 blocos
sequenciais risk-first**. Cada bloco fecha com baseline pytest verde e
doc-sync incremental.

---

## Goal

Zerar o débito técnico documentado em `REVIEW.md` ao fim do PR — 22
findings com fix concreto entregue, 8 com mitigation evidence anotada em
`docs/design/04-pending.md`. CHANGELOG + handoff sincronizados. Baseline
pytest preservada (~1178 collected) e ampliada com regression tests pros
fixes de segurança e correctness do Bloco 1 e Bloco 2. Zero behavior
drift fora do escopo dos findings — refactor disciplinado.

---

## Anti-goals (deferred com razão, anotar em `04-pending.md`)

- **H-05 (subprocess env hardening)** — JÁ corrigido no PR #9
  ultra-review. Anotar em `04-pending.md` como `verified-not-needed` pra
  prevenir reabertura em review futura.
- **H-08 (`_qa_run` test gap)** — wrapper thin, lógica em `run_qa` já
  coberta. Anotar como `verified-not-needed` com pointer pra
  `tests/engine/test_qa.py`.
- **L-02 (PR-reference comments)** — trace history documental,
  comportamento desejado per Decision 7. Anotar como `policy-decision`.
- **L-05 (`_maybe_run_qa_pre_retrospective` log message)** —
  comportamento intencional. Anotar como `policy-decision`.
- **L-08 (PEP 649)** — Python 3.14 distante; revisitar quando wheel pin
  vier. Anotar como `monitor-only` com link pra PEP 649 + bump do
  `python_requires`.
- **M-03 (empty slug propagation)** — `_infer_active_feature` já cobre.
  Anotar como `verified-not-needed`.
- **M-06 (`safe_dump` schema validation)** — YAGNI sem caso concreto.
  Anotar como `verified-not-needed`.
- **M-11 (slug resolution edge cases)** — lógica defensiva atual cobre.
  Anotar como `verified-not-needed`.

Decisão: o `04-pending.md` ganha uma seção `## REVIEW.md 2026-06-11 —
itens verificados sem ação` listando esses 8 com 1 linha cada e link pro
finding ID. Isso fecha a triagem sem deixar shadow debt.

---

## Scope — 22 findings em 5 blocos

### Bloco 1 — Security/correctness quick wins (7 findings)

Risk-first: tudo aqui é fix pontual, isolado, com regression test
direto. Fecha primeiro pra reduzir surface durante o PR.

- **H-01** `engine/graph/builder.py:356` — SQL f-string em DELETE.
  Introduz constante `_ALLOWED_TABLES: frozenset[str]` listando as 14
  tabelas válidas; o loop em `_reset_domain_tables` valida `table in
  _ALLOWED_TABLES` antes do execute, raise `ValueError` se ausente.
  Regression test em `tests/engine/graph/test_builder.py`: passar tabela
  fora da allowlist e assertar `ValueError`.
- **H-02** `engine/utils/yaml_io.py:37` — `yaml.safe_load` sem cap.
  Adiciona cap de 10MB no `read_yaml` (ler `path.stat().st_size` antes,
  ou ler texto e checar `len`), raise `YamlIOError` se excedido.
  Regression test em `tests/engine/utils/test_yaml_io.py`: arquivo
  sintético de 11MB → `YamlIOError`.
- **H-04** `engine/graph/builder.py:352-358` — PRAGMA finally pode
  falhar. Envolve o `conn.execute("PRAGMA foreign_keys = ON")` em
  `try/except sqlite3.Error: pass` no finally block. Regression test:
  fechar a conn antes do finally rodar e assertar que a exception
  original (se houver) propaga sem ser mascarada pelo PRAGMA error.
- **H-06** `engine/undo.py` — `shutil.rmtree(feature_dir(...))` sem
  path-traversal guard. Antes do `rmtree`, resolve `target` e
  `project_root`, valida com `target.resolve().is_relative_to(project_root.resolve())`
  (Python 3.9+); raise `ValueError("Refusing to delete path outside
  project")` se falhar. Regression test: slug com `../../etc` → exception.
- **H-07** `engine/persona/mentor_calmo.py:23` — module-level RNG
  mutable. Introduz `_get_rng()` que retorna `_rng_seeded` quando `_seed
  is not None`, senão `random.Random()` fresh. Substitui sites de uso de
  `_rng.choice(...)` por `_get_rng().choice(...)`. Tests existentes
  (`test_mentor_calmo.py`) devem continuar verdes; adicionar test
  cobrindo: seed unset → duas chamadas consecutivas podem retornar
  valores diferentes.
- **H-10 (parcial)** `engine/verify.py:770-771` — validar
  `project_root.is_dir()` antes de `subprocess.run`, retornar
  `_ValidatorResult(..., status="degraded", ...)` se não. A parte do
  finding sobre batch-diff em `_diff.py` (otimização N→1 git
  invocations) NÃO entra neste PR — é optimização, não correctness.
  Anotar em `04-pending.md` como gap separado pra próxima sessão.
  Regression test: project_root apontando pra arquivo (não dir) →
  resultado degraded.

Validation pra Bloco 1: rapid lane verde + nova suíte de regression
tests passando.

### Bloco 2 — Functional bugs (6 findings)

TDD obrigatório: cada bug ganha regression test FALHANDO primeiro,
depois o fix.

- **M-02** `engine/implement.py:344-354` — unknown dep silently
  satisfied. Substitui o `renderer.write(...) → return` por `raise
  SystemExit(f"forge implement: task '{node_id}' declared in
  dependencies does not exist. Fix the dependency reference.")`.
  Regression test: contract YAML com `dependencies: ["TASK-9999"]`
  inexistente → SystemExit com message claro.
- **M-04** `engine/implement.py:179-186` vs `engine/plan.py:444-461` —
  `_feature_path` divergence. Extrai helper compartilhado
  `feature_path(project_root, slug, subtype=None)` em
  `engine/utils/paths.py`. Ambos `implement.py` e `plan.py` importam e
  removem suas versões locais. O subtype é forwarded de `plan.py` (que
  já tem) e `implement.py` ganha a capacidade de encontrar non-product
  features. Regression test: `forge implement` num refactor feature
  (subtype="non-product") resolve corretamente.
- **M-07** `engine/graph/builder.py:181-237` — custom gitignore parser
  com edge cases não cobertos. Substitui por `pathspec` (PyPI lib que
  implementa gitignore semantics canônicas). Adiciona `pathspec >=
  0.12` em `pyproject.toml [project.dependencies]` runtime. CHANGELOG
  `### Changed` documentando a dep nova. Regression test: arquivo
  `.gitignore` com bracket-class `[abc].txt`, escape `\#`, trailing
  space, `a/**/b` → comportamento bate com `git check-ignore`.
- **M-08** `engine/graph/builder.py:294` — glob regex over-match.
  Remove o sufixo `(?:/.*)?` do regex compilado; o handling de
  "directory match implica files inside ignored" sobe pra camada
  acima em `_matches_gitignore`. Em conjunto com M-07 (que delega pra
  `pathspec`), este finding pode acabar resolvido como side-effect; se
  o `_glob_translate` cair junto com o `_parse_gitignore`, anotar no
  commit body e seguir. Regression test: dir `foo.kt/bar.java` NÃO é
  match pra pattern `*.kt`.
- **M-09** `validators/check_no_invented_behavior.py:48-59` —
  reimplementa `git_staged_files`. Substitui `_git_staged_files` local
  por `from _diff import git_staged_files`. Confirma que o filtro por
  extension é compatível com o uso atual (validator filtra `.md`).
  Regression test: rename com `-M80%` ainda é detectado.
- **M-12** `validators/check_secrets.py:120` — `re.search` broad.
  Atualiza `_DEFAULT_IGNORE_PATTERNS` pra prefixar com `(^|/)`:
  `[r"(^|/)tests/fixtures/secrets/"]`. Regression test:
  `src/tests/fixtures/secrets/x.py` (não é tests-root) NÃO é ignored;
  `tests/fixtures/secrets/x.py` (é) é ignored.

Validation pra Bloco 2: rapid lane verde + regression tests novos
verdes + `forge verify` cascade verde.

### Bloco 3 — Type-checker setup (1 finding + 1 sub-finding)

Setup advisory, sem ativar gate em CI ainda.

- **H-09** — adiciona `mypy >= 1.8` em `[project.optional-dependencies]
  dev` no `pyproject.toml`. Cria seção `[tool.mypy]` com config inicial
  conservadora:
  ```toml
  [tool.mypy]
  python_version = "3.11"
  ignore_missing_imports = true
  no_strict_optional = true
  warn_unused_ignores = true
  files = ["engine", "validators"]
  ```
  Roda `mypy engine/ validators/` localmente, registra baseline (count
  de errors atuais) em `docs/design/04-pending.md` numa subseção
  "Mypy rollout baseline". NÃO ativa em CI nesta sessão (advisory mode
  só). Documenta próximas phases (strict rollout per module) como gap
  separado em `04-pending.md`.
- **M-10** — remove `from typing import Optional` em arquivos onde
  não é usado (`engine/implement.py`, `engine/verify.py`,
  `engine/status.py`, `engine/vision/screenshot.py`, e outros que o
  reviewer marcou). Pra cada arquivo: grep por `Optional`, se zero
  uses → remove do import; se há uses, padroniza pra `X | None`
  (consistência intra-arquivo apenas, não cross-codebase).

Validation pra Bloco 3: rapid lane verde + `mypy` roda sem crash
(errors são expected, não falham CI ainda).

### Bloco 4 — Broad except scrub (1 finding mas 67 ocorrências reportadas)

Endereça o coração do H-03. Sub-batch por arquivo, 1 commit por arquivo
(ou por módulo coeso).

- **H-03** — narrow `except Exception` pra tipos documentados.

  **Whitelist (NÃO narrow, mantém com comment justificativa):**
  catches em context-manager `__exit__`, signal handlers, MCP
  boundaries (engine/mcp/), subprocess timeout wrappers — esses são
  defensivos intencionais. Pra cada catch mantido como broad, adicionar
  inline comment `# broad catch: defensive at <boundary>` com a razão.

  **Hot-path priority order:**
  1. `engine/implement.py` (4 sites: 203, 562, 690, 1038)
  2. `engine/verify.py` (2 sites: 281, 487)
  3. `engine/graph/builder.py` (1 site: 597)
  4. `engine/init.py` (6 sites: 1141, 1151, 1157, 1377, 1565, 1684)
  5. `engine/status.py` (1 site: 267)
  6. `engine/doctor.py` (2 sites: 341, 437)
  7. `validators/validate_*.py` (múltiplos — varrer file by file)

  **Narrow target types canônicos (escolher por catch-site):**
  - JSON read → `(json.JSONDecodeError, OSError, UnicodeDecodeError)`
  - YAML read → `(yaml.YAMLError, OSError, UnicodeDecodeError)`
  - Filesystem → `(OSError, FileNotFoundError, PermissionError)`
  - SQLite → `sqlite3.Error`
  - Dict access → `(KeyError, ValueError, TypeError)`
  - Subprocess → `(subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError)`

  Pra cada arquivo: rodar `pytest tests/<modulo>/ -x` após narrow pra
  confirmar zero regressão. Se algum test começar a falhar
  inesperadamente porque dependia do swallow → registrar no commit
  body, decidir caso a caso (provavelmente o test estava errado e
  precisa ser ajustado).

Validation pra Bloco 4: **full suite verde (lane completa)** ao fim do
bloco — H-03 toca paths críticos, rapid lane sozinha não cobre.

### Bloco 5 — Cleanup (7 findings)

Sem risco funcional, fecha o débito cosmético.

- **M-01** `tests/unit/test_commands_implement.py:15-28` — substitui
  `except (RuntimeError, ValueError, OSError, KeyError,
  FileNotFoundError): pass` por assertions sobre exit code ou
  mensagem específica. Se necessário, troca `tmp_project_root` por
  `tmp_forge_project` (fixture com `.claude/`). Mesma cirurgia em
  `tests/unit/test_commands_verify.py` e `tests/unit/test_commands_plan.py`
  se o mesmo anti-padrão estiver lá.
- **M-05** `engine/implement.py:200-201` — remove o `import json`
  interno (já importado no topo do módulo).
- **L-01** `engine/implement.py:404` — remove `del project_root`;
  remove o parâmetro `project_root` da signature da função quando
  não houver mais uso. Atualiza callers.
- **L-03** — consolida `_utc_now_iso_implement`, `_utc_now_iso_plan`,
  `_utc_now_iso_verify` em import direto de
  `engine.utils.iso.utc_now_iso`. Tests que monkeypatcham os shims
  precisam ser ajustados pra monkeypatch `engine.utils.iso.utc_now_iso`
  no path correto (ou no módulo importador).
- **L-04** `engine/implement.py:393-458` — remove parâmetro
  `project_root` dead de `_print_blocked_refusal` e atualiza callers.
- **L-06** `tests/conftest.py:22-23` — substitui `sys.path.insert` por
  dependência em `pip install -e .`. Adiciona nota em `README.md` (ou
  `CONTRIBUTING.md` se vier a existir) sobre o setup local. Se o
  editable install não for viável agora (CI nem usa pip), manter o
  `sys.path.insert` mas adicionar comment inline explicando o porquê
  (e link pra finding L-06 anotado em `04-pending.md`).
- **L-07 (parcial)** — adiciona marker `@pytest.mark.meobonsai` em
  testes que dependem da fixture `meobonsai_root`. Documenta `pytest
  -m "not meobonsai"` em comentário no `pyproject.toml [tool.pytest]`
  e/ou em README. Registra marker novo em `pyproject.toml
  [tool.pytest.ini_options] markers`. Não muda comportamento da
  fixture em si.

Validation pra Bloco 5: full suite verde + `forge verify` + `forge
doctor` todos verdes.

---

## Decisions revisited

- **Decision 19 (language stack = Python core + Bash dispatcher + YAML
  specs)** — NÃO afetada. Adicionar `pathspec` como dep runtime (Bloco
  2 / M-07) NÃO altera o stack canonical: continua Python, continua
  PyPI. `pathspec` é lib pura Python, sem extensão nativa, sem peer
  deps. Entrada em `CHANGELOG.md` `### Changed` documentando a adição.
- **Decision 22 (no runtime deps em outras skills, absorb patterns
  only)** — NÃO afetada. `pathspec` é PyPI lib genérica, não é skill
  do superpowers ou similar. Boundary preservado.

Nenhum revisita formal necessário. Os blocos não tocam
`docs/design/01-decisions.md`, então o hard-block do hook
`pre-commit-feature-forge.sh` não dispara.

---

## Testing strategy

- **Baseline atual (assumido pós-PR #13):** ~1178 tests collected,
  rapid lane ~1054 passing. Antes de começar, rodar `pytest
  --collect-only -q | tail -1` e registrar count exato em
  `08-session-handoff.md` como baseline da sessão.
- **Bloco 1:** rapid lane verde + regression tests novos pra cada fix
  (5 novos arquivos/funções de test estimadas: SQL allowlist, YAML
  cap, PRAGMA recovery, path traversal, mentor RNG, verify
  project_root validation).
- **Bloco 2:** TDD obrigatório — test FALHANDO primeiro pra M-02,
  M-04, M-07/M-08 (em conjunto), M-09, M-12. Rapid lane verde ao fim.
- **Bloco 3:** rapid lane verde. `mypy engine/ validators/` roda mas
  NÃO bloqueia (advisory). Baseline de errors registrado em
  `04-pending.md`.
- **Bloco 4:** **full suite verde** (lane completa) ao fim do bloco
  inteiro — H-03 cruza módulos críticos, rapid lane insuficiente. Pra
  cada arquivo narrow, rodar `pytest tests/<modulo>/ -x` mid-flight
  pra detectar regressão cedo.
- **Bloco 5:** full suite verde + `forge verify` + `forge doctor`
  verdes ao final.
- **Final do PR:** `pytest` full lane verde, `forge verify` cascade
  verde, `forge doctor` 12 categorias verdes. Test count >= baseline
  (espera-se +5 a +10 novos regression tests entre Bloco 1 e Bloco 2).

---

## Doc-sync strategy

Mandamento #6: doc-sync na mesma mudança. Estratégia incremental por
bloco:

- **Fim de cada bloco:** atualizar `CHANGELOG.md` `### Fixed` /
  `### Changed` com bullet por finding endereçado, ID-prefixed
  (`H-01:`, `M-02:`, etc.) pra rastreabilidade.
- **Fim de cada bloco:** bump em `docs/design/08-session-handoff.md`
  campo `**Última atualização:**` com o slug do bloco entregue
  (ex.: `2026-06-12 (REVIEW.md remediation — Bloco 1: security
  quick wins)`).
- **Single update ao final do PR:** `docs/design/04-pending.md` ganha:
  - Seção `## REVIEW.md 2026-06-11 — itens verificados sem ação` (os
    8 anti-goals, 1 linha cada com finding ID + razão).
  - Gap separado: "Batch git-diff optimization em `_diff.py`" (porção
    deferred do H-10).
  - Gap separado: "Mypy strict rollout per module" (próxima phase do
    H-09).
  - Gap separado: "PEP 649 monitor" (L-08).
- **Final do PR:** `README.md` Stats refresh — test count
  (count novo após +N regression tests) + validators count (deve
  continuar 15, sem add) + LOC se mudou significativamente.

Anti-goals com mitigation evidence: anotados em `04-pending.md` como
`verified-not-needed` com link pro finding ID. Isso previne reabertura
em review futuro e fecha a triagem formalmente.

---

## Rollback strategy

- **Atomic commits por finding** — cada finding fechado é 1 commit
  (ou 2: regression test + fix, quando TDD). Revert por finding é
  cherry-pick reverso isolado.
- **Doc-sync incremental ao fim de cada bloco** — se um bloco precisar
  ser revertido inteiro pós-review, o doc-sync correspondente sai
  junto sem desfazer outros blocos.
- **Branch única** — se o PR review pedir split (ex.: "Bloco 4 é
  grande demais, separa"), é viável cherry-pick blocos pra branches
  independentes. Ordem dos blocos foi pensada pra permitir essa
  decomposição: Bloco 1 + 2 são independentes entre si; Bloco 3, 4, 5
  rodam sobre o resultado do 1+2 mas não dependem fortemente da ordem
  interna entre eles.

---

## Open questions

Nenhuma. Spec é determinístico: os 22 findings têm fix concreto, os 8
anti-goals têm razão escrita, baselines e doc-sync estão mapeados.
Writing-plans (próxima skill) traduz isto em tasks numeradas com
critério de sucesso testável por task.
