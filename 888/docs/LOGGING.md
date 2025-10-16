# Logging guide

This project uses a centralized logging setup with ApplicationLogger and per-module loggers.

- Central setup: `app/startup/logging_setup.py`
- Core logger config: `app/utils/logging/application_logger.py`
- Optional JSON config file: `app/config_data/logging_config.json`

## How levels are chosen

- Default level is provided by the launcher via `setup_logging(log_level)`.
- You can override the level via environment variable `APP_LOG_LEVEL`.
  - Allowed values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

Windows PowerShell example:

```powershell
$env:APP_LOG_LEVEL = 'DEBUG'
python -m app.main
```

## Noisy third‑party loggers

The setup reduces chatter from selected third‑party libraries by setting them to at least `WARNING`:

- `asyncio`
- `urllib3`
- `PIL`

You can change that behavior in `app/startup/logging_setup.py`.

## Where logs are written

- Console (stream) handler is always enabled.
- A rotating file handler is configured by default. Daily log file path is computed in
  `ApplicationLogger` and placed under the user data logs directory configured by `app_config.paths`.

## Per‑module logging

Use a module‑level logger and avoid the root `logging` calls:

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Something happened")
logger.warning("Careful: %s", detail)
```

Exceptions:
- `app/views/base_widgets.py` contains a few `logging.warning/debug` calls intentionally
  kept for test compatibility (unit tests patch `app.views.base_widgets.logging`).

## Customizing with JSON config

You can customize formatting, handlers, and levels via `app/config_data/logging_config.json`.
`ApplicationLogger` looks for a logging config in the following order:

1. `LOGGING_CONFIG_PATH` environment variable (absolute path)
2. Portable config near executable: `config_data/logging_config.json`
3. Project config: `app/config_data/logging_config.json`
4. Built‑in fallback dictConfig

Example snippet for a compact console format:

```jsonc
{
  "version": 1,
  "disable_existing_loggers": false,
  "formatters": {
    "compact": { "format": "%(levelname)s %(name)s:%(lineno)d %(message)s" }
  },
  "handlers": {
    "console": {
      "class": "logging.StreamHandler",
      "level": "INFO",
      "formatter": "compact"
    }
  },
  "loggers": {
    "": {
      "handlers": ["console"],
      "level": "INFO",
      "propagate": false
    }
  }
}
```

To use a custom config without changing the repository:

```powershell
$env:LOGGING_CONFIG_PATH = 'C:\\path\\to\\my_logging.json'
python -m app.main
```

## Tips

- Prefer structured messages with placeholders instead of f-strings for performance:
  `logger.info("User %s logged in", user_id)`
- Avoid logging in hot loops at INFO or DEBUG unless necessary.
- Keep sensitive data out of logs.
