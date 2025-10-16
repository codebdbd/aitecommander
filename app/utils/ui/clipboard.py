import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

LinkData = Union[Dict[str, Any], List[Dict[str, Any]]]

logger = logging.getLogger(__name__)


def _to_jsonable(value: Any) -> Any:
    """Convert a value to a JSON-serializable form or return ``None`` to skip it.

    - Removes UI objects (e.g., ``QIcon``)
    - Converts ``Path`` to ``str``
    - Processes ``dict``/``list``/``tuple`` recursively
    - Skips unsupported types by returning ``None``
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, QIcon):
        return None  # do not serialize UI icon; it is restored via icon_path
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            # skip internal keys like _icon, _cache, etc.
            if isinstance(k, str) and k.startswith("_"):
                continue
            jv = _to_jsonable(v)
            if jv is not None:
                out[k] = jv
        return out
    if isinstance(value, (list, tuple)):
        arr = []
        for item in value:
            jv = _to_jsonable(item)
            if jv is not None:
                arr.append(jv)
        return arr
    # Skip all other unsupported types
    return None


def _sanitize_for_clipboard(data: LinkData) -> LinkData:
    if isinstance(data, list):
        return _to_jsonable(data) or []
    return _to_jsonable(data) or {}


def copy_link_to_clipboard(link_or_links: LinkData) -> bool:
    """Copies a link or list of links to the system clipboard.

    Returns True on success, False on error. Before copying, removes non-serializable
    fields (QIcon, private keys with underscores, etc.).
    """
    app = QApplication.instance()
    if app is None:
        logger.error(
            "QApplication is not initialized; clipboard operations are unavailable"
        )
        return False

    clipboard = app.clipboard()
    try:
        sanitized = _sanitize_for_clipboard(link_or_links)
        clipboard.setText(json.dumps(sanitized, ensure_ascii=False))
        return True
    except Exception as e:
        logger.error("Failed to copy link(s) to clipboard: %s", e, exc_info=True)
        try:
            clipboard.clear()
        except Exception:
            # Ignore secondary cleanup error
            pass
        return False


def get_link_from_clipboard() -> Optional[LinkData]:
    """Reads a link/list of links from the system clipboard.

    Returns:
      - dict or list[dict] on successful read
      - None on error, empty clipboard, missing QApplication, or invalid format
    """
    app = QApplication.instance()
    if app is None:
        logger.error(
            "QApplication is not initialized; clipboard operations are unavailable"
        )
        return None

    clipboard = app.clipboard()
    try:
        text = clipboard.text()
        if not text:
            return None

        data = json.loads(text)
        if isinstance(data, dict):
            # Basic dictionary structure validation (minimal)
            return data
        if isinstance(data, list):
            return data
        # Unsupported format
        return None
    except json.JSONDecodeError:
        return None
    except Exception as e:
        logger.error("Failed to read link from clipboard: %s", e, exc_info=True)
        return None
