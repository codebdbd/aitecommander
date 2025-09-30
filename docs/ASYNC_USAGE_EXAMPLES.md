# Примеры использования асинхронных операций БД

## 🎯 Базовое использование

### 1. Простой асинхронный импорт с helper

```python
from app.models import Database
from app.utils.ui.async_helpers import run_async_import

class MyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
    
    def import_data(self, data):
        """Импорт данных с автоматическим progress dialog."""
        run_async_import(
            self.db,
            data,
            parent=self,
            on_success=lambda stats: self.on_import_success(stats)
        )
    
    def on_import_success(self, stats):
        """Callback после успешного импорта."""
        print(f"Импортировано {stats['links']} ссылок")
        self.reload_ui()
```

### 2. Асинхронный backup без UI

```python
from app.utils.ui.async_helpers import run_async_backup

class BackupManager:
    def create_backup(self):
        """Создает backup в фоне."""
        run_async_backup(
            self.db,
            parent=self.main_window,
            show_notification=True  # Покажет уведомление при завершении
        )
```

### 3. Ручная настройка с собственным диалогом

```python
from app.views.dialogs.async_operation_dialog import AsyncOperationDialog

class DataImporter:
    def import_with_custom_dialog(self, data):
        # Создаем диалог
        dialog = AsyncOperationDialog(
            title="Импорт данных",
            message="Импортируем структуру...",
            cancelable=True,  # Можно отменить
            parent=self.parent
        )
        dialog.set_auto_close(False)  # Не закрывать автоматически
        
        # Callbacks
        def on_finished(stats):
            dialog.on_finished(stats)
            self.show_summary(stats)
        
        def on_error(e, tb):
            dialog.on_error(e, tb)
            self.log_error(str(e))
        
        # Запускаем импорт
        self.db.import_full_structure_async(
            data,
            on_finished=on_finished,
            on_error=on_error,
            on_progress=dialog.update_progress
        )
        
        # Показываем диалог
        result = dialog.exec()
        return result == dialog.DialogCode.Accepted
```

## 🔧 Продвинутые примеры

### 4. Последовательное выполнение операций

```python
class SequentialOperations:
    def import_and_backup(self, data):
        """Сначала импорт, потом backup."""
        
        def on_import_done(stats):
            print("Импорт завершен, создаем backup...")
            
            # После импорта создаем backup
            self.db.backup_async(
                on_finished=lambda r: print(f"Backup создан: {r['backup_filename']}"),
                on_error=lambda e, tb: print(f"Ошибка backup: {e}")
            )
        
        # Запускаем импорт
        self.db.import_full_structure_async(
            data,
            on_finished=on_import_done
        )
```

### 5. Parallel операции (экспорт + backup)

```python
from PyQt6.QtCore import QTimer

class ParallelOperations:
    def export_and_backup_parallel(self):
        """Экспорт и backup параллельно."""
        self.operations_done = 0
        
        def check_all_done():
            self.operations_done += 1
            if self.operations_done == 2:
                print("Все операции завершены!")
        
        # Экспорт
        self.db.export_full_structure_async(
            on_finished=lambda r: check_all_done()
        )
        
        # Backup
        self.db.backup_async(
            on_finished=lambda r: check_all_done()
        )
```

### 6. Кастомный прогресс в статус-баре

```python
class MainWindow(QMainWindow):
    def import_with_statusbar_progress(self, data):
        """Показывает прогресс в статус-баре."""
        # Создаем progress bar в статус-баре
        progress_bar = QProgressBar()
        progress_bar.setMaximum(100)
        self.statusBar().addPermanentWidget(progress_bar)
        
        def on_progress(current, total, message):
            if total > 0:
                percentage = int((current / total) * 100)
                progress_bar.setValue(percentage)
                self.statusBar().showMessage(f"{message} ({percentage}%)")
        
        def on_finished(stats):
            self.statusBar().removeWidget(progress_bar)
            self.statusBar().showMessage(f"Импорт завершен: {stats['links']} ссылок", 5000)
        
        def on_error(e, tb):
            self.statusBar().removeWidget(progress_bar)
            self.statusBar().showMessage(f"Ошибка: {e}", 10000)
        
        self.db.import_full_structure_async(
            data,
            on_finished=on_finished,
            on_error=on_error,
            on_progress=on_progress
        )
```

### 7. Интеграция с Undo/Redo

```python
class ImportCommand(QUndoCommand):
    """Команда импорта с поддержкой Undo."""
    
    def __init__(self, db, data, parent=None):
        super().__init__(parent)
        self.db = db
        self.data = data
        self.backup_data = None
    
    def redo(self):
        """Выполняем импорт."""
        # Сначала экспортируем текущую структуру для undo
        self.backup_data = self.db.export_full_structure()
        
        # Импортируем новые данные
        run_async_import(
            self.db,
            self.data,
            on_success=lambda stats: print("Import done")
        )
    
    def undo(self):
        """Откатываем импорт."""
        if self.backup_data:
            run_async_import(
                self.db,
                self.backup_data,
                on_success=lambda stats: print("Rollback done")
            )
```

### 8. Обработка больших файлов с chunking

```python
class LargeDataImporter:
    def import_large_file(self, file_path):
        """Импорт большого JSON файла по частям."""
        import json
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Разбиваем на чанки по 100 сфер
        chunk_size = 100
        chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
        
        self.current_chunk = 0
        
        def import_next_chunk():
            if self.current_chunk < len(chunks):
                chunk = chunks[self.current_chunk]
                
                self.db.import_full_structure_async(
                    chunk,
                    on_finished=lambda stats: self.on_chunk_done(stats),
                    on_error=lambda e, tb: print(f"Ошибка: {e}")
                )
        
        def on_chunk_done(stats):
            self.current_chunk += 1
            print(f"Chunk {self.current_chunk}/{len(chunks)} done")
            
            # Импортируем следующий chunk
            QTimer.singleShot(100, import_next_chunk)
        
        # Начинаем импорт
        import_next_chunk()
```

## 🎨 UI Patterns

### 9. Modal Dialog с прогрессом

```python
def import_with_modal_dialog(self, data):
    """Блокирующий диалог с прогрессом."""
    dialog = AsyncOperationDialog(
        title="Импорт",
        message="Импортируем данные...",
        cancelable=False,
        parent=self
    )
    dialog.setWindowModality(Qt.WindowModal)  # Блокирует родительское окно
    
    self.db.import_full_structure_async(
        data,
        on_finished=dialog.on_finished,
        on_error=dialog.on_error,
        on_progress=dialog.update_progress
    )
    
    return dialog.exec()  # Блокирует до завершения
```

### 10. Non-modal с уведомлениями

```python
from PyQt6.QtWidgets import QSystemTrayIcon

def import_in_background(self, data):
    """Фоновый импорт с уведомлениями в трее."""
    
    def on_finished(stats):
        # Уведомление в system tray
        if hasattr(self, 'tray_icon'):
            self.tray_icon.showMessage(
                "Импорт завершен",
                f"Импортировано {stats['links']} ссылок",
                QSystemTrayIcon.Information,
                2000
            )
    
    self.db.import_full_structure_async(
        data,
        on_finished=on_finished
    )
    
    # Пользователь может продолжать работу
```

## ⚠️ Error Handling

### 11. Retry логика

```python
class RetryableImport:
    def __init__(self, db, max_retries=3):
        self.db = db
        self.max_retries = max_retries
        self.current_retry = 0
    
    def import_with_retry(self, data):
        def on_error(e, tb):
            self.current_retry += 1
            
            if self.current_retry < self.max_retries:
                print(f"Ошибка, попытка {self.current_retry + 1}/{self.max_retries}")
                # Повторяем через 2 секунды
                QTimer.singleShot(2000, lambda: self.import_with_retry(data))
            else:
                print("Максимальное количество попыток исчерпано")
                QMessageBox.critical(None, "Ошибка", f"Не удалось импортировать: {e}")
        
        def on_finished(stats):
            print("Импорт успешен!")
            self.current_retry = 0
        
        self.db.import_full_structure_async(
            data,
            on_finished=on_finished,
            on_error=on_error
        )
```

## 📊 Мониторинг

### 12. Логирование времени выполнения

```python
import time

class MonitoredImport:
    def import_with_monitoring(self, data):
        start_time = time.time()
        
        def on_finished(stats):
            duration = time.time() - start_time
            print(f"Импорт занял {duration:.2f} секунд")
            print(f"Скорость: {stats['links'] / duration:.2f} ссылок/сек")
        
        self.db.import_full_structure_async(
            data,
            on_finished=on_finished
        )
```

## ✅ Best Practices

1. **Всегда используйте async для операций > 1 секунды**
2. **Показывайте прогресс для операций > 3 секунд**
3. **Обрабатывайте ошибки в on_error callback**
4. **Для критичных операций делайте backup перед импортом**
5. **Не блокируйте UI thread - используйте async**
6. **Добавляйте кнопку отмены для длительных операций**
7. **Логируйте все async операции для диагностики**
