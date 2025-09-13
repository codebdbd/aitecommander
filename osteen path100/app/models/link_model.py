import datetime
import logging
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from .db_base import DatabaseBase, DatabaseError
from .link_type import LinkType

logger = logging.getLogger(__name__)


class LinkModel(DatabaseBase):
    """Унифицированная модель для работы со ссылками в базе данных.

    Объединяет низкоуровневые операции с БД и высокоуровневые методы
    для удобной работы с ссылками.
    """

    def __init__(self, connection_manager):
        """Инициализирует LinkModel с менеджером соединений."""
        super().__init__(connection_manager)

    def get_links(
        self,
        category_id: int,
        *,
        fields: Optional[List[str]] = None,
        all_fields: bool = False,
    ) -> List[Dict[str, Any]]:
        """Возвращает список ссылок для указанной категории.

        Параметры:
        - fields: необязательный список полей для выборки. Игнорируется, если указан all_fields.
        - all_fields: если True — выбираются все столбцы (эквивалент прежнего get_links_for_category()).

        По умолчанию выбирается стабильный поднабор столбцов для UI:
        [id, category_id, name, url, type, notes, is_favorite, last_used, icon_path, args, browser_key, position].
        """
        try:
            # Белый список допустимых колонок для выборки (защита от SQL-инъекций и опечаток)
            ALLOWED_LINK_COLUMNS = {
                "id",
                "category_id",
                "name",
                "url",
                "type",
                "notes",
                "is_favorite",
                "last_used",
                "icon_path",
                "args",
                "browser_key",
                "position",
            }
            if all_fields:
                select_clause = "SELECT *"
            else:
                # Если передан конкретный список полей — используем его, иначе дефолтный поднабор как раньше
                default_fields = [
                    "id",
                    "category_id",
                    "name",
                    "url",
                    "type",
                    "notes",
                    "is_favorite",
                    "last_used",
                    "icon_path",
                    "args",
                    "browser_key",
                    "position",
                ]
                # Фильтрация пользовательских полей по белому списку
                use_fields_raw = list(fields or default_fields)
                use_fields = [
                    f
                    for f in use_fields_raw
                    if isinstance(f, str) and f in ALLOWED_LINK_COLUMNS
                ]
                # Логируем игнорируемые поля
                ignored = [
                    f
                    for f in use_fields_raw
                    if not (isinstance(f, str) and f in ALLOWED_LINK_COLUMNS)
                ]
                if ignored:
                    logger.warning(
                        "get_links: проигнорированы недопустимые поля %s; допустимые=%s",
                        ignored,
                        sorted(ALLOWED_LINK_COLUMNS),
                    )
                # Откат к дефолтному набору при пустом списке после фильтрации
                if not use_fields:
                    use_fields = list(default_fields)
                # Простой фолбэк на * только если по какой-то причине и дефолт пуст
                select_clause = (
                    f"SELECT {', '.join(use_fields)}" if use_fields else "SELECT *"
                )

            rows = self._execute_with_error_handling(
                f"{select_clause} FROM link WHERE category_id=? ORDER BY position ASC",
                (category_id,),
                fetch_method="all",
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(
                "Ошибка получения ссылок для категории %s: %s",
                category_id,
                e,
                exc_info=True,
            )
            raise

    def count_links_by_category(self, category_id: int) -> int:
        """Возвращает количество ссылок для указанной категории (эффективный подсчет)."""
        try:
            result = self._execute_with_error_handling(
                "SELECT COUNT(*) AS cnt FROM link WHERE category_id=?",
                (category_id,),
                fetch_method="one",
            )
            return int(result["cnt"]) if result else 0
        except Exception as e:
            logger.error(
                "Ошибка подсчета ссылок для категории %s: %s",
                category_id,
                e,
                exc_info=True,
            )
            return 0

    def count_links_by_categories(self, category_ids: List[int]) -> Dict[int, int]:
        """Возвращает словарь {category_id: count} для набора категорий одним запросом.

        Безопасно обрабатывает пустой список, возвращая пустой словарь. В случае ошибки
        возвращает пустой словарь и логирует проблему, сохраняя стабильность UI.
        """
        if not category_ids:
            return {}
        try:
            # Убираем дубликаты и некорректные значения
            ids = [int(cid) for cid in category_ids if isinstance(cid, int) and cid > 0]
            if not ids:
                return {}

            # Чанкирование для лимита параметров SQLite (~999)
            CHUNK = 900
            result: Dict[int, int] = {}
            for i in range(0, len(ids), CHUNK):
                chunk = ids[i : i + CHUNK]
                placeholders = ",".join(["?"] * len(chunk))
                rows = self._execute_with_error_handling(
                    f"SELECT category_id AS category_id, COUNT(*) AS cnt FROM link WHERE category_id IN ({placeholders}) GROUP BY category_id",
                    tuple(chunk),
                    fetch_method="all",
                )
                for r in rows or []:
                    try:
                        cat_id = int(r["category_id"])  # sqlite3.Row supports key access
                        cnt = int(r["cnt"])             # aggregated alias
                        result[cat_id] = result.get(cat_id, 0) + cnt
                    except Exception:
                        continue
            return result
        except Exception as e:
            logger.error(
                "Ошибка пакетного подсчета ссылок для категорий %s: %s",
                category_ids,
                e,
                exc_info=True,
            )
            return {}

    def upsert_link(self, link: Dict[str, Any]) -> int:
        """Вставляет или обновляет запись о ссылке. Возвращает ID записи.

        Транзакции не завершаются внутри метода. Коммит/роллбек выполняются
        вызывающей стороной (сервис/бизнес-слой) для возможности группировать
        несколько операций в одну атомарную транзакцию.
        """
        self._validate_required_fields(link, ["category_id"], "ссылки")

        all_possible_fields = [
            "id",
            "category_id",
            "name",
            "url",
            "type",
            "notes",
            "is_favorite",
            "last_used",
            "icon_path",
            "args",
            "position",
            "browser_key",
        ]

        # Создаем копию данных с учётом всех возможных полей
        data = {field: link.get(field) for field in all_possible_fields}
        data["is_favorite"] = int(data.get("is_favorite", 0) or 0)
        # Нормализация типа ссылки: Enum/строка -> строковое значение ('web', 'file', ...)
        try:
            data["type"] = LinkType.from_value(data.get("type", "web")).value
        except Exception:
            # Безопасный фолбэк
            data["type"] = LinkType.WEB.value

        logger.debug(
            "Upsert ссылки: %s, browser_key=%s",
            data.get("name", "Без названия"),
            data.get("browser_key"),
        )
        logger.debug("Upsert ссылки: полные данные=%s", data)

        try:
            if data["id"]:
                # Обновление или восстановление
                if data["position"] is None:
                    data["position"] = 0

                # Подготавливаем данные для обновления
                update_fields = [f for f in all_possible_fields if f != "id"]
                update_placeholders = ", ".join([f"{f}=?" for f in update_fields])
                update_values = [data[f] for f in update_fields]

                cursor = self._execute_with_error_handling(
                    f"UPDATE link SET {update_placeholders} WHERE id=?",
                    tuple(update_values + [data["id"]]),
                )

                # Если запись не была обновлена, вставляем новую с указанным ID
                if cursor.rowcount == 0:
                    insert_fields = all_possible_fields
                    insert_placeholders = ", ".join(["?"] * len(insert_fields))
                    insert_values = [data[f] for f in insert_fields]

                    self._execute_with_error_handling(
                        f"INSERT INTO link ({', '.join(insert_fields)}) VALUES ({insert_placeholders})",
                        tuple(insert_values),
                    )

                logger.debug(
                    "Обновлена ссылка с ID %s, browser_key=%s",
                    data["id"],
                    data.get("browser_key"),
                )
                return data["id"]
            else:
                # Новая запись
                data["position"] = self._get_next_position(
                    "link", "category_id", data["category_id"]
                )

                # Тихая обработка дубликатов по требованию:
                # Дубликат = совпадают Имя (name), Путь (url) и Аргумент (args) в рамках категории
                existing = self.get_link_by_name_url_args(
                    data["category_id"],
                    data.get("name", ""),
                    data.get("url", ""),
                    data.get("args", ""),
                )
                if existing:
                    # Молча возвращаем существующий ID без ошибок/предупреждений
                    return existing.get("id")

                columns = [f for f in all_possible_fields if f != "id"]
                placeholders = ", ".join(["?"] * len(columns))
                values = [data[c] for c in columns]

                cursor = self._execute_with_error_handling(
                    f"INSERT INTO link ({', '.join(columns)}) VALUES ({placeholders})",
                    tuple(values),
                )

                new_id = cursor.lastrowid
                logger.info(
                    "Добавлена новая ссылка: %s, browser_key=%s",
                    data.get("name", "Без названия"),
                    data.get("browser_key"),
                )
                logger.debug(
                    "Добавлена новая ссылка с ID %s, полные данные=%s",
                    new_id,
                    data,
                )
                return new_id
        except sqlite3.IntegrityError as e:
            # Молча игнорируем дубликаты по новой уникальности (category_id,name,url,args):
            # пытаемся найти уже существующую запись и вернуть её ID
            try:
                cat_id = link.get("category_id")
                name = link.get("name", "")
                url = link.get("url", "")
                args = link.get("args", "")
                row = self._execute_with_error_handling(
                    "SELECT id FROM link WHERE category_id=? AND name=? AND url=? AND args=?",
                    (cat_id, name, url, args),
                    fetch_method="one",
                )
                if row:
                    return int(dict(row)["id"])  # sqlite3.Row -> dict for stable key access
            except Exception as ee:
                logger.debug(
                    "upsert_link: failed to recover existing row after IntegrityError: %s",
                    ee,
                    exc_info=True,
                )
            # Если не нашли — пробрасываем как DatabaseError, но без лишнего шума
            raise DatabaseError(f"UNIQUE constraint failed: {e}")

    def get_link_by_unique_fields(
        self,
        category_id: int,
        url: str,
        args: str = "",
        link_type: str = "web",
        name: str = "",
    ):
        """Находит ссылку по уникальным полям (category_id, url, args, type, name).

        Примечание: одинаковые URL считаются дубликатами только если совпадают также args, type и имя ссылки.
        """
        try:
            row = self._execute_with_error_handling(
                "SELECT * FROM link WHERE category_id=? AND url=? AND args=? AND type=? AND name=?",
                (category_id, url, args, link_type, name),
                fetch_method="one",
            )
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(
                "Ошибка поиска ссылки по уникальным полям: %s", e, exc_info=True
            )
            return None

    def get_link_by_name_url_args(
        self, category_id: int, name: str, url: str, args: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Найти ссылку по тройке (Имя, Путь, Аргумент) внутри категории.

        Требование пользователя: дубликатом считается совпадение name, url, args в рамках category_id,
        тип (type) игнорируется для этой проверки.
        """
        try:
            row = self._execute_with_error_handling(
                "SELECT * FROM link WHERE category_id=? AND name=? AND url=? AND args=?",
                (category_id, name, url, args),
                fetch_method="one",
            )
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(
                "Ошибка поиска ссылки по (name,url,args): %s", e, exc_info=True
            )
            return None

    def get_all_links(self) -> List[Dict[str, Any]]:
        """Возвращает все ссылки из базы данных в виде списка словарей."""
        try:
            rows = self._execute_with_error_handling(
                "SELECT id, category_id, name, url, type, notes, "
                "is_favorite, last_used, icon_path, args, browser_key, position "
                "FROM link ORDER BY position ASC",
                fetch_method="all",
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Ошибка получения всех ссылок: %s", e, exc_info=True)
            raise

    def delete_link(self, link_id: int):
        """Удаляет ссылку по её ID."""
        try:
            self._execute_with_error_handling(
                "DELETE FROM link WHERE id= ?", (link_id,)
            )

            logger.info("Удалена ссылка с ID %s", link_id)
        except Exception as e:
            logger.error("Ошибка удаления ссылки: %s", e, exc_info=True)
            raise DatabaseError(f"Не удалось удалить ссылку: {e}")

    def update_link_last_used(self, link_id: int):
        """Обновляет время последнего использования для ссылки."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._execute_with_error_handling(
            "UPDATE link SET last_used = ? WHERE id = ?", (now, link_id)
        )

    def count_favorites(self) -> int:
        """Возвращает количество избранных ссылок."""
        row = self._execute_with_error_handling(
            "SELECT COUNT(*) AS cnt FROM link WHERE is_favorite=1",
            fetch_method="one",
        )
        return int(row["cnt"]) if row else 0

    def clear_favorites(self):
        """Сбрасывает признак избранного у всех ссылок."""
        try:
            self._execute_with_error_handling(
                "UPDATE link SET is_favorite=0 WHERE is_favorite=1"
            )

            logger.info("Очищены все избранные ссылки")
        except Exception as e:
            logger.error("Ошибка очистки избранного: %s", e)
            raise DatabaseError(f"Не удалось очистить избранное: {e}")

    def search_links(self, query: str):
        """Ищет ссылки по всему дереву, где имя, URL или заметки содержат подстроку запроса."""
        if not query:
            return []

        search_term = f"%{query}%"
        try:
            rows = self._execute_with_error_handling(
                "SELECT l.*, cat.name as category_name, sect.name as section_name, sph.name as sphere_name "
                "FROM link l "
                "JOIN category cat ON l.category_id = cat.id "
                "JOIN section sect ON cat.section_id = sect.id "
                "JOIN sphere sph ON sect.sphere_id = sph.id "
                "WHERE l.name LIKE ? COLLATE NOCASE "
                "OR l.url LIKE ? COLLATE NOCASE "
                "OR l.notes LIKE ? COLLATE NOCASE "
                "OR l.args LIKE ? COLLATE NOCASE "
                "ORDER BY l.name",
                (search_term, search_term, search_term, search_term),
                fetch_method="all",
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Ошибка поиска ссылок: %s", e)
            raise

    def get_links_by_args_pattern(self, pattern: str) -> List[Dict[str, Any]]:
        """Возвращает ссылки типа 'web', где args LIKE pattern.

        Пример pattern: '--profile-directory=%'
        """
        try:
            rows = self._execute_with_error_handling(
                "SELECT * FROM link WHERE type = 'web' AND args LIKE ?",
                (pattern,),
                fetch_method="all",
            )
            return [dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error("Ошибка выборки ссылок по шаблону args: %s", e)
            raise

    def update_link_notes(self, link_id: int, new_notes: str) -> None:
        """Обновляет поле notes для указанной ссылки."""
        try:
            self._execute_with_error_handling(
                "UPDATE link SET notes = ? WHERE id = ?",
                (new_notes, link_id),
            )

        except Exception as e:
            logger.error("Ошибка обновления заметок для ссылки %s: %s", link_id, e)
            raise

    def get_links_args_nonempty(self) -> List[Dict[str, Any]]:
        """Возвращает строки с непустыми args (только столбец args)."""
        try:
            rows = self._execute_with_error_handling(
                "SELECT args FROM link WHERE args IS NOT NULL AND TRIM(args) != ''",
                fetch_method="all",
            )
            return [dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error("Ошибка получения непустых args: %s", e)
            raise

    # === Высокоуровневые методы для удобства использования ===

    def get_recent_links(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получить недавние ссылки."""
        try:
            rows = self._execute_with_error_handling(
                """SELECT * FROM link 
                   WHERE last_used IS NOT NULL 
                   ORDER BY last_used DESC 
                   LIMIT ?""",
                (limit,),
                fetch_method="all",
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Ошибка получения недавних ссылок: %s", e, exc_info=True)
            raise

    def get_favorite_links(self) -> List[Dict[str, Any]]:
        """Получить избранные ссылки."""
        try:
            rows = self._execute_with_error_handling(
                "SELECT * FROM link WHERE is_favorite=? ORDER BY position",
                (1,),
                fetch_method="all",
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Ошибка получения избранных ссылок: %s", e, exc_info=True)
            raise

    def get_link_by_id(self, link_id: int) -> Optional[Dict[str, Any]]:
        """Получить ссылку по ID."""
        try:
            row = self._execute_with_error_handling(
                "SELECT * FROM link WHERE id = ?", (link_id,), fetch_method="one"
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error("Ошибка получения ссылки %s: %s", link_id, e, exc_info=True)
            raise

    def update_link_order(self, link_ids: List[int]) -> bool:
        """Обновить порядок ссылок."""
        try:
            with self.transaction():
                for i, link_id in enumerate(link_ids):
                    self._execute_with_error_handling(
                        "UPDATE link SET position = ? WHERE id = ?", (i, link_id)
                    )
            return True
        except Exception as e:
            logger.error("Ошибка обновления порядка ссылок: %s", e, exc_info=True)
            return False

    def batch_update_links(self, links_data: List[Dict[str, Any]]) -> bool:
        """Пакетное обновление ссылок в транзакции."""
        if not links_data:
            return True

        # Готовим параметры для executemany: только валидные записи с id
        params: List[tuple] = []
        for link_data in links_data:
            link_id = link_data.get("id")
            if not isinstance(link_id, int) or link_id <= 0:
                continue
            params.append(
                (
                    link_data.get("position"),
                    link_data.get("category_id"),
                    link_id,
                )
            )

        if not params:
            return True

        sql = "UPDATE link SET position = ?, category_id = ? WHERE id = ?"

        try:
            with self.transaction():
                cursor = self._execute_many_with_error_handling(sql, params)
                # rowcount может быть -1 для некоторых драйверов; оборачиваем безопасно
                try:
                    affected = int(getattr(cursor, "rowcount", 0) or 0)
                except Exception:
                    affected = 0
                # Опционально: если затронуто меньше, чем передано, можно залогировать
                if affected < len(params):
                    logger.debug(
                        "batch_update_links: обновлено строк %s из %s",
                        affected,
                        len(params),
                    )
            return True
        except Exception as e:
            logger.error("Ошибка пакетного обновления ссылок: %s", e, exc_info=True)
            raise

    def get_next_position(self, category_id: int) -> int:
        """Получить следующую позицию для новой ссылки в категории."""
        try:
            result = self._execute_with_error_handling(
                "SELECT COALESCE(MAX(position), 0) + 1 AS next_pos FROM link WHERE category_id = ?",
                (category_id,),
                fetch_method="one",
            )
            return int(result["next_pos"]) if result else 1
        except Exception as e:
            logger.error(
                "Ошибка получения следующей позиции для категории %s: %s",
                category_id,
                e,
                exc_info=True,
            )
            return 1

    # get_links_for_category был объединён с get_links (параметр all_fields=True)

    def batch_upsert_links(self, links_data: List[Dict[str, Any]]) -> List[int]:
        """Пакетное создание/обновление ссылок в одной транзакции.

        - Не выполняет commit после каждой записи — транзакция завершится единым commit.
        - Обновляет входные словари (links_data) установленными ID для новых записей.
        - Возвращает список ID, созданных в рамках этой операции (только для новых записей).
        """
        if not links_data:
            return []

        created_ids: List[int] = []
        try:
            with self.transaction():
                created_ids.extend(self._upsert_links_no_tx(links_data))
            return created_ids
        except sqlite3.IntegrityError as e:
            # Если что-то пошло не так с уникальностью — пробрасываем как DatabaseError
            raise DatabaseError(
                f"UNIQUE constraint failed during batch_upsert_links: {e}"
            )
        except Exception as e:
            logger.error("Ошибка пакетного сохранения ссылок: %s", e)
            raise

    # === Выделенные шаги для пакетного апсерта (без транзакции) ===

    def _normalize_and_group_links(
        self, links_data: List[Dict[str, Any]], all_fields: List[str]
    ) -> Dict[int, List[Dict[str, Any]]]:
        """Нормализует вход и группирует записи по `category_id`.

        - Валидирует обязательные поля.
        - Заполняет значения по умолчанию и приводит типы.
        - Обновляет входные элементы in-place.
        - Возвращает словарь {category_id: [items...]}
        """
        by_cat: Dict[int, List[Dict[str, Any]]] = {}
        for raw in links_data:
            self._validate_required_fields(raw, ["category_id"], "ссылки")
            data = {field: raw.get(field) for field in all_fields}
            data["name"] = data.get("name", "") or ""
            data["url"] = data.get("url", "") or ""
            data["args"] = data.get("args", "") or ""
            # Нормализуем тип к строке (на случай, если пришёл Enum)
            try:
                data["type"] = LinkType.from_value(data.get("type", "web")).value
            except Exception:
                data["type"] = LinkType.WEB.value
            data["notes"] = data.get("notes", "") or ""
            data["is_favorite"] = int(data.get("is_favorite", 0) or 0)
            data["icon_path"] = data.get("icon_path", "default.ico") or "default.ico"
            # position и browser_key оставляем как есть (могут быть None)

            raw.clear()
            raw.update(data)

            by_cat.setdefault(int(data["category_id"]), []).append(raw)
        return by_cat

    def _fetch_existing_maps(
        self, category_id: int
    ) -> Tuple[
        Dict[Tuple[str, str, str], Dict[str, Any]],
        Dict[int, Dict[str, Any]],
        int,
    ]:
        """Получает существующие ссылки и max(position) для категории.

        Возвращает кортеж (existing_by_key, existing_by_id, max_pos).
        key = (name, url, args)
        """
        rows = self._execute_with_error_handling(
            "SELECT id, name, url, args, position FROM link WHERE category_id=?",
            (category_id,),
            fetch_method="all",
        )

        existing_by_key: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        existing_by_id: Dict[int, Dict[str, Any]] = {}
        max_pos = -1
        for rid, rname, rurl, rargs, rpos in rows:
            existing_by_id[int(rid)] = {
                "id": int(rid),
                "name": rname or "",
                "url": rurl or "",
                "args": rargs or "",
                "position": rpos if rpos is not None else -1,
            }
            existing_by_key[(rname or "", rurl or "", rargs or "")] = existing_by_id[
                int(rid)
            ]
            if rpos is not None:
                try:
                    if int(rpos) > max_pos:
                        max_pos = int(rpos)
                except Exception:
                    pass
        return existing_by_key, existing_by_id, max_pos

    def _assign_positions_for_items(
        self, items: List[Dict[str, Any]], start_pos: int
    ) -> None:
        """Назначает позицию тем элементам, у кого она не задана."""
        next_pos = start_pos
        for item in items:
            if item.get("position") is None:
                item["position"] = next_pos
                next_pos += 1

    def _build_update_params(
        self,
        items: List[Dict[str, Any]],
        existing_by_key: Dict[Tuple[str, str, str], Dict[str, Any]],
    ) -> Tuple[List[Tuple[Any, ...]], List[Dict[str, Any]]]:
        """Формирует параметры для UPDATE и список вставок без id."""
        updates: List[Tuple[Any, ...]] = []
        inserts_no_id: List[Dict[str, Any]] = []
        for item in items:
            key = (item.get("name", ""), item.get("url", ""), item.get("args", ""))
            iid = item.get("id")
            if iid:
                updates.append(
                    (
                        item.get("category_id"),
                        item.get("name"),
                        item.get("url"),
                        item.get("type"),
                        item.get("notes"),
                        int(item.get("is_favorite", 0) or 0),
                        item.get("last_used"),
                        item.get("icon_path"),
                        item.get("args"),
                        item.get("browser_key"),
                        item.get("position", 0)
                        if item.get("position") is not None
                        else 0,
                        int(iid),
                    )
                )
            else:
                ex = existing_by_key.get(key)
                if ex:
                    item["id"] = ex["id"]
                    updates.append(
                        (
                            item.get("category_id"),
                            item.get("name"),
                            item.get("url"),
                            item.get("type"),
                            item.get("notes"),
                            int(item.get("is_favorite", 0) or 0),
                            item.get("last_used"),
                            item.get("icon_path"),
                            item.get("args"),
                            item.get("browser_key"),
                            item.get("position", 0)
                            if item.get("position") is not None
                            else 0,
                            ex["id"],
                        )
                    )
                else:
                    inserts_no_id.append(item)
        return updates, inserts_no_id

    def _execute_updates_collect_missing(
        self, updates: List[Tuple[Any, ...]]
    ) -> List[Dict[str, Any]]:
        """Выполняет пакетные UPDATE и собирает записи для последующей вставки с фиксированным id.

        Возвращает список словарей для вставки с заданным `id` (inserts_with_id).
        """
        inserts_with_id: List[Dict[str, Any]] = []
        if not updates:
            return inserts_with_id

        update_sql = (
            "UPDATE link SET category_id=?, name=?, url=?, type=?, notes=?, "
            "is_favorite=?, last_used=?, icon_path=?, args=?, browser_key=?, position=? WHERE id=?"
        )
        try:
            self.connection.executemany(update_sql, updates)
        except sqlite3.IntegrityError as e:
            raise DatabaseError(f"UNIQUE constraint failed during batch update: {e}")

        update_ids = [int(p[-1]) for p in updates]
        if update_ids:
            placeholders = ",".join(["?"] * len(update_ids))
            existed_rows = self._execute_with_error_handling(
                f"SELECT id FROM link WHERE id IN ({placeholders})",
                tuple(update_ids),
                fetch_method="all",
            )
            existed_ids = {
                int(r[0] if isinstance(r, tuple) else r["id"])
                for r in (existed_rows or [])
            }
            missing_ids = [iid for iid in update_ids if iid not in existed_ids]

            if missing_ids:
                params_by_id = {int(p[-1]): p for p in updates}
                for iid in missing_ids:
                    params = params_by_id.get(int(iid))
                    if not params:
                        continue
                    inserts_with_id.append(
                        {
                            "id": int(iid),
                            "category_id": params[0],
                            "name": params[1],
                            "url": params[2],
                            "type": params[3],
                            "notes": params[4],
                            "is_favorite": params[5],
                            "last_used": params[6],
                            "icon_path": params[7],
                            "args": params[8],
                            "browser_key": params[9],
                            "position": params[10],
                        }
                    )
        return inserts_with_id

    def _insert_records_with_id(
        self,
        inserts_with_id: List[Dict[str, Any]],
        all_fields: List[str],
        created_ids: List[int],
    ) -> None:
        """Вставляет записи с фиксированным id (executemany) и добавляет их в created_ids."""
        if not inserts_with_id:
            return
        insert_fields = all_fields
        placeholders = ", ".join(["?"] * len(insert_fields))
        params_with_id = [
            tuple(rec.get(f) for f in insert_fields) for rec in inserts_with_id
        ]
        try:
            # Используем защищённый executemany с удержанием db_lock
            self._execute_many_with_error_handling(
                f"INSERT INTO link ({', '.join(insert_fields)}) VALUES ({placeholders})",
                params_with_id,
            )
        except sqlite3.IntegrityError as e:
            raise DatabaseError(f"Integrity error on inserts_with_id: {e}")
        for rec in inserts_with_id:
            try:
                iid = int(rec.get("id") or 0)
                if iid:
                    created_ids.append(iid)
            except Exception:
                pass

    def _insert_records_no_id(
        self,
        inserts_no_id: List[Dict[str, Any]],
        all_fields: List[str],
        existing_by_key: Dict[Tuple[str, str, str], Dict[str, Any]],
        created_ids: List[int],
    ) -> None:
        """Поштучно вставляет записи без id, обновляет входные элементы и created_ids.

        Следует согласованному хотфиксу: без временной таблицы, поштучные INSERT.
        """
        if not inserts_no_id:
            return
        columns = [f for f in all_fields if f != "id"]
        placeholders = ", ".join(["?"] * len(columns))
        insert_sql = f"INSERT INTO link ({', '.join(columns)}) VALUES ({placeholders})"
        for rec in inserts_no_id:
            params = tuple(rec.get(c) for c in columns)
            try:
                cur = self._execute_with_error_handling(insert_sql, params)
                try:
                    new_id = int(getattr(cur, "lastrowid", 0) or 0)
                except Exception:
                    new_id = 0
                if new_id:
                    rec["id"] = new_id
                    key_simple = (
                        rec.get("name", ""),
                        rec.get("url", ""),
                        rec.get("args", ""),
                    )
                    if key_simple not in existing_by_key:
                        created_ids.append(new_id)
                        existing_by_key[key_simple] = {
                            "id": new_id,
                            "position": rec.get("position", 0),
                        }
            except sqlite3.IntegrityError:
                row = self._execute_with_error_handling(
                    "SELECT id FROM link WHERE category_id=? AND name=? AND url=? AND args=?",
                    (
                        rec.get("category_id"),
                        rec.get("name", ""),
                        rec.get("url", ""),
                        rec.get("args", ""),
                    ),
                    fetch_method="one",
                )
                if row:
                    rec["id"] = row[0] if isinstance(row, tuple) else row["id"]

    def _upsert_links_no_tx(self, links_data: List[Dict[str, Any]]) -> List[int]:
        """Внутренний хелпер: апсерт ссылок без открытия транзакции и без commit().

        - Идентичная логика batch_upsert_links, но предполагает внешнюю транзакцию.
        - Обновляет входные словари `links_data` установленными ID для новых записей.
        - Возвращает список созданных ID.
        """
        if not links_data:
            return []

        created_ids: List[int] = []

        # Поля должны оставаться синхронными с upsert_link
        all_fields = [
            "id",
            "category_id",
            "name",
            "url",
            "type",
            "notes",
            "is_favorite",
            "last_used",
            "icon_path",
            "args",
            "position",
            "browser_key",
        ]

        # 1) Нормализация и группировка
        by_cat = self._normalize_and_group_links(links_data, all_fields)

        # 2..6) Для каждой категории отрабатываем шаги отдельно
        for category_id, items in by_cat.items():
            existing_by_key, _existing_by_id, max_pos = self._fetch_existing_maps(
                category_id
            )

            # 3) Назначаем позиции, если не заданы
            self._assign_positions_for_items(items, max_pos + 1)

            # 4) Формируем обновления и вставки без id
            updates, inserts_no_id = self._build_update_params(items, existing_by_key)

            # 5) Выполняем обновления и собираем вставки с фиксированным id
            inserts_with_id = self._execute_updates_collect_missing(updates)

            # 6a) Выполняем вставки с фиксированным id
            self._insert_records_with_id(inserts_with_id, all_fields, created_ids)

            # 6b) Поштучные INSERT без id (согласованный хотфикс)
            self._insert_records_no_id(
                inserts_no_id, all_fields, existing_by_key, created_ids
            )

        return created_ids

    def batch_delete_links(self, link_ids: List[int]) -> int:
        """Пакетное удаление ссылок по списку ID в одной транзакции.

        Возвращает количество фактически удалённых записей.
        """
        if not link_ids:
            return 0

        # Фильтрация валидных положительных целых и дедупликация (с сохранением порядка)
        valid_ids = [int(x) for x in link_ids if isinstance(x, int) and x > 0]
        unique_ids = list(dict.fromkeys(valid_ids))
        if not unique_ids:
            return 0

        placeholders = ",".join(["?"] * len(unique_ids))
        try:
            with self.transaction():
                cursor = self._execute_with_error_handling(
                    f"DELETE FROM link WHERE id IN ({placeholders})",
                    tuple(unique_ids),
                )
                try:
                    deleted = int(getattr(cursor, "rowcount", 0) or 0)
                except Exception:
                    deleted = 0
            return deleted
        except Exception as e:
            logger.error("Ошибка пакетного удаления ссылок: %s", e)
            raise DatabaseError(f"Не удалось выполнить пакетное удаление: {e}")
