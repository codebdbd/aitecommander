# Разработка Aite Commander

Руководство для разработчиков PyQt6-приложения **Aite Commander** — менеджера закладок с 4-уровневой иерархией, 6 темами и 6 языками.

## Архитектура проекта

### Структура каталогов

```
aitecommander/
├── app/                              # Основной пакет приложения
│   ├── main.py                       # Точка входа: логирование, ошибки, запуск Qt
│   ├── settings.py                   # AppSettings: QSettings (темы, шрифты, хоткеи)
│   ├── interfaces.py                 # Протоколы (Protocol) для слабой связанности
│   ├── config_data/                  # Конфигурационные данные и адаптеры
│   ├── core/                         # Ядро приложения
│   │   ├── constants.py              # AppConstants: имя, версия, размеры окна
│   │   ├── database_manager.py       # Менеджер подключений к SQLite
│   │   ├── error_handler.py          # Глобальный обработчик ошибок
│   │   ├── hotkey_manager.py         # Регистрация горячих клавиш
│   │   ├── log_manager.py            # Настройка логирования
│   │   ├── settings_manager.py       # Менеджер настроек
│   │   ├── style_manager.py          # Управление стилями и темами
│   │   ├── worker_manager.py         # Пул потоков для фоновых задач
│   │   ├── strings.py                # Строковые константы
│   │   ├── results.py                # Типы результатов операций
│   │   └── paths/                    # path_manager.py — утилиты путей
│   ├── models/                       # Слой данных и бизнес-логики
│   │   ├── entities/                 # Sphere, Section, Category, Link, StructureCoordinator
│   │   ├── managers/                 # backup, duplicate_resolver, import_export, structure
│   │   ├── workers/                  # base_worker, backup, bad_url_check, export,
│   │   │                             #   icon_refresh, import, initialization
│   │   ├── base/                     # db_base.py, db_connection_protocol.py
│   │   ├── migrations/               # SQL/Python миграции (0001_init.sql — 0006_add_favorite_position_index.py)
│   │   ├── protocols/                # bulk_operations.py
│   │   ├── types/                    # link_type, link_types, category_types, constants
│   │   ├── utils/                    # link_validators, link_bulk_upsert_service, structure_stats
│   │   ├── db.py                     # Работа с SQLite
│   │   └── schema.sql                # SQL-схема базы данных
│   ├── controllers/                  # Контроллеры
│   │   ├── ui/                       # UI-контроллеры
│   │   │   ├── action_controller.py
│   │   │   ├── menu_controller.py
│   │   │   ├── theme_controller.py
│   │   │   ├── top_panels_controller.py
│   │   │   ├── category_tiles_controller.py
│   │   │   ├── window_facade.py
│   │   │   ├── types.py
│   │   │   ├── state/                # ui_state_manager, task_scheduler
│   │   │   ├── structure/            # structure_ui_controller, tree_update_service,
│   │   │   │                         #   tree_management, tree_snapshot_service,
│   │   │   │                         #   tree_tiles_service, tree_state_service,
│   │   │   │                         #   selection_handling, selection_actions,
│   │   │   │                         #   selection_workflow_service, spheres_bar_controller,
│   │   │   │                         #   icon_handling, item_operations,
│   │   │   │                         #   item_deletion_service, item_dialogs_service
│   │   │   ├── links/                # controller, table_controller, clipboard,
│   │   │   │                         #   links_actions, base_component, handlers,
│   │   │   │                         #   link_operations, exceptions
│   │   │   ├── dialogs/              # dialog_manager, link_dialog_controller,
│   │   │   │                         #   database_controller, system_dialog_controller,
│   │   │   │                         #   link_operations_controller
│   │   │   └── undo/                 # commands, commands_links, commands_structure,
│   │   │                             #   dispatcher, stack, base
│   │   ├── business/                 # Бизнес-логика
│   │   │   ├── links_business.py
│   │   │   ├── structure_business.py
│   │   │   └── structure/            # Подмодули бизнес-логики структуры
│   │   ├── structure_modules/        # Модули работы со структурой
│   │   ├── structure_services/       # Сервисы структуры (7+ файлов)
│   │   ├── system/                   # db_init, app_shutdown_controller, keyboard_manager,
│   │   │                             #   window_setup/ (coordinator, business, wiring, ui,
│   │   │                             #   types, keyboard)
│   │   └── services/                 # icon_refresh_service, bad_url_check_service
│   ├── views/                        # UI-представления (Qt виджеты)
│   │   ├── windows/
│   │   │   ├── main_window.py        # Главное окно
│   │   │   ├── main_window_protocol.py
│   │   │   └── dialogs/
│   │   │       ├── base_dialog.py
│   │   │       ├── entity_dialogs.py
│   │   │       ├── database_dialogs.py
│   │   │       ├── browser_profile_dialog.py
│   │   │       ├── import_browser_dialog.py
│   │   │       ├── restore_db_dialog.py
│   │   │       ├── icon_refresh_dialog.py
│   │   │       ├── bad_url_cleanup_dialog.py
│   │   │       ├── async_operation_dialog.py
│   │   │       ├── link_dialog/       # link_dialog, link_dialog_ui,
│   │   │       │                      #   link_dialog_signals, link_dialog_handlers,
│   │   │       │                      #   icon_utils, handlers_mixins/ (8 миксинов)
│   │   │       └── file_search_dialog/ # file_search_dialog, search_signals,
│   │   │                              #   search_worker, common
│   │   ├── widgets/
│   │   │   ├── base/                 # base_widgets.py, base_panel_widgets.py
│   │   │   ├── link/                 # base_table, links_model, data_management,
│   │   │   │                         #   population_manager, row_operations, item_builders
│   │   │   ├── panels/               # favorites_panel_widget, recent_panel_widget,
│   │   │   │                         #   quick_add_panel_widget
│   │   │   ├── tiles/                # widget, list_view, delegate
│   │   │   ├── tree_components/      # move_operations_handler
│   │   │   ├── status_bar.py
│   │   │   ├── language_selector.py
│   │   │   ├── custom_widgets.py
│   │   │   ├── link_button_mixin.py
│   │   │   └── protocols.py
│   │   ├── main_components/          # Компоненты главного окна
│   │   │   ├── common/               # constants, decorators, exceptions, helpers,
│   │   │   │                         #   protocols, resource_manager
│   │   │   ├── initialization/       # window_initializer, init_steps_config,
│   │   │   │                         #   init_scheduler, init_diagnostics, init_status,
│   │   │   │                         #   init_db_gate
│   │   │   └── ui/
│   │   │       ├── window_ui_setup.py
│   │   │       ├── window_widgets.py
│   │   │       ├── bottom_panel_setup.py
│   │   │       ├── right_panel_setup.py
│   │   │       └── topbar/           # top_bar_setup, top_bar_layout_manager,
│   │   │                             #   toolbar_adapters, controllers/, services/,
│   │   │                             #   models/, utils/
│   │   ├── common/                   # retranslatable.py
│   │   └── models/                   # structure_tree_model, categories_list_model
│   ├── services/                     # Сервисный слой
│   │   ├── theme_registry.py         # Реестр тем
│   │   ├── theme_stylesheet_service.py
│   │   ├── theme_import_service.py
│   │   ├── share_service.py          # Социальный шеринг
│   │   ├── bulk_operation_service.py # Массовые операции
│   │   ├── structure_service.py      # Сервис структуры
│   │   ├── structure_context_service.py
│   │   ├── structure_share_service.py
│   │   ├── links_service.py          # Сервис ссылок
│   │   ├── db_ui_adapter.py          # Адаптер БД ↔ UI
│   │   ├── database_restore_worker.py
│   │   ├── batch_operation_base.py
│   │   ├── protocols.py
│   │   └── uow.py                    # Unit of Work
│   ├── utils/                        # Утилиты
│   │   ├── browser/                  # import_browser_html.py, browser_profiles/
│   │   ├── links/                    # link_parser, link_factory, link_utils, parser/
│   │   ├── ui/                       # async_helpers, clipboard, db_tasks, db_sync,
│   │   │                             #   db_errors, full_diag, signal_suppression,
│   │   │                             #   signal_guard, updates, focus/, qt/
│   │   ├── validators/               # basic, link, structure, import validators
│   │   ├── db/                       # api, migrations, sql_helpers,
│   │   │                             #   db_error_handler, synchronization,
│   │   │                             #   tasks/base, executors/pool
│   │   ├── cache/                    # base, topbar_snapshot
│   │   ├── locking/                  # manager — файловые блокировки
│   │   ├── metrics/                  # startup_metrics, performance_monitor
│   │   ├── i18n/                     # common — утилиты локализации
│   │   ├── system/                   # date_utils
│   │   ├── logging/                  # logging utilities
│   │   ├── common.py
│   │   └── share_paths.py
│   ├── resources/                    # Ресурсы
│   │   ├── app_resources.qrc         # Основной .qrc-манифест
│   │   ├── icons.qrc                 # Манифест иконок
│   │   ├── app_resources_rc.py       # Скомпилированные ресурсы
│   │   ├── icons_rc.py               # Скомпилированные иконки
│   │   ├── app_icon.ico              # Иконка приложения
│   │   ├── ui_icons/                 # Иконки по темам (dark/, violet_pulse/)
│   │   ├── qss.rar                   # Архив QSS-тем
│   │   └── (themes/, qss/, logo/)    # Темы и стили
│   └── startup/                      # Инициализация приложения
│       ├── runtime.py                # Основной цикл запуска Qt (run())
│       ├── initializer.py            # ApplicationInitializer
│       ├── app_factory.py            # Фабрика QApplication
│       ├── argument_parser.py        # Парсинг CLI-аргументов
│       ├── signal_handling.py        # Обработка POSIX-сигналов
│       └── browser_profiles_loader.py # Загрузка профилей браузеров
├── i18n/                             # Локализация
│   ├── app_en.ts / .qm              # Английский
│   ├── app_ru.ts / .qm              # Русский
│   ├── app_uk.ts / .qm              # Украинский
│   ├── app_fr.ts / .qm              # Французский
│   ├── app_es.ts / .qm              # Испанский
│   ├── app_de.ts / .qm              # Немецкий
│   ├── language_service.py           # Сервис смены языка
│   ├── resources_rc.py               # Скомпилированные ресурсы переводов
│   ├── i18n.qrc                      # QRC-манифест переводов
│   ├── locale_utils.py               # Утилиты локали
│   ├── fix_ts_file.py                # Утилита исправления .ts файлов
│   ├── app.pro                       # Проект lupdate/lrelease
│   └── __init__.py
├── tests/                            # Тестовый набор (30+ файлов)
│   ├── conftest.py                   # Bootstrap для импортов (sys.path)
│   └── test_*.py                     # Тесты: database, structure, commands,
│                                     #   bulk, theme, migration, dialog, etc.
├── docs/                             # Документация
├── scripts/                          # Утилитарные скрипты
│   ├── build.py                      # Скрипт сборки
│   ├── migrate_icons_ico_to_png.py   # Миграция иконок
│   └── arch_diag_generate.py         # Генерация арх. диаграмм
├── aitecommander.spec                # PyInstaller .spec
├── aitecommander.bat                 # Windows-лаунчер
├── pyproject.toml                    # Метаданные проекта и зависимости (hatchling)
├── requirements.txt                  # Зависимости (дублирует pyproject.toml)
├── pytest.ini                        # Конфигурация pytest
├── .pre-commit-config.yaml           # Pre-commit хуки
├── .python-version                   # Версия Python (3.12)
├── .gitignore
├── uv.lock                           # Lock-файл uv
├── LICENSE                           # MIT License
├── README.md
├── CAPABILITIES.md                   # Описание возможностей
└── THEME_AUDIT_DETAILED.md           # Аудит тем оформления
```

### Взаимодействие компонентов

Архитектура основана на разделении **UI-представлений** (views) и **бизнес-логики** (models/controllers) через сигналы и слоты PyQt6:

```
┌─────────────┐     сигналы/слоты     ┌─────────────────┐
│   Views     │ ◄──────────────────► │   Controllers   │
│  (Qt UI)    │                       │  (UI-логика)    │
└─────────────┘                       └─────────────────┘
       ▲                                     │
       │                                     ▼
       │                             ┌─────────────────┐
       │                             │    Models       │
       │                             │  (данные + БД)  │
       │                             └─────────────────┘
       │                                     │
       │                                     ▼
       │                             ┌─────────────────┐
       └──────────────────────────── │   Services      │
                                     │  (бизнес-логика)│
                                     └─────────────────┘
```

**Ключевые принципы:**

1. **Views** не содержат бизнес-логики. Виджеты отображают данные, полученные через `set_data()` / `update_data()`, и испускают сигналы при действиях пользователя.

2. **Controllers** связывают Views и Models. Обрабатывают пользовательские действия, вызывают методы Models и обновляют Views через сигналы.

3. **Models** инкапсулируют данные и работу с БД. Не зависят от Qt UI.

4. **Services** реализуют бизнес-операции (импорт, экспорт, шеринг, темы). Используются Controllers.

5. **Workers** (`app/models/workers/`) — наследники `QThread` или `QObject` для фоновых задач (загрузка иконок, проверка URL, резервное копирование). Взаимодействие через сигналы.

6. **Протоколы** (`app/interfaces.py`, `app/models/protocols/`, `app/views/widgets/protocols.py`) определяют контракты между компонентами для слабой связанности.

---

## Настройка окружения разработчика

### Требования

- Python 3.12+
- Windows 10/11 (основная платформа)
- pip или uv (рекомендуется)

### Развертывание

```bash
# Клонирование репозитория
git clone https://github.com/codebdbd/aitecommander.git
cd aitecommander

# Создание виртуального окружения
python -m venv .venv

# Активация (Windows)
.venv\Scripts\activate

# Активация (Linux/macOS)
source .venv/bin/activate

# Установка зависимостей разработки
pip install -e ".[dev]"
```

### Альтернатива: uv

```bash
# Установка uv (если не установлен)
pip install uv

# Создание окружения и установка зависимостей
uv sync
```

### Pre-commit хуки

Проект использует pre-commit для автоматической проверки кода перед коммитом.

```bash
# Установка pre-commit
pip install pre-commit

# Активация хуков
pre-commit install
```

**Конфигурация `.pre-commit-config.yaml`:**

| Хук | Описание |
|-----|----------|
| `ruff --fix` | Автоматическое исправление ошибок линтинга |
| `ruff-format` | Форматирование кода (заменяет Black) |
| `mypy` | Проверка типов |
| `end-of-file-fixer` | Гарантия перевода строки в конце файла |
| `trailing-whitespace` | Удаление завершающих пробелов |

> Ruff и Mypy работают с дефолтными настройками — конфигурация задаётся через pre-commit hooks, а не через `pyproject.toml`.

**Ручной запуск:**

```bash
# Проверка всех файлов
pre-commit run --all-files

# Только линтинг
ruff check app/

# Только форматирование
ruff format app/

# Только типизация
mypy app/
```

---

## Стандарты кодирования (Code Style)

### Именование

| Элемент | Стиль | Пример |
|---------|-------|--------|
| Модули, функции, переменные | `snake_case` | `get_theme()`, `load_bookmarks()` |
| Классы | `PascalCase` | `MainWindow`, `BookmarkController` |
| Константы | `UPPER_SNAKE_CASE` | `APP_NAME`, `DEFAULT_WIDTH` |
| Методы PyQt (слоты, переопределённые) | `camelCase` (Qt-стиль) | `setWindowTitle()`, `setCentralWidget()` |
| Сигналы PyQt | `camelCase` + `Signal` | `itemClicked`, `dataChanged` |
| Приватные атрибуты | `_leading_underscore` | `_qs`, `_db_connection` |
| Протоколы | `PascalCase` + `Like`/`Supports` | `MainWindowLike`, `SupportsUpdates` |

**Важно:** Методы Qt API (`setWindowTitle`, `resize`, `menuBar`) сохраняют `camelCase` даже в нашем коде. Это соглашение PyQt — не нарушать.

### Форматирование

**Ruff** используется как линтер и форматтер (заменяет Black). Конфигурация — дефолтная, задаётся через pre-commit.

Базовые параметры (по умолчанию Ruff):
- Длина строки: 88 символов (дефолт Ruff)
- Кавычки: `"`
- Отступ: 4 пробела
- Target: Python 3.12

### Правила PyQt6

1. **Импорты:**
   ```python
   from PyQt6.QtWidgets import QMainWindow, QApplication
   from PyQt6.QtCore import Qt, QTimer, pyqtSignal
   from PyQt6.QtGui import QAction, QIcon
   ```

2. **Сигналы** объявляются как классовые атрибуты:
   ```python
   class BookmarkModel(QAbstractItemModel):
       itemClicked = pyqtSignal(str, int)  # name, id
       dataChanged = pyqtSignal()
   ```

3. **Слоты** декорируются `@pyqtSlot()` при явном объявлении:
   ```python
   @pyqtSlot(str, int)
   def on_item_clicked(self, name: str, item_id: int) -> None:
       ...
   ```

4. **Типизация:** Все методы должны иметь аннотации типов возвращаемого значения и параметров.

5. **Протоколы** используются для определения контрактов (см. `app/interfaces.py`).

---

## Работа с UI и ресурсами

### Изменение интерфейса

Проект **не использует** `.ui` файлы и компиляцию `pyuic6`. Все UI создаются программно в Python-коде.

**Структура UI:**
- `app/views/windows/` — окна (главное окно, диалоги)
- `app/views/widgets/` — переиспользуемые виджеты (base, link, panels, tiles, tree_components)
- `app/views/main_components/` — компоненты главного окна (common, initialization, ui/topbar)
- `app/views/common/` — общие элементы (retranslatable.py)
- `app/views/models/` — модели представлений (QAbstractItemModel)

**Пример добавления нового виджета:**

```python
# app/views/widgets/my_widget.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel


class MyWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel("Hello")
        layout.addWidget(label)
```

### Qt Designer

Если требуется создать UI через Qt Designer:

1. Установите Qt Designer (входит в PyQt6-tools или отдельно)
2. Создайте `.ui` файл
3. Динамическая загрузка (предпочтительно):
   ```python
   from PyQt6 import uic
   from PyQt6.QtWidgets import QMainWindow

   class MyWindow(QMainWindow):
       def __init__(self):
           super().__init__()
           uic.loadUi("path/to/form.ui", self)
   ```
4. Или компиляция в `.py`:
   ```bash
   pyuic6 form.ui -o form_ui.py
   ```

### Ресурсы (иконки, стили)

**Структура ресурсов:**
- `app/resources/` — .qrc-манифесты, скомпилированные ресурсы, иконки, темы
- `app/resources/ui_icons/` — иконки по темам (dark/, violet_pulse/)
- `app/resources/qss.rar` — архив QSS-тем
- `i18n/` — файлы переводов (.ts/.qm)

**Компиляция ресурсов:**

```bash
# Компиляция основных ресурсов
pyrcc6 app/resources/app_resources.qrc -o app/resources/app_resources_rc.py

# Компиляция иконок
pyrcc6 app/resources/icons.qrc -o app/resources/icons_rc.py

# Компиляция переводов
pyrcc6 i18n/i18n.qrc -o i18n/resources_rc.py
```

**Инициализация ресурсов** в `app/startup/runtime.py`:

```python
from app.resources import app_resources_rc, icons_rc
from i18n import resources_rc as i18n_resources_rc

def qInitResources() -> None:
    app_resources_rc.qInitResources()
    icons_rc.qInitResources()
    i18n_resources_rc.qInitResources()
```

**Использование иконок:**

```python
from PyQt6.QtGui import QIcon

# Из скомпилированных ресурсов
icon = QIcon(":/icons/bookmark.png")

# Из файла
icon = QIcon("path/to/icon.png")
```

**QSS-темы** хранятся в `app/resources/` и применяются через `StyleManager`.

---

## Тестирование (Testing)

### Конфигурация

- **pytest** — основной фреймворк тестирования
- **pytest-qt** — тестирование PyQt6-виджетов (опционально)

Конфигурация в `pytest.ini`:

```ini
[pytest]
testpaths = tests
addopts = -p no:cacheprovider
norecursedirs = .git .venv .pytest_cache
```

### Запуск тестов

```bash
# Все тесты
pytest

# С подробным выводом
pytest -v

# Только конкретный файл
pytest tests/test_database_manager_close.py

# С покрытием кода (требует pytest-cov)
pytest --cov=app --cov-report=html
```

### Написание тестов

**Пример теста модели (unit-тест):**

```python
# tests/test_database_manager_close.py
import pytest
from app.core.database_manager import DatabaseManager


def test_database_manager_close():
    """Проверяет корректное закрытие соединений."""
    db = DatabaseManager()
    # ... setup
    db.close_all()
    # ... assertions
```

**Пример интеграционного теста:**

```python
# tests/test_startup_regression_guards.py
import pytest
from app.startup.argument_parser import parse_arguments


def test_default_args():
    """Проверяет дефолтные значения аргументов."""
    import sys
    sys.argv = ["test"]
    args = parse_arguments()
    assert args.debug is False
    assert args.no_gui is False
    assert args.log_level is None
```

> `conftest.py` автоматически добавляет корень проекта в `sys.path`, поэтому импорты из `app.*` работают без дополнительной настройки.

---

## Процесс сборки (Build & Release)

### Сборка с PyInstaller

Проект уже имеет готовый `.spec` файл — `aitecommander.spec`.

**Сборка:**

```bash
# Установка PyInstaller
pip install pyinstaller

# Сборка через .spec (рекомендуется)
pyinstaller aitecommander.spec

# Или ручная сборка
pyinstaller --name AiteCommander --windowed --onedir app/main.py
```

**Конфигурация `.spec` файла включает:**

| Параметр | Значение |
|----------|----------|
| Точка входа | `app/main.py` |
| Режим | `--onedir` (папка), `console=False` |
| Иконка | `app/resources/app_icon.ico` |
| Ресурсы | themes/, qss/, ui_icons/, logo/, .qm переводы, config_data/ |
| Hidden imports | PyQt6.*, win32api, cloudscraper, cachetools, PIL |
| Исключения | tkinter, matplotlib, numpy, scipy, pandas, pytest |

**Исключения из сборки (не попадают в dist/):**

| Папка/Файл | Причина |
|------------|---------|
| `.git/` | Версионный контроль |
| `.venv/` | Виртуальное окружение |
| `tests/` | Тесты |
| `docs/` | Документация |
| `scripts/` | Утилиты разработки |
| `__pycache__/` | Кэш Python |
| `.pytest_cache/` | Кэш pytest |
| `*.pyc` | Скомпилированные файлы |

### Сборка с Nuitka (альтернатива)

```bash
# Установка
pip install nuitka

# Сборка
python -m nuitka ^
    --standalone ^
    --onefile ^
    --enable-plugin=pyqt6 ^
    --windows-disable-console ^
    --output-filename=AiteCommander.exe ^
    app/main.py
```

### Финальная структура сборки

```
dist/
├── AiteCommander/
│   ├── AiteCommander.exe
│   ├── app/
│   │   ├── resources/
│   │   │   ├── themes/
│   │   │   ├── qss/
│   │   │   ├── ui_icons/
│   │   │   └── logo/
│   │   └── config_data/
│   ├── i18n/
│   │   └── *.qm
│   └── ... (зависимости PyQt6, pywin32)
```

---

## Аргументы командной строки

```bash
# Запуск с отладкой
python -m app.main --debug

# Запуск с конкретным уровнем логирования
python -m app.main --log-level DEBUG

# Запуск без GUI (для тестирования)
python -m app.main --no-gui

# Показать версию
python -m app.main --version
```

| Аргумент | Описание |
|----------|----------|
| `--debug` | Включает DEBUG-логирование |
| `--log-level LEVEL` | Устанавливает уровень (DEBUG/INFO/WARNING/ERROR/CRITICAL) |
| `--no-gui` | Запуск без графического интерфейса |
| `--version` | Показывает версию и завершает работу |
