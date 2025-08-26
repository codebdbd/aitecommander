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

    def insert_categories_bulk(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Пакетная вставка категорий с атомарной транзакцией.

        - Ожидает список словарей с ключами минимум: 'name', 'section_id'.
        - Дополнительно поддерживается 'icon_path'.
        - Дубликаты (UNIQUE(section_id, name)) игнорируются тихо (INSERT OR IGNORE).
        - Позиции вычисляются эффективно: последовательно для каждой группы section_id
          от текущего MAX(position) + 1.

        Возвращает список категорий (dict) для всех переданных имён по секциям
        после операции (как новые, так и существующие), чтобы вызывающая сторона могла
        синхронизировать UI. Порядок в результате: по section_id, затем по position.
        """
        if not items:
            return []

        # Валидация входных данных
        for it in items:
            self._validate_required_fields(it or {}, ["name", "section_id"], "категории")

        # Группируем по section_id для расчёта позиций
        by_section: Dict[int, List[Dict[str, Any]]] = {}
        for it in items:
            try:
                sid = int(it.get("section_id"))
            except Exception:
                raise ValidationError("Некорректный section_id в одном из элементов пакета")
            by_section.setdefault(sid, []).append(it)

        # Формируем батч вставки
        batched_params: List[tuple] = []
        try:
            with self.transaction():
                # Предзагружаем текущие MAX(position) для всех разделов одним запросом
                section_ids = list(by_section.keys())
                max_pos_map: Dict[int, Optional[int]] = {}
                if section_ids:
                    placeholders = ",".join(["?"] * len(section_ids))
                    query = (
                        f"SELECT section_id, MAX(position) AS max_pos "
                        f"FROM category WHERE section_id IN ({placeholders}) "
                        f"GROUP BY section_id"
                    )
                    rows = self._execute_with_error_handling(
                        query, tuple(section_ids), fetch_method="all"
                    )
                    for row in (rows or []):
                        max_pos_map[row["section_id"]] = row["max_pos"]

                for section_id, group in by_section.items():
                    # Стартовая позиция: (MAX(position) + 1) или 0, если записей нет
                    max_pos = max_pos_map.get(section_id)
                    start_pos = (max_pos + 1) if (max_pos is not None) else 0
                    pos = start_pos
                    for it in group:
                        name = it.get("name")
                        icon_path = it.get("icon_path", "")
                        batched_params.append((name, section_id, icon_path, pos))
                        pos += 1

                # Вставляем одним executemany с тихим игнорированием дублей
                self._execute_many_with_error_handling(
                    "INSERT OR IGNORE INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                    batched_params,
                )

                # Возвращаем актуальные записи для всех переданных имён в разрезе разделов
                result: List[Dict[str, Any]] = []
                for section_id, group in by_section.items():
                    names = [g.get("name") for g in group if g.get("name") is not None]
                    if not names:
                        continue
                    placeholders = ",".join(["?"] * len(names))
                    query = (
                        "SELECT id, name, section_id, position, icon_path "
                        "FROM category WHERE section_id = ? AND name IN (" + placeholders + ") "
                        "ORDER BY position"
                    )
                    rows = self._execute_with_error_handling(
                        query, tuple([section_id, *names]), fetch_method="all"
                    )
                    if rows:
                        result.extend([dict(r) for r in rows])

                return result
        except Exception:
            # Инициируем откат и пробрасываем далее
            raise

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

    def delete_categories_bulk(self, category_ids: List[int]) -> int:
        """Пакетное удаление нескольких категорий (и их ссылок) в одной транзакции.

        Возвращает количество удалённых категорий. Игнорирует невалидные ID.
        """
        if not category_ids:
            return 0

        # Оставляем только валидные положительные целые ID и удаляем дубликаты
        ids = [int(x) for x in category_ids if isinstance(x, int) and x > 0]
        # Дедупликация с сохранением порядка первой встречаемости
        unique_ids = list(dict.fromkeys(ids))
        if not unique_ids:
            return 0

        placeholders = ",".join(["?"] * len(unique_ids))
        deleted_categories = 0
        with self.transaction():
            # 1) Удаляем все ссылки, принадлежащие этим категориям
            self._execute_with_error_handling(
                f"DELETE FROM link WHERE category_id IN ({placeholders})",
                tuple(unique_ids),
            )
            # 2) Удаляем сами категории и считаем, сколько реально удалили
            cursor = self._execute_with_error_handling(
                f"DELETE FROM category WHERE id IN ({placeholders})",
                tuple(unique_ids),
            )
            try:
                deleted_categories = int(getattr(cursor, "rowcount", 0) or 0)
            except Exception:
                deleted_categories = 0

        logger.info(
            f"Пакетно удалены категории (шт={deleted_categories}), ids={unique_ids}"
        )
        return deleted_categories

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
