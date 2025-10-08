"""Internationalization package entry point."""

from .language_service import LanguageService  # noqa: F401
from .language_service import language_service  # noqa: F401
from . import locale_utils  # noqa: F401

__all__ = [
    "LanguageService",
    "language_service",
    "locale_utils",
]
