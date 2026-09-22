from __future__ import annotations

from app.config_data.config_loader import normalize_app_config
from app.config_data.ui_config import UIConfig
from app.views.widgets.link.columns import LINK_TABLE_COLUMN_MAP


def test_normalize_app_config_replaces_legacy_link_table_columns() -> None:
    config = {
        "ui": {
            "links_table_columns": {
                "favorite": 0,
                "name": 1,
                "last_used": 2,
                "notes": 3,
            },
        },
    }

    normalize_app_config(config)

    assert config["ui"]["links_table_columns"] == LINK_TABLE_COLUMN_MAP


def test_normalize_app_config_removes_legacy_table_font_keys() -> None:
    config = {
        "ui": {
            "links_table_columns": dict(LINK_TABLE_COLUMN_MAP),
            "fonts": {
                "table_header_px": 10,
                "table_row_px": 11,
                "table_opened_col_px": 11,
                "table_notes_col_px": 11,
                "table_cols_px": [11, 11, 10, 10],
            },
        },
    }

    normalize_app_config(config)

    assert config["ui"]["fonts"] == {
        "table_header_px": 10,
        "table_row_px": 11,
    }


def test_ui_config_returns_normalized_link_table_columns() -> None:
    config = {"ui": {"links_table_columns": dict(LINK_TABLE_COLUMN_MAP)}}

    assert UIConfig(config).get_links_table_columns() == LINK_TABLE_COLUMN_MAP
