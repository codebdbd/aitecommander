from __future__ import annotations

import logging
from typing import Callable, Optional

from PyQt6.QtWidgets import QLayout, QLineEdit, QSizePolicy, QWidget

logger = logging.getLogger(__name__)


def _save_search_state(search: Optional[QLineEdit]) -> None:
    """Сохраняет состояние кнопки очистки и видимости действий поиска на самом QLineEdit.

    Состояние сохраняется в атрибуте Python `_topbar_saved_state` у `search` и
    используется для последующего восстановления при выходе из узкого режима.
    Повторное сохранение не выполняется, если состояние уже сохранено.
    """
    try:
        if not isinstance(search, QLineEdit):
            return
        if getattr(search, "_topbar_saved_state", None) is not None:
            return
        state = {"clear": None, "actions": {}}
        try:
            # Некоторые окружения могут не поддерживать isClearButtonEnabled
            if hasattr(search, "isClearButtonEnabled"):
                state["clear"] = bool(search.isClearButtonEnabled())
        except Exception:
            logger.debug("TopBarLM: failed to read clear button state (save)", exc_info=True)
        try:
            for act in search.actions():
                try:
                    state["actions"][act] = bool(act.isVisible())
                except Exception:
                    logger.debug("TopBarLM: failed to read search action visibility (save)", exc_info=True)
        except Exception:
            logger.debug("TopBarLM: failed to iterate search actions (save)", exc_info=True)
        try:
            setattr(search, "_topbar_saved_state", state)
        except Exception:
            # Если не удалось сохранить атрибут — ничего не ломаем
            logger.debug("TopBarLM: failed to stash search state (save)", exc_info=True)
    except Exception:
        logger.debug("TopBarLM: unexpected error during saving search state", exc_info=True)


def restore_search_state(search: Optional[QLineEdit]) -> None:
    """Восстанавливает состояние кнопки очистки и видимости действий поиска, если оно было сохранено.

    После успешного восстановления сохранённое состояние удаляется.
    """
    try:
        if not isinstance(search, QLineEdit):
            return
        state = getattr(search, "_topbar_saved_state", None)
        if not isinstance(state, dict):
            return
        # Восстановить clear button
        try:
            clear_state = state.get("clear", None)
            if clear_state is not None and hasattr(search, "setClearButtonEnabled"):
                search.setClearButtonEnabled(bool(clear_state))
        except Exception:
            logger.debug("TopBarLM: failed to restore clear button state", exc_info=True)
        # Восстановить видимость действий
        try:
            actions_state = state.get("actions", {})
            for act in search.actions():
                try:
                    if act in actions_state:
                        act.setVisible(bool(actions_state[act]))
                except Exception:
                    logger.debug("TopBarLM: failed to restore action visibility", exc_info=True)
        except Exception:
            logger.debug("TopBarLM: failed to iterate search actions (restore)", exc_info=True)
        # Очистить сохранённое состояние
        try:
            delattr(search, "_topbar_saved_state")
        except Exception:
            pass
    except Exception:
        logger.debug("TopBarLM: unexpected error during restoring search state", exc_info=True)


def apply_narrow_mode(
    *,
    top_bar: QLayout,
    search: Optional[QLineEdit],
    set_top_bar_margins: Callable[[QLayout, int, int, int, int], None],
    enforce_stretches: Callable[[QLayout, Optional[QLineEdit]], None],
    get_container_widget: Callable[[], Optional[QWidget]],
) -> None:
    """Применяет узкий режим top-bar: скрывает все не-поисковые виджеты, убирает отступы
    и растягивает поиск на всю ширину. Поведение идентично исходной реализации.
    """
    try:
        count = top_bar.count()
        for i in range(count):
            it = top_bar.itemAt(i)
            w = it.widget()
            if w is None:
                continue
            if isinstance(search, QLineEdit) and w is search:
                continue
            try:
                w.setVisible(False)
            except Exception:
                logger.debug(
                    "TopBarLM: failed to hide non-search widget in narrow mode",
                    exc_info=True,
                )
        # Обнулить все spacerItem, чтобы не было отступов слева/справа от поиска
        try:
            for i in range(count):
                sp = top_bar.itemAt(i).spacerItem()
                if sp is not None:
                    sp.changeSize(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        except Exception:
            logger.debug("TopBarLM: failed to zero spacers in narrow mode", exc_info=True)
        # Отключить встроенные действия у поиска (иконки слева/справа, кнопка очистки)
        if isinstance(search, QLineEdit):
            # Сохранить текущее состояние перед отключением
            _save_search_state(search)
            try:
                search.setClearButtonEnabled(False)
            except Exception:
                logger.debug(
                    "TopBarLM: failed to disable clear button on search (narrow mode)",
                    exc_info=True,
                )
            try:
                for act in search.actions():
                    try:
                        act.setVisible(False)
                    except Exception:
                        logger.debug(
                            "TopBarLM: failed to hide search action in narrow mode",
                            exc_info=True,
                        )
            except Exception:
                logger.debug(
                    "TopBarLM: failed to iterate search actions in narrow mode",
                    exc_info=True,
                )
        # Нулевые отступы у top_bar, чтобы поиск примыкал к краям
        try:
            set_top_bar_margins(top_bar, 0, 0, 0, 0)
        except Exception:
            logger.debug(
                "TopBarLM: failed to set zero margins on top_bar (narrow mode)",
                exc_info=True,
            )
        # Поиск занимает всю ширину
        try:
            if isinstance(search, QLineEdit):
                search.setMinimumWidth(0)
                # Не ограничиваем maxWidth конкретным значением, чтобы тянулся на весь доступный размер
                search.setMaximumWidth(16777215)
                search.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    search.sizePolicy().verticalPolicy(),
                )
        except Exception:
            logger.debug(
                "TopBarLM: failed to expand search to full width (narrow mode)",
                exc_info=True,
            )
        # Пересчитать лейаут, чтобы исключить наложение
        try:
            # Зафиксировать stretch-факторы: только поиск тянется
            enforce_stretches(top_bar, search)
            top_bar.invalidate()
            host = get_container_widget()
            if isinstance(host, QWidget):
                host.updateGeometry()
                host.update()
        except Exception:
            logger.debug(
                "TopBarLM: failed to enforce stretches/update host in narrow mode",
                exc_info=True,
            )
    except Exception:
        logger.debug(
            "TopBarLayoutManager: narrow-mode hide non-search widgets failed",
            exc_info=True,
        )
