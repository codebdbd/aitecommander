"""Controller for structure data import/export.

Uses async operations for import/export without blocking UI.
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
    """Controller for structure data import/export operations.
    
    Features:
    - Asynchronous import/export with progress dialog
    - Error handling
    - JSON validation
    - Result notifications
    """
    
    # Сигналы для уведомления UI
    export_completed = pyqtSignal(str)  # exported_file_path
    import_completed = pyqtSignal(dict)  # import_stats
    operation_error = pyqtSignal(str, str)  # title, message
    
    def __init__(self, db: Database, parent: Optional[QWidget] = None):
        """
        Args:
            db: Database instance
            parent: Parent widget for dialogs
        """
        super().__init__(parent)
        self.db = db
        self.parent_widget = parent
    
    def handle_export_structure(self):
        """Structure data export handler.
        
        Shows save file dialog and starts async export.
        """
        # Save file dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self.parent_widget,
            "Export structure data",
            "structure_export.json",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if not file_path:
            return  # User cancelled
        
        file_path = Path(file_path)
        
        def on_export_success(result):
            """Callback on successful export."""
            try:
                # Save result to file
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                logger.info(f"Structure exported to {file_path}")
                self.export_completed.emit(str(file_path))
                
                # Show statistics
                stats_msg = (
                    f"Export completed!\n\n"
                    f"Spheres: {len(result.get('spheres', []))}\n"
                    f"Sections: {len(result.get('sections', []))}\n"
                    f"Categories: {len(result.get('categories', []))}\n"
                    f"Links: {len(result.get('links', []))}\n\n"
                    f"File: {file_path.name}"
                )
                QMessageBox.information(
                    self.parent_widget,
                    "Export completed",
                    stats_msg
                )
                
            except Exception as e:
                logger.error(f"Error saving file: {e}")
                self.operation_error.emit(
                    "Save error",
                    f"Failed to save file:\n{str(e)}"
                )
        
        # Start async export with progress dialog
        run_async_export(
            self.db,
            parent=self.parent_widget,
            on_success=on_export_success,
            title="Structure export"
        )
    
    def handle_import_structure(self):
        """Structure data import handler.
        
        Shows file selection dialog and starts async import.
        """
        # File selection dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self.parent_widget,
            "Import structure data",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if not file_path:
            return  # User cancelled
        
        file_path = Path(file_path)
        
        try:
            # Read and validate JSON
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, list):
                raise ValueError("Invalid data format: array expected")
            
            # Import confirmation
            confirm = QMessageBox.question(
                self.parent_widget,
                "Import confirmation",
                f"Import structure from file:\n{file_path.name}\n\n"
                "⚠️ WARNING: Current structure will be completely replaced!\n\n"
                "It is recommended to create a backup before importing.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if confirm != QMessageBox.StandardButton.Yes:
                return
            
            def on_import_success(stats):
                """Callback on successful import."""
                logger.info(f"Structure imported from {file_path}")
                self.import_completed.emit(stats)
                
                # Notification is already shown in run_async_import
                # Additional logic can be added here
            
            # Start async import with progress dialog
            run_async_import(
                self.db,
                data,
                parent=self.parent_widget,
                on_success=on_import_success,
                title="Structure import",
                cancelable=True  # Long import can be cancelled
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            self.operation_error.emit(
                "Format error",
                f"File contains invalid JSON:\n{str(e)}"
            )
            QMessageBox.critical(
                self.parent_widget,
                "Format error",
                f"File contains invalid JSON:\n{str(e)}"
            )
            
        except Exception as e:
            logger.error(f"File loading error: {e}")
            self.operation_error.emit(
                "Load error",
                f"Failed to load file:\n{str(e)}"
            )
            QMessageBox.critical(
                self.parent_widget,
                "Load error",
                f"Failed to load file:\n{str(e)}"
            )
    
    def handle_quick_backup(self):
        """Quick backup without UI (runs in background)."""
        from app.utils.ui.async_helpers import run_async_backup
        
        run_async_backup(
            self.db,
            parent=self.parent_widget,
            show_notification=True
        )
