"""Сервис управления narrow mode."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QLayout, QLineEdit

if TYPE_CHECKING:
    from ..models.types import TopBarWindow
    from .search_manager import SearchWidgetManager
    from .widget_accessor import WidgetAccessor

logger = logging.getLogger(__name__)


class NarrowModeService:
    """Управляет narrow mode (узкий режим отображения)."""

    def __init__(
        self,
        window: TopBarWindow,
        widget_accessor: WidgetAccessor,
        search_manager: SearchWidgetManager,
        min_search_width: int,
    ) -> None:
        self.window = window
        self._widget_accessor = widget_accessor
        self._search_manager = search_manager
        self._min_search_width = min_search_width

    def apply_narrow_mode(self, top_bar: QLayout, search: QLineEdit | None) -> None:
        pass

    def freeze_search_width(self) -> None:
        """Заморозить ширину search widget."""
        search = self._widget_accessor.safe_get(self.window, "search")
        self._search_manager.freeze_width(search, self._min_search_width)

    def set_top_bar_margins(
        self, top_bar: QLayout, left: int, top: int, right: int, bottom: int
    ) -> None:
        """Установить margins для top bar layout."""
        try:
            m = top_bar.contentsMargins()
            if (
                m.left() == left
                and m.top() == top
                and m.right() == right
                and m.bottom() == bottom
            ):
                return
            top_bar.setContentsMargins(left, top, right, bottom)
        except Exception:
            logger.debug("NarrowMode: failed to update contentsMargins()", exc_info=True)
