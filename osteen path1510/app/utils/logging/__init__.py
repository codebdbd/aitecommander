"""Публичный интерфейс подсистемы логирования."""

from typing import Any

__all__ = ["ApplicationLogger", "ExceptionHandler"]


def __getattr__(name: str) -> Any:
    if name == "ApplicationLogger":
        from .application_logger import ApplicationLogger as _ApplicationLogger

        globals()["ApplicationLogger"] = _ApplicationLogger
        return _ApplicationLogger
    if name == "ExceptionHandler":
        from .exception_handler import ExceptionHandler as _ExceptionHandler

        globals()["ExceptionHandler"] = _ExceptionHandler
        return _ExceptionHandler
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
