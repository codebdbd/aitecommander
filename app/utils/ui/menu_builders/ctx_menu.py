"""
Мини-хелпер для применения тематических иконок к стандартным контекстным меню Qt
(по аналогии с остальными меню приложения).

Поддерживает QLineEdit, QTextEdit, QPlainTextEdit.
Иконки берутся через icon_cache.get_icon(<name>, <theme>, 'context_menu').
Тема определяется через app.utils.icon.path_service.get_current_theme().
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QLineEdit, QMenu, QPlainTextEdit, QTextEdit, QWidget

from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
from app.utils.ui.icon.path_service import get_current_theme

# Соответствие стандартных действий нашим именам иконок
_SHORTCUT_TO_ICON: dict[str, str] = {
    QKeySequence.StandardKey.Cut.toString().lower(): "cut",
    QKeySequence.StandardKey.Copy.toString().lower(): "copy",
    QKeySequence.StandardKey.Paste.toString().lower(): "paste",
    QKeySequence.StandardKey.Undo.toString().lower(): "undo",
    QKeySequence.StandardKey.Redo.toString().lower(): "redo",
    QKeySequence.StandardKey.SelectAll.toString().lower(): "select_all",
}

_TEXT_TO_ICON: dict[str, str] = {
    # RU
    "вырезать": "cut",
    "копировать": "copy",
    "вставить": "paste",
    "отменить": "undo",
    "повторить": "redo",
    "выделить все": "select_all",
    "удалить": "delete",
    # EN
    "cut": "cut",
    "copy": "copy",
    "paste": "paste",
    "undo": "undo",
    "redo": "redo",
    "select all": "select_all",
    "delete": "delete",
}


def enable(widget: QWidget) -> None:
    """Включить тематические иконки для стандартного контекстного меню виджета.

    Виджет должен быть QLineEdit, QTextEdit или QPlainTextEdit.
    """
    if not isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
        return

    widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    widget.customContextMenuRequested.connect(
        lambda pos, w=widget: _show_patched_menu(w, pos)
    )


def _show_patched_menu(widget: QWidget, pos: QPoint) -> None:
    menu: Optional[QMenu] = None
    if hasattr(widget, "createStandardContextMenu"):
        menu = widget.createStandardContextMenu()
    if menu is None:
        menu = QMenu(widget)

    _apply_theme_icons(menu)
    menu.exec(widget.mapToGlobal(pos))


def _apply_theme_icons(menu: QMenu) -> None:
    theme = get_current_theme()

    for action in menu.actions():
        if not isinstance(action, QAction):
            continue
        if action.isSeparator() or not action.isEnabled():
            continue

        icon_name = _guess_icon_name(action)
        if not icon_name:
            continue
        try:
            icon = icon_cache.get_icon(icon_name, theme, "context_menu")
            if icon:
                action.setIcon(icon)
        except Exception:
            # Не ломаем меню из-за иконки
            pass


def _guess_icon_name(action: QAction) -> Optional[str]:
    # 1) Пытаемся по стандартному shortcut
    sc: QKeySequence = action.shortcut()
    if sc and not sc.isEmpty():
        key = sc.toString().lower()
        if key in _SHORTCUT_TO_ICON:
            return _SHORTCUT_TO_ICON[key]

    # 2) Пытаемся по тексту (без амперсандов и троеточий)
    text = (
        (action.text() or "")
        .replace("&", "")
        .replace("…", "")
        .replace("...", "")
        .strip()
        .lower()
    )
    if text in _TEXT_TO_ICON:
        return _TEXT_TO_ICON[text]

    # 3) Эвристика на Delete
    if "del" in text:
        return "delete"

    return None
