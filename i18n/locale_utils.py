"""Locale-aware formatting helpers built on top of :class:`QLocale`.

This module provides thin wrappers for date, time, numeric, and currency formatting
so the rest of the application can remain agnostic of Qt's localization APIs.
Use these helpers instead of manual string formatting whenever a user-facing value
is produced.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from PyQt6.QtCore import QDate, QDateTime, QLocale, QTime

from .language_service import LanguageService


@dataclass(frozen=True)
class FormatOptions:
    """Common formatting options shared by helpers."""

    format: QLocale.FormatType = QLocale.FormatType.LongFormat


def _get_locale() -> QLocale:
    return LanguageService.instance().current_locale()


def to_qdate(value: date | QDate) -> QDate:
    return value if isinstance(value, QDate) else QDate(value.year, value.month, value.day)


def to_qtime(value: time | QTime) -> QTime:
    return value if isinstance(value, QTime) else QTime(value.hour, value.minute, value.second)


def to_qdatetime(value: datetime | QDateTime) -> QDateTime:
    if isinstance(value, QDateTime):
        return value
    return QDateTime(to_qdate(value.date()), to_qtime(value.time()))


def format_date(value: date | QDate, *, fmt: QLocale.FormatType | None = None) -> str:
    locale = _get_locale()
    qdate = to_qdate(value)
    format_type = fmt if fmt is not None else QLocale.FormatType.LongFormat
    return locale.toString(qdate, format_type)


def format_time(value: time | QTime, *, fmt: QLocale.FormatType | None = None) -> str:
    locale = _get_locale()
    qtime = to_qtime(value)
    format_type = fmt if fmt is not None else QLocale.FormatType.LongFormat
    return locale.toString(qtime, format_type)


def format_datetime(
    value: datetime | QDateTime,
    *,
    fmt: QLocale.FormatType | None = None,
) -> str:
    locale = _get_locale()
    qdatetime = to_qdatetime(value)
    format_type = fmt if fmt is not None else QLocale.FormatType.LongFormat
    return locale.toString(qdatetime, format_type)


def format_decimal(value: float | int | Decimal, precision: int | None = None) -> str:
    locale = _get_locale()
    number = float(value) if isinstance(value, Decimal) else value
    if precision is None:
        return locale.toString(float(number))
    return locale.toString(float(number), f"f{precision}")


def format_number(value: int) -> str:
    locale = _get_locale()
    return locale.toString(int(value))


def format_currency(value: float | Decimal | int, currency_code: Optional[str] = None) -> str:
    locale = _get_locale()
    amount = float(value) if isinstance(value, (Decimal,)) else float(value)
    code = currency_code or locale.currencySymbol(QLocale.CurrencySymbolFormat.CurrencyIsoCode)
    return locale.toCurrencyString(amount, code)


def is_rtl() -> bool:
    return _get_locale().textDirection() == QLocale.TextDirection.RightToLeft


__all__ = [
    "FormatOptions",
    "format_date",
    "format_time",
    "format_datetime",
    "format_decimal",
    "format_number",
    "format_currency",
    "is_rtl",
    "to_qdate",
    "to_qtime",
    "to_qdatetime",
]
