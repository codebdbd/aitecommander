"""Centralized application constants."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def _get_version() -> str:
    """Read version from package metadata (single source of truth in pyproject.toml)."""
    try:
        return version("aitecommander")
    except PackageNotFoundError:
        return "0.0.0-dev"


class AppConstants:
    """Static container for app-wide constants."""

    APP_NAME = "AiteCommander"
    ORG_NAME = "Codebdbd"
    VERSION = _get_version()

    LOG_DIR_NAME = "logs"

    DEFAULT_WINDOW_WIDTH = 1024
    DEFAULT_WINDOW_HEIGHT = 768
    DEFAULT_WINDOW_MIN_WIDTH = 280
    DEFAULT_WINDOW_MIN_HEIGHT = 600
    LARGE_BATCH_THRESHOLD = 20
    PRELOAD_SUSPEND_DURATION_MS = 3500
    PRELOAD_RESUME_DELAY_MS = 900
