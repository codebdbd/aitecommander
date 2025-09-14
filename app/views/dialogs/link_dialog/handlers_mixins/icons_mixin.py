"""
Миксин для выбора и установки пользовательской иконки в LinkDialogHandlers.
"""

from typing import Any, Protocol

from PyQt6.QtGui import QIcon

from app.utils.ui.icon.selection import choose_icon_and_copy


class _HasDialog(Protocol):
    dialog: Any


class IconsMixin:
    def _on_choose_icon(self: _HasDialog) -> None:
        """Обработчик выбора иконки."""
        user_icons_dir = self.dialog.get_user_icons_dir()
        # Фильтр формируется динамически на основе app_config.get_supported_icon_formats()
        fname, icon = choose_icon_and_copy(self.dialog, user_icons_dir)
        if not fname or not icon:
            return

        self.dialog.icon_name = fname
        btn = self.dialog._get_icon_btn()
        btn.setIcon(icon if icon else QIcon())
