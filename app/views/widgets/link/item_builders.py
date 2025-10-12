"""Utilities for generating display text and tooltips for model roles (``QAbstractTableModel``)."""


# Constants for magic numbers
MAX_NOTES_LENGTH = 462
# Favorite marker: heart symbol instead of the default star
STAR_SYMBOL = "♥"
STAR_COLOR = "#FFD700"
PATH_SEPARATOR = " → "


class ItemBuildersMixin:
    """Utility mixin for building model role data.

    Methods return strings and tooltips for ``DisplayRole`` / ``ToolTipRole``.
    Icons are handled inside the model (`LinksTableModel.data(DecorationRole)`).
    """

    # --- DisplayRole generation ---
    def _star_display_text(self, is_favorite: bool) -> str:
        """Return text for the favorites column (★ or blank)."""
        return STAR_SYMBOL if is_favorite else ""

    def _name_display_text(self, link: dict, mode: str) -> str:
        """Return the name text; append category trail in search mode."""
        name_text = link.get("name", "")
        if mode == "search":
            trail = self._build_category_trail(link)
            if trail:
                name_text = f"{name_text} ({trail})"
        return name_text

    def _build_category_trail(self, link: dict) -> str:
        """Construct the category trail for search mode."""
        parts = [
            link.get("sphere_name", ""),
            link.get("section_name", ""),
            link.get("category_name", ""),
        ]
        return PATH_SEPARATOR.join(filter(None, parts))

    def _last_used_display_text(self, last_used) -> str:
        """Return formatted text representing the last-used timestamp."""
        from app.utils.system.date_utils import format_last_used

        try:
            return format_last_used(last_used)
        except Exception:
            return ""

    def _notes_display_and_tooltip(
        self, notes: str, truncate: bool = False
    ) -> tuple[str, str]:
        """Return the ``(display, tooltip)`` pair for notes."""
        text = str(notes or "")
        # Visual indicator in front of notes text (emoji icon)
        has_text = bool(text)
        prefix = "📝 " if has_text else ""
        if truncate and len(text) > MAX_NOTES_LENGTH:
            return prefix + text[:MAX_NOTES_LENGTH] + "...", text
        return prefix + text, (text or "")

    def _path_display_and_tooltip(self, link: dict) -> tuple[str, str]:
        """Return the ``(display, tooltip)`` pair for path/URL."""
        url_or_path = link.get("url", "") or link.get("path", "")
        return url_or_path, (url_or_path or "")

    def _name_tooltip(self, link: dict) -> str:
        """Return tooltip for the name column (URL/Path)."""
        url_or_path = link.get("url", "") or link.get("path", "")
        return f"<b>URL/Path:</b> {url_or_path}" if url_or_path else ""
