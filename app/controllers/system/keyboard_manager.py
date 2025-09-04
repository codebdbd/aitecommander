# app/controllers/keyboard/keyboard_manager.py

import time
import logging
from typing import Any, Optional, TypeVar

from PyQt6.QtCore import QItemSelection, QItemSelectionModel, QObject, Qt, QTimer
from PyQt6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QWidget

from app.utils.ui.qt.roles import get_tree_tuple

logger = logging.getLogger(__name__)

# =====================
# Встроенные обработчики
# =====================
T = TypeVar("T")

# Константы для идентификации виджетов по классам/именам
WIDGET_CLASSES = {
    "STRUCTURE_TREE": "StructureTreeView",
    "LINKS_TABLE": "LinksTableView",
    "CATEGORY_TILES": "CategoryTiles",
}

WIDGET_OBJECT_NAMES = {"CATEGORY_TILES": "tiles"}


class BaseKeyHandler:
    """Базовый класс для обработчиков клавиш."""

    def __init__(self, main_window: Any) -> None:
        self.main_window = main_window

    def _is_widget_of_type(self, widget: Optional[QWidget], widget_type: str) -> bool:
        if not widget or widget_type not in WIDGET_CLASSES:
            return False
        class_name_to_check = WIDGET_CLASSES[widget_type]
        object_name_to_check = WIDGET_OBJECT_NAMES.get(widget_type)

        current = widget
        while current:
            class_name = current.__class__.__name__
            if class_name_to_check in class_name:
                return True
            if (
                object_name_to_check
                and hasattr(current, "objectName")
                and object_name_to_check in current.objectName().lower()
            ):
                return True
            current = current.parent()
        return False

    def _is_tree_focused(self, widget: Optional[QWidget]) -> bool:
        return self._is_widget_of_type(widget, "STRUCTURE_TREE")

    def _is_table_focused(self, widget: Optional[QWidget]) -> bool:
        return self._is_widget_of_type(widget, "LINKS_TABLE")

    def _is_tiles_focused(self, widget: Optional[QWidget]) -> bool:
        return self._is_widget_of_type(widget, "CATEGORY_TILES")

    def _safe_getattr(self, obj: Any, attr: str, default: T = None) -> Any:
        try:
            return getattr(obj, attr, default)
        except (AttributeError, TypeError):
            return default

    def _safe_call(
        self, obj: Any, method_name: str, *args: Any, default: T = None, **kwargs: Any
    ) -> Any:
        try:
            method = getattr(obj, method_name, None)
            if method and callable(method):
                result = method(*args, **kwargs)
                return result if result is not None else default
        except (AttributeError, TypeError) as e:
            logger.debug(f"_safe_call failed for {obj!r}.{method_name}(*args, **kwargs): {e}")
        return default


class ClipboardKeyHandler(BaseKeyHandler):
    """Обработчик клавиш буфера обмена."""

    def handle_select_all(self) -> None:
        # Контекстно: дерево -> выделить все категории раздела; таблица -> selectAll()
        focused_widget = QApplication.focusWidget()
        if self._is_tree_focused(focused_widget):
            self._handle_tree_select_all()
            return
        table = self._safe_getattr(self.main_window, "table")
        if table:
            # Эксклюзивность: при выделении в таблице снимаем выделение в дереве
            try:
                structure = self._safe_getattr(self.main_window, "structure")
                tree = self._safe_getattr(structure, "tree") if structure else None
                if tree and hasattr(tree, "clearSelection"):
                    tree.clearSelection()
            except Exception as e:
                logger.debug("ClipboardKeyHandler.handle_select_all: failed to clear tree selection", exc_info=e)
            self._safe_call(table, "selectAll")

    def _handle_tree_select_all(self) -> None:
        """Выделяет все категории текущего раздела в дереве структуры."""
        structure = self._safe_getattr(self.main_window, "structure")
        if not structure:
            return
        tree = self._safe_getattr(structure, "tree")
        if not tree:
            return
        # Эксклюзивность: при выделении в дереве снимаем выделение в таблице
        try:
            table = self._safe_getattr(self.main_window, "table")
            if table and hasattr(table, "clearSelection"):
                self._safe_call(table, "clearSelection")
        except Exception as e:
            logger.debug("ClipboardKeyHandler._handle_tree_select_all: failed to clear table selection", exc_info=e)
        # QTreeView: используем модель и selectionModel
        try:
            if hasattr(tree, "currentIndex") and callable(getattr(tree, "currentIndex")):
                idx = tree.currentIndex()
                if not (idx and idx.isValid()):
                    return
                try:
                    tt = get_tree_tuple(idx, 0)
                except Exception:
                    tt = None
                # Если выделена категория — берем её родителя (раздел), иначе предполагаем раздел
                parent_idx = idx.parent() if (tt and tt[0] == "category") else idx
                if not parent_idx or not parent_idx.isValid():
                    return
                model = tree.model() if hasattr(tree, "model") else None
                if not model:
                    return
                rows = model.rowCount(parent_idx)
                if rows <= 0:
                    return
                # Очистить текущее выделение и выделить все строки-раздела (категории)
                try:
                    sel_model = tree.selectionModel()
                    if sel_model:
                        sel_model.clearSelection()
                        top_left = model.index(0, 0, parent_idx)
                        bottom_right = model.index(rows - 1, 0, parent_idx)
                        selection = QItemSelection(top_left, bottom_right)
                        sel_model.select(
                            selection,
                            QItemSelectionModel.SelectionFlag.Select
                            | QItemSelectionModel.SelectionFlag.Rows,
                        )
                        return
                except Exception as e:
                    logger.debug("ClipboardKeyHandler._handle_tree_select_all: selection application failed", exc_info=e)
        except Exception as e:
            logger.debug("ClipboardKeyHandler._handle_tree_select_all: unexpected error", exc_info=e)


    def handle_copy(self) -> None:
        la = self._safe_getattr(self.main_window, "links_actions")
        if la:
            self._safe_call(la, "copy_selected_links")
            return
        links_controller = self._safe_getattr(self.main_window, "links")
        if links_controller:
            self._safe_call(links_controller, "copy_selected_links")

    def handle_cut(self) -> None:
        la = self._safe_getattr(self.main_window, "links_actions")
        if la:
            self._safe_call(la, "cut_selected_links")
            return
        links_controller = self._safe_getattr(self.main_window, "links")
        if links_controller:
            self._safe_call(links_controller, "cut_selected_links")

    def handle_paste(self) -> None:
        la = self._safe_getattr(self.main_window, "links_actions")
        if la:
            self._safe_call(la, "paste_links")
            return
        links_controller = self._safe_getattr(self.main_window, "links")
        if links_controller:
            self._safe_call(links_controller, "paste_links")


class EditingKeyHandler(BaseKeyHandler):
    """Обработчик клавиш редактирования."""

    def handle_key(self, event: QKeyEvent, focused_widget: Optional[QWidget]) -> bool:
        key = event.key()
        if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            return self._handle_enter_key(focused_widget)
        elif key == Qt.Key.Key_Escape:
            return self._handle_escape_key(focused_widget)
        return False

    def _handle_enter_key(self, focused_widget: Optional[QWidget]) -> bool:
        # В дереве - ничего не делаем
        if self._is_tree_focused(focused_widget):
            return False
        # В плитках - открытие категории
        elif self._is_tiles_focused(focused_widget):
            return self._handle_tiles_enter()
        # В таблице - открытие ссылки
        elif self._is_table_focused(focused_widget):
            return self._handle_table_enter()
        return False

    def _handle_escape_key(self, focused_widget: Optional[QWidget]) -> bool:
        # В плитках - очистка фильтра
        if self._is_tiles_focused(focused_widget):
            return self._handle_tiles_escape()
        # Глобально - очистка поиска
        return self._handle_global_escape()

    def _handle_table_enter(self) -> bool:
        table = self._safe_getattr(self.main_window, "table")
        if not table:
            return False
        # Для QTableView: используем текущий индекс и размер модели
        try:
            idx = table.currentIndex() if hasattr(table, "currentIndex") else None
            current_row = idx.row() if idx and idx.isValid() else -1
        except Exception as e:
            logger.debug("EditingKeyHandler._handle_table_enter: failed to read current index", exc_info=e)
            current_row = -1
        try:
            model = table.model() if hasattr(table, "model") else None
            row_count = model.rowCount() if model else 0
        except Exception as e:
            logger.debug("EditingKeyHandler._handle_table_enter: failed to read row count", exc_info=e)
            row_count = 0

        if 0 <= current_row < row_count:
            # get_link_at(row) унифицировано для QTableView и возвращает dict
            link = self._safe_call(table, "get_link_at", current_row)
            if link:
                la = self._safe_getattr(self.main_window, "links_actions")
                if la:
                    self._safe_call(la, "open_link", link)
                    return True
                links = self._safe_getattr(self.main_window, "links")
                if links:
                    link_ops = self._safe_getattr(links, "link_ops")
                    if link_ops:
                        self._safe_call(link_ops, "_open_link", link)
                        return True
        return False

    def _handle_tiles_enter(self) -> bool:
        tiles = self._safe_getattr(self.main_window, "tiles")
        if not tiles:
            return False
        list_widget = self._safe_getattr(tiles, "list_widget")
        if list_widget:
            current_item = self._safe_call(list_widget, "currentItem")
            if current_item:
                result = self._safe_call(
                    tiles, "_on_item_clicked", current_item, default=False
                )
                return bool(result)
        return False

    def _handle_tiles_escape(self) -> bool:
        tiles = self._safe_getattr(self.main_window, "tiles")
        if tiles:
            filter_text = self._safe_getattr(tiles, "_filter_text")
            if filter_text:
                result = self._safe_call(tiles, "clear_filter", default=False)
                return bool(result)
        return False

    def _handle_global_escape(self) -> bool:
        search = self._safe_getattr(self.main_window, "search")
        if search and self._safe_call(search, "text", default=""):
            self._safe_call(search, "clear")
            return True
        return False

    def handle_show_note(self) -> None:
        la = self._safe_getattr(self.main_window, "links_actions")
        if la:
            selected_links = self._safe_call(la, "get_selected_links")
            if selected_links:
                self._safe_call(la, "show_note_dialog", selected_links[0])
            return
        links = self._safe_getattr(self.main_window, "links")
        if links:
            selected_links = self._safe_call(links, "get_selected_links")
            if selected_links:
                self._safe_call(links, "show_note_dialog", selected_links[0])

    def handle_toggle_favorite(self) -> None:
        la = self._safe_getattr(self.main_window, "links_actions")
        if la:
            selected_links = self._safe_call(la, "get_selected_links")
            if selected_links:
                self._safe_call(la, "toggle_link_favorite", selected_links[0])
            return
        links = self._safe_getattr(self.main_window, "links")
        if links:
            selected_links = self._safe_call(links, "get_selected_links")
            if selected_links:
                self._safe_call(
                    self.main_window, "toggle_link_favorite", selected_links[0]
                )


class GlobalKeyHandler(BaseKeyHandler):
    """Обработчик глобальных горячих клавиш."""

    def handle_f1(self) -> None:
        self._safe_call(self.main_window, "show_link_dialog")

    def handle_f2(self) -> None:
        self._safe_call(self.main_window, "edit_current")

    def handle_f3(self) -> None:
        self._safe_call(self.main_window, "show_section_dialog")

    def handle_f4(self) -> None:
        # Добавление категории (ранее метод назывался show_category_dialog)
        self._safe_call(self.main_window, "add_new_category")

    def handle_f6(self) -> None:
        action = self._safe_getattr(self.main_window, "switch_sphere_action")
        if action:
            self._safe_call(action, "trigger")

    def handle_delete(self) -> None:
        self._safe_call(self.main_window, "delete_current")


class SearchKeyHandler(BaseKeyHandler):
    """Обработчик клавиш поиска."""

    SEARCH_TIMEOUT = 1000

    def __init__(self, main_window: Any) -> None:
        super().__init__(main_window)
        self._search_text: str = ""
        self._search_timer: QTimer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._reset_search)

    def handle_focus_search(self) -> None:
        search = self._safe_getattr(self.main_window, "search")
        if search:
            self._safe_call(search, "setFocus")

    def handle_clear_search(self) -> None:
        search = self._safe_getattr(self.main_window, "search")
        if search:
            self._safe_call(search, "clear")

    def handle_quick_search(
        self, event: QKeyEvent, focused_widget: Optional[QWidget]
    ) -> bool:
        if not self._is_tiles_focused(focused_widget):
            return False
        char = event.text().lower()
        self._search_timer.stop()
        self._search_text += char
        self._search_timer.start(self.SEARCH_TIMEOUT)
        tiles = self._safe_getattr(self.main_window, "tiles")
        if tiles:
            result = self._safe_call(
                tiles, "_quick_search", self._search_text, default=False
            )
            return bool(result)
        return False

    def _reset_search(self) -> None:
        self._search_text = ""


class KeyboardManager(QObject):
    """Централизованный менеджер горячих клавиш."""

    ENTER_COOLDOWN = 150

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.shortcuts = []

        self.global_handler = GlobalKeyHandler(main_window)
        self.editing_handler = EditingKeyHandler(main_window)
        self.clipboard_handler = ClipboardKeyHandler(main_window)
        self.search_handler = SearchKeyHandler(main_window)

        self._last_enter_time = 0

        self.main_window.installEventFilter(self)
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        """Настройка QShortcut для комбинаций клавиш."""

        global_shortcuts = [
            ("F1", self.global_handler.handle_f1),
            ("F2", self.global_handler.handle_f2),
            ("F3", self.global_handler.handle_f3),
            ("F4", self.global_handler.handle_f4),
            ("F6", self.global_handler.handle_f6),
            ("Del", self.global_handler.handle_delete),
        ]

        for key_seq, handler in global_shortcuts:
            shortcut = QShortcut(QKeySequence(key_seq), self.main_window)
            shortcut.activated.connect(handler)
            self.shortcuts.append(shortcut)

        table_shortcuts = [
            ("Ctrl+A", self.clipboard_handler.handle_select_all),
            ("Ctrl+F", self.search_handler.handle_focus_search),
            ("Escape", self.search_handler.handle_clear_search),
            ("Ctrl+X", self.clipboard_handler.handle_cut),
            ("Ctrl+C", self.clipboard_handler.handle_copy),
            ("Ctrl+V", self.clipboard_handler.handle_paste),
            ("Ctrl+N", self.editing_handler.handle_show_note),
            ("Ctrl+D", self.editing_handler.handle_toggle_favorite),
        ]

        # Регистрируем на главном окне, чтобы сработало даже если table ещё не создан
        for key_seq, handler in table_shortcuts:
            shortcut = QShortcut(QKeySequence(key_seq), self.main_window)
            # Область действия: на виджете и его детях (таблица внутри окна)
            try:
                shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            except Exception as e:
                # На случай несовместимости — оставим контекст по умолчанию
                logger.debug("KeyboardManager._setup_shortcuts: setContext not supported", exc_info=e)
            shortcut.activated.connect(handler)
            self.shortcuts.append(shortcut)

    def eventFilter(self, obj, event):
        """Фильтр событий для перехвата клавиш."""
        if event.type() == event.Type.KeyPress:
            if self._is_enter_duplicate(event):
                return True

            focused_widget = QApplication.focusWidget()

            if self._handle_editing_keys(event, focused_widget):
                return True
            elif self._handle_search_keys(event, focused_widget):
                return True

        return super().eventFilter(obj, event)

    def _is_enter_duplicate(self, event):
        """Проверка на двойное нажатие Enter."""
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            current_time = int(time.time() * 1000)

            if current_time - self._last_enter_time < self.ENTER_COOLDOWN:
                return True

            self._last_enter_time = current_time

        return False

    def _handle_editing_keys(self, event, focused_widget):
        """Обработка клавиш редактирования."""
        key = event.key()

        if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape):
            return self.editing_handler.handle_key(event, focused_widget)

        return False

    def _handle_search_keys(self, event, focused_widget):
        """Обработка клавиш поиска."""
        if (
            event.text().isalnum()
            and len(event.text()) == 1
            and self.search_handler._is_tiles_focused(focused_widget)
        ):
            return self.search_handler.handle_quick_search(event, focused_widget)

        return False

    def cleanup(self):
        """Очистка ресурсов."""
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts.clear()

        # Удаляем фильтр событий
        self.main_window.removeEventFilter(self)
