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
