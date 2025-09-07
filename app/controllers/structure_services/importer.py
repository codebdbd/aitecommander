from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.models.structure_model import StructureModel
from app.services.structure_service import StructureService


class ImportService:
    """Сервис операций импорта для структуры."""

    def create_category_for_import(
        self,
        model: StructureModel,
        category_data: Dict[str, Any],
        logger: Optional[logging.Logger] = None,
    ) -> Optional[int]:
        """Создает категорию в режиме импорта и возвращает ее ID."""
        try:
            # Пытаемся использовать сервисный слой с транзакцией UnitOfWork
            try:
                service = StructureService(model.db)
            except Exception:
                service = None

            if service:
                category_id = service.create_category(category_data)
            else:
                # Фоллбек на прямую модель (нежелательно, но сохраняет совместимость)
                category_id = model.create_category(category_data)

            if logger and category_id:
                logger.info(
                    "Создана категория для импорта %s: %s",
                    category_id,
                    category_data.get('name', 'Без названия'),
                )
            return category_id
        except Exception as e:
            if logger:
                logger.error("Ошибка создания категории для импорта: %s", e)
            return None
