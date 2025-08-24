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

    def edit_current(self):
        """Определить контекст и выполнить редактирование текущего элемента."""
        # Проверяем плитки категорий
        tiles_stack_index = app_config.get("ui.stack_indices.tiles", 0)
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
        table_stack_index = app_config.get("ui.stack_indices.table", 1)
        if (
            stack is not None
            and stack.currentIndex() == table_stack_index
            and bool(self.main_window.links_actions.get_selected_rows())
        ):
            self._edit_selected_link()
            return

        # Проверяем фокус на дереве структуры
        if self.main_window.tree.hasFocus() and self.main_window.tree.currentItem():
            self.main_window.structure.edit_selected_item()
            return

        # Проверяем фокус на таблице ссылок
        if self.main_window.table.hasFocus() and bool(
            self.main_window.links_actions.get_selected_rows()
        ):
            self._edit_selected_link()
            return

        # Fallback: проверяем наличие выбранного элемента в дереве
        if self.main_window.tree.currentItem():
            self.main_window.structure.edit_selected_item()
            return

        # Fallback: проверяем наличие выбранной ссылки
        if bool(self.main_window.links_actions.get_selected_rows()):
            self._edit_selected_link()

    def delete_current(self):
        """Определить контекст и выполнить удаление текущего элемента."""
        # Проверяем фокус на таблице ссылок
        if (
            self.main_window.table.hasFocus()
            or self.main_window.table.isAncestorOf(self.main_window.focusWidget())
        ) and bool(self.main_window.links_actions.get_selected_rows()):
            links = self._get_selected_links()
            if links:
                self.main_window.links_actions.delete_links_with_confirmation(links)
                self.main_window.update_statusbar()
            return

        # Проверяем фокус на дереве структуры
        if (
            self.main_window.tree.hasFocus()
            or self.main_window.tree.isAncestorOf(self.main_window.focusWidget())
        ) and self.main_window.tree.currentItem():
            self.main_window.structure.delete_selected_item()
            self.main_window.update_statusbar()
            return

        # Fallback: проверяем наличие выбранных ссылок
        if bool(self.main_window.links_actions.get_selected_rows()):
            links = self._get_selected_links()
            if links:
                self.main_window.links_actions.delete_links_with_confirmation(links)
                self.main_window.update_statusbar()
            return

        # Fallback: проверяем наличие выбранного элемента в дереве
        if self.main_window.tree.currentItem():
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
        """Получить список выбранных ссылок."""
        selected_rows = self.main_window.get_selected_rows()
        links = []
        for row in selected_rows:
            link = self.main_window.get_link_at_row(row)
            if link:
                links.append(link)
        return links
