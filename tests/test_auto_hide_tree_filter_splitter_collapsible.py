import sys

import pytest
from PyQt6.QtWidgets import QApplication, QWidget, QSplitter, QStackedWidget
from PyQt6.QtCore import Qt

from app.views.main_components.window_ui_setup import _AutoHideTreeFilter


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    yield app


class _WindowStub(QWidget):
    """Минимальный контейнер окна с необходимыми атрибутами для _AutoHideTreeFilter."""

    def __init__(self):
        super().__init__()
        # Сплиттер с двумя панелями
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.addWidget(QWidget())
        self.splitter.addWidget(QWidget())
        # Стек и таблица (необязательные для данного теста, но присутствуют в фильтре)
        self.stack = QStackedWidget(self)
        self.table = QWidget(self)
        self.stack.addWidget(QWidget(self))
        self.stack.addWidget(self.table)
        # Топ-бар панели (не используются непосредственно, но доступны для вызовов setVisible)
        self.quick_add_widget = QWidget(self)
        self.fav_widget = QWidget(self)
        self.recent_links_widget = QWidget(self)


@pytest.mark.parametrize("initial_collapsible", [False, True])
def test_auto_hide_restores_splitter_collapsible_flag(qapp, initial_collapsible):
    # Arrange: окно шире порога, исходный флаг collapsible задан заранее
    wnd = _WindowStub()
    wnd.resize(900, 600)
    threshold = 800

    # Изначально выставляем состояние collapsible(0)
    wnd.splitter.setCollapsible(0, initial_collapsible)

    ah = _AutoHideTreeFilter(window=wnd, threshold_width=threshold, default_sizes=[200, 600])

    # Act 1: сузить окно -> авто-скрытие левой панели, принудительный collapsible(0)=True
    wnd.resize(700, 600)  # <= threshold
    ah._apply()
    assert ah._is_collapsed is True
    # В узком режиме мы ожидаем принудительный True
    assert wnd.splitter.isCollapsible(0) is True

    # Act 2: расширить обратно -> восстановить исходный флаг
    wnd.resize(900, 600)  # > threshold
    ah._apply()

    # Assert: восстановлен исходный флаг collapsible(0)
    assert ah._is_collapsed is False
    assert wnd.splitter.isCollapsible(0) is initial_collapsible
