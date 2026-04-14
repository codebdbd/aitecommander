"""Сервис управления narrow mode."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QLayout, QLineEdit, QSizePolicy

from ..models.topbar_constants import TOPBAR_CONSTANTS as C

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
        """
        Применить narrow mode: скрыть все виджеты кроме search.
        
        Также корректирует spacing между элементами.
        """

        def _neighbor_widget(idx: int, step: int):
            """Найти соседний виджет в layout."""
            pos = idx + step
            count = top_bar.count()
            while 0 <= pos < count:
                item = top_bar.itemAt(pos)
                widget = item.widget()
                if widget is not None:
                    return widget
                pos += step
            return None

        for index in range(top_bar.count()):
            item = top_bar.itemAt(index)
            widget = item.widget()

            if widget is None:
                # Обработка spacer'ов
                spacer = item.spacerItem()
                if spacer is not None:
                    left_neighbor = _neighbor_widget(index, -1)
                    right_neighbor = _neighbor_widget(index, +1)
                    keep_spacing = False

                    # Сохранить spacing рядом с search или separator
                    left_sep_visible = (
                        left_neighbor
                        and left_neighbor.objectName() == "vSeparator"
                        and left_neighbor.isVisible()
                    )
                    right_sep_visible = (
                        right_neighbor
                        and right_neighbor.objectName() == "vSeparator"
                        and right_neighbor.isVisible()
                    )
                    if left_sep_visible or right_sep_visible:
                        keep_spacing = True

                    target_width = (
                        C.SEPARATOR_SPACING_VISIBLE
                        if keep_spacing
                        else C.SEPARATOR_SPACING_HIDDEN
                    )
                    spacer.changeSize(
                        target_width,
                        0,
                        QSizePolicy.Policy.Fixed,
                        QSizePolicy.Policy.Fixed,
                    )
                continue

            # Не скрывать search
            if isinstance(search, QLineEdit) and widget is search:
                continue

            # Скрыть все остальные виджеты
            try:
                widget.setVisible(False)
            except (RuntimeError, AttributeError) as e:
                # RuntimeError: widget deleted
                # AttributeError: widget is None
                logger.debug(
                    "NarrowMode: failed to hide widget (may be deleted): %s",
                    e
                )

        # Выравниваем боковые отступы вокруг поиска (берём максимальный из текущих)
        try:
            margins = top_bar.contentsMargins()
            target = max(margins.left(), margins.right(), C.SEPARATOR_SPACING_VISIBLE)
            if margins.left() != target or margins.right() != target:
                top_bar.setContentsMargins(
                    target,
                    margins.top(),
                    target,
                    margins.bottom(),
                )
        except Exception:
            logger.debug("NarrowMode: failed to normalize search margins", exc_info=True)

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
