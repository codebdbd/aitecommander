# Модуль для управления данными и кэшем таблицы ссылок
# Содержит методы работы с кэшем, валидации и сравнения данных

import logging
from typing import Dict, List, Optional, Set

from PyQt6.QtCore import Qt

from app.utils.ui.qt.roles import get_item_dict


class DataManagementMixin:
    """Миксин для управления данными и кэшем таблицы ссылок."""
    
    def validate_cache_integrity(self) -> bool:
        """Проверяет целостность кэша ссылок."""
        try:
            row_count = self.rowCount()
            cache_size = len(self._current_links)
            
            # Проверяем, что размер кэша соответствует количеству строк
            if cache_size != row_count:
                logging.warning(f"[LinksTableView] Несоответствие размера кэша: {cache_size} != {row_count}")
                return False
            
            # Проверяем, что все индексы в кэше находятся в допустимом диапазоне
            for row in self._current_links.keys():
                if not (0 <= row < row_count):
                    logging.warning(f"[LinksTableView] Недопустимый индекс в кэше: {row}")
                    return False
            
            return True
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка проверки целостности кэша: {e}")
            return False

    def _links_equal(self, link1: Dict, link2: Dict, mode: str) -> bool:
        """Сравнивает две ссылки на предмет равенства для текущего режима."""
        # Оптимизация: быстрая проверка на идентичность объектов
        if link1 is link2:
            return True
            
        if not link1 or not link2:
            return False
            
        # Быстрая проверка ID
        if link1.get('id') != link2.get('id'):
            return False
            
        # Основные поля, которые всегда проверяются
        basic_fields = ['name', 'is_favorite', 'notes', 'icon_path', 'args']
        
        # Дополнительные поля в зависимости от режима
        if mode == "normal":
            basic_fields.append('last_used')
        else:  # search mode
            basic_fields.extend(['url', 'path', 'sphere_name', 'section_name', 'category_name'])
        
        # Оптимизация: используем all() для более быстрой проверки
        return all(link1.get(field) == link2.get(field) for field in basic_fields)

    def _get_current_link_ids(self) -> Set[str]:
        """Возвращает множество ID текущих ссылок."""
        return {link.get('id') for link in self._current_links.values() if link and 'id' in link}

    def _get_new_link_ids(self, new_links: List[Dict]) -> Set[str]:
        """Возвращает множество ID новых ссылок."""
        return {link.get('id') for link in new_links if link and 'id' in link}

    def _create_link_id_to_data_map(self, links: List[Dict]) -> Dict[str, Dict]:
        """Создает маппинг ID -> данные ссылки."""
        return {link.get('id'): link for link in links if link and 'id' in link}

    def get_link_at(self, row: int) -> Optional[Dict]:
        """Возвращает данные о ссылке для указанной строки."""
        try:
            if not (0 <= row < self.rowCount()):
                return None
            
            # НАДЕЖНОЕ РЕШЕНИЕ: Используем только актуальные данные из элементов таблицы
            item = self.item(row, 0)
            if not item:
                return None
                
            link_data = get_item_dict(item)
            if not isinstance(link_data, dict):
                logging.warning(f"[LinksTableView] Некорректные данные в строке {row}")
                return None
                
            return link_data
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка получения данных ссылки в строке {row}: {e}")
            return None

    def find_row_by_link_id(self, link_id: int) -> Optional[int]:
        """Находит строку таблицы по ID ссылки."""
        try:
            for row in range(self.rowCount()):
                link_data = self.get_link_at(row)
                if link_data and link_data.get('id') == link_id:
                    return row
            return None
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка поиска строки по ID {link_id}: {e}")
            return None

    def focus_on_link_id(self, link_id: int) -> bool:
        """Устанавливает фокус на ссылку по ID."""
        try:
            row = self.find_row_by_link_id(link_id)
            if row is not None:
                self.selectRow(row)
                self.setCurrentCell(row, 0)
                item = self.item(row, 0)
                if item:
                    self.scrollToItem(item)
                logging.info(f"[LinksTableView] Успешно установлен фокус на ссылку ID {link_id} в строке {row}")
                return True
            else:
                logging.warning(f"[LinksTableView] Ссылка с ID {link_id} не найдена в таблице")
                return False
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка установки фокуса на ссылку ID {link_id}: {e}")
            return False
