"""Teste estático de determinismo: validators nunca importam engine.integrations.mem.

W-ROUTE 6c — invariante de determinismo (D1): validators/ são unidades read-only
determinísticas. Memória contextual (mem find) alimenta APENAS os handlers
(plan/implement/verify/qa) como hint educacional, jamais como input de decisão
num validator — isso contaminaria a natureza determinística do cascade.

Este teste é estático: varre o source text dos validators em validators/ e asserta
que nenhum módulo importa ou chama funções do substrato mem.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

# Raiz do repo: dois níveis acima de tests/unit/.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATORS_DIR = _REPO_ROOT / "validators"

# Padrões proibidos: módulo do substrato mem + nomes de funções/tipos do mem.
# IN-02: escopo é "validator não toca mem" — bloqueamos só engine.integrations.mem,
# NÃO toda a package engine.integrations (validators podem usar outros submódulos).
_FORBIDDEN_IMPORTS = {"engine.integrations.mem"}
_FORBIDDEN_NAMES = {
    "mem_find",
    "mem_context_hint",
    "mem_call",
    "mem_get",
    "mem_stats",
    "mem_brief",
    "mem_evolve",
    "mem_inbox_add",
    "MemQuery",
    "MemResult",
}


def _collect_validator_sources() -> list[Path]:
    """Retorna todos os .py de validators/ exceto __init__ e _common/_diff/_gate_infra."""
    return sorted(
        p for p in _VALIDATORS_DIR.glob("*.py")
        if p.name not in {"__init__.py"}
    )


def _check_source(path: Path) -> list[str]:
    """Retorna lista de violações encontradas no arquivo (vazia se ok)."""
    violations: list[str] = []
    source = path.read_text(encoding="utf-8")

    # Parse AST pra detecção estrutural (import statements).
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        violations.append(f"SyntaxError ao parsear: {exc}")
        return violations

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                # Caso 1 — from engine.integrations.mem import ...
                if any(
                    node.module == forbidden or node.module.startswith(f"{forbidden}.")
                    for forbidden in _FORBIDDEN_IMPORTS
                ):
                    violations.append(
                        f"L{node.lineno}: import proibido 'from {node.module} import ...'"
                    )
                # Caso 2 — from engine.integrations import mem (submódulo por nome).
                # IN-02: como a deny-list de módulos foi estreitada pra só
                # `engine.integrations.mem`, esta forma escaparia o caso 1 — então
                # checamos o nome do submódulo importado explicitamente.
                if node.module == "engine.integrations":
                    for alias in node.names:
                        if alias.name == "mem":
                            violations.append(
                                f"L{node.lineno}: import proibido "
                                f"'from engine.integrations import mem'"
                            )
                # Caso 3 — nomes de funções/tipos do mem importados diretamente.
                for alias in node.names:
                    if alias.name in _FORBIDDEN_NAMES:
                        violations.append(
                            f"L{node.lineno}: import de função mem proibida: '{alias.name}'"
                        )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(
                        alias.name == forbidden or alias.name.startswith(f"{forbidden}.")
                        for forbidden in _FORBIDDEN_IMPORTS
                    ):
                        violations.append(
                            f"L{node.lineno}: import proibido 'import {alias.name}'"
                        )

        # Detecção de chamadas diretas por nome (ex: mem_find(...) com import * hipotético).
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_NAMES:
                violations.append(
                    f"L{node.lineno}: chamada direta a função mem proibida: '{func.id}()'"
                )
            if isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_NAMES:
                violations.append(
                    f"L{node.lineno}: chamada a atributo mem proibido: '.{func.attr}()'"
                )

    return violations


@pytest.mark.parametrize(
    "validator_path",
    _collect_validator_sources(),
    ids=lambda p: p.name,
)
def test_validator_does_not_import_mem(validator_path: Path) -> None:
    """Nenhum validator deve importar ou chamar funções de engine.integrations.mem.

    Falha com a lista de violações encontradas pra facilitar o diagnóstico.
    """
    violations = _check_source(validator_path)
    assert not violations, (
        f"Validator '{validator_path.name}' viola o invariante de determinismo (W-ROUTE 6c):\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nValidators são determinísticos e não recebem contexto de mem. "
        "Moves de lógica de mem pra validators quebram a arquitetura — "
        "use os handlers (plan/implement/verify/qa) como ponto de injeção."
    )
