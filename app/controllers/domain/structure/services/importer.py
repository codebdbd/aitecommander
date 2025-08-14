from __future__ import annotations

from typing import Any, Dict, Optional
import logging

from app.models.structure_model import StructureModel


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
            category_id = model.create_category(category_data)
            if logger and category_id:
                logger.info(
                    f"Создана категория для импорта {category_id}: {category_data.get('name', 'Без названия')}"
                )
            return category_id
        except Exception as e:
            if logger:
                logger.error(f"Ошибка создания категории для импорта: {e}")
            return None
