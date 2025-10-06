"""Helper функции для работы с асинхронными операциями БД.

✅ ИСПРАВЛЕНИЕ: Вынесен UI-код, функции возвращают статус и сообщения.
"""
import logging
from typing import Callable, Optional, Tuple, Any

from PyQt6.QtWidgets import QWidget

from app.views.windows.dialogs.async_operation_dialog import AsyncOperationDialog

logger = logging.getLogger(__name__)


def run_async_import(
    db,
    data: list,
    parent: Optional[QWidget] = None,
    on_success: Optional[Callable] = None,
    title: str = "Импорт данных",
    cancelable: bool = False
) -> Tuple[bool, Optional[str], Optional[dict]]:
    """Запускает асинхронный импорт с progress dialog.
    
    ✅ ИСПРАВЛЕНИЕ: Возвращает статус и сообщение вместо показа QMessageBox.
    
    Args:
        db: Экземпляр Database
        data: Данные для импорта
        parent: Родительский виджет
        on_success: Callback при успехе (получает stats)
        title: Заголовок диалога
        cancelable: Можно ли отменить
    
    Returns:
        Tuple[bool, Optional[str], Optional[dict]]: (success, message, stats)
        
    Example:
        >>> success, msg, stats = run_async_import(db, data, parent=self)
        >>> if success and msg:
        ...     QMessageBox.information(self, "Импорт", msg)
    """
    result_stats = None
    result_message = None
    result_success = False
    dialog = AsyncOperationDialog(
        title=title,
        message="Импорт структуры данных...",
        cancelable=cancelable,
        parent=parent
    )
    
    def on_finished(stats):
        nonlocal result_stats, result_message, result_success
        dialog.on_finished(stats)
        
        result_stats = stats
        result_success = True
        result_message = (
            f"Импортировано:\n"
            f"• Сфер: {stats.get('spheres', 0)}\n"
            f"• Разделов: {stats.get('sections', 0)}\n"
            f"• Категорий: {stats.get('categories', 0)}\n"
            f"• Ссылок: {stats.get('links', 0)}"
        )
        
        if on_success:
            on_success(stats)
    
    def on_error(e, tb):
        nonlocal result_message, result_success
        dialog.on_error(e, tb)
        
        result_success = False
        result_message = f"Не удалось импортировать данные:\n{str(e)}"
    
    # Запускаем асинхронный импорт
    db.import_full_structure_async(
        data,
        on_finished=on_finished,
        on_error=on_error,
        on_progress=dialog.update_progress
    )
    
    dialog.exec()


def run_async_export(
    db,
    parent: Optional[QWidget] = None,
    on_success: Optional[Callable] = None,
    title: str = "Экспорт данных"
) -> Tuple[bool, Optional[str], Any]:
    """Запускает асинхронный экспорт с progress dialog.
    
    ✅ ИСПРАВЛЕНИЕ: Возвращает статус и сообщение вместо показа QMessageBox.
    
    Args:
        db: Экземпляр Database
        parent: Родительский виджет
        on_success: Callback при успехе (получает result)
        title: Заголовок диалога
        
    Returns:
        Tuple[bool, Optional[str], Any]: (success, message, exported_data)
    """
    result_success = False
    result_message = None
    dialog = AsyncOperationDialog(
        title=title,
        message="Экспорт структуры данных...",
        cancelable=False,
        parent=parent
    )
    
    result_data = None
    
    def on_finished(result):
        nonlocal result_data, result_success, result_message
        result_data = result
        result_success = True
        dialog.on_finished(result)
        
        if result:
            count = (
                len(result.get('spheres', [])) +
                len(result.get('sections', [])) +
                len(result.get('categories', [])) +
                len(result.get('links', []))
            )
            result_message = f"Экспортировано {count} записей"
        
        if on_success:
            on_success(result)
    
    def on_error(e, tb):
        nonlocal result_success, result_message
        dialog.on_error(e, tb)
        
        result_success = False
        result_message = f"Не удалось экспортировать данные:\n{str(e)}"
    
    # Запускаем асинхронный экспорт
    db.export_full_structure_async(
        on_error=on_error,
        on_progress=dialog.update_progress
    )
    
    dialog.exec()
    return result_success, result_message, result_data


def run_async_backup(
    db,
    parent: Optional[QWidget] = None,
    show_notification: bool = True
) -> Tuple[bool, Optional[str]]:
    """Запускает асинхронное резервное копирование.
    
    ✅ ИСПРАВЛЕНИЕ: Возвращает статус и сообщение вместо показа QMessageBox.
    
    Args:
        db: Экземпляр Database
        parent: Родительский виджет
        on_success: Callback при успехе
        show_notification: Показывать ли уведомление о результате (deprecated)
        
    Returns:
        Tuple[bool, Optional[str]]: (success, message)
        
    Example:
        >>> success, msg = run_async_backup(db, parent=self)
        >>> if success and msg:
        ...     QMessageBox.information(self, "Backup", msg)
    """
    result_success = False
    result_message = None
    def on_finished(result):
        nonlocal result_success, result_message
        backup_file = result.get('backup_filename', 'неизвестно')
        logger.info(f"Backup создан: {backup_file}")
        
        result_success = True
        result_message = f"Резервная копия создана:\n{backup_file}"
        
        if on_success:
            on_success(result)
    
    def on_error(e, tb):
        nonlocal result_success, result_message
        logger.error(f"Ошибка backup: {e}")
        
        result_success = False
        result_message = f"Не удалось создать резервную копию:\n{str(e)}"
    
    # Запускаем асинхронный backup (без диалога)
    db.backup_async(
        on_finished=on_finished,
        on_error=on_error
    )
    
    return result_success, result_message
