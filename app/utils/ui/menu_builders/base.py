from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache


def get_menu_icon(name: str, theme: str, source: str = "context_menu"):
    """Return a themed menu icon through the shared menu icon pipeline.

    ``source`` remains explicit so different menu families can keep separate
    diagnostics while still using the same icon-resolution path.
    """
    return icon_cache.get_icon(name, theme, source)


def create_context_action(
    *,
    actions_builder: Any,
    main_window: Any,
    text: str,
    handler_name: str,
    shortcut: str | None,
    icon_name: str,
    state_attr: str,
    icon_getter: Callable[[str], Any],
):
    """Create a fresh context-menu action mirrored from the global action state."""
    action_controller = getattr(main_window, "action_controller", None)
    if action_controller is None:
        return None
    handler = getattr(action_controller, handler_name, None)
    if not callable(handler):
        return None

    action = actions_builder.create(
        text,
        handler,
        shortcut,
        icon_getter(icon_name),
    )

    state_action = getattr(main_window, state_attr, None)
    if state_action is not None and hasattr(state_action, "isEnabled"):
        try:
            action.setEnabled(bool(state_action.isEnabled()))
        except Exception:
            pass
    return action
