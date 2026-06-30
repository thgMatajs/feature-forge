"""Unit tests — `_glob_any` short-circuit de existência (WR-02, Onda 3).

`_glob_any` é um check de EXISTÊNCIA ("existe ALGUM match?"). O bug de
no-behavior-change (WR-02) era: o caminho `**/X` passava por
`_walk_recursive_pruned`, que materializa a árvore INTEIRA + `sort()`, e o
cap de 800 cortava os primeiros 800 em ordem LEXICOGRÁFICA. Com >800 paths
pós-poda casando o pattern, um arquivo cujo conteúdo casa o `needle` mas cujo
nome é lexicograficamente DEPOIS dos primeiros 800 caía fora do budget →
`_glob_any` retornava False incorretamente (o rglob lazy legado curto-
circuitava em inode-order, sem esse viés lexicográfico).

Fix: short-circuit — varrer o walk podado e retornar True no 1º match, sem
materializar/ordenar/capar a árvore toda. Detecção fica independente de
ordem e de cap.
"""

from __future__ import annotations

from engine.detection._eval import _glob_any


def test_glob_any_content_match_beyond_cap(tmp_path):
    """file-content: o ÚNICO arquivo cujo conteúdo casa o needle é
    lexicograficamente o ÚLTIMO numa árvore com >800 arquivos que casam o
    pattern mas NÃO o needle.

    Bug (cap-sort): após 800 arquivos consumidos do começo ordenado, o `break`
    do cap dispara ANTES de chegar no `zzz_target` → False.
    Fix (short-circuit): o walk encontra o conteúdo e retorna True.
    """
    for i in range(1000):
        (tmp_path / f"aaa_{i:05d}.kt").write_text("nothing here")
    (tmp_path / "zzz_target.kt").write_text("MARKER_NEEDLE present")
    assert _glob_any(tmp_path, "**/*.kt", "MARKER_NEEDLE") is True


def test_glob_any_existence_in_large_tree(tmp_path):
    """file-exists (needle=None): árvore grande com match → True.

    (Guard: o caminho needle=None já curto-circuitava no legado; aqui só
    garantimos que o short-circuit não regrediu o positivo em árvore grande.)
    """
    for i in range(1200):
        (tmp_path / f"aaa_{i:05d}.kt").write_text("x")
    assert _glob_any(tmp_path, "**/*.kt", None) is True


def test_glob_any_false_when_no_match_in_large_tree(tmp_path):
    """Árvore grande sem nenhum match → False (short-circuit não inventa hit)."""
    for i in range(1200):
        (tmp_path / f"f_{i:05d}.txt").write_text("noise")
    assert _glob_any(tmp_path, "**/*.kt", None) is False


def test_glob_any_false_when_needle_absent_large_tree(tmp_path):
    """file-content sem needle em lugar nenhum → False, mesmo em árvore >800."""
    for i in range(1000):
        (tmp_path / f"aaa_{i:05d}.kt").write_text("no marker")
    assert _glob_any(tmp_path, "**/*.kt", "MARKER_NEEDLE") is False
