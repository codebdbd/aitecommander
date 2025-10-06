# 📚 Business Layer Developer Guide

## Обзор

Бизнес-слой приложения (`app/controllers/business/`) отвечает за координацию бизнес-логики между UI и слоем данных. Он построен на принципах **чистой архитектуры** с чётким разделением ответственности.

---

## 🏗️ Архитектура

### Структура модулей

```
app/controllers/business/
├── __init__.py                    # Экспорт публичного API
├── structure_business.py          # Фасад для структуры (сферы/разделы/категории)
├── links_business.py              # Бизнес-логика ссылок
└── structure/                     # Специализированные сервисы
    ├── async_service.py           # Асинхронные операции
    ├── cache_service.py           # Кэширование данных
    ├── crud_service.py            # CRUD операции
    ├── event_service.py           # Обработка событий
    ├── query_service.py           # Запросы данных
    ├── validation_service.py      # Валидация
    └── warmup_service.py          # Прогрев кэша
```

### Принципы дизайна

1. **Single Responsibility Principle (SRP)** — каждый сервис отвечает за одну область
2. **Dependency Injection (DI)** — все зависимости передаются через конструктор
3. **Facade Pattern** — `StructureBusinessLogic` — тонкий фасад над сервисами
4. **Separation of Concerns** — UI не знает о БД, бизнес-логика не знает о Qt виджетах

---

## 🎯 Основные компоненты

### 1. StructureBusinessLogic

**Назначение**: Координатор всех операций со структурой (сферы, разделы, категории).

**Ключевые методы**:
```python
# Загрузка данных
def load_structure_async(sphere_id: int) -> None
def load_spheres_async() -> None

# CRUD операции
def create_section(data: dict) -> Optional[dict]
def update_category(category_id: int, data: dict) -> Optional[dict]
def delete_section(section_id: int) -> tuple[bool, dict, int, int]

# Управление состоянием
def set_current_sphere(sphere_id: int) -> None
def shutdown(timeout: int = 5000) -> None
```

**Сигналы**:
```python
structure_loaded = pyqtSignal(list)           # Структура загружена
item_added = pyqtSignal(str, int, dict)       # Элемент добавлен
item_updated = pyqtSignal(str, int, dict)     # Элемент обновлён
item_deleted = pyqtSignal(str, int)           # Элемент удалён
error_occurred = pyqtSignal(str, str)         # Ошибка
```

**Пример использования**:
```python
from app.controllers.business import StructureBusinessLogic
from app.models.db import Database

# Инициализация
db = Database()
business = StructureBusinessLogic(db, parent=main_window)

# Подключение сигналов
business.structure_loaded.connect(ui.on_structure_loaded)
business.error_occurred.connect(ui.show_error)

# Загрузка данных
business.load_spheres_async()
business.set_current_sphere(1)
business.load_structure_async(1)

# CRUD операции
section_data = business.create_section({
    'name': 'Новый раздел',
    'sphere_id': 1,
    'is_active': True
})

# Cleanup при закрытии
business.shutdown(timeout=5000)
```

---

### 2. LinksBusinessLogic

**Назначение**: Управление ссылками (загрузка, поиск, CRUD, избранное).

**Ключевые методы**:
```python
# Загрузка
def load_links(category_id: int) -> None
def search_links(query: str) -> None
def load_recent_links(limit: int = 10) -> None
def load_favorite_links() -> None

# CRUD
def create_link(link_data: dict) -> None
def update_link(link_id: int, link_data: dict) -> None
def delete_link(link_id: int) -> None

# Batch операции
def update_link_order(link_ids: list[int]) -> None
def delete_links_batch(link_ids: list[int]) -> None
```

**Сигналы**:
```python
links_loaded = pyqtSignal(list, int, int)     # Ссылки загружены
link_updated = pyqtSignal(dict)               # Ссылка обновлена
link_deleted = pyqtSignal(int)                # Ссылка удалена
error_occurred = pyqtSignal(str)              # Ошибка
```

**Пример использования**:
```python
from app.controllers.business import LinksBusinessLogic

# Инициализация
links_business = LinksBusinessLogic(db, parent=main_window)

# Подключение сигналов
links_business.links_loaded.connect(ui.display_links)
links_business.error_occurred.connect(ui.show_error)

# Загрузка ссылок
links_business.load_links(category_id=42)

# Поиск
links_business.search_links("python tutorial")

# Создание ссылки
links_business.create_link({
    'name': 'Python Docs',
    'url': 'https://docs.python.org',
    'type': 'documentation',
    'category_id': 42
})
```

---

## 🔧 Специализированные сервисы

### StructureAsyncService

**Назначение**: Изоляция асинхронных операций и управление перезагрузками.

**Ключевые возможности**:
- Debounce для частых операций
- QTimer для отложенных перезагрузок
- Управление lifecycle асинхронных компонентов

**Пример**:
```python
# Внутри StructureBusinessLogic
self.async_service.load_structure_async(sphere_id)
self.async_service.schedule_structure_reload(delay_ms=150)
```

---

### StructureCacheService

**Назначение**: Централизованное кэширование данных структуры.

**Кэшируемые данные**:
- Список сфер (`all_spheres`)
- Разделы по сфере (`sections_{sphere_id}`)
- Категории по разделу (`categories_{section_id}`)
- Первая категория сферы (`first_category_id:{sphere_id}`)

**Методы инвалидации**:
```python
# Инвалидация структуры
cache_service.invalidate_structure_cache(sphere_id)

# Инвалидация разделов
cache_service.invalidate_sections_cache(sphere_id)

# Инвалидация категорий
cache_service.invalidate_categories_cache(section_id, sphere_id)
```

**Пример**:
```python
# Получение с кэшированием
spheres = cache_service.get_spheres()
sections = cache_service.get_sections(sphere_id=1)
categories = cache_service.get_categories(section_id=5)

# Прогрев кэша после загрузки
cache_service.warm_first_category(sphere_id, structure_payload)
```

---

### StructureCrudService

**Назначение**: CRUD операции с автоматической инвалидацией кэша.

**Паттерн использования**:
```python
# Создание
section_data = crud_service.create_section({
    'name': 'Новый раздел',
    'sphere_id': 1,
    'is_active': True
})
# ✅ Автоматически: эмиссия сигнала, инвалидация кэша

# Обновление
category_data = crud_service.update_category(category_id, {
    'name': 'Обновлённое название'
})
# ✅ Автоматически: эмиссия сигнала, инвалидация кэша

# Удаление
success, old_data, cats_count, links_count = crud_service.delete_section(section_id)
# ✅ Автоматически: эмиссия сигнала, инвалидация кэша

# Batch операции
moved_ids = crud_service.move_categories_batch(
    category_ids=[1, 2, 3],
    target_section_id=10,
    base_row=0
)
# ✅ Batch режим: одна перезагрузка для всех операций
```

---

### StructureEventService

**Назначение**: Обработка событий изменения данных.

**Batch режим** (для массовых операций):
```python
# Начало batch режима
event_service.begin_batch()

try:
    # Множество операций
    for item in items:
        crud_service.update_category(item['id'], item['data'])
finally:
    # Завершение batch режима
    event_service.end_batch()
    # ✅ Одна перезагрузка вместо N перезагрузок
```

**Обработчики событий**:
```python
# Автоматически вызываются при эмиссии сигналов
def on_item_added(item_type: str, parent_id: int, item_data: dict) -> None
def on_item_updated(item_type: str, item_id: int, item_data: dict) -> None
def on_item_deleted(item_type: str, item_id: int) -> None
```

---

## 🚀 Лучшие практики

### 1. Асинхронность

**✅ ПРАВИЛЬНО**:
```python
# Все операции с БД через async методы
business.load_structure_async(sphere_id)
links_business.load_links(category_id)
```

**❌ НЕПРАВИЛЬНО**:
```python
# НЕ вызывайте БД напрямую из UI-потока
sections = db.sections.get_sections(sphere_id)  # Блокирует UI!
```

---

### 2. Управление памятью

**✅ ПРАВИЛЬНО**:
```python
# Всегда передавайте parent для Qt объектов
business = StructureBusinessLogic(db, parent=main_window)

# Вызывайте shutdown при закрытии
def closeEvent(self, event):
    self.business.shutdown(timeout=5000)
    super().closeEvent(event)
```

**❌ НЕПРАВИЛЬНО**:
```python
# Без parent — утечки памяти
business = StructureBusinessLogic(db)  # parent=None

# Без shutdown — потоки не завершаются
# Просто закрываем окно
```

---

### 3. Обработка ошибок

**✅ ПРАВИЛЬНО**:
```python
# Подключайте обработчики ошибок
business.error_occurred.connect(self.show_error_dialog)

def show_error_dialog(self, title: str, message: str):
    QMessageBox.critical(self, title, message)
```

**❌ НЕПРАВИЛЬНО**:
```python
# Игнорирование ошибок
# Пользователь не узнает о проблемах
```

---

### 4. Batch операции

**✅ ПРАВИЛЬНО**:
```python
# Используйте batch режим для массовых операций
business.begin_batch()
try:
    for category_id in category_ids:
        business.update_category(category_id, data)
finally:
    business.end_batch()
# ✅ Одна перезагрузка UI
```

**❌ НЕПРАВИЛЬНО**:
```python
# Без batch режима
for category_id in category_ids:
    business.update_category(category_id, data)
# ❌ N перезагрузок UI — медленно!
```

---

### 5. Мониторинг производительности

**Использование метрик**:
```python
from app.utils.metrics.performance_monitor import measure_time, get_metrics

# Декорирование методов
@measure_time("load_structure", log_threshold_ms=200)
def load_structure_async(self, sphere_id: int) -> None:
    ...

# Получение статистики
metrics = get_metrics()
stats = metrics.get_stats("load_structure")
print(f"Avg: {stats['avg']:.2f}ms, Max: {stats['max']:.2f}ms")

# Логирование сводки
from app.utils.metrics.performance_monitor import log_performance_summary
log_performance_summary()
```

---

## 🐛 Отладка

### Включение debug логов

```python
import logging

# Для всего бизнес-слоя
logging.getLogger('app.controllers.business').setLevel(logging.DEBUG)

# Для конкретного модуля
logging.getLogger('app.controllers.business.structure_business').setLevel(logging.DEBUG)
```

### Проверка состояния кэша

```python
# Получение всех ключей кэша
cache_manager = business.cache_manager
print("Cached keys:", cache_manager._cache.keys())

# Проверка конкретного ключа
cached_value = cache_manager.get("sections_1")
print("Sections for sphere 1:", cached_value)

# Инвалидация для тестирования
cache_manager.invalidate("sections_1")
```

### Мониторинг сигналов

```python
# Подключение debug обработчиков
def debug_signal(*args):
    print(f"Signal emitted: {args}")

business.structure_loaded.connect(debug_signal)
business.item_added.connect(debug_signal)
business.error_occurred.connect(debug_signal)
```

---

## 📊 Метрики производительности

### Ключевые метрики

| Операция | Целевое время | Критичное время |
|----------|---------------|-----------------|
| `load_spheres` | < 50ms | > 200ms |
| `load_structure` | < 100ms | > 500ms |
| `load_categories` | < 50ms | > 200ms |
| `create_section` | < 100ms | > 300ms |
| `delete_category` | < 150ms | > 500ms |

### Cache hit rate цели

| Кэш | Целевой hit rate |
|-----|------------------|
| `all_spheres` | > 95% |
| `sections_{id}` | > 80% |
| `categories_{id}` | > 70% |
| `first_category_id` | > 90% |

---

## 🧪 Тестирование

### Unit тесты

```python
import pytest
from unittest.mock import Mock
from app.controllers.business import StructureBusinessLogic

def test_create_section(qtbot):
    # Arrange
    db = Mock()
    business = StructureBusinessLogic(db)
    qtbot.addWidget(business)
    
    # Act
    result = business.create_section({
        'name': 'Test Section',
        'sphere_id': 1,
        'is_active': True
    })
    
    # Assert
    assert result is not None
    assert result['name'] == 'Test Section'
```

### Integration тесты

```python
def test_full_workflow(qtbot, test_db):
    # Arrange
    business = StructureBusinessLogic(test_db)
    qtbot.addWidget(business)
    
    # Act & Assert
    # 1. Загрузка сфер
    with qtbot.waitSignal(business.spheres_loaded, timeout=1000):
        business.load_spheres_async()
    
    # 2. Создание раздела
    with qtbot.waitSignal(business.item_added, timeout=1000):
        business.create_section({'name': 'Test', 'sphere_id': 1})
    
    # 3. Cleanup
    business.shutdown(timeout=1000)
```

---

## 📝 Чеклист для новых разработчиков

- [ ] Прочитал архитектурный обзор
- [ ] Понимаю разделение на сервисы
- [ ] Знаю, как использовать async методы
- [ ] Умею работать с сигналами Qt
- [ ] Понимаю систему кэширования
- [ ] Знаю, когда использовать batch режим
- [ ] Умею добавлять метрики производительности
- [ ] Написал unit тесты для нового кода
- [ ] Проверил отсутствие утечек памяти
- [ ] Добавил docstrings для публичных методов

---

## 🔗 Связанные документы

- [Async Operations Guide](ASYNC_OPERATIONS.md)
- [Cache Strategy](CACHE_STRATEGY.md)
- [Testing Guide](TESTING_GUIDE.md)
- [Performance Optimization](PERFORMANCE_OPTIMIZATION.md)

---

## 💡 Часто задаваемые вопросы

### Q: Почему нельзя вызывать БД напрямую из UI?
**A**: Это блокирует UI-поток. Все операции с БД должны быть асинхронными через `run_db()` или async методы бизнес-логики.

### Q: Когда использовать batch режим?
**A**: При выполнении множества (>3) операций подряд, чтобы избежать множественных перезагрузок UI.

### Q: Как добавить новый тип элемента структуры?
**A**: 
1. Добавить TypedDict в `structure_modules/models/types.py`
2. Добавить методы в `StructureCrudService`
3. Обновить обработчики в `StructureEventService`
4. Добавить тесты

### Q: Почему мой кэш не работает?
**A**: Проверьте:
1. Правильно ли формируется ключ кэша
2. Не инвалидируется ли кэш слишком часто
3. Установлен ли правильный TTL
4. Используйте `cache_manager.get()` для проверки

---

**Версия документа**: 1.0  
**Последнее обновление**: 2025-10-06  
**Автор**: Development Team
