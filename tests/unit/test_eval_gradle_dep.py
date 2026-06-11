"""Tests for gradle-dep signal type evaluation.

Cobre AC-1..AC-6 do SPEC det-3-gradle-dep-signal.md + edge cases
(TOML mal-formado, coordenada inválida, ambos formatos co-existindo).

CARD-020 tests cobrem validação de shape no loader (note: SPEC §AC-8
diz "CARD-019 ou next free"; CARD-019 já é usado por legacy-marker,
então a regra nova alocada é CARD-020 — ver `.planning/det-3/deviations.md`).
"""

from pathlib import Path

import pytest

from engine.init import _eval_detection_signals, _eval_gradle_dep

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _detection(coordinate: str, confidence: float = 0.5) -> dict:
    return {"signals": [{"type": "gradle-dep", "coordinate": coordinate, "confidence": confidence}]}


def test_ac1_toml_only_module_format() -> None:
    """AC-1: libs.versions.toml com `module = "io.ktor:..."` → match."""
    score, matched = _eval_detection_signals(
        FIXTURES / "gradle-dep-toml-only",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5
    assert any("io.ktor:ktor-client-core" in m for m in matched)


def test_ac2_toml_split_group_name_format() -> None:
    """AC-2: libs.versions.toml com `group + name` separados → match."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-toml-split",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5


def test_ac3_build_gradle_legacy() -> None:
    """AC-3: build.gradle.kts declarando dep diretamente → match."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-legacy",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5


def test_ac4_hybrid_no_double_counting() -> None:
    """AC-4: catálogo + build.gradle → match exatamente uma vez."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-hybrid",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5  # confidence única, sem soma duplicada


def test_ac5_negative_no_match() -> None:
    """AC-5: TOML sem a coordenada → sem match."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-negative",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.0


def test_ac6_file_content_preserved() -> None:
    """AC-6: file-content em **/*.kt continua funcionando após introdução de gradle-dep."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-file-content-preserved",
        {"signals": [{"type": "file-content", "glob": "**/*.kt", "contains": "io.ktor.client", "confidence": 0.2}]},
    )
    assert score == 0.2


def test_helper_returns_false_for_missing_coordinate() -> None:
    """Defesa: coordenada ausente retorna False (não raise)."""
    assert _eval_gradle_dep(FIXTURES / "gradle-dep-negative", "io.ktor:ktor-client-core") is False


def test_helper_handles_empty_coordinate() -> None:
    """Defesa: coordenada vazia/None retorna False (não raise)."""
    assert _eval_gradle_dep(FIXTURES / "gradle-dep-toml-only", "") is False
    assert _eval_gradle_dep(FIXTURES / "gradle-dep-toml-only", None) is False  # type: ignore[arg-type]


def test_helper_handles_malformed_toml(tmp_path: Path) -> None:
    """Defesa: TOML mal-formado não bloqueia (try/except silencioso)."""
    (tmp_path / "gradle").mkdir()
    (tmp_path / "gradle" / "libs.versions.toml").write_text("not valid toml [[[", encoding="utf-8")
    assert _eval_gradle_dep(tmp_path, "io.ktor:ktor-client-core") is False


# ── CARD-020 (shape validation for gradle-dep coordinate) ────────────────────
# Note: SPEC §AC-8 allowed "CARD-019 or next free". CARD-019 is already
# legacy-marker, so this rule lands as CARD-020. See `.planning/det-3/deviations.md`.


def _minimal_card(detection_signals: list[dict]) -> dict:
    """Build minimal valid card.yaml dict with custom detection.signals.

    Uses categories/maturities/provides labels that the canonical catalog
    accepts — keeps CARD-020 as the only violation under test (vs noise
    from CARD-004/005/006).
    """
    return {
        "schema-version": 1,
        "identity": {
            "name": "test-card",
            "version": "1.0.0",
            "category": "network",
            "maturity": "stable",
        },
        "provides": ["http-client"],
        "detection": {"signals": detection_signals},
    }


def test_card020_coordinate_shape_valid(tmp_path: Path) -> None:
    """CARD-020: coordinate válida no shape `<group>:<artifact>`."""
    from engine.cards.loader import validate_card_yaml

    (tmp_path / "README.md").write_text("# test", encoding="utf-8")
    valid = _minimal_card([
        {"type": "gradle-dep", "coordinate": "io.ktor:ktor-client-core", "confidence": 0.5}
    ])
    violations = validate_card_yaml(valid, tmp_path)
    assert not any("CARD-020" in v for v in violations), violations


def test_card020_coordinate_rejects_version_suffix(tmp_path: Path) -> None:
    """CARD-020: rejeita coordenada com versão sufixada."""
    from engine.cards.loader import validate_card_yaml

    (tmp_path / "README.md").write_text("# test", encoding="utf-8")
    bad = _minimal_card([
        {"type": "gradle-dep", "coordinate": "io.ktor:ktor-client-core:2.3.7", "confidence": 0.5}
    ])
    violations = validate_card_yaml(bad, tmp_path)
    assert any("CARD-020" in v for v in violations), violations


def test_card020_coordinate_rejects_missing_colon(tmp_path: Path) -> None:
    """CARD-020: rejeita coordenada sem ':' separator."""
    from engine.cards.loader import validate_card_yaml

    (tmp_path / "README.md").write_text("# test", encoding="utf-8")
    bad = _minimal_card([
        {"type": "gradle-dep", "coordinate": "io.ktor", "confidence": 0.5}
    ])
    violations = validate_card_yaml(bad, tmp_path)
    assert any("CARD-020" in v for v in violations), violations


# ── B-1 / B-2 / M-5 (review findings from PR #11 master review) ──────────────


def test_b1_toml_catalog_cached_per_project_root(tmp_path: Path) -> None:
    """B-1: `_load_toml_catalog` parseia o catálogo uma vez por project_root.

    Chamadas repetidas de `_eval_gradle_dep` com o mesmo project_root devem
    bater no cache `lru_cache` em vez de re-parsear `gradle/*.versions.toml`.
    """
    from unittest.mock import patch

    from engine.init import _eval_gradle_dep, _load_toml_catalog

    # Cache pode estar quente por testes anteriores — limpa para isolar.
    _load_toml_catalog.cache_clear()

    (tmp_path / "gradle").mkdir()
    (tmp_path / "gradle" / "libs.versions.toml").write_text(
        '[libraries]\nktor = { module = "io.ktor:ktor-client-core" }\n',
        encoding="utf-8",
    )

    with patch("engine.init.tomllib.load", wraps=__import__("tomllib").load) as spy:
        first = _eval_gradle_dep(tmp_path, "io.ktor:ktor-client-core")
        second = _eval_gradle_dep(tmp_path, "io.ktor:ktor-client-core")
        third = _eval_gradle_dep(tmp_path, "io.ktor:ktor-client-core")

    assert first is True and second is True and third is True
    assert spy.call_count == 1, (
        f"esperava 1 parse cached, observou {spy.call_count} — cache não pegou"
    )


def test_b2_toml_module_with_version_suffix_matches() -> None:
    """B-2: `module = "g:a:version"` casa coordinate `g:a` (prefix-tolerant).

    Formato inválido pelo padrão canônico mas observado no wild em
    libs.versions.toml. Helper deve comparar apenas os 2 primeiros
    segments split por `:`.
    """
    from engine.init import _load_toml_catalog

    _load_toml_catalog.cache_clear()

    score, matched = _eval_detection_signals(
        FIXTURES / "gradle-dep-toml-version-suffix",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5
    assert any("io.ktor:ktor-client-core" in m for m in matched)


def test_m5_build_gradle_coordinate_in_comment_ignored() -> None:
    """M-5: coordenada em comentário `//` não conta como match.

    Fixture tem `// io.ktor:ktor-client-core retired ...` no app/build.gradle.kts
    mas zero declaração real da dep. Helper deve retornar score 0.
    """
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-comment-only",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.0


def test_m5_build_gradle_block_comment_ignored() -> None:
    """M-5: coordenada em bloco `/* ... */` não conta como match."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-comment-only-block",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.0


# ── S-1 edge cases (PR #11 master review §S-1) ────────────────────────────────
# Cinco edge cases que documentam limites observáveis do helper. Cada test
# vira spec executável — se o comportamento mudar, o test trava e força
# revisita explícita da decisão (intencional vs regressão).


def test_s1_toml_with_utf8_bom_silently_skipped() -> None:
    """S-1.1: `libs.versions.toml` com BOM UTF-8 é silenciosamente ignorado.

    Documenta: tomllib (stdlib ≥3.11) rejeita BOM por aderir à TOML 1.0
    (que proíbe BOM em UTF-8). O helper engole o `TOMLDecodeError` no
    `try/except`, então um catálogo com BOM se torna invisível — não
    crasha mas tampouco ativa cards.

    Por que importa: editores Windows às vezes salvam com BOM por default.
    Usuário que migrar `libs.versions.toml` via copy/paste pode acabar
    com BOM sem saber. Score 0 + (cards matched: 0/N) sem aviso.

    Anotado pra próxima sessão: considerar warning em `forge doctor` quando
    `libs.versions.toml` começa com BOM. Comportamento atual é o trade-off
    aceito (silent skip alinhado a `_glob_any`).
    """
    from engine.init import _load_toml_catalog

    _load_toml_catalog.cache_clear()

    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-toml-bom",
        _detection("io.ktor:ktor-client-core"),
    )
    # Comportamento ATUAL: BOM rejeitado por tomllib, helper trata como
    # malformed → score 0. Se um dia o helper passar a strippar BOM
    # antes do parse, este test trava e força decisão explícita.
    assert score == 0.0


def test_s1_mixed_comment_and_real_dep_detected_once() -> None:
    """S-1.2: dep real + comentário com a mesma coordenada → 1 match, sem soma.

    Regressão de M-5 ampliada: o filtro de comentário não deve descartar a
    dep real só porque ela aparece também num comentário; e também não
    deve contar dobrado. Score == confidence única do signal.
    """
    from engine.init import _load_toml_catalog

    _load_toml_catalog.cache_clear()

    score, matched = _eval_detection_signals(
        FIXTURES / "gradle-dep-mixed-comment",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5
    # `matched` lista o signal uma única vez (mesma confidence aplicada
    # uma vez, sem dobrar entre o comentário e a dep real).
    matches_for_coord = [m for m in matched if "io.ktor:ktor-client-core" in m]
    assert len(matches_for_coord) == 1, (
        f"esperava 1 entrada em matched, observou {len(matches_for_coord)}: {matches_for_coord}"
    )


def test_s1_toml_block_table_form_matches() -> None:
    """S-1.3: `[libraries.name]` (block-table) casa igual a inline-table.

    TOML 1.0 permite as duas formas como equivalentes semânticos:
        # inline (usado em quase todos os projetos):
        ktor-client-core = { module = "io.ktor:ktor-client-core", ... }

        # block-table (válido mas raro):
        [libraries.ktor-client-core]
        module = "io.ktor:ktor-client-core"
        version.ref = "ktor"

    `tomllib.load` normaliza ambos para o mesmo dict, então o helper
    casa transparentemente. Test garante que essa equivalência sobrevive
    a refatorações futuras (ex.: alguém trocar `libraries.values()` por
    parsing manual).
    """
    from engine.init import _load_toml_catalog

    _load_toml_catalog.cache_clear()

    score, matched = _eval_detection_signals(
        FIXTURES / "gradle-dep-toml-block-table",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5
    assert any("io.ktor:ktor-client-core" in m for m in matched)


def test_s1_ktx_variant_does_not_match_base_coordinate_exact() -> None:
    """S-1.4: variante `-ktx` em TOML NÃO casa coordinate base (assimetria M-1).

    Documenta a decisão de match exato em TOML (`firebase-storage-ktx`
    não casa `firebase-storage`). Comportamento canônico do helper —
    `_module_matches_coordinate` compara `mod_parts[1] == coord_parts[1]`
    estritamente.

    Em build.gradle legado, o passo 2 usa substring, então
    `implementation("...firebase-storage-ktx:...")` casaria coordinate
    `com.google.firebase:firebase-storage` (substring match). Essa
    assimetria é tradeoff conhecido (M-1 do review do PR #11).

    Se algum dia o helper adotar prefix-aware em TOML (ex.:
    `mod_parts[1].startswith(coord_parts[1] + "-")`), este test trava
    e força revisita explícita da decisão.
    """
    from engine.init import _eval_gradle_dep, _load_toml_catalog

    _load_toml_catalog.cache_clear()

    # Coordinate base (sem -ktx) — único candidato no catálogo é o `-ktx`.
    result = _eval_gradle_dep(
        FIXTURES / "gradle-dep-toml-ktx-variant",
        "com.google.firebase:firebase-storage",
    )
    assert result is False, (
        "match exato em TOML virou prefix-aware — revisitar M-1 antes de mergear"
    )


def test_s1_custom_catalog_path_ignored_per_spec_nongoals() -> None:
    """S-1.5: catálogo fora de `gradle/*.versions.toml` é ignorado (SPEC §Non-Goals).

    SPEC det-3 §Non-Goals declara: "Resolução de catálogo TOML como graph
    completo — não fazemos parse semântico". Combinado com o glob
    canônico `gradle_dir.glob("*.versions.toml")`, qualquer catálogo em
    `dependencies/dependencies.toml`, `buildSrc/...`, `subprojects/.../`
    fica fora do scope v1.

    Comportamento atual: score 0 (silent). Limitação documentada em
    M-4 do review PR #11 (`forge doctor` poderia avisar; defer aceito).
    """
    from engine.init import _eval_gradle_dep, _load_toml_catalog

    _load_toml_catalog.cache_clear()

    result = _eval_gradle_dep(
        FIXTURES / "gradle-dep-custom-catalog",
        "io.ktor:ktor-client-core",
    )
    assert result is False, (
        "helper passou a varrer catálogos fora de gradle/ — revisitar SPEC §Non-Goals"
    )
