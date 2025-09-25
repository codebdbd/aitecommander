# app/controllers/ui/structure/__init__.py
# Фасад для UI-контроллеров структуры (локальные импорты).

from .item_operations import ItemOperations
from .item_dialogs_service import ItemDialogService
from .item_deletion_service import ItemDeletionService
from .structure_ui_controller import StructureUIController

__all__ = [
    "StructureUIController",
    "ItemOperations",
    "ItemDialogService",
    "ItemDeletionService",
]
