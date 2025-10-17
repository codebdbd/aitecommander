# Icon Module Architecture

## Overview

Модуль `app/utils/ui/icon/` предоставляет централизованную систему управления иконками в приложении с поддержкой:
- Кэширования (LRU + TTL)
- Валидации форматов (SVG, SVGZ, PNG, JPG)
- Потокобезопасности
- Метрик производительности
- Dependency Injection (опционально)

---

## Module Structure

```
app/utils/ui/icon/
├── __init__.py              # Public API
├── cache_manager.py         # Кэширование QIcon и путей
├── path_service.py          # Резолвинг путей к иконкам
├── validation.py            # Валидация форматов
├── metrics_recorder.py      # Сбор метрик
├── file_service.py          # Файловые операции (копирование, валидация)
├── lock_manager.py          # Централизованные блокировки
├── lru_policy.py            # LRU политика
├── negative_cache.py        # Кэш несуществующих иконок
├── inflight.py              # Дедупликация параллельных запросов
├── icon_resolver.py         # Резолвинг иконок по типу (category, folder, link)
├── selection.py             # UI для выбора иконки
├── ui_helpers.py            # Утилиты для установки иконок на виджеты
└── icon_operations/         # Операции с иконками
    ├── creators.py          # Создание QIcon
    └── converters.py        # Конвертация форматов
```

---

## Core Components

### 1. IconPathService (Singleton + DI)

**Ответственность:** Резолвинг путей к иконкам

**Режимы работы:**
- **Filesystem mode** (dev): Иконки загружаются из `app/resources/ui_icons/`
- **QRC mode** (production): Иконки встроены в бинарь через Qt Resource System

**Использование:**
```python
# Singleton (обратная совместимость)
from app.utils.ui.icon import icon_path_service
path = icon_path_service.get_themed_icon_path('add.svg', 'light')

# DI (для тестов)
from app.utils.ui.icon import IconPathService
service = IconPathService(
    user_icons_dir=Path('/custom/user'),
    ui_icons_dir=Path('/custom/ui'),
    config=mock_config
)
```

---

### 2. IconManager (Singleton + DI)

**Ответственность:** Управление кэшем иконок

**Внутренние компоненты:**
- `ThreadSafeIconCache` — LRU кэш с TTL
- `CacheMetrics` — метрики (hits, misses, load time)
- `QPixmapCache` — Qt-кэш для пикселей

**Использование:**
```python
# Singleton
from app.utils.ui.icon.cache_manager import get_cached_category_icon
icon = get_cached_category_icon('/path/to/icon.png')

# DI
from app.utils.ui.icon import IconManager
manager = IconManager(capacity=200)
```

---

### 3. Icon Creation (GUI Thread Safety)

**Критично:** `QIcon` можно создавать **только в GUI-потоке**

**Правильно:**
```python
from app.utils.ui.icon.icon_operations.creators import themed_icon

# В GUI-потоке
icon = themed_icon('add.svg', theme='dark')
```

**Неправильно:**
```python
# В фоновом потоке — выбросит RuntimeError
def worker():
    icon = themed_icon('add.svg')  # ❌ RuntimeError!
```

**Для фоновых потоков:**
```python
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path_async

async def load_icon():
    icon = await create_icon_from_path_async('/path/to/icon.png')
    # Создание QIcon автоматически выполнится в GUI-потоке
```

---

### 4. File Operations (IconFileService)

**Ответственность:** Копирование и валидация файлов иконок

**Использование:**
```python
from app.utils.ui.icon.file_service import IconFileService

service = IconFileService(user_icons_dir=Path('/user/icons'))

# Копирование с автоматическим переименованием при коллизиях
dst = service.copy_icon_to_user_dir(Path('/source/icon.png'))

# Валидация
is_valid = service.validate_icon_file(Path('/path/to/icon.svg'))
```

---

### 5. Metrics (IconMetricsRecorder)

**Ответственность:** Сбор и логирование метрик производительности

**Режимы:**
- **Manual logging:** Вызов `maybe_log_metrics()` вручную
- **QTimer (default):** Автоматическое логирование каждые 60 секунд

**Метрики:**
- `hits` / `misses` — попадания/промахи кэша
- `disk_loads` — загрузки с диска
- `not_found` — несуществующие иконки
- `avg_load_time` — среднее время загрузки

**Пример лога:**
```
Icon metrics: hits=150 misses=12 hit_rate=92.59% disk_loads=12 not_found=2 avg_load_time=0.0045s load_count=12 uptime=120.5s
```

---

## Thread Safety

### Централизованная система блокировок

**Модуль:** `lock_manager.py` → делегирует в `app.utils.locking`

**Блокировки:**
- `GLOBAL` — глобальная блокировка (высший приоритет)
- `CACHE` — операции с кэшем
- `METRICS` — запись метрик
- `LRU` — обновление LRU политики

**Предотвращение deadlock:**
```python
from app.utils.ui.icon import acquire_multiple_locks, LockLevel

# Блокировки всегда захватываются в упорядоченном порядке
with acquire_multiple_locks(LockLevel.LRU, LockLevel.CACHE):
    # Безопасно — порядок: CACHE → LRU
    pass
```

---

## Caching Strategy

### 1. Path Cache (строки)
- **Ключ:** `{icon_name}::{theme}`
- **Значение:** Путь к файлу (строка)
- **TTL:** Настраивается через `app_config.get_icon_cache_ttl()`

### 2. QIcon Cache (объекты)
- **Ключ:** `{icon_name}::{theme}`
- **Значение:** `QIcon` объект
- **TTL:** Настраивается через `app_config.get_icon_cache_ttl()`

### 3. Negative Cache
- **Цель:** Не повторять поиск несуществующих иконок
- **Механизм:** Exponential backoff (strikes)
- **TTL:** Растёт с каждым промахом

### 4. In-Flight Deduplication
- **Цель:** Предотвратить параллельную загрузку одной иконки
- **Механизм:** `threading.Event` для ожидания первого запроса

---

## Validation

**Поддерживаемые форматы:**
- SVG (`.svg`)
- SVGZ (`.svgz` — сжатый SVG)
- PNG, JPG, JPEG, BMP, GIF, ICO

**Проверки:**
- Валидность имени (защита от path traversal)
- Существование файла
- Корректность формата (magic bytes для растров, XML для SVG)
- Размер файла (защита от слишком больших файлов)

**Использование:**
```python
from app.utils.ui.icon import is_valid_icon_file

if is_valid_icon_file(Path('/path/to/icon.svg')):
    # Безопасно использовать
    pass
```

---

## Packaging (PyInstaller / Briefcase)

### QRC Resources

**Генерация:**
```bash
python scripts/generate_icons_qrc.py
pyrcc6 app/resources/icons.qrc -o app/resources/icons_rc.py
```

**Автоматическое переключение:**
```python
# path_service.py автоматически определяет режим:
try:
    import app.resources.icons_rc
    _QRC_AVAILABLE = True  # Production mode
except ImportError:
    _QRC_AVAILABLE = False  # Development mode
```

### PyInstaller Hook

**Файл:** `hooks/hook-app.utils.ui.icon.py`

**Включает:**
- `PyQt6.QtSvg` — поддержка SVG
- `PIL.Image` — валидация растров
- `app.resources.icons_rc` — встроенные ресурсы

---

## Best Practices

### ✅ DO

1. **Создавайте QIcon только в GUI-потоке**
2. **Используйте async методы для фоновой загрузки**
3. **Валидируйте иконки перед использованием**
4. **Используйте DI в тестах для изоляции**
5. **Логируйте метрики для мониторинга производительности**

### ❌ DON'T

1. **Не создавайте QIcon в worker threads**
2. **Не обходите валидацию (path traversal риск)**
3. **Не мокайте глобальный app_config в продакшене**
4. **Не игнорируйте RuntimeError при создании иконок**

---

## Testing

**Тестовое покрытие:** 36 тестов (100% проходят)

**Категории тестов:**
- `test_icon_validation.py` — валидация форматов
- `test_icon_thread_safety.py` — потокобезопасность
- `test_icon_cache_manager.py` — кэширование
- `test_icon_di.py` — dependency injection
- `test_icon_metrics_recorder.py` — метрики
- `test_icon_file_service.py` — файловые операции

**Запуск:**
```bash
pytest tests/test_icon_*.py -v
```

---

## Performance Metrics

**Startup time:** ~980ms (включая инициализацию кэша)

**Типичные метрики:**
- **Cache hit rate:** 90-95%
- **Average load time:** 0.005-0.010s
- **Disk loads:** 5-10% от запросов

---

## Migration Guide

### From Old API to New

**Было (до Фаз 1-2):**
```python
# Silent fallback при ошибках
icon = themed_icon('add.svg')  # Возвращал пустой QIcon из worker thread
```

**Стало (после Фаз 1-2):**
```python
# Явное исключение
try:
    icon = themed_icon('add.svg')
except RuntimeError as e:
    # Обработка ошибки GUI-потока
    logger.error(f"Cannot create icon: {e}")
```

### Using DI in Tests

**Было:**
```python
def test_icon_loading(monkeypatch):
    monkeypatch.setattr('app.config_data.app_config', mock_config)
    # Глобальный мок
```

**Стало:**
```python
def test_icon_loading():
    service = IconPathService(config=mock_config)
    # Изолированный экземпляр
```

---

## Troubleshooting

### QIcon is empty

**Причина:** Создание вне GUI-потока  
**Решение:** Используйте `create_icon_from_path_async()` или вызывайте из GUI

### Icons not found in packaged app

**Причина:** QRC ресурсы не скомпилированы  
**Решение:** Запустите `generate_icons_qrc.py` и `pyrcc6`

### High memory usage

**Причина:** Слишком большой кэш  
**Решение:** Уменьшите `app_config.get_icon_cache_size()`

### Slow icon loading

**Причина:** Много промахов кэша  
**Решение:** Проверьте метрики (`get_icon_cache_stats()`)

---

## Future Improvements

### Отложенные оптимизации (Фаза 3)

1. ⚠️ **Инкапсуляция глобальных переменных** — переместить `_THEME_ICON_INDEX` в `IconPathService`
2. ⚠️ **Декомпозиция кэшей** — разделить на `PathCache` + `IconCache`
3. ⚠️ **QFileSystemWatcher** — автоматическое обновление индекса при изменении файлов

**Статус:** Не критично, модуль стабилен в текущем виде

---

## References

- **PyQt6 Documentation:** https://www.riverbankcomputing.com/static/Docs/PyQt6/
- **Qt Resource System:** https://doc.qt.io/qt-6/resources.html
- **Project Tests:** `tests/test_icon_*.py`
- **Packaging Guide:** `docs/PACKAGING.md`

---

**Last Updated:** 2025-10-17  
**Module Version:** 2.0 (after Phases 1-2)  
**Status:** ✅ Production Ready
