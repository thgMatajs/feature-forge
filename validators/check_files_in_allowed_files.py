#!/usr/bin/env python3
"""check_files_in_allowed_files.py — Allowed-files fence enforcement.

Compares `git diff --cached --name-only` against the current task contract's
`allowed_files` globs. Any staged file outside the fence → fail.

Schema source: templates/task-contract.template.yaml §allowed_files.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePath
from typing import Any

from _common import (
    make_paths,
    result_fail,
    result_pass,
    result_warn,
    run_cli,
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.utils.paths import feature_dir  # noqa: E402
from engine.utils.yaml_io import read_yaml_or_default  # noqa: E402


def _git_staged_files(project_root: Path) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "diff", "--cached", "--name-only"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    if out.returncode != 0:
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def _find_task_yaml(project_root: Path, task_id: str) -> Path | None:
    base = project_root / "docs" / "feature-implementation-workflow" / "features"
    if not base.is_dir():
        return None
    for f in base.iterdir():
        if not f.is_dir():
            continue
        candidate = f / "tasks" / f"{task_id}.yaml"
        if candidate.is_file():
            return candidate
    return None


def _matches_any_glob(path: str, globs: list[str]) -> bool:
    """Match `path` against pathlib-style globs com suporte real a `**`.

    `PurePath.match` reconhece `**` como wildcard recursivo, ao contrário do
    `fnmatch` que trata cada `*` como segmento único. Mantemos o fallback
    "prefix" para o sufixo `/**` que ainda precisa cobrir o diretório raiz.
    """
    p = PurePath(path)
    for glob in globs:
        if not isinstance(glob, str) or not glob:
            continue
        if "{{" in glob:
            continue  # template placeholder
        try:
            if p.match(glob):
                return True
        except ValueError:
            continue
        if glob.endswith("/**/*") or glob.endswith("/**"):
            prefix = glob.rstrip("*").rstrip("/")
            if path.startswith(prefix + "/") or path == prefix:
                return True
    return False


def _resolve_task_id(kwargs: dict[str, Any]) -> str | None:
    given = kwargs.get("id")
    if isinstance(given, str) and given.upper().startswith("TASK-"):
        return given.upper()
    return None


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Check staged files vs task contract allowed_files."""
    staged = _git_staged_files(project_root)
    if not staged:
        return result_pass("nenhum arquivo staged — nada a checar")

    task_id = _resolve_task_id(kwargs)
    if not task_id:
        return result_warn(
            "sem --id TASK-NNNN — allowed_files fence não verificada",
            what_failed="no task id",
            where="--id TASK-NNNN required",
            why=["fence is per-task; precisa do contract pra cercar"],
        )

    task_yaml = _find_task_yaml(project_root, task_id)
    if not task_yaml:
        return result_fail(
            f"task contract {task_id} não encontrado",
            what_failed=f"missing {task_id}.yaml",
            where=str(project_root),
            why=[
                "task-contract-writer (Wave D) ainda não rodou para essa task",
                "Sem allowed_files, todo file staged é potencialmente out-of-bounds.",
            ],
            paths=make_paths(
                "Gerar o contract — `forge plan <feature>` (continua Wave D)",
                "task-contract-writer escreve esses arquivos.",
                "Unstage tudo — `git reset HEAD` e re-plan a feature primeiro",
                "Sem contract o commit não pode passar.",
                "Levantar — `forge plan <feature> --rerun=task-breakdown`",
                "Se o id está fora do range gerado.",
            ),
        )

    try:
        data = read_yaml_or_default(task_yaml, {}) or {}
    except Exception as exc:  # noqa: BLE001
        return result_fail(
            f"task contract {task_id} com YAML inválido",
            what_failed=str(exc),
            where=str(task_yaml.relative_to(project_root)),
            why=["Parsing falha — não é possível resolver allowed_files."],
            paths=make_paths(
                "Corrigir o YAML manualmente",
                "Indentação/aspas costumam ser a causa.",
                "Reverter o último edit — `forge undo`",
                "Se foi sobrescrito por engano.",
                "Re-gerar — `forge plan <feature> --rerun=task-contracts`",
                "Quando o sub-agent quebrou o shape.",
            ),
        )

    allowed = list(data.get("allowed_files") or [])
    allowed += list(data.get("allowed_files_card_contributions") or [])
    forbidden = list(data.get("forbidden_files") or [])

    out_of_fence: list[str] = []
    forbidden_hits: list[str] = []
    for f in staged:
        if _matches_any_glob(f, forbidden):
            forbidden_hits.append(f)
            continue
        if not _matches_any_glob(f, allowed):
            out_of_fence.append(f)

    if forbidden_hits:
        return result_fail(
            f"{len(forbidden_hits)} arquivo(s) staged batem com forbidden_files do {task_id}",
            what_failed=", ".join(forbidden_hits[:5]),
            where=str(task_yaml.relative_to(project_root)),
            why=[
                "forbidden_files é a regra mais forte do contract.",
                "Hard gate: no-files-outside-allowed-files + forbidden_files explícito.",
            ],
            paths=make_paths(
                "Unstage esses arquivos — `git restore --staged <file>`",
                "Eles pertencem a outra task ou outra camada.",
                "Atualizar o task contract — adicionar nos allowed se for legítimo",
                "Re-rodar task-contract-writer; nunca editar à mão sem split.",
                "Split em nova task — `forge plan <feature>` cria TASK nova",
                "Se de fato precisa tocar esses arquivos no mesmo PR.",
            ),
        )

    if out_of_fence:
        return result_fail(
            f"{len(out_of_fence)} arquivo(s) staged fora do allowed_files do {task_id}",
            what_failed=", ".join(out_of_fence[:5]) + (f" (+{len(out_of_fence)-5} more)" if len(out_of_fence) > 5 else ""),
            where=str(task_yaml.relative_to(project_root)),
            why=[
                "Hard gate: no-files-outside-allowed-files.",
                "allowed_files é a CERCA — discipline §1 anti-scope-creep.",
            ],
            paths=make_paths(
                "Unstage os arquivos fora da cerca — `git restore --staged <file>`",
                "Provavelmente trabalho de outra task entrou junto.",
                "Atualizar o contract — `forge plan <feature> --rerun=task-contracts`",
                "Se a cerca está errada, refazer o contract com escopo correto.",
                "Split em nova task — `forge plan <feature>`",
                "Se realmente precisa tocar esses arquivos agora.",
            ),
        )

    return result_pass(
        f"todos os {len(staged)} staged files dentro do allowed_files de {task_id}"
    )


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
