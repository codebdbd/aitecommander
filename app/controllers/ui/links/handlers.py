import logging
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu

from app.controllers.domain.structure.commands import SaveLinkCommand
from app.utils.ui.dnd.commands import AddLinksCommand
from app.utils.links.url_detect import normalize_to_url, detect_link_type, suggest_name

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
        # Внешний дроп из ОС (файлы/URL/текст)
        if hasattr(self.table, 'external_os_drop'):
            try:
                self.table.external_os_drop.connect(self._on_external_os_drop)
            except Exception as e:
                self.logger.warning(f"Не удалось подключить обработчик external_os_drop: {e}")
        
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
        # 1) Если нам передали конкретную ссылку — обновляем строку таблицы
        if link is not None:
            try:
                # Обновить отображение строки, если таблица поддерживает точечное обновление
                if hasattr(self.table, 'update_link_by_id'):
                    self.table.update_link_by_id(link)
            except Exception as e:
                self.logger.warning(f"Failed to update table row for toggled favorite: {e}")
        else:
            # Бывают случаи вызова без конкретной ссылки — не выходим молча
            self.logger.warning("_complete_toggle_fav called without specific link; proceeding with favorites refresh only")

        # 2) В любом случае обновляем панель избранного, чтобы пересчитать список/счетчик
        try:
            if hasattr(self.main, 'fav_widget') and self.main.fav_widget:
                self.main.fav_widget.update_favorites()
        except Exception as e:
            self.logger.warning(f"Failed to refresh favorites widget after toggle: {e}")
    
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

    def _on_external_os_drop(self, strings: list):
        """Обработка внешнего дропа в таблицу ссылок (Windows Explorer/браузер)."""
        try:
            self.logger.debug("[DnD][UI] external_os_drop received: %d items; sample=%s",
                              len(strings), strings[:3])
        except Exception:
            pass
        if not strings:
            return
        main = getattr(self, 'main', None)
        category_id = getattr(main, 'current_category_id', None)
        if not isinstance(category_id, int):
            self.logger.warning("_on_external_os_drop: неизвестная текущая категория")
            return

        payload = []
        for s in strings:
            try:
                url = normalize_to_url(s)
                if not url:
                    continue
                typ = detect_link_type(url)
                name = suggest_name(url)
                payload.append({
                    'name': name,
                    'url': url,
                    'type': typ,
                    'category_id': int(category_id),
                })
            except Exception as e:
                self.logger.debug(f"Пропуск элемента дропа '{s}': {e}")

        if not payload:
            self.logger.debug("[DnD][UI] external_os_drop: пустой payload после нормализации")
            return
        try:
            self.logger.debug("[DnD][UI] external_os_drop: prepared payload: %d items; cat=%s; sample=%s",
                              len(payload), category_id,
                              [{k: v for k, v in payload[0].items() if k in ('name','url','type')}] if payload else [])
        except Exception:
            pass

        # Пушим команду добавления ссылок с поддержкой undo/redo
        try:
            if hasattr(main, 'undo_stack') and main.undo_stack:
                self.logger.debug("[DnD][UI] Using undo_stack to push AddLinksCommand")
                main.undo_stack.push(AddLinksCommand(payload, int(category_id), main))
            else:
                # Fallback: прямое добавление через бизнес-логику (без undo/redo)
                self.logger.warning("Undo stack недоступен. Добавление ссылок без истории.")
                for item in payload:
                    try:
                        self.business.save_link(item)
                    except Exception as e:
                        self.logger.error(f"Ошибка добавления ссылки без undo: {e}")
                # Обновим UI для текущей категории
                try:
                    if hasattr(main, 'ui_state') and main.ui_state:
                        main.ui_state.update_category_without_stack_switch(int(category_id))
                except Exception:
                    pass
        except Exception as e:
            self.logger.error(f"Ошибка при обработке внешнего дропа: {e}")