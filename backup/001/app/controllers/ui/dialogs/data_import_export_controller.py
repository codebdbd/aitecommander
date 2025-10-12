"""Контроллер для импорта/экспорта данных структуры.

Использует async операции для импорта/экспорта без блокировки UI.
"""
import json
import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from app.models.db import Database
from app.utils.ui.async_helpers import run_async_export, run_async_import

logger = logging.getLogger(__name__)


class DataImportExportController(QObject):
    """Контроллер для операций импорта/экспорта структуры данных.
    
    Features:
    - Асинхронный импорт/экспорт с progress dialog
    - Обработка ошибок
    - Валидация JSON
    - Уведомления о результатах
    """
    
    # Сигналы для уведомления UI
    export_completed = pyqtSignal(str)  # exported_file_path
    import_completed = pyqtSignal(dict)  # import_stats
    operation_error = pyqtSignal(str, str)  # title, message
    
    def __init__(self, db: Database, parent: Optional[QWidget] = None):
        """
        Args:
            db: Экземпляр Database
            parent: Родительский виджет для диалогов
        """
        super().__init__(parent)
        self.db = db
        self.parent_widget = parent
    
    def handle_export_structure(self):
        """Обработчик экспорта структуры данных.
        
        Показывает диалог сохранения файла и запускает async экспорт.
        """
        # Диалог выбора места сохранения
        file_path, _ = QFileDialog.getSaveFileName(
            self.parent_widget,
            "Экспорт структуры данных",
            "structure_export.json",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if not file_path:
            return  # Пользователь отменил
        
        file_path = Path(file_path)
        
        def on_export_success(result):
            """Callback при успешном экспорте."""
            try:
                # Сохраняем результат в файл
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                logger.info(f"Структура экспортирована в {file_path}")
                self.export_completed.emit(str(file_path))
                
                # Показываем статистику
                stats_msg = (
                    f"Экспорт завершен!\n\n"
                    f"Сфер: {len(result.get('spheres', []))}\n"
                    f"Разделов: {len(result.get('sections', []))}\n"
                    f"Категорий: {len(result.get('categories', []))}\n"
                    f"Ссылок: {len(result.get('links', []))}\n\n"
                    f"Файл: {file_path.name}"
                )
                QMessageBox.information(
                    self.parent_widget,
                    "Экспорт завершен",
                    stats_msg
                )
                
            except Exception as e:
                logger.error(f"Ошибка сохранения файла: {e}")
                self.operation_error.emit(
                    "Ошибка сохранения",
                    f"Не удалось сохранить файл:\n{str(e)}"
                )
        
        # Запускаем async экспорт с progress dialog
        run_async_export(
            self.db,
            parent=self.parent_widget,
            on_success=on_export_success,
            title="Экспорт структуры"
        )
    
    def handle_import_structure(self):
        """Обработчик импорта структуры данных.
        
        Показывает диалог выбора файла и запускает async импорт.
        """
        # Диалог выбора файла
        file_path, _ = QFileDialog.getOpenFileName(
            self.parent_widget,
            "Импорт структуры данных",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if not file_path:
            return  # Пользователь отменил
        
        file_path = Path(file_path)
        
        try:
            # Читаем и валидируем JSON
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, list):
                raise ValueError("Неверный формат данных: ожидается массив")
            
            # Подтверждение импорта
            confirm = QMessageBox.question(
                self.parent_widget,
                "Подтверждение импорта",
                f"Импортировать структуру из файла:\n{file_path.name}\n\n"
                "⚠️ ВНИМАНИЕ: Текущая структура будет полностью заменена!\n\n"
                "Рекомендуется создать резервную копию перед импортом.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if confirm != QMessageBox.StandardButton.Yes:
                return
            
            def on_import_success(stats):
                """Callback при успешном импорте."""
                logger.info(f"Структура импортирована из {file_path}")
                self.import_completed.emit(stats)
                
                # Уведомление уже показывается в run_async_import
                # Здесь можем добавить дополнительную логику
            
            # Запускаем async импорт с progress dialog
            run_async_import(
                self.db,
                data,
                parent=self.parent_widget,
                on_success=on_import_success,
                title="Импорт структуры",
                cancelable=True  # Можно отменить длительный импорт
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            self.operation_error.emit(
                "Ошибка формата",
                f"Файл содержит невалидный JSON:\n{str(e)}"
            )
            QMessageBox.critical(
                self.parent_widget,
                "Ошибка формата",
                f"Файл содержит невалидный JSON:\n{str(e)}"
            )
            
        except Exception as e:
            logger.error(f"Ошибка загрузки файла: {e}")
            self.operation_error.emit(
                "Ошибка загрузки",
                f"Не удалось загрузить файл:\n{str(e)}"
            )
            QMessageBox.critical(
                self.parent_widget,
                "Ошибка загрузки",
                f"Не удалось загрузить файл:\n{str(e)}"
            )
    
    def handle_quick_backup(self):
        """Быстрый backup без UI (запускается в фоне)."""
        from app.utils.ui.async_helpers import run_async_backup
        
        run_async_backup(
            self.db,
            parent=self.parent_widget,
            show_notification=True
        )
