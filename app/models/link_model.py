import datetime
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from .db_base import DatabaseBase, DatabaseError

logger = logging.getLogger(__name__)


class LinkModel(DatabaseBase):
    """Унифицированная модель для работы со ссылками в базе данных.

    Объединяет низкоуровневые операции с БД и высокоуровневые методы
    для удобной работы с ссылками.
    """

    def __init__(self, connection_manager):
        """Инициализирует LinkModel с менеджером соединений."""
        super().__init__(connection_manager)

    def get_links(self, category_id: int):
        """Возвращает список ссылок для указанной категории."""
        try:
            rows = self._execute_with_error_handling(
                "SELECT id, category_id, name, url, type, notes, "
                "is_favorite, last_used, icon_path, args, browser_key, position "
                "FROM link WHERE category_id=? ORDER BY position DESC",
                (category_id,),
                fetch_method="all",
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения ссылок для категории {category_id}: {e}")
            raise

    def count_links_by_category(self, category_id: int) -> int:
        """Возвращает количество ссылок для указанной категории (эффективный подсчет)."""
        try:
            result = self._execute_with_error_handling(
                "SELECT COUNT(*) FROM link WHERE category_id=?",
                (category_id,),
                fetch_method="one",
            )
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Ошибка подсчета ссылок для категории {category_id}: {e}")
            return 0

    def upsert_link(self, link: Dict[str, Any]) -> int:
        """Вставляет или обновляет запись о ссылке. Возвращает ID записи."""
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

        logger.debug(
            f"Upsert ссылки: {data.get('name', 'Без названия')}, browser_key={data.get('browser_key')}"
        )
        logger.debug(f"Upsert ссылки: полные данные={data}")

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
                self.commit()

                # Если запись не была обновлена, вставляем новую с указанным ID
                if cursor.rowcount == 0:
                    insert_fields = all_possible_fields
                    insert_placeholders = ", ".join(["?"] * len(insert_fields))
                    insert_values = [data[f] for f in insert_fields]

                    self._execute_with_error_handling(
                        f"INSERT INTO link ({', '.join(insert_fields)}) VALUES ({insert_placeholders})",
                        tuple(insert_values),
                    )
                    self.commit()

                logger.debug(
                    f"Обновлена ссылка с ID {data['id']}, browser_key={data.get('browser_key')}"
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
                self.commit()
                new_id = cursor.lastrowid
                logger.info(
                    f"Добавлена новая ссылка: {data.get('name', 'Без названия')}, browser_key={data.get('browser_key')}"
                )
                logger.debug(
                    f"Добавлена новая ссылка с ID {new_id}, полные данные={data}"
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
                    return row[0] if isinstance(row, tuple) else row["id"]
            except Exception:
                pass
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
            logger.error(f"Ошибка поиска ссылки по уникальным полям: {e}")
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
            logger.error(f"Ошибка поиска ссылки по (name,url,args): {e}")
            return None

    def get_all_links(self) -> List[Dict[str, Any]]:
        """Возвращает все ссылки из базы данных в виде списка словарей."""
        try:
            rows = self._execute_with_error_handling(
                "SELECT id, category_id, name, url, type, notes, "
                "is_favorite, last_used, icon_path, args, browser_key, position "
                "FROM link ORDER BY position DESC",
                fetch_method="all",
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения всех ссылок: {e}")
            raise

    def delete_link(self, link_id: int):
        """Удаляет ссылку по её ID."""
        try:
            self._execute_with_error_handling(
                "DELETE FROM link WHERE id= ?", (link_id,)
            )
            self.commit()
            logger.info(f"Удалена ссылка с ID {link_id}")
        except Exception as e:
            logger.error(f"Ошибка удаления ссылки: {e}")
            raise DatabaseError(f"Не удалось удалить ссылку: {e}")

    def update_link_last_used(self, link_id: int):
        """Обновляет время последнего использования для ссылки."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._execute_with_error_handling(
            "UPDATE link SET last_used = ? WHERE id = ?", (now, link_id)
        )
        self.commit()

    def count_favorites(self) -> int:
        """Возвращает количество избранных ссылок."""
        cursor = self._execute_with_error_handling(
            "SELECT COUNT(*) FROM link WHERE is_favorite=1", fetch_method="one"
        )
        return cursor[0]

    def clear_favorites(self):
        """Сбрасывает признак избранного у всех ссылок."""
        try:
            self._execute_with_error_handling(
                "UPDATE link SET is_favorite=0 WHERE is_favorite=1"
            )
            self.commit()
            logger.info("Очищены все избранные ссылки")
        except Exception as e:
            logger.error(f"Ошибка очистки избранного: {e}")
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
            logger.error(f"Ошибка поиска ссылок: {e}")
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
            logger.error(f"Ошибка выборки ссылок по шаблону args: {e}")
            raise

    def update_link_notes(self, link_id: int, new_notes: str) -> None:
        """Обновляет поле notes для указанной ссылки."""
        try:
            self._execute_with_error_handling(
                "UPDATE link SET notes = ? WHERE id = ?",
                (new_notes, link_id),
            )
            self.commit()
        except Exception as e:
            logger.error(f"Ошибка обновления заметок для ссылки {link_id}: {e}")
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
            logger.error(f"Ошибка получения непустых args: {e}")
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
            logger.error(f"Ошибка получения недавних ссылок: {e}")
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
            logger.error(f"Ошибка получения избранных ссылок: {e}")
            raise

    def get_link_by_id(self, link_id: int) -> Optional[Dict[str, Any]]:
        """Получить ссылку по ID."""
        try:
            row = self._execute_with_error_handling(
                "SELECT * FROM link WHERE id = ?", (link_id,), fetch_method="one"
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка получения ссылки {link_id}: {e}")
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
            logger.error(f"Ошибка обновления порядка ссылок: {e}")
            return False

    def batch_update_links(self, links_data: List[Dict[str, Any]]) -> bool:
        """Пакетное обновление ссылок в транзакции."""
        if not links_data:
            return True

        try:
            with self.transaction():
                for link_data in links_data:
                    link_id = link_data.get("id")
                    if not link_id:
                        continue
                    self._execute_with_error_handling(
                        "UPDATE link SET position = ?, category_id = ? WHERE id = ?",
                        (
                            link_data.get("position"),
                            link_data.get("category_id"),
                            link_id,
                        ),
                    )
            return True
        except Exception as e:
            logger.error(f"Ошибка пакетного обновления ссылок: {e}")
            raise

    def get_next_position(self, category_id: int) -> int:
        """Получить следующую позицию для новой ссылки в категории."""
        try:
            result = self._execute_with_error_handling(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM link WHERE category_id = ?",
                (category_id,),
                fetch_method="one",
            )
            return result[0] if result else 1
        except Exception as e:
            logger.error(
                f"Ошибка получения следующей позиции для категории {category_id}: {e}"
            )
            return 1

    def get_links_for_category(self, category_id: int) -> List[Dict[str, Any]]:
        """Получить все ссылки для указанной категории."""
        try:
            rows = self._execute_with_error_handling(
                "SELECT * FROM link WHERE category_id = ? ORDER BY position",
                (category_id,),
                fetch_method="all",
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения ссылок для категории {category_id}: {e}")
            return []

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
            raise DatabaseError(f"UNIQUE constraint failed during batch_upsert_links: {e}")
        except Exception as e:
            logger.error(f"Ошибка пакетного сохранения ссылок: {e}")
            raise

    def _upsert_links_no_tx(self, links_data: List[Dict[str, Any]]) -> List[int]:
        """Внутренний хелпер: апсерт ссылок без открытия транзакции и без commit().

        - Идентичная логика batch_upsert_links, но предполагает внешнюю транзакцию.
        - Обновляет входные словари `links_data` установленными ID для новых записей.
        - Возвращает список созданных ID.
        """
        if not links_data:
            return []

        created_ids: List[int] = []

        # Определяем полный набор полей, синхронно с upsert_link
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

        # 1) Валидация и нормализация входа, группировка по category_id
        by_cat: Dict[int, List[Dict[str, Any]]] = {}
        for raw in links_data:
            self._validate_required_fields(raw, ["category_id"], "ссылки")
            # Нормализуем значения и оставим только ожидаемые поля
            data = {field: raw.get(field) for field in all_fields}
            data["name"] = data.get("name", "") or ""
            data["url"] = data.get("url", "") or ""
            data["args"] = data.get("args", "") or ""
            data["type"] = data.get("type", "web") or "web"
            data["notes"] = data.get("notes", "") or ""
            data["is_favorite"] = int(data.get("is_favorite", 0) or 0)
            data["icon_path"] = data.get("icon_path", "default.ico") or "default.ico"
            # position и browser_key оставляем как есть (могут быть None)

            raw.clear()
            raw.update(data)  # Сохраняем нормализованные данные обратно во входную структуру

            by_cat.setdefault(int(data["category_id"]), []).append(raw)

        # 2) Для каждой категории одним запросом получаем существующие ссылки и max(position)
        for category_id, items in by_cat.items():
            rows = self._execute_with_error_handling(
                "SELECT id, name, url, args, position FROM link WHERE category_id=?",
                (category_id,),
            ).fetchall()

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
                existing_by_key[(rname or "", rurl or "", rargs or "")] = existing_by_id[int(rid)]
                if rpos is not None:
                    try:
                        if int(rpos) > max_pos:
                            max_pos = int(rpos)
                    except Exception:
                        pass

            # 3) Рассчитываем позиции для тех, у кого position не задан
            next_pos = max_pos + 1
            for item in items:
                if item.get("position") is None:
                    item["position"] = next_pos
                    next_pos += 1

            # 4) Разделяем операции на обновления и вставки
            updates: List[Tuple[Any, ...]] = []
            inserts_no_id: List[Dict[str, Any]] = []
            inserts_with_id: List[Dict[str, Any]] = []

            for item in items:
                key = (item.get("name", ""), item.get("url", ""), item.get("args", ""))
                iid = item.get("id")

                if iid:
                    # Попытка обновления по id; если не существует — позже вставим с заданным id
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
                            item.get("position", 0) if item.get("position") is not None else 0,
                            int(iid),
                        )
                    )
                else:
                    # Нет id — проверим дубликат по ключу
                    ex = existing_by_key.get(key)
                    if ex:
                        # Свяжем с существующей записью
                        item["id"] = ex["id"]
                        # Выполним обновление значимых полей
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
                                item.get("position", 0) if item.get("position") is not None else 0,
                                ex["id"],
                            )
                        )
                    else:
                        inserts_no_id.append(item)

            # 5) Выполняем батч-обновления (executemany)
            if updates:
                update_sql = (
                    "UPDATE link SET category_id=?, name=?, url=?, type=?, notes=?, "
                    "is_favorite=?, last_used=?, icon_path=?, args=?, browser_key=?, position=? WHERE id=?"
                )
                try:
                    cur = self.connection.executemany(update_sql, updates)
                except sqlite3.IntegrityError as e:
                    raise DatabaseError(f"UNIQUE constraint failed during batch update: {e}")

                # Определяем какие id отсутствуют после обновления одним запросом IN (...)
                update_ids = [int(p[-1]) for p in updates]
                if update_ids:
                    placeholders = ",".join(["?"] * len(update_ids))
                    existed_rows = self._execute_with_error_handling(
                        f"SELECT id FROM link WHERE id IN ({placeholders})",
                        tuple(update_ids),
                        fetch_method="all",
                    )
                    existed_ids = {int(r[0] if isinstance(r, tuple) else r["id"]) for r in (existed_rows or [])}
                    missing_ids = [iid for iid in update_ids if iid not in existed_ids]

                    if missing_ids:
                        # Подготовим записи к вставке с фиксированным id на базе исходных параметров updates
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

            # 6) Вставки: сначала с фиксированным id (executemany), затем массовая вставка без id через временную таблицу
            if inserts_with_id:
                insert_fields = all_fields
                placeholders = ", ".join(["?"] * len(insert_fields))
                params_with_id = [tuple(rec.get(f) for f in insert_fields) for rec in inserts_with_id]
                try:
                    self.connection.executemany(
                        f"INSERT INTO link ({', '.join(insert_fields)}) VALUES ({placeholders})",
                        params_with_id,
                    )
                except sqlite3.IntegrityError as e:
                    raise DatabaseError(f"Integrity error on inserts_with_id: {e}")
                # Добавляем созданные фиксированные ID
                for rec in inserts_with_id:
                    try:
                        iid = int(rec.get("id") or 0)
                        if iid:
                            created_ids.append(iid)
                    except Exception:
                        pass

            if inserts_no_id:
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
                            key_simple = (rec.get("name", ""), rec.get("url", ""), rec.get("args", ""))
                            if key_simple not in existing_by_key:
                                created_ids.append(new_id)
                                # Обновим карту существующих, чтобы исключить повторные вставки в рамках категории
                                existing_by_key[key_simple] = {"id": new_id, "position": rec.get("position", 0)}
                    except sqlite3.IntegrityError:
                        # На случай гонки/погрешности, попробуем получить id существующей записи
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
            logger.error(f"Ошибка пакетного удаления ссылок: {e}")
            raise DatabaseError(f"Не удалось выполнить пакетное удаление: {e}")
