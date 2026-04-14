# Database Workers - Асинхронные операции БД

## Обзор

Workers обеспечивают выполнение тяжелых операций с БД в фоновых потоках без блокировки UI. Основаны на `QRunnable` и `QThreadPool`.

## Архитектура

```
DatabaseWorker (базовый класс)
├── ImportStructureWorker   - Импорт структуры
├── ExportStructureWorker   - Экспорт структуры  
└── BackupWorker           - Резервное копирование
```

## Особенности

✅ **Потокобезопасность** - каждый worker создает отдельное соединение с БД
✅ **Прогресс** - поддержка отслеживания прогресса операций
✅ **Отмена** - возможность отменить длительную операцию
✅ **Обработка ошибок** - автоматический перехват и передача ошибок через сигналы

## Использование

### 1. Асинхронный импорт структуры

```python
from app.models import Database

db = Database()

def on_import_finished(stats):
    print(f"Импортировано: {stats}")
    # stats = {spheres: 5, sections: 20, categories: 100, links: 500}

def on_import_error(exception, traceback):
    print(f"Ошибка: {exception}")

def on_import_progress(current, total, message):
    print(f"Прогресс: {current}/{total} - {message}")

# Запуск асинхронного импорта
db.import_full_structure_async(
    data=structure_data,
    on_finished=on_import_finished,
    on_error=on_import_error,
    on_progress=on_import_progress
)
```

### 2. Асинхронный экспорт структуры

```python
def on_export_finished(result):
    spheres = result['spheres']
    sections = result['sections']
    print(f"Экспортировано {len(spheres)} сфер")

db.export_full_structure_async(
    on_finished=on_export_finished,
    on_progress=lambda c, t, m: print(f"{m}: {c}/{t}")
)
```

### 3. Асинхронный backup

```python
def on_backup_finished(result):
    backup_path = result['backup_path']
    print(f"Backup создан: {backup_path}")

db.backup_async(
    on_finished=on_backup_finished,
    on_error=lambda e, tb: print(f"Ошибка: {e}")
)
```

### 4. Интеграция с Qt UI

```python
from PyQt6.QtWidgets import QProgressDialog

class MainWindow(QMainWindow):
    def import_data(self, data):
        # Создаем диалог прогресса
        progress = QProgressDialog("Импорт данных...", "Отмена", 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        
        def on_progress(current, total, message):
            progress.setMaximum(total)
            progress.setValue(current)
            progress.setLabelText(message)
        
        def on_finished(stats):
            progress.close()
            QMessageBox.information(
                self, 
                "Успех", 
                f"Импортировано {stats['links']} ссылок"
            )
            self.reload_ui()
        
        def on_error(e, tb):
            progress.close()
            QMessageBox.critical(self, "Ошибка", str(e))
        
        # Запускаем асинхронный импорт
        self.db.import_full_structure_async(
            data,
            on_finished=on_finished,
            on_error=on_error,
            on_progress=on_progress
        )
```

## Сравнение синхронных и асинхронных методов

| Метод | Синхронный | Асинхронный | Рекомендация |
|-------|-----------|-------------|--------------|
| **Import structure** | `import_full_structure()` | `import_full_structure_async()` | ✅ **Async** для >100 записей |
| **Export structure** | `export_full_structure()` | `export_full_structure_async()` | ✅ **Async** для >100 записей |
| **Backup** | `backup()` | `backup_async()` | ✅ **Async** для больших БД |
| **CRUD операции** | `insert_sphere()`, etc. | ❌ Не требуется | Sync OK |
| **Get data** | `get_full_structure()` | ❌ Не требуется | Sync OK (cached) |

## Производительность

### Тест: Импорт 1000 ссылок

- **Синхронный**: ~2-3 секунды, **UI заблокирован** ❌
- **Асинхронный**: ~2-3 секунды, **UI отзывчив** ✅

### Рекомендации

- Используйте **async** для операций > 1 секунды
- Для быстрых CRUD (<100ms) используйте **sync**
- Всегда показывайте прогресс для async операций
- Обрабатывайте ошибки в `on_error` callback

## Внутренние детали

### Создание соединения

Каждый worker создает отдельное соединение с настройками для производительности:

```python
conn = DatabaseManager.get_connection()
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA cache_size=-64000")  # 64MB
```

### Thread Pool

Используется глобальный `QThreadPool` с ограничением 4 потока:

```python
self._thread_pool = QThreadPool.globalInstance()
self._thread_pool.setMaxThreadCount(4)
```

## Создание собственных workers

```python
from app.models.workers import DatabaseWorker

class CustomWorker(DatabaseWorker):
    def do_work(self, connection):
        # Ваша логика с использованием connection
        rows = connection.execute("SELECT * FROM mytable").fetchall()
        
        # Отправка прогресса
        for i, row in enumerate(rows):
            if self.is_cancelled:
                return None
            
            self.emit_progress(i, len(rows), f"Processing {i}")
            # ... обработка
        
        return result

# Использование
worker = CustomWorker()
worker.signals.finished.connect(my_callback)
db._thread_pool.start(worker)
```

## Troubleshooting

### Проблема: "database is locked"

**Причина**: Несколько потоков пытаются записать одновременно  
**Решение**: Используйте `db_lock` или транзакции

### Проблема: UI зависает после запуска async

**Причина**: Забыли вызвать `processEvents()` или операция слишком тяжелая  
**Решение**: Добавьте батчинг и emit прогресса чаще

### Проблема: Memory leak

**Причина**: Callback держит ссылку на большой объект  
**Решение**: Используйте weak references или очищайте данные в callback
