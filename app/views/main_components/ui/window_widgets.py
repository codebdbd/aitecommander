from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QScrollArea, QSplitter, QStackedLayout, QWidget

if TYPE_CHECKING:
    from app.views.widgets.link import LinksTableView
    from app.views.widgets.tiles import CategoryTiles


@dataclass
class MainWindowWidgets:
    """Container for auxiliary widgets owned by MainWindow.

    Centralizes references that historically were attached dynamically to the
    window instance (``window.tiles``, ``window.table`` etc.), allowing us to
    manage lifecycle explicitly and avoid monkey-patching multiple attributes.
    """

    tiles_scroll: QScrollArea | None = None
    tiles: CategoryTiles | None = None
    table: LinksTableView | None = None
    table_container: QWidget | None = None
    stack: QStackedLayout | None = None
    splitter: QSplitter | None = None

    def clear(self) -> None:
        """Drop references to help GC during shutdown."""
        self.tiles_scroll = None
        self.tiles = None
        self.table = None
        self.table_container = None
        self.stack = None
        self.splitter = None
