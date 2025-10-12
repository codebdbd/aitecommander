# 🧪 Руководство по тестированию Aite Commander

**Дата:** 2025-09-30  
**Проект:** Aite Commander (Link Manager)

---

## 📋 Структура тестов

```
tests/
├── __init__.py                  # Инициализация пакета
├── conftest.py                  # Общие fixtures для pytest
├── test_validators.py           # Тесты валидаторов (85 тестов)
├── test_links_business.py       # Тесты бизнес-логики (20+ тестов)
├── test_ui_components.py        # Тесты UI компонентов (15+ тестов)
└── test_database.py             # Тесты базы данных (25+ тестов)
```

**Всего:** **145+ тестов** покрывают критичные компоненты приложения

---

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
# Установите dev-зависимости
pip install -r requirements-dev.txt
```

**Основные тестовые библиотеки:**
- `pytest` - фреймворк тестирования
- `pytest-qt` - поддержка PyQt6
- `pytest-cov` - покрытие кода
- `pytest-mock` - мокирование

---

### 2. Запуск всех тестов

```bash
# Запуск всех тестов
pytest

# С подробным выводом
pytest -v

# С покрытием кода
pytest --cov=app --cov-report=html
```

---

### 3. Запуск конкретных тестов

```bash
# Только тесты валидаторов
pytest tests/test_validators.py

# Только тесты бизнес-логики
pytest tests/test_links_business.py

# Только UI тесты
pytest tests/test_ui_components.py -m qt

# Только тесты БД
pytest tests/test_database.py

# Конкретный тест
pytest tests/test_validators.py::TestValidateUrl::test_valid_http_url
```

---

### 4. Запуск по маркерам

```bash
# Только unit-тесты
pytest -m unit

# Только интеграционные тесты
pytest -m integration

# Только Qt-тесты
pytest -m qt

# Медленные тесты (> 1 сек)
pytest -m slow

# Исключить медленные тесты
pytest -m "not slow"
```

---

## 📊 Категории тестов

### 1. **test_validators.py** - Тесты валидаторов

**85 тестов** для проверки корректности валидации пользовательского ввода.

#### Покрываемые валидаторы:
- ✅ `validate_url()` - валидация URL (9 тестов)
- ✅ `validate_name()` - валидация имён (10 тестов)
- ✅ `validate_email()` - валидация email (6 тестов)
- ✅ `validate_port()` - валидация портов (8 тестов)
- ✅ `sanitize_filename()` - очистка имён файлов (6 тестов)
- ✅ `validate_file_path()` - валидация путей к файлам (5 тестов)
- ✅ `validate_folder_path()` - валидация путей к папкам (3 тесты)
- ✅ `validate_icon_path()` - валидация иконок (3 теста)

**Примеры запуска:**
```bash
# Все тесты валидаторов
pytest tests/test_validators.py -v

# Только тесты URL
pytest tests/test_validators.py::TestValidateUrl -v

# Только тесты email
pytest tests/test_validators.py::TestValidateEmail -v
```

**Пример теста:**
```python
def test_valid_http_url(self):
    """Корректный HTTP URL проходит валидацию."""
    valid, error = validate_url("http://example.com")
    assert valid is True
    assert error is None
```

---

### 2. **test_links_business.py** - Тесты бизнес-логики

**20+ тестов** для проверки логики управления ссылками.

#### Покрываемые компоненты:
- ✅ `LinksBusinessLogic` - основная бизнес-логика
- ✅ Загрузка ссылок (`load_links`)
- ✅ Поиск ссылок (`search_links`)
- ✅ Избранное (`toggle_favorite`, `get_favorite_links`)
- ✅ Недавние ссылки (`get_recent_links`)
- ✅ Создание/обновление (`save_link_async`)
- ✅ Удаление (`delete_link`)
- ✅ Валидация ID
- ✅ Обработка ошибок
- ✅ Кеширование

**Примеры запуска:**
```bash
# Все тесты бизнес-логики
pytest tests/test_links_business.py -v

# Только тесты загрузки
pytest tests/test_links_business.py -k "load" -v

# Только тесты валидации
pytest tests/test_links_business.py::TestLinksBusinessValidation -v
```

**Пример теста:**
```python
def test_load_links_valid_category(self, business_logic, mock_db):
    """Тест загрузки ссылок для валидной категории."""
    category_id = 10
    
    received_links = []
    business_logic.links_loaded.connect(lambda links: received_links.append(links))
    
    business_logic.load_links(category_id)
    
    mock_db.links.get_links_by_category.assert_called_once_with(category_id)
    assert len(received_links) == 1
```

---

### 3. **test_ui_components.py** - Тесты UI компонентов

**15+ тестов** для проверки работы UI компонентов PyQt6.

#### Покрываемые компоненты:
- ✅ `DialogManager` - диалоговые окна
- ✅ `signal_guard` - блокировка сигналов
- ✅ `suspend_updates` - приостановка обновлений
- ✅ `ThemeVariables` - система CSS-переменных
- ✅ `ResourceManager` - управление ресурсами
- ✅ `WeakRef` - слабые ссылки
- ✅ `QTimer` - таймеры и дебаунсинг

**Примеры запуска:**
```bash
# Все UI тесты
pytest tests/test_ui_components.py -v

# Только тесты диалогов
pytest tests/test_ui_components.py::TestDialogManager -v

# Только тесты тем
pytest tests/test_ui_components.py::TestThemeVariables -v
```

**Пример теста:**
```python
def test_signal_guard_blocks_signals(self, qapp, qtbot):
    """Тест блокировки сигналов."""
    from app.utils.ui.signal_utils import signal_guard
    
    button = QPushButton("Test")
    qtbot.addWidget(button)
    
    clicked_count = []
    button.clicked.connect(lambda: clicked_count.append(1))
    
    # С guard - сигнал блокируется
    with signal_guard(button):
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    
    assert len(clicked_count) == 0  # Не сработал!
```

---

### 4. **test_database.py** - Тесты базы данных

**25+ тестов** для проверки работы с SQLite.

#### Покрываемые аспекты:
- ✅ Схема БД (таблицы, FK, cascade)
- ✅ SQL запросы (SELECT, INSERT, UPDATE, DELETE)
- ✅ Индексы (миграция 0005)
- ✅ Транзакции (commit, rollback, isolation)
- ✅ Миграции (версионирование)
- ✅ Производительность (bulk insert, indexed queries)

**Примеры запуска:**
```bash
# Все тесты БД
pytest tests/test_database.py -v

# Только тесты схемы
pytest tests/test_database.py::TestDatabaseSchema -v

# Только тесты индексов
pytest tests/test_database.py::TestDatabaseIndexes -v

# Исключить медленные тесты
pytest tests/test_database.py -m "not slow" -v
```

**Пример теста:**
```python
def test_index_improves_query(self, db_with_data):
    """Тест улучшения производительности с индексом."""
    conn = sqlite3.Connection(db_with_data)
    
    conn.execute("CREATE INDEX idx_link_is_favorite ON link(is_favorite) WHERE is_favorite = 1")
    
    cursor = conn.execute("EXPLAIN QUERY PLAN SELECT * FROM link WHERE is_favorite = 1")
    plan = cursor.fetchall()
    
    plan_text = str(plan).upper()
    assert "INDEX" in plan_text  # Использует индекс!
```

---

## 🔧 Fixtures

### Общие fixtures (conftest.py)

```python
@pytest.fixture
def qapp():
    """QApplication для Qt-тестов."""
    
@pytest.fixture
def mock_db():
    """Mock базы данных."""
    
@pytest.fixture
def temp_db():
    """Временная БД для тестов."""
    
@pytest.fixture
def db_with_data():
    """БД с тестовыми данными."""
```

---

## 📈 Покрытие кода

### Генерация отчёта о покрытии

```bash
# HTML отчёт
pytest --cov=app --cov-report=html

# Откройте htmlcov/index.html в браузере
```

### Покрытие по модулям

```bash
# Покрытие валидаторов
pytest tests/test_validators.py --cov=app.utils.ui.validators --cov-report=term

# Покрытие бизнес-логики
pytest tests/test_links_business.py --cov=app.controllers.business --cov-report=term

# Покрытие UI утилит
pytest tests/test_ui_components.py --cov=app.utils.ui --cov-report=term
```

---

## 🎯 Лучшие практики

### 1. Именование тестов

```python
# ✅ Хорошо - описательное имя
def test_valid_http_url_passes_validation():
    ...

# ❌ Плохо - непонятное имя
def test_url():
    ...
```

### 2. Arrange-Act-Assert паттерн

```python
def test_delete_link():
    # Arrange - подготовка
    link_id = 42
    deleted_ids = []
    business.link_deleted.connect(lambda id_: deleted_ids.append(id_))
    
    # Act - действие
    business.delete_link(link_id)
    
    # Assert - проверка
    assert link_id in deleted_ids
```

### 3. Использование fixtures

```python
# ✅ Хорошо - переиспользуемый fixture
@pytest.fixture
def business_logic(mock_db):
    return LinksBusinessLogic(mock_db)

def test_something(business_logic):
    # Используем готовый объект
    business_logic.load_links(10)
```

### 4. Моки для изоляции

```python
# ✅ Хорошо - мокаем внешние зависимости
with patch('app.utils.db.api.run_db') as mock_run_db:
    mock_run_db.side_effect = lambda func, **kwargs: func()
    business.load_links(10)
```

---

## ⚡ Производительность тестов

### Быстрые тесты (< 1 сек)

```bash
# Исключить медленные тесты
pytest -m "not slow"
```

### Параллельный запуск

```bash
# Установить pytest-xdist
pip install pytest-xdist

# Запустить на 4 ядрах
pytest -n 4
```

---

## 🐛 Отладка тестов

### Подробный вывод

```bash
# Показать print() в тестах
pytest -s

# Максимально подробный вывод
pytest -vv

# Остановиться на первой ошибке
pytest -x

# Показать traceback полностью
pytest --tb=long
```

### Запуск конкретного упавшего теста

```bash
# Последний упавший
pytest --lf

# Только упавшие
pytest --failed-first
```

---

## 📊 CI/CD интеграция

### GitHub Actions пример

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements-dev.txt
      - run: pytest --cov=app --cov-report=xml
      - uses: codecov/codecov-action@v3
```

---

## 📝 Добавление новых тестов

### Шаблон теста

```python
"""Тесты для нового модуля."""

import pytest
from app.my_module import MyClass


@pytest.fixture
def my_object():
    """Fixture для тестируемого объекта."""
    return MyClass()


class TestMyClass:
    """Тесты для MyClass."""
    
    def test_basic_functionality(self, my_object):
        """Тест базовой функциональности."""
        # Arrange
        input_data = "test"
        
        # Act
        result = my_object.process(input_data)
        
        # Assert
        assert result == "expected"
    
    def test_error_handling(self, my_object):
        """Тест обработки ошибок."""
        with pytest.raises(ValueError):
            my_object.process(None)
```

---

## ✅ Чек-лист перед коммитом

- [ ] Все тесты проходят: `pytest`
- [ ] Нет упавших тестов: `pytest --lf`
- [ ] Покрытие не упало: `pytest --cov=app`
- [ ] Новый код покрыт тестами
- [ ] Тесты проходят быстро (< 10 сек для всех)

---

## 📚 Полезные ссылки

- [Pytest документация](https://docs.pytest.org/)
- [pytest-qt документация](https://pytest-qt.readthedocs.io/)
- [PyQt6 тестирование](https://www.riverbankcomputing.com/static/Docs/PyQt6/)

---

## 🎉 Итоги

**Создано тестов:** 145+  
**Покрытие:** Валидаторы, бизнес-логика, UI, БД  
**Время выполнения:** < 5 секунд (без slow)  
**Статус:** ✅ **Готово к использованию**

**Команда для быстрого старта:**
```bash
pip install -r requirements-dev.txt
pytest -v
```

Тесты помогут:
- 🐛 Находить баги на ранних стадиях
- 🔒 Предотвращать регрессии
- 📈 Поддерживать качество кода
- 🚀 Уверенно делать рефакторинг

**Happy Testing!** 🧪
