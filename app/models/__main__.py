"""Entry point для CLI: python -m app.models.db"""

import sys

from .cli.db_cli import main

if __name__ == "__main__":
    sys.exit(main())
