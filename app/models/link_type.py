from __future__ import annotations

from enum import Enum
from typing import Any


class LinkType(Enum):
    WEB = "web"
    FILE = "file"
    FOLDER = "folder"
    PROGRAM = "program"
    SCRIPT = "script"
    CHROMEAPP = "chromeapp"

    @classmethod
    def from_value(cls, value: Any) -> "LinkType":
        """Нормализует входное значение к LinkType.

        Принимает Enum, строку или произвольный скаляр. Неизвестные значения
        приводятся к WEB для безопасного поведения по умолчанию.
        """
        if isinstance(value, LinkType):
            return value
        if value is None:
            return LinkType.WEB
        try:
            val = str(value).lower()
        except Exception:
            return LinkType.WEB
        for lt in cls:
            if lt.value == val:
                return lt
        return LinkType.WEB
