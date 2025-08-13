# Модуль для операций со строками таблицы ссылок
# Содержит методы добавления, обновления и удаления строк

import logging
from typing import Dict

from PyQt6.QtCore import Qt

from app.utils.ui.qt.roles import get_item_dict


class RowOperationsMixin:
    """Миксин для операций со строками таблицы ссылок."""
    
    def update_link_by_id(self, link: dict, mode: str = "normal"):
        """
        Обновляет строку таблицы по id ссылки, если она есть.
        """
        try:
            # Проверка входных параметров
            if not isinstance(link, dict):
                logging.warning(f"[LinksTableView] Некорректные данные ссылки для обновления: {type(link)}")
                return False
                
            link_id = link.get("id")
            link_name = link.get('name', 'Без названия')
            is_favorite = link.get('is_favorite', False)
            
            if link_id is None:
                logging.warning("[LinksTableView] Отсутствует ID в данных ссылки для обновления")
                return False
                
            # НАДЕЖНОЕ РЕШЕНИЕ: Ищем по реальным данным таблицы, а не по кэшу
            for row in range(self.rowCount()):
                item = self.item(row, 0)
                if not item:
                    continue
                    
                row_data = get_item_dict(item)
                if not isinstance(row_data, dict):
                    continue
                
                if row_data.get("id") == link_id:
                    row_name = row_data.get('name', 'Без названия')
                    row_fav = row_data.get('is_favorite', False)
                    
                    success = self._update_row(row, link, mode)
                    return success
                    
            logging.warning(f"Ссылка с ID {link_id} не найдена в таблице")
            return False
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка обновления строки по ID: {e}")
            return False

    def _update_row(self, row: int, link: Dict, mode: str):
        """Обновляет существующую строку новыми данными."""
        try:
            # Проверка входных параметров
            if not isinstance(link, dict):
                logging.warning(f"[LinksTableView] Некорректные данные ссылки для обновления: {type(link)}")
                return False
            
            if row < 0 or row >= self.rowCount():
                logging.warning(f"[LinksTableView] Некорректный индекс строки для обновления: {row}")
                return False
            
            link_id = link.get('id')
            link_name = link.get('name', 'Без названия')
            is_favorite = link.get('is_favorite', False)
            logging.info(f"_update_row: строка {row}, ID {link_id}, '{link_name}', избранное={is_favorite}")
                
            row_items = self.build_row(link, mode=mode)
            if not row_items:
                logging.warning(f"build_row вернул пустой список")
                return False
            
            logging.info(f"Получено {len(row_items)} элементов для обновления")
            
            # Обновляем элементы таблицы
            for col_idx, item in enumerate(row_items):
                if col_idx == 0:  # Звездочка
                    old_item = self.item(row, col_idx)
                    old_text = old_item.text() if old_item else "Нет"
                    new_text = item.text()
                    logging.info(f"Обновление звездочки: '{old_text}' -> '{new_text}'")
                
                self.setItem(row, col_idx, item)
            
            # Обновляем кэш (пока оставляем для совместимости)
            self._current_links[row] = link
            logging.info(f"Строка {row} успешно обновлена")
            return True
            
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка обновления строки {row}: {e}")
            return False

    def _add_row(self, row: int, link: Dict, mode: str):
        """Добавляет новую строку."""
        try:
            # Проверка входных параметров
            if not isinstance(link, dict):
                logging.warning(f"[LinksTableView] Некорректные данные ссылки для добавления: {type(link)}")
                return False
            
            if row < 0 or row > self.rowCount():
                logging.warning(f"[LinksTableView] Некорректный индекс строки для добавления: {row}")
                return False
                
            self.insertRow(row)
            row_items = self.build_row(link, mode=mode)
            if not row_items:
                # Удаляем пустую строку в случае ошибки
                self.removeRow(row)
                return False
                
            for col_idx, item in enumerate(row_items):
                self.setItem(row, col_idx, item)
            
            # Обновляем кэш (сдвигаем индексы)
            new_cache = {}
            for cached_row, cached_link in self._current_links.items():
                if cached_row >= row:
                    new_cache[cached_row + 1] = cached_link
                else:
                    new_cache[cached_row] = cached_link
            new_cache[row] = link
            self._current_links = new_cache
            
            return True
            
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка добавления строки {row}: {e}")
            # Пытаемся откатить изменения
            try:
                if row < self.rowCount():
                    self.removeRow(row)
            except Exception as rollback_error:
                logging.error(f"[LinksTableView] Ошибка отката добавления строки {row}: {rollback_error}")
            return False

    def _remove_row(self, row: int):
        """Удаляет строку."""
        try:
            # Проверка входных параметров
            if row < 0 or row >= self.rowCount():
                logging.warning(f"[LinksTableView] Некорректный индекс строки для удаления: {row}")
                return
                
            self.removeRow(row)
            
            # Обновляем кэш (сдвигаем индексы)
            new_cache = {}
            for cached_row, cached_link in self._current_links.items():
                if cached_row < row:
                    new_cache[cached_row] = cached_link
                elif cached_row > row:
                    new_cache[cached_row - 1] = cached_link
                # cached_row == row - удаляем
            self._current_links = new_cache
            
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка удаления строки {row}: {e}")
