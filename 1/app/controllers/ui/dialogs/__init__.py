# app/controllers/ui/dialogs/__init__.py
# Фасад для диалоговых контроллеров (локальные импорты).

from .database_controller import DatabaseController
from .link_dialog_controller import LinkDialogController
from .link_operations_controller import LinkOperationsController
from .system_dialog_controller import SystemDialogController

__all__ = [
    'DatabaseController',
    'LinkDialogController',
    'LinkOperationsController',
    'SystemDialogController',
]
