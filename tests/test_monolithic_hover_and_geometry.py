"""Tests ensuring monolithic sharp geometry and unified hover token architecture."""
import re
from pathlib import Path

import pytest

from app.services.theme_registry import theme_registry
from app.services.theme_stylesheet_service import ThemeStylesheetService


def test_category_tiles_no_rounded_corners() -> None:
    """Verify that categoryTiles in common.qss has strictly border-radius: 0."""
    common_qss_path = Path("app/resources/qss/common.qss")
    content = common_qss_path.read_text(encoding="utf-8")

    tiles_match = re.search(
        r"QListWidget#categoryTiles::item,\s*QListView#categoryTiles::item\s*\{([^}]+)\}",
        content,
    )
    assert tiles_match is not None, "categoryTiles selector not found in common.qss"
    block = tiles_match.group(1)
    assert "border-radius: 0" in block, "categoryTiles must have border-radius: 0"
    assert "border-radius: 6px" not in block, "categoryTiles must not have rounded corners"


def test_topbar_and_bottombar_hover_synchronization() -> None:
    """Verify that ThemeStylesheetService adapts both topBar and bottomBar buttons with bg_hover."""
    adapted = ThemeStylesheetService._adapt_qss_for_topbar_buttons("", "dark")
    assert "QWidget#bottomBarContainer QPushButton:hover" in adapted
    assert "QWidget#topBarHost QToolButton#quickButton:hover" in adapted

    tokens = theme_registry.get_theme_tokens("dark")
    hover_bg = tokens["hover_bg"]
    assert f"background: {hover_bg};" in adapted
    assert f"background-color: {hover_bg};" in adapted


def test_dark_theme_qmenubar_hover_token() -> None:
    """Verify that QMenuBar::item:hover in dark.qss uses @hover_bg instead of hardcoded hex."""
    dark_qss_path = Path("app/resources/qss/dark.qss")
    content = dark_qss_path.read_text(encoding="utf-8")

    menubar_hover = re.search(r"QMenuBar::item:hover\s*\{([^}]+)\}", content)
    assert menubar_hover is not None
    block = menubar_hover.group(1)
    assert "@hover_bg" in block
    assert "#252D3A" not in block


def test_dark_theme_category_tiles_hover_token() -> None:
    """Verify that categoryTiles hover in dark.qss uses @hover_bg instead of rgba."""
    dark_qss_path = Path("app/resources/qss/dark.qss")
    content = dark_qss_path.read_text(encoding="utf-8")

    tiles_hover = re.search(r"QListView#categoryTiles::item:hover\s*\{([^}]+)\}", content)
    assert tiles_hover is not None
    block = tiles_hover.group(1)
    assert "@hover_bg" in block
