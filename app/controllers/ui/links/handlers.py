import logging
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu

from app.controllers.domain.structure.commands import SaveLinkCommand

from .base_component import BaseLinksUIComponent
from .exceptions import DatabaseError, LinksUIError


class LinksUIHandlers(BaseLinksUIComponent):
    """Обработчики событий для LinksUIController."""
    
    def _connect_signals(self):
        """Подключение сигналов от бизнес-логики."""
        self.business.links_loaded.connect(self._update_table)
        self.business.search_results_ready.connect(self._update_search_results)
        self.business.favorites_counted.connect(self._complete_toggle_fav)
        self.business.link_updated.connect(self._on_link_updated)
        self.business.error_occurred.connect(self._handle_error)
    
    def _connect_table_signals(self):
        """Подключение сигналов от таблицы."""
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)

        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.links_reordered.connect(self._on_links_reordered)
        
        # Обработка клавиш теперь централизована в KeyboardManager
    
    def _update_table(self, links: List[Dict], category_id: int, task_id: int):
        """Обновляет таблицу ссылок новыми данными."""
        # Защита от рассинхронизации: принимаем только ссылки для текущей категории
        current_category_id = getattr(self.main, 'current_category_id', None)
        if current_category_id is not None and category_id != current_category_id:
            # Например, пользователь успел переключить категорию, пока грузились ссылки
            self.logger.info(
                "Пропуск обновления таблицы: загружены ссылки для категории %s (task_id=%s), "
                "но текущая категория = %s",
                category_id, task_id, current_category_id
            )
            return
        
        self.table.populate(links)
    
    def _update_search_results(self, search_results: List[Dict]):
        """Обновить результаты поиска."""
        self.table.populate(search_results, mode="search")
    
    def _complete_toggle_fav(self, fav_count: int, links: List[Dict], link: Optional[Dict]):
        """Завершить переключение избранного."""
        if link is not None:
            current_favorite_status = link.get("is_favorite", False)
        else:
            logging.warning("_complete_toggle_fav called without specific link, skipping to prevent infinite loop")
    
    def _handle_error(self, error_msg: str):
        """Обработать ошибку."""
        self.logger.error(f"LinksUIController error: {error_msg}")
        self._show_error(f"An error occurred: {error_msg}")
    
    def _on_link_updated(self, updated_link: Dict):
        """Обработка обновления ссылки."""
        link_id = updated_link.get('id')
        link_name = updated_link.get('name', 'Untitled')
        is_favorite = updated_link.get('is_favorite', False)
        
        if hasattr(self.table, 'update_link_by_id'):
            self.table.update_link_by_id(updated_link)
        if hasattr(self.main, 'fav_widget'):
            self.main.fav_widget.update_favorites()
    
    
    def _on_double_click(self, row: int, column: int):
        """Обработка двойного клика по строке."""
        link = self.controller.get_link_at(row)
        if not link:
            self.logger.warning(f"No link found at row {row}")
            return

        if column == self.COLUMNS['notes']:
            self.controller.show_note_dialog(link)
        else:
            self.controller.open_link(link)
    
    def _on_cell_clicked(self, row: int, column: int):
        """Обработка клика по ячейке."""
        link = self.controller.get_link_at(row)
        if not link:
            self.logger.warning(f"No link found at row {row}")
            return
            
        if column == self.COLUMNS['favorite']:
            link_id = link.get('id')
            link_name = link.get('name', 'Untitled')
            current_fav_status = link.get('is_favorite', False)
            
            name_item = self.table.item(row, self.COLUMNS['name'])
            visible_name = name_item.text() if name_item else "Unknown"
            
            if link_name != visible_name:
                self.logger.warning(f"MISMATCH! Link data does not match visible content!")
                self.logger.warning(f"  - Expected: '{visible_name}'")
                self.logger.warning(f"  - Received: '{link_name}'")
            
            self.controller.toggle_favorite(link)
    
    def _on_context_menu(self, pos):
        """Обработка контекстного меню."""
        idx = self.table.indexAt(pos)
        
        menu = self.main.menu_controller.create_links_context_menu(
            self.table,
            idx,
            self.controller.clipboard.paste_link
        )
        if menu:
            menu.exec(self.table.mapToGlobal(pos))
    
    # Метод _handle_key_press удален - обработка клавиш централизована в KeyboardManager
    
    def _on_links_reordered(self, link_ids: list):
        """Обработка изменения порядка ссылок."""
        self.business.update_link_order(link_ids)