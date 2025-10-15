from __future__ import annotations

import logging
from collections.abc import Iterable
from functools import wraps
from typing import Callable

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import (
    QToolButton,
    QWidget,
)

from .accessibility_manager import AccessibilityManager
from ..models.panel_state import PanelState
from ..utils.qt_utils import is_deleted
from .width_calculator import WidthCalculator

logger = logging.getLogger(__name__)


def safe_widget_operation(func: Callable) -> Callable:
    """Decorator that guards Qt widget operations.

    Fix: automatically verifies that the widget is not ``None`` or deleted to
    avoid ``RuntimeError`` on dangling Qt objects.
    """

    @wraps(func)
    def wrapper(self, widget: QWidget | None, *args, **kwargs):
        if widget is None or is_deleted(widget):
            logger.debug(f"{func.__name__}: widget is None or deleted")
            # Return a sensible default
            if func.__name__.startswith("get"):
                return None
            elif func.__name__.startswith("set") or func.__name__.startswith("apply"):
                return 0
            return None
        try:
            return func(self, widget, *args, **kwargs)
        except (RuntimeError, AttributeError) as e:
            logger.debug(f"{func.__name__}: operation failed - {e}")
            if func.__name__.startswith("get"):
                return None
            return 0

    return wrapper


class PanelVisibilityManager:
    """Manage panel buttons and their animations.

    Responsibilities:
    - Find panel buttons
    - Toggle button visibility
    - Animate show/hide transitions
    - Constrain panel widths
    """

    def __init__(
        self, width_calculator: WidthCalculator, parent: QWidget | None = None
    ):
        """Initialize panel-visibility manager.

        Fix: include ``AccessibilityManager`` for complete accessibility support.

        Args:
            width_calculator: Panel width calculator.
            parent: Parent widget used by the accessibility manager.
        """
        self._width_calculator = width_calculator
        # Fix: instantiate accessibility manager
        self._accessibility_manager = AccessibilityManager(parent)

    def iter_buttons(
        self, panel_widget: QWidget | None, object_name: str
    ) -> list[QToolButton]:
        """Find all buttons with the given ``objectName`` inside a panel.

        Fix: add checks for deleted objects.

        Args:
            panel_widget: Panel widget.
            object_name: Target button ``objectName`` to locate.

        Returns:
            List of matching buttons.
        """
        if not panel_widget or is_deleted(panel_widget):
            return []

        buttons: list[QToolButton] = []
        bg = getattr(panel_widget, "bg_frame", None)

        if bg and isinstance(bg, QWidget) and not is_deleted(bg):
            try:
                layout = bg.layout()
                if layout:
                    for index in range(layout.count()):
                        item = layout.itemAt(index)
                        if item:
                            widget = item.widget()
                            if (
                                isinstance(widget, QToolButton)
                                and not is_deleted(widget)
                                and widget.objectName() == object_name
                            ):
                                buttons.append(widget)
            except (RuntimeError, AttributeError):
                pass

        # Fallback: search via ``findChildren``
        try:
            for button in panel_widget.findChildren(QToolButton, object_name):
                if button not in buttons and not is_deleted(button):
                    buttons.append(button)
        except (RuntimeError, AttributeError):
            pass

        return buttons

    @safe_widget_operation
    def set_visible_count(
        self, panel_widget: QWidget | None, buttons: list[QToolButton], count: int
    ) -> int:
        """Set the number of visible buttons within the panel.

        Fix: protect against deleted widgets via ``@safe_widget_operation`` and set
        baseline accessibility metadata for screen readers.
        """
        if not buttons:
            self._ensure_panel_visible(panel_widget)
            return 0
        visible = max(0, min(count, len(buttons)))
        for index, button in enumerate(buttons):
            if not is_deleted(button):
                try:
                    is_visible = index < visible
                    button.setVisible(is_visible)

                    # Fix: baseline accessibility attributes (full setup occurs in
                    # ``AccessibilityManager`` via ``apply_counts``)
                    if is_visible:
                        button.setAccessibleDescription(
                            QCoreApplication.translate(
                                "TopBarPanels",
                                "Button {idx} of {total} visible buttons",
                            ).format(idx=index + 1, total=visible)
                        )
                    else:
                        button.setAccessibleDescription(
                            QCoreApplication.translate("TopBarPanels", "Hidden button")
                        )
                except (RuntimeError, AttributeError):
                    pass

        self._ensure_panel_visible(panel_widget)

        # Fix: refresh focus after visibility changes
        try:
            self._accessibility_manager.update_focus_after_visibility_change(
                buttons, visible
            )
        except Exception as e:
            logger.debug("Failed to update focus: %s", e)

        return visible

    def apply_counts(
        self,
        panel_states: Iterable[PanelState],
        counts: dict[str, int],
    ) -> dict[str, int]:
        """Apply visible button counts across all panels.

        Fix: configure full accessibility metadata per panel.
        """
        applied: dict[str, int] = {}
        shortcut_counter = 1  # Counter for keyboard shortcuts

        for state in panel_states:
            visible = self.set_visible_count(
                state.widget,
                state.buttons,
                counts.get(state.definition.label, 0),
            )
            # Apply panel width bounds after adjusting button visibility
            self._apply_panel_width_bounds(state.widget, state.buttons, visible)
            applied[state.definition.label] = visible

            # Fix: configure full accessibility for the panel
            try:
                # Translated panel display names
                panel_name_map = {
                    "recent": QCoreApplication.translate(
                        "TopBarPanels", "Recent Links"
                    ),
                    "fav": QCoreApplication.translate("TopBarPanels", "Favorites"),
                    "quick": QCoreApplication.translate("TopBarPanels", "Quick Add"),
                }
                panel_name = panel_name_map.get(
                    state.definition.label, state.definition.label
                )

                self._accessibility_manager.setup_panel_accessibility(
                    state.widget,
                    state.buttons,
                    panel_name,
                    visible,
                    start_shortcut_number=shortcut_counter,
                )

                # Increment counter for the next panel
                shortcut_counter += visible

            except Exception as e:
                logger.debug(
                    "Failed to setup accessibility for %s: %s",
                    state.definition.label,
                    e,
                )

        return applied

    def retranslate_panels(
        self,
        panel_states: Iterable[PanelState],
        visible_counts: dict[str, int],
    ) -> None:
        """Re-apply accessibility metadata with translated panel names.

        Called when the application language changes.
        """
        try:
            panel_name_map = {
                "recent": QCoreApplication.translate("TopBarPanels", "Recent Links"),
                "fav": QCoreApplication.translate("TopBarPanels", "Favorites"),
                "quick": QCoreApplication.translate("TopBarPanels", "Quick Add"),
            }
            shortcut_counter = 1
            for state in panel_states:
                panel_name = panel_name_map.get(
                    state.definition.label, state.definition.label
                )
                visible = int(visible_counts.get(state.definition.label, 0))
                self._accessibility_manager.setup_panel_accessibility(
                    state.widget,
                    state.buttons,
                    panel_name,
                    visible,
                    start_shortcut_number=shortcut_counter,
                )
                shortcut_counter += visible
        except Exception as e:
            logger.debug("Failed to retranslate panels: %s", e)

    @safe_widget_operation
    def _apply_panel_width_bounds(
        self, panel: QWidget | None, buttons: list[QToolButton], visible: int
    ) -> None:
        """Set panel width bounds based on visible buttons.

        Fix: guard execution with ``@safe_widget_operation`` to handle deleted widgets.
        """
        try:
            panel.setMinimumWidth(0)
            max_width = (
                self._width_calculator.panel_width(panel, buttons, visible)
                if visible > 0
                else 0
            )
            panel.setMaximumWidth(max_width)
            # One-time diagnostics for favorites/quick panels to catch sizing root cause
            try:
                name = getattr(panel, "objectName", lambda: "")() or ""
            except Exception:
                name = ""
            low = name.lower()
            if ("fav" in low or "quick" in low) and not bool(
                getattr(panel, "_dbg_logged_once", False)
            ):
                try:
                    # Collect current visible buttons and their ``sizeHint`` values
                    visible_btns = []
                    for _i, b in enumerate(buttons):
                        try:
                            if b.isVisible():
                                visible_btns.append(int(b.sizeHint().width()))
                        except Exception:
                            pass
                    panel_hint = 0
                    try:
                        panel_hint = int(panel.sizeHint().width())
                    except Exception:
                        pass
                    logger.info(
                        "[TopbarDiag:%s] visible=%s widths=%s "
                        "computed_max=%s panel_hint=%s margins(panel)=%s",
                        low,
                        visible,
                        visible_btns,
                        max_width,
                        panel_hint,
                        getattr(panel, "contentsMargins", lambda: None)(),
                    )
                except Exception:
                    pass
                try:
                    panel._dbg_logged_once = True
                except Exception:
                    pass
        except (RuntimeError, AttributeError):
            pass

    @safe_widget_operation
    def _ensure_panel_visible(self, panel_widget: QWidget | None) -> None:
        """Ensure that the panel itself stays visible.

        Fix: guard the call with ``@safe_widget_operation`` to handle deleted widgets.
        """
        try:
            panel_widget.setVisible(True)
        except (RuntimeError, AttributeError):
            pass
        try:
            panel_widget.updateGeometry()
        except (RuntimeError, AttributeError):
            pass
