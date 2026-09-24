from __future__ import annotations

import html

from PyQt6.QtCore import QCoreApplication

from app.utils.links.type_labels import link_type_address_tooltip, translate_link_type_label

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

    def _last_used_tooltip(self, last_used) -> str:
        """Return a full local timestamp tooltip for the last-used value."""
        if not last_used:
            return ""
        try:
            from datetime import datetime

            return datetime.fromisoformat(str(last_used)).strftime("%d.%m.%Y %H:%M:%S")
        except Exception:
            return str(last_used)

    def _notes_display_and_tooltip(
        self, notes: str, truncate: bool = False
    ) -> tuple[str, str]:
        """Return the ``(display, tooltip)`` pair for notes."""
        raw_text = str(notes or "")
        clean_text = " ".join(raw_text.split())
        # Visual indicator in front of notes text (emoji icon)
        has_text = bool(clean_text)
        prefix = "📝 " if has_text else ""
        tooltip = raw_text.strip()
        if truncate and len(clean_text) > MAX_NOTES_LENGTH:
            return prefix + clean_text[:MAX_NOTES_LENGTH] + "...", tooltip
        return prefix + clean_text, tooltip

    def _path_display_and_tooltip(self, link: dict) -> tuple[str, str]:
        """Return the ``(display, tooltip)`` pair for path/URL."""
        url_or_path = link.get("url", "") or link.get("path", "")
        return url_or_path, (url_or_path or "")

    def _type_display_text(self, link: dict) -> str:
        """Return localized display text for the resource type."""
        return translate_link_type_label(link.get("type"))

    def _type_tooltip(self, link: dict) -> str:
        """Return resource address/details for the type column tooltip."""
        return link_type_address_tooltip(link)

    def _name_tooltip(self, link: dict) -> str:
        """Return informative card tooltip for the name column."""
        name = html.escape(str(link.get("name") or "").strip())
        url_or_path = html.escape(str(link.get("url", "") or link.get("path", "")).strip())
        if not name and not url_or_path:
            return ""

        rows: list[str] = []
        if name:
            rows.append(
                f"<tr><td colspan='2' style='font-weight: bold; font-size: 12px; padding-bottom: 4px;'>{name}</td></tr>"
            )
        if url_or_path:
            lbl_path = QCoreApplication.translate("ItemBuilders", "Path/URL:")
            rows.append(
                f"<tr><td style='color: #888888; padding-right: 8px; vertical-align: top;'>{lbl_path}</td>"
                f"<td style='word-break: break-all;'>{url_or_path}</td></tr>"
            )

        raw_args = str(link.get("args") or "").strip()
        is_admin = "--run-as-admin" in raw_args
        clean_args = raw_args.replace("--run-as-admin", "").strip()
        if clean_args:
            lbl_args = QCoreApplication.translate("ItemBuilders", "Arguments:")
            rows.append(
                f"<tr><td style='color: #888888; padding-right: 8px;'>{lbl_args}</td>"
                f"<td>{html.escape(clean_args)}</td></tr>"
            )

        browser_profile = str(link.get("browser_key") or "").strip()
        if browser_profile:
            lbl_prof = QCoreApplication.translate("ItemBuilders", "Profile:")
            rows.append(
                f"<tr><td style='color: #888888; padding-right: 8px;'>{lbl_prof}</td>"
                f"<td>{html.escape(browser_profile)}</td></tr>"
            )

        if is_admin:
            lbl_admin = QCoreApplication.translate("ItemBuilders", "🛡️ Run as administrator")
            rows.append(
                f"<tr><td colspan='2' style='color: #E5A93C; padding-top: 2px;'>{lbl_admin}</td></tr>"
            )

        table_content = "".join(rows)
        return f"<table style='min-width: 280px; max-width: 520px; margin: 2px;'>{table_content}</table>"
