"""
Мини-хелпер для применения тематических иконок к стандартным контекстным меню Qt
(по аналогии с остальными меню приложения).

Поддерживает QLineEdit, QTextEdit, QPlainTextEdit.
Иконки берутся через icon_cache.get_icon(<name>, <theme>, 'context_menu').
Тема определяется через app.utils.icon.path_service.get_current_theme().
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QLineEdit, QMenu, QPlainTextEdit, QTextEdit, QWidget

from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
from app.utils.ui.icon.path_service import get_current_theme

# Логгер модуля
logger = logging.getLogger(__name__)
# Имя пользовательского свойства на виджете, которым отмечаем, что обработчик уже подключён
_PROP_CONNECTED = "_ctx_menu_icons_connected"
# Имя python-атрибута на виджете, в котором храним ссылку на обработчик
_ATTR_HANDLER = "_ctx_menu_icons_handler"
# Соответствие стандартных действий (enum) нашим именам иконок
_SHORTCUT_TO_ICON: dict[QKeySequence.StandardKey, str] = {
    QKeySequence.StandardKey.Cut: "cut",
    QKeySequence.StandardKey.Copy: "copy",
    QKeySequence.StandardKey.Paste: "paste",
    QKeySequence.StandardKey.Undo: "undo",
    QKeySequence.StandardKey.Redo: "redo",
    QKeySequence.StandardKey.SelectAll: "select_all",
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

    - Поддерживает: QLineEdit, QTextEdit, QPlainTextEdit.
    - Безопасен к повторным вызовам: обработчик подключается только один раз.
    - Ссылка на обработчик хранится на виджете (python-атрибут), а флаг подключения — в
      пользовательском свойстве виджета для лёгкой проверки.
    """
    if not isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
        return

    # Если уже подключали раньше — выходим, чтобы не создавать дубликаты слотов
    try:
        if bool(widget.property(_PROP_CONNECTED)):
            return
    except Exception:
        # В случае экзотических ошибок свойств продолжаем обычным путём
        pass

    # Гарантируем CustomContextMenu и готовим обработчик
    widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    handler = getattr(widget, _ATTR_HANDLER, None)
    if handler is None:
        handler = (lambda pos, w=widget: _show_patched_menu(w, pos))
        setattr(widget, _ATTR_HANDLER, handler)

    # На всякий случай пробуем убрать возможную прежнюю связь с тем же handler,
    # чтобы предотвратить дубликаты, если свойство оказалось невалидным
    try:
        widget.customContextMenuRequested.disconnect(handler)  # type: ignore[arg-type]
    except Exception:
        pass

    widget.customContextMenuRequested.connect(handler)  # type: ignore[arg-type]
    widget.setProperty(_PROP_CONNECTED, True)


def disable(widget: QWidget) -> None:
    """Отключить патчинг контекстного меню и разорвать сигнал, если был подключён.

    Безопасно к многократным вызовам. Ничего не делает для неподдерживаемых виджетов.
    """
    if not isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
        return

    handler = getattr(widget, _ATTR_HANDLER, None)
    if handler is None:
        # Нечего отключать
        widget.setProperty(_PROP_CONNECTED, False)
        return

    try:
        widget.customContextMenuRequested.disconnect(handler)  # type: ignore[arg-type]
    except Exception:
        pass
    finally:
        widget.setProperty(_PROP_CONNECTED, False)


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
        # Сначала рекурсивно применяем иконки к подменю, если оно существует.
        # Делаем это вне зависимости от enabled-состояния родительского action,
        # чтобы вложенные уровни не оставались без иконок.
        try:
            submenu = action.menu()
        except Exception:
            submenu = None
        if submenu is not None:
            _apply_theme_icons(submenu)

        # Для самого действия пропускаем разделители и отключённые пункты
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
            # Не ломаем меню из-за иконки, но логируем причину
            logger.exception("[CtxStdMenu] Ошибка применения иконки '%s' к действию '%s'", icon_name, action.text())


def _detect_standard_key(sc: QKeySequence) -> Optional[QKeySequence.StandardKey]:
    """Определить стандартный ключ для заданной последовательности без зависимости от локали.

    Сравниваем с платформенно-зависимыми биндингами через QKeySequence.keyBindings().
    """
    if not sc or sc.isEmpty():
        return None
    # Перебираем только те StandardKey, что нам нужны для иконок
    for sk in _SHORTCUT_TO_ICON.keys():
        try:
            bindings = QKeySequence.keyBindings(sk)
        except Exception:
            bindings = []
        for kb in bindings:
            if kb == sc:
                return sk
    return None


def _guess_icon_name(action: QAction) -> Optional[str]:
    # 1) Пытаемся по стандартному shortcut (enum, без текстовых представлений)
    sc: QKeySequence = action.shortcut()
    sk = _detect_standard_key(sc)
    if sk is not None:
        return _SHORTCUT_TO_ICON.get(sk)

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
