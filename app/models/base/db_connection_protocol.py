"""Protocol for connection manager to enable type checking."""

import sqlite3
from typing import Protocol


class ConnectionManagerProtocol(Protocol):
    """Protocol for database connection manager."""

    @property
    def connection(self) -> sqlite3.Connection:
        """Return active SQLite connection."""
        ...
