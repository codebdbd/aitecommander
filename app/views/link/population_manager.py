# Модуль для заполнения и обновления таблицы ссылок
# Содержит методы массового обновления данных таблицы

import logging
import time
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
            t0 = time.perf_counter()
            # Сохраняем состояние UI
            try:
                sel_model = self.selectionModel()
                current_selection = [idx.row() for idx in sel_model.selectedRows()] if sel_model else []
            except Exception:
                current_selection = []
            current_scroll_pos = self.verticalScrollBar().value()
            
            # Сохраняем текущую сортировку
            header = self.horizontalHeader()
            sort_col, sort_order = header.sortIndicatorSection(), header.sortIndicatorOrder()

            # Если режим изменился, делаем полное обновление
            if mode != self._current_mode:
                self._current_mode = mode
                t_full0 = time.perf_counter()
                self._full_populate(links, mode)
                self._restore_ui_state(current_selection, current_scroll_pos, sort_col, sort_order)
                t_full1 = time.perf_counter()
                logging.info(f"populate(mode change) total={ (t_full1 - t0)*1000:.1f} ms, full_populate={ (t_full1 - t_full0)*1000:.1f} ms")
                return

            # Инкрементальное обновление
            try:
                t_inc0 = time.perf_counter()
                self.blockSignals(True)
                self.horizontalHeader().blockSignals(True)
                # Гарантируем корректность кэша перед диффом
                t_cache0 = time.perf_counter()
                cache_ok = self.validate_cache_integrity()
                if not cache_ok:
                    self.rebuild_cache_from_items()
                t_cache1 = time.perf_counter()
                
                # Если нет активной сортировки и изменился порядок ID, проще и безопаснее сделать полное обновление
                def _ids_from_table() -> List:
                    ids = []
                    model = self.model()
                    row_count = model.rowCount() if model is not None else 0
                    for row in range(row_count):
                        data = self.get_link_at(row)
                        if data and 'id' in data:
                            ids.append(data['id'])
                    return ids

                t_ids0 = time.perf_counter()
                current_order = _ids_from_table()
                new_order = [link.get('id') for link in links if link and 'id' in link]
                t_ids1 = time.perf_counter()
                if (sort_col == -1) and current_order and (current_order != new_order):
                    logging.info("[LinksTableView] Обнаружено изменение порядка ID без активной сортировки — выполняем полное обновление")
                    t_full2 = time.perf_counter()
                    self._full_populate(links, mode)
                    t_full3 = time.perf_counter()
                    logging.info(f"populate(reorder) total={ (t_full3 - t0)*1000:.1f} ms, cache={ (t_cache1 - t_cache0)*1000:.1f} ms, ids={ (t_ids1 - t_ids0)*1000:.1f} ms, full={ (t_full3 - t_full2)*1000:.1f} ms")
                    return

                t_diff0 = time.perf_counter()
                current_ids = self._get_current_link_ids()
                new_ids = self._get_new_link_ids(links)
                new_link_map = self._create_link_id_to_data_map(links)
                
                # Находим изменения
                ids_to_remove = current_ids - new_ids
                ids_to_add = new_ids - current_ids
                ids_to_check = current_ids & new_ids
                t_diff1 = time.perf_counter()
                
                # Удаляем исчезнувшие ссылки (в обратном порядке)
                t_remove0 = time.perf_counter()
                rows_to_remove = []
                # Создаем копию кэша для итерации, чтобы избежать проблем при изменении кэша во время итерации
                current_links_copy = self._current_links.copy()
                for row, link in current_links_copy.items():
                    if link and link.get('id') in ids_to_remove:
                        rows_to_remove.append(row)
                
                # Сортируем индексы в обратном порядке для корректного удаления
                for row in sorted(rows_to_remove, reverse=True):
                    self._remove_row(row)
                t_remove1 = time.perf_counter()
                
                # Обновляем изменившиеся ссылки
                t_update0 = time.perf_counter()
                for row, current_link in list(self._current_links.items()):
                    if not current_link or current_link.get('id') not in ids_to_check:
                        continue
                        
                    link_id = current_link.get('id')
                    new_link = new_link_map.get(link_id)
                    
                    if new_link and not self._links_equal(current_link, new_link, mode):
                        self._update_row(row, new_link, mode)
                t_update1 = time.perf_counter()
                
                # Добавляем новые ссылки
                if ids_to_add:
                    t_add0 = time.perf_counter()
                    # Находим позицию для вставки каждой новой ссылки
                    for i, link in enumerate(links):
                        link_id = link.get('id')
                        if link_id in ids_to_add:
                            # Ищем правильную позицию для вставки
                            # Если есть активная сортировка, добавляем в конец и затем сортировка восстановится
                            model = self.model()
                            row_count = model.rowCount() if model is not None else 0
                            target_row = row_count if sort_col != -1 else min(i, row_count)
                            self._add_row(target_row, link, mode)
                    t_add1 = time.perf_counter()
                
            except Exception as e:
                logging.error(f"[LinksTableView] Ошибка при инкрементальном обновлении: {e}")
                # В случае ошибки делаем полное обновление
                self._full_populate(links, mode)
            finally:
                self.horizontalHeader().blockSignals(False)
                self.blockSignals(False)
                self._restore_ui_state(current_selection, current_scroll_pos, sort_col, sort_order)
                t1 = time.perf_counter()
                # Итоговые тайминги этапов инкремента
                try:
                    logging.info(
                        "populate(incremental) total=%.1f ms | cache=%.1f ms | ids=%.1f ms | diff=%.1f ms | remove=%.1f ms | update=%.1f ms | add=%.1f ms | restore=%.1f ms"
                        % (
                            (t1 - t0) * 1000,
                            (t_cache1 - t_cache0) * 1000 if 't_cache1' in locals() else 0.0,
                            (t_ids1 - t_ids0) * 1000 if 't_ids1' in locals() else 0.0,
                            (t_diff1 - t_diff0) * 1000 if 't_diff1' in locals() else 0.0,
                            (t_remove1 - t_remove0) * 1000 if 't_remove1' in locals() else 0.0,
                            (t_update1 - t_update0) * 1000 if 't_update1' in locals() else 0.0,
                            (t_add1 - t_add0) * 1000 if 't_add1' in locals() else 0.0,
                            0.0,
                        )
                    )
                except Exception:
                    pass
        finally:
            # Всегда включаем обновление UI в конце
            self.setUpdatesEnabled(True)
            self.viewport().update()
            # Сообщаем подписчикам, что таблица обновлена
            try:
                if hasattr(self, 'table_populated'):
                    self.table_populated.emit()
            except Exception as e:
                logging.debug(f"[LinksTableView] Не удалось эмитить table_populated после populate: {e}")

    def _full_populate(self, links: List[Dict], mode: str):
        """Выполняет полное обновление таблицы (fallback)."""
        try:
            t0 = time.perf_counter()
            model = self.model()
            if model is None:
                return
            self._current_links.clear()
            model.set_links(links, mode=mode)
            for row_idx, link in enumerate(links):
                self._current_links[row_idx] = link
            t1 = time.perf_counter()
            logging.info(f"_full_populate: rows={len(links)} total={ (t1 - t0)*1000:.1f} ms")
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка при полном обновлении таблицы: {e}")
        finally:
            # Сообщаем подписчикам, что таблица полностью обновлена
            try:
                if hasattr(self, 'table_populated'):
                    self.table_populated.emit()
            except Exception as e:
                logging.debug(f"[LinksTableView] Не удалось эмитить table_populated после _full_populate: {e}")

    def _restore_ui_state(self, selection: List[int], scroll_pos: int, sort_col: int, sort_order: Qt.SortOrder):
        # Обновляет состояние UI после обновления
        self._sort_col = sort_col
        self._sort_order = sort_order
        """Восстанавливает состояние UI после обновления."""
        try:
            # Восстанавливаем сортировку
            if sort_col != -1 and sort_col < (self.model().columnCount() if self.model() else 0):
                # Для QTableView используем sortByColumn
                self.sortByColumn(sort_col, sort_order)
                # ВАЖНО: после сортировки строки меняют индексы —
                # нужно синхронизировать кэш _current_links с фактическими элементами,
                # иначе возможны визуальные дубликаты и неверные обновления строк
                try:
                    if hasattr(self, 'rebuild_cache_from_items'):
                        self.rebuild_cache_from_items()
                except Exception as e:
                    logging.warning(f"[LinksTableView] Не удалось перестроить кэш после сортировки: {e}")
            
            # Убрано автоматическое восстановление выделения строк
            # для стандартного поведения Qt без принудительного выбора
            
            # Восстанавливаем позицию скролла
            self.verticalScrollBar().setValue(scroll_pos)
            
            self.viewport().update()
            
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка восстановления UI состояния: {e}")
