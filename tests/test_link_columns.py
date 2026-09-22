from __future__ import annotations

from app.views.widgets.link.columns import (
    LINK_TABLE_COLUMNS,
    LinkTableColumn,
    descriptor_for_column,
    normalize_resize_mode_name,
    resize_mode_name_for_descriptor,
)


def _mode(column: LinkTableColumn, configured_value: object | None = None) -> str:
    descriptor = descriptor_for_column(column)
    assert descriptor is not None
    return resize_mode_name_for_descriptor(descriptor, configured_value)


def test_link_table_resize_policy_matches_column_contract() -> None:
    assert _mode(LinkTableColumn.GROUP_LAUNCH) == "fixed"
    assert _mode(LinkTableColumn.NAME) == "interactive"
    assert _mode(LinkTableColumn.ORDER) == "fixed"
    assert _mode(LinkTableColumn.LAUNCH) == "fixed"
    assert _mode(LinkTableColumn.NOTES) == "stretch"
    assert _mode(LinkTableColumn.TYPE) == "interactive"


def test_launch_resize_policy_accepts_legacy_config_aliases() -> None:
    assert _mode(LinkTableColumn.LAUNCH, "i") == "interactive"
    assert _mode(LinkTableColumn.LAUNCH, "content") == "resize_to_contents"
    assert _mode(LinkTableColumn.LAUNCH, "resizetocontents") == "resize_to_contents"
    assert _mode(LinkTableColumn.LAUNCH, "unknown") == "fixed"


def test_resize_mode_name_normalizes_unknown_values_to_default() -> None:
    assert normalize_resize_mode_name("nope", "stretch") == "stretch"
    assert normalize_resize_mode_name(None, "fixed") == "fixed"


def test_all_columns_declare_resize_modes() -> None:
    assert all(descriptor.resize_mode for descriptor in LINK_TABLE_COLUMNS)


def test_column_role_builders_are_declared_in_column_contract() -> None:
    descriptor_by_column = {
        descriptor.column: descriptor for descriptor in LINK_TABLE_COLUMNS
    }

    assert descriptor_by_column[LinkTableColumn.GROUP_LAUNCH].display_builder is None
    assert descriptor_by_column[LinkTableColumn.NAME].display_builder == "_display_name"
    assert descriptor_by_column[LinkTableColumn.ORDER].display_builder == "_display_order"
    assert descriptor_by_column[LinkTableColumn.LAUNCH].display_builder == "_display_launch"
    assert descriptor_by_column[LinkTableColumn.NOTES].display_builder == "_display_notes"
    assert descriptor_by_column[LinkTableColumn.TYPE].display_builder == "_display_type"

    assert descriptor_by_column[LinkTableColumn.NAME].decoration_builder == "_decoration_name"
    assert descriptor_by_column[LinkTableColumn.ORDER].tooltip_builder == "_tooltip_order"
    assert descriptor_by_column[LinkTableColumn.LAUNCH].tooltip_builder == "_tooltip_launch"
    assert descriptor_by_column[LinkTableColumn.TYPE].tooltip_builder == "_tooltip_type"
