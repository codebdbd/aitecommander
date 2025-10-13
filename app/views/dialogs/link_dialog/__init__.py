"""Compatibility bridge for `app.views.windows.dialogs.link_dialog` package."""

from importlib import import_module
from typing import Any

_TARGET_PREFIX = "app.views.windows.dialogs.link_dialog"
_MAIN_MODULE = import_module(f"{_TARGET_PREFIX}.link_dialog")

__all__ = list(getattr(_MAIN_MODULE, "__all__", [])) or [
    name for name in vars(_MAIN_MODULE) if not name.startswith("_")
]

globals().update({name: getattr(_MAIN_MODULE, name) for name in __all__})


def _load_submodule(name: str):
    module = import_module(f"{_TARGET_PREFIX}.{name}")
    exported = list(getattr(module, "__all__", [])) or [
        attr for attr in vars(module) if not attr.startswith("_")
    ]
    globals().update({attr: getattr(module, attr) for attr in exported})
    __all__.extend(attr for attr in exported if attr not in __all__)
    return module


def __getattr__(name: str) -> Any:
    for sub in ("link_dialog_handlers", "link_dialog_signals", "link_dialog_ui"):
        module = import_module(f"{_TARGET_PREFIX}.{sub}")
        if hasattr(module, name):
            value = getattr(module, name)
            globals()[name] = value
            if name not in __all__:
                __all__.append(name)
            return value
    try:
        return getattr(_MAIN_MODULE, name)
    except AttributeError as exc:
        raise AttributeError(name) from exc


def __dir__() -> list[str]:
    return sorted(set(__all__))
