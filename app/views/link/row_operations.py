# Модуль для операций со строками таблицы ссылок
# Содержит методы добавления, обновления и удаления строк

import logging
from typing import Dict
from PyQt6.QtCore import Qt


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
            
            if link_id is None:
                logging.warning("[LinksTableView] Отсутствует ID в данных ссылки для обновления")
                return False
                
            # Ищем по данным модели
            model = self.model()
            if model is None:
                return False
            for row in range(model.rowCount()):
                index = model.index(row, 0)
                row_data = index.data(Qt.ItemDataRole.UserRole)
                if isinstance(row_data, dict) and row_data.get("id") == link_id:
                    return self._update_row(row, link, mode)
                    
            logging.debug(f"Ссылка с ID {link_id} не найдена в таблице")
            return False
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка обновления строки по ID: {e}")
            return False

    def _update_row(self, row: int, link: Dict, mode: str):
        """Обновляет существующую строку новыми данными."""
        try:
            if not isinstance(link, dict):
                logging.warning(f"[LinksTableView] Некорректные данные ссылки для обновления: {type(link)}")
                return False
            model = self.model()
            if model is None:
                return False
            if row < 0 or row >= model.rowCount():
                logging.warning(f"[LinksTableView] Некорректный индекс строки для обновления: {row}")
                return False
            link_id = link.get('id')
            link_name = link.get('name', 'Без названия')
            is_favorite = link.get('is_favorite', False)
            logging.info(f"_update_row: строка {row}, ID {link_id}, '{link_name}', избранное={is_favorite}")
            success = model.update_link(row, link)
            if success:
                self._current_links[row] = link
                try:
                    self.viewport().update()
                except Exception:
                    pass
                logging.info(f"Строка {row} успешно обновлена")
            return success
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка обновления строки {row}: {e}")
            return False

    def _add_row(self, row: int, link: Dict, mode: str):
        """Добавляет новую строку."""
        try:
            if not isinstance(link, dict):
                logging.warning(f"[LinksTableView] Некорректные данные ссылки для добавления: {type(link)}")
                return False
            model = self.model()
            if model is None:
                return False
            if row < 0 or row > model.rowCount():
                logging.warning(f"[LinksTableView] Некорректный индекс строки для добавления: {row}")
                return False
            success = model.insert_link(row, link)
            if success:
                # Обновляем кэш (сдвигаем индексы)
                new_cache = {}
                for cached_row, cached_link in self._current_links.items():
                    if cached_row >= row:
                        new_cache[cached_row + 1] = cached_link
                    else:
                        new_cache[cached_row] = cached_link
                new_cache[row] = link
                self._current_links = new_cache
            return success
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка добавления строки {row}: {e}")
            return False

    def _remove_row(self, row: int):
        """Удаляет строку."""
        try:
            model = self.model()
            if model is None:
                return
            if row < 0 or row >= model.rowCount():
                logging.warning(f"[LinksTableView] Некорректный индекс строки для удаления: {row}")
                return
            if model.remove_row(row):
                new_cache = {}
                for cached_row, cached_link in self._current_links.items():
                    if cached_row < row:
                        new_cache[cached_row] = cached_link
                    elif cached_row > row:
                        new_cache[cached_row - 1] = cached_link
                self._current_links = new_cache
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка удаления строки {row}: {e}")
