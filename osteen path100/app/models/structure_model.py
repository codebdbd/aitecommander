# app/models/structure_model.py

"""Модель для работы со структурой (сферы, разделы, категории)."""

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.models.db import Database

logger = logging.getLogger(__name__)


class StructureModel:
    """Модель для работы со структурой."""

    def __init__(self, db: Database, logger: Optional[logging.Logger] = None):
        self.db = db
        self.logger = logger or globals().get("logger") or logging.getLogger(__name__)

    def _commit_if_in_tx(self) -> None:
        """Фиксирует транзакцию, если она активна на соединении.

        Вынос дублируемой логики в единое место снижает риск расхождений поведения.
        В случае ошибки логируем и не пробрасываем дальше, чтобы не маскировать
        исходную операцию уровня модели.
        """
        try:
            conn = self.db.connection
            if getattr(conn, "in_transaction", False):
                self.db.commit()
        except Exception as e:
            self.logger.error("Ошибка фиксации транзакции: %s", e, exc_info=True)

    def get_spheres(self) -> List[Dict[str, Any]]:
        """Возвращает список всех сфер."""
        return self.db.spheres.get_spheres() or []

    def get_sphere_by_id(self, sphere_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает сферу по её ID."""
        return self.db.spheres.get_sphere_by_id(sphere_id)

    def upsert_sphere(self, data: Dict[str, Any]) -> int:
        """Вставляет или обновляет сферу. Возвращает ID записи."""
        sid = self.db.spheres.upsert_sphere(data)
        self._commit_if_in_tx()
        return sid

    def create_sphere(self, data: Dict[str, Any]) -> Optional[int]:
        """Создает новую сферу (обертка для upsert_sphere)."""
        try:
            return self.upsert_sphere(data)
        except Exception as e:
            self.logger.error("Ошибка создания сферы: %s", e, exc_info=True)
            return None

    def update_sphere(self, sphere_id: int, data: Dict[str, Any]) -> bool:
        """Обновляет сферу по ID (обертка для upsert_sphere)."""
        try:
            payload = dict(data) if data else {}
            payload["id"] = sphere_id
            self.upsert_sphere(payload)
            return True
        except Exception as e:
            self.logger.error(
                "Ошибка обновления сферы %s: %s", sphere_id, e, exc_info=True
            )
            return False

    def get_sections(self, sphere_id: int) -> List[Dict[str, Any]]:
        """Возвращает список разделов для указанной сферы."""
        return self.db.sections.get_sections(sphere_id) or []

    def get_section_by_id(self, section_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает раздел по его ID."""
        return self.db.sections.get_section_by_id(section_id)

    def get_categories(self, section_id: int) -> List[Dict[str, Any]]:
        """Возвращает список категорий для указанного раздела."""
        return self.db.categories.get_categories(section_id) or []

    def get_category_by_id(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает категорию по её ID."""
        return self.db.categories.get_category_by_id(category_id)

    def get_category_hierarchy(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает иерархию категории (sphere_id, section_id)."""
        hierarchy_data = self.db.categories.get_category_hierarchy(category_id)
        if not hierarchy_data:
            return None

        try:
            # Ожидаем только dict из CategoryModel.get_category_hierarchy
            if not isinstance(hierarchy_data, dict):
                self.logger.warning(
                    "Некорректный формат иерархии для категории %s: %s",
                    category_id,
                    type(hierarchy_data),
                )
                return None

            # Пытаемся прочитать стандартные ключи
            sphere_id = hierarchy_data.get("sphere_id")
            section_id = hierarchy_data.get("section_id")
            # Возможные альтернативные ключи (на случай старых вызовов)
            if sphere_id is None:
                sphere_id = hierarchy_data.get("sphereId")
            if section_id is None:
                section_id = hierarchy_data.get("sectionId")

            # Базовая проверка типов/значений
            if sphere_id is None or section_id is None:
                self.logger.warning(
                    "Отсутствуют ключи sphere_id/section_id в иерархии категории %s: %s",
                    category_id,
                    hierarchy_data,
                )
                return None

            return {"sphere_id": sphere_id, "section_id": section_id}
        except Exception as e:
            self.logger.error(
                "Ошибка обработки иерархии категории %s: %s",
                category_id,
                e,
                exc_info=True,
            )
            return None

    def upsert_section(self, data: Dict[str, Any]) -> int:
        """Вставляет или обновляет раздел. Возвращает ID записи."""
        sid = self.db.sections.upsert_section(data)
        self._commit_if_in_tx()
        return sid

    def upsert_category(self, data: Dict[str, Any]) -> int:
        """Вставляет или обновляет категорию. Возвращает ID записи."""
        cid = self.db.categories.upsert_category(data)
        self._commit_if_in_tx()
        return cid

    # ---------------------------------------------------------------------
    # Обертки для совместимости с бизнес-логикой (ожидаемые методы)
    # ---------------------------------------------------------------------
    def create_section(self, data: Dict[str, Any]) -> Optional[int]:
        """Создает новый раздел (обертка для upsert_section)."""
        try:
            return self.upsert_section(data)
        except Exception as e:
            self.logger.error("Ошибка создания раздела: %s", e, exc_info=True)
            return None

    def update_section(self, section_id: int, data: Dict[str, Any]) -> bool:
        """Обновляет раздел по ID (обертка для upsert_section)."""
        try:
            payload = dict(data) if data else {}
            payload["id"] = section_id
            self.upsert_section(payload)
            return True
        except Exception as e:
            self.logger.error(
                "Ошибка обновления раздела %s: %s", section_id, e, exc_info=True
            )
            return False

    def update_category(self, category_id: int, data: Dict[str, Any]) -> bool:
        """Обновляет категорию по ID (обертка для upsert_category)."""
        try:
            payload = dict(data) if data else {}
            payload["id"] = category_id
            self.upsert_category(payload)
            return True
        except Exception as e:
            self.logger.error(
                "Ошибка обновления категории %s: %s", category_id, e, exc_info=True
            )
            return False

    def get_section_data(self, section_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает данные раздела (алиас get_section_by_id)."""
        return self.get_section_by_id(section_id)

    def get_category_data(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает данные категории (алиас get_category_by_id)."""
        return self.get_category_by_id(category_id)

    def delete_section(self, section_id: int) -> bool:
        """Удаляет раздел по его ID."""
        try:
            self.db.sections.delete_section(section_id)
            self._commit_if_in_tx()
            return True
        except Exception as e:
            self.logger.error(
                "Ошибка удаления раздела %s: %s", section_id, e, exc_info=True
            )
            return False

    def delete_category(self, category_id: int) -> bool:
        """Удаляет категорию по её ID."""
        try:
            self.db.categories.delete_category(category_id)
            self._commit_if_in_tx()
            return True
        except Exception as e:
            self.logger.error(
                "Ошибка удаления категории %s: %s", category_id, e, exc_info=True
            )
            return False

    def get_first_category_id(self) -> Optional[int]:
        """Получает ID первой категории в системе."""
        try:
            result = self.db.categories.get_first_category_id()
            return result if result else None
        except Exception as e:
            self.logger.error("Ошибка получения первой категории: %s", e, exc_info=True)
            return None

    def get_categories_batch(self, section_ids: List[int]) -> List[Dict[str, Any]]:
        """Получает категории для нескольких разделов одним оптимизированным запросом."""
        if not section_ids:
            return []

        try:
            # Используем оптимизированный метод БД вместо N+1 запросов
            categories_raw = self.db.categories.get_categories_for_sections(section_ids)
            return categories_raw or []
        except Exception as e:
            self.logger.error(
                "Ошибка получения категорий для разделов %s: %s",
                section_ids,
                e,
                exc_info=True,
            )
            return []

    def count_nested_objects_for_section(self, section_id: int) -> Tuple[int, int]:
        """Подсчитывает категории и ссылки в разделе."""
        categories_data = self.db.categories.get_categories(section_id)
        cats_count = len(categories_data) if categories_data else 0

        links_count = 0
        if categories_data:
            for category_row in categories_data:
                # Прямой доступ к полю id: get_categories возвращает список dict
                category_id = category_row["id"]
                # Оптимизировано: используем эффективный подсчет вместо загрузки всех строк ссылок
                links_count += self.db.links.count_links_by_category(category_id)

        return cats_count, links_count

    def update_item_positions(self, table_name: str, ids_in_order: List[int]) -> None:
        """Обновляет позиции элементов в указанной таблице."""
        self.db.update_item_positions(table_name, ids_in_order)

    def create_category(self, category_data: Dict[str, Any]) -> Optional[int]:
        """Создает новую категорию."""
        try:
            cat_id = self.db.categories.insert_category(category_data)
            # Явная фиксация, если категория создаётся вне внешней транзакции
            self._commit_if_in_tx()
            return cat_id
        except Exception as e:
            self.logger.error("Ошибка создания категории: %s", e, exc_info=True)
            return None

    def create_categories_bulk(
        self, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Пакетное создание категорий (атомарно).

        Делегирует в `CategoryModel.insert_categories_bulk` и возвращает список
        фактических записей категорий после операции (как новые, так и существующие
        из набора имён), для синхронизации UI/кеша.
        """
        try:
            return self.db.categories.insert_categories_bulk(items or []) or []
        except Exception as e:
            self.logger.error(
                "Ошибка пакетного создания категорий: %s", e, exc_info=True
            )
            return []

    def create_link(self, link_data: Dict[str, Any]) -> Optional[int]:
        """Создает или обновляет ссылку (обертка для upsert_link).

        Возвращает ID записи. Для новых записей модель ссылок выполняет
        тихую проверку дубликатов по (category_id, name, url, args) и
        возвращает ID существующей записи без ошибки, если дубликат найден.
        """
        try:
            # Прямое создание через БД для избежания циклических зависимостей
            link_id = self.db.links.upsert_link(link_data)
            # Явная фиксация, если операция выполняется в рамках активной транзакции
            self._commit_if_in_tx()
            return link_id
        except Exception as e:
            self.logger.error("Ошибка создания ссылки: %s", e, exc_info=True)
            return None

    def get_links(self, category_id: int) -> List[Dict[str, Any]]:
        """Получает список ссылок для указанной категории."""
        try:
            links_raw = self.db.links.get_links(category_id)
            return links_raw or []
        except Exception as e:
            self.logger.error(
                "Ошибка получения ссылок для категории %s: %s",
                category_id,
                e,
                exc_info=True,
            )
            return []

    def count_links_by_category(self, category_id: int) -> int:
        """Возвращает количество ссылок для указанной категории (эффективный подсчет)."""
        try:
            return self.db.links.count_links_by_category(category_id)
        except Exception as e:
            self.logger.error(
                "Ошибка подсчета ссылок для категории %s: %s",
                category_id,
                e,
                exc_info=True,
            )
            return 0

    def count_links_by_categories(self, category_ids: List[int]) -> Dict[int, int]:
        """Пакетный подсчёт ссылок для нескольких категорий одним запросом.

        Возвращает словарь {category_id: count}. В случае ошибки возвращает пустой словарь.
        """
        try:
            return self.db.links.count_links_by_categories(category_ids or [])
        except Exception as e:
            self.logger.error(
                "Ошибка пакетного подсчёта ссылок для категорий %s: %s",
                category_ids,
                e,
                exc_info=True,
            )
            return {}

    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: Optional[int] = None
    ) -> bool:
        """Проверяет наличие дубликата категории в разделе."""
        try:
            return self.db.categories.has_duplicate_category(
                section_id, category_name, exclude_id
            )
        except Exception as e:
            self.logger.error(
                "Ошибка проверки дубликата категории '%s' в разделе %s: %s",
                category_name,
                section_id,
                e,
                exc_info=True,
            )
            raise
