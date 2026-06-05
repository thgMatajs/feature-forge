"""Phase 5 — Emit. Filtra findings actionable, dedup contra rejected,
escreve em proposed-evolutions.yaml (atomic).

Spec: docs/superpowers/specs/2026-06-05-forge-qa-design.md §5.5.

Algoritmo (resumo):
1. Filtra `severity ∈ {critical, high, medium}` (low/info não viram
   proposed-evolution).
2. Para cada finding actionable, carrega rejected-fingerprints.yaml
   (Decisão 25). Se fingerprint vetada → skip silencioso.
3. Append entry em `.claude/memory/L1/proposed-evolutions/proposed.yaml`.
4. Write atômico: temp file `proposed.yaml.tmp` → `os.replace(tmp, final)`.
5. OSError mid-write (ex: disk full) → retorna `write_failed=True`
   graceful, NÃO propaga; tmp file é limpo.

Decisão 26 alinhada: emit só REGISTRA proposed-evolutions. Não auto-aplica
mudança — apply é responsabilidade de `forge evolve` (endpoint humano).

Consumidor canônico: `engine/qa.py` Phase 5 (forge qa).

API pública:

    from engine.qa.emit import emit_proposed_evolutions

    summary = emit_proposed_evolutions(findings, project_root=Path.cwd())
    # summary == {"written": int, "skipped": int, "write_failed": bool}
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# Severity threshold pra virar proposed-evolution (spec §5.5).
# low e info são informativos no qa-report mas não geram entry em
# proposed.yaml — economiza ruído no endpoint humano (forge evolve).
_ACTIONABLE_SEVERITIES: set[str] = {"critical", "high", "medium"}

_PROPOSED_DIR_PARTS = (".claude", "memory", "L1", "proposed-evolutions")
_PROPOSED_FILENAME = "proposed.yaml"
_REJECTED_FILENAME = "rejected-fingerprints.yaml"


def _proposed_dir(project_root: Path) -> Path:
    return project_root.joinpath(*_PROPOSED_DIR_PARTS)


def load_rejected_fingerprints(project_root: Path) -> set[str]:
    """Lê rejected-fingerprints.yaml. Retorna set() se ausente ou corrompido.

    Decisão 25: fingerprints vetadas por humano em `forge evolve` ficam aqui
    pra Phase 5 dedupar — re-propor uma ideia rejeitada é ruído.

    Tolerâncias defensivas:
    - Arquivo ausente → set() (estado fresh é OK).
    - YAML vazio (`safe_load` retorna None) → set().
    - Top-level não-dict (ex: list) → set() (formato inválido, ignora).
    - Chave `rejected` ausente ou não-list → set().

    Args:
        project_root: raiz do projeto onde `.claude/memory/L1/...` mora.

    Returns:
        Conjunto de fingerprints (strings) a pular durante emit.
    """
    if not isinstance(project_root, Path):
        raise TypeError(
            f"project_root deve ser Path, recebido tipo {type(project_root).__name__}"
        )

    rejected_path = _proposed_dir(project_root) / _REJECTED_FILENAME
    if not rejected_path.exists():
        return set()

    data = yaml.safe_load(rejected_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return set()

    raw = data.get("rejected", [])
    if not isinstance(raw, list):
        return set()

    return {str(fp) for fp in raw}


def filter_actionable(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filtra findings com `severity ∈ _ACTIONABLE_SEVERITIES`.

    Findings com severity ausente, inválida, ou em {low, info} são
    descartados. Findings não-dict são silenciosamente ignorados
    (synthesis upstream deveria ter rejeitado, mas é defensa de cinto).
    """
    return [
        f
        for f in findings
        if isinstance(f, dict) and f.get("severity") in _ACTIONABLE_SEVERITIES
    ]


def emit_proposed_evolutions(
    findings: list[dict[str, Any]],
    *,
    project_root: Path,
) -> dict[str, Any]:
    """Escreve findings actionable em proposed.yaml (atomic). Retorna summary.

    Atomic write: temp file `proposed.yaml.tmp` recebe payload completo, depois
    `os.replace(tmp, final)` faz rename atômico em POSIX (e em Windows pra
    Python 3.3+). Ctrl+C mid-write não corrompe o final.

    Failure mode (disk full, perm error, etc.): OSError é capturada,
    `write_failed=True` é retornado, tmp file é limpo. Caller decide se
    avisa user (§10 Cena 8 sugere mensagem cinemática).

    Args:
        findings: lista de findings já sintetizados (Phase 4). Cada dict
            espera campos `severity`, `fingerprint`, `title`,
            `proposed_evolution.type`, `proposed_evolution.summary`.
        project_root: raiz do projeto pra resolver
            `.claude/memory/L1/proposed-evolutions/`.

    Returns:
        Dict com:
        - `written` (int): nº de findings que viraram entries novas.
        - `skipped` (int): nº de findings actionable que foram silenciados
          por fingerprint em rejected-fingerprints.yaml.
        - `write_failed` (bool): True se OSError durante write; False caso
          contrário. Quando True, `written` reflete o que ESPERAVA escrever
          (não o que foi efetivamente persistido).

    Raises:
        TypeError: se `findings` não é list ou `project_root` não é Path.
    """
    if not isinstance(findings, list):
        raise TypeError(
            f"findings deve ser list pra emit_proposed_evolutions, "
            f"recebido tipo {type(findings).__name__}"
        )
    if not isinstance(project_root, Path):
        raise TypeError(
            f"project_root deve ser Path, recebido tipo {type(project_root).__name__}"
        )

    rejected = load_rejected_fingerprints(project_root)
    actionable = filter_actionable(findings)

    to_write = [f for f in actionable if f.get("fingerprint") not in rejected]
    skipped = len(actionable) - len(to_write)

    # Sem trabalho a fazer: não cria arquivo final (evita criar proposed.yaml
    # vazio no fs do projeto). Esta short-circuit cobre os casos
    # `findings=[]` e "todos low/info".
    if not to_write:
        return {"written": 0, "skipped": skipped, "write_failed": False}

    out_dir = _proposed_dir(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / _PROPOSED_FILENAME

    # Carrega entries pré-existentes (append, não overwrite).
    existing: dict[str, Any] = {}
    if out_path.exists():
        loaded = yaml.safe_load(out_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            existing = loaded

    raw_entries = existing.get("entries", [])
    entries: list[dict[str, Any]] = list(raw_entries) if isinstance(raw_entries, list) else []

    for f in to_write:
        pe = f.get("proposed_evolution") or {}
        if not isinstance(pe, dict):
            pe = {}
        entries.append(
            {
                "type": pe.get("type", f"qa-finding-{f.get('vector', 'unknown')}"),
                "fingerprint": f.get("fingerprint", ""),
                "summary": pe.get("summary", f.get("title", "")),
                "payload": f,
            }
        )

    new_data = {"entries": entries}
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    write_failed = False
    try:
        tmp_path.write_text(
            yaml.safe_dump(new_data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        os.replace(tmp_path, out_path)
    except OSError:
        write_failed = True
        # Cleanup defensivo do tmp pra não vazar lixo no fs.
        try:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        except OSError:
            # Falha no cleanup é benigna — caller já vai reportar write_failed.
            pass

    return {
        "written": len(to_write),
        "skipped": skipped,
        "write_failed": write_failed,
    }
