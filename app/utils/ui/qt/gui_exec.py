# gui_exec.py
"""Utilities to execute code in the Qt GUI thread (PyQt6).

Minimal and safe helpers for synchronous and asynchronous execution
in the GUI thread without extra dependencies.
"""

from __future__ import annotations

import asyncio
import threading
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
    """Execute a function in the GUI thread and return its result (blocking).
    
    Note:
        Uses threading.Event for synchronization (not asyncio.Event) to avoid
        blocking the event loop and to work correctly when called from threads
        without a running event loop.
    """
    if is_gui_thread():
        return func()

    app = QApplication.instance()
    if not app:
        # If QApplication is not initialised - run directly (better than crashing)
        return func()

    result_container: dict[str, Any] = {}
    done = threading.Event()  # Use threading.Event for sync code

    def _runner():
        try:
            result_container["result"] = func()
        except Exception as exc:  # noqa: BLE001
            result_container["exc"] = exc
        finally:
            done.set()

    QTimer.singleShot(0, _runner)
    # Blocking wait (does not block event loop)
    done.wait()

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
