"""Compatibility wrapper for legacy `app.models.db_base` imports."""

from app.models.base.db_base import (  # noqa: F401
    DatabaseBase,
    DatabaseError,
    ValidationError,
    db_lock,
)

__all__ = ["DatabaseBase", "DatabaseError", "ValidationError", "db_lock"]
