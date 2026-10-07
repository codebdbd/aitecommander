"""Tests for TintedSvgIconEngine, HiDPI vector scaling, and rotation icon."""
from __future__ import annotations

from pathlib import Path
import pytest
from PyQt6.QtCore import QRect, QSize
from PyQt6.QtGui import QIcon, QIconEngine, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

from app.utils.ui.icon.icon_operations.creators import (
    TintedSvgIconEngine,
    _create_tinted_svg_icon,
)
from app.views.widgets.link.links_model import get_rotation_icon

_SAMPLE_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
<circle cx="12" cy="12" r="10" fill="#ff0000"/>
</svg>"""


def test_tinted_svg_icon_engine_instance(qapp: QApplication) -> None:
    engine = TintedSvgIconEngine(_SAMPLE_SVG)
    assert isinstance(engine, QIconEngine)

    icon = QIcon(engine)
    assert not icon.isNull()


def test_tinted_svg_icon_engine_actual_size(qapp: QApplication) -> None:
    engine = TintedSvgIconEngine(_SAMPLE_SVG)
    icon = QIcon(engine)

    assert icon.actualSize(QSize(16, 16)) == QSize(16, 16)
    assert icon.actualSize(QSize(20, 20)) == QSize(20, 20)
    assert icon.actualSize(QSize(48, 48)) == QSize(48, 48)


def test_tinted_svg_icon_engine_pixmap_hidpi(qapp: QApplication) -> None:
    engine = TintedSvgIconEngine(_SAMPLE_SVG)
    icon = QIcon(engine)

    pixmap = icon.pixmap(24, 24)
    assert not pixmap.isNull()
    assert pixmap.devicePixelRatio() >= 1.0


def test_tinted_svg_icon_engine_paint(qapp: QApplication) -> None:
    engine = TintedSvgIconEngine(_SAMPLE_SVG)
    pix = QPixmap(32, 32)
    pix.fill()
    painter = QPainter(pix)
    engine.paint(painter, QRect(0, 0, 32, 32), QIcon.Mode.Normal, QIcon.State.Off)
    engine.paint(painter, QRect(0, 0, 32, 32), QIcon.Mode.Disabled, QIcon.State.Off)
    painter.end()


def test_tinted_svg_icon_engine_clone(qapp: QApplication) -> None:
    engine = TintedSvgIconEngine(_SAMPLE_SVG)
    cloned = engine.clone()
    assert isinstance(cloned, TintedSvgIconEngine)
    assert cloned._svg_bytes == engine._svg_bytes

    icon = QIcon(engine)
    copied_icon = QIcon(icon)
    assert not copied_icon.isNull()


def test_create_tinted_svg_icon_helper(qapp: QApplication, tmp_path: Path) -> None:
    svg_file = tmp_path / "test.svg"
    svg_file.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="#000">'
        '<rect width="24" height="24"/></svg>',
        encoding="utf-8",
    )
    icon = _create_tinted_svg_icon(str(svg_file), "#00FF00")
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_get_rotation_icon(qapp: QApplication) -> None:
    icon_normal = get_rotation_icon(16, is_selected=False)
    assert icon_normal is not None
    assert not icon_normal.isNull()

    icon_selected = get_rotation_icon(16, is_selected=True)
    assert icon_selected is not None
    assert not icon_selected.isNull()
