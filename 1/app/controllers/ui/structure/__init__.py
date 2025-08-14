# app/controllers/ui/structure/__init__.py
# Фасад для UI-контроллеров структуры (локальные импорты).

from .structure_ui_controller import StructureUIController
from .item_operations import ItemOperations

__all__ = [
    'StructureUIController',
    'ItemOperations',
]
