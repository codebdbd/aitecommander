# Hotfix: QPointer Import Error

## Проблема

```
ImportError: cannot import name 'QPointer' from 'PyQt6.QtCore'
```

`QPointer` недоступен в PyQt6 (это Qt/C++ класс, не экспортированный в Python bindings).

## Решение

Заменил `QPointer` на стандартный Python `weakref.ref` для отслеживания lifetime виджетов.

## Изменённые файлы

### 1. `app/views/main_components/ui/topbar/width_calculator.py`

**Было**:
```python
from PyQt6.QtCore import QEvent, QObject, QPointer

qpointer = QPointer(panel)
cache_key = (qpointer, count)
```

**Стало**:
```python
from PyQt6.QtCore import QEvent, QObject
import weakref

panel_ref = weakref.ref(panel)
cache_key = (panel_ref, count)
```

### 2. `tests/test_cache_improvements.py`

Обновлены импорты и названия тестов:
- `TestWidthCalculatorQPointerTracking` → `TestWidthCalculatorWeakrefTracking`
- Убран импорт `QPointer`
- Добавлен импорт `weakref`

### 3. `CACHE_IMPROVEMENTS_SUMMARY.md`

Обновлена документация:
- Все упоминания `QPointer` заменены на `weakref.ref`
- Обновлены примеры кода

## Функциональность

✅ **Сохранена полностью**:
- Автоматическая очистка кеша при удалении виджета через `weakref.finalize`
- Проверка "мёртвых" ссылок через `ref() is None` вместо `isNull()`
- Event filter для автоматической инвалидации
- Все остальные улучшения (TTL refresh, QPixmapCache, async guard)

## Преимущества weakref над QPointer

1. **Стандартная библиотека Python** — нет зависимости от Qt bindings
2. **Работает с любыми Python объектами** — не только QObject
3. **Совместим с PyQt6** — корректно работает с Qt reference counting
4. **Меньше overhead** — чистый Python без C++ wrapper

## Проверка

```powershell
# Импорт модуля
python -c "from app.views.main_components.ui.topbar.width_calculator import WidthCalculator; print('OK')"

# Запуск приложения
python -m app.main

# Запуск тестов
pytest tests/test_cache_improvements.py -v
```

## Статус

✅ **ИСПРАВЛЕНО** — приложение запускается без ошибок.

Все 6 рекомендаций из PyQt6 Cache Review реализованы с использованием `weakref` вместо `QPointer`.
