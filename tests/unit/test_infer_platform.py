"""Table-driven coverage for `infer_platform` (GRAPH-REAL-REPO Stage 1)."""

from __future__ import annotations

import pytest

from engine.graph.gradle_modules import infer_platform


@pytest.mark.parametrize(
    "module, source_set, rel_path, language, expected",
    [
        # 1. KMP source-set explicit -> mapped platform.
        ("shared", "commonMain", "shared/src/commonMain/kotlin/A.kt", "kotlin", "common"),
        ("shared", "commonTest", "shared/src/commonTest/kotlin/A.kt", "kotlin", "common"),
        ("shared", "androidMain", "shared/src/androidMain/kotlin/A.kt", "kotlin", "android"),
        ("shared", "androidUnitTest", "shared/src/androidUnitTest/kotlin/A.kt", "kotlin", "android"),
        ("shared", "androidTest", "shared/src/androidTest/kotlin/A.kt", "kotlin", "android"),
        ("shared", "iosMain", "shared/src/iosMain/kotlin/A.kt", "kotlin", "ios"),
        ("shared", "iosArm64Main", "shared/src/iosArm64Main/kotlin/A.kt", "kotlin", "ios"),
        ("shared", "iosSimulatorArm64Main", "shared/src/iosSimulatorArm64Main/kotlin/A.kt", "kotlin", "ios"),
        ("shared", "iosX64Main", "shared/src/iosX64Main/kotlin/A.kt", "kotlin", "ios"),
        ("shared", "appleMain", "shared/src/appleMain/kotlin/A.kt", "kotlin", "ios"),
        ("shared", "jvmMain", "shared/src/jvmMain/kotlin/A.kt", "kotlin", "jvm"),
        # KMP source-set present but not in {android,ios,common,jvm} -> None.
        ("shared", "jsMain", "shared/src/jsMain/kotlin/A.kt", "kotlin", None),
        ("shared", "wasmJsMain", "shared/src/wasmJsMain/kotlin/A.kt", "kotlin", None),
        ("shared", "nativeMain", "shared/src/nativeMain/kotlin/A.kt", "kotlin", None),
        # 2. No KMP source-set -> language/path inference.
        ("app", None, "app/src/main/kotlin/com/x/Foo.kt", "kotlin", "android"),
        ("app", None, "app/src/debug/kotlin/com/x/Foo.kt", "kotlin", "android"),
        ("app", None, "app/src/main/res/layout/foo.xml", "xml", "android"),
        ("core", None, "core/src/main/java/com/x/Legacy.java", "java", "android"),
        ("androidApp", None, "androidApp/src/main/kotlin/com/x/Foo.kt", "kotlin", "android"),
        ("iosApp", None, "iosApp/Sources/HomeView.swift", "swift", "ios"),
        ("iosApp", None, "iosApp/Legacy.m", "objc", "ios"),
        # Java is always android even without a src/ dir.
        ("root", None, "tools/Gen.java", "java", "android"),
        # 3. No signal -> None.
        ("root", None, "scripts/build.gradle.kts", "kotlin", None),
        ("root", None, "docs/readme.ts", "typescript", None),
    ],
)
def test_infer_platform_table(module, source_set, rel_path, language, expected):
    assert infer_platform(module, source_set, rel_path, language) == expected
