"""Compatibility package exposing legacy dialog imports.

This module re-exports dialog components from the new
`app.views.windows.dialogs` package to maintain backward compatibility
with older code and tests that import from `app.views.dialogs`.
"""

from app.views.windows.dialogs import *  # noqa: F401,F403
