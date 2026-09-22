"""Declarative column contract for the links table."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

class LinkTableColumn(IntEnum):
    GROUP_LAUNCH = 0
    NAME = 1
    ORDER = 2
    LAUNCH = 3
    NOTES = 4
    TYPE = 5


@dataclass(frozen=True)
class LinkTableColumnDescriptor:
    column: LinkTableColumn
    key: str
    header_source: str
    header_tooltip_source: str | None = None
    editable: bool = False
    sortable: bool = True
    centered: bool = False
    min_width: int = 0
    stretch: bool = False
    chevron_padding: bool = False
    config_width_index: int | None = None
    fallback_width: int | None = None
    resize_mode: str = "interactive"
    resize_mode_config_key: str | None = None
    display_builder: str | None = None
    tooltip_builder: str | None = None
    decoration_builder: str | None = None

    @property
    def index(self) -> int:
        return int(self.column)


LINK_TABLE_COLUMNS: tuple[LinkTableColumnDescriptor, ...] = (
    LinkTableColumnDescriptor(
        column=LinkTableColumn.GROUP_LAUNCH,
        key="group_launch",
        header_source="",
        sortable=False,
        centered=True,
        min_width=32,
        fallback_width=32,
        resize_mode="fixed",
    ),
    LinkTableColumnDescriptor(
        column=LinkTableColumn.NAME,
        key="name",
        header_source="Name",
        config_width_index=1,
        display_builder="_display_name",
        tooltip_builder="_tooltip_name",
        decoration_builder="_decoration_name",
    ),
    LinkTableColumnDescriptor(
        column=LinkTableColumn.ORDER,
        key="order",
        header_source="Order",
        header_tooltip_source="Custom order",
        editable=True,
        centered=True,
        min_width=112,
        chevron_padding=True,
        resize_mode="fixed",
        display_builder="_display_order",
        tooltip_builder="_tooltip_order",
    ),
    LinkTableColumnDescriptor(
        column=LinkTableColumn.LAUNCH,
        key="last_used",
        header_source="Launch",
        header_tooltip_source="Last launch",
        centered=True,
        chevron_padding=True,
        config_width_index=2,
        resize_mode="fixed",
        resize_mode_config_key="ui.links_table_col2_mode",
        display_builder="_display_launch",
        tooltip_builder="_tooltip_launch",
    ),
    LinkTableColumnDescriptor(
        column=LinkTableColumn.NOTES,
        key="notes",
        header_source="Notes",
        stretch=True,
        resize_mode="stretch",
        display_builder="_display_notes",
        tooltip_builder="_tooltip_notes",
    ),
    LinkTableColumnDescriptor(
        column=LinkTableColumn.TYPE,
        key="type",
        header_source="Type",
        header_tooltip_source="Resource type",
        fallback_width=104,
        display_builder="_display_type",
        tooltip_builder="_tooltip_type",
    ),
)

_BY_COLUMN = {descriptor.column: descriptor for descriptor in LINK_TABLE_COLUMNS}
_BY_INDEX = {descriptor.index: descriptor for descriptor in LINK_TABLE_COLUMNS}
_BY_KEY = {descriptor.key: descriptor for descriptor in LINK_TABLE_COLUMNS}

LINK_TABLE_COLUMN_MAP = {descriptor.key: descriptor.index for descriptor in LINK_TABLE_COLUMNS}

_RESIZE_MODE_ALIASES = {
    "f": "fixed",
    "fixed": "fixed",
    "i": "interactive",
    "interactive": "interactive",
    "s": "stretch",
    "stretch": "stretch",
    "auto": "resize_to_contents",
    "content": "resize_to_contents",
    "contents": "resize_to_contents",
    "resizetocontents": "resize_to_contents",
    "resize_to_contents": "resize_to_contents",
}


def descriptor_for_column(column: int | LinkTableColumn) -> LinkTableColumnDescriptor | None:
    try:
        return _BY_INDEX.get(int(column))
    except Exception:
        return None


def is_column(column: int, expected: LinkTableColumn) -> bool:
    return int(column) == int(expected)


def sortable_columns() -> set[int]:
    return {descriptor.index for descriptor in LINK_TABLE_COLUMNS if descriptor.sortable}


def centered_columns() -> set[int]:
    return {descriptor.index for descriptor in LINK_TABLE_COLUMNS if descriptor.centered}


def chevron_padding_columns() -> set[int]:
    return {
        descriptor.index
        for descriptor in LINK_TABLE_COLUMNS
        if descriptor.chevron_padding
    }


def header_tooltips() -> dict[int, str]:
    return {
        descriptor.index: descriptor.header_tooltip_source
        for descriptor in LINK_TABLE_COLUMNS
        if descriptor.header_tooltip_source
    }


def header_sources() -> list[str]:
    return [descriptor.header_source for descriptor in LINK_TABLE_COLUMNS]


def normalize_resize_mode_name(value: object, default: str = "interactive") -> str:
    """Return a canonical resize-mode name supported by the table view."""
    mode = str(value if value is not None else default).strip().lower()
    return _RESIZE_MODE_ALIASES.get(mode, _RESIZE_MODE_ALIASES.get(default, "interactive"))


def resize_mode_name_for_descriptor(
    descriptor: LinkTableColumnDescriptor,
    configured_value: object | None = None,
) -> str:
    """Return the canonical resize mode for a column descriptor."""
    return normalize_resize_mode_name(
        configured_value if configured_value is not None else descriptor.resize_mode,
        descriptor.resize_mode,
    )


def sort_key_for_column(column: int, link: dict[str, Any], type_label: str = "") -> Any:
    """Return the simple sort key field for a table column.

    Complex normalization is still handled by the model while sorting remains
    there. This helper centralizes which data field belongs to each column.
    """
    if is_column(column, LinkTableColumn.GROUP_LAUNCH):
        return 1 if bool(link.get("is_group_launch", False)) else 0
    if is_column(column, LinkTableColumn.NAME):
        return str(link.get("name", "")).casefold()
    if is_column(column, LinkTableColumn.ORDER):
        try:
            return int(link.get("position", 0) or 0)
        except Exception:
            return 0
    if is_column(column, LinkTableColumn.NOTES):
        return str(link.get("notes", "")).casefold()
    if is_column(column, LinkTableColumn.TYPE):
        return type_label.casefold()
    return None
