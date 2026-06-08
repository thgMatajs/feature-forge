"""Checkpoint persistence pra pause/resume de ``forge qa`` (Decisao 27).

SDD §16 edge 6 + Gap QA-12. SIGINT durante ``run_qa`` salva
``<run_tree.root>/checkpoint.json`` atomicamente; re-invocacao detecta o
checkpoint e retoma do ponto correto sem criar novo ``run_id``.

API publica:

    from engine.qa.checkpoint import (
        Checkpoint, CheckpointCorruptError,
        write_checkpoint, read_checkpoint, find_resumable_run,
    )

Atomic-write strategy reusa o pattern de ``engine.utils.yaml_io`` (tmp +
``os.replace``). Schema do checkpoint e minimo deliberadamente (YAGNI):
basta o suficiente pro orchestrator decidir "retomar daqui".
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from engine.qa._common import utc_iso_z
from engine.qa.ingest import sanitize_scope_target


@dataclass(frozen=True)
class Checkpoint:
    """Snapshot do progresso de uma run interrompida.

    Phases canonicas (espelha §5 do spec):
    - 0: ingest completo (run tree + handoff escritos)
    - 3: sandbox-ready (findings + sandbox-results.json processados)
    - 4: synthesis-done
    - 5: emit-done + qa-report.json finalizado

    Attributes:
        run_id: identificador da run interrompida.
        scope_type: ``feature`` | ``screen`` | ``task`` | ``paranoid``.
        scope_target: target conforme passado ao ``run_qa``.
        last_phase_completed: ultima phase totalmente concluida (0..5).
        interrupted_at: timestamp ISO 8601 UTC com sufixo ``Z``.
        findings_partial_count: contagem de findings/*.json no momento do
            checkpoint — usado pra UI ("retomando com N findings parciais").
    """

    run_id: str
    scope_type: str
    scope_target: str
    last_phase_completed: int
    interrupted_at: str
    findings_partial_count: int = 0


class CheckpointCorruptError(Exception):
    """Raised quando checkpoint.json existe mas e invalido.

    Cobre JSON malformado (parse error) E shape inesperado (fields
    obrigatorios faltando ou com tipo errado). Inclui ``path`` + ``reason``
    pra mensagem mentor-calmo apresentar 3-caminhos.
    """

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"checkpoint corrupto em {path}: {reason}")


_REQUIRED_FIELDS: tuple[tuple[str, type], ...] = (
    ("run_id", str),
    ("scope_type", str),
    ("scope_target", str),
    ("last_phase_completed", int),
    ("interrupted_at", str),
)


def write_checkpoint(
    run_tree_root: Path,
    *,
    run_id: str,
    scope_type: str,
    scope_target: str,
    last_phase_completed: int,
    findings_partial_count: int = 0,
) -> Path:
    """Escreve ``<run_tree_root>/checkpoint.json`` atomicamente.

    Strategy: write to ``checkpoint.json.tmp`` + ``os.replace`` (atomico em
    POSIX e Windows pra same-filesystem rename). Pattern espelha
    ``engine.utils.yaml_io.write_yaml``.

    Timestamp ``interrupted_at`` e gerado aqui em UTC ISO 8601 Z-suffixed
    pra consistencia com ``qa-report.json`` (§6.1 spec).

    Args:
        run_tree_root: dir raiz da run (``.planning/qa/<target>/<run-id>/``).
        run_id: identificador da run.
        scope_type: tipo do scope resolvido.
        scope_target: target conforme passado pelo user.
        last_phase_completed: phase concluida (0..5).
        findings_partial_count: contagem de findings ate o momento.

    Returns:
        Path do checkpoint escrito.
    """
    interrupted_at = utc_iso_z()
    checkpoint = Checkpoint(
        run_id=run_id,
        scope_type=scope_type,
        scope_target=scope_target,
        last_phase_completed=last_phase_completed,
        interrupted_at=interrupted_at,
        findings_partial_count=findings_partial_count,
    )

    run_tree_root.mkdir(parents=True, exist_ok=True)
    target = run_tree_root / "checkpoint.json"
    tmp = target.with_suffix(target.suffix + ".tmp")

    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(asdict(checkpoint), fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

    return target


def read_checkpoint(run_dir: Path) -> Optional[Checkpoint]:
    """Le ``<run_dir>/checkpoint.json`` se existir.

    Returns:
        ``Checkpoint`` quando arquivo existe e e valido. ``None`` quando
        arquivo nao existe.

    Raises:
        CheckpointCorruptError: arquivo existe mas JSON e invalido OU
            shape esperado nao bate (fields faltando, tipos errados).
    """
    path = run_dir / "checkpoint.json"
    if not path.exists():
        return None

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CheckpointCorruptError(
            path, f"falha de leitura: {exc}"
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CheckpointCorruptError(
            path, f"JSON malformado: {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise CheckpointCorruptError(
            path, f"esperado dict no topo, recebi {type(data).__name__}"
        )

    for field_name, expected_type in _REQUIRED_FIELDS:
        if field_name not in data:
            raise CheckpointCorruptError(
                path, f"campo obrigatorio ausente: {field_name}"
            )
        value = data[field_name]
        # bool e subclass de int em Python — rejeita explicitamente quando
        # esperamos int puro (last_phase_completed).
        if expected_type is int and isinstance(value, bool):
            raise CheckpointCorruptError(
                path,
                f"campo {field_name} deve ser {expected_type.__name__}, "
                f"recebi bool",
            )
        if not isinstance(value, expected_type):
            raise CheckpointCorruptError(
                path,
                f"campo {field_name} deve ser {expected_type.__name__}, "
                f"recebi {type(value).__name__}",
            )

    findings_partial = data.get("findings_partial_count", 0)
    if not isinstance(findings_partial, int) or isinstance(findings_partial, bool):
        raise CheckpointCorruptError(
            path,
            f"campo findings_partial_count deve ser int, "
            f"recebi {type(findings_partial).__name__}",
        )

    return Checkpoint(
        run_id=data["run_id"],
        scope_type=data["scope_type"],
        scope_target=data["scope_target"],
        last_phase_completed=data["last_phase_completed"],
        interrupted_at=data["interrupted_at"],
        findings_partial_count=findings_partial,
    )


def find_resumable_run(
    project_root: Path, scope_type: str, scope_target: str
) -> Optional[Path]:
    """Procura o run dir mais recente com checkpoint pendente.

    Criterio: dir em ``.planning/qa/<scope_target>/`` que contem ambos
    ``checkpoint.json`` E ``qa-report.json`` com ``verdict == "pending"``.
    "Mais recente" = ultimo na ordenacao alfabetica do nome do dir (run_id
    contem timestamp ISO 8601 monotonicamente crescente — sort lexicografico
    casa com cronologico).

    Args:
        project_root: raiz do projeto consumidor.
        scope_type: tipo do scope (mantido pra API; ainda nao usado na
            busca — futuro: discriminar runs de targets homonimos).
        scope_target: target conforme passado pelo user. Sanitizado via
            :func:`engine.qa.ingest.sanitize_scope_target` (mesmo helper
            usado por ``create_run_tree``), garantindo simetria entre
            "onde ingest gravou" e "onde resume procura".

    Returns:
        Path absoluto do run dir resumivel mais recente, ou ``None``.
        Tambem retorna ``None`` quando ``scope_target`` e
        irrepresentavel apos sanitizacao (ex.: input que vira string
        vazia ou comeca com ``.``) — coerente com "nao ha run resumivel
        a ser encontrada", deixando o caller cair no fluxo de fresh run
        que entao explode em ``create_run_tree`` com mensagem util.
    """
    safe_target = sanitize_scope_target(scope_target)
    if safe_target is None:
        return None

    scope_dir = project_root / ".planning" / "qa" / safe_target
    if not scope_dir.is_dir():
        return None

    candidates: list[Path] = []
    for entry in sorted(scope_dir.iterdir()):
        if not entry.is_dir():
            continue
        if not (entry / "checkpoint.json").is_file():
            continue
        qa_report = entry / "qa-report.json"
        if not qa_report.is_file():
            continue
        try:
            report = json.loads(qa_report.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # qa-report.json ilegivel: nao considera resumivel — fail
            # safe pra evitar loops infinitos de retry em run quebrada.
            continue
        if not isinstance(report, dict):
            continue
        if report.get("verdict") != "pending":
            continue
        candidates.append(entry)

    if not candidates:
        return None
    # candidates ja vem sorted; o ultimo e o mais recente.
    return candidates[-1]
