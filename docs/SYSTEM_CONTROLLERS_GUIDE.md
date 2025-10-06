# 📚 System Controllers Developer Guide

## Обзор

Модуль `app/controllers/system/` содержит системные контроллеры, отвечающие за инициализацию, завершение приложения и управление глобальными функциями.

---

## 🏗️ Архитектура

### Структура модулей

```
app/controllers/system/
├── __init__.py                      # Экспорт публичного API
├── app_shutdown_controller.py       # Управление завершением приложения
├── bootstrap.py                     # Инициализация контроллеров с DI
├── db_init.py                       # Асинхронная инициализация БД
├── keyboard_manager.py              # Управление горячими клавишами
├── window_controllers_setup.py      # Настройка контроллеров окна
└── window_setup/                    # Модули настройки окна
    ├── business.py                  # Настройка бизнес-логики
    ├── coordinator.py               # Координация компонентов
    ├── keyboard.py                  # Настройка клавиатуры
    ├── types.py                     # Типы данных
    ├── ui.py                        # Настройка UI
    └── wiring.py                    # Связывание компонентов
```

---

## 🎯 Основные компоненты

### 1. AppShutdownController

**Назначение**: Управление корректным завершением приложения с приоритизацией операций.

**Ключевые возможности**:
- ✅ Приоритизация операций (CRITICAL, HIGH, NORMAL, LOW)
- ✅ Параллельное выполнение некритичных операций
- ✅ Таймауты и глобальный дедлайн
- ✅ Graceful degradation при ошибках
- ✅ Cleanup ресурсов

**Пример использования**:
```python
from app.controllers.system import AppShutdownController, ShutdownPriority

# Инициализация
shutdown_controller = AppShutdownController(main_window)

# Добавление custom handler
def save_user_data():
    # Сохранение данных пользователя
    pass

shutdown_controller.add_shutdown_handler(
    name="save_user_data",
    handler=save_user_data,
    priority=ShutdownPriority.CRITICAL,
    timeout=3000,
    critical=True  # Ошибка прервёт shutdown
)

# В closeEvent главного окна
def closeEvent(self, event):
    self.shutdown_controller.perform_shutdown(event)
```

**Приоритеты операций**:
```python
class ShutdownPriority(Enum):
    CRITICAL = 1  # Сохранение данных, критичные операции
    HIGH = 2      # Остановка контроллеров
    NORMAL = 3    # Ожидание потоков
    LOW = 4       # Cleanup, бэкапы
```

---

### 2. DatabaseInitializer

**Назначение**: Асинхронная инициализация базы данных без блокировки UI.

**Ключевые возможности**:
- ✅ Фоновая инициализация через `run_db()`
- ✅ Блокировка UI на время инициализации
- ✅ Обратная связь через statusbar
- ✅ Graceful error handling

**Пример использования**:
```python
from app.controllers.system.db_init import DatabaseInitializer

# Инициализация
db_initializer = DatabaseInitializer(database, main_window)

# Запуск асинхронной инициализации
def on_success():
    print("Database initialized successfully")
    # Продолжить загрузку приложения

def on_error(error):
    print(f"Database initialization failed: {error}")
    # Показать ошибку и закрыть приложение

db_initializer.initialize_async(
    on_success=on_success,
    on_error=on_error
)
```

---

### 3. KeyboardManager

**Назначение**: Централизованное управление горячими клавишами с контекстной обработкой.

**Ключевые возможности**:
- ✅ Контекстная обработка (дерево/таблица/плитки)
- ✅ Безопасный доступ через `_safe_getattr()` и `_safe_call()`
- ✅ Модульная архитектура (ClipboardKeyHandler, EditingKeyHandler, etc.)
- ✅ Эксклюзивность выделения (дерево ⇄ таблица)

**Пример использования**:
```python
from app.controllers.system.keyboard_manager import (
    ClipboardKeyHandler,
    EditingKeyHandler
)

# Инициализация handlers
clipboard_handler = ClipboardKeyHandler(main_window)
editing_handler = EditingKeyHandler(main_window)

# Обработка Ctrl+A
clipboard_handler.handle_select_all()

# Обработка Enter
focused_widget = QApplication.focusWidget()
editing_handler.handle_key(event, focused_widget)
```

**Добавление custom handler**:
```python
from app.controllers.system.keyboard_manager import BaseKeyHandler

class CustomKeyHandler(BaseKeyHandler):
    """Custom обработчик клавиш."""
    
    def handle_custom_action(self) -> None:
        """Обрабатывает custom действие."""
        # Безопасный доступ к атрибутам
        controller = self._safe_getattr(self.main_window, "my_controller")
        if controller:
            self._safe_call(controller, "my_method", arg1, arg2)
```

---

### 4. Bootstrap (build_controllers)

**Назначение**: Инициализация всех контроллеров приложения с Dependency Injection.

**Ключевые возможности**:
- ✅ Protocol для валидации входных параметров
- ✅ Централизованное создание контроллеров
- ✅ Явные зависимости через DI
- ✅ Фасад для удобного доступа

**Пример использования**:
```python
from app.controllers.system.bootstrap import build_controllers, ControllersFacade

# Создание контроллеров
controllers: ControllersFacade = build_controllers(main_window)

# Доступ к контроллерам
controllers.structure_business.load_spheres_async()
controllers.links_business.load_links(category_id)
controllers.app_shutdown.perform_shutdown(event)

# Все контроллеры доступны через фасад:
# - structure_business: StructureBusinessLogic
# - structure: StructureUIController
# - links_business: LinksBusinessLogic
# - links: LinksUIController
# - link_operations: LinkOperationsController
# - database_controller: DatabaseController
# - system_dialogs: SystemDialogController
# - app_shutdown: AppShutdownController
```

**Валидация окна**:
```python
from app.controllers.system.bootstrap import WindowWithRequiredAttributes

# Окно должно реализовывать Protocol
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()           # ✅ Обязательно
        self.tree = QTreeView()        # ✅ Обязательно
        self.table = QTableView()      # ✅ Обязательно
        self.undo_stack = QUndoStack() # ✅ Обязательно
```

---

## 🚀 Лучшие практики

### 1. Shutdown Operations

**✅ ПРАВИЛЬНО**:
```python
# Добавление handler с правильным приоритетом
shutdown_controller.add_shutdown_handler(
    name="save_critical_data",
    handler=save_data,
    priority=ShutdownPriority.CRITICAL,
    timeout=5000,
    critical=True
)

# Cleanup в finally
try:
    perform_operation()
finally:
    shutdown_controller.cleanup()
```

**❌ НЕПРАВИЛЬНО**:
```python
# Прямой вызов quit() из UI
QApplication.instance().quit()  # Пропускает shutdown sequence!

# Блокирующие операции в CRITICAL
def slow_operation():
    time.sleep(10)  # ❌ Превысит таймаут!
```

---

### 2. Database Initialization

**✅ ПРАВИЛЬНО**:
```python
# Асинхронная инициализация
db_initializer.initialize_async(
    on_success=lambda: self.continue_loading(),
    on_error=lambda e: self.show_error_and_quit(e)
)

# UI заблокирован автоматически
```

**❌ НЕПРАВИЛЬНО**:
```python
# Синхронная инициализация в GUI-потоке
db.initialize_or_migrate()  # ❌ Блокирует UI!
```

---

### 3. Keyboard Handling

**✅ ПРАВИЛЬНО**:
```python
# Безопасный доступ
controller = self._safe_getattr(self.main_window, "controller")
if controller:
    self._safe_call(controller, "method", default=None)

# Контекстная обработка
if self._is_tree_focused(focused_widget):
    self._handle_tree_action()
elif self._is_table_focused(focused_widget):
    self._handle_table_action()
```

**❌ НЕПРАВИЛЬНО**:
```python
# Прямой доступ без проверок
self.main_window.controller.method()  # ❌ AttributeError!

# Игнорирование контекста
self.main_window.table.selectAll()  # ❌ Не учитывает фокус!
```

---

## 🔧 Настройка

### Конфигурация Shutdown

```json
{
  "shutdown": {
    "default_timeout": 2000,
    "max_total_time": 10000,
    "parallel_execution": false
  }
}
```

### Добавление Custom Shutdown Handler

```python
def custom_cleanup():
    """Custom cleanup операция."""
    # Ваш код
    pass

# Регистрация
shutdown_controller.add_shutdown_handler(
    name="custom_cleanup",
    handler=custom_cleanup,
    priority=ShutdownPriority.LOW,
    timeout=1000,
    critical=False
)
```

---

## 🐛 Отладка

### Логирование Shutdown

```python
import logging

# Включить debug логи для shutdown
logging.getLogger('app.controllers.system.app_shutdown_controller').setLevel(logging.DEBUG)

# Вывод:
# DEBUG: Executing shutdown priority CRITICAL with 2 handlers
# INFO: Starting application shutdown sequence
# INFO: Application shutdown completed successfully
```

### Проверка Handlers

```python
# Вывести все зарегистрированные handlers
for handler in shutdown_controller.shutdown_handlers:
    print(f"{handler.name}: {handler.priority.name}, timeout={handler.timeout}ms")
```

---

## 📊 Метрики

### Время Shutdown

```python
import time

start = time.monotonic()
shutdown_controller.perform_shutdown(event)
duration = (time.monotonic() - start) * 1000

print(f"Shutdown took {duration:.2f}ms")
```

### Целевые показатели

| Операция | Целевое время |
|----------|---------------|
| Total shutdown | < 5000ms |
| CRITICAL handlers | < 2000ms |
| Database backup | < 3000ms |

---

## 🧪 Тестирование

### Unit Test для Shutdown

```python
import pytest
from unittest.mock import Mock
from app.controllers.system import AppShutdownController, ShutdownPriority

def test_shutdown_priority_order():
    # Arrange
    main_window = Mock()
    controller = AppShutdownController(main_window)
    
    call_order = []
    
    def critical_handler():
        call_order.append('critical')
    
    def low_handler():
        call_order.append('low')
    
    controller.add_shutdown_handler(
        "low", low_handler, ShutdownPriority.LOW
    )
    controller.add_shutdown_handler(
        "critical", critical_handler, ShutdownPriority.CRITICAL
    )
    
    # Act
    event = Mock()
    controller.perform_shutdown(event)
    
    # Assert
    assert call_order == ['critical', 'low']
```

---

## 📋 Чеклист для разработчиков

- [ ] Все shutdown операции зарегистрированы с правильными приоритетами
- [ ] Критичные операции имеют `critical=True`
- [ ] Таймауты установлены разумно (< 5s для большинства)
- [ ] БД инициализируется асинхронно
- [ ] Keyboard handlers используют безопасный доступ
- [ ] Контроллеры создаются через `build_controllers()`
- [ ] Cleanup вызывается в finally блоках
- [ ] Добавлены unit тесты для custom handlers

---

## 🔗 Связанные документы

- [Business Layer Guide](BUSINESS_LAYER_GUIDE.md)
- [Performance Metrics Usage](PERFORMANCE_METRICS_USAGE.md)
- [Testing Guide](TESTING_GUIDE.md)

---

**Версия документа**: 1.0  
**Последнее обновление**: 2025-10-06  
**Автор**: Development Team
