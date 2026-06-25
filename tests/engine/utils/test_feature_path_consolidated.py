"""Testes de consolidacao do path de artefatos de feature.

Consolidação + regressão M-04 (feature_path non-product). Garante que
FEATURE_WORKFLOW_DIRNAME em engine.utils.paths e a fonte unica da qual
todos os helpers derivam o caminho base de artefatos de feature, incluindo
o subtype non-product introduzido em M-04.
"""

from __future__ import annotations

import engine.utils.paths as paths


def test_workflow_dirname_is_single_source(monkeypatch, tmp_path):
    # Patching the canonical constant must flow to every derived path.
    monkeypatch.setattr(paths, "FEATURE_WORKFLOW_DIRNAME", "SENTINEL_DIR")
    root = tmp_path
    assert paths.feature_workflow_root(root) == root / "docs" / "SENTINEL_DIR"
    assert paths.feature_dir(root, "x") == root / "docs" / "SENTINEL_DIR" / "features" / "x"
    assert paths._resolve_features_root(root) == (root / "docs" / "SENTINEL_DIR" / "features").resolve()
    assert paths.feature_path(root, "feat-x") == root / "docs" / "SENTINEL_DIR" / "features" / "feat-x"
    # Non-product subtype também deriva da constante única (regressão M-04).
    assert paths.feature_path(root, "x", subtype="refactor") == root.resolve() / "docs" / "SENTINEL_DIR" / "non-product" / "x"
