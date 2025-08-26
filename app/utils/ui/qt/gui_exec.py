# gui_exec.py
"""Утилиты для выполнения кода в GUI-потоке Qt (PyQt6).

Минимальные и безопасные помощники для синхронного и асинхронного исполнения
функций в GUI-потоке без раздувания зависимостей.
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
    """Выполнить функцию в GUI-потоке и вернуть результат (блокирующе)."""
    if is_gui_thread():
        return func()

    app = QApplication.instance()
    if not app:
        # Если QApplication не инициализирован — просто выполняем (лучше, чем падать)
        return func()

    result_container: dict[str, Any] = {}
    done = asyncio.Event()

    def _runner():
        try:
            result_container["result"] = func()
        except Exception as exc:  # noqa: BLE001
            result_container["exc"] = exc
        finally:
            # asyncio.Event нельзя трогать напрямую из другого потока
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(done.set)

    QTimer.singleShot(0, _runner)
    # Блокирующее ожидание через временный цикл событий asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(done.wait())

    if "exc" in result_container:
        raise result_container["exc"]
    return result_container.get("result")


async def run_in_gui_thread_async(func: Callable[[], T]) -> T:
    """Асинхронно выполнить функцию в GUI-потоке и вернуть результат."""
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
