"""Entry point for running i18n CLI via `python -m i18n`."""

import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
