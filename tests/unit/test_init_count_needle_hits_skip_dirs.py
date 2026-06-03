"""Unit tests — _count_needle_hits respeita _SKIP_DIRS.

Gap C16 do power-review PR #2: `rglob` ignorava apenas dirs cujo
componente começa com `.`. Diretórios como `node_modules/`, `build/`,
`.gradle/`, `Pods/`, `DerivedData/`, `dist/` (declarados em `_SKIP_DIRS`)
não eram filtrados — init em monorepos travava por minutos varrendo
deps/build artifacts.

Fix: filtra via `_SKIP_DIRS` no walk.
"""

from __future__ import annotations

from pathlib import Path

from engine.init import _count_needle_hits, _SKIP_DIRS


def test_count_needle_hits_skips_node_modules(tmp_path):
    """Needle dentro de node_modules NÃO deve contar (regressão monorepo)."""
    project = tmp_path / "p"
    nm = project / "node_modules" / "fake-dep"
    nm.mkdir(parents=True)
    (nm / "needle.kt").write_text(
        "import dagger.hilt.android.HiltAndroidApp\n", encoding="utf-8"
    )
    assert _count_needle_hits(project, "dagger.hilt.android") == 0


def test_count_needle_hits_skips_build_dir(tmp_path):
    project = tmp_path / "p"
    bd = project / "build" / "generated" / "src"
    bd.mkdir(parents=True)
    (bd / "Gen.kt").write_text("import dagger.hilt.android\n", encoding="utf-8")
    assert _count_needle_hits(project, "dagger.hilt.android") == 0


def test_count_needle_hits_skips_pods_dir(tmp_path):
    project = tmp_path / "p"
    pods = project / "Pods" / "SomeLib" / "Sources"
    pods.mkdir(parents=True)
    (pods / "Lib.kt").write_text("import io.realm.kotlin.foo\n", encoding="utf-8")
    assert _count_needle_hits(project, "io.realm.kotlin") == 0


def test_count_needle_hits_counts_files_outside_skip_dirs(tmp_path):
    """Confiança: o filtro não devora arquivos LEGÍTIMOS fora dos skip-dirs."""
    project = tmp_path / "p"
    src = project / "app" / "src" / "main" / "kotlin"
    src.mkdir(parents=True)
    (src / "App.kt").write_text(
        "import dagger.hilt.android.HiltAndroidApp\n", encoding="utf-8"
    )
    # node_modules sibling — não deve contar
    nm = project / "node_modules" / "x"
    nm.mkdir(parents=True)
    (nm / "Other.kt").write_text(
        "import dagger.hilt.android.HiltAndroidApp\n", encoding="utf-8"
    )
    # Resultado: só 1 hit (o legítimo em app/src/...)
    assert _count_needle_hits(project, "dagger.hilt.android") == 1


def test_skip_dirs_contains_expected_monorepo_culprits():
    """Garde-rail: _SKIP_DIRS deve cobrir os culpados clássicos."""
    expected = {"node_modules", "build", ".gradle", "Pods", "DerivedData", "dist"}
    assert expected.issubset(_SKIP_DIRS)
