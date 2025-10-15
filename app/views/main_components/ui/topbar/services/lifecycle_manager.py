"""TopBar lifecycle management - signals, event filters, cleanup."""

from __future__ import annotations

import logging
from typing import Any
from weakref import WeakSet

from PyQt6.QtCore import QObject

from ..utils.qt_utils import is_deleted

logger = logging.getLogger(__name__)


class TopBarLifecycleManager:
    """Manages lifecycle operations for TopBar components.
    
    Responsibilities:
    - Signal connection/disconnection
    - Event filter installation/removal
    - Resource cleanup tracking
    """

    def __init__(self, parent: QObject) -> None:
        self._parent = parent
        self._signal_connections: list[tuple[QObject, str, object]] = []
        self._watched_panels: WeakSet[QObject] = WeakSet()

    def connect_signal(self, obj: QObject, signal_name: str, slot: object) -> None:
        """Connect a signal and track the connection."""
        try:
            signal = getattr(obj, signal_name, None)
            if signal is not None:
                signal.connect(slot)
                self._signal_connections.append((obj, signal_name, slot))
                logger.debug("TopBarLifecycle: connected signal %s", signal_name)
        except (AttributeError, TypeError, RuntimeError) as e:
            logger.debug("TopBarLifecycle: failed to connect signal %s: %s", signal_name, e)

    def disconnect_signal(self, obj: QObject, signal_name: str, slot: object) -> None:
        """Disconnect a single signal."""
        try:
            if not is_deleted(obj):
                signal = getattr(obj, signal_name, None)
                if signal is not None:
                    signal.disconnect(slot)
                    logger.debug("TopBarLifecycle: disconnected %s", signal_name)
        except (TypeError, RuntimeError) as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("TopBarLifecycle: failed to disconnect %s: %s", signal_name, e)

    def cleanup_all_signals(self) -> None:
        """Disconnect all tracked signals."""
        for obj, signal_name, slot in self._signal_connections:
            self.disconnect_signal(obj, signal_name, slot)
        self._signal_connections.clear()

    def install_event_filter(self, obj: QObject) -> None:
        """Install event filter and track the object."""
        if obj not in self._watched_panels:
            obj.installEventFilter(self._parent)
            self._watched_panels.add(obj)

    def install_event_filters(self, objects: list[QObject]) -> None:
        """Install event filters on multiple objects."""
        for obj in objects:
            if obj is not None and not is_deleted(obj):
                self.install_event_filter(obj)

    def remove_event_filter(self, obj: QObject) -> None:
        """Remove event filter from an object."""
        try:
            if not is_deleted(obj):
                obj.removeEventFilter(self._parent)
        except (RuntimeError, AttributeError):
            pass

    def cleanup_all_event_filters(self) -> None:
        """Remove all tracked event filters."""
        for panel in list(self._watched_panels):
            self.remove_event_filter(panel)
        self._watched_panels.clear()

    def cleanup(self) -> None:
        """Full cleanup of all lifecycle resources."""
        self.cleanup_all_signals()
        self.cleanup_all_event_filters()

    def get_watched_panels(self) -> WeakSet[QObject]:
        """Get the set of watched panels."""
        return self._watched_panels

    def get_signal_connections(self) -> list[tuple[QObject, str, object]]:
        """Get list of signal connections."""
        return self._signal_connections
