"""Grep-gate: o literal 'feature-implementation-workflow' nao pode restar
em nenhum arquivo de comportamento (engine, validators, hooks, agents,
presets, cards, templates, tests) apos o rename de Task 2.

O split de LEGACY em duas partes evita que o proprio arquivo de teste
case no grep.
"""

import subprocess
from pathlib import Path

# Construido por partes pra o proprio arquivo de teste nao casar no grep.
LEGACY = "feature-implementation" + "-workflow"
BEHAVIOR_DIRS = ["engine", "validators", "hooks", "agents", "presets", "cards", "templates", "tests"]


def test_no_legacy_workflow_path_in_behavior_dirs():
    root = Path(__file__).resolve().parents[2]
    existing = [d for d in BEHAVIOR_DIRS if (root / d).is_dir()]
    out = subprocess.run(
        ["grep", "-rln", "--exclude-dir=__pycache__", LEGACY, *existing],
        cwd=root, capture_output=True, text=True,
    )
    # Self-exclusao por path resolvido completo (nao basename): evita falso-verde
    # se um homonimo existir noutro dir. O split de LEGACY ja previne self-match
    # do conteudo; esta exclusao cobre so este proprio arquivo.
    self_path = Path(__file__).resolve()
    hits = [l for l in out.stdout.splitlines() if l and (root / l).resolve() != self_path]
    assert hits == [], f"Literal legado sobrou em: {hits}"
