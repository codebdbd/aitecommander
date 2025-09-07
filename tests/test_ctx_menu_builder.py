import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QLineEdit, QMenu

import app.utils.ui.menu_builders.ctx_menu as ctx_menu


@pytest.mark.qt_no_exception_capture
def test_enable_idempotent_and_disable_disconnect(qtbot, monkeypatch):
    widget = QLineEdit()
    qtbot.addWidget(widget)

    calls = {"count": 0}

    def spy_show_patched_menu(w, pos):
        calls["count"] += 1

    # Подменяем внутренний обработчик, чтобы считать вызовы
    monkeypatch.setattr(ctx_menu, "_show_patched_menu", spy_show_patched_menu)

    # Многократное включение не должно дублировать обработчик
    ctx_menu.enable(widget)
    ctx_menu.enable(widget)
    ctx_menu.enable(widget)

    # Эмитим сигнал — обработчик должен сработать ровно 1 раз
    widget.customContextMenuRequested.emit(QPoint(1, 2))
    assert calls["count"] == 1

    # Отключаем и проверяем, что обработчик не вызывается
    ctx_menu.disable(widget)
    widget.customContextMenuRequested.emit(QPoint(3, 4))
    assert calls["count"] == 1

    # Включаем снова — теперь должен прибавиться ещё один вызов
    ctx_menu.enable(widget)
    widget.customContextMenuRequested.emit(QPoint(5, 6))
    assert calls["count"] == 2


@pytest.mark.qt_no_exception_capture
def test_apply_theme_icons_recursive_on_submenus(monkeypatch):
    # Строим меню с вложенными подменю, причём родительский action будет disabled,
    # чтобы убедиться, что рекурсивная обработка всё равно дойдёт до подменю
    menu = QMenu()

    # Верхний уровень: один action с подменю (disabled)
    parent_action = QAction("Parent", menu)
    parent_action.setEnabled(False)
    submenu_lvl1 = QMenu("Level 1", menu)
    parent_action.setMenu(submenu_lvl1)
    menu.addAction(parent_action)

    # В подменю lvl1 — действие, которому можно подобрать иконку по тексту
    act_copy = QAction("Copy", submenu_lvl1)
    submenu_lvl1.addAction(act_copy)

    # И ещё одно подменю внутри lvl1
    submenu_lvl2 = QMenu("Level 2", submenu_lvl1)
    act_paste = QAction("Paste", submenu_lvl2)
    submenu_lvl2.addAction(act_paste)

    act_delete = QAction("Delete", submenu_lvl2)
    submenu_lvl2.addAction(act_delete)

    act_sep = QAction(submenu_lvl1)
    act_sep.setSeparator(True)
    submenu_lvl1.addAction(act_sep)

    # Подвешиваем вложенное подменю
    act_nested_menu = QAction("Nested", submenu_lvl1)
    act_nested_menu.setMenu(submenu_lvl2)
    submenu_lvl1.addAction(act_nested_menu)

    # Подменим icon_cache.get_icon, чтобы считать вызовы и возвращать валидную QIcon
    calls = []

    def fake_get_icon(name, theme, scope):
        calls.append((name, theme, scope))
        # Возвращаем пустую иконку; setIcon её примет, а нам важен факт вызова
        return QIcon()

    monkeypatch.setattr(ctx_menu, "icon_cache", type("_Stub", (), {"get_icon": staticmethod(fake_get_icon)})())

    # Выполняем
    ctx_menu._apply_theme_icons(menu)

    # Ожидаем, что иконки пытались назначить для всех пунктов, где можем угадать имя:
    # act_copy -> copy, act_paste -> paste, act_delete -> delete
    requested_icon_names = {name for (name, _, _) in calls}
    assert {"copy", "paste", "delete"}.issubset(requested_icon_names)

    # Также убеждаемся, что вызовы были и для вложенных уровней (минимум 3 вызова)
    assert len(calls) >= 3
