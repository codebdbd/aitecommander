"""
CategoryModel - модель для работы с категориями в базе данных.
"""

import logging
from typing import Any, Dict, List, Optional

from .db_base import DatabaseBase, ValidationError

logger = logging.getLogger(__name__)


class CategoryModel(DatabaseBase):
    """Модель для работы с категориями."""

    def __init__(self, database: Any) -> None:
        """Инициализация модели категорий."""
        super().__init__(database)

    def get_categories(self, section_id: int) -> List[Dict[str, Any]]:
        """Возвращает список категорий для указанного раздела в формате dict."""
        rows = self._execute_with_error_handling(
            "SELECT id, name, section_id, position, icon_path FROM category "
            "WHERE section_id=? ORDER BY position",
            (section_id,),
            fetch_method="all",
        )
        return [dict(row) for row in rows] if rows else []

    def get_categories_for_sections(self, section_ids: List[int]) -> List[Dict[str, Any]]:
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
        rows = self.fetch_all(query, tuple(section_ids))
        return [dict(r) for r in rows] if rows else []

    def get_category_by_id(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает категорию по её ID в формате dict."""
        row = self.fetch_one("SELECT * FROM category WHERE id= ?", (category_id,))
        return dict(row) if row else None

    def get_categories_bulk(self, ids: List[int]) -> List[Dict[str, Any]]:
        """Возвращает несколько категорий по списку ID одним запросом.

        Возвращает список dict с полями таблицы `category` (включая `icon_path`).
        Порядок не гарантируется.
        """
        if not ids:
            return []
        # Оставляем только валидные положительные целые ID (исключая bool) и удаляем дубликаты
        valid_ids = [int(x) for x in ids if isinstance(x, int) and not isinstance(x, bool) and x > 0]
        if not valid_ids:
            return []
        placeholders = ",".join(["?"] * len(valid_ids))
        rows = self.fetch_all(
            f"SELECT * FROM category WHERE id IN ({placeholders})",
            tuple(valid_ids),
        )
        try:
            return [dict(r) for r in rows] if rows else []
        except Exception:
            # На случай нестандартного курсора в тестах
            result: List[Dict[str, Any]] = []
            for r in rows or []:
                try:
                    result.append(dict(r))
                except Exception:
                    continue
            return result

    def get_category_hierarchy(self, category_id: int) -> Optional[Dict[str, int]]:
        """Получить иерархию категории (сфера -> раздел -> категория).

        Args:
            category_id: ID категории

        Returns:
            Dict с sphere_id, section_id, category_id или None при ошибке
        """
        result = self.fetch_one(
            """SELECT s.sphere_id, c.section_id 
               FROM category c 
               JOIN section s ON c.section_id = s.id 
               WHERE c.id = ?""",
            (category_id,),
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

        # Нормализация ввода: убираем лишние пробелы вокруг имени
        try:
            name_norm = str(data["name"]).strip()
        except Exception:
            name_norm = str(data["name"])  # на всякий случай
        data = dict(data)
        data["name"] = name_norm

        # Проверяем, существует ли уже категория с таким именем в этом разделе
        dup = self.fetch_one(
            "SELECT id FROM category WHERE section_id = ? AND name = ? COLLATE NOCASE",
            (data["section_id"], data["name"]),
        )
        if dup is not None:
            # Категория с таким именем уже существует в этом разделе
            logger.warning(
                "Категория '%s' уже существует в разделе %s",
                data["name"],
                data["section_id"],
            )
            return None

        position = self._get_next_position("category", "section_id", data["section_id"])
        cursor = self.exec_query(
            "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
            (data["name"], data["section_id"], data.get("icon_path", ""), position),
        )
        logger.info("Добавлена новая категория: %s", data["name"])
        return int(getattr(cursor, "lastrowid", 0) or 0)

    def insert_categories_bulk(
        self, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
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
            self._validate_required_fields(
                it or {}, ["name", "section_id"], "категории"
            )

        # Группируем по section_id для расчёта позиций
        by_section: Dict[int, List[Dict[str, Any]]] = {}
        for it in items:
            sec_val = it.get("section_id")
            if not isinstance(sec_val, int) or sec_val <= 0:
                raise ValidationError("Некорректный section_id в одном из элементов пакета")
            by_section.setdefault(int(sec_val), []).append(it)

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
                    rows = self.fetch_all(query, tuple(section_ids))
                    for row in rows:
                        max_pos_map[row["section_id"]] = row["max_pos"]

                # Единая предзагрузка существующих имён для всех затронутых разделов одним запросом
                existing_names_by_section: Dict[int, set] = {}
                if section_ids:
                    placeholders = ",".join(["?"] * len(section_ids))
                    query_names = (
                        f"SELECT section_id, LOWER(name) AS lname FROM category "
                        f"WHERE section_id IN ({placeholders})"
                    )
                    rows = self.fetch_all(query_names, tuple(section_ids))
                    for r in rows:
                        rv = r["section_id"]
                        if not isinstance(rv, int):
                            continue
                        nm = str(r["lname"]).strip().lower()
                        if not nm:
                            continue
                        existing_names_by_section.setdefault(int(rv), set()).add(nm)

                # Повторно обойдём сгруппированные элементы для формирования батча, используя предзагруженные имена
                for section_id, group in by_section.items():
                    # Стартовая позиция: (MAX(position) + 1) или 0, если записей нет
                    max_pos = max_pos_map.get(section_id)
                    start_pos = (max_pos + 1) if (max_pos is not None) else 0
                    pos = start_pos
                    existing_names = existing_names_by_section.get(section_id, set())

                    # Дубликаты внутри пакета для этой секции
                    seen_in_batch = set()

                    for it in group:
                        raw_name = it.get("name")
                        # Канонизируем для сравнения и хранения: удаляем пробелы по краям.
                        # Для сравнения используем lower(), но храним в оригинальном регистре без пробелов.
                        name_canon = str(raw_name).strip() if raw_name is not None else ""
                        name_norm = name_canon.lower()
                        # Пропускаем, если имя пустое — валидация выше, но на всякий случай
                        if not name_norm:
                            continue
                        # Пропускаем, если уже существует в БД или уже встречено в этом пакете
                        if name_norm in existing_names or name_norm in seen_in_batch:
                            continue
                        seen_in_batch.add(name_norm)

                        icon_path = it.get("icon_path", "")
                        batched_params.append((name_canon, section_id, icon_path, pos))
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
                        raw_name = g.get("name")
                        if raw_name is None:
                            continue
                        # Поиск должен использовать канонизированное имя (без пробелов по краям),
                        # так как мы именно его сохраняем в БД.
                        nm_canon = str(raw_name).strip()
                        key = (section_id, nm_canon)
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
                rows = self.fetch_all(query, tuple(flat_params))
                return [dict(r) for r in rows]
        except Exception:
            # Инициируем откат и пробрасываем далее
            raise

    def update_category(self, category_id: int, data: Dict[str, Any]) -> None:
        """Обновляет существующую категорию."""
        return self._update_entity(
            "category",
            category_id,
            data,
            ["name", "section_id", "icon_path", "position"],
        )

    def delete_category(self, category_id: int) -> None:
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
        logger.info("Удалена категория с ID %s и все её ссылки", category_id)

    def delete_categories_bulk(self, category_ids: List[int]) -> int:
        """Пакетное удаление нескольких категорий (и их ссылок) в одной транзакции.

        Возвращает количество удалённых категорий. Игнорирует невалидные ID.
        """
        if not category_ids:
            return 0

        # Оставляем только валидные положительные целые ID (исключая bool) и удаляем дубликаты
        ids = [
            int(x)
            for x in category_ids
            if isinstance(x, int) and not isinstance(x, bool) and x > 0
        ]
        # Дедупликация с сохранением порядка первой встречаемости
        unique_ids = list(dict.fromkeys(ids))
        if not unique_ids:
            return 0

        # Чанкирование для соблюдения лимита параметров SQLite (~999)
        CHUNK = 900

        # 0) Собираем затронутые разделы чанками
        affected_sections: List[int] = []
        for i in range(0, len(unique_ids), CHUNK):
            chunk = unique_ids[i : i + CHUNK]
            placeholders = ",".join(["?"] * len(chunk))
            rows = self.fetch_all(
                f"SELECT DISTINCT section_id FROM category WHERE id IN ({placeholders})",
                tuple(chunk),
            )
            affected_sections.extend(int(r["section_id"]) for r in rows)

        deleted_categories = 0
        with self.transaction():
            # 1) Удаляем ссылки и категории чанками, чтобы не превысить лимит параметров
            for i in range(0, len(unique_ids), CHUNK):
                chunk = unique_ids[i : i + CHUNK]
                placeholders = ",".join(["?"] * len(chunk))
                # Удаляем ссылки для категорий чанка. Результат курсора не используется,
                # поэтому используем низкоуровневый вызов с обработкой ошибок без требования
                # реального sqlite3.Cursor (важно для тестов со стабами).
                self._execute_with_error_handling(
                    f"DELETE FROM link WHERE category_id IN ({placeholders})",
                    tuple(chunk),
                )
                # Предварительно считаем количество записей категорий в чанке,
                # чтобы иметь точную величину на случай отсутствия cursor.rowcount
                pre_count_row = self.fetch_one(
                    f"SELECT COUNT(*) as cnt FROM category WHERE id IN ({placeholders})",
                    tuple(chunk),
                )
                if pre_count_row is None:
                    pre_count = 0
                else:
                    try:
                        pre_count = int(dict(pre_count_row).get("cnt", 0))
                    except Exception:
                        pre_count = 0

                # Удаляем сами категории. Используем низкоуровневое выполнение, чтобы в тестах
                # можно было вернуть стаб-курсор без реального соединения; rowcount может отсутствовать.
                cursor = self._execute_with_error_handling(
                    f"DELETE FROM category WHERE id IN ({placeholders})",
                    tuple(chunk),
                )
                try:
                    # Предпочитаем использовать фактический rowcount, если он доступен
                    rc = getattr(cursor, "rowcount")
                    deleted_categories += int(rc)
                except AttributeError:
                    # Логируем отсутствие rowcount и используем предварительный подсчёт
                    logger.warning(
                        "delete_categories_bulk: cursor.rowcount not available; using pre-count (%s) for chunk %s",
                        pre_count,
                        chunk,
                    )
                    deleted_categories += pre_count

            # 2) Переиндексация позиций в затронутых разделах, чтобы убрать "дыры"
            try:
                # Дедупликация и фильтр валидных id
                uniq_sections = list(
                    dict.fromkeys(
                        [s for s in affected_sections if isinstance(s, int) and s > 0]
                    )
                )
                for sid in uniq_sections:
                    self._reindex_positions(sid)
            except Exception:
                # Не прерываем удаление, но логируем на верхнем уровне
                logger.warning(
                    "Не удалось переиндексировать позиции категорий после удаления"
                )

        logger.info(
            "Пакетно удалены категории (шт=%s), ids=%s",
            deleted_categories,
            unique_ids,
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
        if (
            not category_ids
            or not isinstance(target_section_id, int)
            or target_section_id <= 0
        ):
            return []

        # Оставляем только валидные положительные целые ID (исключая bool) и удаляем дубликаты (сохраняя порядок)
        ids = [
            int(x)
            for x in category_ids
            if isinstance(x, int) and not isinstance(x, bool) and x > 0
        ]
        unique_ids = list(dict.fromkeys(ids))
        if not unique_ids:
            return []

        # Получаем данные категорий (id, name, section_id, position), фильтруем существующие
        placeholders = ",".join(["?"] * len(unique_ids))
        rows = self.fetch_all(
            f"SELECT id, name, section_id, position FROM category WHERE id IN ({placeholders})",
            tuple(unique_ids),
        )
        if not rows:
            return []

        # Словарь по id
        data_by_id: dict[int, dict] = {int(r["id"]): dict(r) for r in rows}

        # Сохраняем порядок, заданный пользователем (последовательность unique_ids)
        ordered_existing_ids = [cid for cid in unique_ids if cid in data_by_id]

        # Имена, уже занятые в целевом разделе
        existing_names_rows = self.fetch_all(
            "SELECT LOWER(name) AS name FROM category WHERE section_id = ?",
            (target_section_id,),
        )
        existing_names = {
            str(r["name"]).strip().lower() for r in existing_names_rows
        }

        # Отфильтруем по дубликатам имён (в целевом разделе)
        to_move_ids: List[int] = []
        for cid in ordered_existing_ids:
            nm = str(data_by_id[cid].get("name", "")).strip().lower()
            # Если уже есть дубликат в целевом — пропускаем
            if nm in existing_names:
                continue
            to_move_ids.append(cid)
            existing_names.add(
                nm
            )  # зарезервировать имя, чтобы исключить повторы внутри набора

        if not to_move_ids:
            return []

        # Соберём исходные разделы для переиндексации после переноса
        source_sections = [
            int(data_by_id[cid].get("section_id", 0) or 0) for cid in to_move_ids
        ]
        source_sections = [
            sid for sid in source_sections if sid and sid != target_section_id
        ]
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
                logger.warning(
                    "Не удалось переиндексировать исходные разделы после переноса",
                    exc_info=False,
                )

            # Переиндексируем целевой раздел, чтобы согласовать позиции
            try:
                self._reindex_positions(target_section_id)
            except Exception:
                logger.warning(
                    "Не удалось переиндексировать целевой раздел после переноса",
                    exc_info=False,
                )

        logger.info(
            f"Пакетный перенос категорий (шт={len(to_move_ids)}) в раздел {target_section_id}, ids={to_move_ids}"
        )
        return to_move_ids

    def _reindex_positions(self, section_id: int) -> None:
        """Переиндексировать поле position для всех категорий раздела последовательно от 0.

        Выполняется без собственного begin/commit, предполагая внешний контекст транзакции.
        """
        # Получаем id категорий в нужном порядке
        rows = self.fetch_all(
            "SELECT id FROM category WHERE section_id = ? ORDER BY position, id",
            (section_id,),
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
        # Канонизируем имя: убираем пробелы по краям
        data = dict(category_data)  # не мутируем входящий dict
        if "name" in data:
            try:
                data["name"] = str(data["name"]).strip()
            except Exception:
                data["name"] = str(data["name"])

        if "id" in data and data["id"]:
            # Выполняем атомарно под транзакцией и единым механизмом блокировки
            with self.transaction():
                cursor = self.exec_query(
                    "UPDATE category SET name=?, section_id=?, icon_path=?, position=? WHERE id= ?",
                    (
                        data["name"],
                        data["section_id"],
                        data.get("icon_path", ""),
                        data.get("position", 0),
                        data["id"],
                    ),
                )
                if int(getattr(cursor, "rowcount", 0) or 0) == 0:
                    # Записи не было, делаем вставку с нужным id
                    self.exec_query(
                        "INSERT INTO category (id, name, section_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                        (
                            data["id"],
                            data["name"],
                            data["section_id"],
                            data.get("icon_path", ""),
                            data.get("position", 0),
                        ),
                    )
            return data["id"]
        else:
            category_id = self.insert_category(data)
            if category_id is None:
                raise ValueError(
                    f"Категория с именем '{data['name']}' уже существует в этом разделе"
                )
            return category_id

    def get_first_category_id(self) -> Optional[int]:
        """Возвращает первую категорию в системе."""
        result = self.fetch_one("SELECT id FROM category ORDER BY id LIMIT 1")
        return int(dict(result).get("id", 0)) if result else None

    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: Optional[int] = None
    ) -> bool:
        """Проверяет наличие дубликата категории в разделе."""
        # Проверка на дубликат без учета регистра
        query = (
            "SELECT COUNT(*) as count FROM category WHERE section_id = ? AND name = ? COLLATE NOCASE"
        )
        # Нормализуем вход для предсказуемости поведения
        try:
            category_name = str(category_name).strip()
        except Exception:
            category_name = str(category_name)
        params: tuple[Any, ...] = (section_id, category_name)

        if exclude_id is not None:
            query += " AND id != ?"
            params = (section_id, category_name, exclude_id)

        result = self.fetch_one(query, params)
        if not result:
            return False
        try:
            cnt = int(dict(result).get("count", 0))
        except Exception:
            cnt = 0
        return cnt > 0
