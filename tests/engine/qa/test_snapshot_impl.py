"""Testes de `snapshot_impl_files` (Task A1, vetor impl-vs-spec).

Captura o conteúdo dos `allowed_files` declarados nos task contracts do scope
em `snapshot/impl/`, pra o auditor impl-vs-spec confrontar a implementação real
contra os specs. Containment (H-001): um `allowed_files` cujo path resolva FORA
do project_root é REJEITADO — nada escreve fora de `snapshot/impl/`.
"""

from __future__ import annotations

import yaml

from engine.qa.ingest import snapshot_impl_files
from engine.qa.scope import Scope


def _write_task(feature_dir, task_id, allowed):
    tasks = feature_dir / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / f"{task_id}.yaml").write_text(
        yaml.safe_dump({"task_id": task_id, "allowed_files": allowed}),
        encoding="utf-8",
    )
    return tasks / f"{task_id}.yaml"


def test_snapshot_impl_copies_allowed_file_content(tmp_path):
    root = tmp_path
    impl = root / "src" / "main" / "kotlin" / "Foo.kt"
    impl.parent.mkdir(parents=True, exist_ok=True)
    impl.write_text("class Foo // impl real", encoding="utf-8")
    feature_dir = root / "docs" / "forge-specs" / "features" / "demo"
    task_yaml = _write_task(feature_dir, "TASK-0001", ["src/main/kotlin/Foo.kt"])
    snap = root / ".planning" / "qa" / "demo" / "run" / "snapshot"
    snap.mkdir(parents=True, exist_ok=True)
    scope = Scope(type="task", target="TASK-0001", paths=(task_yaml,))

    copied = snapshot_impl_files(scope, snap, project_root=root)

    dest = snap / "impl" / "src" / "main" / "kotlin" / "Foo.kt"
    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == "class Foo // impl real"
    assert dest in copied


def test_snapshot_impl_skips_missing_allowed_file(tmp_path):
    root = tmp_path
    feature_dir = root / "docs" / "forge-specs" / "features" / "demo"
    task_yaml = _write_task(feature_dir, "TASK-0001", ["src/never/written.kt"])
    snap = root / ".planning" / "qa" / "demo" / "run" / "snapshot"
    snap.mkdir(parents=True, exist_ok=True)
    scope = Scope(type="task", target="TASK-0001", paths=(task_yaml,))

    copied = snapshot_impl_files(scope, snap, project_root=root)

    assert copied == []
    assert not (snap / "impl").exists() or not any((snap / "impl").rglob("*"))


def test_snapshot_impl_feature_scope_dedup(tmp_path):
    """scope=feature enumera os TASK-*.yaml do dir, une allowed_files,
    e copia cada arquivo 1x mesmo quando 2 tasks o declaram (dedup por dest)."""
    root = tmp_path
    a = root / "src" / "A.kt"
    b = root / "src" / "B.kt"
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text("A", encoding="utf-8")
    b.write_text("B", encoding="utf-8")
    feature_dir = root / "docs" / "forge-specs" / "features" / "demo"
    _write_task(feature_dir, "TASK-0001", ["src/A.kt", "src/B.kt"])
    _write_task(feature_dir, "TASK-0002", ["src/B.kt"])  # B duplicado
    snap = root / ".planning" / "qa" / "demo" / "run" / "snapshot"
    snap.mkdir(parents=True, exist_ok=True)
    # scope=feature → paths é o diretório da feature
    scope = Scope(type="feature", target="demo", paths=(feature_dir,))

    copied = snapshot_impl_files(scope, snap, project_root=root)

    assert (snap / "impl" / "src" / "A.kt").read_text(encoding="utf-8") == "A"
    assert (snap / "impl" / "src" / "B.kt").read_text(encoding="utf-8") == "B"
    # B aparece em 2 tasks mas só 1 destino (dedup).
    assert len(copied) == 2
    assert len(set(copied)) == 2


def test_snapshot_impl_traversal_real_escape_is_blocked(tmp_path):
    """H-001 NÃO-VACUO: um allowed_files com `../escape.kt` que resolve FORA
    do project_root DEVE ser rejeitado — o arquivo secreto real NÃO entra no
    snapshot e nenhum destino mora fora de snapshot/impl/.

    Setup com escape REAL: project_root = root/project; o secret mora em
    root/secret.kt (irmão do project_root). O allowed_files `../secret.kt`
    resolve pra esse secret real — se o containment falhasse, ele seria
    copiado. O teste asserta que NÃO foi (não itera lista vazia)."""
    root = tmp_path
    project_root = root / "project"
    project_root.mkdir()
    # Arquivo secreto REAL fora do project_root (irmão).
    secret = root / "secret.kt"
    secret.write_text("TOP SECRET — não deve vazar", encoding="utf-8")
    # Sanity: o secret existe e é um arquivo real (escape não-vacuo).
    assert secret.is_file()

    feature_dir = project_root / "docs" / "forge-specs" / "features" / "demo"
    task_yaml = _write_task(feature_dir, "TASK-0001", ["../secret.kt"])
    snap = project_root / ".planning" / "qa" / "demo" / "run" / "snapshot"
    snap.mkdir(parents=True, exist_ok=True)
    scope = Scope(type="task", target="TASK-0001", paths=(task_yaml,))

    copied = snapshot_impl_files(scope, snap, project_root=project_root)

    # O escape foi BLOQUEADO: o secret não entrou no snapshot.
    assert copied == []
    impl_dir = snap / "impl"
    # O conteúdo do secret não aparece em lugar nenhum sob snapshot/impl/.
    if impl_dir.exists():
        for f in impl_dir.rglob("*"):
            if f.is_file():
                assert "TOP SECRET" not in f.read_text(encoding="utf-8")
    # E o secret real não foi tocado fora do snapshot tampouco.
    assert secret.read_text(encoding="utf-8") == "TOP SECRET — não deve vazar"
    # Nenhum destino mora fora de snapshot/impl/.
    impl_resolved = impl_dir.resolve()
    for dest in copied:
        assert impl_resolved in dest.resolve().parents


def test_snapshot_impl_absolute_path_outside_root_is_blocked(tmp_path):
    """MED-002 (a) — H-001 ADVERSARIAL: um allowed_files com path ABSOLUTO
    fora do project_root DEVE ser rejeitado. `project_root / "/abs"` resolve
    pro path absoluto (pathlib: operando absoluto à direita substitui), então
    `_is_contained` o rejeita via relative_to. O secret real NÃO vaza."""
    root = tmp_path
    project_root = root / "project"
    project_root.mkdir()
    # Secret REAL com path absoluto fora do project_root.
    secret = root / "abs_secret.kt"
    secret.write_text("ABS SECRET — não deve vazar", encoding="utf-8")
    assert secret.is_file()

    feature_dir = project_root / "docs" / "forge-specs" / "features" / "demo"
    # allowed_files com path ABSOLUTO (string absoluta) fora do projeto.
    task_yaml = _write_task(feature_dir, "TASK-0001", [str(secret)])
    snap = project_root / ".planning" / "qa" / "demo" / "run" / "snapshot"
    snap.mkdir(parents=True, exist_ok=True)
    scope = Scope(type="task", target="TASK-0001", paths=(task_yaml,))

    copied = snapshot_impl_files(scope, snap, project_root=project_root)

    # Absoluto fora do root foi BLOQUEADO.
    assert copied == []
    impl_dir = snap / "impl"
    if impl_dir.exists():
        for f in impl_dir.rglob("*"):
            if f.is_file():
                assert "ABS SECRET" not in f.read_text(encoding="utf-8")
    assert secret.read_text(encoding="utf-8") == "ABS SECRET — não deve vazar"


def test_snapshot_impl_symlink_escaping_root_is_blocked(tmp_path):
    """MED-002 (b) — H-001 ADVERSARIAL: um allowed_files apontando pra um
    SYMLINK que mora DENTRO do projeto mas RESOLVE pra um target FORA do
    project_root DEVE ser rejeitado. `candidate.resolve()` segue o symlink
    até o target externo, então relative_to falha e o conteúdo não vaza."""
    root = tmp_path
    project_root = root / "project"
    project_root.mkdir()
    # Secret REAL fora do project_root.
    secret = root / "sym_secret.kt"
    secret.write_text("SYMLINK SECRET — não deve vazar", encoding="utf-8")
    assert secret.is_file()

    # Symlink DENTRO do projeto apontando pro secret externo.
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    link = src_dir / "leak.kt"
    link.symlink_to(secret)
    # Sanity: o symlink mora dentro do projeto mas resolve pra fora.
    assert link.is_symlink()
    assert link.resolve() == secret.resolve()

    feature_dir = project_root / "docs" / "forge-specs" / "features" / "demo"
    task_yaml = _write_task(feature_dir, "TASK-0001", ["src/leak.kt"])
    snap = project_root / ".planning" / "qa" / "demo" / "run" / "snapshot"
    snap.mkdir(parents=True, exist_ok=True)
    scope = Scope(type="task", target="TASK-0001", paths=(task_yaml,))

    copied = snapshot_impl_files(scope, snap, project_root=project_root)

    # O symlink que escapa foi BLOQUEADO: o secret não entrou no snapshot.
    assert copied == []
    impl_dir = snap / "impl"
    if impl_dir.exists():
        for f in impl_dir.rglob("*"):
            if f.is_file():
                assert "SYMLINK SECRET" not in f.read_text(encoding="utf-8")
    assert secret.read_text(encoding="utf-8") == "SYMLINK SECRET — não deve vazar"
