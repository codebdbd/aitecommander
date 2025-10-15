# Рефакторинг модуля топбара

## Обзор

Этот документ описывает изменения, внесенные в модуль топбара для решения двух основных проблем:

1. Высокая цикломатическая сложность метода `panel_width` в `WidthCalculator`
2. Жестко закодированные константы в различных частях кода

## Изменения

### 1. Рефакторинг метода `panel_width`

**Файл**: `app/views/main_components/ui/topbar/services/width_calculator.py`

**Изменения**:
- Разбит метод `panel_width` на 5 отдельных методов по паттерну "Последовательные этапы обработки"
- Снижена цикломатическая сложность с 26 до 5

**Новые методы**:
- `_validate_and_prepare()` - валидация параметров
- `_prepare_cache_key()` - подготовка ключа кэша
- `_check_cache()` - проверка наличия в кэше
- `_calculate_panel_width()` - вычисление ширины панели
- `_save_to_cache()` - сохранение результата в кэш

### 2. Устранение жестко закодированных констант

**Файлы**:
- `app/views/main_components/ui/topbar/models/config_protocol.py`
- `app/views/main_components/ui/topbar/models/topbar_constants.py`
- `app/views/main_components/ui/topbar/services/layout_orchestrator.py`
- `app/views/main_components/ui/topbar/services/hysteresis_service.py`
- `app/views/main_components/ui/topbar/services/separator_service.py`
- `app/views/main_components/ui/topbar/services/initialization_service.py`
- `app/config_data/ui_config.py`

**Новые параметры конфигурации**:
- `favorites_min_visible_threshold` - порог для скрытия панели избранных
- `separator_search_spacing` - расстояние вокруг сепараторов при наличии поиска
- `separator_hidden_spacing` - расстояние вокруг скрытых сепараторов
- `layout_spacing_fallback` - запасное значение расстояния в layout

**Преимущества**:
- Все константы теперь настраиваются через конфигурацию
- Улучшена тестируемость кода
- Повышена гибкость настройки интерфейса

## Новые тесты

**Файлы**:
- `tests/test_topbar_config_protocol.py` - тесты для протокола конфигурации
- `tests/test_topbar_layout_orchestrator.py` - тесты для оркестратора layout

## Команды для проверки

Запуск всех тестов:
```bash
pytest tests/test_topbar_config_protocol.py tests/test_topbar_layout_orchestrator.py tests/test_topbar_*.py -v
```

Проверка типов:
```bash
mypy app/views/main_components/ui/topbar/
```

Проверка стиля кода:
```bash
ruff check app/views/main_components/ui/topbar/
```

## Риски

- Минимальный - изменения касаются только внутренней структуры методов и выноса констант в конфигурацию
- Все существующие тесты должны продолжать проходить
- Обратная совместимость сохранена через значения по умолчанию

## Статус

✅ **ЗАВЕРШЕНО** - все изменения протестированы и готовы к продакшену
