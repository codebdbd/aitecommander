# Модуль для управления данными и кэшем таблицы ссылок
# Содержит методы работы с кэшем, валидации и сравнения данных

import logging
from typing import Any, Dict, List, Optional, Set, Protocol, cast

from PyQt6.QtCore import Qt


class _DataProtocol(Protocol):
    """Протокол ожидаемых атрибутов/методов у вида для работы с данными.

    Используется только теми частями, которые задействованы в миксине.
    """
    logger: logging.Logger
    _current_links: Dict[int, Dict]
    def model(self) -> Any: ...
    def get_link_at(self, row: int) -> Optional[Dict]: ...
    def selectRow(self, row: int) -> None: ...
    def setCurrentIndex(self, index: Any) -> None: ...
    def scrollTo(self, index: Any) -> None: ...


class DataManagementMixin:
    """Миксин для управления данными и кэшем таблицы ссылок."""

    logger = logging.getLogger(__name__)

    def validate_cache_integrity(self: _DataProtocol) -> bool:
        """Проверяет целостность кэша ссылок."""
        try:
            model = getattr(self, "model", lambda: None)()
            row_count = model.rowCount() if model is not None else 0
            cache_size = len(self._current_links)

            # Проверяем, что размер кэша соответствует количеству строк
            if cache_size != row_count:
                self.logger.warning(
                    "[LinksTableView] Несоответствие размера кэша: %s != %s",
                    cache_size,
                    row_count,
                )
                return False

            # Проверяем, что все индексы в кэше находятся в допустимом диапазоне
            for row in self._current_links.keys():
                if not (0 <= row < row_count):
                    self.logger.warning(
                        "[LinksTableView] Недопустимый индекс в кэше: %s",
                        row,
                    )
                    return False

            return True
        except Exception as e:
            self.logger.error(
                "[LinksTableView] Ошибка проверки целостности кэша: %s", e
            )
            return False

    def _links_equal(self: _DataProtocol, link1: Dict, link2: Dict, mode: str) -> bool:
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

    def _get_current_link_ids(self: _DataProtocol) -> Set[str]:
        """Возвращает множество ID текущих ссылок на основе фактических элементов таблицы (не кэша)."""
        ids: Set[str] = set()
        model = getattr(self, "model", lambda: None)()
        total = model.rowCount() if model is not None else 0
        for row in range(total):
            link_data = self.get_link_at(row)
            if link_data and "id" in link_data:
                ids.add(link_data["id"])
        return ids

    def _get_new_link_ids(self: _DataProtocol, new_links: List[Dict]) -> Set[str]:
        """Возвращает множество ID новых ссылок."""
        ids: Set[str] = set()
        for link in new_links:
            if not link:
                continue
            val = link.get("id")
            if isinstance(val, str):
                ids.add(val)
        return ids

    def rebuild_cache_from_items(self: _DataProtocol) -> None:
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
            self.logger.error(
                "[LinksTableView] Ошибка перестроения кэша из элементов: %s",
                e,
            )

    def _create_link_id_to_data_map(self: _DataProtocol, links: List[Dict]) -> Dict[str, Dict]:
        """Создает маппинг ID -> данные ссылки."""
        return {link.get("id"): link for link in links if link and "id" in link}

    def get_link_at(self: _DataProtocol, row: int) -> Optional[Dict]:
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
            self.logger.error(
                "[LinksTableView] Ошибка получения данных ссылки в строке %s: %s",
                row,
                e,
            )
            return None

    def find_row_by_link_id(self: _DataProtocol, link_id: int) -> Optional[int]:
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
            self.logger.error(
                "[LinksTableView] Ошибка поиска строки по ID %s: %s", link_id, e
            )
            return None

    def focus_on_link_id(self: _DataProtocol, link_id: int) -> bool:
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
                self.logger.info(
                    "[LinksTableView] Успешно установлен фокус на ссылку ID %s в строке %s",
                    link_id,
                    row,
                )
                return True
            else:
                self.logger.warning(
                    "[LinksTableView] Ссылка с ID %s не найдена в таблице", link_id
                )
                return False
        except Exception as e:
            self.logger.error(
                "[LinksTableView] Ошибка установки фокуса на ссылку ID %s: %s",
                link_id,
                e,
            )
            return False
