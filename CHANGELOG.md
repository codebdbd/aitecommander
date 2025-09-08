# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Removed
- Deleted unused module `app/utils/system/os_ops.py` (functions `open_file`, `reveal_in_folder`) as it was not referenced anywhere in app or tests.
- Deleted `app/utils/ui/menu_builders/ctx_menu.py` and its test `tests/test_ctx_menu_builder.py` due to UX issues (duplicate standard context menus) and lack of integration needs.
- Deleted obsolete benchmark script `scripts/bench_export_full_structure.py` (bulk vs N+1 export); benchmark completed and no longer needed.

### Changed
- Simplified structure operations architecture by removing validation and operation strategies.
  - Removed `ValidationStrategy`, `DefaultValidationStrategy`, `StructureOperationStrategy`, `DefaultOperationStrategy`.
  - Inlined validation into `BaseOperations._validate_data()` and upsert execution into `BaseOperations._upsert_and_emit()`.
  - Public API of `BaseOperations` remains: `create_item`, `update_item`, `delete_item` and signal emission via `StructureSignalEmitter`.
- UI Top Panels: enforced strict interface contract for favorites widget
  - `TopPanelsController` now requires `FavoritesPanelWithClear` (must implement `clear_favorites`).
  - Removed fallback behavior in `clear_favorites`.
- TreeManagement optimizations and robustness
  - Uses cached `self.model` instead of repeated `tree.model()` calls.
  - Logs and early-exits when model is missing.
- Window setup hardening
  - `_connect_top_panels_signals` now raises `SetupError` on missing required widgets/controllers instead of silent hasattr/try-except.
- Tests cleanup
  - Added shared stubs/fixtures in `tests/conftest.py` (signals, minimal favorites/recents widgets, links business).
  - Updated tests to use shared fixtures; fixed missing imports; added tests for model cache and setup errors.

### Summary
- TopPanelsController жёстко требует виджеты и бизнес‑слой, инициализирует четыре QTimer и предоставляет методы с дебаунсом `request_refresh`, `request_favorites_refresh` и `request_recents_refresh`, логируя ошибки загрузки и обновления панелей.
- CategoryTilesController принимает `ui_state` и `structure_business` как обязательные зависимости и обновляет плитки через состояние, опционально передавая данные напрямую в виджет, при этом фиксируя ошибки получения категорий или переключения состояния.
- LinksTableController проверяет интерфейс таблицы по протоколу, валидирует обязательные зависимости и сериализует перезагрузки, предотвращая параллельные обращения к базе при смене категории.

### Issues & Tasks
- TopPanelsController.__init__: блок вокруг инициализации таймеров использует общий `except Exception: pass`, что скрывает ошибки конфигурации.
  - Задачи: удалить `try/except` вокруг `setParent` и `setInterval`; при исключениях логировать и поднимать `SetupError`; добавить тест, подтверждающий явную ошибку при некорректном `main_window`.
- `_resolve_structure_loader` и `_on_structure_changed_schedule_refresh`: использование `getattr` и широких `except` может маскировать отсутствие методов загрузки структуры или сбои планировщика.
  - Задачи: в `_resolve_structure_loader` явно проверять наличие `load_structure_async` и/или `load_structure`, поднимать `SetupError`, если нет ни одного; в `_on_structure_changed_schedule_refresh` ловить только `AttributeError`/`TypeError`, неожиданные ошибки логировать и пробрасывать; добавить тест, демонстрирующий `SetupError` для неверно сконфигурированного `StructureBusinessLogic`.
- LinksUIHandlers напрямую обновлял таблицу поиска, обходя LinksTableController, что нарушало единый путь обновления.
  - Статус: исправлено — `links_table_controller` передаётся через конструктор, а `_update_search_results` вызывает `links_table_controller.on_search_results(...)`; обновить/поддерживать тесты, проверяющие, что контроллер получает данные поиска.

### Hardening: UI signals and setup
- Links table handlers: stricter wiring contracts
  - `LinksUIHandlers._connect_table_signals()` теперь требует наличие сигналов таблицы: `doubleClicked`, `clicked`, `links_reordered`, а также `selectionModel().selectionChanged`. При отсутствии — явный `SetupError` вместо молчаливых фолбэков.
  - Добавлен тест `tests/test_links_handlers_wiring.py`, проверяющий подъём `SetupError` при неполной таблице.
- Structure loader resolution: явная ошибка конфигурации
  - В `app/controllers/system/window_controllers_setup.py` выделен `_resolve_structure_loader()`; если у `StructureBusinessLogic` нет ни `load_structure_async()`, ни `load_structure()`, поднимается `SetupError` уже на этапе проводки сигналов.
  - Обновлён `tests/test_structure_loader_requirements.py` под новое поведение (ожидается `SetupError`).
- Интеграционные тесты и заглушки обновлены под строгие контракты
  - `tests/test_integration_signals.py`: `TableViewMock` получил необходимые сигналы и `selectionModel().selectionChanged`.
  - `tests/test_structure_spheres_integration.py`: фикстура `window_stub` получила заглушку `load_structure`.

### Motivation
- Стабильность и прозрачность конфигурации важнее микрооптимизаций: убраны молчаливые фолбэки и «скрытые» пути.
- Явные `SetupError` упрощают отладку неправильной проводки сигналов и отсутствующих зависимостей.
- Все изменения покрыты тестами; актуальный статус: все тесты проходят (162 passed).

### Migration notes
- Derived classes (`CategoryOperations`, `SectionOperations`, `SphereOperations`, `PositioningOperations`) typically require no changes if using `BaseOperations` public methods.
- Tests referencing `DefaultValidationStrategy` should be updated to remove the import and, if needed, mimic validation equivalent to `BaseOperations._validate_data()`.

### Notes
- Signals and logging are unchanged.
- Upsert errors now surface as `StructureOperationError` with operation type "upsert" and item type name.
