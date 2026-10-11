# GEMINI_AUDIT: Технический аудит кодовой базы Aite Commander

Данный документ представляет собой результат углубленного статического исследования локального репозитория `Aite Commander` (версия 1.1.8). Он составлен исключительно на основе анализа реальных исходных кодов, конфигураций и тестов проекта без предположений и без генерации синтетических требований.

Цель документа — служить фактологической и технической базой для последующего составления проектных инструкций AI-агентам (`GEMINI.md`).

---

## 1. PROJECT_PROFILE

### 1.1. Название и назначение
- **Проект**: Aite Commander
- **Версия**: `1.1.8` (зафиксирована в `pyproject.toml:7`, `app/startup/argument_parser.py:29`, `installer/AiteCommander.iss:3`).
- **Лицензия**: GNU General Public License v3.0 (`GPL-3.0-only`, файл `LICENSE`).
- **Назначение**: Иерархический менеджер закладок и ссылок с 4-уровневой организацией (`Sphere` → `Section` → `Category` → `Link`), поддержкой 17 тем оформления (включая темные и светлые), 6 языков интерфейса, полным экспортом/импортом (`.aitepack`, `.aitesec`, `.aitecat`, HTML-закладок браузеров) и атомарным резервным копированием SQLite.

### 1.2. Язык программирования и рантайм
- **Язык**: Python
- **Версия рантайма**: `3.12` (зафиксирована в `.python-version:1`, `pyproject.toml:11` `requires-python = ">=3.12"`, в GitHub Actions CI `.github/workflows/ci.yml:19` используется `3.12`). Поддерживается совместимость с Python 3.13 (`pyproject.toml:22`).
- **Целевая ОС**: Windows 10/11 x64 (MS Windows `win32`). Для кроссплатформенных сценариев в коде предусмотрены защитные ветки (`sys.platform == "win32"`).

### 1.3. Зависимости (Dependencies)
Зафиксированы в `pyproject.toml:27-46` и зеркалированы в `requirements.txt`:
- **GUI Framework**:
  - `PyQt6 == 6.10.1` (`pyproject.toml:37`)
  - `PyQt6-Qt6 == 6.10.1` (`pyproject.toml:38`)
  - `PyQt6-sip == 13.11.0` (`pyproject.toml:39`)
- **Системные интеграции Windows**:
  - `pywin32 == 311` (`pyproject.toml:40`) — управление COM (`pythoncom`, `win32api`, `win32com`, ярлыки, UAC, Win32 Shell).
- **Сетевой стек и парсинг**:
  - `requests == 2.32.5` (`pyproject.toml:41`)
  - `urllib3 == 2.7.0` (`pyproject.toml:45`)
  - `cloudscraper == 1.2.71` (`pyproject.toml:32`) — обход Cloudflare при получении favicon/метаданных.
  - `beautifulsoup4 == 4.14.3` (`pyproject.toml:28`), `soupsieve == 2.8.3` (`pyproject.toml:43`) — парсинг HTML-закладок и страниц.
  - `charset-normalizer == 3.4.4` (`pyproject.toml:31`), `idna == 3.11` (`pyproject.toml:34`), `certifi == 2026.1.4` (`pyproject.toml:30`).
- **Графика и кэширование**:
  - `pillow == 12.3.0` (`pyproject.toml:35`) — валидация, санитизация и конвертация иконок и изображений.
  - `cachetools == 6.2.5` (`pyproject.toml:29`) — LRU/TTL кэширование фавиконов и ресурсов.
  - `filelock == 3.19.1` (`pyproject.toml:33`) — межпроцессные файловые блокировки для баз данных и иконок.
  - `pyparsing == 3.3.2` (`pyproject.toml:36`) — синтаксический анализ QSS/CSS селекторов.
  - `typing-extensions == 4.15.0` (`pyproject.toml:44`).

**Инструменты разработки (dev dependencies, `pyproject.toml:48-55`)**:
- `pytest >= 8.0`
- `ruff >= 0.6.0` (в `.pre-commit-config.yaml` используется `v0.6.9`)
- `mypy >= 1.11.0` (в `.pre-commit-config.yaml` используется `v1.11.2`)
- `pre-commit >= 3.0`
- `pyinstaller >= 6.0`

### 1.4. Точки входа и способы запуска
1. **Основная точка входа для пользователей и сборки**:
   - `main.py` (`file:///d:/01_Codebdbd/01_projects/aitecommander/main.py:1-7`) — тонкий bootstrap-файл, импортирующий `app.main:main`.
2. **Точка входа пакета**:
   - `app/main.py` (`file:///d:/01_Codebdbd/01_projects/aitecommander/app/main.py:65-102`) — функция `main() -> int`.
   - Конфигурация GUI-скрипта: `pyproject.toml:57-58` `[project.gui-scripts] aitecommander = "app.main:main"`.
3. **Способы запуска в разработке**:
   - `python main.py`
   - `python -m app.main`
   - `aitecommander.bat` (`file:///d:/01_Codebdbd/01_projects/aitecommander/aitecommander.bat:1-18`) — Windows-скрипт с активацией `.venv`.
4. **CLI-аргументы (`app/startup/argument_parser.py:26-49`)**:
   - `--debug`: включение отладочного логирования.
   - `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}`: явное задание уровня логов.
   - `--no-gui`: запуск в безголовом режиме (headless mode) для тестов и фонового обслуживания.
   - `--version`: вывод версии (`AiteCommander 1.1.8`) и немедленный выход.
   - `[file]`: путь к файлу архива (`.aitepack`, `.aitesec`, `.aitecat`, `.zip`) для импорта при старте.

### 1.5. Способ сборки дистрибутива
1. **Сборка бинарного каталога (PyInstaller onedir)**:
   - Конфигурация: `aitecommander.spec` (`file:///d:/01_Codebdbd/01_projects/aitecommander/aitecommander.spec:1-109`).
   - Скрипт сборки: `python scripts/build.py` (`file:///d:/01_Codebdbd/01_projects/aitecommander/scripts/build.py:1-104`).
   - Параметры сборки: `--noconfirm`, режим `onedir`, `console=False`, иконка `app/resources/app_icon.ico`.
   - В сборку бандлятся: `app/models/schema.sql`, `app/models/migrations`, `app/resources/themes`, `app/resources/qss`, `app/resources/ui_icons`, `app/resources/logo`, `app/resources/package_icon.ico`, `i18n/*.qm`, `app/config_data/*.json`.
   - Исключаются: `tkinter`, `matplotlib`, `numpy`, `scipy`, `pandas`, `pytest`, `brotli`, `brotlicffi`.
2. **Сборка Windows Installer (Inno Setup)**:
   - Скрипт Inno Setup: `installer/AiteCommander.iss` (`file:///d:/01_Codebdbd/01_projects/aitecommander/installer/AiteCommander.iss:1-83`).
   - Скрипт автоматизации: `scripts/build_installer.ps1` (`file:///d:/01_Codebdbd/01_projects/aitecommander/scripts/build_installer.ps1:1-56`).
   - Артефакт инсталлятора: `dist/installer/AiteCommander-Setup-1.1.8.exe`.

---

## 2. PROJECT_STRUCTURE

```
aitecommander/
├── app/                                  # Корневой Python-пакет приложения
│   ├── config_data/                      # Конфигурация и адаптеры данных
│   │   ├── app_config.json               # Базовый JSON-конфиг приложения
│   │   ├── logging_config.json           # Конфигурация логирования
│   │   ├── runtime_config.py             # Синглтон настроек времени выполнения
│   │   └── runtime_config_models.py      # Модели конфигурации
│   ├── controllers/                      # Слой контроллеров (координация UI и данных)
│   │   ├── business/                     # Бизнес-логика, не зависящая от Qt виджетов
│   │   │   ├── links_business.py         # Бизнес-правила для закладок/ссылок
│   │   │   ├── structure_business.py     # Фасад бизнес-логики структуры (4 уровня)
│   │   │   └── structure/                # Подмодули бизнес-логики (cache, events, async, validation)
│   │   ├── services/                     # Вспомогательные сервисы контроллеров
│   │   ├── structure_modules/            # Модули манипуляции структурой
│   │   ├── structure_services/           # Сервисы древовидной структуры
│   │   ├── system/                       # Системные контроллеры
│   │   │   ├── app_shutdown_controller.py # Оркестрация завершения работы и cleanup
│   │   │   ├── db_init.py                # Инициализация схемы и миграций
│   │   │   ├── keyboard_manager.py       # Регистрация и диспетчеризация хоткеев
│   │   │   └── window_setup/             # Модульная сборка компонентов главного окна
│   │   └── ui/                           # Контроллеры пользовательского интерфейса
│   │       ├── action_controller.py      # Глобальные действия: Cut, Copy, Paste, Delete, Select All
│   │       ├── category_tiles_controller.py # Управление плитками категорий
│   │       ├── menu_controller.py        # Главное меню и контекстные меню
│   │       ├── theme_controller.py       # Переключение, применение и ротация 17 тем
│   │       ├── top_panels_controller.py  # Панели топбара: избранное, недавние, быстрые действия
│   │       ├── window_facade.py          # Фасад взаимодействия MainWindow с контроллерами
│   │       ├── dialogs/                  # Контроллеры диалоговых окон
│   │       ├── links/                    # Контроллеры таблицы ссылок, буфера и операций
│   │       ├── state/                    # UIStateManager и TaskScheduler
│   │       ├── structure/                # Диспетчеризация выбора в дереве, D&D, снапшоты
│   │       └── undo/                     # Undo/Redo стек и команды (QUndoCommand)
│   ├── core/                             # Низкоуровневое ядро приложения
│   │   ├── constants.py                  # Константы (имя, версия, геометрия)
│   │   ├── database_manager.py           # Пул и контексты подключений SQLite, maintenance_scope
│   │   ├── error_handler.py              # Глобальный перехват sys.excepthook
│   │   ├── hotkey_manager.py             # Центральный реестр хоткеев
│   │   ├── log_manager.py                # Конфигурирование Python logging
│   │   ├── paths/path_manager.py         # Пути профилей пользователей, бэкапов, логов
│   │   ├── results.py                    # Типы Result, InvalidateRegion, ErrorNotification
│   │   ├── settings_manager.py           # Статический фасад для настроек
│   │   ├── strings.py                    # Общие строковые константы
│   │   ├── style_manager.py              # Применение QSS к QApplication
│   │   └── worker_manager.py             # Глобальный QThreadPool менеджер фоновых задач
│   ├── interfaces.py                     # Typing Protocols (MainWindowLike, TopPanelDataLike и др.)
│   ├── models/                           # Слой хранения и доступа к SQLite
│   │   ├── base/                         # db_base.py (DatabaseBase, db_lock, SAVEPOINT транзакции)
│   │   ├── entities/                     # Модели сущностей: sphere, section, category, link
│   │   ├── managers/                     # backup_manager, duplicate_resolver, import_export, structure
│   │   ├── migrations/                   # Файлы миграций (0001_init.sql — 0010_renumber_link_positions.py)
│   │   ├── protocols/                    # Протоколы моделей
│   │   ├── types/                        # Категории, типы ссылок, числовые лимиты
│   │   ├── utils/                        # Валидаторы идентификаторов, массовая вставка
│   │   ├── workers/                      # QRunnable/QThread воркеры (бэкап, экспорт, проверка URL)
│   │   ├── db.py                         # Главный класс Database (наследник QObject с сигналами)
│   │   └── schema.sql                    # Первичная SQL DDL схема SQLite
│   ├── resources/                        # Ресурсы графического интерфейса
│   │   ├── app_resources.qrc             # Манифест Qt-ресурсов
│   │   ├── app_resources_rc.py           # Скомпилированный pyrcc6 файл ресурсов
│   │   ├── app_icon.ico                  # Главная иконка приложения
│   │   ├── package_icon.ico              # Иконка ассоциированных файлов (.aitesec, .aitecat)
│   │   ├── logo/                         # Логотипы приложения
│   │   ├── qss/                          # common.qss + 17 файлов таблиц стилей тем
│   │   ├── themes/                       # 17 каталогов тем с theme.json манифестами
│   │   └── ui_icons/                     # Наборы SVG-иконок для всех 17 тем
│   ├── services/                         # Слой сервисов бизнес-операций
│   │   ├── bulk_operation_service.py     # Массовые операции над секциями/категориями/ссылками
│   │   ├── database_restore_worker.py    # Атомарное восстановление БД в фоне с проверкой целостности
│   │   ├── file_association_service.py   # Регистрация Windows-ассоциаций для .aitesec и .aitecat
│   │   ├── icon_reference_service.py     # Управление жизненным циклом и удаление осиротевших иконок
│   │   ├── links_service.py              # Высокоуровневые операции с ссылками
│   │   ├── structure_service.py          # Сервисы структуры
│   │   ├── structure_share_service.py    # Экспорт/импорт пакетов .aitesec/.aitecat (ZipSlip защита)
│   │   ├── theme_registry.py             # Синглтон реестра 17 встроенных и пользовательских тем
│   │   ├── theme_stylesheet_service.py   # Сборка, токенизация и LRU-кэширование QSS
│   │   └── uow.py                        # UnitOfWork и декоратор @unit_of_work
│   ├── settings.py                       # AppSettings (обертка над QSettings, INI-формат)
│   ├── startup/                          # Подсистема запуска и инициализации
│   │   ├── app_factory.py                # Фабрика QApplication (high DPI, dark mode hint)
│   │   ├── argument_parser.py            # Парсинг CLI аргументов
│   │   ├── browser_profiles_loader.py    # Обнаружение установленных браузеров (Chrome, Edge, Firefox)
│   │   ├── initializer.py                # ApplicationInitializer (двухфазная инициализация)
│   │   ├── runtime.py                    # Главный цикл run(), обработка POSIX/Windows сигналов
│   │   ├── signal_handling.py            # Обработчики SIGINT, SIGTERM, SIGBREAK
│   │   └── single_instance.py            # SingleInstanceGuard (QLocalServer/QLocalSocket IPC)
│   ├── utils/                            # Вспомогательные утилиты
│   │   ├── browser/                      # Импорт закладок HTML браузеров
│   │   ├── cache/                        # BaseCache, InMemoryCache, selective_lru, topbar_snapshot
│   │   ├── db/                           # synchronization (db_lock), migrations (MigrationRunner)
│   │   ├── locking/                      # Файловые блокировки
│   │   ├── metrics/                      # Мониторинг производительности запуска
│   │   ├── theme_checker.py              # Контроль контрастности тем по стандарту WCAG 2.1
│   │   └── ui/                           # signal_suppression, focus, dnd/mime, async_helpers
│   └── views/                            # Представления (Qt виджеты и диалоги)
│       ├── common/retranslatable.py      # Retranslatable миксин динамической смены языка
│       ├── dialogs/                      # Модальные диалоги (base, link, restore, backup, theme)
│       ├── main_components/              # Инициализация и сборка главного окна
│       │   ├── initialization/           # WindowInitializer, InitScheduler, InitDiagnostics
│       │   └── ui/                       # window_ui_setup, window_widgets, topbar
│       ├── models/                       # Qt модели: StructureTreeModel, CategoriesListModel
│       ├── widgets/                      # Виджеты: LinksTableView, CategoryTiles, Panels
│       └── windows/main_window.py        # MainWindow (QMainWindow)
├── i18n/                                 # Подсистема интернационализации (6 языков)
│   ├── app_*.ts / app_*.qm               # Каталоги переводов (en, ru, uk, fr, es, de)
│   ├── qtbase_*.qm                       # Локализации стандартных диалогов Qt
│   ├── cli.py / __main__.py              # CLI: python -m i18n (update, compile, check, all)
│   ├── language_service.py               # Singleton LanguageService (динамическая смена языка)
│   └── resources_rc.py                   # Скомпилированные ресурсы переводов
├── tests/                                # Набор автоматизированных тестов (140 файлов)
│   ├── conftest.py                       # Bootstrap тестового окружения
│   └── test_*.py                         # Модульные, контрактные и регрессионные тесты
├── scripts/                              # Утилитарные скрипты автоматизации
├── installer/                            # Конфигурация Inno Setup (AiteCommander.iss)
└── docs/                                 # Проектная документация
```

---

## 3. ARCHITECTURE

Фактическая архитектура Aite Commander представляет собой строго эшелонированную слоистую систему с четким распределением ответственности между слоями UI, контроллеров, бизнес-логики, сервисов и базы данных:

```
┌────────────────────────────────────────────────────────────────────────┐
│                              VIEWS LAYER                               │
│  MainWindow, LinksTableView, CategoryTiles, StructureTree, Dialogs    │
│  (Только визуализация и пересылка пользовательских событий)            │
└───────────────────▲────────────────────────────────▲───────────────────┘
                    │ Сигналы / Слоты                │ set_data / update_data
┌───────────────────▼────────────────────────────────▼───────────────────┐
│                          CONTROLLERS LAYER                             │
│  WindowFacade, ActionController, UIStateManager, LinksUIController,    │
│  StructureUIController, ThemeController, TopPanelsController           │
│  (Координация UI, фокус, навигация, Undo/Redo команды)                 │
└───────────────────▲────────────────────────────────▲───────────────────┘
                    │ Вызовы методов                 │ Реактивные сигналы
┌───────────────────▼────────────────────────────────▼───────────────────┐
│                      SERVICES & BUSINESS LAYER                         │
│  LinksBusiness, StructureBusiness, BulkOperationService,               │
│  StructureShareService, ThemeStylesheetService, UnitOfWork             │
│  (Бизнес-правила, валидация, транзакционные сценарии, санитизация)     │
└───────────────────▲────────────────────────────────▲───────────────────┘
                    │ CRUD вызовы                    │ db_lock / transactions
┌───────────────────▼────────────────────────────────▼───────────────────┐
│                           MODELS & DB LAYER                            │
│  Database (QObject), DatabaseManager, DatabaseBase, Entity Models,     │
│  MigrationRunner, SQLite WAL (foreign_keys=ON)                         │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.1. Архитектурные слои и ответственность

1. **Слой представлений (`app/views/`)**:
   - Отвечает исключительно за отображение данных, геометрию, перерисовку и реакцию на системные события Qt.
   - **Строгий контракт**: Виджеты **не содержат бизнес-логики** и **не имеют прямого доступа к базе данных**. Они принимают данные через методы протоколов `set_data()` / `update_data()` (`app/interfaces.py:76-80`) и транслируют пользовательские действия через сигналы PyQt6.
   - Виджеты реализуют протокол `ReTranslatable` (`app/views/common/retranslatable.py:12-70`) для обновления надписей без перезапуска приложения при смене языка.
2. **Слой контроллеров (`app/controllers/ui/`, `app/controllers/system/`)**:
   - Связывает `Views` с бизнес-логикой и моделями.
   - Управляет состоянием интерфейса через синглтон `UIStateManager` (`app/controllers/ui/state/ui_state_manager.py:20-65`), предотвращая повторные загрузки одной и той же категории и циклические перерисовки.
   - Централизует глобальные команды через `ActionController` (`app/controllers/ui/action_controller.py:33-100`), который диспетчеризирует действия Cut/Copy/Paste/Delete в зависимости от текущего фокуса виджета (`FocusManager`).
   - `WindowFacade` (`app/controllers/ui/window_facade.py:29-60`) скрывает сложность десятка контроллеров от `MainWindow`.
3. **Слой бизнес-логики (`app/controllers/business/`)**:
   - Модули `links_business.py` и `structure_business.py` реализуют правила предметной области: иерархию 4 уровней (Сфера → Секция → Категория → Ссылка), расчет позиций, валидацию уникальности имен внутри родительского контейнера.
   - Не зависят от визуальных компонентов Qt.
4. **Сервисный слой (`app/services/`)**:
   - Выполняет сложные системные операции:
     - `BulkOperationService`: пакетные операции над категориями и ссылками с контролем лимита чанков (`app/services/bulk_operation_service.py:27-58`).
     - `StructureShareService`: формирование и распаковка архивов обмена `.aitesec` и `.aitecat` с защитой от ZipSlip и контролем допустимых расширений и magic-bytes картинок (`app/services/structure_share_service.py:24-94`).
     - `ThemeStylesheetService` и `ThemeRegistry`: парсинг, токенизация, расчет контрастности и кэширование QSS-стилей 17 тем (`app/services/theme_stylesheet_service.py:20-70`).
     - `UnitOfWork` (`app/services/uow.py:9-37`): контекстный менеджер для объединения нескольких манипуляций в одну транзакцию.
5. **Слой данных (`app/models/`, `app/core/database_manager.py`)**:
   - `DatabaseManager`: статический фасад для SQLite соединений с thread-local кэшированием, пулом соединений и поддержкой эксклюзивного `maintenance_scope` для резервного копирования.
   - `DatabaseBase`: базовый класс репозиториев, реализующий потокобезопасную транзакционную модель с reentrant блокировкой `db_lock` и механизмом `SAVEPOINT` для вложенных транзакций (`app/models/base/db_base.py:94-164`).
   - `Database`: класс-фасад данных, наследующий `QObject` (`app/models/db.py:78-120`) для испускания сигналов об изменении данных (`data_changed`, `structure_loaded`, `operation_progress`) в GUI-поток.

---

## 4. SUBSYSTEMS

### 4.1. SQLite, доступ к данным и миграции
- **Файлы**: `app/core/database_manager.py`, `app/models/db.py`, `app/models/base/db_base.py`, `app/utils/db/migrations.py`, `app/utils/db/synchronization.py`.
- **Конфигурация SQLite**:
  - `PRAGMA foreign_keys = ON` (`database_manager.py:347`) — гарантирует ссылочную целостность каскадного удаления (`ON DELETE CASCADE`).
  - `PRAGMA journal_mode = WAL` (`database_manager.py:368`) — параллельное чтение и запись.
  - `PRAGMA synchronous = NORMAL` (`database_manager.py:372`) — баланс надежности и скорости в WAL.
  - `PRAGMA busy_timeout = 5000` (`database_manager.py:363`) — 5 секунд ожидания при конкуренции за базу.
  - `PRAGMA temp_store = MEMORY` (`database_manager.py:359`).
  - `PRAGMA mmap_size = 268435456` (256 МБ, `database_manager.py:376`).
- **Синхронизация**: Глобальный `threading.RLock()` объект `db_lock` (`app/utils/db/synchronization.py`). Все транзакции и операции модификации удерживают `db_lock` на протяжении всей операции.
- **Вложенные транзакции**: Реализованы в `DatabaseBase.transaction()` (`app/models/base/db_base.py:94-164`). Если `nesting_level == 0`, выполняется `BEGIN TRANSACTION`. Если `nesting_level > 0`, создается `SAVEPOINT sp_<uuid>` с автоматическим `ROLLBACK TO SAVEPOINT` при исключениях.
- **Миграции**: `MigrationRunner` (`app/utils/db/migrations.py:25-100`).
  - Версионирование через `PRAGMA user_version`.
  - Миграции хранятся в `app/models/migrations/` в формате `0001_init.sql`, `0002_*.py`.
  - SQL-файлы выполняются через `executescript`, Python-файлы импортируются и вызывают `migrate(conn, logger)`.

### 4.2. Управление состоянием приложения
- **Файлы**: `app/settings.py`, `app/controllers/ui/state/ui_state_manager.py`, `app/controllers/ui/structure/tree_state_service.py`.
- **Хранение настроек**: `AppSettings` инкапсулирует `QSettings` в формате `IniFormat` под профилем пользователя (`app/settings.py:15-20`). Сохраняет активную тему (`Appearance/Theme`), лимит бэкапов (`Backup/MaxCopies`), размер шрифта (`UI/FontSize`), хоткеи (`Hotkeys/`), сортировку таблицы (`Table/SortColumn`, `Table/SortOrder`).
- **Состояние UI и навигация**: `UIStateManager` (`app/controllers/ui/state/ui_state_manager.py:20-278`):
  - Метод `load_category(category_id, source, force_reload=...)` — **единственная точка загрузки категорий в приложении**. Защищен флагом `_loading` от рекурсивных и параллельных вызовов.
  - Стек истории переходов (`_history`, лимит 50 записей) с методами `navigate_back()` и `navigate_forward()`.
  - Управление отображением центральной области: переключение `QStackedLayout` между `TABLE` (индекс таблицы ссылок) и `TILES` (индекс плиток категорий).

### 4.3. PyQt6: сигналы, слоты, виджеты и модели
- **Файлы**: `app/views/widgets/link/links_model.py`, `app/views/models/structure_tree_model.py`, `app/views/models/categories_list_model.py`, `app/views/windows/main_window.py`.
- **Таблица ссылок**: `LinksTableModel` (`app/views/widgets/link/links_model.py:7-49`) наследует `QAbstractTableModel`. Поддерживает точечные обновления через `dataChanged` без перестройки всей таблицы (`test_link_table_update_guarantees.py`).
- **Дерево структуры**: `StructureTreeModel` (`app/views/models/structure_tree_model.py:10-60`) наследует `QAbstractItemModel`, реализует ленивую подгрузку и кэширование иконок, а также иерархию `Секция` → `Категория`.
- **Маршалинг потоков**: Класс `Database._CallbackDispatcher` (`app/models/db.py:249-275`) использует `Qt.ConnectionType.QueuedConnection` для безопасного вызова пользовательских коллбэков из фоновых потоков в GUI-потоке.
- **Безопасная эмиссия сигналов**: Метод `Database._safe_emit()` (`app/models/db.py:286-298`) проверяет наличие `QApplication.instance()` перед отправкой сигналов, предотвращая сбои в тестах и headless-режиме.

### 4.4. Выделение, фокус и навигация
- **Файлы**: `app/utils/ui/focus/focus_manager.py`, `app/controllers/ui/structure/selection_handling.py`, `app/controllers/ui/structure/selection_workflow_service.py`.
- **Централизованный FocusManager**: Синглтон `FocusManager` (`app/utils/ui/focus/focus_manager.py:27-80`) предотвращает состояние гонки при переключении фокуса с помощью механизма защитного окна `_focus_guard_deadline` (0.5 сек). Если фокус был передан пользователем, автоматические фокусы ("restore", "auto", "navigation") игнорируются.
- **Подавление сигналов выбора**: `SelectionHandling` (`app/controllers/ui/structure/selection_handling.py:70-98`) предоставляет пару методов `begin_suppress_selection()` и `end_suppress_selection()` со счетчиком `_suppress_counter`. Во время пакетных перестановок и переименований сигналы дерева временно блокируются.
- **Утилита `suppress_ui_signals`** (`app/utils/ui/signal_suppression.py:32-116`): блокирует `tree.blockSignals(True)` и `selection.begin_suppress_selection()`, восстанавливая их в блоке `finally` в обратном порядке (сначала дерево, затем селекция).

### 4.5. Undo/Redo
- **Файлы**: `app/controllers/ui/undo/stack.py`, `app/controllers/ui/undo/base.py`, `app/controllers/ui/undo/commands_links.py`, `app/controllers/ui/undo/commands_structure.py`.
- **Реализация**: Обертка `UndoManager` над `QUndoStack` (`app/controllers/ui/undo/stack.py:21-62`).
- **Базовый класс**: `BaseCommand` (`app/controllers/ui/undo/base.py:14-39`) наследует `QUndoCommand`. Все дочерние команды обязательно переопределяют `redo()` и `undo()`.
- **Макрокоманды**: Контекстный менеджер `UndoManager.macro(text)` (`stack.py:64-70`) группирует связанные операции (например, перемещение нескольких категорий или удаление связей) в одну атомарную транзакцию Undo.
- **Команды ссылок и структуры**:
  - `SaveLinkCmd`, `DeleteLinkCmd`, `BatchSaveLinksCmd`, `BatchDeleteLinksCmd` (`commands_links.py`).
  - `MoveSectionCmd`, `DeleteSectionCmd`, `PasteSectionsCmd`, `PasteCategoriesCmd` (`commands_structure.py`).
  - При `redo()` и `undo()` команды восстанавливают не только данные в БД, но и вызывают отложенное восстановление выделения в UI через `schedule_selection_restore()`.

### 4.6. Drag & Drop и буфер обмена
- **Файлы**: `app/utils/ui/dnd/mime.py`, `app/controllers/ui/links/clipboard.py`, `app/views/widgets/tree_components/move_operations_handler.py`.
- **Строгий MIME-контракт**: `MimeDataParser` (`app/utils/ui/dnd/mime.py:28-100`). Формат полезной нагрузки — **строго JSON**: `{"ids": [int, ...]}`. Использование CSV или строковых представлений запрещено.
  - MIME-тип категорий: `application/x-aite-categories`
  - MIME-тип секций: `application/x-aite-sections`
  - MIME-тип ссылок: `application/x-aite-links`
- **Буфер обмена с отложенным вырезанием (Cut/Paste)**: `LinksUIClipboard` (`app/controllers/ui/links/clipboard.py:20-60`). При операции Cut ссылки не удаляются немедленно: их ID заносятся в `_cut_link_ids`, а таблица отрисовывает их приглушенными (dimmed state). Реальное перемещение происходит только в `paste_link()` или отменяется через `cancel_cut()`.

### 4.7. Контекстные меню и горячие клавиши
- **Файлы**: `app/core/hotkey_manager.py`, `app/controllers/system/keyboard_manager.py`, `app/controllers/ui/action_controller.py`, `app/controllers/ui/menu_controller.py`.
- **Реестр хоткеев**: `HotkeyManager` (`app/core/hotkey_manager.py:15-94`).
  - Контексты горячих клавиш зависят от префикса действия: `global.*` → `WindowShortcut`, `table.*` → `WidgetWithChildrenShortcut`, `edit.*` → `WidgetShortcut`.
  - Хоткеи сохраняются в `SettingsManager` под ключом `hotkeys.<action_id>`.
  - Метод `detect_conflicts()` выявляет коллизии одинаковых комбинаций клавиш в пределах одного контекста.
- **Глобальные действия**: `ActionController` настраивает QAction для `edit.cut` (Ctrl+X), `edit.copy` (Ctrl+C), `edit.paste` (Ctrl+V), `global.delete` (Delete), `edit.select_all` (Ctrl+A) с динамическим обновлением доступности (`setEnabled`) по событиям `QApplication.focusChanged` и `clipboard.dataChanged`.

### 4.8. Кэширование
- **Файлы**: `app/utils/cache/base.py`, `app/utils/cache/topbar_snapshot.py`, `app/services/theme_stylesheet_service.py`, `app/services/icon_reference_service.py`.
- **Унифицированный кэш**: `BaseCache` и `InMemoryCache` (`app/utils/cache/base.py:44-80`) с поддержкой TTL (в секундах) и LRU-вытеснением устаревших ключей при превышении `max_size`.
- **Снапшот верхней панели**: `TopBarSnapshotStore` (`app/utils/cache/topbar_snapshot.py`) сохраняет снимок кнопок избранного и недавних закладок в бинарный shelve-кэш на диске, обеспечивая мгновенную отрисовку топбара при холодном старте до завершения запросов к БД.
- **Кэш иконок и стилей**:
  - `ThemeStylesheetService` содержит `OrderedDict` кэш готовых строк QSS (по умолчанию до 10 тем) с потокобезопасной блокировкой `RLock`.
  - `IconReferenceService` отслеживает использование файлов иконок во всех 4 таблицах (`sphere`, `section`, `category`, `link`) и очищает осиротевшие файлы из каталога пользователя (`app/services/icon_reference_service.py:36-80`).

### 4.9. Фоновые задачи и многопоточность
- **Файлы**: `app/core/worker_manager.py`, `app/models/workers/base_worker.py`, `app/services/database_restore_worker.py`.
- **Управление пулом**: `WorkerManager` (`app/core/worker_manager.py:54-100`) управляет глобальным `QThreadPool`. Лимит потоков по умолчанию: 4 (`max_threads = 4`).
- **Базовый DatabaseWorker**: `app/models/workers/base_worker.py:30-128`.
  - Наследует `QRunnable` с флагом `setAutoDelete(True)`.
  - Создает отдельное соединение SQLite на время работы потока через `DatabaseManager.get_connection()`.
  - В блоке `finally` обязательно вызывает `DatabaseManager.close()`, освобождая соединение текущего потока.
  - Коммуникация с UI происходит исключительно через сигналы `WorkerSignals(QObject)`: `progress(int, int, str)`, `finished(object)`, `error(Exception, str)`, `cancelled()`.

### 4.10. Темы оформления и QSS
- **Файлы**: `app/services/theme_registry.py`, `app/services/theme_stylesheet_service.py`, `app/core/style_manager.py`, `app/utils/theme_checker.py`.
- **17 встроенных тем**: Включая Light, Dark, Sepia, Dracula, Nord, Cyberpunk, Solarized и др. (пакеты в `app/resources/themes/<theme_id>/`).
- **Структура темы**: Каждый каталог темы содержит манифест `theme.json` (метаданные, цветовые токены), стили и набор SVG-иконок.
- **Токенизация и подстановка**: `ThemeStylesheetService` читает `common.qss`, загружает QSS темы, подставляет токены через `resolve_token_placeholders()` и динамически рассчитывает размер шрифта пользователя из `AppSettings.get_font_size()`.
- **Валидация контрастности**: `ThemeChecker` (`app/utils/theme_checker.py`) выполняет автоматический контроль контрастности текста и фона по алгоритму WCAG 2.1 (коэффициент не менее 4.5:1 для обычного текста).

### 4.11. Локализация (i18n)
- **Файлы**: `i18n/language_service.py`, `i18n/cli.py`, `app/views/common/retranslatable.py`.
- **6 поддерживаемых языков**: Английский (`en`), Русский (`ru`), Украинский (`uk`), Французский (`fr`), Испанский (`es`), Немецкий (`de`).
- **Синглтон LanguageService**: Загружает бинарные каталоги `app_<lang>.qm` и системные `qtbase_<lang>.qm` через `QTranslator`.
- **Retranslatable миксин**: Подключает виджеты к сигналу `LanguageService.instance().languageChanged` и автоматически вызывает `retranslateUi()`.
- **CLI-инструмент `python -m i18n`**:
  - `update`: извлечение строк из исходников в `.ts` через `lupdate`.
  - `compile`: компиляция `.ts` в бинарные `.qm` через `lrelease`.
  - `check`: строгая валидация 100% покрытия переводов и паритета ключей (блокирующий шаг в CI!).

### 4.12. Импорт и экспорт данных
- **Файлы**: `app/services/structure_share_service.py`, `app/models/managers/import_export_manager.py`, `app/utils/browser/import_browser_html.py`.
- **Форматы**:
  - Полный бэкап: ZIP-архив с SQLite базой данных и каталогом пользовательских иконок.
  - Обмен секциями и категориями: пакеты `.aitesec` и `.aitecat` (ZIP-архивы с манифестом `manifest.json`, данными `data.json`, иконками и прикрепленными файлами скриптов).
  - Закладки браузеров: HTML в формате Netscape Bookmark File (Chrome, Firefox, Edge, Opera, Vivaldi, Brave, Yandex).
- **Безопасность импорта**:
  - Проверка от ZipSlip: каноникализация путей внутри архива.
  - Лимиты размеров: манифест до 1 МБ, `data.json` до 20 МБ, иконка до 10 МБ, распакованный архив до 50 МБ.
  - Валидация изображений: проверка magic bytes и валидация через `PIL.Image` без выполнения произвольного кода.

### 4.13. Резервное копирование и восстановление
- **Файлы**: `app/models/managers/backup_manager.py`, `app/services/database_restore_worker.py`, `app/controllers/ui/dialogs/database_controller.py`.
- **Создание резервных копий**: Ротация копий в папке `backups/` с ограничением по количеству (`Backup/MaxCopies`, по умолчанию до 5-10 копий).
- **Восстановление (`DatabaseRestoreWorker`)**:
  - Вход в `DatabaseManager.maintenance_scope()`, блокирующий все новые подключения к базе.
  - Закрытие всех активных соединений во всех потоках (`DatabaseManager.close_all()`).
  - Строгая последовательность PRAGMA: `PRAGMA wal_checkpoint(TRUNCATE)` перед переключением `PRAGMA journal_mode = DELETE`.
  - Проверка схемы восстанавливаемой базы (`REQUIRED_TABLES`, базовые колонки).
  - Атомарное перемещение файла базы и каталога иконок с откатом в случае ошибки.
  - Защита от бесконечного цикла повторов восстановления (`_restore_retry_count` в `DatabaseController`).

### 4.14. Инициализация и завершение приложения
- **Файлы**: `app/main.py`, `app/startup/runtime.py`, `app/startup/initializer.py`, `app/startup/single_instance.py`, `app/controllers/system/app_shutdown_controller.py`.
- **Инициализация**:
  1. `main.py`: проверка CLI-аргументов, регистрация `GlobalErrorHandler`, симметричный `pythoncom.CoInitialize()`.
  2. `SingleInstanceGuard`: захват локального сокета `QLocalServer`. Если экземпляр уже запущен, новому процессу передается аргумент файла для открытия через IPC, и второй процесс чисто завершается с кодом 0 (`ExitCode.SUCCESS`).
  3. `ApplicationInitializer`: двухфазная инициализация (ядро, база, профили, главное окно). Окно создается скрытым; `show()` вызывается только после полной готовности UI.
- **Завершение (`AppShutdownController`)**:
  1. Запрещен прямой вызов `app.quit()` из UI-виджетов; закрытие инициируется через `MainWindow.closeEvent()`.
  2. Приоритеты завершения: `CRITICAL` (сохранение данных) → `HIGH` (остановка контроллеров) → `NORMAL` (ожидание завершения потоков с таймаутом) → `LOW` (очистка временных файлов).
  3. В `runtime.py`: завершение фоновых задач парсера, закрытие пула `WorkerManager`, `DatabaseManager.close_all()`.
  4. На Windows в `main()` парный `pythoncom.CoUninitialize()` в блоке `finally`. Для предотвращения хаотичного разрушения C++ Qt-объектов циклическим GC Python при критическом выходе вызывается `ExitProcess`.

---

## 5. CONTRACTS

### Контракт 1: Запрет прямого импорта `app_config` в слоях UI и сервисов
1. **Что сохранять**: В каталогах `app/controllers/`, `app/views/`, `app/services/` запрещен прямой импорт `from app.config_data import app_config`.
2. **Почему**: Архитектурная изоляция слоев. Конфигурация в UI и сервисах должна передаваться через инъекцию зависимостей или через фасад `app.config_data.runtime_config.runtime_app_config`.
3. **Где реализовано**: `tests/test_arch_import_guard.py:11-31` (автоматический тест проверяет отсутствие таких импортов регулярным выражением).
4. **Зависимые компоненты**: Все контроллеры, сервисы и представления.

### Контракт 2: Single-Instance Guard и порядок выполнения PRAGMA при Restore (§63)
1. **Что сохранять**:
   - При восстановлении БД `PRAGMA wal_checkpoint(TRUNCATE)` должен вызываться **строго до** `PRAGMA journal_mode = DELETE`.
   - Второй экземпляр приложения при занятом сокете должен завершаться с кодом `ExitCode.SUCCESS` (0) без падения.
   - Количество повторов попытки восстановления БД при блокировке файла ограничено единицей во избежание бесконечного модального цикла.
2. **Почему**: При несоблюдении порядка PRAGMA SQLite оставляет висячие WAL-файлы, повреждая базу при перезаписи файла. При отсутствии выхода второго экземпляра блокируются файлы SQLite.
3. **Где реализовано**: `app/services/database_restore_worker.py:73-100`, `app/controllers/ui/dialogs/database_controller.py:45-73`.
4. **Зависимые компоненты**: `DatabaseRestoreWorker`, `SingleInstanceGuard`, `DatabaseController`. Проверяется в `tests/test_contract_63_database_guard.py:12-138`.

### Контракт 3: Единая точка загрузки категории — `UIStateManager.load_category`
1. **Что сохранять**: Загрузка категории для отображения в таблице ссылок должна производиться **исключительно** через `UIStateManager.load_category(category_id, source, force_reload=...)`.
2. **Почему**: Устраняет дублирование логики и каскадные зацикливания между кликом по дереву, кликом по плитке, историей переходов, фильтрацией поиска и Undo/Redo командами. Метод содержит защиту от повторной загрузки (`_loading` guard) и переключает стек интерфейса.
3. **Где реализовано**: `app/controllers/ui/state/ui_state_manager.py:36-149`.
4. **Зависимые компоненты**: `StructureUIController`, `CategoryTilesController`, `LinksTableController`, `SelectionActions`, Undo-команды.

### Контракт 4: Симметрия COM-инициализации в Windows
1. **Что сохранять**: Вызов `pythoncom.CoInitialize()` в `app/main.py` должен строго соответствовать вызову `pythoncom.CoUninitialize()` в том же модуле в блоке `finally`.
2. **Почему**: Асинхронные COM-вызовы (работа с ярлыками Windows, системными браузерами) при несимметричной деинициализации приводят к Access Violation (код `0xC0000005`) при завершении процесса PyQt6.
3. **Где реализовано**: `app/main.py:36-43` и `app/main.py:93-100`.
4. **Зависимые компоненты**: `tests/test_com_symmetry.py`, `app/startup/browser_profiles_loader.py`.

### Контракт 5: Формат данных Drag & Drop — только JSON
1. **Что сохранять**: Все MIME-пейлоады для перемещения элементов структуры и ссылок должны формироваться строго через `MimeDataParser` в формате JSON: `{"ids": [int, ...]}`.
2. **Почему**: Исторические форматы (CSV, plain text) приводили к ошибкам разбора при наличии запятых в именах закладок и нарушению безопасности типов.
3. **Где реализовано**: `app/utils/ui/dnd/mime.py:28-64`.
4. **Зависимые компоненты**: `LinksTableView`, `StructureTreeModel`, `CategoryTiles`, `MoveOperationsHandler`.

### Контракт 6: Реентрантная транзакционная изоляция через `db_lock` и `SAVEPOINT`
1. **Что сохранять**: Любая операция модификации базы данных должна выполняться внутри контекстного менеджера `DatabaseBase.transaction()` или декоратора `@unit_of_work`.
2. **Почему**: В многопоточном окружении Qt SQLite требует строгой сериализации записей. Внешняя транзакция удерживает `db_lock`, а вложенные транзакции оформляются через именованные `SAVEPOINT`, предотвращая ошибку `sqlite3.OperationalError: cannot start a transaction within a transaction`.
3. **Где реализовано**: `app/models/base/db_base.py:94-164`, `app/services/uow.py:9-52`.
4. **Зависимые компоненты**: Все модели сущностей (`SphereModel`, `SectionModel`, `CategoryModel`, `LinkModel`), `BulkOperationService`. Проверяется в `tests/test_nested_uow_transactions.py`.

### Контракт 7: Порядок подавления сигналов UI при пакетных изменениях
1. **Что сохранять**: При пакетных обновлениях структуры подавление сигналов должно выполняться парой `suppress_ui_signals` / `restore_ui_signals`. Восстановление в блоке `finally` должно происходить **в обратном порядке**: сначала разблокировка дерева (`tree.blockSignals(False)`), затем завершение подавления селекции (`selection.end_suppress_selection()`).
2. **Почему**: Предотвращает ложные срабатывания обработчиков выбора на промежуточных, не сформированных индексах дерева.
3. **Где реализовано**: `app/utils/ui/signal_suppression.py:32-116`.
4. **Зависимые компоненты**: `MoveOperationsHandler`, `BatchDeleteCategoriesCmd`, `MoveSectionCmd`.

### Контракт 8: Инициализация ReTranslatable при множественном наследовании
1. **Что сохранять**: В классах диалогов с множественным наследованием вида `class MyDialog(BaseDialog, ReTranslatable):` вызов `ReTranslatable.__init__(self)` обязан производиться **строго после** полной инициализации всех дочерних виджетов интерфейса (с параметром `call_retranslate=True` или явным последующим вызовом `retranslateUi()`).
2. **Почему**: При вызове конструктора миксина до создания виджетов метод `retranslateUi()` пытается обратиться к несуществующим полям виджета, вызывая `AttributeError`.
3. **Где реализовано**: `app/views/common/retranslatable.py:15-29`.
4. **Зависимые компоненты**: Все диалоги в `app/views/dialogs/` и `app/views/windows/`.

---

## 6. DEVELOPMENT_WORKFLOW

### 6.1. Тестирование
- **Фреймворк**: `pytest >= 8.0`.
- **Конфигурация (`pytest.ini`)**:
  ```ini
  [pytest]
  testpaths = tests
  addopts = -p no:cacheprovider
  norecursedirs = .git .venv .pytest_cache pytest-cache-files-*
  ```
- **Запуск всех тестов**:
  ```bash
  pytest
  # или через вызов python модуля:
  python -m pytest -q
  ```
- **Запуск конкретного теста / группы**:
  ```bash
  pytest tests/test_contract_63_database_guard.py
  pytest tests/test_link_table_update_guarantees.py -k "test_targeted_row_update"
  ```
- **Тестовый набор**: В репозитории содержится **140 тестовых файлов** в `tests/`, охватывающих архитектурные контракты, регрессии, миграции, многопоточность, темы и UI-модели.
- **Особенности тестовой среды**: В тестах может отсутствовать запущенный `QApplication`. Все модули моделей и утилит используют защитные конструкции вида `if QApplication.instance() is None: return` (`Database._safe_emit`).

### 6.2. Линтинг, форматирование и типизация
- **Ruff**: Используется как единый быстрый линтер и форматтер.
  - Конфигурация в `pyproject.toml:68-96`:
    - `target-version = "py312"`
    - `line-length = 88`
    - Игнорируются: `E501` (длина строки), `W291`, `W293`, `E402` (поздние импорты для bootstrap), `BLE001` (blind except для изоляции падений в Qt event loop), `UP045`.
    - Исключены из проверки сгенерированные файлы: `app/resources/app_resources_rc.py`, `i18n/resources_rc.py`.
  - Команды:
    ```bash
    ruff check app/
    ruff format app/
    ```
- **Mypy**: Статическая проверка типов.
  - Настройка в `.pre-commit-config.yaml:8-12` (`v1.11.2`).
  - Команда: `mypy app/`.
- **Pre-commit**:
  ```bash
  pre-commit install
  pre-commit run --all-files
  ```

### 6.3. Интернационализация (i18n) — Обязательный Quality Gate
- В проекте настроен встроенный CLI-модуль управления переводами `i18n`:
  ```bash
  # 1. Извлечь новые строки из исходного кода в .ts:
  python -m i18n update

  # 2. Скомпилировать .ts файлы в бинарные .qm:
  python -m i18n compile

  # 3. Проверить 100% полноту и паритет переводов (входит в CI!):
  python -m i18n check

  # Полный цикл одной командой:
  python -m i18n all
  ```
- **Важно**: В GitHub Actions CI (`.github/workflows/ci.yml:28`) шаг `python -m i18n check` выполняется перед запуском тестов. Любая добавленная в Python-код строка интерфейса без перевода во всех 6 языках уронит сборку!

### 6.4. Сборка дистрибутива
- **PyInstaller**:
  ```bash
  python scripts/build.py
  ```
- **Inno Setup Installer** (на Windows при наличии установленного Inno Setup 6):
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
  ```

### 6.5. Автоматически генерируемые файлы
Следующие файлы генерируются инструментами сборки и не должны редактироваться вручную:
1. `app/resources/app_resources_rc.py` — генерируется через `pyrcc6 app/resources/app_resources.qrc -o app/resources/app_resources_rc.py`.
2. `i18n/resources_rc.py` — генерируется через `pyrcc6 i18n/i18n.qrc -o i18n/resources_rc.py`.
3. `i18n/*.qm` — бинарные файлы переводов, генерируются через `python -m i18n compile`.
4. Каталоги `dist/` и `build/`.

### 6.6. Файлы и данные высокой степени риска
- `app/models/schema.sql` и `app/models/migrations/`: изменение существующей схемы ломает пользовательские базы. Любое изменение схемы должно оформляться **строго через новую номерную миграцию** (`0011_*.sql` или `0011_*.py`) с инкрементом `PRAGMA user_version`.
- `app/main.py` и `app/startup/runtime.py`: порядок инициализации и очистки ресурсов (COM, `faulthandler`, `SingleInstanceGuard`, закрытие соединений БД). Нарушение порядка приводит к зависаниям процесса в диспетчере задач или падениям при выходе.
- `app/utils/ui/dnd/mime.py`: модификация структуры MIME сломает совместимость Drag & Drop между компонентами.

---

## 7. AI_AGENT_CONTEXT

### 7.1. Карта решения задач по функциональным областям
- **Добавление нового поля в закладку/категорию**:
  1. Создать новую миграцию в `app/models/migrations/` (следующий порядковый номер `0011_*.py` или `.sql`).
  2. Обновить SQL-запросы в репозитории сущности (`app/models/entities/link_model.py` или `category_model.py`).
  3. Обновить валидатор в `app/utils/validators/`.
  4. Обновить модель таблицы `app/views/widgets/link/links_model.py` или диалог `app/views/dialogs/`.
  5. Запустить `python -m i18n all` для добавления локализаций нового поля.
- **Изменение внешнего вида или стилей виджета**:
  - Не использовать жестко закодированные цвета (`#FFFFFF`, `red`) в Python-коде!
  - Использовать токены тем (`app/services/theme_registry.py:18-54`: `DEFAULT_DARK_TOKENS`, `DEFAULT_LIGHT_TOKENS`).
  - Добавлять правила в `app/resources/qss/common.qss` или таблицы стилей тем.
  - Проверять контрастность через `ThemeChecker`.
- **Добавление нового пункта меню или горячей клавиши**:
  - Зарегистрировать хоткей в `HotkeyManager.register("action_id", "DefaultKeySequence")`.
  - Привязать действие через `ActionController` или `MenuController`.
  - Строки локализовать через `self.tr()` или `QCoreApplication.translate()`.
- **Создание фоновой задачи (загрузка данных, парсинг)**:
  - Наследоваться от `DatabaseWorker` (`app/models/workers/base_worker.py:30-128`) или `QRunnable`.
  - Не обращаться к UI-виджетам из метода `do_work()` / `run()`.
  - Передавать результаты в GUI исключительно через сигналы `WorkerSignals`.

### 7.2. Механизмы обязательного повторного использования
1. **Транзакции**: Всегда использовать `with db.transaction():` или `@unit_of_work`. Не открывать транзакции вручную сырыми запросами `BEGIN`.
2. **Переход к категории**: Всегда вызывать `ui_state.load_category(cat_id, source=...)`. Никогда не вызывать напрямую методы перезагрузки таблицы и переключения стека виджетов из разрозненных мест.
3. **Управление фокусом**: Всегда использовать `FocusManager.set_focus(widget, widget_name=...)`. Не вызывать `widget.setFocus()` напрямую без диспетчера, чтобы избежать гонок фокуса.
4. **Подавление сигналов при модификации дерева**: Всегда оборачивать операции в `suppress_ui_signals` / `restore_ui_signals`.
5. **Пути к файлам профиля**: Всегда запрашивать пути через `PathManager` (`app/core/paths/path_manager.py`). Не формировать жесткие пути к `%APPDATA%` вручную.

### 7.3. Опасные действия, которых следует избегать
- **Запрещено вызывать `sys.exit()` или `QApplication.quit()` из UI-компонентов**: Завершение должно идти через закрытие окна и обработчик `AppShutdownController`. Исключение — только `emergency_shutdown()`.
- **Запрещено выполнять операции с БД или тяжелый I/O в GUI-потоке**: Вызывать асинхронные методы (например, `initialize_or_migrate_async()`) или использовать `WorkerManager.run()`.
- **Запрещено использовать сырые потоки `threading.Thread` в связке с Qt-виджетами**: Использовать `QThreadPool`, `QRunnable` или `QThread` для безопасной интеграции с циклом обработки событий Qt.
- **Запрещено нарушать инкапсуляцию `common.qss` через инлайн-стили `widget.setStyleSheet("...")`**: Локальные стили перебивают динамическую смену 17 тем и ломают палитру.
- **Запрещено забывать о плюрализации при переводе**: Числительные обязаны оформляться через `self.tr("%n item(s)", "", count)` для корректной грамматики в славянских и европейских языках.

---

## 8. UNVERIFIED

Следующие аспекты кодовой базы не могут быть однозначно верифицированы исключительно статическим анализом без выполнения кода в целевой ОС:

1. **Реальная работа Windows File Associations на правах обычного пользователя**:
   - `FileAssociationService` (`app/services/file_association_service.py`) производит запись в ветку реестра `HKCU\Software\Classes`. Теоретически это не требует прав Администратора (UAC), но поведение при наличии сторонних ассоциаций в `HKLM` требует верификации на чистой Windows.
2. **Время отклика при восстановлении сверхкрупных баз данных (> 500 МБ)**:
   - В тестах проверяются базы небольшого размера. Поведение `DatabaseManager.maintenance_scope(timeout=30.0)` при завершении длительных фоновых транзакций на очень больших базах данных при медленном дисковом I/O статически не верифицируемо.
3. **Совместимость с Linux / macOS**:
   - Несмотря на абстракции в коде, проект позиционируется для `win32` (`pyproject.toml:17`), использует `pywin32` и расширения реестра Windows. Полноценная работа без GUI на Linux (`--no-gui`) в CI не тестируется (CI запускается строго на `windows-latest`).
