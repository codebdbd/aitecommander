# app/utils/logging/application_logger.py

import json
import logging
import logging.config
import os
import sys
from datetime import datetime
from pathlib import Path

from app.config_data import app_config


class ApplicationLogger:
    """Centralized application logging system."""

    def __init__(self, log_level=logging.INFO):
        self.log_level = log_level
        self.logs_dir = self._ensure_logs_directory()
        self.log_file_path = self._create_log_file_path()
        self._setup_logging()

    def _ensure_logs_directory(self) -> Path:
        """Creates logs directory in user data."""
        pc = app_config.paths
        # ensure existence of basic user directories
        pc.ensure_user_data_dirs()
        logs_dir = pc.get_logs_dir()
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

    def _create_log_file_path(self) -> Path:
        """Creates log file path with date."""
        log_filename = f"app_log_{datetime.now().strftime('%Y%m%d')}.txt"
        return self.logs_dir / log_filename

    def _get_app_directory(self):
        """Determines application root directory (works in packaged form)."""
        if getattr(sys, "frozen", False):
            # Packaged application (PyInstaller, cx_Freeze, etc.)
            return Path(sys.executable).parent
        else:
            # Development mode - project root
            return Path(__file__).parents[3]

    def _get_config_path(self):
        """Determines logging configuration path with priorities."""
        # Priority 1: Environment variable (for advanced users)
        env_path = os.getenv("LOGGING_CONFIG_PATH")
        if env_path and Path(env_path).exists():
            logging.info(
                "Using configuration from environment variable: %s", env_path
            )
            return Path(env_path)

        # Priority 2: Next to executable (portability)
        app_dir = self._get_app_directory()
        portable_path = app_dir / "config_data" / "logging_config.json"
        if portable_path.exists():
            logging.info("Using portable configuration: %s", portable_path)
            return portable_path

        # Priority 3: Standard project location (development)
        # .../app/config_data/logging_config.json
        dev_path = Path(__file__).parents[2] / "config_data" / "logging_config.json"
        if dev_path.exists():
            logging.info("Using development configuration: %s", dev_path)
            return dev_path

        # If nothing found
        logging.warning(
            "Logging configuration file not found, using default settings"
        )
        return None

    def _get_embedded_config(self):
        """Returns embedded logging configuration as fallback."""
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                },
                "detailed": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s"
                },
            },
            "handlers": {
                "console": {
                    "level": "INFO",
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                },
                "file": {
                    "level": "DEBUG",
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": str(self.log_file_path),
                    "maxBytes": 10485760,  # 10MB
                    "backupCount": 5,
                    "formatter": "detailed",
                    "encoding": "utf-8",
                },
            },
            "loggers": {
                "": {
                    "handlers": ["console", "file"],
                    "level": self.log_level,
                    "propagate": False,
                }
            },
        }

    def _setup_logging(self):
        """Sets up logging system via dictConfig with log rotation."""
        try:
            # Get configuration file path
            config_path = self._get_config_path()

            if config_path:
                # Load configuration from file
                with open(config_path, encoding="utf-8") as f:
                    log_config = json.load(f)

                # Update log file path in configuration
                if "handlers" in log_config and "file" in log_config["handlers"]:
                    log_config["handlers"]["file"]["filename"] = str(self.log_file_path)

                # Apply logging level
                if "loggers" in log_config and "" in log_config["loggers"]:
                    log_config["loggers"][""]["level"] = self.log_level

                # Set up logging via dictConfig
                logging.config.dictConfig(log_config)
                logging.info("Logging configured from file: %s", config_path)
            else:
                # Use embedded configuration
                log_config = self._get_embedded_config()
                logging.config.dictConfig(log_config)
                logging.info(
                    self.log_file_path,
                )

        except (FileNotFoundError, PermissionError, json.JSONDecodeError) as e:
            # If an error occurs while loading the configuration, use the embedded one
            logging.warning(
                "Error loading logging configuration: %s. Using embedded configuration.",
                e,
            )
            try:
                log_config = self._get_embedded_config()
                logging.config.dictConfig(log_config)
                logging.info("Logging configured via embedded configuration (fallback)")
            except Exception as fallback_error:
                # Last resort - basic configuration
                logging.basicConfig(
                    level=self.log_level,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[
                        logging.StreamHandler(),
                        logging.FileHandler(self.log_file_path, encoding="utf-8"),
                    ],
                )
                logging.error(
                    "Critical logging configuration error: %s. Using basic configuration.",
                    fallback_error,
                )
        except Exception as e:
            # General handler for unexpected errors
            logging.error(
                "Unexpected logging configuration error: %s. Using basic configuration.",
                e,
            )
            logging.basicConfig(
                level=self.log_level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            )
