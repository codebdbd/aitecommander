"""Centralized focus management for the application.

Provides a single API for all focus operations with automatic scheduling,
logging, and conflict prevention.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtWidgets import QApplication

from .widget_registry import WidgetRegistry, WidgetType

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

# Global singleton instance
_focus_manager_instance: FocusManager | None = None


class FocusManager(QObject):
    """Centralized focus management for the application.

    Features:
    - Scheduled focus setting (prevents race conditions)
    - Widget type detection
    - Focus history tracking
    - Debug logging

    Example:
        manager = get_focus_manager()
        manager.set_focus(tree_widget, widget_name="structure_tree")
    """

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize focus manager.

        Args:
            parent: Parent QObject (optional)
        """
        super().__init__(parent)
        self._focus_history: list[tuple[WidgetType, str]] = []
        self._max_history = 10
        self._debug_mode = False
        self._focus_guard_deadline = 0.0
        self._focus_guard_window_sec = 0.5

    def _set_focus_guard(self, origin: str) -> None:
        if origin in {"user", "user_action", "action"}:
            self._focus_guard_deadline = time.monotonic() + self._focus_guard_window_sec

    def _should_skip_focus(self, origin: str) -> bool:
        if origin in {"restore", "auto", "navigation"}:
            return time.monotonic() < self._focus_guard_deadline
        return False

    def set_focus(
        self,
        widget: QWidget,
        *,
        reason: Qt.FocusReason = Qt.FocusReason.OtherFocusReason,
        scheduled: bool = True,
        widget_name: str | None = None,
        origin: str = "auto",
    ) -> None:
        """Set focus to widget with optional scheduling.

        Args:
            widget: Target widget
            reason: Focus reason (default: OtherFocusReason)
            scheduled: Use TaskScheduler (default: True, recommended)
            widget_name: Optional name for logging

        Example:
            # Scheduled (recommended)
            manager.set_focus(tree_widget, widget_name="structure_tree")

            # Immediate (use sparingly)
            manager.set_focus(dialog_field, scheduled=False,
                            reason=Qt.FocusReason.ActiveWindowFocusReason)
        """
        if widget is None:
            logger.warning("set_focus called with None widget")
            return

        try:
            widget_type = WidgetRegistry.get_type(widget)
            display_name = widget_name or widget_type.value
            self._set_focus_guard(origin)

            if scheduled:
                # Use existing TaskScheduler infrastructure
                from app.controllers.ui.state.task_scheduler import schedule_focus

                def _set_focus_impl():
                    try:
                        if self._should_skip_focus(origin):
                            if self._debug_mode:
                                logger.info(
                                    "Focus skipped (%s): %s", origin, display_name
                                )
                            return
                        if widget and hasattr(widget, "setFocus"):
                            widget.setFocus(reason)
                            self._record_focus_change(widget_type, display_name)
                            if self._debug_mode:
                                logger.info(
                                    "Focus set (scheduled): %s [%s]",
                                    display_name,
                                    reason.name,
                                )
                    except RuntimeError:
                        # Widget was deleted before focus could be set
                        logger.debug("Widget deleted before focus: %s", display_name)
                    except Exception as e:
                        logger.warning(
                            "Failed to set focus to %s: %s", display_name, e
                        )

                schedule_focus(_set_focus_impl, display_name)
            else:
                # Immediate focus (not recommended except for dialogs)
                if self._should_skip_focus(origin):
                    if self._debug_mode:
                        logger.info("Focus skipped (%s): %s", origin, display_name)
                    return
                widget.setFocus(reason)
                self._record_focus_change(widget_type, display_name)
                if self._debug_mode:
                    logger.info(
                        "Focus set (immediate): %s [%s]", display_name, reason.name
                    )

        except Exception as e:
            logger.error("set_focus failed for %s: %s", widget_name or "unknown", e)

    def get_focused_widget_type(self) -> WidgetType:
        """Get type of currently focused widget.

        Returns:
            WidgetType enum value (UNKNOWN if not registered)

        Example:
            if manager.get_focused_widget_type() == WidgetType.STRUCTURE_TREE:
                # Tree has focus
        """
        try:
            focused = QApplication.focusWidget()
            if focused is None:
                return WidgetType.UNKNOWN
            return WidgetRegistry.get_type(focused)
        except Exception as e:
            logger.debug("Failed to get focused widget type: %s", e)
            return WidgetType.UNKNOWN

    def is_widget_focused(self, widget: QWidget) -> bool:
        """Check if widget or its children have focus.

        Args:
            widget: Widget to check

        Returns:
            True if widget or any child has focus

        Example:
            if manager.is_widget_focused(tree_widget):
                # Tree or its children have focus
        """
        if widget is None:
            return False

        try:
            focused = QApplication.focusWidget()
            if focused is None:
                return False

            # Check if widget itself has focus
            if hasattr(widget, "hasFocus") and widget.hasFocus():
                return True

            # Check if focused widget is a child
            if hasattr(widget, "isAncestorOf") and widget.isAncestorOf(focused):
                return True

            return False
        except Exception as e:
            logger.debug("is_widget_focused check failed: %s", e)
            return False

    def is_type_focused(self, widget_type: WidgetType) -> bool:
        """Check if widget of given type has focus.

        Args:
            widget_type: Type to check

        Returns:
            True if widget of this type has focus

        Example:
            if manager.is_type_focused(WidgetType.LINKS_TABLE):
                # Table has focus
        """
        try:
            widget = WidgetRegistry.get_widget(widget_type)
            if widget is None:
                return False
            return self.is_widget_focused(widget)
        except Exception as e:
            logger.debug("is_type_focused check failed: %s", e)
            return False

    def get_focus_history(self) -> list[tuple[WidgetType, str]]:
        """Get recent focus history for debugging.

        Returns:
            List of (widget_type, widget_name) tuples, most recent last

        Example:
            history = manager.get_focus_history()
            for widget_type, name in history:
                logger.debug("Focus: %s (%s)", name, widget_type.value)
        """
        return list(self._focus_history)

    def enable_debug_mode(self, enabled: bool = True) -> None:
        """Enable verbose focus change logging.

        Args:
            enabled: True to enable debug logging

        Example:
            manager.enable_debug_mode(True)  # Enable
            manager.enable_debug_mode(False)  # Disable
        """
        self._debug_mode = enabled
        logger.info("Focus debug mode: %s", "enabled" if enabled else "disabled")

    def get_focus_report(self) -> str:
        """Generate human-readable focus state report.

        Returns:
            Multi-line string with current focus state

        Example:
            logger.debug("%s", manager.get_focus_report())
        """
        lines = ["=== Focus State Report ==="]

        # Current focus
        try:
            focused = QApplication.focusWidget()
            if focused:
                widget_type = WidgetRegistry.get_type(focused)
                lines.append(f"Current focus: {focused} ({widget_type.value})")
            else:
                lines.append("Current focus: None")
        except Exception as e:
            lines.append(f"Current focus: Error ({e})")

        # Registered widgets
        lines.append("\nRegistered widgets:")
        for wtype in WidgetType:
            if wtype == WidgetType.UNKNOWN:
                continue
            widget = WidgetRegistry.get_widget(wtype)
            status = "✓" if widget else "✗"
            lines.append(f"  {status} {wtype.value}")

        # Focus history
        if self._focus_history:
            lines.append("\nRecent focus history:")
            for widget_type, name in self._focus_history[-5:]:
                lines.append(f"  → {name} ({widget_type.value})")
        else:
            lines.append("\nNo focus history")

        return "\n".join(lines)

    def _record_focus_change(self, widget_type: WidgetType, widget_name: str) -> None:
        """Record focus change in history.

        Args:
            widget_type: Type of widget that received focus
            widget_name: Display name of widget
        """
        try:
            self._focus_history.append((widget_type, widget_name))
            # Keep only last N entries
            if len(self._focus_history) > self._max_history:
                self._focus_history = self._focus_history[-self._max_history :]
        except Exception as e:
            logger.debug("Failed to record focus change: %s", e)


def get_focus_manager() -> FocusManager:
    """Get global FocusManager instance.

    Returns:
        Singleton FocusManager instance

    Example:
        manager = get_focus_manager()
        manager.set_focus(widget)
    """
    global _focus_manager_instance
    if _focus_manager_instance is None:
        _focus_manager_instance = FocusManager()
    return _focus_manager_instance
