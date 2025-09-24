"""Калькулятор размеров для топбара с кешированием и оптимизацией."""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple, Protocol

from PyQt6.QtWidgets import QLayout, QLineEdit, QToolButton, QWidget

from app.views.main_components.topbar.top_bar_config import TopBarConfig

logger = logging.getLogger(__name__)


class PanelWidget(Protocol):
    """Протокол для виджетов панелей."""

    def layout(self) -> Optional[QLayout]:
        """Получить layout панели."""
        ...

    def contentsMargins(self) -> tuple[int, int, int, int]:
        """Получить отступы панели."""
        ...

    def setMaximumWidth(self, width: int) -> None:
        """Установить максимальную ширину."""
        ...


class TopBarLayoutCalculator:
    """Калькулятор размеров топбара с кешированием результатов."""

    def __init__(self, config: TopBarConfig) -> None:
        """Инициализация калькулятора."""
        self.config = config
        self._cache: dict[str, int] = {}

    def calculate_panel_width(
        self,
        panel: Optional[PanelWidget],
        buttons: List[QToolButton],
        visible_count: int
    ) -> int:
        """Рассчитать ширину панели для заданного количества видимых кнопок."""
        if not panel or not buttons or visible_count <= 0:
            return 0

        cache_key = f"panel_{id(panel)}_{len(buttons)}_{visible_count}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Получить layout для расчета отступов и spacing
        layout = panel.layout()
        spacing = layout.spacing() if layout else 0

        total_width = 0

        # Рассчитать ширину видимых кнопок
        for i in range(min(visible_count, len(buttons))):
            try:
                button_width = max(self.config.button_size, buttons[i].sizeHint().width())
            except (AttributeError, RuntimeError):
                button_width = self.config.button_size
            if i > 0:
                total_width += spacing
            total_width += button_width

        # Добавить отступы layout'а
        if layout:
            margins = layout.contentsMargins()
            total_width += margins.left() + margins.right()

        # Добавить отступы самой панели
        try:
            panel_margins = panel.contentsMargins()
            total_width += panel_margins.left() + panel_margins.right()
        except (AttributeError, RuntimeError):
            pass

        self._cache[cache_key] = total_width
        return total_width

    def calculate_total_width(
        self,
        top_bar: QLayout,
        search: Optional[QLineEdit],
        recent_panel: Optional[PanelWidget],
        fav_panel: Optional[PanelWidget],
        quick_panel: Optional[PanelWidget],
        recent_buttons: List[QToolButton],
        fav_buttons: List[QToolButton],
        quick_buttons: List[QToolButton],
        recent_count: int,
        fav_count: int,
        quick_count: int
    ) -> int:
        """Рассчитать общую ширину всех элементов топбара."""
        cache_key = f"total_{id(top_bar)}_{recent_count}_{fav_count}_{quick_count}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        items: List[int] = []

        # Обойти все элементы layout'а
        for i in range(top_bar.count()):
            item = top_bar.itemAt(i)
            widget = item.widget()

            if widget:
                if widget is search:
                    items.append(self.config.min_search_width)
                elif widget is recent_panel and recent_count > 0:
                    items.append(self.calculate_panel_width(recent_panel, recent_buttons, recent_count))
                elif widget is fav_panel and fav_count > 0:
                    items.append(self.calculate_panel_width(fav_panel, fav_buttons, fav_count))
                elif widget is quick_panel and quick_count > 0:
                    items.append(self.calculate_panel_width(quick_panel, quick_buttons, quick_count))
                elif widget.isVisible():
                    try:
                        items.append(widget.sizeHint().width())
                    except (AttributeError, RuntimeError):
                        items.append(0)
            else:
                # Spacer item
                spacer = item.spacerItem()
                if spacer:
                    items.append(max(0, spacer.sizeHint().width()))

        # Рассчитать общую ширину
        total = sum(items)
        spacing = top_bar.spacing() or 0
        total += spacing * max(0, len(items) - 1)

        # Добавить отступы layout'а
        margins = top_bar.contentsMargins()
        total += margins.left() + margins.right()

        self._cache[cache_key] = total
        return total

    def compute_visible_counts(
        self,
        container_width: int,
        top_bar: QLayout,
        search: Optional[QLineEdit],
        recent_panel: Optional[PanelWidget],
        fav_panel: Optional[PanelWidget],
        quick_panel: Optional[PanelWidget],
        recent_buttons: List[QToolButton],
        fav_buttons: List[QToolButton],
        quick_buttons: List[QToolButton]
    ) -> Tuple[int, int, int]:
        """Рассчитать оптимальное количество видимых кнопок."""
        # Получить ограничения
        max_recent = min(self.config.max_recent, len(recent_buttons))
        max_fav = min(self.config.max_fav, len(fav_buttons))
        max_quick = min(self.config.max_quick, len(quick_buttons))

        min_recent = min(self.config.min_recent, max_recent)
        min_fav = min(self.config.min_fav, max_fav)
        min_quick = min(self.config.min_quick, max_quick)

        # Начать с максимальных значений
        recent_count, fav_count, quick_count = max_recent, max_fav, max_quick

        max_steps = (
            (max_recent - min_recent) +
            (max_fav - min_fav) +
            (max_quick - min_quick)
        )

        steps = 0
        while (
            self.calculate_total_width(
                top_bar, search, recent_panel, fav_panel, quick_panel,
                recent_buttons, fav_buttons, quick_buttons,
                recent_count, fav_count, quick_count
            ) > container_width
            and steps < max_steps
        ):
            steps += 1

            # Скрывать кнопки в порядке приоритета: recent -> fav -> quick
            if recent_count > min_recent:
                recent_count -= 1
            elif fav_count > min_fav:
                fav_count -= 1
            elif quick_count > min_quick:
                quick_count -= 1
            else:
                break

        # Если все равно не помещается - принудительно установить минимум
        if (
            self.calculate_total_width(
                top_bar, search, recent_panel, fav_panel, quick_panel,
                recent_buttons, fav_buttons, quick_buttons,
                recent_count, fav_count, quick_count
            ) > container_width
        ):
            recent_count = max(min_recent, 0)
            fav_count = max(min_fav, 0)
            quick_count = max(min_quick, 0)

        if self.config.log_info:
            logger.info(
                f"[TopBarCalculator] computed: recent={recent_count}, fav={fav_count}, quick={quick_count} "
                f"for width={container_width}"
            )

        return recent_count, fav_count, quick_count

    def clear_cache(self) -> None:
        """Очистить кеш расчетов."""
        self._cache.clear()

    def get_cache_size(self) -> int:
        """Получить размер кеша для диагностики."""
        return len(self._cache)
