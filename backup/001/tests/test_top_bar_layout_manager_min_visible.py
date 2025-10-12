import sys

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
    """Создаёт панель с указанным количеством кнопок."""
    panel = QWidget()
    panel.setObjectName(f"panel_{object_name}")
    # bg_frame с layout, как ожидает менеджер
    bg = QWidget(panel)
    bg.setObjectName("bg_frame")
    lay = QHBoxLayout(bg)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    # Добавляем кнопки
    for i in range(count):
        b = QToolButton(bg)
        b.setObjectName(object_name)
        b.setText(f"Btn{i+1}")
        b.setFixedSize(32, 32)  # Фиксированный размер для предсказуемости
        lay.addWidget(b)
    # Размещаем bg как единственный дочерний виджет панели
    outer = QHBoxLayout(panel)
    outer.setContentsMargins(2, 0, 2, 0)
    outer.setSpacing(0)
    outer.addWidget(bg)
    return panel


def test_min_visible_quick_respected_in_narrow_container(qapp, monkeypatch):
    """Тест проверяет, что минимальное количество кнопок Quick Add соблюдается 
    даже при очень узком контейнере."""
    
    # Настраиваем конфиг: min_visible.quick = 1
    monkeypatch.setattr(
        app_config, 
        "get", 
        lambda key, default=None: (
            {"recent": 0, "fav": 0, "quick": 1} 
            if key == "topbar.min_visible" 
            else default
        )
    )
    monkeypatch.setattr(
        type(app_config.ui),
        "get_top_panel_search_min_width",
        lambda self: 100,  # Маленькая минимальная ширина поиска
        raising=False,
    )

    # Подготовим окно
    window = QWidget()
    host = QWidget(window)
    host.setObjectName("top_bar_host")
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)

    # Панель Quick Add с 3 кнопками
    quick = _make_panel_with_buttons("quickButton", 3)
    window.quick_add_widget = quick

    # Пустые панели fav/recent
    window.fav_widget = QWidget(window)
    window.recent_links_widget = QWidget(window)

    # Поиск
    search = QLineEdit(window)
    window.search = search

    # Порядок в топбаре: quick | search
    lay.addWidget(quick)
    lay.addWidget(search)

    # Очень узкий контейнер (200px) - должен поместиться только 1 кнопка + поиск
    host.setFixedWidth(200)
    host.setVisible(True)
    window.top_bar_host = host

    # Создаём менеджер и выполняем adjust
    mgr = TopBarLayoutManager(window)
    mgr.adjust()

    # Проверка: должна остаться минимум 1 кнопка Quick Add
    quick_buttons = quick.findChildren(QToolButton, "quickButton")
    visible_count = sum(1 for b in quick_buttons if b.isVisible())
    
    assert len(quick_buttons) == 3, "Должно быть создано 3 кнопки"
    assert visible_count >= 1, f"Минимум 1 кнопка Quick Add должна остаться видимой при min_visible.quick=1, получили {visible_count}"


def test_min_visible_fav_respected_with_multiple_panels(qapp, monkeypatch):
    """Тест проверяет, что минимальное количество кнопок Favorites соблюдается 
    при наличии нескольких панелей."""
    
    # Настраиваем конфиг: min_visible.fav = 2, остальные = 0
    monkeypatch.setattr(
        app_config, 
        "get", 
        lambda key, default=None: (
            {"recent": 0, "fav": 2, "quick": 0} 
            if key == "topbar.min_visible" 
            else default
        )
    )
    monkeypatch.setattr(
        type(app_config.ui),
        "get_top_panel_search_min_width",
        lambda self: 80,
        raising=False,
    )

    # Подготовим окно
    window = QWidget()
    host = QWidget(window)
    host.setObjectName("top_bar_host")
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)

    # Панели с кнопками
    quick = _make_panel_with_buttons("quickButton", 4)
    fav = _make_panel_with_buttons("favoriteButton", 5)
    recent = _make_panel_with_buttons("recentButton", 3)
    
    window.quick_add_widget = quick
    window.fav_widget = fav
    window.recent_links_widget = recent

    # Поиск
    search = QLineEdit(window)
    window.search = search

    # Порядок в топбаре: quick | fav | recent | search
    lay.addWidget(quick)
    lay.addWidget(fav)
    lay.addWidget(recent)
    lay.addWidget(search)

    # Средний размер контейнера - должно хватить на минимум fav + поиск
    host.setFixedWidth(300)
    host.setVisible(True)
    window.top_bar_host = host

    # Создаём менеджер и выполняем adjust
    mgr = TopBarLayoutManager(window)
    mgr.adjust()

    # Проверки
    fav_buttons = fav.findChildren(QToolButton, "favoriteButton")
    fav_visible_count = sum(1 for b in fav_buttons if b.isVisible())
    
    assert len(fav_buttons) == 5, "Должно быть создано 5 кнопок Favorites"
    assert fav_visible_count >= 2, f"Минимум 2 кнопки Favorites должны остаться видимыми при min_visible.fav=2, получили {fav_visible_count}"


def test_min_visible_zero_allows_full_collapse(qapp, monkeypatch):
    """Тест проверяет, что при min_visible = 0 панель может полностью схлопнуться."""
    
    # Настраиваем конфиг: все min_visible = 0
    monkeypatch.setattr(
        app_config, 
        "get", 
        lambda key, default=None: (
            {"recent": 0, "fav": 0, "quick": 0} 
            if key == "topbar.min_visible" 
            else default
        )
    )
    monkeypatch.setattr(
        type(app_config.ui),
        "get_top_panel_search_min_width",
        lambda self: 150,
        raising=False,
    )

    # Подготовим окно
    window = QWidget()
    host = QWidget(window)
    host.setObjectName("top_bar_host")
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)

    # Панель Quick Add с 2 кнопками
    quick = _make_panel_with_buttons("quickButton", 2)
    window.quick_add_widget = quick

    # Пустые панели
    window.fav_widget = QWidget(window)
    window.recent_links_widget = QWidget(window)

    # Поиск
    search = QLineEdit(window)
    window.search = search

    lay.addWidget(quick)
    lay.addWidget(search)

    # Очень узкий контейнер - должен поместиться только поиск
    host.setFixedWidth(180)  # Только для поиска
    host.setVisible(True)
    window.top_bar_host = host

    # Создаём менеджер и выполняем adjust
    mgr = TopBarLayoutManager(window)
    mgr.adjust()

    # Проверка: все кнопки могут быть скрыты при min_visible = 0
    quick_buttons = quick.findChildren(QToolButton, "quickButton")
    visible_count = sum(1 for b in quick_buttons if b.isVisible())
    
    assert visible_count == 0, f"При min_visible.quick=0 и узком контейнере все кнопки должны быть скрыты, получили {visible_count} видимых"


def test_min_visible_limited_by_available_buttons(qapp, monkeypatch):
    """Тест проверяет, что min_visible не может требовать больше кнопок, чем есть в панели."""
    
    # Настраиваем конфиг: min_visible.quick = 5, но в панели только 2 кнопки
    monkeypatch.setattr(
        app_config, 
        "get", 
        lambda key, default=None: (
            {"recent": 0, "fav": 0, "quick": 5}  # Требуем 5, но есть только 2
            if key == "topbar.min_visible" 
            else default
        )
    )
    monkeypatch.setattr(
        type(app_config.ui),
        "get_top_panel_search_min_width",
        lambda self: 100,
        raising=False,
    )

    # Подготовим окно
    window = QWidget()
    host = QWidget(window)
    host.setObjectName("top_bar_host")
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)

    # Панель Quick Add с только 2 кнопками
    quick = _make_panel_with_buttons("quickButton", 2)
    window.quick_add_widget = quick

    # Пустые панели
    window.fav_widget = QWidget(window)
    window.recent_links_widget = QWidget(window)

    # Поиск
    search = QLineEdit(window)
    window.search = search

    lay.addWidget(quick)
    lay.addWidget(search)

    # Достаточно широкий контейнер
    host.setFixedWidth(400)
    host.setVisible(True)
    window.top_bar_host = host

    # Создаём менеджер и выполняем adjust
    mgr = TopBarLayoutManager(window)
    mgr.adjust()

    # Проверка: должны быть видимы все доступные кнопки (2), а не 5
    quick_buttons = quick.findChildren(QToolButton, "quickButton")
    visible_count = sum(1 for b in quick_buttons if b.isVisible())
    
    assert len(quick_buttons) == 2, "Должно быть создано 2 кнопки"
    assert visible_count == 2, f"Должны быть видимы все 2 доступные кнопки (не больше), получили {visible_count}"
