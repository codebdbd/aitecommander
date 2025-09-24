# Архитектура топбара

## Обзор

Новая архитектура топбара разделена на отдельные компоненты с четким разделением ответственности, следуя принципам SOLID и лучшим практикам PyQt6 2025.

## Компоненты

### 1. TopBarConfig
**Файл:** `top_bar_config.py`
**Ответственность:** Управление конфигурацией
- Загрузка настроек из `app_config`
- Валидация параметров
- Предоставление типобезопасного доступа к конфигурации

### 2. TopBarLayoutCalculator
**Файл:** `top_bar_calculator.py`
**Ответственность:** Расчеты размеров
- Вычисление оптимального количества видимых кнопок
- Кеширование результатов расчетов
- Определение ширины панелей

### 3. TopBarAnimationManager
**Файл:** `top_bar_animator.py`
**Ответственность:** Анимации
- Управление анимациями ширины панелей
- Анимация прозрачности кнопок
- Координация параллельных анимаций

### 4. TopBarEventHandler
**Файл:** `top_bar_event_handler.py`
**Ответственность:** Обработка событий
- Фильтрация событий изменения размеров
- Throttling для предотвращения избыточных пересчетов
- Уведомление о необходимости пересчета

### 5. TopBarLayoutManager
**Файл:** `top_bar_manager.py`
**Ответственность:** Координация
- Управление всеми компонентами
- Dependency injection
- Обработка состояний (узкий режим, обычный режим)

## Преимущества новой архитектуры

### 1. **Разделение ответственности (SRP)**
Каждый класс имеет единственную ответственность и не зависит от деталей реализации других компонентов.

### 2. **Типобезопасность**
- Использование протоколов для интерфейсов
- Строгая типизация параметров
- Валидация конфигурации

### 3. **Тестируемость**
- Каждый компонент можно тестировать независимо
- Mock-friendly интерфейсы
- Легко заменяемые зависимости

### 4. **Производительность**
- Кеширование результатов расчетов
- Throttling событий
- Оптимизированные алгоритмы

### 5. **Поддерживаемость**
- Четкие интерфейсы между компонентами
- Легко добавлять новые функции
- Понятная структура кода

## Использование

```python
from app.views.main_components.topbar import (
    TopBarConfig,
    TopBarLayoutCalculator,
    TopBarAnimationManager,
    TopBarEventHandler,
    TopBarLayoutManager
)

# Создание компонентов
config = TopBarConfig()
calculator = TopBarLayoutCalculator(config)
animator = TopBarAnimationManager(config)
event_handler = TopBarEventHandler(config)
manager = TopBarLayoutManager(window, config, calculator, animator, event_handler)
```

## Миграция со старой версии

Старая версия `TopBarLayoutManager` (1185 строк) заменена на модульную архитектуру. Все публичные интерфейсы сохранены для обратной совместимости.

### Основные изменения:
1. **Разделение на компоненты** - вместо одного большого класса
2. **Dependency injection** - явная передача зависимостей
3. **Устранение динамического доступа** - замена `_safe_get()` на типобезопасные интерфейсы
4. **Улучшенная обработка ошибок** - без маскировки исключений

## Лучшие практики

### 1. **Избегайте динамического доступа**
```python
# Плохо
widget = getattr(window, "some_widget", None)

# Хорошо
def __init__(self, some_widget: QWidget):
    self.some_widget = some_widget
```

### 2. **Используйте протоколы для интерфейсов**
```python
class PanelWidget(Protocol):
    def layout(self) -> Optional[QLayout]: ...
    def setMaximumWidth(self, width: int) -> None: ...
```

### 3. **Кешируйте вычисления**
```python
def calculate_width(self) -> int:
    cache_key = f"width_{id(self)}"
    if cache_key in self._cache:
        return self._cache[cache_key]
    # ... расчет
    self._cache[cache_key] = result
    return result
```

### 4. **Используйте throttling для событий**
```python
def eventFilter(self, obj: QObject, event: QEvent) -> bool:
    if event.type() in (QEvent.Type.Resize, QEvent.Type.LayoutRequest):
        self._schedule_adjust()
    return super().eventFilter(obj, event)
```

## Расширение

Для добавления новых функций:

1. **Создайте интерфейс** в протоколе
2. **Реализуйте** в соответствующем компоненте
3. **Обновите** dependency injection в менеджере
4. **Добавьте** тесты для нового компонента

Это обеспечивает модульность и легкость сопровождения кода.
