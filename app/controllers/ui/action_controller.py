"""Контроллер для обработки пользовательских действий (редактирование, удаление, буфер обмена и т.д.)."""

import logging
from typing import TYPE_CHECKING

from app.config_data import app_config

if TYPE_CHECKING:
    from app.views.main_window import MainWindow

logger = logging.getLogger(__name__)


class ActionController:
    """Контроллер для обработки пользовательских действий."""

    def __init__(self, main_window: "MainWindow"):
        self.main_window = main_window
        # Явные зависимости: проверяем наличие ключевых атрибутов UI
        missing = []
        for attr in ("tree", "links_actions", "table"):
            if not hasattr(self.main_window, attr):
                missing.append(attr)
        if missing:
            raise ValueError(
                f"ActionController: отсутствуют обязательные зависимости в main_window: {', '.join(missing)}"
            )

    # --- Helpers: focus/selection/context ---
    def _has_tree_selection(self) -> bool:
        tree = self.main_window.tree
        if not hasattr(tree, "currentIndex"):
            raise ValueError("ActionController: 'tree' не поддерживает currentIndex()")
        index = tree.currentIndex()
        return bool(hasattr(index, "isValid") and index.isValid())

    def _is_tree_focused(self) -> bool:
        tree = self.main_window.tree
        if not hasattr(tree, "hasFocus"):
            raise ValueError("ActionController: 'tree' не поддерживает hasFocus()")
        fw = self.main_window.focusWidget()
        in_tree = tree.hasFocus()
        if hasattr(tree, "isAncestorOf"):
            in_tree = in_tree or tree.isAncestorOf(fw)
        return bool(in_tree)

    def _table_has_selection(self) -> bool:
        la = self.main_window.links_actions
        if not hasattr(la, "get_selected_rows"):
            raise ValueError("ActionController: 'links_actions' не поддерживает get_selected_rows()")
        return bool(la.get_selected_rows())

    def _is_table_focused(self) -> bool:
        table = self.main_window.table
        if not hasattr(table, "hasFocus"):
            raise ValueError("ActionController: 'table' не поддерживает hasFocus()")
        fw = self.main_window.focusWidget()
        in_table = table.hasFocus()
        if hasattr(table, "isAncestorOf"):
            in_table = in_table or table.isAncestorOf(fw)
        return bool(in_table)

    def _is_table_stack_active(self) -> bool:
        table_stack_index = app_config.ui.get_stack_index_table()
        stack = getattr(self.main_window, "stack", None)
        if stack is None:
            raise ValueError("ActionController: отсутствует зависимость 'stack'")
        if not hasattr(stack, "currentIndex"):
            raise ValueError("ActionController: 'stack' не поддерживает currentIndex()")
        return bool(stack.currentIndex() == table_stack_index)

    def _selected_links(self):
        la = self.main_window.links_actions
        if not hasattr(la, "get_selected_links"):
            raise ValueError("ActionController: 'links_actions' не поддерживает get_selected_links()")
        return la.get_selected_links()

    def edit_current(self):
        """Определить контекст и выполнить редактирование текущего элемента."""
        # Проверяем плитки категорий
        tiles_stack_index = app_config.ui.get_stack_index_tiles()
        stack = getattr(self.main_window, "stack", None)
        tiles = getattr(self.main_window, "tiles", None)
        if (
            stack is not None
            and tiles is not None
            and stack.currentIndex() == tiles_stack_index
            and hasattr(tiles, "_current_item_id")
            and tiles._current_item_id is not None
        ):
            self.main_window.structure.handle_edit_category(tiles._current_item_id)
            return

        # Проверяем таблицу ссылок (активная)
        if self._is_table_stack_active() and self._table_has_selection():
            self._edit_selected_link()
            return

        # Проверяем фокус на дереве структуры (QTreeView-only)
        if self._is_tree_focused() and self._has_tree_selection():
            self.main_window.structure.edit_selected_item()
            return

        # Проверяем фокус на таблице ссылок
        if self._is_table_focused() and self._table_has_selection():
            self._edit_selected_link()
            return

        # Fallback: проверяем наличие выбранного элемента в дереве (QTreeView-only)
        if self._has_tree_selection():
            self.main_window.structure.edit_selected_item()
            return

        # Fallback: проверяем наличие выбранной ссылки
        if self._table_has_selection():
            self._edit_selected_link()

    def delete_current(self):
        """Определить контекст и выполнить удаление текущего элемента."""
        # Проверяем фокус на таблице ссылок
        if self._is_table_focused() and self._table_has_selection():
            links = self._selected_links()
            if links:
                self.main_window.links_actions.delete_links_with_confirmation(links)
                self.main_window.update_statusbar()
            return

        # Проверяем фокус на дереве структуры (QTreeView-only)
        if self._is_tree_focused() and self._has_tree_selection():
            self.main_window.structure.delete_selected_item()
            self.main_window.update_statusbar()
            return

        # Fallback: проверяем наличие выбранных ссылок
        if self._table_has_selection():
            links = self._selected_links()
            if links:
                self.main_window.links_actions.delete_links_with_confirmation(links)
                self.main_window.update_statusbar()
            return

        # Fallback: проверяем наличие выбранного элемента в дереве (QTreeView-only)
        if self._has_tree_selection():
            self.main_window.structure.delete_selected_item()
            self.main_window.update_statusbar()

    def copy_current(self):
        """Копировать выбранные элементы."""
        if bool(self.main_window.links_actions.get_selected_rows()):
            self.main_window.links_actions.copy_selected_links()

    def cut_current(self):
        """Вырезать выбранные элементы."""
        if bool(self.main_window.links_actions.get_selected_rows()):
            self.main_window.links_actions.cut_selected_links()

    def paste_current(self):
        """Вставить элементы."""
        self.main_window.links_actions.paste_links()

    def select_all_current(self):
        """Выделить все элементы в текущем контексте."""
        if self.main_window.table.hasFocus():
            self.main_window.select_all_links()

    def _edit_selected_link(self):
        """Редактировать выбранную ссылку."""
        if self.main_window.links_actions.edit_selected_link():
            return

    def _get_selected_links(self):
        """Получить список выбранных ссылок через фасад LinksActions."""
        la = self.main_window.links_actions
        if not hasattr(la, "get_selected_links"):
            raise ValueError("ActionController: 'links_actions' не поддерживает get_selected_links()")
        return la.get_selected_links()
