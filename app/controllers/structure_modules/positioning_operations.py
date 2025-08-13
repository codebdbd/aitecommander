# app/controllers/structure_modules/positioning_operations.py

"""Модуль для операций с позиционированием элементов."""

import logging
from typing import Callable, List

from app.models.structure_model import StructureModel
from .base import BaseOperations


class PositioningOperations(BaseOperations):
    """Класс для операций с позиционированием элементов."""
    
    def update_item_positions(self, table_name: str, ids_in_order: List[int]) -> bool:
        """Обновляет позиции элементов в указанной таблице."""
        def _update_positions_operation():
            self.structure_model.update_item_positions(table_name, ids_in_order)
            self.logger.info(f"Обновлены позиции в таблице {table_name}: {len(ids_in_order)} элементов")
            return True
        
        result = self._execute_with_error_handling(
            _update_positions_operation,
            f"обновить позиции в таблице {table_name}",
            default_return=False
        )
        return result if result is not None else False
