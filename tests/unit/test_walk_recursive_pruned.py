"""Unit tests — `_walk_recursive_pruned` (BUG-5, Onda 3).

Helper compartilhado que substitui os `rglob` crus do hot-path do init por
um walk manual que poda `_SKIP_DIRS` NA DESCIDA (não materializa
node_modules/.gradle inteiros antes de filtrar). Contrato central:
**no-behavior-change** sobre o CONJUNTO yielded vs `rglob(pattern)` filtrado
por skip-dirs.

Acks do plan-auditor cobertos aqui:
- H-001 (no-behavior-change de ORDEM): o helper ORDENA sua saída
  (determinístico). `test_pruned_walk_is_sorted` + `test_first_match_parity`.
- skip_dirs parametrizado (não unifica os 4 sets divergentes — cada site
  passa o seu).
"""

from __future__ import annotations

from pathlib import Path

from engine.detection._eval import _walk_recursive_pruned

_SKIP = {"node_modules", ".gradle", "build"}


def _rglob_filtered(root: Path, pattern: str, skip: set[str]) -> set[Path]:
    """Referência: rglob materializado + filtro skip-dirs pós-enumeração."""
    out = set()
    for p in root.rglob(pattern):
        rel = p.relative_to(root).parts
        if any(part in skip for part in rel):
            continue
        out.add(p)
    return out


def test_pruned_walk_equals_rglob_filtered(tmp_path):
    """Conjunto idêntico ao rglob filtrado (contrato no-behavior-change)."""
    (tmp_path / "node_modules" / "dep").mkdir(parents=True)
    (tmp_path / "node_modules" / "dep" / "X.kt").write_text("x")
    (tmp_path / ".gradle" / "cache").mkdir(parents=True)
    (tmp_path / ".gradle" / "cache" / "Y.kt").write_text("y")
    (tmp_path / "app" / "src").mkdir(parents=True)
    (tmp_path / "app" / "src" / "App.kt").write_text("a")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "Lib.kt").write_text("l")

    got = set(_walk_recursive_pruned(tmp_path, "*.kt", _SKIP))
    expected = _rglob_filtered(tmp_path, "*.kt", _SKIP)
    assert got == expected
    # Garde-rail: os legítimos estão, os skip-dirs não.
    rels = {p.relative_to(tmp_path) for p in got}
    assert Path("app/src/App.kt") in rels
    assert Path("lib/Lib.kt") in rels
    assert Path("node_modules/dep/X.kt") not in rels


def test_pruned_walk_does_not_descend_skip_dirs(tmp_path):
    """Poda na descida: arquivo fundo num skip-dir não aparece."""
    deep = tmp_path / "node_modules" / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "Deep.kt").write_text("d")
    got = {p.name for p in _walk_recursive_pruned(tmp_path, "*.kt", _SKIP)}
    assert "Deep.kt" not in got


def test_pruned_walk_empty_pattern_yields_dirs_only(tmp_path):
    """pattern="" replica rglob("") — SÓ diretórios (não arquivos), sem ValueError."""
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.txt").write_text("f")
    (tmp_path / "b.txt").write_text("b")
    got = set(_walk_recursive_pruned(tmp_path, "", _SKIP))
    expected = _rglob_filtered(tmp_path, "", _SKIP)
    assert got == expected


def test_pruned_walk_does_not_follow_dir_symlinks(tmp_path):
    """Symlink de diretório não é descido (evita ciclos)."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "R.kt").write_text("r")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    got = list(_walk_recursive_pruned(tmp_path, "*.kt", _SKIP))
    # O arquivo real aparece via "real/"; NÃO deve aparecer 2x via "link/".
    rels = [p.relative_to(tmp_path) for p in got]
    assert Path("real/R.kt") in rels
    assert Path("link/R.kt") not in rels


def test_pruned_walk_is_sorted(tmp_path):
    """H-001: saída DETERMINÍSTICA (ordenada) — rglob nativo é inode-order."""
    for d in ("m", "a", "z", "b"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "Spacing.kt").write_text("s")
    got = list(_walk_recursive_pruned(tmp_path, "Spacing.kt", _SKIP))
    assert got == sorted(got)


def test_first_match_parity(tmp_path):
    """H-001: o PRIMEIRO match do helper == o vencedor do rglob-filtrado-ordenado.

    Sites como design_system `break` no 1º token achado. O helper ordena, então
    o vencedor é determinístico e igual ao menor path do conjunto rglob filtrado.
    """
    for d in ("module-b", "module-a"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "Spacing.kt").write_text("s")
    first = next(iter(_walk_recursive_pruned(tmp_path, "Spacing.kt", _SKIP)))
    expected_winner = sorted(_rglob_filtered(tmp_path, "Spacing.kt", _SKIP))[0]
    assert first == expected_winner
