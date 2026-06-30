"""BUG-IMPL-2 (T5): build commands nos cards são project-derived (pelo agente),
não literais hardcoded.

H-002 (redirecionado): o engine NÃO expõe módulos/tasks gradle —
``validations_suggested``/``swiftui_validations`` são consumidos pelo AGENTE,
não por Python. Então o fix mora nos TEMPLATES DE CARD / agent-contributions:
os comandos hardcoded errados/cegos viram project-derived-PELO-AGENTE (o
template instrui derivar do projeto via ``gradlew tasks``/inventory) em vez de
assumir um módulo/script específico.

Default (A) da spec: parametrizar + inventory-derived, SEM invocar gradle em
tempo de plan/implement (sem custo de runtime/rede).
"""

from __future__ import annotations

from pathlib import Path

import yaml

_CARDS = Path(__file__).resolve().parents[2] / "cards"
_SWIFTUI = _CARDS / "swiftui-screens" / "templates" / "swiftui-allowed-files.yaml"
_COMPOSE = _CARDS / "compose-screens" / "templates" / "compose-allowed-files.yaml"
_KOTLIN_PROSE = (
    _CARDS / "kotlin-language" / "agent-contributions" / "task-writer-additions.md"
)


def test_ios_build_command_not_blind_literal() -> None:
    """O build iOS não pode ser o literal cego ``run-ios-simulator.sh --build-only``.

    Esse script pode não existir no projeto; o agente deve derivar o build
    command do projeto (xcodebuild scheme do inventory / script real).
    """
    data = yaml.safe_load(_SWIFTUI.read_text(encoding="utf-8"))
    validations = data.get("swiftui_validations") or []
    ios_build = next((v for v in validations if v.get("name") == "ios-build"), None)
    assert ios_build is not None, "validação ios-build sumiu do card"
    cmd = ios_build.get("command", "")
    assert "run-ios-simulator.sh --build-only" not in cmd, (
        "ios-build ainda usa o literal cego run-ios-simulator.sh --build-only "
        "(BUG-IMPL-2) — deve ser project-derived"
    )
    # Deve sinalizar derivação (placeholder/inventory) em vez de assumir.
    blob = (cmd + " " + str(ios_build.get("derive_from", ""))).lower()
    assert "{" in cmd or "deriv" in blob or "inventory" in blob, (
        "ios-build não indica derivação do projeto"
    )


def test_compose_build_command_module_is_parameterized() -> None:
    """O assembleDebug não pode assumir o módulo fixo ``:composeApp``.

    O nome do módulo Gradle varia por projeto; deve ser parametrizado
    (placeholder derivado do inventory pelo agente).
    """
    data = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    suggested = (data.get("compose_file_patterns") or {}).get("validations_suggested") or []
    commands = [v.get("command", "") for v in suggested]
    assemble = [c for c in commands if "assembleDebug" in c]
    assert assemble, "comando assembleDebug sumiu do card compose"
    for c in assemble:
        assert ":composeApp:" not in c, (
            f"comando ainda assume o módulo fixo :composeApp: ({c!r}) — "
            "deve ser parametrizado (placeholder do inventory)"
        )


def test_kmp_shared_uses_android_host_test_not_debug_unit() -> None:
    """A prose KMP usa testAndroidHostTest, nunca testDebugUnitTest."""
    text = _KOTLIN_PROSE.read_text(encoding="utf-8")
    assert "testAndroidHostTest" in text
    assert "testDebugUnitTest" not in text, (
        "prose KMP ainda menciona testDebugUnitTest (errado pra KMP shared)"
    )
