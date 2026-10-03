from math import ceil

import pytest
from PyQt6.QtCore import QPointF, QRect, QSize, Qt
from PyQt6.QtGui import (
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPalette,
    QStandardItem,
    QStandardItemModel,
    QTextLayout,
    QTextOption,
)
from PyQt6.QtWidgets import QApplication, QStyleOptionViewItem

from app.views.widgets.custom_widgets import StructureTreeView
from app.views.widgets.tiles import delegate as tiles


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize("dpr", [1.0, 1.25, 1.5, 1.75, 2.0])
@pytest.mark.parametrize("text", [
    "📁 Alpha beta gamma delta epsilon zeta",
    "Категорія 🎨 Дизайн — шрифты и изображения",
])
def test_tile_matches_qt_text_layout_with_emoji(qapp, monkeypatch, dpr, text):
    monkeypatch.setattr(tiles.app_config.ui, "get_tile_text_max_lines", lambda: 20)
    model = QStandardItemModel()
    item = QStandardItem(text)
    item.setData(True, Qt.ItemDataRole.UserRole + 1)  # Pending icon: text only.
    model.appendRow(item)
    option = QStyleOptionViewItem()
    option.font = QFont("Segoe UI", 10)
    option.font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
    option.palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.black)
    option.rect = QRect(0, 0, 128, 300)
    delegate = tiles.CategoryTileDelegate()

    actual = QImage(ceil(128 * dpr), ceil(300 * dpr), QImage.Format.Format_ARGB32_Premultiplied)
    actual.setDevicePixelRatio(dpr)
    actual.fill(Qt.GlobalColor.white)
    expected = actual.copy()
    painter = QPainter(actual)
    try:
        delegate.paint(painter, option, model.index(0, 0))
    finally:
        painter.end()

    # Qt's complete layout is the reference, including its UTF-16 shaping.
    layout = QTextLayout(text, option.font)
    text_option = QTextOption()
    text_option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    text_option.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
    layout.setTextOption(text_option)
    layout.beginLayout()
    height = 0.0
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(128 - 2 * delegate.padding)
        line.setPosition(QPointF(0, height))
        height += line.height()
    layout.endLayout()
    painter = QPainter(expected)
    try:
        painter.setPen(Qt.GlobalColor.black)
        layout.draw(painter, QPointF(delegate.padding, delegate.padding + delegate.icon_size.height() + 5))
    finally:
        painter.end()
    assert actual == expected
    assert delegate.sizeHint(option, model.index(0, 0)).height() >= (
        height + 2 * delegate.padding + delegate.icon_size.height() + 5
    )


def test_truncated_tile_preserves_emoji_line_and_ellipsis(qapp, monkeypatch):
    monkeypatch.setattr(tiles.app_config.ui, "get_tile_text_max_lines", lambda: 1)
    font = QFont("Segoe UI", 10)
    prefix = "📁 Alpha beta "
    delegate = tiles.CategoryTileDelegate()
    width = ceil(QFontMetricsF(font).horizontalAdvance(prefix))
    model = QStandardItemModel()
    item = QStandardItem(prefix + "gamma delta epsilon zeta")
    item.setData(True, Qt.ItemDataRole.UserRole + 1)
    model.appendRow(item)
    option = QStyleOptionViewItem()
    option.font = font
    option.rect = QRect(0, 0, width + 2 * delegate.padding, 200)
    captured_text = []
    real_layout = tiles.QTextLayout

    def record_layout(text, *args):
        captured_text.append(text)
        return real_layout(text, *args)

    monkeypatch.setattr(tiles, "QTextLayout", record_layout)
    image = QImage(option.rect.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        delegate.paint(painter, option, model.index(0, 0))
    finally:
        painter.end()
    assert len(captured_text) == 2
    assert captured_text[1] == QFontMetricsF(font).elidedText(
        prefix.rstrip() + "…", Qt.TextElideMode.ElideRight, width
    )


def test_tree_relayouts_rows_when_font_grows_and_shrinks(qapp, monkeypatch):
    # Keep the unrelated deferred branch proxy from owning the shared Qt style.
    monkeypatch.setattr(StructureTreeView, "_schedule_branch_proxy_style", lambda self: None)
    tree = StructureTreeView()
    model = QStandardItemModel()
    model.appendRow(QStandardItem("Категорія — крупный текст"))
    model.appendRow(QStandardItem("Следующая строка"))
    tree.setModel(model)
    tree.resize(400, 200)
    try:
        heights = []
        for size in (10, 20, 30, 10):
            tree.update_font_size(size)
            option = QStyleOptionViewItem()
            tree.initViewItemOption(option)
            hint = tree.itemDelegate().sizeHint(option, model.index(0, 0))
            minimum = ceil(QFontMetricsF(tree.font(), tree).height()) + 4
            assert hint.height() >= minimum
            assert tree.visualRect(model.index(0, 0)).height() >= minimum
            heights.append(hint.height())
        assert heights[2] > heights[0]
        assert heights[3] == heights[0]
    finally:
        tree.close()


def test_tree_row_fits_large_icon(qapp, monkeypatch):
    monkeypatch.setattr(StructureTreeView, "_schedule_branch_proxy_style", lambda self: None)
    tree = StructureTreeView()
    model = QStandardItemModel()
    model.appendRow(QStandardItem("Icon"))
    tree.setModel(model)
    try:
        option = QStyleOptionViewItem()
        tree.initViewItemOption(option)
        option.decorationSize = QSize(48, 48)
        assert tree.itemDelegate().sizeHint(option, model.index(0, 0)).height() >= 52
    finally:
        tree.close()
