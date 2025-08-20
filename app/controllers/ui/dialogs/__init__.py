# app/controllers/ui/dialogs/__init__.py
# Фасад для диалоговых контроллеров. Экспорты ленивые, чтобы избежать
# кольцевых импортов при ранней загрузке низкоуровневых модулей.

__all__ = [
    'DatabaseController',
    'LinkDialogController',
    'LinkOperationsController',
    'SystemDialogController',
    'DialogManager',
    'DialogMixin',
]

def __getattr__(name):
    if name == 'DialogManager':
        from .dialog_manager import DialogManager
        return DialogManager
    if name == 'DialogMixin':
        from .dialog_manager import DialogMixin
        return DialogMixin
    if name == 'DatabaseController':
        from .database_controller import DatabaseController
        return DatabaseController
    if name == 'LinkDialogController':
        from .link_dialog_controller import LinkDialogController
        return LinkDialogController
    if name == 'LinkOperationsController':
        from .link_operations_controller import LinkOperationsController
        return LinkOperationsController
    if name == 'SystemDialogController':
        from .system_dialog_controller import SystemDialogController
        return SystemDialogController
    raise AttributeError(name)

