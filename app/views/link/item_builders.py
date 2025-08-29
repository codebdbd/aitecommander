"""
Утилиты генерации текстов и tooltip'ов для ролей модели (QAbstractTableModel).
"""

from typing import Dict, Tuple

# Константы для магических чисел
MAX_NOTES_LENGTH = 462
STAR_SYMBOL = "★"
STAR_COLOR = "#FFD700"
PATH_SEPARATOR = " → "


class ItemBuildersMixin:
    """Миксин-утилиты для генерации данных под роли модели.
    Методы возвращают строки и тексты для ролей Display/ToolTip.
    Иконки обрабатываются в модели (`LinksTableModel.data(DecorationRole)`).
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
        """Tooltip для названия: показываем именно название, а не адрес."""
        name = link.get("name", "")
        return str(name or "")
