"""Централизованные константы для topbar модуля."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict


class TopBarConstants:
    """Централизованные константы для topbar."""
    
    # Размеры
    DEFAULT_BUTTON_SIZE = 32
    DEFAULT_MIN_SEARCH_WIDTH = 148
    DEFAULT_SPACER_SIZE = 4
    DEFAULT_NARROW_THRESHOLD = 380
    
    # Тайминги
    DEFAULT_THROTTLE_MS = 32
    DEFAULT_ANIMATION_DURATION_MS = 140
    
    # Лимиты панелей
    DEFAULT_MAX_RECENT = 10
    DEFAULT_MAX_FAV = 10
    DEFAULT_MAX_QUICK = 6
    DEFAULT_MIN_RECENT = 0
    DEFAULT_MIN_FAV = 0
    DEFAULT_MIN_QUICK = 0
    
    # Конфигурационные ключи
    CONFIG_THROTTLE = "ui.topbar.throttle_ms"
    CONFIG_LOG_INFO = "ui.topbar.log_info"
    CONFIG_SIDE_SPACING = "ui.top_bar_widgets_side_spacing"
    CONFIG_MIN_SEARCH_WIDTH = "ui.get_top_panel_search_min_width"
    CONFIG_MIN_VISIBLE = "topbar.min_visible"


class AdjustmentReason(Enum):
    """Причины запроса пересчета layout."""
    WINDOW_RESIZE = "window_resize"
    PANEL_CHANGE = "panel_change"
    INITIAL_SETUP = "initial_setup"
    MANUAL_REQUEST = "manual_request"
    ANIMATION_FINISHED = "animation_finished"


@dataclass(frozen=True)
class SizeConstraint:
    """Ограничения размера для панели."""
    min_width: int
    max_width: int
    visible: bool = True
    
    def __post_init__(self) -> None:
        if self.min_width < 0:
            raise ValueError("min_width must be non-negative")
        if self.max_width < self.min_width:
            raise ValueError("max_width must be >= min_width")


@dataclass(frozen=True)
class SeparatorInfo:
    """Информация о разделителе в layout."""
    index: int
    widget: object  # QWidget
    left_widget: object | None  # QWidget | None
    right_widget: object | None  # QWidget | None
    left_spacer: object | None  # QSpacerItem | None
    right_spacer: object | None  # QSpacerItem | None
