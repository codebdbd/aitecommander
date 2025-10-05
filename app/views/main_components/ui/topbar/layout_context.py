from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from PyQt6.QtWidgets import QLayout, QLineEdit, QWidget

from .panel_state import PanelState


@dataclass(frozen=True)
class LayoutContext:
    """Snapshot of the top-bar state during a layout recomputation."""

    container: QWidget
    width: int
    effective_width: int
    min_search_width: int
    top_bar: QLayout
    search: Optional[QLineEdit]
    panel_states: tuple[PanelState, ...]

    @property
    def has_search(self) -> bool:
        return self.search is not None

    @property
    def panels(self) -> Iterable[PanelState]:
        return self.panel_states
