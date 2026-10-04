"""Tests verifying Rule 54: Unified Top Bar Button Styling and Theme Color Isolation."""

from pathlib import Path
from app.config_data import app_config
from app.services.theme_stylesheet_service import ThemeStylesheetService


def test_common_qss_unifies_topbar_buttons() -> None:
    common_qss = Path("app/resources/qss/common.qss").read_text(encoding="utf-8")
    assert "QWidget#topBarHost QToolButton {" in common_qss
    assert "QWidget#topBarHost QToolButton::menu-indicator {" in common_qss
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


def test_topbar_button_geometry_config() -> None:
    assert app_config.ui.get_top_panel_button_size() == 32
    icon_sz = app_config.ui.get_top_panel_icon_size()
    assert tuple(icon_sz) == (24, 24)
