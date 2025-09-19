import sys
import types

import pytest

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QToolButton,
)

from app.config_data import app_config
from app.views.main_components.topbar.top_bar_layout_manager import TopBarLayoutManager


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


def _make_panel_with_buttons(object_name: str, count: int) -> QWidget:
    panel = QWidget()
    panel.setObjectName(f"panel_{object_name}")
    # bg_frame с layout, как ожидает менеджер
    bg = QWidget(panel)
    bg.setObjectName("bg_frame")
    lay = QHBoxLayout(bg)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    # Добавляем кнопки
    for _ in range(count):
        b = QToolButton(bg)
        b.setObjectName(object_name)
        lay.addWidget(b)
    # Упрощённо размещаем bg как единственный дочерний виджет панели
    outer = QHBoxLayout(panel)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addWidget(bg)
    return panel


def test_min_visible_quick_respected_when_space_allows(qapp, monkeypatch):
    # Настраиваем конфиг: min_visible.quick = 1 и min ширина поиска = 360, чтобы влезала только 1 быстрая кнопка
    monkeypatch.setattr(app_config.ui, "get", lambda key, default=None: ({"quick": 1} if key == "ui.topbar.min_visible" else default))
    monkeypatch.setattr(
        type(app_config.ui),
        "get_top_panel_search_min_width",
        lambda self: 360,
        raising=False,
    )

    # Подготовим окно и layout top bar
    window = types.SimpleNamespace()
    host = QWidget()
    host.setObjectName("content_container")
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    # Панели: только quick с ДВУМЯ кнопками, чтобы менеджер мог урезать до 1
    quick = _make_panel_with_buttons("quickButton", 2)
    window.quick_add_widget = quick

    # Пустые панели fav/recent
    window.fav_widget = QWidget()
    window.recent_links_widget = QWidget()

    # Поиск
    search = QLineEdit()
    window.search = search

    # Порядок в топбаре: quick | search
    lay.addWidget(quick)
    lay.addWidget(search)

    # Размер и видимость контейнера: ширина 400 (> узкого порога 380), чтобы не включался narrow-mode
    host.setFixedWidth(400)
    host.setVisible(True)
    window.content_container = host

    # Создаём менеджер и выполняем adjust
    mgr = TopBarLayoutManager(window)
    mgr.adjust()

    # Проверка: хотя бы одна быстрая кнопка должна остаться видимой
    quick_buttons = quick.findChildren(QToolButton, "quickButton")
    visible_count = sum(1 for b in quick_buttons if b.isVisible())
    assert visible_count >= 1, "Минимум 1 быстрая кнопка должна оставаться видимой при min_visible.quick=1"
