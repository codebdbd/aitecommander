# app/config_data/utils.py
from typing import Any, Dict


def get_by_path(config: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """Return a nested dictionary value resolved via dotted key path.

    Example: ``key_path="ui.window.width"``. Returns ``default`` when the key is
    missing or the structure does not match expectations.
    """
    keys = key_path.split(".") if key_path else []
    value: Any = config
    try:
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError):
        return default
