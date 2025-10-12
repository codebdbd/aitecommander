"""Utility helpers that bridge configuration structures with Qt types."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import (
    QCoreApplication,
    QLocale,
    QObject,
    QSize,
    Qt,
    QTranslator,
)
from PyQt6.QtGui import QColor, QFont, QIcon

logger = logging.getLogger(__name__)

__all__ = [
    "to_qsize",
    "to_size_list",
    "to_qfont",
    "to_qcolor",
    "to_qicon",
    "load_and_install_translator",
    "safe_connect",
    "has_signal",
]


def to_qsize(size_data: int | Sequence[int]) -> QSize:
    """Convert a generic size value from config into a `QSize` instance."""
    if isinstance(size_data, Sequence) and len(size_data) >= 2:
        return QSize(int(size_data[0]), int(size_data[1]))
    if isinstance(size_data, int):
        return QSize(size_data, size_data)
    return QSize(24, 24)


def to_size_list(size_data: int | Sequence[int]) -> list[int]:
    """Convert a Qt size configuration into a simple `[width, height]` list."""
    if isinstance(size_data, Sequence) and len(size_data) >= 2:
        return [int(size_data[0]), int(size_data[1])]
    if isinstance(size_data, int):
        return [size_data, size_data]
    return [24, 24]


def to_qfont(font_data: str | Mapping[str, Any] | None) -> QFont:
    """Create a `QFont` instance from configuration data."""
    font = QFont()
    if font_data is None:
        return font
    if isinstance(font_data, str):
        font.setFamily(font_data)
        return font

    if not isinstance(font_data, Mapping):
        logger.warning("Unsupported font configuration: %r", font_data)
        return font

    family = font_data.get("family")
    if family:
        font.setFamily(str(family))

    point_size = font_data.get("point_size")
    if point_size is not None:
        try:
            font.setPointSize(int(point_size))
        except (TypeError, ValueError):
            logger.warning("Invalid point_size value for font config: %r", point_size)

    weight = font_data.get("weight")
    if weight is not None:
        try:
            font.setWeight(int(weight))
        except (TypeError, ValueError):
            logger.warning("Invalid weight value for font config: %r", weight)

    italic = font_data.get("italic")
    if italic is not None:
        font.setItalic(bool(italic))

    return font


def to_qcolor(color_data: str | Sequence[int] | Mapping[str, int] | None) -> QColor:
    """Create a `QColor` instance from configuration data."""
    if color_data is None:
        return QColor()
    if isinstance(color_data, str):
        return QColor(color_data)
    if isinstance(color_data, Mapping):
        r = int(color_data.get("r", 0))
        g = int(color_data.get("g", 0))
        b = int(color_data.get("b", 0))
        a = int(color_data.get("a", 255))
        return QColor(r, g, b, a)
    if isinstance(color_data, Sequence) and len(color_data) in {3, 4}:
        r, g, b = (int(color_data[0]), int(color_data[1]), int(color_data[2]))
        a = int(color_data[3]) if len(color_data) == 4 else 255
        return QColor(r, g, b, a)
    logger.warning("Unsupported color configuration: %r", color_data)
    return QColor()


@lru_cache(maxsize=128)
def to_qicon(path: str | Path, *, base_path: Path | None = None) -> QIcon:
    """Return a cached `QIcon` resolved from a relative or absolute path."""
    icon_path = Path(path)
    if not icon_path.is_absolute() and base_path is not None:
        icon_path = Path(base_path) / icon_path
    if not icon_path.exists():
        logger.warning("Icon path does not exist: %s", icon_path)
    return QIcon(str(icon_path))


def load_and_install_translator(
    base_name: str,
    locale: str | QLocale,
    translations_dir: str | Path,
    *,
    application: QCoreApplication | None = None,
    fallback_locale: str | None = None,
) -> QTranslator | None:
    """Load a `.qm` translation file, install it into the Qt application, and return it."""

    app = application or QCoreApplication.instance()
    if app is None:
        logger.warning(
            "Cannot install translator without an active QCoreApplication instance."
        )
        return None

    translations_path = Path(translations_dir)
    if not translations_path.exists():
        logger.warning("Translations directory not found: %s", translations_path)
        return None

    locale_obj = QLocale(locale) if not isinstance(locale, QLocale) else locale
    translator = QTranslator()

    def _load(locale_name: str) -> bool:
        filename = translations_path / f"{base_name}_{locale_name}.qm"
        if filename.exists() and translator.load(str(filename)):
            app.installTranslator(translator)
            logger.debug("Installed translator: %s", filename)
            return True
        logger.warning("Translation file not found or failed to load: %s", filename)
        return False

    if _load(locale_obj.name()):
        return translator

    if fallback_locale:
        fallback = QLocale(fallback_locale)
        if _load(fallback.name()):
            return translator

    return None


def safe_connect(
    signal: Any,
    slot: Callable[..., Any],
    *,
    logger: logging.Logger | None = None,
    connection_type: Qt.ConnectionType = Qt.ConnectionType.AutoConnection,
) -> bool:
    """Connect a Qt signal to a slot with validation and structured logging."""

    log = logger or logging.getLogger(__name__)

    if not callable(slot):
        log.error("Slot is not callable: %r", slot)
        return False

    try:
        signal.connect(slot, type=connection_type)
        return True
    except TypeError:
        try:
            signal.connect(slot)
            return True
        except Exception as exc:  # noqa: BLE001 - log exact exception for diagnostics
            log.error("Failed to connect signal %r to %r: %s", signal, slot, exc)
    except Exception as exc:  # noqa: BLE001 - catch PyQt specific errors
        log.error("Failed to connect signal %r to %r: %s", signal, slot, exc)

    return False


def has_signal(obj: QObject, signal_name: str) -> bool:
    """Return `True` if the QObject exposes a bound signal with the given name."""

    try:
        candidate = getattr(obj, signal_name)
    except AttributeError:
        return False

    return hasattr(candidate, "connect") and callable(candidate.connect)
