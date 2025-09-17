# app/controllers/business/structure_async.py

"""Тонкая обёртка для асинхронного слоя структуры.

Позволяет `StructureBusinessLogic` зависеть от стабильной точки импорта
(`app.controllers.business.structure_async`) без знания внутреннего расположения
реализаций (`structure_modules.async_operations`). В случае перемещения
реализаций, будет достаточно обновить этот адаптер.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Реэкспорт реализаций
from app.controllers.structure_modules.async_operations import (  # noqa: F401
    AsyncOperations,
    AsyncSignalHandlers,
)

if TYPE_CHECKING:  # pragma: no cover
    # Подсказки типов без лишних зависимостей при рантайме
    from app.models.db import Database
    import logging


def create_async_layer(db: "Database", logger: "logging.Logger") -> AsyncOperations:
    """Фабрика для создания AsyncOperations (для удобства тестов/DI)."""
    return AsyncOperations(db, logger)
