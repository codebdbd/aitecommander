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
