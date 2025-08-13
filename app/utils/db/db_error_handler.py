# app/utils/db_error_handler.py
"""Централизованный обработчик ошибок базы данных"""

import logging
import sqlite3
from typing import Any

from app.utils.ui.dialog_manager import DialogManager

try:
    from app.models.db import DatabaseError
except ImportError:
    class DatabaseError(Exception):
        pass

logger = logging.getLogger(__name__)


class DatabaseErrorHandler:
    """Централизованный обработчик ошибок базы данных"""
    
    def __init__(self):
        self.user_messages = {
            'section_duplicate': "Раздел с таким именем уже существует в выбранной сфере.",
            'category_duplicate': "Категория с таким именем уже существует в выбранном разделе.",
            'link_duplicate': (
                "Такая ссылка уже сохранена в этой категории.\n"
                "Хотите ещё одну? Поменяйте категорию или добавьте аргументы запуска.\n"
                "Пример (Chrome): --incognito, --new-window, --profile-directory=\"Profile 2\"."
            ),
        }

        self.error_patterns = {
            'duplicate': ['unique constraint', 'already exists'],
            'foreign_key': ['foreign key constraint'],
            'validation': ['check constraint', 'not null constraint'],
        }
    
    def handle_error(self, error: Exception, context: Any = None) -> bool:
        """Обработать ошибку базы данных"""
        logger.error(f"Database error in {type(context).__name__ if context else 'unknown'}: {error}")
        error_msg = str(error).lower()
        if isinstance(error, sqlite3.IntegrityError):
            return self._handle_sqlite_integrity_error(error_msg, context)
        elif isinstance(error, DatabaseError):
            return self._handle_database_error(error_msg, context)
        else:
            self._show_error("Ошибка базы данных", str(error), context)
            return False
    
    def _handle_sqlite_integrity_error(self, error_msg: str, context: Any) -> bool:
        """Обработка ошибок целостности SQLite"""
        if 'unique constraint failed' in error_msg:
            return self._handle_duplicate(error_msg, context)
        elif 'foreign key constraint failed' in error_msg:
            return self._handle_foreign_key(error_msg, context)
        elif 'not null constraint failed' in error_msg:
            return self._handle_validation(error_msg, context)
        else:
            self._show_error("Ошибка целостности данных", 
                           "Нарушено ограничение целостности базы данных.", context)
            return False
    
    def _handle_database_error(self, error_msg: str, context: Any) -> bool:
        """Обработка ошибок DatabaseError"""
        if 'unique constraint failed' in error_msg:
            return self._handle_duplicate(error_msg, context)
        elif 'foreign key constraint' in error_msg:
            return self._handle_foreign_key(error_msg, context)
        elif 'not null' in error_msg or 'check constraint' in error_msg:
            return self._handle_validation(error_msg, context)
        else:
            self._show_error("Ошибка базы данных", str(error_msg), context)
            return False
    
    def _handle_duplicate(self, error_msg: str, context: Any) -> bool:
        """Обработка ошибок дубликатов"""
        if 'link' in error_msg:
            self._show_info("Дубликат ссылки", self.user_messages['link_duplicate'], context)
        elif 'category' in error_msg:
            self._show_info("Информация", self.user_messages['category_duplicate'], context)
        elif 'section' in error_msg:
            self._show_info("Информация", self.user_messages['section_duplicate'], context)
        else:
            self._show_info("Информация", "Запись с такими параметрами уже существует.", context)
        return False
    
    def _handle_foreign_key(self, error_msg: str, context: Any) -> bool:
        """Обработка ошибок внешних ключей"""
        self._show_error("Ошибка ссылочной целостности", 
                        "Невозможно выполнить операцию: связанные данные отсутствуют.", context)
        return False
    
    def _handle_validation(self, error_msg: str, context: Any) -> bool:
        """Обработка ошибок валидации"""
        self._show_error("Ошибка валидации данных", 
                        "Введены некорректные данные.", context)
        return False
    
    def _show_info(self, title: str, message: str, context: Any):
        """Показать информационное сообщение"""
        DialogManager.show_info(parent=None, message=message, title=title, silent=True)
    
    def _show_error(self, title: str, message: str, context: Any):
        """Показать сообщение об ошибке"""
        if context and hasattr(context, 'show_error'):
            context.show_error(title, message)
        else:
            DialogManager.show_error(None, title, message)

default_error_handler = DatabaseErrorHandler()


def handle_db_error(error: Exception, context: Any = None) -> bool:
    """Удобная функция для обработки ошибок БД"""
    return default_error_handler.handle_error(error, context)
