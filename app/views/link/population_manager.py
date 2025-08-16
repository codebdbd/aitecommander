# Модуль для заполнения и обновления таблицы ссылок
# Содержит методы массового обновления данных таблицы

import logging
from typing import Dict, List

from PyQt6.QtCore import Qt


class PopulationManagerMixin:
    """Миксин для заполнения и обновления таблицы ссылок."""
    
    def populate(self, links: List[Dict], mode: str = "normal"):
        """Заполняет таблицу данными ссылок с инкрементальным обновлением."""
        if not isinstance(links, list):
            logging.warning(f"[LinksTableView] Ожидался список ссылок, получен {type(links)}")
            return

        # Оптимизация: отключаем обновление UI при массовых изменениях
        self.setUpdatesEnabled(False)
        
        try:
            # Сохраняем состояние UI
            current_selection = [item.row() for item in self.selectedItems()]
            current_scroll_pos = self.verticalScrollBar().value()
            
            # Сохраняем текущую сортировку
            header = self.horizontalHeader()
            sort_col, sort_order = header.sortIndicatorSection(), header.sortIndicatorOrder()
            was_sorting_enabled = self.isSortingEnabled()

            # Если режим изменился, делаем полное обновление
            if mode != self._current_mode:
                self._current_mode = mode
                self._full_populate(links, mode)
                self._restore_ui_state(current_selection, current_scroll_pos, sort_col, sort_order)
                return

            # Инкрементальное обновление
            try:
                self.blockSignals(True)
                self.horizontalHeader().blockSignals(True)

                # Если нет активной сортировки и изменился порядок ID, проще и безопаснее сделать полное обновление
                def _ids_from_table() -> List:
                    ids = []
                    for row in range(self.rowCount()):
                        data = self.get_link_at(row)
                        if data and 'id' in data:
                            ids.append(data['id'])
                    return ids

                current_order = _ids_from_table()
                new_order = [link.get('id') for link in links if link and 'id' in link]
                if (sort_col == -1) and current_order and (current_order != new_order):
                    logging.info("[LinksTableView] Обнаружено изменение порядка ID без активной сортировки — выполняем полное обновление")
                    self._full_populate(links, mode)
                    return

                current_ids = self._get_current_link_ids()
                new_ids = self._get_new_link_ids(links)
                new_link_map = self._create_link_id_to_data_map(links)
                
                # Находим изменения
                ids_to_remove = set(current_ids) - set(new_ids)
                ids_to_add = set(new_ids) - set(current_ids)
                ids_to_check = set(current_ids) & set(new_ids)
                
                # ВАЖНО: на время модификаций отключаем сортировку, чтобы индексы строк не "плавали"
                self.setSortingEnabled(False)

                # Удаляем исчезнувшие ссылки (в обратном порядке)
                rows_to_remove = []
                for row in range(self.rowCount()):
                    data = self.get_link_at(row)
                    if data and data.get('id') in ids_to_remove:
                        rows_to_remove.append(row)
                
                # Сортируем индексы в обратном порядке для корректного удаления
                for row in sorted(rows_to_remove, reverse=True):
                    self._remove_row(row)
                
                # Обновляем изменившиеся ссылки
                for row in range(self.rowCount()):
                    current_link = self.get_link_at(row)
                    if not current_link:
                        continue
                    link_id = current_link.get('id')
                    if link_id not in ids_to_check:
                        continue
                    new_link = new_link_map.get(link_id)
                    if new_link and not self._links_equal(current_link, new_link, mode):
                        self._update_row(row, new_link, mode)
                
                # Добавляем новые ссылки
                if ids_to_add:
                    # Находим позицию для вставки каждой новой ссылки
                    for i, link in enumerate(links):
                        link_id = link.get('id')
                        if link_id in ids_to_add:
                            # Ищем правильную позицию для вставки
                            # Если есть активная сортировка, добавляем в конец и затем сортировка восстановится
                            target_row = self.rowCount() if sort_col != -1 else min(i, self.rowCount())
                            self._add_row(target_row, link, mode)

                # Восстанавливаем сортировку, если она была включена
                self.setSortingEnabled(was_sorting_enabled)
                if was_sorting_enabled and sort_col != -1 and sort_col < self.columnCount():
                    self.sortItems(sort_col, sort_order)
                
            except Exception as e:
                logging.error(f"[LinksTableView] Ошибка при инкрементальном обновлении: {e}")
                # В случае ошибки делаем полное обновление
                self._full_populate(links, mode)
            finally:
                self.horizontalHeader().blockSignals(False)
                self.blockSignals(False)
                self._restore_ui_state(current_selection, current_scroll_pos, sort_col, sort_order)
        finally:
            # Всегда включаем обновление UI в конце
            self.setUpdatesEnabled(True)
            self.viewport().update()

    def _full_populate(self, links: List[Dict], mode: str):
        """Выполняет полное обновление таблицы (fallback)."""
        try:
            # На время полного обновления отключаем сортировку
            header = self.horizontalHeader()
            sort_col, sort_order = header.sortIndicatorSection(), header.sortIndicatorOrder()
            was_sorting_enabled = self.isSortingEnabled()
            self.setSortingEnabled(False)

            self.clearContents()
            self.setRowCount(len(links))
            self.verticalHeader().setVisible(False)
            
            # Заполняем строки
            for row_idx, link in enumerate(links):
                row_items = self.build_row(link, mode=mode)
                if not row_items:
                    continue
                
                for col_idx, item in enumerate(row_items):
                    self.setItem(row_idx, col_idx, item)
            
            # Восстанавливаем сортировку
            self.setSortingEnabled(was_sorting_enabled)
            if was_sorting_enabled and sort_col != -1 and sort_col < self.columnCount():
                self.sortItems(sort_col, sort_order)
            
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка при полном обновлении таблицы: {e}")

    def _restore_ui_state(self, selection: List[int], scroll_pos: int, sort_col: int, sort_order: Qt.SortOrder):
        # Обновляем состояние сортировки
        self._sort_col = sort_col
        self._sort_order = sort_order
        """Восстанавливает состояние UI после обновления."""
        try:
            # Восстанавливаем сортировку
            if sort_col != -1 and sort_col < self.columnCount():
                self.sortItems(sort_col, sort_order)
            
            # Убрано автоматическое восстановление выделения строк
            # для стандартного поведения Qt без принудительного выбора
            
            # Восстанавливаем позицию скролла
            self.verticalScrollBar().setValue(scroll_pos)
            
            self.viewport().update()
            
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка восстановления UI состояния: {e}")
