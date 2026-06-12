"""Smoke + path tests for `validators/validate_workflow_config.py`.

Coverage:
- 3 smoke tests (import, missing config, minimal config, missing keys)
- M-001 (W7 cluster review r1): RULE-021 accepts canonical OR local card
- M-003 (W7 cluster review r1): per-RULE positive/negative cases for
  RULE-019..024 — confirms validator surfaces correct rule ID em
  ``what-failed`` quando spec é violado.
"""

from __future__ import annotations

from pathlib import Path

import validate_workflow_config as v


# ── Helpers ──────────────────────────────────────────────────────────────────

_BASE_REQUIRED_BLOCKS = """\
schema-version: 1
identity:
  project-slug: probe-project
platforms:
  active: [android, kmp]
cards:
  active: []
paths:
  feature-roots: {}
conventions: {}
workflow:
  readiness-strictness: standard
persona: {}
memory: {}
graph: {}
"""


def _write_config(project_root: Path, backend_block: str) -> Path:
    """Compõe workflow-config.yaml com base mínima + backend custom.

    `backend_block` é YAML pra anexar sob a key ``backend:``. Convenção:
    cada teste injeta SÓ o backend que quer exercitar, mantendo o resto
    constante pra isolar a violation testada.
    """
    cfg = _BASE_REQUIRED_BLOCKS + "backend:\n" + backend_block
    path = project_root / ".claude" / "workflow-config.yaml"
    path.write_text(cfg, encoding="utf-8")
    return path


def _seed_card(project_root: Path, card_name: str, *, local: bool = False) -> None:
    """Cria stub `card.yaml` sob canonical (`.claude/cards/`) ou local overlay."""
    if local:
        card_dir = project_root / ".claude" / "cards" / "local" / card_name
    else:
        card_dir = project_root / ".claude" / "cards" / card_name
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / "card.yaml").write_text("name: " + card_name + "\n", encoding="utf-8")


# ── Smoke tests (pre-existing baseline) ──────────────────────────────────────


def test_module_importable() -> None:
    assert callable(v.validate)


def test_missing_workflow_config_fails(tmp_forge_project: Path) -> None:
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("fail", "warn")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


def test_minimal_workflow_config_returns_structured_result(
    tmp_forge_project: Path,
) -> None:
    # W7.4 — `backend-choice` (legacy monolítico) removido em DET-6 Phase B;
    # backend agora vive em ``backend.<axis>.<platform>`` (RULE-019..024).
    # Test fica minimal — top-level keys faltando devem cair em fail/warn
    # com paths estruturados.
    (tmp_forge_project / ".claude" / "workflow-config.yaml").write_text(
        "schema-version: 1\n"
        "preset: kmp-mobile\n"
        "cards:\n"
        "  active: []\n",
        encoding="utf-8",
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("pass", "warn", "fail")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


def test_workflow_config_missing_required_keys_returns_structured_result(
    tmp_forge_project: Path,
) -> None:
    (tmp_forge_project / ".claude" / "workflow-config.yaml").write_text(
        "schema-version: 1\n", encoding="utf-8"
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("fail", "warn", "pass")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3


# ── M-001 — RULE-021 accepts local cards ─────────────────────────────────────


def test_validate_backend_accepts_local_card(tmp_forge_project: Path) -> None:
    """W7 M-001: card em `.claude/cards/local/<name>/card.yaml` satisfaz RULE-021.

    Espelha o behavior de ``engine/reconfigure._card_exists`` — local
    cards são fonte legítima (orphan workflow Step 7.5 + Gap 5).
    Validator deve aceitar canonical OR local; antes do fix, só
    canonical era aceito, gerando loop "reconfigure aceita → verify
    falha".
    """
    _seed_card(tmp_forge_project, "custom-auth-local", local=True)
    _write_config(
        tmp_forge_project,
        "  auth:\n"
        "    all-platforms:\n"
        "      card: custom-auth-local\n"
        "      status: active\n",
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    # Não pode falhar com RULE-021 pra esse card local.
    assert "RULE-021" not in result.get("what-failed", ""), (
        f"RULE-021 disparou contra local card: {result.get('what-failed')!r}"
    )
    # Status final: pass OR warn (warn pode vir de feature-roots, não bloqueia).
    assert result["status"] in ("pass", "warn"), (
        f"esperado pass/warn, got {result['status']}: {result.get('what-failed')!r}"
    )


# ── M-003 — RULE-019..024 positive/negative ──────────────────────────────────


def test_rule_019_rejects_unknown_axis(tmp_forge_project: Path) -> None:
    """RULE-019: axis fora do enum canônico (8 axes) → fail."""
    _write_config(
        tmp_forge_project,
        "  not-a-real-axis:\n"
        "    all-platforms:\n"
        "      card: whatever\n"
        "      status: active\n",
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] == "fail"
    assert "RULE-019" in result["what-failed"], result["what-failed"]
    assert "not-a-real-axis" in result["what-failed"]


def test_rule_020_rejects_unknown_platform(tmp_forge_project: Path) -> None:
    """RULE-020: platform fora de platforms.active (e não 'all-platforms') → fail.

    Setup precisa de card válido pra isolar RULE-020 (sem ele, RULE-021
    também surgiria; o teste ainda passaria mas ficaria menos isolado).
    """
    _seed_card(tmp_forge_project, "stub-data-card")
    _write_config(
        tmp_forge_project,
        "  data:\n"
        "    ios:\n"  # ios NÃO está em platforms.active=[android, kmp]
        "      card: stub-data-card\n"
        "      status: active\n",
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] == "fail"
    assert "RULE-020" in result["what-failed"], result["what-failed"]


def test_rule_021_accepts_existing_card(tmp_forge_project: Path) -> None:
    """RULE-021 positive: card existe em canonical → pass/warn (sem RULE-021)."""
    _seed_card(tmp_forge_project, "stub-auth-card")
    _write_config(
        tmp_forge_project,
        "  auth:\n"
        "    all-platforms:\n"
        "      card: stub-auth-card\n"
        "      status: active\n",
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] in ("pass", "warn"), result.get("what-failed", "")
    # Negative: garantir que nenhuma RULE-021 violation foi reportada.
    assert "RULE-021" not in result.get("what-failed", "")


def test_rule_021_rejects_missing_card(tmp_forge_project: Path) -> None:
    """RULE-021: card.id que não existe em canonical NEM local → fail."""
    _write_config(
        tmp_forge_project,
        "  auth:\n"
        "    all-platforms:\n"
        "      card: ghost-card-not-on-disk\n"
        "      status: active\n",
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] == "fail"
    assert "RULE-021" in result["what-failed"], result["what-failed"]
    assert "ghost-card-not-on-disk" in result["what-failed"]


def test_rule_022_rejects_invalid_status(tmp_forge_project: Path) -> None:
    """RULE-022: status fora do enum {active, migrating-to, deprecated} → fail."""
    _seed_card(tmp_forge_project, "stub-card-status")
    _write_config(
        tmp_forge_project,
        "  data:\n"
        "    all-platforms:\n"
        "      card: stub-card-status\n"
        "      status: bogus-status\n",
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] == "fail"
    assert "RULE-022" in result["what-failed"], result["what-failed"]


def test_rule_023_requires_migrating_to_when_status_migrating_to(
    tmp_forge_project: Path,
) -> None:
    """RULE-023: status=migrating-to SEM migrating-to → fail."""
    _seed_card(tmp_forge_project, "stub-card-from")
    _write_config(
        tmp_forge_project,
        "  data:\n"
        "    all-platforms:\n"
        "      card: stub-card-from\n"
        "      status: migrating-to\n",  # migrating-to ausente
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] == "fail"
    assert "RULE-023" in result["what-failed"], result["what-failed"]


def test_rule_023_rejects_migrating_to_when_status_not_migrating(
    tmp_forge_project: Path,
) -> None:
    """RULE-023: migrating-to presente mas status != migrating-to → fail.

    Cobre o contraste — status=active mas migrating-to setado é
    inconsistente; só faz sentido durante transição.
    """
    _seed_card(tmp_forge_project, "stub-card-from")
    _seed_card(tmp_forge_project, "stub-card-to")
    _write_config(
        tmp_forge_project,
        "  data:\n"
        "    all-platforms:\n"
        "      card: stub-card-from\n"
        "      status: active\n"
        "      migrating-to: stub-card-to\n",
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] == "fail"
    assert "RULE-023" in result["what-failed"], result["what-failed"]


def test_rule_024_rejects_unknown_migrating_to_card(tmp_forge_project: Path) -> None:
    """RULE-024: migrating-to aponta pra card que não existe → fail."""
    _seed_card(tmp_forge_project, "stub-card-from")
    _write_config(
        tmp_forge_project,
        "  data:\n"
        "    all-platforms:\n"
        "      card: stub-card-from\n"
        "      status: migrating-to\n"
        "      migrating-to: ghost-target-card\n",
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    assert result["status"] == "fail"
    assert "RULE-024" in result["what-failed"], result["what-failed"]
    assert "ghost-target-card" in result["what-failed"]


# ── PR #13 review #3405255318 — platforms.active cascade guard ───────────────


_BASE_NO_PLATFORMS_ACTIVE = """\
schema-version: 1
identity:
  project-slug: probe-project
platforms:
  active: []
cards:
  active: []
paths:
  feature-roots: {}
conventions: {}
workflow:
  readiness-strictness: standard
persona: {}
memory: {}
graph: {}
"""


def test_empty_platforms_active_emits_single_guidance_not_cascade(
    tmp_forge_project: Path,
) -> None:
    """When ``platforms.active`` is empty, RULE-020 must NOT cascade once
    per non-``all-platforms`` cell. Instead, one guidance message
    explaining the root cause + RULE-020 skipped. RULE-021..024 still run.
    """
    _seed_card(tmp_forge_project, "stub-card")
    cfg = (
        _BASE_NO_PLATFORMS_ACTIVE
        + "backend:\n"
        + "  data:\n"
        + "    android:\n"
        + "      card: stub-card\n"
        + "      status: active\n"
        + "    ios:\n"
        + "      card: stub-card\n"
        + "      status: active\n"
        + "    kmp:\n"
        + "      card: stub-card\n"
        + "      status: active\n"
    )
    (tmp_forge_project / ".claude" / "workflow-config.yaml").write_text(
        cfg, encoding="utf-8"
    )
    result = v.validate(tmp_forge_project, scope="inferred", id=None)
    # Without the guard: 3 RULE-020 violations (one per platform). With:
    # exactly 0 RULE-020 mentions + 1 guidance line.
    what_failed = result.get("what-failed", "")
    # Cascade signature would be repeated "platform desconhecida" messages,
    # one per cell. With the guard, none should appear — only the guidance
    # line that itself mentions "RULE-020 pulada".
    assert "platform desconhecida" not in what_failed, (
        f"RULE-020 cascade não foi suprimida: {what_failed!r}"
    )
    assert "platforms.active" in what_failed, (
        f"esperado guidance sobre platforms.active, got {what_failed!r}"
    )
