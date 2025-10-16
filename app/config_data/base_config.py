"""Base primitives shared by configuration modules."""

from __future__ import annotations

from typing import Any, Dict

from .utils import get_by_path


class BaseConfig:
    """Common helper used by every configuration namespace."""

    def __init__(self, config_data: Dict[str, Any]):
        """Store the raw configuration payload."""
        self._config = config_data

    def get(self, key_path: str, default: Any = None) -> Any:
        """Return a value from the configuration using a dotted key path."""
        return get_by_path(self._config, key_path, default)
