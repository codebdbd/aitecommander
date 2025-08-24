# Модуль генерации данных для таблицы ссылок (модельно-ролевая архитектура)
# Ранее содержал создание QTableWidgetItem. Теперь предоставляет утилиты
# для формирования текстов и tooltip'ов, совместимых с QAbstractTableModel.

import logging
from pathlib import Path
from typing import Dict, List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from app.utils.ui.icon.icon_operations.creators import (
    create_icon_from_path,
    themed_icon,
)
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.path_service import get_current_theme, icon_path_service

# Константы для магических чисел
MAX_NOTES_LENGTH = 462
STAR_SYMBOL = "★"
STAR_COLOR = "#FFD700"
PATH_SEPARATOR = " → "


class ItemBuildersMixin:
    """Миксин-утилиты для генерации данных под роли модели.

    ВНИМАНИЕ: Создание QTableWidgetItem БОЛЬШЕ НЕ ИСПОЛЬЗУЕТСЯ.
    Вместо этого методы возвращают строки и тексты для ролей Display/ToolTip.
    Иконки теперь обрабатываются моделью (`LinksTableModel.data(DecorationRole)`).
    """

    # --- DisplayRole генерация ---
    def _star_display_text(self, is_favorite: bool) -> str:
        """Текст для столбца избранного (★ или пусто)."""
        return STAR_SYMBOL if is_favorite else ""

    def _name_display_text(self, link: Dict, mode: str) -> str:
        """Текст для названия. В режиме поиска добавляет трейл категории."""
        name_text = link.get("name", "")
        if mode == "search":
            trail = self._build_category_trail(link)
            if trail:
                name_text = f"{name_text} ({trail})"
        return name_text

    def _build_category_trail(self, link: Dict) -> str:
        """Строит путь категории для режима поиска."""
        parts = [
            link.get("sphere_name", ""),
            link.get("section_name", ""),
            link.get("category_name", ""),
        ]
        return PATH_SEPARATOR.join(filter(None, parts))

    def _last_used_display_text(self, last_used) -> str:
        """Форматированный текст для даты последнего использования."""
        from app.utils.system.date_utils import format_last_used
        try:
            return format_last_used(last_used)
        except Exception:
            return ""

    def _notes_display_and_tooltip(self, notes: str, truncate: bool = False) -> Tuple[str, str]:
        """Возвращает (display, tooltip) для заметок."""
        text = str(notes or "")
        if truncate and len(text) > MAX_NOTES_LENGTH:
            return text[:MAX_NOTES_LENGTH] + "...", text
        return text, (text or "")

    def _path_display_and_tooltip(self, link: Dict) -> Tuple[str, str]:
        """Возвращает (display, tooltip) для пути/URL."""
        url_or_path = link.get("url", "") or link.get("path", "")
        return url_or_path, (url_or_path or "")

    def _name_tooltip(self, link: Dict) -> str:
        """Tooltip для названия (URL/Путь)."""
        url_or_path = link.get("url", "") or link.get("path", "")
        return f"<b>URL/Путь:</b> {url_or_path}" if url_or_path else ""

    def build_row(self, link: Dict, mode: str = "normal") -> List:
        """DEPRECATED: ранее создавал список QTableWidgetItem.
        В модельно-индексной архитектуре используйте методы:
          - _star_display_text, _name_display_text, _last_used_display_text
          - _notes_display_and_tooltip, _path_display_and_tooltip, _name_tooltip
        Возвращает пустой список для совместимости.
        """
        logging.info("[ItemBuildersMixin] build_row() устарел и больше не используется")
        return []
