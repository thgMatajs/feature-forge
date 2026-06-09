# Gate Infrastructure Extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **No-behavior-change** is hard gate — pytest count + check_no_behavior_change validator must pass each commit.

**Goal:** Extrair infraestrutura reusável do CC gate (PR #4 mergeado) em `validators/_gate_infra.py` + `validators/_diff.py` + rename de helpers em `validators/_common.py`, mantendo comportamento idêntico (refactor estrito).

**Architecture:** 7 commits de refactor + 1 commit de doc-sync. Cada commit é atômico, mantém suite verde, mantém `check_no_behavior_change` passando. CC validator pós-refactor cai de ~1127 LOC pra ~600-700 LOC composando os helpers públicos extraídos. Sem aliases backwards-compat (hard rename interno).

**Tech Stack:** Python 3.10+, pytest, refactor-driven. Sem novas deps. Sem novo behavior.

**Reference spec:** [`docs/superpowers/specs/2026-06-04-gate-infra-extract-design.md`](../specs/2026-06-04-gate-infra-extract-design.md) — fonte de verdade. Em conflito spec vs plan, spec vence.

---

## Workflow obrigatório por task

Cada uma das 8 tasks abaixo segue ritual TDD-de-refactor:

1. **Baseline pré-task:** `pytest --collect-only -q | tail -1` (captura count), `pytest tests/validators/test_cc_*.py tests/engine/test_*cc*.py -x` (verde)
2. **Aplicar refactor** descrito na task
3. **Verificação imediata:** `pytest tests/validators/test_cc_*.py tests/engine/test_*cc*.py -x` (deve continuar verde com mesmos asserts; só imports mudam ou substituições internas)
4. **Suite full:** `pytest -m "not integration and not e2e" -q | tail -3` (count idêntico, zero fail novo)
5. **Behavior-change check:** invocar `validators/check_no_behavior_change.py` lógica via test ou direct call confirmando refactor é safe (não muda strings de output, não muda contratos)
6. **Commit atômico** com mensagem exata da task

Se step 3/4/5 falhar: ROLLBACK do commit, investigar, re-tentar. Não improvisar.

---

## Task 1 — Skeleton `_gate_infra.py` + `DispatchResult`

**Files:**
- Create: `validators/_gate_infra.py`
- Modify: `validators/check_cyclomatic_complexity.py` (remove `_DispatchResult` definition; importa de `_gate_infra`)
- Tests: nenhum teste novo (refactor); existing tests cobrindo dispatch DEVEM continuar verdes

Steps:
- [ ] Step 1: Baseline pré-task — `pytest --collect-only -q | tail -1` (anota count), `pytest tests/validators/test_cc_dispatch.py tests/validators/test_check_cyclomatic_complexity.py -x` (verde)
- [ ] Step 2: Create `validators/_gate_infra.py` com módulo docstring + skeleton:
  ```python
  """Reusable gate infrastructure — extracted from CC gate (PR #4) per Phase 0
  of quality-gates expansion. See docs/superpowers/specs/2026-06-04-gate-infra-
  extract-design.md.

  Helpers here are gate-agnostic: dispatch to native CLI tools, parse override-
  justify lines in commit body, render config templates with placeholders.
  Used by check_cyclomatic_complexity and (planned) check_secrets, check_deps_cve,
  check_duplication, check_cognitive_complexity, check_dead_code, check_arch_rules,
  check_function_length_and_nesting.
  """

  from __future__ import annotations
  from dataclasses import dataclass


  @dataclass(frozen=True)
  class DispatchResult:
      """Outcome of dispatching a native CLI tool (gate-agnostic).

      Contract: caller filtra por `tool_found` / `crashed` antes de consumir
      `raw_stdout`. Campos idênticos ao `_DispatchResult` original do CC gate
      (rename só remove o underscore).
      """
      language: str
      tool_found: bool
      crashed: bool
      raw_stdout: str
      error_message: str
  ```
- [ ] Step 3: Em `check_cyclomatic_complexity.py`:
  - REMOVE `@dataclass(frozen=True) class _DispatchResult:` + corpo (linhas ~330-348)
  - ADD import no bloco de imports do topo:
    ```python
    from _gate_infra import DispatchResult
    ```
  - Substituir TODAS as referências internas `_DispatchResult` → `DispatchResult` (3 ocorrências em `_dispatch_tool`: lines ~403, ~488, ~506, ~514, ~526, ~535)
- [ ] Step 4: Verificação imediata — `pytest tests/validators/test_cc_dispatch.py tests/validators/test_check_cyclomatic_complexity.py -xvs` → PASS, asserts inalterados
- [ ] Step 5: Suite full — `pytest -m "not integration and not e2e" -q | tail -3` → count idêntico baseline, zero fail novo
- [ ] Step 6: Commit atômico:
  ```
  refactor(validators): _gate_infra.py skeleton + DispatchResult
  ```

---

## Task 2 — Extract `check_tool_available`

**Files:**
- Modify: `validators/_gate_infra.py` (APPEND)
- Modify: `validators/check_cyclomatic_complexity.py` (remove `_check_tool_available`; importa de `_gate_infra`)

Steps:
- [ ] Step 1: Baseline pré-task (count + tests verdes)
- [ ] Step 2: APPEND em `_gate_infra.py`:
  ```python
  import shutil


  def check_tool_available(tool: str) -> bool:
      """Return True iff `tool` is on PATH (uses shutil.which).

      Não tenta executar — apenas PATH lookup. Tool crash em runtime é tratado
      separadamente em `dispatch_native_tool`.
      """
      return shutil.which(tool) is not None
  ```
- [ ] Step 3: Em `check_cyclomatic_complexity.py`:
  - REMOVE `def _check_tool_available(tool: str) -> bool:` + corpo (linhas ~351-357)
  - Atualizar import existente:
    ```python
    from _gate_infra import DispatchResult, check_tool_available
    ```
  - Substituir referência interna em `_dispatch_tool` (linha ~402): `_check_tool_available(tool)` → `check_tool_available(tool)`
  - Remover `import shutil` do topo SE não restou outro uso (verificar com grep — `shutil.which` aparecia só em `_check_tool_available`)
- [ ] Step 4: Verificação imediata — `pytest tests/validators/test_cc_dispatch.py tests/validators/test_check_cyclomatic_complexity.py -xvs`
- [ ] Step 5: Suite full count check
- [ ] Step 6: Commit:
  ```
  refactor(validators): extract check_tool_available to _gate_infra
  ```

---

## Task 3 — Extract `render_config_with_placeholders` (generaliza)

**Files:**
- Modify: `validators/_gate_infra.py` (APPEND)
- Modify: `validators/check_cyclomatic_complexity.py` (remove `_render_config_for_threshold` + constante `_CC_THRESHOLD_PLACEHOLDER`; adapt 2 callsites)

Steps:
- [ ] Step 1: Baseline
- [ ] Step 2: APPEND em `_gate_infra.py`:
  ```python
  import os
  import tempfile
  from pathlib import Path


  def render_config_with_placeholders(
      template_path: Path,
      placeholders: dict[str, str],
  ) -> str:
      """Render config template to a tempfile, substituindo placeholders.

      Generaliza `_render_config_for_threshold` do CC gate. Caller passa dict
      tipo `{"__CC_THRESHOLD__": "10"}`; função aplica `raw.replace(k, v)` para
      cada par e escreve o resultado num tempfile. Devolve o path do tempfile;
      caller é responsável pelo cleanup (padrão try/finally).

      Tools que aceitam threshold via CLI passam `placeholders={}` (no-op render
      mantendo o template literal) ou nem chamam esta função.
      """
      raw = template_path.read_text(encoding="utf-8")
      for placeholder, value in placeholders.items():
          raw = raw.replace(placeholder, value)
      tmp = tempfile.NamedTemporaryFile(
          mode="w",
          suffix=template_path.suffix,
          delete=False,
          encoding="utf-8",
      )
      tmp.write(raw)
      tmp.close()
      return tmp.name
  ```
- [ ] Step 3: Em CC validator:
  - REMOVE `_CC_THRESHOLD_PLACEHOLDER = "__CC_THRESHOLD__"` (linha ~360)
  - REMOVE `def _render_config_for_threshold(...)` + corpo (linhas ~363-377)
  - Atualizar import:
    ```python
    from _gate_infra import DispatchResult, check_tool_available, render_config_with_placeholders
    ```
  - Adaptar 2 callsites em `_dispatch_tool` (kotlin + swift branches). Padrão:

    Antes (kotlin, linhas ~423-435):
    ```python
    rendered_config = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yml", prefix="detekt-cc-", delete=False, encoding="utf-8",
    ).name
    Path(rendered_config).write_text(
        _render_config_for_threshold(_CONFIG_DIR / "detekt.yml", threshold),
        encoding="utf-8",
    )
    ```

    Depois:
    ```python
    rendered_config = render_config_with_placeholders(
        _CONFIG_DIR / "detekt.yml",
        {"__CC_THRESHOLD__": str(threshold)},
    )
    ```

    Mesma substituição pro swift branch (linhas ~446-458), template `swiftlint.yml`.
  - O `try/finally` que faz `os.unlink(rendered_config)` permanece — semântica idêntica.
- [ ] Step 4: `pytest tests/validators/test_cc_dispatch.py tests/validators/test_check_cyclomatic_complexity.py -xvs` (asserts sobre `--config <path>` continuam batendo)
- [ ] Step 5: Suite full
- [ ] Step 6: Commit:
  ```
  refactor(validators): extract render_config_with_placeholders to _gate_infra
  ```

---

## Task 4 — Extract `dispatch_native_tool` (parameteriza cmd_builder)

**Files:**
- Modify: `validators/_gate_infra.py` (APPEND)
- Modify: `validators/check_cyclomatic_complexity.py` (remove `_dispatch_tool`; adiciona 4 cmd_builder lambdas locais; adapta `_run_tools_for_staged`)

Steps:
- [ ] Step 1: Baseline
- [ ] Step 2: APPEND em `_gate_infra.py`:
  ```python
  import subprocess
  from collections.abc import Callable
  from typing import Optional


  def dispatch_native_tool(
      *,
      language: str,
      files: list[str],
      cmd_builder: Callable[[str, list[str], Optional[str]], list[str]],
      project_root: Path,
      tool_bin: str,
      config_template: Optional[Path] = None,
      placeholders: Optional[dict[str, str]] = None,
      timeout: int = 60,
      benign_nonzero_codes: tuple[int, ...] = (),
  ) -> DispatchResult:
      """Generic dispatcher pra tools nativas (detekt/swiftlint/eslint/radon
      pattern; futuro: gitleaks, trufflehog, osv-scanner, jscpd, etc.).

      Renderiza config a tempfile se `config_template` + `placeholders` foram
      passados; constrói o cmd via `cmd_builder(tool_bin, files, rendered_config)`;
      roda subprocess; devolve DispatchResult. Cleanup do tempfile garantido no
      finally. `benign_nonzero_codes` cobre o caso eslint exit=1 normal sem
      hard-code de linguagem aqui.

      Contrato (mesmo do `_dispatch_tool` original):
        - tool ausente em PATH → tool_found=False (sem execução).
        - timeout / OSError → crashed=True + error_message descritivo.
        - exit != 0 (exceto benign_nonzero_codes) → crashed=True + stderr snippet.
        - exit == 0 (ou benign) → raw_stdout entregue ao caller.
      """
      if not check_tool_available(tool_bin):
          return DispatchResult(
              language=language,
              tool_found=False,
              crashed=False,
              raw_stdout="",
              error_message=f"{tool_bin} not installed (PATH lookup failed)",
          )

      rendered_config: Optional[str] = None
      try:
          if config_template is not None:
              rendered_config = render_config_with_placeholders(
                  config_template, placeholders or {}
              )

          cmd = cmd_builder(tool_bin, files, rendered_config)

          try:
              proc = subprocess.run(
                  cmd,
                  cwd=str(project_root),
                  capture_output=True,
                  text=True,
                  timeout=timeout,
                  check=False,
              )
          except subprocess.TimeoutExpired:
              return DispatchResult(
                  language=language, tool_found=True, crashed=True,
                  raw_stdout="", error_message=f"{tool_bin} timeout (>{timeout}s)",
              )
          except OSError as exc:
              return DispatchResult(
                  language=language, tool_found=True, crashed=True,
                  raw_stdout="", error_message=f"{tool_bin} OS error: {exc}",
              )

          benign = proc.returncode in benign_nonzero_codes
          if proc.returncode != 0 and not benign:
              return DispatchResult(
                  language=language, tool_found=True, crashed=True,
                  raw_stdout=proc.stdout or "",
                  error_message=(proc.stderr or "").strip()[:400]
                      or f"{tool_bin} exit={proc.returncode}",
              )

          return DispatchResult(
              language=language, tool_found=True, crashed=False,
              raw_stdout=proc.stdout or "", error_message="",
          )
      finally:
          if rendered_config:
              try:
                  os.unlink(rendered_config)
              except OSError:
                  pass  # best-effort cleanup, mesma semântica do original
  ```
- [ ] Step 3: Em CC validator:
  - REMOVE `def _dispatch_tool(...)` + corpo (linhas ~380-549 inclusive try/finally)
  - Atualizar import:
    ```python
    from _gate_infra import (
        DispatchResult, check_tool_available,
        dispatch_native_tool, render_config_with_placeholders,
    )
    ```
  - Adicionar 4 cmd_builders como funções de módulo (ou lambdas dentro de `_run_tools_for_staged` — preferir funções com nome pra grep/test):
    ```python
    def _build_detekt_cmd(tool_bin: str, files: list[str], config_path: str | None) -> list[str]:
        return [
            tool_bin, "--input", ",".join(files),
            "--config", str(config_path),
            "--report", "json:-",
        ]


    def _build_swiftlint_cmd(tool_bin: str, files: list[str], config_path: str | None) -> list[str]:
        return [
            tool_bin, "lint",
            "--reporter", "json",
            "--config", str(config_path),
            *files,
        ]


    def _build_eslint_cmd_factory(threshold: int):
        def _build(tool_bin: str, files: list[str], config_path: str | None) -> list[str]:
            return [
                tool_bin,
                "--no-eslintrc",
                "--rule", f'{{"complexity": ["error", {{"max": {threshold}}}]}}',
                "--format", "json",
                *files,
            ]
        return _build


    def _build_radon_cmd(tool_bin: str, files: list[str], config_path: str | None) -> list[str]:
        return [tool_bin, "cc", "-j", "-n", "A", *files]
    ```
  - Reescrever o branch `_run_tools_for_staged` (que hoje chama `_dispatch_tool`) pra usar `dispatch_native_tool` per linguagem:
    ```python
    for lang, files in files_by_lang.items():
        if not files:
            continue
        threshold = thresholds_by_lang.get(lang, 10)
        tool_bin = _TOOL_BIN[lang]
        if lang == "kotlin":
            d = dispatch_native_tool(
                language=lang, files=files,
                cmd_builder=_build_detekt_cmd,
                project_root=project_root, tool_bin=tool_bin,
                config_template=_CONFIG_DIR / "detekt.yml",
                placeholders={"__CC_THRESHOLD__": str(threshold)},
            )
        elif lang == "swift":
            d = dispatch_native_tool(
                language=lang, files=files,
                cmd_builder=_build_swiftlint_cmd,
                project_root=project_root, tool_bin=tool_bin,
                config_template=_CONFIG_DIR / "swiftlint.yml",
                placeholders={"__CC_THRESHOLD__": str(threshold)},
            )
        elif lang == "ts":
            d = dispatch_native_tool(
                language=lang, files=files,
                cmd_builder=_build_eslint_cmd_factory(threshold),
                project_root=project_root, tool_bin=tool_bin,
                benign_nonzero_codes=(1,),
            )
        elif lang == "python":
            d = dispatch_native_tool(
                language=lang, files=files,
                cmd_builder=_build_radon_cmd,
                project_root=project_root, tool_bin=tool_bin,
            )
        else:
            continue
        # resto do loop inalterado (warnings, parsers, classify, append)
    ```
  - Remover `import tempfile`, `import os`, `import subprocess` do topo do CC validator SE não restou outro uso (verificar com grep — `os.unlink`, `tempfile.NamedTemporaryFile` e `subprocess.run` viviam só dentro de `_dispatch_tool` + helpers diff-mode que ficam por enquanto). Cuidado: `subprocess` segue sendo usado por `_git_staged_files`, `_extract_diff_hunks`, `_read_commit_body` — esses só saem na Task 6. Portanto `subprocess` NÃO é removido nesta task; `tempfile` e `os.unlink` SÃO removíveis do topo (já só viviam em `_dispatch_tool`).
- [ ] Step 4: `pytest tests/validators/test_cc_dispatch.py tests/validators/test_check_cyclomatic_complexity.py -xvs` — asserts sobre command lines, tool-not-found, crash, timeout devem continuar batendo. Asserts em ordem de cmd args, formato JSON e error message prefixes são contrato — qualquer diff aqui é red flag.
- [ ] Step 5: Suite full count check
- [ ] Step 6: Commit:
  ```
  refactor(validators): extract dispatch_native_tool to _gate_infra
  ```

---

## Task 5 — Extract `parse_overrides` + `apply_overrides` (generaliza prefix/key)

**Files:**
- Modify: `validators/_gate_infra.py` (APPEND)
- Modify: `validators/check_cyclomatic_complexity.py` (remove `_parse_overrides`, `_apply_overrides`, regex `_CC_OVERRIDE_RE` e `_CC_OVERRIDE_LOOSE_RE`; adapta `validate()`)
- Tests: `tests/validators/test_cc_override.py` deve continuar verde sem mudar asserts (só wiring interno do gate muda)

Steps:
- [ ] Step 1: Baseline (`pytest tests/validators/test_cc_override.py -xvs` verde)
- [ ] Step 2: APPEND em `_gate_infra.py`:
  ```python
  import re
  from typing import Any


  def parse_overrides(
      commit_body: str,
      *,
      prefix: str,
      key_fields: list[str],
      return_warnings: bool = False,
  ):
      """Parse `<PREFIX>: <field1> <field2> ... — <razão>` lines from commit body.

      Generaliza `_parse_overrides` do CC gate. Caller passa `prefix` (ex:
      "CC-OVERRIDE", "SECRETS-OVERRIDE") + `key_fields` (nomes que aparecem
      entre `:` e `—`, ex: `["file", "func", "cc"]`).

      Pra cada `key_fields`, o regex casa um grupo nomeado:
        - "file" → `(?P<file>\\S+)` precedido de espaço
        - "func" → casado como `:func` continuando do file (file:func pattern)
        - outros campos → `<name>=<value>` (ex: `cc=12`)
      Caller que precisar shape diferente passa lista alinhada à expectativa
      do gate. CC gate específico: o regex resultante reproduz exatamente os
      dois regex hoje em check_cyclomatic_complexity (strict + loose).

      Returns:
        list[dict] quando `return_warnings=False` (default), ou
        tuple[list[dict], list[str]] (overrides, warnings) quando True.
        Warnings cobrem linhas que CASAM o prefixo mas faltam ` — <razão>`.
      """
      # Implementação interna: compila strict + loose pattern parametrizados em
      # `prefix` e nos `key_fields`, replicando exatamente o comportamento dos
      # regex originais (file:func pattern + cc=N pattern + " — " trailing).
      # Casos D-008 (tail vazio após em-dash) preservados.
      # ... [corpo equivalente a _parse_overrides original, com PREFIX vindo do arg]


  def apply_overrides(
      fails: list[Any],
      commit_body: str,
      *,
      prefix: str,
      key_fields: list[str],
      key_extractor: Callable[[Any], tuple],
  ) -> tuple[list[Any], list[Any], list[str]]:
      """Split fails into (silenced, surviving, warnings) usando override lines.

      `key_extractor(fail)` retorna a tupla comparável que casa contra a chave
      tuple do override. CC gate passa `lambda f: (f.file, f.function)`; secrets
      vai passar `lambda f: (f.file, f.line)`; cada gate define o key tuple.

      `prefix` + `key_fields` repassados pro `parse_overrides` interno. Match
      cover: dicts retornados por `parse_overrides` viram chaves via
      `tuple(override[k] for k in key_fields if k in cover_keys)` — caller
      passa apenas os campos que compõem identidade (ex: CC usa `["file", "func"]`
      como cover_keys, mesmo que key_fields completo seja `["file", "func", "cc"]`).
      """
      # Implementação interna: chama parse_overrides com return_warnings=True;
      # constrói set de cover keys via key_extractor das overrides parseadas;
      # itera fails particionando em silenced/surviving.
      # ... [corpo equivalente a _apply_overrides, com prefix/key_fields/key_extractor parametrizados]
  ```

  Nota técnica: a forma exata do regex parametrizado deve reproduzir BYTE A BYTE os dois regex originais quando chamado com `prefix="CC-OVERRIDE"`, `key_fields=["file", "func", "cc"]`. Snapshot test contra os dois regex literais é boa salvaguarda durante o desenvolvimento (test pode ser deletado depois se redundante).
- [ ] Step 3: Em CC validator:
  - REMOVE `_CC_OVERRIDE_RE` + `_CC_OVERRIDE_LOOSE_RE` (linhas ~565-573)
  - REMOVE `def _parse_overrides(...)` + corpo (linhas ~576-639)
  - REMOVE `def _apply_overrides(...)` + corpo (linhas ~642-670)
  - Atualizar import:
    ```python
    from _gate_infra import (
        DispatchResult, apply_overrides, check_tool_available,
        dispatch_native_tool, parse_overrides, render_config_with_placeholders,
    )
    ```
  - Adicionar key_extractor local + adaptar callsite em `validate()` (linha ~1045):
    ```python
    def _cc_key_extractor(fail: CCResult) -> tuple[str, str]:
        return (fail.file, fail.function)


    # Antes
    # silenced, surviving, override_warnings = _apply_overrides(fails, commit_body)

    # Depois
    silenced, surviving, override_warnings = apply_overrides(
        fails, commit_body,
        prefix="CC-OVERRIDE",
        key_fields=["file", "func", "cc"],
        key_extractor=_cc_key_extractor,
    )
    ```
  - Remover `import re` do topo SE não restou outro uso. Cuidado: `re.search`/`re.compile` segue sendo usado em `_compile_ignore_patterns`, `_path_matches_ignore`, `_extract_diff_hunks`, `_DETEKT_FUNC_RE`, `_SWIFTLINT_FUNC_RE`, `_ESLINT_FUNC_RE` — `re` continua importado.
- [ ] Step 4: `pytest tests/validators/test_cc_override.py -xvs` (asserts sobre overrides parseados, warnings malformados D-008, key cover via file+func, todos inalterados)
- [ ] Step 5: Suite full count check
- [ ] Step 6: Commit:
  ```
  refactor(validators): extract parse_overrides + apply_overrides to _gate_infra
  ```

---

## Task 6 — Create `_diff.py` com DiffHunk + helpers

**Files:**
- Create: `validators/_diff.py`
- Modify: `validators/check_cyclomatic_complexity.py` (remove `classify_function`, `_git_staged_files`, `_extract_diff_hunks`, `_read_commit_body`; adapta 3 callsites em `_run_tools_for_staged` e `validate()`)

Steps:
- [ ] Step 1: Baseline (`pytest tests/validators/test_cc_classifier.py -xvs` se existir, + `test_check_cyclomatic_complexity.py`)
- [ ] Step 2: Create `validators/_diff.py`:
  ```python
  """Diff-mode helpers — extracted from CC gate per Phase 0.

  Usados por qualquer gate que precise limitar análise a staged files / diff
  hunks, ou classificar ranges como new/modified/unchanged vs HEAD.
  """

  from __future__ import annotations

  import re
  import subprocess
  from dataclasses import dataclass
  from pathlib import Path


  @dataclass(frozen=True)
  class DiffHunk:
      """Range de linhas com classificação de diff side.

      `kind` é "add" por enquanto (único valor emitido pelo extractor — capta o
      lado `+` do diff). Futuros gates podem estender pra "del"/"ctx" se
      precisarem do raciocínio simétrico.
      """
      start: int
      end: int
      kind: str


  def classify_range_against_hunks(
      func_range: tuple[int, int],
      diff_hunks: list[DiffHunk],
  ) -> str:
      """Return "new" | "modified" | "unchanged".

      Regras (per CC spec §2 step 9, preservadas):
        - "new"       — func_range inteiro contido num add hunk
        - "modified"  — func_range intersecta qualquer hunk
        - "unchanged" — sem overlap
      """
      if not diff_hunks:
          return "unchanged"
      f_start, f_end = func_range
      add_hunks = [h for h in diff_hunks if h.kind == "add"]
      for h in add_hunks:
          if h.start <= f_start and h.end >= f_end:
              return "new"
      for h in diff_hunks:
          if h.start <= f_end and h.end >= f_start:
              return "modified"
      return "unchanged"


  def extract_diff_hunks(
      project_root: Path,
      files: list[Path],
  ) -> dict[str, list[DiffHunk]]:
      """Parse `git diff --cached -U0` per file; retorna list[DiffHunk] por rel path."""
      by_file: dict[str, list[DiffHunk]] = {}
      for f in files:
          try:
              rel = str(f.relative_to(project_root))
          except ValueError:
              continue
          try:
              proc = subprocess.run(
                  ["git", "-C", str(project_root), "diff", "--cached", "-U0", "--", rel],
                  check=False, capture_output=True, text=True, timeout=10,
              )
          except (subprocess.SubprocessError, OSError):
              by_file[rel] = []
              continue
          hunks: list[DiffHunk] = []
          for line in proc.stdout.splitlines():
              if not line.startswith("@@"):
                  continue
              m = re.search(r"\+(\d+)(?:,(\d+))?", line)
              if not m:
                  continue
              start = int(m.group(1))
              length = int(m.group(2)) if m.group(2) else 1
              hunks.append(DiffHunk(
                  start=start, end=start + max(length - 1, 0), kind="add",
              ))
          by_file[rel] = hunks
      return by_file


  def git_staged_files(
      project_root: Path,
      *,
      extensions: set[str] | None = None,
  ) -> list[Path]:
      """Lista staged files (opcionalmente filtra por suffix set).

      Preserva o `-M80%` rename detection do original — função renomeada (até
      20% de mudança) classifica como "modified" pelo delta rule, não como
      "new" + delete. Sem `extensions`, devolve todos os arquivos staged.
      """
      try:
          out = subprocess.run(
              ["git", "-C", str(project_root), "diff", "--cached", "-M80%", "--name-only"],
              check=False, capture_output=True, text=True, timeout=10,
          )
      except (subprocess.SubprocessError, OSError):
          return []
      if out.returncode != 0:
          return []
      files: list[Path] = []
      for line in out.stdout.splitlines():
          line = line.strip()
          if not line:
              continue
          p = project_root / line
          if not p.is_file():
              continue
          if extensions is not None and p.suffix not in extensions:
              continue
          files.append(p)
      return files


  def read_commit_body(project_root: Path) -> str:
      """Best-effort read do commit body: `.git/COMMIT_EDITMSG` → `git log -1 --format=%B`."""
      editmsg = project_root / ".git" / "COMMIT_EDITMSG"
      if editmsg.is_file():
          try:
              return editmsg.read_text(encoding="utf-8", errors="replace")
          except OSError:
              pass
      try:
          proc = subprocess.run(
              ["git", "-C", str(project_root), "log", "-1", "--format=%B"],
              check=False, capture_output=True, text=True, timeout=5,
          )
          if proc.returncode == 0:
              return proc.stdout
      except (subprocess.SubprocessError, OSError):
          pass
      return ""
  ```
- [ ] Step 3: Em CC validator:
  - REMOVE `def classify_function(...)` + corpo (linhas ~78-109)
  - REMOVE `def _git_staged_files(...)` + corpo (linhas ~705-736)
  - REMOVE `def _extract_diff_hunks(...)` + corpo (linhas ~739-780)
  - REMOVE `def _read_commit_body(...)` + corpo (linhas ~783-812)
  - ADD import:
    ```python
    from _diff import (
        DiffHunk, classify_range_against_hunks,
        extract_diff_hunks, git_staged_files, read_commit_body,
    )
    ```
  - Substituir callsites:
    - `_git_staged_files(project_root)` → `git_staged_files(project_root, extensions=set(SUPPORTED_EXTENSIONS))` em `validate()` linha ~975
    - `_extract_diff_hunks(project_root, staged_paths)` → `extract_diff_hunks(project_root, staged_paths)` em `validate()` linha ~1023
    - `_read_commit_body(project_root)` → `read_commit_body(project_root)` em `validate()` linha ~1044
    - `classify_function((r.line_start, r.line_end), hunks)` em `_run_tools_for_staged` linha ~938 → `classify_range_against_hunks((r.line_start, r.line_end), hunks)`
  - **Atenção shape mudou**: `extract_diff_hunks` agora devolve `list[DiffHunk]` em vez de `list[dict]`. Qualquer código que acessava `h["start"]`/`h["end"]`/`h["kind"]` no CC validator vira `h.start`/`h.end`/`h.kind`. Confirmar com grep — pode haver consumidores além do classify (a busca limita a `_run_tools_for_staged`). `classify_range_against_hunks` já lê via dataclass attrs.
  - Remover `import subprocess` do CC validator topo SE não restou outro uso (verificar — depois desta task, `subprocess.run` saiu junto com os 3 git helpers; deve ser removível).
- [ ] Step 4: `pytest tests/validators/test_cc_classifier.py tests/validators/test_check_cyclomatic_complexity.py tests/integration/test_implement_cc_gate.py -xvs`. Snapshot tests sobre status (new/modified/unchanged) inalterados.
- [ ] Step 5: Suite full count check
- [ ] Step 6: Commit:
  ```
  refactor(validators): create _diff.py with DiffHunk + helpers
  ```

---

## Task 7 — Rename helpers em `_common.py`

**Files:**
- Modify: `validators/_common.py` (rename `cc_threshold_lookup`, `cc_format_three_paths`; `DEFAULTS_CC` mantém)
- Modify: `validators/check_cyclomatic_complexity.py` (atualiza imports + callsites)
- Modify: `tests/validators/test_common_cc_helpers.py` (atualiza imports + chamadas; asserts inalterados)
- Modify: `engine/implement.py` (comentário linha 501)
- Modify: `tests/engine/test_implement_cc_gate.py` (comentário linha 130)

Steps:
- [ ] Step 1: Baseline + grep `cc_threshold_lookup\|cc_format_three_paths` cobre todos os callsites:
  ```bash
  grep -rn "cc_threshold_lookup\|cc_format_three_paths" validators/ engine/ tests/ docs/
  ```
- [ ] Step 2: Em `validators/_common.py`:
  - Rename `def cc_threshold_lookup(language, active_cards, workflow_config)` → `def gate_threshold_lookup(language, active_cards, workflow_config, *, card_override_key="cc-gate-override", workflow_block_key="cc-gate", defaults=None)`.
    - Adiciona os novos kwargs com defaults que preservam comportamento atual.
    - `defaults=None` → usa `DEFAULTS_CC` (gate atual). Outros gates passarão `defaults=DEFAULTS_SECRETS` etc. quando existirem.
    - Substituir referências internas: `card.get("cc-gate-override")` → `card.get(card_override_key)`; `workflow_config.get("cc-gate")` → `workflow_config.get(workflow_block_key)`; `DEFAULTS_CC` (lookup final) → `defaults if defaults is not None else DEFAULTS_CC`.
    - Mensagem do `ValueError` (`f"language {language!r} not in CC gate scope..."`) — generalizar pra `f"language {language!r} not in gate scope; supported: {sorted(defaults)}"`. Asserts pertinentes em test_common_cc_helpers usam `pytest.raises(ValueError)` sem checar texto — verificar e atualizar se necessário.
  - Rename `def cc_format_three_paths(violations, thresholds)` → `def format_three_paths_message(violations, thresholds, *, gate_title="🛑 Cyclomatic Complexity gate", why_lines=None, format_annotation=None)`.
    - `gate_title` default preserva título CC.
    - `why_lines` default = lista atual ("Funções com CC alto...", "Threshold vigente:...", "Decision 23...").
    - `format_annotation: Callable[[dict], str] | None` default = render atual (status="new" → `" [new]"`; status="modified" + cc_before → `f"  ↑ de cc={cc_before} [modified]"`; senão `""`).
    - Corpo restante (header, "Onde:", "Por que importa:", "Três caminhos pra resolver:") fica igual; só os três pontos parametrizados acima mudam de literal para variável.
  - `DEFAULTS_CC` mantém o nome (CC-específico).
- [ ] Step 3: Em `validators/check_cyclomatic_complexity.py`:
  - Atualizar import bloco `from _common import`:
    ```python
    from _common import (
        DEFAULTS_CC,
        format_three_paths_message,
        gate_threshold_lookup,
        make_paths,
        result_fail,
        result_pass,
        result_warn,
        run_cli,
    )
    ```
  - Substituir callsite `cc_threshold_lookup(lang, active_cards=active_cards, workflow_config=config)` em `validate()` linha ~1015 → `gate_threshold_lookup(lang, active_cards=active_cards, workflow_config=config)` (defaults novos têm fallback CC, callsite mínimo).
  - Substituir callsite `cc_format_three_paths(violations, affected_thresholds)` em `validate()` linha ~1094 → `format_three_paths_message(violations, affected_thresholds)`.
- [ ] Step 4: Em `tests/validators/test_common_cc_helpers.py`:
  - Renomear imports no topo: `from _common import cc_format_three_paths, cc_threshold_lookup, DEFAULTS_CC` → `from _common import DEFAULTS_CC, format_three_paths_message, gate_threshold_lookup`.
  - Substituir TODAS as ocorrências `cc_threshold_lookup` → `gate_threshold_lookup` (17 matches conforme grep) e `cc_format_three_paths` → `format_three_paths_message` (3 matches).
  - Assert strings (snapshots de output) inalterados — render deve produzir BYTE A BYTE o mesmo texto. Se um snapshot quebrar, é bug do refactor (defaults dos novos kwargs não preservaram comportamento).
- [ ] Step 5: Atualizar comentários (não-código):
  - `engine/implement.py:501` — substituir texto do comentário/docstring: `Prefers the canonical \`render\` field (\`cc_format_three_paths\` output)` → `Prefers the canonical \`render\` field (\`format_three_paths_message\` output)`.
  - `tests/engine/test_implement_cc_gate.py:130` — substituir comentário `(cc_format_three_paths output)` → `(format_three_paths_message output)`.
- [ ] Step 6: `pytest tests/validators/test_common_cc_helpers.py tests/validators/test_check_cyclomatic_complexity.py tests/engine/test_implement_cc_gate.py -xvs`. Asserts inalterados; snapshots batem byte-a-byte.
- [ ] Step 7: Suite full count check + grep negativo confirma zero ocorrências legadas:
  ```bash
  grep -rn "cc_threshold_lookup\|cc_format_three_paths" validators/ engine/ tests/
  # Expected: zero matches
  ```
- [ ] Step 8: Commit:
  ```
  refactor(validators): rename cc_threshold_lookup → gate_threshold_lookup, cc_format_three_paths → format_three_paths_message
  ```

---

## Task 8 — Doc-sync Phase 0

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/design/08-session-handoff.md`
- Modify: `README.md` (LOC stats podem mudar — re-validar)
- Modify: `.claude/rules/reuse.md` (mention novo módulo `_gate_infra.py` + `_diff.py` como recurso de reuso pra futuros validators)
- Modify: `docs/design/04-pending.md` (marcar entradas relevantes como "infra ready" se aplicável — verificar antes; **não fechar** Phase 0 não implementa nenhum dos novos gates)

Steps:
- [ ] Step 1: Read cada doc atual pra entender estado vigente (Última atualização, último item em Unreleased, stats em README)
- [ ] Step 2: `CHANGELOG.md` — adicionar bloco em `## [Unreleased] ### Changed`:
  ```
  - **Refactor (no-behavior-change):** Extracted reusable gate infrastructure
    from CC gate into `validators/_gate_infra.py` (DispatchResult,
    check_tool_available, dispatch_native_tool, render_config_with_placeholders,
    parse_overrides, apply_overrides) and `validators/_diff.py` (DiffHunk,
    classify_range_against_hunks, extract_diff_hunks, git_staged_files,
    read_commit_body).
  - **Renames in `validators/_common.py`:** cc_threshold_lookup →
    gate_threshold_lookup; cc_format_three_paths → format_three_paths_message.
    DEFAULTS_CC mantido (CC-específico).
  - `check_cyclomatic_complexity.py`: ~1127 LOC → ~600-700 LOC by composition.
  - Unblocks Wave R1+ (check_secrets, check_deps_cve, etc.) — gates compõem
    em vez de copiar.
  ```
- [ ] Step 3: `docs/design/08-session-handoff.md`:
  - Atualizar `**Última atualização:**` pra data do commit (formato `YYYY-MM-DD (v1.X.Y — gate-infra-extract)`)
  - Atualizar `**Estado:**` adicionando narrativa: "Phase 0 (gate-infra-extract) concluída — infra reusável extraída do CC gate, próximas waves (R1.1 check_secrets etc.) podem compor."
- [ ] Step 4: `README.md` — re-validar stats:
  - validators count permanece (refactor não adiciona/remove validator; `_gate_infra.py` e `_diff.py` são módulos compartilhados, não validators)
  - Se LOC total mudou >100 (CC validator caiu ~400-500 linhas, novos módulos ~280) atualizar tabela de stats SE existe
  - Caso README não tenha LOC explícita, skip
- [ ] Step 5: `.claude/rules/reuse.md` — APPEND nova section ao final:
  ```markdown
  ## Infra reusável de validators (Phase 0)

  Quando criar novo validator (gate), consulte PRIMEIRO os módulos
  compartilhados antes de duplicar lógica:

  - `validators/_gate_infra.py` — `DispatchResult`, `check_tool_available`,
    `dispatch_native_tool`, `render_config_with_placeholders`,
    `parse_overrides`, `apply_overrides`. Pattern de dispatch a CLI nativa +
    override-justify parametrizado por prefix.
  - `validators/_diff.py` — `DiffHunk`, `classify_range_against_hunks`,
    `extract_diff_hunks`, `git_staged_files`, `read_commit_body`. Helpers
    diff-mode pra gates que precisam limitar análise ao staged diff.
  - `validators/_common.py` — `gate_threshold_lookup`,
    `format_three_paths_message`, `result_pass/fail/warn`, `make_paths`,
    `run_cli`. Boilerplate canônico.

  Compor é preferível a copiar (Mandamento #3). Se `forge graph query Q11`
  detectar near-duplicate, promova ao módulo compartilhado em vez de criar
  versão paralela.
  ```
- [ ] Step 6: `docs/design/04-pending.md`:
  - Verificar se há entrada anotando "extrair infra do CC gate" — se sim, riscar como ✅ feito em Phase 0
  - Verificar se há entradas CC-* que ficam "infra ready" após Phase 0 — anotar como "infra ready (composta de _gate_infra)" mas **não fechar** (Phase 0 é prereq de implementação, não substitui o gate em si)
- [ ] Step 7: Suite verde + `forge verify` no próprio repo (no-op esperado já que o repo feature-forge não tem cards CC ativados — apenas confirma cascade roda sem crash). Confirmar que count de tests é IDÊNTICO ao baseline pré-Phase 0.
- [ ] Step 8: Commit:
  ```
  docs(sync): Phase 0 refactor — gate-infra-extract
  ```

---

## Self-review — Spec coverage

Cada item das §1-6 do spec mapeado pra task que implementa:

| Item do spec | Onde implementado |
|---|---|
| §1 `_DispatchResult` → `DispatchResult` | Task 1 |
| §1 `_check_tool_available` → `check_tool_available` | Task 2 |
| §1 `_render_config_for_threshold` → `render_config_with_placeholders` (generaliza) | Task 3 |
| §1 `_dispatch_tool` → `dispatch_native_tool` (parameteriza cmd_builder + benign_nonzero_codes) | Task 4 |
| §1 `_parse_overrides` → `parse_overrides` (parameteriza prefix + key_fields) | Task 5 |
| §1 `_apply_overrides` → `apply_overrides` (parameteriza prefix + key_extractor) | Task 5 |
| §1 `DiffHunk` dataclass em `_diff.py` | Task 6 |
| §1 `classify_function` → `classify_range_against_hunks` em `_diff.py` | Task 6 |
| §1 `_extract_diff_hunks` → `extract_diff_hunks` em `_diff.py` | Task 6 |
| §1 `_git_staged_files` → `git_staged_files` em `_diff.py` (+ param `extensions`) | Task 6 |
| §1 `_read_commit_body` → `read_commit_body` em `_diff.py` | Task 6 |
| §1 `cc_threshold_lookup` → `gate_threshold_lookup` (parameteriza card/workflow keys + defaults) | Task 7 |
| §1 `cc_format_three_paths` → `format_three_paths_message` (parameteriza title + why + annotation) | Task 7 |
| §1 `DEFAULTS_CC` mantém nome | Task 7 (explicito: NÃO renomear) |
| §2 CC validator refactor (imports + composição) | Tasks 1-7 incrementalmente |
| §2 cmd_builders locais (`_build_detekt_cmd` etc.) | Task 4 |
| §2 key_extractor local (`_cc_key_extractor`) | Task 5 |
| §2 remove `_CC_OVERRIDE_RE` + `_CC_OVERRIDE_LOOSE_RE` + `_CC_THRESHOLD_PLACEHOLDER` | Task 5 (regex) + Task 3 (placeholder) |
| §3 verificação no-behavior-change (pytest count, check_no_behavior_change, snapshot) | Workflow obrigatório por task (steps 1-5) |
| §3 forge verify cascade + forge implement hook continuam batendo | Cobertos pela suite full + integration tests em cada task |
| §4 sequência 7 refactor + 1 doc-sync | Tasks 1-8 mapeiam 1:1 |
| §5 decisões load-bearing preservadas (14-27) | Nenhuma task toca `docs/design/01-decisions.md`; nenhum hook hard-block dispara |
| §6 próximo passo (Waves R1+) | Documentado na Task 8 (CHANGELOG menciona unblock) + `.claude/rules/reuse.md` (módulos a consultar) |

**Cobertura: 100%.** Cada item de extração + cada item de generalização + cada item de doc-sync tem dono no plano.

---

## Notas operacionais

- **No-behavior-change como hard gate:** TODA task verifica pytest count + tests passing antes/depois. Snapshot tests de output (`cc_format_three_paths` → `format_three_paths_message`) devem produzir string BYTE A BYTE idêntica quando chamados com defaults equivalentes. Qualquer diff observável é bug do refactor — ROLLBACK e investigar.
- **Doc-sync deferred:** Commits de refactor (Tasks 1-7) vão disparar o aviso de drift do hook `.claude/hooks/post-edit-doc-drift.sh` em cada task. É esperado — Task 8 fecha o débito consolidando tudo num único `docs(sync)`.
- **Sem decisão load-bearing tocada.** `docs/design/01-decisions.md` permanece intocado em todas as 8 tasks. Hook `pre-commit-feature-forge.sh` hard-block não dispara.
- **Sem PR aberto na main pra esta branch — confirmar antes do push final** via `gh pr list --state open --base main` (Step 0 do plan estratégico).
- **Ordem dos imports** em `check_cyclomatic_complexity.py` ao final da Task 7 deve ficar limpa: `_common` (renomeados) + `_gate_infra` (6 públicos) + `_diff` (5 públicos) + stdlib remanescente + `engine.utils.*`. Validar que `noqa: F401` em imports não usados foi removido (vide topo do CC validator hoje — tem vários `# noqa: F401` que deixaram de fazer sentido pós-refactor).
- **Hard rename, sem aliases.** Spec §Decisões do brainstorm trava: zero `cc_threshold_lookup = gate_threshold_lookup` ou stub em `check_cyclomatic_complexity.py`. Internos do projeto, sem consumers externos — alias só confundiria `forge graph` Q11.
- **Tests count baseline:** capturar UMA VEZ no início da Task 1 e referenciar nas tasks subsequentes. Se algum commit baixar o count sem justificativa em mensagem (`Removed N tests because...`), bloqueador per `.claude/rules/testing.md §Test count regression`.
- **Forge verify no próprio repo:** Phase 0 deve manter `forge verify` verde (cascade rola, validators passam). Confirmar pré e pós cada task — especialmente após Task 6 (mudança de shape `dict → DiffHunk`) e Task 7 (rename de helpers em `_common.py`).
