# 🎨 Руководство по интеграции async операций в UI

## 📋 Готовый контроллер

Создан **`DataImportExportController`** для интеграции в меню:
- ✅ `app/controllers/ui/dialogs/data_import_export_controller.py`

## 🚀 Как добавить в главное меню

### Шаг 1: Импортировать контроллер

```python
# В MainWindow или где создается меню
from app.controllers.ui.dialogs.data_import_export_controller import DataImportExportController
```

### Шаг 2: Создать экземпляр контроллера

```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        
        # Создаем контроллер для импорта/экспорта
        self.import_export_controller = DataImportExportController(
            self.db, 
            parent=self
        )
```

### Шаг 3: Добавить пункты меню

```python
def create_file_menu(self):
    """Создает меню File."""
    file_menu = self.menuBar().addMenu("&Файл")
    
    # === ИМПОРТ/ЭКСПОРТ ===
    
    # Экспорт структуры
    export_action = QAction("📤 Экспортировать структуру...", self)
    export_action.setShortcut("Ctrl+Shift+E")
    export_action.setStatusTip("Экспортировать всю структуру в JSON")
    export_action.triggered.connect(
        self.import_export_controller.handle_export_structure
    )
    file_menu.addAction(export_action)
    
    # Импорт структуры
    import_action = QAction("📥 Импортировать структуру...", self)
    import_action.setShortcut("Ctrl+Shift+I")
    import_action.setStatusTip("Импортировать структуру из JSON")
    import_action.triggered.connect(
        self.import_export_controller.handle_import_structure
    )
    file_menu.addAction(import_action)
    
    file_menu.addSeparator()
    
    # Быстрый backup
    backup_action = QAction("💾 Создать резервную копию", self)
    backup_action.setShortcut("Ctrl+B")
    backup_action.setStatusTip("Создать резервную копию БД в фоне")
    backup_action.triggered.connect(
        self.import_export_controller.handle_quick_backup
    )
    file_menu.addAction(backup_action)
```

### Шаг 4: Подключить сигналы (опционально)

```python
def __init__(self):
    super().__init__()
    # ... создание контроллера ...
    
    # Подключаем сигналы для реакции UI
    self.import_export_controller.export_completed.connect(
        self.on_export_completed
    )
    self.import_export_controller.import_completed.connect(
        self.on_import_completed
    )
    self.import_export_controller.operation_error.connect(
        self.on_operation_error
    )

def on_export_completed(self, file_path: str):
    """Реакция на успешный экспорт."""
    self.statusBar().showMessage(f"Экспорт завершен: {file_path}", 5000)

def on_import_completed(self, stats: dict):
    """Реакция на успешный импорт."""
    # Перезагружаем UI
    self.reload_structure()
    self.statusBar().showMessage(
        f"Импортировано {stats['links']} ссылок", 5000
    )

def on_operation_error(self, title: str, message: str):
    """Реакция на ошибку."""
    logger.error(f"{title}: {message}")
```

---

## 📝 Полный пример MainWindow

```python
from PyQt6.QtWidgets import QMainWindow, QAction
from app.models import Database
from app.controllers.ui.dialogs.data_import_export_controller import DataImportExportController

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Osteen Path")
        
        # Database
        self.db = Database()
        
        # Контроллер импорта/экспорта
        self.import_export_controller = DataImportExportController(
            self.db, 
            parent=self
        )
        
        # Подключаем сигналы
        self.import_export_controller.import_completed.connect(
            self.on_import_completed
        )
        
        # Создаем меню
        self.create_menus()
    
    def create_menus(self):
        """Создает меню приложения."""
        # Меню File
        file_menu = self.menuBar().addMenu("&Файл")
        
        # Экспорт
        export_action = QAction("📤 Экспортировать структуру...", self)
        export_action.triggered.connect(
            self.import_export_controller.handle_export_structure
        )
        file_menu.addAction(export_action)
        
        # Импорт
        import_action = QAction("📥 Импортировать структуру...", self)
        import_action.triggered.connect(
            self.import_export_controller.handle_import_structure
        )
        file_menu.addAction(import_action)
        
        file_menu.addSeparator()
        
        # Backup
        backup_action = QAction("💾 Резервная копия", self)
        backup_action.triggered.connect(
            self.import_export_controller.handle_quick_backup
        )
        file_menu.addAction(backup_action)
    
    def on_import_completed(self, stats):
        """Обновить UI после импорта."""
        # Перезагрузить структуру
        self.reload_structure()
        
        # Показать статистику
        self.statusBar().showMessage(
            f"Импортировано {stats['links']} ссылок",
            5000
        )
    
    def reload_structure(self):
        """Перезагрузить структуру в UI."""
        # Ваша логика обновления дерева/списков
        pass
```

---

## 🎯 Что это дает

### ✅ Пользователь получает:

1. **Меню "Файл" → "Экспортировать структуру"**
   - Выбирает файл для сохранения
   - Видит progress dialog
   - Получает уведомление об успехе
   - UI не зависает

2. **Меню "Файл" → "Импортировать структуру"**
   - Выбирает JSON файл
   - Видит подтверждение (данные будут заменены)
   - Видит progress dialog с возможностью отмены
   - После импорта UI обновляется автоматически

3. **Меню "Файл" → "Резервная копия"**
   - Backup создается в фоне
   - Уведомление о результате
   - Не блокирует UI

---

## 🔧 Дополнительные возможности

### Drag & Drop импорт

```python
def dropEvent(self, event: QDropEvent):
    """Обработка drop JSON файла."""
    if event.mimeData().hasUrls():
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.endswith('.json'):
                # Запускаем импорт через контроллер
                self.import_json_file(file_path)

def import_json_file(self, file_path: str):
    """Импорт из JSON файла."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        from app.utils.ui.async_helpers import run_async_import
        run_async_import(self.db, data, parent=self)
    except Exception as e:
        QMessageBox.critical(self, "Ошибка", str(e))
```

### Автоматический backup перед импортом

```python
def handle_import_with_backup(self):
    """Импорт с предварительным backup."""
    # Сначала создаем backup
    def on_backup_done(result):
        # После backup запускаем импорт
        self.import_export_controller.handle_import_structure()
    
    from app.utils.ui.async_helpers import run_async_backup
    run_async_backup(
        self.db,
        parent=self,
        on_success=on_backup_done,
        show_notification=False  # Не показываем, т.к. это промежуточный шаг
    )
```

### Экспорт только текущей сферы

```python
def export_current_sphere(self):
    """Экспорт только текущей сферы."""
    from app.views.dialogs.async_operation_dialog import AsyncOperationDialog
    
    dialog = AsyncOperationDialog(
        title="Экспорт сферы",
        message="Экспорт текущей сферы...",
        parent=self
    )
    
    sphere_id = self.get_current_sphere_id()
    
    def on_finished(result):
        dialog.on_finished(result)
        # Сохранить в файл
        # ...
    
    # Используем низкоуровневый API для кастомной логики
    self.db.export_full_structure_async(
        on_finished=on_finished,
        on_progress=dialog.update_progress
    )
    
    dialog.exec()
```

---

## ✨ Итог

**3 шага для полной интеграции:**

1. ✅ Импортировать `DataImportExportController`
2. ✅ Создать экземпляр в `__init__`
3. ✅ Подключить к меню через `triggered.connect()`

**Готово!** Пользователь получает полноценный импорт/экспорт с async операциями и красивым UI! 🎉
