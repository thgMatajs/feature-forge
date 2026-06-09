# Check Secrets Gate Implementation Plan (R1.1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax para tracking — cada subagent marca o que fechou antes de devolver o diff.

**Goal:** Entregar `check_secrets` — gate multi-tool que barra secrets verificados em staged files. `gitleaks` roda no per-task hook de `forge implement` (rápido, regex-based, ~100ms). `trufflehog --only-verified` roda na cascade de `forge verify` (deeper, valida ativamente). Override-justify pelo prefix `SECRETS-OVERRIDE: <file>:<line> kind=<token-type> — <razão>` no commit body. Hard-fail sempre. Tool missing → warn (mesmo contrato do CC gate).

**Architecture:** 1 validator Python (`validators/check_secrets.py`, ~150-200 LOC). Validator **compõe** infra Phase 0 (`dispatch_native_tool`, `check_tool_available`, `apply_overrides`, `git_staged_files`, `read_commit_body`, `result_pass/fail/warn`). Específico do gate: `SecretFinding` dataclass + 2 parsers (gitleaks JSON + trufflehog NDJSON) + stage selection (`per_task` → gitleaks, `cascade` → trufflehog) + render 3-caminhos com vocabulário de secrets. Nenhum helper reimplementado localmente.

**Tech Stack:** Python 3.10+, pytest (markers `integration` em integration tests). Tools nativas: `gitleaks` (regex, exit=1 = "found", `--no-git --report-format json --report-path -`), `trufflehog filesystem --only-verified --json` (exit=1 = "found"). Tools instaladas pelo dev (forge não instala — Decision 22 + filosofia trust-but-verify).

**Reference spec:** [`docs/superpowers/specs/2026-06-05-check-secrets-design.md`](../specs/2026-06-05-check-secrets-design.md) — fonte de verdade. Em conflito spec × plan, spec vence (plan precisa ser corrigido). Em conflito spec × implementação, implementação vence apenas com retorno ao spec.

---

## Workflow obrigatório por task

Cada task segue ritual TDD (Mandamento #2 — verde antes de "pronto"):

1. **Baseline pytest count** — `pytest --collect-only -q | tail -1` registra count atual.
2. **Write tests FAIL primeiro (RED)** — escreve o teste que descreve o comportamento desejado, roda, confirma `FAIL`.
3. **Implement minimal** — código mínimo pra fazer o teste passar.
4. **Run tests PASS (GREEN)** — confirma `PASS` do teste novo.
5. **Suite full sem regressão** — `pytest` full. Count ≥ baseline + tests adicionados na task.
6. **Commit atômico** — `<tipo>(<escopo>): <descrição>`. Sem doc-sync no commit da task (separada na Task 6).

Scope (Mandamento #4): cada task lista `ARQUIVOS PERMITIDOS PARA EDIT/WRITE` literal. Sair da lista = scope creep — abortar dispatch.

Reuso (Mandamento #3): cada task **compõe** explicitamente da infra Phase 0. Nada de subprocess.run inline, nada de regex de override reescrito, nada de `shutil.which` cru. Em dúvida, abrir `validators/_gate_infra.py` + `validators/_diff.py` + `validators/_common.py` antes de escrever.

---

## Task 1 — Skeleton `check_secrets.py` + `SecretFinding` dataclass + ignore-paths helper

**Arquivos permitidos:**
- CRIAR `validators/check_secrets.py`
- CRIAR `tests/validators/test_check_secrets_skeleton.py`

**Leituras antes:** `validators/check_cyclomatic_complexity.py` (linhas 1-90 — imports + `CCResult` shape) · `validators/_gate_infra.py` (módulo inteiro — API surface) · `docs/superpowers/specs/2026-06-05-check-secrets-design.md §2` (SecretFinding shape, ignore-paths).

**Critério de sucesso:** `pytest tests/validators/test_check_secrets_skeleton.py -xvs` verde. Suite full sem regressão.

**Steps:**

- [ ] Step 1 — Baseline pytest count.
- [ ] Step 2 — Escrever `tests/validators/test_check_secrets_skeleton.py` com:
  - `test_secret_finding_shape_is_frozen_dataclass` — 5 campos exatos (`file: str`, `line: int`, `kind: str`, `snippet: str`, `verified: bool`); instância nova de `SecretFinding(file="a.kt", line=1, kind="aws", snippet="x", verified=True)` é frozen (atribuir levanta `dataclasses.FrozenInstanceError`).
  - `test_filter_ignored_drops_matching_paths` — `_filter_ignored([Path("tests/fixtures/secrets/x.kt"), Path("app/Foo.kt")], [r"tests/fixtures/secrets/.*"])` retorna apenas `[Path("app/Foo.kt")]`.
  - `test_filter_ignored_empty_patterns_passes_all` — patterns vazio → input devolvido íntegro.
  - `test_filter_ignored_skips_invalid_regex` — pattern `"["` (inválida) não levanta; resto da lista é aplicado normalmente (paralelo da blindagem em `_compile_ignore_patterns` do CC gate).
- [ ] Step 3 — `pytest tests/validators/test_check_secrets_skeleton.py -xvs` → FAIL (módulo não existe).
- [ ] Step 4 — Criar `validators/check_secrets.py` minimal:
  ```python
  #!/usr/bin/env python3
  """check_secrets.py — multi-tool secrets scanning gate.

  Per-stage split (per design spec §0 brainstorm):
    - stage="per_task" → gitleaks (regex-based, ~100ms, no false negatives but
      no active verification).
    - stage="cascade"  → trufflehog --only-verified (deep, active verification
      against origin, --only-verified filters out unverified).

  Override-justify lives in the commit body:
      SECRETS-OVERRIDE: <file>:<line> kind=<token-type> — <razão concreta>

  Tools NÃO são instaladas pelo forge (Decision 22 + spec §3 trust-but-verify).
  Missing tool → result_warn (cascade segue alive).

  Doc canônica: docs/superpowers/specs/2026-06-05-check-secrets-design.md
  """

  from __future__ import annotations

  import re
  from dataclasses import dataclass
  from pathlib import Path


  @dataclass(frozen=True)
  class SecretFinding:
      """Normalised secret-scan result (tool-agnostic).

      Emitido pelos parsers per-tool (gitleaks/trufflehog) e consumido pelo
      override-apply + render 3-caminhos.
      """
      file: str       # path relativo ao repo
      line: int       # 1-indexed
      kind: str       # "aws_access_key", "firebase_token", "github_pat", ...
      snippet: str    # primeiros ~80 chars do match (redacted no render)
      verified: bool  # True só quando trufflehog confirmou ativa


  def _filter_ignored(files: list[Path], patterns: list[str]) -> list[Path]:
      """Filtra paths que casam com QUALQUER regex em ``patterns``.

      Paralelo de ``_path_matches_ignore`` no CC gate — regex inválida em
      ``patterns`` é skip silencioso (belt-and-suspenders; pre-validation
      acontece no caller de mais alto nível em tasks seguintes).
      """
      if not patterns:
          return list(files)
      out: list[Path] = []
      for f in files:
          rel = str(f)
          dropped = False
          for pat in patterns:
              try:
                  if re.search(pat, rel):
                      dropped = True
                      break
              except re.error:
                  continue
          if not dropped:
              out.append(f)
      return out
  ```
- [ ] Step 5 — `pytest tests/validators/test_check_secrets_skeleton.py -xvs` → PASS.
- [ ] Step 6 — `pytest` full sem regressão.
- [ ] Step 7 — Commit: `feat(validators): check_secrets skeleton + SecretFinding`

**Anti-padrões:**
- NÃO criar `parse_overrides` / `apply_overrides` locais — virá de `_gate_infra` na Task 4.
- NÃO importar `dispatch_native_tool` ainda — Task 3.
- NÃO injetar parsers stub na Task 1 — Task 2.

---

## Task 2 — Parsers gitleaks JSON + trufflehog NDJSON

**Arquivos permitidos:**
- MODIFY `validators/check_secrets.py` (APPEND parsers; não tocar o que já existe)
- CRIAR `tests/validators/test_check_secrets_parsers.py`
- CRIAR `tests/fixtures/secrets/gitleaks_output_sample.json`
- CRIAR `tests/fixtures/secrets/trufflehog_output_sample.json`

**Leituras antes:** `validators/check_cyclomatic_complexity.py` linhas 95-282 (`_parse_detekt`, `_parse_swiftlint`, `_parse_eslint`, `_parse_radon` — robustness contract `JSONDecodeError → []`) · spec §3 (verified flag semantics).

**Critério de sucesso:** Parsers convertem fixtures determinísticos em listas `SecretFinding` corretas. Crash em JSON inválido devolve `[]` (não levanta). Suite full sem regressão.

**Steps:**

- [ ] Step 1 — Baseline.
- [ ] Step 2 — Criar fixture `tests/fixtures/secrets/gitleaks_output_sample.json`:
  ```json
  [
    {
      "RuleID": "aws-access-key",
      "Description": "AWS Access Key",
      "File": "app/auth/AuthRepository.kt",
      "StartLine": 42,
      "Secret": "AKIAIOSFODNN7EXAMPLE",
      "Match": "val key = \"AKIAIOSFODNN7EXAMPLE\""
    },
    {
      "RuleID": "firebase-token",
      "Description": "Firebase token",
      "File": "src/config/firebase.ts",
      "StartLine": 15,
      "Secret": "1//0abcdEFGhiJklmnopQRSTuvWXyz",
      "Match": "const token = '1//0abcd...'"
    }
  ]
  ```
- [ ] Step 3 — Criar fixture `tests/fixtures/secrets/trufflehog_output_sample.json` (NDJSON — 1 line por finding):
  ```jsonl
  {"DetectorName":"AWS","DecoderName":"PLAIN","Verified":true,"Raw":"AKIAIOSFODNN7EXAMPLE","Redacted":"AKIA****EXAMPLE","SourceMetadata":{"Data":{"Filesystem":{"file":"app/auth/AuthRepository.kt","line":42}}}}
  {"DetectorName":"Firebase","DecoderName":"PLAIN","Verified":false,"Raw":"1//0abcdEFGhiJklmnopQRSTuvWXyz","SourceMetadata":{"Data":{"Filesystem":{"file":"src/config/firebase.ts","line":15}}}}
  ```
  Nota no docstring do teste: trufflehog produz NDJSON (uma linha por finding). Parser split por `\n`.
- [ ] Step 4 — Escrever testes em `tests/validators/test_check_secrets_parsers.py`:
  - `test_parse_gitleaks_happy_path` — lê fixture, espera lista com 2 `SecretFinding` (file/line/kind alinhados, `verified=False`, snippet truncado em 80 chars).
  - `test_parse_gitleaks_handles_invalid_json` — `_parse_gitleaks_json("not json {")` → `[]`.
  - `test_parse_gitleaks_handles_empty_string` — `_parse_gitleaks_json("")` → `[]`.
  - `test_parse_gitleaks_handles_non_list_root` — `_parse_gitleaks_json('{"oops": 1}')` → `[]`.
  - `test_parse_trufflehog_happy_path` — fixture NDJSON, espera 2 findings (1 `verified=True`, 1 `verified=False`); kinds alinhados; file/line extraídos de `SourceMetadata.Data.Filesystem`.
  - `test_parse_trufflehog_skips_malformed_lines` — input `"valid_line\n{broken json\nother_valid"` → parser ignora a linha quebrada, mantém as válidas.
  - `test_parse_trufflehog_handles_missing_metadata` — entry sem `SourceMetadata` → `file=""`, `line=0`, sem crash.
- [ ] Step 5 — `pytest tests/validators/test_check_secrets_parsers.py -xvs` → FAIL.
- [ ] Step 6 — Implementar parsers (APPEND a `validators/check_secrets.py`):
  ```python
  import json


  def _parse_gitleaks_json(raw: str) -> list[SecretFinding]:
      """Parse `gitleaks detect --report-format json` output.

      Shape: JSON array de findings. Cada entry tem ``RuleID``, ``File``,
      ``StartLine``, ``Secret``, ``Description``. ``verified`` é sempre
      False — gitleaks é regex-based, não verifica origem (filosofia do split
      per-stage: gitleaks no per_task hook = fast, sem network roundtrip).

      Robustness: JSON inválido / não-array / vazio → ``[]`` (mesmo contrato
      dos parsers do CC gate; spec §3 trust-but-verify).
      """
      try:
          data = json.loads(raw) if raw.strip() else []
      except json.JSONDecodeError:
          return []
      if not isinstance(data, list):
          return []
      out: list[SecretFinding] = []
      for entry in data:
          if not isinstance(entry, dict):
              continue
          try:
              line_value = int(entry.get("StartLine", 0))
          except (TypeError, ValueError):
              continue
          out.append(
              SecretFinding(
                  file=str(entry.get("File", "")),
                  line=line_value,
                  kind=str(entry.get("RuleID", "unknown")),
                  snippet=str(entry.get("Secret", ""))[:80],
                  verified=False,
              )
          )
      return out


  def _parse_trufflehog_json(raw: str) -> list[SecretFinding]:
      """Parse `trufflehog filesystem --json` output (NDJSON — 1 finding por linha).

      Shape por linha: ``{"DetectorName": "AWS", "Verified": bool, "Raw": "...",
      "SourceMetadata": {"Data": {"Filesystem": {"file": "...", "line": N}}}}``.

      ``Verified=False`` ainda entra na lista — o filtro ``--only-verified``
      é responsabilidade da CLI flag, não do parser. Quem ler o output puro
      sem o flag (debug) ainda quer ver tudo. O caller (cascade dispatch)
      garante o flag.

      Linha malformed → skip silencioso. JSON vazio → ``[]``.
      """
      findings: list[SecretFinding] = []
      for line in raw.splitlines():
          line = line.strip()
          if not line:
              continue
          try:
              entry = json.loads(line)
          except json.JSONDecodeError:
              continue
          if not isinstance(entry, dict):
              continue
          metadata = (
              entry.get("SourceMetadata", {})
              .get("Data", {})
              .get("Filesystem", {})
              if isinstance(entry.get("SourceMetadata"), dict)
              else {}
          )
          try:
              line_value = int(metadata.get("line", 0))
          except (TypeError, ValueError):
              line_value = 0
          findings.append(
              SecretFinding(
                  file=str(metadata.get("file", "")),
                  line=line_value,
                  kind=str(entry.get("DetectorName", "unknown")),
                  snippet=str(entry.get("Raw", ""))[:80],
                  verified=bool(entry.get("Verified", False)),
              )
          )
      return findings
  ```
- [ ] Step 7 — `pytest tests/validators/test_check_secrets_parsers.py -xvs` → PASS.
- [ ] Step 8 — Suite full.
- [ ] Step 9 — Commit: `feat(validators): check_secrets parsers (gitleaks + trufflehog)`

**Anti-padrões:**
- NÃO normalizar `verified=True` no parser do gitleaks (gitleaks NÃO verifica — flag fica `False` sempre).
- NÃO filtrar `verified=False` no parser do trufflehog — filtro é via CLI flag `--only-verified`, parser é honesto.
- NÃO inflar snippet acima de 80 chars (segurança — sem token completo em log).

---

## Task 3 — Stage selection + cmd_builders + `_dispatch_for_stage`

**Arquivos permitidos:**
- MODIFY `validators/check_secrets.py` (APPEND seção `# ── Tool dispatch ──`)
- CRIAR `tests/validators/test_check_secrets_dispatch.py`

**Leituras antes:** `validators/_gate_infra.py` linhas 96-205 (`dispatch_native_tool` + `benign_nonzero_codes`) · `validators/check_cyclomatic_complexity.py` linhas 316-383 (`_build_*_cmd` shape) · spec §2 passo 6 (gitleaks/trufflehog cmd shape).

**Critério de sucesso:** `cmd_builders` produzem comandos exatos esperados; `_dispatch_for_stage` resolve stage → tool corretamente; `benign_nonzero_codes=(1,)` documentado e passado.

**Steps:**

- [ ] Step 1 — Baseline.
- [ ] Step 2 — Escrever `tests/validators/test_check_secrets_dispatch.py`:
  - `test_build_gitleaks_cmd_shape` — `_build_gitleaks_cmd("gitleaks", ["a.kt", "b.ts"], None)` retorna `["gitleaks", "detect", "--no-git", "--report-format=json", "--report-path=-", "--source", "a.kt", "--source", "b.ts"]` (ordem literal — asserção `assert cmd == [...]`).
  - `test_build_gitleaks_cmd_empty_files` — `_build_gitleaks_cmd("gitleaks", [], None)` ainda contém os args base; lista vazia não corrompe.
  - `test_build_trufflehog_cmd_shape` — `_build_trufflehog_cmd("trufflehog", ["app/Foo.kt"], None)` começa com `["trufflehog", "filesystem", "--only-verified", "--json"]` e termina com `["app/Foo.kt"]`.
  - `test_dispatch_for_stage_per_task_uses_gitleaks` — patch `dispatch_native_tool` (monkeypatch no módulo) capturando kwargs; chamada `_dispatch_for_stage("per_task", [Path("a.kt")], project_root=Path("."))` invoca com `tool_bin="gitleaks"` e `cmd_builder=_build_gitleaks_cmd`.
  - `test_dispatch_for_stage_cascade_uses_trufflehog` — paralelo com `tool_bin="trufflehog"` e `cmd_builder=_build_trufflehog_cmd`.
  - `test_dispatch_for_stage_passes_benign_nonzero_codes_1` — kwarg `benign_nonzero_codes=(1,)` é forwarded.
  - `test_dispatch_for_stage_raises_on_unknown_stage` — `_dispatch_for_stage("misc", ...)` → `KeyError` (ou `ValueError` se preferir contract claro).
- [ ] Step 3 — `pytest` → FAIL.
- [ ] Step 4 — APPEND em `check_secrets.py`:
  ```python
  from typing import Optional

  from _gate_infra import DispatchResult, dispatch_native_tool


  # ── Tool dispatch ────────────────────────────────────────────────────────────
  #
  # Stage selection (per spec §2 brainstorm):
  #   per_task → gitleaks (fast regex, no network roundtrip — ~100ms).
  #   cascade  → trufflehog --only-verified (deep, active verification).
  #
  # `benign_nonzero_codes=(1,)` — ambas as tools usam exit=1 pra sinalizar
  # "encontrei findings" (não é crash). O contrato `benign_nonzero_codes` em
  # `dispatch_native_tool` cobre exatamente esse padrão (eslint usa o mesmo
  # trick — gate herda da extração Phase 0 sem reinventar).

  def _build_gitleaks_cmd(
      tool_bin: str, files: list[str], rendered_config: Optional[str]
  ) -> list[str]:
      """gitleaks detect --no-git --report-format=json --report-path=- --source <each>.

      `--no-git` evita scan da history (gate é diff-mode — apenas staged).
      `--report-path=-` emite JSON em stdout (parsea via `_parse_gitleaks_json`).
      `--source <file>` repetível pra restringir scan a staged paths (gitleaks v8+).
      `rendered_config` ignorado em v1.2-dev (default rules — gap SECRETS-1 cobre custom).
      """
      cmd = [tool_bin, "detect", "--no-git", "--report-format=json", "--report-path=-"]
      for f in files:
          cmd.extend(["--source", str(f)])
      return cmd


  def _build_trufflehog_cmd(
      tool_bin: str, files: list[str], rendered_config: Optional[str]
  ) -> list[str]:
      """trufflehog filesystem --only-verified --json <files...>.

      `--only-verified` é decisão locked do brainstorm (zero false positives
      ativos vs perda de unverifiable — trade-off aceito). `--json` emite
      NDJSON (1 finding por linha — parser splits por \\n).
      `rendered_config` ignorado em v1.2-dev (gap SECRETS-1).
      """
      return [tool_bin, "filesystem", "--only-verified", "--json", *[str(f) for f in files]]


  _SECRETS_TOOL_BIN = {"per_task": "gitleaks", "cascade": "trufflehog"}
  _SECRETS_CMD_BUILDERS = {
      "per_task": _build_gitleaks_cmd,
      "cascade": _build_trufflehog_cmd,
  }


  def _dispatch_for_stage(
      stage: str,
      files: list[Path],
      *,
      project_root: Path,
  ) -> DispatchResult:
      """Dispatch a tool corresponding to ``stage`` (per_task → gitleaks, cascade → trufflehog).

      Stage desconhecido levanta ``KeyError`` — fail-fast, sem fallback
      silencioso (caller deve sempre passar o stage explícito).
      """
      tool_bin = _SECRETS_TOOL_BIN[stage]
      cmd_builder = _SECRETS_CMD_BUILDERS[stage]
      return dispatch_native_tool(
          language="any",
          files=[str(f) for f in files],
          cmd_builder=cmd_builder,
          project_root=project_root,
          tool_bin=tool_bin,
          benign_nonzero_codes=(1,),
      )
  ```
- [ ] Step 5 — `pytest` → PASS.
- [ ] Step 6 — Suite full.
- [ ] Step 7 — Commit: `feat(validators): check_secrets stage dispatch (gitleaks per_task + trufflehog cascade)`

**Anti-padrões:**
- NÃO usar `language` mais granular que `"any"` — secrets atravessam linguagem (Kotlin, Swift, TS, YAML, Dockerfile, .env...). O campo é descritivo na infra, não é load-bearing aqui.
- NÃO renderizar `config_template` em v1.2-dev (default rules; SECRETS-1 gap cobre custom rules pra v1.3+).
- NÃO trocar `--only-verified` por config flag agora — decisão é locked.

---

## Task 4 — Override-justify wiring + `validate()` entry point + render 3-caminhos

**Arquivos permitidos:**
- MODIFY `validators/check_secrets.py` (APPEND render + validate)
- CRIAR `tests/validators/test_check_secrets.py`

**Leituras antes:** `validators/check_cyclomatic_complexity.py` linhas 389-453 (override wrapper pattern), linhas 664-836 (`validate` orchestrator end-to-end) · `validators/_common.py` linhas 73-93 (`result_fail` exige 3 paths) · spec §3 (render literal) + spec §4 (override mechanic).

**Critério de sucesso:** `validate(project_root, stage=...)` retorna result dict canônico. Override silencia (file, line, kind). Malformed override emite warning. Tool missing → warn. Snapshot do render 3-caminhos bate o template do spec.

**Steps:**

- [ ] Step 1 — Baseline.
- [ ] Step 2 — Escrever `tests/validators/test_check_secrets.py` (cobre ≥12 cenários do spec §5):
  - `test_validate_no_staged_files_passes` — `git_staged_files` mockado retorna `[]` → `result_pass("nenhum staged file pra scanear")`.
  - `test_validate_secrets_gate_disabled_warns` — workflow-config `secrets-gate.enabled=false` → `result_warn("...desligado...")`.
  - `test_validate_tool_missing_warns` — `check_tool_available` retorna False → `result_warn` cita install hint apropriado por tool (gitleaks/trufflehog).
  - `test_validate_no_findings_passes` — dispatch retorna `raw_stdout=""` ou `"[]"` → `result_pass`.
  - `test_validate_finding_without_override_fails` — 1 SecretFinding surviving → `result_fail` com 3 paths exatos, campo `render` populated, `what-failed` cita o primeiro finding.
  - `test_validate_finding_with_valid_override_passes` — commit body contém `SECRETS-OVERRIDE: app/Foo.kt:42 kind=aws_access_key — test fixture` e finding bate exato → `result_pass` mencionando "silenciados via SECRETS-OVERRIDE".
  - `test_validate_override_malformed_emits_warning` — commit body com `SECRETS-OVERRIDE: app/Foo.kt:42 kind=aws_access_key —` (sem razão) → finding NÃO silenced; result tem `warnings` não vazio.
  - `test_validate_override_only_covers_matching_triple` — override pra `(app/Foo.kt, 42, aws_access_key)` NÃO silencia finding em `app/Bar.kt:42 kind=aws_access_key` (file diferente) — surviving inclui o segundo.
  - `test_validate_ignore_paths_filters_before_dispatch` — staged inclui `tests/fixtures/secrets/x.kt`; workflow-config `ignore-paths: ["tests/fixtures/secrets/.*"]` → dispatch invocado com lista sem o path.
  - `test_validate_per_task_stage_uses_gitleaks_parser` — mock dispatch returning fixture JSON do gitleaks; render do `Onde:` cita `(unverified — gitleaks)`.
  - `test_validate_cascade_stage_uses_trufflehog_parser` — mock returning fixture NDJSON; render cita `(verified)`.
  - `test_validate_dispatch_crashed_warns` — DispatchResult com `crashed=True` → `result_warn` cita stderr snippet.
  - `test_render_three_paths_snapshot_per_task` — chamada `_render_secrets_three_paths(findings, stage="per_task")` bate literal o template do spec §3 com adaptação per_task ("unverified — gitleaks").
  - `test_render_three_paths_snapshot_cascade` — idem com `(verified)` no `Onde:` e "trufflehog confirmou ATIVA na origem" no "Por que importa:".
- [ ] Step 3 — `pytest` → FAIL.
- [ ] Step 4 — APPEND em `check_secrets.py`:
  ```python
  from typing import Any

  from _common import (
      make_paths,
      result_fail,
      result_pass,
      result_warn,
      run_cli,
  )
  from _diff import git_staged_files, read_commit_body
  from _gate_infra import (
      apply_overrides as _gate_apply_overrides,
      check_tool_available,
  )

  import sys
  sys.path.insert(0, str(Path(__file__).parent.parent))

  from engine.utils.yaml_io import read_yaml_or_default  # noqa: E402


  # ── Override-justify ────────────────────────────────────────────────────────

  _SECRETS_OVERRIDE_PREFIX = "SECRETS-OVERRIDE"
  _SECRETS_OVERRIDE_KEY_PATTERN = r"(?P<file>\S+):(?P<line>\d+)\s+kind=(?P<kind>\S+)"
  _SECRETS_OVERRIDE_KEY_FIELDS = ["file", "line", "kind"]
  _SECRETS_OVERRIDE_VALUE_CONVERTERS = {"line": int}


  def _secrets_fail_key_extractor(f: SecretFinding) -> tuple[str, int, str]:
      """Cover tuple: (file, line, kind). Match exigente — override é por
      ocorrência específica, não por kind genérico."""
      return (f.file, f.line, f.kind)


  def apply_overrides(
      fails: list[SecretFinding],
      commit_body: str,
  ) -> tuple[list[SecretFinding], list[SecretFinding], list[str]]:
      """Thin wrapper sobre `_gate_infra.apply_overrides` com params do gate."""
      return _gate_apply_overrides(
          fails,
          commit_body,
          prefix=_SECRETS_OVERRIDE_PREFIX,
          key_pattern=_SECRETS_OVERRIDE_KEY_PATTERN,
          fail_key_extractor=_secrets_fail_key_extractor,
          override_key_fields=_SECRETS_OVERRIDE_KEY_FIELDS,
          value_converters=_SECRETS_OVERRIDE_VALUE_CONVERTERS,
      )


  # ── 3-caminhos render (canônico — snapshot test) ────────────────────────────

  def _render_secrets_three_paths(
      findings: list[SecretFinding], *, stage: str
  ) -> str:
      """Render literal do bloco 3-caminhos (spec §3).

      Per_task (gitleaks) cita "(unverified — gitleaks)" no Onde: e
      "gitleaks marcou regex-match" no Por que importa:.
      Cascade (trufflehog) cita "(verified)" e "trufflehog confirmou ATIVA
      na origem".
      """
      if not findings:
          raise ValueError("_render_secrets_three_paths requires ≥1 finding")
      sorted_findings = sorted(findings, key=lambda f: (f.file, f.line))
      lines: list[str] = []
      lines.append("🛑 Check Secrets gate")
      lines.append("")
      lines.append("O que falhou:")
      verified_count = sum(1 for f in sorted_findings if f.verified)
      if stage == "cascade":
          lines.append(f"  {verified_count} secrets verificados detectados em arquivos staged.")
      else:
          lines.append(f"  {len(sorted_findings)} candidatos a secret (regex-match) detectados em arquivos staged.")
      lines.append("")
      lines.append("Onde:")
      for f in sorted_findings:
          flag = "(verified)" if f.verified else "(unverified — gitleaks)"
          lines.append(f"  · {f.file}:{f.line} — kind={f.kind} {flag}")
      lines.append("")
      lines.append("Por que importa:")
      lines.append(
          "  · Tokens commitados ficam no histórico mesmo após delete — "
          "rotação imediata é única mitigação."
      )
      if stage == "cascade":
          lines.append(
              "  · trufflehog confirmou ATIVA na origem (--only-verified). "
              "Não é falso positivo."
          )
      else:
          lines.append(
              "  · gitleaks marcou regex-match no per-task hook. Verificação "
              "ativa acontece na cascade (trufflehog) — bloqueio aqui é preventivo."
          )
      lines.append("  · Decision 23 — cascade fail-fast; check_secrets é gate hard.")
      lines.append("")
      lines.append("Três caminhos pra resolver:")
      lines.append("")
      lines.append("  1) Remover e rotacionar")
      lines.append(
          "     Apague a linha do arquivo, ROTACIONE o token na origem "
          "(revogue + emita novo), e use variável de ambiente / secret manager "
          "pro novo valor."
      )
      lines.append(
          "     Token já commitado vive no git history — assume comprometido."
      )
      lines.append("")
      lines.append("  2) Override-justify (commit body) — apenas pra test fixtures")
      lines.append(
          "     Se a string é deliberadamente um fixture (test, doc exemplo), "
          "adicione ao commit body — EXATAMENTE este formato:"
      )
      lines.append("")
      lines.append(
          "         SECRETS-OVERRIDE: <file>:<line> kind=<token-type> — <razão concreta>"
      )
      lines.append("")
      lines.append(
          "     Validator detecta a linha no commit body e libera APENAS este commit."
      )
      lines.append(
          "     Auditável via `git log --grep='SECRETS-OVERRIDE'`. NÃO é "
          "whitelist persistente."
      )
      lines.append("")
      lines.append("  3) Marcar como fixture")
      lines.append(
          "     Mova o arquivo pra `tests/fixtures/secrets/` (já no `ignore-paths` "
          "default). Use chars deliberadamente inválidos no token (ex: "
          "`AKIA00000000FAKE`) pra trufflehog --only-verified não bater."
      )
      lines.append("")
      lines.append("Sem auto-fix aqui — escolha humana.")
      return "\n".join(lines)


  # ── Orchestrator ────────────────────────────────────────────────────────────

  _SECRETS_TOOL_INSTALL_HINTS = {
      "gitleaks": "brew install gitleaks    # or: go install github.com/gitleaks/gitleaks/v8@latest",
      "trufflehog": "brew install trufflehog",
  }


  def _load_workflow_config(project_root: Path) -> dict[str, Any]:
      cfg_path = project_root / ".claude" / "workflow-config.yaml"
      return read_yaml_or_default(cfg_path, {}) or {}


  _DEFAULT_IGNORE_PATTERNS = [r"tests/fixtures/secrets/.*"]


  def validate(
      project_root: Path,
      *,
      stage: str = "cascade",
      **kwargs: Any,
  ) -> dict[str, Any]:
      """Main entry-point — invocado tanto pelo cascade (`forge verify`,
      stage="cascade") quanto pelo per-task hook (`forge implement`,
      stage="per_task").

      Pipeline (spec §2):
        1. Lê workflow-config; short-circuit se `enabled=false`.
        2. git_staged_files (sem filtro de extensão — secrets viajam em qualquer file).
        3. Filtra ignore-paths.
        4. check_tool_available(stage_tool) — missing → result_warn.
        5. dispatch_native_tool via _dispatch_for_stage (benign_nonzero=(1,)).
        6. Parse via _parse_gitleaks_json ou _parse_trufflehog_json.
        7. apply_overrides com SECRETS-OVERRIDE.
        8. result_fail (com render) se surviving; else result_pass / result_warn.
      """
      cfg = _load_workflow_config(project_root)
      sec_block = cfg.get("secrets-gate") if isinstance(cfg, dict) else None
      if isinstance(sec_block, dict) and sec_block.get("enabled") is False:
          return result_warn(
              "secrets-gate desligado em workflow-config — sem cobertura de "
              "secret scanning"
          )

      staged = git_staged_files(project_root)
      if not staged:
          return result_pass("nenhum staged file pra scanear")

      ignore_patterns = list(_DEFAULT_IGNORE_PATTERNS)
      extra_ignore = (
          sec_block.get("ignore-paths") if isinstance(sec_block, dict) else None
      )
      if isinstance(extra_ignore, list):
          ignore_patterns.extend(str(p) for p in extra_ignore)
      staged = _filter_ignored(staged, ignore_patterns)
      if not staged:
          return result_pass("ignore-paths filtrou todos os staged files")

      tool_bin = _SECRETS_TOOL_BIN[stage]
      if not check_tool_available(tool_bin):
          hint = _SECRETS_TOOL_INSTALL_HINTS.get(tool_bin, "(no hint)")
          return result_warn(
              f"{tool_bin} não instalado — skip {stage} secrets scan. "
              f"install: {hint}"
          )

      dispatch_res = _dispatch_for_stage(stage, staged, project_root=project_root)
      if dispatch_res.crashed:
          return result_warn(
              f"{tool_bin} crashed: {dispatch_res.error_message}"
          )

      parser = (
          _parse_gitleaks_json if stage == "per_task" else _parse_trufflehog_json
      )
      findings = parser(dispatch_res.raw_stdout)
      if not findings:
          return result_pass("zero secrets detectados")

      commit_body = read_commit_body(project_root)
      silenced, surviving, warnings = apply_overrides(findings, commit_body)

      if not surviving:
          msg = (
              f"check_secrets ok ({len(silenced)} silenciados via SECRETS-OVERRIDE)"
          )
          if warnings:
              res = result_warn(msg + "; tentativas malformed: " + "; ".join(warnings))
              res["warnings"] = warnings
              return res
          return result_pass(msg)

      render = _render_secrets_three_paths(surviving, stage=stage)
      sample = ", ".join(
          f"{f.file}:{f.line} kind={f.kind}" for f in surviving[:3]
      )
      res = result_fail(
          f"Check Secrets gate: {len(surviving)} secret(s) detectado(s)",
          what_failed=sample,
          where="staged files",
          why=[
              "Tokens commitados vivem no histórico — rotação é única mitigação.",
              (
                  "trufflehog confirmou ATIVA (--only-verified)."
                  if stage == "cascade"
                  else "gitleaks regex-match (per-task — verificação ativa na cascade)."
              ),
              "Decision 23 — cascade fail-fast; check_secrets é gate hard.",
          ],
          paths=make_paths(
              "Remover e rotacionar",
              "Apague + revogue na origem + emita novo + use env/secret manager.",
              "Override-justify no commit body — SECRETS-OVERRIDE: <file>:<line> kind=<type> — <razão>",
              "Use APENAS pra test fixtures genuínos.",
              "Marcar como fixture",
              "Mova pra tests/fixtures/secrets/ e use chars FAKE no token.",
          ),
      )
      res["render"] = render
      if warnings:
          res["warnings"] = warnings
      return res


  if __name__ == "__main__":
      import sys as _sys
      _sys.exit(run_cli(__doc__ or "", validate))
  ```
- [ ] Step 5 — `pytest tests/validators/test_check_secrets.py -xvs` → PASS (todos os ≥12 cenários).
- [ ] Step 6 — Suite full sem regressão.
- [ ] Step 7 — Commit: `feat(validators): check_secrets validate() entry + override-justify + 3-paths render`

**Anti-padrões:**
- NÃO reimplementar `parse_overrides` local — wrapper enxuto sobre `_gate_apply_overrides` é o contract.
- NÃO emitir render parcial; sempre o bloco inteiro com header `🛑 Check Secrets gate` (load-bearing UX).
- NÃO trocar `make_paths(...)` por `paths=[...]` cru — `result_fail` valida `len==3` em `_common.py`.
- NÃO normalize stage default em `"per_task"` — `cascade` é default consciente (forge verify roda em "feature" scope mais comumente que per-task).

---

## Task 5 — Cascade integration (verify.py) + per-task hook (implement.py) + doctor categoria

**Arquivos permitidos:**
- MODIFY `engine/verify.py` (APPEND `check_secrets` no `_DEFAULT_VALIDATORS` após `check_cyclomatic_complexity`)
- MODIFY `engine/implement.py` (APPEND `_run_secrets_gate` + chamada após `_run_cc_gate`)
- MODIFY `engine/doctor.py` (APPEND `_check_secrets_tools` + registro em scope)
- CRIAR `tests/engine/test_verify_secrets_position.py`
- CRIAR `tests/engine/test_implement_secrets_gate.py`
- CRIAR `tests/engine/test_doctor_secrets_tools.py`

**Leituras antes:** `engine/verify.py` linhas 517-560 (`_DEFAULT_VALIDATORS` shape) · `engine/implement.py` linhas 425-577 (`_cc_bypass_log_path`, `_run_cc_gate`, `_render_cc_gate_block`, hook position) · `engine/doctor.py` linhas 654-689 (`_check_cc_gate_tools` shape + STATUS constants + registry).

**Critério de sucesso:** `check_secrets` aparece no cascade após `check_cyclomatic_complexity`. Per-task hook bloqueia commit em fail; bypass via `NO_SECRETS_GATE=1` loga em `.claude/state/secrets-gate-bypass.jsonl`. Doctor reporta `secrets-tools` (14ª categoria) com gitleaks + trufflehog. Tests passam.

**Steps:**

- [ ] Step 1 — Baseline.
- [ ] Step 2 — Escrever `tests/engine/test_verify_secrets_position.py`:
  - `test_check_secrets_in_default_validators` — `_DEFAULT_VALIDATORS` (após patch do arquivo) contém entry `{"name": "check_secrets", "file": "check_secrets.py", "severity": "fail"}`.
  - `test_check_secrets_after_check_cyclomatic_complexity` — index de `check_secrets` é estritamente maior que index de `check_cyclomatic_complexity` (anti-pattern gates ordenados; CC roda antes — mais barato).
  - `test_default_validator_specs_includes_check_secrets` — `_default_validator_specs(tmp_path)` (com arquivo `validators/check_secrets.py` no disco) inclui spec com nome `check_secrets`.
- [ ] Step 3 — Escrever `tests/engine/test_implement_secrets_gate.py`:
  - `test_run_secrets_gate_blocking_on_fail` — patch `validators.check_secrets.validate` retornando `{"status": "fail", ...}` → `_run_secrets_gate(project_root)` retorna dict com `blocking=True`.
  - `test_run_secrets_gate_non_blocking_on_pass` — patch retornando `{"status": "pass"}` → `blocking=False`.
  - `test_run_secrets_gate_bypass_via_env` — `monkeypatch.setenv("NO_SECRETS_GATE", "1")` → `_run_secrets_gate(tmp_path)` retorna `{"status": "warn", "message": "NO_SECRETS_GATE=1 — gate bypassed", "blocking": False}`; arquivo `.claude/state/secrets-gate-bypass.jsonl` existe e contém 1 linha JSON com `at` (timestamp ISO) + `reason`.
  - `test_run_secrets_gate_handles_import_failure` — patch sys.modules pra falhar import → `blocking=False` + status warn.
  - `test_run_secrets_gate_handles_validator_crash` — patch validate pra raise → `blocking=False` + status warn cita exc.
  - `test_apply_mode_handoff_blocks_when_secrets_gate_fails` — integração com `_apply_mode_handoff`; observa que `cc_result` ok mas `secrets_result.blocking=True` → handoff aborta antes de "1) forge verify" lines.
- [ ] Step 4 — Escrever `tests/engine/test_doctor_secrets_tools.py`:
  - `test_check_secrets_tools_reports_both_binaries` — `_check_secrets_tools(tmp_path)` retorna `_CategoryReport("secrets-tools", checks)` com ≥2 checks (`gitleaks`, `trufflehog`).
  - `test_check_secrets_tools_warns_when_missing` — monkeypatch `shutil.which` pra retornar None → cada check tem `_STATUS_WARN` + hint contém "brew install".
  - `test_check_secrets_tools_ok_when_found` — patch `shutil.which` pra retornar path → status `_STATUS_OK`.
  - `test_doctor_registry_includes_secrets_tools` — chama o entry-point que constrói lista de categorias (ver `engine/doctor.py` linha 142 atual — `_check_cc_gate_tools(project_root)` aparece na lista; adicionar `_check_secrets_tools(project_root)`) → resultado inclui `secrets-tools`.
- [ ] Step 5 — `pytest tests/engine/test_verify_secrets_position.py tests/engine/test_implement_secrets_gate.py tests/engine/test_doctor_secrets_tools.py -xvs` → FAIL.
- [ ] Step 6 — Implementar:
  - `engine/verify.py`: APPEND entry após `check_cyclomatic_complexity` em `_DEFAULT_VALIDATORS`:
    ```python
    {
        "name": "check_secrets",
        "file": "check_secrets.py",
        "severity": "fail",
    },
    ```
  - `engine/implement.py`: APPEND seção `# ── Secrets gate per-task hook ──` após o bloco do CC gate (~linha 535), espelhando o shape de `_run_cc_gate` mas chamando `validators.check_secrets.validate(project_root, stage="per_task")`. Função `_secrets_bypass_log_path(project_root)` retorna `project_root / ".claude" / "state" / "secrets-gate-bypass.jsonl"`. Env var: `NO_SECRETS_GATE`. Render reuso: criar `_render_secrets_gate_block(result)` que segue o mesmo pattern de `_render_cc_gate_block` (preferindo o campo `render`). Em `_apply_mode_handoff`, APPEND após o bloco do CC gate:
    ```python
    secrets_result = _run_secrets_gate(project_root)
    if secrets_result.get("blocking"):
        _render_secrets_gate_block(secrets_result)
        renderer.write("")
        renderer.write(
            "Resolva o gate antes de commitar. Re-rode `forge implement` "
            "depois de remover/rotacionar ou adicionar SECRETS-OVERRIDE no commit body."
        )
        return
    if secrets_result.get("status") == "warn":
        msg = secrets_result.get("message", "")
        if msg:
            renderer.write(renderer.dim(f"secrets-gate: {msg}"))
            renderer.write("")
    ```
  - `engine/doctor.py`: APPEND `_check_secrets_tools` espelhando `_check_cc_gate_tools` (linhas 654-689). Tools list:
    ```python
    tools = [
        ("gitleaks", "brew install gitleaks    # or: go install github.com/gitleaks/gitleaks/v8@latest"),
        ("trufflehog", "brew install trufflehog"),
    ]
    ```
    Categoria nome: `"secrets-tools"`. Registrar a chamada `_check_secrets_tools(project_root)` na lista atual de categorias (atualmente em `engine/doctor.py:142` aparece `_check_cc_gate_tools(project_root)`; adicionar logo abaixo).
- [ ] Step 7 — `pytest tests/engine/...` → PASS.
- [ ] Step 8 — Suite full.
- [ ] Step 9 — Commit: `feat(engine): wire check_secrets into verify cascade + implement hook + doctor`

**Anti-padrões:**
- NÃO refatorar `_run_cc_gate` pra extrair helper compartilhado `_run_per_task_gates(...)` — spec §4 explicitamente difere essa extração pra R1.2+ (princípio Phase 0: 2-3 consumers documentados antes de extrair).
- NÃO bypass cascade Decision 23 (fail-fast) — entry só APPEND, ordem preservada (CC depois secrets).
- NÃO mudar shape do `_CategoryReport` em doctor — só append nova categoria.

---

## Task 6 — Integration tests end-to-end + doc-sync (8 docs)

**Arquivos permitidos:**
- CRIAR `tests/integration/test_secrets_gate_end_to_end.py`
- CRIAR `tests/fixtures/secrets/file_with_secret.kt`
- CRIAR `tests/fixtures/secrets/file_with_test_fixture.kt`
- MODIFY `CHANGELOG.md`
- MODIFY `docs/design/08-session-handoff.md`
- MODIFY `README.md`
- MODIFY `docs/schemas/workflow-config.md`
- MODIFY `docs/design/07-discipline.md`
- MODIFY `docs/design/04-pending.md`
- MODIFY `.claude/rules/testing.md`
- MODIFY `.claude/rules/reuse.md`

**Leituras antes:** spec §5 (testing strategy + doc-sync matriz literal) · `.claude/rules/doc-sync.md` (mandamento #6 — matriz código→docs) · `.claude/rules/testing.md` §"Validators são código".

**Critério de sucesso:** Integration tests verdes. 8 docs sincronizados conforme spec §5. Suite full ≥ baseline + ~16 (unit + integration somados). Mandamento #1 NÃO triggera (nenhuma decisão locked tocada).

**Steps:**

- [ ] Step 1 — Criar fixtures:
  - `tests/fixtures/secrets/file_with_secret.kt`:
    ```kotlin
    // fixture: simula vazamento de token AWS em código real.
    // Chars FAKE no sufixo garantem que trufflehog --only-verified NÃO bate.
    object AwsConfig {
        const val ACCESS_KEY = "AKIA00000000FAKE0000"
    }
    ```
  - `tests/fixtures/secrets/file_with_test_fixture.kt`:
    ```kotlin
    // fixture pra demonstrar SECRETS-OVERRIDE no commit body.
    // O integration test gera commit body contendo:
    //   SECRETS-OVERRIDE: tests/fixtures/secrets/file_with_test_fixture.kt:6 kind=aws_access_key — test fixture
    object FakeAws {
        const val KEY = "AKIA00000000FAKE0001"
    }
    ```
- [ ] Step 2 — Escrever `tests/integration/test_secrets_gate_end_to_end.py` (marker `integration`):
  ```python
  import pytest
  import shutil

  pytestmark = pytest.mark.integration


  def test_cascade_position_correct(tmp_project, ...):
      """check_secrets aparece no cascade após check_cyclomatic_complexity."""

  def test_failfast_skips_secrets_when_prior_validator_fails(...):
      """Cascade Decision 23: CC falha → secrets nem roda."""

  def test_per_task_fail_blocks_commit(...):
      """Subagent simulado escreve file_with_secret.kt; per-task hook detecta
      via gitleaks → handoff aborta antes do commit. Mensagem 3-caminhos
      no stderr."""

  def test_per_task_override_permits_commit(...):
      """Mesmo setup + commit body contém SECRETS-OVERRIDE matching →
      finding silenced, commit ocorre."""

  @pytest.mark.skipif(not shutil.which("gitleaks"), reason="gitleaks ausente")
  def test_smoke_gitleaks_real_detects_fixture(...):
      """Roda gitleaks real em fixture; espera fail com kind detectado."""

  @pytest.mark.skipif(not shutil.which("trufflehog"), reason="trufflehog ausente")
  def test_smoke_trufflehog_real_skips_fake_token(...):
      """Fixture com AKIA00000000FAKE0000 — trufflehog --only-verified
      não confirma (token não existe na AWS real) → pass legítimo.
      Doc no docstring: não dá pra testar verified=true em CI sem leak real."""
  ```
- [ ] Step 3 — Rodar `pytest tests/integration/test_secrets_gate_end_to_end.py -m integration -xvs`. Tests podem precisar de ajustes nos wirings das Tasks 3-5 — fix loop até verde.
- [ ] Step 4 — Doc-sync (matriz literal do spec §5):

  **CHANGELOG.md** — APPEND em `## [Unreleased] ### Added`:
  > Check Secrets gate (`check_secrets`) — per-stage split: gitleaks no `forge implement` per-task hook (fast, regex), trufflehog `--only-verified` na cascade de `forge verify` (deep, verificação ativa). Override via `SECRETS-OVERRIDE: <file>:<line> kind=<token-type> — <razão>` no commit body. Hard-fail sempre. Validators 15→16, doctor 13→14 categorias.

  **docs/design/08-session-handoff.md** — atualizar:
  - `**Última atualização:**` → `2026-06-05 (v1.2-dev — R1.1 secrets gate)`
  - `**Estado:**` → `"v1.1 feito + Phase 0 mergeado; v1.2-dev R1.1 (check_secrets) shipping"`
  - Tabela `| Categoria | Status |` ganha linha "Secrets gate | shipping (R1.1)"

  **README.md** — Stats:
  - validators: 15 → 16
  - doctor categorias: 13 → 14
  - tests baseline: bump pro count após esta wave

  **docs/schemas/workflow-config.md** — APPEND bloco completo:
  ```yaml
  secrets-gate:
    enabled: true
    ignore-paths:
      - "tests/fixtures/secrets/.*"
      - ".*\\.lock$"
    per_task:
      tool: gitleaks                   # fast scan no implement hook
    cascade:
      tool: trufflehog
      only_verified: true              # apenas tokens validados ativamente
  ```
  + 4-5 linhas de prose explicando semântica de cada campo (override por commit body, hard-fail policy, tool missing → warn).

  **docs/design/07-discipline.md §2 (cascade)** — APPEND linha de `check_secrets` após `check_cyclomatic_complexity`. Voz mentor calmo, sem inflar.

  **docs/design/04-pending.md** — APPEND 3 gaps:
  ```markdown
  ### SECRETS-1 — Custom rules per project (deferred v1.3+)
  ...

  ### SECRETS-2 — History scan periódico (out-of-scope até phase 5)
  ...

  ### SECRETS-3 — Webhook/notify on detection (out-of-scope até phase 6)
  ...
  ```
  + atualizar registro de GATE-INFRA-1 com confirmação YAGNI (secrets não usa `gate_threshold_lookup`; defer permanece até R2.2 cognitive complexity).

  **.claude/rules/testing.md** — em `## Validators são código`, append mention:
  > Novo validator em v1.2-dev: `check_secrets` (gate multi-tool, per-stage split — gitleaks no per-task, trufflehog na cascade). Tests em `tests/validators/test_check_secrets*.py` + `tests/integration/test_secrets_gate_end_to_end.py`.

  **.claude/rules/reuse.md** — em "Infra reusável de validators (Phase 0 — v1.2-dev+)", append no fim:
  > **Exemplo concreto 2 — `check_secrets` (R1.1, v1.2-dev):** validator 150-200 LOC composto inteiramente da infra Phase 0. Stage selection (per_task → gitleaks vs cascade → trufflehog) via dict de `cmd_builders`. Override-justify via `apply_overrides` com cover-key `(file, line, kind)`. Render 3-caminhos local (vocabulário de secrets, não generalizado em `format_three_paths_message`). Prova que a extração paga — 2 consumers (CC + secrets) sem helper duplicado.

- [ ] Step 5 — `pytest` suite full verde. Count ≥ baseline + ~16.
- [ ] Step 6 — `forge verify` no próprio repo passa cascade sem hard fail.
- [ ] Step 7 — Commit: `feat(validators): check_secrets integration tests + doc-sync (8 docs)`

**Anti-padrões:**
- NÃO criar entrada `### Changed (load-bearing)` no CHANGELOG — nenhuma decisão revisitada, só `### Added`.
- NÃO inflar `08-session-handoff.md` com narrativa — apenas bumps dos campos canônicos.
- NÃO duplicar a entry de `### Added` se outras waves R1 abrirem na mesma branch — adicionar como sub-bullet sob `### Added` único.

---

## Self-review — Spec coverage matrix

| Spec section | Item | Implementado em |
|---|---|---|
| §1 New files | `validators/check_secrets.py` | Task 1-4 (incremental) |
| §1 New files | `tests/validators/test_check_secrets*.py` | Tasks 1, 2, 4 |
| §1 New files | `tests/integration/test_secrets_gate_end_to_end.py` | Task 6 |
| §1 New files | `tests/fixtures/secrets/*.json` | Task 2 |
| §1 New files | `tests/fixtures/secrets/*.kt` | Task 6 |
| §1 Modified | `engine/verify.py` (`_DEFAULT_VALIDATORS`) | Task 5 |
| §1 Modified | `engine/implement.py` (per-task hook) | Task 5 |
| §1 Modified | `engine/doctor.py` (secrets-tools) | Task 5 |
| §1 Modified | `docs/schemas/workflow-config.md` | Task 6 |
| §1 Modified | `docs/design/04-pending.md` (SECRETS-1/2/3) | Task 6 |
| §1 Modified | `docs/design/07-discipline.md §2` | Task 6 |
| §1 Modified | `CHANGELOG.md` | Task 6 |
| §1 Modified | `README.md` | Task 6 |
| §1 Modified | `docs/design/08-session-handoff.md` | Task 6 |
| §2 Pipeline 1 git_staged_files | Task 4 (validate orquestra) |
| §2 Pipeline 2 ignore-paths | Task 1 (helper) + Task 4 (uso) |
| §2 Pipeline 3 read_commit_body | Task 4 |
| §2 Pipeline 4 stage selection | Task 3 |
| §2 Pipeline 5 check_tool_available | Task 4 |
| §2 Pipeline 6 dispatch_native_tool | Task 3 (dispatch helper) + Task 4 (uso) |
| §2 Pipeline 7 parser | Task 2 |
| §2 Pipeline 8 apply_overrides | Task 4 |
| §2 Pipeline 9 result_fail + render | Task 4 |
| §2 Pipeline 10 result_pass/warn | Task 4 |
| §2 workflow-config shape | Task 6 (schema doc) |
| §2 SecretFinding shape | Task 1 |
| §2 GATE-INFRA-1 YAGNI confirmation | Task 6 (04-pending append) |
| §3 Render 3-caminhos canônico | Task 4 (snapshot tests + impl) |
| §3 Override mechanic | Task 4 |
| §4 Cascade integration | Task 5 |
| §4 Per-task hook integration | Task 5 |
| §4 Doctor secrets-tools | Task 5 |
| §5 Testing strategy unit | Tasks 1-4 (≥12 cenários) |
| §5 Testing strategy integration | Task 6 |
| §5 Doc-sync 8 docs | Task 6 |
| §5 Decisões load-bearing audit | Task 6 (handoff/CHANGELOG não acionam revisita) |
| §5 SECRETS-1/2/3 deferral | Task 6 |
| §5 Critério v1 1 LOC + ruff | Tasks 1-4 |
| §5 Critério v1 2 compõe infra | Tasks 1-4 (sem reimplementação local) |
| §5 Critério v1 3 cascade position | Task 5 |
| §5 Critério v1 4 per-task hook + bypass | Task 5 |
| §5 Critério v1 5 doctor categoria | Task 5 |
| §5 Critério v1 6 schema doc | Task 6 |
| §5 Critério v1 7 snapshot 3-paths × 2 stages | Task 4 |
| §5 Critério v1 8 override regex ≥5 cenários | Task 4 |
| §5 Critério v1 9 pytest verde + baseline | Task 6 |
| §5 Critério v1 10 doc-sync 8 docs | Task 6 |

Cobertura 100% dos 10 critérios de aceitação v1.

---

## Notas operacionais

- **Reuso da Phase 0 explícito** — cada task cita os helpers compostos. Validator final não reimplementa subprocess, regex de override, threshold lookup, nem result-dict shape.
- **GATE-INFRA-1 permanece YAGNI** — secrets é binário (detectou = fail), não tem threshold numérico por linguagem. `gate_threshold_lookup` não é tocado. Parametrização do helper espera R2.2 (Cognitive Complexity) como 2º consumer numérico documentado.
- **PR único pra Phase 0 + R1+** — commits acumulam no PR já aberto (per memory `feedback_single_branch_for_phased_work`). Doc-sync no R1.1 também atualiza referências à wave R1.2+ sem precisar reabrir PR.
- **Override-justify mechanic provada (2× consumer)** — após CC gate (`CC-OVERRIDE: <file>:<func> cc=N`), secrets é a 2ª aplicação literal do padrão (`SECRETS-OVERRIDE: <file>:<line> kind=<type>`). Reforça generalidade do helper `apply_overrides` sem precisar refatorar.
- **Voz mentor calmo nos artefatos** — render 3-caminhos, mensagens de warning, docstrings. Sem voz corporativa, sem emoji decorativo (header `🛑` é canônico da disciplina §1).
- **Mandamento 0 do orchestrator** — implementação rola via subagent dispatch (`gsd-executor`) com context-pack por task. Plan vira input do loop `subagent-driven-development`.
- **Trust-but-verify pós-dispatch** — após cada task commit, orchestrator lê diff (`git diff HEAD~1..HEAD --stat`) confirmando que só arquivos permitidos foram tocados. Desvio = revert + re-dispatch com whitelist mais explícita.

Em conflito spec × este plan: **spec vence**. Em conflito plan × implementação observada: implementação vence APENAS com retorno ao spec pra atualização — sem silent drift.
