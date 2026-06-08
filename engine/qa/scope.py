"""Scope resolution pra forge qa (Phase 0 ingest).

Conversacional (Decisao 10 — sem flags). Resolve via 3-caminhos quando
ambiguo. Reusa convencao de path de engine.plan (mandamento #3):
features moram em ``docs/feature-implementation-workflow/features/<slug>/``.

Consumidor canonico: ``engine/qa.py`` Phase 0 ingest. API publica:

    from engine.qa.scope import resolve_scope, Scope, ScopeError
    scope = resolve_scope(raw_target, project_root=root)

Erros sao tipados (``ScopeAmbiguityError`` / ``ScopeMissingError``) e a
mensagem segue voz mentor calmo com remediation explicita.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


ScopeType = Literal["feature", "screen", "task", "paranoid"]


class ScopeError(RuntimeError):
    """Base pra erros de scope resolution."""


class ScopeAmbiguityError(ScopeError):
    """Mesmo input casa em 2+ scopes — pede 3-caminhos."""


class ScopeMissingError(ScopeError):
    """Scope target nao encontrado no projeto."""


@dataclass(frozen=True)
class Scope:
    """Scope resolvido. ``paths`` lista artefatos concretos (feature dir,
    screen yaml, task yaml) — consumido por Phase 0 ingest.
    """

    type: ScopeType
    target: str
    paths: tuple[Path, ...]


def resolve_scope(
    raw_target: str,
    *,
    project_root: Path,
    paranoid_max_features: int = 10,
) -> Scope:
    """Resolve scope conversacional.

    ``raw_target`` aceita 4 formas:

    - ``"paranoid"`` (literal) — enumera ate ``paranoid_max_features``
      feature dirs presentes em ``docs/feature-implementation-workflow/features/``.
    - ``"TASK-NNNN"`` (prefixo ``TASK-``) — procura task yaml em qualquer
      feature dir.
    - feature slug — casa em ``features/<slug>/``.
    - screen id — casa em ``features/<any>/screens/<id>.yaml``.

    Quando ``raw_target`` casa simultaneamente em feature E screen, dispara
    ``ScopeAmbiguityError`` com 3-caminhos no texto. Quando nao casa em
    nada, dispara ``ScopeMissingError``.

    Args:
        raw_target: input bruto do user. Deve ser str nao-vazia.
        project_root: raiz do projeto consumidor. Deve existir.
        paranoid_max_features: cap pra modo paranoid. Default 10.

    Raises:
        TypeError: ``raw_target`` nao e str, ``project_root`` nao e Path.
        ValueError: ``raw_target`` vazio, ``project_root`` inexistente.
        ScopeAmbiguityError: target casa em 2+ scopes.
        ScopeMissingError: target nao encontrado.
    """
    # Type guards defensivos — consumer pode passar lixo, nao queremos
    # AttributeError vazar.
    if not isinstance(raw_target, str):
        raise TypeError(
            f"raw_target deve ser str, recebi {type(raw_target).__name__!r}. "
            f"Passe o slug/id como string conversacional."
        )
    if not raw_target:
        raise ValueError(
            "raw_target vazio. Passe um slug de feature, screen id, "
            "TASK-NNNN, ou o literal 'paranoid'."
        )
    if not isinstance(project_root, Path):
        raise TypeError(
            f"project_root deve ser pathlib.Path, recebi "
            f"{type(project_root).__name__!r}."
        )
    if not project_root.exists():
        raise ValueError(
            f"project_root {project_root} nao existe. "
            f"Confira o cwd ou rode `forge init` antes."
        )
    if not isinstance(paranoid_max_features, int) or paranoid_max_features < 1:
        raise ValueError(
            f"paranoid_max_features deve ser int >= 1, recebi "
            f"{paranoid_max_features!r}."
        )

    if raw_target == "paranoid":
        features = _list_features_for_paranoid(
            project_root, cap=paranoid_max_features
        )
        if not features:
            raise ScopeMissingError(
                "Nenhuma feature em scope detectado pra paranoid. "
                "Rode `forge plan {slug}` antes."
            )
        return Scope(
            type="paranoid",
            target="paranoid",
            paths=tuple(features),
        )

    if raw_target.startswith("TASK-"):
        path = _find_task(raw_target, project_root)
        if path is None:
            raise ScopeMissingError(
                f"task {raw_target!r} nao encontrada em nenhuma feature. "
                f"Confira o id ou rode `forge plan` antes."
            )
        return Scope(type="task", target=raw_target, paths=(path,))

    # feature ou screen? Ambiguity check
    feature_path = _find_feature(raw_target, project_root)
    screen_path = _find_screen(raw_target, project_root)

    if feature_path is not None and screen_path is not None:
        raise ScopeAmbiguityError(
            f"target {raw_target!r} casa em feature E screen — ambiguo.\n"
            f"3-caminhos pra resolver:\n"
            f"  1) feature {feature_path} (re-invoque com o slug exato da feature)\n"
            f"  2) screen {screen_path} (re-invoque com screen id desambiguado)\n"
            f"  3) abortar e renomear um dos dois pra eliminar a colisao."
        )

    if feature_path is not None:
        return Scope(type="feature", target=raw_target, paths=(feature_path,))

    if screen_path is not None:
        return Scope(type="screen", target=raw_target, paths=(screen_path,))

    raise ScopeMissingError(
        f"target {raw_target!r} nao casa em feature, screen, ou task. "
        f"Confira slug ou rode `forge plan` antes."
    )


# ---------------------------------------------------------------------------
# Internals — path discovery (pattern espelhado de engine.plan)
# ---------------------------------------------------------------------------


def _features_root(root: Path) -> Path:
    return root / "docs" / "feature-implementation-workflow" / "features"


def _list_features_for_paranoid(root: Path, *, cap: int) -> list[Path]:
    """Lista feature dirs ate ``cap``. Ordenado alfabeticamente; ignora
    dirs hidden (``.``-prefixed) como ``.git``, ``.cache`` etc.
    """
    features_root = _features_root(root)
    if not features_root.exists():
        return []
    candidates: list[Path] = []
    for entry in sorted(features_root.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            candidates.append(entry)
        if len(candidates) >= cap:
            break
    return candidates


def _find_feature(slug: str, root: Path) -> Path | None:
    candidate = _features_root(root) / slug
    return candidate if candidate.is_dir() else None


def _find_screen(screen_id: str, root: Path) -> Path | None:
    features_root = _features_root(root)
    if not features_root.exists():
        return None
    # sorted(): determinismo cross-machine — iterdir() retorna em ordem
    # filesystem-dependente, mas scope resolution deve ser estavel.
    for feature_dir in sorted(features_root.iterdir()):
        if not feature_dir.is_dir():
            continue
        candidate = feature_dir / "screens" / f"{screen_id}.yaml"
        if candidate.is_file():
            return candidate
    return None


def _find_task(task_id: str, root: Path) -> Path | None:
    features_root = _features_root(root)
    if not features_root.exists():
        return None
    # sorted(): determinismo cross-machine (mesmo motivo de _find_screen).
    for feature_dir in sorted(features_root.iterdir()):
        if not feature_dir.is_dir():
            continue
        candidate = feature_dir / "tasks" / f"{task_id}.yaml"
        if candidate.is_file():
            return candidate
    return None
