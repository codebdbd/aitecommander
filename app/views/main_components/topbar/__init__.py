"""Модуль топбара с разделением на компоненты."""
from __future__ import annotations

from app.views.main_components.topbar.top_bar_config import TopBarConfig
from app.views.main_components.topbar.top_bar_calculator import TopBarLayoutCalculator
from app.views.main_components.topbar.top_bar_animator import TopBarAnimationManager
from app.views.main_components.topbar.top_bar_event_handler import TopBarEventHandler
from app.views.main_components.topbar.top_bar_manager import TopBarLayoutManager

__all__ = [
    'TopBarConfig',
    'TopBarLayoutCalculator',
    'TopBarAnimationManager',
    'TopBarEventHandler',
    'TopBarLayoutManager'
]
