# app/utils/ui/updates.py
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from app.interfaces import SupportsUpdates

logger = logging.getLogger(__name__)


@contextmanager
def suspend_updates(window: SupportsUpdates) -> Iterator[None]:
    """Temporarily disable widget/window updates for the duration of the `with` block.

    Example:
        with suspend_updates(self.window):
            ...  # heavy UI update operation

    Note:
        Errors when restoring updates (calling `setUpdatesEnabled(True)`) are not
        propagated but are logged at ERROR level for diagnostics. For already
        shown top-level windows updates are not disabled to avoid visual artifacts
        (e.g., phantom outline on maximize).
    """

    should_suspend = True
    try:
        is_window_fn = getattr(window, "isWindow", None)
        is_visible_fn = getattr(window, "isVisible", None)
        is_window = bool(is_window_fn()) if callable(is_window_fn) else False
        is_visible = bool(is_visible_fn()) if callable(is_visible_fn) else False
        if is_window and is_visible:
            should_suspend = False
    except Exception:
        # If the check fails, default to attempting to suspend updates
        should_suspend = True

    if not should_suspend:
        yield
        return

    window.setUpdatesEnabled(False)
    try:
        yield
    finally:
        try:
            window.setUpdatesEnabled(True)
        except Exception as exc:
            # Log to avoid losing information about a potentially "frozen" UI
            logger.error(
                "Failed to restore updates via setUpdatesEnabled(True): %s", exc
            )
