# Модуль для управления данными и кэшем таблицы ссылок
# Содержит методы работы с кэшем, валидации и сравнения данных

import logging
from typing import Dict, List, Optional, Set

from PyQt6.QtCore import Qt


class DataManagementMixin:
    """Миксин для управления данными и кэшем таблицы ссылок."""

    def validate_cache_integrity(self) -> bool:
        """Проверяет целостность кэша ссылок."""
        try:
            model = getattr(self, "model", lambda: None)()
            row_count = model.rowCount() if model is not None else 0
            cache_size = len(self._current_links)

            # Проверяем, что размер кэша соответствует количеству строк
            if cache_size != row_count:
                logging.warning(
                    f"[LinksTableView] Несоответствие размера кэша: {cache_size} != {row_count}"
                )
                return False

            # Проверяем, что все индексы в кэше находятся в допустимом диапазоне
            for row in self._current_links.keys():
                if not (0 <= row < row_count):
                    logging.warning(
                        f"[LinksTableView] Недопустимый индекс в кэше: {row}"
                    )
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
        if link1.get("id") != link2.get("id"):
            return False

        # Основные поля, которые всегда проверяются
        basic_fields = ["name", "is_favorite", "notes", "icon_path", "args"]

        # Дополнительные поля в зависимости от режима
        if mode == "normal":
            basic_fields.append("last_used")
        else:  # search mode
            basic_fields.extend(
                ["url", "path", "sphere_name", "section_name", "category_name"]
            )

        # Оптимизация: используем all() для более быстрой проверки
        return all(link1.get(field) == link2.get(field) for field in basic_fields)

    def _get_current_link_ids(self) -> Set[str]:
        """Возвращает множество ID текущих ссылок на основе фактических элементов таблицы (не кэша)."""
        ids: Set[str] = set()
        model = getattr(self, "model", lambda: None)()
        total = model.rowCount() if model is not None else 0
        for row in range(total):
            link_data = self.get_link_at(row)
            if link_data and "id" in link_data:
                ids.add(link_data["id"])
        return ids

    def _get_new_link_ids(self, new_links: List[Dict]) -> Set[str]:
        """Возвращает множество ID новых ссылок."""
        return {link.get("id") for link in new_links if link and "id" in link}

    def rebuild_cache_from_items(self) -> None:
        """Полностью перестраивает кэш _current_links по текущему состоянию таблицы."""
        try:
            self._current_links.clear()
            model = getattr(self, "model", lambda: None)()
            total = model.rowCount() if model is not None else 0
            for row in range(total):
                link_data = self.get_link_at(row)
                if link_data:
                    self._current_links[row] = link_data
        except Exception as e:
            logging.error(
                f"[LinksTableView] Ошибка перестроения кэша из элементов: {e}"
            )

    def _create_link_id_to_data_map(self, links: List[Dict]) -> Dict[str, Dict]:
        """Создает маппинг ID -> данные ссылки."""
        return {link.get("id"): link for link in links if link and "id" in link}

    def get_link_at(self, row: int) -> Optional[Dict]:
        """Возвращает данные ссылки для строки через модель (UserRole)."""
        try:
            model = getattr(self, "model", lambda: None)()
            if model is None:
                return None
            if not (0 <= row < model.rowCount()):
                return None
            idx = model.index(row, 0)
            data = model.data(idx, Qt.ItemDataRole.UserRole)
            return data if isinstance(data, dict) else None
        except Exception as e:
            logging.error(
                f"[LinksTableView] Ошибка получения данных ссылки в строке {row}: {e}"
            )
            return None

    def find_row_by_link_id(self, link_id: int) -> Optional[int]:
        """Находит строку таблицы по ID ссылки."""
        try:
            model = getattr(self, "model", lambda: None)()
            if model is None:
                return None
            for row in range(model.rowCount()):
                link_data = self.get_link_at(row)
                if link_data and link_data.get("id") == link_id:
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
                # QTableView API
                self.selectRow(row)
                model = self.model()
                idx = model.index(row, 0)
                self.setCurrentIndex(idx)
                self.scrollTo(idx)
                logging.info(
                    f"[LinksTableView] Успешно установлен фокус на ссылку ID {link_id} в строке {row}"
                )
                return True
            else:
                logging.warning(
                    f"[LinksTableView] Ссылка с ID {link_id} не найдена в таблице"
                )
                return False
        except Exception as e:
            logging.error(
                f"[LinksTableView] Ошибка установки фокуса на ссылку ID {link_id}: {e}"
            )
            return False
