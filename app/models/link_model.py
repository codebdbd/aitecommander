import datetime
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from app.utils.db.synchronization import db_lock

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
            with db_lock:
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
        with db_lock:
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
            with db_lock:
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
            with db_lock:
                for i, link_id in enumerate(link_ids):
                    self._execute_with_error_handling(
                        "UPDATE link SET position = ? WHERE id = ?", (i, link_id)
                    )
            self.commit()
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

        # Определяем полный набор полей, синхронно с upsert_link
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

        try:
            with self.transaction():
                for raw in links_data:
                    # Подготовка данных, аналогично upsert_link, но без промежуточных commit()
                    self._validate_required_fields(raw, ["category_id"], "ссылки")
                    data = {field: raw.get(field) for field in all_possible_fields}
                    data["is_favorite"] = int(data.get("is_favorite", 0) or 0)

                    if data.get("id"):
                        # Обновление существующей записи
                        if data["position"] is None:
                            data["position"] = 0
                        update_fields = [f for f in all_possible_fields if f != "id"]
                        update_placeholders = ", ".join([f"{f}=?" for f in update_fields])
                        update_values = [data[f] for f in update_fields]
                        cursor = self._execute_with_error_handling(
                            f"UPDATE link SET {update_placeholders} WHERE id=?",
                            tuple(update_values + [data["id"]]),
                        )
                        # Если не обновили ни одной строки — вставим с заданным ID (восстановление)
                        if cursor.rowcount == 0:
                            insert_fields = all_possible_fields
                            insert_placeholders = ", ".join(["?"] * len(insert_fields))
                            insert_values = [data[f] for f in insert_fields]
                            self._execute_with_error_handling(
                                f"INSERT INTO link ({', '.join(insert_fields)}) VALUES ({insert_placeholders})",
                                tuple(insert_values),
                            )
                    else:
                        # Новая запись — проверка на дубликат и вставка
                        # Назначим позицию только если не указана явно
                        if data.get("position") is None:
                            data["position"] = self._get_next_position(
                                "link", "category_id", data["category_id"]
                            )

                        # Тихая проверка дубликата (category_id,name,url,args)
                        existing = self.get_link_by_name_url_args(
                            data["category_id"],
                            data.get("name", ""),
                            data.get("url", ""),
                            data.get("args", ""),
                        )
                        if existing:
                            # Заполняем исходный словарь найденным id и пропускаем вставку
                            raw["id"] = existing.get("id")
                            continue

                        columns = [f for f in all_possible_fields if f != "id"]
                        placeholders = ", ".join(["?"] * len(columns))
                        values = [data[c] for c in columns]
                        cursor = self._execute_with_error_handling(
                            f"INSERT INTO link ({', '.join(columns)}) VALUES ({placeholders})",
                            tuple(values),
                        )
                        new_id = cursor.lastrowid
                        if new_id:
                            created_ids.append(new_id)
                            # Обновляем входные структуры, чтобы вызывающая сторона знала ID
                            raw["id"] = new_id
            return created_ids
        except sqlite3.IntegrityError as e:
            # Если что-то пошло не так с уникальностью — пробрасываем как DatabaseError
            raise DatabaseError(f"UNIQUE constraint failed during batch_upsert_links: {e}")
        except Exception as e:
            logger.error(f"Ошибка пакетного сохранения ссылок: {e}")
            raise

    def batch_delete_links(self, link_ids: List[int]) -> int:
        """Пакетное удаление ссылок по списку ID в одной транзакции.

        Возвращает количество фактически удалённых записей.
        """
        if not link_ids:
            return 0

        deleted = 0
        try:
            with self.transaction():
                for link_id in link_ids:
                    if not isinstance(link_id, int) or link_id <= 0:
                        continue
                    cursor = self._execute_with_error_handling(
                        "DELETE FROM link WHERE id = ?",
                        (link_id,),
                    )
                    try:
                        # rowcount поддерживается sqlite3 для execute
                        deleted += int(getattr(cursor, "rowcount", 0) or 0)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Ошибка пакетного удаления ссылок: {e}")
            raise DatabaseError(f"Не удалось выполнить пакетное удаление: {e}")
        return deleted
