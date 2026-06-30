"""BUG-4/MEM-5 (T4): o .gitignore gerado pelo init cobre os artefatos derivados.

Regressão: o init só gerava ``.claude/forge/.gitignore`` cobrindo ``state/`` +
checkpoints. Os artefatos derivados grandes vivem como IRMÃOS de ``forge/`` em
``.claude/`` (``graph.db``, ``cards/``, ``memory/``, ``locks/``,
``.memory-cli-checkpoint.yaml``) e um ``git add .`` commitava 2.3 MB de
graph.db + snapshots.

Decisão de escopo (A): semear/anexar também um ``.claude/.gitignore``
(append-only, não-destrutivo) cobrindo os irmãos derivados.
"""

from __future__ import annotations

from pathlib import Path

from engine.init import _write_claude_gitignores
from engine.utils.paths import claude_dir, forge_dir


_DERIVED = ("graph.db", "cards/", "memory/", "locks/", ".memory-cli-checkpoint.yaml")


def _read_all_gitignores(project_root: Path) -> str:
    """Concatena os .gitignore que o init gera sob .claude/ (forge/ + raiz)."""
    out = []
    for p in (claude_dir(project_root) / ".gitignore", forge_dir(project_root) / ".gitignore"):
        if p.is_file():
            out.append(p.read_text(encoding="utf-8"))
    return "\n".join(out)


def test_init_gitignore_covers_derived_artifacts(tmp_path: Path) -> None:
    """Cada artefato derivado aparece em algum .gitignore gerado sob .claude/."""
    _write_claude_gitignores(tmp_path)

    content = _read_all_gitignores(tmp_path)
    for artifact in _DERIVED:
        assert artifact in content, (
            f"artefato derivado {artifact!r} não coberto pelos .gitignore do init "
            f"(BUG-4/MEM-5) — conteúdo:\n{content}"
        )


def test_init_gitignore_covers_all_sqlite_wal_sidecars(tmp_path: Path) -> None:
    """MED-02: o graph.db roda em WAL mode → SQLite cria graph.db-wal E
    graph.db-shm (além do -journal de rollback). O bloco só cobria -journal e
    -wal, omitindo -shm — um ``git add .`` ainda commitaria o sidecar -shm.

    Assert que os 3 sufixos SQLite (-wal, -shm, -journal) estão cobertos.
    """
    _write_claude_gitignores(tmp_path)
    content = _read_all_gitignores(tmp_path)
    for suffix in ("graph.db-wal", "graph.db-shm", "graph.db-journal"):
        assert suffix in content, (
            f"sidecar SQLite {suffix!r} não coberto pelo .gitignore do init "
            f"(MED-02) — conteúdo:\n{content}"
        )


def test_init_gitignore_append_non_destructive(tmp_path: Path) -> None:
    """Um .claude/.gitignore pré-existente do usuário é PRESERVADO (append-only)."""
    user_line = "# linha do usuário — não tocar\nmeu-segredo.local\n"
    claude_gi = claude_dir(tmp_path) / ".gitignore"
    claude_gi.parent.mkdir(parents=True, exist_ok=True)
    claude_gi.write_text(user_line, encoding="utf-8")

    _write_claude_gitignores(tmp_path)

    after = claude_gi.read_text(encoding="utf-8")
    assert "meu-segredo.local" in after, "init clobberou o .gitignore do usuário"
    assert "graph.db" in after, "init não anexou os artefatos derivados"


def test_init_gitignore_idempotent(tmp_path: Path) -> None:
    """Rodar o gerador 2× não duplica o bloco do forge (marker idempotente)."""
    _write_claude_gitignores(tmp_path)
    first = (claude_dir(tmp_path) / ".gitignore").read_text(encoding="utf-8")
    _write_claude_gitignores(tmp_path)
    second = (claude_dir(tmp_path) / ".gitignore").read_text(encoding="utf-8")
    assert first == second, "segundo run alterou o .gitignore (não idempotente)"
