import logging
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, List

from app.utils.db.synchronization import db_lock

# Настройка логирования
logger = logging.getLogger(__name__)

# Валидные таблицы для операций с позициями
VALID_POSITION_TABLES = {"sphere", "section", "category", "link"}


class DatabaseError(Exception):
    """Базовый класс для ошибок базы данных"""

    pass


class ValidationError(DatabaseError):
    """Ошибка валидации данных"""

    pass


class DatabaseBase:
    """Базовый класс для моделей БД с единым доступом к соединению и операциям."""

    def __init__(self, connection_manager):
        """Инициализирует базовый класс с менеджером соединения (Database)."""
        self.connection_manager = connection_manager

    @property
    def connection(self):
        """Возвращает активное соединение SQLite через менеджер."""
        return self.connection_manager.connection

    def commit(self) -> None:
        """Фиксирует текущую транзакцию."""
        try:
            with db_lock:
                self.connection.commit()
        except sqlite3.Error as e:
            logger.error(f"Ошибка commit: {e}")
            raise DatabaseError(f"Ошибка commit: {e}")

    def rollback(self) -> None:
        """Откатывает текущую транзакцию."""
        try:
            with db_lock:
                self.connection.rollback()
        except sqlite3.Error as e:
            logger.error(f"Ошибка rollback: {e}")
            raise DatabaseError(f"Ошибка rollback: {e}")

    @contextmanager
    def transaction(self):
        """Контекстный менеджер транзакции с автоматическим commit/rollback.

        Теперь глобальная блокировка `db_lock` удерживается на ПРОТЯЖЕНИИ
        всего блока транзакции (включая тело `with ...:`), что обеспечивает
        эксклюзивный доступ к БД и исключает вмешательство других потоков
        между BEGIN/COMMIT/ROLLBACK.

        Примечания:
        - `db_lock` реентерабельный (RLock), поэтому вложенные вызовы, которые
          также используют `db_lock`, безопасны и не приводят к дедлокам.
        - Внутри блока не следует открывать вложенные транзакции на уровне SQLite,
          используйте один общий блок или SAVEPOINT при необходимости.
        """
        with db_lock:
            try:
                self.connection.execute("BEGIN TRANSACTION")
                yield
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    def _validate_required_fields(
        self, data: Dict[str, Any], required_fields: List[str], entity_name: str = ""
    ):
        """Валидирует обязательные поля"""
        # Отложенный импорт для предотвращения циклических импортов
        from app.utils.validators import validate_required_fields

        if not validate_required_fields(data, required_fields, entity_name):
            raise ValidationError(
                f"Отсутствуют обязательные поля для {entity_name}: {[field for field in required_fields if field not in data]}"
            )

    def _get_next_position(
        self, table_name: str, parent_field: str = None, parent_id: int = None
    ) -> int:
        """Получает следующую позицию для элемента в таблице."""
        try:
            if parent_field and parent_id is not None:
                row = self._execute_with_error_handling(
                    f"SELECT MAX(position) AS max_pos FROM {table_name} WHERE {parent_field} = ?",
                    (parent_id,),
                    fetch_method="one",
                )
            else:
                row = self._execute_with_error_handling(
                    f"SELECT MAX(position) AS max_pos FROM {table_name}",
                    fetch_method="one",
                )

            max_pos = None if row is None else row["max_pos"] if isinstance(row, dict) else row[0]
            return (max_pos + 1) if max_pos is not None else 0
        except Exception as e:
            logger.error(f"Ошибка получения позиции для таблицы {table_name}: {e}")
            return 0

    def _execute_with_error_handling(
        self, query: str, params: tuple = (), fetch_method: str = None
    ):
        """Выполняет SQL-запрос с обработкой ошибок и блокировкой."""
        try:
            with db_lock:
                cursor = self.connection.execute(query, params)
            if fetch_method == "one":
                return cursor.fetchone()
            elif fetch_method == "all":
                return cursor.fetchall()
            return cursor
        except sqlite3.Error as e:
            logger.error(f"Ошибка выполнения SQL запроса: {query}, ошибка: {e}")
            raise DatabaseError(f"Ошибка базы данных: {e}")

    def _execute_many_with_error_handling(
        self, query: str, seq_of_params: List[tuple]
    ):
        """
        Выполняет SQL-запрос executemany с обработкой ошибок и блокировкой.

        Примечание: Коммит не выполняется автоматически, как и в
        `_execute_with_error_handling`. Вызывающая сторона должна решать,
        когда фиксировать транзакцию (commit) или использовать `self.transaction()`.
        """
        try:
            with db_lock:
                cursor = self.connection.executemany(query, seq_of_params)
            return cursor
        except sqlite3.Error as e:
            logger.error(
                f"Ошибка выполнения SQL executemany: {query}, кол-во пакетов={len(seq_of_params)}, ошибка: {e}"
            )
            raise DatabaseError(f"Ошибка базы данных (executemany): {e}")

    def _update_entity(
        self,
        table_name: str,
        entity_id: int,
        data: Dict[str, Any],
        valid_keys: List[str],
    ):
        """Универсальный метод обновления сущности."""
        fields = []
        params = []

        for key in valid_keys:
            if key in data:
                fields.append(f"{key} = ?")
                params.append(data[key])

        if not fields:
            return

        query = f"UPDATE {table_name} SET {', '.join(fields)} WHERE id=?"
        params.append(entity_id)

        try:
            with db_lock:
                self.connection.execute(query, tuple(params))
            logger.debug(f"Обновлен {table_name} с ID {entity_id}")
        except Exception as e:
            logger.error(f"Ошибка обновления {table_name}: {e}")
            raise DatabaseError(f"Не удалось обновить {table_name}: {e}")
