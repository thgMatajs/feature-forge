"""Screenshot metadata extraction — magic bytes only, no Pillow.

Vision interpretation is delegated to Claude's multimodal layer. This
module's job is to validate paths, extract dimensions, infer platform
from aspect ratio, and fingerprint files for manifest traceability.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_SOI = b"\xff\xd8\xff"
_WEBP_RIFF = b"RIFF"
_WEBP_FORMAT = b"WEBP"

_JPEG_SOF_MARKERS = {
    0xC0, 0xC1, 0xC2, 0xC3,
    0xC5, 0xC6, 0xC7,
    0xC9, 0xCA, 0xCB,
    0xCD, 0xCE, 0xCF,
}

_MIN_DIMENSION = 100
_FINGERPRINT_CHUNK = 64 * 1024


@dataclass
class PlatformInference:
    """F3: inferência rica de plataforma com confidence + nota explicativa.

    `platform` é um dos: 'mobile', 'web', 'tablet', 'unknown'.
    Note que NÃO discriminamos android vs ios — ambos compartilham aspect
    ratios mobile portrait (e.g. iPhone 15 ≈ Pixel 7 ≈ 2.17), então 'mobile'
    é o melhor commit honesto sem screenshot chrome.
    """

    platform: str
    confidence: float
    note: str = ""


@dataclass
class ScreenshotMetadata:
    path: Path
    width: int
    height: int
    file_size_bytes: int
    format: str
    has_alpha: bool
    inferred_platform: str | None
    platform_inference: PlatformInference | None = None


def _detect_format(head: bytes) -> str | None:
    if head.startswith(_PNG_MAGIC):
        return "png"
    if head.startswith(_JPEG_SOI):
        return "jpg"
    if len(head) >= 12 and head[:4] == _WEBP_RIFF and head[8:12] == _WEBP_FORMAT:
        return "webp"
    return None


def _parse_png_from_bytes(data: bytes, path: Path) -> tuple[int, int, bool]:
    """PNG: IHDR begins at byte 8. Parse direto sobre bytes lidos uma única vez."""
    if len(data) < 26 or data[12:16] != b"IHDR":
        raise ValueError(f"{path}: malformed PNG (no IHDR chunk)")
    width = struct.unpack(">I", data[16:20])[0]
    height = struct.unpack(">I", data[20:24])[0]
    color_type = data[25]
    has_alpha = color_type in (4, 6)
    return width, height, has_alpha


def _parse_jpeg_from_bytes(data: bytes, path: Path) -> tuple[int, int, bool]:
    """JPEG: scan markers a partir do byte 2 procurando SOFn.

    Implementação varre `data` com índice ao invés de file pointer — equivale
    a passar por um BytesIO mas sem alocar wrapper.
    """
    if len(data) < 2 or data[0:2] != b"\xff\xd8":
        raise ValueError(f"{path}: not a JPEG (missing SOI)")
    i = 2
    n = len(data)
    while i < n:
        if data[i] != 0xFF:
            i += 1
            continue
        # Pular bytes 0xFF de stuffing.
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            raise ValueError(f"{path}: truncated JPEG")
        marker = data[i]
        i += 1
        if marker == 0x00:
            continue
        if marker in _JPEG_SOF_MARKERS:
            if i + 7 > n:
                raise ValueError(f"{path}: truncated SOF segment")
            segment = data[i : i + 7]
            height = struct.unpack(">H", segment[3:5])[0]
            width = struct.unpack(">H", segment[5:7])[0]
            return width, height, False
        if i + 2 > n:
            raise ValueError(f"{path}: truncated JPEG segment length")
        length = struct.unpack(">H", data[i : i + 2])[0]
        i += length
    raise ValueError(f"{path}: malformed JPEG (no SOF marker)")


def _parse_webp_from_bytes(data: bytes, path: Path) -> tuple[int, int, bool]:
    """WebP — best effort across VP8/VP8L/VP8X sub-formats."""
    if len(data) < 30:
        raise ValueError(f"{path}: WebP too small to parse")
    fourcc = data[12:16]
    if fourcc == b"VP8 ":
        width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return width, height, False
    if fourcc == b"VP8L":
        b0, b1, b2, b3 = data[21], data[22], data[23], data[24]
        width = ((b1 & 0x3F) << 8 | b0) + 1
        height = ((b3 & 0x0F) << 10 | b2 << 2 | (b1 & 0xC0) >> 6) + 1
        has_alpha = bool(b3 & 0x10)
        return width, height, has_alpha
    if fourcc == b"VP8X":
        width = (data[24] | data[25] << 8 | data[26] << 16) + 1
        height = (data[27] | data[28] << 8 | data[29] << 16) + 1
        has_alpha = bool(data[20] & 0x10)
        return width, height, has_alpha
    raise ValueError(f"{path}: unsupported WebP variant {fourcc!r}")


def load_screenshot(path: Path) -> ScreenshotMetadata:
    """Read dimensions/format from a screenshot file using magic bytes only.

    Single-open: a versão anterior chamava `_read_head` + `_parse_*` que
    abriam o arquivo 2× (uma para detect, outra para parse). Agora lemos o
    cabeçalho 1× (até 4096 bytes — suficiente p/ PNG/WebP; JPEG cobre 99%
    dos SOF markers nesse intervalo) e passamos para os parsers em bytes.
    """
    if not isinstance(path, Path):
        path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Screenshot not found: {path}")
    if not path.is_file():
        raise ValueError(f"Screenshot path is not a regular file: {path}")

    with open(path, "rb") as fp:
        head = fp.read(4096)

    fmt = _detect_format(head)
    if fmt is None:
        raise ValueError(f"{path}: unrecognized image format (not PNG/JPEG/WebP)")

    if fmt == "png":
        width, height, has_alpha = _parse_png_from_bytes(head, path)
    elif fmt == "jpg":
        try:
            width, height, has_alpha = _parse_jpeg_from_bytes(head, path)
        except ValueError:
            # Fallback: SOF além dos 4 KB iniciais — re-lê tudo (raro).
            with open(path, "rb") as fp:
                full = fp.read()
            width, height, has_alpha = _parse_jpeg_from_bytes(full, path)
    else:
        width, height, has_alpha = _parse_webp_from_bytes(head, path)

    inference = infer_platform_inference(width, height)
    return ScreenshotMetadata(
        path=path,
        width=width,
        height=height,
        file_size_bytes=path.stat().st_size,
        format=fmt,
        has_alpha=has_alpha,
        inferred_platform=infer_platform_from_aspect(width, height),
        platform_inference=inference,
    )


def validate_screenshot(path: Path, *, max_size_mb: int = 10) -> list[str]:
    """Return list of human-readable issues. Empty list = OK."""
    if not isinstance(path, Path):
        path = Path(path)

    issues: list[str] = []

    if not path.exists():
        issues.append(f"file does not exist: {path}")
        return issues
    if not path.is_file():
        issues.append(f"path is not a regular file: {path}")
        return issues

    size_bytes = path.stat().st_size
    max_bytes = max_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        issues.append(
            f"file size {size_bytes // 1024} KB exceeds limit of {max_size_mb} MB"
        )

    try:
        meta = load_screenshot(path)
    except (ValueError, FileNotFoundError) as exc:
        issues.append(str(exc))
        return issues

    if meta.width < _MIN_DIMENSION or meta.height < _MIN_DIMENSION:
        issues.append(
            f"dimensions {meta.width}x{meta.height} below minimum "
            f"{_MIN_DIMENSION}x{_MIN_DIMENSION}"
        )

    return issues


def infer_platform_inference(width: int, height: int) -> PlatformInference:
    """F3: heurística rica — retorna PlatformInference com confidence + nota.

    Plataformas possíveis: 'mobile' (não distingue android/ios), 'web',
    'tablet', 'unknown'. O screen-analysis-agent deve usar o target platform
    declarado no feature-intake-agent para resolver mobile→android|ios.
    """
    if width <= 0 or height <= 0:
        return PlatformInference("unknown", 0.0, "Dimensões inválidas")

    long_side = max(width, height)
    short_side = min(width, height)
    ratio = long_side / short_side
    is_landscape = width > height

    if 0.95 <= ratio <= 1.05:
        return PlatformInference("unknown", 0.0, "Aspect ratio quadrada — ambígua")

    if is_landscape:
        if 1.20 <= ratio <= 2.40:
            return PlatformInference(
                "web",
                0.7,
                "Landscape com aspect ratio típica de desktop/laptop (16:9/16:10/3:2)",
            )
        return PlatformInference("unknown", 0.0, "Landscape com aspect ratio incomum")

    # portrait
    if 1.20 <= ratio < 1.70:
        return PlatformInference(
            "tablet",
            0.5,
            "Portrait com aspect ratio típica de tablet (4:3 a ~5:3)",
        )
    if 1.70 <= ratio <= 2.50:
        return PlatformInference(
            "mobile",
            0.6,
            "Aspect ratio típica de mobile portrait (Android e iPhone indistinguíveis sem screenshot chrome)",
        )
    if ratio > 2.50:
        return PlatformInference(
            "mobile",
            0.5,
            "Portrait muito alto — provavelmente mobile flagship recente",
        )
    return PlatformInference("unknown", 0.0, "Aspect ratio fora dos buckets conhecidos")


def infer_platform_from_aspect(width: int, height: int) -> str | None:
    """Compat shim que retorna apenas a string da plataforma.

    Mantido para callers existentes — novos callers devem preferir
    `infer_platform_inference` para acessar confidence + nota explicativa.

    Diferença de comportamento vs versão anterior: mobile portrait agora
    retorna 'mobile' (não 'android' especulativo) — caller resolve usando
    o target platform declarado pelo intake-agent.
    """
    inference = infer_platform_inference(width, height)
    if inference.platform == "unknown":
        return None
    return inference.platform


def compute_screenshot_fingerprint(path: Path) -> str:
    """sha256 of the file — used in feature manifests for traceability."""
    if not isinstance(path, Path):
        path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Screenshot not found: {path}")

    hasher = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(_FINGERPRINT_CHUNK), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def list_screenshots_in_feature(feature_dir: Path) -> list[ScreenshotMetadata]:
    """Walk `feature_dir/screenshots/` and return metadata for each image, sorted by name."""
    if not isinstance(feature_dir, Path):
        feature_dir = Path(feature_dir)

    screenshots_dir = feature_dir / "screenshots"
    if not screenshots_dir.exists():
        return []
    if not screenshots_dir.is_dir():
        raise NotADirectoryError(f"Expected directory: {screenshots_dir}")

    candidates = sorted(
        p for p in screenshots_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )

    results: list[ScreenshotMetadata] = []
    for candidate in candidates:
        try:
            results.append(load_screenshot(candidate))
        except ValueError:
            continue
    return results


def normalize_screenshot_path(raw_input: str, feature_dir: Path) -> Path:
    """Resolve user-provided screenshot reference to an absolute path.

    Accepted forms:
      - absolute path: aceito apenas se resolver dentro de `feature_dir`
        (bloqueia path traversal — e.g. `/etc/passwd`)
      - relative path: resolved against `feature_dir`, mas tem que resolver
        dentro dela (bloqueia `../../../etc/passwd`)
      - bare filename: looked up under `feature_dir/screenshots/`
    """
    if not raw_input:
        raise ValueError("Empty screenshot path")
    if not isinstance(feature_dir, Path):
        feature_dir = Path(feature_dir)

    feature_dir_resolved = feature_dir.resolve()
    candidate = Path(raw_input)

    if candidate.is_absolute():
        resolved = candidate.resolve()
        # F2: bloqueia path traversal — absolutes têm que ficar contidos em feature_dir.
        if not _is_relative_to(resolved, feature_dir_resolved):
            raise ValueError(
                f"Path traversal detectado: {raw_input!r} resolve fora de {feature_dir}"
            )
        if not resolved.exists():
            raise FileNotFoundError(f"Screenshot not found at absolute path: {resolved}")
        return resolved

    if candidate.parent != Path("."):
        resolved = (feature_dir / candidate).resolve()
        # F2: relative paths com `..` também são bloqueados.
        if not _is_relative_to(resolved, feature_dir_resolved):
            raise ValueError(
                f"Path traversal detectado: {raw_input!r} resolve fora de {feature_dir}"
            )
        if not resolved.exists():
            raise FileNotFoundError(
                f"Screenshot not found relative to feature dir: {resolved}"
            )
        return resolved

    in_screenshots = (feature_dir / "screenshots" / candidate.name).resolve()
    if in_screenshots.exists():
        return in_screenshots

    in_feature = (feature_dir / candidate.name).resolve()
    if in_feature.exists():
        return in_feature

    raise FileNotFoundError(
        f"Screenshot {raw_input!r} not found under {feature_dir}/screenshots/ or {feature_dir}/"
    )


def _is_relative_to(child: Path, parent: Path) -> bool:
    """Polyfill — `Path.is_relative_to` só existe a partir de Python 3.9."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False
