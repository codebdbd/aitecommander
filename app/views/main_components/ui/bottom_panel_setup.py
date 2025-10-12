# app/views/main_components/bottom_panel_setup.py
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, Qt
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from app.config_data import app_config

logger = logging.getLogger(__name__)


_BOTTOM_PANEL_CONTEXT = "BottomPanel"

_BOTTOM_ACTION_TEXTS: dict[str, str] = {
    "add_section": QT_TRANSLATE_NOOP(_BOTTOM_PANEL_CONTEXT, "Add Section"),
    "add_category": QT_TRANSLATE_NOOP(_BOTTOM_PANEL_CONTEXT, "Add Category"),
    "add_link": QT_TRANSLATE_NOOP(_BOTTOM_PANEL_CONTEXT, "Add Link"),
    "edit_link": QT_TRANSLATE_NOOP(_BOTTOM_PANEL_CONTEXT, "Edit"),
    "delete_link": QT_TRANSLATE_NOOP(_BOTTOM_PANEL_CONTEXT, "Delete"),
}

_BOTTOM_ACTION_TOOLTIPS: dict[str, str] = {
    "add_section": QT_TRANSLATE_NOOP(_BOTTOM_PANEL_CONTEXT, "Create a new section."),
    "add_category": QT_TRANSLATE_NOOP(_BOTTOM_PANEL_CONTEXT, "Create a new category in the selected section."),
    "add_link": QT_TRANSLATE_NOOP(_BOTTOM_PANEL_CONTEXT, "Create a new link."),
    "edit_link": QT_TRANSLATE_NOOP(_BOTTOM_PANEL_CONTEXT, "Edit the selected item."),
    "delete_link": QT_TRANSLATE_NOOP(_BOTTOM_PANEL_CONTEXT, "Delete the selected item."),
}

_ACTION_BUTTON_DESC_TEMPLATE = QT_TRANSLATE_NOOP(
    _BOTTOM_PANEL_CONTEXT, "Action button: {label}"
)


def _format_with_shortcut(label: str, shortcut: str | None) -> str:
    label = label or ""
    shortcut_clean = (shortcut or "").strip()
    if shortcut_clean and shortcut_clean not in label:
        return f"{label} ({shortcut_clean})"
    return label


def _resolve_label(action_id: str | None, fallback_label: str | None) -> str:
    if action_id and action_id in _BOTTOM_ACTION_TEXTS:
        return QCoreApplication.translate(
            _BOTTOM_PANEL_CONTEXT, _BOTTOM_ACTION_TEXTS[action_id]
        )
    if fallback_label:
        return fallback_label
    if action_id:
        return action_id.replace("_", " ").title()
    return ""


def _resolve_tooltip(action_id: str | None, fallback_tooltip: str | None) -> str:
    if fallback_tooltip:
        return fallback_tooltip
    if action_id and action_id in _BOTTOM_ACTION_TOOLTIPS:
        return QCoreApplication.translate(
            _BOTTOM_PANEL_CONTEXT, _BOTTOM_ACTION_TOOLTIPS[action_id]
        )
    return ""


def _apply_translations_to_button(
    button: QPushButton, action: dict[str, str | None]
) -> None:
    action_id = action.get("id")
    fallback_label = action.get("label")
    shortcut = action.get("shortcut")
    tooltip_fallback = action.get("tooltip")

    label = _resolve_label(action_id, fallback_label)
    display_text = _format_with_shortcut(label, shortcut)
    button.setText(display_text)
    button.setAccessibleName(label)

    desc_template = QCoreApplication.translate(
        _BOTTOM_PANEL_CONTEXT, _ACTION_BUTTON_DESC_TEMPLATE
    )
    try:
        button.setAccessibleDescription(desc_template.format(label=label))
    except Exception:
        logger.debug(
            "BottomPanel: failed to format accessible description for action '%s'",
            action_id,
            exc_info=True,
        )
        button.setAccessibleDescription(label)

    tooltip = _resolve_tooltip(action_id, tooltip_fallback)
    button.setToolTip(tooltip)

    if shortcut:
        # KeyboardManager handles global shortcuts; we keep text hint only.
        pass


def retranslate_bottom_panel(window: QWidget) -> None:
    bindings = getattr(window, "_bottom_bar_bindings", None)
    if not bindings:
        return

    for binding in list(bindings):
        button = binding.get("button")
        action = binding.get("action")

        if not isinstance(button, QPushButton) or action is None:
            continue

        try:
            _apply_translations_to_button(button, action)
        except RuntimeError:
            logger.debug(
                "BottomPanel: button for action '%s' is not available",
                action.get("id"),
                exc_info=True,
            )
        except Exception:
            logger.debug(
                "BottomPanel: failed to retranslate action '%s'",
                action.get("id"),
                exc_info=True,
            )


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
            pass
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
        parsed_actions = [
            self._normalize_action_spec(spec, index)
            for index, spec in enumerate(bottom_actions)
        ]
        parsed_actions = [action for action in parsed_actions if action is not None]
        self.window._bottom_bar_bindings = []
        bottom_btns: list[QPushButton] = []
        for action in parsed_actions:
            handler_name = action["handler"]
            action_id = action.get("id")
            log_label = action.get("label") or action_id or handler_name

            btn = QPushButton()
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # Accessibility: add accessible name for screen readers
            if action_id:
                btn.setObjectName(f"bottomBarButton_{action_id}")
                btn.setProperty("action_id", action_id)
            # Allow horizontal shrink below sizeHint
            try:
                btn.setMinimumWidth(0)
                btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            except (RuntimeError, TypeError):
                logger.debug(
                    "BottomPanel: failed to apply size policy to bottom button '%s': %s",
                    log_label,
                    exc_info=True,
                )

            # Connect click handler and add to the panel
            handler = getattr(self.window, handler_name, None)
            if not callable(handler):
                logger.warning(
                    "BottomPanel: click handler '%s' not found for button '%s' — skipping",
                    handler_name,
                    log_label,
                )
                continue
            try:
                btn.clicked.connect(handler)
            except (TypeError, RuntimeError) as e:
                logger.warning(
                    "BottomPanel: failed to connect handler '%s' for button '%s': %s — skipping",
                    handler_name,
                    log_label,
                    e,
                    exc_info=True,
                )
                continue
            bottom_layout.addWidget(btn)
            bottom_btns.append(btn)
            self._register_bottom_button(btn, action)
            self._apply_localized_text(btn, action)

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

    @staticmethod
    def _coerce_to_str(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            return str(value)
        except Exception:
            return None

    def _normalize_action_spec(
        self,
        spec: Any,
        index: int,
    ) -> dict[str, str | None] | None:
        """Convert config entry into a unified action descriptor."""
        action_id: str | None = None
        handler_name: str | None = None
        label: str | None = None
        shortcut: str | None = None
        tooltip: str | None = None

        if isinstance(spec, dict):
            action_id = self._coerce_to_str(spec.get("id"))
            handler_name = self._coerce_to_str(spec.get("handler"))
            label = self._coerce_to_str(
                spec.get("label")
                or spec.get("text")
                or spec.get("title")
            )
            shortcut = self._coerce_to_str(spec.get("shortcut"))
            tooltip = self._coerce_to_str(spec.get("tooltip") or spec.get("description"))
        elif isinstance(spec, (list, tuple)):
            parts = list(spec)
            if len(parts) < 2:
                logger.warning(
                    "BottomPanel: action spec at index %s has insufficient data: %s",
                    index,
                    spec,
                )
                return None
            label = self._coerce_to_str(parts[0])
            handler_name = self._coerce_to_str(parts[1])
            if len(parts) >= 3:
                shortcut = self._coerce_to_str(parts[2])
            if len(parts) >= 4 and action_id is None:
                action_id = self._coerce_to_str(parts[3])
            if len(parts) >= 5 and tooltip is None:
                tooltip = self._coerce_to_str(parts[4])
        else:
            logger.warning(
                "BottomPanel: unsupported action spec type '%s' at index %s",
                type(spec).__name__,
                index,
            )
            return None

        if not handler_name:
            logger.warning(
                "BottomPanel: action spec at index %s is missing handler: %s",
                index,
                spec,
            )
            return None

        if not label:
            label = action_id or handler_name.replace("_", " ").title()

        display_text = label
        if shortcut:
            shortcut_clean = shortcut.strip()
            if shortcut_clean and shortcut_clean not in display_text:
                display_text = f"{display_text} ({shortcut_clean})"

        action_id = action_id.strip() if action_id else None
        shortcut = shortcut.strip() if shortcut else None
        label = label.strip() if label else None
        tooltip = tooltip.strip() if tooltip else None

        return {
            "id": action_id,
            "handler": handler_name,
            "label": label,
            "shortcut": shortcut,
            "tooltip": tooltip,
        }

    def _register_bottom_button(
        self, button: QPushButton, action: dict[str, str | None]
    ) -> None:
        bindings = getattr(self.window, "_bottom_bar_bindings", None)
        if bindings is None:
            bindings = []
            self.window._bottom_bar_bindings = bindings
        bindings.append({"button": button, "action": dict(action)})

    def _apply_localized_text(
        self, button: QPushButton, action: dict[str, str | None]
    ) -> None:
        try:
            _apply_translations_to_button(button, action)
        except Exception as exc:
            logger.debug(
                "BottomPanel: failed to apply translations for action '%s': %s",
                action.get("id"),
                exc,
                exc_info=True,
            )

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
