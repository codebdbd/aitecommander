# Modular structure for ``LinksTableView``
# Defer heavyweight ``base_table`` import to avoid circular imports.
# ``columns.py`` (LINK_TABLE_COLUMN_MAP) has no GUI/service deps and must stay
# importable from pure-config paths such as normalize_app_config().
from __future__ import annotations

from typing import TYPE_CHECKING

from .columns import (
    LINK_TABLE_COLUMNS,
    LINK_TABLE_COLUMN_MAP,
    LinkTableColumn,
    LinkTableColumnDescriptor,
)

__all__ = [
    "LINK_TABLE_COLUMNS",
    "LINK_TABLE_COLUMN_MAP",
    "LinkTableColumn",
    "LinkTableColumnDescriptor",
    "LinksTableView",
]

if TYPE_CHECKING:  # pragma: no cover - runtime lazy import below
    from .base_table import LinksTableView


def __getattr__(name: str):
    if name == "LinksTableView":
        from .base_table import LinksTableView as _LTV

        globals()["LinksTableView"] = _LTV
        return _LTV
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
