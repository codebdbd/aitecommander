"""Locale-specific formatting utilities for dates, numbers, and currency."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Optional

from PyQt6.QtCore import QLocale

from .language_service import LanguageService


def format_datetime(
    dt: datetime.datetime,
    format_str: str = "dd.MM.yyyy HH:mm",
    locale_code: Optional[str] = None,
) -> str:
    """Format datetime using locale-specific formatting.

    Args:
        dt: Datetime to format
        format_str: Qt date format string
        locale_code: Override locale (default: current UI language)

    Returns:
        Formatted datetime string
    """
    if locale_code is None:
        locale_code = LanguageService.instance().current_language()

    locale = QLocale(locale_code)
    qdt = locale.toDateTime(
        dt.date(),
        dt.time()
    )
    return locale.toString(qdt, format_str)


def format_date(
    date: datetime.date,
    format_str: str = "dd.MM.yyyy",
    locale_code: Optional[str] = None,
) -> str:
    """Format date using locale-specific formatting.

    Args:
        date: Date to format
        format_str: Qt date format string
        locale_code: Override locale (default: current UI language)

    Returns:
        Formatted date string
    """
    if locale_code is None:
        locale_code = LanguageService.instance().current_language()

    locale = QLocale(locale_code)
    qdate = locale.toDate(date.year, date.month, date.day)
    return locale.toString(qdate, format_str)


def format_time(
    time: datetime.time,
    format_str: str = "HH:mm",
    locale_code: Optional[str] = None,
) -> str:
    """Format time using locale-specific formatting.

    Args:
        time: Time to format
        format_str: Qt time format string
        locale_code: Override locale (default: current UI language)

    Returns:
        Formatted time string
    """
    if locale_code is None:
        locale_code = LanguageService.instance().current_language()

    locale = QLocale(locale_code)
    qtime = locale.toTime(time.hour, time.minute, time.second)
    return locale.toString(qtime, format_str)


def format_decimal(
    value: float | Decimal | int,
    precision: int = 2,
    locale_code: Optional[str] = None,
) -> str:
    """Format decimal number using locale-specific formatting.

    Args:
        value: Number to format
        precision: Decimal places
        locale_code: Override locale (default: current UI language)

    Returns:
        Formatted number string
    """
    if locale_code is None:
        locale_code = LanguageService.instance().current_language()

    locale = QLocale(locale_code)
    return locale.toString(float(value), "f", precision)


def format_currency(
    amount: float | Decimal | int,
    currency_code: str = "USD",
    locale_code: Optional[str] = None,
) -> str:
    """Format currency amount using locale-specific formatting.

    Args:
        amount: Amount to format
        currency_code: ISO currency code
        locale_code: Override locale (default: current UI language)

    Returns:
        Formatted currency string
    """
    if locale_code is None:
        locale_code = LanguageService.instance().current_language()

    locale = QLocale(locale_code)
    return locale.toCurrencyString(float(amount), currency_code)


def format_number(
    value: int,
    locale_code: Optional[str] = None,
) -> str:
    """Format integer using locale-specific formatting.

    Args:
        value: Integer to format
        locale_code: Override locale (default: current UI language)

    Returns:
        Formatted number string
    """
    if locale_code is None:
        locale_code = LanguageService.instance().current_language()

    locale = QLocale(locale_code)
    return locale.toString(value)


def format_percent(
    value: float | Decimal | int,
    precision: int = 1,
    locale_code: Optional[str] = None,
) -> str:
    """Format percentage using locale-specific formatting.

    Args:
        value: Percentage value (0.15 for 15%)
        precision: Decimal places
        locale_code: Override locale (default: current UI language)

    Returns:
        Formatted percentage string
    """
    if locale_code is None:
        locale_code = LanguageService.instance().current_language()

    locale = QLocale(locale_code)
    return locale.toString(float(value) * 100, "f", precision) + "%"


def format_filesize(
    bytes_count: int,
    locale_code: Optional[str] = None,
) -> str:
    """Format file size in human-readable format.

    Args:
        bytes_count: Size in bytes
        locale_code: Override locale (default: current UI language)

    Returns:
        Formatted file size (e.g., "1.5 MB")
    """
    if locale_code is None:
        locale_code = LanguageService.instance().current_language()

    locale = QLocale(locale_code)

    if bytes_count < 1024:
        return locale.toString(bytes_count) + " B"
    elif bytes_count < 1024 * 1024:
        return locale.toString(bytes_count / 1024, "f", 1) + " KB"
    elif bytes_count < 1024 * 1024 * 1024:
        return locale.toString(bytes_count / (1024 * 1024), "f", 1) + " MB"
    else:
        return locale.toString(bytes_count / (1024 * 1024 * 1024), "f", 1) + " GB"
