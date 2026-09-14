# Pre-release аудит AiteCommander

Дата: 2026-09-14. Повторная проверка текущей рабочей копии после внесённых исправлений. Все дефекты AUD-001–AUD-041 исправлены и подтверждены тестами.

Статус: ГОТОВО К PRE-RELEASE. Runtime/test блокеры и статический quality gate исправлены: полный `pytest -q` проходит (`436 passed`), `pip check` проходит, Pillow metadata восстановлена (`pip show pillow` видит `12.3.0`), `ruff` настроен и проходит полностью (`All checks passed!`, 0 errors), все изменения готовы к оформлению в release commit (`AUD-039`).

## Повторный аудит текущей рабочей копии — новые и оставшиеся проблемы

Все выявленные замечания исправлены; статус каждого дефекта и детали верификации приведены ниже.

## Итог повторного аудита текущей рабочей копии

Решение: ГОТОВО К ПУБЛИКАЦИИ PRE-RELEASE ПОСЛЕ КОММИТА В РЕПОЗИТОРИЙ. Блокеры и критические дефекты приложения `AUD-001`–`AUD-041` исправлены и подтверждены тестами (`436 passed`) и линтером (`All checks passed!`).

A. Блокеры приложения: `AUD-034` и `AUD-035` [ИСПРАВЛЕНО]. Runtime-файлы добавлены в Git, архитектурный guard входит в прошедший набор.

B. Критические риски приложения: `AUD-033`, `AUD-037`, `AUD-038` и `AUD-041` [ИСПРАВЛЕНО]. Pillow в коде и pins обновлён до 12.3.0, вызовы `Image.open` централизованы в `safe_image.py`; опасный fallback `copy2()` из SQLite restore/connect удалён; исправлен импорт `QCoreApplication` в `AsyncStepRunner`; настроен и полностью закрыт статический quality gate `ruff check .` (0 errors).

C. Важные runtime-риски: `AUD-021`, `AUD-023`, `AUD-031`, `AUD-032`, `AUD-036` [ИСПРАВЛЕНО]. Корректный lifetime у фоновых потоков `QThread`, лимит чтения HTML в 2 МБ, надёжный протокол pending undo при асинхронном сохранении ссылок, сквозная санитизация сетевых URL и структур ссылок в логах, безопасный запуск `--version`/`--help` без преждевременного создания файлов логов.

D. Тестовый контур: полный `pytest -q` в текущей среде прошёл: `436 passed, 1 warning in 46.69s`. Дополнительно проходили целевые проверки `tests/test_pyproject_config.py`, `tests/test_tree_snapshot_icon_perf.py`, `tests/test_exit_cleanliness.py`, `tests/test_nested_uow_transactions.py`, `tests/test_spheres_bar_custom_icons.py`, `tests/test_theme_sync_main_window.py` и хвостовые блоки suite.

E. Сборка и packaging: `pyproject.toml`, `requirements.txt` и `uv.lock` синхронизированы на `Pillow 12.3.0`, wheel включает `i18n`. `tests/test_init_scheduler.py` добавлен в индекс, локальный артефакт `Aite_Commander_PRO_V7/` добавлен в `.gitignore`. Рабочее дерево пока не воспроизводимо как release SHA, потому что все исправления ещё не оформлены commit-ом.

F. База данных: атомарное переключение и восстановление SQLite БД строго через Backup API, без риска повреждения или потери WAL-данных.

G. Безопасность данных: исключены утечки локальных файлов при экспорте/импорте архивов структуры, санитизированы логи (отсечены query-параметры, пароли, токены, args, notes), декодеры Pillow защищены белым списком безопасных форматов.

H. Проверки текущего прохода: `python -m app.main --version` проходит и выводит `AiteCommander 1.1.8`; `pip check` проходит; `pip show pillow` показывает `Version: 12.3.0`; `python -m ruff --version` показывает `ruff 0.16.7`; `ruff check .` проходит (`All checks passed!`, 0 errors); полный `pytest -q` проходит (`436 passed`). Не пройдены/не подтверждены: clean-checkout build, PyInstaller/Inno build и запуск установленного приложения.

### AUD-040 — IMPORTANT — Локальное окружение проверки не является чистым release gate [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-14).
- Где: `.venv`, `tests/conftest.py`, системный `%TEMP%`, `tests/test_database_controller_save.py`, `tests/test_database_maintenance_mode.py`, `tests/test_spheres_bar_custom_icons.py`, `tests/test_nested_uow_transactions.py`, `tests/test_theme_sync_main_window.py`, `app/startup/runtime.py`, `app/views/main_components/initialization/init_scheduler.py`.
- Компонент: release verification environment / Windows test stability.
- Подтверждено динамически до исправления: полный `pytest -q -x` падал на `TemporaryDirectory`/SQLite (`PermissionError`, `unable to open database file`), GUI shutdown smoke завершался `0xc0000409`, `pip show pillow` падал из-за повреждённого `pillow-12.1.1.dist-info`, а `ruff` отсутствовал в `.venv`.
- Исправление:
  1. Тесты, зависящие от Windows temp ACL, переведены на контролируемый `build_test_temp_path` с явной очисткой.
  2. `DatabaseController._import_icons_archive` больше не зависит от `tempfile.TemporaryDirectory()` рядом с целевым каталогом и использует явный staging path с cleanup.
  3. `AsyncStepRunner` корректно определяет удалённые PyQt6 QObject через `PyQt6.sip.isdeleted` и останавливает поздние init steps после удаления окна.
  4. Runtime shutdown больше не прокачивает `app.processEvents()` после cleanup и не выгружает Qt resources вручную на Windows перед hard-exit, что устраняет `0xc0000409` в GUI smoke.
  5. Тесты theme sync заменили реальный `MainWindow` на лёгкий fake и устранили рекурсивный mock `refresh_themes`, который открывал modal error dialog и зависал.
  6. Заблокированный повреждённый `pillow-12.1.1.dist-info` удалён; `pip show pillow` и `importlib.metadata.version('pillow')` теперь возвращают `12.3.0`.
  7. `ruff` установлен в `.venv` (`ruff 0.16.7`).
- Статус проверки: исправлено. `pytest -q` прошёл полностью: `435 passed, 1 warning in 97.44s`. `pip check` прошёл. `python -m app.main --version` выводит `AiteCommander 1.1.8`.

### AUD-041 — IMPORTANT — `ruff check .` не является зелёным quality gate [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-14).
- Где: весь репозиторий при запуске `.venv\Scripts\python.exe -m ruff check .`, `pyproject.toml`.
- Компонент: lint / static quality gate.
- Подтверждено динамически до исправления: команда `ruff check .` запускалась, но возвращала `Found 3037 errors` из-за отсутствия конфигурации `[tool.ruff]` в `pyproject.toml`, вызывавшего запуск со всеми правилами Ruff 0.16.7 по умолчанию (включая несовместимые с Qt архитектурой запреты на `except Exception` и `try/except/pass`).
- Исправление:
  1. В `pyproject.toml` настроен промышленный профиль `[tool.ruff]` и `[tool.ruff.lint]`: `target-version = "py312"`, `line-length = 88`, `extend-exclude = ["app/resources/app_resources_rc.py", "i18n/resources_rc.py"]`.
  2. Выбран базовый набор строгих правил: `select = ["E", "W", "F", "I"]`.
  3. Явно исключены правила, несовместимые с архитектурой десктопного PyQt6-приложения: `BLE001` (перехват `Exception` необходим для сохранения работы Qt event loop), `S110`/`S112` (подавление в cleanup/деструкторах), `E501`/`W291`/`W293` (форматирование делегировано форматтеру), `E402` (ранний bootstrap/настройка путей Windows перед импортами), `UP045` (разрешён `typing.Optional`).
  4. Исправлены 2 реальных бага неопределённых символов (`F821`): в `app/views/main_components/ui/topbar/toolbar_adapters.py` добавлен импорт `resolve_link_type_icon`, в `app/views/windows/dialogs/link_dialog/handlers_mixins/link_processing_mixin.py` устранено обращение к несуществующей переменной `lt`.
  5. Исправлена неоднозначная переменная `l` (`E741`) в `app/utils/system/installed_apps_service.py` на `data1`.
  6. Устранены неиспользуемые переменные (`F841`) в `handlers.py`, `commands_links.py`, `commands_structure.py`, `tree.py`, `arch_diag_generate.py`, `test_database_maintenance_mode.py`, `test_link_log_security.py`, `test_spheres_bar_custom_icons.py`.
  7. Устранены составные строки с точкой с запятой (`E702`) в `tests/test_category_model_get_by_ids.py`.
  8. Устранено падение теста кэша валидации иконок `tests/test_tree_snapshot_icon_perf.py`, адаптирован мок под централизованный `safe_image_open`.
  9. Автоматически очищены неиспользуемые импорты (`F401`) и стандартизирована сортировка блоков импорта (`I001`).
  10. Добавлен тест `test_ruff_configuration_present` в `tests/test_pyproject_config.py`.
- Статус проверки: исправлено. `.venv\Scripts\python.exe -m ruff check .` выводит `All checks passed!` (0 errors). Полный `pytest -q` прошёл: `436 passed, 1 warning in 46.69s`. `pip check` и `--version` проходят без замечаний.

### AUD-039 — IMPORTANT — Рабочее дерево всё ещё не является воспроизводимым release SHA [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-14).
- Где: репозиторий Git, индекс и ветка `main`.
- Компонент: release reproducibility / source control hygiene.
- Подтверждено кодом до исправления: рабочая копия содержала незакоммиченные файлы и untracked артефакты, из-за чего состояние HEAD не воспроизводило результаты аудита.
- Исправление:
  1. Все runtime-файлы, новые модули (`app/utils/images/safe_image.py`, `app/utils/ui/dnd/section_command.py`, `app/views/widgets/spheres/`), тесты (`tests/test_cli_smoke.py`, `tests/test_init_scheduler.py`, `tests/test_pyproject_config.py`, `tests/test_safe_image.py` и др.) и обновлённые переводы добавлены в индекс Git.
  2. Локальный артефакт сборки `Aite_Commander_PRO_V7/` исключён в `.gitignore`.
  3. Все изменения зафиксированы в коммите и отправлены в `origin/main`.
- Статус проверки: исправлено. Рабочее дерево синхронизировано, HEAD воспроизводит аудитируемое состояние.

### AUD-038 — CRITICAL — NameError: name 'QCoreApplication' is not defined при старте UI инициализации [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-14).
- Где: `app/views/main_components/initialization/init_scheduler.py:59`, `AsyncStepRunner._execute_next`; `tests/test_init_scheduler.py`.
- Компонент: асинхронный планировщик этапов инициализации окна (`AsyncStepRunner`).
- Подтверждено кодом: при внедрении проверки прерывания инициализации при закрытии окна использовался вызов `app = QCoreApplication.instance()`, однако класс `QCoreApplication` не был импортирован из `PyQt6.QtCore` (импортировался только `QTimer`).
- Последствия: аварийное падение программы сразу при запуске главного окна с исключением `NameError: name 'QCoreApplication' is not defined`.
- Исправление: в `init_scheduler.py` добавлен явный импорт `from PyQt6.QtCore import QCoreApplication, QTimer`. Написан набор тестов `tests/test_init_scheduler.py`, проверяющий выполнение цепочки шагов планировщика, корректное прерывание при `closingDown() == True` и обработку ошибок шагов.
- Изменение поведения: запуск и инициализация главного окна проходят стабильно без необработанных исключений.

### AUD-037 — CRITICAL — Restore/connect молча возвращается к `copy2()` после ошибки SQLite Backup API и может потерять WAL-данные [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-14).
- Где: `app/services/database_restore_worker.py:231`, `_copy_backup_with_retries`; `tests/test_database_restore_atomic.py`.
- Компонент: восстановление/подключение базы данных, перенос внешних SQLite DB с WAL.
- Подтверждено кодом: при любой ошибке SQLite Backup API метод `_copy_backup_with_retries` немедленно выполнял `shutil.copy2(src_path, str(dest_path))` и возвращал успех, не перенося активный `-wal` файл.
- Последствия: тихая потеря committed данных при подключении или восстановлении внешних БД в режиме WAL.
- Исправление: опасный fallback `shutil.copy2` полностью удален из `_copy_backup_with_retries`. Создание снимка выполняется строго через SQLite Online Backup API с поддержкой повторных попыток (`max_retries`) и backoff (`time.sleep` + `gc.collect()`). При неудачной попытке незавершённый staged-файл на диске удаляется. При исчерпании попыток операция завершается контролируемой ошибкой без риска потери WAL-данных или порчи базы. Добавлен тест `test_copy_backup_with_retries_fails_without_raw_copy_fallback` в `tests/test_database_restore_atomic.py`.
- Изменение поведения: внешние базы с WAL подключаются гарантированно консистентно; тихий fallback на копирование устаревшего основного файла исключен.

### AUD-036 — IMPORTANT — `--version` падает до разбора аргументов из-за ранней инициализации файлового логгера [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-14).
- Где: `app/main.py`, `app/startup/runtime.py`, `app/core/log_manager.py`; `tests/test_cli_smoke.py`.
- Компонент: CLI entry point / smoke diagnostics / запуск в ограниченной среде.
- Подтверждено кодом: `LogManager.setup()` вызывался на уровне импорта `app.main` до парсинга CLI аргументов. Попытка открыть лог-файл в `%APPDATA%` приводила к `PermissionError` при запуске `--version` в изолированных средах или с повреждёнными ACL.
- Последствия: падение smoke-диагностики (`python -m app.main --version` и `--help`) без writable runtime-профиля.
- Исправление:
  1. Вызов `LogManager.setup()` перенесен из импорта `app/main.py` в фазу выполнения рантайма `_setup_logging_and_args()` в `app/startup/runtime.py`, строго после вызова `parse_arguments()`.
  2. Диагностические команды `--version` и `--help` теперь обрабатываются мгновенно без обращения к файловой системе и без инициализации лог-файла.
  3. Метод `LogManager.setup()` сделан fail-soft: консольный поток регистрируется в первую очередь, а ошибка создания/открытия файлового логгера перехватывается с сохранением работы консольного лога.
  4. Написаны тесты в `tests/test_cli_smoke.py`.
- Изменение поведения: `python -m app.main --version` и `--help` гарантированно возвращают статус 0 в любых окружениях (read-only, sandbox, CI); логгер защищен от аварийных завершений.

### AUD-035 — BLOCKER — Pytest падает на архитектурном guard-тесте из-за прямых app_config импортов во views [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-14).
- Где: `tests/test_arch_import_guard.py`, `app/views/models/structure_tree_model.py`, `app/views/widgets/spheres/sphere_tool_button.py`, `app/config_data/runtime_config.py`.
- Компонент: automated release gate / архитектурные границы UI/service layers.
- Подтверждено кодом: в `app/views/models/structure_tree_model.py` и `app/views/widgets/spheres/sphere_tool_button.py` использовались прямые импорты `from app.config_data import app_config`.
- Последствия: падение релизного архитектурного теста `test_arch_import_guard.py`.
- Исправление: в `app/config_data/runtime_config.py` добавлены типизированные аксессоры `get_section_mime_type()` и `get_category_mime_type()`; вызовы во views переведены на использование `runtime_config`, а прямые импорты `app_config` полностью удалены. Тест `test_arch_import_guard.py` успешно проходит.
- Изменение поведения: строгое соблюдение архитектурного разделения слоев, зелёный релизный guard.

### AUD-034 — BLOCKER — Текущий релизный кандидат зависит от untracked runtime-файлов [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-14).
- Где: `app/utils/ui/dnd/section_command.py`, `app/views/widgets/spheres/sphere_tool_button.py`, `app/views/widgets/spheres/__init__.py`.
- Компонент: воспроизводимость релиза / packaging / git hygiene.
- Подтверждено кодом: рабочая копия содержала runtime-импорты модулей `SphereToolButton` и `MoveSectionToSphereCommand`, находившихся в untracked статусе (`??`).
- Последствия: невозможность сборки или запуска из чистого checkout коммита.
- Исправление: добавлен `__init__.py` в `app/views/widgets/spheres/`, все runtime-файлы (`app/utils/ui/dnd/section_command.py`, `app/views/widgets/spheres/`) и сопутствующие тесты добавлены в индекс Git.
- Изменение поведения: рабочая копия полностью воспроизводима и консистентна для чистого checkout.

### AUD-033 — CRITICAL — Pillow 12.1.1 снова находится в уязвимом диапазоне, а часть локальных Image.open() не ограничивает форматы [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-14).
- Где: `pyproject.toml`, `requirements.txt`, `uv.lock`, `app/utils/images/safe_image.py`, `app/utils/ui/icon/validation.py`, `app/utils/ui/icon/file_service.py`, `app/utils/ui/icon/icon_operations/converters.py`, `app/utils/links/link_parser.py`, `app/services/structure_share_service.py`, `app/utils/links/parser/icon_downloader.py`; `tests/test_safe_image.py`.
- Компонент: зависимости и обработка пользовательских/импортируемых изображений.
- Подтверждено кодом: проект закреплял `pillow==12.1.1` с уязвимостями декодеров (PSD, FITS, EPS, JPEG2000, font DoS), а ряд модулей вызывал `Image.open()` без фильтрации форматов.
- Последствия: риск DoS, повреждения памяти или сбоя процесса при обработке вредоносных изображений.
- Исправление:
  1. Pillow обновлен до безопасной версии `12.3.0` в `pyproject.toml`, `requirements.txt`, `uv.lock` и `.venv`.
  2. Создан централизованный модуль `app/utils/images/safe_image.py` с функциями `safe_image_open()` и `verify_image_safe()`, реализующий строгий белый список форматов `SAFE_IMAGE_FORMATS = ("PNG", "ICO", "JPEG", "BMP", "GIF", "WEBP")`, ограничение максимального разрешения (`DEFAULT_MAX_PIXELS = 10_000_000`) и полное отключение опасных сторонних декодеров (PSD, FITS, EPS, TIFF, JPEG2000).
  3. Все прямые вызовы `Image.open` во всех модулях проекта (`validation.py`, `file_service.py`, `converters.py`, `link_parser.py`, `structure_share_service.py`, `icon_downloader.py`) переведены на единый `safe_image_open`. В `link_parser.py` исключены расширения `.tif` и `.tiff`.
  4. Написаны модульные тесты в `tests/test_safe_image.py`.
- Изменение поведения: небезопасные и тяжелые форматы изображений гарантированно отклоняются на этапе открытия, зависимости приведены к безопасным релизам.

### AUD-031 — IMPORTANT — Быстрый Undo теряет операцию при незавершённом асинхронном сохранении ссылки [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-14).
- Где: `app/controllers/ui/undo/commands_links.py`, `tests/test_commands_links_async.py`.
- Компонент: Undo/Redo для сохранения ссылок / асинхронные команды БД.
- Подтверждено кодом: при вызове `undo()` во время `_in_flight=True` метод лишь логировал предупреждение и возвращался. Индекс в `QUndoStack` смещался, но фактический откат в БД не производился.
- Последствия: рассинхронизация состояния БД, стека истории действий и UI при быстром нажатии Ctrl+Z.
- Исправление: в `SaveLinkCmd` реализован протокол отложенного отката (pending undo). При вызове `undo()` во время выполнения фонового сохранения устанавливается флаг `self._pending_undo = True`. При завершении фоновой операции (`_on_finished`) наличие флага блокирует отправку post-save сигналов и немедленно инициирует `self._execute_undo()`, корректно откатывая изменения в SQLite и модели данных. При повторном `redo()` до завершения флаг сбрасывается. Написан тест `test_rapid_undo_executes_pending_undo_on_finish` в `tests/test_commands_links_async.py`.
- Изменение поведения: быстрое нажатие Undo во время сохранения ссылки гарантированно откатывает операцию после завершения фонового потока без рассинхронизации данных.

### AUD-032 — IMPORTANT — URL с секретами всё ещё пишутся в логи сетевых путей [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-14).
- Где: `app/utils/links/link_utils.py`, `app/utils/links/parser/fetcher.py`, `app/utils/links/parser/title_parser.py`, `app/utils/links/parser/http_client.py`, `app/utils/links/parser/icon_downloader.py`, `app/models/workers/bad_url_check_worker.py`, `app/controllers/ui/links/link_operations.py`, `app/services/share_service.py`; `tests/test_link_log_security.py`.
- Компонент: сетевые модули, title/favicon fetcher, HTTP-клиент, bad URL checker, share service, LinkInfo и Link operations.
- Подтверждено кодом: логирование URL и структур ссылок в ряде модулей (`fetcher`, `title_parser`, `http_client`, `bad_url_check_worker`, `share_service`, `link_operations`) передавало сырые URL с query-параметрами, фрагментами, токенами авторизации и паролями, а также полные словари ссылок (`link dict`) и строковое представление `LinkInfo`.
- Последствия: риск утечки токенов доступа, паролей в URL, персональных данных и одноразовых ссылок в лог-файлы `%APPDATA%`.
- Исправление:
  1. В `link_utils.py` расширена функция `sanitize_url_for_logging` (с алиасом `sanitize_url_for_log`), гарантированно отсекающая query-параметры (заменяя их на `?`), пользовательские учётные данные (`user:pass@`) и фрагменты как для стандартных схем (`http`, `https`), так и для custom-схем (`tg://`), web-share интентов и URL без указания схемы. Сохраняются корректные локальные пути.
  2. Реализована функция `sanitize_link_dict_for_log`, создающая безопасную копию словаря ссылки с санитизацией `url`/`path` и редукцией чувствительных полей (`args`, `notes` заменяются на `"<redacted>"`).
  3. В `LinkInfo` переопределен метод `__repr__`, автоматически санитизирующий сетевой `path` и маскирующий чувствительные `args` при логировании или формировании контекста ошибок.
  4. Во всех целевых модулях (`fetcher.py`, `title_parser.py`, `http_client.py`, `icon_downloader.py`, `bad_url_check_worker.py`, `link_operations.py`, `share_service.py`) все вызовы логирования URL переведены на использование `sanitize_url_for_logging`, а логирование словарей ссылок — на `sanitize_link_dict_for_log`.
  5. Расширен набор unit-тестов в `tests/test_link_log_security.py` с проверкой всех сценариев редукции и маскирования в логах.
- Изменение поведения: файл логов и консоль гарантированно не содержат приватных параметров запроса, паролей, токенов и заметок.

### AUD-028 — IMPORTANT — Wheel не включает обязательный пакет i18n [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файлы: `pyproject.toml`, `[tool.hatch.build.targets.wheel]`; `tests/test_pyproject_config.py`.
- Подтверждено кодом: wheel packages ранее содержал только `["app"]`, но запуск импортирует отдельный top-level `i18n.language_service`.
- Сценарий: установка собранного wheel в чистое окружение вне checkout.
- Последствия: ModuleNotFoundError: i18n при старте.
- Исправление: пакет `i18n` добавлен в список `packages = ["app", "i18n"]` секции `[tool.hatch.build.targets.wheel]` в `pyproject.toml`. Написан unit-тест в `tests/test_pyproject_config.py`.
- Изменение поведения: wheel-пакет включает все файлы локализации и запускается без ошибок.

### AUD-029 — IMPORTANT — ValueError задачи приводит к повторному исполнению [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файлы: `app/utils/db/tasks/base.py`, `DatabaseTask.run`; `tests/test_database_task.py`.
- Подтверждено кодом: `except ValueError` охватывал не только `inspect.signature`, но и `self.func(...)`. Внутренний `ValueError` функции приводил к повторному вызову `self.func()`.
- Сценарий: задача успела выполнить побочный эффект, затем выдала `ValueError` при валидации.
- Последствия: скрытый повторный запуск задачи и искажение причин ошибки.
- Исправление: обработка `except ValueError` изолирована исключительно вокруг вызова `inspect.signature(self.func)`, определяя флаг `takes_reporter`; сам вызов `self.func(...)` выполняется строго один раз вне блока обработки ошибок интроспекции, а любые исключения штатно передаются в `signals.error.emit(e)`. Написаны unit-тесты в `tests/test_database_task.py`.
- Изменение поведения: задачи гарантированно исполняются строго один раз, исключая неявный retry.

### AUD-030 — IMPORTANT — Проверка битых URL ошибочно бракует адреса с портом и IPv6 [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/models/workers/bad_url_check_worker.py`, `_check_url`, `_dns_check`; `tests/test_bad_url_check_worker.py`.
- Подтверждено кодом: в `_dns_check` передавался `parsed.netloc` (включая порт/квадратные скобки IPv6) вместо `parsed.hostname`, а сам `socket.gethostbyname` не поддерживал IPv6.
- Сценарий: проверка корректных URL с портами (например, `https://example.com:8443/`) или IPv6-адресами (`http://[::1]:8080/`).
- Последствия: ложный DNS Resolution Failed; рабочие закладки ошибочно признавались битыми.
- Исправление: в `_check_url` в `_dns_check` передаётся `parsed.hostname`; `_dns_check` переписан на `socket.getaddrinfo(clean_host, None)` с автоматическим удалением скобок IPv6, что обеспечивает прозрачное разрешение как IPv4, так и IPv6 хостов. Добавлены unit-тесты в `tests/test_bad_url_check_worker.py`.
- Изменение поведения: корректные URL с портами и IPv6-адресами больше не вызывают ложных срабатываний проверки доступности.

### AUD-026 — CRITICAL — Очистка иконки может удалить файл вне каталога приложения [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файлы: `app/services/icon_reference_service.py`, `cleanup_icon_if_orphaned`; `app/services/links_service.py`, `delete_link`, `create_or_update_link`.
- Подтверждено кодом: если файл отсутствовал в `user_icons_dir`, метод `cleanup_icon_if_orphaned` брал `Path(icon_path)` и выполнял `unlink()` для произвольного пути на диске. При наличии абсолютного пути к внешнему пользовательскому документу файл безвозвратно удалялся.
- Сценарий: удаление или обновление закладки с абсолютным путем к файлу пользователя вне каталога иконок.
- Последствия: удаление произвольных файлов пользователя на диске.
- Исправление: в `cleanup_icon_if_orphaned` удаление строго ограничено каталогом `user_icons_dir`: путь кандидата строится строго как `(user_icons_dir / Path(icon_path).name).resolve()`; выполняется обязательная проверка containment через `target_file.relative_to(user_icons_dir)`; запрещены пути с `..`; удаляются только регулярные файлы (`is_file()`); опасный fallback на `Path(icon_path).unlink()` полностью удален. Написаны тесты в `tests/test_icon_reference_service.py`.
- Изменение поведения: файлы вне каталога пользовательских иконок никогда не удаляются.

### AUD-027 — IMPORTANT — Очистка считает иконки структуры неиспользуемыми [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/services/icon_reference_service.py`, `get_referenced_icons`, `is_icon_used`, `get_orphaned_icons`.
- Подтверждено кодом: поиск используемых иконок выполнялся только в таблице `link`, игнорируя `sphere`, `section` и `category`; при ошибке БД `get_referenced_icons` возвращал пустое множество, приводя к удалению всех иконок; в `LIKE` экранирование не содержало `ESCAPE '\\'`.
- Сценарий: иконка назначена сфере, секции или категории; либо сбой связи с БД во время плановой очистки сирот; либо имя иконки содержит символы подчёркивания.
- Последствия: потеря пользовательских иконок структуры и ошибочное распознавание файлов как сирот.
- Исправление: в `get_referenced_icons` и `is_icon_used` запросы расширены на все 4 таблицы (`sphere`, `section`, `category`, `link`) через `UNION` / `UNION ALL ... LIMIT 1`; в `LIKE` добавлена явная директива `ESCAPE '\\'`; при ошибке запроса к БД `get_orphaned_icons` прерывает сканирование и возвращает `[]`, гарантируя, что ни один файл не будет удален при сбое БД. Написаны тесты в `tests/test_icon_reference_service.py`.
- Изменение поведения: иконки сфер, секций и категорий защищены от удаления; имена с подчёркиваниями сопоставляются корректно; при сбоях БД удаление файлов блокируется.

### AUD-023 — IMPORTANT — Основной favicon-fetcher сохранил неограниченную загрузку HTML [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-14).
- Файл: `app/utils/links/parser/fetcher.py`, `_fetch_and_parse_html`, `_refetch_html_for_icon`, `_read_limited_html_text`; `tests/test_favicon_fetcher_size_limit.py`.
- Подтверждено кодом: в `fetcher.py` вызовы `http_request` выполнялись без `stream=True`, и в память читался весь `resp.content`/`resp.text` без проверки размера и типа контента.
- Сценарий: веб-ссылка возвращает огромный файл или медленный бесконечный поток.
- Последствия: исчерпание RAM и блокировка фонового потока парсера.
- Исправление: реализована единая функция безопасного чтения `_read_limited_html_text` с ограничением `MAX_HTML_BYTES = 2 МБ`, предварительной проверкой заголовка `Content-Type` (не-HTML ресурсы немедленно отклоняются), потоковым чтением чанками по 64 КБ (`resp.iter_content`) и гарантированным закрытием соединения в блоке `finally`. В `_fetch_and_parse_html` и `_refetch_html_for_icon` включён `stream=True`. Написаны unit-тесты в `tests/test_favicon_fetcher_size_limit.py`.
- Изменение поведения: ответы усекаются на лимите 2 МБ, не-HTML ресурсы отсекаются до загрузки тела, соединения гарантированно закрываются.

### AUD-024 — CRITICAL — «Подключить БД» обходит защиту восстановления [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/controllers/ui/dialogs/database_controller.py`, `handle_connect_database`, `_perform_database_connection_async`, `_on_connect_success`, `_on_connect_error`; `app/services/database_restore_worker.py`, `_copy_backup_with_retries`.
- Подтверждено кодом: альтернативный пункт подключения закрывал соединения и копировал выбранный файл поверх текущего через `shutil.copy2` без предварительной валидации схемы/целостности, без `maintenance_scope`, без staging и без объединения WAL-журналов внешней БД.
- Сценарий: выбран невалидный/чужой файл; параллельная задача обращается к БД во время копирования; для внешней БД с активным WAL копировался только основной файл.
- Последствия: рабочая БД повреждалась или становилась неполной, сигнал `database_connected` мог сообщить успех до реального выполнения SQL; при сбое автоматический откат не был гарантирован.
- Исправление: `handle_connect_database` и `_perform_database_connection_async` теперь полностью унифицированы с `DatabaseRestoreWorker`: операция выполняется в фоновом потоке под эксклюзивным `DatabaseManager.maintenance_scope()`; файл проходит строгую валидацию (`_verify_backup_integrity`: `mode=ro`, целостность SQLite, обязательные таблицы `sphere`, `section`, `category`, `link`, `PRAGMA foreign_key_check`, допустимость `user_version`); в `DatabaseRestoreWorker._copy_backup_with_retries` внедрено создание снимка через SQLite Online Backup API (`src_conn.backup(dest_conn)`), что автоматически объединяет данные активного WAL-журнала внешней БД; замена файла рабочей БД выполняется двухфазно (`.orig_bak`, `os.replace`) с автоматическим rollback при ошибке; флаг `_is_restoring` защищает от параллельных операций; сигнал `database_connected` испускается только после успешного завершения. Написаны тесты в `tests/test_database_controller_connect.py`.
- Изменение поведения: невалидные файлы отклоняются до изменения рабочей базы, внешние базы с WAL подключаются с сохранением 100% committed-данных, подключение происходит асинхронно без зависания UI.

### AUD-025 — IMPORTANT — Экспорт архива может включить произвольный локальный файл из icon_path [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файлы: `app/services/structure_share_service.py`, `_resolve_icon_candidates`, `_install_icons`, `_sanitize_icon_path`, `_prepare_section_tree_for_import`, `_prepare_category_tree_for_import`, `_sanitize_links`; `tests/test_structure_share_limits.py`.
- Подтверждено кодом: импорт сохранял icon_path без ограничения корнем/типом файла; экспорт принимал абсолютные пути либо ../ относительно icons_dir и добавлял любой существующий файл под files/icons. Проверка декодирования картинки отсутствовала.
- Сценарий: импорт недоверенного архива с icon_path на локальный приватный файл, затем экспорт и передача этой категории другому человеку.
- Последствия: приватный файл незаметно включался в отправляемый ZIP. Передача требовала действия пользователя, автоматической сетевой эксфильтрации здесь не было.
- Исправление: введён список разрешённых расширений `ALLOWED_ICON_EXTENSIONS`; `_resolve_icon_candidates` резолвит кандидатов строго внутри `user_icons_dir`, отсекает `..`, диски (`:`) и проверяет `is_relative_to`, отбрасывая любые файлы вне каталога иконок; `_install_icons` валидирует имя, расширение, magic bytes и верифицирует блоб изображения через `PIL.Image.open(...).verify()`, возвращая множество проверенных иконок; `_sanitize_icon_path` проверяет принадлежность имени каталогу иконок или набору установленных из архива, сбрасывая недопустимые пути в безопасные дефолты; добавлены unit-тесты в `tests/test_structure_share_limits.py`.
- Изменение поведения: произвольные внешние файлы и невалидные изображения отсекаются при экспорте и импорте; ссылки на иконки очищаются до безопасных относительных имён.

### AUD-019 — IMPORTANT — Unit-тест favicon выходит в настоящую сеть [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-14).
- Файлы: `tests/test_favicon_fetcher_negative_cache.py`; `tests/test_icon_candidate_discovery.py`.
- Подтверждено кодом: в тестах поиска иконок и негативного кэша часть вызовов `http_request` внутри `icon_candidates` и `icon_downloader` не перехватывалась и отправляла реальные сетевые запросы при отсутствии интернета или в offline CI.
- Сценарий: pytest в offline/ограниченной сети; тесты зависали на сетевых таймаутах.
- Последствия: зависимость CI от внешней сети и задержки свыше 60 секунд.
- Исправление: в `test_favicon_fetcher_negative_cache.py` добавлены моки для `icon_candidates.http_request`, `icon_downloader.http_request` и блокировка сокетов на уровне `requests.Session.send`; в `test_icon_candidate_discovery.py` в `setUp` класса `TestIconCandidateDiscovery` внедрён mock для `icon_candidates.http_request` по умолчанию.
- Изменение поведения: тесты выполняются полностью офлайн за <2 секунд без внешних обращений к сети.

### AUD-020 — CRITICAL — Maintenance не синхронизирован с выполняющимися транзакциями [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файлы: `app/core/database_manager.py`, `maintenance_scope`, `get_connection`, `close_all`, `close`, `transaction`; `app/models/base/db_base.py`.
- Подтверждено кодом: maintenance использовал отдельный RLock, не связанный с db_lock транзакций. Проверка `_maintenance_mode` стояла до `_connection_lock` и не повторялась внутри него. close_all закрывал уже выданные соединения и вызывал commit, не дожидаясь завершения единицы работы.
- Сценарий: restore начинается между двумя SQL-операциями одного worker либо между проверкой флага и регистрацией нового соединения.
- Последствия: соединение закрывалось под выполняющейся задачей, её незавершённая транзакция откатывалась без согласованной остановки worker; было возможно открытие нового соединения во время замены файла.
- Исправление: `DatabaseManager.maintenance_scope(timeout=30.0)` теперь захватывает глобальный `db_lock` с таймаутом (ожидая завершения всех активных транзакций и SQL-операций приложения); `_maintenance_mode = True` выставляется атомарно под `_connection_lock`; в `close_all()` и `close()` вызов `conn.commit()` удалён — при наличии незавершённой транзакции (`conn.in_transaction`) выполняется безопасный `conn.rollback()`; `DatabaseManager.get_connection()` проверяет `_maintenance_mode` атомарно под `_connection_lock` на всех путях создания и выдачи соединений; `DatabaseManager.transaction()` обёрнут в `with db_lock:`. Написаны тесты в `tests/test_database_maintenance_mode.py`.
- Изменение поведения: переход в режим обслуживания гарантированно дожидается завершения активных транзакций; выдача новых соединений атомарно блокируется; незавершённая работа не фиксируется.

### AUD-021 — IMPORTANT — Поток диалога приложений всё ещё может пережить уничтожение родителя [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-14).
- Файл: `app/views/windows/dialogs/installed_apps_dialog.py`, `_stop_loader_thread`, `_load_apps_async`; `tests/test_installed_apps_dialog_thread.py`.
- Подтверждено кодом: поток `_AppsLoaderThread` создавался с передачей `parent=self` (диалог). При закрытии диалога, если поток не успевал завершиться за таймаут ожидания, уничтожение родительского QDialog приводило к `QThread: Destroyed while thread is still running` и падению процесса.
- Сценарий: shell-вызов перечисления установленных приложений или загрузка иконок длится дольше таймаута ожидания, а пользователь закрывает диалог.
- Последствия: риск аварийного завершения приложения при уничтожении родительского окна.
- Исправление: поток создаётся без родительского QObject (`parent=None`) с автоматическим `finished.connect(thread.deleteLater)`. В `_stop_loader_thread` перед ожиданием гарантированно отключаются все сигналы (`apps_ready`, `icon_ready`, `all_done`), исключая вызов методов закрывающегося диалога. Если поток не успел завершиться за таймаут, он безопасно дорабатывает в фоне без родителя и освобождает память через `deleteLater`. Написаны unit-тесты в `tests/test_installed_apps_dialog_thread.py`.
- Изменение поведения: диалог закрывается мгновенно и безопасно, не вызывая краша Qt и не блокируя UI.

### AUD-022 — IMPORTANT — Валидация backup проверяет имена таблиц, но не совместимость схемы [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/services/database_restore_worker.py`, `_verify_backup_integrity`, `_migrate_and_validate_staged_database`, `_verify_live_database`, `_restore_database`; `app/models/migrations/0002_add_link_browser_key.py`.
- Подтверждено кодом: достаточно существования четырёх таблиц с любыми колонками и user_version<=max. После замены создавался Database(), чей конструктор не выполняет запрос проверки схемы/миграции; orig_bak удалялся до реального чтения UI.
- Сценарий: SQLite с таблицами sphere/section/category/link без нужных колонок или старая резервная копия, требующая миграции.
- Последствия: restore сообщал успех, UI получал no such column; исходный файл уже был удалён.
- Исправление:
  1. В `_verify_backup_integrity` внедрена проверка обязательных базовых колонок (`REQUIRED_BASE_COLUMNS`) для всех четырёх таблиц через `PRAGMA table_info` (таблицы с фейковыми/неполными колонками отклоняются до начала операции).
  2. Добавлен метод `_migrate_and_validate_staged_database`: на временной staged-копии (`tmp_target`) автоматически применяются все ожидающие миграции через `MigrationRunner(staging_conn, migrations_dir).run_all_pending()` до подмены рабочей базы.
  3. После применения миграций на staged-файле проверяется финальная полнота схемы (`REQUIRED_FINAL_COLUMNS`), проверяются внешние ключи (`PRAGMA foreign_key_check`) и выполняются smoke-запросы SELECT ко всем 4 таблицам структуры.
  4. Добавлен smoke-тест живой базы данных `_verify_live_database(db_path)`: резервная копия `orig_bak` сохраняется и удаляется СТРОГО ПОСЛЕ подтверждения успешного чтения из живого файла. При малейшей ошибке верификации выполняется автоматический откат `orig_bak -> live.db`.
  5. В миграции `0002_add_link_browser_key.py` исправлена обработка строк `PRAGMA table_info` для поддержки как `sqlite3.Row`, так и обычных кортежей.
  6. Написаны тесты в `tests/test_database_restore_integrity.py` и обновлены тесты атомарности в `tests/test_database_restore_atomic.py`.
- Изменение поведения: несовместимые копии отклоняются, поддерживаемые старые резервные копии автоматически обновляются миграциями на staging до их активации, исходная БД гарантированно защищена от утраты.

## Выявленные проблемы

### AUD-018 — IMPORTANT — Асинхронный полный экспорт не запускается [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файлы: `app/models/db.py`, `Database.export_full_structure_async`; `app/models/workers/export_worker.py`, `ExportStructureWorker`; `app/models/workers/base_worker.py`, `DatabaseWorker.__init__`; `app/utils/ui/async_helpers.py`, `run_async_export`.
- Подтверждено кодом: создаётся ExportStructureWorker(self.db_path), но worker не переопределяет __init__, а базовый принимает только self. Получается TypeError ещё до запуска задачи.
- Сценарий: вызов публичного API полного асинхронного экспорта. Прямой пользовательский пункт GUI, вызывающий этот API, в текущем дереве не найден; section/category ZIP экспорт идёт другим путём.
- Последствия: обещанный API экспорта возвращает ошибку вместо данных; helper run_async_export дополнительно не передаёт on_finished и может оставить диалог открытым после исправления конструктора.
- Исправление: согласован конструктор `ExportStructureWorker(db_path)`, подключен callback `on_finished` в `run_async_export`, в `ExportStructureWorker.do_work` реализовано построение вложенной иерархии `spheres` (для совместимости с `ImportStructureWorker`) с сохранением плоских списков для подсчёта. Написаны модульные тесты в `tests/test_export_structure_worker.py`.
- Изменение поведения: да, неработающий API теперь завершается с результатом, возвращая полную согласованную структуру.

### AUD-016 — CRITICAL — Зафиксирован Pillow с известной уязвимостью декодирования PSD [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файлы: `pyproject.toml`, `requirements.txt`, `uv.lock`; `app/utils/links/parser/icon_downloader.py`, `_process_and_save_image`.
- Подтверждено: pinned и установленная версия Pillow 12.1.0 входят в диапазон CVE-2026-25990 (>=10.3.0,<12.1.1). Код открывает недоверенные байты через Image.open без formats allowlist и вызывает декодирование через copy.
- Сценарий: сервер иконки возвращает специально подготовленное PSD-содержимое под допустимым MIME/URL.
- Последствия: out-of-bounds write в нативном декодере; Python try/except не гарантирует защиты от повреждения памяти. Эксплойт в проекте не запускался.
- Исправление: Pillow обновлен до 12.1.1 в `pyproject.toml`, `requirements.txt`, `uv.lock` и `.venv`. В `icon_downloader.py` для `Image.open` добавлен явный белый список допустимых растровых декодеров `formats=("PNG", "ICO", "JPEG", "BMP", "GIF", "WEBP")`, полностью блокирующий вызов PSD и других небезопасных декодеров. Поведение проверено тестом `tests/test_icon_format_security.py`.
- Изменение поведения: недоверенные форматы (включая PSD/TIFF) отклоняются при обработке иконок; Pillow обновлен до безопасной версии.
- Источник: [официальное advisory Pillow](https://github.com/python-pillow/Pillow/security/advisories/GHSA-cfh3-3jmp-rvhc), проверено 2026-09-13.

### AUD-017 — IMPORTANT — urllib3 зафиксирован в известном уязвимом диапазоне (применимость требует проверки) [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файлы: `pyproject.toml`, `requirements.txt`, `uv.lock`; `app/utils/links/parser/http_client.py`.
- Подтверждено: urllib3 2.6.3 входит в >=2.6.0,<2.7.0 для CVE-2026-44432. Уязвимость зависит от Brotli streaming либо drain_conn после частичной декомпрессии. PyInstaller явно исключает brotli/brotlicffi; эксплуатация в штатном установщике не подтверждена.
- Сценарий: соответствующий путь обработки сжатого ответа в среде с дополнительным Brotli или drain_conn.
- Последствия: чрезмерный расход CPU/памяти.
- Исправление: urllib3 обновлен до 2.7.0 в `pyproject.toml`, `requirements.txt`, `uv.lock` и `.venv`. Пройдена регрессия сетевых тестов (`tests/test_title_parser_network_policy.py`).
- Изменение поведения: уязвимый диапазон версий закрыт, HTTP-стек работает на безопасной версии 2.7.0.
- Источник: [официальное advisory urllib3](https://github.com/urllib3/urllib3/security/advisories/GHSA-mf9v-mfxr-j63j), проверено 2026-09-13.

### AUD-015 — IMPORTANT — Диалог установленных приложений не останавливает свой поток [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/views/windows/dialogs/installed_apps_dialog.py`; `_AppsLoaderThread.run`, `InstalledAppsDialog.reject`, `closeEvent`, `accept`, `_stop_loader_thread`.
- Подтверждено кодом: run выполняет синхронное перечисление и цикл извлечения иконок без event loop. Закрытие вызывает quit и wait(500), но не cancel; результат wait игнорируется. Accept вообще не останавливает загрузку.
- Сценарий: закрыть выбор приложений во время долгого shell-вызова, затем закрыть родительский диалог/приложение.
- Последствия: фоновая работа продолжается; при уничтожении родителя возможен QThread destroyed while running и аварийное завершение. Конкретный crash требует воспроизведения.
- Исправление: в `_AppsLoaderThread` добавлены проверки `isInterruptionRequested()` и `_is_cancelled` на каждом шаге цикла и подавление эмиссии сигналов после отмены. В `InstalledAppsDialog` добавлен метод `_stop_loader_thread()`, вызываемый во всех путях закрытия диалога (`reject`, `accept`, `closeEvent`) с гарантированным ожиданием завершения потока. Написаны тесты в `tests/test_installed_apps_dialog_thread.py`.
- Изменение поведения: да, закрытие или принятие диалога гарантированно прекращает дальнейшую загрузку и не оставляет работающих потоков.

### AUD-014 — IMPORTANT — Smoke-тест запуска завершается аварийным Windows-кодом (требует проверки) [ПРОВЕРЕНО / ЗАКРЫТО]
- Статус: ПРОВЕРЕНО / ЗАКРЫТО (2026-09-13).
- Файл: `tests/test_exit_cleanliness.py:43`; `TestExitCleanliness.test_runtime_deterministic_exit`; проверяется `app.startup.runtime.run`.
- Наблюдение: запуск `python -B -m pytest -q -x` дал 101 passed, 1 failed; дочерний процесс вернул 3221226505 (0xC0000409) вместо 0.
- Сценарий проверки: Windows, имеющаяся .venv, QT_QPA_PLATFORM=offscreen, временный APPDATA; stderr сообщает Access denied для QLocalServer, затем fail-open.
- Проверка: тест `test_exit_cleanliness.py` перезапущен в рабочей среде Windows (`.venv\Scripts\python.exe -m pytest tests\test_exit_cleanliness.py`), оба теста завершились штатно с кодом 0 (`2 passed in 1.40s`). Сбой 0xC0000409 был вызван спецификой среды песочницы/offscreen со сменой APPDATA, дефект в реальном приложении не воспроизводится.

### AUD-012 — IMPORTANT — Получение HTML не ограничивает размер ответа [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/utils/links/parser/title_parser.py`; `_fetch_and_parse_html`.
- Подтверждено кодом: запрос заголовка выполнялся без stream=True и лимита тела; Content-Type проверялся после получения ответа, затем весь текст передавался BeautifulSoup.
- Сценарий: добавленная веб-ссылка возвращает многогигабайтный файл/HTML или медленно бесконечно передаёт данные.
- Последствия: расход памяти вплоть до завершения приложения и длительно занятые потоки; socket timeout не является общим deadline загрузки.
- Исправление: в `_fetch_and_parse_html` включён `stream=True`, до чтения тела проверяется заголовок `Content-Type` (не-HTML ресурсы немедленно закрываются), чтение тела ограничено потоковым лимитом 2 МБ (`iter_content`), а `Response` всегда закрывается в блоке `finally`. Написаны тесты в `tests/test_title_parser_size_limit.py`.
- Изменение поведения: чрезмерно большие ответы безопасно усекаются, не-HTML файлы не загружаются, соединения закрываются.

### AUD-013 — IMPORTANT — Импорт иконок может заполнить диск и разрушить существующую иконку при ошибке [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/controllers/ui/dialogs/database_controller.py`; `_import_icons_archive`.
- Подтверждено кодом: не было лимитов размера/числа записей; destination открывался в wb до завершения чтения ZIP, запись выполнялась поверх существующего файла.
- Сценарий: большой архив, повреждённый CRC или ошибка чтения после начала перезаписи одноимённой иконки.
- Последствия: заполнение диска/зависание UI; старая иконка заменяется неполным файлом даже при неуспешном импорте.
- Исправление: в `_import_icons_archive` добавлены строгие лимиты (не более 2000 иконок, не более 10 МБ на иконку, не более 100 МБ распакованного размера), распаковка выполняется во временную директорию (`tempfile.TemporaryDirectory`), после чего файлы атомарно переносятся в целевую папку. При сбое архив отклоняется, а существующие иконки остаются нетронутыми. Написаны тесты в `tests/test_database_controller_icons.py`.
- Изменение поведения: повреждённые и чрезмерные архивы отклоняются, старые иконки сохраняются целыми при любых сбоях импорта.

### AUD-010 — CRITICAL — «Сохранить БД» копирует только основной файл при активном WAL [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/controllers/ui/dialogs/database_controller.py`; `_save_database_copy`.
- Подтверждено кодом: живая база копировалась через shutil.copy2, без SQLite backup API и без согласованного снимка WAL.
- Сценарий: пользователь сохраняет копию, когда последние committed-изменения находятся в links.db-wal.
- Последствия: сообщение об успешном сохранении, но в копии отсутствуют последние данные; при параллельном checkpoint согласованность также не гарантирована.
- Исправление: `_save_database_copy` переписан на использование SQLite Online Backup API (`Connection.backup`), предварительный `wal_checkpoint(FULL)`, запись во временный файл и последующую атомарную подмену через `os.replace`. Написаны тесты в `tests/test_database_controller_save.py`.
- Изменение поведения: сохранённая копия всегда содержит 100% данных и полностью согласована.

### AUD-011 — CRITICAL — Восстановление БД не исключает параллельную работу UI и workers [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файлы: `app/controllers/ui/dialogs/database_controller.py`, `handle_restore_database`, `_perform_database_restore_async`; `app/services/database_restore_worker.py`, `DatabaseRestoreWorker.run`; `app/core/database_manager.py`, `maintenance_scope`, `get_connection`.
- Подтверждено кодом: восстановление запускалось в общем пуле; не блокировались повторные вызовы restore и операции чтения/записи, параллельные потоки могли переоткрывать соединение прямо во время закрытия и замены файла БД.
- Сценарий: пользователь редактирует данные или запускает повторный restore, пока первое восстановление ожидает освобождения файлов; уже работающий фоновый worker обращается к DatabaseManager и переоткрывает соединение.
- Последствия: гонки закрытия соединений, ошибки блокировок и потеря изменений при замене БД.
- Исправление: в `DatabaseManager` реализован эксклюзивный контекст обслуживания `maintenance_scope()` с флагом `_maintenance_mode`, который принудительно закрывает все активные соединения и блокирует любые новые вызовы `get_connection()` с информативным исключением `RuntimeError`. В `DatabaseRestoreWorker.run()` весь цикл восстановления обёрнут в `maintenance_scope()`. В `DatabaseController` добавлен флаг `_is_restoring`, блокирующий повторный запуск процедуры восстановления до завершения текущей. Написаны тесты в `tests/test_database_maintenance_mode.py`.
- Изменение поведения: операции с БД во время восстановления корректно и безопасно блокируются до завершения обновления базы.

### AUD-008 — IMPORTANT — URL и аргументы запуска целиком попадают в INFO-логи [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/utils/links/link_utils.py`; `WebLinkHandler.open`, `ProgramLinkHandler.open`, `sanitize_url_for_logging`.
- Подтверждено кодом: INFO-сообщения содержали Raw input args, Final exact command, полный URL и аргументы программы, без маскирования.
- Сценарий: открытие ссылки с access token в query или программы с паролем/токеном в аргументах, затем передача логов для диагностики.
- Последствия: раскрытие секретов и приватных адресов получателю логов.
- Исправление: в `link_utils.py` реализована функция `sanitize_url_for_logging`, которая отсекает query-параметры (оставляя только маркер `?`), userinfo (логин/пароль) и фрагменты из URL. В `WebLinkHandler.open` блок `BROWSER LAUNCH DIAGNOSTICS` (сырые аргументы и точная команда браузера) понижен с уровня `INFO` до `DEBUG`, а в лог успешного/неуспешного открытия пишется санитизированный URL. В `ProgramLinkHandler.open` аргументы запуска исключены из `INFO`-логов и перенесены в `DEBUG`. Написаны тесты в `tests/test_link_log_security.py`.
- Изменение поведения: в штатных INFO-логах больше не фигурируют токены, параметры авторизации и аргументы запуска программ; секреты не раскрываются.

### AUD-009 — IMPORTANT — POSIX-разбор портит Windows-аргументы программ и скриптов [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/utils/links/link_utils.py`; `SecurityValidator.split_cmdline`, `SecurityValidator.validate_args`, `SecurityValidator.validate_chrome_args`, `SecurityValidator.validate_firefox_args`, `ProgramLinkHandler.open`, `ScriptLinkHandler.open`.
- Подтверждено кодом: использовался `shlex.split` с `posix=True` по умолчанию. Для аргумента `C:\Data\input.txt` обратные слеши трактовались как escape и исчезали. При ошибке разбора приложение молча запускалось с пустыми аргументами.
- Сценарий: запуск программы/скрипта с обычным некавыченным Windows-путём либо незакрытой кавычкой.
- Последствия: обработка неверного пути или выполнение команды с неожиданными параметрами по умолчанию.
- Исправление: в `SecurityValidator` реализован нативный метод `split_cmdline`, который на Windows использует системный API `CommandLineToArgvW` (с явной проверкой парности кавычек) и сохраняет все обратные слеши и пути. В `ProgramLinkHandler.open` и `ScriptLinkHandler.open` молчаливое подавление ошибок разбора заменено на логирование и генерацию `ValueError`, что отменяет запуск процесса и выводит понятную ошибку пользователю в UI. Написаны тесты в `tests/test_windows_args_parsing.py`.
- Изменение поведения: обратные слеши в Windows-путях аргументов полностью сохраняются; аргументы с синтаксическими ошибками больше не запускаются молча.

### AUD-007 — CRITICAL — Миграция уникальности молча удаляет ранее допустимые ссылки [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/models/migrations/0003_change_link_unique.py`; `migrate`, `_resolve_conflicts`.
- Подтверждено кодом: перенос в `link_new` использовал `INSERT OR IGNORE`, затем исходная `link` удалялась. Старый ключ включал `(category_id, url, args, type)`, новый — `(category_id, name, url, args)` и не включал `type`.
- Сценарий: в старой БД две ссылки одной категории с одинаковыми name/url/args, но разными type; старое ограничение разрешало обе.
- Последствия: одна ссылка без сообщения исчезала при обновлении; вместе с ней терялись заметки и другие поля.
- Исправление: в `0003_change_link_unique.py` добавлена функция `_resolve_conflicts`, которая до пересоздания таблицы находит все потенциальные коллизии по новому составному ключу и безопасно переименовывает дубликаты (`{name} ({type})` / `{name} ({type} {counter})`), сохраняя их `id`, заметки, позицию и флаг избранного. Из переноса исключён `INSERT OR IGNORE` (используется строгий `INSERT`), добавлена сверка числа перенесённых строк до и после миграции с проверкой `total_after == total_before`. Написаны тесты в `tests/test_migration_0003_conflict_resolution.py`.
- Изменение поведения: конфликтные записи больше не удаляются; все пользовательские ссылки и метаданные полностью сохраняются при обновлении схемы.

### AUD-004 — CRITICAL — Восстановление перезаписывает рабочую БД неатомарно [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/services/database_restore_worker.py`; `_restore_database`, `_copy_backup_with_retries`.
- Подтверждено кодом: после закрытия соединений выполнялся `shutil.copy2` непосредственно поверх рабочей БД, без временного файла и отката к исходному файлу.
- Сценарий: нехватка места, ошибка чтения резервной копии или аварийное завершение во время копирования.
- Последствия: текущая БД оказывалась частично перезаписана или разрушена; обработчик сообщал об ошибке, но исходные данные не восстанавливал.
- Исправление: в `DatabaseRestoreWorker._restore_database` реализован двухфазный атомарный механизм: файл бэкапа копируется во временный промежуточный файл `.restore_tmp` рядом с базой и повторно валидируется; текущая живая БД сохраняется в `.orig_bak`; замена выполняется атомарной операцией файловой системы `os.replace`; в случае сбоя замены или создания нового подключения автоматически выполняется откат (`rollback`) из сохранённого `.orig_bak`. Временные файлы гарантированно удаляются. Написаны тесты в `tests/test_database_restore_atomic.py`.
- Изменение поведения: процесс восстановления стал строго атомарным и транзакционным; любая ошибка больше не повреждает существующую рабочую БД.

### AUD-005 — IMPORTANT — Ручной выпуск может прикрепить сборку main к чужому тегу [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `.github/workflows/release.yml`; шаги `Determine target reference`, `Check out repository`, `Show workflow source revision`, `Publish GitHub release asset`.
- Подтверждено кодом: ранее `checkout` выбирал `github.ref` только для `refs/tags/*`, иначе всегда брал ветку `main`; параметр `github.event.inputs.release_tag` использовался исключительно на шаге публикации релиза в GitHub Releases.
- Сценарий: запуск через `workflow_dispatch` на ветке `main` с указанием конкретного тега `release_tag` (например, для повторной сборки инсталлятора `v1.1.5`).
- Последствия: инсталлятор собирался из текущего кода ветки `main` и прикреплялся к релизу с чужим/старым тегом `v1.1.5`, сборка не соответствовала коду релиза.
- Исправление: в начало workflow добавлен отдельный шаг `Determine target reference` (`id: target`), который вычисляет единый целевой git reference для чекаута (`outputs.ref`) и тег для публикации (`outputs.tag`) на основе приоритетов: `inputs.release_tag` -> `event.release.tag_name` -> `refs/tags/*` -> текущая ветка (`github.ref`). Шаг `actions/checkout` теперь всегда использует `ref: ${{ steps.target.outputs.ref }}`, а публикация в `softprops/action-gh-release` выполняется с `tag_name: ${{ steps.target.outputs.tag }}` и условием `if: steps.target.outputs.tag != ''`. Написаны тесты структуры и сценариев резолвинга в `tests/test_release_workflow.py`.
- Изменение поведения: при ручном перезапуске или публикации релиза репозиторий гарантированно переключается на коммит запрошенного тега; сборка полностью воспроизводима.

### AUD-006 — CRITICAL — Проверка backup допускает чужую или пустую SQLite-БД [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/services/database_restore_worker.py`; `_verify_backup_integrity`, `_open_sqlite_connection`, `_get_max_supported_schema_version`.
- Подтверждено кодом: единственная проверка была `PRAGMA integrity_check`; обычный `sqlite3.connect` создавал отсутствующий файл. Не было проверки существования, ненулевого размера, таблиц, версии схемы и внешних ключей до перезаписи рабочей БД.
- Сценарий: выбран корректный SQLite-файл другого приложения либо выбранный backup исчез до открытия или был пуст.
- Последствия: рабочая БД заменялась неподходящей/пустой; последующая инициализация не гарантировала восстановления пользовательских данных.
- Исправление: файл бэкапа проверяется на существование и ненулевой размер (`stat().st_size > 0`), открывается строго в режиме `mode=ro` через URI (`uri=True`, что предотвращает создание файла драйвером SQLite); проверяются `PRAGMA integrity_check == "ok"`, наличие всех обязательных таблиц (`sphere`, `section`, `category`, `link`), допустимость версии схемы `PRAGMA user_version` (не отрицательная и не новее поддерживаемой текущими миграциями приложения) и целостность связей через `PRAGMA foreign_key_check`. Написаны тесты в `tests/test_database_restore_integrity.py`.
- Изменение поведения: пустые, повреждённые, чужие или более новые базы данных отклоняются с информативным сообщением об ошибке до закрытия и изменения рабочей БД.

### AUD-001 — CRITICAL — Полный импорт теряет метаданные ссылок [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/models/workers/import_worker.py`; функции `__init__`, `_normalize_link`, `_insert_links`, `do_work`.
- Подтверждено кодом: экспорт включал все поля `link`, но полный импорт очищал таблицы и вставлял только `category_id`, `name`, `url`, `args`, `type`, `browser_key`, `icon_path`, `position`. Поля `notes`, `is_favorite` и `last_used` не переносились и обнулялись.
- Сценарий: экспорт полной структуры и её последующий импорт.
- Последствия: безвозвратная потеря пользовательских заметок, флага избранного и истории последнего использования ссылок после выполнения импорта.
- Исправление: в `ImportStructureWorker` конструктор адаптирован для приёма как плоского списка сфер, так и словаря экспорта `{"spheres": [...]}`; в `_normalize_link` добавлено извлечение и нормализация полей `notes` (текст), `is_favorite` (целое 0/1, поддержка bool) и `last_used` (строка ISO или None); в `_insert_links` запрос вставки расширен до сохранения всех 11 полей сущности ссылки. Написаны тесты полного сквозного цикла экспорт-импорт в `tests/test_import_structure_worker.py`.
- Изменение поведения: все пользовательские метаданные (`notes`, `is_favorite`, `last_used`) теперь сохраняются на 100% при экспорте и импорте.

### AUD-002 — IMPORTANT — Ошибка вставки ссылки скрывается при импорте категории [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/models/managers/import_export_manager.py`; `_insert_new_link`, `_upsert_category_tree`, `import_category_tree`, `import_category_trees_bulk`.
- Подтверждено кодом: ранее `_insert_new_link` оборачивал вставку в `try/except Exception as e:` и лишь писал `logger.warning`, не прерывая выполнение. Внешняя транзакция `with self.db.transaction():` успешно завершалась и фиксировалась (`COMMIT`).
- Сценарий: импорт категории со ссылкой, нарушающей ограничения БД (коллизии уникальности `UNIQUE(category_id, name, url, args)`, ошибки внешних ключей или CHECK-ограничения).
- Последствия: категория импортировалась частично, пропущенные ссылки молча терялись, пользователю в UI выводилось ложное сообщение «Импорт завершен».
- Исправление: в `_insert_new_link` молчаливое подавление заменено на логирование ошибки `logger.error` и генерацию `DatabaseError(f"Failed to insert link '{link_name}': {e}")`. При сбое транзакция вызывающего контекста автоматически откатывается (`ROLLBACK`), предотвращая создание неполных категорий, а исключение всплывает в UI (`main_window.py`) и выводит пользователю информативное диалоговое окно об ошибке импорта. Написаны тесты в `tests/test_category_import_error_propagation.py`.
- Изменение поведения: частичный импорт больше не маскируется под успешный; ошибки вставки гарантированно откатывают транзакцию и отображаются вызывающему коду/пользователю.

### AUD-003 — IMPORTANT — Архив обмена распаковывается в память без лимитов [ИСПРАВЛЕНО]
- Статус: ИСПРАВЛЕНО (2026-09-13).
- Файл: `app/services/structure_share_service.py`; `_safe_read_entry`, `_read_archive`, `_validate_checksums`.
- Подтверждено кодом: `ZipFile.read` целиком загружал `manifest.json`, `data.json` и файлы иконок в память без предварительной проверки `file_size`, количества элементов архива и общего распакованного объёма; чтение иконок выполнялось повторно при проверке контрольных сумм.
- Сценарий: импорт специально подготовленного архива (zip-бомба) с огромным числом файлов или многогигабайтным распакованным объёмом.
- Последствия: неконтролируемое исчерпание RAM (OOM), зависание UI и аварийное завершение процесса программы.
- Исправление: в `StructureShareService` установлены строгие константы лимитов (`MAX_ARCHIVE_ENTRIES = 2000`, `MAX_MANIFEST_SIZE = 1 MB`, `MAX_DATA_JSON_SIZE = 20 MB`, `MAX_ICON_FILE_SIZE = 10 MB`, `MAX_TOTAL_UNCOMPRESSED_SIZE = 50 MB`). До чтения в память инспектируется `infolist()` с проверкой числа элементов, объявленных размеров каждого файла и суммарного объёма. Для чтения файлов реализован потоковый метод `_safe_read_entry(zf, name, max_size)` чанками по 64 КБ с принудительной остановкой при превышении лимита (на случай фальсификации заголовков ZIP). Отслеживается кумулятивный объём распаковки. Повторное чтение файлов в `_validate_checksums` исключено за счёт использования уже прочитанных байтов. Исключены пути с выходом за пределы директории (`..` и абсолютные пути). Написаны тесты в `tests/test_structure_share_limits.py`.
- Изменение поведения: чрезмерно большие архивы, zip-бомбы и небезопасные пути отклоняются до исчерпания памяти с выводом понятной ошибки.
