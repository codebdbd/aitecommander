# 🔧 Рекомендации по дальнейшему рефакторингу

## ✅ Выполнено

### Критичные исправления (2025-09-30)

1. **✓ Исправлено множественное наследование в Database**
   - Убрано проблемное наследование `Database(DatabaseBase, QObject)`
   - Использована композиция: `self._base = DatabaseBase(self)`
   - Правильный MRO (Method Resolution Order)
   - Файл: `app/models/db.py`

2. **✓ Добавлены @deprecated для синхронных методов БД**
   - `export_full_structure()` → использовать `export_full_structure_async()`
   - `import_full_structure()` → использовать `import_full_structure_async()`
   - Предупреждения через `warnings.warn()`
   - Файл: `app/models/db.py`

3. **✓ Исправлен showEvent в MainWindow**
   - Эмиссия сигнала через `QTimer.singleShot(0, self.shown.emit)`
   - Предотвращена блокировка отрисовки окна
   - Файл: `app/views/main_window.py`

4. **✓ Вынесены магические числа в конфигурацию**
   - Добавлена секция `threading.max_db_threads = 4`
   - Добавлена секция `startup.app_ready_delay_ms = 100`
   - Файлы: `app/config_data/app_config.json`, `app/models/db.py`, `app/main.py`

---

## 🚀 Следующие шаги (по приоритету)

### Высокий приоритет

#### 1. Рефакторинг MainWindow (Бог-объект)
**Проблема:** MainWindow содержит слишком много логики (425 строк, ~15 зон ответственности)

**Решение:**
```python
# app/controllers/ui/main_window_controller.py
class MainWindowController:
    """Координатор главного окна - делегирует задачи специализированным контроллерам."""
    
    def __init__(self, window: MainWindow):
        self.window = window
        self.structure_ctrl = StructureUIController(...)
        self.links_ctrl = LinksActionsController(...)
        self.menu_ctrl = MenuController(...)
        self.theme_ctrl = ThemeController(...)
    
    def reload_current_category(self):
        """Делегирование вместо прямой логики."""
        category_id = self.structure_ctrl.get_current_category_id()
        if category_id:
            self.links_ctrl.load_category(category_id)
```

**Польза:**
- Упрощение тестирования (mock отдельных контроллеров)
- Лучшая изоляция изменений
- Уменьшение размера MainWindow до 100-150 строк

---

#### 2. Унификация обработки ошибок

**Проблема:** Неконсистентная стратегия (иногда raise, иногда return None, иногда подавление)

**Решение:** Создать документ с правилами

```markdown
# ERROR_HANDLING_STRATEGY.md

## Правила обработки ошибок

### 1. Модели и БД (app/models/)
- **Критичные операции** (сохранение, удаление) → пробрасывать исключение
- **Валидация** → `ValidationError` с детальным сообщением
- **БД ошибки** → `DatabaseError` с context

### 2. Контроллеры (app/controllers/)
- Ловить специфичные исключения от моделей
- Логировать с `exc_info=True`
- Показывать пользователю понятное сообщение через UI

### 3. UI-слой (app/views/)
- **НЕ** подавлять исключения в `try/except` без логирования
- При инициализации - пробрасывать ошибки (не скрывать баги)
- В event handlers - ловить и показывать QMessageBox

### 4. Утилиты (app/utils/)
- Документировать возможные исключения в docstring
- Не логировать (это задача вызывающего кода)
- Пробрасывать специфичные исключения
```

**Пример применения:**
```python
# app/views/dialogs/entity_dialogs.py
# БЫЛО (неправильно):
try:
    self.name_le.returnPressed.connect(...)
except Exception:
    logger.debug("failed to connect", exc_info=True)

# СТАЛО (правильно):
self.name_le.returnPressed.connect(...)  # Если упадёт - это баг, который нужно исправить
```

---

#### 3. Добавить метрики производительности

**Проблема:** Нет visibility в производительность критичных операций

**Решение:**
```python
# app/utils/metrics/performance.py
import time
import functools
import logging

logger = logging.getLogger(__name__)

def measure_time(operation_name: str = None, warn_threshold_ms: float = 100.0):
    """Декоратор для измерения времени выполнения операций.
    
    Args:
        operation_name: Имя операции (по умолчанию - имя функции)
        warn_threshold_ms: Порог для WARNING (миллисекунды)
    
    Example:
        @measure_time("загрузка структуры", warn_threshold_ms=500)
        def load_structure():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                op_name = operation_name or func.__name__
                
                if elapsed_ms > warn_threshold_ms:
                    logger.warning(
                        "[PERFORMANCE] %s занял %.2f мс (порог: %.2f мс)",
                        op_name, elapsed_ms, warn_threshold_ms
                    )
                else:
                    logger.debug(
                        "[PERFORMANCE] %s занял %.2f мс",
                        op_name, elapsed_ms
                    )
        return wrapper
    return decorator

# Использование:
@measure_time("импорт структуры", warn_threshold_ms=1000)
def import_full_structure(data):
    ...
```

---

### Средний приоритет

#### 4. CI/CD Pipeline

**Решение:** Создать GitHub Actions workflow

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: windows-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      
      - name: Run linters
        run: |
          ruff check .
          mypy app/models app/controllers/system
      
      - name: Run tests
        run: pytest --cov=app --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

---

#### 5. Pre-commit hooks

**Решение:**
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format
  
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: ['--maxkb=1000']

# Установка:
# pip install pre-commit
# pre-commit install
```

---

#### 6. Профилирование памяти

**Проблема:** Возможные утечки памяти при длительных сессиях

**Решение:**
```python
# app/utils/diagnostics/memory_profiler.py
import tracemalloc
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class MemoryProfiler:
    """Профилировщик памяти для отладки утечек."""
    
    def __init__(self):
        self.snapshot: Optional[tracemalloc.Snapshot] = None
    
    def start(self):
        """Запускает отслеживание памяти."""
        tracemalloc.start()
        logger.info("Memory profiling started")
    
    def take_snapshot(self):
        """Делает снимок текущего состояния памяти."""
        if not tracemalloc.is_tracing():
            logger.warning("Tracemalloc не запущен")
            return
        
        new_snapshot = tracemalloc.take_snapshot()
        
        if self.snapshot:
            # Сравниваем с предыдущим снимком
            top_stats = new_snapshot.compare_to(self.snapshot, 'lineno')
            
            logger.info("=== Top 10 memory allocations ===")
            for stat in top_stats[:10]:
                logger.info(stat)
        
        self.snapshot = new_snapshot
    
    def stop(self):
        """Останавливает профилирование."""
        tracemalloc.stop()
        logger.info("Memory profiling stopped")

# Использование в main.py:
if args.profile_memory:
    profiler = MemoryProfiler()
    profiler.start()
    
    # Периодические снимки
    QTimer.singleShot(60000, profiler.take_snapshot)  # каждую минуту
```

---

### Низкий приоритет (но полезно)

#### 7. Плагинная система

```python
# app/plugins/interface.py
from typing import Protocol
from PyQt6.QtWidgets import QApplication

class PluginInterface(Protocol):
    """Интерфейс плагина."""
    
    name: str
    version: str
    
    def initialize(self, app: QApplication) -> None:
        """Инициализация плагина."""
        ...
    
    def shutdown(self) -> None:
        """Корректное завершение работы плагина."""
        ...

# app/plugins/manager.py
class PluginManager:
    def __init__(self):
        self.plugins = []
    
    def load_plugins(self, plugin_names: list[str]):
        for name in plugin_names:
            module = importlib.import_module(f"app.plugins.{name}")
            plugin = module.Plugin()  # Должен реализовать PluginInterface
            plugin.initialize(QApplication.instance())
            self.plugins.append(plugin)
    
    def shutdown_all(self):
        for plugin in self.plugins:
            plugin.shutdown()
```

---

#### 8. REST API для автоматизации

```python
# app/api/server.py
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class LinkCreate(BaseModel):
    name: str
    url: str
    category_id: int

@app.post("/api/links")
def create_link(link: LinkCreate):
    # Добавление через Database
    db = get_database()
    link_id = db.links.add_link(link.dict())
    return {"id": link_id}

@app.get("/api/categories")
def list_categories():
    db = get_database()
    return db.categories.get_all_categories()

# Запуск:
# python -m app.api --port 8080
```

---

## 📊 Метрики успеха

После рефакторинга ожидаемые улучшения:

| Метрика | Сейчас | Цель |
|---------|--------|------|
| Сложность MainWindow | 425 строк | <150 строк |
| Покрытие тестами | ~60% | >80% |
| Время старта | ~500ms | <300ms |
| Утечки памяти | Неизвестно | 0 за 8 часов |
| CI/CD | Нет | Есть |
| Типизация (mypy) | Частично | Строгая везде |

---

## 🎯 Итоговая roadmap

### Q1 2026
- ✅ Критичные исправления (выполнено 2025-09-30)
- [ ] Рефакторинг MainWindow
- [ ] Унификация error handling
- [ ] Метрики производительности

### Q2 2026
- [ ] CI/CD pipeline
- [ ] Pre-commit hooks
- [ ] Профилирование памяти
- [ ] Полное покрытие типами (mypy --strict)

### Q3 2026
- [ ] Плагинная система
- [ ] REST API
- [ ] Документация для разработчиков
- [ ] Performance benchmarks

---

**Автор:** Technical Audit AI  
**Дата:** 2025-09-30  
**Версия:** 1.0
