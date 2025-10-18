"""Internationalization helpers for the application.

The :mod:`i18n` package exposes the high-level API that the rest of the codebase
uses for working with translations and locale-aware formatting.  It re-exports
the :class:`LanguageService` singleton together with convenience helpers that
delegate to it, plus formatting utilities for numbers, dates, and monetary
values.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .language_service import LanguageDescriptor, LanguageService
from .locale_utils import (
    format_currency,
    format_date,
    format_datetime,
    format_decimal,
    format_filesize,
    format_number,
    format_percent,
    format_time,
)

__all__ = [
    # Service layer
    "LanguageDescriptor",
    "LanguageService",
    "available_languages",
    "current_language",
    "get_language_descriptor",
    "install_translator",
    "set_language",
    # Formatting utilities
    "format_currency",
    "format_date",
    "format_datetime",
    "format_decimal",
    "format_filesize",
    "format_number",
    "format_percent",
    "format_time",
]

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QApplication


def available_languages() -> list[LanguageDescriptor]:
    """Return descriptors for the languages supported by the UI."""
    return LanguageService.instance().available_languages()


def current_language() -> str:
    """Return the language code currently active in the UI."""
    return LanguageService.instance().current_language()


def set_language(language_code: str) -> bool:
    """Switch the UI to the requested language."""
    return LanguageService.instance().set_language(language_code)


def get_language_descriptor(code: str) -> LanguageDescriptor | None:
    """Fetch metadata for a specific language code."""
    return LanguageService.instance().get_language_descriptor(code)


def install_translator(app: QApplication | None) -> bool:
    """Install the currently selected translator on ``app`` (``QApplication``)."""
    return LanguageService.instance().install_translator(app)
