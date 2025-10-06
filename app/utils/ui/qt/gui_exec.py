# gui_exec.py
"""Utilities to execute code in the Qt GUI thread (PyQt6).

Minimal and safe helpers for synchronous and asynchronous execution
in the GUI thread without extra dependencies.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, TypeVar

from PyQt6.QtCore import QThread, QTimer
from PyQt6.QtWidgets import QApplication

T = TypeVar("T")

__all__ = [
    "is_gui_thread",
    "run_in_gui_thread_sync",
    "run_in_gui_thread_async",
]


def is_gui_thread() -> bool:
    try:
        app = QApplication.instance()
        if not app:
            return False
        return QThread.currentThread() == app.thread()
    except Exception:
        return False


def run_in_gui_thread_sync(func: Callable[[], T]) -> T:
    """Execute a function in the GUI thread and return its result (blocking)."""
    if is_gui_thread():
        return func()

    app = QApplication.instance()
    if not app:
        # If QApplication is not initialised — run directly (better than crashing)
        return func()

    result_container: dict[str, Any] = {}
    done = asyncio.Event()

    def _runner():
        try:
            result_container["result"] = func()
        except Exception as exc:  # noqa: BLE001
            result_container["exc"] = exc
        finally:
            # asyncio.Event cannot be set directly from another thread
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(done.set)

    QTimer.singleShot(0, _runner)
    # Blocking wait via the current asyncio event loop
    loop = asyncio.get_event_loop()
    loop.run_until_complete(done.wait())

    if "exc" in result_container:
        raise result_container["exc"]
    return result_container.get("result")


async def run_in_gui_thread_async(func: Callable[[], T]) -> T:
    """Execute a function in the GUI thread asynchronously and return result."""
    if is_gui_thread():
        return func()

    app = QApplication.instance()
    if not app:
        # Если QApplication не инициализирован — просто выполняем (лучше, чем падать)
        return func()

    loop = asyncio.get_event_loop()
    fut: asyncio.Future[T] = loop.create_future()

    def _runner():
        try:
            res = func()
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(fut.set_exception, exc)
        else:
            loop.call_soon_threadsafe(fut.set_result, res)

    QTimer.singleShot(0, _runner)
    return await fut
