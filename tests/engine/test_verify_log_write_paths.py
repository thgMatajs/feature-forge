"""Investigação dos dois write-paths do verify-log (Fase 0c).

_write_verify_log_entry (engine/verify.py) serializa JSON DIRETO, sem validar.
append_verify_log (engine/memory/l1.py) VALIDA scope/result/warnings. O scout
indica que ambos escrevem no MESMO arquivo
(lifecycle_root(root)/slug/verify-log.jsonl). Este teste confirma a colisão e se
o caminho do verify.py produz entradas que append_verify_log rejeitaria.

Não assume o veredito — observa. O resultado dirige o 3-caminhos (A/B/C).

LN-2 (plan-auditor): a ordem de validação em l1.py é scope-dict (VL-003, ~L988)
ANTES de warnings degraded (VL-005, ~L1003). A forma do verify.py tem scope como
dict {"type","id"} — então é VL-003 que dispara primeiro, não VL-005. Asserta
pelo motivo CERTO (scope dict ∉ _VERIFY_SCOPES), não pelo que se assume.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.memory.l1 import append_verify_log
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


def test_both_paths_target_same_file(tmp_path: Path) -> None:
    slug = "feat-x"
    # Path 1: verify.py — escreve DIRETO, sem validar.
    _write_verify_log_entry(
        tmp_path,
        feature_slug=slug,
        scope_type="task",
        scope_id="t1",
        validators=["v1"],
        result="pass",
        hard_fails=[],
        warnings_list=[],
    )
    log_after_verify = lifecycle_root(tmp_path) / slug / "verify-log.jsonl"
    assert log_after_verify.exists(), "verify.py deveria ter escrito o log"
    # Path 2: l1.append_verify_log com uma entrada VÁLIDA (scope string, sem degraded)
    append_verify_log(
        slug,
        tmp_path,
        {
            "verify-id": "verify-manual",
            "scope": "task",
            "validators-run": ["v2"],
            "result": "pass",
        },
    )
    entries = _read_log(tmp_path, slug)
    # Se colidem no mesmo arquivo, há 2 linhas agora.
    assert len(entries) == 2, f"esperava ambos no mesmo arquivo, vi {len(entries)}"


def test_verify_py_entry_shape_would_violate_append_validation(tmp_path: Path) -> None:
    """A entrada que verify.py monta (scope dict + warnings list) seria rejeitada
    por append_verify_log? Reconstrói a MESMA forma e passa por append_verify_log.

    OBSERVAÇÃO (Fase 0c — diverge do que o plano supunha em LN-2): a rejeição NÃO
    é um MemoryError limpo de VL-003. O membership test `scope not in
    _VERIFY_SCOPES` (l1.py:988) estoura `TypeError: unhashable type: 'dict'` ANTES
    de poder formatar a mensagem VL-003 — porque `_VERIFY_SCOPES` é um set e um
    dict não é hashable. Ou seja: a forma do verify.py é rejeitada de modo AINDA
    MAIS grosseiro (exceção crua, não a MemoryError de schema). Isso reforça o
    drift (Caminho A): consolidar exige mapear scope dict → string validável.

    LN-2 honrado: assertamos o motivo REAL observado (TypeError por dict
    unhashable em VL-003), não o MemoryError de VL-005 que poderia ser assumido.
    """
    # Forma idêntica à de _write_verify_log_entry (verify.py:674-683):
    verify_shaped_entry = {
        "schema-version": 1,
        "verify-id": "verify-x",
        "at": "2026-06-30T00:00:00Z",
        "scope": {"type": "task", "id": "t1"},  # DICT, não string
        "validators-run": ["v1"],
        "result": "degraded",
        "hard-fails": [],
        "warnings": ["alguma ressalva"],  # LIST, não int
    }
    # A rejeição vem na checagem de scope (VL-003, l1.py:988), que é a PRIMEIRA
    # checagem de enum — e estoura TypeError porque o dict não é hashable contra
    # o set _VERIFY_SCOPES. Não chega na checagem de warnings (VL-005).
    with pytest.raises(TypeError, match="unhashable type: 'dict'"):
        append_verify_log("feat-x", tmp_path, dict(verify_shaped_entry))


def test_verify_py_writes_validated_shape_after_consolidation(tmp_path: Path) -> None:
    """Pós-consolidação (Fase 0c, Caminho A): o que verify.py PERSISTE de fato tem
    scope como STRING validável + warnings como CONTAGEM int — a forma que
    append_verify_log ACEITA. Lê o disco, não a suposição.

    Antes da consolidação, verify.py gravava scope dict + warnings list (bypass);
    test_verify_py_entry_shape_would_violate_append_validation documenta que essa
    forma seria rejeitada. Este teste prova que o write-path real já não a produz.
    """
    slug = "feat-y"
    _write_verify_log_entry(
        tmp_path,
        feature_slug=slug,
        scope_type="task",
        scope_id="t1",
        validators=["v1"],
        result="degraded",
        hard_fails=[],
        warnings_list=["ressalva-1"],
    )
    entries = _read_log(tmp_path, slug)
    assert len(entries) == 1
    persisted = entries[0]
    # scope é STRING validável (não dict) e scope-id preservado:
    assert persisted["scope"] == "task"
    assert persisted["scope-id"] == "t1"
    # warnings é a CONTAGEM int (VL-005); a lista humana vive sob warnings-list:
    assert persisted["warnings"] == 1
    assert persisted["warnings-list"] == ["ressalva-1"]
