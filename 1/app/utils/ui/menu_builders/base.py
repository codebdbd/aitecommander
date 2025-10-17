from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache


def get_menu_icon(name: str, theme: str):
    """Return an icon for context menus considering the current theme.
    Centralized hook for caching and future changes.
    """
    return icon_cache.get_icon(name, theme, "context_menu")
