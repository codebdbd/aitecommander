"""Совместимый слой для легаси-импорта `app.utils.ui.widget_utils`."""

from app.utils.ui.updates import suspend_updates  # noqa: F401

__all__ = ["suspend_updates"]
