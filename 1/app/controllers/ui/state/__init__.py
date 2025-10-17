"""Пакет состояния UI."""

from typing import Any

__all__ = ["UIStateManager"]


def __getattr__(name: str) -> Any:
    if name == "UIStateManager":
        from .ui_state_manager import UIStateManager as _UIStateManager

        globals()["UIStateManager"] = _UIStateManager
        return _UIStateManager
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
