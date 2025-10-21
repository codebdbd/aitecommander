"""Compatibility wrapper for legacy imports.

The topbar utilities were moved to ``topbar.utils``.  Keep this thin module so
older code (including our regression tests) can continue importing
``app.views.main_components.ui.topbar.qt_utils`` without changes.
"""

from __future__ import annotations

from .utils.qt_utils import *  # noqa: F401,F403
