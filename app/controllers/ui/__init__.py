"""Публичные контроллеры UI."""

from typing import Any

__all__ = ["MenuController", "ThemeController"]


def __getattr__(name: str) -> Any:
    if name == "MenuController":
        from .menu_controller import MenuController as _MenuController

        globals()["MenuController"] = _MenuController
        return _MenuController
    if name == "ThemeController":
        from .theme_controller import ThemeController as _ThemeController

        globals()["ThemeController"] = _ThemeController
        return _ThemeController
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
