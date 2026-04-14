"""Focus guard to prevent unwanted focus changes.

Reusable event filter for protecting widgets from losing focus during
UI updates (e.g., combo box population).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class FocusGuard(QObject):
    """Event filter to prevent unwanted focus changes.

    Use case: Prevent combo boxes from stealing focus during UI updates
    (e.g., when populating hierarchy dropdowns in link dialog).

    Example:
        guard = FocusGuard(combo_box, url_field, duration_ms=300)
        # For 300ms, if combo_box tries to take focus, url_field keeps it
    """

    def __init__(
        self,
        protected_widget: QWidget,
        preferred_target: QWidget,
        duration_ms: int = 300,
        parent: QObject | None = None,
    ) -> None:
        """Initialize focus guard.

        Args:
            protected_widget: Widget to install filter on (will be blocked from taking focus)
            preferred_target: Widget that should keep focus
            duration_ms: How long to guard (default: 300ms)
            parent: Parent QObject (optional)

        Example:
            # Prevent section_cb from stealing focus from url_le for 300ms
            guard = FocusGuard(section_cb, url_le, duration_ms=300)
        """
        super().__init__(parent)
        self._protected_widget = protected_widget
        self._preferred_target = preferred_target
        self._active = True

        # Install event filter
        try:
            if protected_widget and not getattr(
                protected_widget, "_focus_guard_installed", False
            ):
                protected_widget.installEventFilter(self)
                protected_widget._focus_guard_installed = True  # type: ignore[attr-defined]
                logger.debug(
                    "FocusGuard installed on %s, protecting %s",
                    protected_widget,
                    preferred_target,
                )
        except Exception as e:
            logger.warning("Failed to install FocusGuard: %s", e)

        # Auto-disable after duration
        if duration_ms > 0:
            QTimer.singleShot(duration_ms, self._deactivate)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        """Intercept FocusIn events and restore preferred focus.

        Args:
            obj: Object that received the event
            event: Event to filter

        Returns:
            True if event was consumed, False otherwise
        """
        if not self._active:
            return False

        try:
            # If protected widget tries to grab focus, restore preferred target
            if event and event.type() == QEvent.Type.FocusIn:
                target = self._preferred_target
                if (
                    target is not None
                    and obj is not target
                    and obj == self._protected_widget
                ):
                    try:
                        if hasattr(target, "setFocus"):
                            target.setFocus(Qt.FocusReason.OtherFocusReason)
                            logger.debug(
                                "FocusGuard: Restored focus to %s (blocked %s)",
                                target,
                                obj,
                            )
                            return True  # Consume event
                    except RuntimeError:
                        # Widget was deleted
                        self._deactivate()
                    except Exception as e:
                        logger.debug("FocusGuard: Failed to restore focus: %s", e)
        except Exception as e:
            logger.debug("FocusGuard eventFilter error: %s", e)

        return False

    def _deactivate(self) -> None:
        """Deactivate the guard (called after timeout)."""
        self._active = False
        logger.debug("FocusGuard deactivated")

    def deactivate(self) -> None:
        """Manually deactivate the guard.

        Example:
            guard.deactivate()  # Stop guarding immediately
        """
        self._deactivate()

    def is_active(self) -> bool:
        """Check if guard is still active.

        Returns:
            True if guard is active

        Example:
            if guard.is_active():
                # Guard is still protecting
        """
        return self._active
