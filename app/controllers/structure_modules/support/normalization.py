# app/controllers/structure_modules/normalization.py

"""Module for normalizing data from database."""

import logging
from typing import Any, Optional, Protocol, Union, runtime_checkable

# Module logger
logger = logging.getLogger(__name__)


@runtime_checkable
class RowLike(Protocol):
    """Protocol for DB row-like objects."""

    def keys(self) -> Any:
        """Return object keys."""
        ...


# Data types that module can handle
SupportedRowType = Union[dict[str, Any], RowLike, tuple, None]


def _try_namedtuple_conversion(row, logger):
    """Try to convert namedtuple to dict."""
    try:
        return row._asdict()
    except AttributeError as e:
        logger.warning("Error calling _asdict() for namedtuple: %s", e)
        try:
            return dict(zip(row._fields, row))
        except (AttributeError, TypeError) as fallback_e:
            logger.error("Failed to process namedtuple: %s", fallback_e)
            return None


def _try_keys_conversion(row, logger):
    """Try to convert object with keys() method to dict."""
    try:
        keys = row.keys()
        if hasattr(keys, "__iter__"):
            return dict(row)
        else:
            logger.warning(
                "keys() method of object %s does not return iterable object",
                type(row),
            )
            return None
    except (TypeError, ValueError, AttributeError) as e:
        logger.warning(
            "Error accessing keys() of object %s: %s",
            type(row),
            e,
        )
        return None


def _try_mapping_protocol(row, logger):
    """Try to use mapping protocol to convert to dict."""
    if hasattr(row, "__getitem__") and hasattr(row, "keys"):
        try:
            return {key: row[key] for key in row.keys()}
        except (KeyError, TypeError, AttributeError) as e:
            logger.warning(
                "Error manually creating dictionary from object %s: %s",
                type(row),
                e,
            )
    return None


def normalize_row(row: Any, logger: Optional[logging.Logger] = None) -> dict[str, Any]:
    """Safely normalize DB row to dictionary.

    Supports:
    - sqlite3.Row
    - namedtuple
    - dict
    - any objects with keys() method

    Args:
        row: DB data row
        logger: Logger for warnings

    Returns:
        Dict[str, Any]: Normalized dictionary
    """
    active_logger = logger or logging.getLogger(__name__)

    if row is None:
        return {}

    if isinstance(row, dict):
        return row.copy()

    if isinstance(row, tuple) and hasattr(row, "_fields"):
        result = _try_namedtuple_conversion(row, active_logger)
        if result is not None:
            return result
        return {}

    if hasattr(row, "keys"):
        result = _try_keys_conversion(row, active_logger)
        if result is not None:
            return result

    try:
        result = dict(row)
        if result:
            return result
    except (TypeError, ValueError, AttributeError):
        pass

    result = _try_mapping_protocol(row, active_logger)
    if result is not None:
        return result

    # If nothing worked
    active_logger.error(
        "Failed to normalize object of type %s. Supported types: dict, namedtuple, sqlite3.Row, objects with keys() method",
        type(row).__name__,
    )
    return {}


def normalize_rows(
    rows: Any, logger: Optional[logging.Logger] = None
) -> list[dict[str, Any]]:
    """Normalize list of DB rows to list of dictionaries.

    Args:
        rows: List of DB rows, single row or None
        logger: Logger for warnings

    Returns:
        List[Dict[str, Any]]: Normalized list of dictionaries
    """
    active_logger = logger or logging.getLogger(__name__)

    if rows is None:
        return []

    # If single row passed, wrap in list
    if not isinstance(rows, (list, tuple)):
        rows = [rows]

    result = []
    for i, row in enumerate(rows):
        try:
            normalized = normalize_row(row, active_logger)
            result.append(normalized)
        except Exception as e:
            active_logger.error("Error normalizing row #%s: %s", i, e)

    return result


def validate_required_keys(
    data: dict[str, Any], required_keys: Optional[list[str]] = None
) -> bool:
    """Validate normalized data.

        Args:
            data: Normalized data (dictionary or list of dictionaries)
    {{ ... }}

        Returns:
            bool: True if data is valid, False otherwise
    """
    if required_keys is None:
        required_keys = []

    def _validate_dict(d: dict[str, Any]) -> bool:
        if not isinstance(d, dict):
            return False
        return all(key in d for key in required_keys)

    if isinstance(data, dict):
        return _validate_dict(data)
    elif isinstance(data, list):
        return all(isinstance(item, dict) and _validate_dict(item) for item in data)

    return False


# For backward compatibility - export old names
__all__ = [
    "normalize_row",
    "normalize_rows",
    "validate_required_keys",
    "SupportedRowType",
    "RowLike",
]
