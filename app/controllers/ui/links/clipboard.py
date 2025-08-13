# app/controllers/links_ui/clipboard.py

from typing import Dict, List

from app.controllers.domain.structure.commands import DeleteLinkCommand, SaveLinkCommand
from app.utils.system.clipboard_utils import copy_link_to_clipboard, get_link_from_clipboard

from .base_component import BaseLinksUIComponent
from .exceptions import CategoryNotFoundError, DatabaseError


class LinksUIClipboard(BaseLinksUIComponent):
    """Логика работы с буфером обмена для LinksUIController."""
    
    def cut_link(self):
        """Вырезать выбранные ссылки."""
        links = self.get_selected_links()
        if not links:
            return
        
        copy_link_to_clipboard(links[0] if len(links) == 1 else links)
        self.delete_links(links)
    
    def copy_link(self):
        """Копировать выбранные ссылки."""
        links = self.get_selected_links()
        if not links:
            return
        
        copy_link_to_clipboard(links[0] if len(links) == 1 else links)
    
    def paste_link(self):
        """Вставить ссылки из буфера обмена."""
        try:
            current_category_id = self._validate_category_exists(None)
        except CategoryNotFoundError as e:
            self._show_warning(str(e))
            return
        
        links = get_link_from_clipboard()
        if not links:
            return
        
        if isinstance(links, dict):
            links = [links]
        if not isinstance(links, list):
            return
        
        # Получаем существующие ссылки для проверки дубликатов
        existing_links = self.business.get_links_for_category(current_category_id)
        
        if len(links) > 1:
            with self.main.undo_stack.macro(f"Вставка {len(links)} ссылок"):
                for link in links:
                    new_data = dict(link)
                    new_data.pop("id", None)
                    new_data["category_id"] = current_category_id
                    # Проверка на дубликат
                    if not self._is_duplicate(new_data, existing_links):
                        self.main.undo_stack.push(SaveLinkCommand(new_data, None, self.main))
                        existing_links.append(new_data)
        else:
            for link in links:
                new_data = dict(link)
                new_data.pop("id", None)
                new_data["category_id"] = current_category_id
                # Проверка на дубликат
                if not self._is_duplicate(new_data, existing_links):
                    self.main.undo_stack.push(SaveLinkCommand(new_data, None, self.main))
                    existing_links.append(new_data)
    
    def delete_links(self, links: List[Dict]):
        """Удалить ссылки."""
        if not links:
            return
        
        category_id = links[0].get('category_id')
        
        if len(links) > 1:
            with self.main.undo_stack.macro(f"Удаление {len(links)} ссылок"):
                for link in links:
                    command = DeleteLinkCommand(link, self.main)
                    command._suppress_ui = True
                    self.main.undo_stack.push(command)
        else:
            for link in links:
                command = DeleteLinkCommand(link, self.main)
                command._suppress_ui = True
                self.main.undo_stack.push(command)
        
        # Обновляем отображение
        if category_id is not None:
            try:
                self._update_category_safe(category_id)
            except DatabaseError as e:
                self.logger.error(f"Failed to update category after deletion: {e}")
        if hasattr(self.main, 'fav_widget'):
            self.main.fav_widget.update_favorites()
    
    def get_selected_links(self) -> List[Dict]:
        """Получить выбранные ссылки."""
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        return [self.controller.get_link_at(row) for row in selected_rows if self.controller.get_link_at(row)]
    
    def _is_duplicate(self, candidate: Dict, links: List[Dict]) -> bool:
        """Проверить, является ли ссылка дубликатом."""
        for link in links:
            link_dict = dict(link) if not isinstance(link, dict) else link
            if (
                link_dict.get('url', '') == candidate.get('url', '') and
                link_dict.get('type', '') == candidate.get('type', '') and
                link_dict.get('args', '') == candidate.get('args', '')
            ):
                return True
        return False