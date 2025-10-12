from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import QToolButton, QWidget


@dataclass(frozen=True)
class PanelDefinition:
    """Definition of a topbar panel configuration.

    Attributes:
        label: Panel identifier (use PanelLabel enum)
        attr_name: Attribute name on window object for the panel widget
        button_object_name: Qt objectName for buttons in this panel (use ButtonObjectName enum)
        min_attr: Attribute name on manager for minimum visible buttons
        max_attr: Attribute name on manager for maximum visible buttons
    """

    label: str  # Should be PanelLabel value
    attr_name: str
    button_object_name: str  # Should be ButtonObjectName value
    min_attr: str
    max_attr: str


@dataclass
class PanelState:
    definition: PanelDefinition
    widget: QWidget | None
    buttons: list[QToolButton]
    min_visible: int
    max_visible: int
