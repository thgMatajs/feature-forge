"""Codebase graph — full builder, incremental delta updates, canonical queries.

Backing store: SQLite (WAL mode). Schema em docs/schemas/graph.md.
"""

from engine.graph.builder import build_full, discover_source_files
from engine.graph.incremental import remove_file, update_batch, update_file
from engine.graph.queries import (
    blast_radius,
    commits_touching_feature,
    find_di_dependencies,
    find_ds_components_used_in,
    find_i18n_keys_used_in,
    find_orphan_files,
    find_routes_in_feature,
    find_similar_features,
    find_symbols_in_module,
    find_tests_covering_file,
)

__all__ = [
    "build_full",
    "discover_source_files",
    "update_file",
    "remove_file",
    "update_batch",
    "find_similar_features",
    "blast_radius",
    "find_orphan_files",
    "find_symbols_in_module",
    "find_ds_components_used_in",
    "find_i18n_keys_used_in",
    "find_routes_in_feature",
    "find_di_dependencies",
    "find_tests_covering_file",
    "commits_touching_feature",
]
