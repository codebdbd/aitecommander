# validation.py
"""Icon validation and verification utilities.

Features:
- Strict filtering of icon names without slashes to protect against traversal.
- Careful SVG/SVGZ validation (by content, with read size limit).
- Raster validation through PIL without unnecessary file openings.
- Configuration support via app_config.

Complies with PEP 8.
"""

from __future__ import annotations

import logging
import re
import stat as stat_module
import threading
from collections import OrderedDict
from collections.abc import Iterable
from enum import Enum
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.config_data import app_config

logger = logging.getLogger(__name__)

_VALID_ICON_CACHE_MAX = 1024
_valid_icon_file_cache: OrderedDict[tuple[str, int, int], bool] = OrderedDict()
_valid_icon_file_cache_lock = threading.RLock()


def _get_cached_icon_validation(cache_key: tuple[str, int, int]) -> bool | None:
    with _valid_icon_file_cache_lock:
        cached = _valid_icon_file_cache.get(cache_key)
        if cached is None:
            return None
        _valid_icon_file_cache.move_to_end(cache_key)
        return cached


def _set_cached_icon_validation(cache_key: tuple[str, int, int], is_valid: bool) -> bool:
    with _valid_icon_file_cache_lock:
        _valid_icon_file_cache[cache_key] = bool(is_valid)
        _valid_icon_file_cache.move_to_end(cache_key)
        while len(_valid_icon_file_cache) > _VALID_ICON_CACHE_MAX:
            _valid_icon_file_cache.popitem(last=False)
    return bool(is_valid)


# === Configuration proxies (updated dynamically) ===


def get_max_icon_size() -> int:
    """Maximum icon file size in bytes (from configuration)."""
    return int(app_config.get_max_icon_size())


def get_supported_icon_formats() -> Iterable[str]:
    """Set of supported raster extensions (including .png, .jpg, etc.)."""
    return app_config.get_supported_icon_formats()


def get_valid_themes() -> Iterable[str]:
    """List of valid theme names."""
    try:
        from app.services.theme_registry import theme_registry

        return theme_registry.get_theme_ids()
    except Exception:
        return ["light", "dark"]


# === Enums / exceptions ===


class Theme(Enum):
    """Appearance theme."""

    LIGHT = "light"
    DARK = "dark"

    @classmethod
    def from_string(cls, theme_str: str) -> Theme:
        s = (theme_str or "").lower().strip()
        return cls.DARK if s == "dark" else cls.LIGHT


class IconError(Exception):
    """Base exception for icon errors."""


class IconNotFoundError(IconError):
    """Icon not found."""


class InvalidIconError(IconError):
    """Icon file/parameters are incorrect."""


# === Internal validators for vector formats ===


def _safe_decode_bytes_preview(data: bytes) -> str | None:
    """Attempt to decode the first bytes of a file into a string.

    Encoding order: utf-8 -> utf-16 -> latin-1.
    Returns None if decoding failed.
    """
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc, errors="strict")
        except UnicodeDecodeError:
            continue
    return None


def _is_valid_svg(path: Path) -> bool:
    """Check if an SVG file is valid by its tag structure."""
    try:
        max_read_size = min(get_max_icon_size(), 1024 * 1024)  # no more than 1 MB
        with path.open("rb") as f:
            content = f.read(max_read_size)

        text = _safe_decode_bytes_preview(content)
        if text is None:
            logger.debug("SVG decode failed: %s", path)
            return False

        open_tag = re.search(r"<\s*svg\b[^>]*>", text, re.IGNORECASE | re.DOTALL)
        close_tag = re.search(r"<\s*/\s*svg\s*>", text, re.IGNORECASE)
        if not open_tag or not close_tag:
            logger.debug("SVG tags missing in: %s", path)
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("SVG validation error for %s: %s", path, exc)
        return False


def _is_valid_svgz(path: Path) -> bool:
    """SVGZ validity check (gzip + valid SVG inside)."""
    import gzip

    try:
        # fast gzip signature
        with path.open("rb") as f:
            sig = f.read(2)
            if len(sig) < 2 or sig[0] != 0x1F or sig[1] != 0x8B:
                logger.debug("Not a gzip file: %s", path)
                return False

        max_read_size = min(get_max_icon_size(), 1024 * 1024)
        with gzip.open(path, "rb") as f:
            content = f.read(max_read_size)

        text = _safe_decode_bytes_preview(content)
        if text is None:
            logger.debug("SVGZ inner decode failed: %s", path)
            return False

        open_tag = re.search(r"<\s*svg\b[^>]*>", text, re.IGNORECASE | re.DOTALL)
        close_tag = re.search(r"<\s*/\s*svg\s*>", text, re.IGNORECASE)
        return bool(open_tag and close_tag)
    except (OSError, gzip.BadGzipFile) as exc:
        logger.debug("SVGZ validation error for %s: %s", path, exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected SVGZ error for %s: %s", path, exc)
        return False


# === Public validators ===


def _validate_icon_name(icon_name: str) -> bool:
    """Icon name validation.

    Requirements:
    - String is not empty.
    - Allowed characters: Latin letters, digits, `_`, `-`, `.`.
    - Paths/subfolders and traversal (`/`, `\\`, `..`) are forbidden to avoid accessing outside the expected folder.
    """
    if not icon_name or not isinstance(icon_name, str):
        return False

    if "../" in icon_name or "..\\" in icon_name:
        # Forbidden traversal
        return False

    # no slashes - icons are searched only in expected theme folders by path service
    if "/" in icon_name or "\\" in icon_name:
        return False

    return bool(re.match(r"^[a-zA-Z0-9_.-]+$", icon_name))


def validate_theme(theme: str) -> str:
    """Theme name normalization with safe fallback."""
    if not theme or not isinstance(theme, str):
        try:
            from app.services.theme_registry import theme_registry

            return theme_registry.get_default_theme_id()
        except Exception:
            return "light"
    t = theme.lower().strip()
    valid = set(get_valid_themes())
    if t in valid:
        return t
    logger.warning("Invalid theme '%s', using fallback", theme)
    try:
        from app.services.theme_registry import theme_registry

        return theme_registry.get_default_theme_id()
    except Exception:
        return "light"

def is_valid_icon_file(file_path: str | Path) -> bool:
    """Check if path is a valid icon file.

    Support:
    - SVG / SVGZ (structural validation).
    - Raster formats from configuration (via PIL.Image.verify()).
    - File size limit from configuration.

    Returns:
        True if file is acceptable; False otherwise.
    """
    if not file_path:
        return False

    path = Path(file_path)

    # size limit
    try:
        stat_result = path.stat()
    except OSError as exc:
        logger.debug("stat() failed for %s: %s", path, exc)
        return False

    if not stat_module.S_ISREG(stat_result.st_mode):
        return False

    cache_key = (
        str(path),
        int(stat_result.st_mtime_ns),
        int(stat_result.st_size),
    )
    cached = _get_cached_icon_validation(cache_key)
    if cached is not None:
        return cached

    file_size = int(stat_result.st_size)
    max_size = get_max_icon_size()
    if file_size > max_size:
        logger.debug("File too large %s (%s > %s)", path, file_size, max_size)
        return _set_cached_icon_validation(cache_key, False)

    ext = path.suffix.lower()

    if ext == ".svg":
        return _set_cached_icon_validation(cache_key, _is_valid_svg(path))

    if ext == ".svgz":
        return _set_cached_icon_validation(cache_key, _is_valid_svgz(path))

    if ext not in set(map(str.lower, get_supported_icon_formats())):
        logger.debug("Unsupported raster format %s for %s", ext, path)
        return _set_cached_icon_validation(cache_key, False)

    # Rasters: quick integrity check
    try:
        with Image.open(path) as img:
            img.verify()  # does not load fully into memory
        return _set_cached_icon_validation(cache_key, True)
    except (UnidentifiedImageError, OSError) as exc:
        logger.debug("PIL verify failed for %s: %s", path, exc)
        return _set_cached_icon_validation(cache_key, False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected raster validation error for %s: %s", path, exc)
        return _set_cached_icon_validation(cache_key, False)


def validate_config_for_icons(config) -> bool:
    """Checks if config supports icon directories.

    Minimal UI icon check: presence of get_link_icons_dir method.
    Keep in UI layer to avoid pulling UI dependency into general validators.
    """
    return hasattr(config, "get_link_icons_dir")


def is_cached_icon_valid(save_path: str | Path, source_path: str | Path) -> bool:
    """Checks if cached icon is up-to-date by modification time.

    Returns True if save_path exists, is a valid icon file
    and its mtime is not less than the source file's.
    """
    try:
        save_path = str(save_path)
        source_path = str(source_path)
        save_path_obj = Path(save_path)
        if not (save_path_obj.exists() and is_valid_icon_file(save_path)):
            return False
        return save_path_obj.stat().st_mtime >= Path(source_path).stat().st_mtime
    except OSError:
        return False


# === Icon environment startup validation ===


def validate_ui_icon_environment() -> bool:
    """Checks basic readiness of icon environment.

    Checks:
    - Base UI icons directory exists from configuration (`app_config.paths.get_ui_icons_dir()`).
    - Bundled theme icon folders exist (from ThemeRegistry).

    Returns True if all checks passed; otherwise False.
    Logs itself (error/warning/info).
    """
    ok = True
    try:
        base_dir = app_config.paths.get_ui_icons_dir()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to get UI icons path from configuration: %s", exc)
        return False

    if not base_dir or not isinstance(base_dir, (str, Path)):
        logger.error("Invalid UI icons path in configuration: %r", base_dir)
        return False

    base_dir = Path(base_dir)
    if not base_dir.exists() or not base_dir.is_dir():
        logger.error("UI icons directory not found: %s", base_dir)
        ok = False
    else:
        logger.info("UI icons directory: %s", base_dir)

    # Theme check (bundled themes only)
    try:
        from app.services.theme_registry import theme_registry

        themes = [t for t in theme_registry.list_themes() if t.source == "bundled"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to get list of bundled themes: %s", exc)
        themes = []

    for theme in themes:
        theme_dir = theme.icons_dir
        if not theme_dir.exists() or not theme_dir.is_dir():
            logger.error("Theme folder not found: %s", theme_dir)
            ok = False
        else:
            try:
                count = sum(1 for _ in theme_dir.iterdir())
                logger.info(
                    "Theme '%s': %s (elements: %d)",
                    theme.theme_id,
                    theme_dir,
                    count,
                )
            except OSError as exc:  # noqa: BLE001
                logger.debug("Failed to scan theme folder %s: %s", theme_dir, exc)

    return ok


def validate_and_log_ui_icons_startup() -> bool:
    """Runs icon environment check at startup and writes summary to log.

    Returns result of `validate_ui_icon_environment()` without interrupting startup.
    """
    result = validate_ui_icon_environment()
    if result:
        logger.info("UI icons environment check: OK")
    else:
        logger.warning(
            "UI icons environment check completed with errors. Check path and themes."
        )
    return result
