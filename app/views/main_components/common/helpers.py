"""Helper utilities that simplify frequent operations.

Improvement note: pragmatic helpers without unnecessary complexity.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QTimer

from .constants import Timeout


def defer(callback: callable, delay_ms: int = Timeout.DEFER_OPERATION) -> None:
    """Defer ``callback`` execution until a future event-loop tick.

    Improvement note: wraps the common ``QTimer.singleShot(0, callback)`` pattern.

    Args:
        callback: Callable to invoke later.
        delay_ms: Delay in milliseconds (defaults to 0).

    Example:
        >>> defer(lambda: print("Deferred"))
        >>> defer(self.update_ui, 100)
    """
    QTimer.singleShot(delay_ms, callback)


def safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    """Safely read an attribute while guarding against deleted Qt objects.

    Improvement note: shortens the repetitive deleted-object pattern.

    Args:
        obj: Object that may carry the attribute.
        name: Attribute name to access.
        default: Fallback value when attribute is missing or invalid.

    Returns:
        The attribute value or ``default``.

    Example:
        >>> widget = safe_getattr(window, "search")
        >>> if widget:
        ...     widget.setText("test")
    """
    if obj is None:
        return default
    
    try:
        from sip import isdeleted
        if isdeleted(obj):
            return default
    except ImportError:
        pass
    
    try:
        return getattr(obj, name, default)
    except (RuntimeError, AttributeError):
        return default


def safe_disconnect(signal, slot) -> bool:
    """Safely disconnect a Qt signal from its slot.

    Improvement note: centralizes the usual try/except around Qt's ``disconnect``.

    Args:
        signal: Qt signal instance.
        slot: Slot callable to detach.

    Returns:
        ``True`` if the disconnect succeeded, otherwise ``False``.

    Example:
        >>> safe_disconnect(button.clicked, self.on_click)
    """
    try:
        signal.disconnect(slot)
        return True
    except (TypeError, RuntimeError, AttributeError):
        return False


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Restrict ``value`` to the inclusive range [``min_val``, ``max_val``].

    Args:
        value: Value to clamp.
        min_val: Lower bound.
        max_val: Upper bound.

    Returns:
        Clamped result that never falls outside the bounds.

    Example:
        >>> clamp(150, 100, 200)  # 150
        >>> clamp(50, 100, 200)   # 100
        >>> clamp(250, 100, 200)  # 200
    """
    return max(min_val, min(value, max_val))
