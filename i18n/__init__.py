"""Internationalization (i18n) package for Aite Commander.

This package provides comprehensive localization support for the PyQt6 application,
including language switching, translation management, and locale-specific formatting.

Key Components:
    - LanguageService: Singleton for managing UI languages and translations
    - locale_utils: Formatting utilities for dates, numbers, and currency
    - Translation files: .ts and .qm files for different languages

Supported Languages:
    - en (English) - source language
    - uk (Ukrainian)
    - ru (Russian)
    - fr (French)
    - es (Spanish)
    - de (German)
"""

from __future__ import annotations

__all__ = [
    "LanguageService",
    "format_datetime",
    "format_decimal",
    "format_currency",
]
