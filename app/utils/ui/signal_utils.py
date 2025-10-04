"""Совместимый слой для легаси-импорта `app.utils.ui.signal_utils`."""

from __future__ import annotations

from typing import Any, Callable, Optional

import weakref

from app.utils.db.synchronization import (  # noqa: F401
    signal_guard as _decorator_signal_guard,
)


class _SignalBlocker:
    """Контекстный менеджер, временно блокирующий сигналы у Qt-объекта."""

    def __init__(self, target: Any):
        self._target = target
        self._supports_blocking = hasattr(target, "blockSignals")
        self._previous_state: Optional[bool] = None

    def __enter__(self):
        if self._supports_blocking:
            try:
                self._previous_state = bool(self._target.blockSignals(True))
            except Exception:
                # Если объект не поддерживает блокировку, просто пропускаем
                self._supports_blocking = False
        return self._target

    def __exit__(self, exc_type, exc, tb):
        if self._supports_blocking:
            try:
                restore_state = self._previous_state if self._previous_state is not None else False
                self._target.blockSignals(restore_state)
            except Exception:
                pass
        return False


def signal_guard(obj_or_func: Any = None, *, slot_name: Optional[str] = None):
    """Поддерживает два способа использования:

    1. Как контекстный менеджер: ``with signal_guard(widget): ...``
    2. Как декоратор: ``@signal_guard`` или ``@signal_guard("slot")``
    """

    # Декоратор без аргументов: @signal_guard
    if callable(obj_or_func) and slot_name is None:
        return _decorator_signal_guard()(obj_or_func)

    # Декоратор с именем слота: @signal_guard("slot") или signal_guard("slot")(func)
    if isinstance(obj_or_func, str) and slot_name is None:
        return _decorator_signal_guard(obj_or_func)

    # signal_guard()(func) -> возвращаем сам декоратор
    if obj_or_func is None and slot_name is None:
        return _decorator_signal_guard()

    # signal_guard(slot_name=...)(func)
    if obj_or_func is None and slot_name is not None:
        return _decorator_signal_guard(slot_name)

    # signal_guard(widget) -> контекстный менеджер
    return _SignalBlocker(obj_or_func)


# -- Legacy weakref.WeakMethod compatibility ---------------------------------


class _LegacyWeakMethod:
    """WeakMethod, который не удерживает сильных ссылок на экземпляр."""

    def __init__(self, method: Callable):
        try:
            self._func = method.__func__  # type: ignore[attr-defined]
            self._self_ref = weakref.ref(method.__self__)  # type: ignore[attr-defined]
        except AttributeError:
            # Обычная функция (не bound method)
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


# Переопределяем WeakMethod только если ещё не подменён
if getattr(weakref.WeakMethod, "__module__", "") != __name__:
    weakref.WeakMethod = _LegacyWeakMethod  # type: ignore[assignment]


__all__ = ["signal_guard"]
