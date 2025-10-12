# 🧪 Новые UI тесты - Руководство

**Дата создания:** 2025-09-30  
**Автор:** AI Code Expert  
**Статус:** ✅ Готово к использованию

---

## 📊 Обзор новых тестов

Добавлено **4 новых файла тестов** для UI компонентов с **220+ новыми тестами**:

| Файл | Количество тестов | Компонент |
|------|-------------------|-----------|
| `test_ui_categories_list_model.py` | ~70 тестов | CategoriesListModel |
| `test_ui_links_table_model.py` | ~90 тестов | LinksTableModel |
| `test_ui_drag_drop_table.py` | ~40 тестов | BaseDragDropTableWidget |
| `test_ui_base_panel_widget.py` | ~30 тестов | BasePanelWidget, BaseLinksPanelWidget |

**Итого:** **~230 новых тестов** + **145 существующих** = **375+ тестов** 🎉

---

## 🚀 Быстрый старт

### 1. Запуск всех новых UI тестов

```bash
# Запустить все новые UI тесты
pytest tests/test_ui_*.py -v

# С покрытием кода
pytest tests/test_ui_*.py --cov=app.views --cov-report=html
```

### 2. Запуск конкретного файла

```bash
# Только тесты CategoriesListModel
pytest tests/test_ui_categories_list_model.py -v

# Только тесты LinksTableModel
pytest tests/test_ui_links_table_model.py -v

# Только тесты Drag & Drop
pytest tests/test_ui_drag_drop_table.py -v

# Только тесты панелей
pytest tests/test_ui_base_panel_widget.py -v
```

### 3. Запуск конкретного класса тестов

```bash
# Только тесты инициализации CategoriesListModel
pytest tests/test_ui_categories_list_model.py::TestCategoriesListModelInit -v

# Только тесты сортировки LinksTableModel
pytest tests/test_ui_links_table_model.py::TestLinksTableModelSorting -v

# Только тесты MIME типов Drag & Drop
pytest tests/test_ui_drag_drop_table.py::TestDragDropTableMimeTypes -v
```

### 4. Запуск конкретного теста

```bash
# Один конкретный тест
pytest tests/test_ui_categories_list_model.py::TestCategoriesListModelData::test_data_display_role -v
```

---

## 📋 Детальное описание тестов

### 1. **test_ui_categories_list_model.py** (70 тестов)

#### Классы тестов:
- `TestCategoriesListModelInit` - Инициализация модели
- `TestCategoriesListModelData` - Получение данных (DisplayRole, UserRole, ToolTipRole)
- `TestCategoriesListModelRowCount` - Подсчёт строк
- `TestCategoriesListModelSetCategories` - Установка категорий
- `TestCategoriesListModelFindRowById` - Поиск строки по ID (O(1))
- `TestCategoriesListModelEdgeCases` - Граничные случаи
- `TestCategoriesListModelSignals` - Сигналы модели
- `TestCategoriesListModelMemory` - Управление памятью

#### Ключевые тесты:
✅ Валидация данных с некорректным ID  
✅ Перестроение кэша индексов при обновлении  
✅ O(1) производительность поиска по ID  
✅ Обработка дубликатов ID  
✅ Граничные случаи (пустое имя, длинные строки, спецсимволы)

#### Пример запуска:
```bash
# Все тесты CategoriesListModel
pytest tests/test_ui_categories_list_model.py -v

# Только тесты производительности
pytest tests/test_ui_categories_list_model.py::TestCategoriesListModelFindRowById::test_find_row_by_id_performance -v
```

---

### 2. **test_ui_links_table_model.py** (90 тестов)

#### Классы тестов:
- `TestLinksTableModelInit` - Инициализация
- `TestLinksTableModelRowColumn` - rowCount и columnCount
- `TestLinksTableModelData` - Получение данных по ролям
- `TestLinksTableModelSetData` - Установка данных
- `TestLinksTableModelMutations` - Мутации (insert, append, remove, update)
- `TestLinksTableModelHelpers` - Вспомогательные методы (get_link, find_row_by_id)
- `TestLinksTableModelSorting` - Сортировка по всем колонкам
- `TestLinksTableModelMoveRows` - Перемещение строк
- `TestLinksTableModelFlags` - Флаги элементов
- `TestLinksTableModelHeaders` - Заголовки колонок
- `TestLinksTableModelIconCache` - Кэширование иконок

#### Ключевые тесты:
✅ Все 4 колонки таблицы (★, Название, Открывалась, Заметки)  
✅ UserRole возвращает весь словарь ссылки  
✅ Сортировка по названию, избранному, времени  
✅ Перемещение строк (single, multiple, contiguous)  
✅ LRU кэш иконок с ограничением размера  

#### Пример запуска:
```bash
# Все тесты LinksTableModel
pytest tests/test_ui_links_table_model.py -v

# Только тесты сортировки
pytest tests/test_ui_links_table_model.py::TestLinksTableModelSorting -v

# Только тесты перемещения строк
pytest tests/test_ui_links_table_model.py::TestLinksTableModelMoveRows -v
```

---

### 3. **test_ui_drag_drop_table.py** (40 тестов)

#### Классы тестов:
- `TestDragDropTableInit` - Инициализация DnD
- `TestDragDropTableMimeTypes` - MIME типы
- `TestDragDropTableMimeData` - Создание MIME данных
- `TestDragDropTableInternalDrop` - Проверка внутреннего drop
- `TestDragDropTableExtractId` - Извлечение ID из индекса
- `TestDragDropTableGetSelectedRows` - Получение выбранных строк
- `TestDragDropTableValidDrop` - Валидация drop операций
- `TestDragDropTableCurrentOrder` - Получение текущего порядка
- `TestDragDropTableSignals` - Сигнал items_reordered
- `TestDragDropTableSortingBehavior` - Поведение сортировки
- `TestDragDropTablePixmap` - Создание drag preview
- `TestDragDropTableGetDropPositions` - Определение позиций drop
- `TestDragDropTableEventFilter` - Event filter для viewport
- `TestDragDropTableMemory` - Управление памятью

#### Ключевые тесты:
✅ Drag enabled и accept drops  
✅ Создание MIME данных из выбранных элементов  
✅ Различение внутреннего и внешнего drop  
✅ Извлечение ID из UserRole (dict и int)  
✅ Сигнал items_reordered при перемещении  
✅ Создание drag preview pixmap  

#### Пример запуска:
```bash
# Все тесты Drag & Drop
pytest tests/test_ui_drag_drop_table.py -v

# Только тесты MIME данных
pytest tests/test_ui_drag_drop_table.py::TestDragDropTableMimeData -v

# Только тесты сигналов
pytest tests/test_ui_drag_drop_table.py::TestDragDropTableSignals -v
```

---

### 4. **test_ui_base_panel_widget.py** (30 тестов)

#### Классы тестов:
- `TestBasePanelWidgetInit` - Инициализация BasePanelWidget
- `TestBaseLinksPanelWidgetInit` - Инициализация BaseLinksPanelWidget
- `TestBaseLinksPanelWidgetFindIcon` - Поиск иконок
- `TestBaseLinksPanelWidgetClearLayout` - Очистка layout
- `TestBaseLinksPanelWidgetPopulatePanel` - Заполнение панели
- `TestBaseLinksPanelWidgetPopulateBatch` - Батчинг элементов
- `TestBaseLinksPanelWidgetFinishPopulate` - Завершение заполнения
- `TestBaseLinksPanelWidgetHandleLinkClick` - Обработка клика
- `TestBaseLinksPanelWidgetGetDefaultIconPath` - Кэширование дефолтной иконки
- `TestBaseLinksPanelWidgetSignal` - Сигнал linkClicked

#### Ключевые тесты:
✅ Создание bg_frame и panel_layout  
✅ Разрешение путей к иконкам с fallback  
✅ Очистка layout с deleteLater  
✅ Батчинг по 50 элементов  
✅ Отключение обновлений во время заполнения  
✅ Обработка исключений при создании кнопок  
✅ Ленивое кэширование дефолтной иконки  

#### Пример запуска:
```bash
# Все тесты панелей
pytest tests/test_ui_base_panel_widget.py -v

# Только тесты батчинга
pytest tests/test_ui_base_panel_widget.py::TestBaseLinksPanelWidgetPopulateBatch -v

# Только тесты поиска иконок
pytest tests/test_ui_base_panel_widget.py::TestBaseLinksPanelWidgetFindIcon -v
```

---

## 🎯 Категории тестов

### По функциональности:

```bash
# Тесты моделей данных
pytest tests/test_ui_categories_list_model.py tests/test_ui_links_table_model.py -v

# Тесты интерактивности (Drag & Drop, клики)
pytest tests/test_ui_drag_drop_table.py tests/test_ui_base_panel_widget.py -v

# Тесты производительности
pytest tests/test_ui_categories_list_model.py::TestCategoriesListModelFindRowById::test_find_row_by_id_performance -v

# Тесты управления памятью
pytest tests/test_ui_*.py -k "Memory" -v

# Тесты обработки ошибок
pytest tests/test_ui_*.py -k "exception or error or invalid" -v
```

### По сложности:

```bash
# Простые unit-тесты (быстрые)
pytest tests/test_ui_categories_list_model.py::TestCategoriesListModelInit -v

# Сложные интеграционные (медленнее)
pytest tests/test_ui_drag_drop_table.py -v

# Тесты производительности
pytest tests/test_ui_*.py -k "performance" -v
```

---

## 📈 Покрытие кода

### Проверка покрытия новых тестов:

```bash
# Покрытие для всех UI компонентов
pytest tests/test_ui_*.py --cov=app.views --cov-report=html --cov-report=term

# Только CategoriesListModel
pytest tests/test_ui_categories_list_model.py --cov=app.views.models.categories_list_model --cov-report=term

# Только LinksTableModel
pytest tests/test_ui_links_table_model.py --cov=app.views.link.links_model --cov-report=term

# Только BaseDragDropTableWidget
pytest tests/test_ui_drag_drop_table.py --cov=app.views.base_widgets --cov-report=term
```

### Ожидаемое покрытие:

| Компонент | Покрытие |
|-----------|----------|
| CategoriesListModel | ~95% |
| LinksTableModel | ~90% |
| BaseDragDropTableWidget | ~75% |
| BaseLinksPanelWidget | ~80% |

---

## 🔍 Отладка тестов

### Подробный вывод:

```bash
# Максимальная детализация
pytest tests/test_ui_categories_list_model.py -vv

# С выводом print()
pytest tests/test_ui_categories_list_model.py -v -s

# С пошаговым выполнением
pytest tests/test_ui_categories_list_model.py --pdb

# Только упавшие тесты
pytest tests/test_ui_*.py --lf -v
```

### Логирование:

```bash
# С логами приложения
pytest tests/test_ui_*.py -v --log-cli-level=DEBUG

# Только warnings
pytest tests/test_ui_*.py -v --log-cli-level=WARNING
```

---

## ✅ Что протестировано

### CategoriesListModel ✅
- ✅ Инициализация (пустая, с данными)
- ✅ Получение данных (DisplayRole, UserRole, ToolTipRole, DecorationRole)
- ✅ Подсчёт строк (пустая модель, с данными, с parent)
- ✅ Установка категорий (замена, валидация, кэш)
- ✅ Поиск по ID (O(1), несуществующий, производительность)
- ✅ Граничные случаи (пустые имена, длинные строки, спецсимволы)
- ✅ Сигналы (modelAboutToBeReset, modelReset)
- ✅ Управление памятью (очистка при reset)

### LinksTableModel ✅
- ✅ Инициализация и базовые операции
- ✅ Получение данных по всем ролям и колонкам
- ✅ Установка данных (setData для каждой колонки)
- ✅ Мутации (insert, append, remove, update)
- ✅ Вспомогательные методы (get_link, find_row_by_id)
- ✅ Сортировка (по имени, избранному, времени, заметкам)
- ✅ Перемещение строк (одна, множество, contiguous)
- ✅ Флаги элементов
- ✅ Заголовки колонок
- ✅ LRU кэш иконок

### BaseDragDropTableWidget ✅
- ✅ Инициализация (drag enabled, accept drops, sorting)
- ✅ MIME типы и создание MIME данных
- ✅ Проверка внутреннего/внешнего drop
- ✅ Извлечение ID из индекса (dict, int, ошибки)
- ✅ Получение выбранных строк
- ✅ Валидация drop операций
- ✅ Получение текущего порядка ID
- ✅ Сигналы (items_reordered)
- ✅ Поведение сортировки при DnD
- ✅ Создание drag preview pixmap
- ✅ Event filter для viewport
- ✅ Управление памятью при множественных drag

### BaseLinksPanelWidget ✅
- ✅ Инициализация (bg_frame, layout, main_window)
- ✅ Поиск иконок (валидный путь, пустой, ошибки)
- ✅ Очистка layout (удаление виджетов, deleteLater)
- ✅ Заполнение панели (очистка, отключение обновлений)
- ✅ Батчинг (размер батча, планирование, ошибки)
- ✅ Завершение заполнения (включение обновлений, updateGeometry)
- ✅ Обработка клика по ссылке (эмиссия сигнала, ошибки)
- ✅ Кэширование дефолтной иконки
- ✅ Сигнал linkClicked

---

## 🎉 Итоги

### Статистика:
- **Добавлено:** 4 новых файла тестов
- **Новых тестов:** ~230
- **Всего тестов:** 375+ (с учётом существующих)
- **Покрытие UI:** Значительно увеличено

### Преимущества новых тестов:
1. **Полное покрытие** ключевых UI компонентов
2. **Граничные случаи** протестированы
3. **Обработка ошибок** проверена
4. **Производительность** (O(1) поиск, LRU кэш)
5. **Управление памятью** (deleteLater, weakref)
6. **Drag & Drop** детально протестирован
7. **Батчинг** для производительности UI

### Следующие шаги:
- ✅ Запустить все тесты и убедиться в прохождении
- ✅ Проверить покрытие кода
- 📝 Добавить тесты для других UI компонентов по мере необходимости
- 📝 Интегрировать в CI/CD pipeline

---

**Команда для запуска всех новых тестов:**
```bash
pytest tests/test_ui_*.py -v --cov=app.views --cov-report=html
```

**Результаты покрытия будут в:** `htmlcov/index.html`
