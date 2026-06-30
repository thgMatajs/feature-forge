"""Pure detection signal evaluation — shared by init.py and
detection/composer.py to break the import cycle (DET-6 Phase B,
PR #13 review #3405252850 + #3405253600 + #3405256623).

Antes desta extração, ``engine.detection.composer`` importava
``_eval_detection_signals`` de ``engine.init``, e ``engine.init`` por
sua vez importava ``compose_backend_axes`` de ``engine.detection.
composer`` — ciclo só fechado via lazy import dentro de funções
(``# noqa: PLC0415``). O ciclo travava qualquer reorganização futura
da camada de detection e mascarava o import order pros testes.

Este módulo concentra:

  - ``_eval_detection_signals`` — função canônica de scoring per-card
    sobre os 4 signal types (file-exists, file-content, gradle-dep,
    directory-exists). Schema fonte: ``docs/schemas/card.md``
    §"detection.signals".
  - Helpers privados que ``_eval_detection_signals`` consome:
    ``_glob_any``, ``_eval_gradle_dep``, ``_load_toml_catalog``,
    ``_module_matches_coordinate``, ``_scan_build_gradle_for_coordinate``.
  - Constante ``_SKIP_DIRS`` — set canônico de dirs ignorados em walks
    do detection layer (node_modules, build, .gradle, etc.).

``engine.init`` re-importa ``_SKIP_DIRS`` daqui pra alimentar
``_count_needle_hits`` (orphan signal scan). ``_eval_detection_signals``
**não** é re-exportada — callers de fora devem importar diretamente
deste módulo (contrato pós-Phase B).

Voz mentor calmo: docstrings preservadas do site original sem
alteração de semântica — esta é movimentação pura (no-behavior-change).
"""

from __future__ import annotations

import functools
import tomllib
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from engine.cards._signal_shapes import parse_gradle_coordinate

# Set canônico de directories que o detection layer pula em walks.
# Cobre artifacts de build (node_modules, build, .gradle, dist, .next),
# IDE caches (.idea, DerivedData), Cocoapods (Pods), virtualenvs (.venv,
# venv), git internals (.git), python bytecode (__pycache__) e o próprio
# .claude/ (worktrees, state, cards snapshot — não fazem parte do
# project surface que detection inspeciona).
_SKIP_DIRS = {
    "node_modules",
    "build",
    ".git",
    ".gradle",
    ".idea",
    "DerivedData",
    "Pods",
    "dist",
    ".next",
    ".cache",
    ".venv",
    "venv",
    ".claude",
    "__pycache__",
}


def _walk_recursive_pruned(
    project_root: Path,
    pattern: str,
    skip_dirs: Iterable[str],
) -> Iterator[Path]:
    """Yield descendants matching ``pattern`` (rglob-style), podando ``skip_dirs``.

    Substitui ``project_root.rglob(pattern)`` por um walk manual que NÃO desce
    em diretórios cujo nome está em ``skip_dirs`` — mesma técnica de
    poda-na-descida de ``_scan_build_gradle_for_coordinate``. Sem isso, em
    monorepo real (node_modules 492M + .gradle 484M) o ``rglob`` materializa
    centenas de milhares de paths antes do filtro agir, travando o init.

    **Contrato no-behavior-change (conjunto):** o conjunto yielded é IDÊNTICO
    ao de ``rglob(pattern)`` filtrado por ``skip_dirs``, porque podar um
    skip-dir na descida remove exatamente os mesmos paths que o filtro
    removeria depois (qualquer componente relativo em ``skip_dirs`` ⇒ path
    ignorado). Yield inclui diretórios E arquivos, igual ao rglob.

    **Contrato de ORDEM (H-001):** a saída é ORDENADA (sorted), tornando o
    walk DETERMINÍSTICO. O ``rglob`` nativo yield em ordem de ``os.scandir``
    (inode-order, dependente de filesystem) — sites que fazem ``break`` no
    primeiro match (ex.: ``design_system._extract_tokens`` com 2 ``Spacing.kt``)
    tinham vencedor não-determinístico. Ordenar fixa o vencedor sem alterar o
    conjunto.

    ``pattern == ""`` (vinda do glob literal ``"**/"``) replica EXATAMENTE o
    comportamento de ``rglob("")`` / ``glob("**/")``: yield SÓ de diretórios
    (incluindo o próprio ``project_root``), NÃO de arquivos. ``Path.match("")``
    levantaria ValueError, então tratamos esse caso à parte. (O branch
    `fix/pilot-init-perf` documentava "yield de TODOS os descendants", mas a
    semântica real de ``rglob("")`` é só-diretórios — corrigido aqui.)

    Symlinks de diretório não são seguidos (evita ciclos).

    ``skip_dirs`` é PARÂMETRO (não o ``_SKIP_DIRS`` global): cada site passa o
    seu set atual, preservando o no-behavior-change por-site (há 4 sets
    divergentes no codebase — não unificados nesta onda, por design).
    """
    skip = set(skip_dirs)
    dirs_only = pattern == ""
    collected: list[Path] = []
    # `rglob("")` inclui o próprio root (um diretório). Replicamos isso.
    if dirs_only and project_root.is_dir():
        collected.append(project_root)
    stack: list[Path] = [project_root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            is_dir = entry.is_dir()
            if is_dir and not entry.is_symlink():
                # Poda na descida: não recursa em skip-dirs. Match contra o
                # NOME do dir — equivale ao filtro "qualquer part relativa em
                # skip_dirs".
                if entry.name in skip:
                    continue
                stack.append(entry)
            if dirs_only:
                # Paridade com rglob("")/glob("**/"): só diretórios.
                if is_dir:
                    collected.append(entry)
            elif entry.match(pattern):
                collected.append(entry)
    collected.sort()
    yield from collected


def _walk_recursive_pruned_lazy(
    project_root: Path,
    pattern: str,
    skip_dirs: Iterable[str],
) -> Iterator[Path]:
    """Variante LAZY de ``_walk_recursive_pruned`` — yield SEM ordenar/materializar.

    Mesma poda-na-descida e mesma semântica de ``pattern == ""`` (só-diretórios)
    do ``_walk_recursive_pruned``, mas yield em ordem de ``os.scandir``
    (inode-order) à medida que desce, SEM coletar a árvore inteira nem ``sort()``.
    Existe para o caminho de EXISTÊNCIA (``_glob_any``), que só precisa do 1º
    match e portanto pode (e deve) curto-circuitar sem pagar materialização +
    ordenação + cap.

    NÃO use esta variante onde a ORDEM importa (sites com ``break`` no 1º match
    que precisam de vencedor determinístico — H-001): esses continuam usando
    ``_walk_recursive_pruned`` (ordenado). Aqui a ordem é irrelevante porque o
    consumidor só pergunta "existe ALGUM match?".
    """
    skip = set(skip_dirs)
    dirs_only = pattern == ""
    # `rglob("")` inclui o próprio root (um diretório). Replicamos isso.
    if dirs_only and project_root.is_dir():
        yield project_root
    stack: list[Path] = [project_root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            is_dir = entry.is_dir()
            if is_dir and not entry.is_symlink():
                if entry.name in skip:
                    continue
                stack.append(entry)
            if dirs_only:
                if is_dir:
                    yield entry
            elif entry.match(pattern):
                yield entry


def _glob_any(project_root: Path, glob: str, needle: str | None) -> bool:
    """Best-effort glob walk para check de EXISTÊNCIA — curto-circuita no 1º match.

    Para padrões ``**/X`` usa ``_walk_recursive_pruned_lazy`` — walk manual que
    poda ``_SKIP_DIRS`` NA DESCIDA (evita materializar node_modules / .gradle
    inteiros) e yield LAZY, permitindo retornar ``True`` assim que o primeiro
    match é encontrado.

    **Independente de ordem e de cap (WR-02):** por ser um check de existência
    ("existe ALGUM match?"), o resultado é o 1º match achado. NÃO ordenamos nem
    capamos a árvore: o ``_walk_recursive_pruned`` ordenado + cap de 800
    introduzia um viés lexicográfico que podia ESCONDER um match cujo nome
    ordenava depois da posição 800 (divergindo do rglob lazy legado, que
    curto-circuitava em inode-order). O short-circuit elimina esse viés — com
    1 ou 1M de paths, basta UM match para retornar ``True``. O cap antigo
    mitigava materialização de node_modules, hoje podada na descida.
    """
    if not glob:
        return False
    if glob.startswith("**/"):
        pattern = glob[3:]
        iterator: Iterator[Path] = _walk_recursive_pruned_lazy(
            project_root, pattern, _SKIP_DIRS
        )
    else:
        iterator = project_root.glob(glob)
    for path in iterator:
        # Match _SKIP_DIRS contra parts RELATIVO a project_root — não path.parts
        # absoluto. Sem isso, paths sob .claude/worktrees/<branch>/ ficam
        # invisíveis (parent .claude/ é skip-dir legítimo só no top-level).
        try:
            relative_parts = path.relative_to(project_root).parts
        except ValueError:
            continue
        if any(part in _SKIP_DIRS for part in relative_parts):
            continue
        if not path.is_file():
            continue
        if needle is None:
            return True
        # Stream linha-a-linha — evita carregar arquivos grandes inteiros em
        # memória só para procurar uma substring.
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if needle in line:
                        return True
        except OSError:
            continue
    return False


@functools.lru_cache(maxsize=8)
def _load_toml_catalog(project_root: Path) -> tuple[dict, ...]:
    """Carrega e parseia `gradle/*.versions.toml` uma vez por project_root.

    Cache module-level pequeno (maxsize=8) — cada `forge init` típico
    inspeciona um único project_root, então 8 cobre runs em fila +
    fixtures de teste sem reter memória. Cache invalida implicitamente
    entre sessões CLI (cada run é processo novo).

    Retorna tuple de dicts (top-level TOML root) — tuple porque o cache
    decorator exige imutabilidade do retorno. TOML mal-formado / OSError
    são ignorados silenciosamente, alinhado a `_glob_any`.
    """
    gradle_dir = project_root / "gradle"
    if not gradle_dir.is_dir():
        return ()
    catalogs: list[dict] = []
    for toml_path in gradle_dir.glob("*.versions.toml"):
        try:
            with toml_path.open("rb") as fh:
                catalogs.append(tomllib.load(fh))
        except (OSError, tomllib.TOMLDecodeError):
            continue
    return tuple(catalogs)


def _module_matches_coordinate(module: str, coordinate: str) -> bool:
    """`entry["module"]` casa `coordinate` ignorando version sufixada.

    TOML canônico declara `module = "group:artifact"`, mas no wild
    aparece `module = "group:artifact:version"` (B-2). Compara apenas
    os 2 primeiros segments split por `:`; preserva comportamento
    canônico `module == coordinate` para a forma de 2 segments.

    Usa `parse_gradle_coordinate` no lado `coordinate` (shape canônica
    `<group>:<artifact>` validado pelo loader CARD-020). Quando o
    helper retorna `None`, cai pra fallback string-exato — não introduz
    comportamento novo, só dedupe (B-3 from PR #11 review).
    """
    if module == coordinate:
        return True
    coord_parsed = parse_gradle_coordinate(coordinate)
    if coord_parsed is None:
        return False
    mod_parts = module.split(":")
    if len(mod_parts) < 2:
        return False
    coord_group, coord_artifact = coord_parsed
    return mod_parts[0] == coord_group and mod_parts[1] == coord_artifact


def _scan_build_gradle_for_coordinate(project_root: Path, coordinate: str) -> bool:
    """Substring search em `**/build.gradle*` ignorando comentários.

    Filtra linhas de comentário Groovy/KTS (`//` line-comment e blocos
    `/* ... */`) antes de testar substring — evita falso positivo de
    coordenadas mencionadas em comentários do tipo `// io.ktor:foo
    retirado 2024` (M-5). Mantém o cap de arquivos visitados de
    `_glob_any` (800) e o skip-dirs canônico. Walk manual em vez de
    rglob() para evitar descer em node_modules/.gradle/build.
    """
    stack: list[Path] = [project_root]
    count = 0
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir() and not entry.is_symlink():
                if entry.name in _SKIP_DIRS or entry.name.startswith("."):
                    continue
                stack.append(entry)
            elif entry.is_file() and entry.name.startswith("build.gradle"):
                if count > 800:
                    return False
                count += 1
                try:
                    with entry.open("r", encoding="utf-8", errors="ignore") as fh:
                        in_block_comment = False
                        for line in fh:
                            stripped = line.lstrip()
                            code_segments: list[str] = []
                            i = 0
                            src = line
                            while i < len(src):
                                if in_block_comment:
                                    close = src.find("*/", i)
                                    if close == -1:
                                        break
                                    i = close + 2
                                    in_block_comment = False
                                    continue
                                if src.startswith("//", i):
                                    break
                                if src.startswith("/*", i):
                                    in_block_comment = True
                                    i += 2
                                    continue
                                j = i
                                while j < len(src):
                                    if src.startswith("//", j) or src.startswith("/*", j):
                                        break
                                    j += 1
                                code_segments.append(src[i:j])
                                i = j
                            if stripped.startswith("//"):
                                continue
                            code_line = "".join(code_segments)
                            if coordinate in code_line:
                                return True
                except OSError:
                    continue
    return False


def _eval_gradle_dep(project_root: Path, coordinate: str | None) -> bool:
    """True se a coordenada Maven existe em qualquer formato Gradle.

    Ordem: 1) catálogo gradle/*.versions.toml, 2) build.gradle(.kts) legado.
    Curto-circuita no primeiro match. Defensivo contra TOML mal-formado
    (try/except silencioso, alinhado a `_glob_any`).

    Format aceito do `coordinate`: `<groupId>:<artifactId>` sem version,
    sem espaços. Shape validation acontece em `engine/cards/loader.py`
    (regra CARD-020); aqui usamos o helper compartilhado
    `parse_gradle_coordinate` e retornamos `False` silenciosamente em
    qualquer shape inválida (B-3 from PR #11 review).
    """
    parsed = parse_gradle_coordinate(coordinate)
    if parsed is None:
        return False
    group, artifact = parsed

    # 1) Catálogo TOML (path canônico gradle/*.versions.toml) — cached por
    # project_root (B-1) e match prefix-tolerant em `module` (B-2).
    for data in _load_toml_catalog(project_root):
        libraries = data.get("libraries") or {}
        if not isinstance(libraries, dict):
            continue
        for entry in libraries.values():
            if not isinstance(entry, dict):
                continue
            module = entry.get("module")
            if isinstance(module, str) and _module_matches_coordinate(module, coordinate):
                return True
            grp = entry.get("group")
            nm = entry.get("name")
            if (
                isinstance(grp, str)
                and isinstance(nm, str)
                and grp == group
                and nm == artifact
            ):
                return True

    # 2) build.gradle(.kts) legado — substring com filtro de comentários (M-5).
    if _scan_build_gradle_for_coordinate(project_root, coordinate):
        return True

    return False


def _eval_detection_signals(
    project_root: Path, detection: dict[str, Any]
) -> tuple[float, list[str]]:
    """Evaluate detection signals against the project. Returns (score, matched).

    Supports `file-exists`, `file-content`, `directory-exists` signal types
    (same schema used by cards and presets — see docs/schemas/card.md
    §detection.signals).
    """
    signals = (detection or {}).get("signals") or []
    score = 0.0
    matched: list[str] = []
    for sig in signals:
        if not isinstance(sig, dict):
            continue
        kind = sig.get("type")
        conf = float(sig.get("confidence") or 0.0)
        ok = False
        if kind == "directory-exists":
            path = sig.get("path")
            if isinstance(path, str) and (project_root / path).is_dir():
                ok = True
        elif kind == "file-exists":
            ok = _glob_any(project_root, str(sig.get("glob") or ""), None)
        elif kind == "gradle-dep":
            coordinate = sig.get("coordinate")
            if isinstance(coordinate, str) and coordinate:
                ok = _eval_gradle_dep(project_root, coordinate)
        elif kind == "file-content":
            ok = _glob_any(
                project_root,
                str(sig.get("glob") or ""),
                str(sig.get("contains") or ""),
            )
        if ok:
            score += conf
            label = (
                sig.get("coordinate")
                or sig.get("contains")
                or sig.get("path")
                or sig.get("glob")
                or kind
            )
            matched.append(f"{kind}: {label}")
    return round(score, 3), matched
