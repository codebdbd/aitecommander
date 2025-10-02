"""Helper функции для работы с асинхронными операциями БД."""
import logging
from typing import Callable, Optional

from PyQt6.QtWidgets import QMessageBox, QWidget

from app.views.windows.dialogs.async_operation_dialog import AsyncOperationDialog

logger = logging.getLogger(__name__)


def run_async_import(
    db,
    data: list,
    parent: Optional[QWidget] = None,
    on_success: Optional[Callable] = None,
    title: str = "Импорт данных",
    cancelable: bool = False
):
    """Запускает асинхронный импорт с progress dialog.
    
    Args:
        db: Экземпляр Database
        data: Данные для импорта
        parent: Родительский виджет
        on_success: Callback при успехе (получает stats)
        title: Заголовок диалога
        cancelable: Можно ли отменить
        
    Example:
        >>> run_async_import(
        ...     db, 
        ...     data, 
        ...     parent=self,
        ...     on_success=lambda stats: self.reload_ui()
        ... )
    """
    dialog = AsyncOperationDialog(
        title=title,
        message="Импорт структуры данных...",
        cancelable=cancelable,
        parent=parent
    )
    
    def on_finished(stats):
        dialog.on_finished(stats)
        if on_success:
            on_success(stats)
        
        # Показываем итоги
        if parent:
            summary = (
                f"Импортировано:\n"
                f"• Сфер: {stats.get('spheres', 0)}\n"
                f"• Разделов: {stats.get('sections', 0)}\n"
                f"• Категорий: {stats.get('categories', 0)}\n"
                f"• Ссылок: {stats.get('links', 0)}"
            )
            QMessageBox.information(parent, "Импорт завершен", summary)
    
    def on_error(e, tb):
        dialog.on_error(e, tb)
        if parent:
            QMessageBox.critical(
                parent,
                "Ошибка импорта",
                f"Не удалось импортировать данные:\n{str(e)}"
            )
    
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
):
    """Запускает асинхронный экспорт с progress dialog.
    
    Args:
        db: Экземпляр Database
        parent: Родительский виджет
        on_success: Callback при успехе (получает result)
        title: Заголовок диалога
        
    Returns:
        Экспортированные данные (если успешно) или None
    """
    dialog = AsyncOperationDialog(
        title=title,
        message="Экспорт структуры данных...",
        cancelable=False,
        parent=parent
    )
    
    result_data = None
    
    def on_finished(result):
        nonlocal result_data
        result_data = result
        dialog.on_finished(result)
        
        if on_success:
            on_success(result)
        
        # Показываем итоги
        if parent and result:
            count = (
                len(result.get('spheres', [])) +
                len(result.get('sections', [])) +
                len(result.get('categories', [])) +
                len(result.get('links', []))
            )
            QMessageBox.information(
                parent,
                "Экспорт завершен",
                f"Экспортировано {count} записей"
            )
    
    def on_error(e, tb):
        dialog.on_error(e, tb)
        if parent:
            QMessageBox.critical(
                parent,
                "Ошибка экспорта",
                f"Не удалось экспортировать данные:\n{str(e)}"
            )
    
    # Запускаем асинхронный экспорт
    db.export_full_structure_async(
        on_finished=on_finished,
        on_error=on_error,
        on_progress=dialog.update_progress
    )
    
    dialog.exec()
    return result_data


def run_async_backup(
    db,
    parent: Optional[QWidget] = None,
    on_success: Optional[Callable] = None,
    show_notification: bool = True
):
    """Запускает асинхронное резервное копирование.
    
    Args:
        db: Экземпляр Database
        parent: Родительский виджет
        on_success: Callback при успехе
        show_notification: Показывать ли уведомление о результате
        
    Example:
        >>> run_async_backup(db, parent=self)
    """
    def on_finished(result):
        backup_file = result.get('backup_filename', 'неизвестно')
        logger.info(f"Backup создан: {backup_file}")
        
        if on_success:
            on_success(result)
        
        if show_notification and parent:
            QMessageBox.information(
                parent,
                "Backup создан",
                f"Резервная копия создана:\n{backup_file}"
            )
    
    def on_error(e, tb):
        logger.error(f"Ошибка backup: {e}")
        
        if show_notification and parent:
            QMessageBox.warning(
                parent,
                "Ошибка backup",
                f"Не удалось создать резервную копию:\n{str(e)}"
            )
    
    # Запускаем асинхронный backup (без диалога)
    db.backup_async(
        on_finished=on_finished,
        on_error=on_error
    )
