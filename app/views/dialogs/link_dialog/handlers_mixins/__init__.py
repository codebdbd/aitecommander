"""Compatibility package for legacy handlers mixins imports."""

from __future__ import annotations

import importlib
import sys

_TARGET_PREFIX = "app.views.windows.dialogs.link_dialog.handlers_mixins"
_LEGACY_PREFIX = __name__

_MODULES = {
    "file_dialog_mixin",
    "form_data_mixin",
    "hierarchy_mixin",
    "icons_mixin",
    "link_processing_mixin",
    "profiles_mixin",
    "type_change_mixin",
    "validation_mixin",
}

for mod in _MODULES:
    target = f"{_TARGET_PREFIX}.{mod}"
    module = importlib.import_module(target)
    sys.modules.setdefault(f"{_LEGACY_PREFIX}.{mod}", module)

__all__: list[str] = []
