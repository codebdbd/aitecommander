from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import QToolButton, QWidget


@dataclass(frozen=True)
class PanelDefinition:
    """Definition of a top bar panel configuration."""

    label: str  # Should be PanelLabel value
    attr_name: str
    button_object_name: str  # Should be ButtonObjectName value
    min_visible: int
    max_visible: int


@dataclass
class PanelState:
    definition: PanelDefinition
    widget: QWidget | None
    buttons: list[QToolButton]
    min_visible: int
    max_visible: int
