# Стратегия рефакторинга циклической сложности (C901)

## Выполнено

### ✅ `category_model.py::insert_categories_bulk` (C901: 35 → 0)
**Паттерн**: Извлечение последовательных этапов в отдельные методы
- `_validate_and_prepare_items()` — валидация входа
- `_group_by_section()` — группировка
- `_load_max_positions()` — загрузка позиций
- `_load_existing_names()` — загрузка имён
- `_build_insert_batch()` — формирование батча
- `_collect_category_pairs()` — сбор пар для запроса
- `_query_categories_by_pairs()` — запрос к БД
- `_build_category_index()` — индексация результатов
- `_attach_uuid_tokens()` — присоединение токенов

### ✅ `status_bar.py::update_status_bar` (C901: 29 → 0)
**Паттерн**: Извлечение независимых блоков обновления UI
- `_set_text_if_changed()` — безопасное обновление текста
- `_update_counter()` — обновление счётчика
- `_update_db_status()` — статус БД
- `_build_tree_path()` — построение пути из дерева
- `_add_sphere_prefix()` — добавление префикса сферы
- `_add_selected_link()` — добавление выбранной ссылки
- `_update_path()` — обновление пути

## Паттерны рефакторинга

### 1. **Последовательные этапы обработки**
Применяется к: импорт/экспорт, обработка данных, валидация
```python
# До: одна функция с 10+ этапами
def process_data(data):
    # этап 1: валидация (5 условий)
    # этап 2: нормализация (7 условий)
    # этап 3: группировка (4 цикла)
    # этап 4: вставка (6 условий)
    # этап 5: результат (5 условий)

# После: разбиение на методы
def process_data(data):
    validated = self._validate_input(data)
    normalized = self._normalize_data(validated)
    grouped = self._group_by_key(normalized)
    self._insert_batch(grouped)
    return self._build_result(grouped)
```

### 2. **Независимые блоки try-except**
Применяется к: UI обновления, обработка событий
```python
# До: множество вложенных try-except
def update_ui(window):
    try:
        # блок 1: обновление счётчика (10 строк)
        # блок 2: обновление статуса (8 строк)
        # блок 3: обновление пути (15 строк)
    except Exception:
        pass

# После: извлечение независимых блоков
def update_ui(window):
    self._update_counter(window)
    self._update_status(window)
    self._update_path(window)
```

### 3. **Условные ветвления с общей логикой**
Применяется к: парсеры, обработчики типов
```python
# До: множество if-elif с дублированием
def parse_title(url, config):
    if host == "youtube.com":
        # 10 строк специфичной логики
    elif host == "github.com":
        # 12 строк специфичной логики
    # ... ещё 5 хостов
    # общая логика (20 строк)

# После: стратегия + общая логика
def parse_title(url, config):
    specific = self._extract_site_specific(url, host)
    if specific:
        return specific
    return self._extract_generic(url, config)
```

### 4. **Вложенные циклы с накоплением**
Применяется к: импорт структур, обход иерархий
```python
# До: 3-4 уровня вложенности
def import_structure(data):
    for sphere in data:
        for section in sphere.sections:
            for category in section.categories:
                for link in category.links:
                    # обработка (10 условий)

# После: извлечение уровней
def import_structure(data):
    spheres = self._prepare_spheres(data)
    sections = self._prepare_sections(data, spheres)
    categories = self._prepare_categories(data, sections)
    links = self._prepare_links(data, categories)
    self._insert_all(spheres, sections, categories, links)
```

### 5. **Условия с ранним выходом (guard clauses)**
```python
# До: глубокая вложенность
def process(item):
    if item:
        if item.valid:
            if item.data:
                # основная логика

# После: ранние выходы
def process(item):
    if not item:
        return
    if not item.valid:
        return
    if not item.data:
        return
    # основная логика на верхнем уровне
```

## Приоритетный план рефакторинга

### Критичные (C901 > 25) — 12 функций
1. ✅ `category_model.py::insert_categories_bulk` (35)
2. `structure_manager.py::import_full_structure` (36) — **Паттерн 4**
3. `import_worker.py::do_work` (30) — **Паттерн 4**
4. ✅ `status_bar.py::update_status_bar` (29) — **Паттерн 2**
5. `window_ui_setup.py::_apply` (30) — **Паттерн 2**
6. `runtime.py::run` (29) — **Паттерн 1**
7. `title_parser.py::get_title` (28) — **Паттерн 3**
8. `icon_candidates.py::_handle_manifests` (29) — **Паттерн 1**
9. `top_bar_layout_manager.py::_update_separators_visibility` (27) — **Паттерн 2**
10. `width_calculator.py::panel_width` (26) — **Паттерн 1**
11. `dnd/commands.py::_apply_states` (26) — **Паттерн 1**
12. `dnd/commands.py::redo` (29) — **Паттерн 1**

### Высокие (C901 20-25) — 10 функций
13. `icon_candidates.py::_fetch_all_manifests_and_emit` (17)
14. `icon_downloader.py::save_icon` (22)
15. `icon_downloader.py::pick_icon_parallel` (21)
16. `http_client.py::http_request` (22)
17. `dnd/tree.py::move_categories` (21)
18. `browser_profiles_loader.py::_on_window_shown` (21)
19. `favicon_cache.py::_maybe_cleanup` (20)
20. `favicon_cache.py::get` (19)
21. `favicon_cache.py::invalidate` (20)
22. `move_operations_handler.py::_refresh_ui_after_move` (21)

### Средние (C901 13-19) — остальные 54 функции
Применять те же паттерны по мере необходимости.

## Рекомендации

1. **Не ломать поведение**: каждый рефакторинг должен сохранять существующую логику
2. **Тестировать после каждого изменения**: `pytest -xvs tests/`
3. **Проверять типы**: `mypy app/` после каждого файла
4. **Минимальные правки**: извлекать только то, что снижает сложность
5. **Документировать**: добавлять docstring к каждому новому методу

## Метрики успеха

- **До**: 78 функций с C901 > 12
- **После рефакторинга 2 файлов**: 76 функций
- **Цель**: < 20 функций с C901 > 12 (снижение на 75%)
