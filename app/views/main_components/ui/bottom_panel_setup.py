# app/views/main_components/bottom_panel_setup.py
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from app.config_data import app_config

logger = logging.getLogger(__name__)


@runtime_checkable
class WindowUISetupProtocol(Protocol):
    """Protocol for WindowUISetup to enable better type checking without circular imports."""
    window: QWidget
    main_layout: Any  # Typically QVBoxLayout
    fonts: Any  # Typically dict with 'bottom_bar_button_px'


class BottomPanelBuilder:
    """Build the bottom panel using existing WindowUISetup behavior (no changes)."""

    def __init__(self, ui: WindowUISetupProtocol) -> None:
        self.ui = ui
        self.window = ui.window
        self.main_layout = ui.main_layout

    def build(self) -> None:
        """Construct and attach the bottom panel (action strip + separator).

        Responsibilities:
        - Create a bottom layout with margins/spacing from UIConfig
        - Build action buttons from `bottom_actions` and connect click handlers
        - Create `bottom_bar_container`, set size policy, and add to the main layout
        - Add a separator widget below the panel

        Note: preserves existing behavior including focus policies and error handling.
        """
        bottom_layout = QHBoxLayout()
        # Tight fit: no inner margins and no inter-button gap
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        # Bottom bar font is centralized via ui.fonts.bottom_bar_button_px (ThemeController)
        # Apply the font here for consistency (if not handled by QSS)
        if hasattr(self.ui, 'fonts') and hasattr(self.ui.fonts, 'bottom_bar_button_px'):
            bottom_font = self.ui.fonts.bottom_bar_button_px
            # Note: in practice apply via QApplication.setFont or stylesheet

        # Switch-sphere button (created after controllers init)
        # Add a placeholder for future insertion (e.g., at the start of the layout)
        self.window.switch_sphere_button = None
        placeholder = QWidget()  # Temporary spacer for the future button
        placeholder.setFixedWidth(0)  # Takes no space initially
        placeholder.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        bottom_layout.addWidget(placeholder)

        # Additional buttons from configuration (cached for performance)
        bottom_actions = app_config.ui.get_bottom_actions()
        bottom_btns: list[QPushButton] = []
        for text, fn_name in bottom_actions:
            btn = QPushButton(text)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # Accessibility: add accessible name for screen readers
            btn.setAccessibleName(text)
            btn.setAccessibleDescription(f"Action button: {text}")
            # Allow horizontal shrink below sizeHint
            try:
                btn.setMinimumWidth(0)
                btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            except (RuntimeError, TypeError) as e:
                logger.debug(
                    "BottomPanel: failed to apply size policy to bottom button '%s': %s",
                    text, e,
                    exc_info=True,
                )
            # Connect click handler and add to the panel
            handler = getattr(self.window, fn_name, None)
            if not callable(handler):
                logger.warning(
                    "BottomPanel: click handler '%s' not found for button '%s' — skipping",
                    fn_name, text,
                )
                continue
            try:
                btn.clicked.connect(handler)
            except (TypeError, RuntimeError) as e:
                logger.warning(
                    "BottomPanel: failed to connect handler '%s' for button '%s': %s — skipping",
                    fn_name, text, e,
                    exc_info=True,
                )
                continue
            bottom_layout.addWidget(btn)
            bottom_btns.append(btn)

        # Mark the last button to remove its right border via QSS
        if bottom_btns:
            try:
                bottom_btns[-1].setProperty("last", "1")
            except (RuntimeError, AttributeError) as e:
                logger.debug(
                    "BottomPanel: failed to set 'last' property on final button: %s",
                    e, exc_info=True,
                )

        # Container for bottom bar
        container_parent = (
            getattr(self.main_layout, "parentWidget", lambda: None)()
            or self.window.centralWidget()
        )
        bottom_bar_container = QWidget(container_parent)
        bottom_bar_container.setObjectName("bottomBarContainer")
        bottom_bar_container.setLayout(bottom_layout)
        # Store the widget on the window for further focus configuration
        self.window.bottom_bar_container = bottom_bar_container
        # Explicit policy: horizontal expanding/shrinking, vertical fixed
        try:
            bottom_bar_container.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
        except (RuntimeError, TypeError) as e:
            logger.debug(
                "BottomPanel: failed to set size policy on bottom bar container: %s",
                e, exc_info=True,
            )

        # Add the container into the main layout (at the end, before a separator if present)
        self.main_layout.addWidget(bottom_bar_container)

        # Remove the bottom separator: the panel should adjoin the content
        # Find a separator by objectName (assume it was added earlier as "bottomSeparator")
        # For robustness: search among layout children
        separator = self._find_separator_in_layout(self.main_layout)
        if separator:
            try:
                self.main_layout.removeWidget(separator)
                separator.setParent(None)  # Release resources
                separator.deleteLater()  # Qt idiom for deferred deletion
                logger.debug("BottomPanel: removed bottom separator")
            except (RuntimeError, AttributeError) as e:
                logger.warning("BottomPanel: failed to remove bottom separator: %s", e)
        else:
            logger.debug("BottomPanel: no bottom separator found to remove")

    def _find_separator_in_layout(self, layout: Any) -> QWidget | None:
        """Helper: find a separator in the layout by objectName."""
        if not hasattr(layout, 'itemAt') or not callable(layout.itemAt):
            return None
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            widget = item.widget()
            if isinstance(widget, QWidget) and widget.objectName() == "bottomSeparator":
                return widget
        return None

    def add_switch_sphere_button(self, button: QPushButton) -> None:
        """Add a sphere-switch button at the beginning of the bottom layout (after the placeholder)."""
        if not hasattr(self.window, 'bottom_bar_container') or self.window.bottom_bar_container is None:
            logger.warning("BottomPanel: cannot add switch button - container not built yet")
            return
        bottom_layout = self.window.bottom_bar_container.layout()
        if bottom_layout is None or not isinstance(bottom_layout, QHBoxLayout):
            logger.warning("BottomPanel: invalid layout for adding switch button")
            return
        # Find the placeholder (first widget)
        if bottom_layout.count() > 0:
            placeholder_item = bottom_layout.itemAt(0)
            if placeholder_item and placeholder_item.widget():
                # Insert the button before the placeholder and remove the placeholder
                bottom_layout.insertWidget(0, button)
                bottom_layout.removeWidget(placeholder_item.widget())
                placeholder_item.widget().setParent(None)
                placeholder_item.widget().deleteLater()
                self.window.switch_sphere_button = button
                logger.debug("BottomPanel: added switch sphere button")
            else:
                # Fallback: add at the beginning
                bottom_layout.insertWidget(0, button)
                self.window.switch_sphere_button = button
                logger.debug("BottomPanel: added switch sphere button (fallback)")