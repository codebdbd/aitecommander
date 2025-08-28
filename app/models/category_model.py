"""
CategoryModel - модель для работы с категориями в базе данных.
"""

import logging
from typing import Any, Dict, List, Optional

from .db_base import DatabaseBase, ValidationError

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
                    # Список уже существующих имён в разделе (в нижнем регистре)
                    try:
                        existing_rows = self._execute_with_error_handling(
                            "SELECT LOWER(name) AS name FROM category WHERE section_id = ?",
                            (section_id,),
                            fetch_method="all",
                        )
                        existing_names = {str(r["name"]).strip().lower() for r in (existing_rows or [])}
                    except Exception:
                        existing_names = set()

                    # Дубликаты внутри пакета для этой секции
                    seen_in_batch = set()

                    for it in group:
                        raw_name = it.get("name")
                        name_norm = (str(raw_name).strip().lower() if raw_name is not None else "")
                        # Пропускаем, если имя пустое — валидация выше, но на всякий случай
                        if not name_norm:
                            continue
                        # Пропускаем, если уже существует в БД или уже встречено в этом пакете
                        if name_norm in existing_names or name_norm in seen_in_batch:
                            continue
                        seen_in_batch.add(name_norm)

                        icon_path = it.get("icon_path", "")
                        batched_params.append((raw_name, section_id, icon_path, pos))
                        pos += 1

                # Вставляем одним executemany с тихим игнорированием дублей
                self._execute_many_with_error_handling(
                    "INSERT OR IGNORE INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                    batched_params,
                )

                # Единый запрос для всех пар (section_id, name)
                pairs: List[tuple] = []
                seen = set()
                for section_id, group in by_section.items():
                    for g in group:
                        name = g.get("name")
                        if name is None:
                            continue
                        key = (section_id, name)
                        if key in seen:
                            continue
                        seen.add(key)
                        pairs.append(key)

                if not pairs:
                    return []

                placeholders = ",".join(["(?, ?)"] * len(pairs))
                flat_params: List[Any] = []
                for sid, nm in pairs:
                    flat_params.extend([sid, nm])

                query = (
                    "SELECT id, name, section_id, position, icon_path "
                    "FROM category WHERE (section_id, name) IN (" + placeholders + ") "
                    "ORDER BY section_id, position"
                )
                rows = self._execute_with_error_handling(
                    query, tuple(flat_params), fetch_method="all"
                )
                return [dict(r) for r in (rows or [])]
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
        # Собираем затронутые разделы до удаления, чтобы потом переиндексировать позиции
        affected_sections: List[int] = []
        try:
            rows = self._execute_with_error_handling(
                f"SELECT DISTINCT section_id FROM category WHERE id IN ({placeholders})",
                tuple(unique_ids),
                fetch_method="all",
            )
            affected_sections = [int(r["section_id"]) for r in (rows or [])]
        except Exception:
            affected_sections = []

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

            # 3) Переиндексация позиций в затронутых разделах, чтобы убрать "дыры"
            # Выполняем внутри той же транзакции
            try:
                # Дедупликация и фильтр валидных id
                uniq_sections = list(dict.fromkeys([s for s in affected_sections if isinstance(s, int) and s > 0]))
                for sid in uniq_sections:
                    self._reindex_positions(sid)
            except Exception:
                # Не прерываем удаление, но логируем на верхнем уровне
                logger.warning("Не удалось переиндексировать позиции категорий после удаления")

        logger.info(
            f"Пакетно удалены категории (шт={deleted_categories}), ids={unique_ids}"
        )
        return deleted_categories

    def move_categories_to_section_bulk(
        self, category_ids: List[int], target_section_id: int, base_row: int = 0
    ) -> List[int]:
        """Атомарно переносит несколько категорий в целевой раздел одной транзакцией.

        - Пропускает категории, которые вызвали бы дубликат имени в целевом разделе
          (UNIQUE(section_id, name)).
        - Позиции для переносимых категорий назначаются последовательно, начиная с base_row.
        - Переиндексирует позиции в затронутых исходных разделах и в целевом разделе.

        Возвращает список фактически перенесённых id в порядке применения.
        """
        # Валидация входных данных
        if not category_ids or not isinstance(target_section_id, int) or target_section_id <= 0:
            return []

        # Оставляем только валидные положительные целые ID и удаляем дубликаты (сохраняя порядок)
        ids = [int(x) for x in category_ids if isinstance(x, int) and x > 0]
        unique_ids = list(dict.fromkeys(ids))
        if not unique_ids:
            return []

        # Получаем данные категорий (id, name, section_id, position), фильтруем существующие
        placeholders = ",".join(["?"] * len(unique_ids))
        rows = self._execute_with_error_handling(
            f"SELECT id, name, section_id, position FROM category WHERE id IN ({placeholders})",
            tuple(unique_ids),
            fetch_method="all",
        )
        if not rows:
            return []

        # Словарь по id
        data_by_id: dict[int, dict] = {int(r["id"]): dict(r) for r in rows}

        # Сортируем переносимые по их текущему порядку (section_id, position, id) для стабильности
        ordered_existing_ids = [cid for cid in unique_ids if cid in data_by_id]
        ordered_existing_ids.sort(
            key=lambda cid: (
                int(data_by_id[cid].get("section_id", 0) or 0),
                int(data_by_id[cid].get("position", 0) or 0),
                int(cid),
            )
        )

        # Имена, уже занятые в целевом разделе
        existing_names_rows = self._execute_with_error_handling(
            "SELECT LOWER(name) AS name FROM category WHERE section_id = ?",
            (target_section_id,),
            fetch_method="all",
        )
        existing_names = {str(r["name"]).strip().lower() for r in (existing_names_rows or [])}

        # Отфильтруем по дубликатам имён (в целевом разделе)
        to_move_ids: List[int] = []
        for cid in ordered_existing_ids:
            nm = str(data_by_id[cid].get("name", "")).strip().lower()
            # Если уже есть дубликат в целевом — пропускаем
            if nm in existing_names:
                continue
            to_move_ids.append(cid)
            existing_names.add(nm)  # зарезервировать имя, чтобы исключить повторы внутри набора

        if not to_move_ids:
            return []

        # Соберём исходные разделы для переиндексации после переноса
        source_sections = [int(data_by_id[cid].get("section_id", 0) or 0) for cid in to_move_ids]
        source_sections = [sid for sid in source_sections if sid and sid != target_section_id]
        uniq_source_sections = list(dict.fromkeys(source_sections))

        # Применяем обновления одной транзакцией
        with self.transaction():
            # Обновляем section_id и временные позиции для переносимых категорий
            updates = []
            pos = int(base_row) if isinstance(base_row, int) and base_row >= 0 else 0
            for cid in to_move_ids:
                updates.append((target_section_id, pos, cid))
                pos += 1
            self._execute_many_with_error_handling(
                "UPDATE category SET section_id = ?, position = ? WHERE id = ?",
                updates,
            )

            # Переиндексируем исходные разделы (закрыть дыры)
            try:
                for sid in uniq_source_sections:
                    self._reindex_positions(sid)
            except Exception:
                logger.warning("Не удалось переиндексировать исходные разделы после переноса", exc_info=False)

            # Переиндексируем целевой раздел, чтобы согласовать позиции
            try:
                self._reindex_positions(target_section_id)
            except Exception:
                logger.warning("Не удалось переиндексировать целевой раздел после переноса", exc_info=False)

        logger.info(
            f"Пакетный перенос категорий (шт={len(to_move_ids)}) в раздел {target_section_id}, ids={to_move_ids}"
        )
        return to_move_ids

    def _reindex_positions(self, section_id: int) -> None:
        """Переиндексировать поле position для всех категорий раздела последовательно от 0.

        Выполняется без собственного begin/commit, предполагая внешний контекст транзакции.
        """
        # Получаем id категорий в нужном порядке
        rows = self._execute_with_error_handling(
            "SELECT id FROM category WHERE section_id = ? ORDER BY position, id",
            (section_id,),
            fetch_method="all",
        )
        ids_in_order = [int(r["id"]) for r in (rows or [])]
        if not ids_in_order:
            return
        # Готовим батч обновлений позиций 0..n-1
        updates = [(pos, cid) for pos, cid in enumerate(ids_in_order)]
        self._execute_many_with_error_handling(
            "UPDATE category SET position = ? WHERE id = ?",
            updates,
        )

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
