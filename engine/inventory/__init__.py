"""Inventory extractors — design-system, i18n, conventions.

Cada extractor lê o projeto real e produz `.claude/inventory/{x}.yaml`.
Os YAMLs são consumidos por agents downstream (screen-analysis-agent,
contract-planner-agent, etc) como snapshot factual do projeto.
"""

from engine.inventory.design_system import (
    DSComponent,
    DSTokens,
    DesignSystemInventory,
    extract_design_system,
    read_design_system_inventory,
    write_design_system_inventory,
)
from engine.inventory.i18n import (
    I18nInventory,
    I18nKey,
    extract_i18n,
    read_i18n_inventory,
    write_i18n_inventory,
)
from engine.inventory.conventions import (
    ConventionsInventory,
    diff_conventions,
    extract_conventions,
    read_conventions_inventory,
    write_conventions_inventory,
)

__all__ = [
    "DSComponent",
    "DSTokens",
    "DesignSystemInventory",
    "extract_design_system",
    "read_design_system_inventory",
    "write_design_system_inventory",
    "I18nInventory",
    "I18nKey",
    "extract_i18n",
    "read_i18n_inventory",
    "write_i18n_inventory",
    "ConventionsInventory",
    "diff_conventions",
    "extract_conventions",
    "read_conventions_inventory",
    "write_conventions_inventory",
]
