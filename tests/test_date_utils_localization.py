from __future__ import annotations

from PyQt6.QtCore import QLocale

from app.utils.system.date_utils import format_last_used


def test_format_last_used_returns_ukrainian_never_for_empty_value() -> None:
    previous = QLocale()
    QLocale.setDefault(QLocale("uk_UA"))
    try:
        assert format_last_used("") in ("Never", "Ніколи", "Никогда")
        assert format_last_used(None) in ("Never", "Ніколи", "Никогда")
    finally:
        QLocale.setDefault(previous)
