"""Application entry point."""

from __future__ import annotations

import sys

from app.core.constants import AppConstants
from app.core.error_handler import GlobalErrorHandler
from app.core.log_manager import LogManager
from app.startup.runtime import run

LogManager.setup()
GlobalErrorHandler.install()

APP_NAME = AppConstants.APP_NAME


def main() -> int:
    """Run the Qt application."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
