import sys

import pytest

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QHBoxLayout,
    QLineEdit,
)

from app.config_data import app_config
from app.views.main_components.topbar.top_bar_layout_manager import TopBarLayoutManager


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


def test_search_width_constrained_on_zero_container_width(qapp, monkeypatch):
    """Тест проверяет, что поле поиска ограничивается минимальной шириной 
    при нулевой ширине контейнера (race condition при первом показе окна)."""
    
    # Настраиваем конфиг: минимальная ширина поиска = 140
    monkeypatch.setattr(
        type(app_config.ui),
        "get_top_panel_search_min_width",
        lambda self: 140,
        raising=False,
    )

    # Подготовим окно и layout top bar
    window = QWidget()
    host = QWidget(window)
    host.setObjectName("top_bar_host")
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    # Пустые панели
    window.quick_add_widget = QWidget(window)
    window.fav_widget = QWidget(window)
    window.recent_links_widget = QWidget(window)

    # Поиск с изначально большой максимальной шириной (Expanding политика)
    search = QLineEdit(window)
    search.setMaximumWidth(16777215)  # Qt максимум
    window.search = search

    lay.addWidget(search)

    # Контейнер с нулевой шириной (имитируем race condition)
    host.setFixedWidth(0)
    host.setVisible(True)
    window.top_bar_host = host

    # Создаём менеджер и выполняем adjust
    mgr = TopBarLayoutManager(window)
    mgr.adjust()

    # Проверка: поиск должен быть ограничен минимальной шириной
    assert search.maximumWidth() == 140, f"Поиск должен быть ограничен 140px при нулевой ширине контейнера, получили {search.maximumWidth()}"


def test_search_width_constrained_on_invisible_container(qapp, monkeypatch):
    """Тест проверяет, что поле поиска ограничивается минимальной шириной 
    при скрытом контейнере."""
    
    # Настраиваем конфиг
    monkeypatch.setattr(
        type(app_config.ui),
        "get_top_panel_search_min_width",
        lambda self: 140,
        raising=False,
    )

    # Подготовим окно
    window = QWidget()
    host = QWidget(window)
    host.setObjectName("top_bar_host")
    lay = QHBoxLayout(host)

    # Пустые панели
    window.quick_add_widget = QWidget(window)
    window.fav_widget = QWidget(window)
    window.recent_links_widget = QWidget(window)

    # Поиск
    search = QLineEdit(window)
    search.setMaximumWidth(16777215)
    window.search = search

    lay.addWidget(search)

    # Контейнер скрыт (но с нормальной шириной)
    host.setFixedWidth(400)
    host.setVisible(False)  # Скрыт!
    window.top_bar_host = host

    # Создаём менеджер и выполняем adjust
    mgr = TopBarLayoutManager(window)
    mgr.adjust()

    # Проверка: поиск должен быть ограничен минимальной шириной
    assert search.maximumWidth() == 140, f"Поиск должен быть ограничен 140px при скрытом контейнере, получили {search.maximumWidth()}"


def test_search_width_normal_when_container_visible_and_sized(qapp, monkeypatch):
    """Тест проверяет, что при нормальных условиях (контейнер видим и имеет ширину)
    поиск получает правильные размеры."""
    
    # Настраиваем конфиг
    monkeypatch.setattr(
        type(app_config.ui),
        "get_top_panel_search_min_width",
        lambda self: 140,
        raising=False,
    )

    # Подготовим окно
    window = QWidget()
    host = QWidget(window)
    host.setObjectName("top_bar_host")
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    # Пустые панели
    window.quick_add_widget = QWidget(window)
    window.fav_widget = QWidget(window)
    window.recent_links_widget = QWidget(window)

    # Поиск
    search = QLineEdit(window)
    search.setMaximumWidth(16777215)
    window.search = search

    lay.addWidget(search)

    # Контейнер видим и имеет нормальную ширину
    host.setFixedWidth(400)
    host.setVisible(True)
    window.top_bar_host = host

    # Создаём менеджер и выполняем adjust
    mgr = TopBarLayoutManager(window)
    mgr.adjust()

    # Проверка: поиск должен получить максимальную ширину больше минимальной
    # (поскольку панели пустые, поиск должен получить всё доступное место)
    assert search.maximumWidth() > 140, f"При нормальных условиях поиск должен получить больше 140px, получили {search.maximumWidth()}"
