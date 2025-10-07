"""Constants for working with database models."""

# SQLite parameters and limits
SQLITE_MAX_VARIABLES = 999  # Maximum number of variables in SQLite query by default
SQLITE_SAFE_BATCH_SIZE = 400  # Safe batch size for operations with 2+ parameters per write
SQLITE_SAFE_SELECT_CHUNK = 900  # Safe chunk size for SELECT queries

# Backup
DEFAULT_MAX_BACKUPS = 10  # Default number of backups
BACKUP_RETRY_ATTEMPTS = 3  # Number of attempts to delete old backups
BACKUP_RETRY_DELAY = 0.1  # Delay between attempts (seconds)

# Performance
PERFORMANCE_WARNING_THRESHOLD_MS = 50.0  # Threshold for slow operation warnings (ms)
DEFAULT_QUERY_TIMEOUT = 30  # Default query timeout (seconds)

# Default values
DEFAULT_ICON_PATH = "default.ico"
EMPTY_ICON_PATH = ""

# Valid tables for position operations
VALID_POSITION_TABLES = frozenset({"sphere", "section", "category", "link"})
