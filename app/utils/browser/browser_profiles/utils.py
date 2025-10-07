import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_browser_display_name(finder: Any, fallback_key: str) -> str:
    """Safely get readable browser name.
    Falls back to browser key on error/missing method.
    """
    try:
        if hasattr(finder, "get_browser_name"):
            return finder.get_browser_name()
    except Exception as e:
        logger.debug("get_browser_display_name: error calling get_browser_name: %s", e)
    return fallback_key
