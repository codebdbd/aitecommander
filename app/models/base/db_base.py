import logging
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Union

from app.utils.db.synchronization import db_lock

# Настройка логирования
logger = logging.getLogger(__name__)


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
        # Счётчик для генерации уникальных имён SAVEPOINT в рамках процесса/потока
        self._savepoint_counter = 0

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
            logger.error("Ошибка commit: %s", e)
            raise DatabaseError(f"Ошибка commit: {e}")

    def rollback(self) -> None:
        """Откатывает текущую транзакцию."""
        try:
            with db_lock:
                self.connection.rollback()
        except sqlite3.Error as e:
            logger.error("Ошибка rollback: %s", e)
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
            conn = self.connection
            # Если уже внутри транзакции — создаём вложенную через SAVEPOINT
            if getattr(conn, "in_transaction", False):
                sp_name = f"sp_{threading.get_ident()}_{self._savepoint_counter}"
                self._savepoint_counter += 1
                try:
                    conn.execute(f"SAVEPOINT {sp_name}")
                    yield
                    conn.execute(f"RELEASE SAVEPOINT {sp_name}")
                except Exception:
                    try:
                        # Откат только до границ вложенной транзакции
                        conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                        conn.execute(f"RELEASE SAVEPOINT {sp_name}")
                    except Exception:
                        # Игнорируем вторичные ошибки отката, чтобы не скрыть первичную
                        pass
                    raise
            else:
                # Внешняя (верхнего уровня) транзакция
                try:
                    conn.execute("BEGIN TRANSACTION")
                    yield
                    conn.commit()
                except Exception:
                    conn.rollback()
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

            max_pos = None if row is None else dict(row).get("max_pos")
            return (max_pos + 1) if max_pos is not None else 0
        except Exception as e:
            logger.error("Ошибка получения позиции для таблицы %s: %s", table_name, e)
            # Пробрасываем как DatabaseError, чтобы не скрывать проблемы с БД и порядком элементов
            raise DatabaseError(f"Не удалось вычислить позицию для {table_name}: {e}")

    def _execute_with_error_handling(
        self, query: str, params: tuple = (), fetch_method: str = None
    ) -> Union[sqlite3.Cursor, sqlite3.Row, List[sqlite3.Row], None]:
        """Выполняет SQL-запрос с обработкой ошибок и блокировкой."""
        try:
            with db_lock:
                cursor = self.connection.execute(query, params)
        except sqlite3.Error as e:
            logger.error("Ошибка выполнения SQL запроса: %s, ошибка: %s", query, e)
            raise DatabaseError(f"Ошибка базы данных: {e}")

        if fetch_method == "one":
            return cursor.fetchone()
        elif fetch_method == "all":
            return cursor.fetchall()
        return cursor

    def _execute_many_with_error_handling(self, query: str, seq_of_params: List[tuple]):
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
                "Ошибка выполнения SQL executemany: %s, кол-во пакетов=%s, ошибка: %s",
                query,
                len(seq_of_params),
                e,
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
            logger.debug("Обновлен %s с ID %s", table_name, entity_id)
        except Exception as e:
            logger.error("Ошибка обновления %s: %s", table_name, e)
            raise DatabaseError(f"Не удалось обновить {table_name}: {e}")
