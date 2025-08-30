# Руководство по логированию в проекте

Цель: единообразное, поддерживаемое логирование во всём проекте PyQt6.

## Базовые принципы
- Используем модульный логгер в утилитарных и инфраструктурных модулях:
  - В начале файла: `logger = logging.getLogger(__name__)`
  - В коде: `logger.debug/info/warning/error(...)`
- В бизнес-слое допускается DI-логгер (`self.logger`) для тестируемости и контекстуализации.
- Запрещены `print()` в рабочем коде.

## Где какой подход применять
- Инфраструктура/утилиты (пример: `app/utils/*`, `app/controllers/structure_modules/*`, модели):
  - Модульный логгер — по умолчанию.
  - Если класс принимает логгер извне — параметр опционален, с fallback на модульный (`logger or logging.getLogger(__name__)`).
- Бизнес-слой (пример: `app/controllers/business/*`):
  - DI-логгер через конструктор, хранить как `self.logger`.

## Примеры

### Модульный логгер (утилиты/инфраструктура)
```python
import logging

logger = logging.getLogger(__name__)

def do_work(x: int) -> int:
    logger.debug("Starting work", extra={"x": x})
    try:
        return x + 1
    except Exception as e:
        logger.error(f"Failed: {e}")
        raise
```

### Класс с опциональным DI-логгером
```python
import logging

logger = logging.getLogger(__name__)

class Foo:
    def __init__(self, logger_obj: logging.Logger | None = None):
        self.logger = logger_obj or logger
```

### Бизнес-слой (жёсткий DI)
```python
class BarService:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
```

## Типичные замены
- Было: `self._logger.info(...)` или `logging.getLogger(__name__).info(...)`
- Стало: `logger.info(...)` (при наличии module-level) либо `self.logger.info(...)` (в DI-классах)
- `print(...)` → `logger.debug/info/warning/error(...)`

## Уровни логирования (рекомендации)
- debug: подробности выполнения, частые сообщения, результаты промежуточных шагов
- info: старт/финиш операций, ключевые пользовательские события
- warning: восстановимые проблемы, неверные входные данные
- error: ошибки, приводящие к деградации функционала или прерыванию операции

## Антипаттерны
- Вызовы `logging.getLogger(__name__).<method>(...)` внутри функций/методов — используйте `logger`.
- Локальные логгеры на инстансах в утилитах (`self.logger = logging.getLogger(__name__)`) — заменять на module-level.
- `print()` в продакшн-коде.

## Миграция существующего кода
1. Вверху файла добавьте:
   ```python
   import logging
   logger = logging.getLogger(__name__)
   ```
2. Замените локальные логгеры и inline-вызовы на `logger.*`.
3. Для классов с параметром `logger` сделайте его опциональным: `logger or logging.getLogger(__name__)`.
4. Удалите `print()`.
5. Прогоните линтеры: `ruff check app --fix` и `ruff format`.

## Инструменты
- Ruff:
  - Проверка: `ruff check app`
  - Автофикс: `ruff check app --fix`
  - Форматирование: `ruff format`

## Примечания
- Учитывайте совместимость: где нужно — оставляйте DI-подписи конструкторов, но добавляйте fallback на модульный логгер.
- Логгер должен импортироваться и объявляться вверху файла.

---

## Транзакции БД и использование db_lock

- Используйте контекст-менеджер транзакции `DatabaseBase.transaction()` для атомарных операций записи.
- Глобальная блокировка `db_lock` теперь удерживается на протяжении ВСЕГО блока транзакции (между `BEGIN` и `COMMIT/ROLLBACK`). Это гарантирует эксклюзивный доступ к SQLite в рамках транзакции и исключает вмешательство других потоков.
- `db_lock` — реентерабельный (`RLock`), поэтому вызовы, которые внутри транзакции также используют `db_lock` (например, `_execute_with_error_handling`, прямые `SELECT/UPDATE`), безопасны и не приводят к дедлокам.
- Не создавайте вложенных транзакций на уровне SQLite внутри `transaction()` (повторные `BEGIN`). При необходимости используйте один общий блок транзакции и/или `SAVEPOINT`.
- Операции, связанные с массовым обновлением позиций или импортом, должны выполняться либо под `transaction()`, либо явно под `with db_lock:` для консистентности.

---

## Регистронезависимая уникальность (NOCASE)

- В БД добавлены уникальные индексы с `COLLATE NOCASE` для согласованности с логикой интерфейса и сервисов:
  - `sphere(name)` → индекс `idx_sphere_name_nocase`.
  - `section(sphere_id, name)` → индекс `idx_section_sphere_name_nocase`.
  - `category(section_id, name)` → индекс `idx_category_section_name_nocase`.
- Это предотвращает одновременное существование записей вроде `"Brand"` и `"brand"` в одной области.
- Если индексы не создаются (из-за уже существующих дублей по регистру), используйте CLI ниже для детекта/устранения и повторного создания индексов.

## CLI для диагностики и обслуживания БД

Запускать из корня проекта:

```bash
python -m app.models.db --detect-duplicates [--json] [--db-path PATH]
python -m app.models.db --resolve-duplicates rename|remove [--json] [--create-indexes-after] [--db-path PATH]
python -m app.models.db --create-indexes [--db-path PATH]
python -m app.models.db --backup [--db-path PATH]
```

- `--detect-duplicates` — показывает группы регистронезависимых дублей в `sphere/section/category`.
- `--resolve-duplicates rename` — оставляет запись с минимальным id, остальные переименовывает: `name -> "name (#{id})"`.
- `--resolve-duplicates remove` — оставляет запись с минимальным id, остальные удаляет.
- `--create-indexes-after` — после `resolve` сразу создаёт NOCASE-индексы.
- `--json` — вывод в JSON, удобно для логов/CI.
- `--db-path` — путь к пользовательской БД. По умолчанию берётся из конфигурации приложения.

Рекомендуемая безопасная последовательность:

```bash
python -m app.models.db --backup
python -m app.models.db --detect-duplicates
# Если есть группы дублей, выбрать стратегию (обычно "rename")
python -m app.models.db --resolve-duplicates rename --create-indexes-after
python -m app.models.db --detect-duplicates
```

## Миграции и поведение при дублях

- При инициализации/миграции (`Database.initialize_or_migrate()`):
  - Добавляется поле `link.browser_key` (если отсутствует).
  - Изменяется уникальность `link` на `UNIQUE(category_id,name,url,args)`.
  - Создаются NOCASE-индексы для `sphere/section/category`.
- Если при создании NOCASE-индексов возникает ошибка (из-за дублей), в лог пишется предупреждение. Затем используйте CLI для устранения дублей и вызовите `--create-indexes`.

## Восстановление и импорт/экспорт

- Резервные копии: `python -m app.models.db --backup` создаёт консистентную копию через `sqlite3.Connection.backup`.
- Экспорт/импорт структуры для разделов/категорий: методы `Database.export_section_tree()`, `Database.import_section_tree()`, `Database.export_category_tree()`, `Database.import_category_tree()`.
- Массовый импорт категорий: `Database.import_category_trees_bulk()` выполняет апсерт в одной транзакции, сохраняет ID/позиции, толерантен к уникальности ссылок.

## Порядок при массовом перемещении категорий

- `CategoryModel.move_categories_to_section_bulk()` сохраняет входной порядок `category_ids`. Позиции в целевом разделе назначаются последовательно, начиная с базовой позиции, строго по порядку ввода.

## Отладка и тесты

- Запуск тестов: `pytest -q`.
- Добавляйте тесты на:
  - NOCASE-уникальность в `sphere/section/category` (вставки `"Brand"`/`"brand"` должны конфликтовать).
  - Сохранение порядка в `move_categories_to_section_bulk()`.

---

## Единый API кэширования

Стандартизирован единый интерфейс для кэшей. Используйте только указанные функции/классы.

- Иконки (`app/utils/ui/icon/cache_manager.py`):
  - `get_icon(name, theme) -> QIcon | None`
  - `set_icon(name, theme, icon: QIcon | None, *, negative: bool = False) -> None`
  - `get_path(name, theme) -> str | None`
  - `set_path(name, theme, path: str | None) -> None`
  - Админ/метрики: `clear_icon_cache()`, `get_icon_cache_stats()`, `reset_icon_cache_stats()`, `log_icon_cache_stats()`
  - Негативный кэш: см. `app/utils/ui/icon/negative_cache.py`
  - Примечание: устаревшие алиасы удалены — `get_qicon_from_cache`, `cache_qicon`, `get_path_from_cache`, `cache_path`.

- Структура (`app/controllers/structure_modules/cache_manager.py`):
  - Класс `CacheManager(ttl: float | None = None, max_size: int | None = None)`
  - `get(key)`, `set(key, value, *, ttl: float | None = None)`
  - `invalidate(key: str | None = None)`, `clear_all()`
  - Спец-кэш: `get_first_category_id()`, `set_first_category_id(id)`, `invalidate_first_category_cache()`

Общие правила:
- TTL в секундах; значения `<= 0` — запись невалидна.
- LRU-вытеснение действует при превышении `max_size`.
- Для тестов допускается переопределение конфигурации через ленивый прокси `app_config` (поддерживает `__setattr__/__delattr__`).
