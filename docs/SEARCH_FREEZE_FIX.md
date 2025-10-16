# Исправление "залипания" ширины строки поиска

## Проблема

`SearchWidgetManager.freeze_width()` устанавливает одинаковые `minimumWidth` и `maximumWidth` для фиксации ширины строки поиска при скрытии контейнера. Однако отсутствовал симметричный механизм восстановления диапазона, что приводило к "залипанию" строки поиска на узком значении после возвращения контейнера.

### Сценарий проблемы

```python
# 1. Начальное состояние
search.minimumWidth() == 140  # MIN_SEARCH_WIDTH_ABSOLUTE
search.maximumWidth() == 800  # MAX_WIDGET_WIDTH

# 2. Контейнер скрывается -> freeze_width(search, 140)
search.minimumWidth() == 140
search.maximumWidth() == 140  # Зафиксировано!

# 3. Контейнер показывается -> clamp_width() пытается пересчитать
# ПРОБЛЕМА: cur_min = 140, и новый min_search = max(140, 140) = 140
# Строка поиска "залипла" на минимальной ширине!
```

## Решение

Добавлен метод `unfreeze_width()` с сохранением предыдущих ограничений:

### Новый API

```python
class SearchWidgetManager:
    def freeze_width(self, search: QLineEdit | None, width: int) -> None:
        """Заморозить ширину с сохранением текущих ограничений."""
        
    def unfreeze_width(
        self, search: QLineEdit | None, default_min: int | None = None
    ) -> None:
        """Разморозить ширину и восстановить ограничения."""
```

### Механизм работы

1. **freeze_width()** сохраняет текущие `(minimumWidth, maximumWidth)` в `_saved_constraints`
2. **unfreeze_width()** восстанавливает сохранённые значения или использует defaults
3. **clamp_width()** автоматически вызывает `unfreeze_width()` перед новым расчётом

### Пример использования

```python
# Инициализация
search_manager = SearchWidgetManager(width_calculator)
search = QLineEdit()
search.setMinimumWidth(140)
search.setMaximumWidth(800)

# Контейнер скрывается
search_manager.freeze_width(search, 140)
# Внутри:
# - Сохранено: _saved_constraints[id(search)] = (140, 800)
# - Установлено: min=140, max=140

# Контейнер показывается
search_manager.unfreeze_width(search)
# Внутри:
# - Восстановлено: min=140, max=800
# - Удалено: _saved_constraints[id(search)]

# Или автоматически через clamp_width():
search_manager.clamp_width(ctx, applied_counts, min_search_width=140)
# Внутри:
# 1. unfreeze_width(search, default_min=140)  # Автоматически!
# 2. Пересчёт и применение новых ограничений
```

## Изменения в коде

### search_manager.py

```python
class SearchWidgetManager:
    def __init__(self, width_calculator) -> None:
        # ...
        # Хранение предыдущих ограничений для восстановления
        self._saved_constraints: dict[int, tuple[int, int]] = {}

    def freeze_width(self, search: QLineEdit | None, width: int) -> None:
        if not isinstance(search, QLineEdit):
            return
        try:
            # Сохранить текущие ограничения перед заморозкой
            search_id = id(search)
            if search_id not in self._saved_constraints:
                current_min = search.minimumWidth()
                current_max = search.maximumWidth()
                self._saved_constraints[search_id] = (current_min, current_max)

            search.setMaximumWidth(width)
            search.setMinimumWidth(width)
        except Exception as e:
            logger.debug("Failed to freeze width: %s", e, exc_info=True)

    def unfreeze_width(
        self, search: QLineEdit | None, default_min: int | None = None
    ) -> None:
        if not isinstance(search, QLineEdit):
            return
        try:
            search_id = id(search)
            if search_id in self._saved_constraints:
                # Восстановить сохранённые ограничения
                saved_min, saved_max = self._saved_constraints.pop(search_id)
                search.setMinimumWidth(saved_min)
                search.setMaximumWidth(saved_max)
            else:
                # Использовать значения по умолчанию
                min_width = (
                    default_min if default_min is not None
                    else C.MIN_SEARCH_WIDTH_ABSOLUTE
                )
                search.setMinimumWidth(min_width)
                search.setMaximumWidth(self._max_widget_width)
        except Exception as e:
            logger.debug("Failed to unfreeze width: %s", e, exc_info=True)

    def clamp_width(self, ctx, applied_counts, min_search_width) -> int | None:
        search = ctx.search
        if not isinstance(search, QLineEdit):
            return None
        try:
            # Разморозить перед новым расчётом, чтобы избежать "залипания"
            self.unfreeze_width(search, default_min=min_search_width)
            
            # ... остальная логика расчёта ...
```

## Тестирование

Создан файл `tests/test_search_manager_freeze.py` с тестами:

- ✅ Сохранение ограничений при `freeze_width()`
- ✅ Восстановление ограничений при `unfreeze_width()`
- ✅ Использование defaults при отсутствии сохранённых значений
- ✅ Множественные циклы freeze/unfreeze
- ✅ Автоматическая разморозка в `clamp_width()`
- ✅ Предотвращение "залипания" после показа контейнера
- ✅ Граничные случаи (None widget, нулевая ширина, и т.д.)

## Преимущества решения

1. **Симметричность**: `freeze_width()` ↔ `unfreeze_width()`
2. **Автоматизм**: `clamp_width()` автоматически размораживает
3. **Безопасность**: Сохранение предыдущих значений предотвращает потерю данных
4. **Идемпотентность**: Повторные вызовы безопасны
5. **Обратная совместимость**: Существующий код продолжает работать

## Потенциальные риски

### Утечка памяти

**Риск**: `_saved_constraints` может накапливать записи для удалённых виджетов.

**Митигация**: 
- `unfreeze_width()` удаляет запись через `pop()`
- `clamp_width()` автоматически вызывает `unfreeze_width()`
- Виджеты обычно живут весь жизненный цикл приложения

**Мониторинг**:
```python
# Добавить в cleanup() или периодическую проверку
def cleanup_stale_constraints(self):
    """Очистить записи для удалённых виджетов."""
    stale_ids = [
        widget_id for widget_id in self._saved_constraints
        if not self._is_widget_alive(widget_id)
    ]
    for widget_id in stale_ids:
        del self._saved_constraints[widget_id]
```

### Множественные freeze без unfreeze

**Риск**: Повторный `freeze_width()` может перезаписать сохранённые значения.

**Решение**: Проверка `if search_id not in self._saved_constraints` сохраняет только первые значения.

## Логирование

Добавлено debug-логирование для отслеживания:

```python
logger.debug("SearchWidgetManager: saved constraints for freeze (min=%d, max=%d)")
logger.debug("SearchWidgetManager: froze width to %d")
logger.debug("SearchWidgetManager: restored constraints (min=%d, max=%d)")
logger.debug("SearchWidgetManager: reset to defaults (min=%d, max=%d)")
```

## Связанные файлы

- `app/views/main_components/ui/topbar/services/search_manager.py` - основная логика
- `app/views/main_components/ui/topbar/services/narrow_mode_service.py` - использует `freeze_width()`
- `app/views/main_components/ui/topbar/services/layout_orchestrator.py` - вызывает `clamp_width()`
- `tests/test_search_manager_freeze.py` - unit-тесты
- `docs/SEARCH_FREEZE_FIX.md` - эта документация

## Ссылки на код

- `search_manager.py:31` - `_saved_constraints` dictionary
- `search_manager.py:73` - `freeze_width()` implementation
- `search_manager.py:106` - `unfreeze_width()` implementation
- `search_manager.py:58` - автоматический вызов в `clamp_width()`
- `narrow_mode_service.py:100` - использование `freeze_search_width()`
- `layout_orchestrator.py:127` - вызов `freeze_search_width()` при скрытии контейнера
