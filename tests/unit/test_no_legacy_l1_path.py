# tests/unit/test_no_legacy_l1_path.py
import subprocess
from pathlib import Path

# DETECÇÃO SIMÉTRICA: o path L1 legado aparece em DUAS formas no código —
#   (1) string literal: ".claude/memory/L1/..." (docstrings, mensagens)
#   (2) segmento quotado "L1": construção Path (memory_dir / "L1") E tupla de
#       literais (".claude","memory","L1",...) — ambas contêm o token "L1".
# Grepar o segmento "L1" quotado pega AS DUAS variantes da Forma 2 (construção
# E tupla); o único "L1" quotado legítimo que NÃO é path é o config
# `"layers-enabled": ["L1","L2","L3"]` (init.py) — allowlisted explicitamente.
# Padrões montados por partes pra o próprio gate não auto-casar.
STRING_LITERAL = "memory" + "/L1"          # Forma 1
QUOTED_SEGMENT = '"' + "L1" + '"'          # Forma 2 (construção + tupla)
ALLOWLIST_TOKENS = ("layers-enabled", "layers_enabled")  # "L1" como nome de camada, não path
BEHAVIOR_DIRS = ["engine", "validators", "hooks", "tests"]

def _grep(pattern, dirs, root):
    out = subprocess.run(
        ["grep", "-rn", "--exclude-dir=__pycache__", pattern, *dirs],
        cwd=root, capture_output=True, text=True,
    )
    return out.stdout.splitlines()

def _not_self(line, root, self_path):
    # grep -rn → "relpath:lineno:conteúdo"; exclui só este próprio arquivo por path resolvido.
    rel = line.split(":", 1)[0]
    return (root / rel).resolve() != self_path

def test_no_legacy_l1_path_in_behavior_code():
    root = Path(__file__).resolve().parents[2]
    self_path = Path(__file__).resolve()
    dirs = [d for d in BEHAVIOR_DIRS if (root / d).is_dir()]
    str_hits = [l for l in _grep(STRING_LITERAL, dirs, root) if _not_self(l, root, self_path)]
    quoted_hits = [
        l for l in _grep(QUOTED_SEGMENT, dirs, root)
        if _not_self(l, root, self_path)
        and not any(tok in l for tok in ALLOWLIST_TOKENS)
    ]
    hits = sorted(set(str_hits + quoted_hits))
    assert hits == [], f"Path L1 legado sobrou: {hits}"
