import logging
import sqlite3
from typing import Any, Dict, List, Optional

from app.utils.db.synchronization import db_lock

# Настройка логирования
logger = logging.getLogger(__name__)

# Валидные таблицы для операций с позициями
VALID_POSITION_TABLES = {'sphere', 'section', 'category', 'link'}


class DatabaseError(Exception):
    """Базовый класс для ошибок базы данных"""
    pass


class ValidationError(DatabaseError):
    """Ошибка валидации данных"""
    pass


class DatabaseBase:
    """Базовый класс для всех моделей БД с общими методами.
    
    Предоставляет унифицированный интерфейс для:
    - Управления соединениями с БД
    - Обработки ошибок и валидации
    - Общих операций (позиционирование, обновление)
    - Выполнения SQL-запросов с блокировками
    
    Архитектурное решение: Все модели наследуются от этого класса
    для обеспечения согласованности и переиспользования кода.
    """
    
    def __init__(self, connection_manager):
        """
        Args:
            connection_manager: Объект Database с методом connection
        """
        self.connection_manager = connection_manager
    
    @property
    def connection(self):
        """Получает соединение через менеджер соединений"""
        return self.connection_manager.connection
    
    def _validate_required_fields(self, data: Dict[str, Any], required_fields: List[str], entity_name: str = ""):
        """Валидирует обязательные поля"""
        # Отложенный импорт для предотвращения циклических импортов
        from app.utils.validators import validate_required_fields
        if not validate_required_fields(data, required_fields, entity_name):
            raise ValidationError(f"Отсутствуют обязательные поля для {entity_name}: {[field for field in required_fields if field not in data]}")

    def _get_next_position(self, table_name: str, parent_field: str = None, parent_id: int = None) -> int:
        """Получает следующую позицию для элемента в таблице."""
        try:
            if parent_field and parent_id is not None:
                cursor = self.connection.execute(
                    f"SELECT MAX(position) FROM {table_name} WHERE {parent_field} = ?",
                    (parent_id,)
                )
            else:
                cursor = self.connection.execute(f"SELECT MAX(position) FROM {table_name}")
            
            max_pos = cursor.fetchone()[0]
            return (max_pos + 1) if max_pos is not None else 0
        except Exception as e:
            logger.error(f"Ошибка получения позиции для таблицы {table_name}: {e}")
            return 0

    def _execute_with_error_handling(self, query: str, params: tuple = (), fetch_method: str = None):
        """Выполняет SQL запрос с обработкой ошибок."""
        try:
            with db_lock:
                cursor = self.connection.execute(query, params)
            if fetch_method == 'one':
                return cursor.fetchone()
            elif fetch_method == 'all':
                return cursor.fetchall()
            return cursor
        except sqlite3.Error as e:
            logger.error(f"Ошибка выполнения SQL запроса: {query}, ошибка: {e}")
            raise DatabaseError(f"Ошибка базы данных: {e}")

    def _update_entity(self, table_name: str, entity_id: int, data: Dict[str, Any], valid_keys: List[str]):
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
                self.connection.commit()
            logger.debug(f"Обновлен {table_name} с ID {entity_id}")
        except Exception as e:
            logger.error(f"Ошибка обновления {table_name}: {e}")
            raise DatabaseError(f"Не удалось обновить {table_name}: {e}")
