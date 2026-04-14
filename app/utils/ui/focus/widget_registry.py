"""Widget registry for tracking and identifying application widgets.

Provides centralized widget type detection to eliminate duplicate
`_is_*_focused()` methods across controllers.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING
from weakref import WeakValueDictionary

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class WidgetType(Enum):
    """Known widget types in the application."""

    STRUCTURE_TREE = "structure_tree"
    LINKS_TABLE = "links_table"
    CATEGORY_TILES = "category_tiles"
    SEARCH_FIELD = "search_field"
    UNKNOWN = "unknown"


class WidgetRegistry:
    """Registry for tracking and identifying application widgets.

    Uses weak references to avoid keeping widgets alive.
    """

    _widgets: WeakValueDictionary = WeakValueDictionary()
    _reverse_map: dict[int, WidgetType] = {}

    @classmethod
    def register(cls, widget_type: WidgetType, widget: QWidget) -> None:
        """Register a widget with its type.

        Args:
            widget_type: Type of the widget
            widget: Widget instance to register

        Example:
            WidgetRegistry.register(WidgetType.STRUCTURE_TREE, tree_widget)
        """
        if widget is None:
            logger.warning("Cannot register None widget for type %s", widget_type.value)
            return
            
        try:
            cls._widgets[widget_type] = widget
            cls._reverse_map[id(widget)] = widget_type
            logger.debug("Registered widget: %s -> %s", widget_type.value, widget)
        except Exception as e:
            logger.warning(
                "Failed to register widget %s: %s", widget_type.value, e, exc_info=True
            )

    @classmethod
    def unregister(cls, widget_type: WidgetType) -> None:
        """Unregister a widget type.

        Args:
            widget_type: Type to unregister
        """
        try:
            widget = cls._widgets.pop(widget_type, None)
            if widget is not None:
                cls._reverse_map.pop(id(widget), None)
                logger.debug("Unregistered widget: %s", widget_type.value)
        except Exception as e:
            logger.debug("Failed to unregister widget %s: %s", widget_type.value, e)

    @classmethod
    def get_widget(cls, widget_type: WidgetType) -> QWidget | None:
        """Get registered widget by type.

        Args:
            widget_type: Type of widget to retrieve

        Returns:
            Widget instance or None if not registered or already deleted

        Example:
            tree = WidgetRegistry.get_widget(WidgetType.STRUCTURE_TREE)
        """
        return cls._widgets.get(widget_type)

    @classmethod
    def get_type(cls, widget: QWidget) -> WidgetType:
        """Determine widget type.

        Args:
            widget: Widget to identify

        Returns:
            WidgetType enum value (UNKNOWN if not registered)

        Example:
            widget_type = WidgetRegistry.get_type(some_widget)
            if widget_type == WidgetType.STRUCTURE_TREE:
                ...
        """
        if widget is None:
            return WidgetType.UNKNOWN

        try:
            widget_id = id(widget)
            return cls._reverse_map.get(widget_id, WidgetType.UNKNOWN)
        except Exception as e:
            logger.debug("Failed to get widget type: %s", e)
            return WidgetType.UNKNOWN

    @classmethod
    def is_registered(cls, widget_type: WidgetType) -> bool:
        """Check if widget type is registered.

        Args:
            widget_type: Type to check

        Returns:
            True if registered and widget still exists
        """
        return widget_type in cls._widgets

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations (for testing)."""
        cls._widgets.clear()
        cls._reverse_map.clear()
        logger.debug("Cleared widget registry")
