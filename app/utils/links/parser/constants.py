"""Constants and logger used by parser modules."""

import logging

try:
    import lxml

    BS_PARSER = "lxml"
except Exception:
    BS_PARSER = "html.parser"

# --- Constants ---
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
TIMEOUT = 8.0  # Increased for more robust fetching under slow/CF-protected sites
CACHE_TTL = 7 * 24 * 3600
SHORT_NEGATIVE_TTL = 3600  # 1 hour for negative cache (timeouts, 5xx)
MEDIUM_NEGATIVE_TTL = 4 * 3600  # 4 hours for 4xx
ICON_FILE_TTL = 3 * 24 * 3600  # 3 days for icon file refresh
DEFAULT_JITTER_PCT = 0.15
MIN_GOOD_SIZE = 16
TARGET_SIZE = 64
FORMAT_RANK = {
    "ico": 0,
    "png": 1,
    "apng": 1,  # Animated PNG: treat the same priority as PNG
    "webp": 2,
    "avif": 2,  # Modern format; availability depends on PIL plugins
    "gif": 3,
    "jpg": 4,
    "bmp": 5,
    "svg": 9,  # SVG last
    "unknown": 6,
}

# Logger
logger = logging.getLogger("favicon_parser")
logger.setLevel(logging.DEBUG)

__all__ = [
    "USER_AGENT",
    "TIMEOUT",
    "CACHE_TTL",
    "SHORT_NEGATIVE_TTL",
    "MEDIUM_NEGATIVE_TTL",
    "ICON_FILE_TTL",
    "DEFAULT_JITTER_PCT",
    "MIN_GOOD_SIZE",
    "TARGET_SIZE",
    "FORMAT_RANK",
    "BS_PARSER",
    "logger",
]
