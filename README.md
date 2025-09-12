# Project Overview

This repository contains the application source code and tests. See `docs/` for additional guides.

## Table of Contents

1. [Project structure](#project-structure)
2. [Logging](#logging)
3. [Development](#development)
4. [How to run](#how-to-run)

## Project structure

Key directories and files:

- `app/`
  - `startup/`
    - `argument_parser.py` — CLI args parsing (e.g., log level)
    - `logging_setup.py` — centralized logging bootstrap
    - `app_factory.py` — creates and configures `QApplication`
    - `browser_profiles_loader.py` — lazy load of browser profiles
  - `controllers/`
    - `system/` — system controllers (bootstrap, DB init, etc.)
    - `ui/` — UI controllers (dialogs, actions)
  - `views/` — Qt widgets, components, dialogs
  - `models/` — data models and domain logic
  - `services/` — app services and helpers
  - `config_data/` — app configuration and defaults (incl. `logging_config.json`)

- `tests/` — unit tests
- `docs/` — guides and docs (see `docs/LOGGING.md`)

## Logging

For details on how logging is configured and how to control log levels and formats, see:

- `docs/LOGGING.md`

Quick start (Windows PowerShell):

```powershell
# Set DEBUG level for this session
$env:APP_LOG_LEVEL = 'DEBUG'
python -m app.main
```

To provide a custom logging JSON config without changing the repo:

```powershell
$env:LOGGING_CONFIG_PATH = 'C:\\path\\to\\my_logging.json'
python -m app.main
```

## Development

- Run tests: `pytest -q`
- Lint & format: `ruff check . --fix` and `ruff format .`

## How to run

Run the application in development mode:

```powershell
python -m app.main --log-level INFO
```

## Architecture contracts (DI and Transactions)

- Dependency Injection (DI):
  - Wiring выполняется централизованно в `app/controllers/system/window_controllers_setup.py`.
  - Критичные зависимости валидируются явными проверками; ошибки конфигурации поднимаются как `SetupError`.
  - Не используйте "магические" `getattr` в прод-пути; предпочтительнее явные проверки `hasattr` и явная передача зависимостей.

- Transactions (SQLite):
  - Все операции записи должны выполняться через внешний транзакционный контекст `DatabaseBase.transaction()` или `UnitOfWork` (`app/services/uow.py`).
  - Модели не выполняют `commit()` внутрь методов. Транзакции контролируются вызывающей стороной.
  - Потокобезопасность обеспечивается глобальной блокировкой `db_lock` и `thread_local` соединениями; рекомендовано избегать параллельных write-операций.
  - Для массовых апсертов ссылок используется `_upsert_links_no_tx` с поштучными INSERT без временных таблиц (зафиксировано тестами).

## Static analysis

- Ruff: расширенные правила (flake8-bugbear, mccabe, pyupgrade). Конфиг: `ruff.toml`.
- Mypy: строгие правила включены для ключевых модулей. Конфиг: `mypy.ini`.

Запуск проверок:

```powershell
ruff check . --fix
ruff format .
mypy
```

## Pre-commit hooks

Файл конфигурации: `.pre-commit-config.yaml`.

Установка и запуск:

```powershell
pip install pre-commit ruff mypy
pre-commit install
pre-commit run --all-files
