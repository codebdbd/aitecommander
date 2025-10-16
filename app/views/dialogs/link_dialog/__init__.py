"""Compatibility package for legacy link dialog imports.

This module bridges historical import paths (``app.views.dialogs.link_dialog.*``)
to the refactored implementation under ``app.views.windows.dialogs.link_dialog``.
It avoids code duplication by aliasing the new modules in ``sys.modules`` and by
re-exporting the primary symbols for convenience. All logic remains in the new
package; this file only preserves API stability for tests and older extensions.
"""

from __future__ import annotations

import importlib
import sys
from typing import Dict

_TARGET_PREFIX = "app.views.windows.dialogs.link_dialog"
_LEGACY_PREFIX = __name__

_MODULE_ALIASES: Dict[str, str] = {
    f"{_LEGACY_PREFIX}.link_dialog": f"{_TARGET_PREFIX}.link_dialog",
    f"{_LEGACY_PREFIX}.link_dialog_ui": f"{_TARGET_PREFIX}.link_dialog_ui",
    f"{_LEGACY_PREFIX}.link_dialog_handlers": f"{_TARGET_PREFIX}.link_dialog_handlers",
    f"{_LEGACY_PREFIX}.link_dialog_signals": f"{_TARGET_PREFIX}.link_dialog_signals",
}

# handlers_mixins subpackage exposes multiple modules; map them individually
for name in (
    "file_dialog_mixin",
    "form_data_mixin",
    "hierarchy_mixin",
    "icons_mixin",
    "link_processing_mixin",
    "profiles_mixin",
    "type_change_mixin",
    "validation_mixin",
):
    _MODULE_ALIASES[
        f"{_LEGACY_PREFIX}.handlers_mixins.{name}"
    ] = f"{_TARGET_PREFIX}.handlers_mixins.{name}"


def _install_aliases() -> None:
    for legacy, target in _MODULE_ALIASES.items():
        if legacy in sys.modules:
            continue
        module = importlib.import_module(target)
        sys.modules.setdefault(legacy, module)


_install_aliases()

# Re-export primary classes/functions for convenience
from app.views.windows.dialogs.link_dialog.link_dialog import *  # noqa: F401,F403,E402
from app.views.windows.dialogs.link_dialog.link_dialog_ui import *  # noqa: F401,F403,E402
from app.views.windows.dialogs.link_dialog.link_dialog_handlers import *  # noqa: F401,F403,E402
from app.views.windows.dialogs.link_dialog.link_dialog_signals import *  # noqa: F401,F403,E402

__all__ = []  # populated dynamically by star-imports above
