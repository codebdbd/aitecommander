"""Compatibility proxy for `app.views.windows.dialogs.link_dialog.icon_utils`."""

from importlib import import_module
from typing import Any

_TARGET_MODULE = import_module("app.views.windows.dialogs.link_dialog.icon_utils")

__all__ = list(getattr(_TARGET_MODULE, "__all__", [])) or [
    name for name in vars(_TARGET_MODULE) if not name.startswith("_")
]

globals().update({name: getattr(_TARGET_MODULE, name) for name in __all__})


def __getattr__(name: str) -> Any:
    try:
        return getattr(_TARGET_MODULE, name)
    except AttributeError as exc:  # pragma: no cover
        raise AttributeError(name) from exc


def __dir__() -> list[str]:
    return sorted(set(__all__))
