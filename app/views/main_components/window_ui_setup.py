"""Compatibility layer for legacy import `app.views.main_components.window_ui_setup`."""

from __future__ import annotations

import importlib

_MODULE = importlib.import_module("app.views.main_components.ui.window_ui_setup")

_EXPORT_NAMES = [
    "WindowUISetup",
    "setup_top_panel",
    "setup_main_content",
    "_AutoHideTreeFilter",
    "logger",
]

__all__ = []

for _name in _EXPORT_NAMES:
    _obj = getattr(_MODULE, _name, None)
    if _obj is not None:
        globals()[_name] = _obj  # noqa: F401
        __all__.append(_name)

# Additional helpers might exist in legacy versions; export when present.
for _optional in ("create_top_panel_metrics", "WindowUISerializer"):
    _obj = getattr(_MODULE, _optional, None)
    if _obj is not None:
        globals()[_optional] = _obj  # noqa: F401
        __all__.append(_optional)

del _MODULE
del _EXPORT_NAMES
