from __future__ import annotations

import logging
logger = logging.getLogger(__name__)
from contextlib import suppress
from typing import TYPE_CHECKING, Optional
import weakref

from PyQt6.QtCore import pyqtSignal, QTimer
from app.utils.ui.timings import SEARCH_RETRY_INTERVAL_MS, SEARCH_RETRY_ATTEMPTS
from PyQt6.QtGui import QKeySequence, QUndoStack, QAction
from PyQt6.QtWidgets import QMainWindow, QWidget

from app.views.link import LinksTableView

if TYPE_CHECKING:
    # Узкоспециализированные типы только для статического анализа
    from typing import Protocol, Any, Dict

    class StructureItem(Protocol):
        """Элемент структуры (дерева). Минимальный протокол для статпроверки.

        Конкретный тип в рантайме может быть `QModelIndex` или объект модели дерева.
        Здесь протокол пустой, так как `MainWindow` лишь проксирует объект дальше.
        """
        ...

    LinkDict = Dict[str, Any]
    from app.controllers.ui.links.links_actions import LinksActions
    from app.controllers.ui.menu_controller import ActionController, MenuController
    from app.controllers.ui.state.ui_state_manager import UIStateManager
    from app.controllers.ui.structure.spheres_bar_controller import SpheresBarController
    from app.controllers.ui.structure.structure_ui_controller import (
        StructureUIController,
    )
    from app.controllers.ui.theme_controller import ThemeController
    from app.controllers.ui.top_panels_controller import TopPanelsController

from app.settings import AppSettings
from app.utils.db.synchronization import signal_guard
from app.views.status_bar import update_status_bar as _update_status_bar
from app.utils.ui.updates import suspend_updates


class MainWindow(QMainWindow):
    shown: pyqtSignal = pyqtSignal()

    structure: "StructureUIController"
    menu_controller: "MenuController"
    action_controller: "ActionController"
    links_actions: "LinksActions"
    spheres_controller: "SpheresBarController"
    top_panels_controller: "TopPanelsController"
    ui_state: "UIStateManager"
    system_dialogs: object
    theme_ctrl: "ThemeController"
    table: LinksTableView
    left_panel: QWidget
    undo_stack: Optional[QUndoStack]
    # Типизированные атрибуты действий отмены/повтора, могут быть None до инициализации
    undo_action: Optional[QAction]
    redo_action: Optional[QAction]

    def handle_import_browser_bookmarks(self) -> None:
        self.system_dialogs.handle_import_browser_bookmarks()

    def get_current_category_id(self) -> Optional[int]:
        """Возвращает ID текущей категории или None до инициализации."""
        structure = getattr(self, "structure", None)
        if structure is None:
            return None
        return structure.get_current_category_id()

    def edit_structure_item(self, item: "StructureItem") -> None:
        """Редактирует элемент структуры."""
        self.structure.edit_item(item)

    def add_new_category(self) -> None:
        """Добавляет новую категорию.

        Ранее публичный метод назывался `show_category_dialog`. Он
        объединён в этот метод для устранения дублирования.
        """
        self.structure.add_new_category()

    def reload_structure(self) -> None:
        """Перезагружает структуру."""
        self.structure.load()

    def reload_current_category(self) -> None:
        """Перезагружает текущую категорию через UIStateManager."""
        category_id = self.get_current_category_id()
        if category_id:
            self.ui_state.load_category(category_id, source="reload_current_category")

    def get_link_at_row(self, row: int) -> "LinkDict | None":
        """Возвращает ссылку по номеру строки."""
        return self.links_actions.get_link_at(row)

    def select_all_links(self) -> None:
        """Выделяет все ссылки."""
        self.table.selectAll()

    def get_selected_rows(self) -> list[int]:
        """Возвращает номера выбранных строк."""
        return self.links_actions.get_selected_rows()

    def get_available_themes(self) -> list[tuple[str, str]]:
        """Возвращает список доступных тем."""
        return self.theme_ctrl.available()

    def apply_theme(self, theme_name: str) -> None:
        """Применяет тему."""
        self.theme_ctrl.apply(theme_name)

    def get_undo_stack(self) -> Optional[QUndoStack]:
        """Возвращает undo stack или None."""
        return getattr(self, "undo_stack", None)

    def create_undo_redo_actions(self) -> tuple[Optional[QAction], Optional[QAction]]:
        """Создает действия Undo/Redo."""
        us = getattr(self, "undo_stack", None)
        if us is None:
            return None, None

        undo_action = us.createUndoAction(self)
        undo_action.setText("&Отменить")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)

        redo_action = us.createRedoAction(self)
        redo_action.setText("&Повторить")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)

        us.undoTextChanged.connect(lambda *_: undo_action.setText("&Отменить"))
        us.redoTextChanged.connect(lambda *_: redo_action.setText("&Повторить"))

        self.undo_action = undo_action
        self.redo_action = redo_action

        # Диагностические логи undo/redo и состояния стека для расследования двойного вызова
        try:
            # Логируем активации действий меню/шорткатов
            undo_action.triggered.connect(
                lambda checked=False: logging.getLogger(__name__).debug(
                    "[UI] QAction.undo.triggered checked=%s", checked
                )
            )
            redo_action.triggered.connect(
                lambda checked=False: logging.getLogger(__name__).debug(
                    "[UI] QAction.redo.triggered checked=%s", checked
                )
            )
        except Exception:
            pass

        try:
            # Локальные безопасные колбэки через weakref, чтобы избежать обращения к удалённому объекту
            _us_ref = weakref.ref(us)

            def _on_index_changed(idx: int):
                u = _us_ref()
                if u is None:
                    return
                try:
                    can_undo = bool(u.canUndo())
                except RuntimeError:
                    return
                try:
                    can_redo = bool(u.canRedo())
                except RuntimeError:
                    return
                logging.getLogger(__name__).debug(
                    "[UndoStack] indexChanged=%s canUndo=%s canRedo=%s",
                    idx,
                    can_undo,
                    can_redo,
                )

            def _on_clean_changed(clean: bool):
                u = _us_ref()
                index_val = None
                if u is not None:
                    try:
                        index_val = u.index()
                    except RuntimeError:
                        index_val = None
                logging.getLogger(__name__).debug(
                    "[UndoStack] cleanChanged=%s index=%s", clean, index_val
                )

            us.indexChanged.connect(_on_index_changed)
            us.cleanChanged.connect(_on_clean_changed)
        except Exception:
            pass
        try:
            us.canUndoChanged.connect(
                lambda can: logging.getLogger(__name__).debug(
                    "[UndoStack] canUndoChanged=%s", can
                )
            )
        except Exception:
            pass
        try:
            us.canRedoChanged.connect(
                lambda can: logging.getLogger(__name__).debug(
                    "[UndoStack] canRedoChanged=%s", can
                )
            )
        except Exception:
            pass

        return undo_action, redo_action

    def __init__(self, settings: AppSettings, theme_ctrl: ThemeController):
        super().__init__()
        # Инициализация перенесена в bootstrap. Здесь только приём базовых зависимостей.
        self.settings = settings
        self.theme_ctrl = theme_ctrl

    def _init_spheres_ui(self):
        """Инициализирует UI сфер (асинхронно)."""
        self.spheres_controller.init()

    def show_link_dialog(
        self,
        link: "LinkDict | None" = None,
        category_id: int | None = None,
    ) -> bool:
        """Показывает диалог создания/редактирования ссылки."""
        selected_link_id = link.get("id") if link else None

        result = self.links_actions.show_link_dialog(link, category_id)
        self.update_statusbar()

        if result and selected_link_id:
            # Планирование восстановления выделения делегировано в LinksActions
            self.links_actions.schedule_restore_selection(selected_link_id)
        # Возвращаем результат, чтобы внешние вызовы могли узнать об успешности
        return bool(result)

    def show_link_dialog_for_category(
        self, category_id: int | None = None, link: "LinkDict | None" = None
    ) -> bool:
        """Открывает диалог ссылки для указанной категории (используется плитками категорий)."""
        return bool(self.show_link_dialog(link=link, category_id=category_id))

    def _get_selected_links(self) -> list["LinkDict"]:
        """Возвращает список выбранных ссылок."""
        return self.links_actions.get_selected_links()

    def _edit_selected_link(self) -> bool:
        """Редактирует выбранную ссылку."""
        return bool(self.links_actions.edit_selected_link())

    def edit_current(self) -> None:
        """Редактирует текущий элемент."""
        self.action_controller.edit_current()

    def delete_current(self) -> None:
        """Удаляет текущий элемент (ссылку или структурный элемент)."""
        self.action_controller.delete_current()

    def show_section_dialog(self) -> None:
        self.structure.add_new_section()

    

    def update_statusbar(self) -> None:
        _update_status_bar(self)

    def on_structure_item_added(self, item_type: str, parent_id: int, data: dict) -> None:
        self.structure.on_structure_item_added(item_type, parent_id, data)

    @signal_guard("on_structure_item_changed")
    def on_structure_item_changed(self, item_type: str, item_id: int, data: dict) -> None:
        self.structure.on_structure_item_changed(item_type, item_id, data)

    def show_about_dialog(self) -> None:
        self.system_dialogs.show_about_dialog()

    def show_settings_dialog(self) -> None:
        self.system_dialogs.show_settings_dialog()

    def show_file_search_dialog(self) -> None:
        self.system_dialogs.show_file_search_dialog()

    def update_theme(self):
        """Применяет тему и обновляет UI."""
        self.theme_ctrl.apply_and_refresh_ui()

    def update_widget_font_size(self, widget, size: int) -> None:
        """Унифицированно применяет размер шрифта к переданному виджету.

        Ожидается, что у виджета есть метод `update_font_size(int)`.
        Безопасно обрабатывает отсутствие атрибута/метода и редкие непредвиденные ошибки.

        Примечание: со временем логику можно перенести в соответствующие контроллеры
        дерева/таблицы, а здесь оставить только делегирование.
        """
        try:
            with suppress(AttributeError, RuntimeError, TypeError, ValueError):
                if widget and hasattr(widget, "update_font_size"):
                    widget.update_font_size(size)
        except Exception:
            # Лог с типом виджета для диагностики неожиданных ошибок
            logger.exception(
                "MainWindow: unexpected error updating font size for %s",
                type(widget).__name__ if widget is not None else "<None>",
            )

    def apply_font_size_to_content(self, fs: int) -> None:
        """Централизованно применяет размер шрифта к основным контент‑виджетам.

        Применяется ТОЛЬКО к дереву и таблице (пользовательская настройка).
        """
        if isinstance(fs, bool):  # защитимся от ошибок типов
            return
        try:
            size = int(fs)
        except (TypeError, ValueError):
            return

        # Дерево
        tree = getattr(self, "tree", None)
        self.update_widget_font_size(tree, size)

        # Таблица
        table = getattr(self, "table", None)
        self.update_widget_font_size(table, size)

        # Плитки категорий — намеренно НЕ меняем здесь, их шрифт независим

    @signal_guard("_update_left_panel_style")
    def _update_left_panel_style(self, sphere_id: int):
        """Обновляет стиль левой панели при смене сферы."""
        current_sphere = self.left_panel.property("sphere")
        if current_sphere == str(sphere_id):
            return

        with suspend_updates(self.left_panel):
            self.left_panel.setProperty("sphere", str(sphere_id))
            self.left_panel.style().unpolish(self.left_panel)
            self.left_panel.style().polish(self.left_panel)

    def on_search(self, text: str) -> None:
        # Сохраняем последний ввод, чтобы при поздней инициализации не потерять запрос
        self._last_search_text = text
        la = getattr(self, "links_actions", None)
        if la is None:
            # Отложенная переотправка: дадим системе инициализироваться
            if not hasattr(self, "_search_retry_attempts"):
                self._search_retry_attempts = SEARCH_RETRY_ATTEMPTS  # ~2 сек при шаге 100 мс
            if not getattr(self, "_search_retry_active", False):
                self._search_retry_active = True
                logger.debug("MainWindow.on_search buffered until links_actions is ready")
                QTimer.singleShot(SEARCH_RETRY_INTERVAL_MS, self._retry_forward_search)
            return
        try:
            la.on_search(text)
        except Exception:
            logger.exception("MainWindow.on_search failed to delegate to links_actions")

    def _retry_forward_search(self) -> None:
        try:
            la = getattr(self, "links_actions", None)
            if la is not None:
                txt = getattr(self, "_last_search_text", "")
                la.on_search(txt)
                self._search_retry_active = False
                return
            # Ещё не готово — попробуем позже, ограниченное число попыток
            attempts = getattr(self, "_search_retry_attempts", 0)
            if attempts <= 0:
                self._search_retry_active = False
                logger.debug("Search retry limit reached before links_actions initialized")
                return
            self._search_retry_attempts = attempts - 1
            QTimer.singleShot(SEARCH_RETRY_INTERVAL_MS, self._retry_forward_search)
        except Exception:
            # Негативные сценарии не должны ронять UI
            self._search_retry_active = False
            logger.exception("Unexpected error in _retry_forward_search")

    def showEvent(self, event):
        """Эмитит сигнал shown при первом показе окна."""
        super().showEvent(event)
        if not hasattr(self, "_shown_emitted"):
            self._shown_emitted = True
            # Эмитим сигнал немедленно, без искусственной задержки
            self.shown.emit()

    def closeEvent(self, event):
        """Корректно завершает работу и закрывает ресурсы."""
        if hasattr(self, "app_shutdown") and self.app_shutdown:
            self.app_shutdown.perform_shutdown(event)
            return
        super().closeEvent(event)
