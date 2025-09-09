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
