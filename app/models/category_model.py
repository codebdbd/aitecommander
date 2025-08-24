"""
CategoryModel - модель для работы с категориями в базе данных.
"""

import logging
from typing import Any, Dict, List, Optional

from .db_base import DatabaseBase

logger = logging.getLogger(__name__)


class CategoryModel(DatabaseBase):
    """Модель для работы с категориями."""

    def __init__(self, database):
        """Инициализация модели категорий."""
        super().__init__(database)

    def get_categories(self, section_id: int):
        """Возвращает список категорий для указанного раздела в формате dict."""
        rows = self._execute_with_error_handling(
            "SELECT id, name, section_id, position, icon_path FROM category "
            "WHERE section_id=? ORDER BY position",
            (section_id,),
            fetch_method="all",
        )
        return [dict(row) for row in rows] if rows else []

    def get_categories_for_sections(self, section_ids: List[int]):
        """Возвращает категории для нескольких разделов одним запросом в формате dict."""
        if not section_ids:
            return []

        placeholders = ",".join("?" * len(section_ids))
        query = f"""
            SELECT id, name, section_id, position, icon_path 
            FROM category 
            WHERE section_id IN ({placeholders}) 
            ORDER BY section_id, position
        """
        rows = self._execute_with_error_handling(query, section_ids, fetch_method="all")
        return [dict(row) for row in rows] if rows else []

    def get_category_by_id(self, category_id: int):
        """Возвращает категорию по её ID в формате dict."""
        row = self._execute_with_error_handling(
            "SELECT * FROM category WHERE id= ?", (category_id,), fetch_method="one"
        )
        return dict(row) if row else None

    def get_category_hierarchy(self, category_id: int) -> Optional[Dict[str, int]]:
        """Получить иерархию категории (сфера -> раздел -> категория).

        Args:
            category_id: ID категории

        Returns:
            Dict с sphere_id, section_id, category_id или None при ошибке
        """
        result = self._execute_with_error_handling(
            """SELECT s.sphere_id, c.section_id 
               FROM category c 
               JOIN section s ON c.section_id = s.id 
               WHERE c.id = ?""",
            (category_id,),
            fetch_method="one",
        )

        if result:
            return {
                "sphere_id": result["sphere_id"],
                "section_id": result["section_id"],
                "category_id": category_id,
            }
        return None

    def insert_category(self, data: Dict[str, Any]) -> Optional[int]:
        """Вставляет новую категорию и возвращает её ID.

        Args:
            data: Словарь с данными категории, должен содержать 'name' и 'section_id'

        Returns:
            int: ID созданной категории или None, если категория с таким именем уже существует
        """
        self._validate_required_fields(data, ["name", "section_id"], "категории")

        # Проверяем, существует ли уже категория с таким именем в этом разделе
        cursor = self._execute_with_error_handling(
            "SELECT id FROM category WHERE section_id = ? AND name = ?",
            (data["section_id"], data["name"]),
            fetch_method="one",
        )
        if cursor is not None:
            # Категория с таким именем уже существует в этом разделе
            logger.warning(
                f"Категория '{data['name']}' уже существует в разделе {data['section_id']}"
            )
            return None

        position = self._get_next_position("category", "section_id", data["section_id"])
        cursor = self._execute_with_error_handling(
            "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
            (data["name"], data["section_id"], data.get("icon_path", ""), position),
        )
        self.connection.commit()
        logger.info(f"Добавлена новая категория: {data['name']}")
        return cursor.lastrowid

    def update_category(self, category_id: int, data: Dict[str, Any]):
        """Обновляет существующую категорию."""
        return self._update_entity("category", category_id, data)

    def delete_category(self, category_id: int):
        """Удаляет категорию по её ID вместе со всеми её ссылками (атомарно)."""
        with self.transaction():
            # Сначала удаляем все ссылки категории
            self._execute_with_error_handling(
                "DELETE FROM link WHERE category_id=?", (category_id,)
            )
            # Затем удаляем саму категорию
            self._execute_with_error_handling(
                "DELETE FROM category WHERE id=?", (category_id,)
            )
        logger.info(f"Удалена категория с ID {category_id} и все её ссылки")

    def upsert_category(self, category_data: Dict[str, Any]) -> int:
        """Вставляет или обновляет категорию. Если категории с таким id нет, вставляет новую с этим id."""
        if "id" in category_data and category_data["id"]:
            cursor = self._execute_with_error_handling(
                "UPDATE category SET name=?, section_id=?, icon_path=?, position=? WHERE id=?",
                (
                    category_data["name"],
                    category_data["section_id"],
                    category_data.get("icon_path", ""),
                    category_data.get("position", 0),
                    category_data["id"],
                ),
            )
            self.connection.commit()
            if cursor.rowcount == 0:
                # Записи не было, делаем вставку с нужным id
                self.connection.execute(
                    "INSERT INTO category (id, name, section_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                    (
                        category_data["id"],
                        category_data["name"],
                        category_data["section_id"],
                        category_data.get("icon_path", ""),
                        category_data.get("position", 0),
                    ),
                )
                self.connection.commit()
            return category_data["id"]
        else:
            category_id = self.insert_category(category_data)
            if category_id is None:
                raise ValueError(
                    f"Категория с именем '{category_data['name']}' уже существует в этом разделе"
                )
            return category_id

    def get_first_category_id(self):
        """Возвращает первую категорию в системе."""
        result = self._execute_with_error_handling(
            "SELECT id FROM category ORDER BY id LIMIT 1", fetch_method="one"
        )
        return result["id"] if result else None

    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: Optional[int] = None
    ):
        """Проверяет наличие дубликата категории в разделе."""
        query = (
            "SELECT COUNT(*) as count FROM category WHERE section_id = ? AND name = ?"
        )
        params = [section_id, category_name]

        if exclude_id is not None:
            query += " AND id != ?"
            params.append(exclude_id)

        result = self._execute_with_error_handling(query, params, fetch_method="one")
        return result["count"] > 0
