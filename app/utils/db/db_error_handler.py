# app/utils/db_error_handler.py
"""Centralised database error handler."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Optional, Type


_DATABASE_ERROR_CLS: Optional[Type[Exception]] = None


def _get_database_error_cls() -> Optional[Type[Exception]]:
    """Lazily import ``DatabaseError`` to avoid circular import during startup."""

    global _DATABASE_ERROR_CLS
    if _DATABASE_ERROR_CLS is not None:
        return _DATABASE_ERROR_CLS

    try:  # Attempt import only when needed
        from app.models.base.db_base import DatabaseError as DatabaseErrorRuntime

        _DATABASE_ERROR_CLS = DatabaseErrorRuntime
    except Exception:
        _DATABASE_ERROR_CLS = None
    return _DATABASE_ERROR_CLS


def _is_database_error(error: Exception) -> bool:
    """Check whether ``error`` is an instance of ``DatabaseError`` without eager import."""

    cls = _get_database_error_cls()
    return cls is not None and isinstance(error, cls)


logger = logging.getLogger(__name__)


class DatabaseErrorHandler:
    """Centralised database error handler."""

    def __init__(self):
        self.user_messages = {
            "section_duplicate": "A section with this name already exists in the selected sphere.",
            "category_duplicate": "A category with this name already exists in the selected section.",
            "link_duplicate": (
                "This link is already saved in this category.\n"
                "Want another one? Change the category or add launch arguments.\n"
                'Example (Chrome): --incognito, --new-window, --profile-directory="Profile 2".'
            ),
        }

        self.error_patterns = {
            "duplicate": ["unique constraint", "already exists"],
            "foreign_key": ["foreign key constraint"],
            "validation": ["check constraint", "not null constraint"],
        }

    def handle_error(self, error: Exception, context: Any = None) -> bool:
        """Handle a database error."""
        logger.error(
            f"Database error in {type(context).__name__ if context else 'unknown'}: {error}"
        )
        error_msg = str(error).lower()
        if isinstance(error, sqlite3.IntegrityError):
            return self._handle_sqlite_integrity_error(error_msg, context)
        elif _is_database_error(error):
            return self._handle_database_error(error_msg, context)
        else:
            self._show_error("Database error", str(error), context)
            return False

    def _handle_sqlite_integrity_error(self, error_msg: str, context: Any) -> bool:
        """Handle SQLite integrity errors."""
        if "unique constraint failed" in error_msg:
            return self._handle_duplicate(error_msg, context)
        elif "foreign key constraint failed" in error_msg:
            return self._handle_foreign_key(error_msg, context)
        elif "not null constraint failed" in error_msg:
            return self._handle_validation(error_msg, context)
        else:
            self._show_error(
                "Integrity constraint violation",
                "A database integrity constraint was violated.",
                context,
            )
            return False

    def _handle_database_error(self, error_msg: str, context: Any) -> bool:
        """Handle ``DatabaseError`` instances."""
        if "unique constraint failed" in error_msg:
            return self._handle_duplicate(error_msg, context)
        elif "foreign key constraint" in error_msg:
            return self._handle_foreign_key(error_msg, context)
        elif "not null" in error_msg or "check constraint" in error_msg:
            return self._handle_validation(error_msg, context)
        else:
            self._show_error("Database error", str(error_msg), context)
            return False

    def _handle_duplicate(self, error_msg: str, context: Any) -> bool:
        """Handle duplicate constraint violations."""
        if "link" in error_msg:
            self._show_info(
                "Duplicate link", self.user_messages["link_duplicate"], context
            )
        elif "category" in error_msg:
            self._show_info(
                "Information", self.user_messages["category_duplicate"], context
            )
        elif "section" in error_msg:
            self._show_info(
                "Information", self.user_messages["section_duplicate"], context
            )
        else:
            self._show_info(
                "Information",
                "A record with the same parameters already exists.",
                context,
            )
        return False

    def _handle_foreign_key(self, error_msg: str, context: Any) -> bool:
        """Handle foreign-key constraint issues."""
        self._show_error(
            "Referential integrity error",
            "Operation cannot be completed because related data is missing.",
            context,
        )
        return False

    def _handle_validation(self, error_msg: str, context: Any) -> bool:
        """Handle validation constraint issues."""
        self._show_error("Validation error", "Incorrect data was provided.", context)
        return False

    def _show_info(self, title: str, message: str, context: Any):
        """Display an informational message."""
        # Локальный импорт, чтобы избежать ранних кольцевых импортов
        from app.controllers.ui.dialogs.dialog_manager import DialogManager

        DialogManager.show_info(parent=None, message=message, title=title, silent=True)

    def _show_error(self, title: str, message: str, context: Any):
        """Display an error message."""
        if context and hasattr(context, "show_error"):
            context.show_error(title, message)
        else:
            # Локальный импорт, чтобы избежать ранних кольцевых импортов
            from app.controllers.ui.dialogs.dialog_manager import DialogManager

            DialogManager.show_error(None, title, message)


default_error_handler = DatabaseErrorHandler()


def handle_db_error(error: Exception, context: Any = None) -> bool:
    """Convenience function for handling database errors."""
    return default_error_handler.handle_error(error, context)
