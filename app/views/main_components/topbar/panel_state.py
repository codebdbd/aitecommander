from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from PyQt6.QtWidgets import QToolButton, QWidget


@dataclass(frozen=True)
class PanelDefinition:
    label: str
    attr_name: str
    button_object_name: str
    min_attr: str
    max_attr: str


@dataclass
class PanelState:
    definition: PanelDefinition
    widget: Optional[QWidget]
    buttons: List[QToolButton]
    min_visible: int
    max_visible: int
