"""Integration: composer emits Conflict cell em setup misto KMP.

W5.2 do plano DET-6. Cobre AC-5 do SPEC `det-6-multi-axis-backend.md`.

Cenário-âncora: um projeto KMP "no caminho da migração" — ainda tem
Retrofit ativo na Android-side (legado funcional) e já adotou Ktor
multiplatform no shared. Ambos batem signals acima do threshold no axis
`data`. O composer DEVE marcar a cell `(data, android)` como `Conflict`
expondo ambos candidatos pro auditor humano decidir cell-cardinality.

## Justificativa do desvio em relação ao plano W5.2

O plano canônico (`docs/superpowers/plans/det-6-multi-axis-backend.md`
§W5.2 linha 511) declara fixture estática em
`tests/fixtures/mixed-kmp-setup/`. Adotamos fixture programática via
`tmp_path` por uma razão concreta e reproduzível:

- `engine.init._SKIP_DIRS` filtra `.claude` no walk de signals
  (engine/init.py linha 832-847). Fixtures sob
  `tests/fixtures/...` rodando a partir de
  `.claude/worktrees/<wt>/tests/fixtures/...` não são lidas pelo
  scanner do helper.
- O suite unit `tests/unit/test_eval_gradle_dep.py::test_ac6_file_content_preserved`
  já evidencia o bug em campo: passa do repo root, falha do worktree.
- `tmp_path` resolve em `/tmp/.../` ou `/private/var/folders/...`,
  fora do filtro — o test fica hermético independente do contexto de
  execução (root, worktree, CI).

Os cards reais (`cards/retrofit-client/card.yaml` +
`cards/ktor-client/card.yaml`) seguem sendo a fonte das signals — o
composer recebe os dicts YAML carregados como `active_cards`. Apenas
o "ambiente sob análise" é programático.

## Reuso

- `engine.detection.composer.compose_backend_axes` (W5.1).
- `engine.detection.composer.Cell` / `Conflict` (W5.1).
- `_eval_detection_signals` / `_eval_gradle_dep` exercitados
  end-to-end via composer (sem mock).
"""

from pathlib import Path

import pytest
import yaml

from engine.detection.composer import Cell, Conflict, compose_backend_axes

REPO_ROOT = Path(__file__).resolve().parents[2]
CARDS_DIR = REPO_ROOT / "cards"


def _load_card_yaml(card_dir_name: str) -> dict:
    """Carrega card.yaml real do diretório `cards/<name>/`."""
    path = CARDS_DIR / card_dir_name / "card.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _build_mixed_kmp_setup(root: Path) -> None:
    """Materializa em `root` um projeto KMP simulando setup misto.

    Layout produzido:
        <root>/
            gradle/
                libs.versions.toml      ← retrofit + ktor coords
            build.gradle.kts            ← legacy mention pra cobrir signal 2
            src/main/kotlin/Api.kt      ← imports retrofit2 + io.ktor.client

    Esse layout faz com que ambos os cards atinjam score acima dos
    respectivos thresholds (retrofit 0.6 / ktor 0.5):
      - retrofit-client: gradle file-content (0.5) +
                          import retrofit2 file-content (0.2) +
                          @retrofit2.http file-content (0.3) → 1.0
      - ktor-client:     gradle-dep (0.5) +
                          build.gradle "io.ktor:ktor-client-" (0.3) +
                          HttpClient( file-content (0.3) +
                          io.ktor.client file-content (0.2) → 1.3
    """
    gradle_dir = root / "gradle"
    gradle_dir.mkdir(parents=True, exist_ok=True)
    (gradle_dir / "libs.versions.toml").write_text(
        """\
[versions]
retrofit = "2.9.0"
ktor     = "2.3.7"

[libraries]
retrofit          = { module = "com.squareup.retrofit2:retrofit", version.ref = "retrofit" }
ktor-client-core  = { module = "io.ktor:ktor-client-core",        version.ref = "ktor" }
""",
        encoding="utf-8",
    )

    (root / "build.gradle.kts").write_text(
        """\
plugins { kotlin("multiplatform") }

dependencies {
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("io.ktor:ktor-client-core:2.3.7")
}
""",
        encoding="utf-8",
    )

    src_dir = root / "src" / "main" / "kotlin"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "Api.kt").write_text(
        """\
package app.api

import retrofit2.Retrofit
import retrofit2.http.GET
import io.ktor.client.HttpClient

interface LegacyApi {
    @retrofit2.http.GET("/v1/items")
    fun fetch(): String
}

fun newClient() = HttpClient()
""",
        encoding="utf-8",
    )


@pytest.mark.integration
def test_composer_emits_conflict_in_mixed_kmp_setup(tmp_path: Path) -> None:
    """AC-5 W5.2: composer marca (data, android) como Conflict com 2 candidatos.

    Em projeto KMP misto (retrofit ativo + ktor ativo na Android-side),
    o composer não escolhe vencedor — expõe os candidatos pro auditor.
    """
    # Materializa ambiente sob análise.
    _build_mixed_kmp_setup(tmp_path)

    # Carrega cards reais (fonte canônica das signals).
    retrofit_card_yaml = _load_card_yaml("retrofit-client")
    ktor_card_yaml = _load_card_yaml("ktor-client")

    # Open Detail #8 do SPEC: caller-supplied platforms. Retrofit é
    # Android-side; Ktor cobre ambos Android e KMP no projeto misto.
    active_cards = [
        {
            "card_id": retrofit_card_yaml["identity"]["name"],
            "axis": retrofit_card_yaml["identity"]["category"],
            "platforms": ["android"],
            "detection": retrofit_card_yaml["detection"],
        },
        {
            "card_id": ktor_card_yaml["identity"]["name"],
            "axis": ktor_card_yaml["identity"]["category"],
            "platforms": ["android", "kmp"],
            "detection": ktor_card_yaml["detection"],
        },
    ]

    result = compose_backend_axes(tmp_path, active_cards)

    # Eixo `data` declarado por ambos os cards.
    assert "data" in result, f"expected 'data' axis in result, got {list(result)}"

    data_cells = result["data"]
    assert "android" in data_cells, (
        f"expected 'android' platform in data axis, got {list(data_cells)}"
    )

    android_cell = data_cells["android"]
    assert isinstance(android_cell, Conflict), (
        f"expected Conflict at (data, android), got {type(android_cell).__name__}: "
        f"{android_cell!r}"
    )

    candidates = android_cell.candidates
    assert len(candidates) == 2, (
        f"expected 2 candidates in conflict, got {len(candidates)}: {candidates!r}"
    )

    candidate_ids = {c.card_id for c in candidates}
    assert candidate_ids == {"retrofit-client", "ktor-client"}, (
        f"expected retrofit + ktor candidates, got {candidate_ids}"
    )

    # Cada candidato é uma Cell completa com score acima do threshold do
    # próprio card (defensivo: garante que score real foi medido, não zerado).
    for cand in candidates:
        assert isinstance(cand, Cell)
        assert cand.score > 0.0, (
            f"candidate {cand.card_id} has zero score — signals did not match: "
            f"{cand!r}"
        )
        assert cand.matched_signals, (
            f"candidate {cand.card_id} has empty matched_signals: {cand!r}"
        )

    # Platform `kmp` foi declarada apenas por ktor — deve ser Cell singular
    # (não Conflict). Defesa secundária contra regressão "composer ignora
    # platforms per-card e funde tudo".
    kmp_cell = data_cells.get("kmp")
    assert isinstance(kmp_cell, Cell), (
        f"expected Cell (single ktor) at (data, kmp), got {type(kmp_cell).__name__}: "
        f"{kmp_cell!r}"
    )
    assert kmp_cell.card_id == "ktor-client"
