# План полной ликвидации технического долга по Shutdown (без хвостов и мёртвого кода)

> **Дата:** 2026-09-16  
> **Статус:** 🔄 В процессе (Этапы 1–6 ✅ выполнены; Этап 7 запланирован)  
> База:** SHUTDOWN_CODE_REVIEW.md, app/main.py, root main.py, runtime.py, initializer.py, resource_manager.py
> **Цель:** Полностью убрать краш Windows «Прекращена работа программы python.exe» + ликвидировать саму возможность регрессии в будущем за счёт архитектурной централизации.

---

## 🎯 Целевая архитектура (правильная модель)

**Принцип единой точки правды:**
> Кто инициализирует ресурс — тот и отвечает за его cleanup в **том же файле**, в **одном** месте, в **LIFO-порядке**. Никаких «один модуль инициализирует, другой деинициализирует».

### Целевая схема владельцев

| Владелец | Инициализация | Cleanup | Комментарий |
|----------|---------------|---------|-------------|
| `app.main` (точка входа для python) | `CoInitialize()` в [app/main.py:38](file:///d:/01_Codebdbd/01_projects/aitecommander/app/main.py#L38) | ✅ `CoUninitialize()` в том же **finally** `app/main` | ❌ **НЕ** в корневом `main.py`! |
| `app.startup.runtime` | `qInitResources()`, `QApplication`, горячие клавиши в [runtime.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/runtime.py) | ✅ `qCleanupResources()`, WorkerManager.shutdown в том же **finally** runtime.py | |
| `app.startup.initializer` | `Database`, `MainWindow`, `ThemeController` в [initializer.py:527-550](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/initializer.py#L527-L550) | ✅ `cleanup()` через **один** путь `aboutToQuit` | ❌ Удалить дублирующий handler из AppShutdownController |
| `AppShutdownController` | ТОЛЬКО прикладные handlers (snapshot, controllers, backup) в [app_shutdown_controller.py:381-416](file:///d:/01_Codebdbd/01_projects/aitecommander/app/controllers/system/app_shutdown_controller.py#L381-L416) | ✅ Удалить `application_initializer_cleanup` из списка handlers | Не владеет lifecycle initializer |
| `app.utils.links.parser.*` | 4 модуля регистрируют `atexit.register(...)` | ✅ **Только один путь** → явный `shutdown_parser_background_tasks()`. ❌ Удалить все `atexit.register` как дубли | |

---

## 🚀 Этап 1. ЦЕНТРАЛИЗАЦИЯ: переносим COM-инициализацию из корня в `app/main.py` ✅

> **Статус:** ✅ **ВЫПОЛНЕНО** (2026-09-16)  
> **Изменённые файлы:** [main.py](file:///d:/01_Codebdbd/01_projects/aitecommander/main.py), [app/main.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/main.py)

**Решённые проблемы:**
- Корневой `main.py` состоял из 27 строк → теперь **7 строк** (тонкая обёртка). Удалён мёртвый код `CoUninitialize + ExitProcess`, который был обойдён через `sys.exit` из `runtime.py`.
- В `app/main.py:93-109` добавлен **finally-блок с симметричным LIFO-cleanup**:
  1. `atexit._run_exitfuncs()` — явный вызов перед COM-выключением (favicon shelve.close и т.п.)
  2. `pythoncom.CoUninitialize()` — парный вызов для `CoInitialize()` на строках 34-43 того же модуля.
- На строках [app/main.py:111-125](file:///d:/01_Codebdbd/01_projects/aitecommander/app/main.py#L111-L125) централизован **безопасный hard-exit** через `ExitProcess`/`os._exit` (Windows GUI, не-тесты) с защитой от 0xC0000005.

**Проблема сейчас:** COM-инициализация живёт в `app/main.py`, а cleanup — в корневом `main.py`. Это **два разных модуля**, и нет никаких гарантий, что cleanup достигнет корня (что сейчас и происходит).

### 1.1 Ликвидируем всю cleanup-логику из корневого `main.py`

Файл [main.py](file:///d:/01_Codebdbd/01_projects/aitecommander/main.py) должен стать **тонкой обёрткой**, единственная задача которого — вызвать `app.main.main()`. Никакой логики COM, никакого ExitProcess.

**Целевое содержание `main.py`:**
```python
"""Тонкая точка входа для PyInstaller/`python main.py`. Вся бизнес-логика инициализации/cleanup — в app/main."""
import sys
from app.main import main

if __name__ == "__main__":
    # ТОЛЬКО вызов app.main. Никаких if sys.platform == 'win32', никакого CoUninitialize, никакого ExitProcess.
    sys.exit(main())
```

**Результат:** удаляется ~20 строк дублирующего/мёртвого кода с `main.py:13-25`.

---

### 1.2 Создаём **СИММЕТРИЧНЫЙ** cleanup-блок в `app/main.py`

В файле [app/main.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/main.py#L62-L72) функция `main()` сейчас выглядит так:
```python
def main() -> int:
    early_exit_code = _handle_early_cli_exit()
    if early_exit_code is not None:
        return early_exit_code
    from app.core.error_handler import GlobalErrorHandler
    from app.startup.runtime import run
    GlobalErrorHandler.install()
    return run()   # ← run() внутри себя вызвал sys.exit и обошёл cleanup ниже!
```

**Переписываем main() с finally-блоком (LIFO):**

```python
def main() -> int:
    # COM инициализация — САМОЕ ПЕРВОЕ (находилось здесь и раньше, ок)
    sys.coinit_flags = 2  # COINIT_APARTMENTTHREADED
    try:
        import pythoncom
        pythoncom.CoInitialize()
        _com_initialized = True
    except ImportError:
        _com_initialized = False

    exit_code = 0
    try:
        # --- CLI ранний выход (--version / --help) ---
        early_exit_code = _handle_early_cli_exit()
        if early_exit_code is not None:
            return int(early_exit_code)

        # --- Установка глобального обработчика ошибок ---
        from app.core.error_handler import GlobalErrorHandler
        GlobalErrorHandler.install()

        # --- Запуск рантайма. ВАЖНО: run() больше не вызывает sys.exit()! ---
        from app.startup.runtime import run
        exit_code = int(run())

    finally:
        # =============== LIFO Cleanup: COM — ПОСЛЕ ВСЕГО ===============
        # 1) Сначала flush atexit-хендлеров (shelve БД favicon_cache.close и др.)
        try:
            import atexit
            atexit._run_exitfuncs()
        except Exception:
            pass
        # 2) Потому что следующий шаг — CoUninitialize, он должен быть после всех COM-потребителей
        if _com_initialized:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

    # ✅ ТОЛЬКО ПОСЛЕ всех cleanup-операций — безопасный hard-exit (если Windows GUI режим)
    #    Это устраняет случайный порядок деструкторов sip/G C++ объектов.
    import sys, os
    if sys.platform == "win32" and not getattr(sys, "_running_tests", False):
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        try:
            import ctypes
            ctypes.windll.kernel32.ExitProcess(exit_code)
        except Exception:
            os._exit(exit_code)
    return exit_code
```

**Ключевое:**
- `CoInitialize` и `CoUninitialize` теперь **в одном файле** ([app/main.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/main.py)), в одной функции, симметрично.
- Никто другой в проекте **не должен вызывать CoInitialize/CoUninitialize для главного потока (периодические COM-инициализации воркерами в `link_parser.py:71`/`icon_enrichment_service.py:87` — OK, они симметричны в тех же функциях).

---

## 🚀 Этап 2. УСТРАНЯЕМ `sys.exit()` ИЗНУТРИ `runtime.py:finally` ✅

> **Статус:** ✅ **ВЫПОЛНЕНО** (2026-09-16)  
> **Изменённые файлы:** [runtime.py:674-723](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/runtime.py#L674-L723)

**Решённые проблемы:**
- Удалён `sys.exit(int(target_code))` из [runtime.py:719-731](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/runtime.py#L719-L731). Теперь run() всегда возвращает `return int(resolved_exit)` clean way — это гарантирует, что внешний finally-блок `app/main.main()` (где CoUninitialize + ExitProcess) **обязательно сработает**, а не будет обойдён через возбуждение SystemExit внутри finally.
- Удалена хрупкая платформенная вилка `sys.platform != "win32"` вокруг `qCleanupResources()` (было `runtime.py:708-710`). Теперь очистка Qt-ресурсов **симметрична** и всегда выполняется (`runtime.py:707-709`). Обход был костылём против старого краша — теперь устраняемый по-честному централизованным ExitProcess в `app/main.py`.

Это самая опасная анти-паттерн строка в проекте: `sys.exit()` **внутри finally** [runtime.py:731](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/runtime.py#L731). Она обходит **все** внешние finally-блоки на стеке вызовов.

### 2.1 Удаляем sys.exit из runtime

**Было (строки 719-731):
```python
target_code = resolved_exit
if (options.exit_on_finish and mode == GUI and не тест):
    ...flush...
    sys.exit(int(target_code))  # ← УДАЛИТЬ
```

**Стало:**
```python
# Никакого sys.exit внутри run(). Просто возвращаем код:
return int(resolved_exit)
```

### 2.2 Удаляем дублирующую условно-вызванную очистку ресурсов, которая срабатывала «если мы сами себя убиваем»

В [runtime.py:708-710](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/runtime.py#L708-L710) есть условие:
```python
if _resources_initialized and options.exit_on_finish and sys.platform != "win32":
    qCleanupResources()
    _resources_initialized = False
```

**Рефакторим в единый симметричный блок без флагов:**
- `qInitResources()` на старте [runtime.py:626](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/runtime.py#L626)
- `qCleanupResources()` — **всегда и всем** в finally run().

Цель: убрать «вилку» `win32 / not win32`, которая делает разное поведение на разных ОС без необходимости. Причина, по которой там стоит `sys.platform != "win32"`, — это как раз **обход старого краша. Но теперь мы решаем его в `app/main` через `ExitProcess`, так что обход больше не нужен.

---

## 🚀 Этап 3. ОДИН ТРИГГЕР INITIALIZER.CLEANUP — УДАЛЯЕМ ДВОЙНОЙ ВЫЗОВ ✅

> **Статус:** ✅ **ВЫПОЛНЕНО** (2026-09-16)  
> **Изменённые файлы:** [initializer.py:178-187](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/initializer.py#L178-L187), [initializer.py:407](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/initializer.py#L407)

**Результат аудита фактического состояния:** Регистрация handler `application_initializer_cleanup` через `add_shutdown_handler(...)` в **продакшен коде отсутствует** (была удалена раньше, остались только dead-code artefacts). `Lock-флаг _cleanup_done` продолжал быть **primary-mechanism** защиты против фиктивного второго вызова.

**Решённые проблемы:**
- Удалён атрибут `self._shutdown_cleanup_started` (бывший `initializer.py:185`) — использовался **только** в `_cleanup_via_shutdown_controller`.
- Удалён целиком мёртвый метод `_cleanup_via_shutdown_controller` (бывший `initializer.py:407-418`). Референсы на него — только в `tests/test_startup_regression_guards.py` (тесты будут отдельно адаптированы на Этап 7).

**Итог:** Путь `initializer.cleanup()` через `app.aboutToQuit.connect()` [runtime.py:193-209](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/runtime.py#L193-L209) — единственный действующий. Вторичный lock-флаг `_cleanup_done` оставлен как defense-in-depth на случай ручных вызовов cleanup() из embedding-тестов.

Как показал аудит #16, раньше `initializer.cleanup()` вызывался **дважды** — спасал только lock-флаг `_cleanup_done`. Причина дублирования (регистрация handler в AppShutdownController) в текущем коде уже ликвидирована, ликвидированы и residual dead-code артефакты.

### 3.1 Удаляем handler `application_initializer_cleanup` из AppShutdownController

Оставь в AppShutdownController ТОЛЬКО его прикладные handlers:
1. `topbar_snapshot` — [app_shutdown_controller.py:384-390](file:///d:/01_Codebdbd/01_projects/aitecommander/app/controllers/system/app_shutdown_controller.py#L384-L390) ✅ оставляем
2. `controllers_shutdown` — [app_shutdown_controller.py:392-398](file:///d:/01_Codebdbd/01_projects/aitecommander/app/controllers/system/app_shutdown_controller.py#L392-L398) ✅ оставляем
3. `thread_pools_wait` — [app_shutdown_controller.py:400-408](file:///d:/01_Codebdbd/01_projects/aitecommander/app/controllers/system/app_shutdown_controller.py#L400-L408) ✅ оставляем
4. `database_backup` — [app_shutdown_controller.py:410-416](file:///d:/01_Codebdbd/01_projects/aitecommander/app/controllers/system/app_shutdown_controller.py#L410-L416) ✅ оставляем
5. ❌ **УДАЛИТЬ**: `application_initializer_cleanup`, регистрируемый где-то в initializer

Найди и удали:
```python
# В initializer.py:503-509 или рядом — КУСОК ДЛЯ УДАЛЕНИЯ:
shutdown_ctrl.add_shutdown_handler(
    "application_initializer_cleanup",
    self._cleanup_via_shutdown_controller,
    ShutdownPriority.LOW,
)
```

### 3.2 Оставляем **единственный** путь: `app.aboutToQuit`

Путь через [runtime.py:193-209](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/runtime.py#L193-L209) с `about_to_quit.connect(initializer.cleanup)` — идиоматичный для Qt, правильный по времени срабатывания. Lock-флаг `_cleanup_done` можешь оставить как **second-layer defense**, но он перестаёт быть основным механизмом (превращается в assertion на случай багов в будущем).

---

## 🚀 Этап 4. УДАЛЯЕМ ДУБЛИРУЮЩИЕ `atexit.register` В PARSER-МОДУЛЯХ (Audit #17, #22) ✅

> **Статус:** ✅ **ВЫПОЛНЕНО** (2026-09-16)  
> **Изменённые файлы:** [app/main.py:94-105](file:///d:/01_Codebdbd/01_projects/aitecommander/app/main.py#L94-L105), [icon_candidates.py:10-20](file:///d:/01_Codebdbd/01_projects/aitecommander/app/utils/links/parser/icon_candidates.py#L10-L20)

**Решённые проблемы:**
- `atexit.register(...)` полностью устранены из всех 4 модулей парсера (`icon_downloader`, `icon_candidates`, `http_client`, `favicon_cache`).
- Все ресурсы парсера (пулы потоков, cloudscraper, sessions, shelve БД `FaviconCache`) детерминированно и явно останавливаются через `shutdown_parser_background_tasks(wait=True, cancel_futures=True)`, вызываемый из `runtime.py:681`.
- Из `app/main.py` удалён хак принудительного сброса `atexit._run_exitfuncs()`, который запускался перед деинициализацией COM.
- Обновлена устаревшая документация в `icon_candidates.py`.

---

## 🚀 Этап 5. РЕМОНТ ResourceManager: `deleteLater` → реальный destroy на shutdown-фазе ✅

> **Статус:** ✅ **ВЫПОЛНЕНО** (2026-09-16)  
> **Изменённые файлы:** [resource_manager.py:117-155](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/common/resource_manager.py#L117-L155)

**Решённые проблемы:**
- В `ResourceManager._auto_detect_cleanup` добавлена проверка состояния жизненного цикла Qt-приложения (`QCoreApplication.instance() is None or app.closingDown()`).
- В фазе закрытия (когда event loop остановлен и `deleteLater()` становится no-op/dead-code) возвращается функция немедленного освобождения `_forced_destroy`, вызывающая `r.destroy(destroyWindows=True, destroySubWindows=True)` и `sip.delete(r)`.
- В обычном режиме работы приложения при активном event loop сохранён вызов `resource.deleteLater`.

В [resource_manager.py:117-135](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/common/resource_manager.py#L117-L135):

**Цель:** Удалить «хрупкую» зависимость от event-loop при очистке top-level QMainWindow/QWidget в shutdown-фазе.

```python
def _auto_detect_cleanup(self, resource: Any) -> Callable[[], None] | None:
    from PyQt6.QtCore import QCoreApplication

    # 1) Таймеры -> stop() — это всегда ок
    if hasattr(resource, "stop") and callable(resource.stop):
        return resource.stop

    # 2) QObjects/QWidgets — учитываем фазу жизненного цикла
    if hasattr(resource, "deleteLater") and callable(resource.deleteLater):
        app = QCoreApplication.instance()
        if app is None or app.closingDown():
            # ✅ Event loop остановлен или останавливается.
            # deleteLater() — dead code. Реальная очистка через destroy + sip.delete
            from PyQt6 import sip

            def _forced_destroy(r=resource):
                try:
                    if hasattr(r, "destroy") and callable(r.destroy):
                        r.destroy(destroyWindows=True, destroySubWindows=True)
                except Exception:
                    pass
                try:
                    if not sip.isdeleted(r):
                        sip.delete(r)
                except Exception:
                    pass
            return _forced_destroy
        else:
            # ✅ Нормальная работа приложения: event-loop жив — deleteLater идеален
            return resource.deleteLater

    # 3) Файлоподобные/DB соединения -> close()
    if hasattr(resource, "close") and callable(resource.close):
        return resource.close

    return None
```

---

## 🚀 Этап 6. УДАЛЯЕМ МЁРТВЫЙ КОД (список конкретных мест) ✅

> **Статус:** ✅ **ВЫПОЛНЕНО** (2026-09-16)  
> **Изменённые файлы:** [main.py](file:///d:/01_Codebdbd/01_projects/aitecommander/main.py), [runtime.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/runtime.py), [app/main.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/main.py), [initializer.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/initializer.py), [db.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/models/db.py)

Все 7 выявленных позиций мёртвого/дублирующего кода полностью ликвидированы:

| № | Удаляемый код | Файл | Статус |
|---|---------------|------|--------|
| 1 | `if sys.platform == "win32": try CoUninitialize + ExitProcess/os._exit` | [main.py:13-25](file:///d:/01_Codebdbd/01_projects/aitecommander/main.py#L13-L25) | ✅ Удалён (переехал в `app/main.py`) |
| 2 | Блок `if _resources_initialized and options.exit_on_finish and sys.platform != "win32"` и его содержимое | [runtime.py:708-710](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/runtime.py#L708-L710) | ✅ Удалён (симметричный LIFO cleanup) |
| 3 | Весь блок `if options.exit_on_finish and mode==GUI and not tests` + `sys.exit(...)` внутри | [runtime.py:719-731](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/runtime.py#L719-L731) | ✅ Удалён (run() возвращает int) |
| 4 | 4 строки с `atexit.register(...)` | icon_downloader, icon_candidates, http_client, favicon_cache | ✅ Удалены (единый `shutdown_parser_background_tasks`) |
| 5 | `atexit._run_exitfuncs()` хак из `app/main.py finally` | [app/main.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/main.py) | ✅ Удалён |
| 6 | Метод `_cleanup_via_shutdown_controller` + handler-регистрация | [initializer.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/startup/initializer.py) | ✅ Удалён |
| 7 | Удалить дублирующий `DatabaseManager.close_all` в cleanup | [db.py:728](file:///d:/01_Codebdbd/01_projects/aitecommander/app/models/db.py#L728) | ✅ Удалён (централизован в `runtime.py:700`) |

---

## 🚀 Этап 7. VERIFICATION GUARD-RAILS (не доверяй себе)

### 7.1 Добавляем 2 санити-интеграционных теста

**Тест A: `test_single_initializer_cleanup_trigger.py**
```python
"""Архитектурный тест: initializer.cleanup вызывается ровно 1 раз (не 2, не 0)"""
from unittest.mock import patch, MagicMock

def test_cleanup_called_once_after_app_quit(qt_app):
    # Запускаем минимальный app lifecycle с мок-окном
    # Проверяем, что cleanup вызвался ровно ОДИН раз
    ...
```

**Тест B: `test_com_symmetry.py`**
```python
"""Архитектурный тест: CoInitialize и CoUninitialize — парный вызов в одном модуле app/main, не разбросаны"""
import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
app_main_src = (APP_ROOT / "app" / "main.py").read_text(encoding="utf-8")
root_main_src = (APP_ROOT / "main.py").read_text(encoding="utf-8")

def test_no_com_logic_in_root_main():
    """У нас ТОЧНО нет CoUninitialize/ExitProcess в корне main.py (мертвый код удален)"""
    assert "CoUninitialize" not in root_main_src
    assert "ExitProcess" not in root_main_src

def test_com_lifecycle_in_app_main():
    """CoInitialize/CoUninitialize живут вместе в app/main.py"""
    assert "CoInitialize" in app_main_src
    assert "CoUninitialize" in app_main_src
```

### 7.2 Обновляем `SHUTDOWN_CODE_REVIEW.md`

Все пункты, которые устранены по факту — ставь пометку **✅ УСТРАНЕНО** со ссылкой на изменённые файлы. В будущем это предотвратит возврат старых анти-паттернов.

---

## 📊 Итоговые метрики чистоты (KPI после всех этапов):

| Показатель | До | После |
|------------|-----|-------|
| Точек `CoUninitialize` в проекте для главного потока | 2 (одна dead code) | **1** (в том же блоке где `CoInitialize`) |
| Точек `sys.exit` / hard-exit | 3 места | **1** (центрально в app/main после всех cleanup) |
| Путей вызова `initializer.cleanup` | 2 + lock-защита | **1** (`aboutToQuit`) |
| Путей shutdown parser pools | 2 (1 dead) | **1** (явный вызов функции) |
| Мёртвых строк кода ~ | ~80 | **0** |

---

## ✅ Как понять, что работа сделана до конца (чек-лист):

- [ ] `grep -r "CoUninitialize" --include="*.py"` показывает ТОЛЬКО `app/main.py` + локальные COM-воркеры (link_parser.py и т.п.)
- [ ] `grep -r "sys.exit" --include="*.py"` кроме тестов и argparse-handlers находит ТОЛЬКО `app/main.py` + `main.py` (тонкая обёртка)
- [ ] `grep -r "atexit.register" --include="*.py"` выдаёт 0 совпадений в `app/utils/links/parser/`
- [ ] `main.py` в корне проекта ≤ 7 строк (только импорт + вызов `app.main`)
- [ ] Запуск приложения → закрытие → повторить 10 раз → 0 крашей Windows
- [ ] Код возврата `echo %ERRORLEVEL%` → ровно 0, не -1073741819 (0xC0000005)
- [ ] Все существующие тесты проходят (`pytest tests/`) без падений

**В результате:**
- ❌ Никакого мёртвого кода в корне `main.py`
- ❌ Никаких lock-флагов, маскирующих двойной вызов (флаги остаются как defense, но не как primary-mechanism)
- ❌ Никаких дублирующих atexit + явный shutdown конкурирующих путей
- ✅ LIFO-симметрия Init/Shutdown в каждом файле-владельце
- ✅ Краш Windows Access Violation — устранён по-честному (не обход через условные платформенные костыли)
