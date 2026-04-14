"""Focus management utilities.

Centralized focus handling for the application to eliminate code duplication
and provide consistent focus behavior.
"""

from __future__ import annotations

from .focus_guard import FocusGuard
from .focus_manager import FocusManager, get_focus_manager
from .widget_registry import WidgetRegistry, WidgetType

__all__ = [
    "FocusManager",
    "get_focus_manager",
    "FocusGuard",
    "WidgetRegistry",
    "WidgetType",
]
