"""Content hashing helpers.

Three flavours:
- `file_sha256(path)` — file content fingerprint (used by card snapshots).
- `string_sha256(s)` — arbitrary string fingerprint.
- `canonical_form_fingerprint(proposal)` — stable fingerprint of an evolve
  proposal, per discipline §4 / Decision 25. Survives cosmetic edits but
  changes when type/name/description/provenance changes.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any, Iterable

_CHUNK = 65536


def file_sha256(path: Path) -> str:
    """Stream-hash a file. Memory-safe for large blobs."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def string_sha256(s: str) -> str:
    """Hash a UTF-8 string."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def normalise_description(text: str) -> str:
    """Apply discipline §4 normalisation: NFC + casefold + whitespace strip.

    NFC ensures precomposed vs decomposed accents hash the same.
    Casefold (not lower()) handles Unicode properly (German ß, Turkish dotless I).
    Whitespace strip collapses multi-space and trims.

    Public per Mandamento #3 (reuse): consumers em outros módulos (ex.:
    ``engine.qa.synthesis``) precisam compartilhar a mesma normalização
    canônica de canonical-form fingerprint (Decisão 25).
    """
    nfc = unicodedata.normalize("NFC", text or "")
    folded = nfc.casefold()
    # Collapse internal whitespace to single space, strip ends.
    return " ".join(folded.split())


# deprecated alias — use normalise_description.
# Mantido por backward-compat com consumers internos que importavam o nome
# privado antes da promoção pública. Pode ser removido quando todos os
# call sites migrarem.
_normalise_description = normalise_description


def _sorted_unique(items: Iterable[str]) -> list[str]:
    """Sorted-unique list of strings — stable provenance set per discipline §4."""
    return sorted(set(items))


def canonical_form_fingerprint(proposal: dict[str, Any]) -> str:
    """Compute the canonical fingerprint of an evolve proposal.

    Algorithm (Decision 25, discipline §4):

        canonical = json-stringify-sorted({
          "type":                    proposal.type,
          "name":                    proposal.name (id stripped),
          "description-normalized":  casefold(NFC(strip-ws(description))),
          "provenance-set":          sorted-unique(provenance.feature-slugs)
        })
        fingerprint = sha256(canonical)

    The provenance set grows as more features show the same pattern — by design,
    a new provenance entry produces a new fingerprint, so the proposal is
    re-presented to the user with stronger evidence.

    The input dict is expected to have at least:
        type:        str
        name:        str
        description: str
        provenance:  { feature-slugs: [str, ...] }   (may be missing/empty)
    """
    p_type = str(proposal.get("type", ""))
    p_name = str(proposal.get("name", ""))
    p_desc = normalise_description(str(proposal.get("description", "")))

    provenance = proposal.get("provenance") or {}
    slugs = provenance.get("feature-slugs") if isinstance(provenance, dict) else None
    p_provenance = _sorted_unique(slugs or [])

    canonical = json.dumps(
        {
            "type": p_type,
            "name": p_name,
            "description-normalized": p_desc,
            "provenance-set": p_provenance,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return string_sha256(canonical)
