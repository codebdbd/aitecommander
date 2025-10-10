"""Accessibility manager for top-bar components.

Provides keyboard navigation, screen-reader support, focus handling, and ARIA-like
metadata for top-bar panels.
"""

from __future__ import annotations

import logging
from typing import List, Optional
from weakref import WeakKeyDictionary

from PyQt6.QtCore import QObject, QEvent, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QToolButton, QWidget

logger = logging.getLogger(__name__)


class AccessibilityManager(QObject):
    """Manage accessibility for top-bar panels.

    Provides keyboard shortcuts (Alt+1-9), tab navigation, arrow-key navigation,
    screen-reader descriptions, and focus management.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the accessibility manager."""

        super().__init__(parent)
        self._shortcuts: List[QShortcut] = []
        self._button_shortcuts: "WeakKeyDictionary[QToolButton, QShortcut]" = WeakKeyDictionary()
        self._focused_panel: Optional[QWidget] = None
        self._focused_button_index = 0

    def setup_panel_accessibility(
        self,
        panel: QWidget,
        buttons: List[QToolButton],
        panel_name: str,
        visible_count: int,
        start_shortcut_number: int = 1,
    ) -> None:
        """Configure accessibility metadata, focus policy, and shortcuts."""

        if not panel or not buttons:
            return

        try:
            panel.setAccessibleName(panel_name)
            panel.setAccessibleDescription(
                self.tr("{panel} panel with {count} visible items").format(
                    panel=panel_name,
                    count=visible_count,
                )
            )

            for index, button in enumerate(buttons):
                is_visible = index < visible_count
                button.setAccessibleName(
                    self.tr("{panel} item {n}").format(panel=panel_name, n=index + 1)
                )

                if is_visible:
                    button.setAccessibleDescription(
                        self.tr(
                            "Button {idx} of {total} in {panel}. Press Enter to activate, Arrow keys to navigate."
                        ).format(idx=index + 1, total=visible_count, panel=panel_name)
                    )
                    button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

                    shortcut_num = start_shortcut_number + index
                    if shortcut_num <= 9:
                        self._create_button_shortcut(
                            button,
                            shortcut_num,
                            f"{panel_name} item {index + 1}"
                        )
                    else:
                        self._remove_button_shortcut(button)
                else:
                    self._remove_button_shortcut(button)
                    button.setAccessibleDescription(
                        self.tr("Hidden button {n} in {panel}").format(
                            n=index + 1, panel=panel_name
                        )
                    )
                    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

            self._setup_tab_order(buttons[:visible_count])
            logger.debug(
                "Accessibility setup for %s: %d visible buttons with shortcuts",
                panel_name,
                visible_count,
            )
        except (RuntimeError, AttributeError) as exc:
            logger.warning("Failed to setup accessibility for %s: %s", panel_name, exc)

    def _create_button_shortcut(
        self,
        button: QToolButton,
        number: int,
        description: str,
    ) -> None:
        """Bind ``Alt+number`` to activate the given button."""

        try:
            self._remove_button_shortcut(button)

            shortcut = QShortcut(QKeySequence(f"Alt+{number}"), button)
            shortcut.activated.connect(button.click)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self._shortcuts.append(shortcut)
            self._button_shortcuts[button] = shortcut

            current_tooltip = button.toolTip() or ""
            shortcut_info = self.tr(" (Alt+{n})").format(n=number)
            if shortcut_info not in current_tooltip:
                button.setToolTip(current_tooltip + shortcut_info)
        except (RuntimeError, AttributeError) as exc:
            logger.debug("Failed to create shortcut for button: %s", exc)

    def _setup_tab_order(self, buttons: List[QToolButton]) -> None:
        """Ensure tab navigation matches the visible-button order.

        Note: translated from the original Russian comment about tab traversal.
        """

        if len(buttons) < 2:
            return

        try:
            for first, second in zip(buttons, buttons[1:]):
                QWidget.setTabOrder(first, second)
        except (RuntimeError, AttributeError) as exc:
            logger.debug("Failed to setup tab order: %s", exc)

    def handle_arrow_navigation(
        self,
        event: QEvent,
        buttons: List[QToolButton],
        current_button: QToolButton,
    ) -> bool:
        """Handle arrow-key navigation within a panel.

        Note: translated from the original Russian description.
        """

        if event.type() != QEvent.Type.KeyPress:
            return False

        try:
            key = event.key()
            try:
                current_index = buttons.index(current_button)
            except ValueError:
                return False

            new_index = current_index
            if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
                new_index = (current_index + 1) % len(buttons)
            elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
                new_index = (current_index - 1) % len(buttons)
            elif key == Qt.Key.Key_Home:
                new_index = 0
            elif key == Qt.Key.Key_End:
                new_index = len(buttons) - 1
            else:
                return False

            if new_index != current_index:
                target = buttons[new_index]
                if target.isVisible() and target.isEnabled():
                    target.setFocus(Qt.FocusReason.KeyboardFocusReason)
                    return True
        except (RuntimeError, AttributeError) as exc:
            logger.debug("Failed to handle arrow navigation: %s", exc)

        return False

    def update_focus_after_visibility_change(
        self,
        buttons: List[QToolButton],
        visible_count: int,
    ) -> None:
        """Restore focus to the first visible button when needed."""

        if not buttons or visible_count <= 0:
            return

        try:
            focused_button = next((btn for btn in buttons if btn.hasFocus()), None)
            if focused_button and not focused_button.isVisible():
                first_visible = buttons[0] if visible_count > 0 else None
                if first_visible and first_visible.isVisible():
                    first_visible.setFocus(Qt.FocusReason.OtherFocusReason)
                    logger.debug(
                        "Focus moved to first visible button after visibility change"
                    )
        except (RuntimeError, AttributeError) as exc:
            logger.debug("Failed to update focus: %s", exc)

    def cleanup(self) -> None:
        """Detach shortcuts and reset state."""

        try:
            seen: set[int] = set()
            for shortcut in list(self._shortcuts):
                if shortcut is None:
                    continue
                ident = id(shortcut)
                if ident in seen:
                    continue
                seen.add(ident)
                self._dispose_shortcut(shortcut)
            self._shortcuts.clear()
            for shortcut in list(self._button_shortcuts.values()):
                ident = id(shortcut)
                if ident in seen:
                    continue
                self._dispose_shortcut(shortcut)
            self._button_shortcuts.clear()
            self._focused_panel = None
            logger.debug("AccessibilityManager cleanup completed")
        except Exception as exc:
            logger.warning("Error during AccessibilityManager cleanup: %s", exc)

    def __del__(self) -> None:
        """Destructor that performs best-effort cleanup."""

        try:
            self.cleanup()
        except Exception:
            pass

    def _remove_button_shortcut(self, button: QToolButton) -> None:
        """Remove an existing shortcut for the given button, if any."""
        try:
            shortcut = self._button_shortcuts.pop(button, None)
        except Exception:
            shortcut = None
        if shortcut is not None:
            self._dispose_shortcut(shortcut)
            try:
                self._shortcuts.remove(shortcut)
            except ValueError:
                pass

    @staticmethod
    def _dispose_shortcut(shortcut: QShortcut) -> None:
        """Safely disable and delete a shortcut instance."""
        try:
            shortcut.setEnabled(False)
        except RuntimeError:
            pass
        try:
            shortcut.deleteLater()
        except RuntimeError:
            pass
