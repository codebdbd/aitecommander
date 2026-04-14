"""Types and constants for models."""

from .category_types import BulkInsertResult, CategoryDict
from .constants import (
    BACKUP_RETRY_ATTEMPTS,
    BACKUP_RETRY_DELAY,
    CATEGORY_BULK_UUID_FIELD,
    DEFAULT_ICON_PATH,
    DEFAULT_MAX_BACKUPS,
    DEFAULT_QUERY_TIMEOUT,
    EMPTY_ICON_PATH,
    PERFORMANCE_WARNING_THRESHOLD_MS,
    SQLITE_MAX_VARIABLES,
    SQLITE_SAFE_BATCH_SIZE,
    SQLITE_SAFE_SELECT_CHUNK,
    VALID_POSITION_TABLES,
)
from .link_type import LinkType
from .link_types import LinkDict, LinkInput

__all__ = [
    # Types
    "BulkInsertResult",
    "CategoryDict",
    "LinkDict",
    "LinkInput",
    "LinkType",
    # Constants
    "CATEGORY_BULK_UUID_FIELD",
    "SQLITE_MAX_VARIABLES",
    "SQLITE_SAFE_BATCH_SIZE",
    "SQLITE_SAFE_SELECT_CHUNK",
    "DEFAULT_MAX_BACKUPS",
    "BACKUP_RETRY_ATTEMPTS",
    "BACKUP_RETRY_DELAY",
    "PERFORMANCE_WARNING_THRESHOLD_MS",
    "DEFAULT_QUERY_TIMEOUT",
    "DEFAULT_ICON_PATH",
    "EMPTY_ICON_PATH",
    "VALID_POSITION_TABLES",
]
