"""
Common utilities used throughout the application.
"""

import logging
from typing import Any, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


def get_value(obj: Any, key: str, default: Any = None) -> Any:
    """Safely extracts a value by key/attribute from an object.

    Supports:
    - dict-like objects (having a .get method)
    - regular objects (via getattr)

    Args:
        obj: data source (dict, dataclass, object, etc.)
        key: key/attribute name
        default: default value if key/attribute is missing

    Returns:
        Value by key/attribute or default
    """
    try:
        if hasattr(obj, "get"):
            return obj.get(key, default)  # type: ignore[attr-defined]
        return getattr(obj, key, default)
    except (AttributeError, TypeError, KeyError):
        return default
    except Exception as unexpected_error:  # pragma: no cover - diagnostic scenario
        logger.warning(
            "get_value: unexpected error for key %s: %s", key, unexpected_error
        )
        return default


def safe_getattr(obj: Any, attr: str, default: T | None = None) -> T | None:
    """Safely get an attribute from an object, returning default on error.

    Handles AttributeError/TypeError and any unexpected exceptions,
    to prevent UI code from crashing when accessing stubs/test objects.
    """
    try:
        return getattr(obj, attr) if obj is not None else default
    except (AttributeError, TypeError):
        return default
    except Exception as unexpected_error:  # pragma: no cover - diagnostic scenario
        logger.warning(
            "safe_getattr: unexpected error for attr %s: %s", attr, unexpected_error
        )
        return default


def safe_call(
    obj: Any,
    method_name: str,
    *args: Any,
    default: T | None = None,
    **kwargs: Any,
) -> T | None:
    """Safely call an object method by name.

    If the method doesn't exist or throws expected errors, returns default.
    Unexpected exceptions are swallowed to protect the UI thread.
    """
    try:
        method = getattr(obj, method_name, None)
        if method and callable(method):
            result = method(*args, **kwargs)
            return result if result is not None else default
    except (AttributeError, TypeError):
        return default
    except Exception as unexpected_error:  # pragma: no cover - diagnostic scenario
        logger.warning(
            "safe_call: unexpected error calling %s on %s: %s",
            method_name,
            type(obj).__name__ if obj is not None else "<None>",
            unexpected_error,
        )
        return default
    return default
