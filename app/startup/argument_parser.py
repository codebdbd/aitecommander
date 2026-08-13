"""Module for parsing command-line arguments."""

import argparse
import logging
from typing import NamedTuple


class AppArguments(NamedTuple):
    """Container for application arguments."""

    debug: bool
    log_level: str | None
    no_gui: bool


def parse_arguments() -> AppArguments:
    """
    Parse command-line arguments.

    Returns:
        AppArguments: Parsed arguments container
    """
    parser = argparse.ArgumentParser(description="Run application")
    # Additional flags that do not affect the returned structure (compatibility)
    parser.add_argument(
        "--version",
        action="version",
        version="AiteCommander 1.1.3",
        help="Show version and exit",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (overrides --debug)",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run without initializing GUI (for certain testing scenarios)",
    )
    args = parser.parse_args()

    return AppArguments(
        debug=args.debug,
        log_level=args.log_level,
        no_gui=args.no_gui,
    )


def determine_log_level(args: AppArguments) -> int:
    """
    Determine the logging level based on arguments.

    Args:
        args: Parsed application arguments

    Returns:
        int: Logging level
    """
    if args.log_level:
        return getattr(logging, args.log_level)
    else:
        return logging.DEBUG if args.debug else logging.INFO
