"""Consolidação do verify-log via fronteira validada (Fase 0c — Caminho A).

A investigação (test_verify_log_write_paths.py) confirmou que os dois write-paths
escrevem no MESMO arquivo e que verify.py persiste uma forma (scope dict +
warnings list) que append_verify_log REJEITA — de modo grosseiro (TypeError cru
por dict não-hashable no membership test do set _VERIFY_SCOPES).

O fix roteia _write_verify_log_entry pela fronteira validada append_verify_log,
mapeando seus campos pra forma aceita:
- scope dict {"type": t, "id": i} → `scope` = t (string validável) + `scope-id` = i
  (preservado, não validado contra o enum).
- warnings (list) → mantém a list humana sob `warnings-list`; quando
  result=="degraded", passa também `warnings` como int (a CONTAGEM) pra satisfazer
  MEM-L1-VL-005.

Estes testes FALHAM contra o código atual (RED — verify.py grava scope dict, que
NÃO passa pela validação) e PASSAM depois do fix (GREEN — a linha persistida é
validável + sem perda de info).
"""
from __future__ import annotations

import json
from pathlib import Path

from engine.memory.l1 import _VERIFY_RESULTS, _VERIFY_SCOPES, append_verify_log
from engine.utils.paths import lifecycle_root
from engine.verify import _write_verify_log_entry


def _read_log(root: Path, slug: str) -> list[dict]:
    p = lifecycle_root(root) / slug / "verify-log.jsonl"
    if not p.exists():
        return []
    return [
        json.loads(line)
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_persisted_entry_passes_append_validation_for_pass(tmp_path: Path) -> None:
    """Uma entrada `result=pass` + scope `feature` persistida por verify.py deve
    ter forma validável: scope é string ∈ _VERIFY_SCOPES, result ∈ _VERIFY_RESULTS,
    e o scope-id é preservado (sem perda de info)."""
    slug = "feat-a"
    _write_verify_log_entry(
        tmp_path,
        feature_slug=slug,
        scope_type="feature",
        scope_id=slug,
        validators=["v1", "v2"],
        result="pass",
        hard_fails=[],
        warnings_list=[],
    )
    entries = _read_log(tmp_path, slug)
    assert len(entries) == 1
    entry = entries[0]
    # Forma validável (o que append_verify_log exige):
    assert entry["scope"] in _VERIFY_SCOPES, entry["scope"]
    assert entry["scope"] == "feature"
    assert entry["result"] in _VERIFY_RESULTS, entry["result"]
    # scope-id preservado (não se perde no mapeamento dict→string):
    assert entry["scope-id"] == slug
    # validators-run preservado:
    assert entry["validators-run"] == ["v1", "v2"]


def test_persisted_entry_passes_append_validation_for_degraded(tmp_path: Path) -> None:
    """Caso de stress: mesmo com result=degraded + warnings, a linha persistida é
    validável — warnings vira a CONTAGEM int (VL-005) e a lista humana fica sob
    `warnings-list`. append_verify_log re-aplicado à entrada persistida NÃO estoura."""
    slug = "feat-b"
    _write_verify_log_entry(
        tmp_path,
        feature_slug=slug,
        scope_type="task",
        scope_id="TASK-1",
        validators=["v1"],
        result="degraded",
        hard_fails=[],
        warnings_list=["ressalva-1", "ressalva-2"],
    )
    entries = _read_log(tmp_path, slug)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["scope"] == "task"
    assert entry["scope-id"] == "TASK-1"
    # VL-005: degraded exige warnings>=1 como INT (contagem).
    assert isinstance(entry["warnings"], int)
    assert entry["warnings"] == 2
    # Info humana preservada (a lista de nomes) sob chave que não colide.
    assert entry["warnings-list"] == ["ressalva-1", "ressalva-2"]
    # Prova forte de validabilidade: re-passar a MESMA linha por append_verify_log
    # não levanta (a forma persistida É aceita pela fronteira validada).
    append_verify_log(slug, tmp_path, dict(entry))
    assert len(_read_log(tmp_path, slug)) == 2


def test_consolidated_entry_roundtrips_through_append(tmp_path: Path) -> None:
    """A linha que verify.py grava deve passar limpa por append_verify_log (a
    fronteira validada) — prova de que o bypass fechou."""
    slug = "feat-c"
    _write_verify_log_entry(
        tmp_path,
        feature_slug=slug,
        scope_type="task",
        scope_id="TASK-9",
        validators=["v"],
        result="warn",
        hard_fails=[],
        warnings_list=["w1"],
    )
    entry = _read_log(tmp_path, slug)[0]
    # Não estoura (nem TypeError nem MemoryError):
    append_verify_log(slug, tmp_path, dict(entry))
    assert len(_read_log(tmp_path, slug)) == 2
