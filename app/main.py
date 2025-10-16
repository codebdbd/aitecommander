"""Application entry point."""

from __future__ import annotations

import sys

from app.startup.runtime import run


def main() -> int:
    """Run the Qt application."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
