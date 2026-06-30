"""Shared file walk cache para inventory extractors.

Os 3 extractors (design_system, i18n, conventions) faziam `rglob` independentes
sobre `project_root`, repetindo a varredura do disco. Este módulo provê um cache
LRU keyed por (project_root, extensions) — assim a primeira varredura paga o
custo e as próximas reusam o resultado.

Invalidação manual via `invalidate_cache()` quando o caller souber que arquivos
mudaram (incremental builds, ingest after edit).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from engine.detection._eval import _walk_recursive_pruned

_SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "build",
        ".gradle",
        "DerivedData",
        "Pods",
        "target",
        "dist",
        ".next",
        ".idea",
        ".vscode",
        ".claude",
        ".turbo",
        ".cache",
        "vendor",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "venv",
        "worktrees",
    }
)


@lru_cache(maxsize=32)
def walk_project(project_root: str, extensions: tuple[str, ...]) -> tuple[Path, ...]:
    """Walk `project_root` retornando paths cujo suffix está em `extensions`.

    - Pula diretórios irrelevantes (`_SKIP_DIRS`) — match é feito contra
      `path.relative_to(project_root).parts`, não `path.parts`. Isso garante
      que `.claude` só filtra quando é top-level no project_root (caso
      legítimo); quando aparece como PARENT do project_root (ex.: worktree
      em `.../.claude/worktrees/<branch>/`), não bloqueia o walk.
    - Resultado é tupla imutável sorted, segura para cache LRU.
    - Caller passa `str` (Path não é hashable em algumas combinações antigas).
    """
    root = Path(project_root)
    if not root.is_dir():
        return ()
    paths: list[Path] = []
    ext_set = {ext.lower() for ext in extensions}
    # BUG-5: `_walk_recursive_pruned` poda `_SKIP_DIRS` NA DESCIDA (não
    # materializa node_modules/.gradle inteiros antes do filtro). Conjunto
    # idêntico ao `rglob("*")` filtrado; o helper já ORDENA, então o
    # `paths.sort()` final fica redundante mas é mantido por clareza/segurança.
    # O filtro `relative_to(root)` pós-walk é preservado (cobre o caso
    # worktree onde `.claude/` é parent de root, não descendente).
    for path in _walk_recursive_pruned(root, "*", _SKIP_DIRS):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            # path não é descendente de root — skip por segurança
            continue
        if any(part in _SKIP_DIRS for part in relative.parts):
            continue
        if path.suffix.lower() in ext_set:
            paths.append(path)
    paths.sort()
    return tuple(paths)


def invalidate_cache() -> None:
    """Limpa o cache LRU. Chamar após edição de arquivos."""
    walk_project.cache_clear()
