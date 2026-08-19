"""Mixin for switching link types and refreshing UI in `LinkDialogHandlers`."""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon

from app.models import LinkType
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.ui_helpers import set_icon_to_button

logger = logging.getLogger(__name__)


class TypeChangeMixin:
    def on_type_changed(self, link_type) -> None:
        """Handle link type change."""
        lt = LinkType.from_value(link_type)
        self.dialog.link_type = lt

        # Clear fields when type changes
        self.dialog.ui.set_widget_value("url_le", "")
        self.dialog.ui.set_widget_value("name_le", "")
        self.dialog.ui.set_widget_value("args_le", "")

        # Reset processing state so auto-fill can run again
        self._last_processed_path = ""
        self._is_processing = False

        # Cancel active worker when link type changes
        if self._active_worker:
            try:
                self._active_worker.cancel()
            except (AttributeError, RuntimeError) as e:
                logger.debug("Failed to cancel active worker: %s", e)
            self._active_worker = None

        # Set default icon via centralized resolver
        try:
            resolved_icon_path = resolve_icon_for_link(
                {"type": lt.value, "icon_path": ""}
            )
        except (AttributeError, KeyError, ValueError) as e:
            logger.warning("Failed to resolve icon for type %s: %s", link_type, e)
            resolved_icon_path = ""
        self.dialog.icon_name = (
            Path(resolved_icon_path).name if resolved_icon_path else ""
        )
        if resolved_icon_path and Path(resolved_icon_path).exists():
            set_icon_to_button(self.dialog._get_icon_btn(), resolved_icon_path)
        else:
            self.dialog._get_icon_btn().setIcon(QIcon())

        self._update_ui_state()

    def _update_ui_state(self) -> None:
        """Update UI state according to link type."""
        lt = LinkType.from_value(self.dialog.link_type)
        is_web = lt == LinkType.WEB
        profile_btn = self.dialog._get_profile_btn()
        browse_btn = self.dialog._get_browse_btn()
        args_le = self.dialog._get_args_le()
        args_label = self.dialog._get_args_label()

        profile_btn.setVisible(is_web)

        # "Browse" button is shown only for specific types
        browse_btn.setVisible(
            lt
            in (
                LinkType.FILE,
                LinkType.FOLDER,
                LinkType.PROGRAM,
                LinkType.SCRIPT,
            )
        )

        # Arguments: combo for Web (stack index 0), plain field for Program/Script (index 1)
        args_supported_types = (
            LinkType.SCRIPT,
            LinkType.WEB,
            LinkType.PROGRAM,
        )
        show_args = lt in args_supported_types
        args_stack = self.dialog.ui.widgets.get("args_stack")
        if args_stack is not None:
            args_stack.setVisible(show_args)
            if show_args:
                args_stack.setCurrentIndex(0 if lt == LinkType.WEB else 1)
        else:
            args_le.setVisible(show_args)
        args_label.setVisible(show_args)

        # Focus depending on type: WEB -> URL field, otherwise -> "Browse" button
        def _apply_focus():
            try:
                if lt == LinkType.WEB:
                    target = self.dialog._get_url_le()
                    target.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
                else:
                    target = self.dialog._get_browse_btn()
                    target.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
                # Hold preferred focus briefly so hierarchy updates do not steal it
                try:
                    self.dialog._preferred_focus_widget = target
                    QTimer.singleShot(
                        300,
                        lambda: setattr(self.dialog, "_preferred_focus_widget", None),
                    )
                except Exception:
                    pass
            except Exception:
                pass

        try:
            QTimer.singleShot(10, _apply_focus)
        except Exception:
            _apply_focus()

    def set_link_type(self, link_type) -> None:
        """Programmatically set link type and update UI."""
        # Safely obtain available types from dialog
        try:
            link_types = getattr(self.dialog, "link_types", None)
        except (AttributeError, RuntimeError):
            link_types = None

        if not link_types:
            return

        # Normalize `link_types` to a set of type codes (strings)
        codes = set()
        try:
            for item in link_types:
                if isinstance(item, (list, tuple)):
                    if len(item) >= 1:
                        codes.add(item[0])
                elif isinstance(item, dict):
                    code = item.get("code") or item.get("id") or item.get("type")
                    if code:
                        codes.add(code)
                else:
                    # String or scalar
                    codes.add(str(item))
        except (TypeError, ValueError, AttributeError) as e:
            # Fail silently without changing state in ambiguous cases
            logger.debug("set_link_type: failed to normalize link_types: %s", e)
            return

        # Support external calls using both strings and Enum values
        lt = LinkType.from_value(link_type)
        if lt.value not in codes:
            return

        type_group = self.dialog.ui.widgets["type_group"]
        for btn in type_group.buttons():
            if btn.property("link_type") == lt.value:
                btn.setChecked(True)
                break

        # Preserve backward compatibility: call handler with the original value
        # (string) because tests expect a string argument.
        self.on_type_changed(link_type)
