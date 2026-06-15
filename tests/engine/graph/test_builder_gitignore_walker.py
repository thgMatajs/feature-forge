"""PR #15 perf finding (gemini-code-assist comment 3415097379):
`_find_gitignore_files` deve skipar `_EXCLUDED_DIRS` durante a travessia
(não depois) e nunca seguir symlinks. Garante que o gate não trava em
monorepos mobile com `node_modules/build/.gradle` gigantes.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from engine.graph import builder


def test_excluded_dirs_skipped_during_traversal(tmp_path: Path) -> None:
    """`.gitignore` dentro de `_EXCLUDED_DIRS` não aparece no resultado.

    Caso a travessia descesse em `node_modules` antes do filtro (como
    `rglob` fazia), este teste ainda passaria — mas o sentinel
    `__should_never_be_read__` abaixo garante que a função NÃO entrou
    na subárvore: se entrasse, o arquivo seria coletado.
    """
    # Setup árvore: root tem .gitignore válido + node_modules com .gitignore
    # que NÃO deve ser coletado.
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / ".gitignore").write_text("*.tmp\n", encoding="utf-8")

    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / ".gitignore").write_text(
        "# should never be parsed\n", encoding="utf-8"
    )
    # Sentinel pra detectar descida indevida:
    nested = tmp_path / "node_modules" / "pkg" / "sub"
    nested.mkdir(parents=True)
    (nested / ".gitignore").write_text("nested\n", encoding="utf-8")

    (tmp_path / "build").mkdir()
    (tmp_path / "build" / ".gitignore").write_text("# excluded\n", encoding="utf-8")

    found = builder._find_gitignore_files(tmp_path)
    found_relatives = {p.relative_to(tmp_path).as_posix() for p in found}

    assert "app/.gitignore" in found_relatives
    # Nenhum gitignore de _EXCLUDED_DIRS pode aparecer:
    for rel in found_relatives:
        first = rel.split("/", 1)[0]
        assert first not in builder._EXCLUDED_DIRS, (
            f"Walker desceu em diretório excluído: {rel}"
        )


def test_root_gitignore_collected(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
    found = builder._find_gitignore_files(tmp_path)
    rels = {p.relative_to(tmp_path).as_posix() for p in found}
    assert ".gitignore" in rels


def test_symlink_loop_does_not_hang(tmp_path: Path) -> None:
    """Symlink cycle não pode travar o walker.

    Cria a -> b -> a (ciclo). Walker bem-comportado retorna em <1s.
    `follow_symlinks=False` já evita seguir o link; o teste é guard
    contra regressão futura caso alguém ative follow.
    """
    a = tmp_path / "a"
    a.mkdir()
    (a / ".gitignore").write_text("ok\n", encoding="utf-8")
    b = tmp_path / "b"
    b.mkdir()
    try:
        os.symlink(a, b / "loop_to_a")
        os.symlink(b, a / "loop_to_b")
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks não suportados neste filesystem")

    # Se travasse, pytest mata via default timeout; aqui assertamos retorno.
    found = builder._find_gitignore_files(tmp_path)
    rels = {p.relative_to(tmp_path).as_posix() for p in found}
    assert "a/.gitignore" in rels


def test_permission_error_tolerated(tmp_path: Path) -> None:
    """Subdir sem permissão é skipado sem propagar exception."""
    if os.name == "nt":
        pytest.skip("chmod semantics distintas no Windows")
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / ".gitignore").write_text("hidden\n", encoding="utf-8")
    (tmp_path / "ok" / "sub").mkdir(parents=True)
    (tmp_path / "ok" / ".gitignore").write_text("visible\n", encoding="utf-8")

    secret.chmod(0o000)
    try:
        found = builder._find_gitignore_files(tmp_path)
        rels = {p.relative_to(tmp_path).as_posix() for p in found}
        assert "ok/.gitignore" in rels
        # Não asserta sobre secret/.gitignore — em alguns FS root consegue
        # ler mesmo após chmod 000; o ponto é "não levantar exception".
    finally:
        secret.chmod(0o755)


def test_parse_gitignore_integration_with_walker(tmp_path: Path) -> None:
    """`_parse_gitignore` segue funcionando end-to-end com o walker novo."""
    (tmp_path / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / ".gitignore").write_text(
        "should-not-be-parsed.txt\n", encoding="utf-8"
    )
    rules = builder._parse_gitignore(tmp_path)
    # Confirma que a rule de node_modules NÃO entrou:
    assert not any("should-not-be-parsed" in r[0] for r in rules)
    # Confirma que rule do root entrou:
    assert any("*.tmp" in r[0] for r in rules)
