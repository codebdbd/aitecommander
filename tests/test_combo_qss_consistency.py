from __future__ import annotations

from pathlib import Path


THEME_FILES = [
    "common.qss",
    "dark.qss",
    "dreamy_room.qss",
    "light.qss",
    "matrix.qss",
    "violet_pulse.qss",
    "crimson_noir.qss",
    "cyberpunk_neon.qss",
    "ghost_terminal.qss",
    "industrial_yellow.qss",
    "love.qss",
    "nord_light.qss",
    "obsidian_luxe.qss",
    "pastel_bloom.qss",
    "pearl_gray.qss",
    "rasta_royale.qss",
    "sage_light.qss",
    "sakura_anime.qss",
]


def test_combo_popup_hover_and_selection_rules_exist_for_all_themes() -> None:
    qss_dir = Path("app/resources/qss")
    for file_name in THEME_FILES:
        content = (qss_dir / file_name).read_text(encoding="utf-8")
        if file_name != "common.qss":
            assert "QComboBox QAbstractItemView::item:selected" in content, file_name
            assert "QComboBox QAbstractItemView::item:hover" in content, file_name


def test_settings_dialog_has_no_theme_specific_qss_branch() -> None:
    qss_dir = Path("app/resources/qss")
    for file_name in THEME_FILES:
        content = (qss_dir / file_name).read_text(encoding="utf-8")
        assert "QDialog#SettingsDialog" not in content, file_name
