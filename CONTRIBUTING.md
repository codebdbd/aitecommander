# Участие в разработке Aite Commander

Руководство для контрибьюторов. Описывает процесс Fork→Branch→PR, стандарты кода и требования к коммитам.

## Быстрый старт

```bash
# 1. Fork репозитория на GitHub

# 2. Клонирование вашего форка
git clone https://github.com/<ваш-логин>/aitecommander.git
cd aitecommander

# 3. Создание ветки
git checkout -b fix/описание-проблемы

# 4. Установка окружения
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
pre-commit install

# 5. Разработка, тесты, коммит
pytest
git add .
git commit -m "fix(dnd): описание"
git push origin fix/описание-проблемы

# 6. Pull Request на GitHub
```

---

## Ветвление

| Ветка | Назначение |
|-------|-----------|
| `main` | Стабильный релиз. PR мержатся через squash merge. |
| `fix/*` | Исправления багов |
| `feat/*` | Новые функции |
| `refactor/*` | Рефакторинг без изменения поведения |
| `docs/*` | Обновление документации |

---

## Коммиты

Проект использует [Conventional Commits](https://www.conventionalcommits.org/) для последних коммитов. Это предпочтительный стиль, но не строгое требование.

### Формат

```
<type>(<scope>): <описание>
```

### Типы

| Тип | Описание | Пример |
|-----|----------|--------|
| `fix` | Исправление бага | `fix(dnd): block tree signals on undo` |
| `feat` | Новая функция | `feat(share): add Viber sharing` |
| `refactor` | Рефакторинг | `refactor(undo): extract MacroCommand` |
| `docs` | Документация | `docs: add localization guide` |
| `i18n` | Локализация | `i18n: add missing Russian translations` |
| `test` | Тесты | `test(db): cover close_all edge case` |
| `style` | Форматирование (без изменения логики) | `style: ruff format` |

### Scopes (области)

Используются в реальных коммитах проекта:

| Scope | Пример |
|-------|--------|
| `dnd` | Drag & Drop операции |
| `i18n` | Переводы |

> Использование scope не ограничено — добавляйте по необходимости.

### Примеры

```bash
git commit -m "fix(dnd): use ClearAndSelect to prevent selecting all categories on undo"
git commit -m "refactor(dnd): extract duplicated focus restoration into shared method"
git commit -m "docs: add localization guide for developers"
git commit -m "i18n: add missing translations for Invalid link data strings"
```

---

## Код-стайл

### Инструменты

| Инструмент | Назначение | Запуск |
|------------|-----------|--------|
| **Ruff** | Линтинг + форматирование | `ruff check app/` / `ruff format app/` |
| **Mypy** | Проверка типов | `mypy app/` |
| **pre-commit** | Автоматизация перед коммитом | `pre-commit run --all-files` |

Pre-commit хуки настроены в `.pre-commit-config.yaml`:
- `ruff --fix` — автоматическое исправление
- `ruff-format` — форматирование
- `mypy` — проверка типов
- `end-of-file-fixer` — перевод строки в конце файла
- `trailing-whitespace` — удаление завершающих пробелов

### Именование

| Элемент | Стиль | Пример |
|---------|-------|--------|
| Модули, функции, переменные | `snake_case` | `load_bookmarks()` |
| Классы | `PascalCase` | `MainWindow` |
| Константы | `UPPER_SNAKE_CASE` | `APP_NAME` |
| Методы Qt API | `camelCase` | `setWindowTitle()` |
| Сигналы PyQt | `camelCase` | `itemClicked` |
| Приватные атрибуты | `_leading_underscore` | `_db_connection` |
| Протоколы | `PascalCase` + `Like`/`Supports` | `MainWindowLike` |

### Требования к коду

1. **Типизация** — все функции и методы должны иметь аннотации типов:
   ```python
   def get_theme(self, theme_id: str) -> ThemeDefinition | None:
       ...
   ```

2. **Протоколы** — используйте `Protocol` для контрактов между модулями (см. `app/interfaces.py`).

3. **Нет Qt UI в бизнес-моделях** — `app/models/` не импортирует PyQt6. Модели представлений (`app/views/models/`) могут импортировать PyQt6.

4. **Сигналы вместо колбэков** — компоненты взаимодействуют через `pyqtSignal`, не через прямые вызовы.

5. **Документирование** — docstring только когда WHY неочевиден. Не дублируйте что делает код.

---

## Тестирование

### Запуск

```bash
# Все тесты
pytest

# С подробным выводом
pytest -v

# Конкретный файл
pytest tests/test_database_manager_close.py

# С покрытием
pytest --cov=app --cov-report=html
```

### Стили тестов

Проект использует оба стиля:

**pytest-функции** (предпочтительно для новых тестов):
```python
from __future__ import annotations

import sqlite3
import threading

from app.core.database_manager import DatabaseManager


def test_close_ignores_already_closed_connection() -> None:
    conn = sqlite3.connect(":memory:")
    thread_id = threading.get_ident()
    DatabaseManager._thread_local.conn = conn
    DatabaseManager._thread_local.last_used = 0
    DatabaseManager._active_connections[thread_id] = conn

    conn.close()
    DatabaseManager.close()

    assert not hasattr(DatabaseManager._thread_local, "conn")
```

**unittest.TestCase** (для тестов с QApplication):
```python
from __future__ import annotations

import unittest

from PyQt6.QtWidgets import QApplication, QComboBox

from app.utils.ui.qt.combo_helpers import select_combo_data


class TestComboHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_select_combo_data_prefers_current(self) -> None:
        combo = QComboBox()
        combo.addItem("Dark", "dark")
        combo.addItem("Light", "light")

        index = select_combo_data(
            combo,
            current_data="light",
            preferred_data="dark",
            fallback_to_first=False,
        )

        self.assertEqual(1, index)
```

### Тесты миграций

Миграции тестируются с использованием `MigrationRunner` и временных директорий:
```python
from pathlib import Path
from app.utils.db.migrations import MigrationRunner


def test_migrations_apply() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    runner = MigrationRunner(conn, Path("app/models/migrations"))

    applied = runner.run_all_pending()
    assert applied == 6
```

### Требования

- **Минимальное покрытие**: новые функции должны иметь тесты.
- **Тесты БД**: используют `:memory:` SQLite или временные файлы в `tests/.tmp_pytest/`.
- **Запускайте тесты перед коммитом**.

---

## Pull Request

### Чек-лист перед отправкой

- [ ] Код форматирован (`ruff format app/`)
- [ ] Нет ошибок линтинга (`ruff check app/`)
- [ ] Тесты проходят (`pytest`)
- [ ] Типы корректны (`mypy app/`)
- [ ] Есть тесты для нового кода
- [ ] Не забыл обновить документацию (если нужно)

### Описание PR

```markdown
## Что изменено
- fix(dnd): block tree signals when setting selection after link move

## Как тестировал
- pytest tests/test_dnd_move_commands.py -v
- Вручную: переместил категорию → Ctrl+Z → фокус вернулся
```

### Процесс

1. Отправьте PR из ветки `fix/*` / `feat/*` в `main`.
2. CI запустит тесты и линтинг.
3. После ревью — squash merge в `main`.
4. Ветка удаляется после мержа.

---

## Миграции базы данных

Миграции находятся в `app/models/migrations/`. Каждая миграция — Python-файл с функцией `migrate`:

```python
# app/models/migrations/0007_add_bookmark_type.py
import sqlite3
from typing import Any


def migrate(conn: sqlite3.Connection, logger: Any) -> None:
    cols = conn.execute("PRAGMA table_info('link')").fetchall()
    names = {dict(r)["name"] for r in cols}
    if "bookmark_type" in names:
        logger.debug("Migration 0007: bookmark_type already exists — skipping")
        return
    conn.execute("ALTER TABLE link ADD COLUMN bookmark_type TEXT DEFAULT NULL")
    logger.info("Migration 0007: added bookmark_type column to link")
```

### Правила

- Имя файла: `NNNN_описание.py` или `NNNN_описание.sql`
- SQL-миграции: `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX`
- Python-миграции: функция `migrate(conn, logger)` для сложной логики
- **Всегда проверяйте** существует ли уже колонка/таблица перед изменением
- Миграции запускаются автоматически при старте приложения через `MigrationRunner`
- Номер миграции = `PRAGMA user_version`

---

## Добавление новой функции

### Пример: новый тип ссылки

1. Добавить значение в `app/models/types/link_type.py`:
   ```python
   class LinkType(Enum):
       WEB = "web"
       FILE = "file"
       FOLDER = "folder"
       PROGRAM = "program"
       SCRIPT = "script"
       BOOKMARK = "bookmark"  # новый
   ```

2. Обновить CHECK-ограничение в `app/models/schema.sql`:
   ```sql
   type TEXT NOT NULL CHECK(type IN ('web','file','program','script','folder','bookmark'))
   ```

3. Добавить миграцию `app/models/migrations/0007_add_bookmark_type.py` (если нужна миграция данных).

4. Обновить UI: диалоги (`app/views/windows/dialogs/`), иконки, дефолтные значения.

5. Написать тесты в `tests/`.

6. Обновить `CAPABILITIES.md` если это пользовательская функция.

---

## Контакты

- Issues: https://github.com/codebdbd/aitecommander/issues
- Repository: https://github.com/codebdbd/aitecommander
