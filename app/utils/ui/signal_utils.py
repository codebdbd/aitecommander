"""Compatibility layer for legacy import `app.utils.ui.signal_utils`."""

from __future__ import annotations

import weakref
from typing import Any, Callable

from app.utils.db.synchronization import (  # noqa: F401
    signal_guard as _decorator_signal_guard,
)


class _SignalBlocker:
    """Context manager that temporarily blocks signals on a Qt object."""

    def __init__(self, target: Any):
        self._target = target
        self._supports_blocking = hasattr(target, "blockSignals")
        self._previous_state: bool | None = None

    def __enter__(self):
        if self._supports_blocking:
            try:
                self._previous_state = bool(self._target.blockSignals(True))
            except Exception:
                # If the object does not support blocking, just skip
                self._supports_blocking = False
        return self._target

    def __exit__(self, exc_type, exc, tb):
        if self._supports_blocking:
            try:
                restore_state = (
                    self._previous_state if self._previous_state is not None else False
                )
                self._target.blockSignals(restore_state)
            except Exception:
                pass
        return False


def signal_guard(obj_or_func: Any = None, *, slot_name: str | None = None):
    """Supports two usage patterns:

    1. As a context manager: ``with signal_guard(widget): ...``
    2. As a decorator: ``@signal_guard`` or ``@signal_guard("slot")``
    """

    # Decorator without args: @signal_guard
    if callable(obj_or_func) and slot_name is None:
        return _decorator_signal_guard()(obj_or_func)

    # Decorator with slot name: @signal_guard("slot") or signal_guard("slot")(func)
    if isinstance(obj_or_func, str) and slot_name is None:
        return _decorator_signal_guard(obj_or_func)

    # signal_guard()(func) -> return the decorator itself
    if obj_or_func is None and slot_name is None:
        return _decorator_signal_guard()

    # signal_guard(slot_name=...)(func)
    if obj_or_func is None and slot_name is not None:
        return _decorator_signal_guard(slot_name)

    # signal_guard(widget) -> context manager
    return _SignalBlocker(obj_or_func)


# -- Legacy weakref.WeakMethod compatibility ---------------------------------


class _LegacyWeakMethod:
    """WeakMethod that does not keep strong references to the instance."""

    def __init__(self, method: Callable):
        try:
            self._func = method.__func__  # type: ignore[attr-defined]
            self._self_ref: weakref.ReferenceType[Any] | None = weakref.ref(method.__self__)  # type: ignore[attr-defined]
        except AttributeError:
            # Plain function (not a bound method)
            self._func = method
            self._self_ref = None

    def __call__(self):
        if self._self_ref is None:
            return self._func

        instance = self._self_ref()
        if instance is None:
            return None

        func = self._func
        self_ref = self._self_ref

        def _bound(*args, **kwargs):
            target = self_ref()
            if target is None:
                raise ReferenceError("weakly-referenced object no longer exists")
            return func(target, *args, **kwargs)

        _bound.__name__ = getattr(func, "__name__", _bound.__name__)
        _bound.__qualname__ = getattr(func, "__qualname__", _bound.__qualname__)
        _bound.__doc__ = getattr(func, "__doc__", _bound.__doc__)
        return _bound


# Override WeakMethod only if it hasn't been replaced yet
if getattr(weakref.WeakMethod, "__module__", "") != __name__:
    weakref.WeakMethod = _LegacyWeakMethod  # type: ignore[assignment, misc]


__all__ = ["signal_guard"]
