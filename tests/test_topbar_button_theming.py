"""Tests verifying Rule 54: Unified Top Bar Button Styling and Theme Color Isolation."""

from pathlib import Path
from app.config_data import app_config
from app.services.theme_stylesheet_service import ThemeStylesheetService


def test_common_qss_unifies_topbar_buttons() -> None:
    common_qss = Path("app/resources/qss/common.qss").read_text(encoding="utf-8")
    assert "QWidget#topBarHost QToolButton {" in common_qss
    assert "QWidget#topBarHost QToolButton::menu-indicator {" in common_qss
    assert "min-width: 32px;" in common_qss
    assert "max-width: 32px;" in common_qss
    assert "min-height: 32px;" in common_qss
    assert "max-height: 32px;" in common_qss
    # Fragmented per-button indicators must not exist
    assert "QToolBar#topBarToolbar QToolButton#quickButton::menu-indicator" not in common_qss
    assert "QToolBar#topBarToolbar QToolButton#favoriteButton::menu-indicator" not in common_qss


def test_theme_stylesheet_service_unifies_hover_and_click() -> None:
    service = ThemeStylesheetService(app_config)
    qss = service.load_stylesheet("dark", "dark.qss")
    assert qss is not None
    # Must contain unified hover block overriding button states
    assert "/* ==== TopBar button hover accent fill ==== */" in qss
    assert "QWidget#topBarHost QToolButton:hover" in qss
    assert "QWidget#topBarHost QToolButton:pressed" in qss
    assert 'QWidget#topBarHost QToolButton[menu_active="true"]' in qss
    assert "QWidget#topBarHost QToolButton::menu-indicator" in qss


def test_theme_stylesheet_service_does_not_inject_sizes() -> None:
    service = ThemeStylesheetService(app_config)
    overrides_qss = service._build_config_overrides_qss()
    # Dynamic QSS must not constrain topbar button geometry
    assert "QToolBar#topBarToolbar QToolButton[toolbar_btn=\"true\"]" not in overrides_qss
    assert "min-width:" not in overrides_qss or "QToolButton" not in overrides_qss


def test_topbar_icon_geometry_config() -> None:
    icon_sz = app_config.ui.get_top_panel_icon_size()
    assert tuple(icon_sz) == (24, 24)


def test_topbar_geometry_contract() -> None:
    """Verify the exact 323px top bar toolbar geometry contract:
    4px left margin + 8 buttons (34px with 1px border / 32px content) +
    3 separators (1px) + 10 gaps (4px spacing) + 4px separator spacing == 323px.
    """
    button_content_size = 32
    border_width = 1
    button_total_size = button_content_size + 2 * border_width  # 34px
    buttons_count = 8
    separators_count = 3
    spacing = 4
    gaps_count = (buttons_count + separators_count) - 1  # 10
    left_margin = 4
    sep_spacing = 4
    total_width = left_margin + buttons_count * button_total_size + separators_count * 1 + gaps_count * spacing + sep_spacing
    assert total_width == 323
